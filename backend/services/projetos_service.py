"""Gestor de Projetos (migração de `Geral\\frmgespro.frm`).

Um Projeto é um contêiner (cliente, responsável, datas, situação) ao qual
se vinculam documentos JÁ EXISTENTES — Pedido de Venda, O.S. e Requisição
— via a tabela de junção `projetos_documentos`. Um documento só pode
pertencer a um projeto no sistema inteiro (mesma regra do legado). Sem
tipo de documento "Orçamento" — ver CLAUDE.md > "Regras Globais de
Pré-venda": um Pedido com `situacao='A'` já cumpre esse papel.

A agregação de itens (Produtos/Serviços de todos os documentos vinculados)
é calculada AO VIVO por query a cada leitura — o legado materializa isso
numa tabela de staging (`itens_temp_projetos`) só porque precisava
preencher um grid VB6; aqui não há necessidade equivalente (ver "Não
replicar truques VB6" no CLAUDE.md).

Fase 2 (Ajustar Valores, `_ajustar_valores_sync`) — motor de redistribuição
de desconto/acréscimo entre os itens de Pedido/O.S. vinculados (nunca
Requisição — sem preço de venda ao cliente), pra bater um novo total-alvo
de Produtos ou Serviços. Simplificações deliberadas em relação ao legado
(ver PENDENCIAS.md > "Gestor de Projetos" > "Fase 2" pro detalhe completo
do rastreio): seleção só no nível de DOCUMENTO (não item individual dentro
de um documento — o próprio legado descarta essa seleção fina a cada troca
de documento marcado, então replicá-la não teria efeito prático real);
"Valores Já Faturados" usa a mesma definição já usada na Fase 1
(documentos com situação `PG`), não o rastreamento de NFe/NFSe por comanda
que o legado usa nesse cálculo específico (esta migração não tem esse
vínculo fiscal automático); e a redistribuição sempre reseta pro preço
BRUTO antes de aplicar o novo ajuste (mesmo comportamento do legado —
cada passada de "Ajustar Valores" é um recálculo do zero, não empilha em
cima de uma passada anterior).

Ver PENDENCIAS.md > "Gestor de Projetos" pro rastreio completo e plano de
fases.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.schemas import (
    ProjetosListRequest, ProjetoSaveRequest, ProjetoDocumentoRequest, FecharRequest,
    ProjetoAjustarValoresRequest,
)
from services.pedido_common import _modulo_gestor_projetos_ativo
from services.permissoes_service import tem_permissao
from services.os_itens_service import _recalc_os_total

# Situação do PRÓPRIO projeto — distinta de SITUACAO_LABEL (Pedido/O.S.,
# que usa "F"="Fechado"/tem "PG"). Projeto nunca fica "Faturado" (isso é
# por documento vinculado, não do projeto em si).
SITUACAO_PROJETO_LABEL = {"A": "Aberto", "F": "Finalizado", "C": "Cancelado"}

TIPOS_DOC = ("PED", "OSS", "REQ")
TIPO_DOC_LABEL = {"PED": "Pedido", "OSS": "O.S.", "REQ": "Requisição"}


def _ensure_projetos_tables(cur) -> None:
    """Migração idempotente — `projetos`/`projetos_documentos` já existem
    no schema legado (confirmado no dump de schema), mas o backend serve
    instalações independentes sem executor de migração central, então
    seguimos o mesmo padrão de `IF NOT EXISTS` já usado em todo o resto
    desta migração."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='projetos') "
        "CREATE TABLE projetos ("
        " codigo INT IDENTITY(1,1) PRIMARY KEY,"
        " data_abertura DATE,"
        " data_inicio DATE,"
        " data_prevista DATE,"
        " data_termino DATE,"
        " cliente INT DEFAULT 0,"
        " situacao NVARCHAR(1) DEFAULT 'A',"
        " valor_projeto FLOAT DEFAULT 0,"
        " valor_produtos FLOAT DEFAULT 0,"
        " valor_servicos FLOAT DEFAULT 0,"
        " responsavel INT DEFAULT 0,"
        " detalhes NVARCHAR(MAX),"
        " logs NVARCHAR(MAX)"
        ")"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='projetos_documentos') "
        "CREATE TABLE projetos_documentos ("
        " codauto INT IDENTITY(1,1) PRIMARY KEY,"
        " projeto INT DEFAULT 0,"
        " tipo_doc NVARCHAR(3) DEFAULT '',"
        " num_doc INT DEFAULT 0,"
        " data_inclusao DATE,"
        " incluido_por INT DEFAULT 0"
        ")"
    )


def _check_projeto_aberto(cur, codigo: int) -> tuple[bool, str]:
    """(existe, situacao) — situacao='' quando não encontrado."""
    cur.execute("SELECT situacao FROM projetos WHERE codigo=%s", (codigo,))
    row = cur.fetchone()
    if not row:
        return False, ""
    return True, (row.get("situacao") or "A").strip().upper()


def _list_projetos_sync(req: ProjetosListRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_projetos_tables(cur)
        where = ["1=1"]
        params: list = []
        term = (req.search or "").strip()
        if term:
            where.append("(c.nome LIKE %s OR c.fantasia LIKE %s)")
            params.extend([f"%{term}%", f"%{term}%"])
        sit = (req.situacao or "").strip().upper()
        if sit in ("A", "F", "C"):
            where.append("p.situacao=%s")
            params.append(sit)
        if req.responsavel:
            where.append("p.responsavel=%s")
            params.append(req.responsavel)
        where_sql = " AND ".join(where)

        cur.execute(f"SELECT COUNT(*) AS total FROM projetos p LEFT JOIN cliente c ON c.codigo=p.cliente WHERE {where_sql}", params)
        total = int((cur.fetchone() or {}).get("total") or 0)

        page = max(1, req.page or 1)
        size = max(1, min(200, req.size or 20))
        offset = (page - 1) * size
        cur.execute(
            "SELECT p.codigo, p.cliente, c.nome AS cliente_nome, p.responsavel, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS responsavel_nome, "
            "       p.data_abertura, p.data_prevista, p.situacao, "
            "       p.valor_produtos, p.valor_servicos, p.valor_projeto, "
            "       (SELECT MAX(pd.data_inclusao) FROM projetos_documentos pd WHERE pd.projeto=p.codigo) AS ultimo_vinculo "
            f"FROM projetos p LEFT JOIN cliente c ON c.codigo=p.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int=p.responsavel "
            f"WHERE {where_sql} ORDER BY p.codigo DESC "
            "OFFSET %s ROWS FETCH NEXT %s ROWS ONLY",
            params + [offset, size],
        )
        items = []
        for r in cur.fetchall():
            sit_p = (r.get("situacao") or "A").strip().upper()
            items.append({
                "codigo": int(r["codigo"]),
                "cliente": r.get("cliente"),
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "responsavel": r.get("responsavel"),
                "responsavel_nome": (r.get("responsavel_nome") or "").strip(),
                "data_abertura": r["data_abertura"].isoformat() if r.get("data_abertura") else None,
                "data_prevista": r["data_prevista"].isoformat() if r.get("data_prevista") else None,
                "situacao": sit_p,
                "situacao_label": SITUACAO_PROJETO_LABEL.get(sit_p, sit_p),
                "valor_produtos": float(r.get("valor_produtos") or 0),
                "valor_servicos": float(r.get("valor_servicos") or 0),
                "valor_projeto": float(r.get("valor_projeto") or 0),
                "ultimo_vinculo": r["ultimo_vinculo"].isoformat() if r.get("ultimo_vinculo") else None,
            })
        conn.close()
        return {"success": True, "items": items, "total": total}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


def _documentos_vinculados_sync(cur, codigo: int) -> list:
    """Documentos vinculados ao projeto — Pedido/O.S./Requisição, com
    situação e total resolvidos AO VIVO de cada tabela dona (nunca de uma
    coluna cacheada). Réplica de `CarregaProjeto`'s grade `Documentos`."""
    cur.execute(
        "SELECT 'PED' AS tipo_doc, pv.pedido AS num_doc, pd.data_inclusao, pv.situacao, "
        "       ISNULL(pv.total,0) AS total "
        "FROM projetos_documentos pd JOIN pedido_venda pv ON pv.pedido = pd.num_doc "
        "WHERE pd.projeto=%s AND pd.tipo_doc='PED' "
        "UNION ALL "
        "SELECT 'OSS', o.codigo, pd.data_inclusao, o.situacao, "
        "       ISNULL((SELECT SUM(quant*p_venda) FROM os_produto WHERE os=o.codigo AND ISNULL(item_cancelado,0)=0),0) "
        "FROM projetos_documentos pd JOIN os o ON o.codigo = pd.num_doc "
        "WHERE pd.projeto=%s AND pd.tipo_doc='OSS' "
        "UNION ALL "
        "SELECT 'REQ', r.codigo, pd.data_inclusao, r.situacao, "
        "       ISNULL((SELECT SUM(qtd*p_unit) FROM rec_prod WHERE requisicao=r.codigo),0) "
        "FROM projetos_documentos pd JOIN requisicao r ON r.codigo = pd.num_doc "
        "WHERE pd.projeto=%s AND pd.tipo_doc='REQ' "
        "ORDER BY data_inclusao",
        (codigo, codigo, codigo),
    )
    out = []
    for r in cur.fetchall():
        out.append({
            "tipo_doc": r["tipo_doc"],
            "tipo_doc_label": TIPO_DOC_LABEL.get(r["tipo_doc"], r["tipo_doc"]),
            "num_doc": int(r["num_doc"]),
            "data_inclusao": r["data_inclusao"].isoformat() if r.get("data_inclusao") else None,
            "situacao": (r.get("situacao") or "").strip(),
            "total": float(r.get("total") or 0),
        })
    return out


def _itens_agregados_sync(cur, codigo: int) -> dict:
    """Agregação Produtos/Serviços de todos os documentos vinculados —
    réplica de `CarregaItens`, mas calculada ao vivo (sem staging table) e
    distinguindo peça×serviço via existência em `pecas`/`servicos` (join
    real), não pelo prefixo de código do legado (`Left(codigo,1)='S'`) —
    ver "Não replicar truques VB6" no CLAUDE.md."""
    cur.execute(
        "SELECT pecas.codigo_fab, pecas.descricao, pvp.qtd_pedida AS qtd, "
        "       pvp.p_venda AS preco, pvp.custo_ped AS custo "
        "FROM pecas, projetos_documentos pd, pedido_venda pv, pedido_venda_prod pvp "
        "WHERE pecas.codigo_int = pvp.produto AND pd.projeto=%s AND pd.tipo_doc='PED' "
        "  AND pd.num_doc = pv.pedido AND pv.pedido = pvp.pedido "
        "UNION ALL "
        "SELECT pecas.codigo_fab, pecas.descricao, osp.quant, osp.p_venda, osp.custo_os "
        "FROM pecas, projetos_documentos pd, os o, os_produto osp "
        "WHERE pecas.codigo_int = osp.codigo_interno AND pd.projeto=%s AND pd.tipo_doc='OSS' "
        "  AND pd.num_doc = o.codigo AND o.codigo = osp.os "
        "UNION ALL "
        "SELECT pecas.codigo_fab, pecas.descricao, rp.qtd, rp.p_unit, rp.p_unit "
        "FROM pecas, projetos_documentos pd, requisicao r, rec_prod rp "
        "WHERE pecas.codigo_int = rp.prod AND pd.projeto=%s AND pd.tipo_doc='REQ' "
        "  AND pd.num_doc = r.codigo AND r.codigo = rp.requisicao",
        (codigo, codigo, codigo),
    )
    produtos = []
    total_custo_produtos = 0.0
    total_venda_produtos = 0.0
    for r in cur.fetchall():
        qtd = float(r.get("qtd") or 0)
        preco = float(r.get("preco") or 0)
        custo = float(r.get("custo") or 0)
        t_custo = round(qtd * custo, 2)
        t_venda = round(qtd * preco, 2)
        total_custo_produtos += t_custo
        total_venda_produtos += t_venda
        produtos.append({
            "codigo_fab": (r.get("codigo_fab") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "qtd": qtd, "preco_custo": custo, "preco_venda": preco,
            "total_custo": t_custo, "total_venda": t_venda,
        })

    cur.execute(
        "SELECT servicos.codigo AS codigo_fab, servicos.descricao, pvp.qtd_pedida AS qtd, "
        "       pvp.p_venda AS preco, pvp.custo_ped AS custo "
        "FROM servicos, projetos_documentos pd, pedido_venda pv, pedido_venda_prod pvp "
        "WHERE servicos.codigo = pvp.produto AND pd.projeto=%s AND pd.tipo_doc='PED' "
        "  AND pd.num_doc = pv.pedido AND pv.pedido = pvp.pedido "
        "UNION ALL "
        "SELECT servicos.codigo, servicos.descricao, osp.quant, osp.p_venda, osp.custo_os "
        "FROM servicos, projetos_documentos pd, os o, os_produto osp "
        "WHERE servicos.codigo = osp.codigo_interno AND pd.projeto=%s AND pd.tipo_doc='OSS' "
        "  AND pd.num_doc = o.codigo AND o.codigo = osp.os "
        "UNION ALL "
        "SELECT servicos.codigo, servicos.descricao, rp.qtd, rp.p_unit, rp.p_unit "
        "FROM servicos, projetos_documentos pd, requisicao r, rec_prod rp "
        "WHERE servicos.codigo = rp.prod AND pd.projeto=%s AND pd.tipo_doc='REQ' "
        "  AND pd.num_doc = r.codigo AND r.codigo = rp.requisicao",
        (codigo, codigo, codigo),
    )
    servicos = []
    total_custo_servicos = 0.0
    total_venda_servicos = 0.0
    for r in cur.fetchall():
        qtd = float(r.get("qtd") or 0)
        preco = float(r.get("preco") or 0)
        custo = float(r.get("custo") or 0)
        t_custo = round(qtd * custo, 2)
        t_venda = round(qtd * preco, 2)
        total_custo_servicos += t_custo
        total_venda_servicos += t_venda
        servicos.append({
            "codigo_fab": (r.get("codigo_fab") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "qtd": qtd, "preco_custo": custo, "preco_venda": preco,
            "total_custo": t_custo, "total_venda": t_venda,
        })

    return {
        "produtos": produtos,
        "servicos": servicos,
        "total_custo_produtos": round(total_custo_produtos, 2),
        "total_venda_produtos": round(total_venda_produtos, 2),
        "total_custo_servicos": round(total_custo_servicos, 2),
        "total_venda_servicos": round(total_venda_servicos, 2),
        "total_custo_geral": round(total_custo_produtos + total_custo_servicos, 2),
        "total_venda_geral": round(total_venda_produtos + total_venda_servicos, 2),
    }


def _faturado_saldo(documentos: list) -> dict:
    """Faturado vs. saldo a faturar — soma o total dos documentos
    vinculados que já estão PG (faturados) vs. os demais. Réplica da
    seção "Valores já faturados"/"Saldo a Faturar" do Resumo do legado.
    Recebe a lista já carregada por `_documentos_vinculados_sync` (não
    reconsulta) — evita rodar a mesma query 2x numa mesma leitura."""
    faturado = sum(d["total"] for d in documentos if d["situacao"] == "PG")
    total = sum(d["total"] for d in documentos)
    return {"faturado": round(faturado, 2), "saldo_a_faturar": round(total - faturado, 2)}


def _get_projeto_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_projetos_tables(cur)
        cur.execute(
            "SELECT p.*, c.nome AS cliente_nome, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS responsavel_nome "
            "FROM projetos p LEFT JOIN cliente c ON c.codigo=p.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int=p.responsavel "
            "WHERE p.codigo=%s",
            (codigo,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Projeto não encontrado."}
        sit = (row.get("situacao") or "A").strip().upper()
        documentos = _documentos_vinculados_sync(cur, codigo)
        itens = _itens_agregados_sync(cur, codigo)
        fat = _faturado_saldo(documentos)
        conn.close()
        return {
            "success": True,
            "projeto": {
                "codigo": int(row["codigo"]),
                "cliente": row.get("cliente"),
                "cliente_nome": (row.get("cliente_nome") or "").strip(),
                "responsavel": row.get("responsavel"),
                "responsavel_nome": (row.get("responsavel_nome") or "").strip(),
                "data_abertura": row["data_abertura"].isoformat() if row.get("data_abertura") else None,
                "data_inicio": row["data_inicio"].isoformat() if row.get("data_inicio") else None,
                "data_prevista": row["data_prevista"].isoformat() if row.get("data_prevista") else None,
                "data_termino": row["data_termino"].isoformat() if row.get("data_termino") else None,
                "situacao": sit,
                "situacao_label": SITUACAO_PROJETO_LABEL.get(sit, sit),
                "detalhes": (row.get("detalhes") or ""),
                "valor_produtos": float(row.get("valor_produtos") or 0),
                "valor_servicos": float(row.get("valor_servicos") or 0),
                "valor_projeto": float(row.get("valor_projeto") or 0),
                "documentos": documentos,
                "itens": itens,
                "faturado": fat["faturado"],
                "saldo_a_faturar": fat["saldo_a_faturar"],
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_projeto_sync(req: ProjetoSaveRequest, codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_projetos_tables(cur)
        if not _modulo_gestor_projetos_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Gestor de Projetos não está ativo."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PROJETOS", "GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para gravar Projeto."}

        data_inicio = req.data_inicio or None
        data_prevista = req.data_prevista or None
        detalhes = req.detalhes or ""
        # valor_projeto é sempre a soma — mesmo comportamento de
        # `Campo(7) = Campo(8) + Campo(9)` no `Campo_LostFocus` do legado,
        # nunca aceito direto do cliente.
        valor_produtos = round(float(req.valor_produtos or 0), 2)
        valor_servicos = round(float(req.valor_servicos or 0), 2)
        valor_projeto = round(valor_produtos + valor_servicos, 2)

        if codigo is None:
            cur.execute(
                "INSERT INTO projetos (data_abertura, data_inicio, data_prevista, cliente, situacao, "
                " responsavel, detalhes, valor_projeto, valor_produtos, valor_servicos) "
                "OUTPUT INSERTED.codigo "
                "VALUES (CAST(GETDATE() AS DATE), %s, %s, %s, 'A', %s, %s, %s, %s, %s)",
                (data_inicio, data_prevista, req.cliente, req.responsavel, detalhes,
                 valor_projeto, valor_produtos, valor_servicos),
            )
            novo = int(cur.fetchone()["codigo"])
            conn.commit()
            cur.close()
            conn.close()
            return {"success": True, "codigo": novo}
        else:
            cur.execute("SELECT situacao FROM projetos WHERE codigo=%s", (codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "Projeto não encontrado."}
            sit = (ex.get("situacao") or "A").strip().upper()
            if sit != "A":
                conn.close()
                label = SITUACAO_PROJETO_LABEL.get(sit, sit)
                return {"success": False, "message": f"Projeto '{label}' não pode ser alterado."}
            cur.execute(
                "UPDATE projetos SET data_inicio=%s, data_prevista=%s, cliente=%s, "
                " responsavel=%s, detalhes=%s, valor_projeto=%s, valor_produtos=%s, valor_servicos=%s "
                "WHERE codigo=%s",
                (data_inicio, data_prevista, req.cliente, req.responsavel, detalhes,
                 valor_projeto, valor_produtos, valor_servicos, codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Projeto não encontrado."}
            conn.commit()
            cur.close()
            conn.close()
            return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _transicao_situacao_sync(req: FecharRequest, codigo: int, de: tuple, para: str, mensagem_bloqueio: str) -> dict:
    """Helper comum a Finalizar/Reabrir/Cancelar — todas seguem o mesmo
    formato (situação atual precisa estar em `de`, permissão SITUACAO).

    Cancelar (`para='C'`) também DESVINCULA todos os documentos do
    projeto (`DELETE FROM projetos_documentos`) — confirmado em
    `Command10_Click` (`frmgespro.frm`): cancelar um projeto libera seus
    Pedidos/O.S./Requisições pra serem vinculados a outro projeto no
    futuro, em vez de ficarem presos a um projeto cancelado."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_projeto_aberto(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "Projeto não encontrado."}
        if sit not in de:
            conn.close()
            return {"success": False, "message": mensagem_bloqueio}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PROJETOS", "SITUACAO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para alterar a situação do Projeto."}
        if para == "C":
            cur.execute("DELETE FROM projetos_documentos WHERE projeto=%s", (codigo,))
            cur.execute("UPDATE projetos SET situacao='C' WHERE codigo=%s", (codigo,))
        elif para == "F":
            cur.execute("UPDATE projetos SET situacao='F', data_termino=CAST(GETDATE() AS DATE) WHERE codigo=%s", (codigo,))
        else:
            cur.execute("UPDATE projetos SET situacao=%s WHERE codigo=%s", (para, codigo))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "situacao": para, "situacao_antes": sit}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _finalizar_projeto_sync(req: FecharRequest, codigo: int) -> dict:
    return _transicao_situacao_sync(req, codigo, ("A",), "F", "Somente Projetos Abertos podem ser finalizados.")


def _reabrir_projeto_sync(req: FecharRequest, codigo: int) -> dict:
    return _transicao_situacao_sync(req, codigo, ("F",), "A", "Somente Projetos Finalizados podem ser reabertos.")


def _cancelar_projeto_sync(req: FecharRequest, codigo: int) -> dict:
    return _transicao_situacao_sync(req, codigo, ("A",), "C", "Somente Projetos Abertos podem ser cancelados.")


_TIPO_ACAO = {"PED": "ADD_PEDIDO", "OSS": "ADD_OS", "REQ": "ADD_REQUISICAO"}
_TIPO_TABELA = {"PED": ("pedido_venda", "pedido"), "OSS": ("os", "codigo"), "REQ": ("requisicao", "codigo")}


def _add_documento_sync(req: ProjetoDocumentoRequest, codigo: int, classe: Optional[int] = None, master: bool = False) -> dict:
    tipo_doc = (req.tipo_doc or "").strip().upper()
    if tipo_doc not in TIPOS_DOC:
        return {"success": False, "message": "Tipo de documento inválido."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_projetos_tables(cur)
        existe, sit = _check_projeto_aberto(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "Projeto não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": "Somente Projetos Abertos podem receber novos documentos."}
        if not master and classe is not None and not tem_permissao(cur, classe, "PROJETOS", _TIPO_ACAO[tipo_doc]):
            conn.close()
            return {"success": False, "message": "Sem permissão para vincular este tipo de documento."}

        tabela, pk = _TIPO_TABELA[tipo_doc]
        cur.execute(f"SELECT TOP 1 1 AS ok FROM {tabela} WHERE {pk}=%s", (req.num_doc,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": f"{TIPO_DOC_LABEL[tipo_doc]} não encontrado(a)."}

        cur.execute(
            "SELECT pd.projeto, c.nome AS cliente_nome FROM projetos_documentos pd "
            "JOIN projetos p ON p.codigo = pd.projeto LEFT JOIN cliente c ON c.codigo = p.cliente "
            "WHERE pd.tipo_doc=%s AND pd.num_doc=%s",
            (tipo_doc, req.num_doc),
        )
        conflito = cur.fetchone()
        if conflito:
            conn.close()
            return {
                "success": False,
                "message": (
                    f"Este documento já está vinculado ao Projeto nº {conflito['projeto']}"
                    f" do cliente {(conflito.get('cliente_nome') or '').strip()}."
                ),
            }

        cur.execute(
            "INSERT INTO projetos_documentos (projeto, tipo_doc, num_doc, data_inclusao, incluido_por) "
            "VALUES (%s, %s, %s, CAST(GETDATE() AS DATE), %s)",
            (codigo, tipo_doc, req.num_doc, req.usuario_alteracao or 0),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": f"{TIPO_DOC_LABEL[tipo_doc]} vinculado(a) com sucesso."}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao vincular documento: {e}"}


def _find_vinculo_sync(servidor: str, banco: str, tipo_doc: str, num_doc: int) -> dict:
    """Busca reversa documento→projeto — Fase 4 (recurso extra, sem
    equivalente no legado): usada pra mostrar um chip "Projeto #N" dentro
    da própria tela de Pedido/O.S. quando aquele documento já pertence a
    um Projeto, sem precisar abrir o Gestor de Projetos pra descobrir."""
    tipo_doc = (tipo_doc or "").strip().upper()
    if tipo_doc not in TIPOS_DOC:
        return {"success": False, "message": "Tipo de documento inválido."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_projetos_tables(cur)
        cur.execute(
            "SELECT pd.projeto, c.nome AS cliente_nome FROM projetos_documentos pd "
            "JOIN projetos p ON p.codigo = pd.projeto LEFT JOIN cliente c ON c.codigo = p.cliente "
            "WHERE pd.tipo_doc=%s AND pd.num_doc=%s",
            (tipo_doc, num_doc),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"success": True, "projeto": None}
        return {
            "success": True,
            "projeto": {"codigo": int(row["projeto"]), "cliente_nome": (row.get("cliente_nome") or "").strip()},
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _remove_documento_sync(req: ProjetoDocumentoRequest, codigo: int, classe: Optional[int] = None, master: bool = False) -> dict:
    tipo_doc = (req.tipo_doc or "").strip().upper()
    if tipo_doc not in TIPOS_DOC:
        return {"success": False, "message": "Tipo de documento inválido."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_projeto_aberto(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "Projeto não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": "Somente Projetos Abertos podem ter documentos removidos."}
        if not master and classe is not None and not tem_permissao(cur, classe, "PROJETOS", "REMOVER_DOC"):
            conn.close()
            return {"success": False, "message": "Sem permissão para remover documento do Projeto."}
        cur.execute(
            "DELETE FROM projetos_documentos WHERE projeto=%s AND tipo_doc=%s AND num_doc=%s",
            (codigo, tipo_doc, req.num_doc),
        )
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {"success": False, "message": "Vínculo não encontrado."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Documento removido do Projeto."}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao remover documento: {e}"}


# ==================== Fase 2 — Ajustar Valores ====================

def _itens_detalhados_sync(cur, codigo: int) -> list:
    """Itens (peças+serviços) de todos os documentos Pedido/O.S. vinculados
    (nunca Requisição — sem preço de venda ao cliente), com o tipo/número/
    situação do documento dono e o preço BRUTO (`p_normal`/`preco_unitario`
    — antes de desconto/acréscimo). Base compartilhada tanto do preview
    quanto da execução do Ajustar Valores — evita repetir a mesma consulta
    2x com pequenas variações."""
    cur.execute(
        "SELECT 'produto' AS categoria, pd.tipo_doc, pd.num_doc, pv.situacao AS situacao_doc, "
        "       pvp.codauto AS item_id, pvp.qtd_pedida AS qtd, pvp.p_normal AS preco_bruto "
        "FROM projetos_documentos pd JOIN pedido_venda pv ON pv.pedido = pd.num_doc "
        "JOIN pedido_venda_prod pvp ON pvp.pedido = pv.pedido "
        "JOIN pecas ON pecas.codigo_int = pvp.produto "
        "WHERE pd.projeto=%s AND pd.tipo_doc='PED' "
        "UNION ALL "
        "SELECT 'produto', pd.tipo_doc, pd.num_doc, o.situacao, "
        "       osp.cod_os_prod, osp.quant, osp.preco_unitario "
        "FROM projetos_documentos pd JOIN os o ON o.codigo = pd.num_doc "
        "JOIN os_produto osp ON osp.os = o.codigo "
        "JOIN pecas ON pecas.codigo_int = osp.codigo_interno "
        "WHERE pd.projeto=%s AND pd.tipo_doc='OSS' "
        "UNION ALL "
        "SELECT 'servico', pd.tipo_doc, pd.num_doc, pv.situacao, "
        "       pvp.codauto, pvp.qtd_pedida, pvp.p_normal "
        "FROM projetos_documentos pd JOIN pedido_venda pv ON pv.pedido = pd.num_doc "
        "JOIN pedido_venda_prod pvp ON pvp.pedido = pv.pedido "
        "JOIN servicos ON servicos.codigo = pvp.produto "
        "WHERE pd.projeto=%s AND pd.tipo_doc='PED' "
        "UNION ALL "
        "SELECT 'servico', pd.tipo_doc, pd.num_doc, o.situacao, "
        "       osp.cod_os_prod, osp.quant, osp.preco_unitario "
        "FROM projetos_documentos pd JOIN os o ON o.codigo = pd.num_doc "
        "JOIN os_produto osp ON osp.os = o.codigo "
        "JOIN servicos ON servicos.codigo = osp.codigo_interno "
        "WHERE pd.projeto=%s AND pd.tipo_doc='OSS'",
        (codigo, codigo, codigo, codigo),
    )
    out = []
    for r in cur.fetchall():
        out.append({
            "categoria": r["categoria"],
            "tipo_doc": r["tipo_doc"],
            "num_doc": int(r["num_doc"]),
            "situacao_doc": (r.get("situacao_doc") or "").strip().upper(),
            "item_id": int(r["item_id"]),
            "qtd": float(r.get("qtd") or 0),
            "preco_bruto": float(r.get("preco_bruto") or 0),
        })
    return out


def _ajuste_valores_preview_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Dados de apoio pra tela "Ajustar Valores": valor estimado do
    projeto (gravado no cabeçalho), valor já faturado (documentos com
    situação `PG` — mesma definição já usada no card "Itens do Projeto"
    da Fase 1), valor pendente (documentos Aberto/Fechado, ainda não
    faturados — o "Total dos DAV's selecionados" do legado quando tudo
    começa marcado) e a lista de documentos elegíveis pra reprocessar,
    cada um com seu total de Produtos/Serviços."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_projetos_tables(cur)
        cur.execute("SELECT valor_produtos, valor_servicos, valor_projeto FROM projetos WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Projeto não encontrado."}

        itens = _itens_detalhados_sync(cur, codigo)
        conn.close()

        def _soma(categoria: str, situacoes: tuple) -> float:
            return round(sum(
                i["qtd"] * i["preco_bruto"] for i in itens
                if i["categoria"] == categoria and i["situacao_doc"] in situacoes
            ), 2)

        faturado_produtos = _soma("produto", ("PG",))
        faturado_servicos = _soma("servico", ("PG",))
        pendente_produtos = _soma("produto", ("A", "F"))
        pendente_servicos = _soma("servico", ("A", "F"))

        docs: dict[tuple, dict] = {}
        for i in itens:
            if i["situacao_doc"] not in ("A", "F"):
                continue
            key = (i["tipo_doc"], i["num_doc"])
            d = docs.setdefault(key, {
                "tipo_doc": i["tipo_doc"], "tipo_doc_label": TIPO_DOC_LABEL.get(i["tipo_doc"], i["tipo_doc"]),
                "num_doc": i["num_doc"], "situacao": i["situacao_doc"],
                "total_produtos": 0.0, "total_servicos": 0.0,
            })
            valor = i["qtd"] * i["preco_bruto"]
            if i["categoria"] == "produto":
                d["total_produtos"] = round(d["total_produtos"] + valor, 2)
            else:
                d["total_servicos"] = round(d["total_servicos"] + valor, 2)

        documentos = sorted(docs.values(), key=lambda d: (d["tipo_doc"], d["num_doc"]))
        for d in documentos:
            d["total"] = round(d["total_produtos"] + d["total_servicos"], 2)

        estimado_produtos = float(row.get("valor_produtos") or 0)
        estimado_servicos = float(row.get("valor_servicos") or 0)

        return {
            "success": True,
            "estimado": {
                "produtos": estimado_produtos, "servicos": estimado_servicos,
                "geral": round(estimado_produtos + estimado_servicos, 2),
            },
            "faturado": {
                "produtos": faturado_produtos, "servicos": faturado_servicos,
                "geral": round(faturado_produtos + faturado_servicos, 2),
            },
            "pendente": {
                "produtos": pendente_produtos, "servicos": pendente_servicos,
                "geral": round(pendente_produtos + pendente_servicos, 2),
            },
            "saldo_orcamento": {
                "produtos": round(estimado_produtos - faturado_produtos - pendente_produtos, 2),
                "servicos": round(estimado_servicos - faturado_servicos - pendente_servicos, 2),
            },
            "documentos": documentos,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _ajustar_valores_sync(req: ProjetoAjustarValoresRequest, codigo: int) -> dict:
    """Motor de "Ajustar Valores" — migração de `Reprocessa`/
    `RecalculaDAVS`/`Descontos_Acrescimos` (`frmgespro.frm`). Redistribui
    desconto/acréscimo proporcionalmente entre os itens dos documentos
    SELECIONADOS (`req.documentos`) pra bater `req.novo_valor` de Produtos
    ou Serviços (`req.tipo`) — sempre reiniciando do preço BRUTO (mesmo
    comportamento do legado: cada passada é um recálculo do zero, não
    empilha em cima de um ajuste anterior)."""
    tipo = (req.tipo or "").strip().upper()
    if tipo not in ("P", "S"):
        return {"success": False, "message": "Tipo inválido — use 'P' (Produtos) ou 'S' (Serviços)."}
    if not req.novo_valor or req.novo_valor <= 0:
        return {"success": False, "message": "Informe um valor válido para o ajuste."}
    if not req.documentos:
        return {"success": False, "message": "Selecione ao menos um documento para reprocessar."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_projetos_tables(cur)
        existe, sit = _check_projeto_aberto(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "Projeto não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": "Somente Projetos Abertos podem ter valores reprocessados."}
        if not _modulo_gestor_projetos_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Gestor de Projetos não está ativo."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PROJETOS", "AJUSTAR_VALORES"):
            conn.close()
            return {"success": False, "message": "Sem permissão para ajustar valores do Projeto."}

        selecionados = {(d.tipo_doc.strip().upper(), d.num_doc) for d in req.documentos}
        categoria = "produto" if tipo == "P" else "servico"
        itens = [
            i for i in _itens_detalhados_sync(cur, codigo)
            if i["categoria"] == categoria
            and i["situacao_doc"] in ("A", "F")
            and (i["tipo_doc"], i["num_doc"]) in selecionados
        ]
        if not itens:
            conn.close()
            return {"success": False, "message": "Nenhum item elegível encontrado nos documentos selecionados."}

        total_atual = sum(i["qtd"] * i["preco_bruto"] for i in itens)
        if total_atual <= 0:
            conn.close()
            return {"success": False, "message": "Os itens selecionados não têm valor para redistribuir."}

        diferenca = round(req.novo_valor - total_atual, 2)
        if diferenca == 0:
            conn.close()
            return {"success": True, "message": "Valores já batem — nenhum ajuste necessário.", "total_atual": round(total_atual, 2)}

        percentual = diferenca / total_atual
        repartido = 0.0
        docs_afetados: set[tuple] = set()
        for idx, i in enumerate(itens):
            ajuste_unit = round(i["preco_bruto"] * percentual, 2)
            # Sobra de arredondamento inteira fica no último item — mesmo
            # espírito do "Aplica_Desc_Final"/"Aplica_Acresc_Final" do
            # legado (fecha o centavo que faltou na distribuição
            # proporcional), só que numa única passada final em vez de um
            # laço de R$0,01 por vez.
            if idx == len(itens) - 1:
                repartido_ate_aqui = round(repartido, 2)
                ajuste_unit = round((diferenca - repartido_ate_aqui) / i["qtd"], 2) if i["qtd"] else ajuste_unit
            novo_preco = round(i["preco_bruto"] + ajuste_unit, 2)
            desconto = max(0.0, round(-ajuste_unit, 2))
            acrescimo = max(0.0, round(ajuste_unit, 2))
            if i["tipo_doc"] == "PED":
                cur.execute(
                    "UPDATE pedido_venda_prod SET p_venda=%s, desconto=%s, acrescimo=%s WHERE codauto=%s",
                    (novo_preco, desconto, acrescimo, i["item_id"]),
                )
            else:
                cur.execute(
                    "UPDATE os_produto SET p_venda=%s, desconto=%s, acrescimo=%s WHERE cod_os_prod=%s",
                    (novo_preco, desconto, acrescimo, i["item_id"]),
                )
            repartido += ajuste_unit * i["qtd"]
            docs_afetados.add((i["tipo_doc"], i["num_doc"]))

        for tipo_doc, num_doc in docs_afetados:
            if tipo_doc == "PED":
                cur.execute(
                    "UPDATE pedido_venda SET total = ISNULL(("
                    "  SELECT SUM(qtd_pedida*p_venda) FROM pedido_venda_prod "
                    "  WHERE pedido=%s AND ISNULL(item_cancelado,0)=0), 0) WHERE pedido=%s",
                    (num_doc, num_doc),
                )
            else:
                # Correção deliberada em relação ao legado: `RecalculaDAVS`
                # recalcula o total de `orcamento`/`pedido_venda` mas
                # esquece de recalcular o de `os` — aqui os 2 tipos ficam
                # consistentes.
                _recalc_os_total(cur, num_doc)

        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True,
            "message": "Valores ajustados com sucesso.",
            "total_atual": round(total_atual, 2),
            "novo_valor": round(req.novo_valor, 2),
            "itens_ajustados": len(itens),
            "documentos_afetados": len(docs_afetados),
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao ajustar valores: {e}"}


async def ajuste_valores_preview(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_ajuste_valores_preview_sync, servidor, banco, codigo)


async def ajustar_valores(req: ProjetoAjustarValoresRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_ajustar_valores_sync, req, codigo)


async def list_projetos(req: ProjetosListRequest) -> dict:
    return await asyncio.to_thread(_list_projetos_sync, req)


async def get_projeto(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_projeto_sync, servidor, banco, codigo)


async def save_projeto(req: ProjetoSaveRequest, codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_projeto_sync, req, codigo)


async def finalizar_projeto(req: FecharRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_finalizar_projeto_sync, req, codigo)


async def reabrir_projeto(req: FecharRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_reabrir_projeto_sync, req, codigo)


async def cancelar_projeto(req: FecharRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_cancelar_projeto_sync, req, codigo)


def _resumo_projetos_sync(servidor: str, banco: str) -> dict:
    """Resumo pro card "Projetos" da Tela Principal — Fase 4 (recurso
    extra, sem equivalente no legado, implementado só sob confirmação
    explícita do usuário). Quantidade de Projetos Abertos + saldo a
    faturar agregado (soma do total de todos os documentos Pedido/O.S.
    vinculados a Projetos Abertos, exceto os já `PG`/faturados) — mesma
    definição de "saldo a faturar" já usada em `_faturado_saldo` (Fase 1),
    só que agregada por instalação inteira em vez de por projeto."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_projetos_tables(cur)
        if not _modulo_gestor_projetos_ativo(cur):
            conn.close()
            return {"success": True, "ativo": False, "total_abertos": 0, "saldo_a_faturar": 0.0}
        cur.execute("SELECT COUNT(*) AS total FROM projetos WHERE situacao='A'")
        total_abertos = int((cur.fetchone() or {}).get("total") or 0)
        cur.execute(
            "SELECT ISNULL(SUM(CASE WHEN doc.situacao='PG' THEN 0 ELSE doc.total END),0) AS saldo "
            "FROM projetos p "
            "JOIN ("
            "  SELECT pd.projeto, pv.situacao, ISNULL(pv.total,0) AS total "
            "  FROM projetos_documentos pd JOIN pedido_venda pv ON pv.pedido=pd.num_doc "
            "  WHERE pd.tipo_doc='PED' "
            "  UNION ALL "
            "  SELECT pd.projeto, o.situacao, "
            "         ISNULL((SELECT SUM(quant*p_venda) FROM os_produto "
            "                 WHERE os=o.codigo AND ISNULL(item_cancelado,0)=0),0) "
            "  FROM projetos_documentos pd JOIN os o ON o.codigo=pd.num_doc "
            "  WHERE pd.tipo_doc='OSS'"
            ") doc ON doc.projeto = p.codigo "
            "WHERE p.situacao='A'",
        )
        saldo = float((cur.fetchone() or {}).get("saldo") or 0)
        conn.close()
        return {"success": True, "ativo": True, "total_abertos": total_abertos, "saldo_a_faturar": round(saldo, 2)}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def resumo_projetos(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_resumo_projetos_sync, servidor, banco)


async def find_vinculo(servidor: str, banco: str, tipo_doc: str, num_doc: int) -> dict:
    return await asyncio.to_thread(_find_vinculo_sync, servidor, banco, tipo_doc, num_doc)


async def add_documento(req: ProjetoDocumentoRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_add_documento_sync, req, codigo, req.classe, bool(req.master))


async def remove_documento(req: ProjetoDocumentoRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_remove_documento_sync, req, codigo, req.classe, bool(req.master))

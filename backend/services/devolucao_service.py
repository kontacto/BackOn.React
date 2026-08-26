"""Gestor de Devolução — Fase 1 enxuta (migração de `Geral\\FrmManDev.frm`).

Escopo confirmado com o usuário via `AskUserQuestion` (2026-08-05), depois
de rastrear o `.frm` real: busca de itens de uma venda já PAGA (`comanda`/
`movimentacao`, mesma base já madura usada pelo Gestor de Comandas) +
registrar a devolução (`devolucao_itens`) + emitir opcionalmente um Vale de
Devolução (`vale_devolucao`, crédito ao cliente). **Fora desta fase**
(decisão explícita, não lacuna):

- **Emissão de NF de devolução**: no próprio legado, `FrmManDev.frm` NUNCA
  emite a NF sozinha — delega inteiramente pra `FrmTraNFe.ImportaDevolucao`
  (um subsistema fiscal à parte). Reproduzir isso ficaria pra quando/se
  pedido, reaproveitando o módulo Notas Fiscais.
- **Reposição física de estoque** (`pecas.qtd`): confirmado no código real
  do `.frm` que esta tela NUNCA toca em `pecas.qtd` — quem devolve estoque
  de verdade é outro caminho do legado (Recebimento de Mercadoria/
  `FrmConDev`, ao dar entrada na NF de devolução). Fiel a isso, esta
  migração também não mexe em estoque aqui.

`devolucao_itens.Status` NÃO é um estado de fluxo (pendente/concluído) —
confirmado contra dado real (GERDELL/BARESTELA): é o MOTIVO/tipo da
devolução (`devolucao_status`: 1="Devolução Normal", 2="Devolução por
Defeito"), escolhido por item ao registrar.

Simplificação registrada (ver PENDENCIAS.md > "Gestor de Devolução"): o
valor do item devolvido é `qtd_devolvida * p_unit`, sem o rateio de
frete/outras despesas/desconto que o legado aplica — `devolucao_itens`
grava `frete`/`outras`/`descontos` sempre 0 nesta fase.

**Reauditoria 2026-08-21** (ver PENDENCIAS.md > "🔴 FRENTE ATIVA" e
CLAUDE.md > "Toda ramificação condicional...") — 2 achados reais
corrigidos nesta rodada, ambos rastreados até a linha exata:
1. `_cliente_permitido_para_vale_sync` — "Devolução permitida somente
   para o proprio cliente da venda ou em nome da propria empresa!"
   (`FrmManDev.frm:1537-1540`) não estava implementada; o cliente do
   Vale era um campo livre sem validação nenhuma contra o cliente real
   da venda ou a lista `ClienteControle` (`Form_Load:2271-2287` —
   clientes cadastrados com o CNPJ da própria empresa).
2. Validação de "Data Final não pode ser maior que hoje" (`Critica`,
   `FrmManDev.frm:1054-1058`) não estava implementada na busca de itens."""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn, _to_json_safe
from services.comanda_service import _resolver_cliente_termo, _resolver_produto_termo
from services.permissoes_service import tem_permissao

TELA = "DEVOLUCAO"

MODULO_DESATIVADO_MSG = (
    "Módulo Gestor de Devolução está desativado em Configurações do Sistema > "
    "Módulos e Recursos. Ative-o para consultar ou lançar devoluções."
)


def _modulo_devolucao_ativo(cur) -> bool:
    cur.execute("SELECT TOP 1 devolucao FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("devolucao") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _list_motivos_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT Codigo AS codigo, Descricao AS descricao FROM devolucao_status ORDER BY Codigo")
        items = [_to_json_safe(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _list_itens_venda_sync(req) -> dict:
    """Busca itens de vendas PAGAS elegíveis pra devolução — réplica dos
    filtros de `FrmManDev.frm` (data/cupom/NFCe/NF/comanda/cliente/produto/
    valor unitário). Só devolve itens com saldo ainda não devolvido
    (`m.qtd` menos a soma já registrada em `devolucao_itens`), e nunca
    itens já estornados (`movimentacao.Estornado`)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_devolucao_ativo(cur):
            conn.close()
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}

        # Achado real (`Critica`, `FrmManDev.frm:1054-1058`): "A Data Final
        # deve ter Valor Máximo: DATESIST" — bloqueia buscar com Data Final
        # no futuro.
        if req.data_fim and req.data_fim > date.today().isoformat():
            conn.close()
            return {"success": False, "message": "A Data Final não pode ser maior que a data de hoje.", "items": []}

        where: list[str] = ["c.situacao = 'PG'", "m.serie_nf = 'CM'", "ISNULL(m.Estornado,0) = 0"]
        params: list = []

        if req.data_ini:
            where.append("c.data >= %s")
            params.append(req.data_ini)
        if req.data_fim:
            where.append("c.data <= %s")
            params.append(req.data_fim)
        if req.comanda is not None:
            where.append("c.comanda = %s")
            params.append(req.comanda)
        if req.cupom is not None:
            where.append("%s IN (SELECT cc.num_cupom FROM comanda_cupom cc WHERE cc.comanda = c.comanda)")
            params.append(req.cupom)
        if req.nfce is not None:
            where.append("%s IN (SELECT cn.num_nfce FROM comanda_nfce cn WHERE cn.comanda = c.comanda)")
            params.append(req.nfce)
        if req.nf is not None:
            where.append(
                "%s IN (SELECT nf.num_nf FROM comanda_nf AS cnf, n_fiscal AS nf "
                "WHERE cnf.nota_fisc = nf.codigo AND cnf.comanda = c.comanda)"
            )
            params.append(req.nf)
        if req.cliente:
            cod_cliente = _resolver_cliente_termo(cur, req.cliente)
            if cod_cliente is None:
                cur.close(); conn.close()
                return {"success": True, "items": []}
            where.append("c.cliente = %s")
            params.append(cod_cliente)
        if req.produto:
            cod_produto = _resolver_produto_termo(cur, req.produto)
            if cod_produto is None:
                cur.close(); conn.close()
                return {"success": True, "items": []}
            where.append("m.codigo_int = %s")
            params.append(cod_produto)
        if req.valor_de is not None:
            where.append("m.p_unit >= %s")
            params.append(req.valor_de)
        if req.valor_ate is not None:
            where.append("m.p_unit <= %s")
            params.append(req.valor_ate)

        where_sql = " AND ".join(where)
        cur.execute(
            f"SELECT m.id_mov, c.comanda, c.data, c.cliente, "
            f"ISNULL(cli.nome, 'CLIENTES DIVERSOS') AS cliente_nome, "
            f"m.codigo_int, ISNULL(NULLIF(p.descricao_pdv,''), p.descricao) AS descricao_p, s.descricao AS descricao_s, "
            f"m.qtd, m.p_unit, "
            f"ISNULL((SELECT SUM(d.Qtd_Devolvida) FROM devolucao_itens d WHERE d.CodMov = m.id_mov), 0) AS qtd_ja_devolvida "
            f"FROM comanda c "
            f"JOIN movimentacao m ON m.num_nf = c.comanda "
            f"LEFT JOIN cliente cli ON cli.codigo = c.cliente "
            f"LEFT JOIN pecas p ON p.codigo_int = m.codigo_int "
            f"LEFT JOIN servicos s ON s.codigo = m.codigo_int "
            f"WHERE {where_sql} "
            f"ORDER BY c.data DESC, m.id_mov DESC",
            tuple(params),
        )
        items = []
        for r in cur.fetchall():
            r = _to_json_safe(r) or {}
            qtd = float(r.get("qtd") or 0)
            qtd_ja_dev = float(r.get("qtd_ja_devolvida") or 0)
            qtd_disponivel = round(qtd - qtd_ja_dev, 4)
            if qtd_disponivel <= 0:
                continue
            items.append({
                "id_mov": int(r["id_mov"]),
                "comanda": int(r["comanda"]),
                "data": r.get("data"),
                "cliente": r.get("cliente"),
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "codigo": (r.get("codigo_int") or "").strip(),
                "descricao": (r.get("descricao_p") or r.get("descricao_s") or "").strip(),
                "qtd": qtd,
                "qtd_disponivel": qtd_disponivel,
                "p_unit": float(r.get("p_unit") or 0),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _cliente_permitido_para_vale_sync(cur, cliente_destino: int, cliente_venda) -> bool:
    """Achado real, `FrmManDev.frm:1537-1540` (`Command14_Click`) —
    "Devolução permitida somente para o proprio cliente da venda ou em
    nome da propria empresa!". `ClienteControle` (`Form_Load:2271-2287`)
    é a lista de `cliente.codigo` cujo `cgc_cpf` bate com `controle.cgc`
    (registros de cliente cadastrados com o CNPJ da própria empresa —
    usados quando a devolução é feita "em nome da empresa", não do
    cliente final). Reaproveitado aqui pro Vale de Devolução (a fonte só
    aplicava essa checagem dentro do fluxo combinado Vale+NFe, mas a
    regra em si — não deixar um Vale ir pra um cliente qualquer sem
    relação com a venda original — é de negócio real, não amarrada à
    emissão de NF em si)."""
    if cliente_venda is not None and int(cliente_destino) == int(cliente_venda):
        return True
    cur.execute(
        "SELECT 1 AS ok FROM cliente WHERE codigo=%s AND cgc_cpf = (SELECT TOP 1 cgc FROM controle)",
        (cliente_destino,),
    )
    return cur.fetchone() is not None


def _registrar_devolucao_sync(req) -> dict:
    """Registra a devolução de 1+ itens (`devolucao_itens`) e, se pedido,
    emite um Vale de Devolução agregando o valor total — réplica do fluxo
    real (marcar itens + perguntar se emite vale a cada operação),
    simplificado numa única ação pra esta fase."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_devolucao_ativo(cur):
            conn.close()
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "REGISTRAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para registrar devolução."}
        if not req.itens:
            conn.close()
            return {"success": False, "message": "Selecione ao menos um item para devolver."}
        if req.emitir_vale and not req.cliente:
            conn.close()
            return {"success": False, "message": "Informe o cliente para emitir o Vale de Devolução."}

        hoje = date.today()
        ids_devolucao: list[int] = []
        valor_total = 0.0
        for it in req.itens:
            cur.execute(
                "SELECT m.id_mov, m.qtd, m.p_unit, c.situacao, c.cliente AS cliente_venda, "
                "ISNULL(m.Estornado,0) AS estornado "
                "FROM movimentacao m JOIN comanda c ON c.comanda = m.num_nf "
                "WHERE m.id_mov=%s AND m.serie_nf='CM'",
                (it.id_mov,),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback(); conn.close()
                return {"success": False, "message": f"Item {it.id_mov} não encontrado."}
            if (row.get("situacao") or "").strip().upper() != "PG" or row.get("estornado"):
                conn.rollback(); conn.close()
                return {"success": False, "message": f"Item {it.id_mov} não está mais elegível para devolução."}
            if req.emitir_vale and not _cliente_permitido_para_vale_sync(cur, req.cliente, row.get("cliente_venda")):
                conn.rollback(); conn.close()
                return {
                    "success": False,
                    "message": "O Vale de Devolução só pode ser emitido para o próprio cliente da venda "
                               "ou em nome da própria empresa.",
                }
            cur.execute("SELECT ISNULL(SUM(Qtd_Devolvida),0) AS qtd FROM devolucao_itens WHERE CodMov=%s", (it.id_mov,))
            qtd_ja_dev = float(cur.fetchone()["qtd"] or 0)
            qtd_disponivel = float(row["qtd"] or 0) - qtd_ja_dev
            qtd_devolvida = float(it.qtd_devolvida or 0)
            if qtd_devolvida <= 0 or qtd_devolvida > qtd_disponivel + 0.0001:
                conn.rollback(); conn.close()
                return {
                    "success": False,
                    "message": f"Quantidade a devolver do item {it.id_mov} inválida "
                               f"(disponível: {qtd_disponivel}).",
                }
            valor_item = round(qtd_devolvida * float(row["p_unit"] or 0), 2)
            cur.execute(
                "INSERT INTO devolucao_itens (CodMov, Data, Nfe, Status, Qtd_Devolvida, vale_devolucao, "
                "frete, outras, descontos) "
                "OUTPUT INSERTED.id_devolucao "
                "VALUES (%s, %s, 0, %s, %s, 0, 0, 0, 0)",
                (it.id_mov, hoje, it.motivo, qtd_devolvida),
            )
            ids_devolucao.append(int(cur.fetchone()["id_devolucao"]))
            valor_total += valor_item

        vale_gerado = None
        if req.emitir_vale:
            cur.execute(
                "INSERT INTO vale_devolucao (cliente, valor, data, situacao, usuario) "
                "OUTPUT INSERTED.codvale VALUES (%s, %s, %s, 'A', %s)",
                (req.cliente, round(valor_total, 2), hoje, req.usuario_alteracao or 0),
            )
            vale_gerado = int(cur.fetchone()["codvale"])
            placeholders = ",".join(["%s"] * len(ids_devolucao))
            cur.execute(
                f"UPDATE devolucao_itens SET vale_devolucao=%s WHERE id_devolucao IN ({placeholders})",
                tuple([vale_gerado] + ids_devolucao),
            )

        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "ids_devolucao": ids_devolucao,
            "valor_total": round(valor_total, 2), "vale_devolucao": vale_gerado,
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao registrar devolução: {e}"}


def _list_devolucoes_sync(req) -> dict:
    """Consulta de devoluções já registradas — réplica simplificada de
    `FrmConDev.frm` (aqui, listando o que já foi gravado por esta tela, não
    o fluxo de vínculo via Recebimento de Mercadoria)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_devolucao_ativo(cur):
            conn.close()
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        where: list[str] = []
        params: list = []
        if req.data_ini:
            where.append("d.Data >= %s")
            params.append(req.data_ini)
        if req.data_fim:
            where.append("d.Data <= %s")
            params.append(req.data_fim)
        if req.cliente:
            cod_cliente = _resolver_cliente_termo(cur, req.cliente)
            if cod_cliente is None:
                cur.close(); conn.close()
                return {"success": True, "items": []}
            where.append("c.cliente = %s")
            params.append(cod_cliente)
        if req.comanda is not None:
            where.append("c.comanda = %s")
            params.append(req.comanda)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        cur.execute(
            f"SELECT d.id_devolucao, d.CodMov, d.Data, d.Qtd_Devolvida, d.vale_devolucao, d.Status, "
            f"c.comanda, ISNULL(cli.nome, 'CLIENTES DIVERSOS') AS cliente_nome, "
            f"ISNULL(NULLIF(p.descricao_pdv,''), p.descricao) AS descricao_p, s.descricao AS descricao_s, m.p_unit, "
            f"ds.Descricao AS motivo_descricao, v.situacao AS vale_situacao "
            f"FROM devolucao_itens d "
            f"JOIN movimentacao m ON m.id_mov = d.CodMov "
            f"JOIN comanda c ON c.comanda = m.num_nf "
            f"LEFT JOIN cliente cli ON cli.codigo = c.cliente "
            f"LEFT JOIN pecas p ON p.codigo_int = m.codigo_int "
            f"LEFT JOIN servicos s ON s.codigo = m.codigo_int "
            f"LEFT JOIN devolucao_status ds ON ds.Codigo = d.Status "
            f"LEFT JOIN vale_devolucao v ON v.codvale = d.vale_devolucao "
            f"{where_sql} "
            f"ORDER BY d.Data DESC, d.id_devolucao DESC",
            tuple(params),
        )
        items = []
        for r in cur.fetchall():
            r = _to_json_safe(r) or {}
            items.append({
                "id_devolucao": int(r["id_devolucao"]),
                "id_mov": int(r["CodMov"]),
                "comanda": int(r["comanda"]),
                "data": r.get("Data"),
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "descricao": (r.get("descricao_p") or r.get("descricao_s") or "").strip(),
                "qtd_devolvida": float(r.get("Qtd_Devolvida") or 0),
                "valor": round(float(r.get("Qtd_Devolvida") or 0) * float(r.get("p_unit") or 0), 2),
                "motivo": (r.get("motivo_descricao") or "").strip(),
                "vale_devolucao": int(r["vale_devolucao"]) if r.get("vale_devolucao") else None,
                "vale_situacao": (r.get("vale_situacao") or "").strip() or None,
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _cancelar_devolucao_sync(req, id_devolucao: int) -> dict:
    """Cancela um registro de devolução — réplica de "Excluir da fila
    cancela o Vale vinculado, se houver" (mesma regra do legado: reversão,
    não exclusão isolada)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_devolucao_ativo(cur):
            conn.close()
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "CANCELAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar devolução."}
        cur.execute("SELECT vale_devolucao, Nfe FROM devolucao_itens WHERE id_devolucao=%s", (id_devolucao,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Devolução não encontrada."}
        if row.get("Nfe"):
            conn.close()
            return {"success": False, "message": "Esta devolução já tem NF vinculada — não pode ser cancelada por aqui."}
        if row.get("vale_devolucao"):
            cur.execute("UPDATE vale_devolucao SET situacao='C' WHERE codvale=%s", (row["vale_devolucao"],))
        cur.execute("DELETE FROM devolucao_itens WHERE id_devolucao=%s", (id_devolucao,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar devolução: {e}"}


async def list_motivos(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_motivos_sync, servidor, banco)


async def list_itens_venda(req) -> dict:
    return await asyncio.to_thread(_list_itens_venda_sync, req)


async def registrar_devolucao(req) -> dict:
    return await asyncio.to_thread(_registrar_devolucao_sync, req)


async def list_devolucoes(req) -> dict:
    return await asyncio.to_thread(_list_devolucoes_sync, req)


async def cancelar_devolucao(req, id_devolucao: int) -> dict:
    return await asyncio.to_thread(_cancelar_devolucao_sync, req, id_devolucao)

"""Cadastros > Telemarketing.

Migração de `FrmManTMa.frm` (VB6, "TeleMarketing...") — gestor de
comunicação com o cliente: carrega um cliente, registra um novo contato
(texto + agendamento opcional) que é ACRESCENTADO em `cliente.historico`
(mesmo mecanismo de texto corrido já usado por outras partes do sistema —
inclusive os logs automáticos de envio por WhatsApp, ver
`services/whatsapp/repository.py::registrar_envio_whatsapp_no_historico`),
e permite selecionar clientes por uma lista extensa de filtros.

**Decisão confirmada pelo usuário (2026-07-12)**: NÃO existe tabela
`telemarketing` — "Telemarketing" é o nome da tela/funcionalidade, não uma
tabela literal. Tudo grava em `cliente` (historico, ultimo_contato,
DATA_AGENDAMENTO_TELEMARKETING, FUNCIONARIO_AGENDAMENTO_TELEMARKETING) —
exatamente como o `.frm` original (conferido ao vivo: essas colunas já
existem em `cliente`, tabela `telemarketing` não existe).

Fora de escopo (ver PENDENCIAS.md):
  • `Pos_Sistema` (mesma pendência já registrada em Equipamentos) — não
    implementado, arquitetura nova é stateless.
  • Botões "Ranking de Vendas" (`FrmRkgCliPro`) e "Vendas" (`FrmConCupom`)
    — telas legadas ainda não migradas pra este sistema novo.
  • "Inatividade de Clientes" (`FrmRelCliSMV`) — idem.
  • Filtro "Categoria" (`Cmb(7)` no `.frm`) — declarado na tela mas NUNCA
    usado na query de fato (`Command8_Click` não referencia `Cmb(7)`) —
    campo morto do próprio legado, não implementado aqui.
  • Filtro "Endereço" (`Camp(4)`) — mesmo caso: existe na tela mas nunca é
    aplicado na query (só "Bairro"/`Camp(5)` é usado de fato no legado).
  • "CarteiraVendedor" (restrição de quais vendedores aparecem no filtro,
    por usuário logado, via `funcionarios_carteiras`) — não implementado;
    o filtro de Vendedor aqui mostra todos os funcionários.

Melhoria técnica (não é regra de negócio): a query de seleção de clientes
usa `LEFT JOIN dia_semana` em vez do `UNION ALL` que o legado usava (uma
branch com JOIN normal em `dia_contato` + uma segunda branch idêntica só
pra cobrir clientes com `dia_contato` nulo/zero, contornando um INNER
JOIN) — resultado idêntico, sem duplicar a query inteira. A 2ª branch do
legado também tinha um bug real (reaproveitava `Camp(2)`, um campo de
data, como filtro `historico LIKE '%data%'`) — não replicado.
"""
import asyncio
from datetime import datetime
from typing import Optional

from db.connection import _open_conn


def _iso_to_ddmmaaaa(iso: Optional[str]) -> str:
    """'2026-07-17' -> '17-07-2026' — formato pedido pelo usuário pra
    exibição da data de agendamento dentro do texto do histórico (o
    valor cru vindo do <input type=date> do frontend é ISO)."""
    if not iso:
        return ""
    partes = iso.split("-")
    if len(partes) != 3:
        return iso
    ano, mes, dia = partes
    return f"{dia}-{mes}-{ano}"


def _resolve_nome_funcionario(cur, usuario_id: Optional[int]) -> str:
    if not usuario_id:
        return "Sistema"
    cur.execute("SELECT nome_guerra FROM funcionarios WHERE codigo_int=%s", (usuario_id,))
    row = cur.fetchone()
    if row and row.get("nome_guerra"):
        return row["nome_guerra"].strip()
    return "Sistema"


def _get_cliente_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT c.codigo, c.nome, c.fantasia, c.cgc_cpf, c.data, c.e_mail, c.contato, "
            "c.ultimo_contato, c.historico, c.dia_contato, "
            "c.DATA_AGENDAMENTO_TELEMARKETING AS data_agendamento, "
            "LTRIM(RTRIM(ISNULL(CAST(c.ddd_cli AS NVARCHAR(4)),'') + ISNULL(c.telefone_cli,''))) AS telefone, "
            "(SELECT rotas.descricao FROM rotas WHERE rotas.codigo = c.rota) AS rota_nome, "
            "(SELECT regioes.descricao FROM regioes WHERE regioes.codigo = c.regiao) AS regiao_nome, "
            "(SELECT segmentos.descricao FROM segmentos WHERE segmentos.codigo = c.segmento) AS segmento_nome, "
            "(SELECT tipo_cliente.descricao FROM tipo_cliente WHERE tipo_cliente.codigo = c.cliente_forn) AS tipo_cliente_nome, "
            "(SELECT f.nome_guerra FROM funcionarios f WHERE f.codigo_int = c.FUNCIONARIO_AGENDAMENTO_TELEMARKETING) AS funcionario_agendamento_nome, "
            "(SELECT TOP 1 endereco + ' - ' + bairro + ' - ' + cidade + ' - ' + uf FROM cliente_end "
            " WHERE cliente_end.codigo=c.codigo AND cliente_end.tipo=0) AS endereco "
            "FROM cliente c WHERE c.codigo=%s",
            (codigo,),
        )
        r = cur.fetchone()
        cur.close()
        if not r:
            return {"success": False, "message": "Cliente não encontrado."}
        return {
            "success": True,
            "codigo": int(r["codigo"]),
            "nome": (r.get("nome") or "").strip(),
            "fantasia": (r.get("fantasia") or "").strip(),
            "cgc_cpf": (r.get("cgc_cpf") or "").strip(),
            "data_cadastro": r["data"].isoformat() if r.get("data") else None,
            "e_mail": (r.get("e_mail") or "").strip(),
            "contato": (r.get("contato") or "").strip(),
            "telefone": (r.get("telefone") or "").strip(),
            "ultimo_contato": r["ultimo_contato"].isoformat() if r.get("ultimo_contato") else None,
            "historico": r.get("historico") or "",
            "dia_contato": r.get("dia_contato"),
            "data_agendamento": r["data_agendamento"].isoformat() if r.get("data_agendamento") else None,
            "endereco": (r.get("endereco") or "").strip(),
            "rota_nome": (r.get("rota_nome") or "").strip() or None,
            "regiao_nome": (r.get("regiao_nome") or "").strip() or None,
            "segmento_nome": (r.get("segmento_nome") or "").strip() or None,
            "tipo_cliente_nome": (r.get("tipo_cliente_nome") or "").strip() or None,
            "funcionario_agendamento_nome": (r.get("funcionario_agendamento_nome") or "").strip() or None,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _save_contato_sync(
    servidor: str, banco: str, cliente_codigo: int, texto: str,
    agendamento: Optional[str], usuario_id: Optional[int],
) -> dict:
    texto_v = (texto or "").strip()
    if not cliente_codigo:
        return {"success": False, "message": "Selecione um cliente corretamente."}
    if not texto_v:
        return {"success": False, "message": "Digite o texto do contato."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT historico FROM cliente WHERE codigo=%s", (cliente_codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Cliente não encontrado."}
        antigo = row.get("historico") or ""
        nome_usuario = _resolve_nome_funcionario(cur, usuario_id)
        agora = datetime.now()
        cabecalho = f"{agora.strftime('%d/%m/%Y')} {agora.strftime('%H:%M:%S')} (Adicionado por {nome_usuario})"
        linha_agendamento = f"\r\nContato agendado para o dia {_iso_to_ddmmaaaa(agendamento)}." if agendamento else ""
        nova_entrada = f"{cabecalho}\r\n{texto_v}{linha_agendamento}"
        novo_historico = f"{nova_entrada}\r\n{antigo}" if antigo.strip() else nova_entrada

        cur.execute(
            "UPDATE cliente SET historico=%s, ultimo_contato=CAST(GETDATE() AS DATE) WHERE codigo=%s",
            (novo_historico, cliente_codigo),
        )
        if agendamento:
            cur.execute(
                "UPDATE cliente SET DATA_AGENDAMENTO_TELEMARKETING=%s, "
                "FUNCIONARIO_AGENDAMENTO_TELEMARKETING=%s WHERE codigo=%s",
                (agendamento, usuario_id, cliente_codigo),
            )
        else:
            cur.execute(
                "UPDATE cliente SET DATA_AGENDAMENTO_TELEMARKETING=NULL, "
                "FUNCIONARIO_AGENDAMENTO_TELEMARKETING=%s WHERE codigo=%s",
                (usuario_id, cliente_codigo),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Histórico gravado.", "historico": novo_historico}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _list_selecionar_sync(servidor: str, banco: str, f: dict) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ["1=1"]
        params: list = []
        if f.get("dia_contato") is not None:
            where.append("c.dia_contato = %s"); params.append(f["dia_contato"])
        if f.get("dia_entrega") is not None:
            where.append("c.dia_entrega = %s"); params.append(f["dia_entrega"])
        if f.get("vendedor") is not None:
            where.append("c.vendedor = %s"); params.append(f["vendedor"])
        if f.get("regiao") is not None:
            where.append("c.regiao = %s"); params.append(f["regiao"])
        if f.get("segmento"):
            where.append("c.segmento = %s"); params.append(f["segmento"])
        if f.get("rota") is not None:
            where.append("c.rota = %s"); params.append(f["rota"])
        if f.get("tipo_cliente") is not None:
            where.append("c.cliente_forn = %s"); params.append(f["tipo_cliente"])
        if f.get("situacao"):
            where.append("c.situacao = %s"); params.append(f["situacao"])
        termo = (f.get("cliente_termo") or "").strip()
        if termo:
            if termo.isdigit():
                where.append("c.codigo = %s"); params.append(int(termo))
            else:
                # Busca por nome também bate no nome fantasia — [GLOBAL] em
                # toda busca de cliente do sistema, pedido explícito do
                # usuário, 2026-07-18.
                where.append("(c.nome LIKE %s OR c.fantasia LIKE %s)")
                like_termo = f"%{termo}%"
                params.extend([like_termo, like_termo])
        if f.get("cgc_cpf"):
            where.append("c.cgc_cpf LIKE %s"); params.append(f"%{f['cgc_cpf'].strip()}%")
        if f.get("bairro"):
            where.append("c.codigo IN (SELECT ce.codigo FROM cliente_end ce WHERE ce.bairro LIKE %s)")
            params.append(f"%{f['bairro'].strip()}%")
        if f.get("ultimo_contato_de"):
            where.append("c.ultimo_contato >= %s"); params.append(f["ultimo_contato_de"])
        if f.get("ultimo_contato_ate"):
            where.append("c.ultimo_contato <= %s"); params.append(f["ultimo_contato_ate"])
        if f.get("agendamento_de"):
            where.append("c.DATA_AGENDAMENTO_TELEMARKETING >= %s"); params.append(f["agendamento_de"])
        if f.get("agendamento_ate"):
            where.append("c.DATA_AGENDAMENTO_TELEMARKETING <= %s"); params.append(f["agendamento_ate"])
        where_sql = " AND ".join(where)
        order_sql = "c.nome, c.ultimo_contato DESC" if f.get("ordenar_por") == "cliente" else "c.ultimo_contato, c.nome"

        cur.execute(
            "SELECT c.codigo, c.nome, c.fantasia, c.contato, c.ultimo_contato, c.dia_contato, c.dia_entrega, "
            "c.DATA_AGENDAMENTO_TELEMARKETING AS data_agendamento, "
            "LTRIM(RTRIM(ISNULL(CAST(c.ddd_cli AS NVARCHAR(4)),'') + ISNULL(c.telefone_cli,''))) AS telefone, "
            "(SELECT ds.descricao FROM dia_semana ds WHERE ds.dia = c.dia_contato) AS dia_contato_nome, "
            "(SELECT ds2.descricao FROM dia_semana ds2 WHERE ds2.dia = c.dia_entrega) AS dia_entrega_nome, "
            "(SELECT fu.nome_guerra FROM funcionarios fu WHERE fu.codigo_int = c.FUNCIONARIO_AGENDAMENTO_TELEMARKETING) AS funcionario_agendamento_nome "
            f"FROM cliente c WHERE {where_sql} ORDER BY {order_sql}",
            tuple(params),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "nome": (r.get("nome") or "").strip(),
            "fantasia": (r.get("fantasia") or "").strip(),
            "contato": (r.get("contato") or "").strip(),
            "telefone": (r.get("telefone") or "").strip(),
            "ultimo_contato": r["ultimo_contato"].isoformat() if r.get("ultimo_contato") else None,
            "dia_contato_nome": (r.get("dia_contato_nome") or "").strip() or None,
            "dia_entrega_nome": (r.get("dia_entrega_nome") or "").strip() or None,
            "data_agendamento": r["data_agendamento"].isoformat() if r.get("data_agendamento") else None,
            "funcionario_agendamento_nome": (r.get("funcionario_agendamento_nome") or "").strip() or None,
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def get_cliente(servidor, banco, codigo):
    return await asyncio.to_thread(_get_cliente_sync, servidor, banco, codigo)


async def save_contato(servidor, banco, cliente_codigo, texto, agendamento, usuario_id):
    return await asyncio.to_thread(_save_contato_sync, servidor, banco, cliente_codigo, texto, agendamento, usuario_id)


async def list_selecionar(servidor, banco, filtros):
    return await asyncio.to_thread(_list_selecionar_sync, servidor, banco, filtros)

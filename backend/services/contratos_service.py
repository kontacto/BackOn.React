"""Módulo Contratos (Transações > Contratos) — Fase A da migração de
`FrmManTPC.frm`/`FrmManRea.frm`/`FrmManInd.frm`/`FrmConPDI.frm`/
`FrmManContra.frm` (ver CLAUDE.md/PENDENCIAS.md), mais o motor de
faturamento (`FrmFatContrato2.frm`/`FrmFatContrato.frm`) adicionado
2026-07-20. Envio de Cobrança (`FrmEnvCob.frm`) continua fora de escopo —
motor de remessa bancária CNAB/e-mail em massa, pendência separada.

- tipo_contrato / prazo_reajuste / indice_reajuste: cadastros simples
  codigo+descricao, mesmo padrão de `tabelas_aux_service.tipo_cliente`.
- contratos_produtos_disponiveis: catálogo de produtos/equipamentos/
  serviços/cilindros liberados para uso em contrato, com qtd/qtd_alocada.
- contratos / contratos_produtos / contratos_centro_custo /
  contratos_preco / contratos_cred_deb: contrato em si — dados principais,
  itens, rateio por centro de custo, histórico de reajuste de valor e
  lançamentos de acréscimo/desconto.
- Faturar Contratos (ver seção própria abaixo): seleção de contratos por
  período com cálculo pró-rata, faturamento (grava comanda/Receber/
  Duplicata_Receber — o modelo de faturamento REAL do legado, decisão
  explícita do usuário 2026-07-20 de manter fidelidade em vez de migrar
  pra pedido_venda) e geração de Recibo. Nota Fiscal (emissão fiscal real)
  e Boleto (layout bancário) ficam fora desta rodada — ver PENDENCIAS.md.

Reajuste automático por índice (IGPM/IPCA) — feature NOVA, sem
equivalente no VB6 (que só permitia digitar o valor/percentual na mão):
consulta a API pública do Banco Central (SGS, sem autenticação, mesmo
princípio já usado no app pra ViaCEP) e sugere o percentual acumulado do
período pro usuário confirmar antes de gravar — nunca aplica sozinho.
"""
import asyncio
import calendar
import json
import urllib.request
from datetime import date, datetime, timedelta
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc
from services.pedido_common import _modulo_contratos_ativo

_MODULO_OFF_MSG = "Módulo Contratos está desativado — fale com o administrador em Configurações > Módulos e Recursos."

BACEN_SGS_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
# Séries oficiais do SGS/BACEN — variação MENSAL (não acumulada), verificadas
# 2026-07-19: IGP-M (FGV) = 189, IPCA (IBGE) = 433. Não existe série dedicada
# de "IGP-M acumulado 12 meses" no SGS — o acumulado do período é calculado
# aqui compondo as variações mensais (juros compostos), não uma soma simples.
INDICES_BACEN = {
    "IGPM": 189,
    "IGP-M": 189,
    "IPCA": 433,
}


# ==================== Helpers ====================

def _row_dict(r: dict) -> dict:
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}


def _iso(d) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    return str(d)


# ==================== Tipo de Contrato / Tipo de Reajuste / Índice de Reajuste ====================
# Três cadastros idênticos em formato (codigo smallint gerado por MAX+1,
# descricao) — mesmo padrão de `tabelas_aux_service._*_tipo_cliente_sync`.

def _list_lookup_sync(servidor: str, banco: str, tabela: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM {tabela} {where} ORDER BY descricao", params)
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_lookup_sync(servidor: str, banco: str, tabela: str, codigo: Optional[int], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        sz = _get_col_sizes(conn, banco, tabela)
        desc_v = _trunc(desc, sz, "descricao", 30)
        if codigo is not None:
            cur.execute(f"UPDATE {tabela} SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Registro não encontrado."}
            novo = codigo
        else:
            cur.execute(f"SELECT ISNULL(MAX(codigo), 0) + 1 AS novo FROM {tabela}")
            novo = int(cur.fetchone()["novo"])
            cur.execute(f"INSERT INTO {tabela} (codigo, descricao) VALUES (%s,%s)", (novo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Registro gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_lookup_sync(servidor: str, banco: str, tabela: str, coluna_fk: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute(f"SELECT TOP 1 1 AS ok FROM contratos WHERE {coluna_fk}=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Registro vinculado a contrato(s) — não pode ser excluído."}
        cur.execute(f"DELETE FROM {tabela} WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tipo_contrato(servidor, banco, search=""):
    return await asyncio.to_thread(_list_lookup_sync, servidor, banco, "tipo_contrato", search)


async def save_tipo_contrato(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_lookup_sync, servidor, banco, "tipo_contrato", codigo, descricao)


async def delete_tipo_contrato(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_lookup_sync, servidor, banco, "tipo_contrato", "tipo_contrato", codigo)


async def list_tipo_reajuste(servidor, banco, search=""):
    return await asyncio.to_thread(_list_lookup_sync, servidor, banco, "prazo_reajuste", search)


async def save_tipo_reajuste(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_lookup_sync, servidor, banco, "prazo_reajuste", codigo, descricao)


async def delete_tipo_reajuste(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_lookup_sync, servidor, banco, "prazo_reajuste", "tipo_reajuste", codigo)


async def list_indice_reajuste(servidor, banco, search=""):
    return await asyncio.to_thread(_list_lookup_sync, servidor, banco, "indice_reajuste", search)


async def save_indice_reajuste(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_lookup_sync, servidor, banco, "indice_reajuste", codigo, descricao)


async def delete_indice_reajuste(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_lookup_sync, servidor, banco, "indice_reajuste", "indice_reajuste", codigo)


# ==================== Resolver de Produto/Equipamento/Cilindro/Serviço ====================
# Réplica de `Campo_LostFocus(0)` de FrmConPDI/`Campo_LostFocus(12)` de
# FrmManContra — cascata Cilindro -> Equipamentos -> Peças
# (codigo_int/codigo_fab/codigo_bar) -> Serviços. Não existe hoje um
# resolver compartilhado que cubra as 4 tabelas (o `_resolve_produto` de
# `pedido_common.py` só cobre peças/serviços) — implementado aqui de novo,
# escopo próprio deste módulo.
def _resolve_produto_contrato_sync(cur, termo: str) -> Optional[dict]:
    t = (termo or "").strip()
    if not t:
        return None
    if t.isdigit():
        cur.execute("SELECT Cod AS interno, Descricao AS vdescricao FROM Cilindro WHERE Cod=%s", (int(t),))
        r = cur.fetchone()
        if r:
            return {"tipo": "CILINDRO", "codigo": str(r["interno"]), "descricao": (r["vdescricao"] or "").strip()}
    cur.execute("SELECT Cod AS interno, Descricao AS vdescricao FROM Cilindro WHERE Codigo=%s", (t,))
    r = cur.fetchone()
    if r:
        return {"tipo": "CILINDRO", "codigo": str(r["interno"]), "descricao": (r["vdescricao"] or "").strip()}
    cur.execute(
        "SELECT numero_de_serie AS interno, descricao_equipamento AS vdescricao FROM equipamentos WHERE numero_de_serie=%s",
        (t,),
    )
    r = cur.fetchone()
    if r:
        return {"tipo": "EQUIPAMENTO", "codigo": str(r["interno"]).strip(), "descricao": (r["vdescricao"] or "").strip()}
    for col in ("codigo_int", "codigo_fab", "codigo_bar"):
        cur.execute(f"SELECT codigo_int AS interno, descricao AS vdescricao FROM pecas WHERE {col}=%s", (t,))
        r = cur.fetchone()
        if r:
            return {"tipo": "PRODUTO", "codigo": str(r["interno"]).strip(), "descricao": (r["vdescricao"] or "").strip()}
    cur.execute("SELECT codigo AS interno, descricao AS vdescricao FROM servicos WHERE codigo=%s", (t,))
    r = cur.fetchone()
    if r:
        return {"tipo": "SERVICO", "codigo": str(r["interno"]).strip(), "descricao": (r["vdescricao"] or "").strip()}
    return None


def _resolver_produto_sync(servidor: str, banco: str, termo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        r = _resolve_produto_contrato_sync(cur, termo)
        cur.close()
        if not r:
            return {"success": False, "message": "Produto, Equipamento, Serviço ou Cilindro não cadastrado."}
        return {"success": True, **r}
    finally:
        conn.close()


async def resolver_produto(servidor, banco, termo):
    return await asyncio.to_thread(_resolver_produto_sync, servidor, banco, termo)


# ==================== Produtos Disponíveis (contratos_produtos_disponiveis) ====================

def _list_produtos_disponiveis_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE produto LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(
            f"SELECT produto, preco, qtd, qtd_alocada, situacao, obs FROM contratos_produtos_disponiveis {where} ORDER BY produto",
            params,
        )
        rows = cur.fetchall()
        cur.close()
        items = []
        for r in rows:
            desc = None
            info = _resolve_produto_contrato_sync(conn.cursor(as_dict=True), r["produto"])
            if info:
                desc = info["descricao"]
            items.append({
                "produto": (r["produto"] or "").strip(),
                "descricao": desc,
                "preco": float(r["preco"] or 0),
                "qtd": float(r["qtd"] or 0),
                "qtd_alocada": float(r["qtd_alocada"] or 0),
                "situacao": (r.get("situacao") or "A").strip(),
                "obs": (r.get("obs") or "").strip(),
            })
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_produto_disponivel_sync(servidor: str, banco: str, produto: str, preco: float, qtd: float, situacao: str, obs: str) -> dict:
    prod = (produto or "").strip().upper()
    if not prod:
        return {"success": False, "message": "Informe o Produto/Equipamento."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        info = _resolve_produto_contrato_sync(cur, prod)
        if not info:
            return {"success": False, "message": "Produto, Equipamento, Serviço ou Cilindro não cadastrado."}
        prod = info["codigo"]
        sz = _get_col_sizes(conn, banco, "contratos_produtos_disponiveis")
        obs_v = _trunc((obs or "").strip(), sz, "obs", 500)
        cur.execute("SELECT TOP 1 1 AS ok FROM contratos_produtos_disponiveis WHERE produto=%s", (prod,))
        existe = cur.fetchone() is not None
        sit = (situacao or "A").strip()[:1].upper() or "A"
        if existe:
            cur.execute(
                "UPDATE contratos_produtos_disponiveis SET preco=%s, qtd=%s, situacao=%s, obs=%s WHERE produto=%s",
                (preco, qtd, sit, obs_v, prod),
            )
        else:
            cur.execute(
                "INSERT INTO contratos_produtos_disponiveis (produto, preco, qtd, qtd_alocada, situacao, obs) VALUES (%s,%s,%s,0,%s,%s)",
                (prod, preco, qtd, sit, obs_v),
            )
        conn.commit()
        cur.close()
        return {"success": True, "produto": prod, "descricao": info["descricao"], "message": "Registro gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_produto_disponivel_sync(servidor: str, banco: str, produto: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT qtd_alocada FROM contratos_produtos_disponiveis WHERE produto=%s", (produto,))
        r = cur.fetchone()
        if not r:
            return {"success": False, "message": "Produto/Equipamento não cadastrado nesta lista."}
        # Guarda de exclusão (não existe no VB6 original — reforço de
        # integridade padrão deste projeto: nunca excluir um registro com
        # dependência ativa, ver CLAUDE.md "Delete guards required").
        if float(r["qtd_alocada"] or 0) > 0:
            cur.close()
            return {"success": False, "message": "Há quantidade alocada em contrato(s) — não pode ser excluído."}
        cur.execute("DELETE FROM contratos_produtos_disponiveis WHERE produto=%s", (produto,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_produtos_disponiveis(servidor, banco, search=""):
    return await asyncio.to_thread(_list_produtos_disponiveis_sync, servidor, banco, search)


async def save_produto_disponivel(servidor, banco, produto, preco, qtd, situacao, obs):
    return await asyncio.to_thread(_save_produto_disponivel_sync, servidor, banco, produto, preco, qtd, situacao, obs)


async def delete_produto_disponivel(servidor, banco, produto):
    return await asyncio.to_thread(_delete_produto_disponivel_sync, servidor, banco, produto)


# ==================== Lookups combinados (form Contrato) ====================
# Uma chamada só carrega tudo que o formulário de Contrato precisa pros
# combos — mesmo princípio já usado em telas de Pedido/O.S. (evita N
# chamadas separadas no boot da tela).
TIPO_COBRANCA_OPCOES = [
    {"codigo": 0, "descricao": "Recibo"},
    {"codigo": 1, "descricao": "Nota Fiscal"},
    {"codigo": 2, "descricao": "Boleto"},
    {"codigo": 3, "descricao": "Recibo Locação"},
]


def _lookups_contrato_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        out = {"tipo_cobranca": TIPO_COBRANCA_OPCOES}
        cur.execute("SELECT codigo, descricao FROM tipo_contrato ORDER BY descricao")
        out["tipo_contrato"] = [_row_dict(r) for r in cur.fetchall()]
        cur.execute("SELECT codigo, descricao FROM prazo_reajuste ORDER BY descricao")
        out["tipo_reajuste"] = [_row_dict(r) for r in cur.fetchall()]
        cur.execute("SELECT codigo, descricao FROM indice_reajuste ORDER BY descricao")
        out["indice_reajuste"] = [_row_dict(r) for r in cur.fetchall()]
        try:
            cur.execute("SELECT codigo, descricao FROM periodicidade_contratual WHERE situacao='A' ORDER BY descricao")
            out["periodicidade"] = [_row_dict(r) for r in cur.fetchall()]
        except Exception:
            out["periodicidade"] = []
        try:
            cur.execute("SELECT codigo, descricao FROM centro_custo ORDER BY descricao")
            out["centro_custo"] = [_row_dict(r) for r in cur.fetchall()]
        except Exception:
            out["centro_custo"] = []
        cur.execute(
            "SELECT codigo_int AS codigo, ISNULL(NULLIF(nome_guerra,''), nome) AS descricao "
            "FROM funcionarios WHERE situacao='A' ORDER BY descricao"
        )
        out["vendedor"] = [_row_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, **out}
    finally:
        conn.close()


async def lookups_contrato(servidor, banco):
    return await asyncio.to_thread(_lookups_contrato_sync, servidor, banco)


# ==================== Contratos ====================

def _vcodcli_sync(cur) -> int:
    """Cliente 'interno' da própria empresa — usado pra desvincular
    equipamentos de um contrato encerrado/excluído (mesma consulta de
    `Command10_Click`/`Command19_Click`: `cliente.cgc_cpf = controle.cgc`)."""
    cur.execute("SELECT cliente.codigo FROM controle, cliente WHERE cliente.cgc_cpf = controle.cgc")
    r = cur.fetchone()
    return int(r["codigo"]) if r else 0


def _list_contratos_sync(servidor: str, banco: str, search: str, situacao: str, page: int, size: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        where = ["1=1"]
        params: list = []
        if situacao and situacao.strip():
            where.append("co.situacao=%s")
            params.append(situacao.strip()[:1].upper())
        if search and search.strip():
            where.append("(co.contrato LIKE %s OR cli.nome LIKE %s OR cli.fantasia LIKE %s)")
            like = f"%{search.strip()}%"
            params += [like, like, like]
        where_sql = " AND ".join(where)
        cur.execute(f"SELECT COUNT(*) AS total FROM contratos AS co, cliente AS cli WHERE co.cliente=cli.codigo AND {where_sql}", params)
        total = int(cur.fetchone()["total"])
        offset = max(0, (page - 1) * size)
        cur.execute(
            f"SELECT co.codigo, co.contrato, co.cliente, cli.nome AS cliente_nome, cli.fantasia AS cliente_fantasia, "
            f"co.valor_atual, co.situacao, co.inicio, co.fim, co.dia_vencimento "
            f"FROM contratos AS co, cliente AS cli WHERE co.cliente=cli.codigo AND {where_sql} "
            f"ORDER BY cli.nome, co.contrato OFFSET %s ROWS FETCH NEXT %s ROWS ONLY",
            params + [offset, size],
        )
        items = []
        for r in cur.fetchall():
            items.append({
                "codigo": int(r["codigo"]),
                "contrato": (r["contrato"] or "").strip(),
                "cliente": int(r["cliente"]),
                "cliente_nome": (r.get("cliente_fantasia") or r.get("cliente_nome") or "").strip(),
                "valor_atual": float(r["valor_atual"] or 0),
                "situacao": (r.get("situacao") or "").strip(),
                "inicio": _iso(r.get("inicio")),
                "fim": _iso(r.get("fim")),
                "dia_vencimento": r.get("dia_vencimento"),
            })
        cur.close()
        return {"success": True, "items": items, "total": total, "page": page, "size": size}
    finally:
        conn.close()


async def list_contratos(servidor, banco, search="", situacao="", page=1, size=30):
    return await asyncio.to_thread(_list_contratos_sync, servidor, banco, search, situacao, page, size)


_CONTRATO_COLS = (
    "contrato,cliente,servico_contrato,vendedor_contrato,assinatura,inicio,fim,renovado_ate,"
    "data_encerramento,dia_vencimento,mes_reajuste,valor_inicial,valor_atual,valor_ant,ultimo_reajuste,"
    "tipo_contrato,tipo_reajuste,indice_reajuste,tipo_cobranca,periodicidade,tarifa_cobranca,cobra_iss,"
    "agrupa_nf,fatura_os,descr_nf,msg_obs_nf,obs,historico,situacao,multa,mora_dia,desc_venc,dias_chave_renovacao"
).split(",")


def _get_contrato_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute(
            f"SELECT co.codigo, {','.join('co.'+c for c in _CONTRATO_COLS)}, cli.nome AS cliente_nome, cli.fantasia AS cliente_fantasia "
            f"FROM contratos AS co, cliente AS cli WHERE co.cliente=cli.codigo AND co.codigo=%s",
            (codigo,),
        )
        r = cur.fetchone()
        if not r:
            cur.close()
            return {"success": False, "message": "Contrato não encontrado."}
        out = {"codigo": int(r["codigo"])}
        for c in _CONTRATO_COLS:
            v = r.get(c)
            if c in ("assinatura", "inicio", "fim", "renovado_ate", "data_encerramento", "ultimo_reajuste"):
                out[c] = _iso(v)
            elif isinstance(v, str):
                out[c] = v.strip()
            elif isinstance(v, bool):
                out[c] = v
            elif isinstance(v, (int, float)) and c not in ("cliente", "vendedor_contrato", "tipo_contrato", "tipo_reajuste", "indice_reajuste", "tipo_cobranca", "periodicidade", "dia_vencimento", "mes_reajuste", "desc_venc", "dias_chave_renovacao"):
                out[c] = float(v)
            else:
                out[c] = v
        out["cliente_nome"] = (r.get("cliente_fantasia") or r.get("cliente_nome") or "").strip()

        cur.execute(
            "SELECT cp.codigo, cp.produto, cp.data_inicio, cp.data_encerramento, cp.preco, cp.qtd, cp.obs, cp.situacao "
            "FROM contratos_produtos AS cp WHERE cp.contrato=%s ORDER BY cp.codigo",
            (codigo,),
        )
        itens = []
        for it in cur.fetchall():
            info = _resolve_produto_contrato_sync(conn.cursor(as_dict=True), it["produto"])
            itens.append({
                "codigo": int(it["codigo"]),
                "produto": (it["produto"] or "").strip(),
                "descricao": info["descricao"] if info else it["produto"],
                "tipo": info["tipo"] if info else None,
                "data_inicio": _iso(it.get("data_inicio")),
                "data_encerramento": _iso(it.get("data_encerramento")),
                "preco": float(it["preco"] or 0),
                "qtd": float(it["qtd"] or 0),
                "obs": (it.get("obs") or "").strip(),
                "situacao": (it.get("situacao") or "").strip(),
            })
        out["itens"] = itens

        cur.execute(
            "SELECT ccc.centro_custo, cc.descricao, ccc.valor FROM contratos_centro_custo AS ccc, centro_custo AS cc "
            "WHERE ccc.contrato=%s AND ccc.centro_custo=cc.codigo ORDER BY cc.descricao",
            (codigo,),
        )
        out["centro_custo"] = [{
            "centro_custo": int(r2["centro_custo"]), "descricao": (r2["descricao"] or "").strip(), "valor": float(r2["valor"] or 0),
        } for r2 in cur.fetchall()]

        cur.execute(
            "SELECT codigo, data, preco_ant, preco_atual, percentual, descricao FROM contratos_preco "
            "WHERE contrato=%s ORDER BY codigo DESC",
            (codigo,),
        )
        out["precos"] = [{
            "codigo": int(r3["codigo"]), "data": _iso(r3["data"]), "preco_ant": float(r3["preco_ant"] or 0),
            "preco_atual": float(r3["preco_atual"] or 0), "percentual": float(r3["percentual"] or 0),
            "descricao": (r3.get("descricao") or "").strip(),
        } for r3 in cur.fetchall()]

        cur.execute(
            "SELECT codigo, ano, mes, item, tipo, valor, compl_descr FROM contratos_cred_deb "
            "WHERE contrato=%s ORDER BY ano DESC, mes DESC, codigo DESC",
            (codigo,),
        )
        out["cred_deb"] = [{
            "codigo": int(r4["codigo"]), "ano": int(r4["ano"]), "mes": int(r4["mes"]), "item": (r4.get("item") or "").strip(),
            "tipo": int(r4["tipo"]), "valor": float(r4["valor"] or 0), "compl_descr": (r4.get("compl_descr") or "").strip(),
        } for r4 in cur.fetchall()]

        cur.close()
        return {"success": True, "contrato": out}
    finally:
        conn.close()


async def get_contrato(servidor, banco, codigo):
    return await asyncio.to_thread(_get_contrato_sync, servidor, banco, codigo)


def _save_contrato_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    contrato_num = (dados.get("contrato") or "").strip()
    if not contrato_num:
        return {"success": False, "message": "O número do contrato não pode ficar em branco."}
    if not dados.get("cliente"):
        return {"success": False, "message": "Informe o cliente do contrato."}
    if not (1 <= int(dados.get("mes_reajuste") or 0) <= 12):
        return {"success": False, "message": "Mês de Reajuste do Contrato inválido."}
    if not (1 <= int(dados.get("dia_vencimento") or 0) <= 31):
        return {"success": False, "message": "Dia de Vencimento do Contrato inválido."}
    for campo, label in (("tipo_contrato", "Tipo de Contrato"), ("tipo_reajuste", "Tipo de Reajuste"), ("indice_reajuste", "Índice de Reajuste"), ("tipo_cobranca", "Tipo de Cobrança"), ("periodicidade", "Periodicidade Contratual")):
        # dados.get(campo) is None (não `not dados.get(campo)`) — Tipo de
        # Cobrança 0 ("Recibo", ver TIPO_COBRANCA_OPCOES) é um valor válido
        # e não pode ser confundido com "campo não preenchido". Bug real
        # encontrado 2026-07-20 validando contra banco real: com `not`,
        # tipo_cobranca=0 nunca conseguia ser gravado.
        if dados.get(campo) is None:
            return {"success": False, "message": f"Defina o {label}!"}
    if not (dados.get("descr_nf") or "").strip():
        return {"success": False, "message": "Preencha a Descrição da Nota Fiscal!"}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        sz = _get_col_sizes(conn, banco, "contratos")
        vals = {
            "contrato": _trunc(contrato_num, sz, "contrato", 20),
            "cliente": int(dados["cliente"]),
            "servico_contrato": (dados.get("servico_contrato") or "").strip() or None,
            "vendedor_contrato": dados.get("vendedor_contrato") or None,
            "assinatura": dados.get("assinatura"),
            "inicio": dados.get("inicio"),
            "fim": dados.get("fim") or None,
            "renovado_ate": dados.get("renovado_ate") or None,
            "data_encerramento": dados.get("data_encerramento") or None,
            "dia_vencimento": int(dados["dia_vencimento"]),
            "mes_reajuste": int(dados["mes_reajuste"]),
            "valor_inicial": float(dados.get("valor_inicial") or 0),
            "tipo_contrato": int(dados["tipo_contrato"]),
            "tipo_reajuste": int(dados["tipo_reajuste"]),
            "indice_reajuste": int(dados["indice_reajuste"]),
            "tipo_cobranca": int(dados["tipo_cobranca"]),
            "periodicidade": int(dados["periodicidade"]),
            "tarifa_cobranca": bool(dados.get("tarifa_cobranca")),
            "cobra_iss": bool(dados.get("cobra_iss")),
            "agrupa_nf": bool(dados.get("agrupa_nf")),
            "fatura_os": bool(dados.get("fatura_os")),
            "descr_nf": _trunc((dados.get("descr_nf") or "").strip(), sz, "descr_nf", 40),
            "msg_obs_nf": _trunc((dados.get("msg_obs_nf") or "").strip(), sz, "msg_obs_nf", 40),
            "obs": (dados.get("obs") or "").strip(),
            "situacao": (dados.get("situacao") or "A").strip()[:1].upper() or "A",
            "multa": float(dados.get("multa") or 0),
            "mora_dia": float(dados.get("mora_dia") or 0),
            "desc_venc": float(dados.get("desc_venc") or 0),
            "dias_chave_renovacao": int(dados.get("dias_chave_renovacao") or 0),
        }
        try:
            if codigo is not None:
                cur.execute("SELECT historico FROM contratos WHERE codigo=%s", (codigo,))
                r = cur.fetchone()
                if not r:
                    return {"success": False, "message": "Contrato não encontrado."}
                cols_set = ",".join(f"{k}=%s" for k in vals)
                cur.execute(
                    f"UPDATE contratos SET {cols_set} WHERE codigo=%s",
                    (*vals.values(), codigo),
                )
                novo_codigo = codigo
            else:
                vals["valor_atual"] = vals["valor_inicial"]
                cols = ",".join(vals.keys())
                marks = ",".join(["%s"] * len(vals))
                cur.execute(f"INSERT INTO contratos ({cols}) VALUES ({marks})", tuple(vals.values()))
                cur.execute("SELECT MAX(codigo) AS novo FROM contratos WHERE contrato=%s AND cliente=%s", (vals["contrato"], vals["cliente"]))
                novo_codigo = int(cur.fetchone()["novo"])
            conn.commit()
            cur.close()
            return {"success": True, "codigo": novo_codigo, "message": "Registro gravado."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


async def save_contrato(servidor, banco, codigo, dados):
    return await asyncio.to_thread(_save_contrato_sync, servidor, banco, codigo, dados)


def _reverter_estoque_itens_sync(cur, codigo: int, vcodcli: int):
    """Devolve estoque/desalocação de todos os itens de um contrato — usado
    tanto por excluir quanto por encerrar (mesma lógica de
    `Command10_Click`/`Command19_Click`)."""
    cur.execute("SELECT produto, qtd FROM contratos_produtos WHERE contrato=%s", (codigo,))
    itens = cur.fetchall()
    for it in itens:
        produto, qtd = it["produto"], it["qtd"]
        cur.execute(
            "UPDATE contratos_produtos_disponiveis SET qtd_alocada = qtd_alocada - %s WHERE produto=%s",
            (qtd, produto),
        )
        cur.execute(
            "UPDATE pecas SET qtd = qtd + %s, estoque_cli = estoque_cli - %s WHERE CODIGO_INT=%s",
            (qtd, qtd, produto),
        )
        cur.execute("UPDATE equipamentos SET cliente=%s WHERE numero_de_serie=%s", (vcodcli, produto))


def _delete_contrato_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT situacao FROM contratos WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        if not r:
            return {"success": False, "message": "Contrato não encontrado."}
        if (r["situacao"] or "").strip() != "A":
            return {"success": False, "message": "Situação inválida — só é possível excluir contratos Ativos."}
        try:
            vcodcli = _vcodcli_sync(cur)
            _reverter_estoque_itens_sync(cur, codigo, vcodcli)
            cur.execute("DELETE FROM contratos_preco WHERE contrato=%s", (codigo,))
            cur.execute("DELETE FROM contratos_centro_custo WHERE contrato=%s", (codigo,))
            cur.execute("DELETE FROM contratos_cred_deb WHERE contrato=%s", (codigo,))
            cur.execute("DELETE FROM contratos_produtos WHERE contrato=%s", (codigo,))
            cur.execute("DELETE FROM contratos WHERE codigo=%s", (codigo,))
            conn.commit()
            cur.close()
            return {"success": True, "message": "Contrato excluído."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def delete_contrato(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_contrato_sync, servidor, banco, codigo)


def _encerrar_contrato_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT situacao FROM contratos WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        if not r:
            return {"success": False, "message": "Contrato não encontrado."}
        if (r["situacao"] or "").strip() != "A":
            return {"success": False, "message": "Situação inválida — este contrato não está Ativo."}
        try:
            vcodcli = _vcodcli_sync(cur)
            _reverter_estoque_itens_sync(cur, codigo, vcodcli)
            cur.execute(
                "UPDATE contratos SET data_encerramento=%s, situacao='F' WHERE codigo=%s",
                (date.today().isoformat(), codigo),
            )
            conn.commit()
            cur.close()
            return {"success": True, "message": "Contrato encerrado."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao encerrar: {e}"}
    finally:
        conn.close()


async def encerrar_contrato(servidor, banco, codigo):
    return await asyncio.to_thread(_encerrar_contrato_sync, servidor, banco, codigo)


# ==================== Itens do Contrato ====================

def _checar_disponibilidade_sync(cur, produto: str, qtd: float) -> Optional[str]:
    """Retorna mensagem de erro (ou None se OK) — mesma regra de
    `Campo_LostFocus(12)`/`Command9_Click`: `qtd=0` na disponibilidade
    significa ilimitado; senão bloqueia se já não houver saldo pra alocar."""
    cur.execute("SELECT qtd, qtd_alocada FROM contratos_produtos_disponiveis WHERE produto=%s", (produto,))
    disp = cur.fetchone()
    if not disp:
        return "Produto, Equipamento ou Serviço não Disponível para uso em Contrato!"
    qtd_total = float(disp["qtd"] or 0)
    if qtd_total == 0:
        return None
    qtd_alocada = float(disp["qtd_alocada"] or 0)
    qtd_max = qtd_total - qtd_alocada
    if qtd_max <= 0:
        return "Produto, Equipamento ou Serviço não Disponível — sem saldo pra alocar!"
    if qtd > qtd_max:
        return f"Quantidade não permitida! Disponível: {qtd_max:g}."
    return None


def _aplicar_alocacao_sync(cur, produto: str, qtd: float, cliente: int, reverter: bool = False):
    """`cliente` é sempre o cliente a GRAVAR em `equipamentos.cliente` —
    o cliente do contrato ao alocar (`reverter=False`), ou `_vcodcli_sync`
    (cliente "da própria empresa") ao devolver (`reverter=True`). Bug
    corrigido 2026-07-19: a versão anterior só atualizava `equipamentos`
    ao alocar, nunca ao reverter — um item de equipamento excluído/editado
    ficava vinculado pra sempre ao cliente antigo do contrato."""
    sinal = -1 if reverter else 1
    cur.execute(
        "UPDATE contratos_produtos_disponiveis SET qtd_alocada = qtd_alocada + %s WHERE produto=%s",
        (sinal * qtd, produto),
    )
    cur.execute(
        "UPDATE pecas SET qtd = qtd - %s, estoque_cli = estoque_cli + %s WHERE CODIGO_INT=%s",
        (sinal * qtd, sinal * qtd, produto),
    )
    cur.execute("UPDATE equipamentos SET cliente=%s WHERE numero_de_serie=%s", (cliente, produto))


def _save_item_contrato_sync(servidor: str, banco: str, codigo_contrato: int, item_codigo: Optional[int], dados: dict) -> dict:
    produto_in = (dados.get("produto") or "").strip()
    qtd = float(dados.get("qtd") or 0)
    if not produto_in or qtd <= 0:
        return {"success": False, "message": "Defina o Item e a Quantidade corretamente!"}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT cliente FROM contratos WHERE codigo=%s", (codigo_contrato,))
        c = cur.fetchone()
        if not c:
            return {"success": False, "message": "Contrato não encontrado."}
        cliente = int(c["cliente"])
        info = _resolve_produto_contrato_sync(cur, produto_in)
        if not info:
            return {"success": False, "message": "Produto, Equipamento ou Serviço não Cadastrado!"}
        produto = info["codigo"]
        preco = float(dados.get("preco") or 0)
        obs_val = (dados.get("obs") or "").strip()
        situ = (dados.get("situacao") or "A").strip()[:1].upper() or "A"
        try:
            if item_codigo is not None:
                cur.execute("SELECT produto, qtd FROM contratos_produtos WHERE codigo=%s AND contrato=%s", (item_codigo, codigo_contrato))
                antigo = cur.fetchone()
                if not antigo:
                    return {"success": False, "message": "Item não encontrado."}
                _aplicar_alocacao_sync(cur, antigo["produto"], float(antigo["qtd"] or 0), _vcodcli_sync(cur), reverter=True)
                erro = _checar_disponibilidade_sync(cur, produto, qtd)
                if erro:
                    conn.rollback()
                    return {"success": False, "message": erro}
                cur.execute(
                    "UPDATE contratos_produtos SET produto=%s, data_inicio=%s, data_encerramento=%s, preco=%s, qtd=%s, obs=%s, situacao=%s WHERE codigo=%s",
                    (produto, dados.get("data_inicio"), dados.get("data_encerramento") or None, preco, qtd, obs_val, situ, item_codigo),
                )
                _aplicar_alocacao_sync(cur, produto, qtd, cliente, reverter=False)
                novo_codigo = item_codigo
            else:
                erro = _checar_disponibilidade_sync(cur, produto, qtd)
                if erro:
                    return {"success": False, "message": erro}
                cur.execute(
                    "INSERT INTO contratos_produtos (contrato, produto, data_inicio, data_encerramento, preco, qtd, obs, situacao) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (codigo_contrato, produto, dados.get("data_inicio"), dados.get("data_encerramento") or None, preco, qtd, obs_val, situ),
                )
                cur.execute("SELECT MAX(codigo) AS novo FROM contratos_produtos WHERE contrato=%s", (codigo_contrato,))
                novo_codigo = int(cur.fetchone()["novo"])
                _aplicar_alocacao_sync(cur, produto, qtd, cliente, reverter=False)
            conn.commit()
            cur.close()
            return {"success": True, "codigo": novo_codigo, "descricao": info["descricao"], "message": "Item gravado."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao gravar item: {e}"}
    finally:
        conn.close()


async def save_item_contrato(servidor, banco, codigo_contrato, item_codigo, dados):
    return await asyncio.to_thread(_save_item_contrato_sync, servidor, banco, codigo_contrato, item_codigo, dados)


def _delete_item_contrato_sync(servidor: str, banco: str, codigo_contrato: int, item_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT cliente FROM contratos WHERE codigo=%s", (codigo_contrato,))
        c = cur.fetchone()
        if not c:
            return {"success": False, "message": "Contrato não encontrado."}
        cur.execute("SELECT produto, qtd FROM contratos_produtos WHERE codigo=%s AND contrato=%s", (item_codigo, codigo_contrato))
        it = cur.fetchone()
        if not it:
            return {"success": False, "message": "Item não encontrado."}
        try:
            _aplicar_alocacao_sync(cur, it["produto"], float(it["qtd"] or 0), _vcodcli_sync(cur), reverter=True)
            cur.execute("DELETE FROM contratos_produtos WHERE codigo=%s", (item_codigo,))
            conn.commit()
            cur.close()
            return {"success": True, "message": "Item excluído."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao excluir item: {e}"}
    finally:
        conn.close()


async def delete_item_contrato(servidor, banco, codigo_contrato, item_codigo):
    return await asyncio.to_thread(_delete_item_contrato_sync, servidor, banco, codigo_contrato, item_codigo)


# ==================== Centro de Custo do Contrato ====================

def _save_centro_custo_sync(servidor: str, banco: str, codigo_contrato: int, centro_custo: int, valor: float) -> dict:
    if not centro_custo:
        return {"success": False, "message": "Defina o Centro de Custo!"}
    if not valor:
        return {"success": False, "message": "Valor inválido!"}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT TOP 1 1 AS ok FROM contratos_centro_custo WHERE contrato=%s AND centro_custo=%s", (codigo_contrato, centro_custo))
        try:
            if cur.fetchone():
                cur.execute("UPDATE contratos_centro_custo SET valor=%s WHERE contrato=%s AND centro_custo=%s", (valor, codigo_contrato, centro_custo))
            else:
                cur.execute("INSERT INTO contratos_centro_custo (contrato, centro_custo, valor) VALUES (%s,%s,%s)", (codigo_contrato, centro_custo, valor))
            conn.commit()
            cur.close()
            return {"success": True, "message": "Centro de Custo gravado."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


async def save_centro_custo(servidor, banco, codigo_contrato, centro_custo, valor):
    return await asyncio.to_thread(_save_centro_custo_sync, servidor, banco, codigo_contrato, centro_custo, valor)


def _delete_centro_custo_sync(servidor: str, banco: str, codigo_contrato: int, centro_custo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        try:
            cur.execute("DELETE FROM contratos_centro_custo WHERE contrato=%s AND centro_custo=%s", (codigo_contrato, centro_custo))
            conn.commit()
            cur.close()
            return {"success": True, "message": "Centro de Custo removido."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao remover: {e}"}
    finally:
        conn.close()


async def delete_centro_custo(servidor, banco, codigo_contrato, centro_custo):
    return await asyncio.to_thread(_delete_centro_custo_sync, servidor, banco, codigo_contrato, centro_custo)


def _rateio_centro_custo_sync(servidor: str, banco: str, codigo_contrato: int) -> dict:
    """Botão "Rateio Valor" do modal `FrmCustoContrato` (Centro Custo) —
    réplica de `Acerta_Contrato_Custo` (`Geral/mdl_proc.bas`), localizada
    via `.vbp` (Kontacto.vbp lista `..\\Geral\\FrmCustoContrato.frm`) a
    pedido do usuário 2026-07-20, depois de a rotina não ter aparecido no
    código colado originalmente (por isso ficava registrada como "não
    implementada" em PENDENCIAS.md). Redistribui a diferença entre o total
    já lançado nos centros de custo e o `valor_atual` do contrato,
    proporcionalmente ao peso de cada linha — nunca editando linha a linha
    na mão. Com 1 único centro de custo lançado, joga o valor inteiro nele
    (sem rateio proporcional, mesma regra do legado).

    Não replicado do legado (ver "Não replicar truques VB6" no CLAUDE.md):
    o bloqueio de fechar o modal `FrmCustoContrato` quando os valores
    divergem (`Form_QueryUnload`) estava condicionado a
    `Not Dados_Controle_Configuracao.Cilindro` — um flag de módulo sem
    nenhuma relação com Centro de Custo, quase certamente resíduo de
    copiar-colar de outra tela. A regra real (avisar/permitir corrigir a
    divergência) é preservada via aviso no frontend, não via bloqueio
    condicionado a um módulo aleatório.
    """
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT valor_atual FROM contratos WHERE codigo=%s", (codigo_contrato,))
        r = cur.fetchone()
        if not r:
            return {"success": False, "message": "Contrato não encontrado."}
        valor_atual = float(r["valor_atual"] or 0)
        cur.execute("SELECT centro_custo, valor FROM contratos_centro_custo WHERE contrato=%s", (codigo_contrato,))
        rows = cur.fetchall()
        if not rows:
            return {"success": False, "message": "Nenhum Centro de Custo lançado para ratear."}
        totcontra = sum(float(row["valor"] or 0) for row in rows)
        if round(totcontra, 2) == round(valor_atual, 2):
            return {"success": True, "message": "Os Centros de Custo já somam o valor atual do contrato — nada a ratear."}
        try:
            if len(rows) == 1:
                cur.execute(
                    "UPDATE contratos_centro_custo SET valor=%s WHERE contrato=%s AND centro_custo=%s",
                    (round(valor_atual, 2), codigo_contrato, rows[0]["centro_custo"]),
                )
            elif totcontra == 0:
                # Legado divide por totcontra sem checar zero (crashava em
                # runtime nesse caso) — não é regra de negócio, é limitação
                # do VB6. Bloquear com mensagem clara em vez de reproduzir
                # o erro ou inventar uma distribuição não documentada.
                return {"success": False, "message": "Todos os Centros de Custo estão com valor R$ 0,00 — lance ao menos um valor antes de ratear."}
            else:
                if valor_atual < totcontra:
                    percentual = 100 - (valor_atual / totcontra * 100)
                    for row in rows:
                        novo = round(float(row["valor"] or 0) - (float(row["valor"] or 0) * percentual / 100), 2)
                        cur.execute(
                            "UPDATE contratos_centro_custo SET valor=%s WHERE contrato=%s AND centro_custo=%s",
                            (novo, codigo_contrato, row["centro_custo"]),
                        )
                else:
                    percentual = ((valor_atual / totcontra) - 1) * 100
                    for row in rows:
                        novo = round(float(row["valor"] or 0) + (float(row["valor"] or 0) * percentual / 100), 2)
                        cur.execute(
                            "UPDATE contratos_centro_custo SET valor=%s WHERE contrato=%s AND centro_custo=%s",
                            (novo, codigo_contrato, row["centro_custo"]),
                        )
            conn.commit()
            cur.close()
            return {"success": True, "message": "Rateio aplicado."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao ratear: {e}"}
    finally:
        conn.close()


async def rateio_centro_custo(servidor, banco, codigo_contrato):
    return await asyncio.to_thread(_rateio_centro_custo_sync, servidor, banco, codigo_contrato)


# ==================== Reajuste de Valor (Alteração de Preço) ====================

def _aplicar_reajuste_sync(servidor: str, banco: str, codigo_contrato: int, valor_novo: float, percentual: float, descricao: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT valor_atual, historico FROM contratos WHERE codigo=%s", (codigo_contrato,))
        r = cur.fetchone()
        if not r:
            return {"success": False, "message": "Contrato não encontrado."}
        valor_atual = float(r["valor_atual"] or 0)
        if round(valor_novo, 2) == round(valor_atual, 2):
            return {"success": False, "message": "Valor Reajustado igual ao Valor Atual — alteração não permitida!"}
        hoje = date.today()
        historico_novo = (r.get("historico") or "").rstrip()
        linha = f"{hoje.strftime('%d/%m/%Y')} - Ajuste Valor"
        historico_novo = f"{historico_novo}\n{linha}" if historico_novo else linha
        try:
            cur.execute(
                "INSERT INTO contratos_preco (contrato, data, preco_ant, preco_atual, percentual, descricao) VALUES (%s,%s,%s,%s,%s,%s)",
                (codigo_contrato, hoje.isoformat(), valor_atual, valor_novo, percentual or 0, (descricao or "").strip()),
            )
            cur.execute(
                "UPDATE contratos SET valor_atual=%s, valor_ant=%s, ultimo_reajuste=%s, historico=%s WHERE codigo=%s",
                (valor_novo, valor_atual, hoje.isoformat(), historico_novo, codigo_contrato),
            )
            conn.commit()
            cur.close()
            return {"success": True, "message": "Reajuste gravado."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao gravar reajuste: {e}"}
    finally:
        conn.close()


async def aplicar_reajuste(servidor, banco, codigo_contrato, valor_novo, percentual, descricao):
    return await asyncio.to_thread(_aplicar_reajuste_sync, servidor, banco, codigo_contrato, valor_novo, percentual, descricao)


# ==================== Acréscimo/Desconto (contratos_cred_deb) ====================

def _resolve_item_cred_deb_sync(cur, item: str) -> Optional[dict]:
    """Resolução de item pro Acréscimo/Desconto — só peças/serviços, mesma
    cascata de `Campo_LostFocus(43)` (não inclui equipamentos/cilindro,
    diferente do resolver de itens do contrato). Retorna também o código
    NORMALIZADO (`Codigo_Int`/`Servicos.Codigo`, sempre nvarchar(8)) — bug
    real encontrado 2026-07-20 validando contra banco real: quando o item
    era resolvido por `Codigo_Fab` (nvarchar(40), pode ser bem mais longo
    que 8 chars), o valor bruto digitado pelo usuário era gravado sem
    normalização em `contratos_cred_deb.item` (nvarchar(8)), estourando
    "String or binary data would be truncated" — erro técnico cru
    vazando pro usuário (contra a regra [GLOBAL] de mensagens não-
    técnicas). Gravar sempre o código normalizado corrige isso."""
    it = (item or "").strip()
    if not it:
        return None
    for col in ("Codigo_Int", "Codigo_Fab"):
        cur.execute(f"SELECT Codigo_Int, Descricao FROM Pecas WHERE {col}=%s", (it,))
        r = cur.fetchone()
        if r:
            return {"codigo": (r["Codigo_Int"] or "").strip(), "descricao": (r["Descricao"] or "").strip()}
    cur.execute("SELECT Codigo, Descricao FROM Servicos WHERE Codigo=%s", (it,))
    r = cur.fetchone()
    if r:
        return {"codigo": (r["Codigo"] or "").strip(), "descricao": (r["Descricao"] or "").strip()}
    return None


def _save_cred_deb_sync(servidor: str, banco: str, codigo_contrato: int, cred_deb_codigo: Optional[int], dados: dict) -> dict:
    ano = int(dados.get("ano") or 0)
    mes = int(dados.get("mes") or 0)
    valor = float(dados.get("valor") or 0)
    tipo = int(dados.get("tipo") or 0)  # 0 = Acréscimo, 1 = Desconto
    item = (dados.get("item") or "").strip()
    if ano < 2000 or ano > 2100:
        return {"success": False, "message": "Ano inválido!"}
    if not (1 <= mes <= 12):
        return {"success": False, "message": "Mês inválido!"}
    if valor <= 0:
        return {"success": False, "message": "Valor inválido!"}
    if tipo == 0 and not item:
        return {"success": False, "message": "Código do Item inválido para Acréscimo!"}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        if item:
            info_item = _resolve_item_cred_deb_sync(cur, item)
            if info_item is None:
                return {"success": False, "message": "Código do Item não cadastrado!"}
            item = info_item["codigo"]
        compl = (dados.get("compl_descr") or "").strip()
        try:
            if cred_deb_codigo is not None:
                cur.execute(
                    "UPDATE contratos_cred_deb SET ano=%s, mes=%s, item=%s, tipo=%s, valor=%s, compl_descr=%s WHERE codigo=%s AND contrato=%s",
                    (ano, mes, item, tipo, valor, compl, cred_deb_codigo, codigo_contrato),
                )
                novo_codigo = cred_deb_codigo
            else:
                cur.execute(
                    "INSERT INTO contratos_cred_deb (contrato, ano, mes, item, tipo, valor, compl_descr) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (codigo_contrato, ano, mes, item, tipo, valor, compl),
                )
                cur.execute("SELECT MAX(codigo) AS novo FROM contratos_cred_deb WHERE contrato=%s", (codigo_contrato,))
                novo_codigo = int(cur.fetchone()["novo"])
            conn.commit()
            cur.close()
            return {"success": True, "codigo": novo_codigo, "message": "Lançamento gravado."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


async def save_cred_deb(servidor, banco, codigo_contrato, cred_deb_codigo, dados):
    return await asyncio.to_thread(_save_cred_deb_sync, servidor, banco, codigo_contrato, cred_deb_codigo, dados)


def _delete_cred_deb_sync(servidor: str, banco: str, codigo_contrato: int, cred_deb_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        try:
            cur.execute("DELETE FROM contratos_cred_deb WHERE codigo=%s AND contrato=%s", (cred_deb_codigo, codigo_contrato))
            conn.commit()
            cur.close()
            return {"success": True, "message": "Lançamento excluído."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def delete_cred_deb(servidor, banco, codigo_contrato, cred_deb_codigo):
    return await asyncio.to_thread(_delete_cred_deb_sync, servidor, banco, codigo_contrato, cred_deb_codigo)


# ==================== Reajuste automático por Índice (BACEN SGS) ====================

def _consultar_indice_bacen_sync(servidor: str, banco: str, indice_codigo: int, data_inicial: str, data_fim: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT descricao FROM indice_reajuste WHERE codigo=%s", (indice_codigo,))
        r = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    if not r:
        return {"success": False, "message": "Índice de Reajuste não encontrado."}
    desc = (r["descricao"] or "").strip().upper()
    serie = INDICES_BACEN.get(desc)
    if not serie:
        return {
            "success": False,
            "sem_correspondencia": True,
            "message": f"Índice '{desc}' não tem correspondência automática com o Banco Central — informe o percentual manualmente.",
        }
    try:
        di = datetime.strptime(data_inicial, "%Y-%m-%d").strftime("%d/%m/%Y")
        dfim = datetime.strptime(data_fim, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return {"success": False, "message": "Período inválido."}
    url = f"{BACEN_SGS_BASE.format(codigo=serie)}?formato=json&dataInicial={di}&dataFinal={dfim}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {
            "success": False,
            "message": "Não foi possível consultar o índice no site do Banco Central agora. Informe o percentual manualmente.",
        }
    if not payload:
        return {"success": False, "message": "Nenhum valor publicado pelo Banco Central para este período."}
    fator = 1.0
    for item in payload:
        try:
            fator *= 1 + float(str(item["valor"]).replace(",", ".")) / 100
        except (KeyError, ValueError):
            continue
    percentual = round((fator - 1) * 100, 4)
    return {
        "success": True,
        "percentual": percentual,
        "serie_bacen": serie,
        "indice": desc,
        "meses_considerados": len(payload),
        "periodo": {"inicio": data_inicial, "fim": data_fim},
    }


async def consultar_indice_bacen(servidor, banco, indice_codigo, data_inicial, data_fim):
    return await asyncio.to_thread(_consultar_indice_bacen_sync, servidor, banco, indice_codigo, data_inicial, data_fim)


# ==================== Faturar Contratos ====================
# Réplica de `FrmFatContrato2.frm`/`FrmFatContrato.frm` (Clauwan — o único
# variante que de fato define o botão "Rateio Valor" também referencia
# este form; achado via `.vbp`, ver CLAUDE.md > "Nunca marcar uma rotina
# como não implementada..."). Decisão explícita do usuário 2026-07-20: o
# faturamento grava fiel ao legado em `comanda`/`comanda_duplicata`/
# `comanda_contrato`/`comanda_os`/`movimentacao` + `Receber`/
# `Duplicata_Receber`/`Duplicata_Rec_Venc`/`Duplicata_Rec_Nf` — NÃO em
# `pedido_venda` (que é o que todo o resto do app usa) — logo um contrato
# faturado não aparece no Painel de Pedidos/Fechamento de Caixa/relatórios
# já existentes, só nas telas deste módulo. Escopo desta rodada (confirmado
# via AskUserQuestion): faturar (motor completo) + gerar Recibo. Nota
# Fiscal (EmiteNF, emissão fiscal real) e Boleto (layout bancário) ficam
# de fora — ver PENDENCIAS.md > "Contratos".

def _ultimo_dia_valido(ano: int, mes: int, dia_max: int) -> date:
    """Maior dia <= dia_max que existe de fato em (ano, mes) — réplica do
    laço `Do Until IsDate(...)` do legado (decrementa até achar uma data
    válida, ex.: dia_max=31 num mês de 30 dias vira dia 30)."""
    ultimo_do_mes = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(dia_max, ultimo_do_mes))


def _mes_ano_anterior(ano: int, mes: int) -> tuple:
    if mes == 1:
        return ano - 1, 12
    return ano, mes - 1


def _calc_periodo_faturamento(ano: int, mes: int) -> tuple:
    """(inicio_periodo, fim_periodo) — réplica exata de `Command2_Click`:
    inicio_periodo = último dia do mês ANTERIOR ao de referência (fica de
    fora do período, é só a âncora pra calcular dias — o período real
    começa no dia seguinte); fim_periodo = dia 30 do mês de referência
    (nunca 31 — o legado trata todo mês como "mês comercial" de 30 dias
    pro cálculo pró-rata, mesma base do `valor/30` usado adiante)."""
    ano_ant, mes_ant = _mes_ano_anterior(ano, mes)
    inicio_periodo = _ultimo_dia_valido(ano_ant, mes_ant, 31)
    fim_periodo = _ultimo_dia_valido(ano, mes, 30)
    return inicio_periodo, fim_periodo


def _calc_valor_prorata(valor_atual: float, inicio: Optional[date], fim_contrato: Optional[date],
                         inicio_periodo: date, fim_periodo: date) -> float:
    """Réplica exata do trecho de `Command2_Click` que calcula `Dia_Aux`/
    `VALOR_CONTRATO` — desconta 1/30 do valor por dia fora do período
    (contrato começou depois do início do período, ou terminou/foi
    encerrado/venceu antes do fim do período)."""
    dia_aux = 0
    if inicio and inicio > inicio_periodo:
        dia_aux = (inicio - (inicio_periodo + timedelta(days=1))).days
    if fim_contrato and fim_contrato < fim_periodo:
        dia_aux += (fim_periodo - fim_contrato).days
    if dia_aux == 0:
        return round(valor_atual, 2)
    return round(valor_atual - (valor_atual / 30) * dia_aux, 2)


def _calc_vencimento(dia_vencimento: int, mes_venc: int, ano_venc: int, data_emissao: date) -> date:
    """Réplica de `Data_Aux`/vencimento em `Command2_Click`: monta a data
    com o dia de vencimento do contrato no mês/ano de vencimento pedido
    (decrementando o dia até achar uma data válida, ex.: dia 31 num mês de
    30 dias), e nunca deixa o vencimento ficar ANTES da data de emissão."""
    dia = max(1, min(int(dia_vencimento or 1), 31))
    venc = _ultimo_dia_valido(ano_venc, mes_venc, dia)
    if venc < data_emissao:
        venc = data_emissao
    return venc


_EXTENSO_UNIDADES = ["", "UM", "DOIS", "TRÊS", "QUATRO", "CINCO", "SEIS", "SETE", "OITO", "NOVE"]
_EXTENSO_DEZ_A_DEZENOVE = ["DEZ", "ONZE", "DOZE", "TREZE", "QUATORZE", "QUINZE", "DEZESSEIS", "DEZESSETE", "DEZOITO", "DEZENOVE"]
_EXTENSO_DEZENAS = ["", "", "VINTE", "TRINTA", "QUARENTA", "CINQUENTA", "SESSENTA", "SETENTA", "OITENTA", "NOVENTA"]
_EXTENSO_CENTENAS = ["", "CEM", "DUZENTOS", "TREZENTOS", "QUATROCENTOS", "QUINHENTOS", "SEISCENTOS", "SETECENTOS", "OITOCENTOS", "NOVECENTOS"]


def _extenso_ate_999(n: int) -> str:
    if n == 0:
        return ""
    if n < 10:
        return _EXTENSO_UNIDADES[n]
    if n < 20:
        return _EXTENSO_DEZ_A_DEZENOVE[n - 10]
    if n < 100:
        d, u = divmod(n, 10)
        return _EXTENSO_DEZENAS[d] + (" E " + _EXTENSO_UNIDADES[u] if u else "")
    c, resto = divmod(n, 100)
    if c == 1 and resto == 0:
        return "CEM"
    texto_centena = "CENTO" if c == 1 else _EXTENSO_CENTENAS[c]
    return texto_centena + (" E " + _extenso_ate_999(resto) if resto else "")


def _extenso_grupo(n: int, singular: str, plural: str) -> str:
    if n == 0:
        return ""
    texto = _extenso_ate_999(n)
    return texto + " " + (singular if n == 1 else plural)


def _valor_por_extenso(valor: float) -> str:
    """Valor por extenso em português (reais + centavos) — mesma ideia de
    `Extenso`/`PegaExtenso` do legado (singular "Real"/"Centavo" vs plural
    "Reais"/"Centavos", "e" entre as duas partes), reimplementado do zero
    em vez de portar o parsing de string VB6 — mesmo algoritmo, sem
    depender de `PegaExtenso` (não localizada em nenhum `.bas` acessível)."""
    valor = round(abs(valor), 2)
    reais = int(valor)
    centavos = round((valor - reais) * 100)
    if centavos == 100:
        reais += 1
        centavos = 0
    partes = []
    if reais > 0:
        milhar, resto_milhar = divmod(reais, 1000)
        texto_reais = ""
        if milhar > 0:
            texto_reais += ("MIL" if milhar == 1 else _extenso_ate_999(milhar) + " MIL")
            if resto_milhar:
                texto_reais += " E " if resto_milhar < 100 else " "
        texto_reais += _extenso_ate_999(resto_milhar)
        partes.append(texto_reais.strip() + " " + ("REAL" if reais == 1 else "REAIS"))
    if centavos > 0:
        partes.append(_extenso_grupo(centavos, "CENTAVO", "CENTAVOS"))
    return " E ".join(partes) if partes else "ZERO REAIS"


def _ensure_forma_pag_contrato_sync(cur) -> str:
    """Garante a forma de pagamento "CONTRATO" (tipo 'DU' — Duplicata),
    usada como forma padrão em `comanda_duplicata` quando o contrato não
    tem um parcelamento específico configurado (`forma_pag_prazo`) —
    réplica de `Form_Load` (cria uma vez, reaproveita depois)."""
    cur.execute("SELECT TOP 1 codigo FROM forma_pagamento WHERE tipo='DU'")
    r = cur.fetchone()
    if r:
        return r["codigo"]
    cur.execute("SELECT codigo FROM forma_pagamento")
    maxcod = 0
    for row in cur.fetchall():
        try:
            maxcod = max(maxcod, int(row["codigo"]))
        except (TypeError, ValueError):
            continue
    novo = str(maxcod + 1)
    cur.execute(
        "INSERT INTO forma_pagamento (codigo, descricao, tipo, transf_caixa) VALUES (%s,%s,%s,%s)",
        (novo, "CONTRATO", "DU", "M"),
    )
    return novo


def _config_faturamento_sync(cur) -> dict:
    """Config de `Controle` usada pelo faturamento — réplica de
    `Form_Load`, com os mesmos fallbacks do legado quando `Controle` não
    tem linha ou os campos estão vazios."""
    cur.execute(
        "SELECT fatura_os_contrato, cfop_contrato_peca, cfop_contrato_servico, "
        "cod_servico_contrato, tipo_mov_contrato_peca, tipo_mov_contrato_servico "
        "FROM controle"
    )
    r = cur.fetchone()
    if not r:
        return {
            "fatura_os": True, "cfop_peca": "5102", "cfop_servico": "5933",
            "cod_servico_contrato": "S999", "tmov_peca": "S01", "tmov_servico": "S02",
        }
    return {
        "fatura_os": bool(r.get("fatura_os_contrato")),
        "cfop_peca": (r.get("cfop_contrato_peca") or "5102").strip(),
        "cfop_servico": (r.get("cfop_contrato_servico") or "5933").strip(),
        "cod_servico_contrato": (r.get("cod_servico_contrato") or "S999").strip(),
        "tmov_peca": (r.get("tipo_mov_contrato_peca") or "S01").strip(),
        "tmov_servico": (r.get("tipo_mov_contrato_servico") or "S02").strip(),
    }


def _listar_contratos_faturar_sync(
    servidor: str, banco: str, ano: int, mes: int,
    contrato_ini: Optional[str], contrato_fim: Optional[str],
    tipos_cobranca: list, somente_nao_faturados: bool,
    mes_venc: int, ano_venc: int, data_emissao_iso: str,
) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cfg = _config_faturamento_sync(cur)
        inicio_periodo, fim_periodo = _calc_periodo_faturamento(ano, mes)
        data_emissao = datetime.strptime(data_emissao_iso, "%Y-%m-%d").date() if data_emissao_iso else date.today()

        where = [
            "co.situacao='A'",
            "(co.fim IS NULL OR co.fim > %s OR co.renovado_ate > %s)",
            "(co.data_encerramento IS NULL OR co.data_encerramento > %s)",
            "NOT co.inicio > %s",
        ]
        params: list = [inicio_periodo, inicio_periodo, inicio_periodo, fim_periodo]
        if contrato_ini:
            where.append("co.contrato >= %s")
            params.append(contrato_ini)
        if contrato_fim:
            where.append("co.contrato <= %s")
            params.append(contrato_fim)
        tipos_validos = [t for t in (tipos_cobranca or []) if t in (0, 1, 2)]
        if not tipos_validos:
            tipos_validos = [0, 1, 2]
        where.append(f"co.tipo_cobranca IN ({','.join(['%s'] * len(tipos_validos))})")
        params += tipos_validos
        if somente_nao_faturados:
            where.append(
                "co.codigo NOT IN (SELECT contrato FROM comanda_contrato WHERE mes_referencia=%s AND ano_referencia=%s)"
            )
            params += [mes, ano]
        where_sql = " AND ".join(where)
        cur.execute(
            f"SELECT co.codigo, co.contrato, co.cliente, co.inicio, co.fim, co.renovado_ate, "
            f"co.data_encerramento, co.dia_vencimento, co.valor_atual, co.tipo_cobranca, "
            f"co.tarifa_cobranca, co.cobra_iss, co.agrupa_nf, co.descr_nf, co.fatura_os, "
            f"cli.nome, cli.fantasia "
            f"FROM contratos AS co, cliente AS cli "
            f"WHERE co.cliente = cli.codigo AND {where_sql} "
            f"ORDER BY cli.nome, cli.codigo, co.agrupa_nf, co.contrato",
            params,
        )
        rows = cur.fetchall()
        if not rows:
            cur.close()
            return {"success": True, "items": []}

        os_cache: dict = {}

        def _os_valores(cliente_codigo: int) -> tuple:
            if cliente_codigo in os_cache:
                return os_cache[cliente_codigo]
            cur.execute(
                "SELECT op.quant, op.preco_unitario FROM os, os_produto AS op "
                "WHERE os.situacao='F' AND os.cliente=%s AND os.codigo=op.os AND op.situacao=0 AND op.faturado=0 "
                "UNION ALL "
                "SELECT op.quant, op.preco_unitario FROM os, os_produto AS op, cliente "
                "WHERE os.situacao='F' AND os.cliente=cliente.codigo AND cliente.faturar=%s "
                "AND os.codigo=op.os AND op.situacao=0 AND op.faturado=0",
                (cliente_codigo, cliente_codigo),
            )
            fechada = sum(float(r["quant"] or 0) * float(r["preco_unitario"] or 0) for r in cur.fetchall())
            cur.execute(
                "SELECT op.quant, op.preco_unitario FROM os, os_produto AS op "
                "WHERE os.situacao='A' AND os.cliente=%s AND os.codigo=op.os AND op.situacao=0 AND op.faturado=0 "
                "UNION ALL "
                "SELECT op.quant, op.preco_unitario FROM os, os_produto AS op, cliente "
                "WHERE os.situacao='A' AND os.cliente=cliente.codigo AND cliente.faturar=%s "
                "AND os.codigo=op.os AND op.situacao=0 AND op.faturado=0",
                (cliente_codigo, cliente_codigo),
            )
            aberta = sum(float(r["quant"] or 0) * float(r["preco_unitario"] or 0) for r in cur.fetchall())
            os_cache[cliente_codigo] = (round(fechada, 2), round(aberta, 2))
            return os_cache[cliente_codigo]

        items = []
        for r in rows:
            fim_efetivo = r.get("data_encerramento") or r.get("renovado_ate") or r.get("fim")
            valor_contrato = _calc_valor_prorata(
                float(r["valor_atual"] or 0), r.get("inicio"), fim_efetivo, inicio_periodo, fim_periodo
            )
            os_fechada = os_aberta = 0.0
            if r.get("fatura_os"):
                os_fechada, os_aberta = _os_valores(int(r["cliente"]))
            vencimento = _calc_vencimento(int(r["dia_vencimento"] or 1), mes_venc, ano_venc, data_emissao)
            tipo_cobranca = int(r["tipo_cobranca"] or 0)
            tipo_doc = "N" if tipo_cobranca == 1 else ("B" if tipo_cobranca == 2 else "R")
            items.append({
                "codigo": int(r["codigo"]),
                "contrato": (r["contrato"] or "").strip(),
                "cliente": int(r["cliente"]),
                "cliente_nome": (r.get("fantasia") or r.get("nome") or "").strip(),
                "inicio": _iso(r.get("inicio")),
                "fim": _iso(fim_efetivo),
                "valor_contrato": valor_contrato,
                "os_fechada": os_fechada,
                "valor_total": round(valor_contrato + os_fechada, 2),
                "os_aberta": os_aberta,
                "vencimento": _iso(vencimento),
                "tarifa_cobranca": bool(r.get("tarifa_cobranca")),
                "cobra_iss": bool(r.get("cobra_iss")),
                "tipo_doc": tipo_doc,
                "tipo_cobranca": tipo_cobranca,
                "descr_nf": (r.get("descr_nf") or "").strip(),
            })
        cur.close()
        return {"success": True, "items": items, "fatura_os_ativo": cfg["fatura_os"]}
    finally:
        conn.close()


async def listar_contratos_faturar(servidor, banco, ano, mes, contrato_ini, contrato_fim, tipos_cobranca, somente_nao_faturados, mes_venc, ano_venc, data_emissao):
    return await asyncio.to_thread(
        _listar_contratos_faturar_sync, servidor, banco, ano, mes, contrato_ini, contrato_fim,
        tipos_cobranca, somente_nao_faturados, mes_venc, ano_venc, data_emissao,
    )


def _gerar_comanda_sync(cur, cfg: dict, contrato_codigo: int, valor_total: float, ano_ref: int, mes_ref: int, cod_func: int) -> dict:
    """Réplica de `GeraComanda` — cria a comanda (o "documento" de
    faturamento no modelo legado), a(s) parcela(s) em `comanda_duplicata`
    (usando `forma_pag_prazo` do contrato se existir, senão parcela única
    na forma "CONTRATO"), o vínculo `comanda_contrato` (idempotência de
    "já faturado" pro mês/ano de referência) e, se o contrato faturar
    O.S., agrupa as O.S. Fechadas não faturadas do cliente (ou de quem
    "fatura para" ele) na mesma comanda."""
    cur.execute("SELECT * FROM contratos WHERE codigo=%s", (contrato_codigo,))
    contrato = cur.fetchone()
    if not contrato:
        return {"success": False, "message": "Contrato não encontrado."}
    cliente = int(contrato["cliente"])
    hoje = date.today()

    cur.execute(
        "INSERT INTO comanda (data, cliente, valor_venda, situacao, atendente) VALUES (%s,%s,%s,%s,%s)",
        (hoje, cliente, valor_total, "PG", cod_func),
    )
    cur.execute("SELECT comanda FROM comanda WHERE cliente=%s AND data=%s ORDER BY comanda DESC", (cliente, hoje))
    r = cur.fetchone()
    if not r:
        return {"success": False, "message": "Falha ao gerar comanda."}
    comanda = int(r["comanda"])

    fp_contrato = _ensure_forma_pag_contrato_sync(cur)
    cur.execute("SELECT * FROM forma_pag_prazo WHERE forma_pag=%s", (fp_contrato,))
    prazos = cur.fetchall()
    if not prazos:
        cur.execute(
            "INSERT INTO comanda_duplicata (comanda, forma_pag, valor_pag, data_venc) VALUES (%s,%s,%s,%s)",
            (comanda, fp_contrato, round(valor_total, 2), hoje + timedelta(days=int(0))),
        )
    else:
        total_parcelado = 0.0
        n = len(prazos)
        for i, p in enumerate(prazos, start=1):
            parcela = round(valor_total * float(p["percentual"] or 0) / 100, 2)
            total_parcelado += parcela
            if i == n:
                diff = round(valor_total - total_parcelado, 2)
                parcela = round(parcela + diff, 2)
            cur.execute(
                "INSERT INTO comanda_duplicata (comanda, forma_pag, valor_pag, data_venc) VALUES (%s,%s,%s,%s)",
                (comanda, p["forma_pag"], parcela, hoje + timedelta(days=int(p["prazo"] or 0))),
            )

    if float(contrato["valor_atual"] or 0) != 0:
        cur.execute(
            "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, p_unit, num_nf, serie_nf, vendedor) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (hoje, cfg["tmov_servico"], cfg["cod_servico_contrato"], 1, valor_total, comanda, "CM", 0),
        )
    cur.execute(
        "UPDATE servicos SET descricao_nf=%s WHERE codigo=%s",
        ((contrato.get("descr_nf") or "").strip(), cfg["cod_servico_contrato"]),
    )
    cur.execute(
        "INSERT INTO comanda_contrato (comanda, contrato, ano_referencia, mes_referencia) VALUES (%s,%s,%s,%s)",
        (comanda, contrato_codigo, ano_ref, mes_ref),
    )

    descreve_os = ""
    if contrato.get("fatura_os"):
        cur.execute(
            "SELECT op.os, op.quant, op.preco_unitario, op.codigo_interno FROM os, os_produto AS op "
            "WHERE os.situacao='F' AND os.cliente=%s AND os.codigo=op.os AND op.situacao=0 AND op.faturado=0 "
            "UNION "
            "SELECT op.os, op.quant, op.preco_unitario, op.codigo_interno FROM os, os_produto AS op, cliente "
            "WHERE os.situacao='F' AND os.cliente=cliente.codigo AND cliente.faturar=%s "
            "AND os.codigo=op.os AND op.situacao=0 AND op.faturado=0 ORDER BY 1",
            (cliente, cliente),
        )
        itens_os = cur.fetchall()
        if itens_os:
            os_ja_lancadas = set()
            numeros_os = []
            for it in itens_os:
                os_num = int(it["os"])
                if os_num not in os_ja_lancadas:
                    cur.execute("INSERT INTO comanda_os (comanda, os) VALUES (%s,%s)", (comanda, os_num))
                    cur.execute("UPDATE os SET situacao='PG' WHERE codigo=%s", (os_num,))
                    os_ja_lancadas.add(os_num)
                    numeros_os.append(str(os_num))
                cur.execute(
                    "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, p_unit, num_nf, serie_nf, vendedor) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (hoje, "S01", it["codigo_interno"], it["quant"], it["preco_unitario"], comanda, "CM", 0),
                )
                if (it["codigo_interno"] or "").strip().upper().startswith("P"):
                    cur.execute(
                        "UPDATE pecas SET reservado_os = reservado_os - %s WHERE codigo_int=%s",
                        (it["quant"], it["codigo_interno"]),
                    )
            descreve_os = " e O.S. nº " + ",".join(numeros_os) + "."

    return {"success": True, "comanda": comanda, "descreve_os": descreve_os}


def _transf_receber_sync(cur, comanda: int, tipo_mov: str) -> Optional[str]:
    """Réplica simplificada de `Transf_Receber` — posta a comanda recém-
    gerada em `Receber` (contas a receber) e distribui o valor em
    `Duplicata_Receber`/`Duplicata_Rec_Venc`/`Duplicata_Rec_Nf`, seguindo
    um cronograma de vencimentos em `nf_vencimento` quando existir (senão
    parcela única na data de emissão da comanda). `tipo_mov` (no legado,
    `Tipo_Mov_Contrato` — variável nunca declarada em nenhum `.frm`/`.bas`
    acessível, quase certamente resíduo morto do VB6): usa
    `Controle.tipo_mov_contrato_servico` no lugar, por ser o tipo de
    movimento mais próximo semanticamente disponível — decisão registrada
    em PENDENCIAS.md, ajustar se o usuário confirmar outro valor. Retorna
    mensagem de erro (ou None se OK) — nunca lança, pra não abortar o lote
    inteiro por um contrato problemático."""
    cur.execute("SELECT * FROM comanda WHERE comanda=%s", (comanda,))
    c = cur.fetchone()
    if not c:
        return "Comanda não encontrada para transferir a contas a receber."
    cur.execute("SELECT geranumerodup, desmembramento_dup, numero_dup, agrupa_nf_receber FROM controle")
    cfgr = cur.fetchone() or {}
    geranum = bool(cfgr.get("geranumerodup"))
    desmembramento = (cfgr.get("desmembramento_dup") or "").strip()
    numero_dup = int(cfgr.get("numero_dup") or 0)

    cliente = int(c["cliente"])
    valor = round(float(c["valor_venda"] or 0), 2)
    dt_emissao = c["data"]

    cur.execute(
        "INSERT INTO Receber (cliente, nota_fiscal, serie, dt_emissao, dt_entrada, valor, tipo_mov, cod_n_fiscal, valor_contabilizado, situacao, origem_nf) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (cliente, comanda, "CO", dt_emissao, dt_emissao, valor, tipo_mov, comanda, 0, "DU", "C"),
    )
    cur.execute(
        "SELECT TOP 1 codigo FROM Receber WHERE cliente=%s AND nota_fiscal=%s AND serie='CO' AND dt_emissao=%s AND valor=%s ORDER BY codigo DESC",
        (cliente, comanda, dt_emissao, valor),
    )
    r = cur.fetchone()
    if not r:
        return "Falha ao localizar o lançamento gerado em Receber."
    cod_receber = int(r["codigo"])

    if geranum:
        numero_dup += 1
        while True:
            cur.execute("SELECT TOP 1 duplicata FROM Duplicata_Receber WHERE duplicata=%s AND desmembramento=%s", (numero_dup, desmembramento))
            if not cur.fetchone():
                break
            numero_dup += 1
        cur.execute("UPDATE controle SET numero_dup=%s", (numero_dup,))
    else:
        numero_dup = comanda

    cur.execute("INSERT INTO Duplicata_Receber (desmembramento) VALUES (%s)", (desmembramento,))
    cur.execute("SELECT MAX(codigo) AS xcod FROM Duplicata_Receber")
    dup_receber = int(cur.fetchone()["xcod"])
    cur.execute(
        "UPDATE Duplicata_Receber SET cliente=%s, duplicata=%s, dt_emissao=%s, valor=ISNULL(valor,0)+%s, situacao=%s WHERE codigo=%s",
        (cliente, numero_dup, dt_emissao, valor, "A", dup_receber),
    )

    cur.execute("SELECT * FROM nf_vencimento WHERE codigo=%s ORDER BY data_venc", (comanda,))
    vencimentos = cur.fetchall()
    if vencimentos:
        cur.execute("UPDATE Receber SET dt_vencimento=%s WHERE codigo=%s", (vencimentos[0]["data_venc"], cod_receber))
        for i, v in enumerate(vencimentos, start=1):
            cur.execute(
                "SELECT valor FROM Duplicata_Rec_Venc WHERE duplicata=%s AND dt_vencimento=%s",
                (dup_receber, v["data_venc"]),
            )
            existente = cur.fetchone()
            if existente:
                cur.execute(
                    "UPDATE Duplicata_Rec_Venc SET valor=%s WHERE duplicata=%s AND dt_vencimento=%s",
                    (round(float(existente["valor"] or 0) + float(v["valor"] or 0), 2), dup_receber, v["data_venc"]),
                )
            else:
                cur.execute(
                    "INSERT INTO Duplicata_Rec_Venc (duplicata, desmembramento, dt_vencimento, valor, situacao) VALUES (%s,%s,%s,%s,%s)",
                    (dup_receber, i, v["data_venc"], v["valor"], "A"),
                )
    else:
        cur.execute("UPDATE Receber SET dt_vencimento=%s WHERE codigo=%s", (dt_emissao, cod_receber))
        cur.execute(
            "SELECT valor FROM Duplicata_Rec_Venc WHERE duplicata=%s AND dt_vencimento=%s",
            (dup_receber, dt_emissao),
        )
        existente = cur.fetchone()
        if existente:
            cur.execute(
                "UPDATE Duplicata_Rec_Venc SET valor=%s WHERE duplicata=%s AND dt_vencimento=%s",
                (round(float(existente["valor"] or 0) + valor, 2), dup_receber, dt_emissao),
            )
        else:
            cur.execute(
                "INSERT INTO Duplicata_Rec_Venc (duplicata, desmembramento, dt_vencimento, valor, situacao) VALUES (%s,%s,%s,%s,%s)",
                (dup_receber, 1, dt_emissao, valor, "A"),
            )
    cur.execute("INSERT INTO Duplicata_Rec_Nf (duplicata, nf_fiscal) VALUES (%s,%s)", (dup_receber, cod_receber))
    cur.execute("UPDATE N_fiscal SET pagar='T' WHERE codigo=%s", (comanda,))
    return None


def _faturar_contratos_sync(servidor: str, banco: str, ano: int, mes: int, itens: list, cod_func: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cfg = _config_faturamento_sync(cur)
        resultados = []
        for item in itens:
            contrato_codigo = int(item["codigo"])
            valor_total = round(float(item["valor_total"] or 0), 2)
            try:
                r = _gerar_comanda_sync(cur, cfg, contrato_codigo, valor_total, ano, mes, cod_func or 0)
                if not r["success"]:
                    conn.rollback()
                    resultados.append({"codigo": contrato_codigo, "success": False, "message": r["message"]})
                    continue
                erro = _transf_receber_sync(cur, r["comanda"], cfg["tmov_servico"])
                if erro:
                    conn.rollback()
                    resultados.append({"codigo": contrato_codigo, "success": False, "message": erro})
                    continue
                conn.commit()
                resultados.append({
                    "codigo": contrato_codigo, "success": True, "comanda": r["comanda"],
                    "descreve_os": r["descreve_os"], "vencimento": item.get("vencimento"),
                })
            except Exception as e:
                conn.rollback()
                resultados.append({"codigo": contrato_codigo, "success": False, "message": f"Erro ao faturar: {e}"})
        cur.close()
        return {"success": True, "resultados": resultados}
    finally:
        conn.close()


async def faturar_contratos(servidor, banco, ano, mes, itens, usuario_codigo):
    return await asyncio.to_thread(_faturar_contratos_sync, servidor, banco, ano, mes, itens, usuario_codigo)


def _gerar_recibo_sync(servidor: str, banco: str, contrato_codigo: int, comanda: int, ano_ref: int, mes_ref: int, descreve_os: str) -> dict:
    """Réplica de `Recibo()` sem a impressão física (VB6 `Printer`) — devolve
    o conteúdo estruturado pro frontend renderizar/imprimir (mesmo padrão
    de `ReciboPedidoModal`), e grava o registro em `Recibos` + incrementa
    `Controle.Seq_Recibo`/reaproveita `Controle.Ano_Recibo`, igual ao
    legado (numeração sequencial por empresa)."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_contratos_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute(
            "SELECT co.descr_nf, cli.nome, cli.fantasia FROM contratos AS co, cliente AS cli "
            "WHERE co.cliente=cli.codigo AND co.codigo=%s",
            (contrato_codigo,),
        )
        contrato = cur.fetchone()
        cur.execute("SELECT valor_venda, data FROM comanda WHERE comanda=%s", (comanda,))
        com = cur.fetchone()
        if not contrato or not com:
            cur.close()
            return {"success": False, "message": "Contrato ou comanda não encontrados."}
        cur.execute("SELECT rz_social, seq_recibo, ano_recibo FROM controle")
        ctl = cur.fetchone() or {}
        seq = int(ctl.get("seq_recibo") or 0) + 1
        ano_recibo = int(ctl.get("ano_recibo") or date.today().year)
        valor = float(com["valor_venda"] or 0)
        meses_pt = ["", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
        referente = f"{(contrato.get('descr_nf') or '').strip()} Ref: {meses_pt[mes_ref]}/{ano_ref}" + (descreve_os if descreve_os else ".")
        nome_cliente = (contrato.get("fantasia") or contrato.get("nome") or "").strip()
        rz_social = (ctl.get("rz_social") or "").strip()
        hoje = date.today()
        cur.execute(
            "INSERT INTO Recibos (seq, ano, recebemos, valor, referente, data, assinatura) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (seq, ano_recibo, nome_cliente, valor, referente, hoje, rz_social),
        )
        cur.execute("UPDATE controle SET seq_recibo=%s", (seq,))
        conn.commit()
        cur.close()
        return {
            "success": True,
            "numero": f"{seq:03d}/{ano_recibo}",
            "recebemos": nome_cliente,
            "valor": round(valor, 2),
            "valor_extenso": _valor_por_extenso(valor),
            "referente": referente,
            "data": _iso(hoje),
            "assinatura": rz_social,
        }
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gerar recibo: {e}"}
    finally:
        conn.close()


async def gerar_recibo(servidor, banco, contrato_codigo, comanda, ano_ref, mes_ref, descreve_os):
    return await asyncio.to_thread(_gerar_recibo_sync, servidor, banco, contrato_codigo, comanda, ano_ref, mes_ref, descreve_os)

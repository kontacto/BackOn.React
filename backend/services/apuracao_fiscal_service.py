"""Apuração Fiscal — relatório item-a-item de PIS/COFINS/ICMS/FCP/DIFAL.

Migração de `Geral\\FrmCalImp.frm` ("Apuração Fiscal"). Puramente
consulta/relatório — sem Gravar/Excluir. 3 modos, cada um com sua fonte:

- **NFCE** (`comanda` + `comanda_nfce` + `comanda_nfce_detalhe` + `pecas`):
  comanda paga (`c.situacao='PG'`) e NFC-e autorizada (`cnf.situacao='F'`).
  A alíquota de ICMS aqui é CALCULADA (`valor_icms/base_icms*100`) porque
  `comanda_nfce_detalhe` não tem uma coluna própria de alíquota — achado
  ao vivo (confirmado contra ARGEN TESTE: existe `ALQT_ICMS_EFETIVO`, mas
  não um `ALQT_ICMS` genérico), exatamente como o legado já fazia.
- **NFE** (`n_fiscal` + `n_fiscal_itens` + `pecas`): saída de venda
  autorizada (`MOV='S01'`, `situacao='A'`, `situacao_nfe=1`). Aqui a
  alíquota de ICMS já vem de uma coluna própria (`n_fiscal_itens.
  Alqt_Icms`, confirmada ao vivo) — não recalculada, diferente do NFCE.
- **DIFAL**: mesma fonte do NFE, mas só itens com partilha interestadual
  real (`aliquota_interna_destino>0 OR aliquota_interestadual>0`) e 3
  colunas extras de rateio origem/destino (ver `_calc_difal` abaixo).

**Achado real, RESOLVIDO 2026-08-24 contra fonte oficial** (CONFAZ,
Convênio ICMS 93/2015 — cv093_15, `confaz.fazenda.gov.br/legislacao/
convenios/2015/CV093_15` —, Cláusula segunda § 1º-A + Cláusula décima):
o legado (`Command1_Click`, ramo `Else`) tinha o RÓTULO das colunas de
rateio DIFAL invertido em relação à FÓRMULA. Confirmado na fonte:
`percentual_origem` é a fatia do diferencial que fica retida com a UF de
ORIGEM (não a de destino) — cronograma oficial de transição: 60% origem/
40% destino em 2016, 40%/60% em 2017, 20%/80% em 2018, tendendo a 0%
origem/100% destino a partir de 2019 (Cláusula décima). Logo:
`TempDifal * percentual_origem / 100` é o valor real da ORIGEM, e
`TempDifal * (100 - percentual_origem) / 100` é o valor real do DESTINO
— o legado rotulava exatamente ao contrário ("$ Origem" na fórmula que é
na verdade destino, e vice-versa). A FÓRMULA (os dois valores numéricos
calculados) nunca mudou — só a rotulagem/nome das chaves foi corrigido
pra bater com o significado real confirmado na fonte oficial
(`valor_origem`/`valor_destino`, ver `_calc_difal` abaixo).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _fmt2(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _aliquota_icms_nfce(valor_icms, base_icms) -> float:
    v = float(valor_icms or 0)
    if not v:
        return 0.0
    b = float(base_icms or 0)
    if not b:
        return 0.0
    return round(v / b * 100, 2)


def _apurar_nfce_sync(cur, data_ini: Optional[str], data_fim: Optional[str], cfop: Optional[str]) -> list:
    where = ["c.situacao='PG'", "c.comanda=cnf.comanda", "cnf.comanda=cnfd.comanda", "cnf.situacao='F'", "cnfd.produto=p.codigo_int"]
    params: list = []
    if data_ini and data_fim:
        where.append("cnf.data_emissao >= %s AND cnf.data_emissao <= %s")
        params += [data_ini, data_fim]
    if cfop:
        where.append("cnfd.cfop = %s")
        params.append(cfop)
    sql = (
        "SELECT cnf.num_nfce, cnf.comanda, cnf.data_emissao, p.codigo_fab, p.descricao, "
        "cnfd.cfop, cnfd.tributacao, cnfd.qtd, cnfd.p_unit, cnfd.valor_total, "
        "cnfd.cst_pis, cnfd.valor_pis, cnfd.cst_cofins, cnfd.valor_cofins, "
        "cnfd.base_icms, cnfd.valor_icms, cnfd.alqt_fcp, cnfd.valor_fcp, "
        "cnfd.alqt_fcp_retido, cnfd.valor_fcp_retido "
        "FROM comanda c, comanda_nfce cnf, comanda_nfce_detalhe cnfd, pecas p "
        f"WHERE {' AND '.join(where)} ORDER BY cnf.num_nfce, cnfd.item"
    )
    cur.execute(sql, tuple(params))
    rows = cur.fetchall() or []
    out = []
    for r in rows:
        out.append({
            "documento": r.get("num_nfce"),
            "comanda": r.get("comanda"),
            "emissao": r.get("data_emissao"),
            "codigo_fab": r.get("codigo_fab"),
            "descricao": r.get("descricao"),
            "cfop": r.get("cfop"),
            "cst": (r.get("tributacao") or "").strip() if isinstance(r.get("tributacao"), str) else r.get("tributacao"),
            "qtd": r.get("qtd"),
            "valor_unitario": _fmt2(r.get("p_unit")),
            "valor_total": _fmt2(r.get("valor_total")),
            "cst_pis": r.get("cst_pis"),
            "valor_pis": _fmt2(r.get("valor_pis")),
            "cst_cofins": r.get("cst_cofins"),
            "valor_cofins": _fmt2(r.get("valor_cofins")),
            "aliquota_icms": _aliquota_icms_nfce(r.get("valor_icms"), r.get("base_icms")),
            "valor_icms": _fmt2(r.get("valor_icms")),
            "aliquota_fcp": _fmt2(r.get("alqt_fcp")),
            "valor_fcp": _fmt2(r.get("valor_fcp")),
            "aliquota_fcp_retido": _fmt2(r.get("alqt_fcp_retido")),
            "valor_fcp_retido": _fmt2(r.get("valor_fcp_retido")),
        })
    return out


def _apurar_nfe_sync(cur, data_ini: Optional[str], data_fim: Optional[str], cfop: Optional[str], *, difal: bool) -> list:
    where = ["NF.MOV='S01'", "nf.situacao='A'", "nf.situacao_nfe=1", "nf.codigo=nfi.codigo", "p.codigo_int=nfi.codigo_int"]
    params: list = []
    if data_ini and data_fim:
        where.append("nf.data_nf >= %s AND nf.data_nf <= %s")
        params += [data_ini, data_fim]
    if cfop:
        where.append("nfi.cod_fiscal = %s")
        params.append(cfop)
    if difal:
        where.append("(nfi.aliquota_interna_destino>0 OR nfi.aliquota_interestadual>0)")
    extra = ", nfi.aliquota_interestadual, nfi.aliquota_interna_destino, nfi.percentual_origem, nfi.fundo_pobreza" if difal else ""
    sql = (
        f"SELECT nf.num_nf, nf.data_nf, p.codigo_fab, p.descricao, "
        "nfi.cod_fiscal, nfi.tributacao, nfi.qtd, nfi.p_unit, nfi.valor_total, "
        "nfi.tributacao_pis, nfi.valor_pis, nfi.tributacao_cofins, nfi.valor_cofins, "
        f"nfi.base_icms, nfi.Alqt_Icms, nfi.Valor_Icms, nfi.alqt_fcp, nfi.valor_fcp, "
        f"nfi.alqt_fcp_retido, nfi.valor_fcp_retido{extra} "
        "FROM n_fiscal nf, n_fiscal_itens nfi, pecas p "
        f"WHERE {' AND '.join(where)} ORDER BY nf.num_nf, nfi.id"
    )
    cur.execute(sql, tuple(params))
    rows = cur.fetchall() or []
    out = []
    for r in rows:
        item = {
            "documento": r.get("num_nf"),
            "comanda": None,
            "emissao": r.get("data_nf"),
            "codigo_fab": r.get("codigo_fab"),
            "descricao": r.get("descricao"),
            "cfop": r.get("cod_fiscal"),
            "cst": r.get("tributacao"),
            "qtd": r.get("qtd"),
            "valor_unitario": _fmt2(r.get("p_unit")),
            "valor_total": _fmt2(r.get("valor_total")),
            "cst_pis": r.get("tributacao_pis"),
            "valor_pis": _fmt2(r.get("valor_pis")),
            "cst_cofins": r.get("tributacao_cofins"),
            "valor_cofins": _fmt2(r.get("valor_cofins")),
            "aliquota_icms": _fmt2(r.get("Alqt_Icms")),
            "valor_icms": _fmt2(r.get("Valor_Icms")),
            "aliquota_fcp": _fmt2(r.get("alqt_fcp")),
            "valor_fcp": _fmt2(r.get("valor_fcp")),
            "aliquota_fcp_retido": _fmt2(r.get("alqt_fcp_retido")),
            "valor_fcp_retido": _fmt2(r.get("valor_fcp_retido")),
        }
        if difal:
            item.update(_calc_difal(r))
        out.append(item)
    return out


def _calc_difal(r) -> dict:
    base_icms = float(r.get("base_icms") or 0)
    aliq_inter = float(r.get("aliquota_interestadual") or 0)
    aliq_dest = float(r.get("aliquota_interna_destino") or 0)
    perc_origem = float(r.get("percentual_origem") or 0)
    fundo_pobreza = float(r.get("fundo_pobreza") or 0)

    # Fórmula do legado (Command1_Click, ramo Else) — nunca mudou. Só a
    # ROTULAGEM foi corrigida 2026-08-24 (ver docstring do módulo):
    # confirmado contra o Convênio ICMS 93/2015 (fonte oficial CONFAZ)
    # que `percentual_origem` é a fatia retida pela UF de ORIGEM — o
    # legado rotulava essas duas colunas ao contrário.
    valor_fcp_difal = base_icms * fundo_pobreza / 100
    temp_difal = base_icms * (aliq_dest - aliq_inter) / 100
    valor_origem = temp_difal * perc_origem / 100
    valor_destino = temp_difal * (100 - perc_origem) / 100

    return {
        "aliquota_interestadual": _fmt2(aliq_inter),
        "aliquota_interna_destino": _fmt2(aliq_dest),
        "percentual_origem": _fmt2(perc_origem),
        "valor_fcp_difal": _fmt2(valor_fcp_difal),
        "valor_origem": _fmt2(valor_origem),
        "valor_destino": _fmt2(valor_destino),
    }


_TOTAIS_COMUNS = ["valor_total", "valor_pis", "valor_cofins", "valor_icms", "valor_fcp", "valor_fcp_retido"]
_TOTAIS_DIFAL = ["valor_fcp_difal", "valor_origem", "valor_destino"]


def _somar_totais(itens: list, *, difal: bool) -> dict:
    chaves = _TOTAIS_COMUNS + (_TOTAIS_DIFAL if difal else [])
    return {f"total_{k}": round(sum(float(it.get(k) or 0) for it in itens), 2) for k in chaves}


def _apurar_sync(servidor: str, banco: str, *, modo: str, data_ini: Optional[str], data_fim: Optional[str], cfop: Optional[str]) -> dict:
    modo_v = (modo or "NFCE").strip().upper()
    if modo_v not in ("NFCE", "NFE", "DIFAL"):
        return {"success": False, "message": "Modo inválido — use NFCE, NFE ou DIFAL."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if modo_v == "NFCE":
            itens = _apurar_nfce_sync(cur, data_ini, data_fim, cfop)
        elif modo_v == "NFE":
            itens = _apurar_nfe_sync(cur, data_ini, data_fim, cfop, difal=False)
        else:
            itens = _apurar_nfe_sync(cur, data_ini, data_fim, cfop, difal=True)
        if not itens:
            return {"success": True, "itens": [], "totais": {}, "message": "Nenhum registro encontrado."}
        totais = _somar_totais(itens, difal=(modo_v == "DIFAL"))
        return {"success": True, "itens": itens, "totais": totais}
    except Exception as e:
        return {"success": False, "message": f"Falha ao apurar: {e}"}
    finally:
        conn.close()


async def apurar(servidor, banco, *, modo, data_ini=None, data_fim=None, cfop=None):
    return await asyncio.to_thread(_apurar_sync, servidor, banco, modo=modo, data_ini=data_ini, data_fim=data_fim, cfop=cfop)

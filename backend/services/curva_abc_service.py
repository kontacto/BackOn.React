"""Curva ABC e Estoques (Transações > Gestão de Compras > Compra). Legado:
`FrmCurvaABC.frm` ("Gerar Curva ABC..."). Duas ações independentes, cada
uma sua própria gravação em `pecas`:

  1. **Gerar Curva ABC** (`Command4_Click` do legado) — classifica
     `curva_abc`/`percent_abc` (Quantidade) ou `curva_abc_fin`/
     `percent_abc_fin` (Financeira). Importante: **não** é o clássico corte
     80/20 por valor acumulado — é corte por QUANTIDADE DE ITENS
     proporcional ao percentual configurado em cada faixa (`GridCurva` do
     legado), sobre o ranking de produtos vendidos no período ordenado
     decrescente. Ex.: faixa A=50% com 100 itens vendidos → os 50
     primeiros do ranking viram 'A', independente de quanto valor eles
     representam. `percent_abc` grava o % ACUMULADO do total até aquele
     item (não o % da faixa).
  2. **Processar atualização de estoques** (`Command6_Click`) — recalcula
     `Consumo_Medio_Mensal`/`estoque_minimo`/`estoque_ressuprimento`/
     `estoque_maximo` a partir das vendas do período + Grau de Atendimento
     (fator de segurança) + prazo de reposição do produto/fornecedor.
     `intervalo_ressuprimento` do legado (baseado em NFs de entrada no
     período) não foi portado — no próprio `.frm` a fórmula final do
     estoque máximo não usa essa variável (ficou como `Int(estoque_minimo
     + cmm_diario) * Tempo_Reposicao`, a linha que a usava está comentada)
     — replicar a variável seria calcular algo que o legado também nunca
     lê.

Fonte de vendas: `comanda`+`movimentacao` (`serie_nf='CM'`,
`situacao='PG'`) — mesma convenção de "vendas realizadas" já usada em
`fechamento_caixa_service.py`/`margem_lucro_service.py` (`_bloco_comanda`),
não é gambiarra Bar-específica, é a fonte canônica de vendas faturadas
deste app.
"""
import asyncio
from datetime import datetime
from typing import Optional

from db.connection import _open_conn
from services.margem_lucro_service import _nivel_clause
from services.pedido_common import _modulo_curva_abc_ativo

_MODULO_OFF_MSG = "Módulo Curva ABC/Compras está desativado — fale com o administrador em Configurações > Módulos e Recursos."


def _numero_de_meses(data_ini_s: str, data_fim_s: str) -> int:
    d1 = datetime.strptime(data_ini_s, "%Y-%m-%d").date()
    d2 = datetime.strptime(data_fim_s, "%Y-%m-%d").date()
    anos_inteiros = d2.year - d1.year - 1
    tot_meses = 12 * anos_inteiros if anos_inteiros > 0 else 0
    if d2.year == d1.year:
        tot_meses += (d2.month - d1.month + 1)
    else:
        tot_meses += d2.month
        tot_meses += (12 - d1.month + 1)
    return max(tot_meses, 1)


def _reset_where(nivel: Optional[str]) -> tuple[list, list]:
    where, params = [], []
    if nivel and nivel.strip():
        n = nivel.strip()
        partes = [n[i:i + 3] for i in range(0, len(n), 3)][:5]
        for idx, parte in enumerate(partes, start=1):
            if parte:
                where.append(f"nivel{idx} = %s")
                params.append(parte)
    return where, params


def _vendas_periodo(cur, data_ini: str, data_fim: str, nivel: Optional[str], tipo: str) -> list:
    nc, npar = _nivel_clause("p", nivel)
    where = ["c.situacao = 'PG'", "m.serie_nf = 'CM'", "c.data >= %s", "c.data <= %s"] + nc
    params = [data_ini, data_fim] + npar
    campo = "SUM(CAST(m.qtd * m.p_unit AS NUMERIC(15,2)))" if tipo == "financeira" else "SUM(CAST(m.qtd AS NUMERIC(15,2)))"
    cur.execute(
        f"SELECT m.codigo_int, p.descricao, {campo} AS total "
        "FROM movimentacao m JOIN comanda c ON c.comanda = m.num_nf JOIN pecas p ON p.codigo_int = m.codigo_int "
        f"WHERE {' AND '.join(where)} "
        "GROUP BY m.codigo_int, p.descricao ORDER BY total DESC",
        tuple(params),
    )
    return cur.fetchall()


def _gerar_curva_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str, tipo: str, faixas: list,
    nivel: Optional[str] = None,
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Defina o período corretamente."}
    tipo = (tipo or "").strip().lower()
    if tipo not in ("financeira", "quantidade"):
        return {"success": False, "message": "Defina o tipo de curva (Financeira ou Quantidade)."}
    faixas = [f for f in (faixas or []) if (f.get("curva") or "").strip()]
    if not faixas:
        return {"success": False, "message": "Defina os limites da curva corretamente."}
    soma = sum(float(f.get("percentual") or 0) for f in faixas)
    if round(soma, 2) != 100:
        return {"success": False, "message": "O somatório da curva não totaliza 100%."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        col_curva = "curva_abc_fin" if tipo == "financeira" else "curva_abc"
        col_percent = "percent_abc_fin" if tipo == "financeira" else "percent_abc"

        ultima_curva = faixas[-1]["curva"].strip().upper()[:1]
        curva_reset = chr(ord(ultima_curva) + 1)
        where_reset, params_reset = _reset_where(nivel)
        where_reset_sql = f" WHERE {' AND '.join(where_reset)}" if where_reset else ""
        cur.execute(
            f"UPDATE pecas SET {col_curva} = %s, {col_percent} = 0{where_reset_sql}",
            tuple([curva_reset] + params_reset),
        )

        vendas = _vendas_periodo(cur, data_ini, data_fim, nivel, tipo)
        if not vendas:
            conn.rollback()
            return {"success": False, "message": "Nenhum registro encontrado no período."}

        tot_itens = len(vendas)
        tot_geral = sum(float(v.get("total") or 0) for v in vendas)

        resultado = []
        acumulado_valor = 0.0
        pos = 0
        for i, faixa in enumerate(faixas):
            letra = faixa["curva"].strip().upper()[:1]
            pct = float(faixa.get("percentual") or 0)
            if i == len(faixas) - 1:
                fim = tot_itens
            else:
                qtd_itens_faixa = max(1, int(pct * tot_itens / 100))
                fim = min(pos + qtd_itens_faixa, tot_itens)
            for v in vendas[pos:fim]:
                total = float(v.get("total") or 0)
                acumulado_valor += total
                percentual_acumulado = round((acumulado_valor / tot_geral * 100), 2) if tot_geral else 0
                cur.execute(
                    f"UPDATE pecas SET {col_curva} = %s, {col_percent} = %s WHERE codigo_int = %s",
                    (letra, percentual_acumulado, v["codigo_int"]),
                )
                resultado.append({
                    "codigo_int": (v.get("codigo_int") or "").strip(),
                    "descricao": (v.get("descricao") or "").strip(),
                    "total": total, "curva": letra, "percentual_acumulado": percentual_acumulado,
                })
            pos = fim
            if pos >= tot_itens:
                break

        conn.commit()
        cur.close()
        return {"success": True, "total_geral": tot_geral, "total_itens": tot_itens, "items": resultado}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _reprocessar_estoques_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str, grau_atendimento: float,
    nivel: Optional[str] = None,
    atualizar_minimo: bool = False, atualizar_ressuprimento: bool = False,
    atualizar_maximo: bool = False, atualizar_consumo: bool = False,
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Defina o período corretamente."}
    if grau_atendimento is None:
        return {"success": False, "message": "Defina o Grau de Atendimento (Fator de segurança)."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        vendas = _vendas_periodo(cur, data_ini, data_fim, nivel, "quantidade")
        if not vendas:
            return {"success": False, "message": "Nenhum registro encontrado no período."}

        meses = _numero_de_meses(data_ini, data_fim)
        resultado = []
        for v in vendas:
            codigo_int = (v.get("codigo_int") or "").strip()
            total_vendido = float(v.get("total") or 0)

            cur.execute(
                "SELECT estoque_minimo, estoque_ressuprimento, estoque_maximo, prazo_fornecedor "
                "FROM pecas WHERE codigo_int = %s",
                (codigo_int,),
            )
            peca = cur.fetchone()
            if not peca:
                continue

            cmm = int(total_vendido / meses) if meses else 0
            if cmm == 0:
                cmm = 1
            cmm_diario = cmm / 30

            prazo_fornecedor = peca.get("prazo_fornecedor")
            if prazo_fornecedor:
                tempo_reposicao = int(prazo_fornecedor)
            else:
                cur.execute(
                    "SELECT TOP 1 f.prazo_pgto FROM pecas_fornecedor pf "
                    "JOIN fornecedor f ON f.codigo_int = pf.fornecedor "
                    "WHERE pf.peca = %s ORDER BY f.prazo_pgto DESC",
                    (codigo_int,),
                )
                forn = cur.fetchone()
                tempo_reposicao = int(forn["prazo_pgto"]) if forn and forn.get("prazo_pgto") else 0

            estoque_minimo_novo = int(cmm * grau_atendimento / 100)
            estoque_ressuprimento_novo = int((cmm_diario * tempo_reposicao) + estoque_minimo_novo)
            estoque_maximo_novo = int(estoque_minimo_novo + cmm_diario) * tempo_reposicao

            updates, params = [], []
            if atualizar_minimo:
                updates.append("estoque_minimo=%s")
                params.append(estoque_minimo_novo)
            if atualizar_ressuprimento:
                updates.append("estoque_ressuprimento=%s")
                params.append(estoque_ressuprimento_novo)
            if atualizar_maximo:
                updates.append("estoque_maximo=%s")
                params.append(estoque_maximo_novo)
            if atualizar_consumo:
                updates.append("Consumo_Medio_Mensal=%s")
                params.append(cmm)
            if updates:
                params.append(codigo_int)
                cur.execute(f"UPDATE pecas SET {', '.join(updates)} WHERE codigo_int = %s", tuple(params))

            resultado.append({
                "codigo_int": codigo_int,
                "descricao": (v.get("descricao") or "").strip(),
                "total_vendido": total_vendido,
                "consumo_medio_mensal": cmm,
                "estoque_minimo_anterior": float(peca.get("estoque_minimo") or 0),
                "estoque_minimo_atual": estoque_minimo_novo,
                "tempo_reposicao": tempo_reposicao,
                "estoque_ressuprimento_anterior": float(peca.get("estoque_ressuprimento") or 0),
                "estoque_ressuprimento_atual": estoque_ressuprimento_novo,
                "estoque_maximo_anterior": float(peca.get("estoque_maximo") or 0),
                "estoque_maximo_atual": estoque_maximo_novo,
            })

        conn.commit()
        cur.close()
        return {"success": True, "items": resultado}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def gerar_curva(
    servidor: str, banco: str, data_ini: str, data_fim: str, tipo: str, faixas: list,
    nivel: Optional[str] = None,
) -> dict:
    return await asyncio.to_thread(_gerar_curva_sync, servidor, banco, data_ini, data_fim, tipo, faixas, nivel)


async def reprocessar_estoques(
    servidor: str, banco: str, data_ini: str, data_fim: str, grau_atendimento: float,
    nivel: Optional[str] = None,
    atualizar_minimo: bool = False, atualizar_ressuprimento: bool = False,
    atualizar_maximo: bool = False, atualizar_consumo: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _reprocessar_estoques_sync, servidor, banco, data_ini, data_fim, grau_atendimento, nivel,
        atualizar_minimo, atualizar_ressuprimento, atualizar_maximo, atualizar_consumo,
    )

"""Resumo Atendimento — Painel de Relatórios > Pré Venda.

Migração de `Kontacto\\frmrelos.frm` (`VB_Name="FrmRelOSs"` — não
confundir com `FrmRelOs`/"Ordem de Serviço", ver PENDENCIAS.md > "Painel
de Relatórios (VB6)" > "Pré Venda" pro rastreio completo e a correção de
qual arquivo é qual). Relatório operacional por período: uma linha por
O.S., com técnico responsável, horas trabalhadas, quebra Serviço/Peça e
quebra por destino do item (Cliente Pg./Interno-Contrato/Garantia).

Adaptações confirmadas em relação ao `.frm` original (não são suposição —
ver docstrings de `os_service.py`/`tabelas_aux_service.py`):
- **Tipo de O.S.**: o legado usa `os.posicao_os`; esta migração não tem
  essa coluna — o FK real confirmado (`sys.foreign_keys`,
  `tabelas_aux_service.py`) é `os.tipo` → `tipo_os.codigo`. Mesma
  adaptação já usada em "Custo de O.S".
- **Técnico responsável**: `nome_guerra` do funcionário com o MAIOR
  `codigo_int` entre os `executor` dos itens daquela O.S.
  (`os_produto.executor`, coluna real — `os_itens_service.py` confirma
  "executor fica por item") — regra literal do legado, replicada como
  está (é a única forma que o legado tinha de resumir "o técnico" numa
  O.S. que pode ter vários executores por item).
- **Horas**: `os_tempo.hora_inicio`/`hora_fim` (tabela já migrada,
  `os_tempo_service.py`) — MIN/MAX por O.S.
- **Destino do item**: `os_produto.situacao` (0=Cliente, 1=Garantia,
  2=Interno, 3=Rev. de Fábrica) — mesmo achado já confirmado 3x nesta
  sessão (Custo de O.S, Ordem de Serviço, aqui).

Os 3 flags de inclusão (`incluir_cliente_pg`/`incluir_contrato`/
`incluir_garantia`, todos `True` por padrão — mesmo default do `.frm`,
onde os 3 checkboxes vêm marcados) controlam TANTO se a O.S. aparece
(precisa ter total > 0 em pelo menos um destino incluído) QUANTO se a
coluna daquele destino é zerada quando desmarcada — replicado em Python
após buscar os dados brutos, mais simples que replicar em SQL.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _resumo_atendimento_sync(
    servidor: str, banco: str,
    data_ini: Optional[str], data_fim: Optional[str],
    situacao: Optional[str], tipo: Optional[int], tecnico: Optional[int],
    cliente: Optional[int], chassi: Optional[str],
    incluir_cliente_pg: bool, incluir_contrato: bool, incluir_garantia: bool,
) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if data_ini and data_fim:
            where.append("CAST(o.data_termino AS DATE) BETWEEN %s AND %s")
            params.extend([data_ini, data_fim])
        sits = [s.strip() for s in (situacao or "").split(",") if s.strip()]
        if sits:
            where.append(f"o.situacao IN ({','.join(['%s'] * len(sits))})")
            params.extend(sits)
        if tipo is not None:
            where.append("o.tipo = %s")
            params.append(tipo)
        if cliente is not None:
            where.append("o.cliente = %s")
            params.append(cliente)
        if chassi:
            where.append("o.chassi = %s")
            params.append(chassi)
        if tecnico is not None:
            where.append("(SELECT MAX(executor) FROM os_produto WHERE os_produto.os = o.codigo) = %s")
            params.append(tecnico)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        cur.execute(
            "SELECT o.codigo, o.data_termino, o.resumo, t.descricao AS tipo_desc, "
            "  (SELECT MIN(hora_inicio) FROM os_tempo WHERE os_tempo.os = o.codigo) AS hora_inicio, "
            "  (SELECT MAX(hora_fim) FROM os_tempo WHERE os_tempo.os = o.codigo) AS hora_fim, "
            "  (SELECT nome_guerra FROM funcionarios WHERE codigo_int = "
            "     (SELECT MAX(executor) FROM os_produto WHERE os_produto.os = o.codigo)) AS tecnico_nome, "
            "  (SELECT SUM(quant) FROM os_produto WHERE os = o.codigo AND LEFT(codigo_interno,1) = 'S' "
            "     AND ISNULL(item_cancelado,0) = 0) AS tot_horas, "
            "  (SELECT SUM(quant*preco_unitario) FROM os_produto WHERE os = o.codigo AND LEFT(codigo_interno,1) = 'S' "
            "     AND ISNULL(item_cancelado,0) = 0) AS tot_servicos, "
            "  (SELECT SUM(quant*preco_unitario) FROM os_produto WHERE os = o.codigo AND LEFT(codigo_interno,1) <> 'S' "
            "     AND ISNULL(item_cancelado,0) = 0) AS tot_pecas, "
            "  (SELECT SUM(quant*preco_unitario) FROM os_produto WHERE os = o.codigo AND situacao = 0 "
            "     AND ISNULL(item_cancelado,0) = 0) AS tot_cliente_pg, "
            "  (SELECT SUM(quant*preco_unitario) FROM os_produto WHERE os = o.codigo AND situacao IN (2,3) "
            "     AND ISNULL(item_cancelado,0) = 0) AS tot_contrato, "
            "  (SELECT SUM(quant*preco_unitario) FROM os_produto WHERE os = o.codigo AND situacao = 1 "
            "     AND ISNULL(item_cancelado,0) = 0) AS tot_garantia "
            "FROM os o "
            "LEFT JOIN tipo_os t ON t.codigo = o.tipo "
            f"{where_sql} "
            "ORDER BY o.codigo",
            tuple(params),
        )
        rows = cur.fetchall()
        cur.close()

        itens = []
        tot = {"horas": 0.0, "servicos": 0.0, "pecas": 0.0, "contrato": 0.0, "garantia": 0.0, "cliente_pg": 0.0}
        for r in rows:
            v_cliente_pg = float(r.get("tot_cliente_pg") or 0) if incluir_cliente_pg else 0.0
            v_contrato = float(r.get("tot_contrato") or 0) if incluir_contrato else 0.0
            v_garantia = float(r.get("tot_garantia") or 0) if incluir_garantia else 0.0
            if v_cliente_pg <= 0 and v_contrato <= 0 and v_garantia <= 0:
                continue
            dt = r.get("data_termino")
            horas = float(r.get("tot_horas") or 0)
            servicos = round(float(r.get("tot_servicos") or 0), 2)
            pecas = round(float(r.get("tot_pecas") or 0), 2)
            resumo_txt = (r.get("resumo") or "").replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
            itens.append({
                "os": int(r["codigo"]),
                "data_termino": dt.isoformat() if hasattr(dt, "isoformat") else (str(dt)[:10] if dt else None),
                "tecnico_nome": (r.get("tecnico_nome") or "").strip() or "—",
                "hora_inicio": (str(r.get("hora_inicio") or "")).strip() or None,
                "hora_fim": (str(r.get("hora_fim") or "")).strip() or None,
                "tot_horas": round(horas, 2),
                "tot_servicos": servicos,
                "tot_pecas": pecas,
                "tot_contrato": round(v_contrato, 2),
                "tot_garantia": round(v_garantia, 2),
                "tot_cliente_pg": round(v_cliente_pg, 2),
                "tipo_desc": (r.get("tipo_desc") or "").strip() or "—",
                "resumo": resumo_txt,
            })
            tot["horas"] += horas
            tot["servicos"] += servicos
            tot["pecas"] += pecas
            tot["contrato"] += v_contrato
            tot["garantia"] += v_garantia
            tot["cliente_pg"] += v_cliente_pg

        totais = {k: round(v, 2) for k, v in tot.items()}
        return {"success": True, "itens": itens, "totais": totais}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "totais": {}}
    finally:
        conn.close()


async def resumo_atendimento(
    servidor, banco, data_ini, data_fim, situacao, tipo, tecnico, cliente, chassi,
    incluir_cliente_pg, incluir_contrato, incluir_garantia,
):
    return await asyncio.to_thread(
        _resumo_atendimento_sync, servidor, banco, data_ini, data_fim, situacao, tipo, tecnico, cliente, chassi,
        incluir_cliente_pg, incluir_contrato, incluir_garantia,
    )

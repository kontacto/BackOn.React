"""Ordem de Serviço (busca) — Painel de Relatórios > Pré Venda.

Migração de `Revenda\\FrmRelOS.frm` (`VB_Name="FrmRelOs"`) — ver
PENDENCIAS.md > "Painel de Relatórios (VB6)" > "Pré Venda" pro rastreio
completo. **Não é um relatório de período** — é uma tela de busca/lookup
de O.S. por um único critério por vez (Cliente, Data Entrada, Data
Término, Placa, Chassi, intervalo de código de O.S., Marca ou Modelo),
com master-detail (lista de O.S. → itens da O.S. selecionada).

Diferença consciente em relação ao legado: o `.frm` faz `INNER JOIN`
com `marcas`/`modelos` — uma O.S. sem marca/modelo cadastrado nunca
aparece no resultado. Nesta migração usamos **`LEFT JOIN`**: `os` já é
usado de forma mais genérica que no legado (Assistência Técnica,
Equipamentos — nem toda O.S. necessariamente representa um veículo), e
esconder silenciosamente uma O.S. só por falta de marca/modelo seria
perda de dado, não fidelidade ao legado.

`os_produto.situacao` decodificado como Destino (0=Cliente, 1=Garantia,
2=Interno, 3=Rev. de Fábrica) — mesmo achado já confirmado em "Custo de
O.S" e no rastreio de `tabelas_aux_service.py` (FK real pra
`tipo_os_prod`, coluna com nome enganoso).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

DESTINO_LABEL = {0: "Cliente", 1: "Garantia", 2: "Interno", 3: "Rev. de Fábrica"}

_ORDEM_COL = {
    "cliente": "c.nome", "data_entrada": "o.data_entrada", "data_termino": "o.data_termino",
    "placa": "o.placa", "chassi": "o.chassi", "os": "o.codigo",
    "marca": "ma.descricao", "modelo": "mo.descricao",
}


def _busca_os_sync(
    servidor: str, banco: str, filtro: str,
    valor1: Optional[str], valor2: Optional[str], ordem: str,
) -> dict:
    if filtro not in _ORDEM_COL:
        return {"success": False, "message": "Filtro inválido.", "itens": []}
    if not (valor1 or "").strip():
        return {"success": False, "message": "Informe o valor do filtro.", "itens": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        v1 = valor1.strip()
        v2 = (valor2 or "").strip() or v1
        if filtro == "cliente":
            where.append("o.cliente = %s")
            params.append(v1)
        elif filtro == "data_entrada":
            where.append("CAST(o.data_entrada AS DATE) BETWEEN %s AND %s")
            params.extend([v1, v2])
        elif filtro == "data_termino":
            where.append("CAST(o.data_termino AS DATE) BETWEEN %s AND %s")
            params.extend([v1, v2])
        elif filtro == "placa":
            where.append("LEFT(o.placa, %s) = %s")
            params.extend([len(v1), v1])
        elif filtro == "chassi":
            where.append("LEFT(o.chassi, %s) = %s")
            params.extend([len(v1), v1])
        elif filtro == "os":
            where.append("o.codigo BETWEEN %s AND %s")
            params.extend([v1, v2])
        elif filtro == "marca":
            where.append("o.marca = %s")
            params.append(v1)
        elif filtro == "modelo":
            where.append("o.modelo = %s")
            params.append(v1)

        ordem_sql = "ASC" if ordem != "desc" else "DESC"
        cur.execute(
            "SELECT c.codigo AS cliente_codigo, c.nome AS cliente_nome, o.codigo AS os, "
            "  ma.descricao AS marca_desc, mo.descricao AS modelo_desc, "
            "  o.data_entrada, o.data_termino, o.placa, o.chassi, o.situacao "
            "FROM os o "
            "JOIN cliente c ON c.codigo = o.cliente "
            "LEFT JOIN marcas ma ON ma.codigo = o.marca "
            "LEFT JOIN modelos mo ON mo.codigo = o.modelo "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY {_ORDEM_COL[filtro]} {ordem_sql}, c.nome ASC",
            tuple(params),
        )
        rows = cur.fetchall()
        cur.close()

        itens = []
        for r in rows:
            de = r.get("data_entrada")
            dt = r.get("data_termino")
            veiculo = " ".join(x for x in [(r.get("marca_desc") or "").strip(), (r.get("modelo_desc") or "").strip()] if x)
            itens.append({
                "cliente_codigo": r.get("cliente_codigo"),
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "os": int(r["os"]),
                "veiculo": veiculo or "—",
                "data_entrada": de.isoformat() if hasattr(de, "isoformat") else (str(de)[:10] if de else None),
                "data_termino": dt.isoformat() if hasattr(dt, "isoformat") else (str(dt)[:10] if dt else None),
                "placa": (r.get("placa") or "").strip(),
                "chassi": (r.get("chassi") or "").strip(),
                "situacao": (r.get("situacao") or "").strip(),
            })
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


def _itens_os_sync(servidor: str, banco: str, os_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT i.codigo_interno AS codigo, COALESCE(pe.descricao, sv.descricao, i.codigo_interno) AS descricao, "
            "  i.quant, i.preco_unitario, i.situacao "
            "FROM os_produto i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE i.os = %s AND ISNULL(i.item_cancelado,0) = 0 "
            "ORDER BY i.cod_os_prod",
            (os_codigo,),
        )
        itens = []
        for r in cur.fetchall():
            qtd = float(r.get("quant") or 0)
            valor_unit = float(r.get("preco_unitario") or 0)
            itens.append({
                "codigo": (r.get("codigo") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "qtd": qtd,
                "valor_unitario": valor_unit,
                "valor_total": round(qtd * valor_unit, 2),
                "destino": DESTINO_LABEL.get(int(r["situacao"]) if r.get("situacao") is not None else -1, "—"),
            })
        cur.close()
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


async def busca_os(servidor, banco, filtro, valor1, valor2, ordem):
    return await asyncio.to_thread(_busca_os_sync, servidor, banco, filtro, valor1, valor2, ordem)


async def itens_os(servidor, banco, os_codigo):
    return await asyncio.to_thread(_itens_os_sync, servidor, banco, os_codigo)

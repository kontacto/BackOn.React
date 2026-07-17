"""Cilindros — Cadastro/Consulta (Fase 1 do módulo Cilindros). Tabela
`Cilindro`. Legado: `FrmManCil.frm` (Frame1 "Cadastro", Frame2 "Consulta").

Módulo específico de segmento (indústria/locação de gás) — gated pela
coluna já existente `controle_configuracao.Cilindro` (mesmo mecanismo de
Posto/Serviços, ver MODULE_TELAS em controle_config_service.py). Neste
banco de teste (GERDELL/BARESTELA) o módulo nunca foi usado — todas as
tabelas operacionais (Cilindro, Cilindro_Cliente, Cilindro_Serie, Viagem,
Viagem_Cilindro, Viagem_Retorno) estão zeradas, confirmado ao vivo
2026-07-14.

Regra real (não um truque): a chave de duplicidade do cilindro é o
conjunto (codigo, capacidade, pressao, padrao) — não existe um código
único simples, um mesmo "produto" pode ter várias combinações de
capacidade/pressão/padrão, cada uma um cilindro cadastrado à parte.
Confirmado em `Command1_Click` do legado.

Grupo Gás é derivado automaticamente do `codigo` (produto de venda) —
tudo antes do primeiro "." — e a linha correspondente em
`Cilindro_Grupo` é criada on-the-fly se ainda não existir (mesmo
comportamento do legado, `Campo_LostFocus(78)`/`Command1_Click`).

Exclusão bloqueada se houver vínculo em `Cilindro_Cliente`,
`Cilindro_Serie`, `Viagem_Cilindro` ou pedido de venda aberto/fechado
para aquele cilindro (`Command3_Click` no legado).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _row_to_dict(r: dict) -> dict:
    return dict(r)


def _grupo_gas_de(codigo_produto: str) -> str:
    return (codigo_produto or "").split(".")[0].strip()[:8]


def _garantir_grupo_gas_sync(cur, grupo_gas: str, descricao: str) -> None:
    if not grupo_gas:
        return
    cur.execute("SELECT codigo FROM Cilindro_Grupo WHERE codigo=%s", (grupo_gas,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO Cilindro_Grupo (codigo, descricao, situacao) VALUES (%s,%s,'A')",
            (grupo_gas, descricao or grupo_gas),
        )


def _list_cilindros_sync(servidor: str, banco: str, search: str, page: int, size: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = "1=1"
        params: list = []
        term = (search or "").strip()
        if term:
            where += " AND (c.codigo LIKE %s OR c.descricao LIKE %s OR c.grupo_gas LIKE %s)"
            like = f"%{term}%"
            params += [like, like, like]
        cur.execute(f"SELECT COUNT(*) AS n FROM Cilindro c WHERE {where}", tuple(params))
        total = cur.fetchone()["n"]
        offset = max(0, (page - 1) * size)
        cur.execute(
            f"SELECT c.cod, c.codigo, c.capacidade, c.pressao, c.padrao, c.descricao, "
            f"c.grupo_gas, c.situacao, c.preco_venda FROM Cilindro c WHERE {where} "
            f"ORDER BY c.codigo, c.capacidade, c.pressao, c.padrao "
            f"OFFSET {offset} ROWS FETCH NEXT {size} ROWS ONLY",
            tuple(params),
        )
        items = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items, "total": total}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}
    finally:
        conn.close()


def _find_produto_por_codigo_fab_sync(servidor: str, banco: str, codigo_fab: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT descricao FROM Pecas WHERE codigo_fab=%s", (codigo_fab,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": True, "found": False}
        return {"success": True, "found": True, "descricao": (row.get("descricao") or "").strip()}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _get_cilindro_sync(servidor: str, banco: str, cod: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM Cilindro WHERE cod=%s", (cod,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Cilindro não encontrado."}
        cur.close()
        return {"success": True, "item": _row_to_dict(row)}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


CAMPOS = [
    "codigo", "capacidade", "pressao", "padrao", "descricao", "grupo_gas",
    "qtd_produto", "un_qtd_produto", "un_cp", "fator",
    "peso_liq", "peso_bruto", "preco_venda", "preco_custo", "preco_locacao",
    "prazo_revisao", "situacao", "E_CILINDRO",
]


def _save_cilindro_sync(servidor: str, banco: str, cod: Optional[int], dados: dict) -> dict:
    codigo = (dados.get("codigo") or "").strip()
    if not codigo:
        return {"success": False, "message": "Informe o Produto de Venda."}
    capacidade = int(dados.get("capacidade") or 0)
    pressao = int(dados.get("pressao") or 0)
    padrao = (dados.get("padrao") or "").strip()
    if not padrao:
        return {"success": False, "message": "Informe o Padrão."}
    if not (dados.get("situacao") or "").strip():
        return {"success": False, "message": "Informe a Situação."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT descricao FROM Pecas WHERE codigo_fab=%s", (codigo,))
        prod = cur.fetchone()
        if not prod:
            cur.close()
            return {"success": False, "message": "Produto de Venda não cadastrado."}

        cur.execute("SELECT descricao FROM Cilindro_Fabricante WHERE fabricante=%s", (padrao,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Padrão não cadastrado."}

        cur.execute(
            "SELECT cod FROM Cilindro WHERE codigo=%s AND capacidade=%s AND pressao=%s AND padrao=%s"
            + (" AND cod<>%s" if cod else ""),
            (codigo, capacidade, pressao, padrao, cod) if cod else (codigo, capacidade, pressao, padrao),
        )
        dup = cur.fetchone()
        if dup:
            cur.close()
            return {"success": False, "message": f"Cilindro ({codigo} - {capacidade} - {pressao} - {padrao}) já cadastrado com o código {dup['cod']}."}

        grupo_gas = _grupo_gas_de(codigo)
        _garantir_grupo_gas_sync(cur, grupo_gas, dados.get("descricao") or "")

        campos = {c: dados.get(c) for c in CAMPOS if c in dados}
        campos["codigo"] = codigo
        campos["capacidade"] = capacidade
        campos["pressao"] = pressao
        campos["padrao"] = padrao
        campos["grupo_gas"] = grupo_gas
        campos["situacao"] = dados["situacao"].strip().upper()[:2]
        campos["E_CILINDRO"] = bool(dados.get("E_CILINDRO", True))

        if cod:
            set_clause = ", ".join(f"[{c}]=%s" for c in campos)
            cur.execute(f"UPDATE Cilindro SET {set_clause} WHERE cod=%s", (*campos.values(), cod))
        else:
            cols = list(campos.keys())
            placeholders = ",".join(["%s"] * len(cols))
            cur.execute(f"INSERT INTO Cilindro ([{'],['.join(cols)}]) VALUES ({placeholders})", tuple(campos.values()))
            conn.commit()
            cur.execute(
                "SELECT cod FROM Cilindro WHERE codigo=%s AND capacidade=%s AND pressao=%s AND padrao=%s",
                (codigo, capacidade, pressao, padrao),
            )
            cod = cur.fetchone()["cod"]

        conn.commit()
        cur.close()
        return {"success": True, "message": "Cilindro gravado.", "cod": cod}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


_DEP_CHECKS = [
    ("clientes", "SELECT TOP 1 1 FROM Cilindro_Cliente WHERE cilindro=%s"),
    ("números de série", "SELECT TOP 1 1 FROM Cilindro_Serie WHERE cilindro=%s"),
    ("viagens", "SELECT TOP 1 1 FROM Viagem_Cilindro WHERE cilindro=%s"),
    ("pedidos de venda", "SELECT TOP 1 1 FROM Pedido_Venda_Prod pvp JOIN Pedido_Venda pv ON pv.Pedido = pvp.Pedido "
                          "WHERE pvp.Area_Venda=%s AND (pv.Situacao='A' OR pv.Situacao='F')"),
]


def _delete_cilindro_sync(servidor: str, banco: str, cod: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cod FROM Cilindro WHERE cod=%s", (cod,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Cilindro não encontrado."}
        for label, sql in _DEP_CHECKS:
            try:
                cur.execute(sql, (cod,))
                if cur.fetchone():
                    cur.close()
                    return {"success": False, "message": f"Existem registros de {label} para este cilindro — não pode ser excluído."}
            except Exception:
                continue
        cur.execute("DELETE FROM Cilindro WHERE cod=%s", (cod,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Cilindro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_cilindros(servidor: str, banco: str, search: str = "", page: int = 1, size: int = 20) -> dict:
    return await asyncio.to_thread(_list_cilindros_sync, servidor, banco, search, page, size)


async def get_cilindro(servidor: str, banco: str, cod: int) -> dict:
    return await asyncio.to_thread(_get_cilindro_sync, servidor, banco, cod)


async def find_produto_por_codigo_fab(servidor: str, banco: str, codigo_fab: str) -> dict:
    return await asyncio.to_thread(_find_produto_por_codigo_fab_sync, servidor, banco, codigo_fab)


async def save_cilindro(servidor: str, banco: str, cod: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_cilindro_sync, servidor, banco, cod, dados)


async def delete_cilindro(servidor: str, banco: str, cod: int) -> dict:
    return await asyncio.to_thread(_delete_cilindro_sync, servidor, banco, cod)

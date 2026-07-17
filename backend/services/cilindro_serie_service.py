"""Cilindro/Nº Série (Fase 2 do módulo Cilindros). Tabela `Cilindro_Serie`.

Legado: `FrmManCil.frm`, `Frame4` "Nº Série Cilindro" — popup aberto pelo
botão "Cilindro/Nº Série" (`Command8`) da tela de Cadastro de Cilindros, não
uma tela separada. Ver PENDENCIAS.md > "Cilindros".

Rastreia unidades físicas serializadas de um cilindro cadastrado (`Cilindro`,
Fase 1): compra, fabricação, última entrada/saída, carga (Cheio/Vazio) e
destino atual (Cliente/Fornecedor/Pátio — pátio = destino 0).

Regra real (não um truque VB6): a previsão da próxima revisão é calculada a
partir de `Prazo_Revisao` (anos, cadastrado no `Cilindro` pai) somado à data
da última revisão — manutenção preventiva por unidade. No legado
(`Campo_LostFocus`/`Monta_Tela_Cil_Ser`) esse valor é só exibido, nunca
persistido — replicado aqui como campo calculado na resposta, não uma coluna
gravada.

Diferença deliberada em relação ao legado (mesma razão do
`cilindro_cliente_service.py`): o cilindro é escolhido a partir da lista já
cadastrada (picker no frontend), então este serviço recebe o `cod` do
Cilindro diretamente em vez de resolver por código+capacidade+pressão+padrão.
"""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn


def _proxima_revisao(revisao, prazo_revisao: Optional[int]):
    if not revisao or not prazo_revisao:
        return None
    try:
        d = revisao if isinstance(revisao, date) else date.fromisoformat(str(revisao)[:10])
        return date(d.year + int(prazo_revisao), d.month, d.day).isoformat()
    except Exception:
        return None


def _list_serie_sync(servidor: str, banco: str, search: str, page: int, size: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = "1=1"
        params: list = []
        term = (search or "").strip()
        if term:
            where += " AND (cs.numero_de_serie LIKE %s OR cil.codigo LIKE %s)"
            like = f"%{term}%"
            params += [like, like]
        cur.execute(
            f"SELECT COUNT(*) AS n FROM Cilindro_Serie cs JOIN Cilindro cil ON cil.cod = cs.cilindro WHERE {where}",
            tuple(params),
        )
        total = cur.fetchone()["n"]
        offset = max(0, (page - 1) * size)
        cur.execute(
            f"SELECT cs.codigo, cs.numero_de_serie, cs.cilindro, cil.codigo AS cilindro_codigo, "
            f"cil.capacidade, cil.pressao, cil.padrao, cil.descricao, cs.destino, cs.tipo_destino, "
            f"cs.carga, cs.situacao, cs.revisao, cil.prazo_revisao "
            f"FROM Cilindro_Serie cs JOIN Cilindro cil ON cil.cod = cs.cilindro WHERE {where} "
            f"ORDER BY cil.codigo, cil.capacidade, cil.pressao, cil.padrao, cs.numero_de_serie "
            f"OFFSET {offset} ROWS FETCH NEXT {size} ROWS ONLY",
            tuple(params),
        )
        items = []
        for r in cur.fetchall():
            d = dict(r)
            d["proxima_revisao"] = _proxima_revisao(d.get("revisao"), d.get("prazo_revisao"))
            items.append(d)
        cur.close()
        return {"success": True, "items": items, "total": total}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}
    finally:
        conn.close()


def _get_serie_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cs.*, cil.codigo AS cilindro_codigo, cil.capacidade, cil.pressao, cil.padrao, "
            "cil.prazo_revisao FROM Cilindro_Serie cs JOIN Cilindro cil ON cil.cod = cs.cilindro "
            "WHERE cs.codigo=%s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": False, "message": "Registro não encontrado."}
        item = dict(row)
        item["proxima_revisao"] = _proxima_revisao(item.get("revisao"), item.get("prazo_revisao"))
        return {"success": True, "item": item}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


CAMPOS_DATA = ["data_compra", "nf_compra", "fornecedor", "fabricacao", "entrada", "saida", "revisao"]


def _save_serie_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    numero_de_serie = (dados.get("numero_de_serie") or "").strip()
    if not numero_de_serie:
        return {"success": False, "message": "Informe o Número de Série."}
    cilindro_cod = dados.get("cilindro") or 0
    if not cilindro_cod:
        return {"success": False, "message": "Informe o Cilindro."}
    situacao = (dados.get("situacao") or "A").strip()
    destino = dados.get("destino") or 0
    tipo_destino = 1 if dados.get("tipo_destino") == "F" else 0
    carga = 1 if dados.get("carga") == "VAZIO" else 0

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT cod FROM Cilindro WHERE cod=%s", (cilindro_cod,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Cilindro não cadastrado."}

        if destino:
            tabela = "Fornecedor" if tipo_destino == 1 else "Cliente"
            coluna = "Codigo_Int" if tipo_destino == 1 else "Codigo"
            cur.execute(f"SELECT {coluna} FROM {tabela} WHERE {coluna}=%s", (destino,))
            if not cur.fetchone():
                cur.close()
                return {"success": False, "message": f"{tabela} não cadastrado."}

        cur.execute("SELECT descricao FROM Situacao WHERE codigo=%s", (situacao,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Situação não cadastrada."}

        campos = {c: (dados.get(c) or None) for c in CAMPOS_DATA}
        campos["numero_de_serie"] = numero_de_serie
        campos["cilindro"] = cilindro_cod
        campos["destino"] = destino
        campos["tipo_destino"] = tipo_destino
        campos["carga"] = carga
        campos["situacao"] = situacao

        if codigo:
            set_clause = ", ".join(f"[{c}]=%s" for c in campos)
            cur.execute(f"UPDATE Cilindro_Serie SET {set_clause} WHERE codigo=%s", (*campos.values(), codigo))
        else:
            cols = list(campos.keys())
            placeholders = ",".join(["%s"] * len(cols))
            cur.execute(f"INSERT INTO Cilindro_Serie ([{'],['.join(cols)}]) VALUES ({placeholders})", tuple(campos.values()))
            conn.commit()
            cur.execute("SELECT codigo FROM Cilindro_Serie WHERE numero_de_serie=%s", (numero_de_serie,))
            row = cur.fetchone()
            codigo = row["codigo"] if row else None

        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro gravado.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_serie_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM Cilindro_Serie WHERE codigo=%s", (codigo,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Registro não encontrado."}
        try:
            cur.execute("SELECT TOP 1 1 FROM Viagem_Cilindro WHERE num_serie_retorno=%s", (codigo,))
            if cur.fetchone():
                cur.close()
                return {"success": False, "message": "Existem viagens vinculadas a este número de série — não pode ser excluído."}
        except Exception:
            pass
        cur.execute("DELETE FROM Cilindro_Serie WHERE codigo=%s", (codigo,))
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


async def list_serie(servidor: str, banco: str, search: str = "", page: int = 1, size: int = 20) -> dict:
    return await asyncio.to_thread(_list_serie_sync, servidor, banco, search, page, size)


async def get_serie(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_serie_sync, servidor, banco, codigo)


async def save_serie(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_serie_sync, servidor, banco, codigo, dados)


async def delete_serie(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_serie_sync, servidor, banco, codigo)

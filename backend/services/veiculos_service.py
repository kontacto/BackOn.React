"""Serviço de Veículos (tabela `veiculos_transp` + N:N `veiculos_rota`).

Cadastro de Veículos > Cadastros (tela própria, não é Tabela Auxiliar — liberada
pela flag de módulo `Cilindro` OU para o usuário master, ver `app/veiculos.tsx`
e o hub `app/(tabs)/cadastros.tsx`). Legado: FrmManVei ("Cadastro de
Veículos..."). `marca`/`modelo`/`cor` reaproveitam as mesmas tabelas/telas já
usadas em Produtos (`marcas.marca_produto=0` filtra só marcas de veículo,
mesmo padrão de `_import_fipe_sync`); `rotas` reaproveita a Tabela Auxiliar
Rotas.

Desvio deliberado do legado: `Command1_Click` decide INSERT/UPDATE
consultando `veiculos_transp` pela PLACA digitada (não pelo `codigo`) — se o
usuário renomeia a Placa de um registro existente pra um valor não usado, o
legado silenciosamente cria uma linha NOVA em vez de alterar a existente
(bug de identidade, porque Placa é ao mesmo tempo chave de negócio e campo
livre editável). Aqui o app sempre conhece o `codigo` (IDENTITY) do registro
sendo editado (carregado da lista) e faz UPDATE ... WHERE codigo=%s nesse
caso; placa duplicada em OUTRO veículo é bloqueada explicitamente com
mensagem clara, em vez do bug silencioso.

Bug de validação corrigido: ao validar o campo Tipo, o legado checa
`Motorista.ListIndex` de novo em vez de `Tipo.ListIndex` (copy-paste) — na
prática o legado NUNCA exige Tipo preenchido, apesar da mensagem de erro
("Defina o Tipo do Veículo!") deixar clara a intenção original. Aqui Tipo é
validado de verdade.

Guard de exclusão: `viagem.veiculo` e `MDFe.veiculo` (ambas int, mesmo tipo de
`veiculos_transp.codigo`; nenhuma tem FK real no banco, mas são o mesmo
padrão de "soft reference" já usado nas demais telas) — checadas mesmo vazias
no banco de teste (nenhum dos dois subsistemas está implementado neste app
ainda). NÃO checa `comissao_venda.veiculo` — apesar do nome, essa coluna é
`real` (percentual de comissão), não uma referência a `veiculos_transp.codigo`
(falso positivo por coincidência de nome). `veiculos_rota` não é guard, é
cascata: vínculos de rota são só preferência de roteirização, sem
significado próprio que impeça a exclusão do veículo.
"""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn

CAMPOS = [
    "placa", "descricao", "motorista", "auxiliar", "hodometro", "km",
    "data_compra", "valor_compra", "peso_max", "volume_max", "peso_min", "volume_min",
    "marca", "modelo", "cor", "motor", "renavam", "chassi", "combustivel",
    "ano_fab", "ano_mod", "tipo", "situacao",
    "doc_proprietario", "rntrc_proprietario", "nome_proprietario", "ie_proprietario", "uf_proprietario",
    "tpRod", "tpCar", "UF",
]


def _list_veiculos_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE v.placa LIKE %s OR v.descricao LIKE %s"
            params = (like, like)
        cur.execute(f"""
            SELECT v.codigo, v.placa, v.descricao, v.situacao,
                   m.descricao AS marca_desc, mo.descricao AS modelo_desc,
                   f.nome_guerra AS motorista_nome
            FROM veiculos_transp v
            LEFT JOIN marcas m ON m.codigo = v.marca
            LEFT JOIN modelos mo ON mo.codigo = v.modelo AND mo.cod_marca = v.marca
            LEFT JOIN funcionarios f ON f.codigo_int = v.motorista
            {where}
            ORDER BY v.placa
        """, params)
        items = [{
            "codigo": int(r["codigo"]),
            "placa": (r.get("placa") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "situacao": (r.get("situacao") or "A").strip(),
            "marca_desc": (r.get("marca_desc") or "").strip(),
            "modelo_desc": (r.get("modelo_desc") or "").strip(),
            "motorista_nome": (r.get("motorista_nome") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _get_veiculo_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cols = ", ".join(CAMPOS)
        cur.execute(f"SELECT codigo, {cols} FROM veiculos_transp WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Veículo não encontrado."}
        veiculo: dict = {"codigo": int(row["codigo"])}
        for c in CAMPOS:
            v = row.get(c)
            if c == "data_compra":
                veiculo[c] = v.isoformat() if v else None
            elif isinstance(v, str):
                veiculo[c] = v.strip()
            else:
                veiculo[c] = v
        cur.execute("""
            SELECT vr.rota, r.descricao FROM veiculos_rota vr
            JOIN rotas r ON r.codigo = vr.rota
            WHERE vr.veiculo=%s ORDER BY r.descricao
        """, (codigo,))
        veiculo["rotas"] = [
            {"rota": int(r["rota"]), "descricao": (r.get("descricao") or "").strip()}
            for r in cur.fetchall()
        ]
        cur.close()
        return {"success": True, "veiculo": veiculo}
    finally:
        conn.close()


def _save_veiculo_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    placa = (dados.get("placa") or "").strip().upper()
    if not placa:
        return {"success": False, "message": "Defina a Placa do Veículo!"}
    if not dados.get("motorista"):
        return {"success": False, "message": "Defina o Motorista do Veículo!"}
    if not dados.get("marca"):
        return {"success": False, "message": "Defina a Marca do Veículo!"}
    if not dados.get("modelo"):
        return {"success": False, "message": "Defina o Modelo do Veículo!"}
    if not dados.get("cor"):
        return {"success": False, "message": "Defina a Cor do Veículo!"}
    if dados.get("combustivel") in (None, ""):
        return {"success": False, "message": "Defina o Combustível do Veículo!"}
    if dados.get("tipo") in (None, ""):
        return {"success": False, "message": "Defina o Tipo do Veículo!"}

    ano_atual = date.today().year
    vals = {
        "placa": placa,
        "descricao": (dados.get("descricao") or "").strip()[:30],
        "motorista": dados.get("motorista"),
        "auxiliar": dados.get("auxiliar") or None,
        "hodometro": dados.get("hodometro") or 0,
        "km": dados.get("km") or 0,
        "data_compra": dados.get("data_compra") or None,
        "valor_compra": dados.get("valor_compra") or 0,
        "peso_max": dados.get("peso_max") or 0,
        "volume_max": dados.get("volume_max") or 0,
        "peso_min": dados.get("peso_min") or 0,
        "volume_min": dados.get("volume_min") or 0,
        "marca": dados.get("marca"),
        "modelo": dados.get("modelo"),
        "cor": dados.get("cor"),
        "motor": (dados.get("motor") or "").strip()[:13],
        "renavam": (dados.get("renavam") or "").strip()[:10],
        "chassi": (dados.get("chassi") or "").strip()[:18],
        "combustivel": str(dados.get("combustivel")),
        "ano_fab": dados.get("ano_fab") or ano_atual,
        "ano_mod": dados.get("ano_mod") or ano_atual,
        "tipo": str(dados.get("tipo")),
        "situacao": ((dados.get("situacao") or "").strip().upper() or "A")[:2],
        "doc_proprietario": (dados.get("doc_proprietario") or "").strip()[:14],
        "rntrc_proprietario": (dados.get("rntrc_proprietario") or "").strip()[:8],
        "nome_proprietario": (dados.get("nome_proprietario") or "").strip()[:60],
        "ie_proprietario": (dados.get("ie_proprietario") or "").strip()[:14],
        "uf_proprietario": (dados.get("uf_proprietario") or "").strip()[:2].upper(),
        "tpRod": (dados.get("tpRod") or "").strip()[:2],
        "tpCar": (dados.get("tpCar") or "").strip()[:2],
        "UF": (dados.get("UF") or "").strip()[:2].upper(),
    }

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 codigo FROM veiculos_transp WHERE placa=%s", (placa,))
        existing = cur.fetchone()
        if existing and (not codigo or int(existing["codigo"]) != int(codigo)):
            return {"success": False, "message": f"Placa '{placa}' já cadastrada para outro veículo."}

        if codigo:
            set_sql = ", ".join(f"{c}=%s" for c in CAMPOS)
            cur.execute(
                f"UPDATE veiculos_transp SET {set_sql} WHERE codigo=%s",
                tuple(vals[c] for c in CAMPOS) + (codigo,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Veículo não encontrado."}
            novo_codigo = codigo
        else:
            cols_sql = ", ".join(CAMPOS)
            placeholders = ", ".join(["%s"] * len(CAMPOS))
            cur.execute(
                f"INSERT INTO veiculos_transp ({cols_sql}) OUTPUT INSERTED.codigo VALUES ({placeholders})",
                tuple(vals[c] for c in CAMPOS),
            )
            row = cur.fetchone()
            novo_codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo_codigo, "message": "Veículo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_veiculo_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        for tabela, rotulo in (
            ("viagem", "Viagens"),
            ("MDFe", "Manifestos de Documentos Fiscais (MDF-e)"),
        ):
            cur.execute(f"SELECT TOP 1 1 AS ok FROM {tabela} WHERE veiculo=%s", (codigo,))
            if cur.fetchone():
                return {"success": False, "message": f"Veículo vinculado a {rotulo} — não pode ser excluído."}
        cur.execute("DELETE FROM veiculos_rota WHERE veiculo=%s", (codigo,))
        cur.execute("DELETE FROM veiculos_transp WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Veículo não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Veículo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _add_veiculo_rota_sync(servidor: str, banco: str, codigo: int, rota: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM veiculos_rota WHERE veiculo=%s AND rota=%s", (codigo, rota))
        if cur.fetchone():
            return {"success": False, "message": "Rota já cadastrada para este veículo."}
        cur.execute("INSERT INTO veiculos_rota (veiculo, rota) VALUES (%s,%s)", (codigo, rota))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Rota vinculada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _remove_veiculo_rota_sync(servidor: str, banco: str, codigo: int, rota: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM veiculos_rota WHERE veiculo=%s AND rota=%s", (codigo, rota))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Rota removida."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _list_motoristas_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("""
            SELECT f.codigo_int, f.nome_guerra FROM funcionarios f
            JOIN Funcoes fc ON fc.codigo = f.cod_funcao
            WHERE f.situacao='A' AND fc.descricao='MOTORISTA'
            ORDER BY f.nome_guerra
        """)
        items = [{"codigo": int(r["codigo_int"]), "nome": (r.get("nome_guerra") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _list_auxiliares_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("""
            SELECT f.codigo_int, f.nome_guerra FROM funcionarios f
            JOIN Funcoes fc ON fc.codigo = f.cod_funcao
            WHERE f.situacao='A' AND fc.descricao='MOTORISTA AUXILIAR'
            ORDER BY f.nome_guerra
        """)
        items = [{"codigo": int(r["codigo_int"]), "nome": (r.get("nome_guerra") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def list_veiculos(servidor, banco, search):
    return await asyncio.to_thread(_list_veiculos_sync, servidor, banco, search)


async def get_veiculo(servidor, banco, codigo):
    return await asyncio.to_thread(_get_veiculo_sync, servidor, banco, codigo)


async def save_veiculo(servidor, banco, codigo, dados):
    return await asyncio.to_thread(_save_veiculo_sync, servidor, banco, codigo, dados)


async def delete_veiculo(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_veiculo_sync, servidor, banco, codigo)


async def add_veiculo_rota(servidor, banco, codigo, rota):
    return await asyncio.to_thread(_add_veiculo_rota_sync, servidor, banco, codigo, rota)


async def remove_veiculo_rota(servidor, banco, codigo, rota):
    return await asyncio.to_thread(_remove_veiculo_rota_sync, servidor, banco, codigo, rota)


async def list_motoristas(servidor, banco):
    return await asyncio.to_thread(_list_motoristas_sync, servidor, banco)


async def list_auxiliares(servidor, banco):
    return await asyncio.to_thread(_list_auxiliares_sync, servidor, banco)

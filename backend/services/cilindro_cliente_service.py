"""Clientes x Cilindro (Fase 2 do módulo Cilindros). Tabela `Cilindro_Cliente`.

Legado: `FrmManCil.frm`, `Frame3` "Cilindros X Clientes" — não é uma tela
separada, é um popup aberto pelo botão "Cliente/ Cilindro" (`Command7`) da
tela de Cadastro de Cilindros. Ver PENDENCIAS.md > "Cilindros" para o
rastreio completo e a confirmação dessa arquitetura (2026-07-14).

Regra real (não um truque VB6): o vínculo (cliente, cilindro) é único — não
existem colunas adicionais além da dupla FK. Gravar só insere se o par ainda
não existir; se já existir, não faz nada (sem update, é só existência do
vínculo). É o mesmo vínculo que `FrmPedCil` cria automaticamente na primeira
venda de um item de cilindro para um cliente (ver "Pedido de Cilindro —
Unificação com Pedido de Venda Geral" em CLAUDE.md) — esta tela é a via
manual do mesmo relacionamento. Rastreado de `Command14_Click`/
`Command16_Click` do legado.

Diferença deliberada em relação ao legado: `FrmManCil` resolve o cilindro
digitando código+capacidade+pressão+padrão à mão (não há picker no VB6).
Esta migração já tem uma tela/lista de Cilindros cadastrados
(`cilindro_service.list_cilindros`) — o frontend usa ela como picker, então
aqui basta receber o `cod` do Cilindro já resolvido, sem repetir a busca por
combinação.
"""
import asyncio

from db.connection import _open_conn


def _list_vinculos_sync(servidor: str, banco: str, search: str, page: int, size: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = "1=1"
        params: list = []
        term = (search or "").strip()
        if term:
            where += " AND (cli.nome LIKE %s OR cil.codigo LIKE %s)"
            like = f"%{term}%"
            params += [like, like]
        cur.execute(
            f"SELECT COUNT(*) AS n FROM Cilindro_Cliente cc "
            f"JOIN Cilindro cil ON cil.cod = cc.cilindro "
            f"JOIN Cliente cli ON cli.codigo = cc.cliente WHERE {where}",
            tuple(params),
        )
        total = cur.fetchone()["n"]
        offset = max(0, (page - 1) * size)
        cur.execute(
            f"SELECT cc.cliente, cli.nome AS cliente_nome, cc.cilindro, cil.codigo, "
            f"cil.capacidade, cil.pressao, cil.padrao, cil.descricao "
            f"FROM Cilindro_Cliente cc "
            f"JOIN Cilindro cil ON cil.cod = cc.cilindro "
            f"JOIN Cliente cli ON cli.codigo = cc.cliente WHERE {where} "
            f"ORDER BY cli.nome, cil.codigo, cil.capacidade, cil.pressao, cil.padrao "
            f"OFFSET {offset} ROWS FETCH NEXT {size} ROWS ONLY",
            tuple(params),
        )
        items = [dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items, "total": total}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}
    finally:
        conn.close()


def _save_vinculo_sync(servidor: str, banco: str, cliente: int, cilindro_cod: int) -> dict:
    if not cliente:
        return {"success": False, "message": "Informe o Cliente."}
    if not cilindro_cod:
        return {"success": False, "message": "Informe o Cilindro."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cod FROM Cilindro WHERE cod=%s", (cilindro_cod,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Cilindro não cadastrado."}
        cil_cod = row["cod"]

        cur.execute("SELECT codigo FROM Cliente WHERE codigo=%s", (cliente,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Cliente não cadastrado."}

        cur.execute("SELECT cilindro FROM Cilindro_Cliente WHERE cliente=%s AND cilindro=%s", (cliente, cil_cod))
        if not cur.fetchone():
            cur.execute("INSERT INTO Cilindro_Cliente (cliente, cilindro) VALUES (%s,%s)", (cliente, cil_cod))
            conn.commit()

        cur.close()
        return {"success": True, "message": "Vínculo gravado.", "cilindro": cil_cod}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_vinculo_sync(servidor: str, banco: str, cliente: int, cilindro: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cilindro FROM Cilindro_Cliente WHERE cliente=%s AND cilindro=%s", (cliente, cilindro))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Vínculo não encontrado."}
        cur.execute("DELETE FROM Cilindro_Cliente WHERE cliente=%s AND cilindro=%s", (cliente, cilindro))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Vínculo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_vinculos(servidor: str, banco: str, search: str = "", page: int = 1, size: int = 20) -> dict:
    return await asyncio.to_thread(_list_vinculos_sync, servidor, banco, search, page, size)


async def save_vinculo(servidor: str, banco: str, cliente: int, cilindro_cod: int) -> dict:
    return await asyncio.to_thread(_save_vinculo_sync, servidor, banco, cliente, cilindro_cod)


async def delete_vinculo(servidor: str, banco: str, cliente: int, cilindro: int) -> dict:
    return await asyncio.to_thread(_delete_vinculo_sync, servidor, banco, cliente, cilindro)

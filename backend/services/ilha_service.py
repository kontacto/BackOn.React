"""Ilhas (Posto de Combustível) — tabela `ilha`.

Legado: `frmmanilha.frm` ("Manutenção de Ilhas"). Chave natural composta
(`data`, `ilha`, `turno`) — sem PK própria. Fiel ao legado: **só
Incluir/Excluir, sem Alterar** (o `.frm` não tem botão de alteração —
pra trocar o funcionário de uma combinação já existente, exclui e inclui
de novo).

Schema conferido ao vivo em GERDELL/BARESTELA: `ilha` (data date NOT
NULL, ilha smallint NOT NULL, turno smallint NOT NULL, funcionario int
NULL). **Correção 2026-07-13**: uma primeira leitura de `sys.foreign_keys`
encontrou `ilha.ilha -> bomba.codigo` (em vez de `bomba.ilha`) e uma
versão anterior deste service passou a listar/validar por `bomba.codigo`
por causa disso. Investigando mais a fundo (ao migrar "Bombas" e achar o
mesmo padrão estranho em `estoque.combustivel`, que tinha DUAS FKs
simultâneas pra tabelas diferentes — logicamente impossível se estivessem
ativas), confirmou-se via `sys.foreign_keys.is_disabled`/`is_not_trusted`
que **todas as FKs desta área do schema (`ilha`, `bomba`, `tanque`,
`estoque`, `mov_bomba`, `bomba_encerrante`, `tanque_nf`, `tanque_estoque`)
estão desabilitadas** — são vestígios de uma migração de dados antiga,
não regras vigentes. Ou seja, o banco NÃO impede gravar em `ilha.ilha`
um valor que não exista em `bomba.codigo`. Revertido para o
comportamento fiel ao `.frm` original: o combo "Ilha" lista
`SELECT DISTINCT ilha FROM bomba ORDER BY ilha` (o número de agrupamento
físico, não o código da bomba) — **lição geral**: nunca tratar uma linha
de `sys.foreign_keys` como regra vigente sem checar `is_disabled`/
`is_not_trusted` primeiro.
- Turno: o `.frm` carrega de um combo estático (`frmmanilha.frx`, recurso
  binário não legível como texto) — aqui geramos 1..`controle.qtd_turnos`
  (mesmo campo usado por Fechamento/Reabertura de Turno), com fallback
  pra 1 turno se `qtd_turnos` ainda não estiver configurado (0 no banco
  de teste atual).
- Funcionário: `funcionarios` com `situacao='A'`, mesmo filtro do legado.
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG


def _list_opcoes_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        # Mesma query do `.frm` original — número de agrupamento físico
        # "ilha", não o código da bomba (ver nota no topo do arquivo sobre
        # as FKs desabilitadas nesta área do schema).
        cur.execute("SELECT DISTINCT ilha FROM bomba WHERE ilha IS NOT NULL ORDER BY ilha")
        ilhas = [int(r["ilha"]) for r in cur.fetchall()]
        cur.execute("SELECT TOP 1 qtd_turnos FROM controle")
        row = cur.fetchone()
        qtd_turnos = int((row or {}).get("qtd_turnos") or 0) or 1
        turnos = list(range(1, qtd_turnos + 1))
        cur.execute(
            "SELECT codigo_int, nome_guerra FROM funcionarios WHERE situacao='A' ORDER BY nome_guerra"
        )
        funcionarios = [
            {"codigo": int(r["codigo_int"]), "nome": (r.get("nome_guerra") or "").strip()}
            for r in cur.fetchall()
        ]
        return {"success": True, "ilhas": ilhas, "turnos": turnos, "funcionarios": funcionarios}
    finally:
        conn.close()


def _list_sync(servidor: str, banco: str, data: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT i.ilha, i.turno, i.funcionario, f.nome_guerra "
            "FROM ilha i LEFT JOIN funcionarios f ON f.codigo_int = i.funcionario "
            "WHERE i.data=%s ORDER BY i.ilha, i.turno",
            (data,),
        )
        items = [
            {
                "ilha": int(r["ilha"]),
                "turno": int(r["turno"]),
                "funcionario": int(r["funcionario"]) if r.get("funcionario") is not None else None,
                "funcionario_nome": (r.get("nome_guerra") or "").strip(),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_sync(servidor: str, banco: str, data: str, ilha: int, turno: int, funcionario: int) -> dict:
    if not data:
        return {"success": False, "message": "Informe a data."}
    if ilha is None:
        return {"success": False, "message": "Selecione a ilha."}
    if turno is None:
        return {"success": False, "message": "Selecione o turno."}
    if funcionario is None:
        return {"success": False, "message": "Selecione o funcionário."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT 1 AS ok FROM bomba WHERE ilha=%s", (ilha,))
        if not cur.fetchone():
            return {"success": False, "message": "Ilha não encontrada — verifique se existe alguma bomba cadastrada com esse número de ilha."}
        cur.execute("SELECT 1 AS ok FROM funcionarios WHERE codigo_int=%s", (funcionario,))
        if not cur.fetchone():
            return {"success": False, "message": "Funcionário não encontrado."}
        cur.execute(
            "SELECT 1 AS ok FROM ilha WHERE data=%s AND ilha=%s AND turno=%s",
            (data, ilha, turno),
        )
        if cur.fetchone():
            return {
                "success": False,
                "message": "Já existe um funcionário cadastrado para esta Ilha/Turno nesta data — exclua o registro antes de trocar.",
            }
        cur.execute(
            "INSERT INTO ilha (data, ilha, turno, funcionario) VALUES (%s,%s,%s,%s)",
            (data, ilha, turno, funcionario),
        )
        conn.commit()
        return {"success": True, "message": "Ilha cadastrada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, data: str, ilha: int, turno: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute(
            "DELETE FROM ilha WHERE data=%s AND ilha=%s AND turno=%s",
            (data, ilha, turno),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Registro não encontrado."}
        conn.commit()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_opcoes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_opcoes_sync, servidor, banco)


async def list_ilhas(servidor: str, banco: str, data: str) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, data)


async def save_ilha(servidor: str, banco: str, data: str, ilha: int, turno: int, funcionario: int) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, data, ilha, turno, funcionario)


async def delete_ilha(servidor: str, banco: str, data: str, ilha: int, turno: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, data, ilha, turno)

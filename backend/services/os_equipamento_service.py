"""Múltiplos equipamentos por O.S. (`os_equipamento`) — Assistência
Técnica, Fase 1 (ver AssistenciaTecnicaCampo.md seção 5, regra 14: "uma OS
pode ter vários equipamentos", decidida user-directed 2026-08-12).

Antes desta feature, uma O.S. de Assistência tinha um único equipamento
vinculado via coluna escalar `os.numero_de_serie` (texto livre, soft-FK por
valor pra `equipamentos.numero_de_serie`). Essa coluna **não é removida**
— continua existindo, intocada, e vira a fonte do backfill automático
abaixo (histórico do "equipamento principal" de toda OS já existente).
Daqui pra frente, todo código novo lê/grava só `os_equipamento`.

Mesmo padrão de CRUD já usado por `os_itens_service.py` pra `os_produto`
(tabela-irmã, mesmo formato de "itens de um documento pai"): CRUD
individual por linha, nunca replace-all-on-save; "Cancelar" é soft
(`situacao='C'`), nunca delete físico — mantém histórico do atendimento
daquele equipamento, ao contrário do delete físico usado em `os_produto`
(lá a exclusão é de um rascunho de item, aqui é o cancelamento de um
equipamento já potencialmente atendido).

Status do equipamento (`os_equipamento.status_os`) reaproveita a MESMA
tabela `status_os` já usada pelo status da própria OS (`os.status_os`) —
decisão explícita do usuário, 2026-08-12: são dois níveis (OS e
equipamento) apontando pra linhas da mesma tabela de cadastro, não duas
tabelas separadas.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc
from models.schemas import OSEquipamentoSaveRequest
from services.os_itens_service import _check_os_aberta
from services.constants import SITUACAO_LABEL


def _ensure_os_equipamento_table(cur) -> None:
    """Migração idempotente: cria `os_equipamento` se ainda não existir, e
    faz o backfill automático a partir de `os.numero_de_serie` (o
    equipamento principal histórico de cada OS já existente) — set-based,
    idempotente via `NOT EXISTS`, sem script manual (mesmo princípio já
    estabelecido em CLAUDE.md > "Cada app precisa se auto-atualizar no
    banco, de forma INTEGRAL").

    `LEFT JOIN equipamentos` (não INNER) — se o `numero_de_serie` da OS não
    bater com nenhum equipamento cadastrado (dado órfão/digitado à mão no
    legado), a linha ainda é criada com `equipamento=NULL` e o texto
    preservado, pra nunca perder dado por causa de um número de série que
    não resolve. `descricao_cliente`/`resumo` (os campos de talão que já
    existiam no cabeçalho da OS) são copiados pro equipamento principal —
    mesmo princípio de "sem perda de dado".

    **Bug real encontrado em teste ao vivo (2026-08-13, KONTACTO TESTE)**:
    `equipamentos.numero_de_serie` é documentado como único GLOBALMENTE
    (ver `equipamentos_service.py`), mas isso nunca foi de fato uma
    constraint de banco — dado legado sujo pode ter (e tinha, ao vivo: 15
    linhas com `numero_de_serie='1'`) vários equipamentos com o mesmo
    número de série. Um `LEFT JOIN equipamentos e ON e.numero_de_serie =
    o.numero_de_serie` puro faz fan-out: 1 linha de `os` vira N linhas em
    `os_equipamento` (uma por equipamento casado), corrompendo o
    "principal" pra sempre múltiplo. Corrigido casando só o `codigo` MAIS
    BAIXO (`MIN`) entre os duplicados, via subquery correlacionada — mantém
    o comportamento determinístico e de "nunca perde dado" (ainda cria a
    linha, com `equipamento=NULL`, se não achar nenhum match), só resolve
    no máximo 1 equipamento por OS no backfill, nunca mais que 1."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'os_equipamento') "
        "CREATE TABLE os_equipamento ("
        " codigo INT IDENTITY(1,1) PRIMARY KEY,"
        " os INT NOT NULL,"
        " equipamento INT NULL,"
        " numero_de_serie NVARCHAR(20) NOT NULL,"
        " principal BIT NOT NULL DEFAULT 0,"
        " situacao NVARCHAR(2) NOT NULL DEFAULT 'A',"
        " defeito_reclamado NVARCHAR(500) NULL,"
        " servico_executado NVARCHAR(500) NULL,"
        " servico_a_executar NVARCHAR(500) NULL,"
        " diagnostico NVARCHAR(500) NULL,"
        " status_os SMALLINT NULL,"
        " data_inclusao DATETIME NOT NULL DEFAULT GETDATE())"
    )
    cur.execute(
        "INSERT INTO os_equipamento (os, equipamento, numero_de_serie, principal, "
        "                            defeito_reclamado, servico_executado) "
        "SELECT o.codigo, e.codigo, o.numero_de_serie, 1, o.descricao_cliente, o.resumo "
        "FROM os o "
        "LEFT JOIN equipamentos e ON e.codigo = ("
        "    SELECT MIN(e2.codigo) FROM equipamentos e2 WHERE e2.numero_de_serie = o.numero_de_serie"
        ") "
        "WHERE o.numero_de_serie IS NOT NULL AND o.numero_de_serie <> '' "
        "  AND NOT EXISTS (SELECT 1 FROM os_equipamento oe WHERE oe.os = o.codigo)"
    )
    # Índices — achado numa análise técnica (Thomé, Protocolo Gauntlet,
    # 2026-08-14): `os_equipamento` nunca teve índice secundário nenhum
    # (só a PK em `codigo`), mesmo sendo consultada por `os`
    # (`_list_equipamentos_sync`, toda vez que a O.S. Completa/Atendimento
    # de Campo abre) e por `equipamento`
    # (`equipamentos_service._historico_os_sync`, toda vez que se vê o
    # histórico de um equipamento) desde que a tabela nasceu (2026-08-13).
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
        "WHERE name='IX_os_equipamento_os' AND object_id=Object_ID('os_equipamento')) "
        "CREATE INDEX IX_os_equipamento_os ON os_equipamento(os)"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
        "WHERE name='IX_os_equipamento_equipamento' AND object_id=Object_ID('os_equipamento')) "
        "CREATE INDEX IX_os_equipamento_equipamento ON os_equipamento(equipamento)"
    )


def _list_equipamentos_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada.", "items": []}
        cur.execute(
            "SELECT oe.codigo, oe.equipamento, oe.numero_de_serie, oe.principal, oe.situacao, "
            "       oe.defeito_reclamado, oe.servico_executado, oe.servico_a_executar, oe.diagnostico, "
            "       oe.status_os, so.descricao AS status_os_descricao, "
            "       e.marca, ma.descricao AS marca_descricao, e.modelo, mo.descricao AS modelo_descricao "
            "FROM os_equipamento oe "
            "LEFT JOIN equipamentos e ON e.codigo = oe.equipamento "
            "LEFT JOIN marcas ma ON ma.codigo = e.marca "
            "LEFT JOIN modelos mo ON mo.codigo = e.modelo AND mo.cod_marca = e.marca "
            "LEFT JOIN status_os so ON so.codigo = oe.status_os "
            "WHERE oe.os = %s AND ISNULL(oe.situacao,'A') <> 'C' "
            "ORDER BY oe.codigo",
            (codigo,),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "equipamento": int(r["equipamento"]) if r.get("equipamento") is not None else None,
            "numero_de_serie": (r.get("numero_de_serie") or "").strip(),
            "principal": bool(r.get("principal")),
            "situacao": (r.get("situacao") or "A").strip(),
            "defeito_reclamado": (r.get("defeito_reclamado") or "").strip(),
            "servico_executado": (r.get("servico_executado") or "").strip(),
            "servico_a_executar": (r.get("servico_a_executar") or "").strip(),
            "diagnostico": (r.get("diagnostico") or "").strip(),
            "status_os": int(r["status_os"]) if r.get("status_os") is not None else None,
            "status_os_descricao": (r.get("status_os_descricao") or "").strip() or None,
            "marca_descricao": (r.get("marca_descricao") or "").strip() or None,
            "modelo_descricao": (r.get("modelo_descricao") or "").strip() or None,
        } for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items, "situacao_os": sit, "editavel": sit == "A"}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _add_equipamento_sync(req: OSEquipamentoSaveRequest, codigo: int) -> dict:
    if not req.equipamento:
        return {"success": False, "message": "Selecione um equipamento pra vincular."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}

        cur.execute("SELECT numero_de_serie FROM equipamentos WHERE codigo=%s", (req.equipamento,))
        equip = cur.fetchone()
        if not equip:
            conn.close()
            return {"success": False, "message": "Equipamento não encontrado."}
        num_serie = equip["numero_de_serie"]

        cur.execute(
            "SELECT TOP 1 1 AS ok FROM os_equipamento WHERE os=%s AND equipamento=%s AND ISNULL(situacao,'A')<>'C'",
            (codigo, req.equipamento),
        )
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Este equipamento já está vinculado a esta O.S."}

        sz = _get_col_sizes(conn, req.banco, "os_equipamento")
        defeito = _trunc((req.defeito_reclamado or "").strip(), sz, "defeito_reclamado", 500)
        exec_v = _trunc((req.servico_executado or "").strip(), sz, "servico_executado", 500)
        a_exec = _trunc((req.servico_a_executar or "").strip(), sz, "servico_a_executar", 500)
        diag = _trunc((req.diagnostico or "").strip(), sz, "diagnostico", 500)

        cur.execute(
            "INSERT INTO os_equipamento (os, equipamento, numero_de_serie, principal, situacao, "
            " defeito_reclamado, servico_executado, servico_a_executar, diagnostico, status_os) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s,%s,%s,0,'A',%s,%s,%s,%s,%s)",
            (codigo, req.equipamento, num_serie, defeito, exec_v, a_exec, diag, req.status_os),
        )
        row = cur.fetchone()
        novo_codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": novo_codigo}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao vincular equipamento: {e}"}


def _update_equipamento_sync(req: OSEquipamentoSaveRequest, codigo: int, item_codigo: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}

        sz = _get_col_sizes(conn, req.banco, "os_equipamento")
        defeito = _trunc((req.defeito_reclamado or "").strip(), sz, "defeito_reclamado", 500)
        exec_v = _trunc((req.servico_executado or "").strip(), sz, "servico_executado", 500)
        a_exec = _trunc((req.servico_a_executar or "").strip(), sz, "servico_a_executar", 500)
        diag = _trunc((req.diagnostico or "").strip(), sz, "diagnostico", 500)

        cur.execute(
            "UPDATE os_equipamento SET defeito_reclamado=%s, servico_executado=%s, "
            " servico_a_executar=%s, diagnostico=%s, status_os=%s "
            "WHERE codigo=%s AND os=%s",
            (defeito, exec_v, a_exec, diag, req.status_os, item_codigo, codigo),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Equipamento não encontrado nesta O.S."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao atualizar equipamento: {e}"}


def _cancelar_equipamento_sync(servidor: str, banco: str, codigo: int, item_codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        cur.execute(
            "UPDATE os_equipamento SET situacao='C' WHERE codigo=%s AND os=%s AND ISNULL(situacao,'A')<>'C'",
            (item_codigo, codigo),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Equipamento não encontrado (ou já cancelado) nesta O.S."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar equipamento: {e}"}


async def list_equipamentos(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_list_equipamentos_sync, servidor, banco, codigo)


async def add_equipamento(req: OSEquipamentoSaveRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_add_equipamento_sync, req, codigo)


async def update_equipamento(req: OSEquipamentoSaveRequest, codigo: int, item_codigo: int) -> dict:
    return await asyncio.to_thread(_update_equipamento_sync, req, codigo, item_codigo)


async def cancelar_equipamento(servidor: str, banco: str, codigo: int, item_codigo: int) -> dict:
    return await asyncio.to_thread(_cancelar_equipamento_sync, servidor, banco, codigo, item_codigo)


def _resolver_os_aberta_por_serie_sync(servidor: str, banco: str, numero_de_serie: str) -> dict:
    """Resolve um nº de série (lido do QR Code do equipamento) pra uma O.S.
    Aberta já vinculada a ele — tela de Atendimento de Campo, regras 1/8 do
    AssistenciaTecnicaCampo.md: o técnico NÃO vincula um equipamento novo em
    campo, só carrega uma OS que a retaguarda já preparou (O.S. Completa).

    Junta `equipamentos`->`os_equipamento`->`os` pelo NÚMERO DE SÉRIE
    diretamente (não resolve um único `equipamentos.codigo` primeiro) —
    achado ao vivo em ARGEN-TESTE: `equipamentos.numero_de_serie` tem
    duplicatas reais (mesmo problema já documentado no backfill de
    `_ensure_os_equipamento_table`, "dado legado sujo"). Resolver por um
    `equipamento.codigo` só (ex.: `TOP 1`) pode escolher a linha errada entre
    duplicatas e nunca achar o vínculo real em `os_equipamento`, que aponta
    pra um `equipamentos.codigo` específico — casar pelo texto do nº de série
    nos dois lados evita esse problema."""
    numero_de_serie = (numero_de_serie or "").strip()
    if not numero_de_serie:
        return {"success": False, "message": "Número de série vazio."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM equipamentos WHERE numero_de_serie=%s", (numero_de_serie,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Nenhum equipamento cadastrado com este número de série."}
        cur.execute(
            "SELECT TOP 1 o.codigo FROM os_equipamento oe "
            "JOIN os o ON o.codigo = oe.os "
            "JOIN equipamentos e ON e.codigo = oe.equipamento "
            "WHERE e.numero_de_serie=%s AND ISNULL(oe.situacao,'A')<>'C' AND o.situacao='A' "
            "ORDER BY o.codigo DESC",
            (numero_de_serie,),
        )
        os_row = cur.fetchone()
        cur.close()
        conn.close()
        if not os_row:
            return {
                "success": False,
                "message": "Este equipamento precisa ser vinculado a uma OS pela retaguarda antes do atendimento.",
            }
        return {"success": True, "os_codigo": int(os_row["codigo"])}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def resolver_os_aberta_por_serie(servidor: str, banco: str, numero_de_serie: str) -> dict:
    return await asyncio.to_thread(_resolver_os_aberta_por_serie_sync, servidor, banco, numero_de_serie)

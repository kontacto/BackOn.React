"""Checklist de Entrada de Veículo (O.S. Oficina) — pedido explícito do
usuário 2026-08-26. Sem precedente no legado: o técnico/atendente toca
num diagrama simples de carro (frontend), marca uma avaria (amassado,
arranhão, quebrado, faltando, outro) numa posição do diagrama — cada
toque vira UM registro dinâmico aqui, não um checklist estático de
perguntas fixas (leitura inicial errada de um documento de referência,
corrigida via `AskUserQuestion` antes de implementar).

Mesmo padrão de CRUD já usado por `os_equipamento_service.py` (tabela-
irmã, mesmo formato "itens filhos de uma O.S."): "Cancelar" é soft
(`situacao='C'`), nunca delete físico — mantém histórico de que uma
marcação existiu e foi removida (ex.: usuário marcou errado). Sem
UPDATE/editar — errou a posição/tipo, cancela e marca de novo (mais
simples, condiz com "marcação física", não um cadastro a editar).

Só aparece impresso na O.S. (`os_completa_pdf_service.py`) quando a O.S.
é de Oficina (tem placa) e está Aberta — ver docstring de
`_desenhar_checklist_veiculo` nesse módulo.

**Tabela `os_checklist`** (cabeçalho/conclusão, distinta de
`os_checklist_veiculo` que guarda as marcações) — pedido explícito do
usuário 2026-08-26: "O CHECKLIST DEVE SER OBRIGATÓRIO VIA PERMISSÃO"
("se na permissão estiver marcado para o grupo... tem que obrigar a
fazer") + "marcar o atendente que marcou sem avaria com os dados do
veículo, atendente data e hora" + "acho que tem que ser criado uma
tabela de OS_Checklist". Uma linha ATIVA (`situacao='A'`) representa "o
checklist desta O.S. foi revisado" — inclui quem revisou
(`usuario`)/quando (`data`/`hora`) e se não havia nenhuma avaria pra
marcar (`sem_avaria`), calculado no momento de concluir a partir de
`os_checklist_veiculo` (nenhuma marcação ativa = sem avaria). O botão
"Concluir Checklist" (`_concluir_sync`) é idempotente — reconcluir soft-
cancela a conclusão anterior e grava uma nova, sempre refletindo o
estado mais recente (ex.: atendente concluiu, lembrou de marcar algo,
marcou, concluiu de novo). Dados do veículo (placa/marca/modelo) não são
duplicados aqui — resolvidos via JOIN com `os` no momento da exibição/
impressão, mesmo princípio de não duplicar dado já existente na tabela
pai usado no resto do projeto.

A obrigatoriedade em si (bloquear incluir item/fechar/faturar sem
conclusão) fica em `pedido_common._checklist_veiculo_pendente_bloqueia`
— módulo "folha" sem dependências de outros services, evita import
circular com `os_itens_service`/`os_service` (que precisam chamar esse
bloqueio e já são importados POR este módulo/por quem importa este
módulo). Ver docstring daquela função pro detalhe completo da regra.
"""
import asyncio
from datetime import datetime

from db.connection import _open_conn, _get_col_sizes, _trunc
from models.schemas import FecharRequest, OSChecklistVeiculoSaveRequest
from services.os_itens_service import _check_os_aberta
from services.constants import SITUACAO_LABEL

TIPOS_AVARIA = {"AMASSADO", "ARRANHAO", "QUEBRADO", "FALTANDO", "OUTRO"}


def _ensure_os_checklist_veiculo_table(cur) -> None:
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'os_checklist_veiculo') "
        "CREATE TABLE os_checklist_veiculo ("
        " codigo INT IDENTITY(1,1) PRIMARY KEY,"
        " os INT NOT NULL,"
        " tipo_avaria NVARCHAR(20) NOT NULL,"
        " pos_x FLOAT NOT NULL,"
        " pos_y FLOAT NOT NULL,"
        " descricao NVARCHAR(200) NULL,"
        " situacao NVARCHAR(2) NOT NULL DEFAULT 'A',"
        " usuario_inclusao INT NULL,"
        " data_inclusao DATETIME NOT NULL DEFAULT GETDATE())"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
        "WHERE name='IX_os_checklist_veiculo_os' AND object_id=Object_ID('os_checklist_veiculo')) "
        "CREATE INDEX IX_os_checklist_veiculo_os ON os_checklist_veiculo(os)"
    )


def _ensure_os_checklist_table(cur) -> None:
    """Tabela de CONCLUSÃO do checklist (1 linha ativa por O.S., distinta
    de `os_checklist_veiculo` que guarda cada marcação) — ver docstring
    do módulo pro contexto completo da obrigatoriedade por permissão."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'os_checklist') "
        "CREATE TABLE os_checklist ("
        " codigo INT IDENTITY(1,1) PRIMARY KEY,"
        " os INT NOT NULL,"
        " sem_avaria BIT NOT NULL DEFAULT 0,"
        " usuario INT NULL,"
        " data DATE NOT NULL,"
        " hora NVARCHAR(5) NOT NULL,"
        " situacao NVARCHAR(2) NOT NULL DEFAULT 'A',"
        " data_inclusao DATETIME NOT NULL DEFAULT GETDATE())"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
        "WHERE name='IX_os_checklist_os' AND object_id=Object_ID('os_checklist')) "
        "CREATE INDEX IX_os_checklist_os ON os_checklist(os)"
    )


def _list_checklist_sync(servidor: str, banco: str, codigo: int) -> dict:
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
            "SELECT codigo, tipo_avaria, pos_x, pos_y, descricao "
            "FROM os_checklist_veiculo "
            "WHERE os=%s AND ISNULL(situacao,'A')<>'C' "
            "ORDER BY codigo",
            (codigo,),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "tipo_avaria": (r.get("tipo_avaria") or "").strip(),
            "pos_x": float(r["pos_x"]),
            "pos_y": float(r["pos_y"]),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]

        cur.execute(
            "SELECT TOP 1 c.sem_avaria, c.data, c.hora, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS usuario_nome "
            "FROM os_checklist c "
            "LEFT JOIN funcionarios f ON f.codigo_int = c.usuario "
            "WHERE c.os=%s AND ISNULL(c.situacao,'A')<>'C' "
            "ORDER BY c.codigo DESC",
            (codigo,),
        )
        conclusao = cur.fetchone()
        cur.close()
        conn.close()
        return {
            "success": True, "items": items, "editavel": sit == "A",
            "concluido": conclusao is not None,
            "sem_avaria": bool(conclusao.get("sem_avaria")) if conclusao else False,
            "concluido_por": (conclusao.get("usuario_nome") or "").strip() if conclusao else "",
            "concluido_data": conclusao["data"].isoformat() if conclusao and conclusao.get("data") else None,
            "concluido_hora": (conclusao.get("hora") or "").strip() if conclusao else "",
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _add_item_sync(req: OSChecklistVeiculoSaveRequest, codigo: int) -> dict:
    tipo = (req.tipo_avaria or "").strip().upper()
    if tipo not in TIPOS_AVARIA:
        return {"success": False, "message": "Tipo de avaria inválido."}
    if not (0 <= req.pos_x <= 1) or not (0 <= req.pos_y <= 1):
        return {"success": False, "message": "Posição da marcação fora do diagrama."}
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

        sz = _get_col_sizes(conn, req.banco, "os_checklist_veiculo")
        descricao = _trunc((req.descricao or "").strip(), sz, "descricao", 200)

        cur.execute(
            "INSERT INTO os_checklist_veiculo (os, tipo_avaria, pos_x, pos_y, descricao, situacao, usuario_inclusao) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s,%s,%s,%s,%s,'A',%s)",
            (codigo, tipo, req.pos_x, req.pos_y, descricao, req.usuario_alteracao),
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
        return {"success": False, "message": f"Erro ao gravar marcação: {e}"}


def _cancelar_item_sync(servidor: str, banco: str, codigo: int, item_codigo: int) -> dict:
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
            "UPDATE os_checklist_veiculo SET situacao='C' WHERE codigo=%s AND os=%s AND ISNULL(situacao,'A')<>'C'",
            (item_codigo, codigo),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Marcação não encontrada (ou já cancelada) nesta O.S."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar marcação: {e}"}


def _concluir_sync(req: FecharRequest, codigo: int) -> dict:
    """Marca o checklist desta O.S. como revisado — botão "Concluir
    Checklist" na tela, ação SEPARADA de marcar uma avaria (existe mesmo
    quando não há nenhuma marcação: "veículo revisado, sem avaria
    encontrada"). `sem_avaria` é calculado aqui, não escolhido pelo
    usuário — reflete o estado real de `os_checklist_veiculo` no momento
    da conclusão. Idempotente: soft-cancela qualquer conclusão ativa
    anterior e grava uma nova, sempre a mais recente."""
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

        cur.execute(
            "SELECT TOP 1 1 AS ok FROM os_checklist_veiculo WHERE os=%s AND ISNULL(situacao,'A')<>'C'",
            (codigo,),
        )
        sem_avaria = cur.fetchone() is None

        cur.execute(
            "UPDATE os_checklist SET situacao='C' WHERE os=%s AND ISNULL(situacao,'A')<>'C'",
            (codigo,),
        )
        agora = datetime.now()
        cur.execute(
            "INSERT INTO os_checklist (os, sem_avaria, usuario, data, hora, situacao) "
            "VALUES (%s,%s,%s,%s,%s,'A')",
            (codigo, 1 if sem_avaria else 0, req.usuario_alteracao, agora.date().isoformat(), agora.strftime("%H:%M")),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "sem_avaria": sem_avaria}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao concluir checklist: {e}"}


async def list_checklist(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_list_checklist_sync, servidor, banco, codigo)


async def add_item(req: OSChecklistVeiculoSaveRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_add_item_sync, req, codigo)


async def cancelar_item(servidor: str, banco: str, codigo: int, item_codigo: int) -> dict:
    return await asyncio.to_thread(_cancelar_item_sync, servidor, banco, codigo, item_codigo)


async def concluir(req: FecharRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_concluir_sync, req, codigo)

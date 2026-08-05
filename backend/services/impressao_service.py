"""Impressão de rede via socket TCP cru + fila de impressão pra impressoras
USB locais (polling do agente local — ver `print-agent/`).

Esboço da primeira peça da feature de impressão automática de comandas por
Finalidade do produto (módulo Bar, tela Pedido de Venda) — ver memória de
projeto "Impressão automática por Finalidade" para o desenho completo.
Nenhum navegador tem API de impressão silenciosa; a solução tem duas
pontas, conforme o tipo de impressora:

- **Rede**: o backend manda os bytes direto pro socket da impressora
  (impressoras térmicas de rede aceitam conexão TCP crua, sem driver, na
  porta 9100 por convenção — protocolo "RAW"/JetDirect). `enviar_rede`
  abaixo, sem fila — é síncrono, o backend já tem acesso direto à rede da
  impressora.
- **USB local**: o backend não tem acesso físico à porta USB de uma
  máquina cliente — a solução é uma FILA (`impressao_fila`, criada por
  empresa/`servidor`+`banco`, mesmo padrão de `_ensure_*_table` já usado
  em outros módulos) que um agente Python pequeno, rodando na própria
  máquina com a impressora conectada (`print-agent/agente_impressao.py`),
  consulta por polling (`GET /impressao/fila/pendentes?computador=X`) e
  confirma o resultado (`POST /impressao/fila/{id}/confirmar`) depois de
  mandar os bytes pro spooler do Windows via `win32print`.

Ainda faltam (fora do escopo desta rodada):
- Montagem do layout ESC/POS do cupom em si (formatação, corte de papel,
  código de barras etc.) — hoje `conteudo` é texto puro (o mesmo texto já
  usado pelo preview/impressão via navegador, ver `printHtml.ts`).
- Resolver automaticamente qual computador/impressora usar a partir da
  Finalidade do item (join com `direcionamento_impressora`) — hoje quem
  enfileira informa `computador`/`impressora` explicitamente.
"""
import asyncio
import socket
from typing import Optional

from db.connection import _open_conn, _to_json_safe

DEFAULT_PORT = 9100  # porta padrão RAW/JetDirect de impressoras térmicas de rede
CONNECT_TIMEOUT_SECONDS = 5

# Job "ENVIADO" há mais desse tempo sem confirmação volta a ser elegível
# pro próximo polling — recuperação pra quando o agente cai/trava no meio
# do processamento de um job e nunca chama /confirmar.
RECUPERACAO_ENVIADO_MINUTOS = 2


def _enviar_rede_sync(ip: str, porta: int, conteudo: str) -> dict:
    ip = (ip or "").strip()
    if not ip:
        return {"success": False, "message": "Informe o IP da impressora."}
    if not conteudo:
        return {"success": False, "message": "Conteúdo vazio — nada para imprimir."}

    # cp850 é a codepage mais comum em impressoras térmicas ESC/POS na
    # América Latina (acentuação PT-BR); impressoras que esperam outra
    # codepage vão precisar de configuração por impressora futuramente,
    # não coberto neste esboço.
    try:
        dados = conteudo.encode("cp850", errors="replace")
    except LookupError:
        dados = conteudo.encode("latin-1", errors="replace")

    try:
        with socket.create_connection((ip, porta), timeout=CONNECT_TIMEOUT_SECONDS) as sock:
            sock.sendall(dados)
        return {"success": True, "message": "Impressão enviada."}
    except socket.timeout:
        return {"success": False, "message": f"Tempo esgotado ao conectar em {ip}:{porta}."}
    except (ConnectionRefusedError, OSError) as e:
        return {"success": False, "message": f"Não foi possível conectar na impressora {ip}:{porta}: {e}"}


async def enviar_rede(ip: str, porta: int, conteudo: str) -> dict:
    return await asyncio.to_thread(_enviar_rede_sync, ip, porta or DEFAULT_PORT, conteudo)


# ---------------------------------------------------------------------------
# Fila de impressão (polling do agente local — impressoras USB)
# ---------------------------------------------------------------------------

def _ensure_impressao_fila_table(cur) -> None:
    """Migração idempotente (mesmo padrão de `_ensure_agenda_forma_pag_tables`
    em `pedido_common.py`) — cria a tabela na primeira vez que alguma
    empresa (`servidor`+`banco`) usa a fila. `status`: PENDENTE (aguardando
    o agente buscar) -> ENVIADO (agente já buscou, ainda processando) ->
    IMPRESSO/ERRO (resultado final, confirmado pelo agente)."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'impressao_fila') "
        "CREATE TABLE impressao_fila ("
        "id INT IDENTITY(1,1) PRIMARY KEY, "
        "computador NVARCHAR(60) NOT NULL, "
        "impressora NVARCHAR(120) NULL, "
        "tipo NVARCHAR(10) NOT NULL DEFAULT 'TEXTO', "
        "conteudo NVARCHAR(MAX) NOT NULL, "
        "status NVARCHAR(12) NOT NULL DEFAULT 'PENDENTE', "
        "mensagem_erro NVARCHAR(500) NULL, "
        "data_criacao DATETIME NOT NULL DEFAULT GETDATE(), "
        "data_envio DATETIME NULL, "
        "data_conclusao DATETIME NULL)"
    )


def _enfileirar_sync(servidor: str, banco: str, computador: str, impressora: Optional[str], conteudo: str, tipo: str = "TEXTO") -> dict:
    computador = (computador or "").strip()
    if not computador:
        return {"success": False, "message": "Informe o computador de destino."}
    if not conteudo:
        return {"success": False, "message": "Conteúdo vazio — nada para imprimir."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_impressao_fila_table(cur)
        cur.execute(
            "INSERT INTO impressao_fila (computador, impressora, tipo, conteudo) "
            "OUTPUT INSERTED.id VALUES (%s,%s,%s,%s)",
            (computador, (impressora or "").strip() or None, tipo, conteudo),
        )
        job_id = int(cur.fetchone()["id"])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "id": job_id, "message": "Impressão enfileirada."}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao enfileirar: {e}"}


def _list_pendentes_sync(servidor: str, banco: str, computador: str) -> dict:
    computador = (computador or "").strip()
    if not computador:
        return {"success": False, "message": "Informe o computador.", "items": []}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_impressao_fila_table(cur)
        cur.execute(
            "SELECT id, impressora, tipo, conteudo FROM impressao_fila "
            "WHERE computador=%s AND ("
            "  status='PENDENTE' "
            "  OR (status='ENVIADO' AND data_envio < DATEADD(minute,-%s,GETDATE()))"
            ") ORDER BY id",
            (computador, RECUPERACAO_ENVIADO_MINUTOS),
        )
        itens = [_to_json_safe(r) for r in cur.fetchall()]
        ids = [int(r["id"]) for r in itens]
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"UPDATE impressao_fila SET status='ENVIADO', data_envio=GETDATE() WHERE id IN ({placeholders})",
                tuple(ids),
            )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "items": itens}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _confirmar_sync(servidor: str, banco: str, job_id: int, sucesso: bool, mensagem_erro: Optional[str] = None) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_impressao_fila_table(cur)
        status = "IMPRESSO" if sucesso else "ERRO"
        cur.execute(
            "UPDATE impressao_fila SET status=%s, mensagem_erro=%s, data_conclusao=GETDATE() WHERE id=%s",
            (status, (mensagem_erro or "")[:500] or None, job_id),
        )
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {"success": False, "message": "Job não encontrado."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao confirmar: {e}"}


async def enfileirar(servidor: str, banco: str, computador: str, impressora: Optional[str], conteudo: str, tipo: str = "TEXTO") -> dict:
    return await asyncio.to_thread(_enfileirar_sync, servidor, banco, computador, impressora, conteudo, tipo)


async def list_pendentes(servidor: str, banco: str, computador: str) -> dict:
    return await asyncio.to_thread(_list_pendentes_sync, servidor, banco, computador)


async def confirmar(servidor: str, banco: str, job_id: int, sucesso: bool, mensagem_erro: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_confirmar_sync, servidor, banco, job_id, sucesso, mensagem_erro)

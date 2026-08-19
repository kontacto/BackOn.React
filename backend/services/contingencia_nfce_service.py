"""Contingência NFCe — infraestrutura mínima pra "Validar Contingência"
(Gestor NFCe) fazer sentido de verdade. Migração de `Geral\\FrmConNFC.frm`
— só abrir/fechar/consultar o estado atual, **não** a grade histórica
completa do `.frm` (com Excluir/edição de registro antigo) — decisão
explícita do usuário na Rodada 2 do ecossistema fiscal ("Gestor NFCe"):
só o necessário pra "Validar Contingência" existir, não a tela inteira.

Schema confirmado direto na fonte (`FrmConNFC.frm`, lido por completo):
`data_inicio, hora_inicio, data_fim, hora_fim, motivo, tipo_contingencia`
— `tipo_contingencia` é `9` ("Off-Line", único selecionável pra abrir
contingência NOVA — `Option1`/"Formulário de Segurança"=`5` fica
`Visible=0` no legado pra criação, só aparece ao editar um registro
histórico já existente com esse tipo) ou `5`. Como esta migração não
tem ainda essa grade histórica/edição, só `9` é gravável aqui — mesma
restrição de fato do legado, não uma simplificação nossa.

**Divergência deliberada do SQL literal do legado, documentada**: a
checagem de "contingência aberta" no VB6 (`Verifica_NFCe_Contingencia`,
`NFe.bas:627-643`) usa `WHERE ISNULL(Data_Fim,'') = ''` — funciona lá
porque a coluna já existia como tipo solto o bastante pra aceitar essa
comparação. Como esta é uma tabela NOVA desta migração (schema definido
aqui, não herdado), `data_fim` é `DATE NULL` de verdade — `ISNULL(data_
fim,'') = ''` forçaria uma conversão string↔date inválida no SQL Server.
Usamos `data_fim IS NULL` (semanticamente idêntico: "sem data de fim =
ainda aberta"), não uma mudança de regra de negócio.
"""
import asyncio
from datetime import datetime
from typing import Optional

from db.connection import _open_conn
from services.permissoes_service import tem_permissao


def _sem_permissao(cur, *, classe: Optional[int], master: bool) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "GESTOR_NFCE", "CONTINGENCIA")

_DDL_CONTINGENCIA_NFCE = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'contingencia_nfce')
BEGIN
    CREATE TABLE contingencia_nfce (
        id INT IDENTITY(1,1) PRIMARY KEY,
        data_inicio DATE NOT NULL,
        hora_inicio VARCHAR(8) NOT NULL,
        data_fim DATE NULL,
        hora_fim VARCHAR(8) NULL,
        motivo NVARCHAR(500) NOT NULL,
        tipo_contingencia SMALLINT NOT NULL DEFAULT 9
    );
    CREATE INDEX IX_contingencia_nfce_aberta ON contingencia_nfce (data_fim);
END
"""


def _ensure_contingencia_nfce_table(cur) -> None:
    cur.execute(_DDL_CONTINGENCIA_NFCE)


def contingencia_aberta_sync(cur) -> Optional[dict]:
    """Réplica de `Verifica_NFCe_Contingencia()` (`NFe.bas:627-643`) —
    devolve a linha de contingência aberta (sem `data_fim`) ou `None` se
    não há nenhuma ativa. Chamado com o cursor já aberto de dentro da
    mesma transação de quem precisa saber (emissão, ações do Gestor
    NFCe) — nunca abre conexão própria."""
    _ensure_contingencia_nfce_table(cur)
    cur.execute(
        "SELECT TOP 1 id, data_inicio, hora_inicio, motivo, tipo_contingencia "
        "FROM contingencia_nfce WHERE data_fim IS NULL ORDER BY id DESC"
    )
    return cur.fetchone()


def _abrir_contingencia_sync(
    servidor: str, banco: str, *, motivo: str, classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Abre uma contingência nova — réplica de `FrmConNFC.frm::
    Command1_Click` (ramo de abertura, linhas 315-325): valida motivo
    (15-256 chars, igual à fonte), bloqueia dupla abertura, sempre
    `tipo_contingencia=9` (ver docstring do módulo)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master):
            conn.close()
            return {"success": False, "message": "Sem permissão para abrir contingência."}
        motivo = (motivo or "").strip()
        if len(motivo) < 15 or len(motivo) > 256:
            conn.close()
            return {"success": False, "message": "O motivo deve ter entre 15 e 256 caracteres."}
        if contingencia_aberta_sync(cur):
            conn.close()
            return {"success": False, "message": "Já existe uma contingência aberta — feche-a antes de abrir outra."}
        agora = datetime.now()
        cur.execute(
            "INSERT INTO contingencia_nfce (data_inicio, hora_inicio, motivo, tipo_contingencia) "
            "VALUES (%s, %s, %s, 9)",
            (agora.date(), agora.strftime("%H:%M:%S"), motivo),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Contingência aberta. Novas NFC-e serão emitidas em contingência até o fechamento."}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _fechar_contingencia_sync(
    servidor: str, banco: str, *, classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Fecha a contingência aberta — réplica de `FrmConNFC.frm::
    Command1_Click` (ramo de fechamento, linha 314): grava `data_fim`/
    `hora_fim` na linha aberta."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar contingência."}
        aberta = contingencia_aberta_sync(cur)
        if not aberta:
            conn.close()
            return {"success": False, "message": "Não há contingência aberta pra fechar."}
        agora = datetime.now()
        cur.execute(
            "UPDATE contingencia_nfce SET data_fim = %s, hora_fim = %s WHERE id = %s",
            (agora.date(), agora.strftime("%H:%M:%S"), aberta["id"]),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True,
            "message": "Contingência fechada. Use \"Validar Contingência\" no Gestor NFCe pra transmitir as NFC-e emitidas nesse período.",
        }
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _status_contingencia_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        aberta = contingencia_aberta_sync(cur)
        cur.close()
        conn.close()
        if not aberta:
            return {"success": True, "aberta": False}
        return {
            "success": True, "aberta": True,
            "data_inicio": str(aberta.get("data_inicio")), "hora_inicio": aberta.get("hora_inicio"),
            "motivo": aberta.get("motivo"), "tipo_contingencia": aberta.get("tipo_contingencia"),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def abrir_contingencia(
    servidor: str, banco: str, motivo: str, classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(_abrir_contingencia_sync, servidor, banco, motivo=motivo, classe=classe, master=master)


async def fechar_contingencia(servidor: str, banco: str, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_fechar_contingencia_sync, servidor, banco, classe=classe, master=master)


async def status_contingencia(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_status_contingencia_sync, servidor, banco)

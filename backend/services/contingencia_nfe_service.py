"""Contingência NFe — migração de `Geral\\FrmConNFe.frm` (444 linhas, lido
por completo 2026-08-20). Mesma "infraestrutura mínima" já decidida pra
Contingência NFCe (`contingencia_nfce_service.py`) — só abrir/fechar/
consultar o estado atual, não a grade histórica completa (Excluir/edição
de registro antigo) — mesmo princípio, tela pequena e independente.

**Diferença real confirmada contra a fonte** (não presumida — ver
PENDENCIAS.md > blueprint itens 7/8): ao contrário de Contingência NFCe
(onde só um tipo é selecionável pra abrir — `tipo_contingencia=9` fixo),
aqui os DOIS tipos são igualmente selecionáveis ao abrir uma contingência
nova (`Option1`/`Option2`, ambos visíveis e obrigatórios — `FrmConNFe.
frm:276-279`): **FS-IA (2)** "Formulário de Segurança - Impressor
Autônomo" ou **FS-DA (5)** "Formulário de Segurança - Documento
Auxiliar" (`FrmConNFe.frm:301`, `IIf(Option1.Value, 2, 5)`). Motivo:
15-256 chars, mesma regra de NFCe.

Schema confirmado direto no banco real (`INFORMATION_SCHEMA`/
`sys.indexes`, GERDELL/BARESTELA, 2026-08-20 — a tabela JÁ EXISTE no
legado, não foi presumida): `contingencia_nfe(Data_Inicio, Hora_Inicio,
Data_Fim, Hora_Fim, Motivo, tipo_contingencia)`, **chave primária
composta `(Data_Inicio, Hora_Inicio)`, sem coluna `id`** — mesmo achado
que corrigiu um bug real em `contingencia_nfce_service.py` no mesmo dia
(a 1ª versão daquele service assumia um `id` que não existe na tabela
real; corrigido lá e replicado certo aqui desde o início).

**Divergência deliberada do SQL literal do legado**: `Command1_Click`
(`FrmConNFe.frm:294`) usa `WHERE DATA_FIM=NULL` (tecnicamente incorreto,
só funciona por `ANSI_NULLS OFF` legado) — a regra em si (só uma
contingência aberta por vez) é real, portado com `IS NULL` correto.

**Ainda não conectado à emissão real** — diferente de Contingência NFCe
(já consultada por `comanda_service._emitir_nfce_comanda_sync`),
`nfe_agrupada_service.py`/`nfe_avulsa_service.py` ainda não chamam
`contingencia_aberta_sync` nem passam `contingencia=` pro `emitir_nfe_
sync` — essa tela fica só como registro/CRUD por enquanto, sem "Validar
Contingência" equivalente ainda. Ver PENDENCIAS.md pra esse gap
registrado explicitamente, fora do escopo desta rodada.

**NUNCA testado ao vivo contra SEFAZ real** — mesma ressalva de todo o
resto do pacote fiscal desta migração."""
import asyncio
from datetime import datetime
from typing import Optional

from db.connection import _open_conn
from services import nfe_fiscal_common
from services.permissoes_service import tem_permissao

_TIPOS_VALIDOS = (2, 5)  # FS-IA, FS-DA


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "CONT_NFE", comando)


_DDL_CONT_NFE = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'contingencia_nfe')
BEGIN
    CREATE TABLE contingencia_nfe (
        data_inicio DATE NOT NULL,
        hora_inicio VARCHAR(8) NOT NULL,
        data_fim DATE NULL,
        hora_fim VARCHAR(8) NULL,
        motivo NVARCHAR(500) NULL,
        tipo_contingencia SMALLINT NULL,
        CONSTRAINT PK_contingencia_nfe PRIMARY KEY (data_inicio, hora_inicio)
    );
    CREATE INDEX IX_contingencia_nfe_aberta ON contingencia_nfe (data_fim);
END
"""


def _ensure_contingencia_nfe_table(cur) -> None:
    cur.execute(_DDL_CONT_NFE)


def contingencia_aberta_sync(cur) -> Optional[dict]:
    """Devolve a linha de contingência NFe aberta (sem `data_fim`) ou
    `None` — mesmo padrão de `contingencia_nfce_service.contingencia_
    aberta_sync`. Chamado com o cursor já aberto de dentro da mesma
    transação de quem precisa saber (futura emissão NFe em contingência —
    ver docstring do módulo)."""
    _ensure_contingencia_nfe_table(cur)
    cur.execute(
        "SELECT TOP 1 data_inicio, hora_inicio, motivo, tipo_contingencia "
        "FROM contingencia_nfe WHERE data_fim IS NULL ORDER BY data_inicio DESC, hora_inicio DESC"
    )
    return cur.fetchone()


def _abrir_contingencia_sync(
    servidor: str, banco: str, *, motivo: str, tipo_contingencia: int,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Abre uma contingência nova — réplica de `FrmConNFe.frm::
    Command1_Click` (ramo de abertura, linhas 291-302): valida motivo
    (15-256 chars), tipo obrigatório (2=FS-IA ou 5=FS-DA — os DOIS são
    selecionáveis aqui, diferente de NFCe), bloqueia dupla abertura."""
    if tipo_contingencia not in _TIPOS_VALIDOS:
        return {"success": False, "message": "Defina o tipo de contingência (FS-IA ou FS-DA)."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para abrir contingência."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}
        motivo = (motivo or "").strip()
        if len(motivo) < 15 or len(motivo) > 256:
            conn.close()
            return {"success": False, "message": "O motivo deve ter entre 15 e 256 caracteres."}
        if contingencia_aberta_sync(cur):
            conn.close()
            return {"success": False, "message": "Já existe uma contingência aberta — feche-a antes de abrir outra."}
        agora = datetime.now()
        cur.execute(
            "INSERT INTO contingencia_nfe (data_inicio, hora_inicio, motivo, tipo_contingencia) "
            "VALUES (%s, %s, %s, %s)",
            (agora.date(), agora.strftime("%H:%M:%S"), motivo, tipo_contingencia),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Contingência aberta. Novas NF-e serão emitidas em contingência até o fechamento."}
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
    """Fecha a contingência aberta — grava `data_fim`/`hora_fim` na linha
    aberta (identificada por `data_fim IS NULL`, sem precisar de `id` —
    a regra "só uma aberta por vez" já garante que é única)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar contingência."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}
        if not contingencia_aberta_sync(cur):
            conn.close()
            return {"success": False, "message": "Não há contingência aberta pra fechar."}
        agora = datetime.now()
        cur.execute(
            "UPDATE contingencia_nfe SET data_fim = %s, hora_fim = %s WHERE data_fim IS NULL",
            (agora.date(), agora.strftime("%H:%M:%S")),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Contingência fechada."}
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
    servidor: str, banco: str, motivo: str, tipo_contingencia: int,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _abrir_contingencia_sync, servidor, banco, motivo=motivo, tipo_contingencia=tipo_contingencia,
        classe=classe, master=master,
    )


async def fechar_contingencia(servidor: str, banco: str, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_fechar_contingencia_sync, servidor, banco, classe=classe, master=master)


async def status_contingencia(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_status_contingencia_sync, servidor, banco)

"""Abertura do Dia — menu Gerencial > Abertura do Dia.

Migração de `MdiPrincipal` (`Ger_Abr_Click`) + `Revenda\\frmAbreDia.frm` +
`Geral\\mdl_proc.bas` (`MudaDataSistema`/`TestaSistema`). Ver
PENDENCIAS.md > "MDI Principal (VB6)" pro rastreio completo.

Escopo confirmado com a equipe VB6 (2026-08-16): `controle_configuracao.
CONTROLA_ABERTURA_DIA` é real — lido no boot do legado e atribuído a
`Dados_Controle_Configuracao.Abertura_do_dia`, decide se a empresa abre o
dia manualmente (flag ligada, usuário precisa vir aqui) ou automaticamente
(flag desligada — comportamento default de toda instalação até hoje,
nenhuma nunca ligou o flag; a Data de Movimento avança sozinha na próxima
criação de Pedido/O.S., ver `_auto_abrir_dia_se_necessario` em
`pedido_common.py`). **A reconciliação de estoque do legado (zerar e
recalcular `pecas.qtd` a partir de `movimentacao`/`os_produto`/
`pedido_venda_prod`) está CONFIRMADA EM DESUSO pela própria equipe VB6 —
deliberadamente NÃO portada, nem como auditoria/snapshot.** Esta tela cuida
só de `controle.Data_Movimento` + log de auditoria.
"""
import asyncio
from datetime import date, datetime
from typing import Optional

from db.connection import _open_conn, iso
from services.log_auditoria_service import registrar_log
from services.permissoes_service import tem_permissao

TELA = "ABERTURA_DIA"

# Gate de rollout temporário — recurso novo, nunca testado ao vivo antes
# desta rodada. Pedido explícito do usuário, 2026-08-16: disponível só
# quando o Nome Fantasia da empresa conectada (`controle.fantasia`) é
# literalmente "Kontacto" — usar a conexão "Kontacto Teste" pra validar
# antes de liberar de forma geral pra qualquer empresa/cliente. Reforçado
# tanto no status (esconde a tela) quanto no abrir_dia (bloqueia a
# gravação), mesmo princípio de "backend reforça, nunca só confia no
# frontend" já usado em outros gates deste projeto.
FANTASIA_LIBERADA = "KONTACTO"


def _recurso_disponivel(fantasia: Optional[str]) -> bool:
    return (fantasia or "").strip().upper() == FANTASIA_LIBERADA


def _status_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha de conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 Data_Movimento, fantasia FROM controle")
        row = cur.fetchone() or {}
        cur.execute("SELECT TOP 1 CONTROLA_ABERTURA_DIA FROM controle_configuracao")
        row2 = cur.fetchone() or {}
        cur.close()
        return {
            "success": True,
            "data_movimento": iso(row.get("Data_Movimento")),
            "controla_abertura_dia": bool(row2.get("CONTROLA_ABERTURA_DIA")),
            "disponivel": _recurso_disponivel(row.get("fantasia")),
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _abrir_dia_sync(
    servidor: str, banco: str, nova_data: str,
    classe: Optional[int], master: bool, confirma_retrocesso: bool,
) -> dict:
    try:
        d = datetime.strptime(nova_data, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"success": False, "message": "Data inválida."}
    if d > date.today():
        return {"success": False, "message": "A nova data não pode ser superior à data atual."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha de conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not master and not tem_permissao(cur, classe or 0, TELA, "GRAVAR"):
            return {"success": False, "message": "Sem permissão para abrir o dia."}

        cur.execute("SELECT TOP 1 Data_Movimento, fantasia FROM controle")
        row = cur.fetchone() or {}
        if not _recurso_disponivel(row.get("fantasia")):
            return {"success": False, "message": "Recurso ainda em teste — disponível só para a Kontacto."}
        data_atual = iso(row.get("Data_Movimento"))

        if data_atual and nova_data < data_atual and not confirma_retrocesso:
            return {
                "success": False,
                "requer_confirmacao": True,
                "message": f"A nova data ({nova_data}) é anterior à Data de Movimento atual ({data_atual}). Confirma?",
            }

        cur.execute("UPDATE controle SET Data_Movimento = %s", (nova_data,))
        conn.commit()
        cur.close()
        return {"success": True, "data_movimento": nova_data, "data_anterior": data_atual}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def status(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_status_sync, servidor, banco)


async def abrir_dia(
    servidor: str, banco: str, nova_data: str,
    usuario_alteracao: Optional[int], classe: Optional[int], master: bool,
    plataforma: Optional[str], confirma_retrocesso: bool = False,
) -> dict:
    r = await asyncio.to_thread(
        _abrir_dia_sync, servidor, banco, nova_data, classe, master, confirma_retrocesso,
    )
    if r.get("success"):
        await registrar_log(
            servidor, banco, tela=TELA, comando="GRAVAR",
            usuario=usuario_alteracao, classe=classe,
            descricao=f"Abertura do dia: de {r.get('data_anterior') or '—'} para {nova_data}",
            plataforma=plataforma,
        )
    return r

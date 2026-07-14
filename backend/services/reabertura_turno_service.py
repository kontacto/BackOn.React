"""Reabertura de Turno (Posto de Combustível) — desfaz o fechamento mais
recente (`controle_turno`), revertendo `controle.turno_movimento` (e
`controle.data_movimento`/`FECHAMENTO_TURNO`, se o fechamento desfeito
tiver sido o que fechou o dia inteiro).

Legado: `FrmReaTurno.frm`. **Simplificação deliberada, não lacuna**: o
`.frm` original também reatribui (`UPDATE ... SET turno = turno-1`)
registros de `abastecimento`/`abastecimento_log`/`comanda`/`mov_bomba` do
turno reaberto pro turno anterior — isso existia porque, no legado, esses
registros eram gravados implicitamente sob "o turno aberto agora" (uma
variável de sessão), então reabrir um turno passado exigia corrigir
registros que tinham sido gravados sob o turno errado enquanto ele ainda
não tinha sido reaberto. **Nesta arquitetura isso não existe**: toda tela
de movimentação (Mov. Encerrantes, Aferições/Despesas) já pede
explicitamente `data`+`turno` ao usuário, em vez de herdar implicitamente
"o turno aberto agora" — não há registro pra "corrigir" depois. Por isso
Reabertura aqui só reverte o estado de controle (`controle_turno`,
`turno_movimento`, `data_movimento`, `FECHAMENTO_TURNO`), sem tocar em
`abastecimento`/`mov_bomba`.

Também não replicado: a checagem de "`CodTurno = Qtd_Turnos`" do legado
que, junto com um `Msgbox`, tratava reabrir o último fechamento do dia
como um caso especial — investigando o código, essa ramificação existia
pra contornar um bug de sincronização do `DATESIST` (global de processo,
podia ficar desatualizado numa estação enquanto outra já tinha fechado o
dia). Como `data_movimento`/`turno_movimento` aqui são sempre lidos frescos
do banco a cada requisição (nunca cacheados), esse bug não existe — o
caso "reabrir o fechamento que encerrou o dia" e o caso "reabrir um turno
do mesmo dia" usam a mesma lógica simples abaixo (cruzar ou não a
fronteira do dia é só uma questão de `turno_movimento == 1`).
"""
import asyncio
from datetime import timedelta

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG, data_movimento, turno_movimento, qtd_turnos


def _preview_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        dm = data_movimento(cur)
        turno = turno_movimento(cur)
        qt = qtd_turnos(cur)
        if turno == 1:
            prev_turno, prev_data, cruza_dia = qt, dm - timedelta(days=1), True
        else:
            prev_turno, prev_data, cruza_dia = turno - 1, dm, False
        cur.execute("SELECT TOP 1 1 AS ok FROM controle_turno WHERE turno=%s AND data_movimento_pc=%s", (prev_turno, prev_data))
        existe = cur.fetchone() is not None
        return {
            "success": True, "data_movimento": str(dm) if dm else None, "turno_atual": turno,
            "turno_a_reabrir": prev_turno, "data_a_reabrir": str(prev_data), "cruza_dia": cruza_dia,
            "existe_fechamento": existe,
        }
    finally:
        conn.close()


def _reabrir_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}

        dm = data_movimento(cur)
        turno = turno_movimento(cur)
        qt = qtd_turnos(cur)
        if turno == 1:
            prev_turno, prev_data, cruza_dia = qt, dm - timedelta(days=1), True
        else:
            prev_turno, prev_data, cruza_dia = turno - 1, dm, False

        cur.execute("SELECT TOP 1 1 AS ok FROM controle_turno WHERE turno=%s AND data_movimento_pc=%s", (prev_turno, prev_data))
        if not cur.fetchone():
            return {"success": False, "message": "Nenhum fechamento encontrado pra reabrir."}

        cur.execute("DELETE FROM controle_turno WHERE turno=%s AND data_movimento_pc=%s", (prev_turno, prev_data))
        cur.execute("DELETE FROM bomba_encerrante WHERE turno=%s AND movimento=%s", (prev_turno, prev_data))
        if cruza_dia:
            cur.execute("DELETE FROM FECHAMENTO_TURNO WHERE Data_Movimento_PC=%s", (prev_data,))
            cur.execute("UPDATE controle SET data_movimento=%s, turno_movimento=%s", (prev_data, prev_turno))
        else:
            cur.execute("UPDATE controle SET turno_movimento=%s", (prev_turno,))
        conn.commit()
        return {
            "success": True,
            "message": f"Turno {prev_turno} de {prev_data} reaberto." + (" O dia voltou a ficar aberto." if cruza_dia else ""),
            "turno_reaberto": prev_turno, "data_reaberta": str(prev_data), "cruzou_dia": cruza_dia,
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao reabrir turno: {e}"}
    finally:
        conn.close()


async def preview(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_preview_sync, servidor, banco)


async def reabrir(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_reabrir_sync, servidor, banco)

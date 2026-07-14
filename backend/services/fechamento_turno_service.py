"""Fechamento de Turno (Posto de Combustível) — tabelas `controle_turno`,
`FECHAMENTO_TURNO`, `controle` (turno_movimento/data_movimento).

Legado: `FrmFecTurno.frm`. Fecha o turno corrente
(`posto_common.turno_movimento`); ao fechar o ÚLTIMO turno do dia
(`qtd_turnos`), também fecha o dia inteiro (`FECHAMENTO_TURNO`) e avança
`controle.data_movimento` (o "DATESIST" do dia seguinte).

**Regras reais replicadas**:
- Bloqueia se o turno já foi fechado, ou se o dia inteiro já foi fechado
  (existe `controle_turno` pro último turno desta data).
- Bloqueia fechar fora do horário mínimo configurado em
  `controle_turno_horario` (se não houver horário configurado pro turno,
  não restringe — mesmo comportamento neutro de "sem regra configurada").
- Bloqueia se houver abastecimentos pendentes de baixa
  (`status_abastecimento='PENDENTE'`) neste turno.

**Truques de VB6 NÃO replicados** (ver
`feedback_nao_replicar_truques_vb6`):
- Checagem hardcoded de CNPJ (`cgccontrole = "28663094000106"`) que
  liberava o fechamento mesmo com abastecimentos pendentes pra UM cliente
  específico — gambiarra de cliente único, não regra geral.
- `Rel_Encerra`/`Bombas_Sem_Movimento` (impressão de relatório + captura
  de encerrante via hardware Wayne Fusion) — Fase 2, fora de escopo (ver
  PENDENCIAS.md, decisão já tomada).
- `COMPUTADOR`/`USUARIO_REDE` (nome de máquina/usuário de rede do
  Windows) não são gravados — conceito de identidade de SO que não existe
  numa aplicação web (mesmo princípio de "Windows-only areas" do
  CLAUDE.md); `log_auditoria` já registra usuário/IP/plataforma.

Schema conferido ao vivo: `controle_turno` (Sequencia IDENTITY,
Data_Movimento_PC, Turno, Data_Fechamento_PC, Hora_Fechamento_PC,
Usuario_Fechamento, Computador, Usuario_Rede). `FECHAMENTO_TURNO`
(Sequencia IDENTITY, Data_Movimento_PC, Data_Fechamento_PC,
Hora_Fechamento_PC, Emitiu_Pendentes, Emitiu_Volume — colunas extras
`Tem_Volume_Pendente`/`Tem_Ab_Pendente` não usadas pelo `.frm`, fora de
escopo). `controle_turno_horario` (turno, hora_inicio, hora_fim).
"""
import asyncio
from datetime import date, datetime, timedelta

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG, data_movimento, turno_movimento, qtd_turnos


def _status_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        dm = data_movimento(cur)
        turno = turno_movimento(cur)
        qt = qtd_turnos(cur)
        cur.execute("SELECT TOP 1 1 AS ok FROM abastecimento WHERE status_abastecimento='PENDENTE' AND turno=%s", (turno,))
        tem_pendentes = cur.fetchone() is not None
        cur.execute("SELECT hora_inicio FROM controle_turno_horario WHERE turno=%s", (turno,))
        row = cur.fetchone()
        return {
            "success": True,
            "data_movimento": str(dm) if dm else None,
            "turno_atual": turno,
            "qtd_turnos": qt,
            "ultimo_turno_do_dia": turno == qt,
            "abastecimentos_pendentes": tem_pendentes,
            "hora_minima": (row or {}).get("hora_inicio"),
        }
    finally:
        conn.close()


def _fechar_sync(servidor: str, banco: str, usuario: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}

        dm = data_movimento(cur)
        turno = turno_movimento(cur)
        qt = qtd_turnos(cur)

        cur.execute("SELECT TOP 1 1 AS ok FROM controle_turno WHERE turno=%s AND data_movimento_pc=%s", (qt, dm))
        if cur.fetchone():
            return {"success": False, "message": "Todos os turnos desta data já foram fechados."}

        cur.execute("SELECT hora_inicio FROM controle_turno_horario WHERE turno=%s", (turno,))
        row = cur.fetchone()
        hora_inicio = (row or {}).get("hora_inicio")
        if hora_inicio:
            agora_hhmm = datetime.now().strftime("%H:%M")
            if agora_hhmm < str(hora_inicio)[:5]:
                return {"success": False, "message": f"Fora do horário permitido para fechar este turno (a partir de {hora_inicio})."}

        cur.execute("SELECT TOP 1 1 AS ok FROM abastecimento WHERE status_abastecimento='PENDENTE' AND turno=%s", (turno,))
        if cur.fetchone():
            return {"success": False, "message": f"Existem abastecimentos pendentes de baixa no turno {turno} — baixe-os antes de fechar."}

        hoje = date.today()
        hora = datetime.now().strftime("%H:%M:%S")
        cur.execute(
            "INSERT INTO controle_turno (data_movimento_pc, turno, data_fechamento_pc, hora_fechamento_pc, usuario_fechamento) "
            "VALUES (%s,%s,%s,%s,%s)",
            (dm, turno, hoje, hora, usuario),
        )

        dia_fechado = False
        nova_data_movimento = dm
        if turno == qt:
            cur.execute(
                "INSERT INTO FECHAMENTO_TURNO (Data_Movimento_PC, Data_Fechamento_PC, Hora_Fechamento_PC, Emitiu_Pendentes, Emitiu_Volume) "
                "VALUES (%s,%s,%s,0,0)",
                (dm, hoje, hora),
            )
            nova_data_movimento = dm + timedelta(days=1)
            cur.execute("UPDATE controle SET data_movimento=%s", (nova_data_movimento,))
            proximo_turno = 1
            dia_fechado = True
        else:
            proximo_turno = turno + 1
        cur.execute("UPDATE controle SET turno_movimento=%s", (proximo_turno,))
        conn.commit()
        return {
            "success": True,
            "message": f"Turno {turno} fechado." + (f" Dia encerrado — movimento avança para {nova_data_movimento}." if dia_fechado else ""),
            "turno_fechado": turno,
            "dia_fechado": dia_fechado,
            "novo_turno": proximo_turno,
            "nova_data_movimento": str(nova_data_movimento),
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar turno: {e}"}
    finally:
        conn.close()


async def status(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_status_sync, servidor, banco)


async def fechar(servidor: str, banco: str, usuario: int) -> dict:
    return await asyncio.to_thread(_fechar_sync, servidor, banco, usuario)

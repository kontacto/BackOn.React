"""Agenda — módulo de agendamento do legado (`FrmMarAge2.frm`/`FrmAtende.frm`/
`FrmCadLay.frm`/`FrmPreLay2.frm`), habilitado pelo módulo Clínica OU pelo
módulo Assistência (mesma tela/fluxo pros dois — ver `_modulo_agenda_ativo`,
`pedido_common.py`). Cobre tanto um item de Serviço do Pedido Geral
(`codauto` informado — cliente/serviço vêm do próprio pedido) quanto um
agendamento AVULSO criado direto da grade semanal (sem `codauto` —
cliente/serviço escolhidos na hora, inclusive cliente cadastrado na hora).
Ver PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: Clínica
(Agendamento)" pro rastreio completo e o racional de cada decisão.

Arquivo próprio (não dentro de `pedido_completo_service.py`) porque Agenda é
um conceito genérico no legado (também usado por O.S./Comanda) — mesmo
princípio de desacoplamento já usado pra Forma de Pagamento/Gestor de
Documentos.
"""
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional

from db.connection import _open_conn
from models.schemas import AgendarItemRequest, TrocarProfissionalRequest, FaturarAgendaAvulsoRequest
from services.pedido_common import (
    _modulo_agenda_ativo, DAV_AGE, DavPagamento, _fecha_fpag_dav,
    _ensure_agenda_forma_pag_tables, _ensure_agenda_os_table, _ensure_os_produto_agenda_cols,
)
from services.permissoes_service import tem_permissao

# 13 estados de "Situação do Atendimento" — réplica exata da lista fixa
# populada em `Form_Load` de `FrmAtende.frm`/`FrmMarAge2.frm` (sem tabela de
# lookup no legado, é texto livre mesmo).
SITUACOES_ATENDIMENTO = [
    "Aguardando", "Em Atendimento", "Atendido", "Desistência", "Não Confirmado",
    "Confirmado", "Avaliação", "Avaliado", "Chamando", "Ausente", "Medicar",
    "Medicado", "Encaminhar", "Encaminhado",
]
# Situações que bloqueiam edição sem autorização de gerente/supervisor/master
# (mesma regra do legado — `Command120.Enabled`/`PermissoesAgendamento`).
_SITUACOES_PROTEGIDAS = {"Atendido", "Desistência"}


def _dia_semana(data_str: str) -> int:
    """Domingo=1 ... Sábado=7 — mesma convenção já usada em
    `funcionarios_horarios.dia` (Cadastro de Funcionários,
    `frontend/app/funcionario-completo.tsx`'s `DIAS_SEMANA`)."""
    d = date.fromisoformat(data_str)
    return d.isoweekday() % 7 + 1


def _hhmm(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    return str(v)[:5]


def _hora_full(hora: str) -> str:
    return hora if len(hora) > 5 else f"{hora}:00"


def _data_iso(v) -> Optional[str]:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _formata_telefone(ddd, tel) -> str:
    """Junta DDD + telefone (ambos podem vir vazios) — mesmo dado exposto
    por `_find_clientes_for_pedido_sync` (clientes_service.py), só formatado
    pra exibição direto na linha da Agenda."""
    ddd_s = (str(ddd).strip() if ddd else "")
    tel_s = (str(tel).strip() if tel else "")
    if ddd_s and tel_s:
        return f"({ddd_s}) {tel_s}"
    return tel_s or ddd_s


def _somar_minutos(hora: str, minutos: int) -> str:
    t = datetime.strptime(hora[:5], "%H:%M")
    return (t + timedelta(minutes=minutos)).strftime("%H:%M")


def _horario_funcionario(cur, funcionario: int, data_str: str) -> Optional[dict]:
    cur.execute(
        "SELECT disp_ini, disp_fim, pausa_ini, pausa_fim, intervalo1, encaixe "
        "FROM funcionarios_horarios WHERE funcionario=%s AND dia=%s",
        (funcionario, _dia_semana(data_str)),
    )
    return cur.fetchone()


def _ausente(cur, funcionario: int, data_str: str, hora: str) -> bool:
    cur.execute(
        "SELECT TOP 1 1 AS ok FROM funcionarios_ausencias WHERE funcionario=%s "
        "AND data_ini<=%s AND data_fim>=%s AND hora_ini<=%s AND hora_fim>%s",
        (funcionario, data_str, data_str, _hora_full(hora), _hora_full(hora)),
    )
    return cur.fetchone() is not None


def _validar_disponibilidade(cur, funcionario: int, data_str: str, hora_ini: str,
                              excluir_codagenda: Optional[int] = None) -> tuple[Optional[dict], Optional[str]]:
    """Valida disponibilidade/pausa/ausência/capacidade de encaixe pro
    profissional no dia/hora dados. Retorna (horario_dict, None) se ok, ou
    (None, mensagem_de_erro) caso contrário. Compartilhada entre
    `_salvar_agendamento_sync` (validar antes de gravar), a grade semanal
    (`_list_grade_sync`, que reaproveita as peças soltas em vez desta função
    inteira — ela desenha TODOS os slots do dia, não só valida um) e
    `_trocar_profissional_sync`."""
    horario = _horario_funcionario(cur, funcionario, data_str)
    if not horario:
        return None, "Profissional não atende neste dia da semana."
    disp_ini, disp_fim = _hhmm(horario.get("disp_ini")), _hhmm(horario.get("disp_fim"))
    if not disp_ini or not disp_fim or not (disp_ini <= hora_ini < disp_fim):
        return None, f"Fora do horário de atendimento ({disp_ini or '?'} às {disp_fim or '?'})."
    pausa_ini, pausa_fim = _hhmm(horario.get("pausa_ini")), _hhmm(horario.get("pausa_fim"))
    if pausa_ini and pausa_fim and pausa_ini <= hora_ini < pausa_fim:
        return None, f"Horário de pausa do profissional ({pausa_ini} às {pausa_fim})."
    if _ausente(cur, funcionario, data_str, hora_ini):
        return None, "Profissional ausente nesse horário."
    encaixe_permitido = int(horario.get("encaixe") or 0)
    # AGENDA.hora_ini é nvarchar gravado sem segundos ("HH:MM" — ver
    # `_salvar_agendamento_sync`, que grava `req.hora_ini[:5]` cru, sem
    # `_hora_full()`); comparar aqui com segundos ("HH:MM:00") nunca batia
    # com o valor real gravado — bug real que fazia a checagem de
    # capacidade/vaga disponível nunca encontrar agendamentos já existentes
    # (achado ao vivo 2026-07-28, contra a conexão KONTACTO-TESTE: o slot
    # 08:00 do Leandro continuava "livre" na Agenda mesmo já tendo um
    # atendimento gravado nele). Não confundir com `_ausente()` acima, que
    # compara contra `funcionarios_ausencias.hora_ini` — tabela DIFERENTE,
    # essa sim gravada com segundos, `_hora_full()` está correto lá.
    params: list = [funcionario, data_str, hora_ini]
    sql = (
        "SELECT COUNT(*) AS qtd FROM AGENDA WHERE funcionario=%s AND data=%s AND hora_ini=%s "
        "AND situacao_atendimento <> 'Desistência'"
    )
    if excluir_codagenda:
        sql += " AND codagenda <> %s"
        params.append(excluir_codagenda)
    cur.execute(sql, tuple(params))
    ocupados = int(cur.fetchone()["qtd"])
    if ocupados >= 1 + encaixe_permitido:
        return None, "Não há vaga disponível nesse horário — capacidade excedida."
    horario["_ocupados"] = ocupados
    return horario, None


def _agendamento_por_codagenda(cur, codagenda: int) -> Optional[dict]:
    cur.execute(
        "SELECT a.codagenda, a.data, a.hora_ini, a.hora_fim, a.funcionario, a.cliente, a.servico, "
        "       a.valor, a.revisao, a.situacao_atendimento, a.agenda_descartavel, "
        "       a.agenda_obs_descartavel, a.hora_chegada, a.hora_saida, "
        "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS profissional, "
        "       COALESCE(c.fantasia, c.nome) AS cliente_nome, s.descricao AS servico_descricao, "
        "       ap.CODPEDIDO AS codauto, i.pedido, "
        "       ao.CODOS AS codauto_os, io.os AS os "
        "FROM AGENDA a "
        "JOIN funcionarios f ON f.codigo_int = a.funcionario "
        "LEFT JOIN cliente c ON c.codigo = a.cliente "
        "LEFT JOIN servicos s ON s.codigo = a.servico "
        "LEFT JOIN AGENDA_PEDIDO ap ON ap.CODAGENDA = a.codagenda "
        "LEFT JOIN pedido_venda_prod i ON i.codauto = ap.CODPEDIDO "
        "LEFT JOIN AGENDA_OS ao ON ao.CODAGENDA = a.codagenda "
        "LEFT JOIN os_produto io ON io.cod_os_prod = ao.CODOS "
        "WHERE a.codagenda = %s",
        (codagenda,),
    )
    r = cur.fetchone()
    if not r:
        return None
    data_v = r.get("data")
    codauto_pedido = int(r["codauto"]) if r.get("codauto") else None
    codauto_os = int(r["codauto_os"]) if r.get("codauto_os") else None
    return {
        "codagenda": int(r["codagenda"]),
        "data": data_v.isoformat() if hasattr(data_v, "isoformat") else str(data_v),
        "hora_ini": _hhmm(r.get("hora_ini")),
        "hora_fim": _hhmm(r.get("hora_fim")),
        "funcionario": int(r["funcionario"]),
        "cliente": int(r["cliente"]) if r.get("cliente") else None,
        "cliente_nome": (r.get("cliente_nome") or "").strip(),
        "servico": (r.get("servico") or "").strip(),
        "servico_descricao": (r.get("servico_descricao") or "").strip(),
        "valor": float(r.get("valor") or 0),
        "revisao": bool(r.get("revisao")),
        "profissional": (r.get("profissional") or "").strip(),
        "situacao_atendimento": (r.get("situacao_atendimento") or "").strip(),
        "descartavel_valor": float(r["agenda_descartavel"]) if r.get("agenda_descartavel") is not None else None,
        "descartavel_obs": (r.get("agenda_obs_descartavel") or "").strip(),
        "hora_chegada": _hhmm(r.get("hora_chegada")) or None,
        "hora_saida": _hhmm(r.get("hora_saida")) or None,
        # Item de origem — `codauto` continua sendo o codauto de PEDIDO (não
        # mexe no contrato já usado por `_faturar_avulso_sync`/frontend);
        # `origem`/`os` são os campos NOVOS pro vínculo com O.S. Completa
        # (ver `_salvar_agendamento_sync`/`_trocar_profissional_sync`, que
        # usam `origem` pra decidir qual tabela atualizar).
        "codauto": codauto_pedido,
        "codauto_os": codauto_os,
        "origem": "pedido" if codauto_pedido else ("os" if codauto_os else None),
        # Número do Pedido de Venda (não o codauto do item) — usado pra
        # abrir a Pré-venda direto da tela de Atendimento (user-directed,
        # 2026-07-28: "colocar um ícone para visualizar a Pré-venda").
        "pedido": int(r["pedido"]) if r.get("pedido") else None,
        "os": int(r["os"]) if r.get("os") else None,
    }


def _agendamento_atual(cur, codauto: int, origem: str = "pedido") -> Optional[dict]:
    """Agendamento vinculado a um item — de Pedido (`AGENDA_PEDIDO`,
    `origem="pedido"`, default — mantém 100% do comportamento anterior a
    esta extensão) ou de O.S. Completa (`AGENDA_OS`, `origem="os"`,
    `codauto` aqui é o `os_produto.cod_os_prod`)."""
    tabela = "AGENDA_PEDIDO" if origem == "pedido" else "AGENDA_OS"
    coluna = "CODPEDIDO" if origem == "pedido" else "CODOS"
    cur.execute(f"SELECT CODAGENDA FROM {tabela} WHERE {coluna} = %s", (codauto,))
    r = cur.fetchone()
    if not r:
        return None
    return _agendamento_por_codagenda(cur, int(r["CODAGENDA"]))


def _list_profissionais_agenda_sync(
    servidor: str, banco: str, servico: Optional[str] = None, especialidade: Optional[int] = None,
) -> dict:
    """`servico=None` e `especialidade=None` lista TODO profissional
    habilitado pra Agenda (`controla_agenda=1`), independente de
    especialidade — usado pelo seletor de profissional da grade semanal
    (`GET /agenda/grade`), que precisa listar profissionais antes de
    qualquer serviço estar em contexto. Com `servico` informado, filtra por
    elegibilidade de especialidade daquele serviço específico (uso original
    — Agendar item de Serviço/atendimento). Com `especialidade` informado
    (2026-07-28, user-directed — filtro por especialidade na tela Agenda),
    filtra direto por `funcionario_especialidades`, sem depender de nenhum
    serviço específico — os dois filtros são alternativos, `especialidade`
    tem prioridade se os dois vierem preenchidos (não deveria acontecer no
    uso normal, cada tela usa um)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if especialidade:
            cur.execute(
                "SELECT DISTINCT f.codigo_int, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS nome_guerra "
                "FROM funcionarios f "
                "JOIN funcionario_especialidades fe ON fe.funcionario = f.codigo_int "
                "WHERE f.controla_agenda = 1 AND f.situacao = 'A' AND fe.codigo_especialidade = %s "
                "ORDER BY nome_guerra",
                (especialidade,),
            )
        elif servico:
            cur.execute(
                "SELECT DISTINCT f.codigo_int, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS nome_guerra "
                "FROM funcionarios f "
                "JOIN funcionario_especialidades fe ON fe.funcionario = f.codigo_int "
                "JOIN servicos s ON s.codigo_especialidade = fe.codigo_especialidade "
                "WHERE f.controla_agenda = 1 AND f.situacao = 'A' AND s.codigo = %s "
                "ORDER BY nome_guerra",
                (servico,),
            )
        else:
            cur.execute(
                "SELECT DISTINCT f.codigo_int, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS nome_guerra "
                "FROM funcionarios f "
                "WHERE f.controla_agenda = 1 AND f.situacao = 'A' "
                "ORDER BY nome_guerra"
            )
        items = [
            {"codigo": int(r["codigo_int"]), "nome_guerra": (r.get("nome_guerra") or "").strip()}
            for r in cur.fetchall()
        ]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao buscar profissionais: {e}"}


def _get_agendamento_item_sync(servidor: str, banco: str, codauto: int, origem: str = "pedido") -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        ag = _agendamento_atual(cur, codauto, origem)
        cur.close()
        conn.close()
        return {"success": True, "agendamento": ag}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao buscar agendamento: {e}"}


def _get_agendamento_sync(servidor: str, banco: str, codagenda: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        ag = _agendamento_por_codagenda(cur, codagenda)
        cur.close()
        conn.close()
        if not ag:
            return {"success": False, "message": "Agendamento não encontrado."}
        return {"success": True, "agendamento": ag}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao buscar agendamento: {e}"}


def _list_grade_sync(servidor: str, banco: str, funcionario: int, data_ini: str, data_fim: str) -> dict:
    """Grade semanal de disponibilidade (réplica de `FrmMarAge2.frm`'s
    `MontaHorarios`, simplificada pra web: sem MSFlexGrid, uma lista de dias
    com uma lista de slots cada). Cada slot vem marcado `livre`/`ocupado`
    (com os atendimentos daquele horário)/`pausa`/`ausente`."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        dias = []
        d = date.fromisoformat(data_ini)
        fim = date.fromisoformat(data_fim)
        while d <= fim:
            data_str = d.isoformat()
            horario = _horario_funcionario(cur, funcionario, data_str)
            slots: list = []
            if horario:
                disp_ini, disp_fim = _hhmm(horario.get("disp_ini")), _hhmm(horario.get("disp_fim"))
                pausa_ini, pausa_fim = _hhmm(horario.get("pausa_ini")), _hhmm(horario.get("pausa_fim"))
                intervalo = int(horario.get("intervalo1") or 30)
                if disp_ini and disp_fim:
                    hora = disp_ini
                    while hora < disp_fim:
                        status = "livre"
                        atendimentos: Optional[list] = None
                        if pausa_ini and pausa_fim and pausa_ini <= hora < pausa_fim:
                            status = "pausa"
                        elif _ausente(cur, funcionario, data_str, hora):
                            status = "ausente"
                        else:
                            # Campos extra (2026-07-28, user-directed — referência
                            # de tela Agenda em VB.NET colada pelo usuário):
                            # telefone (via `cliente_tel`, mesmo padrão OUTER APPLY
                            # já usado em `clientes_service.py`), "Marcado Por"
                            # (`usuario_agenda` → funcionarios, mesma convenção de
                            # `usuario_alteracao` em toda auditoria do projeto),
                            # data/hora da marcação (`data_agenda`/`hora_agenda`),
                            # `encaixe`/`revisao`/`situacao_caixa` (já existiam na
                            # tabela AGENDA, só não eram lidos), e o Pedido de
                            # Venda vinculado (pro ícone "Visualizar Pré-venda" na
                            # própria linha).
                            cur.execute(
                                "SELECT a.codagenda, a.situacao_atendimento, a.servico, "
                                "       COALESCE(c.fantasia, c.nome) AS cliente_nome, "
                                "       s.descricao AS servico_descricao, "
                                "       a.encaixe, a.revisao, a.situacao_caixa, "
                                "       COALESCE(NULLIF(uf.nome_guerra,''), uf.nome) AS marcado_por, "
                                "       a.data_agenda, a.hora_agenda, "
                                "       COALESCE(ct.ddd, c.ddd_cli) AS ddd, "
                                "       COALESCE(ct.tel, c.telefone_cli) AS telefone, "
                                "       ap.CODPEDIDO AS codauto, i.pedido "
                                "FROM AGENDA a "
                                "LEFT JOIN cliente c ON c.codigo = a.cliente "
                                "LEFT JOIN servicos s ON s.codigo = a.servico "
                                "LEFT JOIN funcionarios uf ON uf.codigo_int = a.usuario_agenda "
                                "OUTER APPLY (SELECT TOP 1 ddd, tel FROM cliente_tel WHERE codigo = a.cliente ORDER BY sequencia) ct "
                                "LEFT JOIN AGENDA_PEDIDO ap ON ap.CODAGENDA = a.codagenda "
                                "LEFT JOIN pedido_venda_prod i ON i.codauto = ap.CODPEDIDO "
                                "WHERE a.funcionario=%s AND a.data=%s AND a.hora_ini=%s "
                                "AND a.situacao_atendimento <> 'Desistência'",
                                # AGENDA.hora_ini gravado sem segundos ("HH:MM") — ver
                                # comentário em `_validar_disponibilidade`, mesmo bug.
                                (funcionario, data_str, hora),
                            )
                            ocupantes = cur.fetchall()
                            if ocupantes:
                                status = "ocupado"
                                atendimentos = [{
                                    "codagenda": int(o["codagenda"]),
                                    "situacao": (o.get("situacao_atendimento") or "").strip(),
                                    "cliente": (o.get("cliente_nome") or "").strip(),
                                    "servico": (o.get("servico_descricao") or o.get("servico") or "").strip(),
                                    "encaixe": bool(o.get("encaixe")),
                                    "revisao": bool(o.get("revisao")),
                                    "pago": (o.get("situacao_caixa") or "").strip().upper() == "P",
                                    "marcado_por": (o.get("marcado_por") or "").strip(),
                                    "data_marcacao": _data_iso(o.get("data_agenda")),
                                    "hora_marcacao": _hhmm(o.get("hora_agenda")),
                                    "telefone": _formata_telefone(o.get("ddd"), o.get("telefone")),
                                    "pedido": int(o["pedido"]) if o.get("pedido") else None,
                                } for o in ocupantes]
                        slots.append({"hora": hora, "status": status, "atendimentos": atendimentos})
                        hora = _somar_minutos(hora, intervalo)
            # Resumo do dia (Marcados/Encaixe/Desistência) — mesmos 3
            # contadores da tela VB.NET de referência. Consulta própria (não
            # reaproveita `slots` acima) porque Desistência é deliberadamente
            # excluída da lista de ocupação normal (um horário cancelado
            # continua "livre" pra novo agendamento), mas ainda entra na
            # contagem do resumo.
            cur.execute(
                "SELECT "
                "  SUM(CASE WHEN situacao_atendimento <> 'Desistência' THEN 1 ELSE 0 END) AS marcados, "
                "  SUM(CASE WHEN situacao_atendimento <> 'Desistência' AND ISNULL(encaixe,0)=1 THEN 1 ELSE 0 END) AS encaixe, "
                "  SUM(CASE WHEN situacao_atendimento = 'Desistência' THEN 1 ELSE 0 END) AS desistencia "
                "FROM AGENDA WHERE funcionario=%s AND data=%s",
                (funcionario, data_str),
            )
            resumo_row = cur.fetchone() or {}
            resumo = {
                "marcados": int(resumo_row.get("marcados") or 0),
                "encaixe": int(resumo_row.get("encaixe") or 0),
                "desistencia": int(resumo_row.get("desistencia") or 0),
            }
            dias.append({"data": data_str, "atende": bool(horario), "slots": slots, "resumo": resumo})
            d = d + timedelta(days=1)
        cur.close()
        conn.close()
        return {"success": True, "dias": dias}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao buscar grade: {e}"}


def _list_horarios_disponiveis_sync(servidor: str, banco: str, funcionario: int, data_ini: str, meses: int) -> dict:
    """"Horários Disponíveis" (referência: tela Agenda em VB.NET colada pelo
    usuário, 2026-07-28 — checkbox + campo "Meses", default 1) — lista TODO
    slot livre do profissional num intervalo de N meses a partir de
    `data_ini`, achatado (sem quebrar por dia como `_list_grade_sync`).

    Implementação DELIBERADAMENTE diferente de `_list_grade_sync` (que faz
    uma consulta SQL por slot): pra 1-3 meses isso significa milhares de
    idas ao banco (dezenas de slots × ~60-90 dias), lento demais pra essa
    tela. Aqui busca-se UMA VEZ cada fonte de dado (horários semanais,
    ausências, agendamentos já feitos no período) e a disponibilidade é
    calculada em memória — mesmas regras de `_horario_funcionario`/
    `_ausente`/checagem de capacidade da grade normal, só que sem round-trip
    por slot."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        d_ini = date.fromisoformat(data_ini)
        # "N meses" aproximado por 30 dias corridos cada — mesma convenção já
        # usada em `_verificar_garantia_sync` acima ("1 Ano = 365 dias, 1 Mês
        # = 30 dias... aproximação deliberada, sem dependência nova"). Não é
        # uma data de vencimento contratual, só o horizonte desta lista.
        d_fim = d_ini + timedelta(days=30 * max(1, meses))
        data_fim = d_fim.isoformat()

        cur.execute(
            "SELECT dia, disp_ini, disp_fim, pausa_ini, pausa_fim, intervalo1, encaixe "
            "FROM funcionarios_horarios WHERE funcionario=%s",
            (funcionario,),
        )
        horarios_por_dia = {int(r["dia"]): r for r in cur.fetchall()}

        cur.execute(
            "SELECT data_ini, data_fim, hora_ini, hora_fim FROM funcionarios_ausencias "
            "WHERE funcionario=%s AND data_ini<=%s AND data_fim>=%s",
            (funcionario, data_fim, data_ini),
        )
        ausencias = []
        for r in cur.fetchall():
            ai = _data_iso(r.get("data_ini")) or ""
            af = _data_iso(r.get("data_fim")) or ""
            ausencias.append((ai, af, _hora_full(_hhmm(r.get("hora_ini"))), _hora_full(_hhmm(r.get("hora_fim")))))

        cur.execute(
            "SELECT data, hora_ini, COUNT(*) AS qtd FROM AGENDA "
            "WHERE funcionario=%s AND data BETWEEN %s AND %s AND situacao_atendimento <> 'Desistência' "
            "GROUP BY data, hora_ini",
            (funcionario, data_ini, data_fim),
        )
        ocupados: dict[tuple[str, str], int] = {}
        for r in cur.fetchall():
            data_r = _data_iso(r.get("data")) or ""
            hora_r = (r.get("hora_ini") or "")[:5]
            ocupados[(data_r, hora_r)] = int(r.get("qtd") or 0)

        def ausente(data_str: str, hora: str) -> bool:
            hf = _hora_full(hora)
            return any(ai <= data_str <= af and hi <= hf < hf2 for ai, af, hi, hf2 in ausencias)

        disponiveis = []
        d = d_ini
        dias_pt = ["Domingo", "Segunda-Feira", "Terça-Feira", "Quarta-Feira", "Quinta-Feira", "Sexta-Feira", "Sábado"]
        while d <= d_fim:
            data_str = d.isoformat()
            horario = horarios_por_dia.get(_dia_semana(data_str))
            if horario:
                disp_ini, disp_fim = _hhmm(horario.get("disp_ini")), _hhmm(horario.get("disp_fim"))
                pausa_ini, pausa_fim = _hhmm(horario.get("pausa_ini")), _hhmm(horario.get("pausa_fim"))
                intervalo = int(horario.get("intervalo1") or 30)
                encaixe_permitido = int(horario.get("encaixe") or 0)
                if disp_ini and disp_fim:
                    hora = disp_ini
                    while hora < disp_fim:
                        na_pausa = pausa_ini and pausa_fim and pausa_ini <= hora < pausa_fim
                        if not na_pausa and not ausente(data_str, hora):
                            qtd = ocupados.get((data_str, hora), 0)
                            if qtd < 1 + encaixe_permitido:
                                disponiveis.append({
                                    "data": data_str, "hora": hora,
                                    "dia_semana": dias_pt[d.isoweekday() % 7],
                                })
                        hora = _somar_minutos(hora, intervalo)
            d = d + timedelta(days=1)
        cur.close()
        conn.close()
        return {"success": True, "items": disponiveis, "data_fim": data_fim}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao buscar horários disponíveis: {e}"}


def _verificar_garantia_sync(servidor: str, banco: str, cliente: int, servico: str) -> dict:
    """Revisão/Garantia (`servicos.prazo_garantia`/`tipo_garantia` — 1=Anos,
    2=Dias, 3=Horas, 4=Meses, 5=Km, réplica de `RetornaGarantia`,
    `mdl_proc.bas:13468`): se o cliente já foi Atendido nesse mesmo serviço
    antes, calcula se ainda está dentro do prazo de garantia contado da data
    de execução. Km (tipo 5) não é validável por data (sem odômetro
    rastreado) — só sinaliza, não calcula prazo."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT prazo_garantia, tipo_garantia FROM servicos WHERE codigo=%s", (servico,))
        srow = cur.fetchone()
        if not srow or not int(srow.get("prazo_garantia") or 0):
            cur.close()
            conn.close()
            return {"success": True, "dentro_garantia": False}
        prazo = int(srow["prazo_garantia"])
        tipo = int(srow.get("tipo_garantia") or 0)
        if tipo == 5:
            cur.close()
            conn.close()
            return {
                "success": True, "dentro_garantia": False,
                "aviso": "Garantia por quilometragem — não verificável automaticamente por data.",
            }
        cur.execute(
            "SELECT TOP 1 data FROM AGENDA WHERE cliente=%s AND servico=%s "
            "AND situacao_atendimento='Atendido' ORDER BY data DESC",
            (cliente, servico),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": True, "dentro_garantia": False}
        data_exec = row["data"]
        if isinstance(data_exec, datetime):
            data_exec = data_exec.date()
        elif isinstance(data_exec, str):
            data_exec = date.fromisoformat(data_exec[:10])
        # Aproximação deliberada (sem dependência nova pra meses/anos
        # calendáricos exatos): 1 Ano = 365 dias, 1 Mês = 30 dias, Horas
        # tratado como "mesmo dia" (garantia por hora não se aplica a
        # reagendar em outro dia).
        dias_prazo = {1: prazo * 365, 2: prazo, 3: 0, 4: prazo * 30}.get(tipo, 0)
        expira = data_exec + timedelta(days=dias_prazo)
        dentro = date.today() <= expira
        return {"success": True, "dentro_garantia": dentro, "expira_em": expira.isoformat(), "data_execucao": data_exec.isoformat()}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao verificar garantia: {e}"}


def _recalc_data_agendamento_os_sync(cur, os_codigo: int) -> None:
    """Recalcula `os.data_agendamento`/`hora_agendamento` a partir do
    agendamento mais próximo entre os itens de serviço da OS (mesma
    semântica de `proxima_agenda`, os_service.py — exceto que aqui
    excluímos agendamentos com SITUACAO_ATENDIMENTO='Desistência', o que
    `proxima_agenda` não faz por ser só um indicador decorativo; aqui o
    valor alimenta de verdade a Lista de Atendimento por Calendário,
    então a correção é intencional). Chamada depois de qualquer
    criação/cancelamento de agendamento de item (`_salvar_agendamento_sync`/
    `_cancelar_agendamento_sync`, `origem="os"`) — user-directed
    2026-08-15: "data e hora agendada deverá ser alimentada pela agenda".

    NUNCA sobrescreve um compromisso de CABEÇALHO direto já setado
    (`os.codagenda_atendimento IS NOT NULL`, ver
    `os_completo_service._sincronizar_agendamento_cabecalho_sync`) — esse
    tem precedência; evita os dois mecanismos brigarem pelo mesmo campo."""
    cur.execute("SELECT codagenda_atendimento FROM os WHERE codigo=%s", (os_codigo,))
    row = cur.fetchone()
    if row and row.get("codagenda_atendimento"):
        return
    cur.execute(
        "SELECT TOP 1 a.data, a.hora_ini FROM AGENDA_OS ao "
        "JOIN os_produto op ON op.cod_os_prod = ao.CODOS "
        "JOIN AGENDA a ON a.codagenda = ao.CODAGENDA "
        "WHERE op.os = %s AND a.situacao_atendimento <> 'Desistência' "
        "ORDER BY a.data ASC, a.hora_ini ASC",
        (os_codigo,),
    )
    prox = cur.fetchone()
    cur.execute(
        "UPDATE os SET data_agendamento=%s, hora_agendamento=%s WHERE codigo=%s",
        (prox["data"] if prox else None, prox["hora_ini"] if prox else None, os_codigo),
    )


def _salvar_agendamento_sync(
    req: AgendarItemRequest, codauto: Optional[int], origem: str = "pedido", tela: str = "PEDIDO_COMP",
) -> dict:
    """Cria/reagenda um atendimento. `codauto` = item de Serviço de um
    Pedido Geral OU de uma O.S. Completa (`origem` decide qual —
    `origem="os"`: `codauto` é `os_produto.cod_os_prod`, cliente/serviço
    vêm do item da O.S.); `codauto=None` = avulso (usa `req.cliente`/
    `req.servico`/`req.valor`, direto da grade — `origem` não se aplica a
    esse caso). `tela` decide qual catálogo de permissão checar
    (`PEDIDO_COMP`/`OS_COMP`), mesmo padrão de `os_service._fechar_os_sync`."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, "AGENDAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para agendar."}
        if not _modulo_agenda_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Clínica/Assistência está desativado."}

        if codauto:
            if origem == "os":
                _ensure_agenda_os_table(cur)
                _ensure_os_produto_agenda_cols(cur)
                cur.execute(
                    "SELECT o.codigo AS pedido, i.codigo_interno AS produto, i.p_venda, i.item_cancelado, o.cliente "
                    "FROM os_produto i JOIN os o ON o.codigo = i.os "
                    "WHERE i.cod_os_prod = %s",
                    (codauto,),
                )
            else:
                cur.execute(
                    "SELECT i.pedido, i.produto, i.p_venda, i.item_cancelado, pv.cliente "
                    "FROM pedido_venda_prod i JOIN pedido_venda pv ON pv.pedido = i.pedido "
                    "WHERE i.codauto = %s",
                    (codauto,),
                )
            item = cur.fetchone()
            if not item:
                conn.close()
                return {"success": False, "message": "Item não encontrado."}
            # `item_cancelado` (bit) é a flag de cancelamento REALMENTE usada em
            # todo o resto do sistema (itens_service.py, descontos_service.py,
            # relatorios_service.py, etc. — sempre `ISNULL(item_cancelado,0)=0`
            # pra filtrar item ativo). `situacao_item` (usada aqui antes) é
            # gravada como literal 'A' em todo INSERT e nunca mais atualizada
            # por nenhum código deste app — em registros migrados do legado
            # (dado antigo, fora do controle desta gravação) pode vir com outro
            # valor sem que o item esteja de fato cancelado, gerando bloqueio
            # falso "Item cancelado não pode ser agendado" mesmo em item ativo.
            # Achado ao vivo 2026-07-28 contra a conexão KONTACTO-TESTE.
            if item.get("item_cancelado"):
                conn.close()
                return {"success": False, "message": "Item cancelado não pode ser agendado."}
            cur.execute("SELECT codigo FROM servicos WHERE codigo=%s", (item["produto"],))
            if not cur.fetchone():
                conn.close()
                return {"success": False, "message": "Só itens de Serviço podem ser agendados."}
            cliente = item["cliente"]
            servico = item["produto"]
            valor = float(item.get("p_venda") or 0)
            agendamento_atual = _agendamento_atual(cur, codauto, origem)
            codagenda_existente = agendamento_atual["codagenda"] if agendamento_atual else None
        else:
            if not req.cliente or not req.servico:
                conn.close()
                return {"success": False, "message": "Cliente e serviço são obrigatórios."}
            cur.execute("SELECT codigo, valor_hora FROM servicos WHERE codigo=%s", (req.servico,))
            srow = cur.fetchone()
            if not srow:
                conn.close()
                return {"success": False, "message": "Serviço não encontrado."}
            cliente = req.cliente
            servico = req.servico
            valor = float(req.valor) if req.valor is not None else float(srow.get("valor_hora") or 0)
            codagenda_existente = req.codagenda if req.codagenda else None
            agendamento_atual = _agendamento_por_codagenda(cur, codagenda_existente) if codagenda_existente else None
            if codagenda_existente and not agendamento_atual:
                conn.close()
                return {"success": False, "message": "Agendamento não encontrado."}

        if req.revisao:
            valor = 0.0

        # Elegibilidade por especialidade — mesma checagem já aplicada em
        # `_trocar_profissional_sync`, faltava aqui no caminho de
        # criar/salvar (`POST /api/agenda/avulso`), que é por onde o campo
        # Profissional PRINCIPAL da tela realmente grava (o combobox dele é
        # deliberadamente sem filtro, ver `_list_profissionais_agenda_sync`
        # — "não precisa selecionar o profissional novamente"). Sem essa
        # checagem aqui, dava pra salvar (inclusive editando um atendimento
        # já existente, sem passar pelo fluxo "Trocar Profissional") um
        # profissional sem nenhuma relação com a especialidade do serviço —
        # bug real achado ao vivo 2026-07-28.
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM funcionario_especialidades fe "
            "JOIN servicos s ON s.codigo_especialidade = fe.codigo_especialidade "
            "WHERE fe.funcionario=%s AND s.codigo=%s",
            (req.funcionario, servico),
        )
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Profissional não elegível para este serviço (especialidade/Controla Agenda)."}

        if agendamento_atual and agendamento_atual["situacao_atendimento"] in _SITUACOES_PROTEGIDAS:
            if not (req.autorizado_por or "").strip():
                conn.close()
                return {
                    "success": False,
                    "message": f"Atendimento já '{agendamento_atual['situacao_atendimento']}' — exige autorização de gerente/supervisor para alterar.",
                }

        hora_ini = req.hora_ini[:5]
        _horario, erro = _validar_disponibilidade(
            cur, req.funcionario, req.data, hora_ini,
            excluir_codagenda=codagenda_existente,
        )
        if erro:
            conn.close()
            return {"success": False, "message": erro}

        encaixe = 1 if _horario["_ocupados"] >= 1 else 0
        hora_fim = _somar_minutos(hora_ini, int(_horario.get("intervalo1") or 30))
        situacao = (req.situacao_atendimento or "Confirmado").strip()
        if situacao not in SITUACOES_ATENDIMENTO:
            situacao = "Confirmado"
        hora_chegada = _hora_full(req.hora_chegada[:5]) if req.hora_chegada else None
        hora_saida = _hora_full(req.hora_saida[:5]) if req.hora_saida else None

        if codagenda_existente:
            codagenda = codagenda_existente
            cur.execute(
                "UPDATE AGENDA SET funcionario=%s, cliente=%s, servico=%s, data=%s, hora_ini=%s, hora_fim=%s, "
                "encaixe=%s, valor=%s, revisao=%s, situacao_atendimento=%s, "
                "agenda_descartavel=%s, agenda_obs_descartavel=%s, hora_chegada=%s, hora_saida=%s "
                "WHERE codagenda=%s",
                (
                    req.funcionario, cliente, servico, req.data, hora_ini, hora_fim, encaixe,
                    valor, 1 if req.revisao else 0, situacao,
                    req.descartavel_valor, (req.descartavel_obs or "").strip() or None,
                    hora_chegada, hora_saida, codagenda,
                ),
            )
        else:
            cur.execute(
                "INSERT INTO AGENDA (funcionario, cliente, servico, data, hora_ini, hora_fim, valor, "
                "VALOR_ORIGINAL, encaixe, revisao, agenda_descartavel, agenda_obs_descartavel, "
                "hora_chegada, hora_saida, data_agenda, hora_agenda, usuario_agenda, situacao, "
                "SITUACAO_ATENDIMENTO, SITUACAO_CAIXA) "
                "OUTPUT INSERTED.codagenda "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,GETDATE(),"
                "        CONVERT(VARCHAR(8),GETDATE(),108),%s,'A',%s,'A')",
                (
                    req.funcionario, cliente, servico, req.data, hora_ini, hora_fim, valor, valor,
                    encaixe, 1 if req.revisao else 0,
                    req.descartavel_valor, (req.descartavel_obs or "").strip() or None,
                    hora_chegada, hora_saida, req.usuario_alteracao or 0, situacao,
                ),
            )
            row = cur.fetchone()
            codagenda = int(row["codagenda"] if isinstance(row, dict) else row[0])
            if codauto:
                tabela_bridge = "AGENDA_PEDIDO" if origem != "os" else "AGENDA_OS"
                coluna_bridge = "CODPEDIDO" if origem != "os" else "CODOS"
                cur.execute(
                    f"INSERT INTO {tabela_bridge} (CODAGENDA, {coluna_bridge}) VALUES (%s,%s)",
                    (codagenda, codauto),
                )

        if codauto:
            if origem == "os":
                cur.execute(
                    "UPDATE os_produto SET data_servico=%s, executor_agenda=%s WHERE cod_os_prod=%s",
                    (req.data, req.funcionario, codauto),
                )
                _recalc_data_agendamento_os_sync(cur, item["pedido"])
            else:
                cur.execute(
                    "UPDATE pedido_venda_prod SET data_servico=%s, executor_agenda=%s WHERE codauto=%s",
                    (req.data, req.funcionario, codauto),
                )
        conn.commit()
        ag = _agendamento_por_codagenda(cur, codagenda)
        cur.close()
        conn.close()
        return {"success": True, "agendamento": ag}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao agendar: {e}"}


def _cancelar_agendamento_sync(
    req: AgendarItemRequest, codauto: int, origem: str = "pedido", tela: str = "PEDIDO_COMP",
) -> dict:
    """Réplica a cascata real do legado (`FrmAtende.frm`, mudar
    SITUACAO_ATENDIMENTO pra 'Desistência'): desfaz o vínculo do item com o
    agendamento, mantendo a linha de `AGENDA` como histórico (marcada
    Desistência), e libera o item pra ser reagendado do zero. (Só se aplica
    ao fluxo vinculado a um item de Pedido/O.S. — pra um agendamento avulso,
    usar o mesmo `_salvar_agendamento_sync` mudando `situacao_atendimento`
    pra "Desistência".) `origem`/`tela` — ver `_salvar_agendamento_sync`."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, "AGENDAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar agendamento."}
        agendamento_atual = _agendamento_atual(cur, codauto, origem)
        if not agendamento_atual:
            conn.close()
            return {"success": False, "message": "Este item não tem agendamento."}
        cur.execute(
            "UPDATE AGENDA SET SITUACAO_ATENDIMENTO='Desistência' WHERE codagenda=%s",
            (agendamento_atual["codagenda"],),
        )
        if origem == "os":
            cur.execute("SELECT os FROM os_produto WHERE cod_os_prod=%s", (codauto,))
            os_row = cur.fetchone()
            cur.execute(
                "UPDATE os_produto SET data_servico=NULL, executor_agenda=0 WHERE cod_os_prod=%s",
                (codauto,),
            )
            cur.execute("DELETE FROM AGENDA_OS WHERE CODAGENDA=%s", (agendamento_atual["codagenda"],))
            if os_row and os_row.get("os"):
                _recalc_data_agendamento_os_sync(cur, int(os_row["os"]))
        else:
            cur.execute(
                "UPDATE pedido_venda_prod SET data_servico=NULL, executor_agenda=0 WHERE codauto=%s",
                (codauto,),
            )
            cur.execute("DELETE FROM AGENDA_PEDIDO WHERE CODAGENDA=%s", (agendamento_atual["codagenda"],))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar agendamento: {e}"}


def _trocar_profissional_sync(req: TrocarProfissionalRequest, codagenda: int) -> dict:
    """Troca o profissional de um agendamento já feito — exige autorização
    de gerente/supervisor/master (validada no frontend via
    `AuthorizationSlide`, o `autorizado_por` aqui só registra QUEM autorizou
    no log de auditoria; ver `PENDENCIAS.md` — a mesma decisão de não
    reverificar senha no backend já usada por `produtos-niveis.tsx`).
    Filtra o novo profissional por `controla_agenda=1` (confirmado pelo
    usuário — o legado não filtra ali, e isso foi tratado como bug do
    legado, não regra a replicar)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not (req.autorizado_por or "").strip():
            conn.close()
            return {"success": False, "message": "Troca de profissional exige autorização de gerente/supervisor."}
        ag = _agendamento_por_codagenda(cur, codagenda)
        if not ag:
            conn.close()
            return {"success": False, "message": "Agendamento não encontrado."}
        if ag["situacao_atendimento"] == "Desistência":
            conn.close()
            return {"success": False, "message": "Agendamento cancelado não pode trocar de profissional."}
        cur.execute(
            "SELECT DISTINCT f.codigo_int FROM funcionarios f "
            "JOIN funcionario_especialidades fe ON fe.funcionario=f.codigo_int "
            "JOIN servicos s ON s.codigo_especialidade=fe.codigo_especialidade "
            "WHERE f.controla_agenda=1 AND f.situacao='A' AND s.codigo=%s AND f.codigo_int=%s",
            (ag["servico"], req.novo_funcionario),
        )
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Profissional não elegível para este serviço (especialidade/Controla Agenda)."}
        _horario, erro = _validar_disponibilidade(
            cur, req.novo_funcionario, ag["data"], ag["hora_ini"], excluir_codagenda=codagenda,
        )
        if erro:
            conn.close()
            return {"success": False, "message": erro}
        cur.execute("UPDATE AGENDA SET funcionario=%s WHERE codagenda=%s", (req.novo_funcionario, codagenda))
        if ag.get("origem") == "os":
            cur.execute(
                "UPDATE os_produto SET executor_agenda=%s "
                "FROM os_produto JOIN AGENDA_OS ao ON ao.CODOS = os_produto.cod_os_prod "
                "WHERE ao.CODAGENDA=%s",
                (req.novo_funcionario, codagenda),
            )
        else:
            cur.execute(
                "UPDATE pedido_venda_prod SET executor_agenda=%s "
                "FROM pedido_venda_prod JOIN AGENDA_PEDIDO ap ON ap.CODPEDIDO = pedido_venda_prod.codauto "
                "WHERE ap.CODAGENDA=%s",
                (req.novo_funcionario, codagenda),
            )
        conn.commit()
        ag2 = _agendamento_por_codagenda(cur, codagenda)
        cur.close()
        conn.close()
        return {"success": True, "agendamento": ag2}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao trocar profissional: {e}"}


def _faturar_avulso_sync(req: FaturarAgendaAvulsoRequest, codagenda: int) -> dict:
    """Faturar direto pela Agenda (réplica de `GeraComanda`, `FrmAtende.frm`
    — sem emissão fiscal, mesmo recorte já usado no Faturar do Pedido Bar/
    Geral). Só permitido se o agendamento NÃO estiver vinculado a um item de
    Pedido/O.S. (mesma regra do legado: bloqueia faturamento avulso quando é
    pré-venda — nesse caso o faturamento é sempre pelo Pedido)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        ag = _agendamento_por_codagenda(cur, codagenda)
        if not ag:
            conn.close()
            return {"success": False, "message": "Agendamento não encontrado."}
        if ag.get("codauto"):
            conn.close()
            return {"success": False, "message": "Agendamento vinculado a um Pedido — fature pelo Pedido de Venda."}
        cur.execute("SELECT TOP 1 1 AS ok FROM agenda_comanda WHERE codagenda=%s", (codagenda,))
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Este agendamento já foi faturado anteriormente."}

        _ensure_agenda_forma_pag_tables(cur)
        dav = DavPagamento(tipo=DAV_AGE, documento=codagenda, situacao="A", valor=ag["valor"], forma_padrao=req.forma_pag)
        erro = _fecha_fpag_dav(cur, dav)
        if erro:
            conn.close()
            return {"success": False, "message": erro}

        cur.execute(
            "INSERT INTO comanda (data, cliente, valor_venda, situacao, atendente, hora_comanda) "
            "OUTPUT INSERTED.comanda "
            "VALUES (CAST(GETDATE() AS DATE), %s, %s, 'PG', %s, CONVERT(VARCHAR(8),GETDATE(),108))",
            (ag["cliente"], ag["valor"], req.usuario_alteracao or 0),
        )
        row = cur.fetchone()
        comanda = int(row["comanda"] if isinstance(row, dict) else row[0])
        cur.execute(
            "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, p_unit, num_nf, serie_nf, vendedor) "
            "VALUES (CAST(GETDATE() AS DATE), 'S01', %s, 1, %s, %s, 'CM', %s)",
            (ag["servico"], ag["valor"], comanda, req.usuario_alteracao or 0),
        )
        cur.execute("SELECT TOP 1 ID_MOV FROM movimentacao WHERE serie_nf='CM' AND num_nf=%s ORDER BY ID_MOV DESC", (comanda,))
        id_mov_row = cur.fetchone()
        id_mov = int(id_mov_row["ID_MOV"]) if id_mov_row else 0
        cur.execute(
            "INSERT INTO agenda_comanda (codagenda, codcomanda, situacao_atendimento, ID_MOVIMENTACAO) "
            "VALUES (%s,%s,%s,%s)",
            (codagenda, comanda, ag["situacao_atendimento"], id_mov),
        )
        cur.execute("UPDATE AGENDA SET SITUACAO_CAIXA='P' WHERE codagenda=%s", (codagenda,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "comanda": comanda}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao faturar: {e}"}


async def list_profissionais_agenda(
    servidor: str, banco: str, servico: Optional[str] = None, especialidade: Optional[int] = None,
) -> dict:
    return await asyncio.to_thread(_list_profissionais_agenda_sync, servidor, banco, servico, especialidade)


async def get_agendamento_item(servidor: str, banco: str, codauto: int, origem: str = "pedido") -> dict:
    return await asyncio.to_thread(_get_agendamento_item_sync, servidor, banco, codauto, origem)


async def get_agendamento(servidor: str, banco: str, codagenda: int) -> dict:
    return await asyncio.to_thread(_get_agendamento_sync, servidor, banco, codagenda)


async def list_grade(servidor: str, banco: str, funcionario: int, data_ini: str, data_fim: str) -> dict:
    return await asyncio.to_thread(_list_grade_sync, servidor, banco, funcionario, data_ini, data_fim)


async def list_horarios_disponiveis(servidor: str, banco: str, funcionario: int, data_ini: str, meses: int) -> dict:
    return await asyncio.to_thread(_list_horarios_disponiveis_sync, servidor, banco, funcionario, data_ini, meses)


async def verificar_garantia(servidor: str, banco: str, cliente: int, servico: str) -> dict:
    return await asyncio.to_thread(_verificar_garantia_sync, servidor, banco, cliente, servico)


async def salvar_agendamento(
    req: AgendarItemRequest, codauto: Optional[int], origem: str = "pedido", tela: str = "PEDIDO_COMP",
) -> dict:
    return await asyncio.to_thread(_salvar_agendamento_sync, req, codauto, origem, tela)


async def cancelar_agendamento(
    req: AgendarItemRequest, codauto: int, origem: str = "pedido", tela: str = "PEDIDO_COMP",
) -> dict:
    return await asyncio.to_thread(_cancelar_agendamento_sync, req, codauto, origem, tela)


async def trocar_profissional(req: TrocarProfissionalRequest, codagenda: int) -> dict:
    return await asyncio.to_thread(_trocar_profissional_sync, req, codagenda)


async def faturar_avulso(req: FaturarAgendaAvulsoRequest, codagenda: int) -> dict:
    return await asyncio.to_thread(_faturar_avulso_sync, req, codagenda)

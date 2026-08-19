"""Testes UNITÁRIOS do módulo Agenda (Fase B — Clínica, versão completa:
grade semanal, agendamento avulso, troca de profissional, garantia/revisão,
faturar avulso). Ver PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B:
Clínica (Agendamento)"."""
from datetime import date

import services.agenda_service as svc
from models.schemas import AgendarItemRequest, TrocarProfissionalRequest, FaturarAgendaAvulsoRequest


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor
        self.committed = False
        self.rolled = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _req(**over):
    base = dict(servidor="srv", banco="bd", funcionario=10, data="2026-08-03", hora_ini="14:00",
                classe=1, master=True, usuario_alteracao=1, plataforma="web")
    base.update(over)
    return AgendarItemRequest(**base)


ITEM_ROW = {"pedido": 1, "produto": "S100", "p_venda": 80.0, "item_cancelado": 0, "cliente": 55}
HORARIO_ROW = {"disp_ini": "08:00", "disp_fim": "18:00", "pausa_ini": "12:00", "pausa_fim": "13:00",
               "intervalo1": 30, "encaixe": 0}
AGENDA_LOOKUP = {"CODAGENDA": 900}
AGENDAMENTO_FULL_ROW = {
    "codagenda": 900, "data": date(2026, 8, 3), "hora_ini": "14:00:00", "hora_fim": "14:30:00",
    "funcionario": 10, "cliente": 55, "servico": "S100", "valor": 80.0, "revisao": False,
    "situacao_atendimento": "Confirmado", "agenda_descartavel": None, "agenda_obs_descartavel": None,
    "hora_chegada": None, "hora_saida": None, "profissional": "MARIA", "cliente_nome": "FULANO",
    "servico_descricao": "Consulta", "codauto": 501, "pedido": 3312,
}


class TestListProfissionaisAgenda:
    def test_lista_profissionais_habilitados(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo_int": 10, "nome_guerra": "MARIA"}]])
        _patch(monkeypatch, cur)
        r = svc._list_profissionais_agenda_sync("srv", "bd", "S100")
        assert r["success"] is True
        assert r["items"] == [{"codigo": 10, "nome_guerra": "MARIA"}]

    def test_sem_servico_lista_todos_controla_agenda(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo_int": 11, "nome_guerra": "JOAO"}]])
        _patch(monkeypatch, cur)
        r = svc._list_profissionais_agenda_sync("srv", "bd", None)
        assert r["success"] is True
        assert r["items"] == [{"codigo": 11, "nome_guerra": "JOAO"}]
        query = cur.queries[0][0]
        assert "funcionario_especialidades" not in query

    def test_filtro_por_especialidade(self, monkeypatch):
        """Filtro novo por Especialidade (tela Agenda, 2026-07-28) — direto
        em `funcionario_especialidades`, sem depender de nenhum serviço
        específico."""
        cur = FakeCursor(many=[[{"codigo_int": 12, "nome_guerra": "PEDRO"}]])
        _patch(monkeypatch, cur)
        r = svc._list_profissionais_agenda_sync("srv", "bd", None, 7)
        assert r["success"] is True
        assert r["items"] == [{"codigo": 12, "nome_guerra": "PEDRO"}]
        query, params = cur.queries[0]
        assert "funcionario_especialidades" in query and "servicos" not in query
        assert params == (7,)

    def test_especialidade_tem_prioridade_sobre_servico(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo_int": 12, "nome_guerra": "PEDRO"}]])
        _patch(monkeypatch, cur)
        r = svc._list_profissionais_agenda_sync("srv", "bd", "S100", 7)
        assert r["success"] is True
        query = cur.queries[0][0]
        assert "servicos" not in query


class TestGetAgendamentoItem:
    def test_sem_agendamento(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_agendamento_item_sync("srv", "bd", 501)
        assert r["success"] is True and r["agendamento"] is None

    def test_com_agendamento(self, monkeypatch):
        cur = FakeCursor(one=[dict(AGENDA_LOOKUP), dict(AGENDAMENTO_FULL_ROW)])
        _patch(monkeypatch, cur)
        r = svc._get_agendamento_item_sync("srv", "bd", 501)
        assert r["success"] is True
        assert r["agendamento"]["hora_ini"] == "14:00"
        assert r["agendamento"]["profissional"] == "MARIA"
        assert r["agendamento"]["cliente_nome"] == "FULANO"


class TestGetAgendamento:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_agendamento_sync("srv", "bd", 900)
        assert r["success"] is False

    def test_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW)])
        _patch(monkeypatch, cur)
        r = svc._get_agendamento_sync("srv", "bd", 900)
        assert r["success"] is True and r["agendamento"]["codagenda"] == 900

    def test_traz_numero_do_pedido_vinculado(self, monkeypatch):
        """Regressão: número do Pedido de Venda (não o codauto do item) —
        usado pro ícone "visualizar Pré-venda" na tela de Atendimento
        (2026-07-28)."""
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW)])
        _patch(monkeypatch, cur)
        r = svc._get_agendamento_sync("srv", "bd", 900)
        assert r["agendamento"]["pedido"] == 3312

    def test_sem_pedido_vinculado_fica_none(self, monkeypatch):
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW, codauto=None, pedido=None)])
        _patch(monkeypatch, cur)
        r = svc._get_agendamento_sync("srv", "bd", 900)
        assert r["agendamento"]["pedido"] is None


class TestAgendamentoPorCodagendaOrigem:
    """`origem` (novo campo, 2026-08-01 — extensão pra O.S. Completa) é
    derivado de qual bridge table tem vínculo (`AGENDA_PEDIDO`/`AGENDA_OS`),
    não lido diretamente da linha — chamado direto com um FakeCursor (a
    própria função só recebe `cur`, não servidor/banco)."""

    def test_deriva_origem_pedido_por_padrao(self):
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW)])
        r = svc._agendamento_por_codagenda(cur, 900)
        assert r["origem"] == "pedido"
        assert r["codauto"] == 501

    def test_deriva_origem_os_quando_vinculado_a_os(self):
        row = dict(AGENDAMENTO_FULL_ROW, codauto=None, pedido=None, codauto_os=333, os=777)
        cur = FakeCursor(one=[row])
        r = svc._agendamento_por_codagenda(cur, 900)
        assert r["origem"] == "os"
        assert r["codauto_os"] == 333
        assert r["os"] == 777
        assert r["codauto"] is None

    def test_sem_vinculo_origem_none(self):
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW, codauto=None, pedido=None)])
        r = svc._agendamento_por_codagenda(cur, 900)
        assert r["origem"] is None


class TestSalvarAgendamentoViaPedido:
    """Fluxo vinculado a um item de Pedido Geral (`codauto`)."""

    def test_modulo_desligado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 0, "Assistencia": 0}])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "clínica" in r["message"].lower()

    def test_modulo_assistencia_liga_mesmo_fluxo(self, monkeypatch):
        """Assistência liga o MESMO fluxo de Agenda que Clínica — mesma
        tela, user-directed 2026-07-28. Ver `_modulo_agenda_ativo`."""
        cur = FakeCursor(one=[{"CLINICA": 0, "Assistencia": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_item_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_item_cancelado_bloqueia(self, monkeypatch):
        row = dict(ITEM_ROW, item_cancelado=1)
        cur = FakeCursor(one=[{"CLINICA": 1}, row])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "cancelado" in r["message"].lower()

    def test_nao_e_servico_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}, dict(ITEM_ROW), None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "serviço" in r["message"].lower()

    def test_profissional_nao_atende_no_dia(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "não atende" in r["message"].lower()

    def test_fora_do_horario_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1}, dict(HORARIO_ROW)])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(hora_ini="20:00"), 501)
        assert r["success"] is False and "fora do horário" in r["message"].lower()

    def test_horario_de_pausa_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1}, dict(HORARIO_ROW)])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(hora_ini="12:30"), 501)
        assert r["success"] is False and "pausa" in r["message"].lower()

    def test_ausencia_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1}, dict(HORARIO_ROW), {"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "ausente" in r["message"].lower()

    def test_nao_elegivel_por_especialidade_bloqueia(self, monkeypatch):
        """Regressão: profissional sem a especialidade do serviço não pode
        ser salvo como responsável do atendimento — antes só a Troca de
        Profissional checava isso; o caminho de criar/salvar (usado pelo
        campo Profissional principal, deliberadamente sem filtro no
        combobox) deixava passar. Achado ao vivo 2026-07-28."""
        cur = FakeCursor(one=[{"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "elegível" in r["message"].lower()

    def test_capacidade_excedida_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[
            {"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1}, dict(HORARIO_ROW), None, {"qtd": 1},
        ])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "capacidade" in r["message"].lower()

    def test_checagem_de_capacidade_compara_sem_segundos(self, monkeypatch):
        """Regressão: AGENDA.hora_ini é nvarchar gravado sem segundos
        ("HH:MM" — ver `_salvar_agendamento_sync`). Comparar com segundos
        (`_hora_full`, "HH:MM:00") nunca batia com o valor real gravado,
        fazendo a checagem de vaga/capacidade sempre contar 0 ocupados —
        bug real achado ao vivo 2026-07-28 (Agenda mostrava um horário como
        livre mesmo já tendo um atendimento gravado nele)."""
        cur = FakeCursor(one=[
            {"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1}, dict(HORARIO_ROW), None, {"qtd": 0},
        ])
        _patch(monkeypatch, cur)
        svc._salvar_agendamento_sync(_req(hora_ini="14:00"), 501)
        _, params = next((q, p) for q, p in cur.queries if "COUNT(*)" in q and "FROM AGENDA" in q)
        assert "14:00" in params and "14:00:00" not in params

    def test_atendimento_atendido_exige_autorizacao(self, monkeypatch):
        existente = dict(AGENDAMENTO_FULL_ROW, situacao_atendimento="Atendido")
        cur = FakeCursor(one=[{"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, dict(AGENDA_LOOKUP), existente, {"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "autorização" in r["message"].lower()

    def test_criar_agendamento_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[
            {"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1}, dict(HORARIO_ROW), None, {"qtd": 0},
            {"codagenda": 900}, dict(AGENDAMENTO_FULL_ROW),
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501)
        assert r["success"] is True
        assert r["agendamento"]["codagenda"] == 900
        assert conn.committed is True
        insert_agenda = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO AGENDA (")]
        insert_vinculo = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO AGENDA_PEDIDO")]
        assert len(insert_agenda) == 1 and len(insert_vinculo) == 1

    def test_reagendar_atualiza_mesma_linha(self, monkeypatch):
        cur = FakeCursor(one=[
            {"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, dict(AGENDA_LOOKUP), dict(AGENDAMENTO_FULL_ROW),
            {"ok": 1}, dict(HORARIO_ROW), None, {"qtd": 0}, dict(AGENDAMENTO_FULL_ROW),
        ])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(hora_ini="15:00"), 501)
        assert r["success"] is True
        update_calls = [q for q, _ in cur.queries if q.strip().startswith("UPDATE AGENDA SET")]
        insert_calls = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO AGENDA (")]
        assert len(update_calls) == 1 and len(insert_calls) == 0

    def test_revisao_zera_valor(self, monkeypatch):
        cur = FakeCursor(one=[
            {"CLINICA": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1}, dict(HORARIO_ROW), None, {"qtd": 0},
            {"codagenda": 900}, dict(AGENDAMENTO_FULL_ROW),
        ])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(revisao=True), 501)
        assert r["success"] is True
        insert_q, insert_p = next(
            (q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO AGENDA (")
        )
        # valor e VALOR_ORIGINAL são os 7º/8º parâmetros do INSERT — ambos 0.0
        assert insert_p[6] == 0.0 and insert_p[7] == 0.0


class TestRecalcDataAgendamentoOS:
    """`_recalc_data_agendamento_os_sync` — alimenta `os.data_agendamento`/
    `hora_agendamento` a partir do agendamento mais próximo entre os itens
    de serviço da OS (user-directed 2026-08-15: "data e hora agendada
    deverá ser alimentada pela agenda"). Chamada de dentro de
    `_salvar_agendamento_sync`/`_cancelar_agendamento_sync` — ver
    TestSalvarAgendamentoViaOS/TestCancelarAgendamentoOS pra confirmação
    de que é de fato chamada no fluxo real."""

    def test_pula_quando_compromisso_de_cabecalho_ja_setado(self, monkeypatch):
        cur = FakeCursor(one=[{"codagenda_atendimento": 555}])
        svc._recalc_data_agendamento_os_sync(cur, 777)
        # só a checagem inicial — nunca chega a recalcular nem gravar
        assert len(cur.queries) == 1
        assert not any(q.strip().startswith("UPDATE os SET") for q, _ in cur.queries)

    def test_recalcula_com_item_agendado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codagenda_atendimento": None},
            {"data": date(2026, 8, 21), "hora_ini": "09:00"},
        ])
        svc._recalc_data_agendamento_os_sync(cur, 777)
        update_q, update_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os SET"))
        assert update_p == (date(2026, 8, 21), "09:00", 777)
        select_q = next(q for q, _ in cur.queries if q.strip().startswith("SELECT TOP 1"))
        assert "situacao_atendimento <> 'Desistência'" in select_q

    def test_limpa_quando_nenhum_item_agendado(self, monkeypatch):
        cur = FakeCursor(one=[{"codagenda_atendimento": None}, None])
        svc._recalc_data_agendamento_os_sync(cur, 777)
        update_q, update_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os SET"))
        assert update_p == (None, None, 777)


class TestSalvarAgendamentoViaOS:
    """Fluxo vinculado a um item de O.S. Completa (`codauto` = `cod_os_prod`,
    `origem="os"`) — mesma máquina de estados do Pedido (validação de
    disponibilidade/especialidade/etc. é 100% compartilhada), só a tabela/
    coluna de item e o vínculo mudam (`os_produto`/`AGENDA_OS` em vez de
    `pedido_venda_prod`/`AGENDA_PEDIDO`)."""

    def test_item_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 0, "Assistencia": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501, origem="os", tela="OS_COMP")
        assert r["success"] is False and "não encontrado" in r["message"].lower()
        item_query = next(q for q, _ in cur.queries if "os_produto i JOIN os o" in q)
        assert "i.cod_os_prod" in item_query

    def test_criar_agendamento_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[
            {"CLINICA": 0, "Assistencia": 1}, dict(ITEM_ROW), {"codigo": "S100"}, None, {"ok": 1},
            dict(HORARIO_ROW), None, {"qtd": 0}, {"codagenda": 900},
            # Recalculo de os.data_agendamento/hora_agendamento (alimenta a
            # Lista de Atendimento por Calendário, user-directed 2026-08-15)
            # — ver TestRecalcDataAgendamentoOS pro detalhe isolado dessa
            # função. Aqui só confirma que é CHAMADA no fluxo real.
            {"codagenda_atendimento": None}, {"data": date(2026, 8, 21), "hora_ini": "09:00"},
            dict(AGENDAMENTO_FULL_ROW),
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501, origem="os", tela="OS_COMP")
        assert r["success"] is True
        assert conn.committed is True
        insert_vinculo = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO AGENDA_OS")]
        assert len(insert_vinculo) == 1
        insert_vinculo_pedido = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO AGENDA_PEDIDO")]
        assert len(insert_vinculo_pedido) == 0
        update_item = [q for q, _ in cur.queries if q.strip().startswith("UPDATE os_produto SET data_servico")]
        assert len(update_item) == 1
        recalc_q, recalc_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os SET data_agendamento"))
        assert recalc_p == (date(2026, 8, 21), "09:00", 1)

    def test_checa_permissao_tela_os_comp(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"CLINICA": 0, "Assistencia": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(master=False, classe=3), 501, origem="os", tela="OS_COMP")
        assert r["success"] is False  # item não encontrado — só interessa a query de permissão aqui
        perm_query, perm_params = next((q, p) for q, p in cur.queries if "FROM permissoes" in q)
        assert perm_params[2] == "OS_COMP" and perm_params[3] == "AGENDAR"

    def test_modulo_desligado_bloqueia_os(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 0, "Assistencia": 0}])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), 501, origem="os", tela="OS_COMP")
        assert r["success"] is False and "clínica" in r["message"].lower()


class TestCancelarAgendamentoOS:
    def test_cancela_e_desfaz_vinculo_os(self, monkeypatch):
        row = dict(AGENDAMENTO_FULL_ROW, codauto=None, pedido=None, codauto_os=501, os=777)
        cur = FakeCursor(one=[
            {"CODAGENDA": 900}, row,
            # Recalculo de os.data_agendamento/hora_agendamento após
            # cancelar (alimenta a Lista de Atendimento por Calendário,
            # user-directed 2026-08-15) — ver TestRecalcDataAgendamentoOS.
            {"os": 777}, {"codagenda_atendimento": None}, None,
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_agendamento_sync(_req(), 501, origem="os", tela="OS_COMP")
        assert r["success"] is True
        assert conn.committed is True
        queries = [q for q in cur.queries]
        assert any("FROM AGENDA_OS" in q for q, _ in queries)
        limpa_item = [q for q, _ in cur.queries if q.strip().startswith("UPDATE os_produto")]
        apaga_vinculo = [q for q, _ in cur.queries if q.strip().startswith("DELETE FROM AGENDA_OS")]
        limpa_pedido = [q for q, _ in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod")]
        recalc_q, recalc_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os SET data_agendamento"))
        assert recalc_p == (None, None, 777)  # sem agendamento restante -> limpa
        assert limpa_item and apaga_vinculo and not limpa_pedido


class TestSalvarAgendamentoAvulso:
    """Fluxo avulso — sem `codauto`, direto da grade (cliente/serviço
    informados na hora)."""

    def test_sem_cliente_ou_servico_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(), None)
        assert r["success"] is False and "obrigatórios" in r["message"].lower()

    def test_servico_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(cliente=55, servico="S100"), None)
        assert r["success"] is False and "serviço não encontrado" in r["message"].lower()

    def test_nao_elegivel_por_especialidade_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 1}, {"codigo": "S100", "valor_hora": 80.0}, None])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(cliente=55, servico="S100"), None)
        assert r["success"] is False and "elegível" in r["message"].lower()

    def test_criar_avulso_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[
            {"CLINICA": 1}, {"codigo": "S100", "valor_hora": 80.0}, {"ok": 1}, dict(HORARIO_ROW), None, {"qtd": 0},
            {"codagenda": 950}, dict(AGENDAMENTO_FULL_ROW, codagenda=950, codauto=None),
        ])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(cliente=55, servico="S100"), None)
        assert r["success"] is True
        assert r["agendamento"]["codagenda"] == 950
        insert_vinculo = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO AGENDA_PEDIDO")]
        assert len(insert_vinculo) == 0  # avulso nunca vincula a um pedido

    def test_editar_avulso_existente(self, monkeypatch):
        cur = FakeCursor(one=[
            {"CLINICA": 1}, {"codigo": "S100", "valor_hora": 80.0}, dict(AGENDAMENTO_FULL_ROW, codauto=None),
            {"ok": 1}, dict(HORARIO_ROW), None, {"qtd": 0}, dict(AGENDAMENTO_FULL_ROW, codauto=None),
        ])
        _patch(monkeypatch, cur)
        r = svc._salvar_agendamento_sync(_req(cliente=55, servico="S100", codagenda=900), None)
        assert r["success"] is True
        update_calls = [q for q, _ in cur.queries if q.strip().startswith("UPDATE AGENDA SET")]
        assert len(update_calls) == 1


class TestCancelarAgendamento:
    def test_sem_agendamento_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._cancelar_agendamento_sync(_req(), 501)
        assert r["success"] is False and "não tem agendamento" in r["message"].lower()

    def test_cancela_e_desfaz_vinculo(self, monkeypatch):
        cur = FakeCursor(one=[dict(AGENDA_LOOKUP), dict(AGENDAMENTO_FULL_ROW)])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_agendamento_sync(_req(), 501)
        assert r["success"] is True
        assert conn.committed is True
        desistencia = [q for q, p in cur.queries if "Desistência" in q]
        limpa_item = [q for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod")]
        apaga_vinculo = [q for q, p in cur.queries if q.strip().startswith("DELETE FROM AGENDA_PEDIDO")]
        assert desistencia and limpa_item and apaga_vinculo


class TestTrocarProfissional:
    def _treq(self, **over):
        base = dict(servidor="srv", banco="bd", novo_funcionario=20, autorizado_por="GERENTE1",
                    classe=1, master=False, usuario_alteracao=1, plataforma="web")
        base.update(over)
        return TrocarProfissionalRequest(**base)

    def test_sem_autorizacao_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._trocar_profissional_sync(self._treq(autorizado_por=""), 900)
        assert r["success"] is False and "autorização" in r["message"].lower()

    def test_agendamento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._trocar_profissional_sync(self._treq(), 900)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_desistencia_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW, situacao_atendimento="Desistência")])
        _patch(monkeypatch, cur)
        r = svc._trocar_profissional_sync(self._treq(), 900)
        assert r["success"] is False and "cancelado" in r["message"].lower()

    def test_profissional_nao_elegivel_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW), None])
        _patch(monkeypatch, cur)
        r = svc._trocar_profissional_sync(self._treq(), 900)
        assert r["success"] is False and "elegível" in r["message"].lower()

    def test_troca_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[
            dict(AGENDAMENTO_FULL_ROW), {"codigo_int": 20}, dict(HORARIO_ROW), None, {"qtd": 0},
            dict(AGENDAMENTO_FULL_ROW, funcionario=20),
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._trocar_profissional_sync(self._treq(), 900)
        assert r["success"] is True
        assert conn.committed is True
        update_ag = [q for q, p in cur.queries if q.strip().startswith("UPDATE AGENDA SET funcionario")]
        assert len(update_ag) == 1
        update_pedido = [q for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod SET executor_agenda")]
        assert len(update_pedido) == 1

    def test_troca_com_sucesso_atualiza_os_produto_quando_origem_os(self, monkeypatch):
        """Regressão: agendamento vinculado a um item de O.S. Completa
        (`origem` derivado de `AGENDA_OS`) precisa atualizar
        `os_produto.executor_agenda`, não `pedido_venda_prod`."""
        ag_os = dict(AGENDAMENTO_FULL_ROW, codauto=None, pedido=None, codauto_os=501, os=777)
        cur = FakeCursor(one=[
            ag_os, {"codigo_int": 20}, dict(HORARIO_ROW), None, {"qtd": 0}, dict(ag_os, funcionario=20),
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._trocar_profissional_sync(self._treq(), 900)
        assert r["success"] is True
        assert conn.committed is True
        update_os = [q for q, p in cur.queries if q.strip().startswith("UPDATE os_produto SET executor_agenda")]
        assert len(update_os) == 1
        update_pedido = [q for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod SET executor_agenda")]
        assert len(update_pedido) == 0


class TestVerificarGarantia:
    def test_sem_prazo_garantia(self, monkeypatch):
        cur = FakeCursor(one=[{"prazo_garantia": 0, "tipo_garantia": 0}])
        _patch(monkeypatch, cur)
        r = svc._verificar_garantia_sync("srv", "bd", 55, "S100")
        assert r["success"] is True and r["dentro_garantia"] is False

    def test_tipo_km_nao_verifica_automaticamente(self, monkeypatch):
        cur = FakeCursor(one=[{"prazo_garantia": 10000, "tipo_garantia": 5}])
        _patch(monkeypatch, cur)
        r = svc._verificar_garantia_sync("srv", "bd", 55, "S100")
        assert r["success"] is True and r["dentro_garantia"] is False and "aviso" in r

    def test_sem_atendimento_anterior(self, monkeypatch):
        cur = FakeCursor(one=[{"prazo_garantia": 90, "tipo_garantia": 2}, None])
        _patch(monkeypatch, cur)
        r = svc._verificar_garantia_sync("srv", "bd", 55, "S100")
        assert r["success"] is True and r["dentro_garantia"] is False

    def test_dentro_do_prazo(self, monkeypatch):
        cur = FakeCursor(one=[{"prazo_garantia": 9999, "tipo_garantia": 2}, {"data": date.today()}])
        _patch(monkeypatch, cur)
        r = svc._verificar_garantia_sync("srv", "bd", 55, "S100")
        assert r["success"] is True and r["dentro_garantia"] is True

    def test_fora_do_prazo(self, monkeypatch):
        cur = FakeCursor(one=[{"prazo_garantia": 1, "tipo_garantia": 2}, {"data": date(2020, 1, 1)}])
        _patch(monkeypatch, cur)
        r = svc._verificar_garantia_sync("srv", "bd", 55, "S100")
        assert r["success"] is True and r["dentro_garantia"] is False


class TestFaturarAvulso:
    def _freq(self, **over):
        base = dict(servidor="srv", banco="bd", forma_pag="001", classe=1, master=True,
                    usuario_alteracao=1, plataforma="web")
        base.update(over)
        return FaturarAgendaAvulsoRequest(**base)

    def test_agendamento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._faturar_avulso_sync(self._freq(), 900)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_vinculado_a_pedido_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW)])  # codauto=501 já presente
        _patch(monkeypatch, cur)
        r = svc._faturar_avulso_sync(self._freq(), 900)
        assert r["success"] is False and "pedido de venda" in r["message"].lower()

    def test_ja_faturado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[dict(AGENDAMENTO_FULL_ROW, codauto=None), {"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._faturar_avulso_sync(self._freq(), 900)
        assert r["success"] is False and "já foi faturado" in r["message"].lower()


class TestListGrade:
    """Campos extra da linha da Agenda (2026-07-28, user-directed — a
    partir de uma tela de referência em VB.NET colada pelo usuário):
    telefone, "Marcado Por", data/hora da marcação, encaixe/revisão/pago, e
    Pedido de Venda vinculado (pro ícone de Pré-venda na própria linha).
    Mais o Resumo do Dia (Marcados/Encaixe/Desistência)."""

    def test_slot_ocupado_traz_campos_novos_e_resumo_do_dia(self, monkeypatch):
        horario_row = {
            "disp_ini": "10:00", "disp_fim": "10:30", "pausa_ini": None, "pausa_fim": None,
            "intervalo1": 30, "encaixe": 0,
        }
        ocupante_row = {
            "codagenda": 900, "situacao_atendimento": "Confirmado", "servico": "S100",
            "cliente_nome": "FULANO", "servico_descricao": "Consulta",
            "encaixe": 1, "revisao": False, "situacao_caixa": "P",
            "marcado_por": "MARIA", "data_agenda": date(2026, 7, 28), "hora_agenda": "10:15:00",
            "ddd": "21", "telefone": "999998888", "codauto": 501, "pedido": 3312,
        }
        resumo_row = {"marcados": 5, "encaixe": 2, "desistencia": 1}
        cur = FakeCursor(one=[horario_row, None, resumo_row], many=[[ocupante_row]])
        _patch(monkeypatch, cur)
        r = svc._list_grade_sync("srv", "bd", 10, "2026-07-28", "2026-07-28")
        assert r["success"] is True
        dia = r["dias"][0]
        assert dia["resumo"] == {"marcados": 5, "encaixe": 2, "desistencia": 1}
        slot = dia["slots"][0]
        assert slot["status"] == "ocupado"
        at = slot["atendimentos"][0]
        assert at["encaixe"] is True
        assert at["pago"] is True
        assert at["revisao"] is False
        assert at["marcado_por"] == "MARIA"
        assert at["data_marcacao"] == "2026-07-28"
        assert at["hora_marcacao"] == "10:15"
        assert at["telefone"] == "(21) 999998888"
        assert at["pedido"] == 3312

    def test_slot_livre_nao_computa_resumo_do_slot(self, monkeypatch):
        horario_row = {
            "disp_ini": "10:00", "disp_fim": "10:30", "pausa_ini": None, "pausa_fim": None,
            "intervalo1": 30, "encaixe": 0,
        }
        resumo_row = {"marcados": 0, "encaixe": 0, "desistencia": 0}
        cur = FakeCursor(one=[horario_row, None, resumo_row], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_grade_sync("srv", "bd", 10, "2026-07-28", "2026-07-28")
        dia = r["dias"][0]
        assert dia["slots"][0]["status"] == "livre"
        assert dia["resumo"] == {"marcados": 0, "encaixe": 0, "desistencia": 0}


class TestListHorariosDisponiveis:
    """"Horários Disponíveis" (checkbox + campo Meses, referência VB.NET
    colada pelo usuário 2026-07-28) — lista achatada de slots livres de um
    profissional num intervalo de N meses, calculada em memória (3 queries
    no total, não 1 por slot) por questão de performance."""

    def test_lista_slots_livres_do_primeiro_dia(self, monkeypatch):
        data_ini = "2026-08-03"
        dia = svc._dia_semana(data_ini)
        horarios = [{
            "dia": dia, "disp_ini": "08:00", "disp_fim": "09:00",
            "pausa_ini": None, "pausa_fim": None, "intervalo1": 30, "encaixe": 0,
        }]
        cur = FakeCursor(many=[horarios, [], []])
        _patch(monkeypatch, cur)
        r = svc._list_horarios_disponiveis_sync("srv", "bd", 10, data_ini, 1)
        assert r["success"] is True
        do_primeiro_dia = [(it["data"], it["hora"]) for it in r["items"] if it["data"] == data_ini]
        assert do_primeiro_dia == [(data_ini, "08:00"), (data_ini, "08:30")]
        assert all(it["dia_semana"] for it in r["items"])

    def test_slot_ocupado_ate_a_capacidade_nao_aparece(self, monkeypatch):
        data_ini = "2026-08-03"
        dia = svc._dia_semana(data_ini)
        horarios = [{
            "dia": dia, "disp_ini": "08:00", "disp_fim": "08:30",
            "pausa_ini": None, "pausa_fim": None, "intervalo1": 30, "encaixe": 0,
        }]
        ocupados = [{"data": date.fromisoformat(data_ini), "hora_ini": "08:00", "qtd": 1}]
        cur = FakeCursor(many=[horarios, [], ocupados])
        _patch(monkeypatch, cur)
        r = svc._list_horarios_disponiveis_sync("srv", "bd", 10, data_ini, 1)
        do_primeiro_dia = [it for it in r["items"] if it["data"] == data_ini]
        assert do_primeiro_dia == []

    def test_encaixe_permite_mais_um_mesmo_com_ocupado(self, monkeypatch):
        data_ini = "2026-08-03"
        dia = svc._dia_semana(data_ini)
        horarios = [{
            "dia": dia, "disp_ini": "08:00", "disp_fim": "08:30",
            "pausa_ini": None, "pausa_fim": None, "intervalo1": 30, "encaixe": 1,
        }]
        ocupados = [{"data": date.fromisoformat(data_ini), "hora_ini": "08:00", "qtd": 1}]
        cur = FakeCursor(many=[horarios, [], ocupados])
        _patch(monkeypatch, cur)
        r = svc._list_horarios_disponiveis_sync("srv", "bd", 10, data_ini, 1)
        do_primeiro_dia = [(it["data"], it["hora"]) for it in r["items"] if it["data"] == data_ini]
        assert do_primeiro_dia == [(data_ini, "08:00")]

    def test_ausencia_bloqueia_o_slot(self, monkeypatch):
        data_ini = "2026-08-03"
        dia = svc._dia_semana(data_ini)
        horarios = [{
            "dia": dia, "disp_ini": "08:00", "disp_fim": "08:30",
            "pausa_ini": None, "pausa_fim": None, "intervalo1": 30, "encaixe": 0,
        }]
        ausencias = [{"data_ini": data_ini, "data_fim": data_ini, "hora_ini": "00:00:00", "hora_fim": "23:59:00"}]
        cur = FakeCursor(many=[horarios, ausencias, []])
        _patch(monkeypatch, cur)
        r = svc._list_horarios_disponiveis_sync("srv", "bd", 10, data_ini, 1)
        do_primeiro_dia = [it for it in r["items"] if it["data"] == data_ini]
        assert do_primeiro_dia == []

    def test_sem_horario_configurado_para_o_dia_nao_gera_slot(self, monkeypatch):
        data_ini = "2026-08-03"
        # Configura horário só pro dia SEGUINTE ao de data_ini — o próprio
        # data_ini não deve gerar nenhum slot.
        dia_outro = (svc._dia_semana(data_ini) % 7) + 1
        horarios = [{
            "dia": dia_outro, "disp_ini": "08:00", "disp_fim": "08:30",
            "pausa_ini": None, "pausa_fim": None, "intervalo1": 30, "encaixe": 0,
        }]
        cur = FakeCursor(many=[horarios, [], []])
        _patch(monkeypatch, cur)
        r = svc._list_horarios_disponiveis_sync("srv", "bd", 10, data_ini, 1)
        do_primeiro_dia = [it for it in r["items"] if it["data"] == data_ini]
        assert do_primeiro_dia == []

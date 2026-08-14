"""Testes unitários de O.S. Completa (Fase 1 — núcleo, `FrmTraOsNew.frm`).
Fechar/Faturar/Reabrir/Cancelar NÃO duplicam a lógica da O.S. Mobile —
`os_completo_service` reaproveita literalmente as mesmas funções de
`os_service` (mesma tabela `os`), só passando `tela="OS_COMP"` (e
`acao="SITUACAO"` pro Cancelar). A regra de negócio em si já está coberta
pelos testes de `test_os_service.py` (`TestReabrirOS`/`TestCancelarOS`/
`TestFaturarOS`) — aqui só confirmamos cabeçalho (get/save) e que a
delegação passa os parâmetros certos, sem reabrir toda a bateria de
cenários de novo (mesmo padrão de `test_pedido_completo_service.py`)."""
import asyncio

import services.os_completo_service as svc
from models.schemas import OSCompletoSaveRequest, FecharRequest


class FakeCursor:
    def __init__(self, one=None, many=None, rowcount=1):
        self._one = list(one or [])
        self._many = list(many or [])
        self.rowcount = rowcount
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


def _os_req(**over):
    base = dict(
        servidor="srv", banco="bd", cliente=10, area_atuacao=None,
        descricao_cliente="", obs="", resumo="", status_os=None, atendente=None,
        situacao=None, placa="", marca="", modelo="", km=None, ano="", chassi="",
        numero_de_serie="", forma_pagamento=None,
        referencia_os="", tecnico_responsavel=None, posicao_os=None,
        previsao_termino=None, data_termino=None, hora_entrada="", hora_fechamento="",
        usuario_alteracao=1, classe=1, plataforma="web",
    )
    base.update(over)
    return OSCompletoSaveRequest(**base)


def _fechar_req(**over):
    base = dict(servidor="srv", banco="bd", classe=1, master=True, usuario_alteracao=1, plataforma="web")
    base.update(over)
    return FecharRequest(**base)


class TestGetOsCompleto:
    def test_nao_encontrada_repassa_erro_da_base(self, monkeypatch):
        monkeypatch.setattr(
            svc.os_service, "_get_os_sync",
            lambda *a, **k: {"success": False, "message": "OS não encontrada."},
        )
        r = svc._get_os_completo_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_encontrada_enriquece_com_campos_extras(self, monkeypatch):
        base = {"success": True, "os": {"codigo": 1, "cliente": 10}}
        monkeypatch.setattr(svc.os_service, "_get_os_sync", lambda *a, **k: base)
        row = {
            "referencia_os": "REF-1", "tecnico_responsavel": 30, "tecnico_nome": "João",
            "posicao_os": 2, "tipo_os_descricao": "Garantia", "previsao_termino": None,
            "data_termino": None, "hora_entrada": "08:00", "hora_fechamento": "",
            "status_os_descricao": "Em análise",
            "forma_pagamento_garantia": "DI", "forma_pagamento_garantia_descricao": "Dinheiro",
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_os_completo_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["os"]["referencia_os"] == "REF-1"
        assert r["os"]["tecnico_responsavel"] == 30
        assert r["os"]["tecnico_responsavel_nome"] == "João"
        assert r["os"]["posicao_os"] == 2
        assert r["os"]["tipo_os_descricao"] == "Garantia"
        assert r["os"]["status_os_descricao"] == "Em análise"
        assert r["os"]["forma_pagamento_garantia"] == "DI"

    def test_auxiliar_tecnico_presente(self, monkeypatch):
        """Auxiliar do técnico (regra 11, AssistenciaTecnicaCampo.md) —
        opcional, mesmo formato de tecnico_responsavel/tecnico_nome."""
        base = {"success": True, "os": {"codigo": 1, "cliente": 10}}
        monkeypatch.setattr(svc.os_service, "_get_os_sync", lambda *a, **k: base)
        row = {
            "referencia_os": "", "tecnico_responsavel": 30, "tecnico_nome": "João",
            "auxiliar_tecnico": 55, "auxiliar_nome": "Maria",
            "posicao_os": None, "tipo_os_descricao": "", "previsao_termino": None,
            "data_termino": None, "hora_entrada": "", "hora_fechamento": "",
            "status_os_descricao": "",
            "forma_pagamento_garantia": "", "forma_pagamento_garantia_descricao": "",
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_os_completo_sync("srv", "bd", 1)
        assert r["os"]["auxiliar_tecnico"] == 55
        assert r["os"]["auxiliar_tecnico_nome"] == "Maria"

    def test_auxiliar_tecnico_ausente_fica_none(self, monkeypatch):
        base = {"success": True, "os": {"codigo": 1, "cliente": 10}}
        monkeypatch.setattr(svc.os_service, "_get_os_sync", lambda *a, **k: base)
        row = {
            "referencia_os": "", "tecnico_responsavel": None, "tecnico_nome": None,
            "auxiliar_tecnico": None, "auxiliar_nome": None,
            "posicao_os": None, "tipo_os_descricao": "", "previsao_termino": None,
            "data_termino": None, "hora_entrada": "", "hora_fechamento": "",
            "status_os_descricao": "",
            "forma_pagamento_garantia": "", "forma_pagamento_garantia_descricao": "",
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_os_completo_sync("srv", "bd", 1)
        assert r["os"]["auxiliar_tecnico"] is None
        assert r["os"]["auxiliar_tecnico_nome"] == ""


class TestSaveOsCompleto:
    def test_criar_cliente_inativo_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "C"}])
        _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(_os_req(), None)
        assert r["success"] is False and "situação" in r["message"].lower()

    def test_criar_sucesso_grava_campos_extras(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "A"}, {"novo": 501}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(
            _os_req(referencia_os="REF-9", tecnico_responsavel=30, forma_pagamento_garantia="DI"), None,
        )
        assert r["success"] is True and r["codigo"] == 501
        assert conn.committed is True
        insert_q = next(q for q, _ in cur.queries if q.strip().startswith("INSERT INTO os "))
        assert "referencia_os" in insert_q and "tecnico_responsavel" in insert_q and "posicao_os" in insert_q
        assert "forma_pagamento_garantia" in insert_q
        insert_p = next(p for q, p in cur.queries if q.strip().startswith("INSERT INTO os "))
        assert "DI" in insert_p

    def test_atualizar_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(_os_req(), 555)
        assert r["success"] is False and "não encontrada" in r["message"].lower()

    def test_atualizar_situacao_diferente_de_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(_os_req(), 555)
        assert r["success"] is False and "não pode ser alterada" in r["message"]

    def test_atualizar_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(
            _os_req(cliente=99, referencia_os="REF-2", forma_pagamento_garantia="CH"), 555,
        )
        assert r["success"] is True and r["codigo"] == 555
        assert conn.committed is True
        update_q = next(q for q, _ in cur.queries if q.strip().startswith("UPDATE os SET"))
        assert "referencia_os=%s" in update_q and "tecnico_responsavel=%s" in update_q
        assert "forma_pagamento_garantia=%s" in update_q

    def test_atualizar_rowcount_zero_trata_como_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(_os_req(), 555)
        assert r["success"] is False and "não encontrada" in r["message"].lower()
        assert conn.rolled is True

    def test_criar_grava_auxiliar_tecnico(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "A"}, {"novo": 501}])
        _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(_os_req(tecnico_responsavel=30, auxiliar_tecnico=55), None)
        assert r["success"] is True
        insert_q = next(q for q, _ in cur.queries if q.strip().startswith("INSERT INTO os "))
        assert "auxiliar_tecnico" in insert_q
        insert_p = next(p for q, p in cur.queries if q.strip().startswith("INSERT INTO os "))
        assert 55 in insert_p

    def test_atualizar_grava_auxiliar_tecnico(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=1)
        _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(_os_req(auxiliar_tecnico=55), 555)
        assert r["success"] is True
        update_q = next(q for q, _ in cur.queries if q.strip().startswith("UPDATE os SET"))
        assert "auxiliar_tecnico=%s" in update_q


class TestEnsureAuxiliarTecnicoCol:
    def test_migracao_idempotente(self):
        queries = []

        class Cur:
            def execute(self, q, p=None):
                queries.append(q)

        svc._ensure_os_auxiliar_tecnico_col(Cur())
        assert len(queries) == 2
        assert "IF NOT EXISTS" in queries[0]
        assert "ALTER TABLE os ADD auxiliar_tecnico INT NULL" in queries[0]
        assert "CREATE INDEX IX_os_auxiliar_tecnico ON os(auxiliar_tecnico)" in queries[1]


class TestSaveOsCompletoDocOrigem:
    """Doc. Origem / Revisão Programada — a validação cruzada em si já é
    testada de ponta a ponta em `test_pedido_common_doc_origem.py`; aqui só
    confirmamos que `_save_os_completo_sync` chama `_validar_doc_origem`
    corretamente (mockada) e trata o resultado (bloqueio/gravação)."""

    def test_pula_validacao_quando_posicao_os_nao_informado(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "A"}, {"novo": 700}])
        _patch(monkeypatch, cur)
        chamou = {"v": False}

        def fake_validar(*a, **k):
            chamou["v"] = True
            return (True, False, "O", None)

        monkeypatch.setattr(svc, "_validar_doc_origem", fake_validar)
        r = svc._save_os_completo_sync(_os_req(), None)  # posicao_os=None (default)
        assert r["success"] is True
        assert chamou["v"] is False

    def test_bloqueia_quando_validacao_falha(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "A"}, {"descricao": "Revisão"}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(
            svc, "_validar_doc_origem", lambda *a, **k: (False, False, "O", "O.S. de origem não encontrada!"),
        )
        r = svc._save_os_completo_sync(_os_req(posicao_os=5), None)
        assert r["success"] is False
        assert r.get("requer_autorizacao") is True
        assert "não encontrada" in r["message"].lower()

    def test_sucesso_grava_os_original_tipo_doc_e_validou_garantia(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "A"}, {"descricao": "Garantia"}, {"novo": 701}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_validar_doc_origem", lambda *a, **k: (True, True, "O", None))
        r = svc._save_os_completo_sync(_os_req(posicao_os=5, os_original=300, tipo_doc_original="O"), None)
        assert r["success"] is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os "))
        assert "OS_ORIGINAL" in insert_q and "Tipo_Doc_Original" in insert_q and "VALIDOU_GARANTIA" in insert_q
        assert 300 in insert_p and "O" in insert_p and 1 in insert_p

    def test_bypass_com_autorizado_por_libera_gravacao(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "A"}, {"descricao": "Garantia"}, {"novo": 702}])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_validar_doc_origem", lambda *a, **k: (True, True, "O", None))
        r = svc._save_os_completo_sync(
            _os_req(posicao_os=5, os_original=300, autorizado_por="GERENTE1"), None,
        )
        assert r["success"] is True
        assert conn.committed is True


class TestSaveOsCompletoRevisoesProgramadas:
    """`qtd_revisoes` (Campo 151) gera N datas futuras (30 em 30 dias,
    pulando domingo) em `osrevisao` — roda em TODA gravação, independente
    do Tipo O.S. (mesmo comportamento do legado, `Campo(151).Enabled =
    True` incondicional no `Form_Load`)."""

    def test_gera_datas_futuras_quando_qtd_revisoes_informado(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "A"}, {"novo": 800}])
        _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(_os_req(qtd_revisoes=2), None)
        assert r["success"] is True
        inserts = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO osrevisao")]
        assert len(inserts) == 2
        deletes = [q for q, _ in cur.queries if q.strip().startswith("DELETE FROM osrevisao")]
        assert len(deletes) == 1

    def test_sem_qtd_revisoes_so_limpa_disponiveis_sem_inserir(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "A"}, {"novo": 801}])
        _patch(monkeypatch, cur)
        r = svc._save_os_completo_sync(_os_req(), None)
        assert r["success"] is True
        inserts = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO osrevisao")]
        assert inserts == []
        deletes = [(q, p) for q, p in cur.queries if q.strip().startswith("DELETE FROM osrevisao")]
        assert len(deletes) == 1
        assert "ISNULL(osrevisao,0)=0" in deletes[0][0]  # nunca apaga linha já consumida

    def test_consome_data_disponivel_da_os_de_origem_ao_gravar_revisao(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"descricao": "Revisão"}, {"sequencia": 42}], rowcount=1)
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_validar_doc_origem", lambda *a, **k: (True, True, "O", None))
        r = svc._save_os_completo_sync(_os_req(posicao_os=5, os_original=300), 555)
        assert r["success"] is True
        consumo = [(q, p) for q, p in cur.queries if q.strip().startswith("UPDATE osrevisao SET osrevisao=%s WHERE sequencia")]
        assert len(consumo) == 1
        assert consumo[0][1] == (555, 42)

    def test_tipo_nao_revisao_nao_tenta_consumir_data_da_origem(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"descricao": "Garantia"}], rowcount=1)
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_validar_doc_origem", lambda *a, **k: (True, True, "O", None))
        r = svc._save_os_completo_sync(_os_req(posicao_os=5, os_original=300), 555)
        assert r["success"] is True
        consumo = [q for q, _ in cur.queries if "osrevisao=%s WHERE sequencia" in q]
        assert consumo == []


class TestGetOsCompletoDocOrigem:
    def test_enriquece_com_doc_origem_e_revisoes(self, monkeypatch):
        from datetime import date

        base = {"success": True, "os": {"codigo": 1, "cliente": 10}}
        monkeypatch.setattr(svc.os_service, "_get_os_sync", lambda *a, **k: base)
        row = {
            "referencia_os": "", "tecnico_responsavel": None, "tecnico_nome": "",
            "posicao_os": 3, "tipo_os_descricao": "Revisão", "previsao_termino": None,
            "data_termino": None, "hora_entrada": "", "hora_fechamento": "",
            "status_os_descricao": "", "os_original": 300, "Tipo_Doc_Original": "O",
            "VALIDOU_GARANTIA": 1, "QtdRevisoes": 2,
        }
        revisoes = [
            {"sequencia": 1, "data": date(2026, 9, 1), "osrevisao": 0},
            {"sequencia": 2, "data": date(2026, 10, 1), "osrevisao": 900},
        ]
        cur = FakeCursor(one=[row], many=[revisoes])
        _patch(monkeypatch, cur)
        r = svc._get_os_completo_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["os"]["os_original"] == 300
        assert r["os"]["tipo_doc_original"] == "O"
        assert r["os"]["validou_garantia"] is True
        assert r["os"]["qtd_revisoes"] == 2
        assert len(r["os"]["revisoes_programadas"]) == 2
        assert r["os"]["revisoes_programadas"][0]["consumida_por"] is None
        assert r["os"]["revisoes_programadas"][1]["consumida_por"] == 900


class TestDelegacaoAcoesSituacao:
    """`os_completo_service` NÃO duplica a lógica de Fechar/Faturar/Reabrir/
    Cancelar — reaproveita literalmente as mesmas funções de `os_service`
    (mesma tabela `os`), só passando `tela="OS_COMP"`. A regra de negócio em
    si já está coberta por `test_os_service.py`
    (`TestReabrirOS`/`TestCancelarOS`/`TestFaturarOS`) — aqui só
    confirmamos que a delegação passa os parâmetros certos."""

    def test_fechar_delega_com_tela_os_comp(self, monkeypatch):
        chamada = {}

        async def fake_fechar(req, codigo, tela):
            chamada["args"] = (req, codigo, tela)
            return {"success": True, "situacao": "F"}

        monkeypatch.setattr(svc.os_service, "fechar_os", fake_fechar)
        req = _fechar_req()
        r = asyncio.run(svc.fechar_os_completo(req, 1))
        assert r["success"] is True
        assert chamada["args"] == (req, 1, "OS_COMP")

    def test_faturar_delega_com_tela_os_comp(self, monkeypatch):
        chamada = {}

        async def fake_faturar(req, codigo, tela):
            chamada["args"] = (req, codigo, tela)
            return {"success": True, "situacao": "PG"}

        monkeypatch.setattr(svc.os_service, "faturar_os", fake_faturar)
        req = _fechar_req()
        r = asyncio.run(svc.faturar_os_completo(req, 1))
        assert r["success"] is True
        assert chamada["args"] == (req, 1, "OS_COMP")

    def test_reabrir_delega_com_tela_os_comp(self, monkeypatch):
        chamada = {}

        async def fake_reabrir(req, codigo, tela):
            chamada["args"] = (req, codigo, tela)
            return {"success": True, "situacao": "A"}

        monkeypatch.setattr(svc.os_service, "reabrir_os", fake_reabrir)
        req = _fechar_req()
        r = asyncio.run(svc.reabrir_os_completo(req, 1))
        assert r["success"] is True
        assert chamada["args"] == (req, 1, "OS_COMP")

    def test_cancelar_delega_com_tela_os_comp_e_acao_situacao(self, monkeypatch):
        chamada = {}

        async def fake_cancelar(req, codigo, tela, acao):
            chamada["args"] = (req, codigo, tela, acao)
            return {"success": True, "situacao": "C"}

        monkeypatch.setattr(svc.os_service, "cancelar_os", fake_cancelar)
        req = _fechar_req()
        r = asyncio.run(svc.cancelar_os_completo(req, 1))
        assert r["success"] is True
        assert chamada["args"] == (req, 1, "OS_COMP", "SITUACAO")


class TestListRequisicoesVinculadas:
    """Aba "Requisições vinculadas a O.S." (`GridReq`, 100% somente leitura
    no legado `Revenda\\FrmTraOsNew.frm`) — une os dois mecanismos de
    vínculo do legado (`os_requisicao` e `requisicao.tipo_mov_requisicao`/
    `codigo_requisicao`), ver PENDENCIAS.md > "Requisições Vinculadas"."""

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._list_requisicoes_vinculadas_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_lista_e_soma_total(self, monkeypatch):
        itens = [
            {"requisicao": 10, "data": None, "qtd": 2.0, "p_unit": 15.0, "descricao": "Parafuso", "cod_fab": "PF-1"},
            {"requisicao": 11, "data": None, "qtd": 1.0, "p_unit": 50.0, "descricao": "Correia", "cod_fab": "CR-2"},
        ]
        cur = FakeCursor(one=[{"ok": 1}], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._list_requisicoes_vinculadas_sync("srv", "bd", 55)
        assert r["success"] is True
        assert len(r["items"]) == 2
        assert r["items"][0]["p_total"] == 30.0
        assert r["items"][1]["p_total"] == 50.0
        assert r["total"] == 80.0
        query = next(q for q, _ in cur.queries if "os_requisicao" in q)
        assert "UNION ALL" in query
        assert "tipo_mov_requisicao" in query

    def test_sem_lancamentos_retorna_lista_vazia(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_requisicoes_vinculadas_sync("srv", "bd", 55)
        assert r["success"] is True
        assert r["items"] == []
        assert r["total"] == 0.0

    def test_list_requisicoes_vinculadas_async(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}], many=[[]])
        _patch(monkeypatch, cur)
        r = asyncio.run(svc.list_requisicoes_vinculadas("srv", "bd", 55))
        assert r["success"] is True


ORIGEM_ROW = {
    "cliente": 10, "area_atuacao": 1, "descricao_cliente": "Reclamação X", "obs": "obs original",
    "resumo": "resumo", "status_os": 2, "atendente": 30, "placa": "ABC1234", "marca": "TOY",
    "modelo": "COR", "km": 50000, "ano": "2020", "chassi": "CHASSI1", "numero_de_serie": "NS100",
    "forma_pagamento": "DI", "referencia_os": "REF-1", "tecnico_responsavel": 40, "posicao_os": 5,
}


class TestCriarCopiaOS:
    """Criar Cópia (`Command49_Click`, `Revenda\\FrmTraOsNew.frm`) — cria
    uma O.S. nova Aberta a partir do cabeçalho + itens (só produto/serviço
    ainda ativo no cadastro) da O.S. de origem."""

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._criar_copia_os_sync("srv", "bd", 55, usuario_alteracao=1, classe=3, master=False)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._criar_copia_os_sync("srv", "bd", 999, usuario_alteracao=1, classe=1, master=True)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_sucesso_cria_nova_os_aberta_sem_itens(self, monkeypatch):
        cur = FakeCursor(
            one=[dict(ORIGEM_ROW), {"novo": 900}, {"exige_aprovacao_itens_os": 0}, {"valor": 0.0}],
            many=[[]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._criar_copia_os_sync("srv", "bd", 55, usuario_alteracao=1, classe=1, master=True)
        assert r["success"] is True
        assert r["codigo"] == 900
        assert conn.committed is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os "))
        assert "'A', 0" in insert_q  # situacao sempre 'A', valor sempre 0 na criação
        assert insert_p[0] == 900  # novo código
        assert insert_p[1] == 10   # cliente copiado da origem
        # OS_ORIGINAL sempre gravado como literal 0 (não parâmetro) — a
        # cópia nunca herda o Doc. Origem da O.S. original.
        assert "OS_ORIGINAL)" in insert_q and insert_q.strip().endswith(", 0)")

    def test_copia_itens_de_pecas_e_servicos_ativos(self, monkeypatch):
        cur = FakeCursor(
            one=[dict(ORIGEM_ROW), {"novo": 901}, {"exige_aprovacao_itens_os": 0}, {"valor": 300.0}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._criar_copia_os_sync("srv", "bd", 55, usuario_alteracao=1, classe=1, master=True)
        assert r["success"] is True
        inserts_itens = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO os_produto")]
        assert len(inserts_itens) == 2
        assert any("JOIN pecas m ON m.codigo_int" in q and "m.situacao='A'" in q for q in inserts_itens)
        assert any("JOIN servicos m ON m.codigo" in q and "m.situacao='A'" in q for q in inserts_itens)
        assert all("desconto, acrescimo" in q for q in inserts_itens)  # zera desconto/acréscimo na cópia

    def test_reserva_estoque_das_pecas_copiadas(self, monkeypatch):
        itens_copiados = [{"codigo_interno": "P100", "quant": 2.0}]
        cur = FakeCursor(
            one=[dict(ORIGEM_ROW), {"novo": 902}, {"exige_aprovacao_itens_os": 0}, {"ok": 1}, {"valor": 100.0}],
            many=[itens_copiados],
        )
        _patch(monkeypatch, cur)
        r = svc._criar_copia_os_sync("srv", "bd", 55, usuario_alteracao=1, classe=1, master=True)
        assert r["success"] is True
        reservas = [p for q, p in cur.queries if "SET qtd = ISNULL" in q]
        assert reservas == [(2.0, 2.0, "P100")]

    def test_nao_reserva_estoque_quando_exige_aprovacao(self, monkeypatch):
        cur = FakeCursor(
            one=[dict(ORIGEM_ROW), {"novo": 903}, {"exige_aprovacao_itens_os": 1}, {"valor": 100.0}],
        )
        _patch(monkeypatch, cur)
        r = svc._criar_copia_os_sync("srv", "bd", 55, usuario_alteracao=1, classe=1, master=True)
        assert r["success"] is True
        assert not any("os_produto WHERE os=" in q and "codigo_interno, quant" in q for q, _ in cur.queries)

    def test_criar_copia_os_async(self, monkeypatch):
        cur = FakeCursor(
            one=[dict(ORIGEM_ROW), {"novo": 904}, {"exige_aprovacao_itens_os": 0}, {"valor": 0.0}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = asyncio.run(svc.criar_copia_os("srv", "bd", 55, usuario_alteracao=1, classe=1, master=True))
        assert r["success"] is True and r["codigo"] == 904

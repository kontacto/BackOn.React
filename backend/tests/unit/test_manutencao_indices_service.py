"""Testes unitários de `services/manutencao_indices_service.py` — ver
docstring do módulo pro achado real que motivou (36 índices fragmentados
até 98%, estatística nunca atualizada, no BackOn VB6 de um cliente real)."""
from datetime import datetime, timedelta

import pytest

import services.manutencao_indices_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append(q)

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
        self.autocommit_calls = []

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def autocommit(self, status):
        self.autocommit_calls.append(status)

    def close(self):
        pass


def _agora_no_dia_e_hora(dia_projeto: int, hora: str) -> datetime:
    """`dia_projeto`: 0=domingo..6=sábado (convenção do projeto) — acha o
    próximo dia real da semana que cai nesse índice e devolve um datetime
    nesse dia, na hora pedida."""
    base = datetime(2026, 8, 30)  # 2026-08-30 é domingo (dia_projeto=0)
    h, m = (int(x) for x in hora.split(":"))
    for delta in range(7):
        candidata = base + timedelta(days=delta)
        if (candidata.weekday() + 1) % 7 == dia_projeto:
            return candidata.replace(hour=h, minute=m)
    raise AssertionError("dia_projeto inválido")


class TestDeveRodarAgoraSync:
    def test_nao_roda_quando_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{
            "manutencao_indices_ativo": False, "manutencao_indices_dias_semana": "0,1,2,3,4,5,6",
            "manutencao_indices_hora": "03:00", "manutencao_indices_ultima_execucao": None,
        }])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        assert svc._deve_rodar_agora_sync("srv", "bd") is False

    def test_nao_roda_fora_do_dia_configurado(self, monkeypatch):
        cur = FakeCursor(one=[{
            "manutencao_indices_ativo": True, "manutencao_indices_dias_semana": "1,2,3,4,5",  # seg-sex
            "manutencao_indices_hora": "03:00", "manutencao_indices_ultima_execucao": None,
        }])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        agora = _agora_no_dia_e_hora(0, "03:00")  # domingo — fora dos dias configurados
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is False

    def test_roda_dentro_do_dia_e_janela(self, monkeypatch):
        cur = FakeCursor(one=[{
            "manutencao_indices_ativo": True, "manutencao_indices_dias_semana": "0,1,2,3,4,5,6",
            "manutencao_indices_hora": "03:00", "manutencao_indices_ultima_execucao": None,
        }])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        agora = _agora_no_dia_e_hora(3, "03:20")  # dentro da janela de tolerância
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is True

    def test_nao_roda_de_novo_no_mesmo_dia(self, monkeypatch):
        agora = _agora_no_dia_e_hora(3, "03:20")
        cur = FakeCursor(one=[{
            "manutencao_indices_ativo": True, "manutencao_indices_dias_semana": "0,1,2,3,4,5,6",
            "manutencao_indices_hora": "03:00", "manutencao_indices_ultima_execucao": agora.replace(hour=3, minute=0),
        }])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is False

    def test_fora_da_janela_de_tolerancia(self, monkeypatch):
        cur = FakeCursor(one=[{
            "manutencao_indices_ativo": True, "manutencao_indices_dias_semana": "0,1,2,3,4,5,6",
            "manutencao_indices_hora": "03:00", "manutencao_indices_ultima_execucao": None,
        }])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        agora = _agora_no_dia_e_hora(3, "10:00")  # bem depois da janela de 59min
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is False


class TestRodarManutencaoSync:
    def test_rebuild_acima_de_30_reorganize_entre_5_e_30_ignora_abaixo_de_5(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"tabela": "pedido_venda", "indice": "PK_pedido", "frag": 66.0, "page_count": 1930},
            {"tabela": "pedido_venda", "indice": "idx_leve", "frag": 20.0, "page_count": 150},
            {"tabela": "pedido_venda", "indice": "idx_ok", "frag": 2.0, "page_count": 200},
        ]])
        conn = FakeConn(cur)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
        monkeypatch.setattr(svc, "_gravar_resultado_sync", lambda *a, **k: None)
        r = svc._rodar_manutencao_sync("srv", "bd")
        rebuild = [q for q in cur.queries if "REBUILD" in q]
        reorganize = [q for q in cur.queries if "REORGANIZE" in q]
        stats = [q for q in cur.queries if q.startswith("UPDATE STATISTICS")]
        assert len(rebuild) == 1 and "PK_pedido" in rebuild[0]
        assert len(reorganize) == 1 and "idx_leve" in reorganize[0]
        assert not any("idx_ok" in q for q in rebuild + reorganize)
        assert len(stats) == 1  # 1 tabela tocada (pedido_venda), stats atualizada 1x só
        assert r["success"] is True
        assert conn.autocommit_calls == [True, False]

    def test_falha_isolada_em_um_indice_nao_impede_os_outros(self, monkeypatch):
        class CursorComFalha(FakeCursor):
            def execute(self, q, p=None):
                self.queries.append(q)
                if "idx_ruim" in q:
                    raise RuntimeError("boom")

        cur = CursorComFalha(many=[[
            {"tabela": "os_produto", "indice": "idx_ruim", "frag": 90.0, "page_count": 500},
            {"tabela": "os_produto", "indice": "idx_bom", "frag": 90.0, "page_count": 500},
        ]])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_gravar_resultado_sync", lambda *a, **k: None)
        r = svc._rodar_manutencao_sync("srv", "bd")
        assert any("idx_bom" in q for q in cur.queries if "REBUILD" in q)
        assert r["success"] is False  # tem erro registrado, mas não propagou exceção

    def test_falha_de_conexao_grava_resultado_e_nao_propaga(self, monkeypatch):
        def _falha(*a, **k):
            raise ConnectionError("Falha conexão")
        monkeypatch.setattr(svc, "_open_conn", _falha)
        gravados = []
        monkeypatch.setattr(svc, "_gravar_resultado_sync", lambda servidor, banco, resumo: gravados.append(resumo))
        r = svc._rodar_manutencao_sync("srv", "bd")
        assert r["success"] is False
        assert gravados and "Falha ao conectar" in gravados[0]


class TestCicloManutencaoSync:
    """`_ciclo_manutencao_sync` agora também decide sobre CHECKDB e roda a
    checagem de espaço a cada ciclo (extensão 2026-08-31) — todo teste
    aqui precisa mockar os 2 novos pontos (`_deve_rodar_checkdb_agora_sync`/
    `_verificar_espaco_sync`) mesmo quando o foco é só a manutenção de
    índices, senão o ciclo tentaria abrir uma conexão real."""

    def _mock_checkdb_e_espaco(self, monkeypatch, chamou_checkdb=None, chamou_espaco=None):
        monkeypatch.setattr(
            svc, "_deve_rodar_checkdb_agora_sync",
            lambda *a: (chamou_checkdb.append(1) or False) if chamou_checkdb is not None else False,
        )
        monkeypatch.setattr(
            svc, "_verificar_espaco_sync",
            lambda *a: chamou_espaco.append(1) if chamou_espaco is not None else None,
        )

    def test_sem_conn_file_nao_faz_nada(self, monkeypatch):
        monkeypatch.setattr(svc, "_ler_conn_file", lambda: None)
        chamou = []
        monkeypatch.setattr(svc, "_deve_rodar_agora_sync", lambda *a: chamou.append(1) or False)
        self._mock_checkdb_e_espaco(monkeypatch)
        svc._ciclo_manutencao_sync()
        assert chamou == []

    def test_nao_dispara_manutencao_fora_da_janela(self, monkeypatch):
        monkeypatch.setattr(svc, "_ler_conn_file", lambda: ("srv", "bd"))
        monkeypatch.setattr(svc, "_deve_rodar_agora_sync", lambda *a: False)
        chamou = []
        monkeypatch.setattr(svc, "_rodar_manutencao_sync", lambda *a, **k: chamou.append(1))
        self._mock_checkdb_e_espaco(monkeypatch)
        svc._ciclo_manutencao_sync()
        assert chamou == []

    def test_dispara_quando_e_a_hora(self, monkeypatch):
        monkeypatch.setattr(svc, "_ler_conn_file", lambda: ("srv", "bd"))
        monkeypatch.setattr(svc, "_deve_rodar_agora_sync", lambda *a: True)
        monkeypatch.setattr(svc, "_ler_orcamento_minutos_sync", lambda *a: 45)
        chamou = []
        monkeypatch.setattr(svc, "_rodar_manutencao_sync", lambda *a, **k: chamou.append((a, k)))
        self._mock_checkdb_e_espaco(monkeypatch)
        svc._ciclo_manutencao_sync()
        assert chamou == [(("srv", "bd"), {"orcamento_minutos": 45})]

    def test_dispara_checkdb_quando_e_a_hora(self, monkeypatch):
        monkeypatch.setattr(svc, "_ler_conn_file", lambda: ("srv", "bd"))
        monkeypatch.setattr(svc, "_deve_rodar_agora_sync", lambda *a: False)
        monkeypatch.setattr(svc, "_deve_rodar_checkdb_agora_sync", lambda *a: True)
        monkeypatch.setattr(svc, "_verificar_espaco_sync", lambda *a: None)
        chamou = []
        monkeypatch.setattr(svc, "_rodar_checkdb_sync", lambda *a: chamou.append(a))
        svc._ciclo_manutencao_sync()
        assert chamou == [("srv", "bd")]

    def test_verifica_espaco_todo_ciclo_independente_de_janela(self, monkeypatch):
        monkeypatch.setattr(svc, "_ler_conn_file", lambda: ("srv", "bd"))
        monkeypatch.setattr(svc, "_deve_rodar_agora_sync", lambda *a: False)
        monkeypatch.setattr(svc, "_deve_rodar_checkdb_agora_sync", lambda *a: False)
        chamou = []
        monkeypatch.setattr(svc, "_verificar_espaco_sync", lambda *a: chamou.append(a))
        svc._ciclo_manutencao_sync()
        assert chamou == [("srv", "bd")]


class TestAvaliarJanela:
    """Motor de janela compartilhado (índices e CHECKDB) — cobertura
    direta, complementa os testes de `_deve_rodar_agora_sync` acima que já
    cobrem o caminho via `_open_conn`."""

    def test_desativado_nunca_roda(self):
        agora = _agora_no_dia_e_hora(3, "03:20")
        assert svc._avaliar_janela(False, "0,1,2,3,4,5,6", "03:00", None, agora) is False

    def test_fora_do_dia_nao_roda(self):
        agora = _agora_no_dia_e_hora(0, "03:00")
        assert svc._avaliar_janela(True, "1,2,3,4,5", "03:00", None, agora) is False

    def test_dentro_da_janela_roda(self):
        agora = _agora_no_dia_e_hora(3, "03:20")
        assert svc._avaliar_janela(True, "0,1,2,3,4,5,6", "03:00", None, agora) is True

    def test_ja_rodou_hoje_nao_roda_de_novo(self):
        agora = _agora_no_dia_e_hora(3, "03:20")
        assert svc._avaliar_janela(True, "0,1,2,3,4,5,6", "03:00", agora.replace(hour=3, minute=0), agora) is False


class TestDeveRodarCheckdbAgoraSync:
    def test_usa_config_propria_checkdb(self, monkeypatch):
        cur = FakeCursor(one=[{
            "checkdb_ativo": True, "checkdb_dias_semana": "0",  # só domingo
            "checkdb_hora": "04:00", "checkdb_ultima_execucao": None,
        }])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        agora = _agora_no_dia_e_hora(0, "04:10")
        assert svc._deve_rodar_checkdb_agora_sync("srv", "bd", agora=agora) is True

    def test_desligado_nao_roda(self, monkeypatch):
        cur = FakeCursor(one=[{
            "checkdb_ativo": False, "checkdb_dias_semana": "0,1,2,3,4,5,6",
            "checkdb_hora": "04:00", "checkdb_ultima_execucao": None,
        }])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        agora = _agora_no_dia_e_hora(0, "04:10")
        assert svc._deve_rodar_checkdb_agora_sync("srv", "bd", agora=agora) is False


class TestRodarCheckdbSync:
    def test_sucesso_sem_erro_de_integridade(self, monkeypatch):
        class CursorCheckdb(FakeCursor):
            def nextset(self):
                return False

        cur = CursorCheckdb()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        gravados = []
        monkeypatch.setattr(svc, "_gravar_resultado_checkdb_sync", lambda *a: gravados.append(a))
        r = svc._rodar_checkdb_sync("srv", "bd")
        assert r["success"] is True
        assert "Nenhum erro" in r["resumo"]
        assert any("DBCC CHECKDB" in q for q in cur.queries)
        assert gravados

    def test_falha_de_integridade_reportada_sem_propagar(self, monkeypatch):
        class CursorFalha(FakeCursor):
            def execute(self, q, p=None):
                self.queries.append(q)
                if "DBCC" in q:
                    raise RuntimeError("Msg 8909: pagina corrompida")

        cur = CursorFalha()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        gravados = []
        monkeypatch.setattr(svc, "_gravar_resultado_checkdb_sync", lambda *a: gravados.append(a))
        r = svc._rodar_checkdb_sync("srv", "bd")
        assert r["success"] is False
        assert "possível problema de integridade" in r["resumo"]
        assert "pagina corrompida" in r["resumo"]

    def test_falha_de_conexao_nao_propaga(self, monkeypatch):
        def _falha(*a, **k):
            raise ConnectionError("Falha conexão")
        monkeypatch.setattr(svc, "_open_conn", _falha)
        gravados = []
        monkeypatch.setattr(svc, "_gravar_resultado_checkdb_sync", lambda *a: gravados.append(a))
        r = svc._rodar_checkdb_sync("srv", "bd")
        assert r["success"] is False
        assert "Falha ao conectar" in r["resumo"]


class TestOrcamentoTempoCircuitBreaker:
    def test_para_de_iniciar_indice_novo_apos_orcamento_esgotado(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"tabela": "os", "indice": "os_1", "frag": 90.0, "page_count": 500},
            {"tabela": "os", "indice": "os_2", "frag": 90.0, "page_count": 500},
            {"tabela": "os", "indice": "os_3", "frag": 90.0, "page_count": 500},
        ]])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_gravar_resultado_sync", lambda *a: None)

        # Relógio falso: t0, depois "ainda dentro" pro 1º índice (checagem
        # de i=0), depois "estourou o orçamento" na checagem de i=1 — daí
        # em diante qualquer nova chamada (inclusive o cálculo final de
        # duração) already reflete o tempo estourado. Simula o tempo
        # passando sem precisar de sleep real.
        base = datetime(2026, 1, 1, 3, 0, 0)
        tempos = iter([base, base, base + timedelta(minutes=999)])
        def _clock():
            try:
                return next(tempos)
            except StopIteration:
                return base + timedelta(minutes=999)

        r = svc._rodar_manutencao_sync("srv", "bd", orcamento_minutos=10, _clock=_clock)
        rebuild = [q for q in cur.queries if "REBUILD" in q]
        assert len(rebuild) == 1 and "os_1" in rebuild[0]
        assert "adiado(s) por orçamento" in r["resumo"]

    def test_orcamento_generoso_processa_tudo(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"tabela": "os", "indice": "os_1", "frag": 90.0, "page_count": 500},
            {"tabela": "os", "indice": "os_2", "frag": 90.0, "page_count": 500},
        ]])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_gravar_resultado_sync", lambda *a: None)
        r = svc._rodar_manutencao_sync("srv", "bd", orcamento_minutos=120)
        rebuild = [q for q in cur.queries if "REBUILD" in q]
        assert len(rebuild) == 2
        assert "adiado" not in r["resumo"]


class TestGravarComRetry:
    """Achado ao vivo 2026-08-31 (teste real contra BD_PAJE): a conexão
    pra gravar o resultado às vezes falha logo depois de um lote pesado
    de REBUILD — 1 retry curto cobre esse hiccup transitório."""

    def test_sucesso_na_segunda_tentativa(self, monkeypatch):
        monkeypatch.setattr(svc.time_module, "sleep", lambda *a: None)  # nunca dormir de verdade em teste
        tentativas = {"n": 0}

        def _open_conn_flaky(*a, **k):
            tentativas["n"] += 1
            if tentativas["n"] == 1:
                raise ConnectionError("Adaptive Server connection timed out")
            return FakeConn(FakeCursor(one=[{"codigo": 1}]))

        monkeypatch.setattr(svc, "_open_conn", _open_conn_flaky)
        svc._gravar_com_retry("srv", "bd", "manutencao_indices_ultima_execucao", "manutencao_indices_ultimo_resultado", "ok", "teste")
        assert tentativas["n"] == 2

    def test_loga_aviso_quando_as_duas_tentativas_falham(self, monkeypatch, caplog):
        monkeypatch.setattr(svc.time_module, "sleep", lambda *a: None)

        def _falha(*a, **k):
            raise ConnectionError("boom")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        svc._gravar_com_retry("srv", "bd", "checkdb_ultima_execucao", "checkdb_ultimo_resultado", "ok", "teste")
        # não propaga exceção — o teste passar sem levantar já comprova
        # o comportamento; conferimos também que o aviso foi emitido.
        assert any("Falha ao gravar resultado" in r.message for r in caplog.records)


class TestListarIndicesNaoUsadosSync:
    def test_devolve_lista(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"tabela": "os", "indice": "os_1", "paginas": 762},
            {"tabela": "cliente", "indice": "cliente_3", "paginas": 847},
        ]])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        r = svc._listar_indices_nao_usados_sync("srv", "bd")
        assert r["success"] is True
        assert len(r["indices"]) == 2

    def test_falha_conexao(self, monkeypatch):
        def _falha(*a, **k):
            raise ConnectionError("boom")
        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._listar_indices_nao_usados_sync("srv", "bd")
        assert r["success"] is False


class TestVerificarEspacoSync:
    def test_express_acima_do_limiar_gera_alerta(self, monkeypatch):
        cur = FakeCursor(one=[{"edicao": 4}, {"mb": 8500.0}, {"codigo": 1}])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        r = svc._verificar_espaco_sync("srv", "bd")
        assert r["success"] is True
        assert r["express"] is True
        assert r["pct_usado"] == pytest.approx(83.0, abs=0.1)
        assert r["alerta"] is True
        assert any("UPDATE servico_sistema_atualizacao SET espaco_pct_usado" in q for q in cur.queries)

    def test_express_abaixo_do_limiar_sem_alerta(self, monkeypatch):
        cur = FakeCursor(one=[{"edicao": 4}, {"mb": 1024.0}, {"codigo": 1}])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        r = svc._verificar_espaco_sync("srv", "bd")
        assert r["alerta"] is False

    def test_edicao_nao_express_nunca_alerta(self, monkeypatch):
        cur = FakeCursor(one=[{"edicao": 3}, {"mb": 999999.0}])  # Standard, sem teto de 10GB
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        r = svc._verificar_espaco_sync("srv", "bd")
        assert r["express"] is False
        assert r["pct_usado"] is None
        assert r["alerta"] is False

    def test_falha_conexao_nao_propaga(self, monkeypatch):
        def _falha(*a, **k):
            raise ConnectionError("boom")
        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._verificar_espaco_sync("srv", "bd")
        assert r["success"] is False

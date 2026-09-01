"""Testes unitários de Serviço do Sistema > aba "Atualização"
(services/servico_sistema_service.py) — config (get/save), status pro
badge, disparo de aplicar/reverter (subprocess sempre mockado, nunca
dispara PowerShell de verdade em teste unitário) e o ciclo do loop de
fundo."""
import json
from datetime import datetime

import services.servico_sistema_service as svc


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


class TestEnsureTable:
    def test_cria_tabela_idempotente(self):
        queries = []

        class Cur:
            def execute(self, q, p=None):
                queries.append(q)

        svc._ensure_servico_sistema_atualizacao_table(Cur())
        # 16 statements: CREATE TABLE (idempotente, instalação nova) + ALTER
        # TABLE ADD canal + cel_suporte + as 5 colunas de manutenção de
        # índices (2026-08-28) + as 8 colunas da extensão 2026-08-31
        # (orçamento de tempo, CHECKDB, espaço vs. teto Express) —
        # idempotentes, cobrem instalação já existente sem as colunas novas.
        assert len(queries) == 16
        assert "servico_sistema_atualizacao" in queries[0]
        assert "IF NOT EXISTS" in queries[0]


class TestGetConfig:
    def test_sem_linha_devolve_padrao(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_config_sync("srv", "bd")
        assert r["success"] is True
        assert r["dados"]["manifest_url"] == ""
        assert r["dados"]["intervalo_minutos"] == 30
        assert r["dados"]["commit_pendente"] is None

    def test_com_linha_devolve_dados_reais(self, monkeypatch):
        row = {
            "manifest_url": "https://x.blob.core.windows.net/releases/manifest.json?sv=1",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 45,
            "commit_atual": "aaa1111",
            "commit_anterior": None,
            "commit_pendente": None,
            "pendente_desde": None,
            "ultima_verificacao": None,
            "ultimo_erro": None,
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_config_sync("srv", "bd")
        assert r["success"] is True
        assert r["dados"]["intervalo_minutos"] == 45
        assert r["dados"]["commit_atual"] == "aaa1111"

    def test_falha_conexao(self, monkeypatch):
        def boom(*a, **k):
            raise Exception("timeout")
        monkeypatch.setattr(svc, "_open_conn", boom)
        r = svc._get_config_sync("srv", "bd")
        assert r["success"] is False
        assert "Falha conexão" in r["message"]


class TestSaveConfig:
    def test_rejeita_intervalo_abaixo_do_minimo(self, monkeypatch):
        r = svc._save_config_sync("srv", "bd", {"intervalo_minutos": 2})
        assert r["success"] is False
        assert "mínimo" in r["message"]

    def test_aceita_zero_como_desligado(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "updater_conn.json")
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 0,
        })
        assert r["success"] is True

    def test_rejeita_negativo(self, monkeypatch):
        r = svc._save_config_sync("srv", "bd", {"intervalo_minutos": -1})
        assert r["success"] is False

    def test_insere_quando_nao_existe_linha(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "updater_conn.json")
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 30,
        })
        assert r["success"] is True
        insert_q = [q for q, p in cur.queries if q.strip().upper().startswith("INSERT")]
        assert len(insert_q) == 1
        conn_file = svc._CONN_FILE
        assert json.loads(conn_file.read_text(encoding="utf-8")) == {"servidor": "srv", "banco": "bd"}

    def test_rejeita_canal_invalido(self, monkeypatch):
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 30,
            "canal": "X",
        })
        assert r["success"] is False
        assert "Canal" in r["message"]

    def test_grava_canal_producao(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "updater_conn.json")
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 30,
            "canal": "p",  # minúsculo — normalizado pra 'P'
        })
        assert r["success"] is True
        insert_params = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT")][0]
        assert insert_params[4] == "P"  # canal — índice fixo, não mais o penúltimo (colunas de manutenção de índices vieram depois)

    def test_canal_ausente_default_homologacao(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "updater_conn.json")
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 30,
        })
        assert r["success"] is True
        insert_params = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT")][0]
        assert insert_params[4] == "H"  # canal — índice fixo, ver comentário acima

    def test_atualiza_quando_ja_existe_linha(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[{"codigo": 1}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "updater_conn.json")
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 60,
        })
        assert r["success"] is True
        update_q = [q for q, p in cur.queries if q.strip().upper().startswith("UPDATE")]
        assert len(update_q) == 1

    def test_orcamento_e_checkdb_default_seguro_quando_ausentes(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "updater_conn.json")
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 30,
        })
        assert r["success"] is True
        insert_params = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT")][0]
        # ordem: manifest,pasta_backend,pasta_frontend,intervalo,canal,cel_suporte,
        # manut_ativo,manut_dias,manut_hora,orcamento,checkdb_ativo,checkdb_dias,checkdb_hora
        assert insert_params[9] == 120
        assert insert_params[10] is True
        assert insert_params[11] == "0"
        assert insert_params[12] == "04:00"

    def test_grava_orcamento_e_checkdb_configurados(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "updater_conn.json")
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 30,
            "manutencao_indices_orcamento_minutos": 45,
            "checkdb_ativo": False,
            "checkdb_dias_semana": "0,3",
            "checkdb_hora": "05:30",
        })
        assert r["success"] is True
        insert_params = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT")][0]
        assert insert_params[9] == 45
        assert insert_params[10] is False
        assert insert_params[11] == "0,3"
        assert insert_params[12] == "05:30"

    def test_orcamento_invalido_cai_no_default(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "updater_conn.json")
        r = svc._save_config_sync("srv", "bd", {
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 30,
            "manutencao_indices_orcamento_minutos": "abc",
        })
        assert r["success"] is True
        insert_params = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT")][0]
        assert insert_params[9] == 120


class TestGetStatus:
    def test_pendente_true_quando_ha_commit_pendente(self, monkeypatch):
        cur = FakeCursor(one=[{"commit_pendente": "bbb2222", "canal": "P"}])
        _patch(monkeypatch, cur)
        r = svc._get_status_sync("srv", "bd")
        assert r == {"success": True, "pendente": True, "canal": "P"}

    def test_pendente_false_sem_linha(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_status_sync("srv", "bd")
        assert r == {"success": True, "pendente": False, "canal": "H"}


class TestAplicarAtualizacao:
    def test_sem_pendente_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{
            "manifest_url": "u", "pasta_backend": "b", "pasta_frontend": "f",
            "intervalo_minutos": 30, "commit_atual": "a", "commit_anterior": None,
            "commit_pendente": None, "pendente_desde": None, "ultima_verificacao": None, "ultimo_erro": None,
        }])
        _patch(monkeypatch, cur)
        r = svc._aplicar_atualizacao_sync("srv", "bd")
        assert r["success"] is False
        assert "pendente" in r["message"].lower()

    def test_com_pendente_dispara_processo(self, monkeypatch):
        cur = FakeCursor(one=[{
            "manifest_url": "u", "pasta_backend": "b", "pasta_frontend": "f",
            "intervalo_minutos": 30, "commit_atual": "a", "commit_anterior": None,
            "commit_pendente": "novo123", "pendente_desde": None, "ultima_verificacao": None, "ultimo_erro": None,
        }])
        _patch(monkeypatch, cur)
        chamadas = []
        monkeypatch.setattr(svc, "_escrever_config_ps1", lambda dados: chamadas.append(("escrever", dados)))
        monkeypatch.setattr(svc, "_disparar_ps1_detached", lambda modo: chamadas.append(("disparar", modo)))
        r = svc._aplicar_atualizacao_sync("srv", "bd")
        assert r["success"] is True
        assert ("disparar", "ApplyPending") in chamadas


class TestReverterAtualizacao:
    def test_sem_anterior_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{
            "manifest_url": "u", "pasta_backend": "b", "pasta_frontend": "f",
            "intervalo_minutos": 30, "commit_atual": "a", "commit_anterior": None,
            "commit_pendente": None, "pendente_desde": None, "ultima_verificacao": None, "ultimo_erro": None,
        }])
        _patch(monkeypatch, cur)
        r = svc._reverter_atualizacao_sync("srv", "bd")
        assert r["success"] is False
        assert "anterior" in r["message"].lower()

    def test_com_anterior_dispara_rollback(self, monkeypatch):
        cur = FakeCursor(one=[{
            "manifest_url": "u", "pasta_backend": "b", "pasta_frontend": "f",
            "intervalo_minutos": 30, "commit_atual": "a", "commit_anterior": "velho000",
            "commit_pendente": None, "pendente_desde": None, "ultima_verificacao": None, "ultimo_erro": None,
        }])
        _patch(monkeypatch, cur)
        chamadas = []
        monkeypatch.setattr(svc, "_escrever_config_ps1", lambda dados: chamadas.append(("escrever", dados)))
        monkeypatch.setattr(svc, "_disparar_ps1_detached", lambda modo: chamadas.append(("disparar", modo)))
        r = svc._reverter_atualizacao_sync("srv", "bd")
        assert r["success"] is True
        assert ("disparar", "Rollback") in chamadas


class TestLerPendingCommit:
    def test_le_state_json_com_bom_utf8(self, monkeypatch, tmp_path):
        # `apply_update.ps1` grava state.json via `Set-Content -Encoding
        # UTF8` — no Windows PowerShell 5.1 isso sempre inclui um BOM.
        # Bug real 2026-08-26: lendo com "utf-8" puro (não "utf-8-sig"),
        # o BOM quebrava o json.loads e a exceção era engolida em
        # silêncio, escondendo um commit pendente real.
        state_file = tmp_path / "state.json"
        bom = b"\xef\xbb\xbf"
        state_file.write_bytes(bom + json.dumps({"pendingCommit": "abc1234"}).encode("utf-8"))
        monkeypatch.setattr(svc, "_UPDATER_STATE_PATH", state_file)
        assert svc._ler_pending_commit() == "abc1234"

    def test_le_state_json_sem_bom(self, monkeypatch, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"pendingCommit": "def5678"}), encoding="utf-8")
        monkeypatch.setattr(svc, "_UPDATER_STATE_PATH", state_file)
        assert svc._ler_pending_commit() == "def5678"

    def test_sem_arquivo_devolve_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(svc, "_UPDATER_STATE_PATH", tmp_path / "nao-existe.json")
        assert svc._ler_pending_commit() is None


class TestVerificarAgora:
    def test_config_incompleta_bloqueia(self, monkeypatch):
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: {"success": True, "dados": dict(svc._CONFIG_PADRAO)})
        r = svc._verificar_agora_sync("srv", "bd")
        assert r["success"] is False
        assert "Configure" in r["message"]

    def test_ignora_intervalo_e_ultima_verificacao(self, monkeypatch):
        # Mesmo com intervalo=0 (desligado) e verificação recente, o botão
        # manual sempre dispara a checagem — só o ciclo automático respeita
        # esse gate.
        dados = dict(svc._CONFIG_PADRAO)
        dados.update({
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 0,
            "ultima_verificacao": datetime.now().isoformat(),
        })
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: {"success": True, "dados": dados})
        chamadas = []
        monkeypatch.setattr(
            svc, "_executar_verificacao_download_sync",
            lambda servidor, banco, d: (chamadas.append(1), {"success": True, "message": "ok", "pendente": False})[1],
        )
        r = svc._verificar_agora_sync("srv", "bd")
        assert r["success"] is True
        assert len(chamadas) == 1


class TestCicloVerificacao:
    def test_intervalo_zero_desliga_verificacao_automatica(self, monkeypatch, tmp_path):
        conn_file = tmp_path / "updater_conn.json"
        conn_file.write_text(json.dumps({"servidor": "srv", "banco": "bd"}), encoding="utf-8")
        monkeypatch.setattr(svc, "_CONN_FILE", conn_file)
        dados = dict(svc._CONFIG_PADRAO)
        dados.update({
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "intervalo_minutos": 0,
        })
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: {"success": True, "dados": dados})
        chamado = []
        monkeypatch.setattr(svc, "_executar_verificacao_download_sync", lambda *a: chamado.append(1))
        svc._ciclo_verificacao_sync()
        assert chamado == []

    def test_sem_conn_file_nao_faz_nada(self, monkeypatch, tmp_path):
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "nao-existe.json")
        chamado = []
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: chamado.append(1))
        svc._ciclo_verificacao_sync()
        assert chamado == []

    def test_config_incompleta_nao_verifica(self, monkeypatch, tmp_path):
        conn_file = tmp_path / "updater_conn.json"
        conn_file.write_text(json.dumps({"servidor": "srv", "banco": "bd"}), encoding="utf-8")
        monkeypatch.setattr(svc, "_CONN_FILE", conn_file)
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: {"success": True, "dados": dict(svc._CONFIG_PADRAO)})
        chamado = []
        monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: chamado.append(1))
        svc._ciclo_verificacao_sync()
        assert chamado == []

    def test_config_completa_e_no_prazo_dispara_download(self, monkeypatch, tmp_path):
        conn_file = tmp_path / "updater_conn.json"
        conn_file.write_text(json.dumps({"servidor": "srv", "banco": "bd"}), encoding="utf-8")
        monkeypatch.setattr(svc, "_CONN_FILE", conn_file)
        dados = dict(svc._CONFIG_PADRAO)
        dados.update({
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
            "ultima_verificacao": None,
        })
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: {"success": True, "dados": dados})
        monkeypatch.setattr(svc, "_escrever_config_ps1", lambda d: None)

        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""
        chamadas = []
        monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: (chamadas.append(a) or FakeResult()))
        monkeypatch.setattr(svc, "_ler_pending_commit", lambda: "novo999")
        atualizados = []
        monkeypatch.setattr(
            svc, "_atualizar_status_pos_verificacao_sync",
            lambda servidor, banco, commit_pendente, erro: atualizados.append((commit_pendente, erro)),
        )
        svc._ciclo_verificacao_sync()
        assert len(chamadas) == 1
        assert atualizados == [("novo999", None)]

    def test_erro_no_processo_nunca_derruba_nem_propaga(self, monkeypatch, tmp_path):
        conn_file = tmp_path / "updater_conn.json"
        conn_file.write_text(json.dumps({"servidor": "srv", "banco": "bd"}), encoding="utf-8")
        monkeypatch.setattr(svc, "_CONN_FILE", conn_file)
        dados = dict(svc._CONFIG_PADRAO)
        dados.update({
            "manifest_url": "https://x/manifest.json?sig=abc",
            "pasta_backend": "C:\\BackOn\\current-backend",
            "pasta_frontend": "C:\\BackOn\\current-frontend",
        })
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: {"success": True, "dados": dados})
        monkeypatch.setattr(svc, "_escrever_config_ps1", lambda d: None)

        def boom(*a, **k):
            raise Exception("powershell sumiu")
        monkeypatch.setattr(svc.subprocess, "run", boom)
        atualizados = []
        monkeypatch.setattr(
            svc, "_atualizar_status_pos_verificacao_sync",
            lambda servidor, banco, commit_pendente, erro: atualizados.append((commit_pendente, erro)),
        )
        svc._ciclo_verificacao_sync()  # não deve levantar
        assert atualizados[0][0] is None
        assert "powershell sumiu" in atualizados[0][1]

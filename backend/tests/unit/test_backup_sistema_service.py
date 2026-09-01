"""Testes unitários de `services/backup_sistema_service.py` — pedido
explícito do usuário (2026-08-28): backup programado (dias/hora/
intervalo) com destino Local ou Blob, log registrado e consultável."""
from datetime import datetime, timedelta

import services.backup_sistema_service as svc


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
        self.autocommit_calls = []

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def autocommit(self, status):
        self.autocommit_calls.append(status)

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _agora_no_dia_e_hora(dia_projeto: int, hora: str) -> datetime:
    base = datetime(2026, 8, 30)  # domingo => dia_projeto=0
    h, m = (int(x) for x in hora.split(":"))
    for delta in range(7):
        candidata = base + timedelta(days=delta)
        if (candidata.weekday() + 1) % 7 == dia_projeto:
            return candidata.replace(hour=h, minute=m)
    raise AssertionError("dia_projeto inválido")


class TestSaveConfig:
    def test_bloqueia_local_sem_pasta_quando_ativo(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_config_sync("srv", "bd", {"ativo": True, "destino": "LOCAL", "pasta_local": ""})
        assert r["success"] is False
        assert "pasta" in r["message"].lower()

    def test_permite_desativado_sem_pasta(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_config_sync("srv", "bd", {"ativo": False, "destino": "LOCAL", "pasta_local": ""})
        assert r["success"] is True

    def test_intervalo_fora_do_range_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_config_sync("srv", "bd", {"intervalo_horas": 200})
        assert r["success"] is False

    def test_destino_invalido_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_config_sync("srv", "bd", {"destino": "FTP"})
        assert r["success"] is False

    def test_grava_valores_validos(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_config_sync("srv", "bd", {
            "ativo": True, "dias_semana": "1,3,5", "hora_inicio": "22:30", "intervalo_horas": 6,
            "destino": "BLOB", "blob_container": "meu-container", "retencao_dias": 15,
        })
        assert r["success"] is True
        insert_params = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT")][0]
        assert insert_params == (True, "1,3,5", "22:30", 6, "BLOB", "", "meu-container", 15)


class TestDeveRodarAgoraSync:
    def test_desativado_nunca_roda(self, monkeypatch):
        cur = FakeCursor(one=[{
            "ativo": False, "dias_semana": "0,1,2,3,4,5,6", "hora_inicio": "02:00",
            "intervalo_horas": 24, "destino": "LOCAL", "pasta_local": "C:\\bkp", "blob_container": "x",
            "retencao_dias": 30, "ultima_execucao": None, "ultimo_resultado": None,
        }])
        _patch(monkeypatch, cur)
        assert svc._deve_rodar_agora_sync("srv", "bd") is False

    def test_antes_da_hora_de_inicio_nao_roda(self, monkeypatch):
        cur = FakeCursor(one=[{
            "ativo": True, "dias_semana": "0,1,2,3,4,5,6", "hora_inicio": "22:00",
            "intervalo_horas": 6, "destino": "LOCAL", "pasta_local": "C:\\bkp", "blob_container": "x",
            "retencao_dias": 30, "ultima_execucao": None, "ultimo_resultado": None,
        }])
        _patch(monkeypatch, cur)
        agora = _agora_no_dia_e_hora(3, "10:00")  # antes das 22h
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is False

    def test_primeira_vez_apos_hora_inicio_roda(self, monkeypatch):
        cur = FakeCursor(one=[{
            "ativo": True, "dias_semana": "0,1,2,3,4,5,6", "hora_inicio": "02:00",
            "intervalo_horas": 6, "destino": "LOCAL", "pasta_local": "C:\\bkp", "blob_container": "x",
            "retencao_dias": 30, "ultima_execucao": None, "ultimo_resultado": None,
        }])
        _patch(monkeypatch, cur)
        agora = _agora_no_dia_e_hora(3, "02:05")
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is True

    def test_dentro_do_intervalo_desde_a_ultima_nao_roda(self, monkeypatch):
        agora = _agora_no_dia_e_hora(3, "08:00")
        cur = FakeCursor(one=[{
            "ativo": True, "dias_semana": "0,1,2,3,4,5,6", "hora_inicio": "02:00",
            "intervalo_horas": 6, "destino": "LOCAL", "pasta_local": "C:\\bkp", "blob_container": "x",
            "retencao_dias": 30, "ultima_execucao": agora - timedelta(hours=2), "ultimo_resultado": "ok",
        }])
        _patch(monkeypatch, cur)
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is False

    def test_apos_intervalo_desde_a_ultima_roda_de_novo(self, monkeypatch):
        agora = _agora_no_dia_e_hora(3, "10:00")
        cur = FakeCursor(one=[{
            "ativo": True, "dias_semana": "0,1,2,3,4,5,6", "hora_inicio": "02:00",
            "intervalo_horas": 6, "destino": "LOCAL", "pasta_local": "C:\\bkp", "blob_container": "x",
            "retencao_dias": 30, "ultima_execucao": agora - timedelta(hours=7), "ultimo_resultado": "ok",
        }])
        _patch(monkeypatch, cur)
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is True

    def test_fora_do_dia_configurado_nao_roda(self, monkeypatch):
        cur = FakeCursor(one=[{
            "ativo": True, "dias_semana": "1,2,3,4,5", "hora_inicio": "02:00",  # seg-sex
            "intervalo_horas": 24, "destino": "LOCAL", "pasta_local": "C:\\bkp", "blob_container": "x",
            "retencao_dias": 30, "ultima_execucao": None, "ultimo_resultado": None,
        }])
        _patch(monkeypatch, cur)
        agora = _agora_no_dia_e_hora(0, "10:00")  # domingo
        assert svc._deve_rodar_agora_sync("srv", "bd", agora=agora) is False


class TestRodarBackupSync:
    def test_local_sucesso_registra_log(self, monkeypatch):
        cfg = {"success": True, "dados": {
            "destino": "LOCAL", "pasta_local": "C:\\bkp", "retencao_dias": 30,
        }}
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: cfg)
        cur = FakeCursor(many=[[{"mb": 12.5}]])
        conn = _patch(monkeypatch, cur)
        logs = []
        monkeypatch.setattr(svc, "_registrar_log_sync", lambda *a, **k: logs.append(k))
        r = svc._rodar_backup_sync("srv", "bd")
        assert r["success"] is True
        backup_q = [q for q, p in cur.queries if q.strip().upper().startswith("BACKUP DATABASE")][0]
        assert "TO DISK" in backup_q and "C:\\bkp" in backup_q
        assert any(q.strip().upper().startswith("EXEC MASTER.DBO.XP_DELETE_FILE") for q, p in cur.queries)
        assert logs[0]["sucesso"] is True
        assert conn.autocommit_calls == [True, False]

    def test_local_sem_pasta_falha_registrada(self, monkeypatch):
        cfg = {"success": True, "dados": {"destino": "LOCAL", "pasta_local": "", "retencao_dias": 30}}
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: cfg)
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        logs = []
        monkeypatch.setattr(svc, "_registrar_log_sync", lambda *a, **k: logs.append(k))
        r = svc._rodar_backup_sync("srv", "bd")
        assert r["success"] is False
        assert logs[0]["sucesso"] is False

    def test_falha_de_conexao_registra_log_sem_propagar(self, monkeypatch):
        cfg = {"success": True, "dados": {"destino": "LOCAL", "pasta_local": "C:\\bkp", "retencao_dias": 30}}
        monkeypatch.setattr(svc, "_get_config_sync", lambda *a: cfg)

        def _falha(*a, **k):
            raise ConnectionError("Falha conexão")
        monkeypatch.setattr(svc, "_open_conn", _falha)
        logs = []
        monkeypatch.setattr(svc, "_registrar_log_sync", lambda *a, **k: logs.append(k))
        r = svc._rodar_backup_sync("srv", "bd")
        assert r["success"] is False
        assert "Falha ao conectar" in logs[0]["mensagem"]


class TestSasDaConnectionString:
    def test_extrai_account_name_e_key(self):
        conn_str = "DefaultEndpointsProtocol=https;AccountName=sys1;AccountKey=abc123==;EndpointSuffix=core.windows.net"
        nome, chave = svc._sas_da_connection_string(conn_str)
        assert nome == "sys1"
        assert chave == "abc123=="

    def test_faltando_campo_levanta_erro(self):
        import pytest
        with pytest.raises(ValueError):
            svc._sas_da_connection_string("AccountName=sys1")


class TestCicloBackupSync:
    def test_sem_conn_file_nao_faz_nada(self, monkeypatch, tmp_path):
        monkeypatch.setattr(svc, "_CONN_FILE", tmp_path / "nao_existe.json")
        chamou = []
        monkeypatch.setattr(svc, "_deve_rodar_agora_sync", lambda *a: chamou.append(1) or False)
        svc._ciclo_backup_sync()
        assert chamou == []

    def test_dispara_quando_e_a_hora(self, monkeypatch, tmp_path):
        conn_file = tmp_path / "updater_conn.json"
        conn_file.write_text('{"servidor": "srv", "banco": "bd"}', encoding="utf-8")
        monkeypatch.setattr(svc, "_CONN_FILE", conn_file)
        monkeypatch.setattr(svc, "_deve_rodar_agora_sync", lambda *a: True)
        chamou = []
        monkeypatch.setattr(svc, "_rodar_backup_sync", lambda *a: chamou.append(a))
        svc._ciclo_backup_sync()
        assert chamou == [("srv", "bd")]

"""Testes UNITÁRIOS de Módulos e Recursos (controle_configuracao).

Mesmo padrão de test_combustivel_meta_service.py: cursor/conexão falsos
(monkeypatch em _open_conn), sem banco real. Cobre só a regra nova
(2026-07-15, user-directed [GLOBAL]): Bar/Cilindro/Pedido de Venda são
segmentos mutuamente exclusivos do mesmo Pedido de Venda.
"""
import services.controle_config_service as svc


class FakeCursor:
    def __init__(self):
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

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


def _patch(monkeypatch):
    cur = FakeCursor()
    conn = FakeConn(cur)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn, cur


def test_save_rejects_two_segmentos_pedido_ligados(monkeypatch):
    conn, cur = _patch(monkeypatch)
    valores = {"Bar": True, "Cilindro": True, "Pedido_venda": False}
    r = svc._save_config_sync("srv", "bd", valores)
    assert r["success"] is False
    assert "só um pode ficar ativo" in r["message"]
    assert not conn.committed
    assert cur.queries == []


def test_save_rejects_all_tres_segmentos_ligados(monkeypatch):
    conn, cur = _patch(monkeypatch)
    valores = {"Bar": True, "Cilindro": True, "Pedido_venda": True}
    r = svc._save_config_sync("srv", "bd", valores)
    assert r["success"] is False
    assert not conn.committed


def test_save_allows_um_segmento_pedido_ligado(monkeypatch):
    conn, cur = _patch(monkeypatch)
    valores = {"Bar": False, "Cilindro": True, "Pedido_venda": False, "Clientes": True}
    r = svc._save_config_sync("srv", "bd", valores)
    assert r["success"] is True
    assert conn.committed


def test_save_allows_nenhum_segmento_pedido_ligado(monkeypatch):
    conn, cur = _patch(monkeypatch)
    valores = {"Bar": False, "Cilindro": False, "Pedido_venda": False}
    r = svc._save_config_sync("srv", "bd", valores)
    assert r["success"] is True
    assert conn.committed


def test_save_ignora_campos_desconhecidos(monkeypatch):
    conn, cur = _patch(monkeypatch)
    valores = {"campo_inexistente": True}
    r = svc._save_config_sync("srv", "bd", valores)
    assert r["success"] is False
    assert "Nenhum campo válido" in r["message"]

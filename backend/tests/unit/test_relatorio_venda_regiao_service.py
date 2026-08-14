"""Testes unitários de Venda por Região/Segmento — réplica de
`Guerengases\\FrmVenTot.frm`, generalização do query-builder dinâmico do
legado pra agregação fixa + reagrupamento em Python (ver docstring do
service pro raciocínio completo)."""
import services.relatorio_venda_regiao_service as svc


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestValidacao:
    def test_periodo_obrigatorio(self):
        r = svc._venda_regiao_sync("srv", "bd", "", "2026-08-07", "regiao")
        assert r["success"] is False and "período" in r["message"].lower()


class TestAgrupamento:
    def _rows(self):
        return [
            {"regiao": "Norte", "segmento": "Varejo", "rota": "R1", "vendedor": "Zé", "qtd": 2.0, "valor": 20.0},
            {"regiao": "Norte", "segmento": "Atacado", "rota": "R2", "vendedor": "Maria", "qtd": 3.0, "valor": 30.0},
            {"regiao": "Sul", "segmento": "Varejo", "rota": "R1", "vendedor": "Zé", "qtd": 1.0, "valor": 10.0},
        ]

    def test_sem_dimensao_retorna_total_unico(self, monkeypatch):
        cur = FakeCursor(rows=self._rows())
        _patch(monkeypatch, cur)
        r = svc._venda_regiao_sync("srv", "bd", "2026-01-01", "2026-01-31", "")
        assert r["success"] is True
        assert len(r["itens"]) == 1
        assert r["itens"][0]["valor"] == 60.0

    def test_dimensao_regiao_agrupa_2_grupos(self, monkeypatch):
        cur = FakeCursor(rows=self._rows())
        _patch(monkeypatch, cur)
        r = svc._venda_regiao_sync("srv", "bd", "2026-01-01", "2026-01-31", "regiao")
        assert len(r["itens"]) == 2
        norte = next(i for i in r["itens"] if i["regiao"] == "Norte")
        assert norte["valor"] == 50.0

    def test_dimensao_regiao_e_segmento(self, monkeypatch):
        cur = FakeCursor(rows=self._rows())
        _patch(monkeypatch, cur)
        r = svc._venda_regiao_sync("srv", "bd", "2026-01-01", "2026-01-31", "regiao,segmento")
        assert len(r["itens"]) == 3
        assert r["dimensoes"] == ["regiao", "segmento"]

    def test_fallback_sem_dado(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"regiao": None, "segmento": None, "rota": None, "vendedor": None, "qtd": 1.0, "valor": 5.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._venda_regiao_sync("srv", "bd", "2026-01-01", "2026-01-31", "regiao,vendedor")
        assert r["itens"][0]["regiao"] == "SEM REGIÃO"
        assert r["itens"][0]["vendedor"] == "SEM VENDEDOR"

    def test_ignora_dimensao_invalida(self, monkeypatch):
        cur = FakeCursor(rows=self._rows())
        _patch(monkeypatch, cur)
        r = svc._venda_regiao_sync("srv", "bd", "2026-01-01", "2026-01-31", "regiao,invalida")
        assert r["dimensoes"] == ["regiao"]

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._venda_regiao_sync("srv", "bd", "2026-01-01", "2026-01-31", "regiao")
        assert r["itens"] == []
        assert r["totais"]["valor"] == 0.0

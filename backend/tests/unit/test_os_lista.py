"""Testes unitários de `_list_os_sync` (os_service.py) — filtros de
Técnico/Auxiliar e a restrição de visibilidade da Lista de Atendimento
(os-lista.tsx, ver AssistenciaTecnicaCampo.md), além dos campos novos
retornados por item (tecnico_nome/auxiliar_nome/checkin_em/checkout_em/
proxima_agenda). A restrição é opt-in — só ativa quando o chamador manda
`classe`+`usuario_codigo` (só `os-lista.tsx` manda; `os.tsx`/`os-form.tsx`
nunca preenchem esses campos e continuam sem restrição, comportamento
inalterado)."""
import services.os_service as svc
from models.schemas import OSListRequest


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

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _req(**over):
    base = dict(servidor="srv", banco="bd", page=1, size=20)
    base.update(over)
    return OSListRequest(**base)


_ITEM_ROW = {
    "codigo": 294, "cliente": 10, "data_entrada": None, "hora_entrada": "10:00", "situacao": "A",
    "valor_calc": 100.0, "area_atuacao": None, "cliente_nome": "Cliente X", "atendente_nome": "Ana",
    "tecnico_responsavel": 30, "tecnico_nome": "João", "auxiliar_tecnico": 55, "auxiliar_nome": "Maria",
    "checkin_em": None, "checkout_em": None, "proxima_agenda": None,
}


class TestSemRestricao:
    def test_sem_classe_nao_chama_tem_permissao(self, monkeypatch):
        """os.tsx/os-form.tsx nunca mandam classe/usuario_codigo — não deve
        haver nenhuma query extra de permissão nem restrição no WHERE."""
        cur = FakeCursor(one=[{"c": 1}], many=[[_ITEM_ROW]])
        _patch(monkeypatch, cur)
        r = svc._list_os_sync(_req())
        assert r["success"] is True
        assert len(r["items"]) == 1
        assert not any("tem_permissao" in (q or "") for q, _ in cur.queries)
        select_q = next(q for q, _ in cur.queries if q.strip().startswith("SELECT o.codigo"))
        assert "tecnico_responsavel = %s OR" not in select_q.replace("o.", "")

    def test_master_bypassa_restricao(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 1}], many=[[_ITEM_ROW]])
        _patch(monkeypatch, cur)
        r = svc._list_os_sync(_req(classe=1, usuario_codigo=99, master=True))
        assert r["success"] is True
        # Nenhuma checagem de permissão — master pula direto.
        assert cur.queries[0][0].strip().startswith("SELECT COUNT")


class TestRestricaoVisibilidade:
    def test_com_ver_todas_nao_restringe(self, monkeypatch):
        # 1ª query: tem_permissao (acha a linha -> tem a permissão).
        cur = FakeCursor(one=[{"ok": 1}, {"c": 1}], many=[[_ITEM_ROW]])
        _patch(monkeypatch, cur)
        r = svc._list_os_sync(_req(classe=1, usuario_codigo=99))
        assert r["success"] is True
        count_q, count_p = next((q, p) for q, p in cur.queries if q.strip().startswith("SELECT COUNT"))
        assert 99 not in (count_p or [])

    def test_sem_ver_todas_restringe_por_tecnico_ou_auxiliar(self, monkeypatch):
        # 1ª query: tem_permissao (não acha -> sem a permissão).
        cur = FakeCursor(one=[None, {"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_os_sync(_req(classe=1, usuario_codigo=99))
        assert r["success"] is True
        count_q, count_p = next((q, p) for q, p in cur.queries if q.strip().startswith("SELECT COUNT"))
        assert "tecnico_responsavel = %s OR o.auxiliar_tecnico = %s" in count_q
        assert count_p == [99, 99]


class TestFiltrosTecnicoAuxiliar:
    def test_filtro_tecnico(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 1}], many=[[_ITEM_ROW]])
        _patch(monkeypatch, cur)
        svc._list_os_sync(_req(tecnico=30))
        count_q, count_p = next((q, p) for q, p in cur.queries if q.strip().startswith("SELECT COUNT"))
        assert "o.tecnico_responsavel = %s" in count_q
        assert 30 in count_p

    def test_filtro_auxiliar(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 1}], many=[[_ITEM_ROW]])
        _patch(monkeypatch, cur)
        svc._list_os_sync(_req(auxiliar=55))
        count_q, count_p = next((q, p) for q, p in cur.queries if q.strip().startswith("SELECT COUNT"))
        assert "o.auxiliar_tecnico = %s" in count_q
        assert 55 in count_p


class TestCamposNovosNoItem:
    def test_item_traz_tecnico_auxiliar_checkin_checkout_agenda(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 1}], many=[[_ITEM_ROW]])
        _patch(monkeypatch, cur)
        r = svc._list_os_sync(_req())
        item = r["items"][0]
        assert item["tecnico_responsavel"] == 30
        assert item["tecnico_nome"] == "João"
        assert item["auxiliar_tecnico"] == 55
        assert item["auxiliar_nome"] == "Maria"
        assert item["checkin_em"] is None
        assert item["checkout_em"] is None
        assert item["proxima_agenda"] is None

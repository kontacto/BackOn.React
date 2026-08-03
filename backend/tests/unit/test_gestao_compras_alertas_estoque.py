"""Testes UNITÁRIOS do resumo de alertas de estoque (card na Tela Principal
p/ Gerente/Supervisor/Master, ver Controle do Sistema > aba Diversos), do
cache compartilhado (`alertas_estoque_cache` — pedido explícito do usuário,
2026-07-21: "guarde o último resultado para todos os usuários") e do filtro
"zerado_negativo" trazido a `_list_ressuprimento_sync`."""
import services.gestao_compras_service as svc
from models.pedido_compra import AtualizarAlertasEstoqueRequest


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

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


MODULO_ON = {"Curva_abc": 1}
MODULO_OFF = {"Curva_abc": 0}
TODOS_LIGADOS = {"ALERTA_ESTOQUE_MINIMO": 1, "ALERTA_ESTOQUE_RESSUPRIMENTO": 1, "ALERTA_ESTOQUE_ZERADO": 1}


class TestResumoAlertasEstoqueModuloDesligado:
    def test_modulo_desativado_nao_conta_nada(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        _patch(monkeypatch, cur)
        r = svc._resumo_alertas_estoque_sync("srv", "bd")
        assert r["success"] is True
        assert r["ativo"] is False
        assert r["minimo"] is None and r["ressuprimento"] is None and r["zerado"] is None
        assert len(cur.queries) == 1


class TestResumoAlertasEstoqueCacheHit:
    """Cache já populado (alguém já apertou "Atualizar" antes) — a leitura
    do card não recalcula nada, só devolve o que está na tabela."""

    def test_le_do_cache_sem_recalcular(self, monkeypatch):
        cache_row = {
            "minimo": 4175, "ressuprimento": 1885, "zerado": 0,
            "curva_abc_ultima_geracao": None, "curva_abc_desatualizada": True, "atualizado_em": None,
        }
        cur = FakeCursor(one=[MODULO_ON, TODOS_LIGADOS, cache_row])
        conn = _patch(monkeypatch, cur)
        r = svc._resumo_alertas_estoque_sync("srv", "bd")
        assert r["success"] is True and r["ativo"] is True
        assert r["minimo"] == {"count": 4175}
        assert r["ressuprimento"] == {"count": 1885}
        assert r["zerado"] == {"count": 0}
        assert r["curva_abc_desatualizada"] is True
        # Nenhuma query em `pecas` — só leu o cache.
        assert not any("FROM pecas" in q for q, _ in cur.queries)
        assert conn.committed is False

    def test_flag_desligada_esconde_contagem_mesmo_com_cache(self, monkeypatch):
        cache_row = {
            "minimo": 10, "ressuprimento": 20, "zerado": 0,
            "curva_abc_ultima_geracao": None, "curva_abc_desatualizada": False, "atualizado_em": None,
        }
        flags = {"ALERTA_ESTOQUE_MINIMO": 1, "ALERTA_ESTOQUE_RESSUPRIMENTO": 0, "ALERTA_ESTOQUE_ZERADO": 0}
        cur = FakeCursor(one=[MODULO_ON, flags, cache_row])
        _patch(monkeypatch, cur)
        r = svc._resumo_alertas_estoque_sync("srv", "bd")
        assert r["minimo"] == {"count": 10}
        assert r["ressuprimento"] is None
        assert r["zerado"] is None


class TestResumoAlertasEstoqueBootstrap:
    """Primeira vez pra essa empresa (cache ainda vazio) — calcula e grava
    uma vez só, pra o card não ficar vazio até alguém clicar "Atualizar"."""

    def test_cache_vazio_calcula_e_grava(self, monkeypatch):
        cur = FakeCursor(one=[
            MODULO_ON,
            TODOS_LIGADOS,
            None,  # cache vazio
            {"minimo": 5, "ressuprimento": 3, "zerado": 1},  # SUM
            None,  # log_auditoria: nunca gerada
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._resumo_alertas_estoque_sync("srv", "bd")
        assert r["success"] is True
        assert r["minimo"] == {"count": 5}
        assert r["ressuprimento"] == {"count": 3}
        assert r["zerado"] == {"count": 1}
        assert r["curva_abc_ultima_geracao"] is None
        assert r["curva_abc_desatualizada"] is True
        assert r["atualizado_em"] is not None
        assert conn.committed is True
        assert any("INSERT INTO alertas_estoque_cache" in q for q, _ in cur.queries)
        assert any("DELETE FROM alertas_estoque_cache" in q for q, _ in cur.queries)


class RaisingLogAuditoriaCursor(FakeCursor):
    """Simula uma base sem a tabela `log_auditoria` (bases mais antigas/de
    teste que nunca tiveram essa tabela criada — achado real testando
    contra a conexão PAGÉ MINIMACHINE/BD_PAJE, 2026-07-20): a query de
    Curva ABC desatualizada estoura, o resto do resumo (contagens) não
    pode quebrar por causa disso."""
    def execute(self, q, p=None):
        super().execute(q, p)
        if "log_auditoria" in q:
            raise Exception("Invalid object name 'log_auditoria'.")


class TestResumoAlertasEstoqueSemTabelaLogAuditoria:
    def test_falha_na_curva_abc_desatualizada_nao_derruba_as_contagens(self, monkeypatch):
        cur = RaisingLogAuditoriaCursor(one=[
            MODULO_ON,
            TODOS_LIGADOS,
            None,  # cache vazio -> bootstrap
            {"minimo": 5, "ressuprimento": 0, "zerado": 0},  # SUM
        ])
        _patch(monkeypatch, cur)
        r = svc._resumo_alertas_estoque_sync("srv", "bd")
        assert r["success"] is True
        assert r["minimo"] == {"count": 5}
        assert r["curva_abc_ultima_geracao"] is None
        assert r["curva_abc_desatualizada"] is True


def _atualizar_req(**over):
    base = dict(servidor="srv", banco="bd", usuario_alteracao=1, classe=1, master=False)
    base.update(over)
    return AtualizarAlertasEstoqueRequest(**base)


class TestAtualizarAlertasEstoque:
    def test_modulo_desligado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        _patch(monkeypatch, cur)
        r = svc._atualizar_alertas_estoque_sync(_atualizar_req())
        assert r["success"] is False
        assert "desativad" in r["message"].lower()

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON])
        _patch(monkeypatch, cur)
        # tem_permissao faz um SELECT que aqui retorna None (sem linha).
        r = svc._atualizar_alertas_estoque_sync(_atualizar_req(classe=2))
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_master_ignora_permissao_e_recalcula(self, monkeypatch):
        cur = FakeCursor(one=[
            MODULO_ON,
            TODOS_LIGADOS,
            {"minimo": 7, "ressuprimento": 2, "zerado": 0},  # SUM
            None,  # log_auditoria: nunca gerada
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._atualizar_alertas_estoque_sync(_atualizar_req(master=True, classe=None))
        assert r["success"] is True
        assert r["minimo"] == {"count": 7}
        assert r["ressuprimento"] == {"count": 2}
        assert conn.committed is True
        assert any("INSERT INTO alertas_estoque_cache" in q for q, _ in cur.queries)

    def test_sempre_recalcula_mesmo_com_cache_existente(self, monkeypatch):
        # Diferente da leitura (GET), "Atualizar" nunca lê o cache — sempre
        # recalcula de verdade e sobrescreve.
        cur = FakeCursor(one=[
            MODULO_ON,
            {"ok": 1},  # tem_permissao encontrou a linha -> permitido
            TODOS_LIGADOS,
            {"minimo": 1, "ressuprimento": 1, "zerado": 1},
            None,
        ])
        _patch(monkeypatch, cur)
        r = svc._atualizar_alertas_estoque_sync(_atualizar_req(classe=1))
        assert r["success"] is True
        assert not any("SELECT TOP 1 minimo" in q for q, _ in cur.queries)


class TestListRessuprimentoZeradoNegativo:
    def test_filtro_zerado_negativo_adiciona_qtd_menor_igual_zero(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_ressuprimento_sync("srv", "bd", zerado_negativo=True)
        q, params = cur.queries[-1]
        assert "p.qtd <= 0" in q
        assert params == ()

    def test_sem_filtro_zerado_negativo_nao_aparece(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_ressuprimento_sync("srv", "bd")
        q, _ = cur.queries[-1]
        assert "p.qtd <= 0" not in q

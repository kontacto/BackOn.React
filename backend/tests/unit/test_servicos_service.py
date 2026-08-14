"""Testes de `_save_servico_sync` (Manutenção de Serviços, `FrmManSer2.frm`)
— foco na validação de `cod_icms` contra a tabela auxiliar `dscr_icms`,
adicionada 2026-08-06 (pedido explícito do usuário, rastreando os campos
novos `cod_icms`/`indop_nfse`): "cod_icms deve validar contra Dscr_Icms,
como Produtos já faz" — o form legado de Serviços nunca validava isso
(achado do rastreio ao VB6/VB.NET), decisão consciente de não replicar essa
lacuna na migração."""
import services.servicos_service as svc


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return []

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


def _patch(monkeypatch, cur):
    conn = FakeConn(cur)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _dados_validos(**over):
    base = dict(
        descricao="Serviço Teste", valor_hora=100.0, situacao="A", tipo=0,
        comissao=0, comissao_e=0, comissao_a=0, desc_g=0, desc_s=0, desc_v=0,
    )
    base.update(over)
    return base


class TestValidacaoCodIcms:
    def test_bloqueia_cod_icms_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[{"servicos": 1}, None])
        conn = _patch(monkeypatch, cur)
        result = svc._save_servico_sync("srv", "bd", "S001", _dados_validos(cod_icms="777"))
        assert result["success"] is False
        assert "não cadastrado" in result["message"]
        assert "777" in result["message"]
        assert conn.committed is False

    def test_permite_cod_icms_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[{"servicos": 1}, {"ok": 1}, None])
        conn = _patch(monkeypatch, cur)
        result = svc._save_servico_sync("srv", "bd", "S001", _dados_validos(cod_icms="999"))
        assert result["success"] is True
        assert conn.committed is True
        icms_q, icms_p = next(q for q in cur.queries if "dscr_icms" in q[0])
        assert icms_p == ("999",)

    def test_cod_icms_vazio_nao_valida(self, monkeypatch):
        cur = FakeCursor(one=[{"servicos": 1}, None])
        conn = _patch(monkeypatch, cur)
        result = svc._save_servico_sync("srv", "bd", "S001", _dados_validos(cod_icms=""))
        assert result["success"] is True
        assert conn.committed is True
        assert not any("dscr_icms" in q for q, _ in cur.queries)

    def test_modulo_desativado_bloqueia_antes_de_validar_icms(self, monkeypatch):
        cur = FakeCursor(one=[{"servicos": 0}])
        _patch(monkeypatch, cur)
        result = svc._save_servico_sync("srv", "bd", "S001", _dados_validos(cod_icms="999"))
        assert result["success"] is False
        assert "desativado" in result["message"].lower()
        assert not any("dscr_icms" in q for q, _ in cur.queries)

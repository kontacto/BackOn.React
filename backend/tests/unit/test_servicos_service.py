"""Testes de `_save_servico_sync` (Manutenção de Serviços, `FrmManSer2.frm`)
— foco na validação de `cod_icms` contra a tabela auxiliar `dscr_icms`,
adicionada 2026-08-06 (pedido explícito do usuário, rastreando os campos
novos `cod_icms`/`indop_nfse`): "cod_icms deve validar contra Dscr_Icms,
como Produtos já faz" — o form legado de Serviços nunca validava isso
(achado do rastreio ao VB6/VB.NET), decisão consciente de não replicar essa
lacuna na migração."""
import services.servicos_service as svc


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


class TestListTributacaoMunicipioSync:
    """Busca em `Tributacao_MUnicipio` — tabela oficial real herdada do
    legado, usada pelo modal de busca do "Código Complementar Municipal"
    em Cadastro de Serviços (achado 2026-08-24, rastreando `DAO_NFE.vb`
    até a raiz — ver `nfse_emissao_service.py`/PENDENCIAS.md)."""

    def _row(self, cod_trib_mun="015", descricao="Manutenção de aparelhos.", cod_trib_nac_mun="14.01.01.015", cod_trib_nac="140101"):
        return {
            "cTribNacMun": cod_trib_nac_mun, "cTribNac": cod_trib_nac,
            "cTribMun": cod_trib_mun, "Descricao": descricao,
        }

    def test_tabela_ausente_devolve_lista_vazia_sem_erro(self, monkeypatch):
        # Nem toda instalação tem essa tabela carregada — degrada
        # graciosamente em vez de bloquear o cadastro de Serviços.
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._list_tributacao_municipio_sync("srv", "bd", search="", cod_lista_servico="")
        assert r["success"] is True
        assert r["items"] == []

    def test_busca_por_termo_usa_descricao_like(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}], many=[[self._row()]])
        _patch(monkeypatch, cur)
        r = svc._list_tributacao_municipio_sync("srv", "bd", search="manuten", cod_lista_servico="140101")
        assert r["success"] is True
        assert len(r["items"]) == 1
        assert r["items"][0]["cod_trib_mun"] == "015"
        assert r["items"][0]["descricao"] == "Manutenção de aparelhos."
        busca_q = next(q for q in cur.queries if "Descricao LIKE" in q[0])
        assert busca_q[1] == ("%manuten%",)

    def test_sem_termo_usa_cod_lista_servico_cttribnac(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}], many=[[self._row(), self._row(cod_trib_mun="032", descricao="Manutenção de equipamentos.")]])
        _patch(monkeypatch, cur)
        r = svc._list_tributacao_municipio_sync("srv", "bd", search="", cod_lista_servico="140101")
        assert r["success"] is True
        assert len(r["items"]) == 2
        cod_q = next(q for q in cur.queries if "cTribNac = " in q[0])
        assert cod_q[1] == ("140101",)

    def test_sem_termo_e_sem_codigo_lista_tudo(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}], many=[[self._row()]])
        _patch(monkeypatch, cur)
        r = svc._list_tributacao_municipio_sync("srv", "bd", search="", cod_lista_servico="")
        assert r["success"] is True
        assert any("ORDER BY cTribNacMun" in q[0] and "WHERE" not in q[0] for q in cur.queries)

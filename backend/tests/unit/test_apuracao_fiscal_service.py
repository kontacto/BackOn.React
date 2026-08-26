"""Testes de `apuracao_fiscal_service.py` — Apuração Fiscal (`Geral\\
FrmCalImp.frm`). Cobre os 3 modos (NFCE/NFE/DIFAL) e as diferenças reais
entre eles: NFCE calcula a alíquota de ICMS (não tem coluna própria),
NFE lê a alíquota de uma coluna já existente; DIFAL replica a fórmula
exata do legado pro rateio (rótulo/fórmula com descompasso não
resolvido — ver docstring do módulo)."""
import services.apuracao_fiscal_service as svc


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

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _patch(monkeypatch, cur):
    conn = FakeConn(cur)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestApurarSync:
    def test_modo_invalido_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._apurar_sync("s", "b", modo="XYZ", data_ini=None, data_fim=None, cfop=None)
        assert r["success"] is False

    def test_sem_registros_retorna_lista_vazia(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._apurar_sync("s", "b", modo="NFCE", data_ini=None, data_fim=None, cfop=None)
        assert r["success"] is True
        assert r["itens"] == []
        assert r["totais"] == {}

    def test_nfce_calcula_aliquota_icms(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "num_nfce": 7, "comanda": 3356, "data_emissao": "2026-08-01",
            "codigo_fab": "ABC", "descricao": "Produto X", "cfop": "5102",
            "tributacao": " 0102 ", "qtd": 2, "p_unit": 10.0, "valor_total": 20.0,
            "cst_pis": "01", "valor_pis": 1.0, "cst_cofins": "01", "valor_cofins": 2.0,
            "base_icms": 20.0, "valor_icms": 3.6, "alqt_fcp": 2.0, "valor_fcp": 0.4,
            "alqt_fcp_retido": 0.0, "valor_fcp_retido": 0.0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._apurar_sync("s", "b", modo="NFCE", data_ini=None, data_fim=None, cfop=None)
        assert r["success"] is True
        item = r["itens"][0]
        assert item["aliquota_icms"] == 18.0  # 3.6 / 20.0 * 100
        assert item["cst"] == "0102"  # Trim() do legado
        assert r["totais"]["total_valor_icms"] == 3.6

    def test_nfce_aliquota_zero_quando_sem_icms(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "num_nfce": 1, "comanda": 1, "data_emissao": None, "codigo_fab": "A", "descricao": "P",
            "cfop": "5102", "tributacao": "", "qtd": 1, "p_unit": 5.0, "valor_total": 5.0,
            "cst_pis": None, "valor_pis": 0, "cst_cofins": None, "valor_cofins": 0,
            "base_icms": 0.0, "valor_icms": 0.0, "alqt_fcp": 0, "valor_fcp": 0,
            "alqt_fcp_retido": 0, "valor_fcp_retido": 0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._apurar_sync("s", "b", modo="NFCE", data_ini=None, data_fim=None, cfop=None)
        assert r["itens"][0]["aliquota_icms"] == 0.0

    def test_nfe_le_aliquota_icms_de_coluna_propria(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "num_nf": 39, "data_nf": "2026-08-01", "codigo_fab": "X", "descricao": "Y",
            "cod_fiscal": "5929", "tributacao": "0101", "qtd": 1, "p_unit": 100.0, "valor_total": 100.0,
            "tributacao_pis": "01", "valor_pis": 1.65, "tributacao_cofins": "01", "valor_cofins": 7.6,
            "base_icms": 100.0, "Alqt_Icms": 18.0, "Valor_Icms": 18.0, "alqt_fcp": 0, "valor_fcp": 0,
            "alqt_fcp_retido": 0, "valor_fcp_retido": 0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._apurar_sync("s", "b", modo="NFE", data_ini=None, data_fim=None, cfop=None)
        item = r["itens"][0]
        assert item["aliquota_icms"] == 18.0
        assert item["cfop"] == "5929"
        assert "aliquota_interestadual" not in item

    def test_difal_filtra_e_calcula_rateio_com_rotulo_correto(self, monkeypatch):
        # percentual_origem = fatia retida pela UF de ORIGEM, confirmado
        # contra o Convênio ICMS 93/2015 (Cláusula décima) — 2026-08-24.
        cur = FakeCursor(many=[[{
            "num_nf": 50, "data_nf": "2026-08-01", "codigo_fab": "X", "descricao": "Y",
            "cod_fiscal": "6108", "tributacao": "0101", "qtd": 1, "p_unit": 1000.0, "valor_total": 1000.0,
            "tributacao_pis": "01", "valor_pis": 16.5, "tributacao_cofins": "01", "valor_cofins": 76.0,
            "base_icms": 1000.0, "Alqt_Icms": 12.0, "Valor_Icms": 120.0, "alqt_fcp": 0, "valor_fcp": 0,
            "alqt_fcp_retido": 0, "valor_fcp_retido": 0,
            "aliquota_interestadual": 12.0, "aliquota_interna_destino": 18.0,
            "percentual_origem": 60.0, "fundo_pobreza": 2.0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._apurar_sync("s", "b", modo="DIFAL", data_ini=None, data_fim=None, cfop=None)
        item = r["itens"][0]
        # TempDifal(fcp) = 1000 * 2 / 100 = 20
        assert item["valor_fcp_difal"] == 20.0
        # TempDifal = 1000 * (18-12) / 100 = 60
        # valor_origem = 60 * 60/100 = 36 (origem fica com 60% em 2016,
        # cronograma da Cláusula décima) ; valor_destino = 60*(100-60)/100 = 24
        assert item["valor_origem"] == 36.0
        assert item["valor_destino"] == 24.0
        assert r["totais"]["total_valor_fcp_difal"] == 20.0
        assert r["totais"]["total_valor_origem"] == 36.0
        assert r["totais"]["total_valor_destino"] == 24.0
        # filtro real aplicado na query
        q, p = cur.queries[0]
        assert "aliquota_interna_destino>0" in q

    def test_filtro_data_e_cfop_aplicados_na_query(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._apurar_sync("s", "b", modo="NFE", data_ini="2026-08-01", data_fim="2026-08-31", cfop="5102")
        q, p = cur.queries[0]
        assert "nf.data_nf >= %s AND nf.data_nf <= %s" in q
        assert "nfi.cod_fiscal = %s" in q
        assert p == ("2026-08-01", "2026-08-31", "5102")

    def test_erro_de_banco_retorna_falha(self, monkeypatch):
        class BrokenConn(FakeConn):
            def cursor(self, as_dict=False):
                raise RuntimeError("boom")
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: BrokenConn(FakeCursor()))
        r = svc._apurar_sync("s", "b", modo="NFCE", data_ini=None, data_fim=None, cfop=None)
        assert r["success"] is False

"""Testes unitários de `_get_empresa_sync`/`_txt` (controle_service.py) —
achado ao vivo 2026-08-17 contra Minimachine/KONTACTO-TESTE:
`controle.empresa` é `int` nessa instalação, não texto, e o código
assumia `.strip()` incondicional — quebrava com `'int' object has no
attribute 'strip'`. Generalizado pra tolerar qualquer campo de texto
vindo como número."""
import services.controle_service as svc


class FakeCursor:
    def __init__(self, row=None, rows=None):
        # `rows` (lista) permite mockar múltiplas queries em sequência
        # (ex.: `controle` + `controle_aux`) — `row` (valor único) continua
        # funcionando pros testes antigos, repete o mesmo valor sempre.
        self._rows = list(rows) if rows is not None else None
        self._row = row

    def execute(self, q, p=None):
        pass

    def fetchone(self):
        if self._rows is not None:
            return self._rows.pop(0) if self._rows else None
        return self._row

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, row=None, rows=None):
    conn = FakeConn(FakeCursor(row=row, rows=rows))
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestTxt:
    def test_none_vira_string_vazia(self):
        assert svc._txt(None) == ""

    def test_string_com_espaco_e_trimada(self):
        assert svc._txt("  Kontacto  ") == "Kontacto"

    def test_int_vira_string(self):
        assert svc._txt(1) == "1"

    def test_int_zero_vira_string_zero_nao_vazia(self):
        # Diferente do padrão antigo `(v or "").strip()`, que trataria 0
        # como falsy e devolveria "" — _txt preserva o valor real.
        assert svc._txt(0) == "0"


class TestGetEmpresaSync:
    def test_campos_string_normais(self, monkeypatch):
        row = {
            "empresa": "Loja Central", "fantasia": "Kontacto", "rz_social": "Kontacto Ltda",
            "uf": "RJ", "endereco": "Rua X", "numero": 10, "complemento": "",
            "bairro": "Centro", "cidade": "Rio", "cep": "20000000", "ddd": "21",
            "telefone": "12345678", "CELULAR": "", "cgc": "123", "inscr_est": "",
            "cod_rel": "F", "exige_cpf_cliente": False, "aceita_duplicar_cnpj": False,
            "exige_chassi_os": True,
        }
        _patch(monkeypatch, row)
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["empresa"] == "Loja Central"
        assert r["fantasia"] == "Kontacto"
        assert r["exige_chassi_os"] is True

    def test_empresa_como_int_nao_quebra(self, monkeypatch):
        """Réplica exata do achado ao vivo: controle.empresa = 1 (int)."""
        row = {
            "empresa": 1, "fantasia": "KONTACTO", "rz_social": "SOFTHWORD INFORMATICA LTDA",
            "uf": "RJ", "endereco": "R 3 PAA 11932", "numero": 3, "complemento": "APT 0704 BLC 0008",
            "bairro": "BARRA DA TIJUCA", "cidade": "RIO DE JANEIRO", "cep": "22775036", "ddd": 21,
            "telefone": "24394995", "CELULAR": "972464361", "cgc": "52179641000159", "inscr_est": "",
            "cod_rel": "I", "exige_cpf_cliente": False, "aceita_duplicar_cnpj": False,
        }
        _patch(monkeypatch, row)
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["empresa"] == "1"
        assert r["fantasia"] == "KONTACTO"
        assert r["ddd"] == 21

    def test_flags_fiscais_da_arvore_de_decisao_kpdv(self, monkeypatch):
        # Parte C do ecossistema fiscal (2026-08-19) — ver ibs_cbs_service.py
        # e VendaViewModel.cs (KPDV). 2 queries em sequência: `controle`
        # (3 flags + emite_nf_comanda) e `controle_aux` (emite_nfce/emite_nfse).
        row_controle = {
            "empresa": "Loja Central", "fantasia": "Kontacto", "rz_social": "Kontacto Ltda",
            "uf": "RJ", "endereco": "Rua X", "numero": 10, "complemento": "",
            "bairro": "Centro", "cidade": "Rio", "cep": "20000000", "ddd": "21",
            "telefone": "12345678", "CELULAR": "", "cgc": "123", "inscr_est": "",
            "cod_rel": "F", "exige_cpf_cliente": False, "aceita_duplicar_cnpj": False,
            "exige_chassi_os": True, "emite_nf_comanda": True,
            "PERGUNTA_EMITE_NFCE": True, "ESCOLHE_NFE_NFCE": False, "IMPRIME_NFCE_NAO_FISCAL": True,
        }
        row_controle_aux = {"emite_nfce": True, "emite_nfse": False}
        _patch(monkeypatch, rows=[row_controle, row_controle_aux])
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["emite_nf_comanda"] is True
        assert r["pergunta_emite_nfce"] is True
        assert r["escolhe_nfe_nfce"] is False
        assert r["imprime_nfce_nao_fiscal"] is True
        assert r["emite_nfce"] is True
        assert r["emite_nfse"] is False

    def test_sem_registro_controle(self, monkeypatch):
        _patch(monkeypatch, None)
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["empresa"] is None
        assert r["fantasia"] is None

    def test_falha_conexao(self, monkeypatch):
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is False

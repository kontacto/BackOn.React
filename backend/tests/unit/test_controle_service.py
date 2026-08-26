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
        # (emite_nf_comanda) e `controle_aux` (emite_nfce/emite_nfse + os 3
        # campos PERGUNTA_EMITE_NFCE/ESCOLHE_NFE_NFCE/IMPRIME_NFCE_NAO_
        # FISCAL — movidos de `controle` pra `controle_aux` 2026-08-26,
        # bug real achado ao vivo, ver TestGetEmpresaSyncTabelaCorreta).
        row_controle = {
            "empresa": "Loja Central", "fantasia": "Kontacto", "rz_social": "Kontacto Ltda",
            "uf": "RJ", "endereco": "Rua X", "numero": 10, "complemento": "",
            "bairro": "Centro", "cidade": "Rio", "cep": "20000000", "ddd": "21",
            "telefone": "12345678", "CELULAR": "", "cgc": "123", "inscr_est": "",
            "cod_rel": "F", "exige_cpf_cliente": False, "aceita_duplicar_cnpj": False,
            "exige_chassi_os": True, "emite_nf_comanda": True,
        }
        row_controle_aux = {
            "emite_nfce": True, "emite_nfse": False,
            "PERGUNTA_EMITE_NFCE": True, "ESCOLHE_NFE_NFCE": False, "IMPRIME_NFCE_NAO_FISCAL": True,
        }
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


class TestGetEmpresaSyncTabelaCorreta:
    """Bug real achado ao vivo 2026-08-26 na conexão "Baixo Brisa Remoto"
    (`DESKTOP-TDK482U`/`BD_BAIXOBRISA`, SQL Server 2014 SP1) — recibo do
    Pedido Bar e O.S. de Oficina saindo sem cabeçalho NENHUM (nem fantasia/
    endereço, não só sem logo). Causa raiz: `PERGUNTA_EMITE_NFCE`/
    `ESCOLHE_NFE_NFCE`/`IMPRIME_NFCE_NAO_FISCAL` eram lidos de `FROM
    controle`, mas `CAMPOS_CONTROLE_AUX` (controle_sistema_service.py)
    sempre os classificou como colunas de `controle_aux` — em instalações
    onde essas 3 colunas não existem redundantemente também em `controle`
    (caso real de `BD_BAIXOBRISA`), a query batia em "Invalid column
    name" e derrubava a função INTEIRA (`success: False`), levando junto
    fantasia/endereço/telefone/CNPJ. Query corrigida pra ler da tabela
    certa (`controle_aux`, junto com `emite_nfce`/`emite_nfse` que já
    liam de lá)."""

    def test_campos_fiscais_sao_lidos_de_controle_aux_nao_controle(self, monkeypatch):
        _patch(monkeypatch, rows=[
            {"empresa": "Loja", "fantasia": "Kontacto"},
            {"emite_nfce": False, "emite_nfse": False, "PERGUNTA_EMITE_NFCE": True, "ESCOLHE_NFE_NFCE": True, "IMPRIME_NFCE_NAO_FISCAL": False},
            {},
        ])
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["pergunta_emite_nfce"] is True
        assert r["escolhe_nfe_nfce"] is True
        assert r["imprime_nfce_nao_fiscal"] is False

    def test_replica_o_bug_real_coluna_so_existe_em_controle_aux(self, monkeypatch):
        """Réplica do erro real reportado pelo SQL Server: se essas 3
        colunas fossem lidas de `FROM controle` (bug antigo) numa base
        onde elas só existem em `controle_aux`, a 1ª query já falharia —
        confirma que a query de `controle` (`r`) não depende mais delas."""

        class CursorSemColunasFiscaisEmControle:
            def __init__(self):
                self._calls = 0

            def execute(self, q, p=None):
                self._calls += 1
                # A 1ª query (controle) NUNCA pode pedir essas 3 colunas —
                # nesta base elas só existem em controle_aux.
                if self._calls == 1:
                    for col in ("PERGUNTA_EMITE_NFCE", "ESCOLHE_NFE_NFCE", "IMPRIME_NFCE_NAO_FISCAL"):
                        assert col not in q, f"{col} não deveria estar na query de `controle`"

            def fetchone(self):
                return {"fantasia": "Kontacto"}

            def close(self):
                pass

        class ConnFake:
            def cursor(self, as_dict=False):
                return CursorSemColunasFiscaisEmControle()

            def close(self):
                pass

        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: ConnFake())
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["fantasia"] == "Kontacto"


class TestGetEmpresaSyncLogo:
    """Bug real corrigido 2026-08-26 (achado ao vivo pelo usuário — O.S. de
    Oficina e recibo do Pedido Bar saindo sem cabeçalho nenhum, não só sem
    logo): `logo_bytes` era lido da 3ª query mas nunca codificado/devolvido
    no dict de resposta (dead code), e essa query ficava dentro do mesmo
    try/except do resto da função — se falhasse, derrubava TODO o
    cabeçalho da empresa, não só a logo."""

    _ROW_BASE = {
        "empresa": "Loja Central", "fantasia": "Kontacto", "rz_social": "Kontacto Ltda",
        "uf": "RJ", "endereco": "Rua X", "numero": 10, "complemento": "",
        "bairro": "Centro", "cidade": "Rio", "cep": "20000000", "ddd": "21",
        "telefone": "12345678", "CELULAR": "", "cgc": "123", "inscr_est": "",
        "cod_rel": "F", "exige_cpf_cliente": False, "aceita_duplicar_cnpj": False,
    }

    def test_logo_presente_e_codificada_em_base64(self, monkeypatch):
        rows = [dict(self._ROW_BASE), {"emite_nfce": False, "emite_nfse": False}, {"logo_empresa": b"\x89PNG\r\n", "logo_empresa_mime": "image/png"}]
        _patch(monkeypatch, rows=rows)
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["logo_mime"] == "image/png"
        import base64
        assert base64.b64decode(r["logo_base64"]) == b"\x89PNG\r\n"

    def test_logo_ausente_fica_none_sem_quebrar(self, monkeypatch):
        rows = [dict(self._ROW_BASE), {"emite_nfce": False, "emite_nfse": False}, {"logo_empresa": None, "logo_empresa_mime": None}]
        _patch(monkeypatch, rows=rows)
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["logo_base64"] is None
        assert r["logo_mime"] is None

    def test_query_da_logo_falhando_nao_derruba_o_resto_do_cabecalho(self, monkeypatch):
        """Réplica exata do bug relatado: se a 3ª query (logo) lançar
        exceção — coluna ainda não migrada num banco específico, por
        exemplo — o resto do cabeçalho (fantasia/endereço/telefone/CNPJ)
        continua vindo normalmente, não é mais tudo-ou-nada."""

        class CursorQueLogoQuebra:
            def __init__(self):
                self._calls = 0

            def execute(self, q, p=None):
                self._calls += 1
                if self._calls == 3:
                    raise RuntimeError("Invalid column name 'logo_empresa'.")

            def fetchone(self):
                if self._calls == 1:
                    return dict(TestGetEmpresaSyncLogo._ROW_BASE)
                if self._calls == 2:
                    return {"emite_nfce": False, "emite_nfse": False}
                return None

            def close(self):
                pass

        class ConnQueLogoQuebra:
            def cursor(self, as_dict=False):
                return CursorQueLogoQuebra()

            def close(self):
                pass

        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: ConnQueLogoQuebra())
        r = svc._get_empresa_sync("srv", "bd")
        assert r["success"] is True
        assert r["fantasia"] == "Kontacto"
        assert r["cgc"] == "123"
        assert r["logo_base64"] is None

"""Testes UNITÁRIOS de Bancos (Financeiro > Cobranças) — Fase 1 (cadastro).
Ver PENDENCIAS.md > "Bancos (Cadastro de Cobrança / Boleto / CNAB)" pro
desenho completo. Mesmo padrão de test_equipamentos_service.py: cursor/
conexão falsos (monkeypatch em _open_conn/_get_col_sizes), sem banco real —
o round trip contra banco real (GERDELL/BARESTELA) já foi validado à parte
nesta sessão."""
import services.bancos_service as svc


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
    monkeypatch.setattr(svc, "_get_col_sizes", lambda *a, **k: {})
    return conn


DADOS_VALIDOS = {
    "codigo": 341, "descricao": "Itaú", "agencia": 1234, "conta_corrente": 98765,
    "carteira": 175, "codigo_cedente": "123456",
    "endereco_remessa": "C:\\Remessa", "endereco_retorno": "C:\\Retorno",
    "integracao_api": False,
}


class TestListBancos:
    def test_list_vazio(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_bancos_sync("srv", "bd")
        assert r["success"] is True
        assert r["items"] == []

    def test_list_com_busca_usa_where(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "cod": 1, "codigo": 341, "descricao": "Itaú", "agencia": 1234,
            "contacorrente": 98765, "carteira": 175, "situacao": "A", "integracao_api": False,
        }]])
        _patch(monkeypatch, cur)
        r = svc._list_bancos_sync("srv", "bd", busca="Itaú")
        assert r["success"] is True
        assert len(r["items"]) == 1
        assert r["items"][0]["descricao"] == "Itaú"
        assert "WHERE" in cur.queries[0][0]

    def test_list_erro_conexao(self, monkeypatch):
        def _boom(*a, **k):
            raise Exception("sem rede")
        monkeypatch.setattr(svc, "_open_conn", _boom)
        r = svc._list_bancos_sync("srv", "bd")
        assert r["success"] is False
        assert r["items"] == []


class TestGetBanco:
    def test_get_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_banco_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_get_encontrado(self, monkeypatch):
        row = {
            "cod": 1, "codigo": 341, "digito_banco": 0, "descricao": "Itaú",
            "descr_arquivo": "ITAU", "agencia": 1234, "dv_agencia": "5",
            "contacorrente": 98765, "dv_contacorrente": "4", "dv_agencia_conta": "3",
            "situacao": "A", "carteira": 175, "VARIACAO_CARTEIRA": 19,
            "codigocedente": "123456", "Cod_Transmissao": "", "contrato": 0,
            "especie_doc": 2, "aceite": "N", "tarifa_cobranca": 3.5,
            "incidencia_multa": 1, "dias_multa": 1, "tipo_multa": 1,
            "Multa_Atraso_Pag": 2.0, "Mora_Dia_Pag": 0.033, "dias_protesto": 5,
            "codigo_protesto": 1, "dias_baixa": 60, "codigo_baixa": 1,
            "tipo_cobranca": 1, "tipo_registro": 1, "emissao_boleto": 1,
            "distribui_boleto": 1, "numero_boleto": 1, "instr_cobranca_1": 0,
            "instr_cobranca_2": 0, "tituloboleto": "DM", "mensagem_boleto_1": "",
            "mensagem_boleto_2": "", "mensagem_boleto_3": "",
            "end_remessa": "C:\\Remessa", "end_retorno": "C:\\Retorno",
            "integracao_api": False, "chave_api": "", "chave_api_2": "",
            "chave_api_3": "", "chave_api_4": "", "remessa": 0, "data_remessa": None,
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_banco_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["descricao"] == "Itaú"
        assert r["carteira"] == 175
        assert r["endereco_remessa"] == "C:\\Remessa"
        assert r["chave_api_1"] == ""


class TestSaveBancoValidacao:
    def test_bloqueia_sem_descricao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "descricao": ""}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False
        assert "descrição" in r["message"].lower()

    def test_bloqueia_sem_codigo(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "codigo": 0}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False
        assert "código" in r["message"].lower()

    def test_bloqueia_sem_agencia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "agencia": 0}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False
        assert "agência" in r["message"].lower()

    def test_bloqueia_sem_conta(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "conta_corrente": 0}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False

    def test_bloqueia_sem_carteira(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "carteira": 0}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False

    def test_bloqueia_sem_codigo_cedente(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "codigo_cedente": ""}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False
        assert "cedente" in r["message"].lower()

    def test_cnab_exige_endereco_remessa_retorno(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "endereco_remessa": ""}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False
        assert "remessa" in r["message"].lower()

        dados = {**DADOS_VALIDOS, "endereco_retorno": ""}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False
        assert "retorno" in r["message"].lower()

    def test_integracao_api_dispensa_endereco_remessa_retorno(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 1}])
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "endereco_remessa": "", "endereco_retorno": "", "integracao_api": True}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is True


class TestSaveBancoCrud:
    def test_cria_novo(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 7}])
        _patch(monkeypatch, cur)
        r = svc._save_banco_sync("srv", "bd", DADOS_VALIDOS)
        assert r["success"] is True
        assert r["cod"] == 7
        assert "INSERT INTO bancos" in cur.queries[-1][0]

    def test_atualiza_existente(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "cod": 7}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is True
        assert r["cod"] == 7
        assert "UPDATE bancos" in cur.queries[-1][0]

    def test_atualiza_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        dados = {**DADOS_VALIDOS, "cod": 999}
        r = svc._save_banco_sync("srv", "bd", dados)
        assert r["success"] is False


class TestDeleteBanco:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_banco_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_bloqueia_por_cartoes_configuracoes(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 341, "contacorrente": 98765, "carteira": 175},  # SELECT banco
            {"ok": 1},  # cartoes_configuracoes encontrado
        ])
        _patch(monkeypatch, cur)
        r = svc._delete_banco_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Cartões" in r["message"]

    def test_bloqueia_por_duplicata_rec_venc(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 341, "contacorrente": 98765, "carteira": 175},  # SELECT banco
            None,  # cartoes_configuracoes: nao encontrado
            {"ok": 1},  # duplicata_rec_venc: encontrado
        ])
        _patch(monkeypatch, cur)
        r = svc._delete_banco_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "títulos associados" in r["message"]

    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 341, "contacorrente": 98765, "carteira": 175},
            None,
            None,
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_banco_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
        assert "DELETE FROM bancos" in cur.queries[-1][0]

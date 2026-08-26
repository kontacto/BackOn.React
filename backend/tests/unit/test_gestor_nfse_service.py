"""Testes unitários de `gestor_nfse_service.py` (Gestor NFSe — Sefin
Nacional/DPS, migração de `Geral\\FrmManNSeSefin.frm`) — ver PENDENCIAS.md
> "Gestor NFSe" pro racional completo.

**Importantíssimo**: nenhum teste aqui fala com o ADN de verdade —
`nfe_fiscal_common.consultar_json_mtls`/`carregar_certificado_sync` são
sempre mockados, mesmo padrão do resto do pacote fiscal."""
import services.gestor_nfse_service as svc


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


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestListNfseSync:
    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._list_nfse_sync("srv", "bd", classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_lista_basica(self, monkeypatch):
        linha = {
            "codigo": 1, "num_dps": 10, "serie_dps": "1", "data_dps": "2026-08-20", "valor_total": 100.0,
            "STATUS": "Transmitida", "situacao": "A", "chave_acesso_dps": "x", "chave_acesso_nfse": "y",
            "comanda": 5, "cliente_codigo": 3, "cliente_nome": "FULANO",
        }
        cur = FakeCursor(many=[[linha]])
        _patch(monkeypatch, cur)
        r = svc._list_nfse_sync("srv", "bd", master=True)
        assert r["success"] is True
        assert r["itens"] == [linha]

    def test_filtros_entram_no_where(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_nfse_sync("srv", "bd", data_de="2026-08-01", data_ate="2026-08-20", comanda=5, cliente=3, master=True)
        q = cur.queries[-1][0]
        assert "dps.data_dps >= %s" in q
        assert "dps.data_dps <= %s" in q
        assert "dps.comanda = %s" in q
        assert "cm.cliente = %s" in q

    def test_falha_conexao(self, monkeypatch):
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: (_ for _ in ()).throw(Exception("timeout")))
        r = svc._list_nfse_sync("srv", "bd", master=True)
        assert r["success"] is False


class TestConsultarSituacaoUmaSync:
    def test_ambiente_nao_reconhecido(self):
        cur = FakeCursor()
        r = svc._consultar_situacao_uma_sync(cur, chave_acesso_nfse="x", tp_amb="9")
        assert r["success"] is False
        assert "não reconhecido" in r["message"].lower()

    def test_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        cur = FakeCursor()
        r = svc._consultar_situacao_uma_sync(cur, chave_acesso_nfse="x", tp_amb="1")
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (b"k", b"c"))
        monkeypatch.setattr(svc.nfe_fiscal_common, "consultar_json_mtls", lambda url, k, c: {"chaveAcesso": "x"})
        cur = FakeCursor()
        r = svc._consultar_situacao_uma_sync(cur, chave_acesso_nfse="x", tp_amb="1")
        assert r["success"] is True
        assert r["resposta"]["chaveAcesso"] == "x"

    def test_erro_http_bloqueia(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (b"k", b"c"))
        monkeypatch.setattr(
            svc.nfe_fiscal_common, "consultar_json_mtls",
            lambda url, k, c: {"_erro_http": 404, "message": "não encontrada"},
        )
        cur = FakeCursor()
        r = svc._consultar_situacao_uma_sync(cur, chave_acesso_nfse="x", tp_amb="1")
        assert r["success"] is False

    def test_falha_comunicacao_nao_propaga_excecao(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (b"k", b"c"))

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "consultar_json_mtls", _falha)
        cur = FakeCursor()
        r = svc._consultar_situacao_uma_sync(cur, chave_acesso_nfse="x", tp_amb="1")
        assert r["success"] is False
        assert "falha ao comunicar" in r["message"].lower()


class TestConsultarSituacaoSync:
    def test_bloqueia_sem_codigos(self):
        r = svc._consultar_situacao_sync("srv", "bd", codigos=[], master=True)
        assert r["success"] is False

    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._consultar_situacao_sync("srv", "bd", codigos=[1], classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: False)
        r = svc._consultar_situacao_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is False
        assert "sefin nacional" in r["message"].lower()

    def test_nfse_sem_chave_bloqueia_essa_linha(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "1")
        cur = FakeCursor(one=[{"codigo": 1, "chave_acesso_nfse": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._consultar_situacao_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is False
        assert "não transmitida" in r["resultados"][0]["message"].lower()
        assert conn.committed is True

    def test_sucesso_atualiza_status(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "1")
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (b"k", b"c"))
        monkeypatch.setattr(svc.nfe_fiscal_common, "consultar_json_mtls", lambda url, k, c: {"chaveAcesso": "x"})
        cur = FakeCursor(one=[{"codigo": 1, "chave_acesso_nfse": "3" * 50}])
        conn = _patch(monkeypatch, cur)
        r = svc._consultar_situacao_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is True
        assert any(q[0].startswith("UPDATE dps SET STATUS") for q in cur.queries)
        assert conn.committed is True

    def test_falha_comunicacao_nao_propaga_excecao(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "1")
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (b"k", b"c"))

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "consultar_json_mtls", _falha)
        cur = FakeCursor(one=[{"codigo": 1, "chave_acesso_nfse": "3" * 50}])
        conn = _patch(monkeypatch, cur)
        r = svc._consultar_situacao_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is False
        assert "falha ao comunicar" in r["resultados"][0]["message"].lower()
        assert conn.committed is True


class TestBaixarDanfeSync:
    def test_sem_permissao(self, monkeypatch):
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._baixar_danfe_sync("srv", "bd", 1, classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_modulo_desligado_bloqueia(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: False)
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._baixar_danfe_sync("srv", "bd", 1, master=True)
        assert r["success"] is False
        assert "sefin nacional" in r["message"].lower()

    def test_nfse_nao_encontrada(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._baixar_danfe_sync("srv", "bd", 1, master=True)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_pdf_em_cache_nao_chama_o_adn(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)

        def _falha(*a, **k):
            raise AssertionError("não deveria chamar o ADN com PDF já em cache")

        monkeypatch.setattr(svc.nfe_fiscal_common, "consultar_binario_mtls", _falha)
        cur = FakeCursor(one=[{"codigo": 1, "chave_acesso_nfse": "x", "PDF_DANFE_NFSE": b"PDFDATA"}])
        _patch(monkeypatch, cur)
        r = svc._baixar_danfe_sync("srv", "bd", 1, master=True)
        assert r["success"] is True
        import base64
        assert base64.b64decode(r["pdf_base64"]) == b"PDFDATA"

    def test_sem_chave_bloqueia(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        cur = FakeCursor(one=[{"codigo": 1, "chave_acesso_nfse": None, "PDF_DANFE_NFSE": None}])
        _patch(monkeypatch, cur)
        r = svc._baixar_danfe_sync("srv", "bd", 1, master=True)
        assert r["success"] is False
        assert "ainda não transmitida" in r["message"].lower()

    def test_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        cur = FakeCursor(one=[{"codigo": 1, "chave_acesso_nfse": "3" * 50, "PDF_DANFE_NFSE": None}])
        _patch(monkeypatch, cur)
        r = svc._baixar_danfe_sync("srv", "bd", 1, master=True)
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso_baixa_e_grava_cache(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (b"k", b"c"))
        monkeypatch.setattr(svc.nfe_fiscal_common, "consultar_binario_mtls", lambda url, k, c: b"%PDF-1.4 conteudo")
        cur = FakeCursor(one=[{"codigo": 1, "chave_acesso_nfse": "3" * 50, "PDF_DANFE_NFSE": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._baixar_danfe_sync("srv", "bd", 1, master=True)
        assert r["success"] is True
        import base64
        assert base64.b64decode(r["pdf_base64"]) == b"%PDF-1.4 conteudo"
        assert any(q[0].startswith("UPDATE dps SET PDF_DANFE_NFSE") for q in cur.queries)
        assert conn.committed is True

    def test_falha_download_repassa_mensagem(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (b"k", b"c"))

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "consultar_binario_mtls", _falha)
        cur = FakeCursor(one=[{"codigo": 1, "chave_acesso_nfse": "3" * 50, "PDF_DANFE_NFSE": None}])
        _patch(monkeypatch, cur)
        r = svc._baixar_danfe_sync("srv", "bd", 1, master=True)
        assert r["success"] is False
        assert "falha ao baixar" in r["message"].lower()


class TestEnviarEmailSync:
    def test_bloqueia_sem_codigos(self):
        r = svc._enviar_email_sync("srv", "bd", codigos=[], master=True)
        assert r["success"] is False

    def test_sem_permissao(self, monkeypatch):
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._enviar_email_sync("srv", "bd", codigos=[1], classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_modulo_desligado_bloqueia(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: False)
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._enviar_email_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is False
        assert "sefin nacional" in r["message"].lower()

    def test_nfse_nao_encontrada_bloqueia_so_essa_linha(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._enviar_email_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is False
        assert "não encontrada" in r["resultados"][0]["message"].lower()
        assert conn.committed is True

    def test_cliente_sem_email_bloqueia_so_essa_linha(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        cur = FakeCursor(one=[
            {"codigo": 1, "num_dps": 10, "comanda": 5, "cliente": 3, "cliente_nome": "Fulano", "e_mail": None},
        ])
        _patch(monkeypatch, cur)
        r = svc._enviar_email_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is False
        assert "e-mail" in r["resultados"][0]["message"].lower()

    def test_falha_ao_obter_pdf_bloqueia_so_essa_linha(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        cur = FakeCursor(one=[
            {"codigo": 1, "num_dps": 10, "comanda": 5, "cliente": 3, "cliente_nome": "Fulano", "e_mail": "x@x.com"},
            {"codigo": 1, "chave_acesso_nfse": None, "PDF_DANFE_NFSE": None},
        ])
        _patch(monkeypatch, cur)
        r = svc._enviar_email_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is False
        assert "ainda não transmitida" in r["resultados"][0]["message"].lower()

    def test_sucesso_chama_email_cobranca_service_com_anexo(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        chamadas = []

        def _fake_enviar(servidor, banco, dest, assunto, corpo, anexos):
            chamadas.append((dest, assunto, anexos))
            return {"success": True, "message": "ok"}

        monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", _fake_enviar)
        cur = FakeCursor(one=[
            {"codigo": 1, "num_dps": 10, "comanda": 5, "cliente": 3, "cliente_nome": "Fulano", "e_mail": "x@x.com"},
            {"codigo": 1, "chave_acesso_nfse": "3" * 50, "PDF_DANFE_NFSE": b"PDFCONTEUDO"},
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._enviar_email_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is True
        assert len(chamadas) == 1
        assert chamadas[0][0] == "x@x.com"
        assert chamadas[0][2][0]["conteudo"] == b"PDFCONTEUDO"
        assert conn.committed is True

    def test_falha_no_envio_e_reportada_sem_derrubar_lote(self, monkeypatch):
        monkeypatch.setattr(svc, "_modulo_sefin_nacional_ativo", lambda cur: True)
        monkeypatch.setattr(
            svc.email_cobranca_service, "_enviar_email_sync",
            lambda *a, **k: {"success": False, "message": "Falha de autenticação SMTP"},
        )
        cur = FakeCursor(one=[
            {"codigo": 1, "num_dps": 10, "comanda": 5, "cliente": 3, "cliente_nome": "Fulano", "e_mail": "x@x.com"},
            {"codigo": 1, "chave_acesso_nfse": "3" * 50, "PDF_DANFE_NFSE": b"PDFCONTEUDO"},
        ])
        _patch(monkeypatch, cur)
        r = svc._enviar_email_sync("srv", "bd", codigos=[1], master=True)
        assert r["success"] is False
        assert "autenticação" in r["resultados"][0]["message"].lower()

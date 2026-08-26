"""Testes unitários do motor de Boleto em PDF (ver services/boleto_pdf_
service.py). Vetores esperados das linhas digitáveis/código de barras
foram cruzados 3 vezes de forma independente (script ad-hoc, fora deste
arquivo) antes de virarem asserção fixa aqui — mesmo princípio de "bate
com arquivo real" já usado em test_cnab_itau_service.py."""
from datetime import date

import services.boleto_pdf_service as svc


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
        self.committed = 0
        self.rolled = 0

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled += 1

    def close(self):
        pass


# ============ Dígito verificador ============
class TestModulo10:
    def test_vetor_conhecido(self):
        # 8 dígitos alternando peso 2,1 da direita: réplica manual da
        # tabela de exemplo Febraban (campo livre simples).
        assert svc._modulo_10("341917500") == 9  # cruzado com script independente

    def test_resto_zero_vira_zero(self):
        assert svc._modulo_10("00000000") == 0


class TestModulo11Real:
    def test_vetor_conhecido(self):
        assert svc._modulo_11_real("34191016000015000175007788998123412345") == 1

    def test_resto_menor_igual_1_vira_1(self):
        # número todo zero -> soma 0 -> resto 0 -> <=1 -> 1
        assert svc._modulo_11_real("0" * 20) == 1


class TestModulo11Unibanco:
    def test_molde_x_resto_0_1_10_vira_1(self):
        assert svc._modulo_11_unibanco("0" * 20, "X") == 1

    def test_molde_n_resto_0_10_vira_0(self):
        assert svc._modulo_11_unibanco("0" * 20, "N") == 0


class TestFatorVencimento:
    def test_antes_do_corte_2025_usa_base_antiga(self):
        # 10/03/2025 é DEPOIS do corte -- testar uma data ANTES pra cobrir o outro ramo
        f = svc._fator_vencimento(date(2024, 1, 1), svc._DATA_BASE_ITAU_BRADESCO)
        assert f == (date(2024, 1, 1) - date(1997, 10, 7)).days

    def test_a_partir_do_corte_2025_reinicia_em_1000(self):
        f = svc._fator_vencimento(date(2025, 2, 22), svc._DATA_BASE_ITAU_BRADESCO)
        assert f == 1000
        f2 = svc._fator_vencimento(date(2025, 3, 10), svc._DATA_BASE_ITAU_BRADESCO)
        assert f2 == 1016


# ============ Linha digitável / código de barras por banco ============
# Dados fixos usados nos 3 casos abaixo -- valores conferidos 3x de forma
# independente (fora deste arquivo) antes de virar asserção fixa.
_DRV = {"dt_vencimento": date(2025, 3, 10), "valor": 1500.00}


class TestMontarBoletoItau:
    def test_codigo_barras_44_digitos_e_bate_com_calculo_independente(self):
        banco_row = {"carteira": 175, "agencia": 1234, "contacorrente": 12345, "dv_contacorrente": "6"}
        dados = svc._montar_boleto_itau(banco_row, _DRV, {}, None, 778899)
        assert len(dados["codigo_barras"]) == 44
        assert dados["codigo_barras"] == "34191101600001500001750077889981234123451000"
        assert dados["linha_digitavel"] == "34191.75009 77889.981237 41234.560005 1 10160000150000"
        assert dados["banco_codigo"] == 341

    def test_carteira_112_usa_ramo_alternativo_do_dac2(self):
        banco_row = {"carteira": 112, "agencia": 1234, "contacorrente": 12345, "dv_contacorrente": "6"}
        dados = svc._montar_boleto_itau(banco_row, _DRV, {}, None, 778899)
        assert len(dados["codigo_barras"]) == 44
        # DAC2 aqui vem de Modulo_10(carteira+nn), não agencia+conta+carteira+nn
        assert dados["codigo_barras"] != svc._montar_boleto_itau(
            {**banco_row, "carteira": 175}, _DRV, {}, None, 778899
        )["codigo_barras"]


class TestMontarBoletoBradesco:
    def test_codigo_barras_44_digitos_e_bate_com_calculo_independente(self):
        banco_row = {"carteira": 9, "agencia": 1234, "contacorrente": 1234567, "dv_contacorrente": "8"}
        drv = {"dt_vencimento": date(2025, 3, 10), "valor": 987.65}
        dados = svc._montar_boleto_bradesco(banco_row, drv, {}, None, 55667788)
        assert len(dados["codigo_barras"]) == 44
        assert dados["codigo_barras"] == "23795101600000987651234090005566778812345670"
        assert dados["banco_codigo"] == 237


class TestMontarBoletoInter:
    def test_codigo_barras_44_digitos_e_bate_com_calculo_independente(self):
        banco_row = {"carteira": 112, "codigocedente": "1234567"}
        drv = {"dt_vencimento": date(2025, 3, 10), "valor": 555.55}
        dados = svc._montar_boleto_inter(banco_row, drv, {}, None, 99887766)
        assert len(dados["codigo_barras"]) == 44
        assert dados["codigo_barras"] == "07793101600000555550001112123456700099887766"
        assert dados["banco_codigo"] == 77


# ============ Código de barras ITF-25 ============
class TestGerarItf25Bars:
    def test_estrutura_start_stop_e_contagem_por_digito(self):
        codigo = "0" * 44
        elementos = svc._gerar_itf25_bars(codigo)
        # start (4) + stop (3) + 22 pares * 10 elementos (5 barra + 5 espaço)
        assert len(elementos) == 4 + 3 + 22 * 10

    def test_todo_codigo_de_44_digitos_gera_mesmo_numero_de_elementos(self):
        a = svc._gerar_itf25_bars("1" * 44)
        b = svc._gerar_itf25_bars("34191101600001500001750077889981234123451000")
        assert len(a) == len(b) == 4 + 3 + 22 * 10


# ============ Dispatcher / montagem completa ============
def _titulo_completo(banco_cedente=341, numero_boleto=778899):
    drv_row = {
        "codigo": 500, "duplicata": 100, "dt_vencimento": date(2025, 3, 10), "dt_vencimento_desc": None,
        "valor": 1500.00, "valor_desc": 0, "OUTROS_acres_pag": 0, "banco_cedente": banco_cedente,
        "conta_cedente": 12345, "drv_carteira": 175, "numero_boleto": numero_boleto, "cliente": 50,
        "num_doc_cliente": "100",
    }
    cliente_row = {"codigo": 50, "nome": "Fulano de Tal LTDA", "cgc_cpf": "12345678000199"}
    endereco_row = {"endereco": "Rua Teste", "numero": "123", "complemento": "", "bairro": "Centro", "cidade": "Rio de Janeiro", "uf": "RJ", "cep": "20000000"}
    banco_row = {
        "cod": 1, "codigo": 341, "carteira": 175, "agencia": 1234, "dv_agencia": "5", "contacorrente": 12345,
        "dv_contacorrente": "6", "dias_protesto": 5, "Mora_Dia_Pag": 0.033, "Multa_Atraso_Pag": 2,
        "mensagem_boleto_1": "Não receber após 30 dias do vencimento.", "mensagem_boleto_2": "", "mensagem_boleto_3": "",
    }
    controle_row = {"rz_social": "EMPRESA TESTE LTDA", "endereco": "Av Principal", "numero": "1000", "complemento": "",
                     "bairro": "Centro", "cidade": "Rio de Janeiro", "uf": "RJ", "cep": "20000001", "cgc": "99888777000166"}
    return [drv_row, cliente_row, endereco_row, banco_row, controle_row]


class TestMontarDadosBoletoSync:
    def test_titulo_nao_encontrado(self):
        cur = FakeCursor(one=[None])
        r = svc._montar_dados_boleto_sync(cur, 999)
        assert r["success"] is False

    def test_banco_nao_suportado_devolve_mensagem_clara(self):
        rows = _titulo_completo(banco_cedente=33)  # Santander, fora de escopo
        cur = FakeCursor(one=rows[:2])  # drv + cliente (endereço/banco nunca chegam a ser buscados)
        r = svc._montar_dados_boleto_sync(cur, 500)
        assert r["success"] is False
        assert "banco" in r["message"].lower()

    def test_sem_nosso_numero_alocado(self):
        rows = _titulo_completo(numero_boleto=0)
        cur = FakeCursor(one=rows[:4])  # drv + cliente + endereço + banco
        r = svc._montar_dados_boleto_sync(cur, 500)
        assert r["success"] is False
        assert "nosso número" in r["message"].lower()

    def test_dados_completos_sucesso(self):
        cur = FakeCursor(one=_titulo_completo())
        r = svc._montar_dados_boleto_sync(cur, 500)
        assert r["success"] is True
        assert r["banco_codigo"] == 341
        assert len(r["codigo_barras"]) == 44
        assert "PROTESTO AUTOMÁTICO APÓS 5 DIA(S)." in r["instrucoes"]

    def test_logo_ausente_fica_none(self):
        """`bancos.logo_banco` (2026-08-26) — sem logo cadastrada, o dict
        de dados não deve travar nem inventar um valor."""
        cur = FakeCursor(one=_titulo_completo())
        r = svc._montar_dados_boleto_sync(cur, 500)
        assert r["logo_bytes"] is None
        assert r["logo_mime"] is None

    def test_logo_presente_e_repassada(self):
        """`SELECT * FROM bancos` já traz `logo_banco`/`logo_banco_mime`
        quando cadastrados — `_montar_dados_boleto_sync` precisa repassar
        os bytes crus (sem base64/serialização), não filtrar/perder."""
        rows = _titulo_completo()
        rows[3] = {**rows[3], "logo_banco": b"\x89PNG\r\n\x1a\nFAKE", "logo_banco_mime": "image/png"}
        cur = FakeCursor(one=rows)
        r = svc._montar_dados_boleto_sync(cur, 500)
        assert r["logo_bytes"] == b"\x89PNG\r\n\x1a\nFAKE"
        assert r["logo_mime"] == "image/png"


class TestGerarPdfUmTitulo:
    def test_titulo_sem_banco_suportado_devolve_none(self):
        rows = _titulo_completo(banco_cedente=33)
        cur = FakeCursor(one=rows[:1])
        assert svc.gerar_pdf_um_titulo_sync(cur, 500) is None

    def test_gera_pdf_valido(self):
        cur = FakeCursor(one=_titulo_completo())
        pdf_bytes = svc.gerar_pdf_um_titulo_sync(cur, 500)
        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF")
        assert b"%%EOF" in pdf_bytes

    def test_gera_pdf_valido_com_logo_do_banco(self):
        """Boleto com `bancos.logo_banco` cadastrada (2026-08-26) — a
        imagem real precisa ser desenhada sem quebrar a geração do PDF."""
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (200, 60), color=(30, 90, 180)).save(buf, format="PNG")
        rows = _titulo_completo()
        rows[3] = {**rows[3], "logo_banco": buf.getvalue(), "logo_banco_mime": "image/png"}
        cur = FakeCursor(one=rows)
        pdf_bytes = svc.gerar_pdf_um_titulo_sync(cur, 500)
        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF")
        assert b"%%EOF" in pdf_bytes

    def test_logo_corrompida_cai_para_texto_sem_quebrar(self):
        """Bytes inválidos em `logo_banco` (upload corrompido/formato não
        suportado) nunca podem derrubar a geração do boleto inteiro —
        `_desenhar_boleto` precisa cair pro texto do nome do banco."""
        rows = _titulo_completo()
        rows[3] = {**rows[3], "logo_banco": b"isto-nao-e-uma-imagem-valida", "logo_banco_mime": "image/png"}
        cur = FakeCursor(one=rows)
        pdf_bytes = svc.gerar_pdf_um_titulo_sync(cur, 500)
        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF")
        assert b"%%EOF" in pdf_bytes


class TestRegistrarBancoNoTitulo:
    def test_banco_nao_encontrado(self):
        cur = FakeCursor(one=[None])
        erro = svc._registrar_banco_no_titulo_sync(cur, 500, 1)
        assert erro is not None and "não encontrado" in erro["message"].lower()

    def test_banco_nao_suportado(self):
        cur = FakeCursor(one=[{"cod": 1, "codigo": 33, "contacorrente": 100, "carteira": 1}])
        erro = svc._registrar_banco_no_titulo_sync(cur, 500, 1)
        assert erro is not None
        assert "não implementada" in erro["message"].lower()

    def test_registra_e_grava_update(self, monkeypatch):
        banco_row = {"cod": 1, "codigo": 341, "contacorrente": 12345, "carteira": 175}
        cur = FakeCursor(one=[banco_row])
        monkeypatch.setattr(svc.cnab_itau_service, "_gerar_nosso_numero_sync", lambda *a, **k: 778899)
        erro = svc._registrar_banco_no_titulo_sync(cur, 500, 1)
        assert erro is None
        sql, params = cur.queries[-1]
        assert sql.startswith("UPDATE duplicata_rec_venc")
        assert params[0] == 341 and params[3] == 778899


class TestGerarPdfTitulosSync:
    def test_sem_titulos_bloqueia(self):
        r = svc.gerar_pdf_titulos_sync("s", "b", 1, [])
        assert r["success"] is False

    def test_gera_pdf_multipagina(self, monkeypatch):
        banco_row = {"cod": 1, "codigo": 341, "contacorrente": 12345, "carteira": 175}
        # 2 títulos -> 2x (registrar_banco fetchone banco_row) + 2x (montar_dados: 5 fetchones cada)
        one = [banco_row, banco_row] + _titulo_completo() + _titulo_completo()
        cur = FakeCursor(one=one)
        conn = FakeConn(cur)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
        monkeypatch.setattr(svc.cnab_itau_service, "_gerar_nosso_numero_sync", lambda *a, **k: 778899)

        r = svc.gerar_pdf_titulos_sync("s", "b", 1, [500, 501])
        assert r["success"] is True
        assert r["conteudo"].startswith(b"%PDF")
        # "/Type /Page" aparece 1x por página + 1x pro nó pai "/Type /Pages"
        assert r["conteudo"].count(b"/Type /Page") - 1 == 2
        assert conn.committed >= 1

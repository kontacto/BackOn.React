"""Testes unitários do gerador de Recibo em PDF (ver
services/recibo_pdf_service.py)."""
import services.recibo_pdf_service as svc


class TestFmtMoeda:
    def test_formata_com_milhar_e_decimal_br(self):
        assert svc._fmt_moeda(1234.5) == "1.234,50"

    def test_zero(self):
        assert svc._fmt_moeda(0) == "0,00"


class TestFmtDataBr:
    def test_converte_iso_para_br(self):
        assert svc._fmt_data_br("2026-09-10") == "10/09/2026"

    def test_none_devolve_vazio(self):
        assert svc._fmt_data_br(None) == ""

    def test_formato_sem_3_partes_devolve_original(self):
        assert svc._fmt_data_br("2026-09") == "2026-09"


class TestQuebrarLinhas:
    def test_texto_curto_vira_1_linha(self):
        from reportlab.pdfgen import canvas
        from io import BytesIO

        c = canvas.Canvas(BytesIO())
        linhas = svc._quebrar_linhas(c, "texto curto", 500, "Helvetica", 11)
        assert linhas == ["texto curto"]

    def test_texto_longo_quebra_em_varias_linhas(self):
        from reportlab.pdfgen import canvas
        from io import BytesIO

        c = canvas.Canvas(BytesIO())
        texto = "palavra " * 40
        linhas = svc._quebrar_linhas(c, texto, 100, "Helvetica", 11)
        assert len(linhas) > 1
        for linha in linhas:
            assert c.stringWidth(linha, "Helvetica", 11) <= 100


class TestGerarReciboPdfBytes:
    DADOS = {
        "numero": "042/2026", "recebemos": "Cliente Teste LTDA", "valor": 1500.0,
        "valor_extenso": "hum mil e quinhentos reais", "referente": "mensalidade de Setembro/2026",
        "data": "2026-09-10", "assinatura": "EMPRESA TESTE LTDA",
    }

    def test_gera_pdf_valido(self):
        pdf_bytes = svc.gerar_recibo_pdf_bytes(self.DADOS)
        assert pdf_bytes.startswith(b"%PDF")
        assert b"%%EOF" in pdf_bytes

    def test_funciona_com_dados_faltando(self):
        # nunca deve lançar mesmo com campos ausentes -- só omite o conteúdo
        pdf_bytes = svc.gerar_recibo_pdf_bytes({})
        assert pdf_bytes.startswith(b"%PDF")

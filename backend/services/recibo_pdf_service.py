"""Recibo de Pagamento em PDF — anexo real no e-mail de "Envio de
Cobrança" de Contratos, pra contratos do tipo Recibo (`tipo_cobranca=0`).
Conteúdo idêntico ao que `frontend/app/contrato-faturar.tsx`'s "Gerar
Recibo" já mostra via HTML impresso no navegador (`printHtml`) — mesmo
texto, agora também disponível como PDF gerado no backend, pra poder ser
anexado a um e-mail (o navegador não tem como gerar um PDF de servidor).

**Achado real, 2026-08-26**: diferente do Boleto (`boleto_pdf_service.py`,
que só ANEXA um boleto já registrado, nunca gera um novo na hora), a
tabela `Recibos` não tem NENHUMA coluna de referência de volta pra
`comanda`/`contrato`/`cobrancas_enviadas` (confirmado ao vivo, schema
real de KONTACTO TESTE — só `codigo, recebemos, referente, valor, data,
assinatura, seq, ano, situacao`). **Resposta de Leandro (2026-08-26)**:
"recibo de contrato é o próprio número da comanda... não precisa criar
coluna, pois o controle é o número da comanda, que já é controlado no
sistema" — o PDF gerado por este módulo pro anexo de e-mail usa o
NÚMERO DA COMANDA como identificador (`contratos_service.
_montar_recibo_para_anexo_sync`, função só-leitura, nunca grava em
`Recibos`) — reenviar o e-mail sempre produz o mesmo PDF, idempotente,
sem precisar de coluna nova. O Recibo NUMERADO oficial
(`Recibos`/`Controle.Seq_Recibo`, `contratos_service._gerar_recibo_
sync`) continua existindo só pro botão "Gerar Recibo" (Faturar
Contratos) — os dois fluxos são independentes.
"""
from io import BytesIO
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _fmt_moeda(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt_data_br(iso: Optional[str]) -> str:
    if not iso:
        return ""
    partes = iso.split("-")
    if len(partes) != 3:
        return iso
    ano, mes, dia = partes
    return f"{dia}/{mes}/{ano}"


def _quebrar_linhas(c: canvas.Canvas, texto: str, largura_max: float, fonte: str, tamanho: float) -> list[str]:
    palavras = (texto or "").split()
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
        candidata = f"{atual} {palavra}".strip()
        if c.stringWidth(candidata, fonte, tamanho) <= largura_max:
            atual = candidata
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas or [""]


def gerar_recibo_pdf_bytes(dados: dict) -> bytes:
    """`dados` no mesmo formato devolvido por `contratos_service.
    _gerar_recibo_sync`: `numero`, `recebemos`, `valor`, `valor_extenso`,
    `referente`, `data` (ISO `yyyy-mm-dd`), `assinatura`."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    largura, altura = A4
    esq = 25 * mm
    dir_ = largura - 25 * mm
    largura_util = dir_ - esq
    y = altura - 45 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(largura / 2, y, f"Recibo de Pagamento Nº {dados.get('numero', '')}")
    y -= 18 * mm

    def paragrafo(texto: str) -> None:
        nonlocal y
        for linha in _quebrar_linhas(c, texto, largura_util, "Helvetica", 11):
            c.setFont("Helvetica", 11)
            c.drawString(esq, y, linha)
            y -= 6.5 * mm
        y -= 3 * mm

    paragrafo(f"Recebemos de {dados.get('recebemos', '')}.")
    paragrafo(f"A importância de R$ {_fmt_moeda(float(dados.get('valor') or 0))} ({dados.get('valor_extenso', '')}).")
    paragrafo(f"Referente à {dados.get('referente', '')}")

    y -= 8 * mm
    c.setFont("Helvetica", 11)
    c.drawString(esq, y, _fmt_data_br(dados.get("data")))

    y -= 28 * mm
    c.line(largura / 2 - 40 * mm, y, largura / 2 + 40 * mm, y)
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawCentredString(largura / 2, y, dados.get("assinatura", ""))

    c.showPage()
    c.save()
    return buf.getvalue()

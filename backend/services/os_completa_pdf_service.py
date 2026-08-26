"""Impressão A4 "Completa" (não-fiscal) de O.S. — motor único de PDF,
reaproveitado por 3 usos: baixar/abrir no navegador (`GET /os-completo/
{codigo}/pdf`), anexo no "Enviar por Email" (`os_email_service.py`) e —
não WhatsApp: o envio por WhatsApp desta tela já existe (`WhatsappButton`,
`documentType="OS"`) e manda só texto, sem anexo — ver
`services/whatsapp/providers.py` ("Fase 1: somente mensagem de texto"),
limitação real da infraestrutura, não decisão deste módulo.

Referência: 2 modelos reais de impressão do legado VB6, enviados pelo
usuário 2026-08-26 — Assistência Técnica (bloco "Número de Série/Marca/
Mod") e Oficina/RJ PNEUS (bloco "Placa/Marca/Modelo/Ano/KM"). A variante é
decidida por `os.placa` não-vazio → Oficina, senão Assistência.

Este é o único gerador do "documento completo" — a impressão "não-fiscal"
térmica (`ReciboOSModal.tsx`, 80mm, gerada no FRONTEND via HTML+iframe)
continua existindo separadamente, mesmo padrão já usado hoje pra Pedido/
O.S. ("impressão normal" vs "impressão não-fiscal", confirmado pelo
usuário como já existente no app). Este PDF é a "impressão normal".

Estilo de desenho: `reportlab.pdfgen.canvas` manual (mesmo padrão de
`boleto_pdf_service.py`/`recibo_pdf_service.py`) — este projeto não usa
`reportlab.platypus` (Table/Paragraph) em lugar nenhum, então a tabela de
itens é desenhada linha a linha, com paginação manual quando não cabe.

Busca de dado 100% reaproveitada dos services já existentes e testados
por trás de `os-geral.tsx` (get_os_completo/list_itens/list_tempo/
list_formas_pagamento/list_equipamentos/get_empresa/cliente_resumo) —
nenhuma SQL nova pra ler o que essas telas já leem.
"""
import base64
from datetime import datetime
from io import BytesIO
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from db.connection import _open_conn
from services import (
    clientes_service,
    controle_service,
    email_cobranca_service,
    forma_pagamento_service,
    os_checklist_veiculo_service,
    os_completo_service,
    os_equipamento_service,
    os_itens_service,
    os_tempo_service,
)

_LARGURA, _ALTURA = A4
_ESQ = 15 * mm
_DIR = _LARGURA - 15 * mm


def _fmt_moeda(v) -> str:
    return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_data(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except Exception:
        return str(iso)


def _fmt_duracao(minutos: Optional[int]) -> str:
    """Réplica de `TempoGastoModal.tsx::fmtDuracao` — "Xh Ymin"."""
    if minutos is None:
        return ""
    h, m = divmod(int(minutos), 60)
    return f"{h}h {m}min" if h else f"{m}min"


def _texto(c: canvas.Canvas, x: float, y: float, texto: str, tamanho: float = 8, negrito: bool = False) -> None:
    c.setFont("Helvetica-Bold" if negrito else "Helvetica", tamanho)
    c.drawString(x, y, texto or "")


def _texto_label_valor(c: canvas.Canvas, x: float, y: float, label: str, valor: str, tamanho: float = 8) -> None:
    """Rótulo em negrito + valor em peso normal, na mesma linha — mesmo
    padrão já usado na pré-venda (Pedido/O.S.) pro par label:valor
    (ex.: "Número de Série:" em negrito, "KC1265" normal). Pedido
    explícito do usuário 2026-08-26 — vale pra todo par label:valor deste
    documento, e é o padrão a seguir também quando a impressão A4 do
    Pedido for construída (fora de escopo desta rodada)."""
    c.setFont("Helvetica-Bold", tamanho)
    c.drawString(x, y, label)
    c.setFont("Helvetica", tamanho)
    c.drawString(x + c.stringWidth(label, "Helvetica-Bold", tamanho), y, valor or "")


def _quebrar_linhas(c: canvas.Canvas, texto: str, largura_max: float, tamanho: float = 8) -> list[str]:
    """Quebra `texto` palavra a palavra pra caber em `largura_max` pontos —
    mesmo espírito de `recibo_pdf_service._quebrar_linhas`."""
    palavras = (texto or "").replace("\r\n", "\n").split(" ")
    linhas: list[str] = []
    atual = ""
    for p in palavras:
        if p == "\n" or "\n" in p:
            partes = p.split("\n")
            for i, parte in enumerate(partes):
                tentativa = f"{atual} {parte}".strip()
                if c.stringWidth(tentativa, "Helvetica", tamanho) <= largura_max:
                    atual = tentativa
                else:
                    if atual:
                        linhas.append(atual)
                    atual = parte
                if i < len(partes) - 1:
                    linhas.append(atual)
                    atual = ""
            continue
        tentativa = f"{atual} {p}".strip()
        if c.stringWidth(tentativa, "Helvetica", tamanho) <= largura_max:
            atual = tentativa
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def _truncar_largura(c: canvas.Canvas, texto: str, largura_max: float, fonte: str = "Helvetica", tamanho: float = 7.5) -> str:
    """Trunca `texto` (com "…") pela LARGURA real renderizada, não por
    contagem de caracteres — bug real achado ao vivo 2026-08-26 (preview
    enviado ao usuário): truncar por `[:52]` deixava a coluna "Descrição"
    invadir visualmente a coluna "Executor" sempre que o texto tinha
    caracteres largos/o complemento do item era longo, já que a largura
    de 52 caracteres em Helvetica 7.5pt passa da largura real disponível
    entre as colunas."""
    if c.stringWidth(texto, fonte, tamanho) <= largura_max:
        return texto
    reticencias = "…"
    lo, hi = 0, len(texto)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if c.stringWidth(texto[:mid] + reticencias, fonte, tamanho) <= largura_max:
            lo = mid
        else:
            hi = mid - 1
    return texto[:lo] + reticencias


async def _montar_dados_os_sync(servidor: str, banco: str, codigo: int) -> Optional[dict]:
    resp = await os_completo_service.get_os_completo(servidor, banco, codigo)
    if not resp.get("success"):
        return None
    os_row = resp["os"]

    itens_resp = await os_itens_service.list_itens(servidor, banco, codigo)
    tempos_resp = await os_tempo_service.list_tempo(servidor, banco, codigo)
    formas_resp = await forma_pagamento_service.list_formas_pagamento(servidor, banco, "OS", codigo)
    equip_resp = await os_equipamento_service.list_equipamentos(servidor, banco, codigo)
    empresa_resp = await controle_service.get_empresa(servidor, banco)
    cliente_resumo = None
    if os_row.get("cliente"):
        cr = await clientes_service.cliente_resumo(servidor, banco, os_row["cliente"])
        if cr.get("success"):
            cliente_resumo = cr

    # Checklist de Entrada de Veículo — só tem conteúdo real quando a O.S.
    # é de Oficina (tem placa); buscar incondicionalmente aqui é barato
    # (lista vazia pras demais) e mantém a decisão "desenha ou não" só em
    # `_desenhar_checklist_veiculo`, não espalhada por 2 lugares.
    checklist_resp = await os_checklist_veiculo_service.list_checklist(servidor, banco, codigo)

    return {
        "os": os_row,
        "itens": itens_resp.get("items") or [],
        "tempos": tempos_resp.get("items") or [],
        "formas": formas_resp.get("items") or [],
        "equipamentos": equip_resp.get("items") or [],
        "empresa": empresa_resp if empresa_resp.get("success") else {},
        "cliente_resumo": cliente_resumo,
        "checklist_veiculo": checklist_resp.get("items") or [],
        # Conclusão do checklist ("Concluir Checklist", `os_checklist`) —
        # quem revisou/quando/se não havia avaria — pedido explícito do
        # usuário 2026-08-26 ("marcar o atendente que marcou sem avaria
        # com os dados do veículo, atendente data e hora").
        "checklist_concluido": bool(checklist_resp.get("concluido")),
        "checklist_sem_avaria": bool(checklist_resp.get("sem_avaria")),
        "checklist_concluido_por": checklist_resp.get("concluido_por") or "",
        "checklist_concluido_data": checklist_resp.get("concluido_data"),
        "checklist_concluido_hora": checklist_resp.get("concluido_hora") or "",
    }


def _desenhar_cabecalho(c: canvas.Canvas, dados: dict) -> float:
    """Logo (se houver) + dados da empresa (centro) + caixa "O.S. Nº..."
    (direita). Devolve o `y` onde o conteúdo seguinte deve começar."""
    empresa = dados["empresa"]
    os_row = dados["os"]
    topo = _ALTURA - 15 * mm

    logo_b64 = empresa.get("logo_base64")
    if logo_b64:
        try:
            img_bytes = base64.b64decode(logo_b64)
            img = ImageReader(BytesIO(img_bytes))
            c.drawImage(img, _ESQ, topo - 20 * mm, width=28 * mm, height=20 * mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass  # logo corrompida/formato não suportado — segue sem ela, nunca quebra o PDF

    centro_x = _LARGURA / 2
    y = topo - 2
    nome = (empresa.get("fantasia") or empresa.get("rz_social") or "").upper()
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(centro_x, y, nome)
    y -= 12
    endereco = ", ".join([p for p in [empresa.get("endereco"), str(empresa.get("numero") or ""), empresa.get("complemento")] if p])
    c.setFont("Helvetica", 8)
    if endereco:
        c.drawCentredString(centro_x, y, endereco); y -= 10
    cidade = " - ".join([p for p in [empresa.get("bairro"), empresa.get("cidade"), empresa.get("uf")] if p])
    if cidade:
        c.drawCentredString(centro_x, y, f"{cidade}{'  CEP: ' + empresa['cep'] if empresa.get('cep') else ''}"); y -= 10
    tel = empresa.get("telefone")
    if tel:
        c.drawCentredString(centro_x, y, f"Tel: ({empresa.get('ddd') or ''}) {tel}"); y -= 10
    cgc = empresa.get("cgc")
    if cgc:
        c.drawCentredString(centro_x, y, f"CNPJ: {cgc}{'  IE: ' + empresa['inscr_est'] if empresa.get('inscr_est') else ''}")

    # Caixa "O.S. Nº" — canto superior direito. Réplica fiel do cabeçalho
    # real do legado (screenshot enviado pelo usuário 2026-08-26,
    # "quero igual"): "O.S" pequeno, "020513" grande logo abaixo (bem
    # juntos, mesma "família"), um respiro maior, depois data/hora e
    # status GRUDADOS entre si (mesmo espaçamento apertado dos dois),
    # com folga de verdade na margem superior/inferior da caixa — não
    # é distribuição uniforme (tentativa anterior, rejeitada: "não ficou
    # bom", "O.S" crescia demais e perdia a hierarquia visual do
    # original).
    caixa_larg, caixa_alt = 45 * mm, 26 * mm
    caixa_x, caixa_y = _DIR - caixa_larg, topo - caixa_alt + 6
    cx = caixa_x + caixa_larg / 2
    topo_caixa = caixa_y + caixa_alt
    c.setLineWidth(0.8)
    c.rect(caixa_x, caixa_y, caixa_larg, caixa_alt)

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(cx, topo_caixa - 18, "O.S")
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(cx, topo_caixa - 36, f"{os_row['codigo']:06d}")

    c.setFont("Helvetica", 8)
    abertura = f"{_fmt_data(os_row.get('data'))} - {os_row.get('hora') or ''}hs."
    c.drawCentredString(cx, caixa_y + 16, abertura)
    status = os_row.get("status_os_descricao") or os_row.get("situacao_label") or ""
    if status:
        c.drawCentredString(cx, caixa_y + 7, f"({status})")

    return topo - caixa_alt - 8


def _desenhar_cliente_equipamento(c: canvas.Canvas, dados: dict, y: float) -> float:
    os_row = dados["os"]
    resumo = dados["cliente_resumo"] or {}
    equipamentos = dados["equipamentos"]
    meio = _LARGURA / 2

    c.setLineWidth(0.6)
    c.line(_ESQ, y, _DIR, y)
    y_topo_borda = y
    y -= 12
    y_topo_linha = y

    # ---- Cliente (esquerda) ----
    c.setFont("Helvetica-Bold", 9)
    c.drawString(_ESQ, y, f"{os_row.get('cliente_nome') or ''} ({os_row.get('cliente') or ''})")
    yl = y - 10
    tel = resumo.get("telefone")
    if tel:
        _texto_label_valor(c, _ESQ, yl, "Tel(s): ", tel); yl -= 10
    endereco = resumo.get("endereco")
    if endereco:
        for linha in _quebrar_linhas(c, endereco, meio - _ESQ - 8, 8):
            _texto(c, _ESQ, yl, linha); yl -= 10

    # ---- Equipamento (Assistência) ou Veículo (Oficina), direita ----
    x2 = meio + 4 * mm
    yr = y
    is_oficina = bool((os_row.get("placa") or "").strip())
    if is_oficina:
        placa = os_row.get("placa") or ""
        marca = os_row.get("marca") or ""
        modelo = os_row.get("modelo") or ""
        _texto_label_valor(c, x2, yr, "Placa: ", placa); yr -= 10
        if marca or modelo:
            _texto_label_valor(c, x2, yr, "Marca/Modelo: ", f"{marca} {modelo}".strip()); yr -= 10
        ano = os_row.get("ano")
        km = os_row.get("km")
        if ano:
            _texto_label_valor(c, x2, yr, "Ano: ", str(ano)); yr -= 10
        if km is not None:
            _texto_label_valor(c, x2, yr, "KM: ", str(km)); yr -= 10
    elif len(equipamentos) >= 2:
        # Mais de 1 equipamento (Assistência Técnica, `os_equipamento`) —
        # sem precedente no legado (o modelo de referência só cobre 1
        # equipamento por O.S.). Este box vira um inventário compacto
        # (nº de série + marca/modelo por linha); o detalhe de "o que o
        # cliente relatou"/"o que foi executado" POR equipamento vai na
        # seção dedicada logo abaixo (`_desenhar_equipamentos_detalhe`),
        # não aqui — aqui só uma lista rápida de "o que está na O.S.".
        _texto(c, x2, yr, f"{len(equipamentos)} equipamentos nesta O.S.:", negrito=True); yr -= 10
        # Cap deliberado — bug real achado ao vivo 2026-08-26 (usuário
        # pediu pra testar com muitos equipamentos): listar TODOS aqui
        # sem limite empurra "Técnico Responsável"/"Atendente" pra baixo
        # sem controle e pode fazer esta caixa-resumo crescer mais que a
        # página inteira. Esta caixa é só um resumo "de relance" — o
        # detalhe completo (defeito/serviço) de CADA equipamento já vai
        # na seção "Equipamento N" logo abaixo, com paginação própria; a
        # lista aqui mostra os primeiros e avisa quantos ficaram de fora.
        _MAX_EQUIP_RESUMO = 6
        for i, eq in enumerate(equipamentos[:_MAX_EQUIP_RESUMO], start=1):
            serie = (eq.get("numero_de_serie") or "").strip()
            mm_ = " ".join([p for p in [eq.get("marca_descricao"), eq.get("modelo_descricao")] if p])
            linha = f"{i}. {serie}{' — ' + mm_ if mm_ else ''}".strip()
            _texto(c, x2, yr, linha, tamanho=7.5); yr -= 9
        if len(equipamentos) > _MAX_EQUIP_RESUMO:
            restantes = len(equipamentos) - _MAX_EQUIP_RESUMO
            _texto(c, x2, yr, f"+ {restantes} outro(s) — ver detalhamento abaixo", tamanho=7.5); yr -= 9
    else:
        equip = equipamentos[0] if equipamentos else None
        num_serie = (equip.get("numero_de_serie") if equip else None) or os_row.get("numero_de_serie") or ""
        marca = (equip.get("marca_descricao") if equip else None) or os_row.get("marca") or ""
        modelo = (equip.get("modelo_descricao") if equip else None) or os_row.get("modelo") or ""
        if num_serie:
            _texto_label_valor(c, x2, yr, "Número de Série: ", num_serie); yr -= 10
        if marca:
            _texto_label_valor(c, x2, yr, "Marca: ", marca); yr -= 10
        if modelo:
            _texto_label_valor(c, x2, yr, "Mod: ", modelo); yr -= 10
    tecnico = os_row.get("tecnico_responsavel_nome")
    if tecnico:
        _texto_label_valor(c, x2, yr, "Técnico Responsável: ", tecnico); yr -= 10
    atendente = os_row.get("atendente_nome")
    if atendente:
        _texto_label_valor(c, x2, yr, "Atendente: ", f"{atendente}."); yr -= 10

    y_final = min(yl, yr) - 4
    c.line(_ESQ, y_final, _DIR, y_final)
    # Linha vertical separando Cliente | Equipamento/Veículo — réplica do
    # cabeçalho real do legado (screenshot enviado pelo usuário
    # 2026-08-26), entre as duas bordas horizontais desta seção.
    c.line(meio, y_topo_borda, meio, y_final)
    return y_final - 12


_Y_MIN_PAGINA = 30 * mm


def _novo_topo_pagina(c: canvas.Canvas, codigo: int) -> float:
    """Abre uma nova página E carimba "O.S. Nº .../Página N" no topo —
    pedido explícito do usuário 2026-08-26 ("o número da OS e página tem
    que constar nas páginas subsequentes"): sem isso, uma página de
    continuação (2ª em diante) saía sem NENHUMA referência de qual O.S.
    é aquela nem em que página está — só a última página (rodapé) tinha
    esse dado. Devolve o `y` onde o conteúdo deve continuar, já abaixo
    do carimbo."""
    c.showPage()
    topo = _ALTURA - 15 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(_ESQ, topo, f"O.S. Nº {codigo:06d}")
    c.setFont("Helvetica", 8)
    c.drawRightString(_DIR, topo, f"Página {c.getPageNumber()}")
    c.setLineWidth(0.4)
    c.line(_ESQ, topo - 4, _DIR, topo - 4)
    return topo - 16


def _quebra_pagina_se_preciso(c: canvas.Canvas, y: float, codigo: int, minimo: float = _Y_MIN_PAGINA) -> float:
    if y < minimo:
        return _novo_topo_pagina(c, codigo)
    return y


def _desenhar_um_bloco_descreve(c: canvas.Canvas, titulo: str, descricao: str, resumo: str, y: float, codigo: int) -> float:
    largura_max = _DIR - _ESQ
    if titulo:
        y = _quebra_pagina_se_preciso(c, y, codigo)
        _texto(c, _ESQ, y, titulo, negrito=True)
        y -= 11
    if descricao:
        for linha in _quebrar_linhas(c, descricao, largura_max, 8):
            y = _quebra_pagina_se_preciso(c, y, codigo)
            _texto(c, _ESQ, y, linha); y -= 10
    if descricao and resumo:
        y -= 4
    if resumo:
        for linha in _quebrar_linhas(c, resumo, largura_max, 8):
            y = _quebra_pagina_se_preciso(c, y, codigo)
            _texto(c, _ESQ, y, linha); y -= 10
    return y


def _desenhar_cliente_descreve(c: canvas.Canvas, dados: dict, y: float) -> float:
    """"Cliente Descreve / Serviço Executado" — no modelo de referência
    (1 equipamento) é um bloco só, no nível da própria O.S.
    (`descricao_cliente`/`resumo`). **Com 2+ equipamentos** (Assistência
    Técnica, `os_equipamento`, sem precedente no legado) vira um bloco
    POR equipamento, usando os campos próprios de cada linha
    (`defeito_reclamado`/`servico_executado`) — mais preciso que repetir
    o texto genérico da O.S. pra cada equipamento, e é a informação que
    de fato foi registrada por equipamento nesta migração."""
    os_row = dados["os"]
    equipamentos = dados["equipamentos"]

    if len(equipamentos) >= 2:
        for i, eq in enumerate(equipamentos, start=1):
            serie = (eq.get("numero_de_serie") or "").strip()
            mm_ = " ".join([p for p in [eq.get("marca_descricao"), eq.get("modelo_descricao")] if p])
            cabecalho = f"Equipamento {i}{' — ' + serie if serie else ''}{' (' + mm_ + ')' if mm_ else ''}:"
            defeito = (eq.get("defeito_reclamado") or "").strip()
            executado = (eq.get("servico_executado") or "").strip()
            if not defeito and not executado:
                continue
            y = _desenhar_um_bloco_descreve(c, cabecalho, defeito, executado, y, os_row["codigo"])
            y -= 8
        return y

    descricao = (os_row.get("descricao_cliente") or "").strip()
    resumo = (os_row.get("resumo") or "").strip()
    if not descricao and not resumo:
        return y
    y = _desenhar_um_bloco_descreve(c, "Cliente Descreve / Serviço Executado:", descricao, resumo, y, os_row["codigo"])
    return y - 8


_COL_CODIGO, _COL_DESC, _COL_EXEC, _COL_QTD, _COL_PRECO, _COL_TOTAL = (
    _ESQ, _ESQ + 22 * mm, _ESQ + 95 * mm, _ESQ + 130 * mm, _ESQ + 150 * mm, _ESQ + 172 * mm,
)
# Largura disponível de cada coluna de texto livre (com 3pt de folga antes
# da coluna seguinte) — usada por `_truncar_largura` em vez de contagem de
# caracteres fixa (ver docstring da função pro bug real que isso corrige).
_LARG_COL_CODIGO = _COL_DESC - _COL_CODIGO - 3
_LARG_COL_DESC = _COL_EXEC - _COL_DESC - 3
_LARG_COL_EXEC = _COL_QTD - _COL_EXEC - 3


def _desenhar_cabecalho_tabela_itens(c: canvas.Canvas, y: float) -> float:
    c.setFont("Helvetica-Bold", 8)
    c.drawString(_COL_CODIGO, y, "Código")
    c.drawString(_COL_DESC, y, "Descrição dos Serviços")
    c.drawString(_COL_EXEC, y, "Executor")
    c.drawRightString(_COL_QTD + 10 * mm, y, "Qtd/Horas")
    c.drawRightString(_COL_PRECO + 12 * mm, y, "Preço")
    c.drawRightString(_DIR, y, "Total")
    y -= 4
    c.setLineWidth(0.6)
    c.line(_ESQ, y, _DIR, y)
    return y - 10


_TIPO_AVARIA_LABEL = {
    "AMASSADO": "Amassado",
    "ARRANHAO": "Arranhão",
    "QUEBRADO": "Quebrado",
    "FALTANDO": "Faltando",
    "OUTRO": "Outro",
}


def _desenhar_diagrama_veiculo(c: canvas.Canvas, x: float, y_topo: float, largura: float, altura: float) -> None:
    """Silhueta vetorial simples do veículo visto de cima — corpo
    (retângulo de cantos arredondados) + 4 rodas (retângulos nos cantos)
    + linha do para-brisa marcando a frente. Decisão já confirmada com o
    usuário via `AskUserQuestion` ("Desenho vetorial simples
    (Recomendado)") — não é fac-símile do documento de referência
    (4 vistas + silhueta detalhada), propositalmente mais simples."""
    c.setLineWidth(1)
    corpo_x = x + largura * 0.12
    corpo_larg = largura * 0.76
    c.roundRect(corpo_x, y_topo - altura, corpo_larg, altura, 6, stroke=1, fill=0)
    roda_larg, roda_alt = 5, 14
    c.setFillColorRGB(0, 0, 0)
    for fx in (corpo_x - 1, corpo_x + corpo_larg - roda_larg + 1):
        for fy_frac in (0.16, 0.72):
            fy = y_topo - altura * fy_frac - roda_alt / 2
            c.rect(fx, fy, roda_larg, roda_alt, stroke=1, fill=1)
    c.line(corpo_x + 6, y_topo - altura * 0.28, corpo_x + corpo_larg - 6, y_topo - altura * 0.28)
    c.setFont("Helvetica", 6)
    c.drawCentredString(x + largura / 2, y_topo + 4, "FRENTE")


def _desenhar_checklist_veiculo(c: canvas.Canvas, dados: dict, y: float, codigo: int) -> float:
    """Checklist de Entrada de Veículo — pedido explícito do usuário
    2026-08-26, sem precedente no legado (documento de referência tinha
    perguntas fixas Sim/Não/Reparar; aqui cada marcação é dinâmica, um
    toque no diagrama do frontend — `ChecklistVeiculoDiagrama.tsx`).

    Só desenha quando a O.S. é de Oficina (tem placa — mesmo critério
    `is_oficina` já usado em `_desenhar_cliente_equipamento`) **e** está
    Aberta (`situacao == 'A'`) — o checklist é feito NA ENTRADA do
    veículo, reimprimir depois de Fechada/Faturada/Cancelada não faz
    sentido (a marcação já não pode mais ser alterada nesse ponto, ver
    `os_checklist_veiculo_service._add_item_sync`). Fora disso, é um
    no-op — `y` devolvido sem alteração. Chamada incondicionalmente no
    fim de `gerar_pdf_os_sync`; é esta função que decide sozinha se há
    o que desenhar, não o chamador."""
    os_row = dados["os"]
    if not (os_row.get("placa") or "").strip():
        return y
    if (os_row.get("situacao") or "").strip().upper() != "A":
        return y

    y = _novo_topo_pagina(c, codigo)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(_ESQ, y, "Checklist de Entrada do Veículo")
    y -= 14

    # Dados do veículo repetidos aqui (já aparecem na 1ª página, seção
    # "Veículo") — pedido explícito do usuário 2026-08-26 ("marcar...
    # com os dados do veículo"): esta página funciona como um registro
    # autocontido de vistoria, sem depender de olhar a página 1.
    veiculo_txt = (os_row.get("placa") or "").strip()
    marca_modelo = " ".join([p for p in [os_row.get("marca"), os_row.get("modelo")] if p]).strip()
    if marca_modelo:
        veiculo_txt = f"{veiculo_txt} — {marca_modelo}"
    _texto_label_valor(c, _ESQ, y, "Veículo: ", veiculo_txt, tamanho=8)
    y -= 16

    largura_diag, altura_diag = 90 * mm, 55 * mm
    x_diag = _ESQ
    y_topo_diag = y
    _desenhar_diagrama_veiculo(c, x_diag, y_topo_diag, largura_diag, altura_diag)

    marcacoes = dados.get("checklist_veiculo") or []
    for i, m in enumerate(marcacoes, start=1):
        px = x_diag + float(m["pos_x"]) * largura_diag
        py = y_topo_diag - float(m["pos_y"]) * altura_diag
        c.setFillColorRGB(0.82, 0.12, 0.12)
        c.circle(px, py, 5.5, stroke=1, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(px, py - 2.5, str(i))
    c.setFillColorRGB(0, 0, 0)

    x_legenda = x_diag + largura_diag + 10 * mm
    largura_legenda = _DIR - x_legenda
    y_legenda = y_topo_diag
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x_legenda, y_legenda, "Avarias marcadas na entrada:")
    y_legenda -= 12
    if not marcacoes:
        c.setFont("Helvetica", 8)
        c.drawString(x_legenda, y_legenda, "Nenhuma avaria marcada.")
        y_legenda -= 10
    else:
        c.setFont("Helvetica", 7.5)
        for i, m in enumerate(marcacoes, start=1):
            tipo = _TIPO_AVARIA_LABEL.get((m.get("tipo_avaria") or "").upper(), m.get("tipo_avaria") or "")
            descricao = (m.get("descricao") or "").strip()
            texto = f"{i}. {tipo}" + (f" — {descricao}" if descricao else "")
            for linha in _quebrar_linhas(c, texto, largura_legenda, 7.5):
                if y_legenda < _Y_MIN_PAGINA:
                    y_legenda = _novo_topo_pagina(c, codigo)
                c.drawString(x_legenda, y_legenda, linha)
                y_legenda -= 9

    y = min(y_topo_diag - altura_diag, y_legenda) - 14
    y = _quebra_pagina_se_preciso(c, y, codigo)
    c.setLineWidth(0.4)
    c.line(_ESQ, y, _DIR, y)
    y -= 12
    if dados.get("checklist_concluido"):
        c.setFont("Helvetica-Bold", 8)
        if dados.get("checklist_sem_avaria"):
            c.drawString(_ESQ, y, "Nenhuma avaria encontrada na entrada do veículo.")
            y -= 11
        atendente = dados.get("checklist_concluido_por") or "—"
        data_txt = _fmt_data(dados.get("checklist_concluido_data"))
        hora_txt = dados.get("checklist_concluido_hora") or ""
        c.setFont("Helvetica", 8)
        c.drawString(_ESQ, y, f"Vistoriado por {atendente} em {data_txt}{' às ' + hora_txt + 'hs.' if hora_txt else '.'}")
        y -= 10
    else:
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(_ESQ, y, "Checklist ainda não concluído.")
        y -= 10

    return y - 4


def gerar_pdf_os_sync(dados: dict) -> bytes:
    """Desenha o documento completo (paginação manual da tabela de
    itens quando não cabe numa página só) e devolve os bytes do PDF."""
    os_row = dados["os"]
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    y = _desenhar_cabecalho(c, dados)
    y = _desenhar_cliente_equipamento(c, dados, y)
    y = _desenhar_cliente_descreve(c, dados, y)

    y_min_pagina = _Y_MIN_PAGINA
    y = _desenhar_cabecalho_tabela_itens(c, y)
    c.setFont("Helvetica", 7.5)
    for it in dados["itens"]:
        if y < y_min_pagina:
            y = _novo_topo_pagina(c, os_row["codigo"])
            y = _desenhar_cabecalho_tabela_itens(c, y)
            c.setFont("Helvetica", 7.5)
        desc = it.get("descricao") or ""
        if it.get("complemento"):
            desc = f"{desc} — {it['complemento']}"
        c.drawString(_COL_CODIGO, y, _truncar_largura(c, str(it.get("produto") or ""), _LARG_COL_CODIGO))
        c.drawString(_COL_DESC, y, _truncar_largura(c, desc, _LARG_COL_DESC))
        c.drawString(_COL_EXEC, y, _truncar_largura(c, it.get("executor_nome") or "", _LARG_COL_EXEC))
        c.drawRightString(_COL_QTD + 10 * mm, y, f"{float(it.get('qtd') or 0):.2f}".replace(".", ","))
        c.drawRightString(_COL_PRECO + 12 * mm, y, _fmt_moeda(it.get("valor_unitario")))
        c.drawRightString(_DIR, y, _fmt_moeda(it.get("total")))
        y -= 11

    if y < y_min_pagina + 40 * mm:
        y = _novo_topo_pagina(c, os_row["codigo"])

    y -= 6
    c.setLineWidth(0.6)
    c.line(_ESQ, y, _DIR, y)
    y -= 12

    subtotal = sum(float(i.get("qtd") or 0) * float(i.get("p_normal") or 0) for i in dados["itens"])
    desconto = sum(float(i.get("qtd") or 0) * float(i.get("desconto") or 0) for i in dados["itens"]) - \
        sum(float(i.get("qtd") or 0) * float(i.get("acrescimo") or 0) for i in dados["itens"])
    a_pagar = float(os_row.get("total") or 0)
    if desconto > 0:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(_ESQ, y, "Subtotal")
        c.drawCentredString(_LARGURA / 2, y, "Descontos")
        c.drawRightString(_DIR, y, "À Pagar")
        y -= 12
        c.setFont("Helvetica", 9)
        c.drawString(_ESQ, y, f"R$ {_fmt_moeda(subtotal)}")
        c.drawCentredString(_LARGURA / 2, y, f"R$ {_fmt_moeda(desconto)}")
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(_DIR, y, f"R$ {_fmt_moeda(a_pagar)}")
    else:
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(_DIR - 32 * mm, y, "À Pagar")
        c.drawRightString(_DIR, y, f"R$ {_fmt_moeda(a_pagar)}")
    y -= 18

    c.setLineWidth(0.6)
    c.line(_ESQ, y, _DIR, y)
    y -= 12
    c.setFont("Helvetica-Bold", 8)
    c.drawString(_ESQ, y, "Forma(s) de Pagamento:")
    y -= 10
    c.setFont("Helvetica", 8)
    for f in dados["formas"]:
        c.drawString(_ESQ, y, f.get("descricao") or f.get("forma_pag") or "")
        c.drawRightString(_DIR, y, f"R$ {_fmt_moeda(f.get('valor'))}")
        y -= 10

    tempos = dados["tempos"]
    if tempos:
        y -= 6
        c.setLineWidth(0.4)
        c.line(_ESQ, y, _DIR, y)
        y -= 10
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(_ESQ, y, "Data")
        c.drawString(_ESQ + 25 * mm, y, "Chegada")
        c.drawString(_ESQ + 50 * mm, y, "Saída")
        c.drawString(_ESQ + 75 * mm, y, "Hrs")
        c.drawString(_ESQ + 95 * mm, y, "Técnico")
        y -= 10
        c.setFont("Helvetica", 7.5)
        total_min = 0
        for t in tempos:
            c.drawString(_ESQ, y, _fmt_data(t.get("data")))
            c.drawString(_ESQ + 25 * mm, y, t.get("hora_inicio") or "")
            c.drawString(_ESQ + 50 * mm, y, t.get("hora_fim") or "")
            c.drawString(_ESQ + 75 * mm, y, _fmt_duracao(t.get("tempo_gasto_min")))
            c.drawString(_ESQ + 95 * mm, y, (t.get("funcionario_nome") or "")[:26])
            total_min += int(t.get("tempo_gasto_min") or 0)
            y -= 10
        y -= 2
        c.setFont("Helvetica-Bold", 8)
        c.drawString(_ESQ, y, f"Tempo Total ===> {_fmt_duracao(total_min)}")
        y -= 16

    # ---- Rodapé ----
    y -= 6
    c.setLineWidth(0.6)
    c.line(_ESQ, y, _DIR, y)
    y -= 10
    if os_row.get("hora_fechamento"):
        c.setFont("Helvetica", 8)
        c.drawString(_ESQ, y, f"O.S. Fechada em {_fmt_data(os_row.get('data_termino'))} às {os_row['hora_fechamento']}hs.")
        y -= 14
    disclaimer = (
        "Informado pelo fornecedor das características dos produtos e fatos do serviço. "
        "Autorizo a execução de todo o serviço acima."
    )
    c.setFont("Helvetica", 7)
    for linha in _quebrar_linhas(c, disclaimer, _DIR - _ESQ, 7):
        c.drawString(_ESQ, y, linha); y -= 9
    y -= 10
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    c.drawString(_ESQ, y, f"De Acordo Em: {agora}")
    c.line(_ESQ + 55 * mm, y - 1, _DIR, y - 1)
    y -= 9
    c.setFont("Helvetica", 6.5)
    c.drawCentredString((_ESQ + 55 * mm + _DIR) / 2, y, os_row.get("cliente_nome") or "")

    c.setFont("Helvetica", 6)
    c.drawCentredString(_LARGURA / 2, 10 * mm, "by Kontacto · www.kontacto.com.br")
    # Número de página real — bug achado ao vivo 2026-08-26 (teste com 12
    # equipamentos/40 itens, documento saiu com 2 páginas): "Página 1"
    # era fixo, sempre errado a partir da 2ª página. `getPageNumber()`
    # reflete a página atual (só a última tem esse rodapé — as páginas
    # anteriores, geradas via `c.showPage()` no meio do desenho, não
    # repetem numeração; suficiente por ora, virar "Página X de N"
    # exigiria 2 passadas de desenho).
    c.drawRightString(_DIR, 10 * mm, f"Página {c.getPageNumber()}")

    _desenhar_checklist_veiculo(c, dados, y, os_row["codigo"])

    c.showPage()
    c.save()
    return buf.getvalue()


async def gerar_pdf_os(servidor: str, banco: str, codigo: int) -> Optional[bytes]:
    dados = await _montar_dados_os_sync(servidor, banco, codigo)
    if not dados:
        return None
    return gerar_pdf_os_sync(dados)


def _resolver_email_cliente_sync(cur, cliente_codigo: int) -> str:
    """Mesma cascata já usada em `contratos_service`/`geracao_boletos_
    service` (`ISNULL(NULLIF(email_cobranca,''), ISNULL(NULLIF(email_NFE,
    ''), e_mail))`) — sem helper Python compartilhado no projeto, cada
    consumidor replica a mesma SQL."""
    cur.execute(
        "SELECT ISNULL(NULLIF(email_cobranca,''), ISNULL(NULLIF(email_NFE,''), e_mail)) AS email "
        "FROM cliente WHERE codigo=%s",
        (cliente_codigo,),
    )
    r = cur.fetchone()
    return (r.get("email") or "").strip() if r else ""


async def enviar_email_os(servidor: str, banco: str, codigo: int) -> dict:
    """Gera o mesmo PDF de `gerar_pdf_os` e anexa via
    `email_cobranca_service.enviar_email` (função genérica, mesmo padrão
    já usado por Boletos/Contratos/Gestor NFSe) — nunca WhatsApp aqui, ver
    docstring do módulo."""
    dados = await _montar_dados_os_sync(servidor, banco, codigo)
    if not dados:
        return {"success": False, "message": "O.S. não encontrada."}
    os_row = dados["os"]
    if not os_row.get("cliente"):
        return {"success": False, "message": "O.S. sem cliente vinculado."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        email_destino = _resolver_email_cliente_sync(cur, os_row["cliente"])
        cur.close()
    finally:
        conn.close()
    if not email_destino:
        return {"success": False, "message": "Cliente sem e-mail cadastrado."}

    pdf_bytes = gerar_pdf_os_sync(dados)
    nome_cliente = os_row.get("cliente_nome") or ""
    assunto = f"O.S. nº {os_row['codigo']} — {nome_cliente}".strip()
    corpo = (
        f'<font face="Arial" size="2">Prezado(a) {nome_cliente},<br><br>'
        f"Segue em anexo a Ordem de Serviço nº {os_row['codigo']}.<br><br>"
        "Atenciosamente,<br></font>"
    )
    anexos = [{"conteudo": pdf_bytes, "nome_arquivo": f"os_{os_row['codigo']}.pdf"}]
    return await email_cobranca_service.enviar_email(servidor, banco, email_destino, assunto, corpo, anexos)

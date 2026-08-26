"""Boleto em PDF (código de barras + linha digitável reais, layout padrão
Febraban) — motor que faltava pros botões "Gerar PDF"/"Enviar por Email"
de "Geração de Boletos" (Financeiro > Cobranças) e pro anexo real de
"Envio de Cobrança de Contratos". Ver PENDENCIAS.md > "Boleto em PDF"
pro plano completo desta rodada.

Fonte VB6: `Geral\\IntegracaoBancaria.bas` (`BoletoItau`/`BoletoBradesco`,
funções `Modulo_10`/`Modulo_11_Real`/`Modulo_11_Unibanco`) e
`Kontacto\\BancoInter.bas` (`BoletoInter`) — lidos linha a linha nesta
sessão. O cálculo da linha digitável/código de barras é regra Febraban
real, portado literalmente (mesma composição de campos, mesma ordem).
O DESENHO visual é um layout único genérico padrão Febraban (mandatório
pra todo banco do Brasil desde 2015) em vez de replicar 3 rotinas de
~500 linhas de coordenadas GDI quase idênticas — ver "Não replicar
truques VB6" no CLAUDE.md: os 3 bancos no legado desenham a MESMA grade
de campos (Recibo do Sacado + Ficha de Compensação), só com coordenadas
levemente diferentes por terem sido escritas em momentos diferentes, não
por divergência de negócio.

**Bancos suportados: Itaú (341), Bradesco (237), Inter (077)** — mesmo
escopo já usado pelos motores de remessa CNAB (`cnab_itau_service`/
`cnab_bradesco_service`/`cnab_inter_service`). Santander/BB devolvem
mensagem clara, não implementados (mesmo padrão de erro do dispatch de
remessa).

**Achado real desta rodada, que muda o que "gerar boleto" precisa
fazer**: a fonte VB6 grava `banco_cedente`/`conta_cedente`/`carteira`/
`numero_boleto` em `duplicata_rec_venc` no momento em que o boleto é
IMPRESSO PELA PRIMEIRA VEZ (não existe um passo "Gerar Boleto" separado
no legado — a gravação está solta no topo de `BoletoItau`/
`BoletoBradesco`/`BoletoInter`, ANTES até de checar a flag `Impressao`).
Essa gravação é o que HABILITA depois o título a aparecer em "Gerar
Remessa": `cnab_*_service._titulos_para_remessa_sync` exige
`drv.banco_cedente = <banco>` batendo exatamente — sem essa gravação
nenhum título recém-faturado (`contratos_service._transf_receber_sync`
nunca grava esses 4 campos) teria como aparecer lá. Replicado aqui:
gerar o PDF pra um banco escolhido explicitamente na tela "Geração de
Boletos" REGISTRA o título nesse banco (idempotente — só grava se ainda
não estava registrado nesse banco, mesmo critério de
`_gerar_nosso_numero_sync`) — fecha esse gap de acoplamento de brinde,
sem inventar nada: é literalmente o que a fonte já faz.
"""
import asyncio
from datetime import date
from io import BytesIO
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from db.connection import _open_conn
from services import cnab_bradesco_service, cnab_inter_service, cnab_itau_service

BANCO_ITAU = 341
BANCO_BRADESCO = 237
BANCO_INTER = 77

_NOMES_BANCO = {BANCO_ITAU: "Itaú Unibanco S.A.", BANCO_BRADESCO: "Banco Bradesco S.A.", BANCO_INTER: "Banco Inter S.A."}

_DATA_BASE_ITAU_BRADESCO = date(1997, 10, 7)
_DATA_BASE_INTER = date(2000, 7, 3)
_DATA_CORTE_2025 = date(2025, 2, 22)


# ============ Algoritmos de dígito verificador (fonte: IntegracaoBancaria.bas) ============
def _modulo_10(codigo: str) -> int:
    """Réplica de `Modulo_10` (`IntegracaoBancaria.bas:1385`) — peso
    alternado 2,1 da direita pra esquerda; soma os 2 dígitos do produto
    quando >9. Usado pelos blocos da linha digitável dos 3 bancos e
    pelo DAC do nosso número do Itaú."""
    peso = 2
    total = 0
    for ch in reversed(codigo):
        produto = int(ch) * peso
        total += (produto // 10 + produto % 10) if produto > 9 else produto
        peso = 1 if peso == 2 else 2
    resto = total % 10
    return 0 if resto == 0 else 10 - resto


def _modulo_11_real(numero: str) -> int:
    """Réplica de `Modulo_11_Real` (`IntegracaoBancaria.bas:1534`) — peso
    2..9 cíclico da direita. Usado só pelo Itaú, DAC do código de
    barras."""
    mult = 2
    total = 0
    for ch in reversed(numero):
        total += int(ch) * mult
        mult = 2 if mult == 9 else mult + 1
    resto = total % 11
    return 1 if resto <= 1 else 11 - resto


def _modulo_11_unibanco(numero: str, molde: str) -> int:
    """Réplica de `Modulo_11_Unibanco` (`IntegracaoBancaria.bas:1801`) —
    peso 2..9 cíclico. `molde="N"` devolve resto cru (0/10→0); qualquer
    outro molde (Inter usa "X" pro DAC do código de barras) devolve 1
    pra resto 0/1/10, senão `11-resto`."""
    mult = 2
    total = 0
    for ch in reversed(numero):
        total += int(ch) * mult
        mult = 2 if mult == 9 else mult + 1
    resto = total % 11
    if molde == "N":
        return 0 if resto in (0, 10) else resto
    return 1 if resto in (0, 1, 10) else 11 - resto


def _fator_vencimento(vencimento: date, data_base: date) -> int:
    """Corte Febraban 2025 (mesma regra lida em `BoletoItau`/
    `BoletoBradesco`/`BoletoInter`): a partir de 22/02/2025 o fator
    reinicia em 1000 contado dessa data (a janela de 9999 dias contada
    da base antiga se esgotaria)."""
    if vencimento >= _DATA_CORTE_2025:
        return (vencimento - _DATA_CORTE_2025).days + 1000
    return (vencimento - data_base).days


def _fmt_moeda(valor: float) -> str:
    """`1234.5` -> `"1.234,50"` — só a formatação de exibição (separador
    decimal vírgula, milhar ponto); nunca usar `.replace('.', ',')` numa
    frase inteira, quebra o ponto final."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _valor_codigo_barras(valor: float) -> str:
    """10 dígitos: 8 de parte inteira + 2 de centavos, réplica de
    `Format(valorboleto,"########0.00")` reformatado sem separador."""
    centavos = round(valor * 100)
    return f"{centavos:010d}"


# ============ Montagem por banco ============
def _montar_boleto_itau(banco_row: dict, drv: dict, cliente: dict, endereco_cli: Optional[dict], nosso_numero: int) -> dict:
    banco_febraban = str(BANCO_ITAU)
    moeda = "9"
    fator = _fator_vencimento(drv["dt_vencimento"], _DATA_BASE_ITAU_BRADESCO)
    fator_s = f"{fator:04d}"
    valor_cb = _valor_codigo_barras(float(drv["valor"]))
    carteira = f"{int(banco_row.get('carteira') or 0):03d}"
    nn = f"{nosso_numero:08d}"
    agencia = f"{int(banco_row.get('agencia') or 0):04d}"
    conta = f"{int(banco_row.get('contacorrente') or 0):05d}"
    dv_conta = str(banco_row.get("dv_contacorrente") or "").strip() or "0"

    if carteira == "112":
        dac2 = _modulo_10(carteira + nn)
    else:
        dac2 = _modulo_10(agencia + conta + carteira + nn)
    dac3 = _modulo_10(agencia + conta)

    campo_livre = f"{carteira}{nn}{dac2}{agencia}{conta}{dac3}000"
    dac_barras = _modulo_11_real(f"{banco_febraban}{moeda}{fator_s}{valor_cb}{campo_livre}")
    codigo_barras = f"{banco_febraban}{moeda}{dac_barras}{fator_s}{valor_cb}{campo_livre}"

    dac_b1 = _modulo_10(f"{banco_febraban}9{carteira}{nn[0:2]}")
    bloco1 = f"{banco_febraban}9{carteira[0]}.{carteira[1:3]}{nn[0:2]}{dac_b1}"
    dac_b2 = _modulo_10(f"{nn[2:8]}{dac2}{agencia[0:3]}")
    bloco2 = f"{nn[2:7]}.{nn[7:8]}{dac2}{agencia[0:3]}{dac_b2}"
    dac_b3 = _modulo_10(f"{agencia[3:4]}{conta}{dv_conta}000")
    bloco3 = f"{agencia[3:4]}{conta[0:4]}.{conta[4:5]}{dv_conta}000{dac_b3}"
    bloco4 = str(dac_barras)
    bloco5 = f"{fator_s}{valor_cb}"
    linha_digitavel = f"{bloco1} {bloco2} {bloco3} {bloco4} {bloco5}"

    return {
        "banco_codigo": BANCO_ITAU, "banco_dv": "7", "banco_nome": _NOMES_BANCO[BANCO_ITAU],
        "codigo_barras": codigo_barras, "linha_digitavel": linha_digitavel,
        "nosso_numero": f"{carteira}/{nn}-{dac2}",
        "agencia_conta": f"{agencia}/{conta}-{dv_conta}",
        "carteira": carteira,
    }


def _montar_boleto_bradesco(banco_row: dict, drv: dict, cliente: dict, endereco_cli: Optional[dict], nosso_numero: int) -> dict:
    banco_febraban = f"{BANCO_BRADESCO:03d}"
    moeda = "9"
    fator = _fator_vencimento(drv["dt_vencimento"], _DATA_BASE_ITAU_BRADESCO)
    fator_s = f"{fator:04d}"
    valor_cb = _valor_codigo_barras(float(drv["valor"]))
    carteira = f"{int(banco_row.get('carteira') or 0):02d}"
    nn = f"{nosso_numero:011d}"
    agencia = f"{int(banco_row.get('agencia') or 0):04d}"
    conta = f"{int(banco_row.get('contacorrente') or 0):07d}"
    dv_conta = str(banco_row.get("dv_contacorrente") or "").strip() or "0"

    dv_nn = cnab_bradesco_service._modulo_11_bradesco(carteira + nn, 7)

    campo_livre = f"{agencia}{carteira}{nn}{conta}0"
    dac_barras = cnab_bradesco_service._modulo_11_bradesco(f"{banco_febraban}{moeda}{fator_s}{valor_cb}{campo_livre}", 9)
    codigo_barras = f"{banco_febraban}{moeda}{dac_barras}{fator_s}{valor_cb}{campo_livre}"

    bloco1_base = f"{banco_febraban}9{campo_livre[0:5]}"
    dac_b1 = _modulo_10(bloco1_base)
    bloco1 = f"{bloco1_base[0:5]}.{bloco1_base[5:9]}{dac_b1}"
    bloco2_base = campo_livre[5:15]
    dac_b2 = _modulo_10(bloco2_base)
    bloco2 = f"{bloco2_base[0:5]}.{bloco2_base[5:10]}{dac_b2}"
    bloco3_base = campo_livre[15:25]
    dac_b3 = _modulo_10(bloco3_base)
    bloco3 = f"{bloco3_base[0:5]}.{bloco3_base[5:10]}{dac_b3}"
    bloco4 = str(dac_barras)
    bloco5 = f"{fator_s}{valor_cb}"
    linha_digitavel = f"{bloco1} {bloco2} {bloco3} {bloco4} {bloco5}"

    return {
        "banco_codigo": BANCO_BRADESCO, "banco_dv": "2", "banco_nome": _NOMES_BANCO[BANCO_BRADESCO],
        "codigo_barras": codigo_barras, "linha_digitavel": linha_digitavel,
        "nosso_numero": f"{nn}-{dv_nn}",
        "agencia_conta": f"{agencia}/{conta}-{dv_conta}",
        "carteira": carteira,
    }


def _montar_boleto_inter(banco_row: dict, drv: dict, cliente: dict, endereco_cli: Optional[dict], nosso_numero: int) -> dict:
    moeda = "9"
    fator = _fator_vencimento(drv["dt_vencimento"], _DATA_BASE_INTER)
    if fator >= 10000:
        fator = _fator_vencimento(drv["dt_vencimento"], _DATA_CORTE_2025)
    fator_s = f"{fator:04d}"
    valor_cb = _valor_codigo_barras(float(drv["valor"]))
    cod_cedente = str(banco_row.get("codigocedente") or "").strip().zfill(7)[:7]
    nn = f"{nosso_numero:011d}"

    campo_livre = f"0001112{cod_cedente}{nn}"
    dac_barras = _modulo_11_unibanco(f"{BANCO_INTER:03d}{moeda}{fator_s}{valor_cb}{campo_livre}", "X")
    codigo_barras = f"{BANCO_INTER:03d}{moeda}{dac_barras}{fator_s}{valor_cb}{campo_livre}"

    dac_b1 = _modulo_10(f"{BANCO_INTER:03d}9{campo_livre[0:5]}")
    b1 = f"{BANCO_INTER:03d}9{campo_livre[0:5]}"
    bloco1 = f"{b1[0:5]}.{b1[5:9]}{dac_b1}"
    dac_b2 = _modulo_10(campo_livre[5:15])
    b2 = campo_livre[5:15]
    bloco2 = f"{b2[0:5]}.{b2[5:10]}{dac_b2}"
    dac_b3 = _modulo_10(campo_livre[15:25])
    b3 = campo_livre[15:25]
    bloco3 = f"{b3[0:5]}.{b3[5:10]}{dac_b3}"
    bloco4 = str(dac_barras)
    bloco5 = f"{fator_s}{valor_cb}"
    linha_digitavel = f"{bloco1} {bloco2} {bloco3} {bloco4} {bloco5}"

    return {
        "banco_codigo": BANCO_INTER, "banco_dv": "0", "banco_nome": _NOMES_BANCO[BANCO_INTER],
        "codigo_barras": codigo_barras, "linha_digitavel": linha_digitavel,
        "nosso_numero": nn,
        "agencia_conta": cod_cedente,
        "carteira": str(int(banco_row.get("carteira") or 0)),
    }


_MONTADORES = {BANCO_ITAU: _montar_boleto_itau, BANCO_BRADESCO: _montar_boleto_bradesco, BANCO_INTER: _montar_boleto_inter}


def _gerar_nosso_numero(cod_banco: int, cur, cod_banco_pk: int, banco_febraban: int, conta_cedente: int, drv_codigo: int) -> int:
    """Dispatch por módulo (não por dict fechado no import) — resolvido
    por atributo do módulo A CADA CHAMADA, pra que `monkeypatch.setattr`
    nos testes (ex.: `cnab_itau_service._gerar_nosso_numero_sync`)
    funcione; um dict `{banco: funcao}` montado uma vez no import
    capturaria a função original por valor e ignoraria qualquer patch
    posterior."""
    if cod_banco == BANCO_ITAU:
        return cnab_itau_service._gerar_nosso_numero_sync(cur, cod_banco_pk, banco_febraban, conta_cedente, drv_codigo)
    if cod_banco == BANCO_BRADESCO:
        return cnab_bradesco_service._gerar_nosso_numero_sync(cur, cod_banco_pk, banco_febraban, conta_cedente, drv_codigo)
    if cod_banco == BANCO_INTER:
        return cnab_inter_service._gerar_nosso_numero_sync(cur, cod_banco_pk, banco_febraban, conta_cedente, drv_codigo)
    raise ValueError(f"Banco {cod_banco} sem gerador de Nosso Número.")


def _resolver_endereco_cliente_sync(cur, codigo_cliente: int) -> Optional[dict]:
    """Réplica de `cnab_itau_service._montar_vendereco`'s critério de
    resolução — `tipo=0 OR tipo=1` (preferindo 1), fallback `tipo=2`."""
    cur.execute(
        "SELECT endereco, numero, complemento, bairro, cidade, uf, cep FROM cliente_end "
        "WHERE codigo=%s AND (tipo=0 OR tipo=1) ORDER BY tipo DESC",
        (codigo_cliente,),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "SELECT endereco, numero, complemento, bairro, cidade, uf, cep FROM cliente_end WHERE codigo=%s AND tipo=2",
            (codigo_cliente,),
        )
        row = cur.fetchone()
    return row


def _linha_endereco(end: Optional[dict]) -> str:
    if not end:
        return ""
    partes = [str(end.get("endereco") or "").strip(), str(end.get("numero") or "").strip()]
    complemento = str(end.get("complemento") or "").strip()
    if complemento:
        partes.append(complemento)
    linha1 = " ".join(p for p in partes if p)
    bairro = str(end.get("bairro") or "").strip()
    cidade = str(end.get("cidade") or "").strip()
    uf = str(end.get("uf") or "").strip()
    cep = str(end.get("cep") or "").strip()
    linha2 = " - ".join(p for p in [bairro, f"{cidade}/{uf}" if cidade else "", f"CEP: {cep}" if cep else ""] if p)
    return " - ".join(p for p in [linha1, linha2] if p)


def _montar_instrucoes(banco_row: dict, valor: float, desconto: float) -> list[str]:
    """Réplica das 4 condicionais lidas em `BoletoItau`/`BoletoBradesco`
    (protesto automático / mora ao dia / multa por atraso / desconto até
    o vencimento), mais as 3 mensagens livres do banco."""
    linhas: list[str] = []
    dias_protesto = int(banco_row.get("dias_protesto") or 0)
    if dias_protesto > 0:
        linhas.append(f"PROTESTO AUTOMÁTICO APÓS {dias_protesto} DIA(S).")
    mora_dia_pct = float(banco_row.get("Mora_Dia_Pag") or 0)
    if mora_dia_pct > 0:
        valor_mora = round(valor * mora_dia_pct / 100, 2)
        linhas.append(f"APÓS VENCIMENTO COBRAR R$ {_fmt_moeda(valor_mora)} POR DIA DE ATRASO")
    multa_pct = float(banco_row.get("Multa_Atraso_Pag") or 0)
    if multa_pct > 0:
        valor_multa = round(valor * multa_pct / 100, 2)
        linhas.append(f"APÓS VENCIMENTO COBRAR MULTA DE R$ {_fmt_moeda(valor_multa)}")
    if desconto > 0:
        linhas.append(f"Desconto de R$ {_fmt_moeda(desconto)} até o vencimento.")
    for campo in ("mensagem_boleto_1", "mensagem_boleto_2", "mensagem_boleto_3"):
        msg = str(banco_row.get(campo) or "").strip()
        if msg:
            linhas.append(msg)
    return linhas[:7]


def _montar_dados_boleto_sync(cur, drv_codigo: int) -> dict:
    cur.execute(
        "SELECT drv.codigo, drv.duplicata, drv.dt_vencimento, drv.dt_vencimento_desc, drv.valor, drv.valor_desc, "
        "drv.OUTROS_acres_pag, drv.banco_cedente, drv.conta_cedente, drv.carteira AS drv_carteira, "
        "drv.numero_boleto, dr.cliente, dr.duplicata AS num_doc_cliente "
        "FROM duplicata_rec_venc drv JOIN duplicata_receber dr ON dr.codigo = drv.duplicata "
        "WHERE drv.codigo = %s",
        (drv_codigo,),
    )
    drv = cur.fetchone()
    if not drv:
        return {"success": False, "message": "Título não encontrado."}
    if not drv.get("dt_vencimento") or drv.get("valor") is None:
        return {"success": False, "message": "Título sem vencimento/valor — não é possível gerar o boleto."}

    cur.execute("SELECT codigo, nome, cgc_cpf FROM cliente WHERE codigo=%s", (drv["cliente"],))
    cliente = cur.fetchone()
    if not cliente:
        return {"success": False, "message": "Cliente do título não encontrado."}
    endereco_cli = _resolver_endereco_cliente_sync(cur, drv["cliente"])

    cod_banco_alvo = int(drv.get("banco_cedente") or 0)
    if cod_banco_alvo not in _MONTADORES:
        return {"success": False, "message": "Título ainda não está registrado em um banco suportado — gere o boleto pela tela Geração de Boletos primeiro."}

    cur.execute("SELECT * FROM bancos WHERE codigo=%s", (cod_banco_alvo,))
    banco_row = cur.fetchone()
    if not banco_row:
        return {"success": False, "message": "Banco do título não encontrado."}

    nosso_numero = int(drv.get("numero_boleto") or 0)
    if nosso_numero <= 0:
        return {"success": False, "message": "Título sem Nosso Número alocado."}

    dados_barras = _MONTADORES[cod_banco_alvo](banco_row, drv, cliente, endereco_cli, nosso_numero)

    cur.execute("SELECT rz_social, endereco, numero, complemento, bairro, cidade, uf, cep, cgc FROM controle")
    empresa = cur.fetchone() or {}

    valor = float(drv["valor"] or 0) + float(drv.get("OUTROS_acres_pag") or 0)
    desconto = float(drv.get("valor_desc") or 0)

    return {
        "success": True,
        **dados_barras,
        "vencimento": drv["dt_vencimento"],
        "data_documento": drv["dt_vencimento"],
        "num_documento": str(drv.get("num_doc_cliente") or ""),
        "valor": valor,
        "valor_desconto": desconto,
        "instrucoes": _montar_instrucoes(banco_row, valor, desconto),
        "sacado_nome": cliente.get("nome") or "",
        "sacado_doc": cliente.get("cgc_cpf") or "",
        "sacado_endereco": _linha_endereco(endereco_cli),
        "cedente_nome": str(empresa.get("rz_social") or "").strip(),
        "cedente_doc": str(empresa.get("cgc") or "").strip(),
        "cedente_endereco": _linha_endereco(empresa) if empresa else "",
        "local_pagamento": "PAGÁVEL EM QUALQUER BANCO ATÉ O VENCIMENTO",
        # Logo do banco (`bancos.logo_banco`, 2026-08-26) — já vem no
        # `banco_row` acima (`SELECT *`), bytes crus (nunca passa por
        # `_to_json_safe`/HTTP aqui, é geração de PDF 100% server-side,
        # não precisa de base64). `None` quando o banco não tem logo
        # cadastrada — `_desenhar_boleto` cai pro texto de sempre.
        "logo_bytes": banco_row.get("logo_banco"),
        "logo_mime": banco_row.get("logo_banco_mime"),
    }


def _registrar_banco_no_titulo_sync(cur, drv_codigo: int, cod_banco_pk: int) -> Optional[dict]:
    """Registra o título no banco escolhido (`banco_cedente`/
    `conta_cedente`/`carteira`/`numero_boleto`) réplica do UPDATE que a
    fonte VB6 faz incondicionalmente no topo de `BoletoItau`/
    `BoletoBradesco`/`BoletoInter`, ANTES de desenhar — é essa gravação
    que faz o título aparecer depois em "Gerar Remessa". Idempotente:
    reaproveita se já registrado neste banco (mesmo critério de
    `_gerar_nosso_numero_sync`).

    `cod_banco_pk` é `bancos.cod` (a PK autoincrement), mesma convenção
    já usada por `geracao_boletos_service._listar_titulos_sync` e pela
    rota `/geracao-boletos/{cod_banco}/titulos` já existente — não
    confundir com `banco_cedente`/`bancos.codigo` (o código Febraban,
    341/237/77, gravado em `duplicata_rec_venc.banco_cedente`)."""
    cur.execute("SELECT * FROM bancos WHERE cod=%s", (cod_banco_pk,))
    banco_row = cur.fetchone()
    if not banco_row:
        return {"success": False, "message": "Banco não encontrado."}
    banco_febraban = int(banco_row.get("codigo") or 0)
    if banco_febraban not in _MONTADORES:
        return {"success": False, "message": "Geração de boleto não implementada para este banco."}
    conta_cedente = int(banco_row.get("contacorrente") or 0)
    carteira = int(banco_row.get("carteira") or 0)

    nosso_numero = _gerar_nosso_numero(banco_febraban, cur, cod_banco_pk, banco_febraban, conta_cedente, drv_codigo)
    if nosso_numero <= 0:
        return {"success": False, "message": "Não foi possível alocar o Nosso Número para este título."}

    cur.execute(
        "UPDATE duplicata_rec_venc SET banco_cedente=%s, conta_cedente=%s, carteira=%s, numero_boleto=%s "
        "WHERE codigo=%s AND (banco_cedente IS NULL OR banco_cedente <> %s OR numero_boleto IS NULL OR numero_boleto=0)",
        (banco_febraban, conta_cedente, carteira, nosso_numero, drv_codigo, banco_febraban),
    )
    return None


# ============ Desenho do PDF ============
_LARGURA, _ALTURA = A4


def _texto(c: canvas.Canvas, x: float, y: float, texto: str, tamanho: float = 7, negrito: bool = False) -> None:
    c.setFont("Helvetica-Bold" if negrito else "Helvetica", tamanho)
    c.drawString(x, y, texto or "")


def _rotulo_valor(c: canvas.Canvas, x: float, y: float, rotulo: str, valor: str, tamanho_rotulo: float = 5.5, tamanho_valor: float = 7.5) -> None:
    c.setFont("Helvetica", tamanho_rotulo)
    c.drawString(x, y, rotulo)
    c.setFont("Helvetica-Bold", tamanho_valor)
    c.drawString(x, y - 9, valor or "")


_ITF_PADROES = {
    "0": "00110", "1": "10001", "2": "01001", "3": "11000", "4": "00101",
    "5": "10100", "6": "01100", "7": "00011", "8": "10010", "9": "01010",
}


def _gerar_itf25_bars(codigo_barras_44: str) -> list[tuple[bool, bool]]:
    """Codificação Intercalado 2 de 5 (padrão do código de barras de
    boleto) — start `0000`, um par de dígitos por iteração (o par vira 5
    barras + 5 espaços intercalados, um dígito codifica as barras, o
    outro os espaços, padrão N(estreito)/W(largo) de 5 elementos por
    dígito — tabela pública ITF25), stop `100`. Devolve uma lista de
    `(é_barra, é_largo)` na ordem de desenho — usada por `_desenhar_
    codigo_barras` pra converter em retângulos."""
    if len(codigo_barras_44) % 2 != 0:
        codigo_barras_44 = "0" + codigo_barras_44
    elementos: list[tuple[bool, bool]] = [(True, False), (False, False), (True, False), (False, False)]
    for i in range(0, len(codigo_barras_44), 2):
        d_barra = _ITF_PADROES[codigo_barras_44[i]]
        d_espaco = _ITF_PADROES[codigo_barras_44[i + 1]]
        for k in range(5):
            elementos.append((True, d_barra[k] == "1"))
            elementos.append((False, d_espaco[k] == "1"))
    elementos += [(True, True), (False, False), (True, False)]
    return elementos


def _desenhar_codigo_barras(c: canvas.Canvas, codigo_barras_44: str, x: float, y: float, largura: float, altura: float) -> None:
    elementos = _gerar_itf25_bars(codigo_barras_44)
    n_estreito = sum(1 for barra, largo in elementos if not largo)
    n_largo = len(elementos) - n_estreito
    largura_estreito = largura / (n_estreito + n_largo * 3)
    cx = x
    for eh_barra, eh_largo in elementos:
        w = largura_estreito * (3 if eh_largo else 1)
        if eh_barra:
            c.rect(cx, y, w, altura, fill=1, stroke=0)
        cx += w


def _desenhar_boleto(c: canvas.Canvas, dados: dict, topo: float) -> None:
    """Layout único padrão Febraban (Recibo do Sacado + Ficha de
    Compensação) — rótulos réplica literal da fonte já lida
    (`BoletoItau`/`BoletoBradesco`), coordenadas próprias (não copiadas
    do GDI do legado, ver docstring do módulo)."""
    esq = 12 * mm
    dir_ = _LARGURA - 12 * mm
    vencimento_str = dados["vencimento"].strftime("%d/%m/%Y")
    valor_str = f"R$ {_fmt_moeda(dados['valor'])}"

    # ---- Recibo do Sacado (canhoto, topo) ----
    y = topo
    c.setLineWidth(0.6)
    c.line(esq, y, dir_, y)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(esq, y - 12, "Recibo do Sacado")
    _rotulo_valor(c, dir_ - 60 * mm, y - 4, "Vencimento", vencimento_str)
    y -= 20
    _texto(c, esq, y, f"Beneficiário: {dados['cedente_nome']}  CNPJ/CPF: {dados['cedente_doc']}")
    _rotulo_valor(c, dir_ - 60 * mm, y - 8, "Valor do Documento", valor_str)
    y -= 12
    _texto(c, esq, y, f"Pagador: {dados['sacado_nome']}  CNPJ/CPF: {dados['sacado_doc']}")
    y -= 12
    _texto(c, esq, y, f"Nosso Número: {dados['nosso_numero']}    Agência/Conta: {dados['agencia_conta']}")
    y -= 14
    c.line(esq, y, dir_, y)
    y -= 10 * mm

    # ---- Ficha de Compensação ----
    c.setFont("Helvetica-Bold", 13)
    c.drawString(esq, y, f"{dados['banco_codigo']}-{dados['banco_dv']}")
    # Logo do banco (`bancos.logo_banco`, 2026-08-26) — quando cadastrada,
    # desenha a imagem no lugar do nome por extenso; o código do banco
    # (linha acima) SEMPRE fica como texto, é o dado que realmente importa
    # pro processamento bancário, com ou sem logo. Nunca deixa uma imagem
    # corrompida derrubar a geração do boleto inteiro — sem logo válida,
    # cai pro texto de sempre.
    logo_bytes = dados.get("logo_bytes")
    logo_desenhada = False
    if logo_bytes:
        try:
            img = ImageReader(BytesIO(bytes(logo_bytes)))
            largura_img, altura_img = img.getSize()
            # Altura pequena de propósito — só ~6pt de folga ABAIXO da
            # linha de base até a próxima linha ("Local de Pagamento"),
            # e a imagem tem que caber nesse espaço sem invadi-la (bug
            # real achado ao vivo: 1ª tentativa vazava por baixo). Cresce
            # só pra CIMA, onde há folga de sobra (~28pt até a seção
            # anterior).
            altura_alvo = 7 * mm
            largura_alvo = min(altura_alvo * largura_img / altura_img, 45 * mm)
            c.drawImage(
                img, esq + 22 * mm, y - 2, width=largura_alvo, height=altura_alvo,
                preserveAspectRatio=True, mask="auto",
            )
            logo_desenhada = True
        except Exception:
            logo_desenhada = False
    if not logo_desenhada:
        c.drawString(esq + 22 * mm, y, dados["banco_nome"])
    c.drawRightString(dir_, y, vencimento_str)
    y -= 6
    c.line(esq, y, dir_, y)
    y -= 12
    _rotulo_valor(c, esq, y, "Local de Pagamento", "PAGÁVEL EM QUALQUER BANCO ATÉ O VENCIMENTO")
    _rotulo_valor(c, dir_ - 55 * mm, y, "Agência/Código Beneficiário", dados["agencia_conta"])
    y -= 16
    _rotulo_valor(c, esq, y, "Beneficiário", f"{dados['cedente_nome']}  {dados['cedente_doc']}")
    _rotulo_valor(c, dir_ - 55 * mm, y, "Nosso Número", dados["nosso_numero"])
    y -= 16
    _rotulo_valor(c, esq, y, "Data do Documento", dados["data_documento"].strftime("%d/%m/%Y"))
    _rotulo_valor(c, esq + 40 * mm, y, "Nº do Documento", dados["num_documento"])
    _rotulo_valor(c, esq + 80 * mm, y, "Espécie Doc.", "DM")
    _rotulo_valor(c, esq + 100 * mm, y, "Aceite", "N")
    y -= 16
    _rotulo_valor(c, esq, y, "Carteira", dados["carteira"])
    _rotulo_valor(c, esq + 40 * mm, y, "(=) Valor do Documento", valor_str)
    _rotulo_valor(c, dir_ - 55 * mm, y, "(-) Desconto/Abatimento", f"R$ {_fmt_moeda(dados['valor_desconto'])}")
    y -= 22
    c.setFont("Helvetica", 6)
    c.drawString(esq, y, "Instruções (Todas as informações deste boleto são de exclusiva responsabilidade do beneficiário.)")
    y -= 10
    for linha in dados["instrucoes"]:
        c.drawString(esq, y, linha[:110])
        y -= 9
    y -= 6
    c.setFont("Helvetica", 7)
    c.drawString(esq, y, f"Pagador: {dados['sacado_nome']}  CPF/CNPJ: {dados['sacado_doc']}")
    y -= 10
    c.drawString(esq, y, dados["sacado_endereco"][:120])
    y -= 6
    c.line(esq, y, dir_, y)
    y -= 12 * mm

    _desenhar_codigo_barras(c, dados["codigo_barras"], esq, y, 90 * mm, 12 * mm)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(esq, topo - 4, dados["linha_digitavel"])


def gerar_pdf_um_titulo_sync(cur, drv_codigo: int) -> Optional[bytes]:
    """Gera o PDF (1 página) de um título já registrado num banco
    suportado — usado tanto pelo envio de e-mail (Geração de Boletos e
    Contratos) quanto por "Baixar PDF". Devolve `None` (nunca lança) se
    o título não tem boleto/banco suportado."""
    dados = _montar_dados_boleto_sync(cur, drv_codigo)
    if not dados.get("success"):
        return None
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _desenhar_boleto(c, dados, _ALTURA - 20 * mm)
    c.showPage()
    c.save()
    return buf.getvalue()


def gerar_pdf_titulos_sync(servidor: str, banco: str, cod_banco: int, titulos: list[int]) -> dict:
    if not titulos:
        return {"success": False, "message": "Selecione ao menos um título."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        erros = []
        for drv_codigo in titulos:
            erro = _registrar_banco_no_titulo_sync(cur, drv_codigo, cod_banco)
            if erro:
                erros.append({"drv_codigo": drv_codigo, "message": erro["message"]})
        conn.commit()

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        gerados = 0
        for drv_codigo in titulos:
            dados = _montar_dados_boleto_sync(cur, drv_codigo)
            if not dados.get("success"):
                erros.append({"drv_codigo": drv_codigo, "message": dados.get("message")})
                continue
            _desenhar_boleto(c, dados, _ALTURA - 20 * mm)
            c.showPage()
            gerados += 1
        cur.close()
        if gerados == 0:
            return {"success": False, "message": "Nenhum boleto pôde ser gerado.", "erros": erros}
        c.save()
        return {"success": True, "conteudo": buf.getvalue(), "erros": erros}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gerar boleto: {e}"}
    finally:
        conn.close()


async def gerar_pdf_titulos(servidor: str, banco: str, cod_banco: int, titulos: list[int]) -> dict:
    return await asyncio.to_thread(gerar_pdf_titulos_sync, servidor, banco, cod_banco, titulos)

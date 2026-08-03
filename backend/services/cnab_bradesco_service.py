"""Fase 2a — Motor CNAB do banco Bradesco (código Febraban 237), único banco
coberto nesta rodada (decisão do usuário via `AskUserQuestion`, 2026-07-24 —
"os dois juntos": remessa (CNAB240) + retorno (CNAB400) para um banco só,
Bradesco escolhido). Ver PENDENCIAS.md > "Bancos (Cadastro de Cobrança /
Boleto / CNAB)" > "Fase 2a" para o desenho completo e os riscos conhecidos.

Fonte legada rastreada campo-a-campo (não presumida): `IntegracaoBancaria.bas`
(em `C:/Desenv/VB6/SQLSERVER/Geral/`) — `Gera_Header_240`/`Gera_Header_Lote_240`/
`Gera_Segmento_P_240`/`Gera_Segmento_Q_240`/`Gera_Segmento_R_240`/
`Gera_Trailer_Lote_240`/`Gera_Trailer_240` (ramos `Banco = "237"`),
`GeraNossoNumero`, `Modulo_11_Bradesco`. Larguras de campo conferidas contra
os `Type Header_Arquivo_240`/`Header_Lote_240`/`Segmento_P_240`/
`Segmento_Q_240`/`Segmento_R_240`/`Trailer_Lote_240`/`Trailer_Arquivo_240` —
cada registro soma exatamente 240 caracteres (padrão Febraban CNAB240),
conferido por soma manual durante o rastreio, não assumido.

**Simplificação deliberada em relação ao legado** (registrar, não é
regra de negócio perdida): `FrmGeraArqBan.frm` deixa o usuário marcar/
desmarcar manualmente quais títulos entram na remessa numa grid. Aqui a
remessa inclui automaticamente TODOS os títulos abertos (`situacao='A'`)
do banco ainda não enviados (`transf_banco = 0`) — um filtro adicional
(`transf_banco`) que o SQL do legado não tinha explícito nessa query
específica (dependia só da seleção manual do usuário na grid); replicar
isso automaticamente evita reenviar por engano um título já remetido, sem
tirar controle nenhum do usuário (ele já vê a lista antes de confirmar,
ver rota `/api/bancos/{cod}/remessa`).

**Risco conhecido, não validado**: a leitura do RETORNO (CNAB400) segue o
layout padrão Febraban (mesmas posições encontradas no bloco "Option1 -
Confirmação de títulos enviados" de `FrmImpRetBan.frm`, ocorrência nas
posições 109-110) — o usuário confirmou não ter nenhum arquivo de retorno
real do Bradesco pra validar contra dado real. Testar com um arquivo real
antes de confiar em produção. Existe um SEGUNDO bloco no mesmo form (usado
só no fluxo de anexo de e-mail) com posições diferentes (ocorrência em
90-91) — decidi seguir o primeiro bloco (bate com o layout oficial Febraban
CNAB400, mais confiável) e não o segundo, que parece um bug/variação da
função de e-mail, não um layout de banco diferente.
"""
import asyncio
from datetime import date, datetime
from typing import Optional

from db.connection import _open_conn

BANCO_BRADESCO_CODIGO = 237


def _n(value, width: int) -> str:
    """Numérico com zeros à esquerda, largura fixa (equivalente a Format(x, "0..0"))."""
    s = str(int(value or 0))
    if len(s) > width:
        s = s[-width:]
    return s.zfill(width)


def _a(value, width: int) -> str:
    """Alfanumérico alinhado à esquerda, espaços à direita, truncado se maior (String * N)."""
    s = "" if value is None else str(value)
    s = s[:width]
    return s.ljust(width)


def _modulo_11_bradesco(numero: str, base_calculo: int):
    """Réplica fiel de `Modulo_11_Bradesco` (IntegracaoBancaria.bas:1754) —
    DAC do Nosso Número (base_calculo=7): pesos 2..7 ciclando da direita pra
    esquerda; resto 1 -> "P", resto 0 -> "0", senão 11-resto."""
    numero = str(numero).strip()
    mult = 2
    conta = 0
    for ch in reversed(numero):
        conta += int(ch) * mult
        mult += 1
        if mult == base_calculo + 1:
            mult = 2
    resto = conta % 11
    if resto == 1:
        return "P"
    if resto == 0:
        return "0"
    return str(11 - resto)


def _gerar_nosso_numero_sync(cur, cod_banco: int, banco_febraban: int, conta_cedente: int, codigo_duplicata: int) -> int:
    """Réplica de `GeraNossoNumero` (linhas 1333-1384) restrita ao caminho do
    Bradesco: se o título já tem `numero_boleto` gravado para ESTE banco,
    reaproveita; senão incrementa `bancos.numero_boleto` até achar um valor
    ainda não usado por `duplicata_rec_venc` (mesmo banco+conta), grava de
    volta em `bancos.numero_boleto`."""
    cur.execute("SELECT numero_boleto FROM bancos WHERE cod=%s", (cod_banco,))
    row = cur.fetchone()
    ultimo = int(float(row.get("numero_boleto") or 0)) if row else 0

    cur.execute(
        "SELECT numero_boleto, banco_cedente FROM duplicata_rec_venc WHERE codigo=%s",
        (codigo_duplicata,),
    )
    drv = cur.fetchone()
    if drv and float(drv.get("numero_boleto") or 0) != 0 and int(drv.get("banco_cedente") or 0) == banco_febraban:
        return int(float(drv["numero_boleto"]))

    while True:
        ultimo += 1
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM duplicata_rec_venc WHERE numero_boleto=%s AND banco_cedente=%s AND conta_cedente=%s",
            (ultimo, banco_febraban, conta_cedente),
        )
        if not cur.fetchone():
            break
    cur.execute("UPDATE bancos SET numero_boleto=%s WHERE cod=%s", (ultimo, cod_banco))
    return ultimo


def _titulos_para_remessa_sync(cur, banco_febraban: int, titulos: Optional[list] = None) -> list:
    """Réplica da query de `FrmGeraArqBan.frm:531` (join duplicata_rec_venc +
    duplicata_receber + cliente, `situacao='A'`, `banco_cedente=<banco>`) —
    ver docstring do módulo pra a diferença deliberada (`transf_banco=0`).

    `titulos` (opcional): subconjunto de `drv.codigo` selecionado pelo
    usuário na grade de "Geração de Boletos" — None/vazio mantém o
    comportamento antigo (todos os títulos pendentes do banco)."""
    filtro_codigos = ""
    params: tuple = (banco_febraban,)
    if titulos:
        placeholders = ",".join(["%s"] * len(titulos))
        filtro_codigos = f" AND drv.codigo IN ({placeholders})"
        params = (banco_febraban, *titulos)
    cur.execute(
        "SELECT drv.codigo, drv.duplicata, drv.desmembramento, drv.dt_vencimento, drv.valor, "
        "drv.dt_vencimento_desc, drv.valor_desc, drv.multa_atraso, drv.carteira, drv.conta_cedente, "
        "dr.cliente, dr.duplicata AS num_doc_cliente, dr.dt_emissao, dr.num_parcelas "
        "FROM duplicata_rec_venc drv "
        "JOIN duplicata_receber dr ON dr.codigo = drv.duplicata "
        "WHERE drv.situacao = 'A' AND drv.banco_cedente = %s AND (drv.transf_banco = 0 OR drv.transf_banco IS NULL)"
        + filtro_codigos +
        " ORDER BY drv.dt_vencimento",
        params,
    )
    return cur.fetchall()


def _montar_header_arquivo_240(banco_row: dict, cgc_empresa: str, razao_social: str, num_remessa: int) -> str:
    agora = datetime.now()
    return (
        _n(BANCO_BRADESCO_CODIGO, 3)
        + _n(0, 4)  # lote
        + "0"  # tipo registro
        + _a("", 9)  # Cnab_01
        + "2"  # tipo inscrição (2=CNPJ)
        + _n(cgc_empresa, 14)
        + _a(banco_row.get("cod_transmissao"), 20)  # convênio
        + _n(banco_row.get("agencia"), 5)
        + _a(banco_row.get("dv_agencia"), 1)
        + _n(banco_row.get("contacorrente"), 12)
        + _a(banco_row.get("dv_contacorrente"), 1)
        + _a(banco_row.get("dv_agencia_conta"), 1)
        + _a(razao_social, 30)
        + _a(banco_row.get("descr_arquivo"), 30)
        + _a("", 10)  # Cnab_02
        + "1"  # código remessa
        + agora.strftime("%d%m%Y")
        + agora.strftime("%H%M%S")
        + _n(num_remessa, 6)
        + "084"  # layout do lote — fixo pro Bradesco
        + "01600"  # densidade — fixo
        + _a("", 69)
    )


def _montar_header_lote_240(banco_row: dict, cgc_empresa: str, razao_social: str, num_remessa: int, data_geracao: str) -> str:
    return (
        _n(BANCO_BRADESCO_CODIGO, 3)
        + _n(1, 4)  # lote 0001
        + "1"
        + "R"  # tipo operação
        + "01"  # tipo serviço
        + _a("", 2)
        + "042"  # layout lote — fixo pro Bradesco (sobrescreve o "084" do header do arquivo)
        + _a("", 1)
        + "2"  # tipo inscrição
        + _n(cgc_empresa, 15)
        + _a(banco_row.get("cod_transmissao"), 20)
        + _n(banco_row.get("agencia"), 5)
        + _a(banco_row.get("dv_agencia"), 1)
        + _n(banco_row.get("contacorrente"), 12)
        + _a(banco_row.get("dv_contacorrente"), 1)
        + _a(banco_row.get("dv_agencia_conta"), 1)
        + _a(razao_social, 30)
        + _a("", 40)  # mensagem 1
        + _a("", 40)  # mensagem 2
        + _n(num_remessa, 8)
        + data_geracao
        + _n(0, 8)  # data crédito
        + _a("", 33)
    )


def _montar_segmento_p_240(banco_row: dict, titulo: dict, seq: int, nosso_numero: int) -> str:
    carteira = int(banco_row.get("carteira") or 0)
    nosso_numero_11 = _n(nosso_numero, 11)
    dv_nosso_numero = _modulo_11_bradesco(_n(carteira, 3) + nosso_numero_11, 7)

    vencimento = titulo["dt_vencimento"]
    emissao = titulo.get("dt_emissao") or date.today()
    valor = float(titulo["valor"] or 0)
    mora_dia = float(banco_row.get("mora_dia_pag") or 0) or 1  # legado: Valor_Mora=0 vira 1 (ver Gera_Segmento_P_240)
    valor_desc = float(titulo.get("valor_desc") or 0)
    dt_venc_desc = titulo.get("dt_vencimento_desc") or vencimento

    num_doc = str(titulo.get("num_doc_cliente") or titulo["duplicata"])
    desmembramento = titulo.get("desmembramento") or 0
    num_parcelas = titulo.get("num_parcelas") or 1
    if num_parcelas > 1:
        num_doc = f"{num_doc}/{desmembramento:03d}"

    num_titulo_cliente = _n(titulo["codigo"], 11) + _n(titulo["duplicata"], 11) + _n(desmembramento, 3)

    return (
        _n(BANCO_BRADESCO_CODIGO, 3)
        + _n(1, 4)
        + "3"
        + _n(seq, 5)
        + "P"
        + _a("", 1)
        + "01"  # código movimento — entrada
        + _n(banco_row.get("agencia"), 5)
        + _a(banco_row.get("dv_agencia"), 1)
        + _n(banco_row.get("contacorrente"), 12)
        + _a(banco_row.get("dv_contacorrente"), 1)
        + _a(banco_row.get("dv_agencia_conta"), 1)
        + _n(carteira, 3)
        + "00000"
        + nosso_numero_11
        + dv_nosso_numero
        + "1"  # emitente = banco emite
        + "1"  # tipo cadastro (registrada)
        + "1"  # tipo cobrança
        + "2"  # emissão do boleto — banco
        + "2"  # distribuição — banco
        + _a(num_doc, 15)
        + vencimento.strftime("%d%m%Y")
        + _n(round(valor * 100), 15)
        + _a("", 5)  # agência cobradora
        + "0"  # dv agência cobradora
        + _n(banco_row.get("especie_doc") or 2, 2)
        + _a(banco_row.get("aceite") or "N", 1)
        + emissao.strftime("%d%m%Y")
        + "1"  # código mora — valor por dia
        + vencimento.strftime("%d%m%Y")
        + _n(round(mora_dia * 100), 15)
        + ("1" if valor_desc > 0 else "0")
        + (dt_venc_desc.strftime("%d%m%Y") if valor_desc > 0 else "0" * 8)
        + _n(round(valor_desc * 100), 15)
        + _n(0, 15)  # IOF
        + _n(0, 15)  # abatimento
        + num_titulo_cliente
        + _n(banco_row.get("codigo_protesto") or 0, 1)
        + _n(banco_row.get("dias_protesto") or 0, 2)
        + _n(banco_row.get("codigo_baixa") or 0, 1)
        + "0"
        + _n(banco_row.get("dias_baixa") or 0, 2)
        + "09"  # moeda — real
        + _n(0, 10)
        + _a("", 1)
    )


def _montar_segmento_q_240(cliente_row: dict, endereco_row: Optional[dict], seq: int) -> str:
    cgc_cpf = str(cliente_row.get("cgc_cpf") or "").strip()
    tipo_inscr = "2" if len(cgc_cpf) > 11 else "1"
    endereco_row = endereco_row or {}
    numero = endereco_row.get("numero") or ""
    complemento = (endereco_row.get("complemento") or "").strip()
    num_compl = f" {numero} {complemento}".strip()
    endereco = _a(f"{(endereco_row.get('endereco') or '').strip()} {num_compl}".strip(), 40)
    return (
        _n(BANCO_BRADESCO_CODIGO, 3)
        + _n(1, 4)
        + "3"
        + _n(seq, 5)
        + "Q"
        + _a("", 1)
        + "01"
        + tipo_inscr
        + _n(cgc_cpf, 15)
        + _a(cliente_row.get("nome"), 40)
        + endereco
        + _a(endereco_row.get("bairro"), 15)
        + _n(str(endereco_row.get("cep") or "")[:5], 5)
        + _n(str(endereco_row.get("cep") or "")[5:8], 3)
        + _a(endereco_row.get("cidade"), 15)
        + _a(endereco_row.get("uf"), 2)
        + "0"  # tipo inscrição avalista — nenhum
        + _n(0, 15)  # cnpj/cpf avalista
        + _a("", 40)  # nome avalista (AlinhaDados ~ 40 no ramo 237)
        + "000"
        + _a("", 20)
        + _a("", 8)
    )


def _montar_segmento_r_240(multa_atraso: float, dt_vencimento: date, seq: int) -> Optional[str]:
    if multa_atraso <= 0:
        return None
    return (
        _n(BANCO_BRADESCO_CODIGO, 3)
        + _n(1, 4)
        + "3"
        + _n(seq, 5)
        + "R"
        + _a("", 1)
        + "01"
        + "0"  # código desconto 2
        + _n(0, 8)  # data desconto 2
        + _n(0, 15)  # valor desconto 2
        + _n(0, 24)
        + "1"  # código multa — valor
        + dt_vencimento.strftime("%d%m%Y")
        + _n(round(multa_atraso * 100), 15)
        + _a("", 10)
        + _a("", 40)
        + _a("", 40)
        + _a("", 20)
        + _n(0, 30)
        + " 3"
        + _a("", 9)
    )


def _montar_trailer_lote_240(qtd_registros: int) -> str:
    return (
        _n(BANCO_BRADESCO_CODIGO, 3)
        + _n(1, 4)
        + "5"
        + _a("", 9)
        + _n(qtd_registros, 6)
        + _a("", 217)
    )


def _montar_trailer_240(qtd_registros: int) -> str:
    return (
        _n(BANCO_BRADESCO_CODIGO, 3)
        + "9999"
        + "9"
        + _a("", 9)
        + _n(1, 6)  # qtd lotes
        + _n(qtd_registros, 6)
        + "000000"
        + _a("", 205)
    )


def _gerar_remessa_sync(servidor: str, banco: str, cod_banco: int, titulos: Optional[list] = None) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM bancos WHERE cod=%s", (cod_banco,))
        banco_row = cur.fetchone()
        if not banco_row:
            return {"success": False, "message": "Banco não encontrado."}
        if int(banco_row.get("codigo") or 0) != BANCO_BRADESCO_CODIGO:
            return {"success": False, "message": "Geração de remessa implementada só para o Bradesco (237) nesta fase."}
        if banco_row.get("integracao_api"):
            return {"success": False, "message": "Este banco está configurado para Integração por API — remessa em arquivo não se aplica."}

        cur.execute("SELECT cgc, rz_social FROM controle")
        controle = cur.fetchone() or {}
        cgc_empresa = str(controle.get("cgc") or "").strip()
        razao_social = str(controle.get("rz_social") or "").strip()

        titulos_encontrados = _titulos_para_remessa_sync(cur, BANCO_BRADESCO_CODIGO, titulos)
        if not titulos_encontrados:
            msg = "Nenhum dos títulos selecionados está pendente de remessa." if titulos else "Nenhum título aberto pendente de remessa para este banco."
            return {"success": False, "message": msg}

        num_remessa = int(float(banco_row.get("remessa") or 0)) + 1
        data_geracao = datetime.now().strftime("%d%m%Y")

        linhas = [_montar_header_arquivo_240(banco_row, cgc_empresa, razao_social, num_remessa)]
        linhas.append(_montar_header_lote_240(banco_row, cgc_empresa, razao_social, num_remessa, data_geracao))

        seq = 0
        qtd_titulos = 0
        for titulo in titulos_encontrados:
            cur.execute("SELECT codigo, nome, cgc_cpf FROM cliente WHERE codigo=%s", (titulo["cliente"],))
            cliente_row = cur.fetchone()
            if not cliente_row:
                continue
            cur.execute(
                "SELECT TOP 1 endereco, numero, complemento, bairro, cidade, uf, cep FROM cliente_end "
                "WHERE codigo=%s AND (tipo=0 OR tipo=1) ORDER BY tipo DESC",
                (titulo["cliente"],),
            )
            endereco_row = cur.fetchone()

            nosso_numero = _gerar_nosso_numero_sync(
                cur, cod_banco, BANCO_BRADESCO_CODIGO, int(titulo.get("conta_cedente") or banco_row.get("contacorrente") or 0), titulo["codigo"],
            )
            seq += 1
            linhas.append(_montar_segmento_p_240(banco_row, titulo, seq, nosso_numero))
            seq += 1
            linhas.append(_montar_segmento_q_240(cliente_row, endereco_row, seq))
            multa_atraso = float(banco_row.get("Multa_Atraso_Pag") or 0)
            if multa_atraso > 0:
                seq += 1
                linha_r = _montar_segmento_r_240(multa_atraso, titulo["dt_vencimento"], seq)
                if linha_r:
                    linhas.append(linha_r)

            cur.execute("UPDATE duplicata_rec_venc SET transf_banco = 1, numero_boleto = %s WHERE codigo = %s", (nosso_numero, titulo["codigo"]))
            qtd_titulos += 1

        # +2 do header/header-lote já contados; +1 do trailer de lote entra no total geral
        qtd_reg_lote = seq + 1  # header do lote não conta no trailer de lote, só os segmentos + o próprio trailer
        linhas.append(_montar_trailer_lote_240(qtd_reg_lote))
        qtd_reg_geral = len(linhas) + 1  # + trailer de arquivo
        linhas.append(_montar_trailer_240(qtd_reg_geral))

        nome_arquivo = f"CB{datetime.now().strftime('%d%m')}{str(num_remessa)[-2:].zfill(2)}.rem"
        conteudo = "\r\n".join(linhas) + "\r\n"

        cur.execute(
            "UPDATE bancos SET remessa=%s, data_remessa=%s, nome_remessa=%s WHERE cod=%s",
            (num_remessa, date.today().isoformat(), nome_arquivo, cod_banco),
        )
        conn.commit()
        cur.close()
        return {
            "success": True,
            "nome_arquivo": nome_arquivo,
            "conteudo": conteudo,
            "qtd_titulos": qtd_titulos,
            "num_remessa": num_remessa,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _parse_valor_cnab(raw: str) -> float:
    raw = (raw or "0").strip() or "0"
    return int(raw) / 100.0


def _parse_data_cnab(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    if len(raw) != 6 or raw == "000000":
        return None
    try:
        return date(2000 + int(raw[4:6]), int(raw[2:4]), int(raw[0:2]))
    except ValueError:
        return None


def _parse_linhas(conteudo: str) -> list:
    """Extrai os registros de detalhe do retorno CNAB400, sem tocar no banco
    de dados — usado tanto pelo processamento direto (`_processar_retorno_sync`,
    abaixo) quanto pela pré-visualização compartilhada
    (`cobranca_retorno_service.py`, ver `Importação do Arquivo de Retorno`).
    Cada item: {numero_boleto, ocorrencia, data_pag, valor_pago, juros,
    desconto, documento, ignorado}."""
    linhas = [l for l in conteudo.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]
    registros = []
    for linha in linhas:
        if len(linha) < 110 or linha[0] != "1":
            registros.append({"ignorado": True})
            continue
        registros.append({
            "ignorado": False,
            "numero_boleto": linha[62:70].strip().lstrip("0") or "0",
            "ocorrencia": linha[108:110].strip(),
            "data_pag": _parse_data_cnab(linha[110:116]),
            "valor_pago": _parse_valor_cnab(linha[253:266]),
            "juros": _parse_valor_cnab(linha[266:279]),
            "desconto": _parse_valor_cnab(linha[240:253]),
            "documento": None,
        })
    return registros


def _processar_retorno_sync(servidor: str, banco: str, cod_banco: int, conteudo: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM bancos WHERE cod=%s", (cod_banco,))
        banco_row = cur.fetchone()
        if not banco_row:
            return {"success": False, "message": "Banco não encontrado."}
        banco_febraban = int(banco_row.get("codigo") or 0)
        conta_cedente = int(banco_row.get("contacorrente") or 0)

        confirmados = 0
        baixados = 0
        nao_encontrados = []
        ignorados = 0

        for reg in _parse_linhas(conteudo):
            if reg["ignorado"]:
                ignorados += 1
                continue
            nosso_numero = reg["numero_boleto"]
            ocorrencia = reg["ocorrencia"]

            if ocorrencia == "02":
                confirmados += 1
                continue

            if ocorrencia in ("06", "09", "17"):
                cur.execute(
                    "SELECT codigo, situacao FROM duplicata_rec_venc "
                    "WHERE numero_boleto = %s AND banco_cedente = %s AND conta_cedente = %s",
                    (int(nosso_numero), banco_febraban, conta_cedente),
                )
                row = cur.fetchone()
                if not row:
                    nao_encontrados.append(nosso_numero)
                    continue
                if row.get("situacao") == "PG":
                    continue  # já baixado antes — idempotente, não conta de novo
                cur.execute(
                    "UPDATE duplicata_rec_venc SET situacao='PG', data_pag=%s, valor_pag=%s, "
                    "juros_pag=%s, desconto_pag=%s, ultima_mov_banco=%s WHERE codigo=%s",
                    (
                        (reg["data_pag"] or date.today()).isoformat(), reg["valor_pago"], reg["juros"], reg["desconto"],
                        int(ocorrencia), row["codigo"],
                    ),
                )
                baixados += 1
            else:
                ignorados += 1

        conn.commit()
        cur.close()
        return {
            "success": True,
            "confirmados": confirmados,
            "baixados": baixados,
            "nao_encontrados": nao_encontrados,
            "ignorados": ignorados,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def gerar_remessa(servidor: str, banco: str, cod_banco: int, titulos: Optional[list] = None) -> dict:
    return await asyncio.to_thread(_gerar_remessa_sync, servidor, banco, cod_banco, titulos)


async def processar_retorno(servidor: str, banco: str, cod_banco: int, conteudo: str) -> dict:
    return await asyncio.to_thread(_processar_retorno_sync, servidor, banco, cod_banco, conteudo)

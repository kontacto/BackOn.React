"""Fase 2a — Motor CNAB do Itaú (código Febraban 341).

**Status: Remessa (CNAB400) + Retorno (CNAB400) implementados e VALIDADOS
byte a byte contra um arquivo de remessa real do Itaú, colado pelo usuário
em 2026-07-24 (dados reais de produção: cliente RACING LUB DO BRASIL,
carteira 109, título da JUNIOR E HUGO MOTO PECAS LTDA).**

Header e trailer usam o ramo `Else` de `Gera_Header_400`/`Gera_Trailer_400`
(`IntegracaoBancaria.bas`) — o mesmo ramo genérico usado por qualquer banco
que não seja 748 (Sicredi) ou 077 (Inter), únicos com ramo próprio nessas
duas funções. Batem 100% com o arquivo real, sem ajuste.

**Registro de detalhe teve 2 achados reais corrigidos contra o arquivo**
(antes da validação, a soma dos campos com `Format()` explícito no legado
fechava 42 caracteres a menos que os 400 exigidos — 2 campos não têm
largura fixa no código-fonte):
- `Carteira`: é um parâmetro `Byte` (0-255) concatenado cru (`.Carteira =
  Carteira`, sem `Format()`) — **largura variável**, não fixa. No arquivo
  real, carteira 109 ocupa exatamente 3 caracteres ("109"), sem zeros à
  esquerda. Implementado como `str(int(carteira))`, sem padding — fiel ao
  que o legado realmente produz (mesmo que isso seja, na prática, uma
  falha de largura fixa do CNAB400 se a carteira algum dia tiver só 1 ou 2
  dígitos; replicado assim mesmo, por ser o comportamento real confirmado).
- `Documento` (número do documento/duplicata): `Format(Num_Duplicata,
  "#########0")` não tem zeros à esquerda nem largura mínima — o arquivo
  real confirmou que o campo ocupa exatamente 10 caracteres (mesma largura
  do campo "Documento" já usado pela leitura do PRÓPRIO retorno do Itaú,
  `Trim(Mid(Registro, 117, 10))` — ver `_processar_retorno_sync` abaixo),
  então implementado com `_a(documento, 10)` (alinhado à esquerda,
  preenchido com espaços).

Dois outros campos que pareciam zerados por padrão também bateram contra o
arquivo real e foram corrigidos: `instrucao_1`/`instrucao_2` vêm de
`bancos.instr_cobranca_1`/`instr_cobranca_2` (não hardcoded em zero), e
`juros_1_dia` usa a mesma fórmula do Inter/Bradesco (`valor_boleto *
bancos.mora_dia_pag / 100`, arredondado a centavos) — confirmado com
`mora_dia_pag=0.5` reproduzindo exatamente os R$ 5,40 de juros do título
real usado na validação.

**Retorno NÃO foi validado contra um arquivo real** (só a remessa foi) —
a leitura continua sendo best-effort a partir do rastreio de código-fonte
(`Processa_Retorno`, ver abaixo), com o mesmo nível de risco que a remessa
tinha antes de hoje. Testar com um retorno real do Itaú antes de confiar
em produção.

**Achado de "bug" real, replicado fielmente**: o campo `Codigo_inscricao`
aparece DUAS vezes na string final (uma vez perto do início, esperado ser o
tipo de inscrição da EMPRESA; outra vez perto do `numero_de_inscricao`,
o tipo de inscrição do CLIENTE) — mas é a MESMA variável no código-fonte,
reatribuída pro tipo do cliente antes de qualquer uma das duas leituras
acontecerem na montagem da string. No arquivo real, as duas ocorrências têm
o MESMO valor ("02", tipo do cliente, CNPJ) — confirmando que a posição
"da empresa" na prática sempre mostra o tipo do CLIENTE, não da empresa.
Replicado fielmente (mesma variável usada nos dois lugares).

**Nome/Logradouro/Bairro/Cidade NÃO passam por `EscreveMatricial`** (ao
contrário do Sicredi/748 e Inter/077, que usam essa função pra maiúsculas +
remoção de acentos) — o arquivo real confirma acentuação preservada
("PRAÇA DA BAN..."). Implementado sem qualquer transformação de caracteres,
só truncamento/preenchimento de largura.

Fonte legada rastreada campo-a-campo: `IntegracaoBancaria.bas` —
`Gera_Header_400`/`Gera_Detalhe_400` (ramo `Else`)/`Gera_Trailer_400` (ramo
`Else`), `GeraNossoNumero` (ramo `Else`, sequencial puro, sem dígito
verificador — banco 341 não está em nenhum `ElseIf` explícito dessa
função). Query de títulos elegíveis e resolução de endereço replicam o
mesmo padrão já usado por `cnab_bradesco_service.py`/`cnab_inter_service.py`
(inclusive a mesma simplificação deliberada do filtro `transf_banco=0`).

**Retorno** usa `Processa_Retorno` (`Geral/FrmImpRetBan.frm`), a MESMA
função genérica usada pelo Sicredi (748, não implementado aqui) — leitura
por posição fixa, sem ambiguidade de largura (arquivo que o BANCO gera, não
um que nós montamos).

**Achado importante no retorno**: a função monta um struct genérico
(`Retorno_400`) que lê `Nosso_Numero` na posição 63 (8 dígitos) — mas a
lógica de negócio que efetivamente localiza o título pra baixa (`ElseIf
Retorno_400.Ocorrencia = "06"`) usa `ultimo_boleto = CLng("0" &
Mid(Registro, 86, 8))` — **posição 86, não 63**. Segui a posição realmente
usada (86), mesmo princípio já aplicado ao Inter mais cedo nesta sessão.
**Isso NÃO foi replicado no `cnab_bradesco_service.py` já implantado**
(que usa a posição 63) — perguntado ao usuário se queria corrigir o
Bradesco também; resposta: "todo banco tem seu layout próprio", ou seja,
não presumir que a mesma correção vale pro Bradesco sem uma confirmação
própria — o Bradesco nem passa por este `Processa_Retorno` no legado (não
está no `Select Case` de despacho por banco). Não mexi no Bradesco.

**Ocorrência "02" é a única tratada além de "06"** neste `Processa_Retorno`
(diferente do `Processa_Retorno_inter`, que também trata "03") — mesmo
padrão usado pelo Bradesco/Inter (02=confirma, 06=baixa, qualquer outra
ocorrência=ignorada).

**Simplificação deliberada, igual aos demais bancos desta fase**: baixa
aplicada direto no `POST /retorno` (colar → processar → resumo), não o
staging manual de duas etapas do legado (`Boletos_Pendentes` +
"Confirma Baixa").
"""
import asyncio
from datetime import date, datetime
from typing import Optional

from db.connection import _open_conn

BANCO_ITAU_CODIGO = 341


def _n(value, width: int) -> str:
    s = str(int(value or 0))
    if len(s) > width:
        s = s[-width:]
    return s.zfill(width)


def _a(value, width: int) -> str:
    s = "" if value is None else str(value)
    s = s[:width]
    return s.ljust(width)


def _montar_vendereco(endereco_row: Optional[dict]) -> str:
    """Mesmo bloco de montagem de endereço compartilhado por `Gera_Detalhe_400`
    (ver docstring equivalente em cnab_inter_service.py) — usado por
    Itaú/341, Sicredi/748 e Inter/077."""
    endereco_row = endereco_row or {}
    numero = endereco_row.get("numero")
    complemento = str(endereco_row.get("complemento") or "").strip()
    num_compl = str(int(numero))[:5] if numero and int(numero) > 0 else ""
    num_compl = f"{num_compl} {complemento}"
    sobra = num_compl[16:46]
    num_compl = " " + num_compl[:16]
    base = str(endereco_row.get("endereco") or "").strip()
    endereco = base[: max(0, 40 - len(num_compl))] + num_compl
    if len(endereco) < 40:
        endereco = endereco + sobra[: 40 - len(endereco)]
    return endereco[:40].ljust(40)


def _gerar_nosso_numero_sync(cur, cod_banco: int, banco_febraban: int, conta_cedente: int, codigo_duplicata: int) -> int:
    """Réplica do ramo `Else` de `GeraNossoNumero` — sequencial puro, sem
    dígito verificador (banco 341 não cai em nenhum `ElseIf` bank-specific
    dessa função)."""
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
    """`titulos` (opcional): mesmo filtro por `drv.codigo` documentado em
    `cnab_bradesco_service._titulos_para_remessa_sync`."""
    filtro_codigos = ""
    params: tuple = (banco_febraban,)
    if titulos:
        placeholders = ",".join(["%s"] * len(titulos))
        filtro_codigos = f" AND drv.codigo IN ({placeholders})"
        params = (banco_febraban, *titulos)
    cur.execute(
        "SELECT drv.codigo, drv.duplicata, drv.desmembramento, drv.dt_vencimento, drv.valor, "
        "drv.conta_cedente, dr.cliente, dr.duplicata AS num_doc_cliente, dr.dt_emissao, dr.num_parcelas "
        "FROM duplicata_rec_venc drv "
        "JOIN duplicata_receber dr ON dr.codigo = drv.duplicata "
        "WHERE drv.situacao = 'A' AND drv.banco_cedente = %s AND (drv.transf_banco = 0 OR drv.transf_banco IS NULL)"
        + filtro_codigos +
        " ORDER BY drv.dt_vencimento",
        params,
    )
    return cur.fetchall()


def _montar_header_400(agencia: int, contacorrente: int, dv_contacorrente, razao_social: str, num_remessa: int) -> str:
    agora = datetime.now()
    return (
        "0"  # tipo registro
        + "1"  # código remessa
        + "REMESSA"
        + "01"
        + _a("COBRANCA", 15)
        + _n(agencia, 4)
        + "00"
        + _n(contacorrente, 5)
        + _a(dv_contacorrente, 1)
        + _a("", 8)
        + _a(razao_social, 30)
        + _n(BANCO_ITAU_CODIGO, 3)
        + _a("BANCO ITAU SA", 15)
        + agora.strftime("%d%m%y")
        + _a("", 294)
        + "000001"
    )


def _montar_detalhe_400(banco_row: dict, cgc_empresa: str, titulo: dict, cliente_row: dict, endereco_row: Optional[dict], nosso_numero: int, seq: int) -> str:
    vencimento = titulo["dt_vencimento"]
    emissao = titulo.get("dt_emissao") or date.today()
    valor = float(titulo["valor"] or 0)

    cgc_cpf = str(cliente_row.get("cgc_cpf") or "").strip()
    codigo_inscricao = "02" if len(cgc_cpf) > 11 else "01"  # mesma variável usada nas duas posições (ver docstring)

    num_doc = str(titulo.get("num_doc_cliente") or titulo["duplicata"])
    desmembramento = titulo.get("desmembramento") or 0
    num_parcelas = titulo.get("num_parcelas") or 1
    if num_parcelas > 1:
        num_doc = f"{num_doc}/{desmembramento:03d}"

    carteira = str(int(banco_row.get("carteira") or 0))  # Byte cru, sem padding — ver docstring
    cod_carteira = str(banco_row.get("cod_carteira") or "I").strip() or "I"

    nome = _a(cliente_row.get("nome"), 30)
    endereco = _montar_vendereco(endereco_row)
    bairro = _a((endereco_row or {}).get("bairro"), 12)
    cep = "".join(ch for ch in str((endereco_row or {}).get("cep") or "") if ch.isdigit()) or "0"
    cidade = _a((endereco_row or {}).get("cidade"), 15)
    estado = _a((endereco_row or {}).get("uf"), 2)
    auto_num_drv = titulo["codigo"]

    return (
        "1"  # tipo registro
        + codigo_inscricao  # "posição empresa" — na prática mostra o tipo do cliente, ver docstring
        + _n(cgc_empresa, 14)
        + _n(banco_row.get("agencia"), 4)
        + "00"
        + _n(banco_row.get("contacorrente"), 5)
        + _a(banco_row.get("dv_agencia_conta"), 1)
        + "    "
        + "0000"
        + _a(auto_num_drv, 25)
        + _n(nosso_numero, 8)
        + _n(0, 13)
        + carteira
        + _a("", 21)
        + cod_carteira
        + "01"  # Ocorrência — sempre "01" (entrada), hardcoded no legado
        + _a(num_doc, 10)
        + vencimento.strftime("%d%m%y")
        + _n(round(valor * 100), 13)
        + _n(BANCO_ITAU_CODIGO, 3)
        + "00000"  # agência cobradora
        + _n(banco_row.get("especie_doc") or 1, 2)
        + _a(banco_row.get("aceite") or "N", 1)
        + emissao.strftime("%d%m%y")
        + _n(banco_row.get("instr_cobranca_1"), 2)
        + _n(banco_row.get("instr_cobranca_2"), 2)
        + _n(round(valor * float(banco_row.get("mora_dia_pag") or 0) / 100 * 100), 13)
        + _n(0, 6)  # desconto até
        + _n(0, 13)  # valor do desconto
        + _n(0, 13)  # valor do IOF
        + _n(0, 13)  # abatimento
        + codigo_inscricao
        + _n(cgc_cpf, 14)
        + nome
        + _a("", 10)
        + endereco
        + bairro
        + _n(cep, 8)
        + cidade
        + estado
        + _a("", 30)  # sacador/avalista
        + _a("", 4)
        + _n(0, 6)  # data da mora
        + _n(0, 2)  # prazo
        + " "
        + _n(seq, 6)
    )


def _montar_trailer_400(qtd_reg_geral: int) -> str:
    return "9" + _a("", 393) + _n(qtd_reg_geral, 6)


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
        if int(banco_row.get("codigo") or 0) != BANCO_ITAU_CODIGO:
            return {"success": False, "message": "Geração de remessa implementada só para Bradesco (237), Inter (077) e Itaú (341) nesta fase."}
        if banco_row.get("integracao_api"):
            return {"success": False, "message": "Este banco está configurado para Integração por API — remessa em arquivo não se aplica."}

        cur.execute("SELECT cgc, rz_social FROM controle")
        controle = cur.fetchone() or {}
        cgc_empresa = str(controle.get("cgc") or "").strip()
        razao_social = str(controle.get("rz_social") or "").strip()

        titulos_encontrados = _titulos_para_remessa_sync(cur, BANCO_ITAU_CODIGO, titulos)
        if not titulos_encontrados:
            msg = "Nenhum dos títulos selecionados está pendente de remessa." if titulos else "Nenhum título aberto pendente de remessa para este banco."
            return {"success": False, "message": msg}

        num_remessa = int(float(banco_row.get("remessa") or 0)) + 1

        linhas = [_montar_header_400(banco_row.get("agencia"), banco_row.get("contacorrente"), banco_row.get("dv_contacorrente"), razao_social, num_remessa)]

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
            if not endereco_row:
                cur.execute(
                    "SELECT TOP 1 endereco, numero, complemento, bairro, cidade, uf, cep FROM cliente_end "
                    "WHERE codigo=%s AND tipo=2 ORDER BY tipo DESC",
                    (titulo["cliente"],),
                )
                endereco_row = cur.fetchone()

            nosso_numero = _gerar_nosso_numero_sync(
                cur, cod_banco, BANCO_ITAU_CODIGO, int(titulo.get("conta_cedente") or banco_row.get("contacorrente") or 0), titulo["codigo"],
            )
            qtd_titulos += 1
            linhas.append(_montar_detalhe_400(banco_row, cgc_empresa, titulo, cliente_row, endereco_row, nosso_numero, len(linhas) + 1))

            cur.execute("UPDATE duplicata_rec_venc SET transf_banco = 1, numero_boleto = %s WHERE codigo = %s", (nosso_numero, titulo["codigo"]))

        if qtd_titulos == 0:
            return {"success": False, "message": "Nenhum título válido (sem cliente cadastrado) pendente de remessa para este banco."}

        linhas.append(_montar_trailer_400(len(linhas) + 1))

        nome_arquivo = f"ITA{num_remessa:05d}.REM"
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
    try:
        return int(raw) / 100.0
    except ValueError:
        return 0.0


def _parse_data_cnab(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    if len(raw) != 6 or raw == "000000":
        return None
    try:
        return date(2000 + int(raw[4:6]), int(raw[2:4]), int(raw[0:2]))
    except ValueError:
        return None


def _parse_linhas(conteudo: str) -> dict:
    """Extrai os registros de detalhe do retorno CNAB400, sem tocar no
    banco de dados — usado tanto por `_processar_retorno_sync` (abaixo)
    quanto pela pré-visualização compartilhada
    (`cobranca_retorno_service.py`, ver `Importação do Arquivo de
    Retorno`). Retorna `{"error": msg}` ou `{"registros": [...]}`."""
    linhas = [l for l in conteudo.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]
    if not linhas or linhas[0][:19] != "02RETORNO01COBRANCA":
        return {"error": "Arquivo inválido — cabeçalho não é um retorno CNAB400."}

    registros = []
    for linha in linhas[1:]:
        if len(linha) < 116 or linha[0] != "1":
            registros.append({"ignorado": True})
            continue
        ocorrencia = linha[108:110].strip()

        if ocorrencia == "02":
            registros.append({"ignorado": False, "numero_boleto": None, "ocorrencia": ocorrencia,
                               "data_pag": None, "valor_pago": 0.0, "juros": 0.0, "desconto": 0.0, "documento": None})
            continue

        if ocorrencia == "06":
            if len(linha) < 266:
                registros.append({"ignorado": True})
                continue
            nosso_numero = linha[85:93].strip().lstrip("0") or "0"
            data_pg = _parse_data_cnab(linha[110:116]) or date.today()
            valor_pago = _parse_valor_cnab(linha[253:266])
            juros = _parse_valor_cnab(linha[266:279]) if len(linha) >= 279 else 0.0
            desconto = _parse_valor_cnab(linha[240:253])
            registros.append({
                "ignorado": False, "numero_boleto": nosso_numero, "ocorrencia": ocorrencia,
                "data_pag": data_pg, "valor_pago": valor_pago, "juros": juros, "desconto": desconto,
                "documento": None,
            })
        else:
            registros.append({"ignorado": True})
    return {"registros": registros}


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
        conta_cedente = int(banco_row.get("contacorrente") or 0)

        parsed = _parse_linhas(conteudo)
        if "error" in parsed:
            return {"success": False, "message": parsed["error"]}

        confirmados = 0
        baixados = 0
        nao_encontrados = []
        ignorados = 0

        for reg in parsed["registros"]:
            if reg["ignorado"]:
                ignorados += 1
                continue
            ocorrencia = reg["ocorrencia"]

            if ocorrencia == "02":
                confirmados += 1
                continue

            if ocorrencia == "06":
                nosso_numero = reg["numero_boleto"]
                cur.execute(
                    "SELECT codigo, situacao FROM duplicata_rec_venc "
                    "WHERE numero_boleto = %s AND banco_cedente = %s AND conta_cedente = %s",
                    (int(nosso_numero), BANCO_ITAU_CODIGO, conta_cedente),
                )
                row = cur.fetchone()
                if not row:
                    nao_encontrados.append(nosso_numero)
                    continue
                if row.get("situacao") == "PG":
                    continue  # já baixado antes — idempotente
                cur.execute(
                    "UPDATE duplicata_rec_venc SET situacao='PG', data_pag=%s, valor_pag=%s, "
                    "juros_pag=%s, desconto_pag=%s, ultima_mov_banco=%s WHERE codigo=%s",
                    (reg["data_pag"].isoformat(), reg["valor_pago"], reg["juros"], reg["desconto"], int(ocorrencia), row["codigo"]),
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

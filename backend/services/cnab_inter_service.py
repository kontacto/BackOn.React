"""Fase 2a — Motor CNAB do Banco Inter (código Febraban 077), segundo banco
coberto nesta fase (o primeiro foi Bradesco/237, ver `cnab_bradesco_service.py`).
Ver PENDENCIAS.md > "Bancos (Cadastro de Cobrança / Boleto / Boleto / CNAB)" >
"Fase 2a" para o desenho completo e os riscos conhecidos.

**Diferença estrutural importante em relação ao Bradesco**: o Inter usa
CNAB400 (registros de largura fixa 400, um por linha — remessa E retorno),
não CNAB240/lotes/segmentos como o Bradesco. Layout do registro de detalhe é
**não-padrão Febraban** (não é o layout genérico CNAB400 usado por
`cnab_bradesco_service.py` na leitura do retorno) — é um layout próprio do
Inter, confirmado campo-a-campo contra o legado (ver abaixo).

Fonte legada rastreada campo-a-campo (não presumida):
- `IntegracaoBancaria.bas` (`C:/Desenv/VB6/SQLSERVER/Geral/`) —
  `Gera_Header_400`/`Gera_Detalhe_400`/`Gera_Trailer_400`/`Gera_Txt_400`
  (ramos `.Banco = "077"` / `Val(...Banco) = 77`), `GeraNossoNumero` (ramo
  `CodBanco = 77`, sem dígito verificador — sequencial puro, igual ao já
  usado para o Bradesco).
- `Kontacto\frmrelbol4.frm` — **achado importante**: a tela `Geral\
  FrmGeraArqBan.frm` (usada para rastrear o Bradesco) só chama as funções
  CNAB240; `Gera_Header_400`/`Gera_Detalhe_400`/`Gera_Trailer_400`/
  `Gera_Txt_400` não são chamadas de lá — a princípio pareciam código morto.
  A chamada real está em `Kontacto\frmrelbol4.frm` (`Command2_Click`/
  `Command10_Click`, dispatch por `Val(Banco_Titulo)` incluindo `77`) — uma
  tela de emissão de boletos (PDF) que **também** gera a remessa quando
  `Check5` está marcado. Confirma que o motor do Inter é código real/
  alcançável (linha de negócio Kontacto), não abandonado — só não está
  cabeado na tela `Geral` usada pelo Bradesco.
- `Geral/FrmImpRetBan.frm` — `Processa_Retorno_inter` (função dedicada,
  distinta da genérica `Processa_Retorno` usada pelo Bradesco/Itaú/Sicredi),
  chamada de `Command1_Click` quando `Banco_Titulo = 77`.

**Achado de código morto no legado, replicado de forma consciente**: dentro
de `Gera_Detalhe_400`, o ramo `.Banco = "077"` calcula uma variável `X` no
layout Febraban genérico (mesmo padrão usado pelos outros bancos) mas
**nunca a usa** — o `INSERT` real que de fato grava a linha do arquivo usa
um segundo cálculo, totalmente diferente, com posições fixas específicas do
Inter ("112"/"0001"/"60"/"01"/"N" literais). Este módulo segue o `INSERT`
realmente executado (o que o legado de fato manda pro banco), tratando `X`
como sobra de código, não como o layout real — mesmo princípio de "Não
replicar truques VB6" já usado no restante do projeto. A soma de larguras
do registro de detalhe foi conferida byte a byte (soma manual = 400,
igual à do header/trailer) durante o rastreio.

**Retorno — leitura sem separador de linha**: `Processa_Retorno_inter` lê o
arquivo linha a linha só para VALIDAR o cabeçalho (`Left(Registro,19) =
"02RETORNO01COBRANCA"`), depois concatena TODO o conteúdo **sem** inserir
quebra de linha entre as linhas lidas, e localiza cada registro de detalhe
por busca de conteúdo (`InStr` do prefixo `"1" & "02" & CNPJ`), não por
posição fixa de linha — replicado aqui do mesmo jeito (remove toda quebra
de linha do conteúdo colado antes de buscar).

**Posição do Nosso Número — CORRIGIDA 2026-08-28, achado real contra
produção**: a versão original (2026-07-24, ver histórico abaixo) usava a
posição 98-107 (0-indexed `[97:107]`), concluída por dedução de formato
(mesma largura que `_n(nosso_numero, 10)` grava na remessa), mas **nunca
validada contra um `duplicata_rec_venc.numero_boleto` real** — os testes
"golden file" da época usavam cursor falso com respostas em fila fixa
(`FakeCursor`), que retornam "encontrado" na ordem chamada, não por
conteúdo da query; ou seja, o teste passava mesmo se o número extraído
fosse incorreto, porque nunca checava QUAL número foi de fato usado no
`WHERE`. Isso só foi descoberto ao processar um retorno real do Inter
contra o banco de produção do cliente real "KONTACTO REAL"
(`minimachine`/`BD_KONTACTO`) — 2 de 78 títulos vieram "não encontrado".
Investigação (consulta direta, só leitura, contra `duplicata_rec_venc`)
confirmou: a posição 98-107 nunca bateu com NENHUM dos 78 títulos reais
(nem os 2 "baixa" nem, testado à parte, os 76 "confirmação"); a posição
**70-81 (0-indexed `[70:81]`, 11 dígitos)** bateu com **os 78/78** —
inclusive reconferida contra o arquivo real de 2026-07-24 já citado
abaixo (MESQUITA/MAX PNEUS/AT2B: `90748479261`/`90748479873`/
`90748479188`, não `3016`/`3012`/`2975` como a posição antiga extraía).
Ou seja, a posição que a versão original descartou como "ID interno do
banco" é, na verdade, o Nosso Número real usado pelo Inter pra
identificar boletos registrados via API (`duplicata_rec_venc.registrado
= 1`, o caso de praticamente todo boleto real desta instalação) — a
posição 98-107 não corresponde a nada útil na prática. **Efeito real
antes desta correção**: toda baixa via Retorno do Inter contra título
genuinamente registrado provavelmente falhava silenciosamente
("não encontrado"), nunca dando baixa de verdade em nenhum título real
processado até hoje.

**Posições do retorno — demais campos validados contra arquivo real do
Inter (2026-07-24)**: `Ocorrencia` em 90-91, `Valor_Titulo` em 125-137,
`Valor_Pago` em 160-172, `Data_Pagamento` em 173-178 — bateram
byte-a-byte com o arquivo real sem precisar de ajuste (só o Nosso Número
precisou da correção acima). Cabeçalho (`"02RETORNO01COBRANCA"`) e a
busca por `"1"+"02"+CNPJ` também bateram exatamente. **Ocorrência "07"
apareceu no arquivo real** (não documentada em nenhum ramo do
`Processa_Retorno_inter` legado) — tratada como ignorada (mesmo
comportamento do legado: nenhum `ElseIf` cobre esse código, então nada
acontece).

**Simplificação deliberada, para ficar simétrico ao Bradesco já
implementado** (registrar, não é regra de negócio perdida): o legado NÃO
grava a baixa direto em `duplicata_rec_venc` durante a leitura do retorno —
ele só monta uma grade de revisão + tabela de staging `Boletos_Pendentes`,
exigindo um clique manual separado ("Confirma Baixa dos Títulos
Selecionados", `Command4_Click`/`Baixa_Titulo`) pra de fato gravar. Esse
fluxo de confirmação em duas etapas **também é o que o Bradesco usa** no
legado (mesma tela `FrmImpRetBan.frm`), mas a Fase 2a já decidiu, para o
Bradesco, aplicar a baixa direto no `POST /retorno` (sem etapa de revisão
manual) para casar com o contrato já construído no frontend (colar
conteúdo → processar → resumo). Este módulo segue a MESMA simplificação
para o Inter, pelos mesmos motivos.

**Achado adicional durante o rastreio de `Baixa_Titulo`, NÃO replicado
aqui nem no Bradesco (registrado como pendência)**: a baixa real do legado
também incrementa `Duplicata_Receber.Parcelas_Pagas` e, quando todas as
parcelas de uma duplicata estão pagas, marca `Duplicata_Receber.Situacao =
'PG'` — nenhuma das duas coisas está implementada aqui (nem no
`cnab_bradesco_service.py` já existente). Ver PENDENCIAS.md.

**Validado contra arquivo real do Inter (2026-07-24)**: o usuário forneceu
um arquivo de remessa real (header+1 título+trailer) e um de retorno real
(8 títulos, ocorrências 02/06/07 misturadas) no mesmo dia da implementação.
`_montar_header_400`/`_montar_detalhe_400`/`_montar_trailer_400` batem
**byte a byte** com a remessa real (nenhuma diferença). As posições de
leitura do retorno bateram todas com o arquivo real, com uma correção feita
nesse processo — ver nota acima sobre a posição do Nosso Número. **O que
ainda NÃO foi validado**: o fluxo de escrita no banco (`UPDATE
duplicata_rec_venc`) — os arquivos reais confirmam o PARSING está correto,
mas a aplicação da baixa contra dados reais (`duplicata_rec_venc.
numero_boleto`/`banco_cedente`/`conta_cedente`) segue só testada com dados
sintéticos/mockados, igual ao round trip ao vivo já feito pro Bradesco.
"""
import asyncio
import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional

from db.connection import _open_conn

BANCO_INTER_CODIGO = 77


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


def _matricial(value) -> str:
    """Réplica funcional de `EscreveMatricial` (Matricial.bas) — maiúsculas +
    remoção de acentuação (o legado troca caractere a caractere por uma
    tabela fixa; aqui usamos normalização Unicode, mesmo resultado prático,
    preservando o comprimento da string)."""
    s = "" if value is None else str(value)
    s = s.upper()
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _montar_vendereco(endereco_row: Optional[dict]) -> str:
    """Réplica do bloco de montagem de endereço comum a `Gera_Detalhe_400`
    (IntegracaoBancaria.bas:2630-2646) — não é lógica específica de um banco
    só (compartilhada por Itaú/341, Sicredi/748, Inter/077), mas só o Inter
    está implementado neste módulo."""
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
    """Réplica de `GeraNossoNumero` (linhas 1333-1384) restrita ao caminho do
    Inter (`CodBanco = 77`): sequencial puro, sem dígito verificador — mesma
    lógica já usada por `cnab_bradesco_service._gerar_nosso_numero_sync`
    (duplicada aqui de propósito, não extraída pra um módulo comum — ver
    docstring de `cnab_bradesco_service.py`: cada motor de banco é um módulo
    autocontido, mesmo padrão já estabelecido na Fase 2a)."""
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
    """Mesma query/mesma simplificação deliberada (`transf_banco=0`) já
    documentada em `cnab_bradesco_service._titulos_para_remessa_sync`.
    `titulos` (opcional): mesmo filtro por `drv.codigo` documentado lá."""
    filtro_codigos = ""
    params: tuple = (banco_febraban,)
    if titulos:
        placeholders = ",".join(["%s"] * len(titulos))
        filtro_codigos = f" AND drv.codigo IN ({placeholders})"
        params = (banco_febraban, *titulos)
    cur.execute(
        "SELECT drv.codigo, drv.duplicata, drv.desmembramento, drv.dt_vencimento, drv.valor, "
        "drv.conta_cedente, dr.cliente, dr.duplicata AS num_doc_cliente, dr.dt_emissao "
        "FROM duplicata_rec_venc drv "
        "JOIN duplicata_receber dr ON dr.codigo = drv.duplicata "
        "WHERE drv.situacao = 'A' AND drv.banco_cedente = %s AND (drv.transf_banco = 0 OR drv.transf_banco IS NULL)"
        + filtro_codigos +
        " ORDER BY drv.dt_vencimento",
        params,
    )
    return cur.fetchall()


def _montar_header_400(razao_social: str, num_remessa: int) -> str:
    agora = datetime.now()
    return (
        "0"  # tipo registro
        + "1"  # código remessa
        + "REMESSA"
        + "01"
        + _a("COBRANCA", 15)
        + _a("", 20)
        + _a(razao_social, 30)
        + "077"
        + _a("INTER", 15)
        + agora.strftime("%d%m%y")
        + _a("", 10)
        + _n(num_remessa, 7)
        + _a("", 277)
        + "000001"
    )


def _montar_detalhe_400(banco_row: dict, titulo: dict, cliente_row: dict, endereco_row: Optional[dict], nosso_numero: int, seq: int) -> str:
    vencimento = titulo["dt_vencimento"]
    vencimento_mais_1 = vencimento + timedelta(days=1)
    valor = float(titulo["valor"] or 0)
    multa_atraso = float(banco_row.get("Multa_Atraso_Pag") or 0)
    mora_dia = float(banco_row.get("mora_dia_pag") or 0)

    multaca_centavos = round(round(valor * mora_dia / 100, 2) * 100)
    if multaca_centavos == 0:
        multaca_centavos = 1

    cgc_cpf = str(cliente_row.get("cgc_cpf") or "").strip()
    codigo_inscricao = "02" if len(cgc_cpf) > 11 else "01"
    nome = _matricial(_a(cliente_row.get("nome"), 40))
    endereco = _matricial(_montar_vendereco(endereco_row))
    cep = "".join(ch for ch in str((endereco_row or {}).get("cep") or "") if ch.isdigit()) or "0"
    auto_num_drv = titulo["codigo"]  # AutoNumDRV = drv.codigo (Rec2GeralBoleto("codigodrv"))

    return (
        "1"  # tipo registro
        + _a("", 19)
        + "112"
        + "0001"
        + _n(banco_row.get("contacorrente"), 10)
        + _a(auto_num_drv, 25)
        + "   "
        + "2"
        + _n(0, 13)
        + _n(round(multa_atraso * 100), 4)
        + vencimento_mais_1.strftime("%d%m%y")
        + _n(0, 11)
        + _a("", 8)
        + "01"
        + _n(nosso_numero, 10)
        + vencimento.strftime("%d%m%y")
        + _n(round(valor * 100), 13)
        + "60"
        + _a("", 6)
        + "01"
        + "N"
        + _a("", 6)
        + "   "
        + "1"
        + _n(multaca_centavos, 13)
        + "0000"
        + vencimento_mais_1.strftime("%d%m%y")
        + "0"
        + _n(0, 13)
        + "0000"
        + "000000"
        + _n(0, 13)
        + codigo_inscricao
        + _n(cgc_cpf, 14)
        + nome
        + endereco
        + _n(cep, 8)
        + _a("", 70)
        + _n(seq, 6)
    )


def _montar_trailer_400(qtd_boletos: int, qtd_reg_geral: int) -> str:
    return "9" + _n(qtd_boletos, 6) + _a("", 387) + _n(qtd_reg_geral, 6)


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
        if int(banco_row.get("codigo") or 0) != BANCO_INTER_CODIGO:
            return {"success": False, "message": "Geração de remessa implementada só para Bradesco (237) e Inter (077) nesta fase."}
        if banco_row.get("integracao_api"):
            return {"success": False, "message": "Este banco está configurado para Integração por API — remessa em arquivo não se aplica."}

        cur.execute("SELECT rz_social FROM controle")
        controle = cur.fetchone() or {}
        razao_social = str(controle.get("rz_social") or "").strip()

        titulos_encontrados = _titulos_para_remessa_sync(cur, BANCO_INTER_CODIGO, titulos)
        if not titulos_encontrados:
            msg = "Nenhum dos títulos selecionados está pendente de remessa." if titulos else "Nenhum título aberto pendente de remessa para este banco."
            return {"success": False, "message": msg}

        num_remessa = int(float(banco_row.get("remessa") or 0)) + 1

        linhas = [_montar_header_400(razao_social, num_remessa)]

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
                cur, cod_banco, BANCO_INTER_CODIGO, int(titulo.get("conta_cedente") or banco_row.get("contacorrente") or 0), titulo["codigo"],
            )
            qtd_titulos += 1
            linhas.append(_montar_detalhe_400(banco_row, titulo, cliente_row, endereco_row, nosso_numero, len(linhas) + 1))

            cur.execute("UPDATE duplicata_rec_venc SET transf_banco = 1, numero_boleto = %s WHERE codigo = %s", (nosso_numero, titulo["codigo"]))

        if qtd_titulos == 0:
            return {"success": False, "message": "Nenhum título válido (sem cliente cadastrado) pendente de remessa para este banco."}

        linhas.append(_montar_trailer_400(qtd_titulos, len(linhas) + 1))

        nome_arquivo = f"CI400_001_{num_remessa:07d}.REM"
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


def _parse_data_ddmmyy(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    if len(raw) != 6 or raw == "000000":
        return None
    try:
        return date(2000 + int(raw[4:6]), int(raw[2:4]), int(raw[0:2]))
    except ValueError:
        return None


def _extrair_registros_retorno(conteudo_flat: str, identificador: str) -> list:
    registros = []
    pos = 0
    while True:
        achado = conteudo_flat.find(identificador, pos)
        if achado == -1:
            break
        registros.append(conteudo_flat[achado:achado + 400])
        pos = achado + 1
    return registros


def _parse_linhas(conteudo: str, cnpj_empresa: str) -> dict:
    """Extrai os registros de detalhe do retorno, sem tocar no banco de
    dados — usado tanto por `_processar_retorno_sync` (abaixo) quanto pela
    pré-visualização compartilhada (`cobranca_retorno_service.py`, ver
    `Importação do Arquivo de Retorno`). `cnpj_empresa` já formatado 14
    dígitos (mesma função `_n` deste módulo). Retorna `{"error": msg}` ou
    `{"registros": [...]}`, cada item com `{ignorado}` ou `{numero_boleto,
    ocorrencia, data_pag, valor_pago, juros, desconto, documento}` — para
    ocorrência "02" também `{codigo_interno}` (ver abaixo).

    **Ocorrência "02" (Confirmação de Título) — achado real 2026-08-28,
    completa o ciclo remessa→retorno**: é aqui que o Nosso Número
    DEFINITIVO do Inter é atribuído a um título nosso pela primeira vez —
    até este ponto, `duplicata_rec_venc.numero_boleto` só tem o valor
    provisório que nós mesmos geramos (`_gerar_nosso_numero_sync`).
    Réplica de `Processa_Retorno_inter`/`Command5_Click`
    (`FrmImpRetBan.frm`, confirmado contra o código real, não só
    dedução): `Uso da Empresa` (posição 38,25 1-indexed = `[37:62]`
    0-indexed) é o NOSSO controle — `_montar_detalhe_400` já grava
    `duplicata_rec_venc.codigo` exatamente aí (`auto_num_drv`, ver
    função acima) — e o Nosso Número real do banco vem ecoado na posição
    108,11 (1-indexed) = `[107:118]` 0-indexed (mesmo valor, confirmado
    ao vivo, também aparece em `[70:81]` nas linhas de ocorrência "02" —
    o legado lê de `[107:118]` especificamente pra esse tipo, replicado
    aqui). **Ocorrência "03" (Entrada Rejeitada)** nunca chega a ganhar
    Nosso Número real (o legado grava `0` no lugar) — tratada só como
    contagem informativa, igual já era antes desta correção."""
    conteudo_flat = "".join(
        l for l in conteudo.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    )
    if conteudo_flat[:19] != "02RETORNO01COBRANCA":
        return {"error": "Arquivo inválido — cabeçalho não é um retorno do Inter (CNAB400)."}

    identificador = "1" + "02" + cnpj_empresa
    achados = _extrair_registros_retorno(conteudo_flat, identificador)
    if not achados:
        return {"error": "Arquivo inválido — nenhum registro de título encontrado (CNPJ não confere)."}

    registros = []
    for registro in achados:
        if len(registro) < 178:
            registros.append({"ignorado": True})
            continue
        ocorrencia = registro[89:91].strip()
        if ocorrencia == "02":
            codigo_interno = registro[37:62].strip().lstrip("0") or "0"
            numero_real = registro[107:118].strip().lstrip("0") or "0"
            registros.append({
                "ignorado": False, "numero_boleto": numero_real, "ocorrencia": ocorrencia,
                "codigo_interno": codigo_interno,
                "data_pag": None, "valor_pago": 0.0, "juros": 0.0, "desconto": 0.0, "documento": None,
            })
            continue
        if ocorrencia == "03":
            registros.append({"ignorado": False, "numero_boleto": None, "ocorrencia": ocorrencia,
                               "data_pag": None, "valor_pago": 0.0, "juros": 0.0, "desconto": 0.0, "documento": None})
            continue
        if ocorrencia == "06":
            # Posição corrigida 2026-08-28 — ver docstring do módulo pro
            # achado real (0/78 x 78/78 contra duplicata_rec_venc real).
            nosso_numero = registro[70:81].strip().lstrip("0") or "0"
            valor_titulo = _parse_valor_cnab(registro[124:137])
            valor_pago = _parse_valor_cnab(registro[159:172])
            data_pg = _parse_data_ddmmyy(registro[172:178]) or date.today()
            juros = max(0.0, round(valor_pago - valor_titulo, 2))
            desconto = max(0.0, round(valor_titulo - valor_pago, 2))
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

        cur.execute("SELECT cgc FROM controle")
        controle = cur.fetchone() or {}
        cnpj = _n(str(controle.get("cgc") or "").strip(), 14)

        parsed = _parse_linhas(conteudo, cnpj)
        if "error" in parsed:
            return {"success": False, "message": parsed["error"]}

        confirmados = 0
        registrados = 0
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
                codigo_interno = int(reg.get("codigo_interno") or 0)
                numero_real = int(reg.get("numero_boleto") or 0)
                if codigo_interno and numero_real:
                    cur.execute(
                        "UPDATE duplicata_rec_venc SET registrado=1, numero_boleto=%s WHERE codigo=%s",
                        (numero_real, codigo_interno),
                    )
                    registrados += 1
                continue

            if ocorrencia == "03":
                confirmados += 1
                continue

            if ocorrencia == "06":
                nosso_numero = reg["numero_boleto"]
                cur.execute(
                    "SELECT codigo, situacao FROM duplicata_rec_venc "
                    "WHERE numero_boleto = %s AND banco_cedente = %s AND conta_cedente = %s",
                    (int(nosso_numero), BANCO_INTER_CODIGO, conta_cedente),
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
            "registrados": registrados,
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

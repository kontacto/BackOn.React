"""Gestor NFCe — migração de `Geral\\FrmTraNFC.frm` (2184 linhas, lido por
completo 2026-08-19, não fragmento — ver CLAUDE.md §12). Lista comandas
com/sem NFC-e emitida e oferece: cancelar (documento fiscal, não a venda —
decisão explícita do usuário), consultar situação no SEFAZ, inutilizar
faixa de numeração, retransmitir NFC-e não transmitida, validar
contingência (transmitir NFC-e que ficou aguardando durante uma
contingência — ver `contingencia_nfce_service.py`) e gerar/baixar o XML já
armazenado.

**Achados da releitura completa da fonte, corrigindo uma leitura
superficial anterior** (ver PENDENCIAS.md > "Gestor NFCe" pro detalhe
completo):
- Bloqueio "alguma linha ruim" (não homogeneidade) pra Cancelar/
  Consultar/Inutilizar — bloqueia se QUALQUER linha selecionada está num
  estado que não serve pra ação.
- Bloqueio de HOMOGENEIDADE (todas as linhas no MESMO estado) só pra
  Retransmitir e Validar Contingência — únicas 2 ações que exigem isso
  na fonte.
- Um bloqueio baseado em `EmContingencia`/`PrimeiraNFCe` está copiado em
  quase toda ação da fonte, mas essas variáveis nunca são setadas
  `True` fora de Retransmitir/Validar Contingência — código morto por
  copy-paste do VB6, não replicado aqui.
- Contingência aberta (`contingencia_nfce_service.contingencia_
  aberta_sync`) bloqueia SÓ Cancelar/Consultar/Inutilizar — nunca
  bloqueou Gerar XML nem Imprimir na fonte.

**NUNCA testado contra o SEFAZ real** — mesma ressalva de todo o resto
do pacote fiscal desta migração. URLs de webservice (Consulta Protocolo
e Inutilização) confirmadas 2026-08-19 direto no Portal SVRS
(`dfe-portal.svrs.rs.gov.br/Nfce/Servicos`), não inventadas.
"""
import asyncio
import re
from datetime import date, datetime, timezone
from typing import Optional

from db.connection import _open_conn
from services import contingencia_nfce_service, nfe_cancelamento_service, nfe_emissao_service, nfe_fiscal_common
from services.permissoes_service import tem_permissao

_NFE_NS = nfe_fiscal_common.NFE_NS


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    """Checagem de permissão padrão pra toda ação do Gestor NFCe — mesmo
    padrão já usado em `comanda_service.py` (`tem_permissao`, tela única
    pro catálogo inteiro desta tela)."""
    return not master and classe is not None and not tem_permissao(cur, classe, "GESTOR_NFCE", comando)

# Endpoints "consulta protocolo" e "inutilização", versão 4.00, grupo SVRS
# (mesmo recorte de UF já documentado em `nfe_cancelamento_service.py`) —
# confirmados 2026-08-19 direto no Portal SVRS, não inferidos por padrão
# de nome como os outros endpoints já existentes neste pacote. Movidos pra
# `nfe_fiscal_common.py` 2026-08-20 (ganharam a chave "55"/NFe também, ao
# implementar Inutilização de Faixa NFe) — aliases locais preservados pra
# não precisar renomear todo o resto deste arquivo.
_ENDPOINTS_CONSULTA = nfe_fiscal_common.ENDPOINTS_CONSULTA_PROTOCOLO
_ENDPOINTS_INUTILIZACAO = nfe_fiscal_common.ENDPOINTS_INUTILIZACAO

# **Correção real de schema, 2026-08-20** (mesmo achado/mesma causa raiz já
# documentada em `contingencia_nfce_service.py`): `inutilizacao_nfe` JÁ
# EXISTE no legado — confirmado ao vivo via `INFORMATION_SCHEMA`/
# `sys.indexes` (GERDELL/BARESTELA) ao rastrear `Geral\FrmTraINF.frm` pra
# implementar o lado NFe (`inutilizacao_nfe_service.py`). A versão anterior
# deste DDL (`id INT IDENTITY` + tipos "modernizados") nunca bateu com a
# tabela real: PK verdadeira é `codauto_inutilizacao`, `numero_inicial`/
# `numero_final` são FLOAT (não INT — herdado do legado, preservado por
# fidelidade), `motivo` é NVARCHAR(50) (não 500), `protocolo_sefaz` é
# NVARCHAR(20) (não 50), `data_registro` é NVARCHAR(30) — o legado grava
# uma STRING formatada à mão ("dd/mm/aaaa às hh:mm:ss"), não um DATETIME
# real —, e `usuario` é NVARCHAR(50) — texto livre (`UsuarioAtual`), não
# FK numérica. O `CREATE TABLE IF NOT EXISTS` nunca disparou contra um
# banco real (a tabela já existia com essa outra estrutura), então o
# mismatch nunca quebrou nada até agora — mas o INSERT já rodava sem
# popular `data_registro` (coluna nunca gravada) e gravando `usuario` como
# número cru numa coluna que o VB6 sempre leu como texto. Ambos corrigidos
# nesta rodada (ver `_inutilizar_faixa_sync` abaixo e `nfe_fiscal_common.
# resolver_usuario_texto_sync`).
_DDL_INUTILIZACAO_NFE = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'inutilizacao_nfe')
BEGIN
    CREATE TABLE inutilizacao_nfe (
        codauto_inutilizacao INT IDENTITY(1,1) PRIMARY KEY,
        numero_inicial FLOAT NULL,
        numero_final FLOAT NULL,
        serie NVARCHAR(3) NULL,
        modelo NVARCHAR(2) NULL DEFAULT '65',
        motivo NVARCHAR(50) NULL,
        protocolo_sefaz NVARCHAR(20) NULL,
        xml NVARCHAR(MAX) NULL,
        data_registro NVARCHAR(30) NULL,
        usuario NVARCHAR(50) NULL
    );
"""
_DDL_INUTILIZACAO_NFE += "END\n"


def _ensure_inutilizacao_nfe_table(cur) -> None:
    cur.execute(_DDL_INUTILIZACAO_NFE)


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------

def _list_nfce_sync(
    servidor: str, banco: str, *,
    data_venda_de: Optional[str] = None, data_venda_ate: Optional[str] = None,
    data_nfce_de: Optional[str] = None, data_nfce_ate: Optional[str] = None,
    comanda: Optional[int] = None, num_nfce: Optional[int] = None, cliente: Optional[int] = None,
    situacoes: Optional[list[str]] = None, incluir_sem_nfce: bool = True,
    somente_gaps: bool = False, classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Lista comandas com/sem NFC-e — simplificação deliberada do UNION ALL
    de 2 SELECTs da fonte (`Command1_Click`, um pra comandas COM NFCe via
    INNER JOIN, outro pra comandas SEM via `NOT IN`): um único `LEFT JOIN
    comanda_nfce` já produz o mesmo resultado (linhas sem NFCe vêm com
    `cn.*` NULL), sem precisar de UNION — não é mudança de regra, só
    simplificação de SQL. `LEFT JOIN cliente` também (a fonte usa INNER
    JOIN pro cliente na branch "com NFCe", o que excluiria comandas de
    "Clientes Diversos"/`cliente IS NULL` — corrigido aqui pra não perder
    dado, mesmo princípio já usado no resto do projeto).

    **Não implementados nesta rodada** (fora de escopo, não inventados):
    `excluir_ecf` (o conceito de nota ECF/cupom fiscal antigo não existe
    nesta migração) e `somente_tributados` (join a nível de item que
    aumenta a complexidade desproporcional ao valor pra esta rodada)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="ABRIR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para abrir o Gestor NFCe."}
        if not nfe_fiscal_common.modulo_nfce_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFCe está desativado — fale com o administrador do sistema."}
        where = []
        params: list = []
        if data_venda_de:
            where.append("c.data >= %s")
            params.append(data_venda_de)
        if data_venda_ate:
            where.append("c.data <= %s")
            params.append(data_venda_ate)
        if data_nfce_de:
            where.append("cn.dhemi >= %s")
            params.append(data_nfce_de)
        if data_nfce_ate:
            where.append("cn.dhemi <= %s")
            params.append(f"{data_nfce_ate} 23:59:59")
        if comanda:
            where.append("c.comanda = %s")
            params.append(comanda)
        if num_nfce:
            where.append("cn.num_nfce = %s")
            params.append(num_nfce)
        if cliente:
            where.append("c.cliente = %s")
            params.append(cliente)
        if situacoes:
            placeholders = ",".join(["%s"] * len(situacoes))
            clausula_sit = f"cn.situacao IN ({placeholders})"
            params.extend(situacoes)
            if incluir_sem_nfce:
                where.append(f"({clausula_sit} OR cn.situacao IS NULL)")
            else:
                where.append(clausula_sit)
        elif not incluir_sem_nfce:
            where.append("cn.situacao IS NOT NULL")

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        cur.execute(
            f"""
            SELECT c.comanda, c.data, c.valor_venda, c.cliente,
                   ISNULL(cli.nome, 'CLIENTES DIVERSOS') AS cliente_nome,
                   cn.num_nfce, cn.serie_nfce, cn.situacao, cn.dhemi, cn.protocolo_sefaz,
                   cn.chave_acesso, cn.vnf
            FROM comanda c
            LEFT JOIN comanda_nfce cn ON cn.comanda = c.comanda
            LEFT JOIN cliente cli ON cli.codigo = c.cliente
            {where_sql}
            ORDER BY c.data DESC, c.comanda DESC
            """,
            tuple(params),
        )
        linhas = cur.fetchall()

        gaps: list[dict] = []
        if somente_gaps:
            gaps = _detectar_gaps_sync(cur, data_nfce_de=data_nfce_de, data_nfce_ate=data_nfce_ate)

        cur.close()
        conn.close()
        itens = [{
            "comanda": r["comanda"], "data": str(r.get("data")) if r.get("data") else None,
            "valor_venda": float(r.get("valor_venda") or 0), "cliente": r.get("cliente"),
            "cliente_nome": (r.get("cliente_nome") or "").strip(),
            "num_nfce": r.get("num_nfce"), "serie_nfce": (r.get("serie_nfce") or "").strip() or None,
            "situacao": (r.get("situacao") or "").strip() or None,
            "dhemi": str(r.get("dhemi")) if r.get("dhemi") else None,
            "protocolo_sefaz": (r.get("protocolo_sefaz") or "").strip() or None,
            "chave_acesso": (r.get("chave_acesso") or "").strip() or None,
            "vnf": float(r.get("vnf") or 0) if r.get("vnf") is not None else None,
        } for r in linhas]
        if somente_gaps:
            itens = [i for i in itens if i["num_nfce"] in {g["numero"] for g in gaps}]
        return {"success": True, "itens": itens, "gaps": gaps}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _detectar_gaps_sync(cur, *, data_nfce_de: Optional[str], data_nfce_ate: Optional[str]) -> list[dict]:
    """Detecção de gaps na numeração — porte da INTENÇÃO de `Check12`
    (`mdl_proc.bas`/`FrmTraNFC.frm:658-727`), não da implementação: a
    fonte usa uma tabela temporária populada número a número (workaround
    VB6-era pra falta de `GENERATE_SERIES` — "Não replicar truques
    VB6"). Aqui: busca MIN/MAX por série e computa os números ausentes
    em Python (set difference), sem tabela temporária nenhuma."""
    where = []
    params: list = []
    if data_nfce_de:
        where.append("dhemi >= %s")
        params.append(data_nfce_de)
    if data_nfce_ate:
        where.append("dhemi <= %s")
        params.append(f"{data_nfce_ate} 23:59:59")
    where_sql = f"AND {' AND '.join(where)}" if where else ""
    cur.execute(
        f"SELECT serie_nfce, MIN(num_nfce) AS minimo, MAX(num_nfce) AS maximo "
        f"FROM comanda_nfce WHERE num_nfce IS NOT NULL {where_sql} GROUP BY serie_nfce",
        tuple(params),
    )
    faixas = cur.fetchall()
    gaps: list[dict] = []
    for faixa in faixas:
        serie = (faixa.get("serie_nfce") or "").strip()
        minimo, maximo = int(faixa["minimo"]), int(faixa["maximo"])
        if maximo <= minimo:
            continue
        cur.execute(
            "SELECT num_nfce FROM comanda_nfce WHERE serie_nfce = %s AND num_nfce BETWEEN %s AND %s",
            (serie, minimo, maximo),
        )
        existentes = {int(r["num_nfce"]) for r in cur.fetchall()}
        ausentes = set(range(minimo, maximo + 1)) - existentes
        gaps.extend({"serie": serie, "numero": n} for n in sorted(ausentes))
    return gaps


# ---------------------------------------------------------------------------
# Cancelar — só o documento fiscal (decisão explícita do usuário,
# 2026-08-19: não reverte a venda, isso continua exclusivo de Alterar
# Comandas > Cancelar).
# ---------------------------------------------------------------------------

def _cancelar_nfce_sync(
    servidor: str, banco: str, *, comandas: list[int], motivo: str,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="CANCELAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar NFC-e."}
        if not nfe_fiscal_common.modulo_nfce_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFCe está desativado — fale com o administrador do sistema."}
        if contingencia_nfce_service.contingencia_aberta_sync(cur):
            conn.close()
            return {"success": False, "message": "Não é possível cancelar NFC-e com uma contingência aberta."}

        cur.execute("SELECT cgc, uf FROM controle")
        controle = cur.fetchone() or {}
        tp_amb = nfe_fiscal_common.resolver_tp_amb_sync(cur)
        resultados = []
        for comanda in comandas:
            cur.execute(
                "SELECT comanda, num_nfce, situacao, protocolo_sefaz, chave_acesso "
                "FROM comanda_nfce WHERE comanda = %s ORDER BY autonum DESC",
                (comanda,),
            )
            linha = cur.fetchone()
            if not linha or not linha.get("num_nfce"):
                resultados.append({"comanda": comanda, "success": False, "message": "Comanda sem NFC-e emitida."})
                continue
            if (linha.get("situacao") or "").strip().upper() == "C":
                resultados.append({"comanda": comanda, "success": False, "message": "NFC-e já cancelada."})
                continue
            r = nfe_cancelamento_service.cancelar_nfe_sync(
                cur, cnpj=(controle.get("cgc") or ""), uf_sigla=(controle.get("uf") or ""), modelo="65",
                chave_acesso=(linha.get("chave_acesso") or ""), protocolo=(linha.get("protocolo_sefaz") or ""),
                motivo=motivo, tp_amb=tp_amb,
            )
            if r.get("success"):
                cur.execute("UPDATE comanda_nfce SET situacao = 'C' WHERE comanda = %s", (comanda,))
            resultados.append({"comanda": comanda, **r})
        conn.commit()
        cur.close()
        conn.close()
        falhas = [r for r in resultados if not r.get("success")]
        return {"success": not falhas, "resultados": resultados}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Consultar situação no SEFAZ
# ---------------------------------------------------------------------------

def _montar_xml_consulta(chave_acesso: str, tp_amb: str) -> bytes:
    """`<consSitNFe>` — layout público NFe 4.00 (`consSitNFe_v4.00.xsd`),
    não extraído de DLL — validar contra o XSD oficial antes de
    transmitir de verdade (mesma ressalva do resto do pacote)."""
    return (
        f'<consSitNFe xmlns="{_NFE_NS}" versao="4.00">'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<xServ>CONSULTAR</xServ>'
        f'<chNFe>{chave_acesso}</chNFe>'
        f'</consSitNFe>'
    ).encode("utf-8")


def _consultar_situacao_uma_sync(cur, *, chave_acesso: str, tp_amb: str) -> dict:
    cod_ibge = chave_acesso[:2]
    url = nfe_fiscal_common.resolver_endpoint(cod_ibge, "65", tp_amb, _ENDPOINTS_CONSULTA)
    if not url:
        return {"success": False, "message": "Consulta ao SEFAZ não disponível pra essa UF."}
    cert = nfe_fiscal_common.carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado."}
    key_pem, cert_pem = cert
    try:
        xml_consulta = _montar_xml_consulta(chave_acesso, tp_amb)
        # "NFeConsultaProtocolo4" (F/e maiúsculos) — achado ao vivo
        # 2026-08-24, confirmado baixando o WSDL público real
        # (`nfce.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx?wsdl`,
        # com o certificado real — precisa de TLS mútuo até pra ler o
        # WSDL): o `targetNamespace` real é `NFeConsultaProtocolo4`, não
        # `NfeConsultaProtocolo4` (o "f" minúsculo usado antes aqui) — 2
        # strings tecnicamente diferentes num identificador de namespace/
        # SOAPAction, sensível a maiúsculas/minúsculas. Esse erro nunca
        # tinha sido pego porque a falta do header `action` (achado
        # irmão, ver `nfe_fiscal_common.transmitir`) mascarava o erro de
        # casing por trás — o SVRS recusava antes mesmo de checar se a
        # action fazia sentido.
        envelope = nfe_fiscal_common.montar_envelope_soap(xml_consulta, "NFeConsultaProtocolo4")
        soap_action = f"{_NFE_NS}/wsdl/NFeConsultaProtocolo4/nfeConsultaNF"
        resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem, soap_action=soap_action)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    # `retConsSitNFe` tem 2 `cStat` aninhados (status da consulta em si, e
    # status da NFe dentro de `protNFe/infProt`) — `extrair_tag` (regex
    # ingênuo) pegaria sempre o primeiro; aqui usamos lxml pra pegar o
    # da NFe de verdade, dentro de `protNFe`.
    from lxml import etree
    try:
        root = etree.fromstring(resposta.encode("utf-8") if isinstance(resposta, str) else resposta)
    except Exception:
        return {"success": False, "message": "Resposta do SEFAZ em formato inesperado."}
    ns = {"n": _NFE_NS}
    inf_prot = root.find(".//n:protNFe/n:infProt", ns)
    if inf_prot is None:
        c_stat_geral = root.findtext(".//n:cStat", namespaces=ns)
        x_motivo_geral = root.findtext(".//n:xMotivo", namespaces=ns)
        return {"success": True, "situacao_sefaz": c_stat_geral, "motivo_sefaz": x_motivo_geral, "protocolo": None}
    c_stat = inf_prot.findtext("n:cStat", namespaces=ns)
    x_motivo = inf_prot.findtext("n:xMotivo", namespaces=ns)
    n_prot = inf_prot.findtext("n:nProt", namespaces=ns)
    return {"success": True, "situacao_sefaz": c_stat, "motivo_sefaz": x_motivo, "protocolo": n_prot}


def _consultar_situacao_sync(
    servidor: str, banco: str, *, comandas: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="CONSULTAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para consultar situação de NFC-e."}
        if not nfe_fiscal_common.modulo_nfce_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFCe está desativado — fale com o administrador do sistema."}
        if contingencia_nfce_service.contingencia_aberta_sync(cur):
            conn.close()
            return {"success": False, "message": "Não é possível consultar situação com uma contingência aberta."}
        tp_amb = nfe_fiscal_common.resolver_tp_amb_sync(cur)
        resultados = []
        for comanda in comandas:
            cur.execute(
                "SELECT chave_acesso FROM comanda_nfce WHERE comanda = %s ORDER BY autonum DESC",
                (comanda,),
            )
            linha = cur.fetchone()
            if not linha or not (linha.get("chave_acesso") or "").strip():
                resultados.append({"comanda": comanda, "success": False, "message": "Comanda sem NFC-e emitida."})
                continue
            r = _consultar_situacao_uma_sync(cur, chave_acesso=linha["chave_acesso"].strip(), tp_amb=tp_amb)
            resultados.append({"comanda": comanda, **r})
        cur.close()
        conn.close()
        return {"success": True, "resultados": resultados}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Inutilizar faixa
# ---------------------------------------------------------------------------

def _montar_xml_inutilizacao(
    *, cod_ibge: str, cnpj: str, serie: str, numero_inicial: int, numero_final: int, motivo: str, tp_amb: str,
) -> tuple[bytes, str]:
    """Alias fino pro lado NFC-e (`modelo="65"`) — a construção do XML em
    si foi generalizada e movida pra `nfe_fiscal_common.montar_xml_
    inutilizacao` 2026-08-20, ao implementar o lado NFe (`inutilizacao_
    nfe_service.py`), que precisa do mesmo XML com `modelo="55"`. Mantido
    aqui como alias (mesmo padrão já usado pra `resolver_destinatario_
    cliente_sync`/`nfe_agrupada_service._resolver_destinatario_sync`) pra
    não quebrar `test_gestor_nfce_service.py`, que chama `svc._montar_xml_
    inutilizacao` diretamente."""
    return nfe_fiscal_common.montar_xml_inutilizacao(
        modelo="65", cod_ibge=cod_ibge, cnpj=cnpj, serie=serie,
        numero_inicial=numero_inicial, numero_final=numero_final, motivo=motivo, tp_amb=tp_amb,
    )


def _inutilizar_faixa_sync(
    servidor: str, banco: str, *, numeros: list[int], serie: str, motivo: str, usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Réplica de `Command7_Click` (`FrmTraNFC.frm:1516-1600`): 1 chamada
    de inutilização por número selecionado (`numero_inicial=numero_
    final`), fiel à fonte — não agrupa em faixas contíguas (não
    confirmado que a fonte faz isso, não inventar essa otimização)."""
    motivo = (motivo or "").strip()
    if len(motivo) < 15:
        return {"success": False, "message": "O motivo precisa ter pelo menos 15 caracteres."}
    if len(motivo) > 50:
        return {"success": False, "message": "O motivo pode ter no máximo 50 caracteres."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="INUTILIZAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para inutilizar numeração de NFC-e."}
        if not nfe_fiscal_common.modulo_nfce_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFCe está desativado — fale com o administrador do sistema."}
        if contingencia_nfce_service.contingencia_aberta_sync(cur):
            conn.close()
            return {"success": False, "message": "Não é possível inutilizar numeração com uma contingência aberta."}
        _ensure_inutilizacao_nfe_table(cur)
        cur.execute("SELECT cgc, uf FROM controle")
        controle = cur.fetchone() or {}
        cod_ibge = nfe_fiscal_common.IBGE_POR_UF.get((controle.get("uf") or "").strip().upper())
        if not cod_ibge:
            conn.close()
            return {"success": False, "message": f"UF '{controle.get('uf')}' não reconhecida."}
        tp_amb = nfe_fiscal_common.resolver_tp_amb_sync(cur)
        url = nfe_fiscal_common.resolver_endpoint(cod_ibge, "65", tp_amb, _ENDPOINTS_INUTILIZACAO)
        if not url:
            conn.close()
            return {"success": False, "message": "Inutilização não disponível pra essa UF."}
        cert = nfe_fiscal_common.carregar_certificado_sync(cur)
        if not cert:
            conn.close()
            return {"success": False, "message": "Nenhum certificado digital válido cadastrado."}
        key_pem, cert_pem = cert

        resultados = []
        for numero in numeros:
            # Réplica de Command7: consulta o SEFAZ antes — só inutiliza
            # se confirmado que o número não foi de fato autorizado.
            cur.execute(
                "SELECT chave_acesso FROM comanda_nfce WHERE num_nfce = %s AND serie_nfce = %s", (numero, serie),
            )
            linha = cur.fetchone()
            if linha and (linha.get("chave_acesso") or "").strip():
                consulta = _consultar_situacao_uma_sync(cur, chave_acesso=linha["chave_acesso"].strip(), tp_amb=tp_amb)
                if consulta.get("success") and consulta.get("situacao_sefaz") == "100":
                    resultados.append({
                        "numero": numero, "success": False,
                        "message": "Número já autorizado no SEFAZ — não é possível inutilizar.",
                    })
                    continue
            try:
                xml_inut, id_inut = _montar_xml_inutilizacao(
                    cod_ibge=cod_ibge, cnpj=(controle.get("cgc") or ""), serie=serie,
                    numero_inicial=numero, numero_final=numero, motivo=motivo, tp_amb=tp_amb,
                )
                # sha1=True — mesmo achado do MDF-e/NFC-e (2026-08-23), ver
                # `nfe_cancelamento_service._assinar_evento`.
                xml_assinado = nfe_fiscal_common.assinar_xml(xml_inut, id_inut, key_pem, cert_pem, sha1=True)
                # "NFeInutilizacao4" (F/e maiúsculos) + `soap_action` —
                # mesmo achado ao vivo 2026-08-24 já confirmado pra
                # `NFeConsultaProtocolo4` (ver comentário lá): baixado o
                # WSDL público real (`nfeinutilizacao4.asmx?wsdl`, com o
                # certificado — precisa de TLS mútuo até pra ler o WSDL)
                # e confirmado `targetNamespace`/`soapAction` reais.
                # **Corrigido preventivamente por semelhança, mas
                # Inutilização em si nunca foi testada ao vivo nesta
                # sessão** — validar contra uma tentativa real antes de
                # confiar 100%.
                envelope = nfe_fiscal_common.montar_envelope_soap(xml_assinado, "NFeInutilizacao4")
                soap_action_inut = f"{_NFE_NS}/wsdl/NFeInutilizacao4/nfeInutilizacaoNF"
                resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem, soap_action=soap_action_inut)
            except Exception as e:
                resultados.append({"numero": numero, "success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"})
                continue
            c_stat = nfe_fiscal_common.extrair_tag(resposta, "cStat")
            n_prot = nfe_fiscal_common.extrair_tag(resposta, "nProt")
            # 102 = "Inutilização de número homologada".
            if c_stat != "102":
                x_motivo = nfe_fiscal_common.extrair_tag(resposta, "xMotivo")
                resultados.append({
                    "numero": numero, "success": False,
                    "message": f"SEFAZ recusou a inutilização (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
                })
                continue
            usuario_texto = nfe_fiscal_common.resolver_usuario_texto_sync(cur, usuario)
            data_registro = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
            cur.execute(
                "INSERT INTO inutilizacao_nfe (numero_inicial, numero_final, serie, modelo, motivo, "
                "protocolo_sefaz, xml, data_registro, usuario) VALUES (%s, %s, %s, '65', %s, %s, %s, %s, %s)",
                (numero, numero, serie, motivo, n_prot, xml_assinado.decode("utf-8"), data_registro, usuario_texto),
            )
            cur.execute(
                "UPDATE comanda_nfce SET situacao = 'I' WHERE num_nfce = %s AND serie_nfce = %s", (numero, serie),
            )
            resultados.append({"numero": numero, "success": True, "protocolo_sefaz": n_prot})
        conn.commit()
        cur.close()
        conn.close()
        falhas = [r for r in resultados if not r.get("success")]
        return {"success": not falhas, "resultados": resultados}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Retransmitir / Validar Contingência — exigem homogeneidade de estado
# entre as linhas selecionadas (únicas 2 ações da fonte que exigem isso).
# ---------------------------------------------------------------------------

def _retransmitir_sync(
    servidor: str, banco: str, *, comandas: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Réplica de `Command9_Click` (`FrmTraNFC.frm:1712-1858`): exige
    homogeneidade (todas as linhas selecionadas "sem NFC-e"/"não
    transmitida"). **Adaptação real ao modelo de dados desta migração**:
    diferente do legado (que pode deixar uma NFC-e "assinada mas nunca
    transmitida" pendente em caso de falha), aqui uma emissão que falha
    nunca persiste linha alguma em `comanda_nfce` (`_emitir_nfce_
    comanda_sync` só grava depois do SEFAZ confirmar) — então o único
    caso real de "retransmitir" possível é comanda ainda sem NENHUMA
    NFC-e, o que é literalmente a MESMA emissão normal. Reaproveita
    `comanda_service._emitir_nfce_comanda_sync` (a mesma função que
    "Emitir NFC-e" já usa) em vez de duplicar a lógica de emissão."""
    from models.comanda import EmitirNfceRequest
    from services import comanda_service

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="RETRANSMITIR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para retransmitir NFC-e."}
        if not nfe_fiscal_common.modulo_nfce_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFCe está desativado — fale com o administrador do sistema."}
        for comanda in comandas:
            cur.execute("SELECT TOP 1 1 AS ok FROM comanda_nfce WHERE comanda = %s AND situacao <> 'C'", (comanda,))
            if cur.fetchone():
                conn.close()
                return {
                    "success": False,
                    "message": "Selecione só comandas sem NFC-e emitida pra retransmitir em lote (as demais já têm documento).",
                }
        cur.close()
        conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}

    resultados = []
    for comanda in comandas:
        req = EmitirNfceRequest(servidor=servidor, banco=banco, master=True)
        r = comanda_service._emitir_nfce_comanda_sync(req, comanda)
        resultados.append({"comanda": comanda, **r})
    falhas = [r for r in resultados if not r.get("success")]
    return {"success": not falhas, "resultados": resultados}


def _validar_contingencia_sync(
    servidor: str, banco: str, *, comandas: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Réplica de `Command5_Click` (`FrmTraNFC.frm:1356-1458`): exige que
    TODAS as linhas selecionadas estejam `situacao='G'` (aguardando —
    emitidas durante uma contingência ainda não fechada/transmitida).
    Reassina (chave/XML já gravados, `tpEmis` 5/9 preservado — nada
    recalculado) e transmite pelo MESMO envelope `NFeAutorizacao4` da
    emissão normal — não é uma operação SEFAZ especial (achado
    2026-08-19, ver docstring de `nfe_emissao_service.emitir_nfce_sync`).
    Ao suceder, `situacao='F'` (valor confirmado na fonte, linha 1420-1430).

    **2 bugs reais achados no PRIMEIRO teste ao vivo desta função,
    2026-08-26** (nunca tinha sido exercitada contra o SEFAZ real antes):
    (1) `id_nfe` tem que ser `NFe<chave_acesso>` (44 dígitos, mesmo Id da
    assinatura original), não `NFe<num_nfce>` — o assinador não achava o
    elemento referenciado, rejeitado localmente antes de sair pra rede;
    (2) `xml_guardado` é o documento FINAL já assinado E com
    `<infNFeSupl>` grudado (mesmo que a emissão original persiste) —
    reassinar esse documento como está deixa a assinatura antiga e o
    QR Code corrompidos ("Falha no Schema XML... infNFeSupl/qrCode").
    Corrigido replicando a sequência exata da emissão original: remove
    assinatura antiga + `infNFeSupl`, assina o XML limpo, regruda o MESMO
    bloco `infNFeSupl` depois (chave/URL não mudam)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="VALIDAR_CONT"):
            conn.close()
            return {"success": False, "message": "Sem permissão para validar contingência."}
        if not nfe_fiscal_common.modulo_nfce_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFCe está desativado — fale com o administrador do sistema."}
        linhas = {}
        for comanda in comandas:
            cur.execute(
                "SELECT comanda, num_nfce, situacao, chave_acesso, xml FROM comanda_nfce WHERE comanda = %s ORDER BY autonum DESC",
                (comanda,),
            )
            linha = cur.fetchone()
            if not linha or (linha.get("situacao") or "").strip().upper() != "G":
                conn.close()
                return {
                    "success": False,
                    "message": "Selecione só comandas com NFC-e aguardando contingência (situação 'G') pra validar em lote.",
                }
            linhas[comanda] = linha

        cert = nfe_fiscal_common.carregar_certificado_sync(cur)
        if not cert:
            conn.close()
            return {"success": False, "message": "Nenhum certificado digital válido cadastrado."}
        key_pem, cert_pem = cert
        tp_amb = nfe_fiscal_common.resolver_tp_amb_sync(cur)

        resultados = []
        for comanda, linha in linhas.items():
            xml_guardado = linha.get("xml")
            if not xml_guardado:
                resultados.append({"comanda": comanda, "success": False, "message": "XML da NFC-e não encontrado."})
                continue
            try:
                # Reassina o MESMO XML já montado (tpEmis 5/9 preservado —
                # nada é recalculado) e reusa o envelope de autorização
                # normal, igual à fonte (ValidaContingencia não é uma
                # operação SEFAZ separada, é a autorização normal atrasada).
                xml_texto = xml_guardado if isinstance(xml_guardado, str) else xml_guardado.decode("utf-8")
                # Achado real (teste ao vivo, 2026-08-26, 2ª rejeição depois
                # de corrigir o `id_nfe` abaixo): `xml_guardado` é o XML JÁ
                # assinado E JÁ com `<infNFeSupl>` (QR Code) grudado — mesmo
                # documento final persistido na emissão original (ver
                # `nfe_emissao_service.emitir_nfce_sync`'s string-splice
                # pós-assinatura). Assinar ESSE documento de novo (com a
                # assinatura antiga e o infNFeSupl ainda dentro) corrompe o
                # XML — SEFAZ recusou com "Falha no Schema XML da NFe
                # (Elemento: enviNFe/NFe[1]/infNFeSupl/qrCode/)". Réplica
                # exata da sequência da emissão original: remove assinatura
                # antiga + infNFeSupl, assina o XML "limpo", e regruda o
                # MESMO bloco infNFeSupl extraído (chave/URL não mudam,
                # nunca precisa ser reconstruído).
                supl_bloco = nfe_fiscal_common.extrair_bloco(xml_texto, "infNFeSupl") or ""
                xml_texto = re.sub(r"<infNFeSupl[ >].*?</infNFeSupl>", "", xml_texto, flags=re.DOTALL)
                xml_texto = re.sub(r"<(?:ds:)?Signature[ >].*?</(?:ds:)?Signature>", "", xml_texto, flags=re.DOTALL)
                xml_bytes = xml_texto.encode("utf-8")
                # Achado real (teste ao vivo, 2026-08-26): `id_nfe` tem que
                # ser o MESMO usado na assinatura original — `NFe<chave_
                # acesso>` (44 dígitos, ver `nfe_emissao_service.
                # _montar_xml_nfce`'s `id_nfe = f"NFe{chave_acesso}"`), não
                # `NFe<num_nfce>` (número sequencial curto). Usar o número
                # sequencial aqui referenciava um `Id` que não existe no XML
                # gravado — rejeitado ANTES de chegar no SEFAZ ("Unable to
                # resolve reference URI: #NFe2002"), já que o assinador não
                # acha o elemento com esse Id pra montar a `<ds:Reference>`.
                id_nfe = f"NFe{linha.get('chave_acesso')}"
                # sha1=True — mesmo achado do MDF-e/NFC-e (2026-08-23), ver
                # `nfe_cancelamento_service._assinar_evento`.
                xml_assinado = nfe_fiscal_common.assinar_xml(xml_bytes, id_nfe, key_pem, cert_pem, sha1=True)
                if supl_bloco:
                    xml_assinado = xml_assinado.replace(b"</infNFe>", f"</infNFe>{supl_bloco}".encode("utf-8"), 1)
                envelope = nfe_emissao_service._montar_envelope_autorizacao(xml_assinado, tp_amb)
                cod_ibge_resp = None
                cur.execute("SELECT uf FROM controle")
                uf_row = cur.fetchone() or {}
                cod_ibge_resp = nfe_fiscal_common.IBGE_POR_UF.get((uf_row.get("uf") or "").strip().upper())
                url = nfe_emissao_service._resolver_url_autorizacao(cod_ibge_resp, "65", tp_amb) if cod_ibge_resp else None
                if not url:
                    resultados.append({"comanda": comanda, "success": False, "message": "Endpoint SEFAZ não disponível pra essa UF."})
                    continue
                resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem)
            except Exception as e:
                resultados.append({"comanda": comanda, "success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"})
                continue
            # `retEnviNFe`/`retNFe` tem 2 `cStat` aninhados — o do LOTE
            # (nível externo, neutro, ex. 104 "Lote processado") e o do
            # DOCUMENTO de verdade, dentro de `infProt` (nível interno).
            # `extrair_tag` ingênuo pega o PRIMEIRO da string inteira (o
            # do lote) — mesmo bug já achado e corrigido em
            # `emitir_nfce_sync`/`emitir_nfe_sync` 2026-08-23, latente
            # aqui até agora porque "Validar Contingência" nunca tinha
            # sido exercitado ao vivo (achado+corrigido 2026-08-24, sem
            # rejeição real ainda — mesma classe de bug, aplicado por
            # analogia/consistência).
            inf_prot = nfe_fiscal_common.extrair_bloco(resposta, "infProt") or resposta
            c_stat = nfe_fiscal_common.extrair_tag(inf_prot, "cStat")
            n_prot = nfe_fiscal_common.extrair_tag(inf_prot, "nProt")
            dh_recbto = nfe_fiscal_common.extrair_tag(inf_prot, "dhRecbto")
            if c_stat != "100":
                x_motivo = nfe_fiscal_common.extrair_tag(inf_prot, "xMotivo")
                resultados.append({
                    "comanda": comanda, "success": False,
                    "message": f"SEFAZ recusou a autorização (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
                })
                continue
            cur.execute(
                "UPDATE comanda_nfce SET situacao = 'F', protocolo_sefaz = %s, dhemi = GETDATE() WHERE comanda = %s",
                (n_prot, comanda),
            )
            # `dh_recbto` cru do SEFAZ (ISO 8601 com offset) quebra numa
            # coluna DATETIME e derruba a transação DEPOIS do sucesso já
            # confirmado — mesmo bug achado ao vivo no MDF-e 2026-08-23,
            # corrigido aqui 2026-08-24 (ver `nfe_fiscal_common.parse_dh_sefaz`).
            cur.execute(
                "UPDATE n_fiscal SET situacao = 'A', cstat = %s, protocolo_sefaz = %s, dhRecbto = %s "
                "WHERE chave_acesso = %s",
                (c_stat, n_prot, nfe_fiscal_common.parse_dh_sefaz(dh_recbto), linha.get("chave_acesso")),
            )
            resultados.append({"comanda": comanda, "success": True, "protocolo_sefaz": n_prot})
        conn.commit()
        cur.close()
        conn.close()
        falhas = [r for r in resultados if not r.get("success")]
        return {"success": not falhas, "resultados": resultados}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Gerar/baixar XML — trivial, já armazenado.
# ---------------------------------------------------------------------------

def _gerar_xml_sync(
    servidor: str, banco: str, *, comanda: int, classe: Optional[int] = None, master: bool = False,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="ABRIR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para abrir o Gestor NFCe."}
        if not nfe_fiscal_common.modulo_nfce_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFCe está desativado — fale com o administrador do sistema."}
        cur.execute("SELECT xml, chave_acesso FROM comanda_nfce WHERE comanda = %s ORDER BY autonum DESC", (comanda,))
        linha = cur.fetchone()
        cur.close()
        conn.close()
        if not linha or not linha.get("xml"):
            return {"success": False, "message": "Comanda sem NFC-e emitida."}
        return {"success": True, "xml": linha["xml"], "chave_acesso": linha.get("chave_acesso")}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Wrappers async
# ---------------------------------------------------------------------------

async def list_nfce(servidor: str, banco: str, **kwargs) -> dict:
    return await asyncio.to_thread(_list_nfce_sync, servidor, banco, **kwargs)


async def cancelar_nfce(
    servidor: str, banco: str, comandas: list[int], motivo: str,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _cancelar_nfce_sync, servidor, banco, comandas=comandas, motivo=motivo, classe=classe, master=master,
    )


async def consultar_situacao(
    servidor: str, banco: str, comandas: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(_consultar_situacao_sync, servidor, banco, comandas=comandas, classe=classe, master=master)


async def inutilizar_faixa(
    servidor: str, banco: str, numeros: list[int], serie: str, motivo: str, usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _inutilizar_faixa_sync, servidor, banco, numeros=numeros, serie=serie, motivo=motivo, usuario=usuario,
        classe=classe, master=master,
    )


async def retransmitir(
    servidor: str, banco: str, comandas: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(_retransmitir_sync, servidor, banco, comandas=comandas, classe=classe, master=master)


async def validar_contingencia(
    servidor: str, banco: str, comandas: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(_validar_contingencia_sync, servidor, banco, comandas=comandas, classe=classe, master=master)


async def gerar_xml(
    servidor: str, banco: str, comanda: int, classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(_gerar_xml_sync, servidor, banco, comanda=comanda, classe=classe, master=master)

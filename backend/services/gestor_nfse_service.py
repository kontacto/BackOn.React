"""Gestor NFSe — Sefin Nacional/DPS (migração de `Geral\\FrmManNSeSefin.frm`,
ações "Selecionar" e "Recuperar Informações") — a listagem/consulta que
faltava do pacote de emissão de NFS-e (Fase 3, já implementada em
`comanda_service.py::_emitir_nfse_comanda_sync` + `nfse_emissao_service.py`
— ver PENDENCIAS.md > "Fase 3 — NFS-e"). **NÃO é o caminho antigo por RPS
municipal** (`Geral\\FrmManNSe.frm`, integração Ginfes/ABRASF por
prefeitura — telas separadas, órgãos separados) — decisão explícita do
usuário 2026-08-20: focar primeiro no padrão nacional, já em uso real pela
cidade do Rio de Janeiro (confirmado pelo usuário: "o município do Rio de
Janeiro usa esse [padrão nacional]").

**Fonte real dos dados: tabela `dps`, não `n_fiscal` sozinha** —
confirmado com 119 linhas reais em produção (conexão ARGEN TESTE,
2026-08-20, `STATUS='Transmitida'`, chaves de acesso de 50 posições reais)
— já alimentada corretamente por `_emitir_nfse_comanda_sync` desde a
sessão que implementou a Fase 3 (achado ao rastrear `FrmManNSeSefin.frm`
pra esta tela: a suposição inicial de que a emissão nunca gravava em `dps`
estava ERRADA — o INSERT já existe lá, só a tela de gestão em cima dele
que faltava).

**"Recuperar Informações"** replica `Backon_Controllers.NFSeDPS.
RetornaXMLDANFEDPS` (`NFSeDPS.vb:672-737`, rastreado direto na fonte) —
`GET https://sefin.nfse.gov.br/SefinNacional/nfse/{chave_acesso_nfse}`,
autenticado por TLS mútuo (mesmo padrão de `emitir_nfse_sync`, endpoints
já existentes em `nfse_emissao_service._ENDPOINTS_DPS`, reaproveitados
tal qual — nunca duplicados). Ao suceder, atualiza `dps.STATUS`/`dps.
XML_NFSE`.

**"Baixar DANFE" e "Enviar por e-mail" implementados 2026-08-20** — ver
seções mais abaixo. Rastreio real de `Command4_Click` ("Enviar por
e-mail", `FrmManNSeSefin.frm:763-856`) revelou que o legado depende de
ARQUIVOS LOCAIS já em disco (pasta `xml\\NFSe\\<ano>\\<mês>`, sob
`Path_Ativo`, nomeados pela chave)
— gambiarra de arquitetura pré-web, não regra de negócio (mesmo
princípio de "Não replicar truques VB6"). A regra de negócio REAL por
trás é "mandar o DANFE em PDF por e-mail pro cliente da comanda" — essa
parte foi replicada, buscando o PDF fresco do ADN em vez de um cache
local em disco que este backend nunca teve. Reaproveita a infra SMTP já
existente (`email_cobranca_service.enviar_email`, já testada ao vivo
pra Boletos) — nenhum motor de e-mail novo.

**NUNCA testado ao vivo contra o ADN real** — mesma ressalva de todo o
resto do pacote fiscal desta migração (CLAUDE.md §12).
"""
import asyncio
import base64
from typing import Optional

from db.connection import _open_conn
from services import email_cobranca_service, nfe_fiscal_common, nfse_emissao_service
from services.comanda_service import _modulo_sefin_nacional_ativo
from services.permissoes_service import tem_permissao

# Endpoint do DANFE em PDF (ADN) — host `adn.nfse.gov.br`, diferente do
# `sefin.nfse.gov.br` usado pra consulta/transmissão de DPS. Confirmado
# no rastreio original desta tela (2026-08-20) — só o host único foi
# encontrado, sem variante de homologação/produção restrita equivalente
# a `_ENDPOINTS_DPS` (`nfse_emissao_service.py`); **não confirmado contra
# o ADN real** — validar antes de depender disso em produção.
_URL_DANFE_NFSE = "https://adn.nfse.gov.br/danfse/{chave}"


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "GESTOR_NFSE", comando)


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------

def _list_nfse_sync(
    servidor: str, banco: str, *,
    data_de: Optional[str] = None, data_ate: Optional[str] = None,
    comanda: Optional[int] = None, cliente: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="ABRIR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para acessar o Gestor NFSe."}

        condicoes = ["1=1"]
        params: list = []
        if data_de:
            condicoes.append("dps.data_dps >= %s")
            params.append(data_de)
        if data_ate:
            condicoes.append("dps.data_dps <= %s")
            params.append(data_ate)
        if comanda:
            condicoes.append("dps.comanda = %s")
            params.append(comanda)
        if cliente:
            condicoes.append("cm.cliente = %s")
            params.append(cliente)

        cur.execute(
            "SELECT dps.codigo, dps.num_dps, dps.serie_dps, dps.data_dps, dps.valor_total, dps.STATUS, "
            "dps.situacao, dps.chave_acesso_dps, dps.chave_acesso_nfse, dps.comanda, "
            "cm.cliente AS cliente_codigo, cli.nome AS cliente_nome "
            "FROM dps "
            "JOIN comanda cm ON cm.comanda = dps.comanda "
            "LEFT JOIN cliente cli ON cli.codigo = cm.cliente "
            f"WHERE {' AND '.join(condicoes)} "
            "ORDER BY dps.codigo DESC",
            tuple(params),
        )
        itens = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "itens": itens}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Recuperar Informações (consulta situação/XML no ADN)
# ---------------------------------------------------------------------------

def _consultar_situacao_uma_sync(cur, *, chave_acesso_nfse: str, tp_amb: str) -> dict:
    url_base = nfse_emissao_service._resolver_url_dps(tp_amb)
    if not url_base:
        return {"success": False, "message": f"Ambiente '{tp_amb}' não reconhecido para consulta de NFS-e."}
    cert = nfe_fiscal_common.carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado."}
    key_pem, cert_pem = cert
    try:
        resposta = nfe_fiscal_common.consultar_json_mtls(f"{url_base}/{chave_acesso_nfse}", key_pem, cert_pem)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o ADN (Sefin Nacional): {e}"}
    if resposta.get("_erro_http"):
        mensagens = resposta.get("mensagens") or resposta.get("message") or resposta
        return {"success": False, "message": f"ADN recusou a consulta: {mensagens}"}
    return {"success": True, "resposta": resposta}


def _consultar_situacao_sync(
    servidor: str, banco: str, *, codigos: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Réplica de `Command3_Click` (`FrmManNSeSefin.frm:692-758`,
    "Recuperar Informações") — consulta cada NFS-e já transmitida no ADN,
    grava a resposta em `dps.STATUS`/`dps.XML_NFSE`."""
    if not codigos:
        return {"success": False, "message": "Selecione ao menos uma NFS-e."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="CONSULTAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para consultar situação de NFS-e."}
        if not _modulo_sefin_nacional_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo SEFIN Nacional não está ativo (Módulos e Recursos)."}
        tp_amb = nfe_fiscal_common.resolver_tp_amb_sync(cur)

        resultados = []
        for codigo in codigos:
            cur.execute("SELECT codigo, chave_acesso_nfse FROM dps WHERE codigo = %s", (codigo,))
            linha = cur.fetchone()
            chave = (linha.get("chave_acesso_nfse") or "").strip() if linha else ""
            if not linha or not chave:
                resultados.append({"codigo": codigo, "success": False, "message": "NFS-e sem chave de acesso — ainda não transmitida."})
                continue
            r = _consultar_situacao_uma_sync(cur, chave_acesso_nfse=chave, tp_amb=tp_amb)
            if r.get("success"):
                resposta = r["resposta"]
                xml_nfse = None
                if resposta.get("nfseXmlGZipB64"):
                    try:
                        xml_nfse = nfse_emissao_service._desempacotar_nfse(resposta["nfseXmlGZipB64"])
                    except Exception:
                        xml_nfse = None
                cur.execute(
                    "UPDATE dps SET STATUS = 'Transmitida', XML_NFSE = %s WHERE codigo = %s",
                    (xml_nfse, codigo),
                )
                resultados.append({"codigo": codigo, "success": True})
            else:
                resultados.append({"codigo": codigo, "success": False, "message": r.get("message")})
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
# Baixar DANFE (PDF) — ADN, host `adn.nfse.gov.br`, distinto do endpoint
# de consulta/transmissão (`sefin.nfse.gov.br`).
# ---------------------------------------------------------------------------

def _obter_danfe_pdf_base64_sync(cur, *, codigo: int) -> dict:
    """Busca o PDF em cache (`dps.PDF_DANFE_NFSE`, `varbinary(max)`) —
    quando ausente, baixa do ADN e grava, evitando re-baixar em toda
    chamada seguinte."""
    cur.execute("SELECT codigo, chave_acesso_nfse, PDF_DANFE_NFSE FROM dps WHERE codigo = %s", (codigo,))
    linha = cur.fetchone()
    if not linha:
        return {"success": False, "message": "NFS-e não encontrada."}
    if linha.get("PDF_DANFE_NFSE"):
        return {"success": True, "pdf_base64": base64.b64encode(bytes(linha["PDF_DANFE_NFSE"])).decode("ascii")}

    chave = (linha.get("chave_acesso_nfse") or "").strip()
    if not chave:
        return {"success": False, "message": "NFS-e sem chave de acesso — ainda não transmitida."}

    cert = nfe_fiscal_common.carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado."}
    key_pem, cert_pem = cert
    try:
        pdf_bytes = nfe_fiscal_common.consultar_binario_mtls(_URL_DANFE_NFSE.format(chave=chave), key_pem, cert_pem)
    except Exception as e:
        return {"success": False, "message": f"Falha ao baixar o DANFE no ADN: {e}"}

    cur.execute("UPDATE dps SET PDF_DANFE_NFSE = %s WHERE codigo = %s", (pdf_bytes, codigo))
    return {"success": True, "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii")}


def _baixar_danfe_sync(servidor: str, banco: str, codigo: int, *, classe: Optional[int] = None, master: bool = False) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="CONSULTAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para baixar DANFE de NFS-e."}
        if not _modulo_sefin_nacional_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo SEFIN Nacional não está ativo (Módulos e Recursos)."}

        resultado = _obter_danfe_pdf_base64_sync(cur, codigo=codigo)
        if resultado.get("success"):
            conn.commit()
        cur.close()
        conn.close()
        return resultado
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Enviar por e-mail — réplica de `Command4_Click` (`FrmManNSeSefin.frm:
# 763-856`), mas sem depender de arquivo local em disco (gambiarra de
# arquitetura pré-web do legado, ver docstring do módulo) — o DANFE é
# baixado fresco do ADN (mesmo mecanismo de "Baixar DANFE" acima,
# reaproveitado por completo — cache em `dps.PDF_DANFE_NFSE` beneficia
# os dois) e anexado no e-mail via `email_cobranca_service`.
# ---------------------------------------------------------------------------

def _enviar_email_sync(
    servidor: str, banco: str, *, codigos: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    if not codigos:
        return {"success": False, "message": "Selecione ao menos uma NFS-e."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="CONSULTAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para enviar e-mail de NFS-e."}
        if not _modulo_sefin_nacional_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo SEFIN Nacional não está ativo (Módulos e Recursos)."}

        resultados = []
        for codigo in codigos:
            cur.execute(
                "SELECT dps.codigo, dps.num_dps, dps.comanda, cm.cliente, cli.nome AS cliente_nome, cli.e_mail "
                "FROM dps JOIN comanda cm ON cm.comanda = dps.comanda "
                "LEFT JOIN cliente cli ON cli.codigo = cm.cliente WHERE dps.codigo = %s",
                (codigo,),
            )
            linha = cur.fetchone()
            if not linha:
                resultados.append({"codigo": codigo, "success": False, "message": "NFS-e não encontrada."})
                continue
            email = (linha.get("e_mail") or "").strip()
            if not email:
                resultados.append({"codigo": codigo, "success": False, "message": "Cliente sem e-mail cadastrado."})
                continue

            pdf_resultado = _obter_danfe_pdf_base64_sync(cur, codigo=codigo)
            if not pdf_resultado.get("success"):
                resultados.append({"codigo": codigo, "success": False, "message": pdf_resultado.get("message")})
                continue

            corpo_html = (
                f"<p>Segue em anexo o DANFE da NFS-e nº {linha.get('num_dps')} "
                f"referente à comanda {linha.get('comanda')}.</p>"
            )
            anexo = {
                "conteudo": base64.b64decode(pdf_resultado["pdf_base64"]),
                "nome_arquivo": f"DANFE_NFSe_{linha.get('num_dps')}.pdf",
            }
            envio = email_cobranca_service._enviar_email_sync(
                servidor, banco, email, f"NFS-e nº {linha.get('num_dps')}", corpo_html, [anexo],
            )
            resultados.append({"codigo": codigo, "success": bool(envio.get("success")), "message": envio.get("message")})

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
# Wrappers async
# ---------------------------------------------------------------------------

async def list_nfse(servidor: str, banco: str, **kwargs) -> dict:
    return await asyncio.to_thread(_list_nfse_sync, servidor, banco, **kwargs)


async def consultar_situacao(servidor: str, banco: str, *, codigos: list[int], classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_consultar_situacao_sync, servidor, banco, codigos=codigos, classe=classe, master=master)


async def baixar_danfe(servidor: str, banco: str, codigo: int, *, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_baixar_danfe_sync, servidor, banco, codigo, classe=classe, master=master)


async def enviar_email(servidor: str, banco: str, *, codigos: list[int], classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_enviar_email_sync, servidor, banco, codigos=codigos, classe=classe, master=master)

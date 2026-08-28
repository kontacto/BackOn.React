"""Contingência NFe — migração de `Geral\\FrmConNFe.frm` (444 linhas, lido
por completo 2026-08-20). Mesma "infraestrutura mínima" já decidida pra
Contingência NFCe (`contingencia_nfce_service.py`) — só abrir/fechar/
consultar o estado atual, não a grade histórica completa (Excluir/edição
de registro antigo) — mesmo princípio, tela pequena e independente.

**Diferença real confirmada contra a fonte** (não presumida — ver
PENDENCIAS.md > blueprint itens 7/8): ao contrário de Contingência NFCe
(onde só um tipo é selecionável pra abrir — `tipo_contingencia=9` fixo),
aqui os DOIS tipos são igualmente selecionáveis ao abrir uma contingência
nova (`Option1`/`Option2`, ambos visíveis e obrigatórios — `FrmConNFe.
frm:276-279`): **FS-IA (2)** "Formulário de Segurança - Impressor
Autônomo" ou **FS-DA (5)** "Formulário de Segurança - Documento
Auxiliar" (`FrmConNFe.frm:301`, `IIf(Option1.Value, 2, 5)`). Motivo:
15-256 chars, mesma regra de NFCe.

Schema confirmado direto no banco real (`INFORMATION_SCHEMA`/
`sys.indexes`, GERDELL/BARESTELA, 2026-08-20 — a tabela JÁ EXISTE no
legado, não foi presumida): `contingencia_nfe(Data_Inicio, Hora_Inicio,
Data_Fim, Hora_Fim, Motivo, tipo_contingencia)`, **chave primária
composta `(Data_Inicio, Hora_Inicio)`, sem coluna `id`** — mesmo achado
que corrigiu um bug real em `contingencia_nfce_service.py` no mesmo dia
(a 1ª versão daquele service assumia um `id` que não existe na tabela
real; corrigido lá e replicado certo aqui desde o início).

**Divergência deliberada do SQL literal do legado**: `Command1_Click`
(`FrmConNFe.frm:294`) usa `WHERE DATA_FIM=NULL` (tecnicamente incorreto,
só funciona por `ANSI_NULLS OFF` legado) — a regra em si (só uma
contingência aberta por vez) é real, portado com `IS NULL` correto.

**Conectado à emissão real 2026-08-20** — `nfe_agrupada_service.py`/
`nfe_avulsa_service.py` agora consultam `contingencia_aberta_sync` antes
de emitir e passam `contingencia=` pro `emitir_nfe_sync` (mesmo padrão já
usado por `comanda_service._emitir_nfce_comanda_sync` pra NFC-e desde
2026-08-19). `listar_pendentes`/`validar_pendentes` abaixo (novos, mesmo
dia) são o equivalente de "Validar Contingência" do Gestor NFCe — aqui
sem tela de listagem própria (não existe "Gestor NFe"), então viraram
ações desta MESMA tela Contingência NFe: mostra as NF-e com `n_fiscal.
situacao='G'` (aguardando) e permite validar (reassinar + transmitir de
verdade) uma a uma ou em lote.

**NUNCA testado ao vivo contra SEFAZ real** — mesma ressalva de todo o
resto do pacote fiscal desta migração."""
import asyncio
import re
from datetime import datetime
from typing import Optional

from db.connection import _open_conn
from services import apoio_fiscal_service, nfe_emissao_service, nfe_fiscal_common
from services.permissoes_service import tem_permissao

_TIPOS_VALIDOS = (2, 5)  # FS-IA, FS-DA


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "CONT_NFE", comando)


_DDL_CONT_NFE = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'contingencia_nfe')
BEGIN
    CREATE TABLE contingencia_nfe (
        data_inicio DATE NOT NULL,
        hora_inicio VARCHAR(8) NOT NULL,
        data_fim DATE NULL,
        hora_fim VARCHAR(8) NULL,
        motivo NVARCHAR(500) NULL,
        tipo_contingencia SMALLINT NULL,
        CONSTRAINT PK_contingencia_nfe PRIMARY KEY (data_inicio, hora_inicio)
    );
    CREATE INDEX IX_contingencia_nfe_aberta ON contingencia_nfe (data_fim);
END
"""


def _ensure_contingencia_nfe_table(cur) -> None:
    cur.execute(_DDL_CONT_NFE)


def contingencia_aberta_sync(cur) -> Optional[dict]:
    """Devolve a linha de contingência NFe aberta (sem `data_fim`) ou
    `None` — mesmo padrão de `contingencia_nfce_service.contingencia_
    aberta_sync`. Chamado com o cursor já aberto de dentro da mesma
    transação de quem precisa saber (futura emissão NFe em contingência —
    ver docstring do módulo)."""
    _ensure_contingencia_nfe_table(cur)
    cur.execute(
        "SELECT TOP 1 data_inicio, hora_inicio, motivo, tipo_contingencia "
        "FROM contingencia_nfe WHERE data_fim IS NULL ORDER BY data_inicio DESC, hora_inicio DESC"
    )
    return cur.fetchone()


def _abrir_contingencia_sync(
    servidor: str, banco: str, *, motivo: str, tipo_contingencia: int,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Abre uma contingência nova — réplica de `FrmConNFe.frm::
    Command1_Click` (ramo de abertura, linhas 291-302): valida motivo
    (15-256 chars), tipo obrigatório (2=FS-IA ou 5=FS-DA — os DOIS são
    selecionáveis aqui, diferente de NFCe), bloqueia dupla abertura."""
    if tipo_contingencia not in _TIPOS_VALIDOS:
        return {"success": False, "message": "Defina o tipo de contingência (FS-IA ou FS-DA)."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para abrir contingência."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}
        motivo = (motivo or "").strip()
        if len(motivo) < 15 or len(motivo) > 256:
            conn.close()
            return {"success": False, "message": "O motivo deve ter entre 15 e 256 caracteres."}
        if contingencia_aberta_sync(cur):
            conn.close()
            return {"success": False, "message": "Já existe uma contingência aberta — feche-a antes de abrir outra."}
        agora = datetime.now()
        cur.execute(
            "INSERT INTO contingencia_nfe (data_inicio, hora_inicio, motivo, tipo_contingencia) "
            "VALUES (%s, %s, %s, %s)",
            (agora.date(), agora.strftime("%H:%M:%S"), motivo, tipo_contingencia),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Contingência aberta. Novas NF-e serão emitidas em contingência até o fechamento."}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _fechar_contingencia_sync(
    servidor: str, banco: str, *, classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Fecha a contingência aberta — grava `data_fim`/`hora_fim` na linha
    aberta (identificada por `data_fim IS NULL`, sem precisar de `id` —
    a regra "só uma aberta por vez" já garante que é única)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar contingência."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}
        if not contingencia_aberta_sync(cur):
            conn.close()
            return {"success": False, "message": "Não há contingência aberta pra fechar."}
        agora = datetime.now()
        cur.execute(
            "UPDATE contingencia_nfe SET data_fim = %s, hora_fim = %s WHERE data_fim IS NULL",
            (agora.date(), agora.strftime("%H:%M:%S")),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Contingência fechada."}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _status_contingencia_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        aberta = contingencia_aberta_sync(cur)
        cur.close()
        conn.close()
        if not aberta:
            return {"success": True, "aberta": False}
        return {
            "success": True, "aberta": True,
            "data_inicio": str(aberta.get("data_inicio")), "hora_inicio": aberta.get("hora_inicio"),
            "motivo": aberta.get("motivo"), "tipo_contingencia": aberta.get("tipo_contingencia"),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def abrir_contingencia(
    servidor: str, banco: str, motivo: str, tipo_contingencia: int,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _abrir_contingencia_sync, servidor, banco, motivo=motivo, tipo_contingencia=tipo_contingencia,
        classe=classe, master=master,
    )


async def fechar_contingencia(servidor: str, banco: str, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_fechar_contingencia_sync, servidor, banco, classe=classe, master=master)


async def status_contingencia(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_status_contingencia_sync, servidor, banco)


# ---------------------------------------------------------------------------
# Listar pendentes / Validar Contingência — equivalente de "Validar
# Contingência" do Gestor NFCe (`gestor_nfce_service._validar_
# contingencia_sync`), adaptado pra NF-e: sem uma tela "Gestor NFe" onde
# embutir a ação, as duas funções abaixo alimentam a própria tela
# Contingência NFe. Mesmo achado 2026-08-19 (Gestor NFCe) reaproveitado
# aqui: "Validar Contingência" NÃO é uma operação SEFAZ especial — é a
# autorização normal (`NFeAutorizacao4`) atrasada, reassinando o MESMO
# XML já gravado (tpEmis 2/5 preservado, nada recalculado).
# ---------------------------------------------------------------------------

def _listar_pendentes_sync(servidor: str, banco: str) -> dict:
    """NF-e emitidas em contingência, ainda aguardando transmissão real
    (`n_fiscal.situacao='G'`)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, num_nf, serie_nf, chave_acesso, valor_total, data_nf "
            "FROM n_fiscal WHERE situacao = 'G' ORDER BY data_nf DESC, num_nf DESC"
        )
        pendentes = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "pendentes": pendentes}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _validar_pendentes_sync(
    servidor: str, banco: str, *, notas: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Reassina o XML já gravado em `n_fiscal.xml` e transmite pelo mesmo
    envelope `NFeAutorizacao4` da emissão normal — réplica do mecanismo já
    confirmado pra NFC-e. Ao suceder: `n_fiscal.situacao='A'` + `comanda_
    nf.situacao='A'` (a segunda só afeta linhas que existirem — nota vinda
    de NF-e Avulsa nunca tem `comanda_nf`, UPDATE vira no-op nesse caso,
    não precisa de branch separado)."""
    if not notas:
        return {"success": False, "message": "Selecione ao menos uma nota."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para validar contingência."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}

        cert = nfe_fiscal_common.carregar_certificado_sync(cur)
        if not cert:
            conn.close()
            return {"success": False, "message": "Nenhum certificado digital válido cadastrado."}
        key_pem, cert_pem = cert

        cur.execute("SELECT uf FROM controle")
        controle = cur.fetchone() or {}
        cod_ibge = nfe_fiscal_common.IBGE_POR_UF.get((controle.get("uf") or "").strip().upper())
        if not cod_ibge:
            conn.close()
            return {"success": False, "message": f"UF '{controle.get('uf')}' não reconhecida."}
        tp_amb = nfe_fiscal_common.resolver_tp_amb_sync(cur)
        url = nfe_emissao_service._resolver_url_autorizacao(cod_ibge, "55", tp_amb)
        if not url:
            conn.close()
            return {"success": False, "message": "Endpoint SEFAZ não disponível pra essa UF."}

        resultados = []
        for codigo in notas:
            cur.execute(
                "SELECT codigo, situacao, chave_acesso, xml FROM n_fiscal WHERE codigo = %s", (codigo,),
            )
            linha = cur.fetchone()
            if not linha or (linha.get("situacao") or "").strip().upper() != "G":
                resultados.append({"codigo": codigo, "success": False, "message": "Nota não está aguardando contingência."})
                continue
            xml_guardado = linha.get("xml")
            if not xml_guardado:
                resultados.append({"codigo": codigo, "success": False, "message": "XML da NF-e não encontrado."})
                continue
            try:
                # Achado real (teste ao vivo, 2026-08-26, NFC-e — corrigido
                # aqui por analogia/consistência, mesmo padrão do dia
                # anterior): `xml_guardado` é o documento JÁ ASSINADO
                # (assinatura da emissão original em contingência, nunca
                # removida). Reassinar isso do jeito que está deixaria a
                # assinatura antiga presente junto da nova — mesma classe
                # de bug confirmada com rejeição real do SEFAZ pro lado
                # NFC-e ("Falha no Schema XML"). NF-e não tem `infNFeSupl`
                # (isso é exclusivo de NFC-e/QR Code), só remove a
                # assinatura antiga antes de reassinar.
                xml_texto = xml_guardado if isinstance(xml_guardado, str) else xml_guardado.decode("utf-8")
                xml_texto = re.sub(r"<(?:ds:)?Signature[ >].*?</(?:ds:)?Signature>", "", xml_texto, flags=re.DOTALL)
                xml_bytes = xml_texto.encode("utf-8")
                id_nfe = f"NFe{linha.get('chave_acesso')}"
                # sha1=True — mesmo achado do MDF-e/NFC-e (2026-08-23), ver
                # `nfe_cancelamento_service._assinar_evento`.
                xml_assinado = nfe_fiscal_common.assinar_xml(xml_bytes, id_nfe, key_pem, cert_pem, sha1=True)
                envelope = nfe_emissao_service._montar_envelope_autorizacao(xml_assinado, tp_amb)
                resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem)
            except Exception as e:
                resultados.append({"codigo": codigo, "success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"})
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
            # 100 = "Autorizado o uso da NF-e" (sucesso).
            if c_stat != "100":
                x_motivo = nfe_fiscal_common.extrair_tag(inf_prot, "xMotivo")
                resultados.append({
                    "codigo": codigo, "success": False,
                    "message": f"SEFAZ recusou a autorização (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
                    "cstat": c_stat,
                })
                continue
            # `dh_recbto` cru do SEFAZ (ISO 8601 com offset) quebra numa
            # coluna DATETIME e derruba a transação DEPOIS do sucesso já
            # confirmado — mesmo bug achado ao vivo no MDF-e 2026-08-23,
            # corrigido aqui 2026-08-24 (ver `nfe_fiscal_common.parse_dh_sefaz`).
            cur.execute(
                "UPDATE n_fiscal SET situacao = 'A', cstat = %s, protocolo_sefaz = %s, dhRecbto = %s, xml = %s "
                "WHERE codigo = %s",
                (c_stat, n_prot, nfe_fiscal_common.parse_dh_sefaz(dh_recbto), xml_assinado.decode("utf-8"), codigo),
            )
            cur.execute("UPDATE comanda_nf SET situacao = 'A' WHERE nota_fisc = %s AND situacao = 'G'", (codigo,))
            resultados.append({"codigo": codigo, "success": True, "protocolo_sefaz": n_prot})
        conn.commit()
        cur.close()
        conn.close()
        falhas = [r for r in resultados if not r.get("success")]
        resposta = {"success": not falhas, "resultados": resultados}
        # Apoio Fiscal BackOn — resumo agregado (2026-08-28, decisão via
        # AskUserQuestion), mesmo padrão do Gestor NFCe: 1 notificação só
        # pro lote inteiro, só cobrindo rejeições REAIS do SEFAZ (têm
        # `cstat`) — "Nota não está aguardando contingência"/"XML não
        # encontrado" são falhas de pré-validação local, não fiscais.
        falhas_sefaz = [f for f in falhas if f.get("cstat")]
        if falhas_sefaz:
            resposta["apoio_fiscal_lote"] = apoio_fiscal_service.notificar_rejeicoes_lote_sync(
                servidor, banco, tipo_documento="Validar Pendentes de Contingência NF-e (lote)",
                itens_falhos=[
                    {"referencia": f.get("codigo"), "codigo_rejeicao": f.get("cstat"), "mensagem_original": f.get("message") or ""}
                    for f in falhas_sefaz
                ],
            )
        return resposta
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def listar_pendentes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_listar_pendentes_sync, servidor, banco)


async def validar_pendentes(
    servidor: str, banco: str, *, notas: list[int], classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(_validar_pendentes_sync, servidor, banco, notas=notas, classe=classe, master=master)

"""Inutilização de Faixa de NFe (modelo 55) — migração de
`Geral\\FrmTraINF.frm` (513 linhas, lido por completo — ver CLAUDE.md §12),
lado NFe. O lado NFC-e já foi implementado como ação embutida em "Gestor
NFCe" (`gestor_nfce_service._inutilizar_faixa_sync`, 2026-08-19) — apesar
de a fonte VB6 tratar os dois modelos numa MESMA tela (rádio "Tipo"
NFe/NFCe), esta migração mantém os dois lados em telas separadas, mesmo
precedente já adotado pra Contingência NFe/NFCe (duas telas dedicadas, não
uma única compartilhada) — ver PENDENCIAS.md > "Inutilização de Faixa NFe"
pro racional completo.

**Diferença real confirmada na releitura completa da fonte**: ao contrário
do lado NFC-e (que consulta o SEFAZ número a número antes de bloquear, via
`comanda_nfce.chave_acesso` + `NfeConsultaProtocolo4`), o lado NFe faz uma
checagem 100% LOCAL — `SELECT num_nf FROM n_fiscal WHERE situacao_nfe IN
(1,2,3,5) AND serie_nf=? AND num_nf BETWEEN ? AND ?` (réplica exata de
`FrmTraINF.frm:302-318`) — nenhuma chamada ao SEFAZ antes de bloquear.
Replicado fielmente aqui, não é uma simplificação inventada.

Também confirmado na fonte: o bloqueio "não pode inutilizar além do último
número emitido" (`FrmTraINF.frm:274-277`) lê a série de duas tabelas
diferentes conforme o tipo — pro NFe (`Option1_Click`), de `controle`
(série "principal") + `controle_nota_fiscal` (séries adicionais,
multi-série) — nunca de `controle_aux` (essa é exclusiva do lado NFC-e,
`Option2_Click`).

O `INSERT INTO inutilizacao_nfe` grava com `modelo='55'`, na MESMA tabela
compartilhada com o lado NFC-e (`modelo='65'`) — schema real confirmado
ao vivo (`INFORMATION_SCHEMA`/`sys.indexes`, GERDELL/BARESTELA) ao construir
esta tela; achou e corrigiu um bug real de schema já existente em
`gestor_nfce_service.py` (DDL antiga assumia `id INT IDENTITY` que não
existe — PK real é `codauto_inutilizacao` — ver o comentário no topo da
DDL lá pro detalhe completo).

**Fora de escopo desta rodada** (decisão explícita, documentada em
PENDENCIAS.md): "Gerar XML" do `.frm` (Command4_Click) escreve arquivos
`.xml` no disco LOCAL da máquina Windows rodando o VB6 — não portável pra
um backend web multiempresa. Reaproveita o mesmo padrão já usado em
"Gestor NFCe" (Ver XML = visualização em modal, não download de arquivo).

**NUNCA testado contra o SEFAZ real** — mesma ressalva de todo o pacote
fiscal desta migração (CLAUDE.md §12).
"""
import asyncio
from datetime import datetime
from typing import Optional

from db.connection import _open_conn
from services import apoio_fiscal_service, nfe_fiscal_common
from services.gestor_nfce_service import _ensure_inutilizacao_nfe_table
from services.permissoes_service import tem_permissao


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "INUTIL_NFE", comando)


# ---------------------------------------------------------------------------
# Séries disponíveis + histórico (leitura, alimentam a tela)
# ---------------------------------------------------------------------------

def _series_disponiveis_sync(servidor: str, banco: str) -> dict:
    """Réplica de `Option1_Click` (`FrmTraINF.frm:462-489`): série "principal"
    (`controle.serie_nf`/`numero_nf`) + séries adicionais (`controle_nota_
    fiscal`, multi-série) — devolve, por série, o último número já emitido
    (usado pro bloqueio "Número Final > último emitido" na tela)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT serie_nf, numero_nf FROM controle")
        principal = cur.fetchone()
        series: list[dict] = []
        if principal and str(principal.get("serie_nf") or "").strip():
            series.append({
                "serie": str(principal["serie_nf"]).strip(),
                "ultimo_numero": principal.get("numero_nf") or 0,
            })
        cur.execute("SELECT serie_nf, numero_nf FROM controle_nota_fiscal")
        for row in cur.fetchall():
            serie_txt = str(row.get("serie_nf") or "").strip()
            if serie_txt:
                series.append({"serie": serie_txt, "ultimo_numero": row.get("numero_nf") or 0})
        cur.close()
        conn.close()
        if not series:
            return {"success": False, "message": "Série de NF-e não cadastrada — configure em Controle do Sistema."}
        return {"success": True, "series": series}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _historico_sync(servidor: str, banco: str) -> dict:
    """Réplica de `PrepLV` (`FrmTraINF.frm:420-460`), filtrado só pra
    `modelo='55'` — o histórico de NFC-e já é mostrado dentro de Gestor
    NFCe."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_inutilizacao_nfe_table(cur)
        cur.execute(
            "SELECT codauto_inutilizacao, numero_inicial, numero_final, serie, motivo, protocolo_sefaz, "
            "data_registro, usuario FROM inutilizacao_nfe WHERE modelo = '55' ORDER BY codauto_inutilizacao DESC"
        )
        linhas = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "historico": linhas}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Inutilizar faixa
# ---------------------------------------------------------------------------

def _inutilizar_faixa_nfe_sync(
    servidor: str, banco: str, *, serie: str, numero_inicial: int, numero_final: int, motivo: str,
    usuario: Optional[int] = None, classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Réplica de `Command1_Click` (`FrmTraINF.frm:245-349`), ramo NFe
    (`Else` do form — `Option2.Value` falso)."""
    motivo = (motivo or "").strip()
    if len(motivo) < 15:
        return {"success": False, "message": "O motivo da inutilização deve ter pelo menos 15 caracteres."}
    if len(motivo) > 50:
        return {"success": False, "message": "O motivo da inutilização pode ter no máximo 50 caracteres."}
    if numero_final < numero_inicial:
        return {"success": False, "message": "Número Final não pode ser menor que o Número Inicial."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para inutilizar numeração de NF-e."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}
        _ensure_inutilizacao_nfe_table(cur)

        cur.execute("SELECT serie_nf, numero_nf FROM controle")
        principal = cur.fetchone() or {}
        cur.execute("SELECT numero_nf FROM controle_nota_fiscal WHERE serie_nf = %s", (serie,))
        adicional = cur.fetchone()
        if adicional:
            ultimo_numero = adicional.get("numero_nf")
        elif str(principal.get("serie_nf") or "").strip() == str(serie).strip():
            ultimo_numero = principal.get("numero_nf")
        else:
            ultimo_numero = None
        if ultimo_numero is None:
            conn.close()
            return {"success": False, "message": "Série informada não está cadastrada."}
        if numero_final > ultimo_numero:
            conn.close()
            return {
                "success": False,
                "message": (
                    f"Inutilização permitida somente até o número {int(ultimo_numero)}, "
                    "pois este é o número da última Nota Fiscal emitida!"
                ),
            }

        cur.execute(
            "SELECT num_nf FROM n_fiscal WHERE situacao_nfe IN (1, 2, 3, 5) AND serie_nf = %s "
            "AND num_nf >= %s AND num_nf <= %s ORDER BY num_nf",
            (serie, numero_inicial, numero_final),
        )
        ja_emitidas = [str(int(r["num_nf"])) for r in cur.fetchall()]
        if ja_emitidas:
            conn.close()
            return {
                "success": False,
                "message": f"Essa faixa não pode ser inutilizada pois possui notas emitidas: {', '.join(ja_emitidas)}.",
            }

        cur.execute("SELECT cgc, uf FROM controle")
        controle = cur.fetchone() or {}
        cod_ibge = nfe_fiscal_common.IBGE_POR_UF.get((controle.get("uf") or "").strip().upper())
        if not cod_ibge:
            conn.close()
            return {"success": False, "message": f"UF '{controle.get('uf')}' não reconhecida."}
        tp_amb = nfe_fiscal_common.resolver_tp_amb_sync(cur)
        url = nfe_fiscal_common.resolver_endpoint(cod_ibge, "55", tp_amb, nfe_fiscal_common.ENDPOINTS_INUTILIZACAO)
        if not url:
            conn.close()
            return {"success": False, "message": "Inutilização não disponível pra essa UF."}
        cert = nfe_fiscal_common.carregar_certificado_sync(cur)
        if not cert:
            conn.close()
            return {"success": False, "message": "Nenhum certificado digital válido cadastrado."}
        key_pem, cert_pem = cert

        try:
            xml_inut, id_inut = nfe_fiscal_common.montar_xml_inutilizacao(
                modelo="55", cod_ibge=cod_ibge, cnpj=(controle.get("cgc") or ""), serie=serie,
                numero_inicial=numero_inicial, numero_final=numero_final, motivo=motivo, tp_amb=tp_amb,
            )
            # sha1=True — mesmo achado do MDF-e/NFC-e (2026-08-23), ver
            # `nfe_cancelamento_service._assinar_evento`.
            xml_assinado = nfe_fiscal_common.assinar_xml(xml_inut, id_inut, key_pem, cert_pem, sha1=True)
            # "NFeInutilizacao4" (F/e maiúsculos) + `soap_action` — mesmo
            # achado ao vivo 2026-08-24 confirmado pro lado NFCe
            # (`gestor_nfce_service.py`, WSDL público real baixado com o
            # certificado). **Corrigido preventivamente por semelhança,
            # nunca testado ao vivo pro lado NFe (modelo 55) nesta
            # sessão** — validar contra uma tentativa real antes de
            # confiar 100%.
            envelope = nfe_fiscal_common.montar_envelope_soap(xml_assinado, "NFeInutilizacao4")
            soap_action = f"{nfe_fiscal_common.NFE_NS}/wsdl/NFeInutilizacao4/nfeInutilizacaoNF"
            resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem, soap_action=soap_action)
        except Exception as e:
            conn.close()
            return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

        c_stat = nfe_fiscal_common.extrair_tag(resposta, "cStat")
        # 102 = "Inutilização de número homologada".
        if c_stat != "102":
            x_motivo = nfe_fiscal_common.extrair_tag(resposta, "xMotivo")
            conn.close()
            resultado_rejeicao = {
                "success": False,
                "message": f"SEFAZ recusou a inutilização (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
            }
            resultado_rejeicao["apoio_fiscal"] = apoio_fiscal_service.notificar_rejeicao_sync(
                servidor, banco, tipo_documento="Inutilização NF-e", codigo_rejeicao=c_stat or "?",
                mensagem_original=x_motivo or "", referencia=f"{serie}/{numero_inicial}-{numero_final}",
            )
            return resultado_rejeicao
        n_prot = nfe_fiscal_common.extrair_tag(resposta, "nProt")
        usuario_texto = nfe_fiscal_common.resolver_usuario_texto_sync(cur, usuario)
        data_registro = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
        cur.execute(
            "INSERT INTO inutilizacao_nfe (numero_inicial, numero_final, serie, modelo, motivo, "
            "protocolo_sefaz, xml, data_registro, usuario) VALUES (%s, %s, %s, '55', %s, %s, %s, %s, %s)",
            (numero_inicial, numero_final, serie, motivo, n_prot, xml_assinado.decode("utf-8"), data_registro, usuario_texto),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "protocolo_sefaz": n_prot}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def series_disponiveis(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_series_disponiveis_sync, servidor, banco)


async def historico(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_historico_sync, servidor, banco)


async def inutilizar_faixa(
    servidor: str, banco: str, *, serie: str, numero_inicial: int, numero_final: int, motivo: str,
    usuario: Optional[int] = None, classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _inutilizar_faixa_nfe_sync, servidor, banco, serie=serie, numero_inicial=numero_inicial,
        numero_final=numero_final, motivo=motivo, usuario=usuario, classe=classe, master=master,
    )

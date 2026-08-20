"""Agrupar Comandas em NF-e (modelo 55) — migração de `Geral\\FrmSelComandas.frm`
(seleção de comandas) + o caminho de agrupamento de `NFe\\FrmTraImpNFE.frm`
(`Geral\\ModNF.bas::grava()`), lidos por completo 2026-08-19 — ver
PENDENCIAS.md > "Agrupar Comandas em NF-e" e > "Agrupamento de Comandas —
rastreio completo de FrmTraImpNFE.frm" pro racional completo. Protocolo
Gauntlet acionado (Leandro+Carlos+Thomé).

**Achados-chave da fonte, replicados aqui**:
- Não existe "modo comanda única" — é sempre uma lista (aqui, a lista de
  comandas vem direto no payload do POST, sem tabela de rascunho
  intermediária como o legado `lista_nfe`/`lista_comandas_nfe` — decisão
  de simplificação, ver plano).
- Itens de comandas diferentes são SOMADOS automaticamente por
  `codigo_int`+`p_unit` — exceto item com `pecas.controla_num_serie=1`
  (nunca soma, mesma regra já usada em Números de Série).
- Vínculo de rastreio = `comanda_nf(comanda, nota_fisc, tipo=3,
  situacao)` — 1 linha por comanda do grupo, todas apontando pro mesmo
  `nota_fisc` (tipo 1=NFCe, 2=NFSe já em uso por `comanda_service.py`).

**4 decisões de negócio confirmadas com o usuário (2026-08-19)**:
1. Data de emissão = sempre hoje (`GETDATE()`), nunca a data original de
   cada venda.
2. Rastreabilidade item↔comanda = só em nível de comanda (via
   `comanda_nf`), sem granularidade de quantidade — decisão explícita do
   usuário, replicando a mesma perda de rastreabilidade do legado.
3. IBS/CBS = calculado sempre neste caminho (mesmo o legado tendo esse
   gap confirmado só no ramo `Metodo=1`/comanda única).
4. NFS-e agrupada = fora de escopo (código morto no legado, sem
   comportamento de referência).

**Correção de ordem 2026-08-20, user-directed**: pro caminho agrupado
(diferente do caminho de comanda única em `comanda_service.py`, que
calcula IBS/CBS ANTES de emitir), o cálculo de IBS/CBS só acontece
**depois** que o registro em `n_fiscal` já existe. Na prática: a NF-e é
assinada/transmitida ao SEFAZ (se aplicável) e gravada em `n_fiscal`
**sem** IBS/CBS embutido no XML; em seguida, com `codigo_n_fiscal` já
disponível, o IBS/CBS é calculado por item e a coluna `xml` de
`n_fiscal` é **reescrita** (recalculada, com os fragmentos IBS/CBS
embutidos) — sem reassinar nem retransmitir ao SEFAZ, é só um registro
mais completo pro nosso banco. Ver `_emitir_nfe_agrupada_sync`.

**Regra nova desta migração, sem precedente direto no legado**: uma
comanda já vinculada a QUALQUER nota fiscal (`comanda_nf`) não pode
entrar em outro agrupamento — o legado não impedia isso explicitamente
(só avisava sobre NFC-e já emitida), mas permitir geraria duplicidade
fiscal real sem nenhum aviso. Ver `_list_comandas_agrupaveis_sync`/
`_emitir_nfe_agrupada_sync`.

**NUNCA testado contra o SEFAZ real** — mesma ressalva de todo o resto
do pacote fiscal desta migração."""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from db.connection import _open_conn
from services import ibs_cbs_service, nfe_emissao_service, nfe_fiscal_common
from services.permissoes_service import tem_permissao


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "NFE_AGRUPADA", comando)


# ---------------------------------------------------------------------------
# Listagem — comandas faturadas (`situacao='PG'`) de um cliente, elegíveis
# pra entrar num agrupamento.
# ---------------------------------------------------------------------------

def _list_comandas_agrupaveis_sync(
    servidor: str, banco: str, *, cliente: int, classe: Optional[int] = None, master: bool = False,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="ABRIR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para abrir Agrupar Comandas em NF-e."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}
        cur.execute(
            "SELECT c.comanda, c.data, c.valor_venda, "
            "EXISTS(SELECT 1 FROM comanda_nfce cn WHERE cn.comanda = c.comanda AND cn.situacao <> 'C') AS tem_nfce, "
            "EXISTS(SELECT 1 FROM comanda_nf cnf WHERE cnf.comanda = c.comanda) AS ja_agrupada, "
            "EXISTS(SELECT 1 FROM movimentacao m JOIN pecas p ON p.codigo_int = m.codigo_int "
            "WHERE m.serie_nf = 'CM' AND m.num_nf = c.comanda AND ISNULL(m.Estornado, 0) = 0) AS tem_item_produto "
            "FROM comanda c WHERE c.cliente = %s AND c.situacao = 'PG' ORDER BY c.data DESC, c.comanda DESC",
            (cliente,),
        )
        itens = [{
            "comanda": r["comanda"], "data": str(r.get("data")) if r.get("data") else None,
            "valor_venda": float(r.get("valor_venda") or 0), "tem_nfce": bool(r.get("tem_nfce")),
            "ja_agrupada": bool(r.get("ja_agrupada")), "tem_item_produto": bool(r.get("tem_item_produto")),
        } for r in cur.fetchall()]
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
# Destinatário — validação obrigatória (bloqueante), diferença real vs.
# NFC-e confirmada na fonte (`TestaEnderecoNFE`, `frmtranfe.frm`).
# ---------------------------------------------------------------------------

# Movido pra `nfe_fiscal_common.py` em 2026-08-20 (NF-e Avulsa também
# precisou de um resolvedor de destinatário, agora pro lado fornecedor) —
# alias mantido aqui pra não quebrar quem já faz `monkeypatch.setattr(svc,
# "_resolver_destinatario_sync", ...)` nos testes existentes, e pra não
# obrigar os call sites internos deste módulo a mudar de nome.
_resolver_destinatario_sync = nfe_fiscal_common.resolver_destinatario_cliente_sync


# ---------------------------------------------------------------------------
# Emissão agrupada
# ---------------------------------------------------------------------------

def _emitir_nfe_agrupada_sync(
    servidor: str, banco: str, *, comandas: list[int], usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    if not comandas or len(comandas) < 1:
        return {"success": False, "message": "Selecione ao menos uma comanda."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para emitir NF-e agrupada."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}

        placeholders = ",".join(["%s"] * len(comandas))
        cur.execute(
            f"SELECT comanda, cliente, situacao, valor_venda FROM comanda WHERE comanda IN ({placeholders})",
            tuple(comandas),
        )
        cabecalhos = {r["comanda"]: r for r in cur.fetchall()}
        faltantes = [c for c in comandas if c not in cabecalhos]
        if faltantes:
            conn.close()
            return {"success": False, "message": f"Comanda(s) não encontrada(s): {faltantes}."}
        nao_pagas = [c for c in comandas if (cabecalhos[c].get("situacao") or "").strip().upper() != "PG"]
        if nao_pagas:
            conn.close()
            return {"success": False, "message": f"Só é possível agrupar comandas faturadas — comanda(s) {nao_pagas} não está(ão) faturada(s)."}
        clientes_distintos = {cabecalhos[c].get("cliente") for c in comandas}
        if len(clientes_distintos) > 1:
            conn.close()
            return {"success": False, "message": "Todas as comandas selecionadas precisam ser do MESMO cliente."}
        cliente_codigo = next(iter(clientes_distintos))
        if not cliente_codigo:
            conn.close()
            return {"success": False, "message": "Comanda sem cliente vinculado — não é possível emitir NF-e."}

        cur.execute(f"SELECT comanda FROM comanda_nf WHERE comanda IN ({placeholders})", tuple(comandas))
        ja_agrupadas = [r["comanda"] for r in cur.fetchall()]
        if ja_agrupadas:
            conn.close()
            return {"success": False, "message": f"Comanda(s) {ja_agrupadas} já está(ão) vinculada(s) a uma nota fiscal — não é possível agrupar de novo."}

        dest_resultado = _resolver_destinatario_sync(cur, cliente_codigo)
        if not dest_resultado.get("success"):
            conn.close()
            return dest_resultado
        destinatario = dest_resultado["destinatario"]
        consumidor_final = dest_resultado["consumidor_final"]
        simples_nacional_cliente = dest_resultado["simples_nacional_cliente"]

        cur.execute(
            "SELECT m.codigo_int, p.descricao, m.qtd, m.p_unit, p.cod_icms, p.origem, "
            "p.codigo_mercosul AS ncm, p.uni AS unidade, p.controla_num_serie "
            f"FROM movimentacao m JOIN pecas p ON p.codigo_int = m.codigo_int "
            f"WHERE m.serie_nf = 'CM' AND m.num_nf IN ({placeholders}) AND ISNULL(m.Estornado, 0) = 0",
            tuple(comandas),
        )
        itens_mov = cur.fetchall()
        if not itens_mov:
            conn.close()
            return {"success": False, "message": "Nenhuma das comandas selecionadas tem item de produto — nada a emitir."}

        # Consolida por (codigo_int, p_unit) — mesma regra confirmada na
        # fonte (`FrmTraImpNFE.frm::TestaComanda`): item com controle de
        # número de série NUNCA soma (rastreabilidade individual real) —
        # cada linha desses vira sua própria entrada, nunca casando com
        # outra (índice sequencial garante isso sem precisar de id() de
        # objeto Python, que seria um detalhe de implementação vazando
        # pra lógica de negócio).
        consolidados: dict[tuple, dict] = {}
        for idx, item in enumerate(itens_mov):
            codigo_int = (item.get("codigo_int") or "").strip()
            p_unit = round(float(item.get("p_unit") or 0), 10)
            controla_serie = bool(item.get("controla_num_serie"))
            chave = (codigo_int, p_unit, idx) if controla_serie else (codigo_int, p_unit)
            if chave in consolidados:
                consolidados[chave]["qtd"] += float(item.get("qtd") or 0)
            else:
                consolidados[chave] = {**item, "qtd": float(item.get("qtd") or 0)}

        cur.execute("SELECT cgc, uf, rz_social, numero_nf, serie_nf FROM controle")
        controle = cur.fetchone() or {}
        uf_sigla = (controle.get("uf") or "").strip().upper()

        cur.execute("SELECT TOP 1 1 AS ok FROM tipo_mov WHERE codigo = 'S01'")
        tipo_mov_existe = cur.fetchone() is not None
        natureza_operacao = "Venda"
        if tipo_mov_existe:
            cur.execute("SELECT descricao FROM tipo_mov WHERE codigo = 'S01'")
            tm = cur.fetchone()
            natureza_operacao = (tm.get("descricao") or "Venda").strip() if tm else "Venda"

        # IBS/CBS NÃO é calculado aqui — decisão de negócio 2026-08-20,
        # ver docstring do módulo ("Correção de ordem"). Só a tributação
        # atual (ICMS/PIS/COFINS/CFOP) é resolvida nesta etapa, igual ao
        # caminho de comanda única.
        itens_resolvidos = []
        valor_total = 0.0
        for item in consolidados.values():
            codigo_int = (item.get("codigo_int") or "").strip()
            cod_icms = (item.get("cod_icms") or "").strip()
            cur.execute("SELECT TOP 1 1 AS ok FROM PECAS_PROTOCOLO_ST WHERE uf = %s AND codigo_int = %s", (uf_sigla, codigo_int))
            protocolo_st = cur.fetchone() is not None
            tributos = nfe_emissao_service._resolver_tributacao_sync(
                cur, cod_icms=cod_icms, cfop_cupom_fiscal="", tipo_mov="S01",
                uf_destino=uf_sigla, uf_controle=uf_sigla, nao_contribuinte=not destinatario.get("ie"),
                simples_nacional_cliente=simples_nacional_cliente, consumidor_final=consumidor_final, protocolo_st=protocolo_st,
            )
            if not tributos:
                conn.close()
                return {"success": False, "message": f"Produto '{codigo_int}' sem tributação cadastrada em Taxas (Tabelas Auxiliares)."}
            qtd = float(item.get("qtd") or 0)
            valor_unitario = float(item.get("p_unit") or 0)
            valor_item = round(qtd * valor_unitario, 2)
            valor_total += valor_item
            itens_resolvidos.append({
                "codigo_int": codigo_int, "descricao": (item.get("descricao") or "").strip(),
                "ncm": (item.get("ncm") or "").strip(), "cfop": tributos.get("cfop_livro") or "5102",
                "unidade": (item.get("unidade") or "UN").strip(), "qtd": qtd, "valor_unitario": valor_unitario,
                "valor_total": valor_item, "origem": int(item.get("origem") or 0),
                "csosn": "102" if simples_nacional_cliente else "400", "cst_pis": "07", "cst_cofins": "07",
                "cod_icms": cod_icms, "ibs_cbs_xml": "",
            })

        proximo_numero = int(controle.get("numero_nf") or 0) + 1
        serie = str(controle.get("serie_nf") or "1")

        resultado = nfe_emissao_service.emitir_nfe_sync(
            cur, cnpj_emit=(controle.get("cgc") or ""), nome_emit=(controle.get("rz_social") or ""),
            uf_sigla=uf_sigla, proximo_numero=proximo_numero, serie=serie, destinatario=destinatario,
            itens_resolvidos=itens_resolvidos, valor_total=round(valor_total, 2), tp_amb="1",
            natureza_operacao=natureza_operacao, indFinal="1" if consumidor_final else "0",
        )
        if not resultado.get("success"):
            conn.close()
            return resultado

        situacao_n_fiscal = resultado.get("situacao") or "A"
        cstat_n_fiscal = resultado.get("cstat") or "100"
        cur.execute(
            "INSERT INTO n_fiscal (num_nf, serie_nf, fornecedor, uf, data_nf, data_mov, valor_total, situacao, "
            "chave_acesso, protocolo_sefaz, dhRecbto, cstat, xml) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s, %s, %s, %s, CONVERT(date, GETDATE()), CONVERT(date, GETDATE()), %s, %s, %s, %s, %s, %s, %s)",
            (resultado["numero"], resultado["serie"], cliente_codigo, uf_sigla, round(valor_total, 2), situacao_n_fiscal,
             resultado["chave_acesso"], resultado["protocolo_sefaz"], resultado.get("dh_recbto"), cstat_n_fiscal, resultado["xml"]),
        )
        codigo_n_fiscal = int(cur.fetchone()["codigo"])
        for item in itens_resolvidos:
            cur.execute(
                "INSERT INTO n_fiscal_itens (codigo, codigo_int, qtd, p_unit, valor_total, tributacao) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (codigo_n_fiscal, item["codigo_int"], item["qtd"], item["valor_unitario"], item["valor_total"], item["cfop"]),
            )

        # IBS/CBS (Reforma Tributária) — só agora, com `codigo_n_fiscal` já
        # existente (decisão de negócio 2026-08-20, ver docstring do
        # módulo). Recalcula por item, monta os totais, e REESCREVE a
        # coluna `xml` de `n_fiscal` já com os fragmentos IBS/CBS embutidos
        # — sem reassinar/retransmitir ao SEFAZ, só enriquece o registro
        # já salvo no banco.
        cod_ibge = nfe_fiscal_common.IBGE_POR_UF.get(uf_sigla)
        if cod_ibge:
            ibs_cbs_calculados = []
            for item in itens_resolvidos:
                taxa_nfce = ibs_cbs_service.resolver_taxa_nfce_para_ibs_cbs_sync(cur, cod_icms=item.get("cod_icms") or "", destino=uf_sigla)
                ibs_cbs_item = (
                    ibs_cbs_service.calcular_item_ibs_cbs(
                        qtd=item["qtd"], p_unit=item["valor_unitario"], codigo_int=item["codigo_int"], taxa=taxa_nfce
                    )
                    if taxa_nfce else None
                )
                ibs_cbs_calculados.append(ibs_cbs_item)
                item["ibs_cbs_xml"] = (ibs_cbs_item or {}).get("xml_item") or ""
            ibs_cbs_totais = ibs_cbs_service.calcular_totais_ibs_cbs(ibs_cbs_calculados)
            xml_com_ibs_cbs, _ = nfe_emissao_service._montar_xml_nfe(
                chave_acesso=resultado["chave_acesso"], cod_ibge=cod_ibge, cnpj_emit=(controle.get("cgc") or ""),
                nome_emit=(controle.get("rz_social") or ""), uf_emit_sigla=uf_sigla, destinatario=destinatario,
                itens=itens_resolvidos, valor_total=round(valor_total, 2), tp_amb="1", numero=resultado["numero"],
                serie=resultado["serie"], data_emissao=datetime.now(timezone.utc), natureza_operacao=natureza_operacao,
                indFinal="1" if consumidor_final else "0", ibs_cbs_totais_xml=ibs_cbs_totais["xml_totais"],
            )
            cur.execute("UPDATE n_fiscal SET xml = %s WHERE codigo = %s", (xml_com_ibs_cbs.decode("utf-8"), codigo_n_fiscal))

        cur.execute(
            f"INSERT INTO comanda_nf (comanda, nota_fisc, tipo, situacao) "
            f"SELECT comanda, %s, 3, %s FROM comanda WHERE comanda IN ({placeholders})",
            (codigo_n_fiscal, situacao_n_fiscal, *comandas),
        )
        cur.execute("UPDATE controle SET numero_nf = %s", (resultado["numero"],))
        conn.commit()
        cur.close()
        conn.close()
        resultado["nota_fisc"] = codigo_n_fiscal
        resultado["comandas"] = comandas
        return resultado
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def list_comandas_agrupaveis(servidor: str, banco: str, cliente: int, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_list_comandas_agrupaveis_sync, servidor, banco, cliente=cliente, classe=classe, master=master)


async def emitir_nfe_agrupada(
    servidor: str, banco: str, comandas: list[int], usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _emitir_nfe_agrupada_sync, servidor, banco, comandas=comandas, usuario=usuario, classe=classe, master=master,
    )

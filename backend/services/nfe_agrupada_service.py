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
   comportamento de referência). **Superado 2026-08-21** — ver achado da
   reauditoria mais abaixo: o usuário pediu NFS-e agrupada como ação
   independente da NF-e nesta mesma tela, sem precedente legado a seguir
   (o que já estava sinalizado aqui — "sem comportamento de referência" —
   dando liberdade de desenho).

**Correção de ordem revertida 2026-08-20, mesmo dia, user-directed**: a
versão anterior desta seção mandava calcular IBS/CBS **depois** de
emitir (registro em `n_fiscal` já existente), reescrevendo a coluna
`xml` com uma versão enriquecida — só que **sem reassinar**, perdendo a
assinatura digital válida sobre o conteúdo salvo (achado ao investigar
esse mesmo dia). Correção pedida pelo usuário, com o princípio geral por
trás: "não existe característica especial pra NF-e agrupada" e "IBS/CBS
não é nada mais que um grupo dentro do XML da NFe/NFSe/NFCe, como
qualquer outro" — mesmo tratamento que ICMS/PIS/COFINS já recebem neste
mesmo arquivo. Agora IBS/CBS é calculado **junto** com o resto da
tributação, ANTES de chamar `emitir_nfe_sync` (mesmo momento/mesmo
padrão já usado em `comanda_service.py` pra NFC-e) — o XML que sai
assinado e vai pro SEFAZ já nasce com os fragmentos IBS/CBS embutidos;
nenhuma reescrita pós-emissão, nenhum risco de assinatura divergir do
conteúdo salvo. Ver `_emitir_nfe_agrupada_sync`.

**Regra nova desta migração, sem precedente direto no legado**: uma
comanda já vinculada a uma nota fiscal do MESMO TIPO (`comanda_nf.tipo`)
não pode entrar em outro agrupamento daquele tipo — o legado não impedia
isso explicitamente (só avisava sobre NFC-e já emitida), mas permitir
geraria duplicidade fiscal real sem nenhum aviso. **Correção 2026-08-21**:
o gate passou de "qualquer linha em `comanda_nf`" pra POR TIPO (3=NF-e
agrupada, 2=NFS-e) — uma comanda já coberta por NF-e ainda pode entrar
numa NFS-e depois (e vice-versa), já que agora são 2 ações fiscais
independentes (ver achado abaixo). Ver `_list_comandas_agrupaveis_sync`/
`_validar_selecao_agrupavel_sync`.

**NUNCA testado contra o SEFAZ real** — mesma ressalva de todo o resto
do pacote fiscal desta migração.

**Achado real da reauditoria 2026-08-21, CORRIGIDO no mesmo dia** (ver
PENDENCIAS.md > "🔴 FRENTE ATIVA" > item 4 pro detalhe completo): o
item-fetch de `_emitir_nfe_agrupada_sync` sempre fez `FROM movimentacao m
JOIN pecas p ON p.codigo_int = m.codigo_int` — INNER JOIN só contra
`pecas`, então item de Serviço numa comanda sendo agrupada era
SILENCIOSAMENTE excluído da nota (a fonte confirma que misturar
Produto+Serviço numa comanda é permitido). Perguntado o que fazer,
Leandro respondeu diretamente: não é um bug de "excluir com aviso" — a
tela precisa de DUAS ações fiscais independentes, e o usuário escolhe
"nenhuma / só produto / só serviço / produto e serviço". Implementado:
`_emitir_nfse_agrupada_sync` (nova, mirror de `_emitir_nfe_agrupada_sync`
mas com `JOIN servicos`/DPS, reaproveitando `nfse_emissao_service.
emitir_nfse_sync` já existente pra comanda única — aqui generalizado pra
lista) + `_emitir_agrupado_sync` (orquestrador, chama uma e/ou outra
função conforme `emitir_nfe`/`emitir_nfse`, cada uma em transação
PRÓPRIA — ver nota "Assunção registrada" logo acima de
`_validar_selecao_agrupavel_sync` pro racional dessa escolha)."""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services import comanda_service, contingencia_nfe_service, ibs_cbs_service, nfe_emissao_service, nfe_fiscal_common, nfse_emissao_service
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
            "CASE WHEN EXISTS(SELECT 1 FROM comanda_nfce cn WHERE cn.comanda = c.comanda AND cn.situacao <> 'C') THEN 1 ELSE 0 END AS tem_nfce, "
            "CASE WHEN EXISTS(SELECT 1 FROM comanda_nf cnf WHERE cnf.comanda = c.comanda AND cnf.tipo = 3 AND cnf.situacao <> 'C') THEN 1 ELSE 0 END AS ja_tem_nfe, "
            "CASE WHEN EXISTS(SELECT 1 FROM comanda_nf cnf WHERE cnf.comanda = c.comanda AND cnf.tipo = 2 AND cnf.situacao <> 'C') THEN 1 ELSE 0 END AS ja_tem_nfse, "
            "CASE WHEN EXISTS(SELECT 1 FROM movimentacao m JOIN pecas p ON p.codigo_int = m.codigo_int "
            "WHERE m.serie_nf = 'CM' AND m.num_nf = c.comanda AND ISNULL(m.Estornado, 0) = 0) THEN 1 ELSE 0 END AS tem_item_produto, "
            "CASE WHEN EXISTS(SELECT 1 FROM movimentacao m JOIN servicos s ON s.codigo = m.codigo_int "
            "WHERE m.serie_nf = 'CM' AND m.num_nf = c.comanda AND ISNULL(m.Estornado, 0) = 0) THEN 1 ELSE 0 END AS tem_item_servico "
            "FROM comanda c WHERE c.cliente = %s AND c.situacao = 'PG' ORDER BY c.data DESC, c.comanda DESC",
            (cliente,),
        )
        itens = [{
            "comanda": r["comanda"], "data": str(r.get("data")) if r.get("data") else None,
            "valor_venda": float(r.get("valor_venda") or 0), "tem_nfce": bool(r.get("tem_nfce")),
            "ja_tem_nfe": bool(r.get("ja_tem_nfe")), "ja_tem_nfse": bool(r.get("ja_tem_nfse")),
            "tem_item_produto": bool(r.get("tem_item_produto")), "tem_item_servico": bool(r.get("tem_item_servico")),
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
#
# Duas ações fiscais INDEPENDENTES sobre a MESMA seleção de comandas —
# decisão direta do usuário (Leandro, 2026-08-21, respondendo o achado da
# reauditoria sobre item de Serviço ser silenciosamente excluído): "Na
# tela existem duas funcionalidades completamente distintas e
# independentes: 1) emitir NFe dos produtos, 2) emitir NFSe dos serviços
# — o usuário escolhe a ação que ele quer: nenhuma / só produto / só
# serviço / produto e serviço." Implementado como 2 checkboxes
# independentes na tela (`emitir_nfe`/`emitir_nfse`) — "nenhuma" é
# simplesmente não marcar nada (validado abaixo, sem estado de sistema
# próprio). Cada ação grava seu PRÓPRIO tipo em `comanda_nf` (3=NF-e
# agrupada, 2=NFS-e — mesmo valor já usado por `comanda_service.
# _emitir_nfse_comanda_sync` pra NFS-e de comanda única, reaproveitado
# aqui porque do ponto de vista de quem lê `comanda_nf` depois não importa
# se a NFS-e cobriu 1 ou várias comandas, só que aquela comanda tem uma) —
# então uma comanda já coberta por NF-e ainda pode entrar numa NFS-e
# depois (e vice-versa), o gate de "já agrupada" é POR TIPO, não mais
# genérico como antes desta rodada.
#
# Assunção registrada (não confirmada explicitamente por Leandro — sinalizar
# se estiver errada): as duas emissões, quando marcadas juntas, rodam em
# transações INDEPENDENTES (cada uma abre sua própria conexão) — se uma
# falhar (ex.: produto sem tributação cadastrada) a outra ainda é tentada e
# o resultado que deu certo não se perde. A alternativa (tudo ou nada, uma
# única transação) faria uma falha na NFS-e desfazer uma NF-e que já tinha
# sido transmitida com sucesso ao SEFAZ — pior, já que não dá pra
# "desfazer" uma nota já autorizada só com ROLLBACK local.
# ---------------------------------------------------------------------------

def _validar_selecao_agrupavel_sync(cur, comandas: list[int]) -> dict:
    """Validações compartilhadas por NF-e e NFS-e agrupadas: comandas
    existem, todas faturadas, todas do MESMO cliente. Retorna
    `{"success": True, "cliente_codigo": ...}` ou o dict de erro pronto
    pra devolver direto."""
    placeholders = ",".join(["%s"] * len(comandas))
    cur.execute(
        f"SELECT comanda, cliente, situacao, valor_venda FROM comanda WHERE comanda IN ({placeholders})",
        tuple(comandas),
    )
    cabecalhos = {r["comanda"]: r for r in cur.fetchall()}
    faltantes = [c for c in comandas if c not in cabecalhos]
    if faltantes:
        return {"success": False, "message": f"Comanda(s) não encontrada(s): {faltantes}."}
    nao_pagas = [c for c in comandas if (cabecalhos[c].get("situacao") or "").strip().upper() != "PG"]
    if nao_pagas:
        return {"success": False, "message": f"Só é possível agrupar comandas faturadas — comanda(s) {nao_pagas} não está(ão) faturada(s)."}
    clientes_distintos = {cabecalhos[c].get("cliente") for c in comandas}
    if len(clientes_distintos) > 1:
        return {"success": False, "message": "Todas as comandas selecionadas precisam ser do MESMO cliente."}
    cliente_codigo = next(iter(clientes_distintos))
    if not cliente_codigo:
        return {"success": False, "message": "Comanda sem cliente vinculado — não é possível emitir nota fiscal."}
    return {"success": True, "cliente_codigo": cliente_codigo}


def _emitir_nfe_agrupada_sync(
    servidor: str, banco: str, *, comandas: list[int], usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False, paga_frete: Optional[int] = None,
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
        validacao = _validar_selecao_agrupavel_sync(cur, comandas)
        if not validacao.get("success"):
            conn.close()
            return validacao
        cliente_codigo = validacao["cliente_codigo"]

        cur.execute(
            f"SELECT comanda FROM comanda_nf WHERE comanda IN ({placeholders}) AND tipo = 3 AND situacao <> 'C'",
            tuple(comandas),
        )
        ja_agrupadas = [r["comanda"] for r in cur.fetchall()]
        if ja_agrupadas:
            conn.close()
            return {"success": False, "message": f"Comanda(s) {ja_agrupadas} já está(ão) vinculada(s) a uma NF-e — não é possível agrupar de novo."}

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

        # IBS/CBS calculado JUNTO com a tributação (ICMS/PIS/COFINS/CFOP) —
        # é só mais um grupo de tags dentro do MESMO XML que vai ser
        # assinado e transmitido, igual a qualquer outro imposto, nunca um
        # enriquecimento à parte depois. Reverte a "Correção de ordem"
        # 2026-08-20 (calculava depois, reescrevendo `n_fiscal.xml` sem
        # reassinar — bug real de assinatura perdida, achado e corrigido
        # no mesmo dia, mesma sessão — ver PENDENCIAS.md > "Agrupar
        # Comandas em NF-e").
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
            taxa_nfce = ibs_cbs_service.resolver_taxa_nfce_para_ibs_cbs_sync(cur, cod_icms=cod_icms, destino=uf_sigla)
            ibs_cbs_item = (
                ibs_cbs_service.calcular_item_ibs_cbs(qtd=qtd, p_unit=valor_unitario, codigo_int=codigo_int, taxa=taxa_nfce)
                if taxa_nfce else None
            )
            itens_resolvidos.append({
                "codigo_int": codigo_int, "descricao": (item.get("descricao") or "").strip(),
                "ncm": (item.get("ncm") or "").strip(), "cfop": tributos.get("cfop_livro") or "5102",
                "unidade": (item.get("unidade") or "UN").strip(), "qtd": qtd, "valor_unitario": valor_unitario,
                "valor_total": valor_item, "origem": int(item.get("origem") or 0),
                "csosn": "102" if simples_nacional_cliente else "400", "cst_pis": "07", "cst_cofins": "07",
                "cod_icms": cod_icms, "ibs_cbs_xml": (ibs_cbs_item or {}).get("xml_item") or "",
                # Colunas DIFAL de `taxas`, já resolvidas em `tributos` —
                # ver nfe_regras_fiscais.py (achado 2026-08-28: grupo
                # ICMSUFDest nunca era montado por faltar esse threading).
                "aliquota_interestadual": tributos.get("aliquota_interestadual") or 0,
                "aliquota_interna_destino": tributos.get("aliquota_interna_destino") or 0,
                "percentual_origem": tributos.get("percentual_origem") or 0,
                "fundo_pobreza": tributos.get("fundo_pobreza") or 0,
                "_ibs_cbs_item": ibs_cbs_item,
            })

        ibs_cbs_totais_xml = ibs_cbs_service.calcular_totais_ibs_cbs(
            [item.pop("_ibs_cbs_item") for item in itens_resolvidos]
        )["xml_totais"]

        proximo_numero = int(controle.get("numero_nf") or 0) + 1
        serie = str(controle.get("serie_nf") or "1")

        # Contingência (Gestor NFCe achou o mecanismo 2026-08-19; conectado
        # aqui 2026-08-20) — se aberta, a emissão segue o caminho
        # alternativo (tpEmis 2/5, sem transmissão) — ver docstring de
        # `nfe_emissao_service.emitir_nfe_sync`. "Validar Contingência"
        # depois faz a transmissão de verdade — ver `contingencia_nfe_
        # service.listar_pendentes`/`validar_pendentes`.
        contingencia = contingencia_nfe_service.contingencia_aberta_sync(cur)
        resultado = nfe_emissao_service.emitir_nfe_sync(
            cur, cnpj_emit=(controle.get("cgc") or ""), nome_emit=(controle.get("rz_social") or ""),
            uf_sigla=uf_sigla, proximo_numero=proximo_numero, serie=serie, destinatario=destinatario,
            itens_resolvidos=itens_resolvidos, valor_total=round(valor_total, 2),
            tp_amb=nfe_fiscal_common.resolver_tp_amb_sync(cur),
            natureza_operacao=natureza_operacao, indFinal="1" if consumidor_final else "0",
            ibs_cbs_totais_xml=ibs_cbs_totais_xml, contingencia=contingencia, paga_frete=paga_frete,
            servidor=servidor, banco=banco,
        )
        if not resultado.get("success"):
            conn.close()
            return resultado

        situacao_n_fiscal = resultado.get("situacao") or "A"
        cstat_n_fiscal = resultado.get("cstat") or "100"
        # `dh_recbto` cru do SEFAZ (ISO 8601 com offset) quebra numa
        # coluna DATETIME e derruba a transação DEPOIS do sucesso já
        # confirmado — mesmo bug achado ao vivo no MDF-e 2026-08-23,
        # corrigido aqui 2026-08-24 (ver `nfe_fiscal_common.parse_dh_sefaz`).
        cur.execute(
            "INSERT INTO n_fiscal (num_nf, serie_nf, fornecedor, uf, data_nf, data_mov, valor_total, situacao, "
            "chave_acesso, protocolo_sefaz, dhRecbto, cstat, xml, XML_TOT_IBS_CBS, paga_frete) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s, %s, %s, %s, CONVERT(date, GETDATE()), CONVERT(date, GETDATE()), %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (resultado["numero"], resultado["serie"], cliente_codigo, uf_sigla, round(valor_total, 2), situacao_n_fiscal,
             resultado["chave_acesso"], resultado["protocolo_sefaz"], nfe_fiscal_common.parse_dh_sefaz(resultado.get("dh_recbto")), cstat_n_fiscal,
             resultado["xml"], ibs_cbs_totais_xml, paga_frete),
        )
        codigo_n_fiscal = int(cur.fetchone()["codigo"])
        for item in itens_resolvidos:
            cur.execute(
                "INSERT INTO n_fiscal_itens (codigo, codigo_int, qtd, p_unit, valor_total, tributacao, "
                "aliquota_interestadual, aliquota_interna_destino, percentual_origem, fundo_pobreza) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    codigo_n_fiscal, item["codigo_int"], item["qtd"], item["valor_unitario"], item["valor_total"], item["cfop"],
                    # DIFAL (2026-08-28) — mesmas 4 colunas já lidas por
                    # apuracao_fiscal_service.py::_calc_difal (Apuração
                    # Fiscal, modo DIFAL). Ver nota em PENDENCIAS.md sobre
                    # o restante do item (ICMS/IPI/PIS/COFINS) NÃO ser
                    # persistido aqui — achado adjacente, fora deste
                    # pedido específico.
                    item.get("aliquota_interestadual") or 0, item.get("aliquota_interna_destino") or 0,
                    item.get("percentual_origem") or 0, item.get("fundo_pobreza") or 0,
                ),
            )

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


def _emitir_nfse_agrupada_sync(
    servidor: str, banco: str, *, comandas: list[int], usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    """Emite UMA NFS-e (DPS Nacional) cobrindo os itens de SERVIÇO de
    várias comandas do MESMO cliente — generaliza
    `comanda_service._emitir_nfse_comanda_sync` (que só cobre 1 comanda)
    pro mesmo formato de agrupamento já usado por `_emitir_nfe_agrupada_
    sync` acima. Ação independente da NF-e (ver docstring do módulo) —
    uma comanda com produto E serviço pode entrar nas duas emissões, cada
    uma pegando só os itens do seu tipo.

    Mesma simplificação já documentada em `comanda_service.
    _emitir_nfse_comanda_sync`: IBS/CBS ("uma DPS = um serviço principal")
    resolve CST/classTrib só a partir do PRIMEIRO item consolidado — não
    reavaliada nesta generalização."""
    if not comandas or len(comandas) < 1:
        return {"success": False, "message": "Selecione ao menos uma comanda."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not master and classe is not None and not tem_permissao(cur, classe, "ALTERAR_COMANDA", "EMITIR_NFSE"):
            conn.close()
            return {"success": False, "message": "Sem permissão para emitir nota fiscal de serviço."}
        if not comanda_service._modulo_sefin_nacional_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo SEFIN Nacional não está ativo (Módulos e Recursos)."}

        placeholders = ",".join(["%s"] * len(comandas))
        validacao = _validar_selecao_agrupavel_sync(cur, comandas)
        if not validacao.get("success"):
            conn.close()
            return validacao
        cliente_codigo = validacao["cliente_codigo"]

        cur.execute(
            f"SELECT comanda FROM comanda_nf WHERE comanda IN ({placeholders}) AND tipo = 2 AND situacao <> 'C'",
            tuple(comandas),
        )
        ja_agrupadas = [r["comanda"] for r in cur.fetchall()]
        if ja_agrupadas:
            conn.close()
            return {"success": False, "message": f"Comanda(s) {ja_agrupadas} já está(ão) vinculada(s) a uma NFS-e — não é possível agrupar de novo."}

        cur.execute(
            "SELECT m.codigo_int, s.descricao, s.cod_lista_servico, s.cod_icms, s.cod_servico_municipio, "
            "m.qtd, m.p_unit "
            f"FROM movimentacao m JOIN servicos s ON s.codigo = m.codigo_int "
            f"WHERE m.serie_nf = 'CM' AND m.num_nf IN ({placeholders}) AND ISNULL(m.Estornado, 0) = 0",
            tuple(comandas),
        )
        itens_mov = cur.fetchall()
        if not itens_mov:
            conn.close()
            return {"success": False, "message": "Nenhuma das comandas selecionadas tem item de serviço — nada a emitir."}

        # Consolida por (codigo_int, p_unit) — serviço não tem controle de
        # número de série (coluna não existe em `servicos`), então
        # diferente de `_emitir_nfe_agrupada_sync` não precisa da exceção
        # de nunca somar.
        consolidados: dict[tuple, dict] = {}
        for item in itens_mov:
            codigo_int = (item.get("codigo_int") or "").strip()
            p_unit = round(float(item.get("p_unit") or 0), 10)
            chave = (codigo_int, p_unit)
            if chave in consolidados:
                consolidados[chave]["qtd"] += float(item.get("qtd") or 0)
            else:
                consolidados[chave] = {**item, "qtd": float(item.get("qtd") or 0)}

        cur.execute("SELECT cgc, cidade, uf, simples_servico FROM controle")
        controle = cur.fetchone() or {}
        cur.execute("SELECT numero_DPS, serie_DPS, opcao_simples, RegimeEspecialTributacao, codigo_nbs FROM controle_aux")
        controle_aux = cur.fetchone() or {}

        itens = [
            {
                "codigo_int": (item.get("codigo_int") or "").strip(),
                "descricao": (item.get("descricao") or "").strip(),
                "cod_lista_servico": (item.get("cod_lista_servico") or "").strip(),
                "cod_servico_municipio": (item.get("cod_servico_municipio") or "").strip(),
                "valor": round(float(item.get("qtd") or 0) * float(item.get("p_unit") or 0), 2),
            }
            for item in consolidados.values()
        ]

        ibs_cbs_cst = ""
        ibs_cbs_classtrib = ""
        primeiro = next(iter(consolidados.values()))
        cod_icms_serv = (primeiro.get("cod_icms") or "").strip()
        uf_sigla_serv = (controle.get("uf") or "").strip().upper()
        if cod_icms_serv and uf_sigla_serv:
            taxa_nfce_serv = ibs_cbs_service.resolver_taxa_nfce_para_ibs_cbs_sync(cur, cod_icms=cod_icms_serv, destino=uf_sigla_serv)
            if taxa_nfce_serv:
                ibs_cbs_serv = ibs_cbs_service.calcular_item_ibs_cbs(
                    qtd=float(primeiro.get("qtd") or 0), p_unit=float(primeiro.get("p_unit") or 0),
                    codigo_int=(primeiro.get("codigo_int") or ""), taxa=taxa_nfce_serv,
                )
                if ibs_cbs_serv:
                    ibs_cbs_cst = ibs_cbs_serv["cst_ibs_uf"]
                    ibs_cbs_classtrib = ibs_cbs_serv["classtrib_ibs_uf"]

        cod_municipio = nfe_fiscal_common.resolver_cod_municipio_ibge(controle.get("cidade"), controle.get("uf"))
        if not cod_municipio:
            conn.close()
            return {
                "success": False,
                "message": (
                    f"Código de município (IBGE) não conhecido para '{controle.get('cidade')}/{controle.get('uf')}' — "
                    "cadastre-o em `_MUNICIPIOS_IBGE_CONHECIDOS` (comanda_service.py) antes de emitir."
                ),
            }

        tomador = None
        if cliente_codigo:
            cur.execute("SELECT cgc_cpf, nome FROM cliente WHERE codigo = %s", (cliente_codigo,))
            tomador = cur.fetchone()

        resultado = nfse_emissao_service.emitir_nfse_sync(
            cur, comanda=comandas[0], cnpj_prest=(controle.get("cgc") or ""), cod_municipio=cod_municipio,
            opcao_simples_nacional=bool(controle_aux.get("opcao_simples")),
            regime_especial_tributacao=int(controle_aux.get("RegimeEspecialTributacao") or 0),
            proximo_numero=int(controle_aux.get("numero_DPS") or 0) + 1,
            serie=str(controle_aux.get("serie_DPS") or "1"), tomador=tomador, itens=itens,
            tp_amb=nfe_fiscal_common.resolver_tp_amb_sync(cur),
            ibs_cbs_cst=ibs_cbs_cst, ibs_cbs_classtrib=ibs_cbs_classtrib,
            codigo_nbs=(controle_aux.get("codigo_nbs") or ""),
            simples_servico_pct=float(controle.get("simples_servico") or 0),
            servidor=servidor, banco=banco,
        )
        if not resultado.get("success"):
            conn.close()
            return resultado

        valor_total = sum(i["valor"] for i in itens)
        cur.execute(
            "INSERT INTO dps (comanda, num_dps, serie_dps, data_dps, hora_dps, valor_total, situacao, STATUS, "
            "chave_acesso_dps, chave_acesso_nfse, XML_NFSE) "
            "VALUES (%s, %s, %s, CONVERT(date, GETDATE()), CONVERT(varchar(8), GETDATE(), 108), %s, 'A', 'Transmitida', %s, %s, %s)",
            (comandas[0], resultado["numero"], resultado["serie"], valor_total,
             resultado.get("id_dps"), resultado.get("chave_acesso"), resultado.get("xml_nfse")),
        )
        cur.execute(
            "INSERT INTO n_fiscal (num_nf, serie_nf, data_nf, data_mov, valor_total, situacao_nfse, chave_acesso, xml) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s, %s, CONVERT(date, GETDATE()), CONVERT(date, GETDATE()), %s, 1, %s, %s)",
            (resultado["numero"], resultado["serie"], valor_total, resultado["chave_acesso"],
             resultado.get("xml_nfse") or resultado["xml_dps"]),
        )
        codigo_n_fiscal = int(cur.fetchone()["codigo"])
        cur.execute(
            f"INSERT INTO comanda_nf (comanda, nota_fisc, tipo, situacao) "
            f"SELECT comanda, %s, 2, 'A' FROM comanda WHERE comanda IN ({placeholders})",
            (codigo_n_fiscal, *comandas),
        )
        cur.execute("UPDATE controle_aux SET numero_DPS = %s", (resultado["numero"],))
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


def _emitir_agrupado_sync(
    servidor: str, banco: str, *, comandas: list[int], emitir_nfe: bool, emitir_nfse: bool,
    usuario: Optional[int] = None, classe: Optional[int] = None, master: bool = False,
    paga_frete: Optional[int] = None,
) -> dict:
    """Orquestra as 2 ações independentes (ver docstring do módulo) —
    chama uma e/ou outra conforme marcado, cada uma em transação própria
    (uma falhar não desfaz a outra que já tenha sido transmitida)."""
    if not emitir_nfe and not emitir_nfse:
        return {"success": False, "message": "Selecione ao menos uma ação: emitir NF-e de produtos e/ou NFS-e de serviços."}

    resultado_nfe = None
    resultado_nfse = None
    if emitir_nfe:
        resultado_nfe = _emitir_nfe_agrupada_sync(
            servidor, banco, comandas=comandas, usuario=usuario, classe=classe, master=master, paga_frete=paga_frete,
        )
    if emitir_nfse:
        resultado_nfse = _emitir_nfse_agrupada_sync(
            servidor, banco, comandas=comandas, usuario=usuario, classe=classe, master=master,
        )

    sucesso_nfe = resultado_nfe is None or resultado_nfe.get("success")
    sucesso_nfse = resultado_nfse is None or resultado_nfse.get("success")
    mensagens = []
    if resultado_nfe is not None:
        mensagens.append(("NF-e: " + (resultado_nfe.get("message") or "emitida com sucesso.")) if not resultado_nfe.get("success") else "NF-e de produtos emitida com sucesso.")
    if resultado_nfse is not None:
        mensagens.append(("NFS-e: " + (resultado_nfse.get("message") or "emitida com sucesso.")) if not resultado_nfse.get("success") else "NFS-e de serviços emitida com sucesso.")

    return {
        "success": sucesso_nfe and sucesso_nfse,
        "message": " ".join(mensagens),
        "resultado_nfe": resultado_nfe,
        "resultado_nfse": resultado_nfse,
    }


async def list_comandas_agrupaveis(servidor: str, banco: str, cliente: int, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_list_comandas_agrupaveis_sync, servidor, banco, cliente=cliente, classe=classe, master=master)


async def emitir_nfe_agrupada(
    servidor: str, banco: str, comandas: list[int], usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False, paga_frete: Optional[int] = None,
) -> dict:
    return await asyncio.to_thread(
        _emitir_nfe_agrupada_sync, servidor, banco, comandas=comandas, usuario=usuario, classe=classe, master=master,
        paga_frete=paga_frete,
    )


async def emitir_agrupado(
    servidor: str, banco: str, comandas: list[int], *, emitir_nfe: bool, emitir_nfse: bool,
    usuario: Optional[int] = None, classe: Optional[int] = None, master: bool = False,
    paga_frete: Optional[int] = None,
) -> dict:
    """Ponto de entrada novo (2026-08-21) — as 2 ações independentes (NF-e
    de produtos / NFS-e de serviços) que a rota chama agora, em vez de
    `emitir_nfe_agrupada` direto. Ver docstring do módulo e de
    `_emitir_agrupado_sync`."""
    return await asyncio.to_thread(
        _emitir_agrupado_sync, servidor, banco, comandas=comandas, emitir_nfe=emitir_nfe, emitir_nfse=emitir_nfse,
        usuario=usuario, classe=classe, master=master, paga_frete=paga_frete,
    )

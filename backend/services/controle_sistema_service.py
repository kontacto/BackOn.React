"""Controle do Sistema (Configurações > Geral) — tabela `controle` (linha única,
`empresa=0`) + `controle_aux` (linha única, `empresa_aux=0`). Legado: FrmGerCon.frm
("Dados para controle"), a versão mestra em
`C:\\Desenv\\VB6\\Diario Access-SQL\\SQLSERVER\\Geral\\FrmGerCon.frm` (ver seção
"Legacy VB6 Source Reference" no CLAUDE.md). Mono-empresa por ora — `empresa`/
`empresa_aux` fixos em 0, update às cegas (sem WHERE), mesmo padrão já usado em
`controle_config_service.py`. Preparado pra virar multi-empresa no futuro sem
redesenho (bastaria parametrizar o 0).

A aba "Kontacto" do legado (ferramenta interna de suporte/revenda, desbloqueio por
senha oculta) não entra aqui — só as 7 abas de configuração de negócio. O campo
`controle_aux.baixa_pedido_compra` também não entra: bug confirmado no legado (o
Gravar tem a linha comentada, nunca teve efeito em produção).

Todo o mapeamento campo→coluna foi extraído do código-fonte do `.frm`
(`CarregaDados`/`CmdOk_Click`), não dos rótulos da tela — vários rótulos mentem sobre
a coluna real, marcados abaixo onde relevante.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _to_json_safe

EMPRESA = 0  # mono-empresa; controle.empresa / controle_aux.empresa_aux fixos em 0

# =====================================================================
# CAMPOS — tabela `controle`
# =====================================================================
CAMPOS_CONTROLE = [
    # Empresarial
    "cgc", "rz_social", "data_abertura", "fantasia", "inscr_est", "inscr_municipal",
    "nire", "ddd", "telefone", "CELULAR", "endereco", "numero", "complemento",
    "bairro", "cep", "cidade", "uf", "dias_troca", "percent_troca", "tipo_controle",
    "codigo", "numero_anp", "qtdturnos", "e_mail",
    # Movimentações — NÃO inclui o trio de NF (numero_nf/serie_nf/modelo_nf +
    # entrada + serviço): esses campos ficam fora do Gravar genérico, com botão
    # e log próprios — ver CAMPOS_NF_PRINCIPAL abaixo. Achado do usuário: o
    # legado grava esse trio com um botão dedicado ("Gravar Alterações NFE"),
    # separado do Gravar geral da tela, e gera uma linha de log específica
    # ("Alteração do Número de NF de X para Y."), não um diff genérico.
    "margem_nf", "modelo_os", "modelo_recibo", "modelo_pedido", "modelo_pedido_compra",
    "cod_rel", "numero_os", "cod_peca", "data_movimento",
    # Diversos — "Senha_Gerente" (rótulo "Senha para venda com estoque negativo")
    # é distinta de controle.senha_gerente_cx (aba Financeiro, "Senha Gerente
    # p/Alteração") — dois campos de senha de gerente diferentes.
    "Senha_Gerente", "preco_cld", "paga_comissao_venda_garantia",
    "desconto_PDV", "desconto_PDV_Gerente", "desconto_PDV_Vendedor", "desconto_PDV_Supervisor",
    # Fiscal — "PROTOCOLO_TLS_NFSE" é a única coluna do grupo NFS-e que fica em
    # `controle`, não `controle_aux`. "protocolo_tls_email" é da seção
    # "Configuração de Emails" (achado: "Usa TLS 1.2").
    "emite_nf_comanda", "pagina_lmc", "PROTOCOLO_TLS_NFSE", "protocolo_tls_email",
    "iss", "Simples_Servico", "cst_pis_cofins_dps", "pis", "Cofins",
    "retencao_pis_cofins_dps", "perc_tributos_federais_dps", "perc_tributos_estaduais_dps",
    "perc_tributos_municipais_dps",
    # Fiscal — "Consulta CEP" (achado pós-screenshots: são colunas de `controle`)
    "CEP_GUIACEP", "CEP_CORREIOS", "CEP_USUARIO", "CEP_SENHA", "CEP_CONTRATO",
    "CEP_URL_TOKEN", "CEP_URL_CEP", "CEP_URL_LOGRADOURO",
    # Outros — Pesquisa de Satisfação BTEN
    "Pesquisa_Satisfacao_BTEN", "token_Authorization_pesquisa_satisfacao",
    "token_business_pesquisa_satisfacao",
    # Financeiro — "Inclui_Classe_Caixa_Mov" (rótulo "Permite Lcto Sem Classe Pré
    # Cadastrada") e "Exclui_Recebimento_Automatico" (rótulo "Cancelar comandas com
    # Vencimentos já recebidos") têm semântica ambígua/contraditória com o rótulo
    # no próprio legado — mantidos com o rótulo tal como aparece na tela hoje,
    # não vale renomear sem confirmação funcional.
    "Inclui_Classe_Caixa_Mov", "senha_gerente_cx", "AgrupaComandas_Cx",
    "Transf_Caixa_Contabil", "Exclui_Recebimento_Automatico",
    "numero_dup", "desmembramento_dup", "seq_recibo", "ano_recibo",
    "Multa_Atraso_Pag", "Mora_Dia_Pag", "Tarifa_Boleto", "dias_protesto",
    "Msg_Padrao_Boleto_1", "Msg_Padrao_Boleto_2", "Msg_Padrao_Boleto_3",
    "Minimo_Boleto", "Dias_Ver_Cx", "dias_alt_cx",
    "conta_transf_caixa",
    "classe_ent_tarifa", "sub_classe_ent_tarifa", "classe_ent_juros", "sub_classe_ent_juros",
    "classe_ent_descontos", "sub_classe_ent_descontos",
    "classe_sai_tarifa", "sub_classe_sai_tarifa", "classe_sai_juros", "sub_classe_sai_juros",
    "classe_sai_descontos", "sub_classe_sai_descontos",
    # Contratos
    "fatura_os_contrato", "tipo_mov_contrato_peca", "tipo_mov_contrato_servico",
    "cod_servico_contrato", "forma_pag_contrato",
    # Kontacto — só visível/editável pelo usuário Master (gate no frontend, ver
    # `controle-sistema.tsx`). Achado: `TICKET_PIX` ("Exibe Ticket como PIX")
    # não existe nesta base — a coluna está no .frm mas não no banco real,
    # descartada. "Validade" também não entra: é um valor decodificado de
    # `controle.controle` (licença) via função proprietária do legado
    # (`RetornaCodigo`), não uma coluna própria.
    "codigo_kontacto", "situacao", "exige_cpf_cliente", "aceita_duplicar_cnpj", "inc_prod_os",
]

# Campo somente-leitura (nunca editável — Enabled=0 no legado, é a licença
# criptografada da instalação). Fica de fora de CAMPOS_CONTROLE (não entra no
# UPDATE do Gravar geral), mas é lido pra exibição na aba Kontacto.
CAMPO_CONTROLE_LICENCA = "controle"

_CONTROLE_BOOL_FIELDS = {
    "Senha_Gerente", "preco_cld", "paga_comissao_venda_garantia",
    "emite_nf_comanda",
    "CEP_GUIACEP", "CEP_CORREIOS", "Pesquisa_Satisfacao_BTEN",
    "Inclui_Classe_Caixa_Mov", "senha_gerente_cx", "AgrupaComandas_Cx",
    "Transf_Caixa_Contabil", "Exclui_Recebimento_Automatico",
    "fatura_os_contrato",
    "exige_cpf_cliente", "aceita_duplicar_cnpj", "inc_prod_os",
}
# `PROTOCOLO_TLS_NFSE`/`protocolo_tls_email` são `int`, não `bit` — apesar de a
# tela mostrar um radio de 2 opções (TLS 1.0/1.2), o valor gravado não é um
# 0/1 simples (visto ao vivo: 10 no banco de teste) — tratados como numéricos
# genéricos (ver ramo `else` de `_coerce_vals`), não como boolean.
_CONTROLE_TEXT_FIELDS = {
    "cgc", "rz_social", "fantasia", "inscr_est", "inscr_municipal", "nire",
    "telefone", "CELULAR", "endereco", "complemento", "bairro", "cep", "cidade", "uf",
    "codigo", "numero_anp", "e_mail",
    "serie_nf", "serie_nf_ent", "serie_nf_ser", "cod_rel", "desmembramento_dup",
    "cst_pis_cofins_dps", "retencao_pis_cofins_dps",
    "codigo_kontacto", "situacao",
    "CEP_USUARIO", "CEP_SENHA", "CEP_CONTRATO", "CEP_URL_TOKEN", "CEP_URL_CEP",
    "CEP_URL_LOGRADOURO", "token_Authorization_pesquisa_satisfacao",
    "token_business_pesquisa_satisfacao",
    "Msg_Padrao_Boleto_1", "Msg_Padrao_Boleto_2", "Msg_Padrao_Boleto_3",
    "tipo_mov_contrato_peca", "tipo_mov_contrato_servico", "cod_servico_contrato",
    "forma_pag_contrato",
}
_CONTROLE_DATE_FIELDS = {"data_abertura", "data_movimento", "data_inicio_nfe", "data_inicio_nfse", "data_inicio_paf"}

# =====================================================================
# CAMPOS — tabela `controle_aux`
# =====================================================================
CAMPOS_CONTROLE_AUX = [
    # Empresarial
    "suframa", "cnae_fiscal_principal", "cnae_fiscal_servico", "csc", "csc_hash",
    # Movimentações — NÃO inclui numero_nfce/serie_nfce (botão "Gravar Alterações
    # NFCE" próprio) nem numero_MDFE/serie_MDFE (botão "Gravar Alterações MDF-e"
    # próprio) — mesmo raciocínio do trio de NF em CAMPOS_CONTROLE, ver
    # CAMPOS_NFCE_NUMERACAO/CAMPOS_MDFE_NUMERACAO abaixo.
    "versao_nfe", "versao_layout_nfce",
    "VersaoQrCodeNFCe", "modelo_danfe_nfce",
    "porta_concentrador", "id_fusion", "modelo_concentrador",
    "tipo_comunicacao_concentrador", "Permite_venda_combustiveis",
    "QTD_ABASTECIMENTOS_NFCE",
    # Diversos
    "nome_fantasia_cabecalho_dav", "Inclui_Dados_Faturar_Para", "Destaca_Desconto_Cedido",
    "Habilita_Preco_Tabela_Pedido", "registra_venda_automatica", "fecha_pedido_automaticamente",
    "exige_aprovacao_itens_os", "exige_expedicao_itens_os", "EXIGE_KM_OS",
    "EXIGE_referencia_OS", "ControlaRevisaoOS", "Altera_preco_venda_tela",
    "ALERTA_ESTOQUE_NEGATIVO", "EXIGE_OS_ORIGINAL_GARANTIA",
    "bloqueia_venda_cliente_com_debito",
    "emite_vale_troca", "msg_vale_troca_1", "msg_vale_troca_2", "validade_vale_troca",
    "dias_troca",  # ⚠ distinta de controle.dias_troca (aba Empresarial)
    "ALERTA_ESTOQUE", "EMAIL_ALERTA_ESTOQUE", "ALERTA_ESTOQUE_MINIMO",
    "ALERTA_ESTOQUE_RESSUPRIMENTO", "ALERTA_ESTOQUE_ZERADO",
    "MENSAGEM_OS", "MENSAGEM_obs_OS", "COD_CLIENTE_ORCAMENTO", "PRODUTO_ORCAMENTO",
    # Fiscal
    "informa_codigo_barras", "Inclui_Endereco_Entrega_Obs_Nfe",
    "Inclui_Endereco_Cobranca_Obs_Nfe", "indicador_intermediario",
    "IMPRIME_VENDEDOR_DANFE_NFCE", "DEVOLUCAO_CANCELA_NFE_ORIGINAL",
    "imprime_dados_os_danfe",
    "Regime_Trib",  # ⚠ rótulo legado "Regime Tributação Municipal" está errado —
    # é o CRT (Código de Regime Tributário nacional do Simples Nacional).
    # Na tela nova o rótulo deve ser "Regime Tributário (CRT)".
    "SERVICO_FRETE_NFCE", "TRANSPORTADOR_FRETE_NFCE",
    "opcao_simples", "incentivo_cultural", "RegimeEspecialTributacao",
    "NaturezaOperacao", "numero_DPS", "serie_DPS", "codigo_nbs", "ISS_Retido",
    "numero_rps", "serie_rps",
    # Fiscal — "Configuração de Emails" (achado pós-screenshots)
    "e_mail_rel", "smtp_rel", "porta_smtp_rel", "login_rel", "ssl_rel", "senha_rel",
    "e_mail_COBRANCA", "smtp_COBRANCA", "porta_smtp_COBRANCA", "login_COBRANCA",
    "ssl_COBRANCA", "senha_COBRANCA", "ident_COBRANCA",
    "e_mail_contrato", "smtp_contrato", "porta_smtp_contrato", "login_contrato",
    "ssl_contrato", "senha_contrato", "ident_contrato", "identificacao_remetente_contrato",
    # Outros
    "m2_area_minima_padrao", "m2_area_minima_modelado", "m2_area_minima_engenharia",
    "m2_area_minima_modelado_engenharia", "m2_area_minima_comum_lapidacao",
    "m2_area_minima_comum_sem_lapidacao", "metro_quadrado_minima_metragem",
    "vidro_controla_cabeca_chapa", "tipo_mov_garantia",
    # Financeiro
    "TROCO_CARTAO", "cancelamento_paf_exige_senha", "transf_ent_sai_caixa",
    # Kontacto — só visível/editável pelo usuário Master. Botões "Configuração
    # de Clientes" (já coberto por Módulos e Recursos) fica de fora — mesmo
    # critério já usado pros outros botões de sub-tela desta leva.
    "consulta_por_descricao_paf", "imprime_nfse",
    "PERGUNTA_EMITE_NFCE", "USA_PRECO_BASE_NFCE", "IMPRIME_NFCE_NAO_FISCAL", "ESCOLHE_NFE_NFCE",
    "data_inicio_nfe", "data_inicio_nfse", "data_inicio_paf",
    "path_padrao_xml", "Path_importacao_venda_externa", "Path_backup_sql", "path_gestor_documentos",
    "PATH_LOGO_EMAIL_COBRANCA", "TEXTO_CORPO_EMAIL_COBRANCA",
    # Integração TRAY (aba Outros, botão próprio) — escopo reduzido aos campos
    # de credencial/ativação (`FrmIntTray.frm`, achado via .frm real). Os
    # campos de sincronização de pedidos do site (tipo_pedido_site,
    # vendedor_site, area_atuacao_site, datas de sincronização) e os de
    # armazenamento em nuvem (Azure_*) ficam de fora — não existe motor de
    # sincronização Tray/Azure implementado neste app pra consumir esses
    # valores, seria configuração morta.
    "integracao_tray", "TRAY_ID_LOJA", "TRAY_url_api", "TRAY_Consumer_Key", "TRAY_Consumer_Secret", "TRAY_code",
]

# =====================================================================
# Campos com botão + log próprios (fora do Gravar genérico) — achado do
# usuário direto na tela legada: o botão "Gravar" principal grava tudo, exceto
# os campos de numeração de nota, que têm botões dedicados ("Gravar Alterações
# NFE"/"NFCE"/"MDF-e") e cada um gera uma linha de log com descrição
# específica do que mudou ("Alteração do Número de NF de X para Y."), não um
# diff genérico de campos. Continuam presentes no SELECT do GET (pra exibição
# no formulário), só saem do UPDATE do Gravar genérico.
CAMPOS_NF_PRINCIPAL = [  # tabela `controle` — botão "Gravar Alterações NFE"
    "numero_nf", "serie_nf", "modelo_nf",
    "numero_nf_ent", "serie_nf_ent", "modelo_nf_ent",
    "numero_nf_ser", "serie_nf_ser",
]
CAMPOS_NFCE_NUMERACAO = ["numero_nfce", "serie_nfce"]  # tabela `controle_aux` — botão "Gravar Alterações NFCE"
CAMPOS_MDFE_NUMERACAO = ["numero_MDFE", "serie_MDFE"]  # tabela `controle_aux` — botão "Gravar Alterações MDF-e"

_NF_PRINCIPAL_TEXT_FIELDS = {"serie_nf", "serie_nf_ent", "serie_nf_ser"}
_NFCE_NUMERACAO_TEXT_FIELDS = {"serie_nfce"}
_MDFE_NUMERACAO_TEXT_FIELDS = {"serie_MDFE"}

# Rótulos amigáveis pra descrição de log — usados por `_descricao_alteracoes`,
# chamada pelas rotas dedicadas de cada um dos 3 grupos acima.
LABELS_NF_PRINCIPAL = {
    "numero_nf": "Número de NF", "serie_nf": "Série de NF", "modelo_nf": "Modelo de NF",
    "numero_nf_ent": "Número de NF de Entrada", "serie_nf_ent": "Série de NF de Entrada",
    "modelo_nf_ent": "Modelo de NF de Entrada",
    "numero_nf_ser": "Número de NF de Serviço", "serie_nf_ser": "Série de NF de Serviço",
}
LABELS_NFCE_NUMERACAO = {"numero_nfce": "Número de NFCe", "serie_nfce": "Série de NFCe"}
LABELS_MDFE_NUMERACAO = {"numero_MDFE": "Número de MDF-e", "serie_MDFE": "Série de MDF-e"}

_CONTROLE_AUX_BOOL_FIELDS = {
    "Inclui_Dados_Faturar_Para", "Destaca_Desconto_Cedido", "Habilita_Preco_Tabela_Pedido",
    "registra_venda_automatica", "fecha_pedido_automaticamente", "exige_aprovacao_itens_os",
    "ControlaRevisaoOS", "ALERTA_ESTOQUE_NEGATIVO", "EXIGE_OS_ORIGINAL_GARANTIA",
    "bloqueia_venda_cliente_com_debito", "emite_vale_troca",
    "ALERTA_ESTOQUE", "ALERTA_ESTOQUE_MINIMO", "ALERTA_ESTOQUE_RESSUPRIMENTO",
    "ALERTA_ESTOQUE_ZERADO", "Inclui_Endereco_Entrega_Obs_Nfe",
    "Inclui_Endereco_Cobranca_Obs_Nfe", "indicador_intermediario",
    "IMPRIME_VENDEDOR_DANFE_NFCE", "DEVOLUCAO_CANCELA_NFE_ORIGINAL",
    "imprime_dados_os_danfe", "opcao_simples", "incentivo_cultural", "ISS_Retido",
    "ssl_rel", "ssl_COBRANCA", "ssl_contrato",
    "m2_area_minima_padrao", "m2_area_minima_modelado", "m2_area_minima_engenharia",
    "m2_area_minima_modelado_engenharia", "m2_area_minima_comum_lapidacao",
    "m2_area_minima_comum_sem_lapidacao", "vidro_controla_cabeca_chapa",
    "TROCO_CARTAO", "cancelamento_paf_exige_senha", "transf_ent_sai_caixa",
    "nome_fantasia_cabecalho_dav",
    # tri-state no legado (Sim/Não/Recebimento) tratados como bool simples aqui:
    "Altera_preco_venda_tela", "EXIGE_KM_OS", "EXIGE_referencia_OS",
    "exige_expedicao_itens_os", "Permite_venda_combustiveis",
    "consulta_por_descricao_paf", "imprime_nfse",
    "PERGUNTA_EMITE_NFCE", "USA_PRECO_BASE_NFCE", "IMPRIME_NFCE_NAO_FISCAL", "ESCOLHE_NFE_NFCE",
    "integracao_tray",
}
_CONTROLE_AUX_TEXT_FIELDS = {
    "suframa", "cnae_fiscal_principal", "cnae_fiscal_servico", "csc", "csc_hash",
    "versao_nfe", "versao_layout_nfce", "serie_nfce", "VersaoQrCodeNFCe",
    "serie_MDFE", "porta_concentrador",
    "msg_vale_troca_1", "msg_vale_troca_2", "EMAIL_ALERTA_ESTOQUE",
    "MENSAGEM_OS", "MENSAGEM_obs_OS", "PRODUTO_ORCAMENTO",
    "SERVICO_FRETE_NFCE", "RegimeEspecialTributacao", "NaturezaOperacao",
    "serie_DPS", "codigo_nbs", "serie_rps",
    "e_mail_rel", "smtp_rel", "login_rel", "senha_rel",
    "e_mail_COBRANCA", "smtp_COBRANCA", "login_COBRANCA", "senha_COBRANCA", "ident_COBRANCA",
    "e_mail_contrato", "smtp_contrato", "login_contrato", "senha_contrato", "ident_contrato",
    "identificacao_remetente_contrato",
    "tipo_mov_garantia",
    "path_padrao_xml", "Path_importacao_venda_externa", "Path_backup_sql", "path_gestor_documentos",
    "PATH_LOGO_EMAIL_COBRANCA", "TEXTO_CORPO_EMAIL_COBRANCA",
    "TRAY_ID_LOJA", "TRAY_url_api", "TRAY_Consumer_Key", "TRAY_Consumer_Secret", "TRAY_code",
}


def _coerce_vals(dados: dict, campos: list, bool_fields: set, text_fields: set) -> dict:
    vals = {}
    for c in campos:
        v = dados.get(c)
        if c in bool_fields:
            vals[c] = 1 if v else 0
        elif c in text_fields:
            vals[c] = (v or "").strip() or None
        elif c in _CONTROLE_DATE_FIELDS:
            vals[c] = v or None
        else:
            try:
                vals[c] = float(v) if v not in (None, "") else 0.0
            except (TypeError, ValueError):
                vals[c] = 0.0
    return vals


def _get_controle_sistema_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        # Inclui os campos de numeração (NF/NFCe/MDF-e) na leitura, mesmo eles
        # ficando fora do Gravar genérico — o formulário precisa mostrar o
        # valor atual antes do usuário usar o botão dedicado de cada um.
        cols_c = ", ".join(CAMPOS_CONTROLE + CAMPOS_NF_PRINCIPAL + [CAMPO_CONTROLE_LICENCA])
        cur.execute(f"SELECT TOP 1 {cols_c} FROM controle WHERE empresa=%s", (EMPRESA,))
        row_c = cur.fetchone() or {}
        cols_a = ", ".join(CAMPOS_CONTROLE_AUX + CAMPOS_NFCE_NUMERACAO + CAMPOS_MDFE_NUMERACAO)
        cur.execute(f"SELECT TOP 1 {cols_a} FROM controle_aux WHERE empresa_aux=%s", (EMPRESA,))
        row_a = cur.fetchone() or {}
        cur.close()
        dados = _to_json_safe(row_c) or {}
        dados.update(_to_json_safe(row_a) or {})
        for k, v in dados.items():
            if isinstance(v, str):
                dados[k] = v.strip()
        return {"success": True, "dados": dados}
    finally:
        conn.close()


def _save_controle_sistema_sync(servidor: str, banco: str, dados: dict) -> dict:
    vals_c = _coerce_vals(dados, CAMPOS_CONTROLE, _CONTROLE_BOOL_FIELDS, _CONTROLE_TEXT_FIELDS)
    vals_a = _coerce_vals(dados, CAMPOS_CONTROLE_AUX, _CONTROLE_AUX_BOOL_FIELDS, _CONTROLE_AUX_TEXT_FIELDS)
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        set_c = ", ".join(f"[{c}]=%s" for c in CAMPOS_CONTROLE)
        cur.execute(
            f"UPDATE controle SET {set_c} WHERE empresa=%s",
            tuple(vals_c[c] for c in CAMPOS_CONTROLE) + (EMPRESA,),
        )
        set_a = ", ".join(f"[{c}]=%s" for c in CAMPOS_CONTROLE_AUX)
        cur.execute(
            f"UPDATE controle_aux SET {set_a} WHERE empresa_aux=%s",
            tuple(vals_a[c] for c in CAMPOS_CONTROLE_AUX) + (EMPRESA,),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Controle do Sistema gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


async def get_controle_sistema(servidor, banco):
    return await asyncio.to_thread(_get_controle_sistema_sync, servidor, banco)


async def save_controle_sistema(servidor, banco, dados):
    return await asyncio.to_thread(_save_controle_sistema_sync, servidor, banco, dados)


def _save_grupo_sync(servidor: str, banco: str, tabela: str, empresa_col: str, campos: list, text_fields: set, dados: dict) -> dict:
    vals = _coerce_vals(dados, campos, set(), text_fields)
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        set_sql = ", ".join(f"[{c}]=%s" for c in campos)
        cur.execute(
            f"UPDATE {tabela} SET {set_sql} WHERE {empresa_col}=%s",
            tuple(vals[c] for c in campos) + (EMPRESA,),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _save_nf_principal_sync(servidor: str, banco: str, dados: dict) -> dict:
    return _save_grupo_sync(servidor, banco, "controle", "empresa", CAMPOS_NF_PRINCIPAL, _NF_PRINCIPAL_TEXT_FIELDS, dados)


def _save_nfce_numeracao_sync(servidor: str, banco: str, dados: dict) -> dict:
    return _save_grupo_sync(servidor, banco, "controle_aux", "empresa_aux", CAMPOS_NFCE_NUMERACAO, _NFCE_NUMERACAO_TEXT_FIELDS, dados)


def _save_mdfe_numeracao_sync(servidor: str, banco: str, dados: dict) -> dict:
    return _save_grupo_sync(servidor, banco, "controle_aux", "empresa_aux", CAMPOS_MDFE_NUMERACAO, _MDFE_NUMERACAO_TEXT_FIELDS, dados)


async def save_nf_principal(servidor, banco, dados):
    return await asyncio.to_thread(_save_nf_principal_sync, servidor, banco, dados)


async def save_nfce_numeracao(servidor, banco, dados):
    return await asyncio.to_thread(_save_nfce_numeracao_sync, servidor, banco, dados)


async def save_mdfe_numeracao(servidor, banco, dados):
    return await asyncio.to_thread(_save_mdfe_numeracao_sync, servidor, banco, dados)


# =====================================================================
# Grid "Outras Séries NFe" — tabela `controle_nota_fiscal`
# (numero_nf, serie_nf, modelo_nf fixo '18', empresa) — legado: GridNF,
# Command6_Click (Gravar)/Command7_Click (Excluir) na aba Movimentações.
# =====================================================================
def _list_series_nf_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT numero_nf, serie_nf, modelo_nf FROM controle_nota_fiscal "
            "WHERE empresa=%s ORDER BY serie_nf",
            (EMPRESA,),
        )
        items = [{
            "serie_nf": (r.get("serie_nf") or "").strip(),
            "numero_nf": int(r.get("numero_nf") or 0),
            "modelo_nf": int(r.get("modelo_nf") or 0),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_serie_nf_sync(servidor: str, banco: str, serie_nf: str, numero_nf: int) -> dict:
    serie = (serie_nf or "").strip()
    if not serie:
        return {"success": False, "message": "Série é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM controle_nota_fiscal WHERE empresa=%s AND serie_nf=%s",
            (EMPRESA, serie),
        )
        if cur.fetchone():
            cur.execute(
                "UPDATE controle_nota_fiscal SET numero_nf=%s, modelo_nf='18' "
                "WHERE empresa=%s AND serie_nf=%s",
                (numero_nf, EMPRESA, serie),
            )
        else:
            cur.execute(
                "INSERT INTO controle_nota_fiscal (numero_nf, serie_nf, modelo_nf, empresa) "
                "VALUES (%s,%s,'18',%s)",
                (numero_nf, serie, EMPRESA),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Série gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_serie_nf_sync(servidor: str, banco: str, serie_nf: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "DELETE FROM controle_nota_fiscal WHERE empresa=%s AND serie_nf=%s",
            (EMPRESA, serie_nf),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Série não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Série excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_series_nf(servidor, banco):
    return await asyncio.to_thread(_list_series_nf_sync, servidor, banco)


async def save_serie_nf(servidor, banco, serie_nf, numero_nf):
    return await asyncio.to_thread(_save_serie_nf_sync, servidor, banco, serie_nf, numero_nf)


async def delete_serie_nf(servidor, banco, serie_nf):
    return await asyncio.to_thread(_delete_serie_nf_sync, servidor, banco, serie_nf)


# =====================================================================
# Grid "Turno" (dentro de "Configurações Posto") — tabela `controle_turno_horario`
# (turno PK, hora_inicio, hora_fim). Legado calcula hora_inicio = hora_fim - 15min
# a partir só do campo "Turno"+hora exibido (Command4_Click/Command5_Click).
# =====================================================================
def _hora_menos_15(hora_fim: str) -> str:
    try:
        h, m = (int(p) for p in hora_fim.split(":")[:2])
        total = (h * 60 + m - 15) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}:00"
    except Exception:
        return hora_fim


def _list_turno_horario_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT turno, hora_inicio, hora_fim FROM controle_turno_horario ORDER BY turno")
        items = [{
            "turno": int(r.get("turno") or 0),
            "hora_inicio": (r.get("hora_inicio") or "").strip(),
            "hora_fim": (r.get("hora_fim") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_turno_horario_sync(servidor: str, banco: str, turno: int, hora_fim: str) -> dict:
    hf = (hora_fim or "").strip()
    if not hf:
        return {"success": False, "message": "Hora é obrigatória."}
    hi = _hora_menos_15(hf)
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM controle_turno_horario WHERE turno=%s", (turno,))
        if cur.fetchone():
            cur.execute(
                "UPDATE controle_turno_horario SET hora_inicio=%s, hora_fim=%s WHERE turno=%s",
                (hi, hf, turno),
            )
        else:
            cur.execute(
                "INSERT INTO controle_turno_horario (turno, hora_inicio, hora_fim) VALUES (%s,%s,%s)",
                (turno, hi, hf),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Turno gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_turno_horario_sync(servidor: str, banco: str, turno: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM controle_turno_horario WHERE turno=%s", (turno,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Turno não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Turno excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_turno_horario(servidor, banco):
    return await asyncio.to_thread(_list_turno_horario_sync, servidor, banco)


async def save_turno_horario(servidor, banco, turno, hora_fim):
    return await asyncio.to_thread(_save_turno_horario_sync, servidor, banco, turno, hora_fim)


async def delete_turno_horario(servidor, banco, turno):
    return await asyncio.to_thread(_delete_turno_horario_sync, servidor, banco, turno)


# =====================================================================
# Modal "NFe de Simples Remessa dos DAV's" (aba Outros, botão próprio) —
# tabela `simples_remessa_config`. Legado: `Form8`/`FrmConNDV.frm`
# ("NFe de Simples Remessa dos DAV's"), único formulário — Gravar sempre
# apaga TODAS as linhas e regrava (config única, não por tipo_mov — o
# `Command1_Click` do legado faz `DELETE FROM simples_remessa_config`
# incondicional, sem WHERE). "Dentro do Estado" = linhas com destino igual à
# UF cadastrada da empresa (`controle.uf`); "Fora do Estado" = destino fixo
# 'XX' — até 4 linhas (Cfop+Cod Icms) em cada grupo.
# =====================================================================
def _list_simples_remessa_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 uf FROM controle WHERE empresa=%s", (EMPRESA,))
        uf = ((cur.fetchone() or {}).get("uf") or "").strip()
        cur.execute(
            "SELECT tipo_mov, destino, cfop, cod_icms FROM simples_remessa_config "
            "ORDER BY SEQUENCIA_SIMPLES_REMESSA_CONFIG"
        )
        rows = cur.fetchall()
        cur.close()
        tipo_mov = (rows[0].get("tipo_mov") or "").strip() if rows else ""
        dentro = [{"cfop": (r.get("cfop") or "").strip(), "cod_icms": (r.get("cod_icms") or "").strip()} for r in rows if (r.get("destino") or "").strip() == uf]
        fora = [{"cfop": (r.get("cfop") or "").strip(), "cod_icms": (r.get("cod_icms") or "").strip()} for r in rows if (r.get("destino") or "").strip() == "XX"]
        return {"success": True, "tipo_mov": tipo_mov, "uf": uf, "dentro": dentro, "fora": fora}
    finally:
        conn.close()


def _save_simples_remessa_sync(servidor: str, banco: str, tipo_mov: str, dentro: list, fora: list) -> dict:
    tm = (tipo_mov or "").strip()
    if not tm:
        return {"success": False, "message": "Selecione o Tipo de Movimentação."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 uf FROM controle WHERE empresa=%s", (EMPRESA,))
        uf = ((cur.fetchone() or {}).get("uf") or "").strip()
        cur.execute("DELETE FROM simples_remessa_config")
        for item in (dentro or [])[:4]:
            cfop = (item.get("cfop") or "").strip()
            cod_icms = (item.get("cod_icms") or "").strip()
            if cfop and cod_icms:
                cur.execute(
                    "INSERT INTO simples_remessa_config (tipo_mov, destino, cfop, cod_icms) VALUES (%s,%s,%s,%s)",
                    (tm, uf, cfop, cod_icms),
                )
        for item in (fora or [])[:4]:
            cfop = (item.get("cfop") or "").strip()
            cod_icms = (item.get("cod_icms") or "").strip()
            if cfop and cod_icms:
                cur.execute(
                    "INSERT INTO simples_remessa_config (tipo_mov, destino, cfop, cod_icms) VALUES (%s,'XX',%s,%s)",
                    (tm, cfop, cod_icms),
                )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Configuração de Simples Remessa gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


async def get_simples_remessa(servidor, banco):
    return await asyncio.to_thread(_list_simples_remessa_sync, servidor, banco)


async def save_simples_remessa(servidor, banco, tipo_mov, dentro, fora):
    return await asyncio.to_thread(_save_simples_remessa_sync, servidor, banco, tipo_mov, dentro, fora)


# =====================================================================
# Modal "Direcionamento de Impressão por Grupo" (aba Outros, botão próprio) —
# tabela `direcionamento_impressora` (codigo PK, computador+tipo chave de
# negócio). Legado: `FrmCadImp.frm`. `Impressora` no legado é populada a
# partir de `Printers()` (API do Windows local à máquina rodando o VB6) —
# não tem como enumerar impressoras instaladas a partir de um browser web
# (limitação de plataforma, não de escopo) — vira campo de texto livre aqui.
# Mesma coisa pro nome do computador: sem hostname confiável disponível no
# browser, o usuário digita.
# =====================================================================
def _list_direcionamento_impressora_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, computador, impressora, tipo, automatica FROM direcionamento_impressora "
            "ORDER BY computador, tipo"
        )
        items = [{
            "codigo": int(r["codigo"]),
            "computador": (r.get("computador") or "").strip(),
            "impressora": (r.get("impressora") or "").strip(),
            "tipo": int(r.get("tipo")) if r.get("tipo") is not None else None,
            "automatica": bool(r.get("automatica")),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_direcionamento_impressora_sync(servidor: str, banco: str, computador: str, tipo: int, impressora: str, automatica: bool) -> dict:
    comp = (computador or "").strip()
    imp = (impressora or "").strip()
    if not comp:
        return {"success": False, "message": "Informe o nome do computador."}
    if tipo is None:
        return {"success": False, "message": "Defina o Tipo!"}
    if not imp:
        return {"success": False, "message": "Defina a Impressora!"}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM direcionamento_impressora WHERE computador=%s AND tipo=%s", (comp, tipo))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE direcionamento_impressora SET impressora=%s, automatica=%s WHERE codigo=%s",
                (imp, 1 if automatica else 0, existing["codigo"]),
            )
        else:
            cur.execute(
                "INSERT INTO direcionamento_impressora (computador, impressora, tipo, automatica) VALUES (%s,%s,%s,%s)",
                (comp, imp, tipo, 1 if automatica else 0),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_direcionamento_impressora_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM direcionamento_impressora WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Registro não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_direcionamento_impressora(servidor, banco):
    return await asyncio.to_thread(_list_direcionamento_impressora_sync, servidor, banco)


async def save_direcionamento_impressora(servidor, banco, computador, tipo, impressora, automatica):
    return await asyncio.to_thread(_save_direcionamento_impressora_sync, servidor, banco, computador, tipo, impressora, automatica)


async def delete_direcionamento_impressora(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_direcionamento_impressora_sync, servidor, banco, codigo)

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "expo-router";

import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";

// Controle do Sistema (Configurações > Geral) — tabelas `controle`/`controle_aux`
// (linha única, mono-empresa por ora). Legado: FrmGerCon.frm ("Dados para
// controle"), ver "Legacy VB6 Source Reference" no CLAUDE.md. Mapeamento
// campo→coluna documentado em `backend/services/controle_sistema_service.py`
// (CAMPOS_CONTROLE/CAMPOS_CONTROLE_AUX) — este hook espelha as mesmas 4 listas
// de classificação de tipo (bool/texto/data/numérico) do lado do backend, pra
// montar/ler o payload do form corretamente.

export type Conn = { servidor: string; banco: string; api: string };
export type LookupItem = { codigo: string; descricao: string };
export type SubClasseItem = { codigo: number; classe: number; descricao: string; tipo: string; ativa: boolean };
export type ClasseItem = { codigo: number; descricao: string; tipo: string; sub_classes: SubClasseItem[] };

export type SerieNfItem = { serie_nf: string; numero_nf: number; modelo_nf: number };
export type TurnoHorarioItem = { turno: number; hora_inicio: string; hora_fim: string };
export type CertificadoItem = {
  sequencia: number; data_inicio: string | null; data_fim: string | null;
  tipo_certificado: string | null; numero_serial: string | null; cnpj_certificado: string | null;
};
export type CfopIcmsPar = { cfop: string; cod_icms: string };
export type DirecionamentoImpressoraItem = {
  codigo: number; computador: string; impressora: string; tipo: number | null; automatica: boolean;
};

const BOOL_FIELDS = [
  "ALERTA_ESTOQUE", "ALERTA_ESTOQUE_MINIMO", "ALERTA_ESTOQUE_NEGATIVO", "ALERTA_ESTOQUE_RESSUPRIMENTO",
  "ALERTA_ESTOQUE_ZERADO", "AgrupaComandas_Cx", "Altera_preco_venda_tela", "CEP_CORREIOS", "CEP_GUIACEP",
  "ControlaRevisaoOS", "DEVOLUCAO_CANCELA_NFE_ORIGINAL", "Destaca_Desconto_Cedido", "EXIGE_KM_OS",
  "EXIGE_OS_ORIGINAL_GARANTIA", "EXIGE_referencia_OS", "Exclui_Recebimento_Automatico",
  "Habilita_Preco_Tabela_Pedido", "IMPRIME_VENDEDOR_DANFE_NFCE", "ISS_Retido", "Inclui_Classe_Caixa_Mov",
  "Inclui_Dados_Faturar_Para", "Inclui_Endereco_Cobranca_Obs_Nfe", "Inclui_Endereco_Entrega_Obs_Nfe",
  "Permite_venda_combustiveis", "Pesquisa_Satisfacao_BTEN", "Senha_Gerente", "TROCO_CARTAO",
  "Transf_Caixa_Contabil", "bloqueia_venda_cliente_com_debito", "cancelamento_paf_exige_senha",
  "emite_nf_comanda", "emite_vale_troca", "exige_aprovacao_itens_os", "exige_expedicao_itens_os",
  "fatura_os_contrato", "fecha_pedido_automaticamente", "imprime_dados_os_danfe", "incentivo_cultural",
  "indicador_intermediario", "m2_area_minima_comum_lapidacao", "m2_area_minima_comum_sem_lapidacao",
  "m2_area_minima_engenharia", "m2_area_minima_modelado", "m2_area_minima_modelado_engenharia",
  "m2_area_minima_padrao", "nome_fantasia_cabecalho_dav", "opcao_simples", "paga_comissao_venda_garantia",
  "preco_cld", "registra_venda_automatica", "senha_gerente_cx", "ssl_COBRANCA", "ssl_contrato", "ssl_rel",
  "transf_ent_sai_caixa", "vidro_controla_cabeca_chapa",
  "integracao_tray",
  // Kontacto (só Master) — TICKET_PIX não existe nesta base, descartado.
  "exige_cpf_cliente", "aceita_duplicar_cnpj", "inc_prod_os",
  "consulta_por_descricao_paf", "imprime_nfse",
  "PERGUNTA_EMITE_NFCE", "USA_PRECO_BASE_NFCE", "IMPRIME_NFCE_NAO_FISCAL", "ESCOLHE_NFE_NFCE",
] as const;

const TEXT_FIELDS = [
  "CELULAR", "CEP_CONTRATO", "CEP_SENHA", "CEP_URL_CEP", "CEP_URL_LOGRADOURO", "CEP_URL_TOKEN", "CEP_USUARIO",
  "EMAIL_ALERTA_ESTOQUE", "MENSAGEM_OS", "MENSAGEM_obs_OS", "Msg_Padrao_Boleto_1", "Msg_Padrao_Boleto_2",
  "Msg_Padrao_Boleto_3", "NaturezaOperacao", "PRODUTO_ORCAMENTO", "RegimeEspecialTributacao",
  "SERVICO_FRETE_NFCE", "VersaoQrCodeNFCe", "bairro", "cep", "cgc", "cidade", "cnae_fiscal_principal",
  "cnae_fiscal_servico", "cod_rel", "cod_servico_contrato", "codigo", "codigo_nbs", "complemento", "csc",
  "csc_hash", "cst_pis_cofins_dps", "desmembramento_dup", "e_mail", "e_mail_COBRANCA", "e_mail_contrato",
  "e_mail_rel", "endereco", "fantasia", "forma_pag_contrato", "ident_COBRANCA", "ident_contrato",
  "identificacao_remetente_contrato", "inscr_est", "inscr_municipal", "login_COBRANCA", "login_contrato",
  "login_rel", "msg_vale_troca_1", "msg_vale_troca_2", "nire", "numero_anp", "porta_concentrador",
  "retencao_pis_cofins_dps", "rz_social", "senha_COBRANCA", "senha_contrato", "senha_rel", "serie_DPS",
  "serie_rps", "smtp_COBRANCA",
  "smtp_contrato", "smtp_rel", "suframa", "telefone", "tipo_mov_contrato_peca", "tipo_mov_contrato_servico",
  "tipo_mov_garantia", "token_Authorization_pesquisa_satisfacao", "token_business_pesquisa_satisfacao", "uf",
  "versao_layout_nfce", "versao_nfe",
  // Kontacto (só Master)
  "codigo_kontacto", "situacao",
  "path_padrao_xml", "Path_importacao_venda_externa", "Path_backup_sql", "path_gestor_documentos",
  "PATH_LOGO_EMAIL_COBRANCA", "TEXTO_CORPO_EMAIL_COBRANCA",
  "TRAY_ID_LOJA", "TRAY_url_api", "TRAY_Consumer_Key", "TRAY_Consumer_Secret", "TRAY_code",
] as const;

const DATE_FIELDS = ["data_abertura", "data_movimento", "data_inicio_nfe", "data_inicio_nfse", "data_inicio_paf"] as const;

// Somente-leitura (nunca gravado) — "controle" é a licença criptografada da
// instalação, `Enabled=0` no legado. Entra no form só pra exibição.
const READONLY_TEXT = ["controle"] as const;

const NUM_FIELDS = [
  "COD_CLIENTE_ORCAMENTO", "Cofins", "Dias_Ver_Cx", "Minimo_Boleto", "Mora_Dia_Pag", "Multa_Atraso_Pag",
  "PROTOCOLO_TLS_NFSE", "QTD_ABASTECIMENTOS_NFCE", "Regime_Trib", "Simples_Servico", "TRANSPORTADOR_FRETE_NFCE",
  "Tarifa_Boleto", "ano_recibo", "classe_ent_descontos", "classe_ent_juros", "classe_ent_tarifa",
  "classe_sai_descontos", "classe_sai_juros", "classe_sai_tarifa", "cod_peca", "conta_transf_caixa", "ddd",
  "desconto_PDV", "desconto_PDV_Gerente", "desconto_PDV_Supervisor", "desconto_PDV_Vendedor", "dias_alt_cx",
  "dias_protesto", "dias_troca", "id_fusion", "informa_codigo_barras", "iss", "margem_nf",
  "metro_quadrado_minima_metragem", "modelo_concentrador", "modelo_danfe_nfce",
  "modelo_os", "modelo_pedido", "modelo_pedido_compra", "modelo_recibo", "numero", "numero_DPS",
  "numero_dup", "numero_os", "numero_rps",
  "pagina_lmc", "perc_tributos_estaduais_dps", "perc_tributos_federais_dps", "perc_tributos_municipais_dps",
  "percent_troca", "pis", "porta_smtp_COBRANCA", "porta_smtp_contrato", "porta_smtp_rel", "protocolo_tls_email",
  "qtdturnos", "seq_recibo", "sub_classe_ent_descontos", "sub_classe_ent_juros", "sub_classe_ent_tarifa",
  "sub_classe_sai_descontos", "sub_classe_sai_juros", "sub_classe_sai_tarifa", "tipo_comunicacao_concentrador",
  "tipo_controle", "validade_vale_troca",
] as const;

// Campos com botão + log próprios (fora do Gravar genérico) — achado do
// usuário direto na tela legada: o botão "Gravar" principal não grava esses
// campos de numeração, que têm botões dedicados ("Gravar Alterações
// NFE"/"NFCE"/"MDF-e") e log com descrição específica (não diff genérico).
// Entram no form pra exibição (o GET já retorna), mas ficam fora de
// NUM_FIELDS/TEXT_FIELDS (usadas só pelo payload do Gravar geral).
const NF_PRINCIPAL_TEXT = ["serie_nf", "serie_nf_ent", "serie_nf_ser"] as const;
const NF_PRINCIPAL_NUM = ["numero_nf", "modelo_nf", "numero_nf_ent", "modelo_nf_ent", "numero_nf_ser"] as const;
const NFCE_NUMERACAO_TEXT = ["serie_nfce"] as const;
const NFCE_NUMERACAO_NUM = ["numero_nfce"] as const;
const MDFE_NUMERACAO_TEXT = ["serie_MDFE"] as const;
const MDFE_NUMERACAO_NUM = ["numero_MDFE"] as const;

export type ControleForm = Record<string, string | boolean>;

const NF_GROUP_TEXT = [...NF_PRINCIPAL_TEXT, ...NFCE_NUMERACAO_TEXT, ...MDFE_NUMERACAO_TEXT];
const NF_GROUP_NUM = [...NF_PRINCIPAL_NUM, ...NFCE_NUMERACAO_NUM, ...MDFE_NUMERACAO_NUM];

export const emptyControleForm = (): ControleForm => {
  const f: ControleForm = {};
  for (const k of BOOL_FIELDS) f[k] = false;
  for (const k of TEXT_FIELDS) f[k] = "";
  for (const k of DATE_FIELDS) f[k] = "";
  for (const k of NUM_FIELDS) f[k] = "";
  for (const k of NF_GROUP_TEXT) f[k] = "";
  for (const k of NF_GROUP_NUM) f[k] = "";
  for (const k of READONLY_TEXT) f[k] = "";
  return f;
};

export const toFloat = (s: string | boolean): number => {
  const v = parseFloat(String(s ?? "0").replace(",", "."));
  return Number.isFinite(v) ? v : 0;
};

export function useControleSistemaForm() {
  const router = useRouter();
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingInit, setLoadingInit] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<ControleForm>(emptyControleForm());

  const [tipoMovOptions, setTipoMovOptions] = useState<LookupItem[]>([]);
  const [formaPagamentoOptions, setFormaPagamentoOptions] = useState<LookupItem[]>([]);
  const [contasOptions, setContasOptions] = useState<LookupItem[]>([]);
  const [tipoPecaOptions, setTipoPecaOptions] = useState<LookupItem[]>([]);
  const [planoContas, setPlanoContas] = useState<ClasseItem[]>([]);

  const [seriesNf, setSeriesNf] = useState<SerieNfItem[]>([]);
  const [turnoHorario, setTurnoHorario] = useState<TurnoHorarioItem[]>([]);
  const [certificados, setCertificados] = useState<CertificadoItem[]>([]);
  const [direcionamentoImpressora, setDirecionamentoImpressora] = useState<DirecionamentoImpressoraItem[]>([]);
  const [simplesRemessa, setSimplesRemessa] = useState<{ tipo_mov: string; uf: string; dentro: CfopIcmsPar[]; fora: CfopIcmsPar[] }>({ tipo_mov: "", uf: "", dentro: [], fora: [] });

  const connRef = useRef<Conn | null>(null);

  const setField = (k: string, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  const base = conn ? conn.api.replace(/\/+$/, "") : "";
  const qsBase = conn ? `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}` : "";

  const applyDados = (d: Record<string, unknown>) => {
    const f = emptyControleForm();
    for (const k of BOOL_FIELDS) f[k] = !!d[k];
    for (const k of TEXT_FIELDS) f[k] = (d[k] as string) || "";
    for (const k of DATE_FIELDS) f[k] = (d[k] as string) || "";
    for (const k of NUM_FIELDS) f[k] = String(d[k] ?? 0);
    for (const k of NF_GROUP_TEXT) f[k] = (d[k] as string) || "";
    for (const k of NF_GROUP_NUM) f[k] = String(d[k] ?? 0);
    for (const k of READONLY_TEXT) f[k] = (d[k] as string) || "";
    setForm(f);
  };

  const loadDados = useCallback(async (c: Conn) => {
    const b = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    const r = await fetch(`${b}/api/controle-sistema?${qs}`);
    const j = await r.json();
    if (j?.success) applyDados(j.dados || {});
    return j;
  }, []);

  const loadGrids = useCallback(async (c: Conn) => {
    const b = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    const [rSeries, rTurno, rCert, rImpr, rRemessa] = await Promise.all([
      fetch(`${b}/api/controle-sistema/series-nf?${qs}`).then((r) => r.json()).catch(() => null),
      fetch(`${b}/api/controle-sistema/turno-horario?${qs}`).then((r) => r.json()).catch(() => null),
      fetch(`${b}/api/controle-sistema/certificados?${qs}`).then((r) => r.json()).catch(() => null),
      fetch(`${b}/api/controle-sistema/direcionamento-impressora?${qs}`).then((r) => r.json()).catch(() => null),
      fetch(`${b}/api/controle-sistema/simples-remessa?${qs}`).then((r) => r.json()).catch(() => null),
    ]);
    if (rSeries?.success) setSeriesNf(rSeries.items || []);
    if (rTurno?.success) setTurnoHorario(rTurno.items || []);
    if (rCert?.success) setCertificados(rCert.items || []);
    if (rImpr?.success) setDirecionamentoImpressora(rImpr.items || []);
    if (rRemessa?.success) setSimplesRemessa({ tipo_mov: rRemessa.tipo_mov || "", uf: rRemessa.uf || "", dentro: rRemessa.dentro || [], fora: rRemessa.fora || [] });
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    const b = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    const fetchLookup = async (path: string, setter: (items: LookupItem[]) => void) => {
      try {
        const r = await fetch(`${b}${path}?${qs}`);
        const j = await r.json();
        if (j?.success && Array.isArray(j.items)) setter(j.items);
      } catch { /* silencioso — lookup opcional */ }
    };
    await Promise.all([
      fetchLookup("/api/tipo-mov", setTipoMovOptions),
      fetchLookup("/api/forma-pagamento", setFormaPagamentoOptions),
      fetchLookup("/api/contas", setContasOptions),
      fetchLookup("/api/tipo-peca", setTipoPecaOptions),
      (async () => {
        try {
          const r = await fetch(`${b}/api/financeiro/plano-contas?${qs}`);
          const j = await r.json();
          if (j?.success && Array.isArray(j.items)) setPlanoContas(j.items);
        } catch { /* silencioso */ }
      })(),
    ]);
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) { setLoadingInit(false); return; }
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      connRef.current = cc;
      await Promise.all([loadDados(cc), loadGrids(cc), loadLookups(cc)]);
      setLoadingInit(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, loadDados, loadGrids, loadLookups]);

  const reloadGrids = useCallback(async () => {
    if (connRef.current) await loadGrids(connRef.current);
  }, [loadGrids]);

  const save = async () => {
    if (!conn) return false;
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      for (const k of BOOL_FIELDS) payload[k] = !!form[k];
      for (const k of TEXT_FIELDS) payload[k] = form[k] || null;
      for (const k of DATE_FIELDS) payload[k] = form[k] || null;
      for (const k of NUM_FIELDS) payload[k] = toFloat(form[k]);

      const r = await fetch(`${base}/api/controle-sistema`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, dados: payload }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Controle do Sistema gravado.");
        return true;
      }
      fb.showError(j?.message || "Falha ao gravar.");
      return false;
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      return false;
    } finally {
      setSaving(false);
    }
  };

  // ---- Numeração NF / NFCe / MDF-e (botão e log próprios, fora do Gravar geral) ----
  const saveGrupo = async (path: string, campos: readonly string[], mensagemPadrao: string) => {
    if (!conn) return false;
    try {
      const dados: Record<string, unknown> = {};
      for (const k of campos) {
        dados[k] = (NF_PRINCIPAL_NUM as readonly string[]).includes(k)
          || (NFCE_NUMERACAO_NUM as readonly string[]).includes(k)
          || (MDFE_NUMERACAO_NUM as readonly string[]).includes(k)
          ? toFloat(form[k]) : (form[k] || null);
      }
      const r = await fetch(`${base}/api/controle-sistema/${path}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, dados }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || mensagemPadrao); return true; }
      fb.showError(j?.message || "Falha ao gravar."); return false;
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); return false; }
  };
  const saveNfPrincipal = () => saveGrupo("nf-principal", [...NF_PRINCIPAL_TEXT, ...NF_PRINCIPAL_NUM], "Numeração de NF gravada.");
  const saveNfceNumeracao = () => saveGrupo("nfce-numeracao", [...NFCE_NUMERACAO_TEXT, ...NFCE_NUMERACAO_NUM], "Numeração de NFCe gravada.");
  const saveMdfeNumeracao = () => saveGrupo("mdfe-numeracao", [...MDFE_NUMERACAO_TEXT, ...MDFE_NUMERACAO_NUM], "Numeração de MDF-e gravada.");

  // ---- Grid: Outras Séries NFe ----
  const saveSerieNf = async (serie_nf: string, numero_nf: number) => {
    if (!conn) return false;
    try {
      const r = await fetch(`${base}/api/controle-sistema/series-nf`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, serie_nf, numero_nf }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Série gravada."); await reloadGrids(); return true; }
      fb.showError(j?.message || "Falha ao gravar."); return false;
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); return false; }
  };
  const deleteSerieNf = async (serie_nf: string) => {
    if (!conn) return;
    try {
      const r = await fetch(`${base}/api/controle-sistema/series-nf/${encodeURIComponent(serie_nf)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Excluído."); await reloadGrids(); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  // ---- Grid: Turno (Configurações Posto) ----
  const saveTurnoHorario = async (turno: number, hora_fim: string) => {
    if (!conn) return false;
    try {
      const r = await fetch(`${base}/api/controle-sistema/turno-horario`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, turno, hora_fim }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Turno gravado."); await reloadGrids(); return true; }
      fb.showError(j?.message || "Falha ao gravar."); return false;
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); return false; }
  };
  const deleteTurnoHorario = async (turno: number) => {
    if (!conn) return;
    try {
      const r = await fetch(`${base}/api/controle-sistema/turno-horario/${turno}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Excluído."); await reloadGrids(); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  // ---- Certificado Digital ----
  const uploadCertificado = async (arquivo: File | Blob, nomeArquivo: string, senha: string, tipoCertificado: string) => {
    if (!conn) return false;
    try {
      const fd = new FormData();
      fd.append("servidor", conn.servidor);
      fd.append("banco", conn.banco);
      fd.append("senha", senha);
      fd.append("tipo_certificado", tipoCertificado);
      if (auditCtx.usuario_alteracao != null) fd.append("usuario_alteracao", String(auditCtx.usuario_alteracao));
      if (auditCtx.classe != null) fd.append("classe", String(auditCtx.classe));
      fd.append("plataforma", auditCtx.plataforma);
      fd.append("arquivo", arquivo, nomeArquivo);
      const r = await fetch(`${base}/api/controle-sistema/certificados`, { method: "POST", body: fd });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Certificado cadastrado."); await reloadGrids(); return true; }
      fb.showError(j?.message || "Falha ao cadastrar certificado."); return false;
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); return false; }
  };
  const deleteCertificado = async (sequencia: number) => {
    if (!conn) return;
    try {
      const r = await fetch(`${base}/api/controle-sistema/certificados/${sequencia}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Excluído."); await reloadGrids(); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  // ---- Modal: Direcionamento de Impressão por Grupo ----
  const saveDirecionamentoImpressora = async (computador: string, tipo: number, impressora: string, automatica: boolean) => {
    if (!conn) return false;
    try {
      const r = await fetch(`${base}/api/controle-sistema/direcionamento-impressora`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, computador, tipo, impressora, automatica }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Gravado."); await reloadGrids(); return true; }
      fb.showError(j?.message || "Falha ao gravar."); return false;
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); return false; }
  };
  const deleteDirecionamentoImpressora = async (codigo: number) => {
    if (!conn) return;
    try {
      const r = await fetch(`${base}/api/controle-sistema/direcionamento-impressora/${codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Excluído."); await reloadGrids(); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  // ---- Modal: NFe de Simples Remessa dos DAV's ----
  const saveSimplesRemessa = async (tipo_mov: string, dentro: CfopIcmsPar[], fora: CfopIcmsPar[]) => {
    if (!conn) return false;
    try {
      const r = await fetch(`${base}/api/controle-sistema/simples-remessa`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, tipo_mov, dentro, fora }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Gravado."); await reloadGrids(); return true; }
      fb.showError(j?.message || "Falha ao gravar."); return false;
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); return false; }
  };

  return {
    conn, loadingInit, saving, form, setField, save,
    saveNfPrincipal, saveNfceNumeracao, saveMdfeNumeracao,
    tipoMovOptions, formaPagamentoOptions, contasOptions, tipoPecaOptions, planoContas,
    seriesNf, turnoHorario, certificados, direcionamentoImpressora, simplesRemessa,
    saveSerieNf, deleteSerieNf, saveTurnoHorario, deleteTurnoHorario,
    uploadCertificado, deleteCertificado,
    saveDirecionamentoImpressora, deleteDirecionamentoImpressora, saveSimplesRemessa,
  };
}

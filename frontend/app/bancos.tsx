import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { apiBase, apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import {
  LOGO_ALTURA_MINIMA, LOGO_LARGURA_MINIMA, LOGO_ORIENTACAO_TEXTO, LOGO_TAMANHO_MAXIMO_BYTES, lerResolucaoImagem,
} from "@/src/utils/imageResolution";

const isWeb = Platform.OS === "web";

type BancoListItem = {
  cod: number; codigo: number; descricao: string; agencia: number;
  conta_corrente: number; carteira: number; situacao: string; integracao_api: boolean;
};

// Estado do formulário — tudo string (mesmo padrão de fornecedores.tsx,
// num()/int_() convertem na gravação), num objeto único em vez de ~40
// useState soltos (única diferença de padrão em relação a fornecedores.tsx,
// justificada pelo volume real de campos desta tela).
type BancoForm = {
  codigo: string; digitoBanco: string; descricao: string; descrArquivo: string;
  agencia: string; dvAgencia: string; contaCorrente: string; dvContaCorrente: string; dvAgenciaConta: string;
  situacao: string;
  carteira: string; variacaoCarteira: string; codigoCedente: string; codTransmissao: string; contrato: string;
  especieDoc: string; aceite: string;
  tarifaCobranca: string; incidenciaMulta: string; diasMulta: string; tipoMulta: string;
  multaAtrasoPag: string; moraDiaPag: string; diasProtesto: string; codigoProtesto: string;
  diasBaixa: string; codigoBaixa: string;
  tipoCobranca: string; tipoRegistro: string; emissaoBoleto: string; distribuiBoleto: string;
  numeroBoleto: string; instrCobranca1: string; instrCobranca2: string;
  tituloBoleto: string; mensagemBoleto1: string; mensagemBoleto2: string; mensagemBoleto3: string;
  enderecoRemessa: string; enderecoRetorno: string;
  integracaoApi: boolean; chaveApi1: string; chaveApi2: string; chaveApi3: string; chaveApi4: string;
};

const FORM_VAZIO: BancoForm = {
  codigo: "", digitoBanco: "", descricao: "", descrArquivo: "",
  agencia: "", dvAgencia: "", contaCorrente: "", dvContaCorrente: "", dvAgenciaConta: "",
  situacao: "A",
  carteira: "", variacaoCarteira: "", codigoCedente: "", codTransmissao: "", contrato: "",
  especieDoc: "", aceite: "N",
  tarifaCobranca: "", incidenciaMulta: "", diasMulta: "", tipoMulta: "",
  multaAtrasoPag: "", moraDiaPag: "", diasProtesto: "", codigoProtesto: "",
  diasBaixa: "", codigoBaixa: "",
  tipoCobranca: "", tipoRegistro: "", emissaoBoleto: "", distribuiBoleto: "",
  numeroBoleto: "", instrCobranca1: "", instrCobranca2: "",
  tituloBoleto: "", mensagemBoleto1: "", mensagemBoleto2: "", mensagemBoleto3: "",
  enderecoRemessa: "", enderecoRetorno: "",
  integracaoApi: false, chaveApi1: "", chaveApi2: "", chaveApi3: "", chaveApi4: "",
};

const num = (s: string): number => (s.trim() ? parseFloat(s.replace(",", ".")) || 0 : 0);
const int_ = (s: string): number => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || 0 : 0);

const AJUDA_ITENS: { titulo: string; texto: string }[] = [
  { titulo: "Integração por API", texto: "Ligado: o banco é integrado por API (credenciais Chave/Token 1-4), sem gerar arquivo de remessa/retorno. Desligado: usa o modelo tradicional de arquivo CNAB (diretórios de Remessa/Retorno). Nenhum dos dois motores de emissão está implementado ainda nesta fase — este cadastro só guarda os parâmetros." },
  { titulo: "Carteira / Variação de Carteira / Código Cedente", texto: "Identificam, junto com Agência e Conta, o contrato de cobrança que o banco reconhece — confira esses números no contrato de cobrança assinado com o banco, não invente um valor." },
  { titulo: "Código Protesto / Código Baixa / Tipo Cobrança / Tipo Registro / Tipo Multa / Emissão de Boleto / Distribuição de Boleto / Espécie do Documento", texto: "Códigos numéricos definidos pelo próprio banco (tabela específica de cada convênio) — este cadastro não conhece a lista de opções de cada banco ainda, então esses campos aceitam o código numérico direto. Consulte o manual de instruções de cobrança do banco para o valor certo." },
  { titulo: "Dias p/ Protestar e Dias p/ Baixa", texto: "0 = confirmar instrução na agência; 99 = não protestar/baixar automaticamente; de 2 a 55 = quantidade de dias corridos." },
  { titulo: "Multa / Mora", texto: "Percentual ou valor fixo cobrado do cliente em atraso — a Incidência/Tipo Multa decide se o percentual informado é aplicado (consulte o manual do banco)." },
  { titulo: "Nº do Boleto e Nº da Última Remessa", texto: "\"Nº do Boleto\" é o próximo número sequencial (\"nosso número\") a usar; \"Nº/Data da Última Remessa\" é só informativo, atualizado automaticamente quando o motor de remessa for implementado — não editável aqui." },
];

function AjudaBancosModal({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  return (
    <AppModal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.helpBg} onPress={onClose}>
        <Pressable style={styles.helpCard} onPress={(e) => e.stopPropagation()}>
          <View style={styles.helpHeader}>
            <Text style={styles.helpTitle}>Ajuda — Cadastro de Bancos</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <ScrollView style={{ maxHeight: 440 }}>
            {AJUDA_ITENS.map((it, idx) => (
              <View key={idx} style={styles.helpItem}>
                <Text style={styles.helpItemTitulo}>{it.titulo}</Text>
                <Text style={styles.helpItemTexto}>{it.texto}</Text>
              </View>
            ))}
          </ScrollView>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// Financeiro > Cobranças — cadastro de Bancos (Fase 1: cadastro; motor de
// emissão CNAB/API real fica pra Fase 2, ver PENDENCIAS.md > "Bancos
// (Cadastro de Cobrança / Boleto / CNAB)"). Legado: FrmManBan.frm
// ("Manutenção de Bancos para Cobrança"). Tela compacta sem abas — mesmo
// padrão de fornecedores.tsx (o legado também não tem controle de aba).
export default function BancosScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Cobranças está disponível apenas no web."
        testID="bancos-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [items, setItems] = useState<BancoListItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [editingCod, setEditingCod] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  // Logo do Banco (`bancos.logo_banco`, VARBINARY) — 2026-08-26, pro
  // layout do Boleto em PDF. Mesmo padrão de gravação direto no banco já
  // decidido pra Logo da Empresa (não Azure Blob).
  const [logoBase64, setLogoBase64] = useState<string | null>(null);
  const [logoMime, setLogoMime] = useState<string | null>(null);
  const [logoArquivo, setLogoArquivo] = useState<File | null>(null);
  const [logoSaving, setLogoSaving] = useState(false);

  // Fase 2a — motor CNAB, Bradesco (237) e Inter (077) nesta rodada. Ver
  // PENDENCIAS.md > "Bancos (Cadastro de Cobrança / Boleto / CNAB)".
  const [remessaSaving, setRemessaSaving] = useState(false);
  const [retornoOpen, setRetornoOpen] = useState(false);
  const [retornoTexto, setRetornoTexto] = useState("");
  const [retornoSaving, setRetornoSaving] = useState(false);
  const [retornoResultado, setRetornoResultado] = useState<string | null>(null);

  const [form, setForm] = useState<BancoForm>(FORM_VAZIO);
  const setField = <K extends keyof BancoForm>(key: K, value: BancoForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const load = useCallback(async (c: Connection) => {
    setLoading(true);
    try {
      const j = await apiGet(c, "/api/bancos", { busca: search });
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, [search]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      load(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (conn) load(conn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const openNew = () => {
    setEditingCod(null);
    setForm(FORM_VAZIO);
    setLogoBase64(null);
    setLogoMime(null);
    setFormOpen(true);
  };

  const openEdit = async (item: BancoListItem) => {
    if (!conn) return;
    setEditingCod(item.cod);
    setFormOpen(true);
    try {
      const j = await apiGet(conn, `/api/bancos/${item.cod}`);
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      const d = j;
      setForm({
        codigo: String(d.codigo ?? ""), digitoBanco: String(d.digito_banco ?? ""),
        descricao: d.descricao || "", descrArquivo: d.descr_arquivo || "",
        agencia: String(d.agencia ?? ""), dvAgencia: d.dv_agencia || "",
        contaCorrente: String(d.conta_corrente ?? ""), dvContaCorrente: d.dv_conta_corrente || "",
        dvAgenciaConta: d.dv_agencia_conta || "", situacao: d.situacao || "A",
        carteira: String(d.carteira ?? ""), variacaoCarteira: String(d.variacao_carteira ?? ""),
        codigoCedente: d.codigo_cedente || "", codTransmissao: d.cod_transmissao || "",
        contrato: String(d.contrato ?? ""), especieDoc: String(d.especie_doc ?? ""), aceite: d.aceite || "N",
        tarifaCobranca: String(d.tarifa_cobranca ?? ""), incidenciaMulta: String(d.incidencia_multa ?? ""),
        diasMulta: String(d.dias_multa ?? ""), tipoMulta: String(d.tipo_multa ?? ""),
        multaAtrasoPag: String(d.multa_atraso_pag ?? ""), moraDiaPag: String(d.mora_dia_pag ?? ""),
        diasProtesto: String(d.dias_protesto ?? ""), codigoProtesto: String(d.codigo_protesto ?? ""),
        diasBaixa: String(d.dias_baixa ?? ""), codigoBaixa: String(d.codigo_baixa ?? ""),
        tipoCobranca: String(d.tipo_cobranca ?? ""), tipoRegistro: String(d.tipo_registro ?? ""),
        emissaoBoleto: String(d.emissao_boleto ?? ""), distribuiBoleto: String(d.distribui_boleto ?? ""),
        numeroBoleto: String(d.numero_boleto ?? ""), instrCobranca1: String(d.instr_cobranca_1 ?? ""),
        instrCobranca2: String(d.instr_cobranca_2 ?? ""), tituloBoleto: d.titulo_boleto || "",
        mensagemBoleto1: d.mensagem_boleto_1 || "", mensagemBoleto2: d.mensagem_boleto_2 || "",
        mensagemBoleto3: d.mensagem_boleto_3 || "", enderecoRemessa: d.endereco_remessa || "",
        enderecoRetorno: d.endereco_retorno || "", integracaoApi: !!d.integracao_api,
        chaveApi1: d.chave_api_1 || "", chaveApi2: d.chave_api_2 || "",
        chaveApi3: d.chave_api_3 || "", chaveApi4: d.chave_api_4 || "",
      });
      setLogoBase64(d.logo_base64 || null);
      setLogoMime(d.logo_mime || null);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      setFormOpen(false);
    }
  };

  const uploadLogoBanco = async () => {
    if (!conn || !editingCod || !logoArquivo) { fb.showWarning("Selecione um arquivo de imagem."); return; }
    if (logoArquivo.size > LOGO_TAMANHO_MAXIMO_BYTES) {
      fb.showWarning(`Arquivo muito grande (${(logoArquivo.size / 1024 / 1024).toFixed(1)} MB) — o recomendado é até 1 MB.`);
    }
    const resolucao = await lerResolucaoImagem(logoArquivo);
    if (resolucao && (resolucao.largura < LOGO_LARGURA_MINIMA || resolucao.altura < LOGO_ALTURA_MINIMA)) {
      fb.showWarning(
        `Imagem com resolução baixa (${resolucao.largura}×${resolucao.altura}px) — pode sair borrada na impressão. ` +
        `Recomendado: pelo menos ${LOGO_LARGURA_MINIMA}×${LOGO_ALTURA_MINIMA}px. Enviando mesmo assim…`,
        undefined, 5000,
      );
    }
    setLogoSaving(true);
    try {
      const fd = new FormData();
      fd.append("servidor", conn.servidor);
      fd.append("banco", conn.banco);
      if (auditCtx.usuario_alteracao != null) fd.append("usuario_alteracao", String(auditCtx.usuario_alteracao));
      if (auditCtx.classe != null) fd.append("classe", String(auditCtx.classe));
      fd.append("plataforma", auditCtx.plataforma);
      fd.append("arquivo", logoArquivo, logoArquivo.name);
      const r = await fetch(`${apiBase(conn)}/api/bancos/${editingCod}/logo`, { method: "POST", body: fd });
      const j = await r.json().catch(() => null);
      if (j?.success) {
        fb.showSuccess(j.message || "Logo cadastrada.");
        setLogoArquivo(null);
        const jd = await apiGet(conn, `/api/bancos/${editingCod}`);
        if (jd?.success) { setLogoBase64(jd.logo_base64 || null); setLogoMime(jd.logo_mime || null); }
      } else {
        fb.showError(!r.ok && !j ? `Falha ao cadastrar a logo (HTTP ${r.status}).` : friendlyApiError(j, "Falha ao cadastrar a logo."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao cadastrar a logo."));
    } finally {
      setLogoSaving(false);
    }
  };

  const removerLogoBanco = async () => {
    if (!conn || !editingCod) return;
    try {
      const j = await apiSend(conn, `/api/bancos/${editingCod}/logo/remover`, "POST", { ...auditCtx });
      if (j?.success) { fb.showSuccess(j.message || "Logo removida."); setLogoBase64(null); setLogoMime(null); }
      else fb.showError(friendlyApiError(j, "Falha ao remover a logo."));
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao remover a logo."));
    }
  };

  const save = async () => {
    if (!conn) return;
    if (!form.descricao.trim()) { fb.showWarning("Informe a descrição do banco."); return; }
    if (!int_(form.codigo)) { fb.showWarning("Informe o código do banco (padrão Febraban)."); return; }
    if (!int_(form.agencia)) { fb.showWarning("Informe a agência."); return; }
    if (!int_(form.contaCorrente)) { fb.showWarning("Informe a conta corrente."); return; }
    if (!int_(form.carteira)) { fb.showWarning("Informe a carteira."); return; }
    if (!form.codigoCedente.trim()) { fb.showWarning("Informe o código cedente."); return; }
    if (!form.integracaoApi) {
      if (!form.enderecoRemessa.trim()) { fb.showWarning("Informe o diretório de remessa."); return; }
      if (!form.enderecoRetorno.trim()) { fb.showWarning("Informe o diretório de retorno."); return; }
    }
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/bancos", "POST", {
        ...auditCtx,
        cod: editingCod,
        codigo: int_(form.codigo), digito_banco: int_(form.digitoBanco),
        descricao: form.descricao.trim(), descr_arquivo: form.descrArquivo.trim(),
        agencia: int_(form.agencia), dv_agencia: form.dvAgencia.trim(),
        conta_corrente: int_(form.contaCorrente), dv_conta_corrente: form.dvContaCorrente.trim(),
        dv_agencia_conta: form.dvAgenciaConta.trim(), situacao: (form.situacao || "A").toUpperCase(),
        carteira: int_(form.carteira), variacao_carteira: int_(form.variacaoCarteira),
        codigo_cedente: form.codigoCedente.trim(), cod_transmissao: form.codTransmissao.trim(),
        contrato: num(form.contrato), especie_doc: int_(form.especieDoc), aceite: (form.aceite || "N").toUpperCase(),
        tarifa_cobranca: num(form.tarifaCobranca), incidencia_multa: int_(form.incidenciaMulta),
        dias_multa: int_(form.diasMulta), tipo_multa: int_(form.tipoMulta),
        multa_atraso_pag: num(form.multaAtrasoPag), mora_dia_pag: num(form.moraDiaPag),
        dias_protesto: int_(form.diasProtesto), codigo_protesto: int_(form.codigoProtesto),
        dias_baixa: int_(form.diasBaixa), codigo_baixa: int_(form.codigoBaixa),
        tipo_cobranca: int_(form.tipoCobranca), tipo_registro: int_(form.tipoRegistro),
        emissao_boleto: int_(form.emissaoBoleto), distribui_boleto: int_(form.distribuiBoleto),
        numero_boleto: num(form.numeroBoleto), instr_cobranca_1: int_(form.instrCobranca1),
        instr_cobranca_2: int_(form.instrCobranca2), titulo_boleto: form.tituloBoleto.trim(),
        mensagem_boleto_1: form.mensagemBoleto1.trim(), mensagem_boleto_2: form.mensagemBoleto2.trim(),
        mensagem_boleto_3: form.mensagemBoleto3.trim(), endereco_remessa: form.enderecoRemessa.trim(),
        endereco_retorno: form.enderecoRetorno.trim(), integracao_api: form.integracaoApi,
        chave_api_1: form.chaveApi1.trim(), chave_api_2: form.chaveApi2.trim(),
        chave_api_3: form.chaveApi3.trim(), chave_api_4: form.chaveApi4.trim(),
      });
      if (j?.success) {
        fb.showSuccess("Banco gravado.");
        setEditingCod(j.cod);
        load(conn);
      } else fb.showError(friendlyApiError(j, "Falha ao gravar."));
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const remove = (item: BancoListItem) => {
    if (!conn) return;
    fb.showConfirm(`Confirma a exclusão do banco "${item.descricao}"?`, async () => {
      try {
        const j = await apiSend(conn, `/api/bancos/${item.cod}`, "DELETE", { ...auditCtx, cod: item.cod });
        if (j?.success) { fb.showSuccess("Banco excluído."); load(conn); }
        else fb.showError(friendlyApiError(j, "Falha ao excluir."));
      } catch (e) {
        fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      }
    }, { destructive: true, confirmText: "Excluir" });
  };

  const canSave = can("BANCOS.GRAVAR") || isMaster;
  const canDel = can("BANCOS.EXCLUIR") || isMaster;
  const canRemessa = can("BANCOS.GERAR_REMESSA") || isMaster;
  const canRetorno = can("BANCOS.IMP_RETORNO") || isMaster;
  // Fase 2a: Bradesco (237) e Inter (077) têm remessa+retorno completos;
  // Santander (033), Banco do Brasil (001) e Itaú (341) só têm retorno —
  // remessa pendente de arquivo real pra confirmar largura de campo (ver
  // PENDENCIAS.md). Botões só aparecem pro banco já salvo, modo CNAB (não API).
  const NOMES_BANCO_CNAB: Record<number, string> = { 237: "Bradesco", 77: "Inter", 33: "Santander", 1: "Banco do Brasil", 341: "Itaú" };
  const BANCOS_REMESSA_SUPORTADOS = [237, 77, 341];
  const codigoBancoAtual = int_(form.codigo);
  const remessaSuportada = !!editingCod && BANCOS_REMESSA_SUPORTADOS.includes(codigoBancoAtual) && !form.integracaoApi;
  const retornoSuportado = !!editingCod && codigoBancoAtual in NOMES_BANCO_CNAB && !form.integracaoApi;
  const cnabSuportado = remessaSuportada || retornoSuportado;
  const nomeBancoCnab = NOMES_BANCO_CNAB[codigoBancoAtual] || "";

  const downloadTexto = (nomeArquivo: string, conteudo: string) => {
    const blob = new Blob([conteudo], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nomeArquivo;
    a.click();
    URL.revokeObjectURL(url);
  };

  const gerarRemessa = async () => {
    if (!conn || !editingCod) return;
    setRemessaSaving(true);
    try {
      const j = await apiSend(conn, `/api/bancos/${editingCod}/remessa`, "POST", { ...auditCtx });
      if (j?.success) {
        downloadTexto(j.nome_arquivo, j.conteudo);
        fb.showSuccess(`Remessa nº ${j.num_remessa} gerada com ${j.qtd_titulos} título(s) — arquivo "${j.nome_arquivo}" baixado.`, undefined, 5000);
      } else {
        fb.showError(friendlyApiError(j, "Falha ao gerar remessa."));
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRemessaSaving(false);
    }
  };

  const processarRetorno = async () => {
    if (!conn || !editingCod) return;
    if (!retornoTexto.trim()) { fb.showWarning("Cole o conteúdo do arquivo de retorno."); return; }
    setRetornoSaving(true);
    try {
      const j = await apiSend(conn, `/api/bancos/${editingCod}/retorno`, "POST", { ...auditCtx, conteudo: retornoTexto });
      if (j?.success) {
        setRetornoResultado(
          `${j.baixados} título(s) baixado(s), ${j.confirmados} confirmação(ões), ` +
          `${j.nao_encontrados.length} não encontrado(s)${j.nao_encontrados.length ? ` (${j.nao_encontrados.join(", ")})` : ""}, ` +
          `${j.ignorados} linha(s) ignorada(s).`
        );
        load(conn);
      } else {
        fb.showError(friendlyApiError(j, "Falha ao processar retorno."));
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRetornoSaving(false);
    }
  };

  if (formOpen) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="bancos-form-screen">
        <View style={styles.header}>
          <Pressable onPress={() => setFormOpen(false)} style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]} hitSlop={12} testID="bancos-form-back-button">
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          <Text style={styles.headerTitle} numberOfLines={1}>{editingCod ? `Banco #${editingCod}` : "Novo Banco"}</Text>
          <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)} color={colors.onBrandPrimary} style={styles.helpIconBtn} testID="bancos-ajuda" />
          <Pressable onPress={save} disabled={saving || !canSave} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]} hitSlop={8} testID="bancos-salvar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
              <>
                <Ionicons name="save-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.saveLabel}>Gravar</Text>
              </>
            )}
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>

            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Código do Banco *</Text>
                  <TextInput value={form.codigo} onChangeText={(v) => setField("codigo", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-codigo" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Dígito</Text>
                  <TextInput value={form.digitoBanco} onChangeText={(v) => setField("digitoBanco", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-digito" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Descrição *</Text>
                  <TextInput value={form.descricao} onChangeText={(v) => setField("descricao", v)} maxLength={30} style={styles.input} testID="bancos-descricao" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Situação</Text>
                  <View style={styles.radioRow}>
                    {[{ v: "A", l: "Ativo" }, { v: "I", l: "Inativo" }].map((op) => (
                      <Pressable key={op.v} onPress={() => setField("situacao", op.v)} style={[styles.radioBtn, form.situacao === op.v && styles.radioBtnSel]} testID={`bancos-situacao-${op.v}`}>
                        <View style={[styles.radioCircle, form.situacao === op.v && styles.radioCircleSel]}>{form.situacao === op.v ? <View style={styles.radioDot} /> : null}</View>
                        <Text style={styles.radioLabel}>{op.l}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
              </View>
            </View>

            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Identificação Bancária</Text></View>
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Agência *</Text>
                  <TextInput value={form.agencia} onChangeText={(v) => setField("agencia", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-agencia" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>DV Agência</Text>
                  <TextInput value={form.dvAgencia} onChangeText={(v) => setField("dvAgencia", v.slice(0, 1))} maxLength={1} style={styles.input} testID="bancos-dv-agencia" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Conta Corrente *</Text>
                  <TextInput value={form.contaCorrente} onChangeText={(v) => setField("contaCorrente", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-conta" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>DV Conta</Text>
                  <TextInput value={form.dvContaCorrente} onChangeText={(v) => setField("dvContaCorrente", v.slice(0, 1))} maxLength={1} style={styles.input} testID="bancos-dv-conta" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>DV Ag./Conta</Text>
                  <TextInput value={form.dvAgenciaConta} onChangeText={(v) => setField("dvAgenciaConta", v.slice(0, 1))} maxLength={1} style={styles.input} testID="bancos-dv-ag-conta" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Descrição do Arquivo (CNAB)</Text>
                  <TextInput value={form.descrArquivo} onChangeText={(v) => setField("descrArquivo", v)} maxLength={30} style={styles.input} testID="bancos-descr-arquivo" />
                </View>
              </View>
            </View>

            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>Integração</Text>
            </View>
            <View style={styles.card}>
              <View style={styles.toggleRow}>
                <Switch value={form.integracaoApi} onValueChange={(v) => setField("integracaoApi", v)} testID="bancos-integracao-api" />
                <Text style={styles.toggleLabel}>Integração por API {form.integracaoApi ? "(sem arquivo CNAB)" : "(desligado — usa arquivo CNAB)"}</Text>
              </View>
              {form.integracaoApi ? (
                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Chave/Token de API 1</Text>
                    <TextInput value={form.chaveApi1} onChangeText={(v) => setField("chaveApi1", v)} secureTextEntry style={styles.input} testID="bancos-chave-1" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Chave/Token de API 2</Text>
                    <TextInput value={form.chaveApi2} onChangeText={(v) => setField("chaveApi2", v)} secureTextEntry style={styles.input} testID="bancos-chave-2" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Chave/Token de API 3</Text>
                    <TextInput value={form.chaveApi3} onChangeText={(v) => setField("chaveApi3", v)} secureTextEntry style={styles.input} testID="bancos-chave-3" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Chave/Token de API 4</Text>
                    <TextInput value={form.chaveApi4} onChangeText={(v) => setField("chaveApi4", v)} secureTextEntry style={styles.input} testID="bancos-chave-4" />
                  </View>
                </View>
              ) : (
                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Diretório de Remessa *</Text>
                    <TextInput value={form.enderecoRemessa} onChangeText={(v) => setField("enderecoRemessa", v)} style={styles.input} testID="bancos-end-remessa" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Diretório de Retorno *</Text>
                    <TextInput value={form.enderecoRetorno} onChangeText={(v) => setField("enderecoRetorno", v)} style={styles.input} testID="bancos-end-retorno" />
                  </View>
                </View>
              )}
            </View>

            {cnabSuportado ? (
              <>
                <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Remessa / Retorno ({nomeBancoCnab})</Text></View>
                <View style={styles.card}>
                  <Text style={styles.hint}>
                    {remessaSuportada
                      ? `Gera o arquivo de remessa (${codigoBancoAtual === 77 || codigoBancoAtual === 341 ? "CNAB400" : "CNAB240"}) com todos os títulos em aberto ainda não enviados deste banco, ou processa um arquivo de retorno colando o conteúdo abaixo.`
                      : "Geração de remessa para este banco ainda não foi implementada (aguardando arquivo real para confirmar o layout). Processa um arquivo de retorno colando o conteúdo abaixo."}
                  </Text>
                  <View style={styles.rowFields}>
                    {canRemessa && remessaSuportada ? (
                      <Pressable
                        onPress={gerarRemessa}
                        disabled={remessaSaving}
                        style={({ pressed }) => [styles.secondaryBtn, (pressed || remessaSaving) && { opacity: 0.8 }]}
                        testID="bancos-gerar-remessa"
                      >
                        {remessaSaving ? (
                          <>
                            <ActivityIndicator size="small" color={colors.brandPrimary} />
                            <Text style={styles.secondaryBtnText}>Gerando…</Text>
                          </>
                        ) : (
                          <>
                            <Ionicons name="document-text-outline" size={16} color={colors.brandPrimary} />
                            <Text style={styles.secondaryBtnText}>Gerar Remessa</Text>
                          </>
                        )}
                      </Pressable>
                    ) : null}
                    {canRetorno ? (
                      <Pressable
                        onPress={() => { setRetornoResultado(null); setRetornoTexto(""); setRetornoOpen(true); }}
                        style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]}
                        testID="bancos-abrir-retorno"
                      >
                        <Ionicons name="cloud-upload-outline" size={16} color={colors.brandPrimary} />
                        <Text style={styles.secondaryBtnText}>Processar Retorno</Text>
                      </Pressable>
                    ) : null}
                  </View>
                </View>
              </>
            ) : null}

            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Cobrança</Text></View>
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Carteira *</Text>
                  <TextInput value={form.carteira} onChangeText={(v) => setField("carteira", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-carteira" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Variação de Carteira</Text>
                  <TextInput value={form.variacaoCarteira} onChangeText={(v) => setField("variacaoCarteira", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-variacao-carteira" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Código Cedente *</Text>
                  <TextInput value={form.codigoCedente} onChangeText={(v) => setField("codigoCedente", v)} maxLength={20} style={styles.input} testID="bancos-codigo-cedente" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Código de Transmissão</Text>
                  <TextInput value={form.codTransmissao} onChangeText={(v) => setField("codTransmissao", v)} maxLength={20} style={styles.input} testID="bancos-cod-transmissao" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Nº Contrato</Text>
                  <TextInput value={form.contrato} onChangeText={(v) => setField("contrato", v.replace(/[^0-9.,]/g, ""))} keyboardType="decimal-pad" style={styles.input} testID="bancos-contrato" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Espécie Doc.</Text>
                  <TextInput value={form.especieDoc} onChangeText={(v) => setField("especieDoc", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-especie-doc" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Aceite (S/N)</Text>
                  <TextInput value={form.aceite} onChangeText={(v) => setField("aceite", v.toUpperCase().slice(0, 1))} maxLength={1} autoCapitalize="characters" style={styles.input} testID="bancos-aceite" />
                </View>
              </View>
            </View>

            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Multa, Mora, Protesto e Baixa</Text></View>
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Incidência Multa</Text>
                  <TextInput value={form.incidenciaMulta} onChangeText={(v) => setField("incidenciaMulta", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-incidencia-multa" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Dias p/ Multa</Text>
                  <TextInput value={form.diasMulta} onChangeText={(v) => setField("diasMulta", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-dias-multa" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Tipo Multa</Text>
                  <TextInput value={form.tipoMulta} onChangeText={(v) => setField("tipoMulta", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-tipo-multa" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Multa Atraso (%)</Text>
                  <TextInput value={form.multaAtrasoPag} onChangeText={(v) => setField("multaAtrasoPag", v.replace(/[^0-9.,]/g, ""))} keyboardType="decimal-pad" style={styles.input} testID="bancos-multa-atraso" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Mora Diária (%)</Text>
                  <TextInput value={form.moraDiaPag} onChangeText={(v) => setField("moraDiaPag", v.replace(/[^0-9.,]/g, ""))} keyboardType="decimal-pad" style={styles.input} testID="bancos-mora-dia" />
                </View>
              </View>
              <Text style={styles.hint}>0 = confirmar instrução na agência · 99 = não protestar/baixar · 2 a 55 = dias corridos.</Text>
              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Dias p/ Protestar</Text>
                  <TextInput value={form.diasProtesto} onChangeText={(v) => setField("diasProtesto", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-dias-protesto" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Código Protesto</Text>
                  <TextInput value={form.codigoProtesto} onChangeText={(v) => setField("codigoProtesto", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-codigo-protesto" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Dias p/ Baixa</Text>
                  <TextInput value={form.diasBaixa} onChangeText={(v) => setField("diasBaixa", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-dias-baixa" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Código Baixa</Text>
                  <TextInput value={form.codigoBaixa} onChangeText={(v) => setField("codigoBaixa", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-codigo-baixa" />
                </View>
              </View>
            </View>

            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Boleto</Text></View>
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Tarifa Bancária</Text>
                  <TextInput value={form.tarifaCobranca} onChangeText={(v) => setField("tarifaCobranca", v.replace(/[^0-9.,]/g, ""))} keyboardType="decimal-pad" style={styles.input} testID="bancos-tarifa" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Tipo Cobrança</Text>
                  <TextInput value={form.tipoCobranca} onChangeText={(v) => setField("tipoCobranca", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-tipo-cobranca" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Tipo Registro</Text>
                  <TextInput value={form.tipoRegistro} onChangeText={(v) => setField("tipoRegistro", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-tipo-registro" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Emissão Boleto</Text>
                  <TextInput value={form.emissaoBoleto} onChangeText={(v) => setField("emissaoBoleto", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-emissao-boleto" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Envio/Distribuição</Text>
                  <TextInput value={form.distribuiBoleto} onChangeText={(v) => setField("distribuiBoleto", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-distribui-boleto" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Nº do Boleto</Text>
                  <TextInput value={form.numeroBoleto} onChangeText={(v) => setField("numeroBoleto", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-numero-boleto" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Instrução Cobrança 1</Text>
                  <TextInput value={form.instrCobranca1} onChangeText={(v) => setField("instrCobranca1", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-instr-1" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Instrução Cobrança 2</Text>
                  <TextInput value={form.instrCobranca2} onChangeText={(v) => setField("instrCobranca2", v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="bancos-instr-2" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Título do Boleto</Text>
                  <TextInput value={form.tituloBoleto} onChangeText={(v) => setField("tituloBoleto", v)} style={styles.input} testID="bancos-titulo-boleto" />
                </View>
              </View>
              <Text style={styles.label}>Mensagem do Boleto (linha 1)</Text>
              <TextInput value={form.mensagemBoleto1} onChangeText={(v) => setField("mensagemBoleto1", v)} style={styles.input} testID="bancos-msg-1" />
              <Text style={styles.label}>Mensagem do Boleto (linha 2)</Text>
              <TextInput value={form.mensagemBoleto2} onChangeText={(v) => setField("mensagemBoleto2", v)} style={styles.input} testID="bancos-msg-2" />
              <Text style={styles.label}>Mensagem do Boleto (linha 3)</Text>
              <TextInput value={form.mensagemBoleto3} onChangeText={(v) => setField("mensagemBoleto3", v)} style={styles.input} testID="bancos-msg-3" />

              <Text style={[styles.label, { marginTop: spacing.md }]}>Logo do Banco</Text>
              {!editingCod ? (
                <Text style={styles.hint}>Grave o banco primeiro para poder enviar a logo.</Text>
              ) : (
                <View>
                  {logoBase64 ? (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.sm }}>
                      <Image
                        source={{ uri: `data:${logoMime || "image/png"};base64,${logoBase64}` }}
                        style={{ width: 100, height: 60, resizeMode: "contain", borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm }}
                      />
                      <Pressable onPress={removerLogoBanco} style={styles.secondaryBtn} testID="bancos-logo-remover">
                        <Text style={styles.secondaryBtnText}>Remover Logo</Text>
                      </Pressable>
                    </View>
                  ) : (
                    <Text style={styles.hint}>Nenhuma logo cadastrada.</Text>
                  )}
                  <View style={styles.rowFields}>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Arquivo (.png/.jpg)</Text>
                      {isWeb ? (
                        <input
                          type="file" accept="image/png,image/jpeg"
                          onChange={(e) => setLogoArquivo((e.target as HTMLInputElement).files?.[0] || null)}
                          style={{
                            height: 36, boxSizing: "border-box", padding: "0 8px", fontSize: 13,
                            border: `1px solid ${colors.border}`, borderRadius: radius.sm,
                            backgroundColor: colors.surface, color: colors.onSurface,
                          }}
                        />
                      ) : null}
                    </View>
                    <View style={[styles.colNarrow, { justifyContent: "flex-end" }]}>
                      <Pressable onPress={uploadLogoBanco} disabled={logoSaving} style={[styles.secondaryBtn, logoSaving && { opacity: 0.8 }]} testID="bancos-logo-upload">
                        {logoSaving ? (
                          <><ActivityIndicator size="small" color={colors.brandPrimary} /><Text style={styles.secondaryBtnText}>Enviando…</Text></>
                        ) : (
                          <Text style={styles.secondaryBtnText}>Enviar Logo</Text>
                        )}
                      </Pressable>
                    </View>
                  </View>
                  <Text style={styles.hint}>{LOGO_ORIENTACAO_TEXTO}</Text>
                </View>
              )}
            </View>

          </View>
        </ScrollView>

        <AjudaBancosModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} />

        <AppModal visible={retornoOpen} transparent animationType="fade" onRequestClose={() => setRetornoOpen(false)}>
          <Pressable style={styles.helpBg} onPress={() => setRetornoOpen(false)}>
            <Pressable style={styles.helpCard} onPress={(e) => e.stopPropagation()}>
              <View style={styles.helpHeader}>
                <Text style={styles.helpTitle}>Processar Retorno ({nomeBancoCnab})</Text>
                <Pressable onPress={() => setRetornoOpen(false)} hitSlop={8}>
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
              </View>
              <Text style={styles.hint}>Cole abaixo o conteúdo do arquivo de retorno (CNAB400) recebido do banco.</Text>
              <TextInput
                value={retornoTexto}
                onChangeText={setRetornoTexto}
                multiline
                style={styles.retornoTextarea}
                placeholder="Cole aqui o conteúdo do arquivo .RET…"
                placeholderTextColor={colors.muted}
                testID="bancos-retorno-texto"
              />
              {retornoResultado ? <Text style={styles.retornoResultado}>{retornoResultado}</Text> : null}
              <View style={[styles.rowFields, { marginTop: spacing.sm }]}>
                <Pressable
                  onPress={processarRetorno}
                  disabled={retornoSaving}
                  style={({ pressed }) => [styles.secondaryBtn, (pressed || retornoSaving) && { opacity: 0.8 }]}
                  testID="bancos-processar-retorno"
                >
                  {retornoSaving ? (
                    <>
                      <ActivityIndicator size="small" color={colors.brandPrimary} />
                      <Text style={styles.secondaryBtnText}>Processando…</Text>
                    </>
                  ) : (
                    <Text style={styles.secondaryBtnText}>Processar</Text>
                  )}
                </Pressable>
              </View>
            </Pressable>
          </Pressable>
        </AppModal>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="bancos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Cobranças</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.listShell}>
        <View style={styles.filterBox}>
          <TextInput value={search} onChangeText={setSearch} placeholder="Buscar por descrição ou código do banco…" placeholderTextColor={colors.muted} style={styles.input} testID="bancos-search" />
        </View>

        <ScrollView contentContainerStyle={[styles.listScroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum banco cadastrado.</Text> : null}
          {items.map((b) => (
            <View key={b.cod} style={styles.row} testID={`bancos-${b.cod}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(b)}>
                <Text style={styles.rowTitle}>{b.descricao || "—"}</Text>
                <Text style={styles.rowSub}>
                  Banco {b.codigo} · Ag. {b.agencia} · Conta {b.conta_corrente} · Carteira {b.carteira}
                  {b.integracao_api ? " · API" : ""}{b.situacao !== "A" ? " · Inativo" : ""}
                </Text>
              </Pressable>
              {canDel ? (
                <IconButtonWithTooltip icon="trash-outline" label="Excluir banco" onPress={() => remove(b)} color={colors.error} testID={`bancos-del-${b.cod}`} />
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="bancos-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  helpIconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center", marginLeft: spacing.sm },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  listShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  listScroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: { flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8, marginBottom: 8, fontSize: 12 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },

  scroll: { paddingBottom: spacing.xxxl },
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm, width: "100%", maxWidth: 1120, alignSelf: "center" },
  sectionTitle: { fontSize: 14, fontWeight: "500", color: colors.onSurface, textTransform: "uppercase", letterSpacing: 0.5 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  hint: { fontSize: 12, color: colors.muted, marginTop: spacing.xs, fontStyle: "italic" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 160 },
  colTiny: { width: 110 },
  radioRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  radioBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  radioBtnSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  radioCircle: { width: 16, height: 16, borderRadius: 8, borderWidth: 1.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioCircleSel: { borderColor: colors.brandPrimary },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  secondaryBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  secondaryBtnText: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  retornoTextarea: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, fontSize: 12, color: colors.onSurface, minHeight: 220, textAlignVertical: "top", fontFamily: Platform.OS === "web" ? "monospace" : undefined },
  retornoResultado: { fontSize: 13, color: colors.onSurface, marginTop: spacing.sm, lineHeight: 18 },
  toggleLabel: { fontSize: 13, fontWeight: "600", color: colors.onSurface },

  helpBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", alignItems: "center", justifyContent: "center", padding: spacing.xl },
  helpCard: { width: "100%", maxWidth: 560, backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg },
  helpHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  helpTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  helpItem: { marginBottom: spacing.md },
  helpItemTitulo: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: 2 },
  helpItemTexto: { fontSize: 12, color: colors.onSurface, lineHeight: 17 },
});

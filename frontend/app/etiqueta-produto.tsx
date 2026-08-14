// Etiquetas de Produto — migração de Geral\FrmEtqProd.frm (Painel de
// Relatórios > Estoque). Ver PENDENCIAS.md > "Painel de Relatórios (VB6)"
// > "Etiqueta de Produto" pro rastreio completo e as decisões tomadas
// (AskUserQuestion, 2026-08-07): Zebra/térmica só documentada no Modo
// Didático (não imprime ainda — precisa de extensão do print-agent);
// Excluir/Limpar Todos implementados de verdade (eram inertes no legado);
// matriz de Grade Cor×Tamanho incluída.
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import SelectField, { SelectOption } from "@/src/components/SelectField";
import FornecedorSearchModal, { FornecedorRow } from "@/src/components/FornecedorSearchModal";
import ProdutoSearchModal, { ProdutoRow } from "@/src/components/ProdutoSearchModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError, friendlyApiError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { imprimirEtiquetas, ModeloEtiqueta, EtiquetaItem } from "@/src/utils/export-etiqueta-produto";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };

type LinhaGrid = EtiquetaItem & {
  imp: boolean;
  num_nf?: string | null;
  entrada?: string | null;
  fornecedor_nome?: string | null;
};

type GradeCelula = {
  cor: number; cor_descricao: string; tamanho: string;
  codigo_int: string; codigo_fab: string; descricao: string; codigo_bar: string; p_venda: number;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

const AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "NF Entrada",
    texto: "Informe Número, Série e Fornecedor de uma nota fiscal de entrada já cadastrada e toque em Selecionar — todos os itens dessa nota entram na lista, uma etiqueta por unidade recebida.",
    icon: { lib: "ion", name: "document-text-outline" },
  },
  {
    titulo: "Código do Produto",
    texto: "Adiciona um produto avulso à lista (sem vínculo com nota fiscal), pela quantidade informada. Aceita código interno, código de fábrica ou código de barras.",
    icon: { lib: "ion", name: "barcode-outline" },
  },
  {
    titulo: "Usar descrição NFCe",
    texto: "Quando marcado, produtos adicionados manualmente usam a descrição alternativa cadastrada para NFC-e (se houver) em vez da descrição normal. Só afeta a adição manual, não os itens vindos de nota fiscal.",
    icon: { lib: "ion", name: "receipt-outline" },
  },
  {
    titulo: "Produto com Grade (Cor/Tamanho)",
    texto: "Se o produto digitado tiver variações de cor e tamanho cadastradas, uma matriz de quantidades aparece no lugar do campo simples — preencha a quantidade de cada combinação e adicione todas de uma vez.",
    icon: { lib: "ion", name: "grid-outline" },
  },
  {
    titulo: "Modelo Etiqueta",
    texto: "Escolha o layout físico da etiqueta. Modelos \"Identificação\" e \"Gôndola\" imprimem numa folha comum (impressora normal). Modelos \"Zebra\" são para impressora térmica dedicada e AINDA NÃO IMPRIMEM nesta versão — dependem de uma extensão do agente de impressão local (o mesmo programa que já imprime cupom/comanda automaticamente) capaz de enviar comandos direto pra esse tipo de impressora, que ainda não foi construída.",
    icon: { lib: "ion", name: "print-outline" },
  },
  {
    titulo: "Margem Lateral / Superior e Gravar",
    texto: "Só se aplicam aos modelos \"Identificação\" (folha comum) — ajustam o alinhamento impresso quando a folha física fica um pouco deslocada na sua impressora. Gravar salva esses valores pra próxima vez, só pra esse modelo.",
    icon: { lib: "ion", name: "save-outline" },
  },
  {
    titulo: "Nº Etiquetas a Saltar",
    texto: "Pula as N primeiras posições da folha antes de começar a imprimir — útil pra reaproveitar uma folha de etiquetas já parcialmente usada.",
    icon: { lib: "ion", name: "play-skip-forward-outline" },
  },
  {
    titulo: "Marcar/Desmarcar Todos, Excluir, Limpar Todos",
    texto: "A coluna \"Imp\" decide o que entra na impressão — só linhas marcadas são impressas. Excluir remove só a linha selecionada; Limpar Todos esvazia a lista inteira.",
    icon: { lib: "ion", name: "checkbox-outline" },
  },
];

export default function EtiquetaProdutoScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  // NF Entrada
  const [numNf, setNumNf] = useState("");
  const [serieNf, setSerieNf] = useState("");
  const [fornecedor, setFornecedor] = useState<FornecedorRow | null>(null);
  const [fornOpen, setFornOpen] = useState(false);
  const [fornTerm, setFornTerm] = useState("");
  const [fornResults, setFornResults] = useState<FornecedorRow[]>([]);
  const [fornLoading, setFornLoading] = useState(false);
  const [loadingNf, setLoadingNf] = useState(false);

  // Adição manual
  const [termoProduto, setTermoProduto] = useState("");
  const [quant, setQuant] = useState("1");
  const [usarDescricaoNfce, setUsarDescricaoNfce] = useState(false);
  const [prodOpen, setProdOpen] = useState(false);
  const [prodTerm, setProdTerm] = useState("");
  const [prodResults, setProdResults] = useState<ProdutoRow[]>([]);
  const [prodLoading, setProdLoading] = useState(false);
  const [loadingManual, setLoadingManual] = useState(false);
  const [grade, setGrade] = useState<GradeCelula[] | null>(null);
  const [gradeQtds, setGradeQtds] = useState<Record<string, string>>({});

  // Modelo de etiqueta
  const [modelos, setModelos] = useState<ModeloEtiqueta[]>([]);
  const [modeloCodigo, setModeloCodigo] = useState<number | null>(null);
  const [margemLateral, setMargemLateral] = useState("0.850");
  const [margemSuperior, setMargemSuperior] = useState("0.950");
  const [saltar, setSaltar] = useState("0");
  const [gravandoMargem, setGravandoMargem] = useState(false);
  const [imprimindo, setImprimindo] = useState(false);

  const [linhas, setLinhas] = useState<LinhaGrid[]>([]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { feedback.showError("Conexão não encontrada."); return; }
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      try {
        const base = cc.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`;
        const r = await fetch(`${base}/api/etiqueta-produto/modelos?${qs}`);
        const j = await r.json();
        if (j?.success) {
          setModelos(j.modelos || []);
          const primeiro = (j.modelos || [])[0];
          if (primeiro) {
            setModeloCodigo(primeiro.codigo);
            setMargemLateral(String(primeiro.margem_lateral_cm ?? "0.850"));
            setMargemSuperior(String(primeiro.margem_superior_cm ?? "0.950"));
          }
        }
      } catch (e) {
        feedback.showError(friendlyCatchError(e, "Falha ao carregar modelos de etiqueta."));
      }
    })();
  }, [router]);

  useEffect(() => {
    if (!fornOpen || !conn) return;
    const t = fornTerm.trim();
    if (t.length < 2) { setFornResults([]); return; }
    setFornLoading(true);
    const timer = setTimeout(async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(t)}`;
        const r = await fetch(`${base}/api/fornecedores?${qs}`);
        const j = await r.json();
        setFornResults(j?.success ? (j.items || []) : []);
      } catch {
        setFornResults([]);
      } finally {
        setFornLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [fornOpen, fornTerm, conn]);

  useEffect(() => {
    if (!prodOpen || !conn) return;
    const t = prodTerm.trim();
    if (t.length < 2) { setProdResults([]); return; }
    setProdLoading(true);
    const timer = setTimeout(async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(t)}&tipo=P&page=1&size=30`;
        const r = await fetch(`${base}/api/produtos-servicos?${qs}`);
        const j = await r.json();
        setProdResults(j?.success ? (j.items || []) : []);
      } catch {
        setProdResults([]);
      } finally {
        setProdLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [prodOpen, prodTerm, conn]);

  const modeloAtual = useMemo(() => modelos.find((m) => m.codigo === modeloCodigo) || null, [modelos, modeloCodigo]);
  const modeloOpts: SelectOption[] = useMemo(
    () => modelos.map((m) => ({ value: m.codigo, label: m.nome + (m.formato === "termica" ? " (ainda não imprime)" : "") })),
    [modelos]
  );

  useEffect(() => {
    if (modeloAtual) {
      setMargemLateral(String(modeloAtual.margem_lateral_cm ?? "0.850"));
      setMargemSuperior(String(modeloAtual.margem_superior_cm ?? "0.950"));
    }
  }, [modeloAtual?.codigo]);

  const stats = useMemo(() => {
    const marcadas = linhas.filter((l) => l.imp);
    const qtdProdutos = marcadas.length;
    const qtdEtiquetas = marcadas.reduce((s, l) => s + (l.quant || 0), 0);
    let qtdFolhas: number | null = null;
    if (modeloAtual && modeloAtual.linhas_por_folha) {
      const capacidade = modeloAtual.colunas * modeloAtual.linhas_por_folha;
      qtdFolhas = Math.ceil((qtdEtiquetas + (Number(saltar) || 0)) / capacidade);
    }
    return { qtdProdutos, qtdEtiquetas, qtdFolhas };
  }, [linhas, modeloAtual, saltar]);

  const selecionarNf = useCallback(async () => {
    if (!conn) return;
    if (!numNf.trim() || !serieNf.trim() || !fornecedor) {
      feedback.showWarning("Informe NF, Série e Fornecedor.");
      return;
    }
    setLoadingNf(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const url = `${base}/api/etiqueta-produto/nf?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}` +
        `&num_nf=${encodeURIComponent(numNf.trim())}&serie_nf=${encodeURIComponent(serieNf.trim())}&fornecedor=${encodeURIComponent(fornecedor.codigo_int)}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao buscar nota fiscal."); return; }
      const novas: LinhaGrid[] = (j.itens || []).map((it: EtiquetaItem) => ({
        ...it, imp: true, num_nf: numNf.trim(), entrada: j.data_mov, fornecedor_nome: fornecedor.nome,
      }));
      setLinhas((prev) => [...prev, ...novas]);
      feedback.showSuccess(`${novas.length} item(ns) adicionado(s) da NF ${numNf.trim()}.`);
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoadingNf(false);
    }
  }, [conn, numNf, serieNf, fornecedor, feedback]);

  const adicionarManual = useCallback(async () => {
    if (!conn) return;
    if (!termoProduto.trim()) { feedback.showWarning("Informe o código do produto."); return; }
    setLoadingManual(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&termo=${encodeURIComponent(termoProduto.trim())}`;
      const r = await fetch(`${base}/api/etiqueta-produto/produto?${qs}`);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Produto não encontrado."); return; }
      const p = j.produto;
      if (p.tem_grade) {
        const rg = await fetch(`${base}/api/etiqueta-produto/grade?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&codigo_int=${encodeURIComponent(p.codigo_int)}`);
        const jg = await rg.json();
        if (jg?.success && (jg.grade || []).length > 0) {
          setGrade(jg.grade);
          setGradeQtds({});
          return;
        }
      }
      const descricao = usarDescricaoNfce && p.descricao_pdv ? p.descricao_pdv : p.descricao;
      const nova: LinhaGrid = {
        imp: true, codigo_int: p.codigo_int, codigo_fab: p.codigo_fab, descricao,
        codigo_bar: p.codigo_bar, p_venda: p.p_venda, quant: Number(quant) || 1,
      };
      setLinhas((prev) => [...prev, nova]);
      setTermoProduto("");
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoadingManual(false);
    }
  }, [conn, termoProduto, quant, usarDescricaoNfce, feedback]);

  const adicionarGrade = useCallback(() => {
    if (!grade) return;
    const novas: LinhaGrid[] = [];
    for (const cel of grade) {
      const q = Number(gradeQtds[cel.codigo_int] || 0);
      if (q > 0) {
        novas.push({
          imp: true, codigo_int: cel.codigo_int, codigo_fab: cel.codigo_fab,
          descricao: cel.descricao, codigo_bar: cel.codigo_bar, p_venda: cel.p_venda, quant: q,
        });
      }
    }
    if (novas.length === 0) { feedback.showWarning("Informe ao menos uma quantidade na grade."); return; }
    setLinhas((prev) => [...prev, ...novas]);
    setGrade(null);
    setGradeQtds({});
    setTermoProduto("");
  }, [grade, gradeQtds, feedback]);

  const toggleImp = (idx: number) => {
    setLinhas((prev) => prev.map((l, i) => (i === idx ? { ...l, imp: !l.imp } : l)));
  };
  const marcarTodos = () => setLinhas((prev) => prev.map((l) => ({ ...l, imp: true })));
  const desmarcarTodos = () => setLinhas((prev) => prev.map((l) => ({ ...l, imp: false })));
  const excluirLinha = (idx: number) => setLinhas((prev) => prev.filter((_, i) => i !== idx));
  const limparTodos = () => setLinhas([]);

  const gravarMargem = useCallback(async () => {
    if (!conn || !modeloAtual) return;
    if (modeloAtual.formato !== "grade_laser") { feedback.showWarning("Este modelo não usa margem configurável."); return; }
    setGravandoMargem(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const url = `${base}/api/etiqueta-produto/modelos/${modeloAtual.codigo}/margem?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ margem_lateral: Number(margemLateral) || 0, margem_superior: Number(margemSuperior) || 0 }),
      });
      const j = await r.json();
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao gravar configurações.")); return; }
      feedback.showSuccess(j.message || "Configurações gravadas!");
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setGravandoMargem(false);
    }
  }, [conn, modeloAtual, margemLateral, margemSuperior, feedback]);

  const imprimir = useCallback(async () => {
    if (!modeloAtual) return;
    const marcadas = linhas.filter((l) => l.imp);
    if (marcadas.length === 0) { feedback.showWarning("Marque ao menos um item pra imprimir."); return; }
    setImprimindo(true);
    try {
      await imprimirEtiquetas(modeloAtual, marcadas, Number(saltar) || 0);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    } finally {
      setImprimindo(false);
    }
  }, [modeloAtual, linhas, saltar, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (linhas.length === 0) return;
    exportSheetsToXlsx("etiquetas-de-produto", [
      {
        name: "Etiquetas",
        rows: linhas.map((l) => ({
          Imp: l.imp ? "X" : "", "Núm NF": l.num_nf || "", Entrada: l.entrada || "", Fornecedor: l.fornecedor_nome || "",
          "Código Fabr": l.codigo_fab, Descrição: l.descricao, Quant: l.quant, "Código Barra": l.codigo_bar,
        })),
      },
    ]);
  }, [linhas]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="etiqueta-produto-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="etqp-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Etiquetas de Produto</Text>
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)} color={colors.onBrandPrimary} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          {/* Origem por NF */}
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Etiqueta a partir de Nota Fiscal de Entrada</Text>
            <View style={styles.rowFields}>
              <View style={{ width: 110 }}>
                <Text style={styles.fieldLabel}>NF Entrada</Text>
                <TextInput value={numNf} onChangeText={setNumNf} keyboardType="numeric" style={styles.input} testID="etqp-num-nf" />
              </View>
              <View style={{ width: 90 }}>
                <Text style={styles.fieldLabel}>Série</Text>
                <TextInput value={serieNf} onChangeText={setSerieNf} style={styles.input} testID="etqp-serie-nf" />
              </View>
              <View style={{ flexGrow: 1, minWidth: 220 }}>
                <Text style={styles.fieldLabel}>Fornecedor</Text>
                <Pressable onPress={() => setFornOpen(true)} style={styles.searchField} testID="etqp-fornecedor-abrir">
                  <Ionicons name="search" size={14} color={colors.muted} />
                  <Text style={styles.searchFieldText} numberOfLines={1}>
                    {fornecedor ? fornecedor.nome : "Buscar fornecedor..."}
                  </Text>
                </Pressable>
              </View>
              <Pressable onPress={selecionarNf} disabled={loadingNf} style={[styles.actionBtn, loadingNf && { opacity: 0.7 }]} testID="etqp-selecionar-nf">
                {loadingNf ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : (
                  <>
                    <Ionicons name="add-circle-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Selecionar</Text>
                  </>
                )}
              </Pressable>
            </View>
            <Text style={styles.subMeta}>
              Produtos marcados: {stats.qtdProdutos} · Etiquetas: {stats.qtdEtiquetas}
              {stats.qtdFolhas !== null ? ` · Folhas estimadas: ${stats.qtdFolhas}` : ""}
            </Text>
          </View>

          {/* Adição manual */}
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Adicionar produto avulso</Text>
            {!grade ? (
              <>
                <View style={styles.rowFields}>
                  <View style={{ flexGrow: 1, minWidth: 200 }}>
                    <Text style={styles.fieldLabel}>Código do Produto</Text>
                    <View style={styles.searchFieldRow}>
                      <TextInput
                        value={termoProduto} onChangeText={setTermoProduto} style={[styles.input, { flex: 1 }]}
                        placeholder="Código interno, fábrica ou barras" testID="etqp-termo-produto"
                      />
                      <Pressable onPress={() => setProdOpen(true)} style={styles.iconBtnInline} testID="etqp-produto-buscar">
                        <Ionicons name="search" size={16} color={colors.brandPrimary} />
                      </Pressable>
                    </View>
                  </View>
                  <View style={{ width: 90 }}>
                    <Text style={styles.fieldLabel}>Quant</Text>
                    <TextInput value={quant} onChangeText={setQuant} keyboardType="numeric" style={styles.input} testID="etqp-quant" />
                  </View>
                  <Pressable onPress={adicionarManual} disabled={loadingManual} style={[styles.actionBtn, loadingManual && { opacity: 0.7 }]} testID="etqp-adicionar-manual">
                    {loadingManual ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : (
                      <>
                        <Ionicons name="add-circle-outline" size={15} color={colors.brandPrimary} />
                        <Text style={styles.actionBtnText}>Adicionar à Lista</Text>
                      </>
                    )}
                  </Pressable>
                </View>
                <Pressable onPress={() => setUsarDescricaoNfce((v) => !v)} style={styles.checkRow} testID="etqp-usar-nfce">
                  <Ionicons name={usarDescricaoNfce ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.checkLabel}>Usar descrição NFCe</Text>
                </Pressable>
              </>
            ) : (
              <View>
                <Text style={styles.subMeta}>Produto com variação de Cor/Tamanho — informe a quantidade de cada combinação:</Text>
                {grade.map((cel) => (
                  <View key={cel.codigo_int} style={styles.gradeRow}>
                    <Text style={styles.gradeLabel} numberOfLines={1}>{cel.cor_descricao} — {cel.tamanho}</Text>
                    <TextInput
                      value={gradeQtds[cel.codigo_int] || ""}
                      onChangeText={(v) => setGradeQtds((prev) => ({ ...prev, [cel.codigo_int]: v }))}
                      keyboardType="numeric" style={[styles.input, { width: 70 }]}
                      testID={`etqp-grade-${cel.codigo_int}`}
                    />
                  </View>
                ))}
                <View style={styles.actionsRow}>
                  <Pressable onPress={adicionarGrade} style={styles.actionBtn} testID="etqp-adicionar-grade">
                    <Ionicons name="add-circle-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Adicionar Grade</Text>
                  </Pressable>
                  <Pressable onPress={() => { setGrade(null); setGradeQtds({}); }} style={styles.actionBtn} testID="etqp-cancelar-grade">
                    <Ionicons name="close-circle-outline" size={15} color={colors.muted} />
                    <Text style={[styles.actionBtnText, { color: colors.muted }]}>Cancelar</Text>
                  </Pressable>
                </View>
              </View>
            )}
          </View>

          {/* Configuração de Etiqueta */}
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Configuração de Etiqueta</Text>
            <View style={{ maxWidth: 420 }}>
              <Text style={styles.fieldLabel}>Modelo Etiqueta</Text>
              <SelectField
                value={modeloCodigo} onChange={(v) => setModeloCodigo(Number(v))} options={modeloOpts}
                placeholder="Selecione" modalTitle="Modelo de Etiqueta" compactWeb testID="etqp-modelo"
              />
            </View>
            {modeloAtual?.especificacao ? <Text style={styles.subMeta}>{modeloAtual.especificacao}</Text> : null}
            {modeloAtual?.formato === "termica" ? (
              <Text style={styles.avisoTermica}>
                Este modelo é para impressora térmica dedicada e ainda não imprime nesta versão — veja o ícone de Ajuda (i) acima.
              </Text>
            ) : null}

            {modeloAtual?.formato === "grade_laser" ? (
              <View style={styles.rowFields}>
                <View style={{ width: 130 }}>
                  <Text style={styles.fieldLabel}>Margem Lateral (Cm)</Text>
                  <TextInput value={margemLateral} onChangeText={setMargemLateral} keyboardType="numeric" style={styles.input} testID="etqp-margem-lateral" />
                </View>
                <View style={{ width: 130 }}>
                  <Text style={styles.fieldLabel}>Margem Superior (Cm)</Text>
                  <TextInput value={margemSuperior} onChangeText={setMargemSuperior} keyboardType="numeric" style={styles.input} testID="etqp-margem-superior" />
                </View>
                <Pressable onPress={gravarMargem} disabled={gravandoMargem} style={[styles.actionBtn, gravandoMargem && { opacity: 0.7 }]} testID="etqp-gravar-margem">
                  {gravandoMargem ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : (
                    <>
                      <Ionicons name="save-outline" size={15} color={colors.brandPrimary} />
                      <Text style={styles.actionBtnText}>Gravar</Text>
                    </>
                  )}
                </Pressable>
              </View>
            ) : null}

            <View style={{ width: 160 }}>
              <Text style={styles.fieldLabel}>Nº Etiquetas a Saltar</Text>
              <TextInput value={saltar} onChangeText={setSaltar} keyboardType="numeric" style={styles.input} testID="etqp-saltar" />
            </View>
          </View>

          {/* Grid */}
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <View style={styles.actionsRow}>
              <Pressable onPress={marcarTodos} style={styles.actionBtn} testID="etqp-marcar-todos">
                <Text style={styles.actionBtnText}>Marcar Todos</Text>
              </Pressable>
              <Pressable onPress={desmarcarTodos} style={styles.actionBtn} testID="etqp-desmarcar-todos">
                <Text style={styles.actionBtnText}>Desmarcar Todos</Text>
              </Pressable>
              <Pressable onPress={imprimir} disabled={imprimindo} style={[styles.searchBtn, imprimindo && { opacity: 0.85 }]} testID="etqp-imprimir">
                {imprimindo ? <ActivityIndicator size="small" color={colors.onBrandPrimary} /> : (
                  <>
                    <Ionicons name="print-outline" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Imprimir</Text>
                  </>
                )}
              </Pressable>
              <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="etqp-planilha">
                <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                <Text style={styles.actionBtnText}>Gerar Planilha</Text>
              </Pressable>
              <Pressable onPress={limparTodos} style={styles.actionBtn} testID="etqp-limpar-todos">
                <Ionicons name="trash-outline" size={15} color={colors.error} />
                <Text style={[styles.actionBtnText, { color: colors.error }]}>Limpar Todos</Text>
              </Pressable>
            </View>

            {linhas.length === 0 ? (
              <Text style={styles.empty}>Nenhum item na lista — selecione uma NF ou adicione um produto avulso.</Text>
            ) : linhas.map((l, idx) => (
              <View key={idx} style={styles.row}>
                <Pressable onPress={() => toggleImp(idx)} hitSlop={8} testID={`etqp-imp-${idx}`}>
                  <Ionicons name={l.imp ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                </Pressable>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowLabel} numberOfLines={1}>{l.descricao}</Text>
                  <Text style={styles.rowMeta}>
                    {l.codigo_fab || l.codigo_int}{l.num_nf ? ` · NF ${l.num_nf} (${l.fornecedor_nome})` : " · Avulso"} · {brl(l.p_venda)}
                  </Text>
                </View>
                <Text style={styles.rowQtd}>Qtd {l.quant}</Text>
                <Pressable onPress={() => excluirLinha(idx)} hitSlop={8} testID={`etqp-excluir-${idx}`}>
                  <Ionicons name="close-circle-outline" size={20} color={colors.muted} />
                </Pressable>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>

      <FornecedorSearchModal
        visible={fornOpen} onClose={() => setFornOpen(false)}
        term={fornTerm} setTerm={setFornTerm} loading={fornLoading} results={fornResults}
        onPick={(f) => { setFornecedor(f); setFornOpen(false); }}
      />
      <ProdutoSearchModal
        visible={prodOpen} onClose={() => setProdOpen(false)}
        term={prodTerm} setTerm={setProdTerm} loading={prodLoading} results={prodResults}
        onPick={(p) => { setTermoProduto(p.codigo); setProdOpen(false); }}
      />
      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Etiquetas de Produto" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 16, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md, gap: spacing.sm, marginBottom: spacing.sm,
  },
  cardWeb: WEB_FILTER_CARD,
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  rowFields: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "flex-end" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    height: 40, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  searchField: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, height: 40,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  searchFieldText: { flex: 1, fontSize: 13, color: colors.onSurface },
  searchFieldRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  iconBtnInline: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.surface,
  },
  checkRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  checkLabel: { fontSize: 13, color: colors.onSurface },
  subMeta: { fontSize: 11, color: colors.muted },
  avisoTermica: { fontSize: 12, color: colors.warning, fontWeight: "600" },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  actionBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  actionBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 12 },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  searchBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  gradeRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 4, gap: spacing.sm },
  gradeLabel: { fontSize: 12, color: colors.onSurface, flex: 1 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 8, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface },
  rowMeta: { fontSize: 10, color: colors.muted, marginTop: 2 },
  rowQtd: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 12, marginBottom: 12 },
});

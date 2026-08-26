// Curva ABC e Estoques (Transações > Gestão de Compras > Compra). Legado:
// `FrmCurvaABC.frm`. Duas ações independentes — ver
// backend/services/curva_abc_service.py para as fórmulas exatas replicadas
// do legado (classificação por quantidade de itens proporcional à faixa,
// não o corte 80/20 clássico; fórmulas de estoque mínimo/ressuprimento/
// máximo) e PENDENCIAS.md > "Gestão de Compras" para o racional completo.
import { useCallback, useEffect, useRef, useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import NiveisModal from "@/src/components/NiveisModal";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { curvaAbcConfigKey, loadCurvaAbcConfig, saveCurvaAbcConfig } from "@/src/utils/storage/curvaAbcConfig";
import { apiSend } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { styles as ps } from "@/src/components/pedido/styles";

type Faixa = { curva: string; percentual: string };
type GerarResultItem = { codigo_int: string; descricao: string; total: number; curva: string; percentual_acumulado: number };
type ReprocResultItem = {
  codigo_int: string; descricao: string; consumo_medio_mensal: number; tempo_reposicao: number;
  estoque_minimo_anterior: number; estoque_minimo_atual: number;
  estoque_ressuprimento_anterior: number; estoque_ressuprimento_atual: number;
  estoque_maximo_anterior: number; estoque_maximo_atual: number;
};

function qtyFmt(n: number): string {
  return (n || 0).toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function focusNext(testID: string) {
  document.querySelector<HTMLInputElement>(`[data-testid="${testID}"]`)?.focus();
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

// Meses de calendário completos entre duas datas ISO (yyyy-mm-dd) — usado
// pra validar o período mínimo de 6 meses (Curva ABC) e pros presets de
// período (6/12/24 meses).
function monthsBetween(iniIso: string, fimIso: string): number {
  const [iy, im, id] = iniIso.split("-").map(Number);
  const [fy, fm, fd] = fimIso.split("-").map(Number);
  let months = (fy - iy) * 12 + (fm - im);
  if (fd < id) months -= 1;
  return months;
}

function isoMinusMonths(baseIso: string, months: number): string {
  const [y, m, d] = baseIso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  date.setUTCMonth(date.getUTCMonth() - months);
  return date.toISOString().slice(0, 10);
}

const PERIODO_PRESETS = [6, 12, 24];

// "Modo Didático" (CLAUDE.md) — ícone único de Ajuda no cabeçalho, reúne a
// explicação de todos os botões/campos não-óbvios das 2 seções desta tela,
// em vez de tooltip espalhado por botão. Reaproveita o mesmo
// `AjudaPedidoModal` genérico já usado em Pedido Bar/Geral/Tela Principal —
// pedido explícito do usuário, 2026-07-20.
const CURVA_ABC_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Gerar Curva ABC",
    texto: "Classifica os produtos em faixas (A, B, C…) de acordo com o quanto cada um vendeu no período escolhido — os mais vendidos caem na primeira faixa, os seguintes na próxima, e assim por diante. Essa classificação é usada em relatórios e filtros de outras telas (ex.: Ressuprimento).",
    icon: { lib: "ion", name: "podium-outline" },
  },
  {
    titulo: "Presets de período (6/12/24 meses)",
    texto: "Preenche De/Até automaticamente contando pra trás a partir de hoje. O período mínimo aceito é sempre 6 meses — períodos mais curtos dão uma classificação e um consumo médio pouco confiáveis.",
    icon: { lib: "ion", name: "calendar-outline" },
  },
  {
    titulo: "Tipo de classificação (Por Quantidade / Por Valor Vendido)",
    texto: "Por Quantidade classifica pelo número de unidades vendidas; Por Valor Vendido classifica pelo total em R$. Um mesmo produto pode cair em faixas diferentes nos dois critérios — por exemplo, um item barato e muito vendido pode ser Curva A por quantidade, mas B ou C por valor.",
    icon: { lib: "ion", name: "swap-horizontal-outline" },
  },
  {
    titulo: "Nível (nas duas seções)",
    texto: "Restringe a classificação (ou o reprocessamento) a um grupo específico de produtos, em vez de todo o catálogo. Deixe em branco para considerar todos.",
    icon: { lib: "ion", name: "layers-outline" },
  },
  {
    titulo: "Faixas da curva",
    texto: "Define quantas faixas existem (A, B, C…) e que percentual de produtos cai em cada uma. A soma dos percentuais precisa fechar em 100% — o sistema avisa se ainda não fechou.",
    icon: { lib: "ion", name: "options-outline" },
  },
  {
    titulo: "Processar Atualização de Estoques",
    texto: "Recalcula, com base nas vendas do período e no prazo de entrega de cada fornecedor, os parâmetros de estoque de cada produto — quanto manter no mínimo, quando comprar de novo (ressuprimento) e o teto recomendado (máximo). É essa atualização que mantém os alertas de estoque (Tela Principal) e a lista de Ressuprimento confiáveis.",
    icon: { lib: "ion", name: "refresh-outline" },
  },
  {
    titulo: "Grau de Atendimento (%)",
    texto: "Fator de segurança do cálculo: 100% mantém o mesmo ritmo médio de vendas; valores acima de 100% guardam estoque extra, reduzindo o risco de faltar produto em picos de venda, ao custo de manter mais capital parado em estoque.",
    icon: { lib: "ion", name: "shield-checkmark-outline" },
  },
  {
    titulo: "O que atualizar (checkboxes)",
    texto: "Escolha quais campos o reprocessamento deve sobrescrever — Estoque Mínimo, Ressuprimento, Máximo e/ou Consumo Médio Mensal. Desmarque o que não quiser recalcular desta vez (ex.: já ajustou o Máximo manualmente e não quer perder esse ajuste).",
    icon: { lib: "ion", name: "checkbox-outline" },
  },
];

export default function CurvaAbcScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Curva ABC e Estoques está disponível apenas no web."
        testID="curva-abc-web-only"
      />
    );
  }

  if (!moduleOn("Curva_abc")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Curva ABC/Compras está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="curva-abc-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);

  // Seção 1 — Gerar Curva ABC
  // Período padrão 12 meses (achado 2026-08-22, varredura de design/UI —
  // as outras 15 telas de relatório da mesma leva já nascem com período
  // preenchido; esta e "Reprocessar Estoques" abaixo nasciam em branco,
  // destoando do padrão). 12 meses = ano cheio, evita viés de sazonalidade
  // numa análise de Curva ABC.
  const [g1DataIni, setG1DataIni] = useState<string | null>(() => isoMinusMonths(todayIso(), 12));
  const [g1DataFim, setG1DataFim] = useState<string | null>(() => todayIso());
  const [g1Preset, setG1Preset] = useState<number | null>(12);
  const [g1Tipo, setG1Tipo] = useState<"financeira" | "quantidade">("quantidade");
  const [g1Nivel, setG1Nivel] = useState<{ codigo: string; label: string } | null>(null);
  const [g1NivelModalOpen, setG1NivelModalOpen] = useState(false);
  const [faixas, setFaixas] = useState<Faixa[]>([
    { curva: "A", percentual: "20" },
    { curva: "B", percentual: "30" },
    { curva: "C", percentual: "50" },
  ]);
  const [gerando, setGerando] = useState(false);
  const [g1Resultado, setG1Resultado] = useState<GerarResultItem[] | null>(null);
  const [g1TotalGeral, setG1TotalGeral] = useState(0);

  // Seção 2 — Reprocessar Estoques (mesmo achado da Seção 1 acima)
  const [r1DataIni, setR1DataIni] = useState<string | null>(() => isoMinusMonths(todayIso(), 12));
  const [r1DataFim, setR1DataFim] = useState<string | null>(() => todayIso());
  const [r1Preset, setR1Preset] = useState<number | null>(12);
  const [grauAtendimento, setGrauAtendimento] = useState("100");
  const [r1Nivel, setR1Nivel] = useState<{ codigo: string; label: string } | null>(null);
  const [r1NivelModalOpen, setR1NivelModalOpen] = useState(false);
  const [atualizarMinimo, setAtualizarMinimo] = useState(true);
  const [atualizarRessuprimento, setAtualizarRessuprimento] = useState(true);
  const [atualizarMaximo, setAtualizarMaximo] = useState(true);
  const [atualizarConsumo, setAtualizarConsumo] = useState(true);
  const [reprocessando, setReprocessando] = useState(false);
  const [r1Resultado, setR1Resultado] = useState<ReprocResultItem[] | null>(null);

  const [hoverInfo, setHoverInfo] = useState<string | null>(null);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const somaFaixas = faixas.reduce((s, f) => s + (parseFloat(f.percentual.replace(",", ".")) || 0), 0);
  const somaOk = Math.round(somaFaixas * 100) / 100 === 100;

  const podeGerar = can("CURVA_ABC.GERAR");
  const podeReprocessar = can("CURVA_ABC.REPROCESSAR");

  // Restaura/grava a última configuração de opções (tipo, nível, faixas,
  // grau de atendimento, o que atualizar) por empresa+banco — pedido
  // explícito do usuário, 2026-07-20 ("salve as configurações de opções
  // setadas, inclusive faixas para um próximo processamento"). Mesmo
  // padrão de app/pedidos.tsx — datas/preset de período NÃO são
  // restauradas, só as opções de configuração propriamente ditas.
  const configRestauradoRef = useRef(false);
  const storageKeyRef = useRef<string | null>(null);

  const ensureConn = useCallback(async (): Promise<Connection | null> => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa);
    if (c) setConn(c);
    return c || null;
  }, [conn, router]);

  useEffect(() => {
    (async () => {
      const c = await ensureConn();
      if (!c || configRestauradoRef.current) return;
      configRestauradoRef.current = true;
      const key = curvaAbcConfigKey(c.empresa, c.banco);
      storageKeyRef.current = key;
      const saved = await loadCurvaAbcConfig(key);
      if (saved) {
        setG1Tipo(saved.g1Tipo);
        setG1Nivel(saved.g1NivelCodigo ? { codigo: saved.g1NivelCodigo, label: saved.g1NivelLabel || "" } : null);
        if (saved.faixas?.length) setFaixas(saved.faixas);
        setGrauAtendimento(saved.grauAtendimento || "100");
        setR1Nivel(saved.r1NivelCodigo ? { codigo: saved.r1NivelCodigo, label: saved.r1NivelLabel || "" } : null);
        setAtualizarMinimo(saved.atualizarMinimo);
        setAtualizarRessuprimento(saved.atualizarRessuprimento);
        setAtualizarMaximo(saved.atualizarMaximo);
        setAtualizarConsumo(saved.atualizarConsumo);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!configRestauradoRef.current || !storageKeyRef.current) return;
    saveCurvaAbcConfig(storageKeyRef.current, {
      g1Tipo, g1NivelCodigo: g1Nivel?.codigo ?? null, g1NivelLabel: g1Nivel?.label ?? null,
      faixas, grauAtendimento,
      r1NivelCodigo: r1Nivel?.codigo ?? null, r1NivelLabel: r1Nivel?.label ?? null,
      atualizarMinimo, atualizarRessuprimento, atualizarMaximo, atualizarConsumo,
    });
  }, [g1Tipo, g1Nivel, faixas, grauAtendimento, r1Nivel, atualizarMinimo, atualizarRessuprimento, atualizarMaximo, atualizarConsumo]);

  const addFaixa = useCallback(() => {
    setFaixas((prev) => [...prev, { curva: "", percentual: "" }]);
  }, []);

  const removeFaixa = useCallback((idx: number) => {
    setFaixas((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const updateFaixa = useCallback((idx: number, field: "curva" | "percentual", value: string) => {
    setFaixas((prev) => prev.map((f, i) => (i === idx ? { ...f, [field]: value } : f)));
  }, []);

  const handleGerar = useCallback(async () => {
    const c = await ensureConn();
    if (!c) return;
    if (!g1DataIni || !g1DataFim) { fb.showError("Defina o período (De/Até)."); return; }
    if (monthsBetween(g1DataIni, g1DataFim) < 6) {
      fb.showError("O período mínimo para gerar a Curva ABC é de 6 meses — um período mais curto dá uma classificação pouco confiável.");
      return;
    }
    if (!somaOk) { fb.showError("A soma dos percentuais das faixas precisa totalizar 100%."); return; }
    fb.showConfirm(
      `Confirma gerar a Curva ABC (${g1Tipo === "financeira" ? "por valor" : "por quantidade"}) para o período de ${new Date(g1DataIni + "T00:00:00").toLocaleDateString("pt-BR")} a ${new Date(g1DataFim + "T00:00:00").toLocaleDateString("pt-BR")}? Isso vai sobrescrever a classificação atual dos produtos afetados.`,
      async () => {
        setGerando(true);
        setG1Resultado(null);
        try {
          const r = await apiSend(c, "/api/curva-abc/gerar", "POST", {
            data_ini: g1DataIni, data_fim: g1DataFim, tipo: g1Tipo,
            faixas: faixas.filter((f) => f.curva.trim()).map((f) => ({
              curva: f.curva.trim().toUpperCase(), percentual: parseFloat(f.percentual.replace(",", ".")) || 0,
            })),
            nivel: g1Nivel?.codigo || undefined,
            ...auditCtx,
          });
          if (r?.success) {
            setG1Resultado(r.items || []);
            setG1TotalGeral(r.total_geral || 0);
            fb.showSuccess(`Curva ABC gerada para ${r.total_itens} produto(s).`);
          } else {
            fb.showError(r?.message || "Não foi possível gerar a Curva ABC.");
          }
        } finally {
          setGerando(false);
        }
      },
    );
  }, [ensureConn, g1DataIni, g1DataFim, somaOk, g1Tipo, faixas, g1Nivel, auditCtx, fb]);

  const handleReprocessar = useCallback(async () => {
    const c = await ensureConn();
    if (!c) return;
    if (!r1DataIni || !r1DataFim) { fb.showError("Defina o período (De/Até)."); return; }
    if (monthsBetween(r1DataIni, r1DataFim) < 6) {
      fb.showError("O período mínimo para processar a atualização de estoques é de 6 meses — um período mais curto dá um consumo médio pouco confiável.");
      return;
    }
    const grau = parseFloat(grauAtendimento.replace(",", "."));
    if (!grau || grau <= 0) { fb.showError("Informe o Grau de Atendimento."); return; }
    if (!atualizarMinimo && !atualizarRessuprimento && !atualizarMaximo && !atualizarConsumo) {
      fb.showError("Marque ao menos um campo para atualizar.");
      return;
    }
    fb.showConfirm(
      "Confirma processar a atualização de estoques para o período selecionado? Isso vai sobrescrever os campos marcados abaixo.",
      async () => {
        setReprocessando(true);
        setR1Resultado(null);
        try {
          const r = await apiSend(c, "/api/curva-abc/reprocessar-estoques", "POST", {
            data_ini: r1DataIni, data_fim: r1DataFim, grau_atendimento: grau,
            nivel: r1Nivel?.codigo || undefined,
            atualizar_minimo: atualizarMinimo, atualizar_ressuprimento: atualizarRessuprimento,
            atualizar_maximo: atualizarMaximo, atualizar_consumo: atualizarConsumo,
            ...auditCtx,
          });
          if (r?.success) {
            setR1Resultado(r.items || []);
            fb.showSuccess(`Estoques recalculados para ${(r.items || []).length} produto(s).`);
          } else {
            fb.showError(r?.message || "Não foi possível processar a atualização de estoques.");
          }
        } finally {
          setReprocessando(false);
        }
      },
    );
  }, [ensureConn, r1DataIni, r1DataFim, grauAtendimento, r1Nivel, atualizarMinimo, atualizarRessuprimento, atualizarMaximo, atualizarConsumo, auditCtx, fb]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="curva-abc-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Curva ABC e Estoques</Text>
        <Pressable onPress={() => setAjudaOpen(true)} hitSlop={12} style={styles.back} testID="curva-abc-ajuda-button">
          <Ionicons name="information-circle-outline" size={22} color={colors.onBrandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          {/* Seção 1 — Gerar Curva ABC */}
          <View style={styles.card}>
            <View style={styles.guideRow}>
              <Ionicons name="bulb-outline" size={20} color={colors.brandPrimary} />
              <Text style={styles.guideText}>
                <Text style={styles.guideBold}>Passo 1 — Classifique seus produtos.</Text> Escolha um período de
                vendas, o tipo de classificação e as faixas (A, B, C…). Os produtos mais vendidos no período viram
                Curva A, os seguintes B, e assim por diante — quanto maior o percentual da faixa, mais produtos
                entram nela.
              </Text>
            </View>

            <View style={styles.sectionTitleRow}>
              <Text style={styles.sectionTitle}>Gerar Curva ABC</Text>
              <View style={styles.chipsRow}>
                {PERIODO_PRESETS.map((m) => (
                  <Pressable
                    key={m}
                    onPress={() => {
                      const fim = todayIso();
                      const ini = isoMinusMonths(fim, m);
                      setG1DataIni(ini); setG1DataFim(fim); setG1Preset(m);
                    }}
                    style={[styles.chip, g1Preset === m && styles.chipSel]}
                    testID={`curva-abc-preset-${m}`}
                  >
                    <Text style={[styles.chipText, g1Preset === m && styles.chipTextSel]}>{m} meses</Text>
                  </Pressable>
                ))}
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Período de</Text>
                <WebDateField
                  value={g1DataIni}
                  onChange={(v) => { setG1DataIni(v || null); if (v) setG1DataFim(v); setG1Preset(null); }}
                  testID="curva-abc-g1-data-ini"
                  onSubmitEditing={() => focusNext("curva-abc-g1-data-fim")}
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>até</Text>
                <WebDateField
                  value={g1DataFim}
                  onChange={(v) => { setG1DataFim(v); setG1Preset(null); }}
                  testID="curva-abc-g1-data-fim"
                />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Tipo de classificação</Text>
                <View style={styles.chipsRow}>
                  <Pressable
                    onPress={() => setG1Tipo("quantidade")}
                    style={[styles.chip, g1Tipo === "quantidade" && styles.chipSel]}
                    testID="curva-abc-tipo-quantidade"
                  >
                    <Text style={[styles.chipText, g1Tipo === "quantidade" && styles.chipTextSel]}>Por Quantidade</Text>
                  </Pressable>
                  <Pressable
                    onPress={() => setG1Tipo("financeira")}
                    style={[styles.chip, g1Tipo === "financeira" && styles.chipSel]}
                    testID="curva-abc-tipo-financeira"
                  >
                    <Text style={[styles.chipText, g1Tipo === "financeira" && styles.chipTextSel]}>Por Valor Vendido</Text>
                  </Pressable>
                </View>
              </View>
            </View>

            <View style={styles.filterGroup}>
              <Text style={styles.label}>Nível (opcional — restringe a classificação a um grupo de produtos)</Text>
              {g1Nivel ? (
                <View style={styles.selectedChipRow}>
                  <View style={styles.selectedChip}>
                    <Text style={styles.selectedChipText} numberOfLines={1}>{g1Nivel.label}</Text>
                    <Pressable onPress={() => setG1Nivel(null)} hitSlop={6}>
                      <Ionicons name="close-circle" size={16} color={colors.onBrandPrimary} />
                    </Pressable>
                  </View>
                </View>
              ) : (
                <Pressable style={styles.pickerBtn} onPress={() => setG1NivelModalOpen(true)} testID="curva-abc-g1-nivel-btn">
                  <Ionicons name="layers-outline" size={16} color={colors.muted} />
                  <Text style={styles.pickerBtnText}>Todos os níveis</Text>
                </Pressable>
              )}
            </View>

            <View style={styles.filterGroup}>
              <View style={styles.faixasHeaderRow}>
                <Text style={styles.label}>Faixas da curva</Text>
                <View style={[styles.somaBadge, { backgroundColor: somaOk ? "#E9F5EF" : "#FBEAEA" }]}>
                  <Text style={[styles.somaBadgeText, { color: somaOk ? colors.success : colors.error }]}>
                    Soma: {somaFaixas}% {somaOk ? "✓" : "(precisa ser 100%)"}
                  </Text>
                </View>
              </View>
              {faixas.map((f, idx) => (
                <View key={idx} style={styles.faixaRow}>
                  <TextInput
                    style={[styles.input, styles.faixaCurva]}
                    value={f.curva}
                    onChangeText={(v) => updateFaixa(idx, "curva", v.toUpperCase().slice(0, 1))}
                    placeholder="A"
                    maxLength={1}
                    testID={`curva-abc-faixa-letra-${idx}`}
                  />
                  <TextInput
                    style={[styles.input, styles.faixaPercentual]}
                    value={f.percentual}
                    onChangeText={(v) => updateFaixa(idx, "percentual", v)}
                    placeholder="0"
                    keyboardType="numeric"
                    testID={`curva-abc-faixa-percentual-${idx}`}
                  />
                  <Text style={styles.pctSign}>%</Text>
                  <Pressable onPress={() => removeFaixa(idx)} style={ps.deleteBtn} testID={`curva-abc-faixa-remover-${idx}`}>
                    <Ionicons name="trash-outline" size={16} color={colors.error} />
                  </Pressable>
                </View>
              ))}
              <Pressable style={styles.addFaixaBtn} onPress={addFaixa} testID="curva-abc-add-faixa">
                <Ionicons name="add-circle-outline" size={16} color={colors.brandPrimary} />
                <Text style={styles.addFaixaText}>Adicionar faixa</Text>
              </Pressable>
            </View>

            {podeGerar ? (
              <View style={styles.toolbarRow}>
                <Pressable
                  style={[styles.actionBtn, gerando && { opacity: 0.6 }]}
                  onPress={handleGerar}
                  disabled={gerando}
                  testID="curva-abc-gerar-btn"
                >
                  <Text style={styles.actionBtnText}>{gerando ? "Gerando…" : "Gerar Curva ABC"}</Text>
                </Pressable>
              </View>
            ) : null}

            {g1Resultado ? (
              <View style={styles.resultBox}>
                <Text style={styles.hint}>
                  {g1Resultado.length} produto(s) classificado(s) · Total do período: {g1TotalGeral.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </Text>
                <ScrollView style={{ maxHeight: 280 }}>
                  {g1Resultado.map((it) => (
                    <View key={it.codigo_int} style={styles.itemRow}>
                      <View style={styles.curvaBadge}>
                        <Text style={styles.curvaBadgeText}>{it.curva}</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemTitle}>{it.codigo_int} — {it.descricao}</Text>
                        <Text style={styles.itemSub}>Total: {qtyFmt(it.total)} · Acumulado: {it.percentual_acumulado}%</Text>
                      </View>
                    </View>
                  ))}
                </ScrollView>
              </View>
            ) : null}
          </View>

          {/* Seção 2 — Reprocessar Estoques */}
          <View style={styles.card}>
            <View style={styles.guideRow}>
              <Ionicons name="bulb-outline" size={20} color={colors.brandPrimary} />
              <Text style={styles.guideText}>
                <Text style={styles.guideBold}>Passo 2 — Atualize os parâmetros de estoque.</Text> Com base nas
                vendas do período e no prazo de entrega de cada fornecedor, o sistema recalcula quanto estocar de
                cada produto: o mínimo antes de faltar, o ponto de comprar de novo (ressuprimento) e o máximo
                recomendado. Ajuste o Grau de Atendimento para dar mais ou menos folga de segurança.
              </Text>
            </View>

            <View style={styles.sectionTitleRow}>
              <Text style={styles.sectionTitle}>Processar Atualização de Estoques</Text>
              <View style={styles.chipsRow}>
                {PERIODO_PRESETS.map((m) => (
                  <Pressable
                    key={m}
                    onPress={() => {
                      const fim = todayIso();
                      const ini = isoMinusMonths(fim, m);
                      setR1DataIni(ini); setR1DataFim(fim); setR1Preset(m);
                    }}
                    style={[styles.chip, r1Preset === m && styles.chipSel]}
                    testID={`curva-abc-r1-preset-${m}`}
                  >
                    <Text style={[styles.chipText, r1Preset === m && styles.chipTextSel]}>{m} meses</Text>
                  </Pressable>
                ))}
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Período de</Text>
                <WebDateField
                  value={r1DataIni}
                  onChange={(v) => { setR1DataIni(v || null); if (v) setR1DataFim(v); setR1Preset(null); }}
                  testID="curva-abc-r1-data-ini"
                  onSubmitEditing={() => focusNext("curva-abc-r1-data-fim")}
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>até</Text>
                <WebDateField
                  value={r1DataFim}
                  onChange={(v) => { setR1DataFim(v); setR1Preset(null); }}
                  testID="curva-abc-r1-data-fim"
                />
              </View>
              <View style={styles.colTiny}>
                <View style={styles.labelWithInfo}>
                  <Text style={styles.label}>Grau Atend. (%)</Text>
                  <Pressable onHoverIn={() => setHoverInfo("grau")} onHoverOut={() => setHoverInfo(null)} hitSlop={6}>
                    <Ionicons name="information-circle-outline" size={13} color={colors.muted} />
                  </Pressable>
                  {hoverInfo === "grau" ? (
                    <View style={styles.tooltip}>
                      <Text style={styles.tooltipText}>Fator de segurança: 100% mantém o mesmo ritmo de vendas; acima disso, guarda mais estoque extra.</Text>
                    </View>
                  ) : null}
                </View>
                <TextInput style={styles.input} value={grauAtendimento} onChangeText={setGrauAtendimento} keyboardType="numeric" testID="curva-abc-grau-atendimento" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Nível (opcional)</Text>
                {r1Nivel ? (
                  <View style={styles.selectedChipRow}>
                    <View style={styles.selectedChip}>
                      <Text style={styles.selectedChipText} numberOfLines={1}>{r1Nivel.label}</Text>
                      <Pressable onPress={() => setR1Nivel(null)} hitSlop={6}>
                        <Ionicons name="close-circle" size={16} color={colors.onBrandPrimary} />
                      </Pressable>
                    </View>
                  </View>
                ) : (
                  <Pressable style={styles.pickerBtn} onPress={() => setR1NivelModalOpen(true)} testID="curva-abc-r1-nivel-btn">
                    <Ionicons name="layers-outline" size={16} color={colors.muted} />
                    <Text style={styles.pickerBtnText}>Todos os níveis</Text>
                  </Pressable>
                )}
              </View>
            </View>

            <View style={styles.filterGroup}>
              <Text style={styles.label}>O que atualizar</Text>
              <View style={styles.chipsRow}>
                <Pressable
                  onPress={() => setAtualizarMinimo((v) => !v)}
                  style={[styles.chip, atualizarMinimo && styles.chipSel]}
                  testID="curva-abc-check-minimo"
                >
                  <Ionicons name={atualizarMinimo ? "checkbox" : "square-outline"} size={14} color={atualizarMinimo ? "#fff" : colors.muted} />
                  <Text style={[styles.chipText, atualizarMinimo && styles.chipTextSel, { marginLeft: 4 }]}>Estoque Mínimo</Text>
                </Pressable>
                <Pressable
                  onPress={() => setAtualizarRessuprimento((v) => !v)}
                  style={[styles.chip, atualizarRessuprimento && styles.chipSel]}
                  testID="curva-abc-check-ressuprimento"
                >
                  <Ionicons name={atualizarRessuprimento ? "checkbox" : "square-outline"} size={14} color={atualizarRessuprimento ? "#fff" : colors.muted} />
                  <Text style={[styles.chipText, atualizarRessuprimento && styles.chipTextSel, { marginLeft: 4 }]}>Estoque Ressuprimento</Text>
                </Pressable>
                <Pressable
                  onPress={() => setAtualizarMaximo((v) => !v)}
                  style={[styles.chip, atualizarMaximo && styles.chipSel]}
                  testID="curva-abc-check-maximo"
                >
                  <Ionicons name={atualizarMaximo ? "checkbox" : "square-outline"} size={14} color={atualizarMaximo ? "#fff" : colors.muted} />
                  <Text style={[styles.chipText, atualizarMaximo && styles.chipTextSel, { marginLeft: 4 }]}>Estoque Máximo</Text>
                </Pressable>
                <Pressable
                  onPress={() => setAtualizarConsumo((v) => !v)}
                  style={[styles.chip, atualizarConsumo && styles.chipSel]}
                  testID="curva-abc-check-consumo"
                >
                  <Ionicons name={atualizarConsumo ? "checkbox" : "square-outline"} size={14} color={atualizarConsumo ? "#fff" : colors.muted} />
                  <Text style={[styles.chipText, atualizarConsumo && styles.chipTextSel, { marginLeft: 4 }]}>Consumo Médio Mensal</Text>
                </Pressable>
              </View>
            </View>

            {podeReprocessar ? (
              <View style={styles.toolbarRow}>
                <Pressable
                  style={[styles.actionBtn, reprocessando && { opacity: 0.6 }]}
                  onPress={handleReprocessar}
                  disabled={reprocessando}
                  testID="curva-abc-reprocessar-btn"
                >
                  <Text style={styles.actionBtnText}>{reprocessando ? "Processando…" : "Processar Atualização de Estoques"}</Text>
                </Pressable>
              </View>
            ) : null}

            {r1Resultado ? (
              <View style={styles.resultBox}>
                <Text style={styles.hint}>{r1Resultado.length} produto(s) recalculado(s).</Text>
                <ScrollView style={{ maxHeight: 280 }}>
                  {r1Resultado.map((it) => (
                    <View key={it.codigo_int} style={styles.itemRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemTitle}>{it.codigo_int} — {it.descricao}</Text>
                        <Text style={styles.itemSub}>
                          Consumo médio: {qtyFmt(it.consumo_medio_mensal)}/mês · Prazo reposição: {it.tempo_reposicao}d
                        </Text>
                        <Text style={styles.itemSub}>
                          Mínimo: {qtyFmt(it.estoque_minimo_anterior)} → {qtyFmt(it.estoque_minimo_atual)} ·
                          {" "}Ressup.: {qtyFmt(it.estoque_ressuprimento_anterior)} → {qtyFmt(it.estoque_ressuprimento_atual)} ·
                          {" "}Máximo: {qtyFmt(it.estoque_maximo_anterior)} → {qtyFmt(it.estoque_maximo_atual)}
                        </Text>
                      </View>
                    </View>
                  ))}
                </ScrollView>
              </View>
            ) : null}
          </View>
        </View>
      </ScrollView>

      <NiveisModal
        visible={g1NivelModalOpen}
        conn={conn}
        onClose={() => setG1NivelModalOpen(false)}
        onPick={(codigo, label) => { setG1Nivel(codigo ? { codigo, label } : null); setG1NivelModalOpen(false); }}
      />
      <NiveisModal
        visible={r1NivelModalOpen}
        conn={conn}
        onClose={() => setR1NivelModalOpen(false)}
        onPick={(codigo, label) => { setR1Nivel(codigo ? { codigo, label } : null); setR1NivelModalOpen(false); }}
      />

      <AjudaPedidoModal
        visible={ajudaOpen}
        onClose={() => setAjudaOpen(false)}
        titulo="Curva ABC e Estoques"
        itens={CURVA_ABC_AJUDA_ITENS}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, gap: spacing.sm, marginBottom: spacing.md },
  guideRow: {
    flexDirection: "row", gap: spacing.sm, alignItems: "flex-start",
    backgroundColor: colors.brandTertiary, borderRadius: radius.md,
    padding: spacing.md, marginBottom: 4,
  },
  guideText: { flex: 1, fontSize: 12.5, color: colors.onSurface, lineHeight: 18 },
  guideBold: { fontWeight: "700" },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  sectionTitleRow: { flexDirection: "row", alignItems: "center", justifyContent: "flex-start", flexWrap: "wrap", gap: spacing.md },
  filterGroup: { gap: 6 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  labelWithInfo: { flexDirection: "row", alignItems: "center", gap: 4, position: "relative" },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4, marginBottom: 6 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface,
  },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 220 },
  colNarrow: { width: 140 },
  colTiny: { width: 110 },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "center" },
  chip: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: 7, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: "#fff" },
  pickerBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    backgroundColor: colors.surface, paddingHorizontal: spacing.md, paddingVertical: 11,
  },
  pickerBtnText: { fontSize: 13, color: colors.muted },
  selectedChipRow: { flexDirection: "row" },
  selectedChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, maxWidth: 320,
  },
  selectedChipText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600", flexShrink: 1 },
  faixasHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  somaBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
  somaBadgeText: { fontSize: 11.5, fontWeight: "700" },
  faixaRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  faixaCurva: { width: 56, textAlign: "center", fontWeight: "700" },
  faixaPercentual: { width: 90 },
  pctSign: { fontSize: 13, color: colors.muted },
  addFaixaBtn: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", paddingVertical: 6 },
  addFaixaText: { fontSize: 12.5, fontWeight: "600", color: colors.brandPrimary },
  toolbarRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "center", marginTop: spacing.sm },
  actionBtn: {
    paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  actionBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  resultBox: { marginTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm },
  itemRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  itemTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  itemSub: { fontSize: 11.5, color: colors.muted, marginTop: 2 },
  curvaBadge: {
    width: 28, height: 28, borderRadius: radius.pill, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  curvaBadgeText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  tooltip: {
    position: "absolute", bottom: 22, left: 0, zIndex: 10,
    backgroundColor: colors.onSurface, borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 6, width: 220,
  },
  tooltipText: { color: "#fff", fontSize: 11, lineHeight: 15 },
});

// Gestão de Compras > Ressuprimento (Transações > Gestão de Compras).
// Legado: `FrmGesCom.frm`, aba "Ressuprimento". Ver
// backend/services/gestao_compras_service.py e PENDENCIAS.md > "Gestão de
// Compras" para o racional completo (prioridade real do cliente — "o que
// precisa comprar" — em vez do fluxo abandonado de Pedido de Compra).
import { useCallback, useEffect, useMemo, useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import NiveisModal from "@/src/components/NiveisModal";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, apiBase } from "@/src/utils/api";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { printHtml, escHtml } from "@/src/utils/printHtml";
import { fetchEmpresaHeader, buildReportHeaderHtml, REPORT_HEADER_CSS } from "@/src/utils/print-report-header";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { styles as ps } from "@/src/components/pedido/styles";

type Item = {
  curva_abc: string;
  curva_abc_fin: string;
  codigo_fab: string;
  codigo_int: string;
  descricao: string;
  qtd: number;
  consumo_medio_mensal: number;
  estoque_minimo: number;
  estoque_ressuprimento: number;
  estoque_maximo: number;
  prev_mes: number;
  prev_dia: number;
};

type Fornecedor = { codigo_int: number; nome: string; fantasia: string };

type Compra = {
  num_nf: number; data_mov: string | null; fornecedor: string;
  qtd: number; valor_unit: number; impostos_unit: number;
};

const ORDER_OPTIONS: { key: string; label: string }[] = [
  { key: "descricao", label: "Descrição" },
  { key: "estoque", label: "Estoque" },
  { key: "consumo", label: "Consumo" },
];

function qtyFmt(n: number): string {
  return (n || 0).toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function money(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Quantidade sugerida pro "Gerar Pedido de Compra": o quanto falta pra
// alcançar o nível de ressuprimento, nunca menos que 1 (produto zerado com
// ressuprimento configurado em 0, edge case raro, ainda pede ao menos 1
// unidade em vez de sugerir comprar zero).
function qtdSugerida(it: Item): number {
  return Math.max(1, Math.ceil(it.estoque_ressuprimento - it.qtd));
}

function statusFor(it: Item): { label: string; color: string; bg: string } {
  if (it.qtd <= 0) return { label: "Sem Estoque", color: colors.error, bg: "#FBEAEA" };
  if (it.qtd < it.estoque_minimo) return { label: "Crítico", color: colors.error, bg: "#FBEAEA" };
  if (it.qtd < it.estoque_ressuprimento) return { label: "Repor", color: colors.warning, bg: "#FBF1E4" };
  if (it.estoque_maximo > 0 && it.qtd > it.estoque_maximo) return { label: "Excesso", color: colors.muted, bg: colors.surfaceSecondary };
  return { label: "OK", color: colors.success, bg: "#E9F5EF" };
}

// Tipo de alerta vindo do card da Tela Principal (`?tipo=`) — pré-marca o
// chip de situação certo e já dispara a busca sozinho, sem o usuário
// precisar reconfigurar os filtros. Pedido explícito do usuário,
// 2026-07-20 ("ao clicar, levar para uma lista com filtros por... tipos").
type TipoAlerta = "minimo" | "ressuprimento" | "zerado";

export default function GestaoComprasRessuprimentoScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const fb = useFeedback();
  const auditCtx = useAuditContext();
  const params = useLocalSearchParams<{ tipo?: TipoAlerta }>();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Gestão de Compras está disponível apenas no web."
        testID="gestao-compras-ressuprimento-web-only"
      />
    );
  }

  if (!moduleOn("Curva_abc")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Curva ABC/Compras está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="gestao-compras-ressuprimento-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);

  const [curvasQtd, setCurvasQtd] = useState<string[]>([]);
  const [curvasFin, setCurvasFin] = useState<string[]>([]);
  const [filtroCurvaQtd, setFiltroCurvaQtd] = useState<string | null>(null);
  const [filtroCurvaFin, setFiltroCurvaFin] = useState<string | null>(null);

  const [fornecedor, setFornecedor] = useState<Fornecedor | null>(null);
  const [fornecedorModalOpen, setFornecedorModalOpen] = useState(false);
  const [fornecedorBusca, setFornecedorBusca] = useState("");
  const [fornecedorResultados, setFornecedorResultados] = useState<Fornecedor[]>([]);

  const [nivel, setNivel] = useState<{ codigo: string; label: string } | null>(null);
  const [nivelModalOpen, setNivelModalOpen] = useState(false);

  const [abaixoMinimo, setAbaixoMinimo] = useState(params.tipo === "minimo");
  const [abaixoRessuprimento, setAbaixoRessuprimento] = useState(params.tipo === "ressuprimento");
  const [acimaMaximo, setAcimaMaximo] = useState(false);
  const [zeradoNegativo, setZeradoNegativo] = useState(params.tipo === "zerado");

  const [orderBy, setOrderBy] = useState("descricao");

  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const [buscouAlgumaVez, setBuscouAlgumaVez] = useState(false);

  const [hoverInfo, setHoverInfo] = useState<string | null>(null);

  const [detalheItem, setDetalheItem] = useState<Item | null>(null);
  const [compras, setCompras] = useState<Compra[]>([]);
  const [loadingCompras, setLoadingCompras] = useState(false);

  // Seleção pro "Gerar Pedido de Compra" — codigo_int -> quantidade a
  // comprar (pré-preenchida com a sugestão, editável). Pedido explícito do
  // usuário, 2026-07-20: fecha o ciclo alerta -> ação sem digitar tudo de
  // novo numa tela separada de Pedido de Compra.
  const [selecionados, setSelecionados] = useState<Record<string, number>>({});
  const [gerandoPedidos, setGerandoPedidos] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      const r = await apiGet(c, "/api/gestao-compras/curvas");
      if (r?.success) {
        setCurvasQtd(r.curva_abc || []);
        setCurvasFin(r.curva_abc_fin || []);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    setBuscouAlgumaVez(true);
    try {
      const r = await apiGet(conn, "/api/gestao-compras/ressuprimento", {
        curva_abc: filtroCurvaQtd || undefined,
        curva_abc_fin: filtroCurvaFin || undefined,
        fornecedor: fornecedor?.codigo_int || undefined,
        nivel: nivel?.codigo || undefined,
        abaixo_minimo: abaixoMinimo || undefined,
        abaixo_ressuprimento: abaixoRessuprimento || undefined,
        acima_maximo: acimaMaximo || undefined,
        zerado_negativo: zeradoNegativo || undefined,
        order_by: orderBy,
      });
      setItems(r?.items || []);
      setSelecionados({});
    } finally {
      setLoading(false);
    }
  }, [conn, filtroCurvaQtd, filtroCurvaFin, fornecedor, nivel, abaixoMinimo, abaixoRessuprimento, acimaMaximo, zeradoNegativo, orderBy]);

  const toggleSelecionado = useCallback((it: Item) => {
    setSelecionados((prev) => {
      const next = { ...prev };
      if (it.codigo_int in next) {
        delete next[it.codigo_int];
      } else {
        next[it.codigo_int] = qtdSugerida(it);
      }
      return next;
    });
  }, []);

  const alterarQtdSelecionada = useCallback((codigo_int: string, qtd: number) => {
    setSelecionados((prev) => ({ ...prev, [codigo_int]: qtd }));
  }, []);

  const handleGerarPedidos = useCallback(async () => {
    if (!conn) return;
    const itensSelecionados = Object.entries(selecionados)
      .map(([codigo_int, qtd]) => ({ codigo_int, qtd }))
      .filter((i) => i.qtd > 0);
    if (itensSelecionados.length === 0) return;
    setGerandoPedidos(true);
    try {
      const r = await apiSend(conn, "/api/gestao-compras/ressuprimento/gerar-pedidos", "POST", {
        itens: itensSelecionados,
        ...auditCtx,
      });
      if (!r?.success) {
        fb.showError(r?.message || "Não foi possível gerar os pedidos de compra.");
        return;
      }
      const criados: { codigo: number; fornecedor: number; itens: number; itens_total: number }[] = r.pedidos_criados || [];
      const semFornecedor: string[] = r.sem_fornecedor || [];
      if (criados.length > 0) {
        const resumoTexto = criados.map((p) => `Pedido ${p.codigo} (fornecedor ${p.fornecedor}, ${p.itens}/${p.itens_total} item(ns))`).join("; ");
        fb.showSuccess(`${criados.length} pedido(s) de compra gerado(s): ${resumoTexto}.`, undefined, 5000);
      }
      if (semFornecedor.length > 0) {
        fb.showWarning(
          `${semFornecedor.length} produto(s) sem fornecedor cadastrado, não incluído(s) em nenhum pedido: ${semFornecedor.join(", ")}.`,
          undefined,
          5000,
        );
      }
      if (criados.length === 0 && semFornecedor.length === 0) {
        fb.showWarning("Nenhum pedido foi gerado.");
      }
      setSelecionados({});
      buscar();
    } finally {
      setGerandoPedidos(false);
    }
  }, [conn, selecionados, auditCtx, fb, buscar]);

  // Chegou pelo card de alerta da Tela Principal (`?tipo=`) — os chips já
  // nasceram marcados (ver useState acima); só falta disparar a busca
  // sozinho assim que a conexão estiver pronta, sem exigir que o usuário
  // aperte "Buscar" de novo. Pedido explícito do usuário, 2026-07-20.
  useEffect(() => {
    if (conn && params.tipo) buscar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const buscarFornecedor = useCallback(async (termo: string) => {
    if (!conn) return;
    const r = await apiGet(conn, "/api/fornecedores", { search: termo });
    if (r?.items) setFornecedorResultados(r.items);
  }, [conn]);

  const abrirDetalhe = useCallback(async (it: Item) => {
    if (!conn) return;
    setDetalheItem(it);
    setCompras([]);
    setLoadingCompras(true);
    try {
      const r = await apiGet(conn, `/api/gestao-compras/ressuprimento/${encodeURIComponent(it.codigo_int)}/ultimas-compras`);
      setCompras(r?.items || []);
    } finally {
      setLoadingCompras(false);
    }
  }, [conn]);

  const handleImprimir = useCallback(async () => {
    if (!conn) return;
    const empresa = await fetchEmpresaHeader(apiBase(conn), conn.servidor, conn.banco);
    const linhas = items.map((it) => {
      const st = statusFor(it);
      return `
      <div class="row3">
        <span>${escHtml(it.codigo_int)} — ${escHtml(it.descricao)} <b style="color:${st.color}">[${st.label}]</b></span>
        <span>Estoque: ${qtyFmt(it.qtd)} · Mín: ${qtyFmt(it.estoque_minimo)} · Ressup: ${qtyFmt(it.estoque_ressuprimento)} · Máx: ${qtyFmt(it.estoque_maximo)}</span>
        <span>Consumo médio: ${qtyFmt(it.consumo_medio_mensal)}/mês · Previsão: ${it.prev_dia} dias</span>
      </div>`;
    }).join("");
    const html = `
      <style>${REPORT_HEADER_CSS}</style>
      ${buildReportHeaderHtml(empresa, "Gestão de Compras — Ressuprimento")}
      ${linhas || '<div class="mb">Nenhum produto encontrado para os filtros selecionados.</div>'}
    `;
    printHtml(html, "Gestão de Compras — Ressuprimento");
  }, [conn, items]);

  const handleExportar = useCallback(() => {
    exportSheetsToXlsx("gestao-compras-ressuprimento", [{
      name: "Ressuprimento",
      rows: items.map((it) => ({
        "Curva (Qtd)": it.curva_abc,
        "Curva (Financeira)": it.curva_abc_fin,
        "Código": it.codigo_int,
        "Cód. Fabricante": it.codigo_fab,
        "Descrição": it.descricao,
        "Estoque Atual": it.qtd,
        "Consumo Médio Mensal": it.consumo_medio_mensal,
        "Estoque Mínimo": it.estoque_minimo,
        "Estoque Ressuprimento": it.estoque_ressuprimento,
        "Estoque Máximo": it.estoque_maximo,
        "Previsão (meses)": it.prev_mes,
        "Previsão (dias)": it.prev_dia,
        "Situação": statusFor(it).label,
      })),
    }]);
  }, [items]);

  const podeImprimir = can("GESTAO_COMPRAS.IMPRIMIR");
  const podeExportar = can("GESTAO_COMPRAS.EXPORTAR");
  const podeGerarPedido = can("PEDIDO_COMPRA.GRAVAR");
  const qtdSelecionados = Object.keys(selecionados).length;

  const resumo = useMemo(() => {
    const criticos = items.filter((it) => it.qtd < it.estoque_minimo).length;
    const repor = items.filter((it) => it.qtd >= it.estoque_minimo && it.qtd < it.estoque_ressuprimento).length;
    return { total: items.length, criticos, repor };
  }, [items]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="gestao-compras-ressuprimento-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Gestão de Compras</Text>
        <View style={styles.back} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.guideCard}>
            <Ionicons name="bulb-outline" size={20} color={colors.brandPrimary} />
            <Text style={styles.guideText}>
              Este relatório mostra <Text style={styles.guideBold}>o que você precisa comprar agora</Text>,
              cruzando a Curva ABC de cada produto com a posição atual de estoque. Marque os filtros abaixo
              (ou deixe todos em branco para ver tudo) e toque em <Text style={styles.guideBold}>Buscar</Text>.
              Toque em um produto da lista para ver suas últimas compras.
            </Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Filtros</Text>

            <View style={styles.filterGroup}>
              <View style={styles.labelWithInfo}>
                <Text style={styles.label}>Curva ABC (por quantidade vendida)</Text>
                <Pressable onHoverIn={() => setHoverInfo("curva-qtd")} onHoverOut={() => setHoverInfo(null)} hitSlop={6}>
                  <Ionicons name="information-circle-outline" size={14} color={colors.muted} />
                </Pressable>
                {hoverInfo === "curva-qtd" ? (
                  <View style={styles.tooltip}>
                    <Text style={styles.tooltipText}>
                      Classificação automática gerada em "Curva ABC e Estoques", pela quantidade vendida de cada
                      produto: A são os mais vendidos, as letras seguintes (B, C, D…) os menos vendidos — depende
                      das faixas configuradas lá.
                    </Text>
                  </View>
                ) : null}
              </View>
              <View style={styles.chipsRow}>
                {curvasQtd.map((c) => (
                  <Pressable
                    key={c}
                    onPress={() => setFiltroCurvaQtd((v) => (v === c ? null : c))}
                    style={[styles.chip, filtroCurvaQtd === c && styles.chipSel]}
                    testID={`ressuprimento-curva-qtd-${c}`}
                  >
                    <Text style={[styles.chipText, filtroCurvaQtd === c && styles.chipTextSel]}>{c}</Text>
                  </Pressable>
                ))}
                {curvasQtd.length === 0 ? <Text style={styles.hint}>Nenhuma curva gerada ainda — use "Curva ABC e Estoques".</Text> : null}
              </View>
            </View>

            <View style={styles.filterGroup}>
              <View style={styles.labelWithInfo}>
                <Text style={styles.label}>Curva ABC (por valor vendido)</Text>
                <Pressable onHoverIn={() => setHoverInfo("curva-fin")} onHoverOut={() => setHoverInfo(null)} hitSlop={6}>
                  <Ionicons name="information-circle-outline" size={14} color={colors.muted} />
                </Pressable>
                {hoverInfo === "curva-fin" ? (
                  <View style={styles.tooltip}>
                    <Text style={styles.tooltipText}>
                      Mesma classificação, mas pelo valor total vendido (R$) de cada produto no período, em vez da
                      quantidade — um produto pode estar em curvas diferentes nos dois filtros.
                    </Text>
                  </View>
                ) : null}
              </View>
              <View style={styles.chipsRow}>
                {curvasFin.map((c) => (
                  <Pressable
                    key={c}
                    onPress={() => setFiltroCurvaFin((v) => (v === c ? null : c))}
                    style={[styles.chip, filtroCurvaFin === c && styles.chipSel]}
                    testID={`ressuprimento-curva-fin-${c}`}
                  >
                    <Text style={[styles.chipText, filtroCurvaFin === c && styles.chipTextSel]}>{c}</Text>
                  </Pressable>
                ))}
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Fornecedor</Text>
                {fornecedor ? (
                  <View style={styles.selectedChipRow}>
                    <View style={styles.selectedChip}>
                      <Text style={styles.selectedChipText} numberOfLines={1}>{fornecedor.fantasia || fornecedor.nome}</Text>
                      <Pressable onPress={() => setFornecedor(null)} hitSlop={6}>
                        <Ionicons name="close-circle" size={16} color={colors.onBrandPrimary} />
                      </Pressable>
                    </View>
                  </View>
                ) : (
                  <Pressable
                    style={styles.pickerBtn}
                    onPress={() => { setFornecedorModalOpen(true); setFornecedorBusca(""); setFornecedorResultados([]); }}
                    testID="ressuprimento-fornecedor-btn"
                  >
                    <Ionicons name="business-outline" size={16} color={colors.muted} />
                    <Text style={styles.pickerBtnText}>Qualquer fornecedor</Text>
                  </Pressable>
                )}
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Nível</Text>
                {nivel ? (
                  <View style={styles.selectedChipRow}>
                    <View style={styles.selectedChip}>
                      <Text style={styles.selectedChipText} numberOfLines={1}>{nivel.label}</Text>
                      <Pressable onPress={() => setNivel(null)} hitSlop={6}>
                        <Ionicons name="close-circle" size={16} color={colors.onBrandPrimary} />
                      </Pressable>
                    </View>
                  </View>
                ) : (
                  <Pressable style={styles.pickerBtn} onPress={() => setNivelModalOpen(true)} testID="ressuprimento-nivel-btn">
                    <Ionicons name="layers-outline" size={16} color={colors.muted} />
                    <Text style={styles.pickerBtnText}>Todos os níveis</Text>
                  </Pressable>
                )}
              </View>
            </View>

            <View style={styles.filterGroup}>
              <Text style={styles.label}>Situação de estoque</Text>
              <View style={styles.chipsRow}>
                <View style={styles.chipWithInfo}>
                  <Pressable
                    onPress={() => setAbaixoMinimo((v) => !v)}
                    style={[styles.chip, abaixoMinimo && { backgroundColor: colors.error, borderColor: colors.error }]}
                    testID="ressuprimento-chip-abaixo-minimo"
                  >
                    <Text style={[styles.chipText, abaixoMinimo && styles.chipTextSel]}>Abaixo do Mínimo</Text>
                  </Pressable>
                  <Pressable
                    onHoverIn={() => setHoverInfo("min")}
                    onHoverOut={() => setHoverInfo(null)}
                    hitSlop={6}
                  >
                    <Ionicons name="information-circle-outline" size={15} color={colors.muted} />
                    {hoverInfo === "min" ? (
                      <View style={styles.tooltip}><Text style={styles.tooltipText}>Estoque atual já abaixo do mínimo — comprar com urgência.</Text></View>
                    ) : null}
                  </Pressable>
                </View>
                <View style={styles.chipWithInfo}>
                  <Pressable
                    onPress={() => setAbaixoRessuprimento((v) => !v)}
                    style={[styles.chip, abaixoRessuprimento && { backgroundColor: colors.warning, borderColor: colors.warning }]}
                    testID="ressuprimento-chip-abaixo-ressuprimento"
                  >
                    <Text style={[styles.chipText, abaixoRessuprimento && styles.chipTextSel]}>Abaixo do Ressuprimento</Text>
                  </Pressable>
                  <Pressable
                    onHoverIn={() => setHoverInfo("ressup")}
                    onHoverOut={() => setHoverInfo(null)}
                    hitSlop={6}
                  >
                    <Ionicons name="information-circle-outline" size={15} color={colors.muted} />
                    {hoverInfo === "ressup" ? (
                      <View style={styles.tooltip}><Text style={styles.tooltipText}>Já é hora de iniciar a compra, antes de faltar.</Text></View>
                    ) : null}
                  </Pressable>
                </View>
                <View style={styles.chipWithInfo}>
                  <Pressable
                    onPress={() => setZeradoNegativo((v) => !v)}
                    style={[styles.chip, zeradoNegativo && { backgroundColor: colors.error, borderColor: colors.error }]}
                    testID="ressuprimento-chip-zerado-negativo"
                  >
                    <Text style={[styles.chipText, zeradoNegativo && styles.chipTextSel]}>Zerado ou Negativo</Text>
                  </Pressable>
                  <Pressable
                    onHoverIn={() => setHoverInfo("zerado")}
                    onHoverOut={() => setHoverInfo(null)}
                    hitSlop={6}
                  >
                    <Ionicons name="information-circle-outline" size={15} color={colors.muted} />
                    {hoverInfo === "zerado" ? (
                      <View style={styles.tooltip}><Text style={styles.tooltipText}>Sem nenhuma unidade disponível — risco real de não conseguir vender.</Text></View>
                    ) : null}
                  </Pressable>
                </View>
                <View style={styles.chipWithInfo}>
                  <Pressable
                    onPress={() => setAcimaMaximo((v) => !v)}
                    style={[styles.chip, acimaMaximo && styles.chipSel]}
                    testID="ressuprimento-chip-acima-maximo"
                  >
                    <Text style={[styles.chipText, acimaMaximo && styles.chipTextSel]}>Acima do Máximo</Text>
                  </Pressable>
                  <Pressable
                    onHoverIn={() => setHoverInfo("max")}
                    onHoverOut={() => setHoverInfo(null)}
                    hitSlop={6}
                  >
                    <Ionicons name="information-circle-outline" size={15} color={colors.muted} />
                    {hoverInfo === "max" ? (
                      <View style={styles.tooltip}><Text style={styles.tooltipText}>Estoque acima do necessário — evitar comprar mais por enquanto.</Text></View>
                    ) : null}
                  </Pressable>
                </View>
              </View>
            </View>

            <View style={styles.filterGroup}>
              <Text style={styles.label}>Ordenar por</Text>
              <View style={styles.chipsRow}>
                {ORDER_OPTIONS.map((o) => (
                  <Pressable
                    key={o.key}
                    onPress={() => setOrderBy(o.key)}
                    style={[styles.chip, orderBy === o.key && styles.chipSel]}
                    testID={`ressuprimento-order-${o.key}`}
                  >
                    <Text style={[styles.chipText, orderBy === o.key && styles.chipTextSel]}>{o.label}</Text>
                  </Pressable>
                ))}
              </View>
            </View>

            <View style={styles.toolbarRow}>
              <Pressable style={styles.buscarBtn} onPress={buscar} disabled={loading} testID="ressuprimento-buscar-btn">
                <Ionicons name="search-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.buscarBtnText}>{loading ? "Buscando…" : "Buscar"}</Text>
              </Pressable>
              {podeImprimir && items.length > 0 ? (
                <Pressable style={ps.secondaryBtn} onPress={handleImprimir} testID="ressuprimento-imprimir-btn">
                  <Text style={ps.secondaryBtnText}>Imprimir</Text>
                </Pressable>
              ) : null}
              {podeExportar && items.length > 0 ? (
                <Pressable style={ps.secondaryBtn} onPress={handleExportar} testID="ressuprimento-exportar-btn">
                  <Text style={ps.secondaryBtnText}>Gerar Planilha</Text>
                </Pressable>
              ) : null}
            </View>
          </View>

          <View style={styles.card}>
            <View style={styles.resultHeader}>
              <Text style={styles.sectionTitle}>Resultado {items.length > 0 ? `(${resumo.total})` : ""}</Text>
              {resumo.criticos > 0 || resumo.repor > 0 ? (
                <Text style={styles.resumoText}>
                  {resumo.criticos > 0 ? <Text style={{ color: colors.error, fontWeight: "700" }}>{resumo.criticos} crítico(s)</Text> : null}
                  {resumo.criticos > 0 && resumo.repor > 0 ? "  ·  " : ""}
                  {resumo.repor > 0 ? <Text style={{ color: colors.warning, fontWeight: "700" }}>{resumo.repor} p/ repor</Text> : null}
                </Text>
              ) : null}
            </View>

            {podeGerarPedido && qtdSelecionados > 0 ? (
              <View style={styles.selecaoBar}>
                <View style={styles.labelWithInfo}>
                  <Text style={styles.selecaoBarText}>{qtdSelecionados} produto(s) selecionado(s)</Text>
                  <Pressable onHoverIn={() => setHoverInfo("gerar-pedido")} onHoverOut={() => setHoverInfo(null)} hitSlop={6}>
                    <Ionicons name="information-circle-outline" size={14} color={colors.muted} />
                  </Pressable>
                  {hoverInfo === "gerar-pedido" ? (
                    <View style={[styles.tooltip, { bottom: 28 }]}>
                      <Text style={styles.tooltipText}>
                        Agrupa os produtos selecionados por fornecedor preferencial (o primeiro cadastrado no
                        produto) e gera um Pedido de Compra por fornecedor, já com a quantidade e o custo sugeridos.
                        Produto sem fornecedor cadastrado fica de fora — cadastre um fornecedor nele antes de tentar
                        de novo.
                      </Text>
                    </View>
                  ) : null}
                </View>
                <Pressable
                  style={[styles.gerarPedidoBtn, gerandoPedidos && { opacity: 0.6 }]}
                  onPress={handleGerarPedidos}
                  disabled={gerandoPedidos}
                  testID="ressuprimento-gerar-pedido-btn"
                >
                  <Ionicons name="cart-outline" size={16} color={colors.onBrandPrimary} />
                  <Text style={styles.buscarBtnText}>{gerandoPedidos ? "Gerando…" : "Gerar Pedido de Compra"}</Text>
                </Pressable>
              </View>
            ) : null}

            {items.map((it) => {
              const st = statusFor(it);
              const selecionado = it.codigo_int in selecionados;
              return (
                <View key={it.codigo_int} style={styles.itemRow} testID={`ressuprimento-item-${it.codigo_int}`}>
                  {podeGerarPedido ? (
                    <Pressable
                      onPress={() => toggleSelecionado(it)}
                      hitSlop={8}
                      testID={`ressuprimento-item-check-${it.codigo_int}`}
                    >
                      <Ionicons
                        name={selecionado ? "checkbox" : "square-outline"}
                        size={20}
                        color={selecionado ? colors.brandPrimary : colors.muted}
                      />
                    </Pressable>
                  ) : null}
                  <Pressable style={styles.itemRowMain} onPress={() => abrirDetalhe(it)}>
                    <View style={[styles.statusBadge, { backgroundColor: st.bg }]}>
                      <Text style={[styles.statusBadgeText, { color: st.color }]}>{st.label}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemTitle}>{it.codigo_int} — {it.descricao}</Text>
                      <Text style={styles.itemSub}>
                        Estoque: {qtyFmt(it.qtd)} · Mín: {qtyFmt(it.estoque_minimo)} · Ressup: {qtyFmt(it.estoque_ressuprimento)} · Máx: {qtyFmt(it.estoque_maximo)}
                      </Text>
                      <Text style={styles.itemSub}>
                        Consumo médio: {qtyFmt(it.consumo_medio_mensal)}/mês
                        {it.consumo_medio_mensal > 0 ? ` · acaba em ~${it.prev_dia} dia(s)` : ""}
                        {(it.curva_abc || it.curva_abc_fin) ? ` · Curva: ${[it.curva_abc, it.curva_abc_fin].filter(Boolean).join(" / ")}` : ""}
                      </Text>
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                  </Pressable>
                  {selecionado ? (
                    <View style={styles.qtdSugeridaBox}>
                      <Text style={styles.qtdSugeridaLabel}>Comprar</Text>
                      <TextInput
                        style={styles.qtdSugeridaInput}
                        value={String(selecionados[it.codigo_int])}
                        onChangeText={(v) => alterarQtdSelecionada(it.codigo_int, Number(v.replace(",", ".")) || 0)}
                        keyboardType="numeric"
                        testID={`ressuprimento-item-qtd-${it.codigo_int}`}
                      />
                    </View>
                  ) : null}
                </View>
              );
            })}
            {items.length === 0 && !loading && buscouAlgumaVez ? (
              <Text style={ps.emptyText}>Nenhum produto encontrado para os filtros selecionados.</Text>
            ) : null}
            {items.length === 0 && !buscouAlgumaVez ? (
              <Text style={styles.hint}>Ajuste os filtros acima e toque em Buscar para ver os resultados.</Text>
            ) : null}
          </View>
        </View>
      </ScrollView>

      {/* Fornecedor — busca */}
      <AppModal visible={fornecedorModalOpen} transparent animationType="fade" onRequestClose={() => setFornecedorModalOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Buscar Fornecedor</Text>
              <Pressable onPress={() => setFornecedorModalOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={ps.searchWrap}>
              <Ionicons name="search-outline" size={18} color={colors.muted} />
              <TextInput
                style={ps.searchInput}
                value={fornecedorBusca}
                onChangeText={(v) => { setFornecedorBusca(v); buscarFornecedor(v); }}
                placeholder="Nome ou código"
                autoFocus
                testID="ressuprimento-fornecedor-search"
              />
            </View>
            <ScrollView style={{ maxHeight: 360 }}>
              {fornecedorResultados.map((f) => (
                <Pressable
                  key={f.codigo_int}
                  style={ps.resultRow}
                  onPress={() => { setFornecedor(f); setFornecedorModalOpen(false); }}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={ps.resultNome}>{f.fantasia || f.nome}</Text>
                    <Text style={ps.resultSub}>{f.nome}</Text>
                  </View>
                </Pressable>
              ))}
              {fornecedorResultados.length === 0 ? <Text style={ps.emptyText}>Digite pra buscar.</Text> : null}
            </ScrollView>
          </View>
        </View>
      </AppModal>

      <NiveisModal
        visible={nivelModalOpen}
        conn={conn}
        onClose={() => setNivelModalOpen(false)}
        onPick={(codigo, label) => { setNivel(codigo ? { codigo, label } : null); setNivelModalOpen(false); }}
      />

      {/* Últimas Compras */}
      <AppModal visible={!!detalheItem} transparent animationType="fade" onRequestClose={() => setDetalheItem(null)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact, { maxWidth: 640 }]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Últimas Compras</Text>
              <Pressable onPress={() => setDetalheItem(null)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {detalheItem ? (
              <Text style={styles.hint}>{detalheItem.codigo_int} — {detalheItem.descricao}</Text>
            ) : null}
            {loadingCompras ? <Text style={styles.hint}>Buscando…</Text> : null}
            <ScrollView style={{ maxHeight: 380, marginTop: spacing.sm }}>
              {compras.map((c, idx) => (
                <View key={`${c.num_nf}-${idx}`} style={styles.itemRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemTitle}>
                      NF {c.num_nf} — {c.fornecedor} {c.data_mov ? `· ${new Date(c.data_mov).toLocaleDateString("pt-BR")}` : ""}
                    </Text>
                    <Text style={styles.itemSub}>
                      Qtd: {qtyFmt(c.qtd)} · Unit.: {money(c.valor_unit)} · Impostos/un: {money(c.impostos_unit)}
                    </Text>
                  </View>
                </View>
              ))}
              {!loadingCompras && compras.length === 0 ? (
                <Text style={ps.emptyText}>Nenhuma compra encontrada para este produto.</Text>
              ) : null}
            </ScrollView>
          </View>
        </View>
      </AppModal>
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
  guideCard: {
    flexDirection: "row", gap: spacing.sm, alignItems: "flex-start",
    backgroundColor: colors.brandTertiary, borderRadius: radius.md,
    padding: spacing.md, marginBottom: spacing.md,
  },
  guideText: { flex: 1, fontSize: 12.5, color: colors.onSurface, lineHeight: 18 },
  guideBold: { fontWeight: "700" },
  card: { ...WEB_FILTER_CARD, gap: spacing.sm, marginBottom: spacing.md },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  filterGroup: { gap: 6 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  labelWithInfo: { flexDirection: "row", alignItems: "center", gap: 4, position: "relative" },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 220 },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "center" },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: 7, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: "#fff" },
  chipWithInfo: { flexDirection: "row", alignItems: "center", gap: 4, position: "relative" },
  tooltip: {
    position: "absolute", bottom: 24, left: 0, zIndex: 10,
    backgroundColor: colors.onSurface, borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 6, width: 200,
  },
  tooltipText: { color: "#fff", fontSize: 11, lineHeight: 15 },
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
    paddingHorizontal: spacing.md, paddingVertical: 10, maxWidth: 280,
  },
  selectedChipText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600", flexShrink: 1 },
  toolbarRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "center", marginTop: spacing.sm },
  buscarBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  buscarBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  resultHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  resumoText: { fontSize: 12 },
  itemRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  itemRowMain: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  itemTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  itemSub: { fontSize: 11.5, color: colors.muted, marginTop: 2 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  statusBadgeText: { fontSize: 11, fontWeight: "700" },
  qtdSugeridaBox: { alignItems: "center", gap: 2 },
  qtdSugeridaLabel: { fontSize: 10, color: colors.muted, fontWeight: "600" },
  qtdSugeridaInput: {
    width: 64, textAlign: "center", fontSize: 13, fontWeight: "600",
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingVertical: 6, color: colors.onSurface, backgroundColor: colors.surface,
  },
  selecaoBar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: colors.brandTertiary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  selecaoBarText: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  gerarPedidoBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
});

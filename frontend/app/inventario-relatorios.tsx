// Relatórios de Inventário (Conferência / Crítica / Resultado / Divergência)
// — Fase 2, 2026-07-23, user-directed. Consolida os 4 relatórios restantes
// do menu legado (só faltava "Registro de Inventário", código morto no
// VB6, não portado — ver PENDENCIAS.md) numa única tela com seletor de
// relatório, em vez de replicar a triplicação do legado (3 telas quase
// idênticas por eixo de agrupamento Nível/Área/Descrição — aqui só o eixo
// Nível é portado, mesmo escopo já usado no Relatório de Contagem). Cada
// relatório tem sua permissão própria (`INVENTARIO.REL_*`) — só aparecem
// no seletor os que o usuário/grupo pode ver.
//
// Legado: `FrmRelInvConf.frm` (Conferência), `FrmRelInvCrit.frm` (Crítica),
// `FrmRelInvRes.frm` (Resultado), `FrmRelInvDiv.frm` (Divergência). Ver
// backend/services/inventario_service.py e PENDENCIAS.md > "Inventário"
// pro rastreio de negócio completo (inclusive um bug real corrigido do
// legado: a Divergência tinha uma variável `um` nunca declarada, que
// quebrava a consulta sempre que existia algum veículo no filtro).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import AjudaInventarioModal, { AjudaInventarioItem } from "@/src/components/inventario/AjudaInventarioModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiBase, friendlyApiError } from "@/src/utils/api";
import { printHtml, escHtml } from "@/src/utils/printHtml";
import { fetchEmpresaHeader, buildReportHeaderHtml, REPORT_HEADER_CSS } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER, WEB_FILTER_CARD } from "@/src/theme/webLayout";

type Relatorio = "conferencia" | "critica" | "resultado" | "divergencia";
type NivelRow = { nivel1: string; nivel2: string; nivel3: string; nivel4: string; nivel5: string; descricao: string };

const TODOS_OPTION: SelectOption = { value: "", label: "TODOS" };
const fmtMoney = (v: number) => (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fmtQtd = (v: number) => (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 3 });

const TIPOS = [
  { valor: 0, label: "Revenda" },
  { valor: 1, label: "Consumo" },
  { valor: 2, label: "Imobilizado" },
];

const PRECO_OPTIONS: SelectOption[] = [
  { value: "venda", label: "Preço de Venda" },
  { value: "custo_inventario", label: "Custo de Inventário" },
  { value: "custo_reposicao", label: "Custo de Reposição" },
];

const ORDENAR_OPTIONS: SelectOption[] = [
  { value: "codigo", label: "Código" },
  { value: "descricao", label: "Descrição" },
  { value: "diferenca", label: "Diferença de Quantidade" },
  { value: "preco_unitario", label: "Preço Unitário" },
  { value: "preco_total", label: "Preço Total" },
];

const RELATORIOS: { key: Relatorio; label: string; permissao: string; endpoint: string; icon: React.ComponentProps<typeof Ionicons>["name"] }[] = [
  { key: "conferencia", label: "Conferência", permissao: "INVENTARIO.REL_CONFERENCIA", endpoint: "/api/inventario/relatorio-conferencia", icon: "checkbox-outline" },
  { key: "critica", label: "Crítica", permissao: "INVENTARIO.REL_CRITICA", endpoint: "/api/inventario/relatorio-critica", icon: "alert-circle-outline" },
  { key: "resultado", label: "Resultado", permissao: "INVENTARIO.REL_RESULTADO", endpoint: "/api/inventario/relatorio-resultado", icon: "cash-outline" },
  { key: "divergencia", label: "Divergência", permissao: "INVENTARIO.REL_DIVERGENCIA", endpoint: "/api/inventario/relatorio-divergencia", icon: "swap-vertical-outline" },
];

const AJUDA_ITENS: AjudaInventarioItem[] = [
  {
    titulo: "Conferência",
    texto: "Lista o que já foi contado (código, descrição e quantidade), separado por Revenda/Consumo/Imobilizado — cada tipo é sempre um grupo à parte, nunca somado com os outros. \"Listar produtos com estoque zerado\" inclui também os itens ainda não contados nesta lista.",
    icon: "checkbox-outline",
  },
  {
    titulo: "Crítica",
    texto: "Mostra só os itens cuja contagem é DIFERENTE do estoque do sistema, com uma coluna em branco pra anotar uma recontagem no papel. Por padrão esconde a quantidade do sistema (recontagem \"às cegas\", sem induzir o conferente) — dá pra revelar com o botão \"Mostrar estoque do sistema\".",
    icon: "alert-circle-outline",
  },
  {
    titulo: "Resultado",
    texto: "Valoriza a quantidade contada nos 3 preços/custos do momento do balanço (Venda, Custo de Inventário, Custo de Reposição) — não o preço atual do cadastro, o congelado na data do balanço. \"Estoque Fornecedor\" troca a quantidade usada pela quantidade em poder do fornecedor (só se aplica a peças, nunca a veículos).",
    icon: "cash-outline",
  },
  {
    titulo: "Divergência",
    texto: "A mesma lista da Crítica, mas mostrando os dois números lado a lado (sistema × contado) e valorizada em 1 dos 3 preços à escolha — é literalmente uma prévia do que o Fechamento vai lançar no estoque. Pode escolher a data de um balanço já fechado, além do critério de ordenação.",
    icon: "swap-vertical-outline",
  },
  {
    titulo: "Data do balanço (Crítica/Resultado/Divergência)",
    texto: "Sem informar nada, o relatório usa o balanço corrente. Informando uma data diferente, consulta o histórico de um balanço já fechado (Conferência não tem essa opção — sempre mostra o balanço corrente).",
    icon: "calendar-outline",
  },
];

export default function InventarioRelatoriosScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Relatórios de Inventário estão disponíveis apenas no web."
        testID="inventario-relatorios-web-only"
      />
    );
  }

  const relatoriosPermitidos = useMemo(() => RELATORIOS.filter((r) => can(r.permissao)), [can]);
  // Chegar aqui a partir de um atalho (ex.: badge de divergência do Painel)
  // já abre direto no relatório certo, em vez de sempre cair no primeiro
  // da lista — pedido explícito do usuário, 2026-07-23.
  const params = useLocalSearchParams<{ relatorio?: string }>();
  const relatorioInicial = useMemo(() => {
    const pedido = (Array.isArray(params.relatorio) ? params.relatorio[0] : params.relatorio) as Relatorio | undefined;
    if (pedido && relatoriosPermitidos.some((r) => r.key === pedido)) return pedido;
    return relatoriosPermitidos[0]?.key ?? null;
  }, [params.relatorio, relatoriosPermitidos]);

  const [conn, setConn] = useState<Connection | null>(null);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [relatorioAtivo, setRelatorioAtivo] = useState<Relatorio | null>(relatorioInicial);
  const [gerando, setGerando] = useState(false);
  const [itens, setItens] = useState<any[] | null>(null);

  const [arvoreNiveis, setArvoreNiveis] = useState<NivelRow[]>([]);
  const [nivelSel, setNivelSel] = useState<string[]>(["", "", "", "", ""]);

  // Filtros específicos por relatório
  const [tiposSel, setTiposSel] = useState<number[]>([0, 1, 2]);
  const [listarZerados, setListarZerados] = useState(false);
  const [data, setData] = useState<string>("");
  const [mostrarSistema, setMostrarSistema] = useState(false);
  const [fonteEstoque, setFonteEstoque] = useState<"inventario" | "fornecedor">("inventario");
  const [preco, setPreco] = useState<string>("venda");
  const [ordenar, setOrdenar] = useState<string>("codigo");

  const bootConn = useCallback(async () => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa);
    if (c) setConn(c);
    return c || null;
  }, [conn, router]);

  useEffect(() => {
    (async () => {
      const c = await bootConn();
      if (!c) return;
      const r = await apiGet(c, "/api/tabelas/grupos-mercadologicos");
      if (r?.success) setArvoreNiveis(r.items || []);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const opcoesPorNivel = useMemo(() => {
    const nivelCols = ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"] as const;
    const resultado: SelectOption[][] = [[], [], [], [], []];
    for (let n = 0; n < 5; n++) {
      if (n > 0 && !nivelSel[n - 1]) continue;
      const vistos = new Map<string, string>();
      for (const row of arvoreNiveis) {
        const anterioresBatem = nivelCols.slice(0, n).every((col, i) => row[col] === nivelSel[i]);
        if (!anterioresBatem) continue;
        const valor = row[nivelCols[n]];
        const proximoVazio = n === 4 || row[nivelCols[n + 1]] === "";
        if (valor && proximoVazio && !vistos.has(valor)) vistos.set(valor, row.descricao);
      }
      resultado[n] = Array.from(vistos.entries())
        .sort(([, a], [, b]) => a.localeCompare(b, "pt-BR"))
        .map(([valor, descricao]) => ({ value: valor, label: `${valor} - ${descricao}` }));
    }
    return resultado;
  }, [arvoreNiveis, nivelSel]);

  const setNivel = useCallback((idx: number, valor: string) => {
    setNivelSel((prev) => {
      const next = [...prev];
      next[idx] = valor;
      for (let i = idx + 1; i < 5; i++) next[i] = "";
      return next;
    });
  }, []);

  const toggleTipo = useCallback((valor: number) => {
    setTiposSel((prev) => (prev.includes(valor) ? prev.filter((v) => v !== valor) : [...prev, valor]));
  }, []);

  const selecionarRelatorio = useCallback((r: Relatorio) => {
    setRelatorioAtivo(r);
    setItens(null);
  }, []);

  const gerar = useCallback(async () => {
    const c = conn || (await bootConn());
    if (!c || !relatorioAtivo) return;
    if (relatorioAtivo === "conferencia" && tiposSel.length === 0) {
      fb.showError("Selecione ao menos um tipo de produto.");
      return;
    }
    const cfg = RELATORIOS.find((r) => r.key === relatorioAtivo)!;
    const nivelParams = {
      nivel1: nivelSel[0] || undefined, nivel2: nivelSel[1] || undefined, nivel3: nivelSel[2] || undefined,
      nivel4: nivelSel[3] || undefined, nivel5: nivelSel[4] || undefined,
    };
    const params: Record<string, any> =
      relatorioAtivo === "conferencia"
        ? { tipos: tiposSel.join(","), listar_zerados: listarZerados, ...nivelParams }
        : relatorioAtivo === "critica"
        ? { data: data || undefined, ...nivelParams }
        : relatorioAtivo === "resultado"
        ? { data: data || undefined, fonte_estoque: fonteEstoque, ...nivelParams }
        : { data: data || undefined, preco, ordenar, ...nivelParams };
    setGerando(true);
    try {
      const r = await apiGet(c, cfg.endpoint, params);
      if (!r?.success) {
        fb.showError(friendlyApiError(r, "Não foi possível gerar o relatório."));
        return;
      }
      setItens(r.itens || []);
    } finally {
      setGerando(false);
    }
  }, [conn, bootConn, relatorioAtivo, tiposSel, listarZerados, data, fonteEstoque, preco, ordenar, nivelSel, fb]);

  // Chegar aqui a partir de um atalho (ex.: badge de divergência do Painel,
  // `?relatorio=divergencia`) já gera o relatório direto com os filtros
  // padrão (que já cobrem o balanço atual — Divergência/Crítica/Resultado
  // sem `data` usam o corrente), sem precisar clicar em "Gerar Relatório"
  // de novo — pedido explícito do usuário, 2026-07-23. Só dispara uma vez,
  // e só quando a URL realmente pediu um relatório específico (visita
  // direta à tela continua exigindo o clique manual de sempre).
  const autoGerouRef = useRef(false);
  useEffect(() => {
    if (autoGerouRef.current || !conn) return;
    const pedido = (Array.isArray(params.relatorio) ? params.relatorio[0] : params.relatorio) as Relatorio | undefined;
    if (pedido && relatoriosPermitidos.some((r) => r.key === pedido)) {
      autoGerouRef.current = true;
      gerar();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, params.relatorio, relatoriosPermitidos]);

  // Conferência agrupa por tipo primeiro, depois por nível (3 grupos sempre
  // separados — mesmo comportamento das 3 abas fixas do legado); os demais
  // relatórios agrupam só por nível.
  const gruposConferencia = useMemo(() => {
    if (!itens || relatorioAtivo !== "conferencia") return [];
    const porTipo = new Map<string, { tipo: string; grupos: { grupo: string; lista: any[]; subtotal: number }[] }>();
    for (const it of itens) {
      if (!porTipo.has(it.tipo_descricao)) porTipo.set(it.tipo_descricao, { tipo: it.tipo_descricao, grupos: [] });
      const bloco = porTipo.get(it.tipo_descricao)!;
      let g = bloco.grupos.find((x) => x.grupo === it.grupo);
      if (!g) { g = { grupo: it.grupo, lista: [], subtotal: 0 }; bloco.grupos.push(g); }
      g.lista.push(it);
      g.subtotal += it.estoque_balanco;
    }
    return Array.from(porTipo.values());
  }, [itens, relatorioAtivo]);

  const gruposSimples = useMemo(() => {
    if (!itens || relatorioAtivo === "conferencia") return [];
    const campoSubtotal = relatorioAtivo === "resultado" ? "total_venda" : relatorioAtivo === "divergencia" ? "preco_total" : null;
    const porGrupo = new Map<string, { grupo: string; lista: any[]; subtotal: number }>();
    for (const it of itens) {
      if (!porGrupo.has(it.grupo)) porGrupo.set(it.grupo, { grupo: it.grupo, lista: [], subtotal: 0 });
      const g = porGrupo.get(it.grupo)!;
      g.lista.push(it);
      if (campoSubtotal) g.subtotal += it[campoSubtotal] || 0;
    }
    return Array.from(porGrupo.values());
  }, [itens, relatorioAtivo]);

  const totalGeral = useMemo(() => {
    if (!itens) return 0;
    if (relatorioAtivo === "resultado") return itens.reduce((s, it) => s + (it.total_venda || 0), 0);
    if (relatorioAtivo === "divergencia") return itens.reduce((s, it) => s + (it.preco_total || 0), 0);
    return 0;
  }, [itens, relatorioAtivo]);

  const precoLabel = PRECO_OPTIONS.find((o) => o.value === preco)?.label || "Preço Unitário";

  const imprimir = useCallback(async () => {
    if (!conn || !itens || !relatorioAtivo) return;
    const empresa = await fetchEmpresaHeader(apiBase(conn), conn.servidor, conn.banco);
    const cfg = RELATORIOS.find((r) => r.key === relatorioAtivo)!;
    let corpo = "";
    if (relatorioAtivo === "conferencia") {
      corpo = gruposConferencia.map((bloco) => `
        <div style="margin-top:14px;font-weight:700;font-size:13px;">${escHtml(bloco.tipo)}</div>
        ${bloco.grupos.map((g) => `
          <div style="margin-top:6px;font-weight:700;border-bottom:1px solid #999;padding-bottom:2px;">${escHtml(g.grupo)} — ${fmtQtd(g.subtotal)}</div>
          ${g.lista.map((it: any) => `
            <div class="row3" style="border-bottom:1px dotted #ccc;padding:3px 0;">
              <span>${escHtml(it.codigo_interno)}</span><span>${escHtml(it.descricao)}</span><span>${fmtQtd(it.estoque_balanco)}</span>
            </div>`).join("")}
        `).join("")}
      `).join("");
    } else if (relatorioAtivo === "critica") {
      corpo = gruposSimples.map((g) => `
        <div style="margin-top:10px;font-weight:700;border-bottom:1px solid #999;padding-bottom:2px;">${escHtml(g.grupo)}</div>
        ${g.lista.map((it: any) => `
          <div class="row3" style="border-bottom:1px dotted #ccc;padding:3px 0;">
            <span>${escHtml(it.codigo_interno)}</span><span>${escHtml(it.descricao)}</span><span>______________</span>
          </div>`).join("")}
      `).join("");
    } else if (relatorioAtivo === "resultado") {
      corpo = gruposSimples.map((g) => `
        <div style="margin-top:10px;font-weight:700;border-bottom:1px solid #999;padding-bottom:2px;">${escHtml(g.grupo)} — Total Venda: ${escHtml(fmtMoney(g.subtotal))}</div>
        ${g.lista.map((it: any) => `
          <div class="row2" style="border-bottom:1px dotted #ccc;padding:3px 0;">
            <span>${escHtml(it.codigo_interno)} — ${escHtml(it.descricao)} (${fmtQtd(it.estoque)})</span>
            <span>Venda ${escHtml(fmtMoney(it.total_venda))} · Custo Inv. ${escHtml(fmtMoney(it.total_custo_inventario))} · Custo Rep. ${escHtml(fmtMoney(it.total_custo_reposicao))}</span>
          </div>`).join("")}
      `).join("") + `<div class="mb" style="margin-top:12px;font-weight:700;">TOTAL GERAL (Venda): ${escHtml(fmtMoney(totalGeral))}</div>`;
    } else {
      corpo = gruposSimples.map((g) => `
        <div style="margin-top:10px;font-weight:700;border-bottom:1px solid #999;padding-bottom:2px;">${escHtml(g.grupo)} — Total: ${escHtml(fmtMoney(g.subtotal))}</div>
        ${g.lista.map((it: any) => `
          <div class="row2" style="border-bottom:1px dotted #ccc;padding:3px 0;">
            <span>${escHtml(it.codigo_interno)} — ${escHtml(it.descricao)}</span>
            <span>Sistema ${fmtQtd(it.estoque_sistema)} · Balanço ${fmtQtd(it.estoque_balanco)} · Dif. ${fmtQtd(it.diferenca)} · ${escHtml(fmtMoney(it.preco_total))}</span>
          </div>`).join("")}
      `).join("") + `<div class="mb" style="margin-top:12px;font-weight:700;">TOTAL GERAL: ${escHtml(fmtMoney(totalGeral))}</div>`;
    }
    const html = `
      <style>${REPORT_HEADER_CSS}</style>
      ${buildReportHeaderHtml(empresa, `Relatório de ${cfg.label}`)}
      ${corpo || '<div class="mb">Nenhum item encontrado para os filtros selecionados.</div>'}
    `;
    printHtml(html, `Relatório de ${cfg.label}`);
  }, [conn, itens, relatorioAtivo, gruposConferencia, gruposSimples, totalGeral]);

  if (relatoriosPermitidos.length === 0) {
    return (
      <LockedView
        title="Sem permissão"
        message="Você não tem permissão para nenhum relatório de Inventário."
        testID="inventario-relatorios-sem-permissao"
      />
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="inventario-relatorios-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back} testID="inventario-relatorios-voltar">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Relatórios de Inventário</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline"
          label="Ajuda"
          onPress={() => setAjudaOpen(true)}
          color={colors.onBrandPrimary}
          size={22}
          testID="inventario-relatorios-ajuda"
        />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <Text style={styles.label}>Relatório</Text>
            <View style={styles.chipsRow}>
              {relatoriosPermitidos.map((r) => {
                const sel = relatorioAtivo === r.key;
                return (
                  <Pressable
                    key={r.key}
                    onPress={() => selecionarRelatorio(r.key)}
                    style={[styles.tabBtn, sel && styles.tabBtnSel]}
                    testID={`inventario-relatorios-tab-${r.key}`}
                  >
                    <Ionicons name={r.icon} size={15} color={sel ? "#fff" : colors.brandPrimary} />
                    <Text style={[styles.tabBtnText, sel && styles.tabBtnTextSel]}>{r.label}</Text>
                  </Pressable>
                );
              })}
            </View>

            {relatorioAtivo === "conferencia" ? (
              <>
                <Text style={styles.label}>Tipos de produto</Text>
                <View style={styles.chipsRow}>
                  {TIPOS.map((t) => {
                    const sel = tiposSel.includes(t.valor);
                    return (
                      <Pressable key={t.valor} onPress={() => toggleTipo(t.valor)} style={[styles.chip, sel && styles.chipSel]} testID={`inventario-relatorios-tipo-${t.valor}`}>
                        <Ionicons name={sel ? "checkbox" : "square-outline"} size={14} color={sel ? "#fff" : colors.muted} />
                        <Text style={[styles.chipText, sel && styles.chipTextSel]}>{t.label}</Text>
                      </Pressable>
                    );
                  })}
                  <Pressable onPress={() => setListarZerados((v) => !v)} style={[styles.chip, listarZerados && styles.chipSel]} testID="inventario-relatorios-zerados">
                    <Ionicons name={listarZerados ? "checkbox" : "square-outline"} size={14} color={listarZerados ? "#fff" : colors.muted} />
                    <Text style={[styles.chipText, listarZerados && styles.chipTextSel]}>Listar produtos com estoque zerado</Text>
                  </Pressable>
                </View>
              </>
            ) : null}

            {relatorioAtivo === "critica" || relatorioAtivo === "resultado" || relatorioAtivo === "divergencia" ? (
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.fieldLabel}>Data do balanço</Text>
                  <WebDateField value={data || null} onChange={(v) => setData(v || "")} testID="inventario-relatorios-data" />
                  <Text style={styles.hint}>Vazio = balanço corrente</Text>
                </View>
                {relatorioAtivo === "critica" ? (
                  <Pressable
                    onPress={() => setMostrarSistema((v) => !v)}
                    style={[styles.chip, mostrarSistema && styles.chipSel, { alignSelf: "flex-end", marginBottom: 6 }]}
                    testID="inventario-relatorios-mostrar-sistema"
                  >
                    <Ionicons name={mostrarSistema ? "eye" : "eye-off-outline"} size={14} color={mostrarSistema ? "#fff" : colors.muted} />
                    <Text style={[styles.chipText, mostrarSistema && styles.chipTextSel]}>Mostrar estoque do sistema</Text>
                  </Pressable>
                ) : null}
                {relatorioAtivo === "resultado" ? (
                  <View style={styles.colFlex}>
                    <Text style={styles.fieldLabel}>Quantidade usada</Text>
                    <SelectField
                      value={fonteEstoque}
                      onChange={(v) => setFonteEstoque(v as "inventario" | "fornecedor")}
                      options={[{ value: "inventario", label: "Estoque do Inventário" }, { value: "fornecedor", label: "Estoque Fornecedor" }]}
                      compactWeb
                      testID="inventario-relatorios-fonte"
                    />
                  </View>
                ) : null}
                {relatorioAtivo === "divergencia" ? (
                  <>
                    <View style={styles.colFlex}>
                      <Text style={styles.fieldLabel}>Valorizar por</Text>
                      <SelectField value={preco} onChange={(v) => setPreco(v as string)} options={PRECO_OPTIONS} compactWeb testID="inventario-relatorios-preco" />
                    </View>
                    <View style={styles.colFlex}>
                      <Text style={styles.fieldLabel}>Ordenar por</Text>
                      <SelectField value={ordenar} onChange={(v) => setOrdenar(v as string)} options={ORDENAR_OPTIONS} compactWeb testID="inventario-relatorios-ordenar" />
                    </View>
                  </>
                ) : null}
              </View>
            ) : null}

            <Text style={styles.label}>Nível (opcional — filtra em cascata, deixe em TODOS pra não restringir)</Text>
            <View style={styles.nivelRow}>
              {[0, 1, 2, 3, 4].map((idx) => (
                <View key={idx} style={styles.nivelCol}>
                  <SelectField
                    label={`Nível ${idx + 1}`}
                    value={nivelSel[idx] || null}
                    onChange={(v) => setNivel(idx, (v as string) || "")}
                    options={[TODOS_OPTION, ...opcoesPorNivel[idx]]}
                    disabled={idx > 0 && !nivelSel[idx - 1]}
                    compactWeb
                    testID={`inventario-relatorios-nivel-${idx + 1}`}
                  />
                </View>
              ))}
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                style={[styles.primaryBtn, gerando && styles.btnDisabled]}
                onPress={gerar}
                disabled={gerando || !relatorioAtivo}
                testID="inventario-relatorios-gerar"
              >
                {gerando ? (
                  <ActivityIndicator size="small" color={colors.onBrandPrimary} />
                ) : (
                  <Ionicons name="list-outline" size={16} color={colors.onBrandPrimary} />
                )}
                <Text style={styles.primaryBtnText}>{gerando ? "Gerando…" : "Gerar Relatório"}</Text>
              </Pressable>
              {itens && itens.length > 0 ? (
                <Pressable style={styles.secondaryBtn} onPress={imprimir} testID="inventario-relatorios-imprimir">
                  <Ionicons name="print-outline" size={16} color={colors.onSurface} />
                  <Text style={styles.secondaryBtnText}>Imprimir</Text>
                </Pressable>
              ) : null}
            </View>
          </View>

          {itens ? (
            <View style={[styles.card, { marginTop: spacing.md }]}>
              <Text style={styles.listTitle}>
                {itens.length} {itens.length === 1 ? "item" : "itens"}
                {(relatorioAtivo === "resultado" || relatorioAtivo === "divergencia") ? `  ·  Total: ${fmtMoney(totalGeral)}` : ""}
              </Text>

              {relatorioAtivo === "conferencia"
                ? gruposConferencia.map((bloco) => (
                    <View key={bloco.tipo} style={{ marginTop: spacing.md }}>
                      <Text style={styles.tipoTitle}>{bloco.tipo}</Text>
                      {bloco.grupos.map((g) => (
                        <View key={g.grupo} style={{ marginTop: spacing.sm }}>
                          <Text style={styles.groupTitle}>{g.grupo} ({g.lista.length}) — {fmtQtd(g.subtotal)}</Text>
                          {g.lista.map((it: any) => (
                            <View key={it.codigo_interno} style={styles.listRow}>
                              <Text style={styles.listRowCodigo}>{it.codigo_interno}</Text>
                              <Text style={styles.listRowDescricao}>{it.descricao}</Text>
                              <Text style={styles.listRowValor}>{fmtQtd(it.estoque_balanco)}</Text>
                            </View>
                          ))}
                        </View>
                      ))}
                    </View>
                  ))
                : gruposSimples.map((g) => (
                    <View key={g.grupo} style={{ marginTop: spacing.sm }}>
                      <Text style={styles.groupTitle}>
                        {g.grupo} ({g.lista.length})
                        {relatorioAtivo !== "critica" ? ` — ${fmtMoney(g.subtotal)}` : ""}
                      </Text>
                      {relatorioAtivo === "critica"
                        ? g.lista.map((it: any) => (
                            <View key={it.codigo_interno} style={styles.listRow}>
                              <Text style={styles.listRowCodigo}>{it.codigo_interno}</Text>
                              <Text style={styles.listRowDescricao}>{it.descricao}</Text>
                              <Text style={styles.listRowValor}>{mostrarSistema ? `Sist. ${fmtQtd(it.estoque_sistema)}` : "______"}</Text>
                            </View>
                          ))
                        : relatorioAtivo === "resultado"
                        ? g.lista.map((it: any) => (
                            <View key={it.codigo_interno} style={styles.listRowResultado}>
                              <Text style={styles.listRowCodigo}>{it.codigo_interno}</Text>
                              <Text style={styles.listRowDescricao}>{it.descricao} ({fmtQtd(it.estoque)})</Text>
                              <Text style={styles.listRowValorSm}>Venda {fmtMoney(it.total_venda)}</Text>
                              <Text style={styles.listRowValorSm}>C.Inv {fmtMoney(it.total_custo_inventario)}</Text>
                              <Text style={styles.listRowValorSm}>C.Rep {fmtMoney(it.total_custo_reposicao)}</Text>
                            </View>
                          ))
                        : g.lista.map((it: any) => (
                            <View key={it.codigo_interno} style={styles.listRowResultado}>
                              <Text style={styles.listRowCodigo}>{it.codigo_interno}</Text>
                              <Text style={styles.listRowDescricao}>{it.descricao}</Text>
                              <Text style={styles.listRowValorSm}>Sist. {fmtQtd(it.estoque_sistema)}</Text>
                              <Text style={styles.listRowValorSm}>Bal. {fmtQtd(it.estoque_balanco)}</Text>
                              <Text style={[styles.listRowValorSm, { fontWeight: "700", color: it.diferenca < 0 ? colors.error : colors.success }]}>
                                Dif. {fmtQtd(it.diferenca)}
                              </Text>
                              <Text style={styles.listRowValorSm}>{fmtMoney(it.preco_total)}</Text>
                            </View>
                          ))}
                    </View>
                  ))}
            </View>
          ) : null}
        </View>
      </ScrollView>

      <AjudaInventarioModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Ajuda — Relatórios de Inventário" itens={AJUDA_ITENS} />
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
  card: { ...WEB_FILTER_CARD, gap: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: 4 },
  nivelRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: 4 },
  nivelCol: { width: 190 },
  rowFields: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm, alignItems: "flex-start" },
  colNarrow: { width: 170 },
  colFlex: { flex: 1, minWidth: 180 },
  fieldLabel: { fontSize: 11, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4 },
  tabBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary },
  tabBtnText: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  tabBtnTextSel: { color: "#fff" },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 7, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: "#fff" },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  secondaryBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  btnDisabled: { opacity: 0.6 },
  listTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  tipoTitle: {
    fontSize: 13, fontWeight: "800", color: colors.onSurface,
    textTransform: "uppercase", borderBottomWidth: 2, borderBottomColor: colors.brandPrimary, paddingBottom: 4,
  },
  groupTitle: {
    fontSize: 12, fontWeight: "700", color: colors.brandPrimary,
    textTransform: "uppercase", marginBottom: 2,
  },
  listRow: {
    flexDirection: "row", gap: spacing.sm,
    paddingVertical: 6,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  listRowResultado: {
    flexDirection: "row", flexWrap: "wrap", gap: spacing.sm,
    paddingVertical: 6,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  listRowCodigo: { fontSize: 12, color: colors.muted, width: 60 },
  listRowDescricao: { fontSize: 13, color: colors.onSurface, flex: 1 },
  listRowValor: { fontSize: 13, color: colors.onSurface, width: 90, textAlign: "right" },
  listRowValorSm: { fontSize: 12, color: colors.onSurface },
});

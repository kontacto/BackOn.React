import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import DateField from "@/src/components/DateField";
import { Connection, listConnections } from "@/src/utils/storage/connections";
import { getSession } from "@/src/utils/storage/session";
import { useMargemLucro, MargemLucroFiltros } from "@/src/hooks/useMargemLucro";
import { exportMargemLucroPdf, MLDav, MLEmpresa } from "@/src/utils/export-margem-lucro";
import { colors, radius, spacing } from "@/src/theme/colors";

function brl(v?: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function brDate(iso: string): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : iso || "";
}
function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function isoToday(): string {
  return isoDaysAgo(0);
}

function Chip({ label, active, onPress, testID }: {
  label: string; active: boolean; onPress: () => void; testID?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.chip, active && styles.chipActive, pressed && { opacity: 0.8 }]}
      testID={testID}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

export default function RelatorioMargemLucroScreen() {
  const router = useRouter();
  const ml = useMargemLucro();

  const [conns, setConns] = useState<Connection[]>([]);
  const [apiBase, setApiBase] = useState<string>("");
  const [selIds, setSelIds] = useState<Set<string>>(new Set());

  const [filtrosOpen, setFiltrosOpen] = useState(true);
  const [dataIni, setDataIni] = useState<string>(isoDaysAgo(30));
  const [dataFim, setDataFim] = useState<string>(isoToday());

  const [incluirPedidos, setIncluirPedidos] = useState(true);
  const [incluirOS, setIncluirOS] = useState(true);
  const [incluirComandas, setIncluirComandas] = useState(true);
  const [retProdutos, setRetProdutos] = useState(true);
  const [retServicos, setRetServicos] = useState(true);
  const [sitAbertos, setSitAbertos] = useState(true);
  const [sitFechados, setSitFechados] = useState(true);
  const [sitFaturados, setSitFaturados] = useState(true);
  const [opOperacional, setOpOperacional] = useState(false);
  const [opGarantias, setOpGarantias] = useState(false);
  const [opVendaDireta, setOpVendaDireta] = useState(false);
  const [opOsNaoCobrados, setOpOsNaoCobrados] = useState(false);

  const [codCliente, setCodCliente] = useState("");
  const [areaAtuacao, setAreaAtuacao] = useState("");
  const [nivel, setNivel] = useState("");
  const [codDav, setCodDav] = useState("");

  const [busca, setBusca] = useState("");
  const [empExp, setEmpExp] = useState<Record<string, boolean>>({});
  const [davExp, setDavExp] = useState<Record<string, boolean>>({});

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const list = await listConnections();
        const sess = await getSession();
        setConns(list);
        const active = list.find((c) => c.empresa === sess?.empresa && c.banco === sess?.database) || list[0];
        setApiBase(active?.api || "");
        setSelIds((prev) => (prev.size > 0 ? prev : new Set(list.map((c) => c.id))));
      })();
    }, [])
  );

  const toggleEmpresa = (id: string) => {
    setSelIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const gerar = () => {
    const conexoes = conns
      .filter((c) => selIds.has(c.id))
      .map((c) => ({ empresa: c.empresa, servidor: c.servidor, banco: c.banco }));
    if (conexoes.length === 0 || !apiBase) return;
    const num = (s: string) => {
      const n = parseInt(s, 10);
      return Number.isFinite(n) && n > 0 ? n : null;
    };
    const filtros: MargemLucroFiltros = {
      data_ini: dataIni, data_fim: dataFim,
      cod_cliente: num(codCliente), area_atuacao: num(areaAtuacao),
      nivel: nivel.trim() || null, cod_dav: num(codDav),
      incluir_pedidos: incluirPedidos, incluir_os: incluirOS, incluir_comandas: incluirComandas,
      davs_abertos: sitAbertos, davs_fechados: sitFechados, davs_faturados: sitFaturados,
      itens_os_nao_cobrados: opOsNaoCobrados,
      retorna_produtos: retProdutos, retorna_servicos: retServicos,
      somente_garantias: opGarantias, somente_venda_direta: opVendaDireta,
      resultado_operacional: opOperacional,
    };
    ml.mutate({ api: apiBase, conexoes, filtros }, {
      onSuccess: (data) => {
        const exp: Record<string, boolean> = {};
        (data.empresas || []).forEach((e) => { exp[e.banco] = true; });
        setEmpExp(exp);
        setFiltrosOpen(false);
      },
    });
  };

  const data = ml.data;
  const consolidado = data?.consolidado;

  const empresasFiltradas = useMemo<MLEmpresa[]>(() => {
    if (!data?.empresas) return [];
    const term = busca.trim().toLowerCase();
    if (!term) return data.empresas;
    return data.empresas
      .map((e) => ({
        ...e,
        davs: (e.davs || []).filter(
          (d) => String(d.codigo).includes(term) || (d.cliente || "").toLowerCase().includes(term)
        ),
      }))
      .filter((e) => !e.success || (e.davs && e.davs.length > 0));
  }, [data, busca]);

  const exportar = async () => {
    if (!data) return;
    try {
      await exportMargemLucroPdf({
        titulo: "Margem de Lucro e Faturamento",
        periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
        consolidado: data.consolidado,
        empresas: data.empresas,
      });
    } catch {
      // silencioso: usuário pode ter cancelado o compartilhamento
    }
  };

  const semConexoes = conns.length === 0;

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="margem-lucro-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} testID="ml-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Margem de Lucro</Text>
        <Pressable onPress={exportar} hitSlop={8} disabled={!data} testID="ml-export">
          <Ionicons name="share-outline" size={22} color={data ? colors.brandPrimary : colors.border} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        {semConexoes ? (
          <Text style={styles.aviso}>Nenhuma conexão configurada. Cadastre uma conexão primeiro.</Text>
        ) : null}

        {/* ---------------- FILTROS ---------------- */}
        <Pressable style={styles.sectionToggle} onPress={() => setFiltrosOpen((v) => !v)} testID="ml-toggle-filtros">
          <Ionicons name="options-outline" size={18} color={colors.brandPrimary} />
          <Text style={styles.sectionToggleText}>Filtros</Text>
          <Ionicons name={filtrosOpen ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
        </Pressable>

        {filtrosOpen ? (
          <View style={styles.filtros}>
            <Text style={styles.label}>Empresas</Text>
            <View style={styles.chipWrap}>
              {conns.map((c) => (
                <Chip key={c.id} label={c.empresa || c.banco} active={selIds.has(c.id)}
                  onPress={() => toggleEmpresa(c.id)} testID={`ml-emp-${c.id}`} />
              ))}
            </View>

            <View style={styles.dateRow}>
              <DateField label="Data inicial" value={dataIni} onChange={(v) => setDataIni(v || dataIni)} allowClear={false} testID="ml-data-ini" />
              <View style={{ width: spacing.md }} />
              <DateField label="Data final" value={dataFim} onChange={(v) => setDataFim(v || dataFim)} allowClear={false} testID="ml-data-fim" />
            </View>

            <Text style={styles.label}>Fontes</Text>
            <View style={styles.chipWrap}>
              <Chip label="Pedidos" active={incluirPedidos} onPress={() => setIncluirPedidos((v) => !v)} testID="ml-f-pedidos" />
              <Chip label="O.S." active={incluirOS} onPress={() => setIncluirOS((v) => !v)} testID="ml-f-os" />
              <Chip label="Comandas" active={incluirComandas} onPress={() => setIncluirComandas((v) => !v)} testID="ml-f-comandas" />
            </View>

            <Text style={styles.label}>Itens</Text>
            <View style={styles.chipWrap}>
              <Chip label="Produtos" active={retProdutos} onPress={() => setRetProdutos((v) => !v)} testID="ml-i-prod" />
              <Chip label="Serviços" active={retServicos} onPress={() => setRetServicos((v) => !v)} testID="ml-i-serv" />
            </View>

            <Text style={styles.label}>Situação</Text>
            <View style={styles.chipWrap}>
              <Chip label="Aberto" active={sitAbertos} onPress={() => setSitAbertos((v) => !v)} testID="ml-s-aberto" />
              <Chip label="Fechado" active={sitFechados} onPress={() => setSitFechados((v) => !v)} testID="ml-s-fechado" />
              <Chip label="Faturado" active={sitFaturados} onPress={() => setSitFaturados((v) => !v)} testID="ml-s-faturado" />
            </View>

            <Text style={styles.label}>Opções</Text>
            <View style={styles.chipWrap}>
              <Chip label="Resultado Operacional" active={opOperacional} onPress={() => setOpOperacional((v) => !v)} testID="ml-o-oper" />
              <Chip label="Só Garantias" active={opGarantias} onPress={() => setOpGarantias((v) => !v)} testID="ml-o-gar" />
              <Chip label="Só Venda Direta" active={opVendaDireta} onPress={() => setOpVendaDireta((v) => !v)} testID="ml-o-vd" />
              <Chip label="Itens O.S. não cobrados" active={opOsNaoCobrados} onPress={() => setOpOsNaoCobrados((v) => !v)} testID="ml-o-nc" />
            </View>

            <View style={styles.inputRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Cód. Cliente</Text>
                <TextInput value={codCliente} onChangeText={setCodCliente} keyboardType="number-pad"
                  placeholder="opcional" placeholderTextColor={colors.muted} style={styles.input} testID="ml-cliente" />
              </View>
              <View style={{ width: spacing.md }} />
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Área Atuação</Text>
                <TextInput value={areaAtuacao} onChangeText={setAreaAtuacao} keyboardType="number-pad"
                  placeholder="opcional" placeholderTextColor={colors.muted} style={styles.input} testID="ml-area" />
              </View>
            </View>
            <View style={styles.inputRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Nível (cód.)</Text>
                <TextInput value={nivel} onChangeText={setNivel} autoCapitalize="none"
                  placeholder="ex: 001002" placeholderTextColor={colors.muted} style={styles.input} testID="ml-nivel" />
              </View>
              <View style={{ width: spacing.md }} />
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Nº DAV</Text>
                <TextInput value={codDav} onChangeText={setCodDav} keyboardType="number-pad"
                  placeholder="opcional" placeholderTextColor={colors.muted} style={styles.input} testID="ml-dav" />
              </View>
            </View>

            <Pressable
              onPress={gerar}
              disabled={ml.isPending || semConexoes || selIds.size === 0}
              style={({ pressed }) => [styles.btnGerar, (ml.isPending || semConexoes || selIds.size === 0) && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}
              testID="ml-gerar"
            >
              {ml.isPending ? <ActivityIndicator color={colors.onBrandPrimary} />
                : <Text style={styles.btnGerarText}>Gerar Relatório</Text>}
            </Pressable>
          </View>
        ) : null}

        {ml.isError ? <Text style={styles.erro}>{ml.error?.message || "Erro ao gerar."}</Text> : null}

        {/* ---------------- RESUMO ---------------- */}
        {consolidado ? (
          <>
            <View style={styles.cardsRow}>
              <View style={styles.card}><Text style={styles.cardLbl}>Total Vendas</Text><Text style={styles.cardVal}>{brl(consolidado.total_venda)}</Text></View>
              <View style={styles.card}><Text style={styles.cardLbl}>Total Custos</Text><Text style={styles.cardVal}>{brl(consolidado.total_custo)}</Text></View>
            </View>
            <View style={styles.cardsRow}>
              <View style={styles.card}><Text style={styles.cardLbl}>Lucro</Text><Text style={[styles.cardVal, { color: colors.brandPrimary }]}>{brl(consolidado.lucro)}</Text></View>
              <View style={styles.card}><Text style={styles.cardLbl}>Margem %</Text><Text style={[styles.cardVal, { color: colors.brandPrimary }]}>{consolidado.margem_pct}%</Text></View>
            </View>
            <Text style={styles.resumoMeta}>{consolidado.qtd_empresas} empresa(s) · {consolidado.qtd_davs} DAV(s)</Text>

            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput value={busca} onChangeText={setBusca} placeholder="Buscar por DAV ou cliente…"
                placeholderTextColor={colors.muted} style={styles.searchInput} testID="ml-busca" />
            </View>

            {empresasFiltradas.map((e) => {
              const open = empExp[e.banco];
              return (
                <View key={`${e.empresa}-${e.banco}`} style={styles.empBox}>
                  <Pressable style={styles.empHead} onPress={() => setEmpExp((p) => ({ ...p, [e.banco]: !p[e.banco] }))}
                    testID={`ml-emp-head-${e.banco}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.empNome}>{e.empresa || e.banco}</Text>
                      {e.success
                        ? <Text style={styles.empSub}>{e.qtd_davs || 0} DAV(s) · Lucro {brl(e.lucro)} ({e.margem_pct}%)</Text>
                        : <Text style={styles.empErro}>Falha: {e.message || "erro"}</Text>}
                    </View>
                    {e.success ? <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} /> : null}
                  </Pressable>

                  {open && e.success ? (
                    (e.davs || []).length === 0
                      ? <Text style={styles.vazio}>Nenhum registro.</Text>
                      : (e.davs || []).map((d: MLDav) => {
                        const dkey = `${e.banco}-${d.tipo}-${d.codigo}`;
                        const dopen = davExp[dkey];
                        return (
                          <View key={dkey} style={styles.davBox}>
                            <Pressable style={styles.davHead} onPress={() => setDavExp((p) => ({ ...p, [dkey]: !p[dkey] }))}
                              testID={`ml-dav-${dkey}`}>
                              <View style={{ flex: 1 }}>
                                <Text style={styles.davTitle}>{d.tipo} #{d.codigo} · {brDate(d.data)}</Text>
                                <Text style={styles.davSub}>{d.cliente || "—"} · Lucro {brl(d.lucro)} ({d.margem_pct}%)</Text>
                              </View>
                              <Ionicons name={dopen ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
                            </Pressable>
                            {dopen ? (
                              <View style={styles.itensWrap}>
                                {d.itens.map((it, idx) => (
                                  <View key={idx} style={styles.itemRow}>
                                    <View style={{ flex: 1 }}>
                                      <Text style={styles.itemDesc} numberOfLines={1}>{it.codigo} · {it.descricao || "—"}</Text>
                                      <Text style={styles.itemMeta}>Qtd {it.qtd} · Líq {brl(it.preco_liquido)} · Custo {brl(it.total_custo)}</Text>
                                    </View>
                                    <View style={{ alignItems: "flex-end" }}>
                                      <Text style={styles.itemVenda}>{brl(it.total_venda)}</Text>
                                      <Text style={styles.itemMargem}>{it.margem_pct}%</Text>
                                    </View>
                                  </View>
                                ))}
                                <View style={styles.davTotRow}>
                                  <Text style={styles.davTotLbl}>Venda {brl(d.total_venda)} · Custo {brl(d.total_custo)}</Text>
                                </View>
                              </View>
                            ) : null}
                          </View>
                        );
                      })
                  ) : null}
                </View>
              );
            })}
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  headerTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  scroll: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  aviso: { color: colors.muted, fontSize: 13, marginBottom: spacing.sm },

  sectionToggle: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  sectionToggleText: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.onSurface },
  filtros: { gap: spacing.sm, marginBottom: spacing.md },
  label: { fontSize: 12, color: colors.muted, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.5, marginTop: spacing.xs },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  chipActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  chipTextActive: { color: colors.brandPrimary, fontWeight: "700" },
  dateRow: { flexDirection: "row", alignItems: "flex-end" },
  inputRow: { flexDirection: "row", alignItems: "flex-end" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderWidth: 1, borderColor: colors.border,
    fontSize: 14, color: colors.onSurface, minHeight: 42,
  },
  btnGerar: {
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    alignItems: "center", justifyContent: "center", paddingVertical: 14, marginTop: spacing.md,
  },
  btnGerarText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 15 },
  erro: { color: colors.danger, fontSize: 13, marginVertical: spacing.sm },

  cardsRow: { flexDirection: "row", gap: spacing.sm },
  card: {
    flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  cardLbl: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4 },
  cardVal: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  resumoMeta: { fontSize: 12, color: colors.muted, marginTop: 2, marginBottom: spacing.xs },

  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 8, borderWidth: 1, borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },

  empBox: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, marginBottom: spacing.sm, overflow: "hidden" },
  empHead: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  empNome: { fontSize: 14, fontWeight: "700", color: colors.onBrandPrimary },
  empSub: { fontSize: 11, color: colors.onBrandPrimary, opacity: 0.9, marginTop: 2 },
  empErro: { fontSize: 11, color: "#ffd2d2", marginTop: 2 },

  davBox: { borderTopWidth: 1, borderTopColor: colors.border },
  davHead: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.sm, backgroundColor: colors.surfaceSecondary },
  davTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  davSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  itensWrap: { paddingHorizontal: spacing.md, paddingBottom: spacing.sm },
  itemRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border, gap: spacing.sm },
  itemDesc: { fontSize: 13, color: colors.onSurface },
  itemMeta: { fontSize: 11, color: colors.muted, marginTop: 2 },
  itemVenda: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  itemMargem: { fontSize: 11, color: colors.brandPrimary, fontWeight: "600", marginTop: 2 },
  davTotRow: { paddingTop: 6 },
  davTotLbl: { fontSize: 11, color: colors.muted, textAlign: "right" },
  vazio: { fontSize: 12, color: colors.muted, padding: spacing.md },
});

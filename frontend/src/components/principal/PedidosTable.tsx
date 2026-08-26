// Tabela de movimento do dia (Checkout + Pedidos + OS), agrupada em
// acordion por tipo (pedido explícito do usuário, 2026-08-11: "acumule na
// lista as venda de checkout, pedidos e OS com acordion para cada um.
// expandido abrir a venda ou pré venda") + linha de total geral. Erros de
// carga do dashboard são mostrados via useFeedback() (toast centralizado)
// direto no hook (useDashboard.ts) — não renderizados inline aqui, regra
// [GLOBAL] "mensagens do sistema sempre no meio da tela", pedido explícito
// do usuário, 2026-07-18.
import { ActivityIndicator, Platform, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { colors } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";
import { SIT_COLOR } from "@/src/components/relatorio/styles";
import { usePermissions } from "@/src/permissions";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import { styles } from "./styles";
import { MovimentoItem } from "./useDashboard";

type Props = {
  movimento: MovimentoItem[];
  dashLoading: boolean;
  totalMovimento: number;
  // Filtro de situação ativo na tela ("" = Todos). Selo de situação por
  // linha só aparece com "Todos" — com um filtro específico já selecionado
  // (ex. só "Faturado"), todas as linhas teriam o mesmo selo, redundante.
  situacaoFiltro: string;
};

// Cor do selo por tipo de movimento — PED usa a cor padrão (brandTertiary/
// brandPrimary), OS já tinha cor própria (#E8F0FE/#2563EB), CHECKOUT (venda
// direta, sem Pedido/O.S.) ganhou a sua também, 2026-08-06.
const TIPO_BADGE_COLOR: Record<string, { bg: string; fg: string }> = {
  OS: { bg: "#E8F0FE", fg: "#2563EB" },
  CHECKOUT: { bg: "#FEF3E8", fg: "#C2661C" },
};

// Ordem fixa dos grupos — mesma ordem pedida pelo usuário ("checkout,
// pedidos e OS"), não a ordem em que os itens chegam da API. Um grupo sem
// nenhum item não renderiza sua seção — mesmo princípio já usado nos
// grupos de Relatórios (CLAUDE.md > "Card List Ordering" > "Relatórios
// groups").
const GRUPOS_MOVIMENTO: { tipo: MovimentoItem["tipo"]; label: string }[] = [
  { tipo: "CHECKOUT", label: "Checkout" },
  { tipo: "PED", label: "Pedidos" },
  { tipo: "OS", label: "O.S." },
];

export default function PedidosTable({ movimento, dashLoading, totalMovimento, situacaoFiltro }: Props) {
  const mostrarSituacao = !situacaoFiltro;
  const router = useRouter();
  const { can } = usePermissions();
  const openItem = (m: MovimentoItem) => {
    if (m.tipo === "OS") { router.push({ pathname: "/os-form", params: { codigo: String(m.doc) } }); return; }
    // Venda direta do Checkout (sem Pedido/O.S. por trás) — `m.doc` aqui é
    // um número de `comanda`, não de `pedido`; abre no Gestor de Comandas
    // (única tela hoje que visualiza uma comanda qualquer por número),
    // não em `/pedido-form`. Pedido explícito do usuário, 2026-08-06.
    if (m.tipo === "CHECKOUT") { router.push({ pathname: "/alterar-comanda", params: { comanda: String(m.doc) } }); return; }
    // Pedido Bar (PEDIDO.ABRIR) x Pedido Geral (PEDIDO_COMP.ABRIR) — antes
    // sempre ia pra `/pedido-form` (Bar), mesmo pra empresa usando o
    // segmento Geral/Clínica/Assistência; a tela Bar não tem os dados de
    // Agenda (só existem no lado Completo), então agendamentos configurados
    // simplesmente não apareciam ao abrir por aqui. Mesmo critério já usado
    // em `ModuleTiles.tsx`'s tile "Pedidos" — achado ao vivo 2026-07-28.
    const pathname = can("PEDIDO.ABRIR") ? "/pedido-form" : "/pedido-geral";
    router.push({ pathname, params: { pedido: String(m.doc) } } as never);
  };

  const renderRow = (m: MovimentoItem) => (
    <Pressable
      key={`${m.tipo}-${m.doc}`}
      onPress={() => openItem(m)}
      style={({ pressed }) => [styles.pedidoRow, pressed && { backgroundColor: colors.brandTertiary }]}
      testID={`mov-${m.tipo}-${m.doc}`}
    >
      <View style={[{ flexDirection: "row", alignItems: "center", gap: 6, flex: 1.1 }]}>
        <View
          style={{
            backgroundColor: TIPO_BADGE_COLOR[m.tipo]?.bg || colors.brandTertiary,
            borderRadius: 4,
            paddingHorizontal: 5,
            paddingVertical: 1,
          }}
        >
          <Text style={{ fontSize: 10, fontWeight: "700", color: TIPO_BADGE_COLOR[m.tipo]?.fg || colors.brandPrimary }}>
            {m.tipo}
          </Text>
        </View>
        <Text style={styles.pedidoCellValue}>#{m.doc}</Text>
      </View>
      <View style={[{ flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 }, Platform.OS === "web" && { flex: 2.1 }]}>
        <Text style={styles.pedidoCellValue} numberOfLines={1}>{m.cliente || "—"}</Text>
        {mostrarSituacao && m.situacaoLabel ? (
          <View
            style={{
              backgroundColor: (SIT_COLOR[m.situacao] || colors.muted) + "22",
              borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1,
            }}
            testID={`mov-situacao-${m.tipo}-${m.doc}`}
          >
            <Text style={{ fontSize: 10, fontWeight: "700", color: SIT_COLOR[m.situacao] || colors.muted }}>
              {m.situacaoLabel}
            </Text>
          </View>
        ) : null}
      </View>
      <Text style={[styles.pedidoCellValue, { flex: 1.5 }]} numberOfLines={1}>{m.vendedor || "—"}</Text>
      <Text style={[styles.pedidoCellValue, { flex: 1.2, textAlign: "right", fontWeight: "500" }]}>{formatBRL(m.valor)}</Text>
    </Pressable>
  );

  const grupos = GRUPOS_MOVIMENTO
    .map((g) => {
      const itens = movimento.filter((m) => m.tipo === g.tipo);
      const subtotal = itens.reduce((s, m) => s + (m.valor || 0), 0);
      return { ...g, itens, subtotal };
    })
    .filter((g) => g.itens.length > 0);

  return (
    <>
      <View style={[styles.pedidosHeader, Platform.OS === "web" && styles.pedidosHeaderWeb]}>
        <Text style={[styles.sectionTitle, Platform.OS === "web" && styles.sectionTitleWeb]}>Movimento de Hoje</Text>
        {dashLoading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
      </View>

      <View style={[styles.pedidosCard, Platform.OS === "web" && styles.pedidosCardWeb]} testID="principal-pedidos-list">
        <View style={styles.pedidosHead}>
          <Text style={[styles.pedidoCell, { flex: 1.1 }]}>Documento</Text>
          <Text style={[styles.pedidoCell, Platform.OS === "web" && { flex: 2.1 }]}>Cliente</Text>
          <Text style={[styles.pedidoCell, { flex: 1.5 }]}>Vendedor</Text>
          <Text style={[styles.pedidoCell, { flex: 1.2, textAlign: "right" }]}>Valor</Text>
        </View>
        {movimento.length === 0 && !dashLoading ? (
          <Text style={styles.empty}>Nenhum movimento hoje.</Text>
        ) : (
          grupos.map((g) => (
            <AccordionSection
              key={g.tipo}
              title={`${g.label} (${g.itens.length}) · ${formatBRL(g.subtotal)}`}
              testID={`mov-grupo-${g.tipo}`}
            >
              {g.itens.map(renderRow)}
            </AccordionSection>
          ))
        )}
        {movimento.length > 0 ? (
          <View style={styles.pedidoTotalRow} testID="principal-pedidos-total">
            <Text style={[styles.pedidoTotalLabel, { flex: 4.7 }]}>Total ({movimento.length})</Text>
            <Text style={[styles.pedidoTotalValue, { flex: 1.2, textAlign: "right" }]}>{formatBRL(totalMovimento)}</Text>
          </View>
        ) : null}
      </View>
    </>
  );
}

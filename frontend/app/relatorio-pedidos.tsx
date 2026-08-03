import { Platform, Pressable, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { styles } from "@/src/components/relatorio/styles";
import { useRelatorioPedidos } from "@/src/components/relatorio/useRelatorioPedidos";
import Filtros from "@/src/components/relatorio/Filtros";
import TotaisBox from "@/src/components/relatorio/TotaisBox";
import PedidoCard from "@/src/components/relatorio/PedidoCard";

export default function RelatorioPedidosScreen() {
  const isWeb = Platform.OS === "web";
  const r = useRelatorioPedidos();

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-pedidos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => r.router.back()} hitSlop={12} style={styles.backBtn} testID="relpedidos-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Relatório de Pedidos</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
        <View style={isWeb ? styles.filtersWeb : undefined}>
        <Filtros
          dataIni={r.dataIni} setDataIni={r.setDataIni}
          dataFim={r.dataFim} setDataFim={r.setDataFim}
          vendedorOpts={r.vendedorOpts} vendedor={r.vendedor} setVendedor={r.setVendedor}
          situacao={r.situacao} setSituacao={r.setSituacao}
          projeto={r.projeto} setProjeto={r.setProjeto}
          loading={r.loading} onBuscar={r.buscar}
        />
        </View>

        {!r.loading && !r.error && r.pedidos.length === 0 ? (
          <Text style={styles.empty}>Nenhum pedido no período/filtros.</Text>
        ) : null}

        {r.totais && r.pedidos.length > 0 ? <TotaisBox totais={r.totais} /> : null}

        {r.pedidos.length > 0 ? <Text style={styles.count}>{r.pedidos.length} pedido(s)</Text> : null}

        {r.pedidos.map((p) => (
          <PedidoCard
            key={p.pedido}
            pedido={p}
            open={r.expandedId === p.pedido}
            analise={r.analises[p.pedido]}
            onToggle={r.toggleExpand}
          />
        ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

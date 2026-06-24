import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import SelectField from "@/src/components/SelectField";
import { colors } from "@/src/theme/colors";
import { styles } from "@/src/components/principal/styles";
import { useDashboard } from "@/src/components/principal/useDashboard";
import WelcomeHero from "@/src/components/principal/WelcomeHero";
import ModuleTiles from "@/src/components/principal/ModuleTiles";
import SituacaoFilter from "@/src/components/principal/SituacaoFilter";
import TotalsCards from "@/src/components/principal/TotalsCards";
import PedidosTable from "@/src/components/principal/PedidosTable";

export default function PrincipalScreen() {
  const d = useDashboard();

  if (d.loading || !d.session) {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]}>
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="principal-screen">
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Back-On</Text>
          <Text style={styles.headerSub} numberOfLines={1}>{d.fantasia || d.session.empresa}</Text>
        </View>
        <Pressable
          onPress={d.handleLogout}
          style={({ pressed }) => [styles.logoutBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="principal-logout-button"
        >
          <Ionicons name="log-out-outline" size={18} color={colors.onBrandPrimary} />
          <Text style={styles.logoutLabel}>Sair</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        <WelcomeHero
          empresa={d.session.empresa}
          logo={d.session.logo}
          displayName={d.displayName}
          nomeGuerra={d.nomeGuerra}
          classe={d.classe}
        />

        <Text style={styles.sectionTitle}>Tela Principal</Text>
        <Text style={styles.sectionSub}>Painel de controle. Os módulos do sistema são exibidos abaixo.</Text>

        <ModuleTiles />

        {d.isManager ? (
          <View style={styles.filterRow} testID="principal-vendedor-filter">
            <SelectField
              label="Filtrar por vendedor"
              value={d.vendedorFiltro}
              onChange={d.setVendedorFiltro}
              options={d.vendedorOpts}
              placeholder="Todos os vendedores"
              modalTitle="Selecionar vendedor"
              allowClear
              testID="principal-vendedor-select"
            />
          </View>
        ) : null}

        <SituacaoFilter value={d.situacaoFiltro} onChange={d.handleSituacao} />

        <TotalsCards totais={d.totais} dashLoading={d.dashLoading} />

        <PedidosTable
          pedidos={d.pedidos}
          dashLoading={d.dashLoading}
          dashError={d.dashError}
          totalPedidos={d.totalPedidos}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

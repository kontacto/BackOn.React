import { ActivityIndicator, Image, Pressable, ScrollView, Text, View } from "react-native";
import { Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@/src/components/Ionicons";

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
  const isWeb = Platform.OS === "web";

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
        <View style={styles.headerLeft}>
          <Image
            source={require("../../assets/images/kontacto-logo.png")}
            style={styles.headerLogo}
            resizeMode="contain"
            accessibilityLabel="Kontacto"
          />
        </View>
        <View style={styles.headerCenter}>
          <Text style={[styles.headerSub, isWeb && styles.headerSubWeb]} numberOfLines={1}>
            {d.fantasia || d.session.empresa}
          </Text>
        </View>
        <View style={styles.headerRight}>
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
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, Platform.OS === "web" && styles.scrollWeb]}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          {Platform.OS === "web" ? (
            <>
              <WelcomeHero
                empresa={d.session.empresa}
                logo={d.session.logo}
                displayName={d.displayName}
                nomeGuerra={d.nomeGuerra}
                classe={d.classe}
              />

              <Text style={[styles.sectionTitle, styles.sectionTitleWeb]}>Tela Principal</Text>
              <Text style={[styles.sectionSub, styles.sectionSubWeb]}>Painel de controle. Os módulos do sistema são exibidos abaixo.</Text>

              <ModuleTiles />

              <SituacaoFilter value={d.situacaoFiltro} onChange={d.handleSituacao} />

              <TotalsCards
                totais={d.totais}
                dashLoading={d.dashLoading}
                showTotais={d.showTotais}
                showMargem={d.showMargem}
                showDescontos={d.showDescontos}
              />

              <PedidosTable
                movimento={d.movimento}
                dashLoading={d.dashLoading}
                dashError={d.dashError}
                totalMovimento={d.totalMovimento}
              />
            </>
          ) : (
            <>
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

              <SituacaoFilter value={d.situacaoFiltro} onChange={d.handleSituacao} />

              <TotalsCards
                totais={d.totais}
                dashLoading={d.dashLoading}
                showTotais={d.showTotais}
                showMargem={d.showMargem}
                showDescontos={d.showDescontos}
              />

              <PedidosTable
                movimento={d.movimento}
                dashLoading={d.dashLoading}
                dashError={d.dashError}
                totalMovimento={d.totalMovimento}
              />
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

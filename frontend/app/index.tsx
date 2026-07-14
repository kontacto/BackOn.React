import { useEffect } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { hasConnections } from "@/src/utils/storage/connections";
import { colors, spacing } from "@/src/theme/colors";
import { AppImage } from "@/src/components/AppImage";

export default function SplashScreen() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const hasAny = await hasConnections();
        if (cancelled) return;
        if (hasAny) {
          router.replace("/login");
        } else {
          router.replace("/connections?initial=1");
        }
      } catch {
        if (!cancelled) router.replace("/connections?initial=1");
      }
    }, 1600);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [router]);

  return (
    <View style={styles.container} testID="splash-screen">
      <View style={styles.center}>
        <AppImage
          source={require("../assets/images/kontacto-logo.png")}
          style={styles.logo}
          contentFit="contain"
          testID="splash-logo"
        />
        <Text style={styles.brand} testID="splash-brand">
          Back-On
        </Text>
        <Text style={styles.tagline}>Acesso Corporativo Seguro</Text>
        <ActivityIndicator
          color={colors.onSurfaceInverse}
          style={{ marginTop: spacing.xxl }}
          testID="splash-loader"
        />
      </View>
      <Text style={styles.footer}>by Kontacto Sistemas</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.brandPrimary,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
  },
  logo: {
    width: 220,
    height: 220,
    marginBottom: spacing.lg,
  },
  brand: {
    fontSize: 32,
    fontWeight: "500",
    color: colors.onSurfaceInverse,
    letterSpacing: -0.5,
  },
  tagline: {
    marginTop: spacing.sm,
    fontSize: 14,
    fontWeight: "400",
    color: "rgba(255,255,255,0.75)",
  },
  footer: {
    textAlign: "center",
    color: "rgba(255,255,255,0.6)",
    fontSize: 12,
    paddingBottom: spacing.xl,
  },
});

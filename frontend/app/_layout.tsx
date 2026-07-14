import { Stack, usePathname } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { PermissionsProvider } from "@/src/permissions";
import { FeedbackProvider } from "@/src/components/feedback/FeedbackProvider";
import { WindowsStack } from "@/src/navigation/WindowsStack";
import Sidebar from "@/src/navigation/Sidebar";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

// Keep the native splash visible from cold start until icon fonts register.
// Required because @expo/vector-icons' componentDidMount fallback fires
// Font.loadAsync against a broken vendor path if any <Icon> mounts before
// the family is registered — which throws on Android Expo Go.
SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [loaded, error] = useIconFonts();
  const pathname = usePathname();

  useEffect(() => {
    if (loaded || error) {
      SplashScreen.hideAsync();
    }
  }, [loaded, error]);

  useEffect(() => {
    if (Platform.OS === "web" && typeof document !== "undefined") {
      document.title = "Back-On";
    }
  }, [pathname]);

  // If the CDN is unreachable we fall through on error rather than wedging
  // the app — icons will tofu, but the app still boots.
  if (!loaded && !error) return null;

  return (
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <PermissionsProvider>
          <View style={styles.shell}>
            <View style={[styles.canvas, Platform.OS === "web" && styles.canvasWeb]}>
              <View style={[styles.body, Platform.OS === "web" && styles.bodyWeb]}>
                {Platform.OS === "web" && <Sidebar />}
                <View style={styles.content}>
                  {Platform.OS === "windows" ? (
                    <WindowsStack screenOptions={{ headerShown: false, title: "Back-On" }} />
                  ) : (
                    <Stack screenOptions={{ headerShown: false, title: "Back-On" }} />
                  )}
                </View>
              </View>
            </View>
          </View>
        </PermissionsProvider>
      </FeedbackProvider>
    </QueryClientProvider>
  );
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
    backgroundColor: "#EAF0F8",
  },
  canvas: {
    flex: 1,
  },
  canvasWeb: {
    width: "100%",
    maxWidth: 1440,
    alignSelf: "center",
    backgroundColor: "#F4F6FB",
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderColor: "rgba(0,0,0,0.04)",
  },
  body: {
    flex: 1,
  },
  bodyWeb: {
    flexDirection: "row",
  },
  content: {
    flex: 1,
  },
});

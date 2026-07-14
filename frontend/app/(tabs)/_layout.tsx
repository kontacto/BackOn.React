import { Tabs } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { Platform } from "react-native";

import { usePermissions } from "@/src/permissions";
import { colors } from "@/src/theme/colors";

export default function TabsLayout() {
  const isWeb = Platform.OS === "web";
  const { moduleOn } = usePermissions();
  // Igual a "Financeiro" (web-only via `href`), mais o módulo "Posto"
  // ligado em Configurações > Módulos e Recursos (controle_configuracao.
  // Posto) — mesmo mecanismo que já liga/desliga Serviços, Veículos etc.
  // em Cadastros. Ver "Posto de Combustível" na memória de projeto.
  const postoVisivel = isWeb && moduleOn("Posto");

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarPosition: isWeb ? "left" : "bottom",
        tabBarLabelPosition: isWeb ? "beside-icon" : "below-icon",
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarActiveBackgroundColor: isWeb ? colors.surfaceSecondary : undefined,
        tabBarInactiveTintColor: colors.muted,
        // No web o menu vertical persistente vive em `src/navigation/Sidebar.tsx`
        // (renderizado no layout raiz, fora do Tabs, pra ficar visível em
        // qualquer tela do sistema — não só nestas 7 abas). A barra própria
        // do Tabs fica escondida aqui pra não duplicar.
        tabBarStyle: {
          backgroundColor: colors.surface,
          ...(isWeb
            ? { display: "none" }
            : {
                borderTopColor: colors.border,
              }),
        },
        tabBarItemStyle: isWeb
          ? {
              paddingVertical: 10,
              paddingHorizontal: 12,
              justifyContent: "flex-start",
              gap: 8,
            }
          : undefined,
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: "500",
          marginLeft: 0,
        },
        tabBarIconStyle: isWeb ? { marginRight: 2 } : undefined,
      }}
    >
      <Tabs.Screen
        name="principal"
        options={{
          title: "Início",
          tabBarIcon: ({ color, size }) => <Ionicons name="home-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="cadastros"
        options={{
          title: "Cadastros",
          tabBarIcon: ({ color, size }) => <Ionicons name="albums-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="transacoes"
        options={{
          title: "Transações",
          href: isWeb ? undefined : null,
          tabBarIcon: ({ color, size }) => <Ionicons name="swap-horizontal-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="financeiro"
        options={{
          title: "Financeiro",
          href: isWeb ? undefined : null,
          tabBarIcon: ({ color, size }) => <Ionicons name="cash-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="posto-combustivel"
        options={{
          title: "Posto",
          href: postoVisivel ? undefined : null,
          tabBarIcon: ({ color, size }) => <Ionicons name="water-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="configuracoes"
        options={{
          title: "Configurações",
          tabBarIcon: ({ color, size }) => <Ionicons name="settings-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="relatorios"
        options={{
          title: "Relatórios",
          tabBarIcon: ({ color, size }) => <Ionicons name="bar-chart-outline" size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}

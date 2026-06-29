import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { Connection, listConnections } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";

type Campo = { campo: string; label: string };

export default function ModulosRecursosScreen() {
  const router = useRouter();
  const { reload: reloadPermissions } = usePermissions();
  const fb = useFeedback();
  const [conn, setConn] = useState<Connection | null>(null);
  const [campos, setCampos] = useState<Campo[]>([]);
  const [valores, setValores] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const boot = useCallback(async () => {
    setLoading(true);
    const session = await getSession();
    const conns = await listConnections();
    const c = conns.find((x) => x.empresa === session?.empresa) ?? null;
    setConn(c);
    if (!c) {
      fb.showError("Conexão não encontrada.");
      setLoading(false);
      return;
    }
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [campR, cfgR] = await Promise.all([
        fetch(`${base}/api/controle-config/campos`).then((r) => r.json()),
        fetch(`${base}/api/controle-config?${qs}`).then((r) => r.json()),
      ]);
      if (campR?.campos) setCampos(campR.campos);
      if (cfgR?.success) setValores(cfgR.valores || {});
      else fb.showError(cfgR?.message || "Erro ao carregar configuração.");
    } catch (e) {
      fb.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [fb]);

  useFocusEffect(
    useCallback(() => {
      boot();
    }, [boot])
  );

  const toggle = (campo: string) => {
    setValores((v) => ({ ...v, [campo]: !v[campo] }));
  };

  const handleSave = async () => {
    if (!conn) return;
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/controle-config/salvar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, valores }),
      }).then((x) => x.json());
      if (r?.success) {
        fb.showSuccess(r.message || "Salvo.");
        await reloadPermissions();
      } else {
        fb.showError(r?.message || "Erro ao salvar.");
      }
    } catch (e) {
      fb.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="modulos-recursos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Módulos e Recursos</Text>
        <View style={{ width: 40 }} />
      </View>

      <Text style={styles.intro}>
        Ative os módulos que esta empresa utiliza. Módulos desativados ficam ocultos no sistema
        inteiro — inclusive na configuração de Permissões.
      </Text>

      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} />
      ) : (
        <FlatList
          data={campos}
          keyExtractor={(c) => c.campo}
          renderItem={({ item }) => {
            const on = !!valores[item.campo];
            return (
              <Pressable style={styles.row} onPress={() => toggle(item.campo)} testID={`mod-${item.campo}`}>
                <Ionicons
                  name={on ? "checkbox" : "square-outline"}
                  size={22}
                  color={on ? colors.brandPrimary : colors.muted}
                />
                <Text style={styles.rowLabel}>{item.label}</Text>
              </Pressable>
            );
          }}
          contentContainerStyle={{ paddingVertical: spacing.sm, paddingBottom: 110 }}
        />
      )}

      {!loading && conn ? (
        <Pressable
          onPress={handleSave}
          disabled={saving}
          style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.8 }]}
          testID="mod-save"
        >
          {saving ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <>
              <Ionicons name="save-outline" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.saveLabel}>Salvar</Text>
            </>
          )}
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.sm,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", color: colors.onBrandPrimary, fontSize: 17, fontWeight: "600" },
  intro: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, color: colors.muted, fontSize: 13, lineHeight: 18 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 12,
    paddingHorizontal: spacing.lg,
    minHeight: 48,
  },
  rowLabel: { fontSize: 15, color: colors.onSurface, flex: 1 },
  saveBtn: {
    position: "absolute",
    left: spacing.lg,
    right: spacing.lg,
    bottom: spacing.lg,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
    paddingVertical: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    elevation: 6,
  },
  saveLabel: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "600" },
});

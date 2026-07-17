import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Image, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { Connection, listConnections } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";

type Campo = { campo: string; label: string };

// "Bar", "Cilindro" e "Pedido de Venda" são 3 versões diferentes da mesma
// tela de Pedido de Venda (segmentos de negócio distintos) — mutuamente
// exclusivos, nunca mais de um ligado ao mesmo tempo. [GLOBAL],
// 2026-07-15, user-directed. Ficam agrupados sob "Pedidos" no topo da
// lista, quebrando a ordem alfabética só nesse caso (mesma exceção já
// aplicada ao Painel Posto de Combustível — ver CLAUDE.md > "Card List
// Ordering").
const SEGMENTOS_PEDIDO_EXCLUSIVOS = ["Bar", "Cilindro", "Pedido_venda"];

export default function ModulosRecursosScreen() {
  const router = useRouter();
  const { reload: reloadPermissions } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const [conn, setConn] = useState<Connection | null>(null);
  const [campos, setCampos] = useState<Campo[]>([]);
  const [valores, setValores] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const boot = useCallback(async () => {
    setLoading(true);
    const session = await getSession();
    if (!session) {
      router.replace("/login");
      setLoading(false);
      return;
    }
    const conns = await listConnections();
    const c = conns.find((x) => x.empresa === session.empresa) ?? null;
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
    setValores((v) => {
      const novo = !v[campo];
      if (novo && SEGMENTOS_PEDIDO_EXCLUSIVOS.includes(campo)) {
        // Ligar um dos 3 segmentos de Pedido de Venda desliga os outros
        // dois automaticamente — mutuamente exclusivos.
        const next = { ...v };
        SEGMENTOS_PEDIDO_EXCLUSIVOS.forEach((c) => { next[c] = c === campo; });
        return next;
      }
      return { ...v, [campo]: novo };
    });
  };

  const handleSave = async () => {
    if (!conn) return;
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/controle-config/salvar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, valores }),
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

  const pedidosCampos = SEGMENTOS_PEDIDO_EXCLUSIVOS
    .map((c) => campos.find((x) => x.campo === c))
    .filter((c): c is Campo => !!c);
  const outrosCampos = campos.filter((c) => !SEGMENTOS_PEDIDO_EXCLUSIVOS.includes(c.campo));

  const renderRow = (item: Campo) => {
    const on = !!valores[item.campo];
    return (
      <Pressable key={item.campo} style={styles.row} onPress={() => toggle(item.campo)} testID={`mod-${item.campo}`}>
        <Ionicons
          name={on ? "checkbox" : "square-outline"}
          size={22}
          color={on ? colors.brandPrimary : colors.muted}
        />
        <Text style={styles.rowLabel}>{item.label}</Text>
      </Pressable>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="modulos-recursos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
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
          data={outrosCampos}
          keyExtractor={(c) => c.campo}
          renderItem={({ item }) => renderRow(item)}
          ListHeaderComponent={
            pedidosCampos.length > 0 ? (
              <View testID="mod-grupo-pedidos">
                <Text style={styles.groupTitle}>Pedidos</Text>
                <Text style={styles.groupHint}>
                  Bar, Cilindro e Pedido de Venda são versões diferentes da mesma tela — só uma pode ficar ativa.
                </Text>
                {pedidosCampos.map((item) => renderRow(item))}
                <View style={styles.groupDivider} />
              </View>
            ) : null
          }
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
  groupTitle: {
    fontSize: 12, fontWeight: "700", color: colors.brandPrimary, textTransform: "uppercase",
    letterSpacing: 0.5, paddingHorizontal: spacing.lg, paddingTop: spacing.sm,
  },
  groupHint: { fontSize: 12, color: colors.muted, paddingHorizontal: spacing.lg, marginTop: 2, marginBottom: 4 },
  groupDivider: { height: 1, backgroundColor: colors.border, marginHorizontal: spacing.lg, marginTop: spacing.sm, marginBottom: spacing.xs },
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

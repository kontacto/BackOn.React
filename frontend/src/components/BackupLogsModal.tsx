// Modal "Ver Logs de Backup" — histórico das execuções do Backup
// Programado (backend/services/backup_sistema_service.py). Pedido
// explícito do usuário (2026-08-28): registrar E visualizar os logs
// através de um botão — mesmo padrão de modal já usado no resto do app
// (ver AjudaPedidoModal.tsx como referência estrutural).
import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles as ps } from "@/src/components/pedido/styles";
import type { BackupLogItem } from "@/src/hooks/useBackupSistemaForm";

const isWeb = Platform.OS === "web";

type Props = {
  visible: boolean;
  onClose: () => void;
  onLoad: () => Promise<BackupLogItem[]>;
};

function formatQuando(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR");
  } catch {
    return iso;
  }
}

export default function BackupLogsModal({ visible, onClose, onLoad }: Props) {
  const [loading, setLoading] = useState(false);
  const [itens, setItens] = useState<BackupLogItem[]>([]);

  useEffect(() => {
    if (!visible) return;
    (async () => {
      setLoading(true);
      const r = await onLoad();
      setItens(r);
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  if (!visible) return null;
  return (
    <View
      style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: "rgba(0,0,0,0.45)",
        alignItems: "center", justifyContent: isWeb ? "center" : "flex-end",
        paddingHorizontal: isWeb ? spacing.xl : 0,
        zIndex: 1000,
      }}
    >
      <Pressable style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }} onPress={onClose} />
      <View style={[ps.modalCard, isWeb && ps.modalCardWebCompact, { maxHeight: "82%" }]}>
        <View style={ps.modalHeader}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="time-outline" size={20} color={colors.brandPrimary} />
            <Text style={ps.modalTitle}>Logs de Backup</Text>
          </View>
          <Pressable onPress={onClose} hitSlop={8} testID="backup-logs-fechar">
            <Ionicons name="close" size={22} color={colors.muted} />
          </Pressable>
        </View>

        {loading ? (
          <View style={{ paddingVertical: spacing.xl, alignItems: "center" }}>
            <ActivityIndicator color={colors.brandPrimary} />
          </View>
        ) : itens.length === 0 ? (
          <Text style={{ fontSize: 13, color: colors.muted, paddingVertical: spacing.lg, textAlign: "center" }}>
            Nenhum backup registrado ainda.
          </Text>
        ) : (
          <ScrollView style={{ maxHeight: 480 }}>
            <View style={{ gap: spacing.sm }}>
              {itens.map((item) => (
                <View
                  key={item.codigo}
                  style={{
                    flexDirection: "row", gap: spacing.sm, alignItems: "flex-start",
                    paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
                  }}
                  testID={`backup-log-item-${item.codigo}`}
                >
                  <Ionicons
                    name={item.sucesso ? "checkmark-circle" : "alert-circle"}
                    size={18}
                    color={item.sucesso ? colors.success : colors.error}
                    style={{ marginTop: 2 }}
                  />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>
                      {formatQuando(item.data_hora)} — {item.destino === "BLOB" ? "Nuvem (Blob)" : "Local"}
                      {item.tamanho_mb != null ? ` — ${item.tamanho_mb.toFixed(1)} MB` : ""}
                      {item.duracao_segundos != null ? ` — ${item.duracao_segundos}s` : ""}
                    </Text>
                    {item.mensagem ? (
                      <Text style={{ fontSize: 12, color: item.sucesso ? colors.muted : colors.error, marginTop: 2 }}>
                        {item.mensagem}
                      </Text>
                    ) : null}
                    {item.caminho_ou_url ? (
                      <Text style={{ fontSize: 11, color: colors.muted, marginTop: 2 }} numberOfLines={1}>
                        {item.caminho_ou_url}
                      </Text>
                    ) : null}
                  </View>
                </View>
              ))}
            </View>
          </ScrollView>
        )}
      </View>
    </View>
  );
}

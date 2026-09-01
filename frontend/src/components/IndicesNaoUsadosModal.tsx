// Modal "Índices não utilizados" — relatório (NUNCA ação automática) da
// Manutenção Automática de Índices (backend/services/manutencao_indices_
// service.py::_listar_indices_nao_usados_sync). Achado real que motivou:
// análise DBA de RJPNEUS-TESTE (Áureo, 2026-08-31) achou dezenas de
// índices com nome sequencial genérico (os_1...os_22 etc.) sem nenhum uso
// registrado desde o boot da instância — candidatos a revisão manual,
// nunca dropados sozinhos (a janela de uso medida pode ser curta demais
// pra cobrir uma rotina mensal/trimestral real). Mesmo padrão estrutural
// de BackupLogsModal.tsx.
import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles as ps } from "@/src/components/pedido/styles";
import type { IndiceNaoUsado } from "@/src/hooks/useServicoSistemaForm";

const isWeb = Platform.OS === "web";

type Props = {
  visible: boolean;
  onClose: () => void;
  onLoad: () => Promise<IndiceNaoUsado[]>;
};

export default function IndicesNaoUsadosModal({ visible, onClose, onLoad }: Props) {
  const [loading, setLoading] = useState(false);
  const [itens, setItens] = useState<IndiceNaoUsado[]>([]);

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
            <Ionicons name="analytics-outline" size={20} color={colors.brandPrimary} />
            <Text style={ps.modalTitle}>Índices Não Utilizados</Text>
          </View>
          <Pressable onPress={onClose} hitSlop={8} testID="indices-nao-usados-fechar">
            <Ionicons name="close" size={22} color={colors.muted} />
          </Pressable>
        </View>

        <Text style={{ fontSize: 12, color: colors.muted, marginBottom: spacing.sm }}>
          Índices sem nenhum uso registrado desde a última reinicialização do banco — não foram apagados
          automaticamente, é só uma lista pra revisão manual. Um índice usado só numa rotina mensal/trimestral
          pode aparecer aqui sem ser realmente "morto" — confirme antes de decidir remover algum.
        </Text>

        {loading ? (
          <View style={{ paddingVertical: spacing.xl, alignItems: "center" }}>
            <ActivityIndicator color={colors.brandPrimary} />
          </View>
        ) : itens.length === 0 ? (
          <Text style={{ fontSize: 13, color: colors.muted, paddingVertical: spacing.lg, textAlign: "center" }}>
            Nenhum índice candidato encontrado.
          </Text>
        ) : (
          <ScrollView style={{ maxHeight: 480 }}>
            <View style={{ gap: spacing.sm }}>
              {itens.map((item, i) => (
                <View
                  key={`${item.tabela}.${item.indice}.${i}`}
                  style={{
                    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
                    paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
                  }}
                  testID={`indice-nao-usado-item-${i}`}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>{item.tabela}</Text>
                    <Text style={{ fontSize: 12, color: colors.muted }}>{item.indice}</Text>
                  </View>
                  <Text style={{ fontSize: 12, color: colors.muted }}>
                    {((item.paginas * 8) / 1024).toFixed(1)} MB
                  </Text>
                </View>
              ))}
            </View>
          </ScrollView>
        )}
      </View>
    </View>
  );
}

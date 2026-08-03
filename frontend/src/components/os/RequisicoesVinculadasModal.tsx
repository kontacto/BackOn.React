// Requisições vinculadas a O.S. — migração da aba "Requisições vinculadas
// a O.S." (`GridReq`, `Sub Requisicoes()`) em `Revenda\FrmTraOsNew.frm`.
// 100% somente leitura no legado (sem Click/DblClick na grade, sem outro
// controle no frame) — replicado aqui como consulta pura, sem nenhuma ação
// de escrita. Une os dois mecanismos de vínculo que o legado usa
// (`os_requisicao` + `requisicao.tipo_mov_requisicao`/`codigo_requisicao`)
// — ver `os_completo_service.py` pro detalhe da query.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles } from "@/src/components/pedido/styles";
import { formatBRL } from "@/src/utils/format";
import { apiGet } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";

const isWeb = Platform.OS === "web";

type RequisicaoItem = {
  requisicao: number;
  data: string | null;
  cod_fab: string;
  descricao: string;
  qtd: number;
  p_unit: number;
  p_total: number;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  osId: number;
};

export default function RequisicoesVinculadasModal({ visible, onClose, conn, osId }: Props) {
  const [items, setItems] = useState<RequisicaoItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!conn || !osId) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, `/api/os-completo/${osId}/requisicoes-vinculadas`);
      setItems(j?.success ? (j.items || []) : []);
      setTotal(j?.success ? (j.total || 0) : 0);
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [conn, osId]);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Requisições Vinculadas</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <View style={styles.itensHint}>
            <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
            <Text style={styles.itensHintText}>
              Produtos requisitados do estoque vinculados a esta O.S. — somente consulta, sem edição aqui.
            </Text>
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
          <ScrollView style={{ maxHeight: 380 }}>
            {items.map((item, idx) => (
              <View key={`${item.requisicao}-${idx}`} style={rs.row}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={rs.desc} numberOfLines={1}>{item.descricao || item.cod_fab}</Text>
                  <Text style={rs.sub} numberOfLines={1}>
                    Requisição #{item.requisicao}{item.data ? ` · ${item.data.split("-").reverse().join("/")}` : ""}
                    {item.cod_fab ? ` · ${item.cod_fab}` : ""} · {item.qtd} × {formatBRL(item.p_unit)}
                  </Text>
                </View>
                <Text style={rs.total}>{formatBRL(item.p_total)}</Text>
              </View>
            ))}
            {!loading && items.length === 0 ? <Text style={styles.emptyText}>Nenhuma requisição vinculada a esta O.S.</Text> : null}
          </ScrollView>
          {items.length > 0 ? (
            <View style={rs.totalRow}>
              <Text style={rs.totalLabel}>TOTAL</Text>
              <Text style={rs.totalValue}>{formatBRL(total)}</Text>
            </View>
          ) : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const rs = {
  row: {
    flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  desc: { fontSize: 13, fontWeight: "600" as const, color: colors.onSurface },
  sub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  total: { fontSize: 13, fontWeight: "700" as const, color: colors.onSurface },
  totalRow: {
    flexDirection: "row" as const, justifyContent: "space-between" as const, alignItems: "center" as const,
    marginTop: spacing.sm, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border,
  },
  totalLabel: { fontSize: 12, fontWeight: "700" as const, color: colors.muted },
  totalValue: { fontSize: 15, fontWeight: "700" as const, color: colors.brandPrimary },
};

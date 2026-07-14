// Seção "Cliente": seletor (abre busca) + resumo (telefone, endereço, e-mail).
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { styles } from "./styles";
import { ClienteRow, ClienteResumo } from "./types";

type Props = {
  cliente: ClienteRow | null;
  clienteResumo: ClienteResumo | null;
  loadingResumo: boolean;
  onOpenSearch: () => void;
};

export default function ClienteSection({ cliente, clienteResumo, loadingResumo, onOpenSearch }: Props) {
  return (
    <>
      <Text style={styles.sectionTitle}>Cliente</Text>
      <Pressable
        onPress={onOpenSearch}
        style={({ pressed }) => [styles.clienteBox, pressed && { opacity: 0.8 }]}
        testID="pedido-form-cliente-select"
      >
        {cliente ? (
          <View style={{ flex: 1 }}>
            <Text style={styles.clienteNome} numberOfLines={1}>{cliente.nome}</Text>
            <Text style={styles.clienteSub} numberOfLines={1}>
              #{cliente.codigo}{cliente.cgc_cpf ? ` · ${cliente.cgc_cpf}` : ""}
            </Text>
          </View>
        ) : (
          <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="search" size={18} color={colors.muted} />
            <Text style={[styles.clienteSub, { fontSize: 14 }]}>Buscar cliente por nome, CPF ou telefone…</Text>
          </View>
        )}
        <Ionicons name="chevron-forward" size={18} color={colors.muted} />
      </Pressable>

      {cliente ? (
        <View style={styles.resumoBox} testID="pedido-form-cliente-resumo">
          {loadingResumo ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <ActivityIndicator size="small" color={colors.brandPrimary} />
              <Text style={styles.resumoText}>Carregando dados…</Text>
            </View>
          ) : clienteResumo ? (
            <>
              <View style={styles.resumoRow}>
                <Ionicons name="call-outline" size={14} color={colors.brandPrimary} />
                <Text style={styles.resumoText} numberOfLines={1}>{clienteResumo.telefone || "Sem telefone"}</Text>
              </View>
              <View style={styles.resumoRow}>
                <Ionicons name="location-outline" size={14} color={colors.brandPrimary} />
                <Text style={styles.resumoText} numberOfLines={2}>{clienteResumo.endereco || "Sem endereço cadastrado"}</Text>
              </View>
              {clienteResumo.e_mail ? (
                <View style={styles.resumoRow}>
                  <Ionicons name="mail-outline" size={14} color={colors.brandPrimary} />
                  <Text style={styles.resumoText} numberOfLines={1}>{clienteResumo.e_mail}</Text>
                </View>
              ) : null}
            </>
          ) : (
            <Text style={styles.resumoText}>Dados do cliente indisponíveis.</Text>
          )}
        </View>
      ) : null}
    </>
  );
}

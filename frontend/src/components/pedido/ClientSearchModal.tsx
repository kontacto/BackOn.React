// Modal de busca de cliente (por nome, CPF/CNPJ ou telefone) com opção de cadastrar.
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { styles } from "./styles";
import { ClienteRow } from "./types";

const isWeb = Platform.OS === "web";

type Props = {
  visible: boolean;
  onClose: () => void;
  term: string;
  setTerm: (v: string) => void;
  loading: boolean;
  results: ClienteRow[];
  onPick: (c: ClienteRow) => void;
  onCreate: () => void;
};

export default function ClientSearchModal({
  visible, onClose, term, setTerm, loading, results, onPick, onCreate,
}: Props) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Buscar Cliente</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <View style={styles.searchWrap}>
            <Ionicons name="search" size={16} color={colors.muted} />
            <TextInput
              value={term}
              onChangeText={setTerm}
              placeholder="Nome, CPF/CNPJ ou telefone…"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
              autoFocus
              testID="pedido-form-search-input"
              autoComplete="off"
              autoCorrect={false}
              textContentType="none"
              importantForAutofill="no"
            />
          </View>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
          <ScrollView style={{ maxHeight: 380 }}>
            {results.map((c) => (
              <Pressable
                key={c.codigo}
                onPress={() => onPick(c)}
                style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                testID={`pedido-form-result-${c.codigo}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.resultNome} numberOfLines={1}>{c.nome}</Text>
                  <Text style={styles.resultSub} numberOfLines={1}>
                    #{c.codigo}{c.cgc_cpf ? ` · ${c.cgc_cpf}` : ""}{c.telefone ? ` · ${c.telefone}` : ""}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
            {!loading && term.length >= 2 && results.length === 0 ? (
              <View style={styles.emptyBox}>
                <Text style={styles.emptyText}>Nenhum cliente encontrado.</Text>
                <Pressable
                  onPress={onCreate}
                  style={({ pressed }) => [styles.createBtn, pressed && { opacity: 0.8 }]}
                  testID="pedido-form-criar-cliente"
                >
                  <Ionicons name="person-add-outline" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.createBtnText}>Cadastrar novo cliente</Text>
                </Pressable>
              </View>
            ) : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

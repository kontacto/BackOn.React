// Seção "Cliente": campo sempre editável (por nome, código, CPF/CNPJ ou
// telefone — mesmo comportamento do Campo(6) do Pedido Bar legado,
// `FrmManPedBar.frm`: o campo nunca vira um "chip" travado, digitar por
// cima sempre refaz a busca) + botão dedicado que abre o modal de busca
// completo (`ClientSearchModal`) + resumo compacto (telefone, endereço) ao
// lado do nome — dados completos (+ e-mail) ficam dentro do accordion
// "Dados Principais" da tela (não duplicados aqui num modal próprio).
//
// Resolução da busca (decidida pelo pai, disparada só pelo Enter —
// onSubmitTerm, digitar sozinho não busca nada):
// 1 resultado -> carrega o cliente direto na tela, sem modal.
// 0 ou 2+ resultados -> abre o modal de busca completo, que já cobre tanto
// a lista pra selecionar quanto o "Cadastrar novo cliente" quando não
// encontra nada.
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { styles } from "./styles";
import { ClienteResumo } from "./types";

type Props = {
  clienteResumo: ClienteResumo | null;
  loadingResumo: boolean;
  hasCliente: boolean;
  // Abre o modal de busca completo (`ClientSearchModal`) — botão dedicado,
  // sempre disponível, independente do que já foi digitado no campo.
  onOpenSearch: () => void;
  // Abre o modal "Dados Principais" da tela dona (telefone/endereço/e-mail
  // + Área de Atuação + Data/Validade + Observação) — o botão de resumo
  // ao lado do nome é o gatilho.
  onOpenDados?: () => void;
  // Campo de busca — sempre editável, mesmo com um cliente já selecionado
  // (o pai preenche com o nome do cliente atual; digitar por cima refaz a
  // busca e troca o cliente).
  quickTerm: string;
  onQuickTermChange: (v: string) => void;
  quickLoading: boolean;
  // Enter no campo dispara a busca/resolução (único gatilho — digitar
  // sozinho não busca nada).
  onSubmitTerm?: (term: string) => void;
  disabled?: boolean;
};

export default function ClienteSection({
  clienteResumo, loadingResumo, hasCliente, onOpenSearch, onOpenDados,
  quickTerm, onQuickTermChange, quickLoading,
  onSubmitTerm, disabled,
}: Props) {
  return (
    <>
      <Text style={styles.sectionTitle}>Cliente</Text>
      <View style={{ flexDirection: "row", gap: 8, alignItems: "stretch" }}>
        <View style={{ flex: 1 }}>
          <View style={styles.clienteBox}>
            <Ionicons name="search" size={18} color={colors.muted} />
            <TextInput
              value={quickTerm}
              onChangeText={onQuickTermChange}
              onSubmitEditing={() => onSubmitTerm?.(quickTerm)}
              returnKeyType="search"
              editable={!disabled}
              selectTextOnFocus
              placeholder="Nome, código, CPF/CNPJ ou telefone…"
              placeholderTextColor={colors.muted}
              style={[styles.searchInput, { fontSize: 14 }]}
              testID="pedido-form-cliente-quick-input"
              autoComplete="new-password"
              autoCorrect={false}
              textContentType="none"
              importantForAutofill="no"
            />
            {quickLoading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
            <Pressable
              onPress={onOpenSearch}
              disabled={disabled}
              hitSlop={8}
              testID="pedido-form-cliente-abrir-busca"
            >
              <Ionicons name="options-outline" size={18} color={colors.muted} />
            </Pressable>
          </View>
        </View>

        {hasCliente ? (
          <Pressable
            onPress={onOpenDados}
            disabled={!onOpenDados}
            style={({ pressed }) => [styles.resumoBox, styles.resumoBoxCompact, pressed && { opacity: 0.8 }]}
            testID="pedido-form-cliente-resumo-btn"
          >
            {loadingResumo ? (
              <ActivityIndicator size="small" color={colors.brandPrimary} />
            ) : clienteResumo ? (
              <>
                <View style={styles.resumoRow}>
                  <Ionicons name="call-outline" size={14} color={colors.brandPrimary} />
                  <Text style={styles.resumoText} numberOfLines={1}>{clienteResumo.telefone || "Sem telefone"}</Text>
                </View>
                <View style={styles.resumoRow}>
                  <Ionicons name="location-outline" size={14} color={colors.brandPrimary} />
                  <Text style={styles.resumoText} numberOfLines={1}>{clienteResumo.endereco || "Sem endereço"}</Text>
                </View>
              </>
            ) : (
              <Text style={styles.resumoText}>Indisponível</Text>
            )}
          </Pressable>
        ) : null}
      </View>
    </>
  );
}

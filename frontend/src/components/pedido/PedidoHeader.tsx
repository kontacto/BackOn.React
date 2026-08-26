// Barra de cabeçalho da tela de pedido (voltar + logo opcional + título +
// Anexos + Ajuda + gravar) — compartilhada por Pedido Bar (pedido-form.tsx)
// e Pedido Geral/Completo (pedido-geral.tsx, prop `logo`) desde 2026-07-20,
// pedido explícito do usuário ("tente usar as mesmas funções para não
// replicar o mesmo código entre telas") — antes o Geral tinha seu próprio
// header inline duplicando essa mesma barra.
import { useState } from "react";
import { ActivityIndicator, Platform, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { styles } from "./styles";

const isWeb = Platform.OS === "web";

type Props = {
  title: string;
  saving: boolean;
  onBack: () => void;
  onSave: () => void;
  canSave?: boolean;
  // Conteúdo extra ao lado do título (ex.: seletor de Vendedor) — ainda
  // dentro da barra, na cor de fundo da barra.
  titleExtra?: React.ReactNode;
  // Abre o Gestor de Documentos (AnexosPedidoModal) — regra `[GLOBAL]`
  // adicionada 2026-07-20, user-directed: "o botão anexos (gestor de
  // Documentos) ficará sempre no título da Janela" — antes vivia entre os
  // pills de ação do `ItemList` (Fechar/Faturar/Cancelar/...), que dependem
  // da situação do registro; Anexos é uma ação de tela, não de estado do
  // pedido, então mora no cabeçalho junto com Ajuda/Gravar. Ícone só
  // aparece se informado (ex.: sem cliente selecionado ainda).
  onAnexos?: () => void;
  // Abre o preenchimento de Formulário Dinâmico (Motor de Layout,
  // `LayoutPreenchimentoModal`) desta O.S./Pedido — mesma lógica de
  // "ação de tela, não de estado do registro" do Anexos acima, por isso
  // mora aqui também. Ícone só aparece se informado. Adicionado
  // 2026-08-12, user-directed (ligação O.S. Completa ↔ Formulário
  // Dinâmico, entidade=O.S.).
  onFormularios?: () => void;
  // Abre a configuração de Impressão Silenciosa desta estação (Checkout —
  // ver ConfiguracaoImpressaoModal.tsx). Ação de tela (não depende do
  // estado do registro), por isso mora aqui junto com Anexos/Ajuda. Ícone
  // só aparece se informado.
  onPrintConfig?: () => void;
  // Abre o modal único de Ajuda da tela (reúne a explicação de todos os
  // botões/campos num só lugar, em vez de tooltip por botão — pedido
  // explícito do usuário, 2026-07-20). Ícone só aparece se informado.
  onHelp?: () => void;
  // "Imprimir O.S. Completa (A4)"/"Enviar por Email" — documento A4
  // completo em PDF (motor `os_completa_pdf_service.py`), distinto do
  // recibo térmico "não-fiscal" já existente na barra de pills do
  // `ItemList` (`onImprimir`). Ação de tela (não depende de `situacao`),
  // por isso mora aqui junto de Anexos/Ajuda. Ícones só aparecem se
  // informados — hoje só usado por `os-geral.tsx` (2026-08-26), nomes
  // genéricos pra o Pedido poder adotar depois sem precisar renomear.
  onImprimirCompleto?: () => void;
  imprimindoCompleto?: boolean;
  onEnviarEmail?: () => void;
  enviandoEmail?: boolean;
  // Chip "Projeto #N" — Gestor de Projetos Fase 4 (recurso extra, sem
  // equivalente no legado): mostra que este documento já está vinculado a
  // um Projeto, sem precisar abrir o Gestor de Projetos pra descobrir.
  // Só aparece se informado (documento sem vínculo não mostra nada).
  vinculoProjeto?: { codigo: number; onPress: () => void };
};

// Ícone de ação do cabeçalho com tooltip no hover (web) — extraído aqui
// pra não duplicar o mesmo onHoverIn/onHoverOut cru pra cada ícone novo
// (Anexos, Ajuda, e o que vier depois seguindo a mesma regra `[GLOBAL]`).
function HeaderIconButton({
  icon, label, onPress, testID, busy,
}: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; onPress: () => void; testID?: string; busy?: boolean }) {
  const [hover, setHover] = useState(false);
  return (
    <View style={{ position: "relative" }}>
      <Pressable
        onPress={onPress}
        disabled={busy}
        onHoverIn={isWeb ? () => setHover(true) : undefined}
        onHoverOut={isWeb ? () => setHover(false) : undefined}
        style={({ pressed }) => [styles.iconBtn, (pressed || busy) && { opacity: 0.7 }]}
        hitSlop={12}
        testID={testID}
      >
        {busy ? (
          <ActivityIndicator size="small" color={colors.onBrandPrimary} />
        ) : (
          <Ionicons name={icon} size={22} color={colors.onBrandPrimary} />
        )}
      </Pressable>
      {hover ? (
        <View
          style={{
            position: "absolute", top: "100%", right: 0, marginTop: 4,
            backgroundColor: "#1a1a1a", borderRadius: 6,
            paddingHorizontal: 8, paddingVertical: 4, zIndex: 10,
          }}
          pointerEvents="none"
        >
          <Text style={{ color: "#fff", fontSize: 11, fontWeight: "600" }}>{label}</Text>
        </View>
      ) : null}
    </View>
  );
}

export default function PedidoHeader({
  title, saving, onBack, onSave, canSave = true, titleExtra, onAnexos, onFormularios, onPrintConfig, onHelp,
  onImprimirCompleto, imprimindoCompleto, onEnviarEmail, enviandoEmail, vinculoProjeto,
}: Props) {
  return (
    <View style={styles.header}>
      <Pressable onPress={onBack} style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]} hitSlop={12}>
        <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
      </Pressable>
      <Text style={styles.headerTitle} numberOfLines={1}>{title}</Text>
      {titleExtra}
      {vinculoProjeto ? (
        <Pressable
          onPress={vinculoProjeto.onPress}
          style={{
            flexDirection: "row", alignItems: "center", gap: 4,
            backgroundColor: "rgba(255,255,255,0.18)", borderRadius: 999,
            paddingHorizontal: 8, paddingVertical: 4, marginRight: 4,
          }}
          testID="pedido-header-vinculo-projeto"
        >
          <Ionicons name="briefcase-outline" size={13} color={colors.onBrandPrimary} />
          <Text style={{ color: colors.onBrandPrimary, fontSize: 11, fontWeight: "700" }}>Projeto #{vinculoProjeto.codigo}</Text>
        </Pressable>
      ) : null}
      {onAnexos ? (
        <HeaderIconButton icon="attach-outline" label="Anexos" onPress={onAnexos} testID="pedido-form-anexos-btn" />
      ) : null}
      {onFormularios ? (
        <HeaderIconButton icon="document-text-outline" label="Formulários" onPress={onFormularios} testID="pedido-form-formularios-btn" />
      ) : null}
      {onPrintConfig ? (
        <HeaderIconButton icon="settings-outline" label="Configurar Impressão" onPress={onPrintConfig} testID="pedido-form-print-config-btn" />
      ) : null}
      {onImprimirCompleto ? (
        <HeaderIconButton
          icon="print-outline" label="Imprimir O.S. Completa (A4)" onPress={onImprimirCompleto}
          busy={imprimindoCompleto} testID="pedido-form-imprimir-completo-btn"
        />
      ) : null}
      {onEnviarEmail ? (
        <HeaderIconButton
          icon="mail-outline" label="Enviar por Email" onPress={onEnviarEmail}
          busy={enviandoEmail} testID="pedido-form-enviar-email-btn"
        />
      ) : null}
      {onHelp ? (
        <HeaderIconButton icon="information-circle-outline" label="Ajuda" onPress={onHelp} testID="pedido-form-ajuda-btn" />
      ) : null}
      {canSave ? (
        <Pressable
          onPress={onSave}
          disabled={saving}
          style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]}
          hitSlop={8}
          testID="pedido-form-save"
        >
          {saving ? (
            <ActivityIndicator color={colors.onBrandPrimary} size="small" />
          ) : (
            <>
              <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.saveLabel}>Gravar</Text>
            </>
          )}
        </Pressable>
      ) : (
        <View style={{ width: 40 }} />
      )}
    </View>
  );
}

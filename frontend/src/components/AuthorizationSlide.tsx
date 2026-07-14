// Slide (bottom-sheet) de autorização — usado sempre que uma ação exigir aval
// de um gerente/supervisor (funcionarios.cod_funcao 1 ou 2) ou do master
// (KONTACTO), mesmo quando o usuário logado já tem a permissão da tela
// liberada. Valida usuário/senha reaproveitando o próprio POST /api/login
// (mesma checagem de credencial usada no login normal), sem abrir uma sessão
// nova — só confirma que quem digitou tem alçada para autorizar.
import { useEffect, useState } from "react";
import {
  ActivityIndicator, Modal, Pressable, StyleSheet, Text, TextInput, View,
} from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { apiSend } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

type Props = {
  visible: boolean;
  conn: Connection | null;
  title?: string;
  message?: string;
  onClose: () => void;
  onAuthorized: (info: { usuario: string }) => void;
};

export default function AuthorizationSlide({
  visible, conn, title, message, onClose, onAuthorized,
}: Props) {
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (visible) { setUsuario(""); setSenha(""); setErro(null); }
  }, [visible]);

  const confirmar = async () => {
    if (!conn) return;
    if (!usuario.trim() || !senha) { setErro("Informe usuário e senha."); return; }
    setLoading(true);
    setErro(null);
    try {
      const j = await apiSend(conn, "/api/login", "POST", {
        empresa: conn.empresa, usuario: usuario.trim(), senha, timeout: 8,
      });
      if (!j?.success) { setErro(j?.message || "Usuário ou senha inválidos."); return; }
      const isMasterAuth =
        j?.usuario?.master === true || String(j?.usuario?.usuario ?? "").toUpperCase() === "KONTACTO";
      const codFuncaoRaw = j?.funcionario?.cod_funcao;
      const codFuncao = codFuncaoRaw != null ? parseInt(String(codFuncaoRaw), 10) : null;
      const autorizado = isMasterAuth || codFuncao === 1 || codFuncao === 2;
      if (!autorizado) { setErro("Este usuário não tem alçada para autorizar esta ação."); return; }
      onAuthorized({ usuario: usuario.trim() });
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao validar credenciais.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose} testID="authorization-slide">
      <Pressable style={styles.bg} onPress={onClose}>
        <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Ionicons name="key-outline" size={18} color={colors.brandPrimary} />
            <Text style={styles.title}>{title || "Autorização necessária"}</Text>
          </View>
          <Text style={styles.message}>
            {message || "Esta ação exige autorização de um gerente, supervisor ou administrador."}
          </Text>

          <Text style={styles.label}>Usuário</Text>
          <TextInput
            value={usuario}
            onChangeText={setUsuario}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
            placeholder="Usuário autorizante"
            placeholderTextColor={colors.muted}
            testID="authorization-slide-usuario"
          />
          <Text style={styles.label}>Senha</Text>
          <TextInput
            value={senha}
            onChangeText={setSenha}
            secureTextEntry
            style={styles.input}
            placeholder="Senha"
            placeholderTextColor={colors.muted}
            testID="authorization-slide-senha"
          />

          {erro ? <Text style={styles.erro} testID="authorization-slide-erro">{erro}</Text> : null}

          <View style={styles.btnRow}>
            <Pressable onPress={onClose} disabled={loading} style={styles.btnSecondary} testID="authorization-slide-cancelar">
              <Text style={styles.btnSecondaryText}>Cancelar</Text>
            </Pressable>
            <Pressable onPress={confirmar} disabled={loading} style={styles.btnPrimary} testID="authorization-slide-confirmar">
              {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.btnPrimaryText}>Autorizar</Text>}
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  card: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
  },
  header: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 4 },
  title: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  message: { fontSize: 13, color: colors.muted, marginBottom: spacing.md, lineHeight: 18 },
  label: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
    minHeight: 40, marginBottom: spacing.sm,
  },
  erro: { color: colors.error, fontSize: 12, marginBottom: spacing.sm },
  btnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  btnSecondary: {
    flex: 1, paddingVertical: 12, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, alignItems: "center",
  },
  btnSecondaryText: { color: colors.onSurface, fontWeight: "500", fontSize: 14 },
  btnPrimary: {
    flex: 1, paddingVertical: 12, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center",
  },
  btnPrimaryText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 14 },
});

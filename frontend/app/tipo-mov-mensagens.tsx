import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Mensagem = { codigo: number; descricao: string };

// Cadastro/Tabelas Auxiliares > Tipo Mov x Mensagem (tabela `tipo_msg`,
// relacionamento N:N entre `tipo_mov` e `Mensagens`). Legado: FrmTipMsg
// ("Relacionamento Tipo Movimetação X Mensagens") — duas listas
// (Possíveis/Cadastrados) com transferência via botões >, >>, <, <<.
export default function TipoMovMensagensScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Tipo Mov x Mensagem está disponível apenas no web."
        testID="tipo-mov-mensagens-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [movOptions, setMovOptions] = useState<SelectOption[]>([]);
  const [mov, setMov] = useState<string | null>(null);

  const [disponiveis, setDisponiveis] = useState<Mensagem[]>([]);
  const [vinculados, setVinculados] = useState<Mensagem[]>([]);
  const [selDisponiveis, setSelDisponiveis] = useState<Set<number>>(new Set());
  const [selVinculados, setSelVinculados] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);

  const canSave = can("TIPO_MOV_MSG.GRAVAR") || isMaster;

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      try {
        const base = cc.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`;
        const r = await fetch(`${base}/api/tabelas/tipo-mov?${qs}`);
        const j = await r.json();
        if (j?.success) {
          setMovOptions((j.items || []).map((i: any) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })));
        }
      } catch {
        // silencioso
      }
    })();
  }, [router]);

  const loadRel = useCallback(async (c: Conn, m: string) => {
    setLoading(true);
    setSelDisponiveis(new Set());
    setSelVinculados(new Set());
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&mov=${encodeURIComponent(m)}`;
      const r = await fetch(`${base}/api/tabelas/tipo-msg?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setDisponiveis(j.disponiveis || []);
        setVinculados(j.vinculados || []);
      } else {
        setDisponiveis([]); setVinculados([]);
      }
    } catch { setDisponiveis([]); setVinculados([]); } finally { setLoading(false); }
  }, []);

  const onSelectMov = (v: string | number | null) => {
    const m = v ? String(v) : null;
    setMov(m);
    if (conn && m) loadRel(conn, m);
    else { setDisponiveis([]); setVinculados([]); }
  };

  const toggle = (set: Set<number>, setFn: (s: Set<number>) => void, codigo: number) => {
    const next = new Set(set);
    if (next.has(codigo)) next.delete(codigo); else next.add(codigo);
    setFn(next);
  };

  const vincular = async () => {
    if (!conn || !mov || selDisponiveis.size === 0) return;
    setWorking(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/tipo-msg/vincular`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, mov, mensagens: Array.from(selDisponiveis) }),
      });
      const j = await r.json();
      if (j?.success) loadRel(conn, mov); else fb.showError(j?.message || "Falha ao vincular.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setWorking(false); }
  };

  const desvincular = async () => {
    if (!conn || !mov || selVinculados.size === 0) return;
    setWorking(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/tipo-msg/desvincular`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, mov, mensagens: Array.from(selVinculados) }),
      });
      const j = await r.json();
      if (j?.success) loadRel(conn, mov); else fb.showError(j?.message || "Falha ao desvincular.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setWorking(false); }
  };

  const vincularTodos = async () => {
    if (!conn || !mov) return;
    setWorking(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/tipo-msg/vincular-todos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, mov }),
      });
      const j = await r.json();
      if (j?.success) loadRel(conn, mov); else fb.showError(j?.message || "Falha ao vincular.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setWorking(false); }
  };

  const desvincularTodos = async () => {
    if (!conn || !mov) return;
    setWorking(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/tipo-msg/desvincular-todos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, mov }),
      });
      const j = await r.json();
      if (j?.success) loadRel(conn, mov); else fb.showError(j?.message || "Falha ao desvincular.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setWorking(false); }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="tipo-mov-mensagens-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Tipo Mov x Mensagem</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.filterCard}>
            <Text style={styles.label}>Tipo Movimentação</Text>
            <SelectField
              value={mov}
              onChange={onSelectMov}
              options={movOptions}
              placeholder="Selecione…"
              testID="tipo-mov-mensagens-mov"
              modalTitle="Tipo Movimentação"
              compactWeb
            />
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}

          {!loading && mov ? (
            <View style={styles.colunas}>
              <View style={styles.coluna}>
                <Text style={styles.colunaTitulo}>Possíveis</Text>
                <View style={styles.lista}>
                  {disponiveis.length === 0 ? <Text style={styles.empty}>Nenhuma.</Text> : null}
                  {disponiveis.map((m) => (
                    <Pressable
                      key={m.codigo}
                      onPress={() => canSave && toggle(selDisponiveis, setSelDisponiveis, m.codigo)}
                      style={[styles.item, selDisponiveis.has(m.codigo) && styles.itemSel]}
                      testID={`tipo-mov-msg-disp-${m.codigo}`}
                    >
                      <Text style={[styles.itemText, selDisponiveis.has(m.codigo) && styles.itemTextSel]} numberOfLines={1}>{m.codigo} - {m.descricao}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>

              {canSave ? (
                <View style={styles.botoes}>
                  <Pressable onPress={vincular} disabled={working || selDisponiveis.size === 0} style={[styles.btn, (working || selDisponiveis.size === 0) && styles.btnDisabled]} testID="tipo-mov-msg-vai">
                    <Text style={styles.btnText}>{">"}</Text>
                  </Pressable>
                  <Pressable onPress={vincularTodos} disabled={working || disponiveis.length === 0} style={[styles.btn, (working || disponiveis.length === 0) && styles.btnDisabled]} testID="tipo-mov-msg-tudao">
                    <Text style={styles.btnText}>{">>"}</Text>
                  </Pressable>
                  <Pressable onPress={desvincular} disabled={working || selVinculados.size === 0} style={[styles.btn, (working || selVinculados.size === 0) && styles.btnDisabled]} testID="tipo-mov-msg-volta">
                    <Text style={styles.btnText}>{"<"}</Text>
                  </Pressable>
                  <Pressable onPress={desvincularTodos} disabled={working || vinculados.length === 0} style={[styles.btn, (working || vinculados.length === 0) && styles.btnDisabled]} testID="tipo-mov-msg-nada">
                    <Text style={styles.btnText}>{"<<"}</Text>
                  </Pressable>
                </View>
              ) : null}

              <View style={styles.coluna}>
                <Text style={styles.colunaTitulo}>Cadastrados</Text>
                <View style={styles.lista}>
                  {vinculados.length === 0 ? <Text style={styles.empty}>Nenhuma.</Text> : null}
                  {vinculados.map((m) => (
                    <Pressable
                      key={m.codigo}
                      onPress={() => canSave && toggle(selVinculados, setSelVinculados, m.codigo)}
                      style={[styles.item, selVinculados.has(m.codigo) && styles.itemSel]}
                      testID={`tipo-mov-msg-vinc-${m.codigo}`}
                    >
                      <Text style={[styles.itemText, selVinculados.has(m.codigo) && styles.itemTextSel]} numberOfLines={1}>{m.codigo} - {m.descricao}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            </View>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filterCard: { ...WEB_FILTER_CARD, gap: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  colunas: { flexDirection: "row", gap: spacing.md, marginTop: spacing.lg, alignItems: "center" },
  coluna: { flex: 1, gap: spacing.xs },
  colunaTitulo: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  lista: {
    height: 360, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, padding: spacing.xs,
  },
  item: { paddingVertical: 8, paddingHorizontal: spacing.sm, borderRadius: radius.sm },
  itemSel: { backgroundColor: colors.brandPrimary },
  itemText: { fontSize: 12, color: colors.onSurface },
  itemTextSel: { color: "#fff", fontWeight: "600" },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24, fontSize: 12 },
  botoes: { gap: spacing.sm, alignItems: "center" },
  btn: { width: 48, height: 40, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  btnDisabled: { opacity: 0.4 },
  btnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});

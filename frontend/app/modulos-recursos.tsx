import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
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
type Grupo = {
  chave: string; titulo: string; hint?: string; campos: string[]; exclusivo?: boolean;
  // Subconjuntos mutuamente exclusivos DENTRO do mesmo grupo visual —
  // diferente de `exclusivo` (que trata TODO `campos` como uma única
  // exclusividade). Ver grupo "Pré Venda" abaixo: Pedido e O.S. são dois
  // subgrupos exclusivos independentes, mas convivem no mesmo cabeçalho.
  subgruposExclusivos?: string[][];
};

// "Bar", "Cilindro", "Pedido de Venda", "Metro Quadrado" e "Clínica" são 5
// versões/segmentos diferentes da mesma tela de Pedido de Venda — mutuamente
// exclusivos, nunca mais de um ligado ao mesmo tempo. [GLOBAL], 2026-07-15,
// user-directed (Metro Quadrado e Clínica adicionados 2026-07-27 — ver
// PENDENCIAS.md > "Transações" > "Pedido Geral — Metro Quadrado / Clínica"
// pro rastreio de campo-a-campo do `frmmanpedfor.frm`, ainda não
// implementado, só o registro do módulo).
const SEGMENTOS_PEDIDO_EXCLUSIVOS = ["Bar", "Cilindro", "Pedido_venda", "metro_quadrado", "CLINICA"];

// Oficina/Assistência/TSO são 3 variações diferentes da mesma Ordem de
// Serviço — mutuamente exclusivas entre si, mas NÃO exclusivas com o
// grupo "Pré Venda" (uma empresa pode ter os dois grupos ligados ao
// mesmo tempo). Grupo próprio "Ordem de Serviço" desde 2026-08-24
// (antes era um subgrupo dentro de "Pré Venda"). "TSO" adicionado
// 2026-08-20, user-directed ("TSO é uma Ordem de Serviço para Ótica") —
// mesmo espelho de `SEGMENTOS_OS_EXCLUSIVOS` em
// `controle_config_service.py` (backend).
const SEGMENTOS_OS_EXCLUSIVOS = ["Oficina", "Assistencia", "TSO"];

// Grupos nomeados exibidos no topo da lista (nesta ordem), cada um quebrando
// a ordem alfabética igual ao grupo "Pré Venda" já existente. Generalizado
// 2026-08-10 (user-directed — grupo "Automação Comercial" novo) a partir do
// único grupo hardcoded que existia antes (só "Pedidos") — campos fora de
// todo grupo continuam na lista alfabética normal ("outrosCampos" abaixo).
const GRUPOS: Grupo[] = [
  // Grupo "Pré Venda" (renomeado de "Pedidos", 2026-08-20, user-directed
  // — "TEM QUE FICAR NO GRUPO pré venda junto com Pedidos e OS"). Reunia
  // Pedido de Venda E Ordem de Serviço num único cabeçalho até
  // 2026-08-24, quando o usuário pediu pra separar Ordem de Serviço num
  // grupo próprio (ver "Ordem de Serviço" logo abaixo) — agora só cobre
  // as variações de Pedido de Venda, todas mutuamente exclusivas entre
  // si (`exclusivo: true`).
  {
    chave: "pre_venda",
    titulo: "Pré Venda",
    hint: "Bar, Cilindro, Pedido de Venda, Metro Quadrado e Clínica são 5 versões diferentes da mesma tela de Pedido de Venda — só uma pode ficar ativa por vez.",
    campos: SEGMENTOS_PEDIDO_EXCLUSIVOS,
    exclusivo: true,
  },
  // Grupo "Ordem de Serviço" (separado do grupo "Pré Venda" acima,
  // 2026-08-24, user-directed) — Oficina/Assistência/TSO são 3 variações
  // diferentes da mesma tela de Ordem de Serviço, mutuamente exclusivas
  // entre si (`exclusivo: true`) mas independentes do grupo "Pré Venda"
  // (uma empresa pode ter os dois grupos ligados ao mesmo tempo).
  {
    chave: "ordem_servico",
    titulo: "Ordem de Serviço",
    hint: "Oficina, Assistência e TSO (Ótica) são 3 versões diferentes da mesma tela de Ordem de Serviço — só uma pode ficar ativa por vez.",
    campos: SEGMENTOS_OS_EXCLUSIVOS,
    exclusivo: true,
  },
  {
    chave: "automacao_comercial",
    titulo: "Automação Comercial",
    campos: ["balanca_toledo", "balanca_pre_pesagem"],
  },
  // Grupo "Fiscal" (2026-08-20, user-directed). SPED/Emite MDF-e/SEFIN
  // Nacional + "Alterdata" (integração contábil, incluída a pedido
  // explícito do usuário) + os 3 campos fiscais reais do legado
  // ("Módulos do Cliente" > NFCE/NFe via Webservice/Emite NFSe via PC-RJ
  // — tabela `controle_aux`, expostos aqui pela 1ª vez nesta migração,
  // achado 2026-08-20 depois de uma tentativa anterior errada ter criado
  // colunas novas por engano; ver CLAUDE.md). "DMC" NÃO entra aqui — não é
  // campo fiscal, é "Exportação do DMC Combustíveis" (Posto), confirmado
  // extinto pelo usuário. "TSO" também NÃO entra — confirmado pelo
  // usuário como uma Ordem de Serviço pro segmento Ótica, sem relação
  // com fiscal; fica no grupo "Ordem de Serviço" acima, junto de
  // Oficina/Assistência.
  {
    chave: "fiscal",
    titulo: "Fiscal",
    campos: ["sped", "emite_mdfe", "sefin_nacional", "Alterdata", "emite_nfce", "nfe_ws", "emite_nfse"],
  },
];

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
      // Subgrupo exclusivo (mais granular que `exclusivo` — permite 2+
      // conjuntos mutuamente exclusivos DENTRO do mesmo grupo visual,
      // cada um independente dos outros) checado antes do grupo inteiro.
      // Nenhum grupo usa isso hoje (Pré Venda/Ordem de Serviço viraram
      // grupos próprios, cada um só com `exclusivo: true`, 2026-08-24) —
      // mecanismo mantido pronto pro próximo grupo que precisar dele.
      for (const g of GRUPOS) {
        const sub = g.subgruposExclusivos?.find((s) => s.includes(campo));
        if (novo && sub) {
          const next = { ...v };
          sub.forEach((c) => { next[c] = c === campo; });
          return next;
        }
      }
      const grupoExclusivo = GRUPOS.find((g) => g.exclusivo && g.campos.includes(campo));
      if (novo && grupoExclusivo) {
        // Ligar um campo de um grupo exclusivo desliga os outros do mesmo
        // grupo automaticamente — mesma regra de sempre, generalizada pra
        // qualquer grupo marcado `exclusivo`.
        const next = { ...v };
        grupoExclusivo.campos.forEach((c) => { next[c] = c === campo; });
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

  const camposEmGrupo = new Set(GRUPOS.flatMap((g) => g.campos));
  const gruposComCampos = GRUPOS.map((g) => ({
    grupo: g,
    itens: g.campos.map((c) => campos.find((x) => x.campo === c)).filter((c): c is Campo => !!c),
  })).filter((g) => g.itens.length > 0);
  const outrosCampos = campos.filter((c) => !camposEmGrupo.has(c.campo));

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
            gruposComCampos.length > 0 ? (
              <View>
                {gruposComCampos.map(({ grupo, itens }) => (
                  <View key={grupo.chave} testID={`mod-grupo-${grupo.chave}`}>
                    <Text style={styles.groupTitle}>{grupo.titulo}</Text>
                    {grupo.hint ? <Text style={styles.groupHint}>{grupo.hint}</Text> : null}
                    {itens.map((item) => renderRow(item))}
                    <View style={styles.groupDivider} />
                  </View>
                ))}
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

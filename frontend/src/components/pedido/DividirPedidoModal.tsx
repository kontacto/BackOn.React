// Dividir Pedido — funcionalidade NOVA, sem precedente no legado (pesquisado
// em toda a árvore VB6, nenhum "Dividir/Separar Conta" existe — ver
// PENDENCIAS.md > "Pedido Bar" > "Dividir Pedido"). Move uma quantidade (que
// pode ser fracionária — mesma mecânica pra dividir o VALOR de 1 unidade
// indivisível entre várias pessoas, ex. 1 pizza / 4 = 0,25 cada) de cada item
// pro um pedido NOVO, sob o mesmo cliente (Mesa/Comanda). O que não for
// movido continua no pedido atual.
//
// UI deliberadamente simples ("tem que ser prático", pedido do usuário
// 2026-07-17): um "arrancar um pedaço pro pedido novo" por vez, repetível —
// em vez de uma grade N-colunas (1 grupo por chamada ao back, que já aceita
// vários grupos numa chamada só se um dia precisar). Pra dividir entre 4
// pessoas: usar esta ação 3 vezes (cada uma tira a parte de 1 pessoa), o que
// sobra no pedido original é a 4ª parte.
import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { AppModal } from "@/src/components/AppModal";
import { Ionicons } from "@/src/components/Ionicons";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { usePermissions } from "@/src/permissions";
import { apiSend } from "@/src/utils/api";
import { formatBRL, fmtNum } from "@/src/utils/format";
import { colors, radius, spacing } from "@/src/theme/colors";
import { Connection } from "@/src/utils/storage/connections";
import { ItemRow } from "./types";

const TAXA_SERVICO_CODIGO = "S002";

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  pedido: number;
  itens: ItemRow[];
  basePath?: string; // "/api/pedidos" (Pedido Bar) — Dividir é exclusivo do Bar por ora.
  onDivided: (novosPedidos: number[]) => void;
};

// Uma linha por produto do pedido — o mesmo produto pode ter sido incluído
// várias vezes (linhas separadas em pedido_venda_prod), mas pra "dividir"
// o usuário pensa no TOTAL daquele produto no pedido, não em cada inclusão
// isolada (pedido explícito do usuário, 2026-07-17, "totalizar cada item
// antes de dividir" — mesmo raciocínio de "Pedido Totalizado",
// `usePedidoItens.pedidoTotalizadoGrupos`, só que aqui mantendo acesso às
// linhas originais pra poder distribuir a quantidade movida entre elas).
type GrupoItem = { produto: string; descricao: string; unidade: string; qtdTotal: number; valorUnitMedio: number; linhas: ItemRow[] };

function agruparPorProduto(itens: ItemRow[]): GrupoItem[] {
  const porProduto = new Map<string, GrupoItem>();
  for (const item of itens) {
    const atual = porProduto.get(item.produto);
    if (atual) {
      atual.qtdTotal += item.qtd;
      atual.linhas.push(item);
    } else {
      porProduto.set(item.produto, {
        produto: item.produto, descricao: item.descricao, unidade: item.unidade,
        qtdTotal: item.qtd, valorUnitMedio: item.valor_unitario, linhas: [item],
      });
    }
  }
  // Preço médio ponderado — na prática quase sempre todas as linhas do
  // mesmo produto têm o mesmo valor_unitario; só diverge se o preço mudou
  // entre duas inclusões do mesmo item.
  for (const g of porProduto.values()) {
    const valorTotal = g.linhas.reduce((s, l) => s + l.qtd * l.valor_unitario, 0);
    g.valorUnitMedio = g.qtdTotal > 0 ? valorTotal / g.qtdTotal : 0;
  }
  return Array.from(porProduto.values());
}

// Distribui a quantidade pedida pelas linhas originais daquele produto, na
// ordem em que existem — a primeira linha absorve o quanto puder, o
// restante vai pra próxima, e assim por diante (pode até dividir 1 linha só
// em duas partes: uma fica, outra move).
function distribuirEntreLinhas(linhas: ItemRow[], qtdDesejada: number): { codauto: number; qtd: number }[] {
  const out: { codauto: number; qtd: number }[] = [];
  let restante = qtdDesejada;
  for (const linha of linhas) {
    if (restante <= 0.0001) break;
    const pega = Math.min(linha.qtd, restante);
    if (pega > 0.0001) {
      out.push({ codauto: linha.codauto, qtd: pega });
      restante -= pega;
    }
  }
  return out;
}

export default function DividirPedidoModal({ visible, onClose, conn, pedido, itens, basePath = "/api/pedidos", onDivided }: Props) {
  const fb = useFeedback();
  const auditCtx = useAuditContext();
  const { isMaster } = usePermissions();
  const [qtds, setQtds] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const itensDivisiveis = useMemo(() => itens.filter((i) => i.produto !== TAXA_SERVICO_CODIGO), [itens]);
  const grupos = useMemo(() => agruparPorProduto(itensDivisiveis), [itensDivisiveis]);

  const parseQtd = (s: string): number => {
    const n = parseFloat((s || "").replace(",", "."));
    return isNaN(n) ? 0 : n;
  };

  const setQtd = (produto: string, v: string) => setQtds((q) => ({ ...q, [produto]: v }));
  const metade = (g: GrupoItem) => setQtd(g.produto, String(Math.round((g.qtdTotal / 2) * 1000) / 1000).replace(".", ","));

  const totalMovido = useMemo(
    () => grupos.reduce((s, g) => s + parseQtd(qtds[g.produto] || "") * g.valorUnitMedio, 0),
    [grupos, qtds]
  );
  const temAlgoParaMover = totalMovido > 0;

  const handleClose = () => {
    if (!saving) { setQtds({}); onClose(); }
  };

  const confirmar = async () => {
    if (!conn) return;
    const itensGrupo: { codauto: number; qtd: number }[] = [];
    for (const g of grupos) {
      const qtd = parseQtd(qtds[g.produto] || "");
      if (qtd <= 0) continue;
      if (qtd > g.qtdTotal + 0.0001) {
        fb.showError(`Quantidade de "${g.descricao}" não pode passar de ${fmtNum(g.qtdTotal)}.`);
        return;
      }
      itensGrupo.push(...distribuirEntreLinhas(g.linhas, qtd));
    }
    if (itensGrupo.length === 0) {
      fb.showWarning("Informe a quantidade de pelo menos um item para mover.");
      return;
    }
    setSaving(true);
    try {
      const j = await apiSend(conn, `${basePath}/${pedido}/dividir`, "POST", {
        grupos: [{ itens: itensGrupo }],
        master: isMaster,
        usuario_alteracao: auditCtx.usuario_alteracao,
        classe: auditCtx.classe,
        plataforma: auditCtx.plataforma,
      });
      if (j?.success) {
        fb.showSuccess(j.message || "Pedido dividido.");
        setQtds({});
        onDivided(j.novos_pedidos || []);
        onClose();
      } else {
        fb.showError(j?.message || "Falha ao dividir o pedido.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={handleClose}>
      <Pressable style={styles.bg} onPress={handleClose}>
        <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Distribuir Pedido nº {pedido}</Text>
            <Pressable onPress={handleClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <Text style={styles.hint}>
            Informe quanto de cada item vai para um pedido novo. O que sobrar continua neste pedido.
          </Text>

          <ScrollView style={{ maxHeight: 420 }}>
            {grupos.length === 0 ? (
              <Text style={styles.empty}>Nenhum item divisível neste pedido.</Text>
            ) : (
              grupos.map((g) => (
                <View key={g.produto} style={styles.row} testID={`dividir-item-${g.produto}`}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={styles.rowDesc} numberOfLines={1}>{g.descricao}</Text>
                    <Text style={styles.rowSub}>
                      Total: {fmtNum(g.qtdTotal)} {g.unidade} · {formatBRL(g.valorUnitMedio)}/un
                    </Text>
                  </View>
                  <Pressable onPress={() => metade(g)} style={styles.metadeBtn} testID={`dividir-item-metade-${g.produto}`}>
                    <Text style={styles.metadeBtnText}>½</Text>
                  </Pressable>
                  <TextInput
                    value={qtds[g.produto] || ""}
                    onChangeText={(v) => setQtd(g.produto, v)}
                    placeholder="0"
                    placeholderTextColor={colors.muted}
                    keyboardType="decimal-pad"
                    style={styles.qtdInput}
                    testID={`dividir-item-qtd-${g.produto}`}
                  />
                </View>
              ))
            )}
          </ScrollView>

          <View style={styles.footer}>
            <Text style={styles.footerLabel}>Valor movido para o pedido novo</Text>
            <Text style={styles.footerValue}>{formatBRL(totalMovido)}</Text>
          </View>

          <View style={styles.btns}>
            <Pressable onPress={handleClose} style={[styles.secondaryBtn, { flex: 1 }]} testID="dividir-pedido-cancelar">
              <Text style={styles.secondaryBtnText}>Fechar</Text>
            </Pressable>
            <Pressable
              onPress={confirmar}
              disabled={saving || !temAlgoParaMover}
              style={[styles.primaryBtn, { flex: 1 }, (saving || !temAlgoParaMover) && { opacity: 0.5 }]}
              testID="dividir-pedido-confirmar"
            >
              <Text style={styles.primaryBtnText}>{saving ? "Dividindo…" : "Criar Pedido Novo"}</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  bg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: "center", alignItems: "center", padding: spacing.xl,
  },
  card: {
    width: "100%", maxWidth: 560,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    padding: spacing.lg,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.xs },
  title: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
  hint: { fontSize: 12, color: colors.muted, marginBottom: spacing.md },
  empty: { fontSize: 13, color: colors.muted, textAlign: "center", paddingVertical: spacing.lg },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  rowDesc: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  metadeBtn: {
    width: 32, height: 32, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  metadeBtnText: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  qtdInput: {
    width: 72, height: 36, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, fontSize: 14, color: colors.onSurface, backgroundColor: colors.surfaceSecondary,
    textAlign: "center",
  },
  footer: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border,
  },
  footerLabel: { fontSize: 12, color: colors.muted },
  footerValue: { fontSize: 16, fontWeight: "700", color: colors.brandPrimary },
  btns: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  secondaryBtn: {
    alignItems: "center", justifyContent: "center", height: 40, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
  },
  secondaryBtnText: { color: colors.onSurface, fontWeight: "500", fontSize: 14 },
  primaryBtn: {
    alignItems: "center", justifyContent: "center", height: 40, borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 14 },
});

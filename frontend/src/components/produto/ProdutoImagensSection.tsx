import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { Ionicons } from "@/src/components/Ionicons";
import SelectField from "@/src/components/SelectField";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";
import { produtoImagemUrl } from "@/src/utils/produtoImagem";

// Fotos de Produto — sistema NOVO, isolado do Gestor de Documentos (que
// continua sendo usado pelo modal "Anexos" da mesma tela, pra documento
// do produto). Ver backend/services/produto_imagem_service.py e o
// documento de arquitetura aprovado (PENDENCIAS.md > "Fotos de Produto").
//
// A foto marcada como "Principal" é a que aparece na busca de produto/PDV/
// catálogo — mesmo raciocínio do texto de ajuda abaixo.

type Props = {
  api: string;
  servidor: string;
  banco: string;
  codigoInt: string;
};

type ImagemItem = {
  codigo: number;
  cor: number | null;
  principal: boolean;
};

export default function ProdutoImagensSection({ api, servidor, banco, codigoInt }: Props) {
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const base = api.replace(/\/+$/, "");
  const qsConn = `servidor=${encodeURIComponent(servidor)}&banco=${encodeURIComponent(banco)}`;
  const conn = { api, servidor, banco };

  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<ImagemItem[]>([]);
  const [cores, setCores] = useState<{ value: number; label: string }[]>([]);
  const [corSelecionada, setCorSelecionada] = useState<number | null>(null);
  const [definirPrincipal, setDefinirPrincipal] = useState(false);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/produto-imagem?${qsConn}&codigo_int=${encodeURIComponent(codigoInt)}`);
      const j = await r.json();
      setItems(j?.success ? j.items : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [base, qsConn, codigoInt]);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/grade/cores?${qsConn}`);
        const j = await r.json();
        if (j?.success) {
          setCores(j.items.map((c: { codigo: number; descricao: string }) => ({ value: c.codigo, label: c.descricao })));
        }
      } catch {
        setCores([]);
      }
    })();
    reload();
  }, [base, qsConn, codigoInt, reload]);

  const upload = async () => {
    if (!arquivo) { fb.showWarning("Selecione uma foto."); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("servidor", servidor);
      fd.append("banco", banco);
      fd.append("codigo_int", codigoInt);
      if (corSelecionada != null) fd.append("cor", String(corSelecionada));
      fd.append("principal", definirPrincipal ? "true" : "false");
      if (auditCtx.usuario_alteracao != null) fd.append("usuario_alteracao", String(auditCtx.usuario_alteracao));
      if (auditCtx.classe != null) fd.append("classe", String(auditCtx.classe));
      fd.append("plataforma", auditCtx.plataforma);
      fd.append("arquivo", arquivo, arquivo.name);
      const r = await fetch(`${base}/api/produto-imagem`, { method: "POST", body: fd });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Foto enviada.");
        setArquivo(null);
        setCorSelecionada(null);
        setDefinirPrincipal(false);
        await reload();
      } else {
        fb.showError(j?.message || "Falha ao enviar a foto.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setUploading(false);
    }
  };

  const excluir = async (codigo: number) => {
    try {
      const r = await fetch(`${base}/api/produto-imagem/${codigo}/excluir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor, banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Foto removida."); await reload(); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const marcarPrincipal = async (codigo: number) => {
    try {
      const r = await fetch(`${base}/api/produto-imagem/${codigo}/principal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor, banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { await reload(); }
      else fb.showError(j?.message || "Falha ao definir foto principal.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <View testID="produto-imagens-section">
      <Text style={styles.hint}>
        A foto marcada com a estrela é a "Principal" — é ela que aparece na busca de produto, no PDV e no
        catálogo. As demais ficam guardadas como fotos extras do produto.
      </Text>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : items.length === 0 ? (
        <Text style={styles.empty}>Nenhuma foto cadastrada ainda.</Text>
      ) : (
        <View style={styles.grid}>
          {items.map((it) => (
            <View key={it.codigo} style={styles.cell} testID={`produto-imagem-${it.codigo}`}>
              {/* eslint-disable-next-line jsx-a11y/alt-text */}
              <img src={produtoImagemUrl(conn, it.codigo, "thumb")} style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: radius.sm }} />
              {it.principal ? (
                <View style={styles.badgePrincipal}>
                  <Ionicons name="star" size={12} color="#fff" />
                </View>
              ) : (
                <Pressable onPress={() => marcarPrincipal(it.codigo)} style={styles.actionStar} hitSlop={6} testID={`produto-imagem-${it.codigo}-principal`}>
                  <Ionicons name="star-outline" size={16} color={colors.onBrandPrimary} />
                </Pressable>
              )}
              <Pressable onPress={() => excluir(it.codigo)} style={styles.actionTrash} hitSlop={6} testID={`produto-imagem-${it.codigo}-excluir`}>
                <Ionicons name="trash-outline" size={16} color={colors.onBrandPrimary} />
              </Pressable>
            </View>
          ))}
        </View>
      )}

      <View style={styles.uploadCard}>
        <View style={styles.uploadRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Cor (opcional — vinculada à Grade)</Text>
            <SelectField
              value={corSelecionada}
              onChange={(v) => setCorSelecionada(v != null ? Number(v) : null)}
              options={cores.map((c) => ({ value: c.value, label: c.label }))}
              allowClear
              compactWeb
              testID="produto-imagem-cor"
            />
          </View>
          <Pressable onPress={() => setDefinirPrincipal((v) => !v)} style={styles.chkRow} testID="produto-imagem-definir-principal">
            <Ionicons name={definirPrincipal ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
            <Text style={styles.chkLabel}>Definir como principal</Text>
          </Pressable>
        </View>
        <View style={styles.uploadRow}>
          {Platform.OS === "web" ? (
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setArquivo((e.target as HTMLInputElement).files?.[0] || null)}
              style={{
                flex: 1, height: 36, boxSizing: "border-box", padding: "0 8px", fontSize: 13,
                border: `1px solid ${colors.border}`, borderRadius: radius.sm,
                backgroundColor: colors.surface, color: colors.onSurface,
              }}
            />
          ) : null}
          <Pressable onPress={upload} disabled={uploading} style={styles.uploadBtn} testID="produto-imagem-upload">
            {uploading ? (
              <ActivityIndicator color={colors.onBrandPrimary} size="small" />
            ) : (
              <>
                <Ionicons name="cloud-upload-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.uploadBtnText}>Enviar Foto</Text>
              </>
            )}
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  hint: { fontSize: 12, color: colors.muted, marginBottom: spacing.md },
  center: { paddingVertical: spacing.lg, alignItems: "center" },
  empty: { color: colors.muted, fontSize: 13, paddingVertical: spacing.md },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.md },
  cell: {
    width: 110, height: 110, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, overflow: "hidden", position: "relative",
  },
  badgePrincipal: {
    position: "absolute", top: 4, left: 4, backgroundColor: colors.brandPrimary,
    borderRadius: 10, width: 20, height: 20, alignItems: "center", justifyContent: "center",
  },
  actionStar: {
    position: "absolute", top: 4, left: 4, backgroundColor: "rgba(0,0,0,0.45)",
    borderRadius: 10, width: 20, height: 20, alignItems: "center", justifyContent: "center",
  },
  actionTrash: {
    position: "absolute", top: 4, right: 4, backgroundColor: "rgba(0,0,0,0.45)",
    borderRadius: 10, width: 20, height: 20, alignItems: "center", justifyContent: "center",
  },
  uploadCard: {
    padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  uploadRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, marginBottom: 4 },
  chkRow: { flexDirection: "row", alignItems: "center", gap: 6, height: 36 },
  chkLabel: { fontSize: 13, color: colors.onSurface },
  uploadBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, height: 36, borderRadius: radius.sm,
  },
  uploadBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
});

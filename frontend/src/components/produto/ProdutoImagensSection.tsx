import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { Ionicons } from "@/src/components/Ionicons";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import ImageLightboxModal from "@/src/components/ImageLightboxModal";
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

// Mesmos formatos aceitos por `_MIME_POR_FORMATO`/decodificação real via
// Pillow no backend (produto_imagem_service.py) — mudar um lado sem o
// outro deixa a mensagem/`accept` do input mentindo sobre o que de fato é
// aceito no upload.
const FORMATOS_ACEITOS_ACCEPT = "image/jpeg,image/png,image/webp,image/gif,image/bmp";

type Props = {
  api: string;
  servidor: string;
  banco: string;
  codigoInt: string;
  // Chamado toda vez que a lista é recarregada (upload/excluir/marcar
  // principal), com o `codigo` da foto principal atual (ou `null` — sem
  // foto principal) — pra quem embute este componente (o modal Fotografia
  // de produto-completo.tsx) já atualizar a miniatura da tela de produto
  // na hora, sem precisar fechar o modal primeiro.
  onPrincipalChanged?: (codigo: number | null) => void;
};

type ImagemItem = {
  codigo: number;
  cor: number | null;
  principal: boolean;
};

export default function ProdutoImagensSection({ api, servidor, banco, codigoInt, onPrincipalChanged }: Props) {
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
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/produto-imagem?${qsConn}&codigo_int=${encodeURIComponent(codigoInt)}`);
      const j = await r.json();
      const novosItems: ImagemItem[] = j?.success ? j.items : [];
      setItems(novosItems);
      onPrincipalChanged?.(novosItems.find((i) => i.principal)?.codigo ?? null);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [base, qsConn, codigoInt, onPrincipalChanged]);

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
              <img
                src={produtoImagemUrl(conn, it.codigo, "thumb")}
                onClick={() => setLightboxUrl(produtoImagemUrl(conn, it.codigo, "web"))}
                style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: radius.sm, cursor: "pointer" }}
              />
              {it.principal ? (
                <View style={styles.actionStarPos}>
                  <IconButtonWithTooltip
                    icon="star"
                    label="Foto principal"
                    onPress={() => {}}
                    size={12}
                    color="#fff"
                    tooltipAlign="left"
                    style={[styles.actionIconInner, { backgroundColor: colors.brandPrimary }]}
                    testID={`produto-imagem-${it.codigo}-principal-badge`}
                  />
                </View>
              ) : (
                <View style={styles.actionStarPos}>
                  <IconButtonWithTooltip
                    icon="star-outline"
                    label="Definir como principal"
                    onPress={() => marcarPrincipal(it.codigo)}
                    size={16}
                    color={colors.onBrandPrimary}
                    tooltipAlign="left"
                    style={styles.actionIconInner}
                    testID={`produto-imagem-${it.codigo}-principal`}
                  />
                </View>
              )}
              <View style={styles.actionTrashPos}>
                <IconButtonWithTooltip
                  icon="trash-outline"
                  label="Excluir foto"
                  onPress={() => excluir(it.codigo)}
                  size={16}
                  color={colors.onBrandPrimary}
                  tooltipAlign="right"
                  style={styles.actionIconInner}
                  testID={`produto-imagem-${it.codigo}-excluir`}
                />
              </View>
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
              accept={FORMATOS_ACEITOS_ACCEPT}
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
        <Text style={styles.formatosHint}>
          Formatos aceitos: JPG, PNG, WEBP, GIF ou BMP — até 10MB por foto.
        </Text>
        <Text style={styles.formatosHint}>
          Prefira fotos QUADRADAS (proporção 1:1), com pelo menos 600x600 pixels — as miniaturas (busca de
          produto, PDV, catálogo) sempre aparecem em formato quadrado, então uma foto retangular tem as bordas
          cortadas automaticamente pra preencher o quadrado, sem distorcer a imagem.
        </Text>
      </View>
      <ImageLightboxModal visible={!!lightboxUrl} onClose={() => setLightboxUrl(null)} imageUrl={lightboxUrl} />
    </View>
  );
}

const styles = StyleSheet.create({
  hint: { fontSize: 12, color: colors.muted, marginBottom: spacing.md },
  center: { paddingVertical: spacing.lg, alignItems: "center" },
  empty: { color: colors.muted, fontSize: 13, paddingVertical: spacing.md },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.md },
  cell: {
    // Sem `overflow: "hidden"` — a própria <img> já se recorta nos cantos
    // (mesmo `borderRadius` aplicado direto nela); manter overflow visível
    // aqui é o que permite a tooltip dos ícones (Definir principal/Excluir)
    // escapar pra fora da miniatura 110x110 em vez de ficar cortada.
    width: 110, height: 110, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, position: "relative",
  },
  // Posicionamento (absoluto sobre a miniatura) separado do visual do
  // círculo (`actionIconInner`) — `IconButtonWithTooltip` aplica seu
  // `style` no Pressable interno, não no wrapper que ele mesmo cria pra
  // posicionar a tooltip; por isso o wrapper de posição fica aqui fora.
  actionStarPos: { position: "absolute", top: 4, left: 4 },
  actionTrashPos: { position: "absolute", top: 4, right: 4 },
  actionIconInner: {
    backgroundColor: "rgba(0,0,0,0.45)",
    borderRadius: 10, width: 20, height: 20, alignItems: "center", justifyContent: "center",
  },
  uploadCard: {
    padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  uploadRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", marginBottom: spacing.sm },
  formatosHint: { fontSize: 11, color: colors.muted },
  label: { fontSize: 12, color: colors.muted, marginBottom: 4 },
  chkRow: { flexDirection: "row", alignItems: "center", gap: 6, height: 36 },
  chkLabel: { fontSize: 13, color: colors.onSurface },
  uploadBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, height: 36, borderRadius: radius.sm,
  },
  uploadBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
});

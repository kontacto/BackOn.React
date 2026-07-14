import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { Ionicons } from "@/src/components/Ionicons";
import SelectField from "@/src/components/SelectField";
import DateField from "@/src/components/DateField";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";

// Gestor de Documentos (Anexos) — genérico, reutilizável por qualquer tela
// "identidade" (Cliente, Fornecedor, Funcionário, Produto, Serviço) e,
// dentro do Cliente, também por Pedidos/O.S. via `referencia` (mesmo padrão
// do legado: anexo do pedido é um anexo do Cliente, filtrado por sub-grupo +
// número do pedido). Ver FrmGesDoc.frm / backend/services/
// gestor_documentos_service.py para o desenho completo.
//
// Só abre a partir da tela de uma entidade (Cliente, Fornecedor, ...) — não
// tem ponto de entrada próprio, por isso "Entidade" aqui é um rótulo fixo
// (a partir de `codGrupo`, decidido pelo chamador), não um combo editável,
// diferente do resto do formulário — mesmo comportamento do combo travado
// "Entidade" no legado (`Grupos.Enabled = False`, sempre pré-selecionado
// pela tela que abriu o Gestor de Documentos).
//
// Web-only por enquanto (usa <input type="file"> nativo, mesmo raciocínio
// já usado em CertificadoGrid/DateField pra não puxar expo-document-picker
// só pra essa primeira integração) — telas mobile (Pedidos/O.S.) vão
// precisar de um picker nativo quando esta seção for reaproveitada lá.

export const GESTOR_DOC_GRUPO_CLIENTE = 1;
export const GESTOR_DOC_GRUPO_FORNECEDOR = 2;
export const GESTOR_DOC_GRUPO_FUNCIONARIO = 3;
export const GESTOR_DOC_GRUPO_PRODUTO = 4;
export const GESTOR_DOC_GRUPO_SERVICO = 5;

const GRUPO_LABELS: Record<number, string> = {
  [GESTOR_DOC_GRUPO_CLIENTE]: "Clientes",
  [GESTOR_DOC_GRUPO_FORNECEDOR]: "Fornecedores",
  [GESTOR_DOC_GRUPO_FUNCIONARIO]: "Funcionários",
  [GESTOR_DOC_GRUPO_PRODUTO]: "Produtos",
  [GESTOR_DOC_GRUPO_SERVICO]: "Serviços",
};

const IMAGE_EXT = new Set(["jpg", "jpeg", "png", "bmp", "gif", "webp"]);

function extensaoDe(nomeArquivo: string): string {
  const m = /\.([a-zA-Z0-9]+)$/.exec(nomeArquivo || "");
  return (m?.[1] || "").toLowerCase();
}

type Documento = {
  codigo: number;
  cod_sub_grupo: number | null;
  sub_grupo: string;
  descricao: string;
  adicionado_por: string;
  data: string | null;
  hora: string;
  computador: string;
  path_origem: string;
};

type Props = {
  api: string;
  servidor: string;
  banco: string;
  codGrupo: number;
  codigoEntidade: string | number;
  // `codGrupo` é sempre a entidade PRINCIPAL (Cliente/Fornecedor/Funcionário/
  // Produto/Serviço). Quando quem abre o Gestor de Documentos não é uma
  // entidade principal (ex.: Pedido de Venda, O.S. — que são anexos do
  // Cliente, filtrados por sub-grupo + referência), passar `codSubGrupo` e
  // `referencia` também: filtra a lista pelos dois (evita um Pedido nº100 e
  // uma O.S. nº100 do mesmo cliente colidirem só por causa de `referencia`)
  // e trava o formulário de upload nesse sub-grupo (igual ao legado,
  // Sub_Grupos.Enabled = False quando o chamador já define o contexto).
  codSubGrupo?: number;
  referencia?: number;
};

export default function GestorDocumentosSection({ api, servidor, banco, codGrupo, codigoEntidade, codSubGrupo, referencia }: Props) {
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const base = api.replace(/\/+$/, "");
  const qsConn = `servidor=${encodeURIComponent(servidor)}&banco=${encodeURIComponent(banco)}`;

  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<Documento[]>([]);
  const [selecionado, setSelecionado] = useState<Documento | null>(null);
  const [subGrupos, setSubGrupos] = useState<{ value: number; label: string }[]>([]);
  const [subGrupo, setSubGrupo] = useState<number | null>(codSubGrupo ?? null);
  const [descricao, setDescricao] = useState("");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  // Referência: pré-preenchida e travada quando o chamador já sabe o valor
  // (ex.: Pedido/O.S. passando o próprio número via prop `referencia`),
  // editável livremente quando não — igual ao legado (Campo(2).Enabled).
  const [referenciaInput, setReferenciaInput] = useState(referencia ? String(referencia) : "");
  const [validade, setValidade] = useState<string | null>(null);

  const codigoStr = String(codigoEntidade);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = `${qsConn}&cod_grupo=${codGrupo}&codigo_entidade=${encodeURIComponent(codigoStr)}` +
        (codSubGrupo ? `&cod_sub_grupo=${codSubGrupo}` : "") +
        (referencia ? `&referencia=${referencia}` : "");
      const r = await fetch(`${base}/api/gestor-documentos?${qs}`);
      const j = await r.json();
      const novosItems: Documento[] = j?.success ? j.items : [];
      setItems(novosItems);
      setSelecionado((atual) => novosItems.find((i) => i.codigo === atual?.codigo) || novosItems[0] || null);
    } catch {
      setItems([]);
      setSelecionado(null);
    } finally {
      setLoading(false);
    }
  }, [base, qsConn, codGrupo, codigoStr, codSubGrupo, referencia]);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${base}/api/gestor-documentos/sub-grupos?${qsConn}&cod_grupo=${codGrupo}`);
        const j = await r.json();
        if (j?.success) {
          setSubGrupos(j.items.map((s: { cod_sub_grupo: number; descricao: string }) => ({ value: s.cod_sub_grupo, label: s.descricao })));
        }
      } catch {
        setSubGrupos([]);
      }
    })();
    reload();
  }, [base, qsConn, codGrupo, reload]);

  const upload = async () => {
    if (!arquivo) { fb.showWarning("Selecione um arquivo."); return; }
    if (subGrupo == null) { fb.showWarning("Selecione o sub-grupo."); return; }
    if (!descricao.trim()) { fb.showWarning("Informe a descrição do documento."); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("servidor", servidor);
      fd.append("banco", banco);
      fd.append("cod_grupo", String(codGrupo));
      fd.append("cod_sub_grupo", String(subGrupo));
      fd.append("codigo_entidade", codigoStr);
      fd.append("descricao", descricao.trim());
      if (referenciaInput.trim()) fd.append("referencia", String(parseInt(referenciaInput, 10)));
      if (validade) fd.append("validade", validade);
      if (auditCtx.usuario_alteracao != null) fd.append("usuario_alteracao", String(auditCtx.usuario_alteracao));
      if (auditCtx.classe != null) fd.append("classe", String(auditCtx.classe));
      fd.append("plataforma", auditCtx.plataforma);
      fd.append("adicionado_por", String(auditCtx.usuario_alteracao ?? ""));
      fd.append("arquivo", arquivo, arquivo.name);
      const r = await fetch(`${base}/api/gestor-documentos`, { method: "POST", body: fd });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Documento anexado.");
        setDescricao("");
        setArquivo(null);
        setSubGrupo(null);
        setValidade(null);
        if (!referencia) setReferenciaInput("");
        await reload();
      } else {
        fb.showError(j?.message || "Falha ao anexar documento.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setUploading(false);
    }
  };

  const excluir = async (codigo: number) => {
    try {
      const r = await fetch(`${base}/api/gestor-documentos/${codigo}/excluir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor, banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Documento removido."); await reload(); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const arquivoUrl = (codigo: number) => `${base}/api/gestor-documentos/${codigo}/arquivo?${qsConn}`;

  const baixar = (codigo: number) => {
    if (Platform.OS === "web" && typeof window !== "undefined") window.open(arquivoUrl(codigo), "_blank");
  };

  const previewExt = selecionado ? extensaoDe(selecionado.path_origem) : "";

  return (
    <View testID="gestor-documentos-section">
      <Text style={styles.entidadeLabel}>Entidade: <Text style={styles.entidadeValor}>{GRUPO_LABELS[codGrupo] || codGrupo}</Text></Text>

      <View style={styles.mainRow}>
        <View style={styles.listCol}>
          {loading ? (
            <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
          ) : items.length === 0 ? (
            <Text style={styles.empty}>Nenhum documento anexado.</Text>
          ) : (
            items.map((it) => (
              <Pressable
                key={it.codigo}
                onPress={() => setSelecionado(it)}
                style={[styles.row, selecionado?.codigo === it.codigo && styles.rowSel]}
                testID={`gestor-doc-${it.codigo}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle} numberOfLines={1}>{it.descricao}</Text>
                  <Text style={styles.rowSub} numberOfLines={1}>
                    {it.sub_grupo} — {it.adicionado_por} em {it.data} {it.hora}
                  </Text>
                </View>
                <Pressable onPress={() => baixar(it.codigo)} hitSlop={8} style={{ marginRight: spacing.sm }}>
                  <Ionicons name="download-outline" size={18} color={colors.brandPrimary} />
                </Pressable>
                <Pressable onPress={() => excluir(it.codigo)} hitSlop={8}>
                  <Ionicons name="trash-outline" size={18} color={colors.error} />
                </Pressable>
              </Pressable>
            ))
          )}

          <View style={styles.uploadCard}>
            <View style={styles.uploadRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Sub-grupo</Text>
                <SelectField
                  value={subGrupo}
                  onChange={(v) => setSubGrupo(v != null ? Number(v) : null)}
                  options={subGrupos.map((s) => ({ value: s.value, label: s.label }))}
                  disabled={!!codSubGrupo}
                  compactWeb
                  testID="gestor-doc-subgrupo"
                />
              </View>
              <View style={{ flex: 2 }}>
                <Text style={styles.label}>Descrição</Text>
                <TextInput
                  value={descricao}
                  onChangeText={setDescricao}
                  style={styles.input}
                  placeholder="Ex: Contrato assinado"
                  placeholderTextColor={colors.muted}
                  testID="gestor-doc-descricao"
                />
              </View>
            </View>
            <View style={styles.uploadRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Referência</Text>
                <TextInput
                  value={referenciaInput}
                  onChangeText={setReferenciaInput}
                  editable={!referencia}
                  style={[styles.input, !!referencia && { color: colors.muted }]}
                  placeholder="Opcional"
                  placeholderTextColor={colors.muted}
                  keyboardType="number-pad"
                  testID="gestor-doc-referencia"
                />
              </View>
              <View style={{ flex: 1 }}>
                <DateField
                  label="Validade"
                  value={validade}
                  onChange={setValidade}
                  allowClear
                  testID="gestor-doc-validade"
                />
              </View>
            </View>
            <View style={styles.uploadRow}>
              {Platform.OS === "web" ? (
                <input
                  type="file"
                  onChange={(e) => setArquivo((e.target as HTMLInputElement).files?.[0] || null)}
                  style={{
                    flex: 1, height: 36, boxSizing: "border-box", padding: "0 8px", fontSize: 13,
                    border: `1px solid ${colors.border}`, borderRadius: radius.sm,
                    backgroundColor: colors.surface, color: colors.onSurface,
                  }}
                />
              ) : null}
              <Pressable onPress={upload} disabled={uploading} style={styles.uploadBtn} testID="gestor-doc-upload">
                {uploading ? (
                  <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                ) : (
                  <>
                    <Ionicons name="attach-outline" size={16} color={colors.onBrandPrimary} />
                    <Text style={styles.uploadBtnText}>Anexar</Text>
                  </>
                )}
              </Pressable>
            </View>
          </View>
        </View>

        {/* Painel de visualização — mesma ideia do AcroPDF1/Image1 do legado */}
        {Platform.OS === "web" ? (
          <View style={styles.previewCol} testID="gestor-doc-preview">
            {!selecionado ? (
              <Text style={styles.previewEmpty}>Selecione um documento para visualizar.</Text>
            ) : IMAGE_EXT.has(previewExt) ? (
              // eslint-disable-next-line jsx-a11y/alt-text
              <img src={arquivoUrl(selecionado.codigo)} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
            ) : previewExt === "pdf" ? (
              <iframe src={arquivoUrl(selecionado.codigo)} style={{ width: "100%", height: "100%", border: "none" }} />
            ) : (
              <Text style={styles.previewEmpty}>Sem pré-visualização disponível para este tipo de arquivo.</Text>
            )}
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  entidadeLabel: { fontSize: 13, color: colors.muted, marginBottom: spacing.sm },
  entidadeValor: { color: colors.onSurface, fontWeight: "600" },
  mainRow: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  listCol: { flex: 1, minWidth: 0 },
  previewCol: {
    flex: 1, minHeight: 420, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", overflow: "hidden",
    padding: spacing.sm,
  },
  previewEmpty: { color: colors.muted, fontSize: 13, textAlign: "center", paddingHorizontal: spacing.md },
  center: { paddingVertical: spacing.lg, alignItems: "center" },
  empty: { color: colors.muted, fontSize: 13, paddingVertical: spacing.md },
  row: {
    flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm, paddingHorizontal: spacing.xs,
    borderBottomWidth: 1, borderBottomColor: colors.border, borderRadius: radius.sm,
  },
  rowSel: { backgroundColor: colors.surfaceSecondary },
  rowTitle: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  uploadCard: {
    marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  uploadRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, marginBottom: 4 },
  input: {
    height: 36, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  uploadBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, height: 36, borderRadius: radius.sm,
  },
  uploadBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
});

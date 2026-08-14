// Preenchimento de Formulário Dinâmico (Motor de Layout — `FrmPreLay2.frm`,
// lógica comentada usada como especificação funcional, ver
// backend/services/layout_service.py e PENDENCIAS.md > "Motor de Layout").
// Reaproveitável por qualquer entidade (Agenda, `entidade=8`; O.S.,
// `entidade=7`; ver `_ENTIDADE_COLUNA` no backend) — basta passar
// `entidade`/`codentidade` diferentes.
//
// Escopo: modo "grade de campos" em texto livre — sem resolução ao vivo de
// campo calculado (soma/subtração/multiplicação/divisão entre 2 campos).
// Campo calculado aparece desabilitado com um aviso, em vez de tentar
// calcular errado.
//
// 2026-08-12, user-directed: campos agora respeitam a posição/disposição
// original do documento (`campo_agrupado` — 2 campos consecutivos com o
// primeiro marcado renderizam lado a lado, 2 colunas); campos do tipo
// "Sim/Não" viram um seletor de 2 opções em vez de texto livre; botões de
// ação (Gravar/Imprimir) ficam no topo do modal, não no rodapé; Possíveis
// (a preencher) e Preenchidos ficam em abas separadas — uma lista só ficava
// "uma bagunça" com muitos layouts associados à mesma entidade (OS com 20+
// layouts, por exemplo); Imprimir gera um PDF A4 com cabeçalho da empresa.
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { apiBase, apiDelete, apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { fetchEmpresaHeader } from "@/src/utils/print-report-header";
import { exportLayoutPreenchimentoPdf } from "@/src/utils/export-layout-preenchimento";
import SelectField from "@/src/components/SelectField";
import { styles } from "@/src/components/pedido/styles";

const SIM_NAO_OPCOES = [{ value: "Sim", label: "Sim" }, { value: "Não", label: "Não" }];

const isWeb = Platform.OS === "web";

type LayoutOpt = { codigo: number; descricao: string };
type Preenchido = { codigo: number; descricao: string; data: string };
type Campo = {
  codigo: number; campo1: string; campo2: string; tipo_descricao: string;
  calculado: boolean; unidade_medida: string; campo_agrupado: boolean; conteudo?: string;
};

function ehSimNao(tipoDescricao: string): boolean {
  const t = (tipoDescricao || "").trim().toLowerCase();
  return t.includes("sim") && (t.includes("não") || t.includes("nao"));
}

// Autofill nativo do navegador desabilitado — mesmo achado já documentado
// no campo Cliente (Pedido/O.S.): campos de texto genéricos num formulário
// podem ser mal-interpretados pelo Chrome como login/senha, disparando o
// prompt "Atualizar senha?" ao Gravar. `autoComplete="off"` sozinho é
// ignorado pelo Chrome pra esse caso — precisa da combinação abaixo.
const NO_AUTOFILL = {
  autoComplete: "new-password" as const,
  autoCorrect: false as const,
  textContentType: "none" as const,
  importantForAutofill: "no" as const,
};

// Formatação reduzida (CLAUDE.md > "Padrões de UI" > seção 3) — sobrepõe os
// estilos compartilhados de pedido/styles.ts (mais largos, pensados pra
// telas de Pedido/O.S.) só localmente, sem editar o arquivo compartilhado.
const compact = {
  input: { paddingVertical: 8, fontSize: 13, minHeight: 36 },
  modalTitle: { fontSize: 15 },
  resultRow: { paddingVertical: spacing.sm },
  // Botões da barra de ações (Excluir/Imprimir/Gravar) — mesma largura
  // (flex:1, dividem a linha em partes iguais) e mesma altura pros 3,
  // sobrepondo o `flex:1` que `secondaryBtn`/`primaryBtn` já trazem de
  // pedido/styles.ts (esse já é flex:1 — o bug visual veio de outro ponto
  // dar flex:0 só pros contornados, não de faltar a propriedade aqui).
  acaoBtn: { flex: 1, paddingHorizontal: spacing.sm, paddingVertical: 9, minHeight: 38 },
};

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  entidade: number;
  codentidade: number;
  usuarioCod: number;
  title?: string;
  // Dados de identidade já cadastrados na entidade vinculada (Cliente,
  // Técnico, Data do atendimento, etc.) — exibidos só na impressão do
  // preenchimento, nunca digitados no formulário. Pedido explícito do
  // usuário: "trazer da entidade se existir".
  dadosExtras?: { label: string; valor: string }[];
};

export default function LayoutPreenchimentoModal({
  visible, onClose, conn, entidade, codentidade, usuarioCod, title, dadosExtras,
}: Props) {
  const feedback = useFeedback();
  const [loading, setLoading] = useState(false);
  const [possiveis, setPossiveis] = useState<LayoutOpt[]>([]);
  const [preenchidos, setPreenchidos] = useState<Preenchido[]>([]);
  const [aba, setAba] = useState<"novo" | "preenchidos">("novo");

  // Formulário aberto pra preencher/editar — codlayout + código de
  // layout_entidade (null = novo preenchimento).
  const [formLayout, setFormLayout] = useState<{ codlayout: number; codigo: number | null; descricao: string } | null>(null);
  const [campos, setCampos] = useState<Campo[]>([]);
  const [saving, setSaving] = useState(false);
  const [imprimindo, setImprimindo] = useState(false);

  useEffect(() => {
    if (!visible || !conn) return;
    setFormLayout(null);
    setAba("novo");
    setLoading(true);
    Promise.all([
      apiGet(conn, "/api/layout/possiveis", { entidade, codentidade }),
      apiGet(conn, "/api/layout/preenchidos", { entidade, codentidade }),
    ])
      .then(([jp, jh]) => {
        setPossiveis(jp?.success ? jp.items || [] : []);
        setPreenchidos(jh?.success ? jh.items || [] : []);
      })
      .finally(() => setLoading(false));
  }, [visible, conn, entidade, codentidade]);

  const abrirNovo = async (l: LayoutOpt) => {
    if (!conn) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, "/api/layout/campos", { layout: l.codigo });
      const items: Campo[] = (j?.success ? j.items || [] : []).map((c: Campo) => ({ ...c, conteudo: "" }));
      setCampos(items);
      setFormLayout({ codlayout: l.codigo, codigo: null, descricao: l.descricao });
    } finally {
      setLoading(false);
    }
  };

  const abrirPreenchido = async (p: Preenchido) => {
    if (!conn) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, `/api/layout/preenchimento/${p.codigo}`);
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao carregar preenchimento.")); return; }
      setCampos(j.campos || []);
      setFormLayout({ codlayout: j.codlayout, codigo: j.codigo, descricao: p.descricao });
    } finally {
      setLoading(false);
    }
  };

  const setConteudo = (codigoCampo: number, v: string) => {
    setCampos((prev) => prev.map((c) => (c.codigo === codigoCampo ? { ...c, conteudo: v } : c)));
  };

  const salvar = async () => {
    if (!conn || !formLayout) return;
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/layout/preencher", "POST", {
        entidade, codentidade, codlayout: formLayout.codlayout, codigo: formLayout.codigo,
        usuario_alteracao: usuarioCod,
        respostas: campos
          .filter((c) => !c.calculado && (c.conteudo || "").trim())
          .map((c) => ({ codigo_campo: c.codigo, conteudo: c.conteudo || "" })),
      });
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao gravar preenchimento.")); return; }
      feedback.showSuccess("Preenchimento gravado.");
      const codigoGravado = formLayout.codigo ?? j.codigo;
      setFormLayout((prev) => (prev ? { ...prev, codigo: codigoGravado } : prev));
      const jh = await apiGet(conn, "/api/layout/preenchidos", { entidade, codentidade });
      setPreenchidos(jh?.success ? jh.items || [] : []);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao gravar preenchimento."));
    } finally {
      setSaving(false);
    }
  };

  const imprimir = async () => {
    if (!conn || !formLayout) return;
    setImprimindo(true);
    try {
      const empresa = await fetchEmpresaHeader(apiBase(conn), conn.servidor, conn.banco);
      await exportLayoutPreenchimentoPdf({
        titulo: formLayout.descricao,
        empresa,
        dadosExtras,
        campos: campos.map((c) => ({
          campo1: c.campo1, tipo_descricao: c.tipo_descricao, unidade_medida: c.unidade_medida,
          conteudo: c.conteudo || "", campo_agrupado: c.campo_agrupado,
        })),
      });
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao gerar a impressão."));
    } finally {
      setImprimindo(false);
    }
  };

  const excluirPreenchimento = () => {
    if (!conn || !formLayout || !formLayout.codigo) return;
    const codigo = formLayout.codigo;
    feedback.showConfirm(`Excluir este preenchimento de "${formLayout.descricao}"?`, async () => {
      try {
        const j = await apiDelete(conn, `/api/layout/preenchimento/${codigo}`, { usuario_alteracao: usuarioCod, plataforma: Platform.OS });
        if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao excluir preenchimento.")); return; }
        feedback.showSuccess("Preenchimento excluído.");
        setFormLayout(null);
        const jh = await apiGet(conn, "/api/layout/preenchidos", { entidade, codentidade });
        setPreenchidos(jh?.success ? jh.items || [] : []);
      } catch (e) {
        feedback.showError(friendlyCatchError(e, "Falha ao excluir preenchimento."));
      }
    });
  };

  // Agrupa campos consecutivos (campo_agrupado=true no primeiro) em linhas
  // de até 2 colunas, preservando a posição/disposição original do
  // documento importado.
  const linhas: Campo[][] = [];
  for (let i = 0; i < campos.length; i++) {
    const atual = campos[i];
    const proximo = campos[i + 1];
    if (atual.campo_agrupado && proximo) {
      linhas.push([atual, proximo]);
      i++;
    } else {
      linhas.push([atual]);
    }
  }

  const renderCampo = (c: Campo) => (
    <View key={c.codigo} style={{ flex: 1, minWidth: 0 }}>
      <Text style={styles.fieldLabel}>
        {c.campo1}{c.campo2 ? ` — ${c.campo2}` : ""}{c.unidade_medida ? ` (${c.unidade_medida})` : ""}
      </Text>
      {c.calculado ? (
        <Text style={[styles.resultSub, { fontStyle: "italic" }]}>
          Campo calculado — resolvido a partir de outros campos (sem edição direta).
        </Text>
      ) : ehSimNao(c.tipo_descricao) ? (
        <SelectField
          value={c.conteudo || null}
          onChange={(v) => setConteudo(c.codigo, (v as string) || "")}
          options={SIM_NAO_OPCOES}
          compactWeb
          testID={`layout-campo-${c.codigo}`}
        />
      ) : (
        <TextInput
          value={c.conteudo || ""}
          onChangeText={(v) => setConteudo(c.codigo, v)}
          style={[styles.input, compact.input]}
          placeholder={c.tipo_descricao}
          placeholderTextColor={colors.muted}
          testID={`layout-campo-${c.codigo}`}
          {...NO_AUTOFILL}
        />
      )}
    </View>
  );

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={[styles.modalHeader, { marginBottom: formLayout ? spacing.sm : spacing.md }]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flex: 1, minWidth: 0 }}>
              {formLayout ? (
                <Pressable onPress={() => setFormLayout(null)} hitSlop={8} testID="layout-preencher-voltar">
                  <Ionicons name="arrow-back" size={20} color={colors.onSurface} />
                </Pressable>
              ) : null}
              <Text style={[styles.modalTitle, compact.modalTitle]} numberOfLines={1}>
                {formLayout ? formLayout.descricao : (title || "Formulários (Layouts)")}
              </Text>
            </View>
            <Pressable onPress={onClose} hitSlop={8} testID="layout-preencher-fechar">
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          {/* Barra de ações — sempre no topo do modal, nunca no rodapé
              depois de rolar a lista de campos. Padronizado 2026-08-12,
              user-directed: os 3 botões têm exatamente a MESMA largura
              (flex:1, todos dividindo a linha em partes iguais) e a MESMA
              altura (mesmo paddingVertical) — só a COR muda por ação
              (Excluir=vermelho contornado, Imprimir=neutro contornado,
              Gravar=preenchido azul). O bug anterior vinha de dar flex:0
              (largura pelo conteúdo) só pra Excluir/Imprimir enquanto
              Gravar ficava com flex:1 — sobrava toda a largura da linha só
              pra ele. */}
          {formLayout ? (
            <View style={{ flexDirection: "row", alignItems: "stretch", gap: spacing.sm, marginBottom: spacing.sm }}>
              {formLayout.codigo ? (
                <Pressable
                  onPress={excluirPreenchimento}
                  style={[styles.secondaryBtn, compact.acaoBtn, { borderColor: colors.error }]}
                  testID="layout-preencher-excluir"
                >
                  <Text style={[styles.secondaryBtnText, { color: colors.error }]}>Excluir</Text>
                </Pressable>
              ) : null}
              <Pressable
                onPress={imprimir}
                disabled={imprimindo}
                style={[styles.secondaryBtn, compact.acaoBtn, { opacity: imprimindo ? 0.7 : 1 }]}
                testID="layout-preencher-imprimir"
              >
                {imprimindo ? <ActivityIndicator color={colors.onSurface} size="small" /> : <Text style={styles.secondaryBtnText}>Imprimir</Text>}
              </Pressable>
              <Pressable
                onPress={salvar}
                disabled={saving}
                style={[styles.primaryBtn, compact.acaoBtn, { opacity: saving ? 0.7 : 1 }]}
                testID="layout-preencher-salvar"
              >
                {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
              </Pressable>
            </View>
          ) : null}

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}

          {!loading && !formLayout ? (
            <>
              <View style={{ flexDirection: "row", gap: spacing.xs, marginBottom: spacing.sm }}>
                {([
                  { key: "novo" as const, label: `Novo (${possiveis.length})` },
                  { key: "preenchidos" as const, label: `Preenchidos (${preenchidos.length})` },
                ]).map((t) => (
                  <Pressable
                    key={t.key}
                    onPress={() => setAba(t.key)}
                    style={{
                      flex: 1, paddingVertical: 8, borderRadius: radius.sm, alignItems: "center",
                      backgroundColor: aba === t.key ? colors.brandPrimary : colors.surfaceSecondary,
                    }}
                    testID={`layout-preencher-aba-${t.key}`}
                  >
                    <Text style={{ fontSize: 12, fontWeight: "600", color: aba === t.key ? colors.onBrandPrimary : colors.onSurface }}>
                      {t.label}
                    </Text>
                  </Pressable>
                ))}
              </View>
              <ScrollView style={{ maxHeight: 420 }}>
                {aba === "novo" ? (
                  [...possiveis].sort((a, b) => a.descricao.localeCompare(b.descricao, "pt-BR")).map((l) => (
                    <Pressable
                      key={l.codigo}
                      onPress={() => abrirNovo(l)}
                      style={({ pressed }) => [styles.resultRow, compact.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                      testID={`layout-possivel-${l.codigo}`}
                    >
                      <Ionicons name="square-outline" size={16} color={colors.brandPrimary} />
                      <Text style={styles.resultNome}>{l.descricao}</Text>
                    </Pressable>
                  ))
                ) : preenchidos.length === 0 ? (
                  <Text style={styles.resultSub}>Nenhum preenchimento ainda.</Text>
                ) : (
                  preenchidos.map((p) => (
                    <Pressable
                      key={p.codigo}
                      onPress={() => abrirPreenchido(p)}
                      style={({ pressed }) => [styles.resultRow, compact.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                      testID={`layout-preenchido-${p.codigo}`}
                    >
                      <Ionicons name="document-outline" size={16} color={colors.muted} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.resultNome}>{p.descricao}</Text>
                        <Text style={styles.resultSub}>{p.data}</Text>
                      </View>
                    </Pressable>
                  ))
                )}
                {aba === "novo" && possiveis.length === 0 ? (
                  <Text style={styles.resultSub}>Nenhum layout aplicável a este registro.</Text>
                ) : null}
              </ScrollView>
            </>
          ) : null}

          {!loading && formLayout ? (
            <ScrollView style={{ maxHeight: 460 }}>
              <View style={{ gap: spacing.sm }}>
                {linhas.map((linha, i) => (
                  <View key={i} style={{ flexDirection: "row", gap: spacing.sm }}>
                    {linha.map((c) => renderCampo(c))}
                  </View>
                ))}
                {campos.length === 0 ? (
                  <Text style={styles.resultSub}>Este layout não tem campos cadastrados.</Text>
                ) : null}
              </View>
            </ScrollView>
          ) : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

import { useState } from "react";
import {
  ActivityIndicator, Alert, Image, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { AppModal } from "@/src/components/AppModal";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_PRODUTO } from "@/src/components/GestorDocumentosSection";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import {
  useProdutoCompletoForm, ProdutoForm, FornecedorItem, SimilarItem, SecundarioItem, XmlVinculoItem,
} from "@/src/hooks/useProdutoCompletoForm";

// Cadastro de Produtos (completo) — tabela `pecas`. Legado: FrmManPec.frm
// (Kontacto, "Cadastro de Produtos"), rastreado campo-a-campo 2026-07-14 —
// ver backend/services/produto_completo_service.py e PENDENCIAS.md >
// "Produtos (Cadastro Completo)" pro relatório de rastreio e as decisões
// tomadas (Tray real, Grade/Livro condicionados a módulo).
//
// Web-only, tela cheia (não modal) — mesmo padrão de cliente-completo.tsx/
// fornecedores.tsx/servicos.tsx (header com Gravar no topo direito, abas
// com ícone). Diferente de Cliente/Fornecedor, esta tela é ACESSADA por
// código na URL (`?codigo=P123`), não tem lista+form no mesmo arquivo — a
// lista já existe em produtos.tsx (buscador compartilhado com o picker de
// item de Pedido/O.S.), que agora navega pra cá ao tocar num item.
//
// Fornecedores/Fotografia são botões que abrem modal (mesmo padrão de
// "Secondary sections that are separate Frames/popups" no CLAUDE.md) —
// Similares/Secundários e Grade são abas de verdade no legado, então viram
// conteúdo inline de aba aqui.

type TabKey = "principal" | "descontos" | "fiscal" | "secundarios" | "grade" | "similares" | "livro" | "anexos";

type FieldProps = { form: ProdutoForm; setField: (k: string, v: string | boolean) => void };

function Txt({ form, setField, campo, label, placeholder, maxLength, disabled = false }: FieldProps & {
  campo: string; label: string; placeholder?: string; maxLength?: number; disabled?: boolean;
}) {
  return (
    <View style={styles.colFlex}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={String(form[campo] ?? "")}
        onChangeText={(v) => setField(campo, v)}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={[styles.input, disabled && styles.inputDisabled]}
        maxLength={maxLength}
        editable={!disabled}
        testID={`produto-${campo}`}
      />
    </View>
  );
}

function Num({ form, setField, campo, label, placeholder, narrow = false, disabled = false }: FieldProps & {
  campo: string; label: string; placeholder?: string; narrow?: boolean; disabled?: boolean;
}) {
  return (
    <View style={narrow ? styles.colNarrow : styles.colFlex}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={String(form[campo] ?? "")}
        onChangeText={(v) => setField(campo, v.replace(/[^0-9,.-]/g, ""))}
        keyboardType="decimal-pad"
        placeholder={placeholder ?? "0,00"}
        placeholderTextColor={colors.muted}
        editable={!disabled}
        style={[styles.input, disabled && styles.inputDisabled]}
        testID={`produto-${campo}`}
      />
    </View>
  );
}

function Chk({ form, setField, campo, label }: FieldProps & { campo: string; label: string }) {
  return (
    <View style={styles.switchRow}>
      <Switch value={!!form[campo]} onValueChange={(v) => setField(campo, v)} testID={`produto-${campo}-switch`} />
      <Text style={styles.switchLabel}>{label}</Text>
    </View>
  );
}

const SITUACAO_OPTS: SelectOption[] = [
  { value: "A", label: "Ativo" },
  { value: "I", label: "Inativo" },
];
const ORIGEM_OPTS: SelectOption[] = Array.from({ length: 9 }, (_, i) => ({ value: String(i), label: String(i) }));

export default function ProdutoCompletoScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ codigo?: string }>();
  const { can, moduleOn } = usePermissions();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="O Cadastro de Produtos completo está disponível apenas no web."
        testID="produto-completo-web-only"
      />
    );
  }

  const f = useProdutoCompletoForm(params.codigo);
  const [tab, setTab] = useState<TabKey>("principal");
  const [fornecedorModal, setFornecedorModal] = useState(false);
  const [fotografiaModal, setFotografiaModal] = useState(false);
  const [gradeModal, setGradeModal] = useState(false);

  const canSave = can("PRODUTO_COMP.GRAVAR");
  const gradeOn = moduleOn("grade");
  const livroOn = moduleOn("Livraria");

  const TABS: { key: TabKey; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { key: "principal", label: "Dados Principais", icon: "cube-outline" },
    { key: "descontos", label: "Descontos e Comissões", icon: "pricetag-outline" },
    { key: "fiscal", label: "Configurações Fiscais", icon: "receipt-outline" },
    { key: "secundarios", label: "Dados Secundários", icon: "layers-outline" },
    ...(gradeOn ? [{ key: "grade" as TabKey, label: "Grade do Produto", icon: "grid-outline" as const }] : []),
    { key: "similares", label: "Similares e Equivalentes", icon: "git-compare-outline" },
    ...(livroOn ? [{ key: "livro" as TabKey, label: "Livro", icon: "book-outline" as const }] : []),
    { key: "anexos", label: "Anexos", icon: "attach-outline" },
  ];

  const handleSave = async () => {
    const result = await f.save();
    if (result && !result.wasEditing) {
      router.replace({ pathname: "/produto-completo", params: { codigo: result.codigo_int } });
    }
  };

  const handleDelete = () => {
    Alert.alert("Excluir", `Confirma a exclusão do produto "${f.editingCodigo}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          if (await f.deleteProduto()) router.back();
        },
      },
    ]);
  };

  if (f.loadingInit) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="produto-completo-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]} hitSlop={12} testID="produto-completo-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>
          {String(f.form.descricao || "") || "Novo Produto"}
        </Text>
        {canSave ? (
          <Pressable onPress={handleSave} disabled={f.saving} style={({ pressed }) => [styles.saveBtn, (pressed || f.saving) && { opacity: 0.7 }]} testID="produto-completo-save">
            {f.saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
              <>
                <Ionicons name="save-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.saveLabel}>Gravar</Text>
              </>
            )}
          </Pressable>
        ) : <View style={{ width: 90 }} />}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          {/* Identidade do produto — sempre visível, qualquer que seja a aba
              selecionada (mesmo padrão do FrmManPec.frm legado: código,
              descrição e aplicação ficam ACIMA da barra de abas, nunca
              escondidos ao trocar de aba). Ver CLAUDE.md > "Produto Completo". */}
          <View style={styles.card}>
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Código Interno</Text>
                <TextInput
                  value={String(f.form.codigo_int || "")}
                  onChangeText={(v) => f.setField("codigo_int", v.toUpperCase())}
                  onBlur={() => {
                    const val = String(f.form.codigo_int || "").trim();
                    if (val) f.buscarPorCodigoInt(val);
                  }}
                  placeholder="novo"
                  placeholderTextColor={colors.muted}
                  autoCapitalize="characters"
                  style={styles.input}
                  testID="produto-codigo_int"
                />
              </View>
              <Txt form={f.form} setField={f.setField} campo="codigo_fab" label="Código de Fábrica/Referência" />
              <Txt form={f.form} setField={f.setField} campo="codigo_bar" label="Código de Barras" />
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Situação</Text>
                <SelectField value={String(f.form.situacao || "A")} onChange={(v) => f.setField("situacao", String(v))} options={SITUACAO_OPTS} testID="produto-situacao" />
              </View>
            </View>

            <Text style={styles.label}>Descrição</Text>
            <TextInput value={String(f.form.descricao || "")} onChangeText={(v) => f.setField("descricao", v)} style={styles.input} testID="produto-descricao" />

            <Text style={styles.label}>Aplicação/Observações</Text>
            <TextInput value={String(f.form.Descricao_Completa || "")} onChangeText={(v) => f.setField("Descricao_Completa", v)} style={[styles.input, { minHeight: 70 }]} multiline testID="produto-aplicacao" />
          </View>

          <View style={styles.tabBar}>
            {TABS.map((t) => {
              const sel = tab === t.key;
              return (
                <Pressable key={t.key} onPress={() => setTab(t.key)} style={({ pressed }) => [styles.tabBtn, sel && styles.tabBtnSel, pressed && { opacity: 0.85 }]} testID={`produto-completo-tab-${t.key}`}>
                  <Ionicons name={t.icon} size={16} color={sel ? colors.onBrandPrimary : colors.muted} />
                  <Text style={[styles.tabLabel, sel && styles.tabLabelSel]}>{t.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {tab === "principal" ? (
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="descricao_pdv" label="Descrição PDV" />
                <Txt form={f.form} setField={f.setField} campo="descricao_embarque" label="Descrição Embarque" />
              </View>
              <Text style={styles.label}>Descrição NF</Text>
              <TextInput value={String(f.form.descricao_nf || "")} onChangeText={(v) => f.setField("descricao_nf", v)} style={[styles.input, { minHeight: 44 }]} multiline testID="produto-descricao-nf" />

              <Text style={styles.sectionTitle}>Preços</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="p_custo" label="Preço de Custo" />
                <Num form={f.form} setField={f.setField} campo="p_venda" label="Preço de Venda" />
                <Num form={f.form} setField={f.setField} campo="preco_lista" label="Preço de Tabela" />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="p_sugestao" label="Preço Sugestão" />
                <Num form={f.form} setField={f.setField} campo="p_garantia" label="Preço Garantia" />
                <Num form={f.form} setField={f.setField} campo="p_sugerido" label="Preço Sugerido" />
                <Num form={f.form} setField={f.setField} campo="preco_base" label="Preço Base" />
                <Num form={f.form} setField={f.setField} campo="preco_promocional" label="Preço Promocional" />
              </View>
              <Chk form={f.form} setField={f.setField} campo="preco_variado" label="Preço Variado" />

              <Text style={styles.sectionTitle}>Classificação</Text>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="marca_produto" label="Marca (código)" />
                <Txt form={f.form} setField={f.setField} campo="modelo_produto" label="Modelo (código)" />
                <Num form={f.form} setField={f.setField} campo="fornecedor" label="Fornecedor (código)" narrow />
                <Txt form={f.form} setField={f.setField} campo="cod_anp" label="Código ANP" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="nivel1" label="Nível 1" />
                <Txt form={f.form} setField={f.setField} campo="nivel2" label="Nível 2" />
                <Txt form={f.form} setField={f.setField} campo="nivel3" label="Nível 3" />
                <Txt form={f.form} setField={f.setField} campo="nivel4" label="Nível 4" />
                <Txt form={f.form} setField={f.setField} campo="nivel5" label="Nível 5" />
              </View>

              <View style={styles.checkRowGroup}>
                <Chk form={f.form} setField={f.setField} campo="Produto_web" label="Produto Web" />
                <Chk form={f.form} setField={f.setField} campo="FRETE_GRATIS_SITE" label="Frete Grátis Site" />
              </View>

              <Text style={styles.sectionTitle}>Estoque (somente leitura)</Text>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}><Text style={styles.label}>Estoque Atual</Text><Text style={styles.readonlyValue}>{String(f.form.qtd || 0)}</Text></View>
                <View style={styles.colNarrow}><Text style={styles.label}>Reservado</Text><Text style={styles.readonlyValue}>{String(f.form.reservado || 0)}</Text></View>
                <View style={styles.colNarrow}><Text style={styles.label}>Reservado OS</Text><Text style={styles.readonlyValue}>{String(f.form.reservado_os || 0)}</Text></View>
                <View style={styles.colNarrow}><Text style={styles.label}>Custo Médio</Text><Text style={styles.readonlyValue}>{String(f.form.custo_medio || 0)}</Text></View>
              </View>

              <View style={styles.toolbarRow}>
                <Pressable
                  onPress={() => (f.editingCodigo ? setFornecedorModal(true) : Alert.alert("Grave o produto primeiro"))}
                  disabled={!can("PRODUTO_COMP.FORNECEDORES")}
                  style={styles.secondaryBtn}
                  testID="produto-btn-fornecedores"
                >
                  <Ionicons name="briefcase-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.secondaryBtnText}>Fornecedores ({f.fornecedores.length})</Text>
                </Pressable>
                <Pressable
                  onPress={() => (f.editingCodigo ? setFotografiaModal(true) : Alert.alert("Grave o produto primeiro"))}
                  disabled={!can("PRODUTO_COMP.FOTOGRAFIA")}
                  style={styles.secondaryBtn}
                  testID="produto-btn-fotografia"
                >
                  <Ionicons name="image-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.secondaryBtnText}>Fotografia</Text>
                </Pressable>
                {f.editingCodigo && can("PRODUTO_COMP.EXCLUIR") ? (
                  <Pressable onPress={handleDelete} style={[styles.secondaryBtn, styles.dangerBtn]} testID="produto-btn-excluir">
                    <Ionicons name="trash-outline" size={16} color={colors.error} />
                    <Text style={[styles.secondaryBtnText, { color: colors.error }]}>Excluir</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          ) : null}

          {tab === "descontos" ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Descontos</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="desc_g" label="Desconto Grupo" narrow />
                <Num form={f.form} setField={f.setField} campo="desc_s" label="Desconto Subgrupo" narrow />
                <Num form={f.form} setField={f.setField} campo="desc_v" label="Desconto Vendedor" narrow />
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Política de Preço</Text>
                  <TextInput value={String(f.form.politica_preco || "")} onChangeText={(v) => f.setField("politica_preco", v.slice(0, 1))} style={styles.input} maxLength={1} testID="produto-politica_preco" />
                </View>
              </View>
              <Chk form={f.form} setField={f.setField} campo="aceita_desconto" label="Aceita Desconto" />

              <Text style={styles.sectionTitle}>Comissões</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="comissao" label="Comissão" narrow />
                <Num form={f.form} setField={f.setField} campo="comissao_e" label="Comissão Executor" narrow />
                <Num form={f.form} setField={f.setField} campo="comissao_a" label="Comissão Atendente" narrow />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="valor_comissao" label="Valor Comissão" />
                <Num form={f.form} setField={f.setField} campo="Valor_Comissão_E" label="Valor Comissão Executor" />
                <Num form={f.form} setField={f.setField} campo="Valor_Comissão_A" label="Valor Comissão Atendente" />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="valor_desc_base_comissao" label="Desc. Base Comissão" />
                <Num form={f.form} setField={f.setField} campo="valor_desc_base_comissao_e" label="Desc. Base Com. Executor" />
                <Num form={f.form} setField={f.setField} campo="valor_desc_base_comissao_a" label="Desc. Base Com. Atendente" />
              </View>
              <Chk form={f.form} setField={f.setField} campo="paga_comissao" label="Paga Comissão" />
            </View>
          ) : null}

          {tab === "fiscal" ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Classificações Fiscais</Text>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="codigo_mercosul" label="NCM" />
                <Txt form={f.form} setField={f.setField} campo="codigo_cest" label="CEST" />
                <Txt form={f.form} setField={f.setField} campo="BENEFICIO_FISCAL" label="Benefício Fiscal" />
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Origem</Text>
                  <SelectField value={String(f.form.origem || "0")} onChange={(v) => f.setField("origem", String(v))} options={ORIGEM_OPTS} testID="produto-origem" />
                </View>
                <Txt form={f.form} setField={f.setField} campo="cod_icms" label="Código ICMS" />
                <Num form={f.form} setField={f.setField} campo="perc_mva" label="% MVA" narrow />
                <Num form={f.form} setField={f.setField} campo="valor_substituicao" label="Valor Subst. Tributária" />
              </View>

              <Text style={styles.sectionTitle}>Impostos (PIS, Cofins, Frete, IPI)</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="perc_ipi" label="% IPI" narrow />
                <Num form={f.form} setField={f.setField} campo="valor_ipi" label="Valor IPI" narrow />
                <Txt form={f.form} setField={f.setField} campo="cst_ipi_entrada" label="CST IPI Entrada" />
                <Txt form={f.form} setField={f.setField} campo="cst_ipi_saida" label="CST IPI Saída" />
                <Txt form={f.form} setField={f.setField} campo="ENQUADRAMENTO_IPI" label="Enquadramento IPI" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="cod_grupo_pis_cofins" label="Grupo PIS/COFINS" />
                <Num form={f.form} setField={f.setField} campo="perc_valor_pis" label="% PIS" narrow />
                <Num form={f.form} setField={f.setField} campo="perc_valor_cofins" label="% COFINS" narrow />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="percent_frete" label="% Frete" narrow />
                <Num form={f.form} setField={f.setField} campo="valor_frete" label="Valor Frete" narrow />
                <Num form={f.form} setField={f.setField} campo="outros_trib_federais" label="Outros Tributos Federais" />
                <Num form={f.form} setField={f.setField} campo="IBPT_FEDERAIS" label="IBPT Federais" />
                <Num form={f.form} setField={f.setField} campo="IBPT_ESTADUAIS" label="IBPT Estaduais" />
              </View>

              <ProtocoloStSection protocoloSt={f.protocoloSt} setProtocoloSt={f.setProtocoloSt} />
              <XmlVinculosSection xmlVinculos={f.xmlVinculos} setXmlVinculos={f.setXmlVinculos} />
            </View>
          ) : null}

          {tab === "secundarios" ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Unidades e Dimensões</Text>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="unidade_medida" label="Unidade de Medida" />
                <Num form={f.form} setField={f.setField} campo="comprimento" label="Comprimento" narrow />
                <Num form={f.form} setField={f.setField} campo="largura" label="Largura" narrow />
                <Num form={f.form} setField={f.setField} campo="altura" label="Altura" narrow />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="peso_liquido" label="Peso Líquido" narrow />
                <Num form={f.form} setField={f.setField} campo="peso_bruto" label="Peso Bruto" narrow />
                <Chk form={f.form} setField={f.setField} campo="peso_variado" label="Peso Variado" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="un_compra" label="Unidade Compra" />
                <Num form={f.form} setField={f.setField} campo="qtd_un_compra" label="Qtd Un. Compra" narrow />
                <Txt form={f.form} setField={f.setField} campo="un_embarque" label="Unidade Embarque" />
                <Num form={f.form} setField={f.setField} campo="qtd_un_embarque" label="Qtd Un. Embarque" narrow />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="un_fracao" label="Un. Fração Venda" />
                <Num form={f.form} setField={f.setField} campo="QTD_UN_VENDA" label="Qtd Unid. Venda" narrow />
                <Num form={f.form} setField={f.setField} campo="prazo_entrega" label="Prazo Entrega" narrow />
                <Num form={f.form} setField={f.setField} campo="prazo_fornecedor" label="Prazo Fornecedor" narrow />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="prazo_garantia" label="Prazo Garantia" narrow />
                <Num form={f.form} setField={f.setField} campo="tipo_garantia" label="Tipo Garantia" narrow />
                <Chk form={f.form} setField={f.setField} campo="controla_num_serie" label="Controla Número de Série" />
              </View>

              <Text style={styles.sectionTitle}>Estoque</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="estoque_minimo" label="Estoque Mínimo" narrow />
                <Num form={f.form} setField={f.setField} campo="estoque_maximo" label="Estoque Máximo" narrow />
                <Num form={f.form} setField={f.setField} campo="estoque_ressuprimento" label="Ressuprimento" narrow />
              </View>

              <Text style={styles.sectionTitle}>Localização / Categorias</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="area" label="Área" narrow />
                <Txt form={f.form} setField={f.setField} campo="prateleira" label="Prateleira" />
                <Num form={f.form} setField={f.setField} campo="escaninho" label="Escaninho" narrow />
                <Num form={f.form} setField={f.setField} campo="tipo" label="Tipo" narrow />
                <Num form={f.form} setField={f.setField} campo="tipo_peca" label="Tipo Peça" narrow />
              </View>

              <Text style={styles.sectionTitle}>Custos e Margens</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="custo_inventario" label="Custo Inventário" />
                <Num form={f.form} setField={f.setField} campo="custo_reposicao" label="Custo Reposição" />
                <Num form={f.form} setField={f.setField} campo="desconto_compra" label="Desconto Compra" />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="margem_lucro" label="Margem Real de Venda" />
                <Num form={f.form} setField={f.setField} campo="margem_tabela" label="Margem Real de Tabela" />
                <Txt form={f.form} setField={f.setField} campo="indice_preco" label="Índice de Preço" />
              </View>

              <Text style={styles.sectionTitle}>Pontuação</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="pontuacao_a" label="Atendente" narrow />
                <Num form={f.form} setField={f.setField} campo="pontuacao_e" label="Executor" narrow />
                <Num form={f.form} setField={f.setField} campo="pontuacao_v" label="Vendedor" narrow />
              </View>
            </View>
          ) : null}

          {tab === "grade" ? (
            <View style={styles.card}>
              <Text style={styles.sectionHint}>
                Cada combinação de cor/tamanho gera um produto-filho de verdade, vinculado a este produto principal.
              </Text>
              {f.grade.length === 0 ? (
                <Text style={styles.empty}>Nenhum item de grade gerado ainda.</Text>
              ) : (
                f.grade.map((g) => (
                  <View key={g.equivalente} style={styles.gridRow} testID={`produto-grade-${g.equivalente}`}>
                    <Text style={styles.gridRowText}>{g.equivalente} — {g.descricao} (Cor {g.cor}, Tam. {g.tamanho})</Text>
                  </View>
                ))
              )}
              {f.editingCodigo && can("PRODUTO_COMP.GRADE") ? (
                <Pressable onPress={() => setGradeModal(true)} style={[styles.secondaryBtn, { marginTop: spacing.md }]} testID="produto-btn-inclui-grade">
                  <Ionicons name="add-circle-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.secondaryBtnText}>Inclusão de Itens na Grade</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          {tab === "similares" ? (
            <View style={styles.card}>
              <SimilaresSection similares={f.similares} setSimilares={f.setSimilares} />
              <SecundariosSection secundarios={f.secundarios} setSecundarios={f.setSecundarios} />
            </View>
          ) : null}

          {tab === "livro" ? (
            <View style={styles.card}>
              <Text style={styles.sectionHint}>
                Campos específicos do ramo livraria/editora — reaproveitam Fornecedor (Editora), Tipo Peça e Desconto Compra/Venda já definidos nas outras abas.
              </Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="autor" label="Autor (código)" narrow />
                <Num form={f.form} setField={f.setField} campo="serie" label="Série (código)" narrow />
              </View>
              <Text style={styles.label}>Sinopse</Text>
              <TextInput value={String(f.form.sinopse || "")} onChangeText={(v) => f.setField("sinopse", v)} style={[styles.input, { minHeight: 90 }]} multiline testID="produto-sinopse" />
              <View style={styles.checkRowGroup}>
                <Chk form={f.form} setField={f.setField} campo="lancamento" label="Lançamento" />
                <Chk form={f.form} setField={f.setField} campo="esgotado" label="Esgotado" />
              </View>
            </View>
          ) : null}

          {tab === "anexos" ? (
            <View style={styles.card}>
              {f.conn && f.editingCodigo ? (
                <GestorDocumentosSection api={f.conn.api} servidor={f.conn.servidor} banco={f.conn.banco} codGrupo={GESTOR_DOC_GRUPO_PRODUTO} codigoEntidade={f.editingCodigo} />
              ) : (
                <Text style={styles.empty}>Grave o produto para anexar documentos.</Text>
              )}
            </View>
          ) : null}
        </View>
      </ScrollView>

      {f.conn && f.editingCodigo ? (
        <FornecedorModal visible={fornecedorModal} onClose={() => setFornecedorModal(false)} fornecedores={f.fornecedores} setFornecedores={f.setFornecedores} />
      ) : null}
      {f.conn && f.editingCodigo ? (
        <FotografiaModal
          visible={fotografiaModal}
          onClose={() => setFotografiaModal(false)}
          conn={f.conn}
          codigoInt={f.editingCodigo}
          gradeOn={gradeOn}
          canEnviarSite={can("PRODUTO_COMP.ENVIAR_SITE")}
          onEnviarSite={f.enviarSite}
        />
      ) : null}
      {f.editingCodigo ? (
        <GradeIncluiModal visible={gradeModal} onClose={() => setGradeModal(false)} onConfirm={f.criarItensGrade} />
      ) : null}
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Similares / Secundários (aba "Similares e Equivalentes") — duas seções
// independentes no legado (Pecaseq/pecas_secundaria), replace-all no save.
// ---------------------------------------------------------------------------

function SimilaresSection({ similares, setSimilares }: { similares: SimilarItem[]; setSimilares: (v: SimilarItem[]) => void }) {
  const [codigo, setCodigo] = useState("");
  return (
    <View>
      <Text style={styles.sectionTitle}>Produtos Similares</Text>
      {similares.map((s, i) => (
        <View key={`${s.equivalente}-${i}`} style={styles.gridRow} testID={`produto-similar-${s.equivalente}`}>
          <Text style={styles.gridRowText}>{s.equivalente} {s.descricao ? `— ${s.descricao}` : ""}</Text>
          <Pressable onPress={() => setSimilares(similares.filter((_, idx) => idx !== i))} hitSlop={8}>
            <Ionicons name="trash-outline" size={18} color={colors.error} />
          </Pressable>
        </View>
      ))}
      <View style={styles.rowFields}>
        <Txt form={{ codigo }} setField={(_, v) => setCodigo(String(v))} campo="codigo" label="Código de Fábrica/Referência" />
        <Pressable
          onPress={() => { if (codigo.trim()) { setSimilares([...similares, { equivalente: codigo.trim() }]); setCodigo(""); } }}
          style={[styles.secondaryBtn, { alignSelf: "flex-end" }]}
          testID="produto-similar-vincular"
        >
          <Text style={styles.secondaryBtnText}>Vincular</Text>
        </Pressable>
      </View>
    </View>
  );
}

function SecundariosSection({ secundarios, setSecundarios }: { secundarios: SecundarioItem[]; setSecundarios: (v: SecundarioItem[]) => void }) {
  const [codigo, setCodigo] = useState("");
  return (
    <View>
      <Text style={styles.sectionTitle}>Produtos Secundários</Text>
      {secundarios.map((s, i) => (
        <View key={`${s.peca_secundaria}-${i}`} style={styles.gridRow} testID={`produto-secundario-${s.peca_secundaria}`}>
          <Text style={styles.gridRowText}>{s.peca_secundaria} {s.descricao ? `— ${s.descricao}` : ""}</Text>
          <Pressable onPress={() => setSecundarios(secundarios.filter((_, idx) => idx !== i))} hitSlop={8}>
            <Ionicons name="trash-outline" size={18} color={colors.error} />
          </Pressable>
        </View>
      ))}
      <View style={styles.rowFields}>
        <Txt form={{ codigo }} setField={(_, v) => setCodigo(String(v))} campo="codigo" label="Código de Fábrica/Referência" />
        <Pressable
          onPress={() => { if (codigo.trim()) { setSecundarios([...secundarios, { peca_secundaria: codigo.trim() }]); setCodigo(""); } }}
          style={[styles.secondaryBtn, { alignSelf: "flex-end" }]}
          testID="produto-secundario-vincular"
        >
          <Text style={styles.secondaryBtnText}>Vincular</Text>
        </Pressable>
      </View>
    </View>
  );
}

function XmlVinculosSection({ xmlVinculos, setXmlVinculos }: { xmlVinculos: XmlVinculoItem[]; setXmlVinculos: (v: XmlVinculoItem[]) => void }) {
  const [codXml, setCodXml] = useState("");
  return (
    <View>
      <Text style={styles.sectionTitle}>Vínculos XML do Fornecedor</Text>
      {xmlVinculos.map((x, i) => (
        <View key={`${x.codigo_xml}-${i}`} style={styles.gridRow} testID={`produto-xml-${i}`}>
          <Text style={styles.gridRowText}>{x.codigo_xml} {x.nome ? `— ${x.nome}` : ""}</Text>
          <Pressable onPress={() => setXmlVinculos(xmlVinculos.filter((_, idx) => idx !== i))} hitSlop={8}>
            <Ionicons name="trash-outline" size={18} color={colors.error} />
          </Pressable>
        </View>
      ))}
      <View style={styles.rowFields}>
        <Txt form={{ codXml }} setField={(_, v) => setCodXml(String(v))} campo="codXml" label="Código XML" />
        <Pressable
          onPress={() => { if (codXml.trim()) { setXmlVinculos([...xmlVinculos, { codigo_xml: codXml.trim(), fornecedor_xml: null }]); setCodXml(""); } }}
          style={[styles.secondaryBtn, { alignSelf: "flex-end" }]}
          testID="produto-xml-vincular"
        >
          <Text style={styles.secondaryBtnText}>Vincular</Text>
        </Pressable>
      </View>
    </View>
  );
}

const UF_LIST = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];

function ProtocoloStSection({ protocoloSt, setProtocoloSt }: { protocoloSt: string[]; setProtocoloSt: (v: string[]) => void }) {
  return (
    <View>
      <Text style={styles.sectionTitle}>Protocolo ST por UF</Text>
      <View style={styles.chipsRow}>
        {UF_LIST.map((uf) => {
          const sel = protocoloSt.includes(uf);
          return (
            <Pressable
              key={uf}
              onPress={() => setProtocoloSt(sel ? protocoloSt.filter((u) => u !== uf) : [...protocoloSt, uf])}
              style={[styles.chip, sel && styles.chipSel]}
              testID={`produto-protocolo-st-${uf}`}
            >
              <Text style={[styles.chipText, sel && { color: colors.onBrandPrimary }]}>{uf}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Fornecedores — modal (Command23_Click no legado, tabela pecas_fornecedor).
// ---------------------------------------------------------------------------

function FornecedorModal({ visible, onClose, fornecedores, setFornecedores }: {
  visible: boolean; onClose: () => void; fornecedores: FornecedorItem[]; setFornecedores: (v: FornecedorItem[]) => void;
}) {
  const [codigo, setCodigo] = useState("");
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Fornecedores</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          <ScrollView style={{ maxHeight: 360 }}>
            {fornecedores.map((f, i) => (
              <View key={`${f.fornecedor}-${i}`} style={styles.gridRow} testID={`produto-fornecedor-${f.fornecedor}`}>
                <Text style={styles.gridRowText}>{f.fornecedor} {f.nome ? `— ${f.nome}` : ""}</Text>
                <Pressable onPress={() => setFornecedores(fornecedores.filter((_, idx) => idx !== i))} hitSlop={8}>
                  <Ionicons name="trash-outline" size={18} color={colors.error} />
                </Pressable>
              </View>
            ))}
            {fornecedores.length === 0 ? <Text style={styles.empty}>Nenhum fornecedor vinculado.</Text> : null}
          </ScrollView>
          <View style={styles.rowFields}>
            <View style={styles.colFlex}>
              <Text style={styles.label}>Código do Fornecedor</Text>
              <TextInput value={codigo} onChangeText={(v) => setCodigo(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" testID="produto-fornecedor-codigo" />
            </View>
            <Pressable
              onPress={() => { const n = parseInt(codigo, 10); if (n) { setFornecedores([...fornecedores, { fornecedor: n, sequencia: fornecedores.length + 1 }]); setCodigo(""); } }}
              style={[styles.secondaryBtn, { alignSelf: "flex-end" }]}
              testID="produto-fornecedor-vincular"
            >
              <Text style={styles.secondaryBtnText}>Vincular</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// ---------------------------------------------------------------------------
// Fotografia — modal (Command15_Click no legado). Módulo Grade desligado:
// só o Gestor de Documentos (Imagens). Módulo Grade ligado: FrmAsoFot
// equivalente — associar cor por foto + enviar/atualizar na Tray (ver
// backend/services/tray_service.py, "Aviso de teste" na docstring).
// ---------------------------------------------------------------------------

function FotografiaModal({ visible, onClose, conn, codigoInt, gradeOn, canEnviarSite, onEnviarSite }: {
  visible: boolean; onClose: () => void; conn: { servidor: string; banco: string; api: string };
  codigoInt: string; gradeOn: boolean; canEnviarSite: boolean; onEnviarSite: (idTray?: number) => Promise<boolean>;
}) {
  const [enviando, setEnviando] = useState(false);
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebCompact, { maxHeight: "85%" }]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Fotografia</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          <ScrollView style={{ maxHeight: 480 }}>
            <GestorDocumentosSection api={conn.api} servidor={conn.servidor} banco={conn.banco} codGrupo={GESTOR_DOC_GRUPO_PRODUTO} codigoEntidade={codigoInt} />
            {gradeOn ? (
              <Text style={styles.sectionHint}>
                Depois de anexar as fotos acima, use "Cadastrar/Atualizar no Site" para publicar na Tray — a cor de
                cada foto é ajustada diretamente no Gestor de Documentos (campo "Cor").
              </Text>
            ) : null}
            {canEnviarSite ? (
              <Pressable
                onPress={async () => { setEnviando(true); await onEnviarSite(); setEnviando(false); }}
                disabled={enviando}
                style={[styles.secondaryBtn, { marginTop: spacing.md, opacity: enviando ? 0.6 : 1 }]}
                testID="produto-btn-enviar-site"
              >
                {enviando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="cloud-upload-outline" size={16} color={colors.brandPrimary} />
                    <Text style={styles.secondaryBtnText}>Cadastrar/Atualizar Produto no Site</Text>
                  </>
                )}
              </Pressable>
            ) : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// ---------------------------------------------------------------------------
// Grade — modal "Inclusão de Itens na Grade" (Command12 no legado).
// ---------------------------------------------------------------------------

function GradeIncluiModal({ visible, onClose, onConfirm }: {
  visible: boolean; onClose: () => void; onConfirm: (combinacoes: { cor: string; tamanho: string }[]) => Promise<boolean>;
}) {
  const [cor, setCor] = useState("");
  const [tamanho, setTamanho] = useState("");
  const [combinacoes, setCombinacoes] = useState<{ cor: string; tamanho: string }[]>([]);
  const [saving, setSaving] = useState(false);

  const add = () => {
    if (!cor.trim()) return;
    setCombinacoes([...combinacoes, { cor: cor.trim(), tamanho: tamanho.trim() }]);
    setCor(""); setTamanho("");
  };

  const confirm = async () => {
    if (combinacoes.length === 0) return;
    setSaving(true);
    const ok = await onConfirm(combinacoes);
    setSaving(false);
    if (ok) { setCombinacoes([]); onClose(); }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Inclusão de Itens na Grade</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          {combinacoes.map((c, i) => (
            <View key={i} style={styles.gridRow}>
              <Text style={styles.gridRowText}>Cor {c.cor} — Tamanho {c.tamanho || "—"}</Text>
              <Pressable onPress={() => setCombinacoes(combinacoes.filter((_, idx) => idx !== i))} hitSlop={8}>
                <Ionicons name="trash-outline" size={18} color={colors.error} />
              </Pressable>
            </View>
          ))}
          <View style={styles.rowFields}>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Cor (código)</Text>
              <TextInput value={cor} onChangeText={setCor} style={styles.input} testID="produto-grade-cor" />
            </View>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Tamanho</Text>
              <TextInput value={tamanho} onChangeText={setTamanho} style={styles.input} testID="produto-grade-tamanho" />
            </View>
            <Pressable onPress={add} style={[styles.secondaryBtn, { alignSelf: "flex-end" }]} testID="produto-grade-add">
              <Text style={styles.secondaryBtnText}>Adicionar</Text>
            </Pressable>
          </View>
          <Pressable onPress={confirm} disabled={saving || combinacoes.length === 0} style={[styles.saveBtnModal, (saving || combinacoes.length === 0) && { opacity: 0.6 }]} testID="produto-grade-gravar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center",
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  tabBar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.lg },
  tabBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabLabel: { fontSize: 13, fontWeight: "500", color: colors.muted },
  tabLabelSel: { color: colors.onBrandPrimary },
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: spacing.xs },
  sectionHint: { fontSize: 11, color: colors.muted, marginTop: spacing.md, fontStyle: "italic" },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceTertiary, color: colors.muted },
  readonlyValue: { fontSize: 14, color: colors.onSurface, paddingVertical: 11 },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 140 },
  switchRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md },
  switchLabel: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  checkRowGroup: { flexDirection: "row", gap: spacing.lg, marginTop: spacing.md, flexWrap: "wrap" },
  toolbarRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, flexWrap: "wrap" },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.surface,
  },
  dangerBtn: { borderColor: colors.error },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "500", fontSize: 13 },
  gridRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  gridRowText: { fontSize: 13, color: colors.onSurface, flex: 1 },
  empty: { fontSize: 12, color: colors.muted, textAlign: "center", paddingVertical: spacing.md },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: spacing.xs },
  chip: { paddingHorizontal: spacing.sm, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, color: colors.onSurface, fontWeight: "500" },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modalBgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  modalCard: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
  },
  modalCardWebCompact: {
    width: "100%", maxWidth: 560, alignSelf: "center",
    borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
  },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  saveBtnModal: {
    marginTop: spacing.md, backgroundColor: colors.brandPrimary, borderRadius: radius.md,
    paddingVertical: 12, alignItems: "center",
  },
});

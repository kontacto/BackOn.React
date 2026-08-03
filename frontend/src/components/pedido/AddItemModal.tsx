// Modal "Adicionar Item": busca de produto/serviço + formulário de confirmação.
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
// Ícone de garçom/prato servido pra Taxa de Serviço — ver comentário em
// ItemList.tsx (MaterialCommunityIcons não tem wrapper Windows ainda,
// inofensivo enquanto a plataforma Windows estiver pausada).
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL, parseNum, fmtNum, calcDescUnit } from "@/src/utils/format";
import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { apiGet } from "@/src/utils/api";
import { styles } from "./styles";
import { ProdutoServico, ModificadorCategoriaVenda } from "./types";
import { UsePedidoItens } from "./usePedidoItens";

const isWeb = Platform.OS === "web";

type Props = {
  it: UsePedidoItens;
  onOpenProdutos: () => void;
  // Tela dona da permissão — "PEDIDO" (rápido, default) ou "PEDIDO_COMP".
  tela?: string;
};

export default function AddItemModal({ it, onOpenProdutos, tela = "PEDIDO" }: Props) {
  const { selProd } = it;
  const { can } = usePermissions();
  const fb = useFeedback();
  const canDesc = can(`${tela}.DESC_ITEM`);
  // Seletor de Modificadores (Fase 2) — por pedido explícito do usuário
  // (2026-07-23: "faça somente em Pedidos Bar. Depois faremos nas outras
  // pré-venda"), só ativo no Pedido Bar por enquanto; Pedido Geral/O.S.
  // ficam com o comportamento de antes, sem nenhuma chamada extra à API.
  const modificadoresOn = tela === "PEDIDO";
  const [modCategorias, setModCategorias] = useState<ModificadorCategoriaVenda[]>([]);
  const [modLoading, setModLoading] = useState(false);
  const [modSelecionados, setModSelecionados] = useState<Map<number, Set<number>>>(new Map());

  const buscarModificadores = useCallback(async (p: ProdutoServico): Promise<ModificadorCategoriaVenda[]> => {
    if (!modificadoresOn || !it.conn) return [];
    try {
      const j = await apiGet(it.conn, `/api/modificadores/por-item/${p.tipo}/${encodeURIComponent(p.codigo)}/completo`);
      return j?.success ? (j.items || []) : [];
    } catch {
      return [];
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modificadoresOn, it.conn]);

  // Recarrega os modificadores do produto sempre que a tela "Confirmar Item"
  // abre pra um produto novo — reseta a seleção anterior.
  useEffect(() => {
    setModSelecionados(new Map());
    if (!modificadoresOn || !selProd) { setModCategorias([]); return; }
    let cancelado = false;
    setModLoading(true);
    buscarModificadores(selProd).then((cats) => {
      if (!cancelado) setModCategorias(cats);
    }).finally(() => { if (!cancelado) setModLoading(false); });
    return () => { cancelado = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selProd, modificadoresOn]);

  const toggleModificador = useCallback((cat: ModificadorCategoriaVenda, modCodigo: number) => {
    setModSelecionados((prev) => {
      const next = new Map(prev);
      const atual = new Set(next.get(cat.codigo) || []);
      if (cat.selecao_multipla) {
        if (atual.has(modCodigo)) atual.delete(modCodigo); else atual.add(modCodigo);
      } else if (atual.has(modCodigo)) {
        if (!cat.obrigatorio) atual.clear();
      } else {
        atual.clear();
        atual.add(modCodigo);
      }
      next.set(cat.codigo, atual);
      return next;
    });
  }, []);

  // Soma dos acréscimos/descontos dos modificadores selecionados (valor
  // fixo em R$ por unidade, mesma convenção dos campos manuais "Acrésc.
  // R$"/"Desc. R$" já existentes) + texto com os nomes escolhidos, pra
  // anexar no Complemento do item — "por enquanto" (pedido explícito do
  // usuário) é só isso que sai impresso como Obs do item do Bar.
  let modAcrescimoTotal = 0;
  let modDescontoTotal = 0;
  const modNomesEscolhidos: string[] = [];
  for (const cat of modCategorias) {
    const sel = modSelecionados.get(cat.codigo);
    if (!sel || sel.size === 0) continue;
    for (const mod of cat.modificadores) {
      if (!sel.has(mod.codigo)) continue;
      modAcrescimoTotal += mod.acrescimo || 0;
      modDescontoTotal += mod.desconto || 0;
      modNomesEscolhidos.push(mod.nome);
    }
  }
  const modNomesTexto = modNomesEscolhidos.join(", ");
  const categoriasObrigatoriasFaltando = modCategorias.filter(
    (cat) => cat.obrigatorio && (modSelecionados.get(cat.codigo)?.size || 0) === 0,
  );

  const handleConfirmar = useCallback(() => {
    if (categoriasObrigatoriasFaltando.length > 0) {
      fb.showError(
        `Selecione uma opção em: ${categoriasObrigatoriasFaltando.map((c) => c.nome).join(", ")}.`,
      );
      return;
    }
    it.handleAddItem({
      acrescimoExtra: modAcrescimoTotal,
      descontoExtra: modDescontoTotal,
      complementoExtra: modNomesTexto || undefined,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoriasObrigatoriasFaltando, modAcrescimoTotal, modDescontoTotal, modNomesTexto, it.handleAddItem]);
  // Pedido Geral tem comportamento DIFERENTE do Bar (pedido explícito do
  // usuário, 2026-07-20: "a busca do pedido geral não precisa trazer os
  // itens do pedido, como acontece no bar") — sem a lista de conveniência
  // "repetir item já lançado", já que o Geral não é um fluxo de
  // atendimento rápido tipo mesa/comanda.
  const isPedidoComp = tela === "PEDIDO_COMP";

  // Número de série (Fase B, só Pedido Geral — `PECAS.controla_num_serie`,
  // padrão `CmbNDS`/`FrmNDS` do legado). Ver PENDENCIAS.md > "Transações" >
  // "Pedido Geral — Fase B: número de série".
  const exigeNumSerie = isPedidoComp && !!selProd?.controla_num_serie;
  const [numSerieOpts, setNumSerieOpts] = useState<{ codigo: number; num_serie: string; detalhes: string }[]>([]);
  const [numSerieLoading, setNumSerieLoading] = useState(false);

  // Metro Quadrado (Fase B, só Pedido Geral — `pecas.uni` M2/ML/M3). Ver
  // PENDENCIAS.md > "Transações" > "Pedido Geral — Metro Quadrado".
  const exigeM2 = isPedidoComp && it.ehProdutoM2(selProd);

  useEffect(() => {
    if (!exigeNumSerie || !it.conn || !selProd) { setNumSerieOpts([]); return; }
    let cancelado = false;
    setNumSerieLoading(true);
    apiGet(it.conn, "/api/tabelas/num-serie", { codigo_int: selProd.codigo })
      .then((j) => {
        if (cancelado) return;
        const disponiveis = (j?.success ? (j.items || []) : []).filter((r: { disponivel: boolean }) => r.disponivel);
        setNumSerieOpts(disponiveis);
      })
      .finally(() => { if (!cancelado) setNumSerieLoading(false); });
    return () => { cancelado = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exigeNumSerie, selProd?.codigo]);
  // Busca só dispara no Enter no Pedido Geral (pedido explícito do
  // usuário, 2026-07-20: "na busca do pedido geral só efetuar a busca
  // depois do enter") — diferente do Bar, que busca enquanto digita com
  // debounce (`usePedidoItens`'s `buscaProdutoSoEnter`). `searchTriggered`
  // controla só a exibição/mensagem aqui; quem decide se busca de fato é
  // o hook (`buscarProdutos`, chamada no onSubmitEditing abaixo).
  const [searchTriggered, setSearchTriggered] = useState(false);
  const digitou = it.prodTerm.trim().length > 0;
  // Com o campo de busca vazio, a lista padrão é a dos itens já lançados
  // no pedido — só troca pra resultado de busca quando o usuário digita
  // (Bar) ou aperta Enter (Geral). Não mostra a lista de conveniência no
  // Pedido Geral (ver comentário acima).
  const buscando = isPedidoComp ? (digitou && searchTriggered) : digitou;
  const listaExibida = buscando ? it.prodResults : (isPedidoComp ? [] : it.pedidoProdutos);

  // Pedido sem nenhum item ainda -> não há nada útil pra "repetir" na lista
  // padrão do modal (ver comentário acima), então pula direto pra lista
  // completa de produtos em vez de abrir o modal só pra mostrar o estado
  // vazio + botão "Abrir lista completa de produtos". Não se aplica ao
  // Pedido Geral, que nunca mostra essa lista de conveniência mesmo — a
  // busca fica sempre disponível no próprio modal.
  useEffect(() => {
    if (!isPedidoComp && it.addOpen && !selProd && it.pedidoProdutos.length === 0 && !it.prodTerm.trim()) {
      it.setAddOpen(false);
      onOpenProdutos();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [it.addOpen]);

  // Modal não desmonta ao fechar (`Modal` do RN só esconde) — reseta o
  // estado "já buscou" a cada reabertura, senão reaparece com o resultado
  // da busca anterior antes do usuário digitar de novo.
  useEffect(() => {
    if (it.addOpen) setSearchTriggered(false);
  }, [it.addOpen]);

  return (
    <Modal visible={it.addOpen} transparent animationType="slide" onRequestClose={() => it.setAddOpen(false)}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => it.setAddOpen(false)}>
        {/* Busca/lista de produtos usa o tier de seleção (560px, precisa de
            espaço pra lista); confirmar o item selecionado (qtd/valor/
            desconto) usa o tier estreito de confirmação pontual (420px). */}
        <Pressable
          style={[styles.modalCard, isWeb && (selProd ? styles.modalCardWebCompactNarrow : styles.modalCardWebCompact)]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{selProd ? "Confirmar Item" : "Adicionar Item"}</Text>
            <Pressable onPress={() => it.setAddOpen(false)} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          {!selProd ? (
            <>
              <View style={styles.searchWrap}>
                <Ionicons name="search" size={16} color={colors.muted} />
                <TextInput
                  value={it.prodTerm}
                  onChangeText={(v) => { it.setProdTerm(v); if (isPedidoComp) setSearchTriggered(false); }}
                  onSubmitEditing={isPedidoComp ? async () => {
                    const encontrados = await it.buscarProdutos(it.prodTerm);
                    setSearchTriggered(true);
                    // 1 resultado só -> pula direto pra "Confirmar Item",
                    // sem precisar tocar no registro (pedido explícito do
                    // usuário, 2026-07-20 — mesmo princípio já usado no
                    // campo Cliente: 1 resultado carrega direto).
                    if (encontrados.length === 1) it.pickProduto(encontrados[0]);
                  } : undefined}
                  returnKeyType={isPedidoComp ? "search" : undefined}
                  placeholder="Buscar produto ou serviço…"
                  placeholderTextColor={colors.muted}
                  style={styles.searchInput}
                  autoFocus
                  testID="pedido-form-prod-search"
                />
              </View>
              {!isPedidoComp && !buscando && it.pedidoProdutos.length > 0 ? (
                <Text style={styles.resultSub}>Itens do pedido — toque em + pra repetir, ou busque outro produto</Text>
              ) : null}
              {it.prodLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
              <ScrollView style={{ maxHeight: 360 }} keyboardShouldPersistTaps="handled">
                {listaExibida.map((p: ProdutoServico) => (
                  <Pressable
                    key={`${p.tipo}-${p.codigo}`}
                    onPress={() => it.pickProduto(p)}
                    style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                    testID={`pedido-form-prod-${p.codigo}`}
                  >
                    <View
                      style={[
                        styles.itemTipo,
                        p.codigo === "S002" ? styles.tagTaxaServico : p.tipo === "P" ? styles.tagProd : styles.tagServ,
                      ]}
                    >
                      {p.codigo === "S002" ? (
                        <MaterialCommunityIcons name="room-service" size={16} color={colors.success} />
                      ) : (
                        <Ionicons
                          name={p.tipo === "P" ? "cube" : "construct"}
                          size={16}
                          color={p.tipo === "P" ? colors.brandPrimary : colors.warning}
                        />
                      )}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.resultNome} numberOfLines={1}>{p.descricao}</Text>
                      <Text style={styles.resultSub} numberOfLines={1}>
                        #{p.codigo}{p.cod_fab ? ` · ${p.cod_fab}` : ""}
                      </Text>
                    </View>
                    <Text style={styles.itemTotal}>{formatBRL(p.valor)}</Text>
                    <TouchableOpacity
                      onPress={async (e) => {
                        e.stopPropagation();
                        // Produto com modificador associado não pode pular
                        // direto pro "+" rápido — precisa passar pela tela
                        // "Confirmar Item" pra escolher o modificador antes
                        // (mesmo princípio de "Ponto da Carne" precisar ser
                        // escolhido antes de lançar o item).
                        if (modificadoresOn) {
                          const cats = await buscarModificadores(p);
                          if (cats.length > 0) { it.pickProduto(p); return; }
                        }
                        // Produto com número de série sempre precisa passar
                        // pela tela "Confirmar Item" pra escolher qual série
                        // — não pode pular direto pro "+" rápido.
                        if (isPedidoComp && p.controla_num_serie) { it.pickProduto(p); return; }
                        // Idem pra produto m² — precisa do tipo de preço e
                        // das dimensões antes de ter um preço pra lançar.
                        if (isPedidoComp && it.ehProdutoM2(p)) { it.pickProduto(p); return; }
                        it.quickAddItem(p);
                      }}
                      disabled={it.addSaving}
                      activeOpacity={0.7}
                      hitSlop={8}
                      style={[styles.quickAddBtn, it.addSaving && { opacity: 0.5 }]}
                      testID={`pedido-form-prod-quickadd-${p.codigo}`}
                    >
                      <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                    </TouchableOpacity>
                  </Pressable>
                ))}
                {!it.prodLoading && listaExibida.length === 0 ? (
                  <Text style={styles.emptyText}>
                    {isPedidoComp
                      ? (searchTriggered
                          ? "Nenhum produto/serviço encontrado."
                          : (digitou ? "Aperte Enter para buscar." : "Digite e aperte Enter para buscar um produto ou serviço."))
                      : (buscando
                          ? "Nenhum produto/serviço encontrado."
                          : "Nenhum item no pedido ainda — busque um produto ou serviço.")}
                  </Text>
                ) : null}
              </ScrollView>
              <Pressable
                onPress={onOpenProdutos}
                style={({ pressed }) => [styles.fullListBtn, pressed && { opacity: 0.8 }]}
                testID="pedido-form-open-produtos"
              >
                <Ionicons name="grid-outline" size={16} color={colors.brandPrimary} />
                <Text style={styles.fullListText}>Abrir lista completa de produtos</Text>
              </Pressable>
            </>
          ) : (
            <ScrollView style={{ maxHeight: 520 }} keyboardShouldPersistTaps="handled">
              <View style={{ gap: spacing.sm }}>
                <View style={styles.selProdBox}>
                  <Text style={styles.itemDesc} numberOfLines={2}>{selProd.descricao}</Text>
                  <Text style={styles.resultSub}>#{selProd.codigo}{selProd.cod_fab ? ` · ${selProd.cod_fab}` : ""}</Text>
                </View>
                {exigeNumSerie ? (
                  <View>
                    <Text style={styles.fieldLabel}>Número de Série *</Text>
                    {numSerieLoading ? (
                      <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 8 }} />
                    ) : numSerieOpts.length === 0 ? (
                      <Text style={[styles.emptyText, { color: colors.error }]}>
                        Nenhum número de série disponível para este produto.
                      </Text>
                    ) : (
                      <View style={{ gap: 4 }}>
                        {numSerieOpts.map((ns) => {
                          const ativo = it.selNumSerie === ns.codigo;
                          return (
                            <Pressable
                              key={ns.codigo}
                              onPress={() => it.setSelNumSerie(ns.codigo)}
                              style={[modStyles.modRow, ativo && { backgroundColor: colors.brandTertiary, borderRadius: radius.sm }]}
                              testID={`pedido-form-numserie-${ns.codigo}`}
                            >
                              <Ionicons
                                name={ativo ? "radio-button-on" : "radio-button-off"}
                                size={18}
                                color={ativo ? colors.brandPrimary : colors.muted}
                              />
                              <Text style={modStyles.modNome}>{ns.num_serie}{ns.detalhes ? ` — ${ns.detalhes}` : ""}</Text>
                            </Pressable>
                          );
                        })}
                      </View>
                    )}
                  </View>
                ) : null}
                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Quantidade</Text>
                    <View style={styles.qtdInputRow}>
                      <TextInput
                        value={it.addQtd}
                        onChangeText={it.setAddQtd}
                        editable={!exigeNumSerie}
                        keyboardType="decimal-pad"
                        style={[styles.input, { flex: 1, minWidth: 0 }, exigeNumSerie && styles.inputDisabled]}
                        testID="pedido-form-add-qtd"
                      />
                      {!exigeNumSerie ? (
                        <TouchableOpacity
                          onPress={() => it.setAddQtd(fmtNum(parseNum(it.addQtd) + 1))}
                          activeOpacity={0.7}
                          style={styles.plusBtn}
                          testID="pedido-form-add-qtd-plus"
                        >
                          <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                        </TouchableOpacity>
                      ) : null}
                    </View>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Valor unitário</Text>
                    <TextInput
                      value={it.addValor}
                      onChangeText={it.setAddValor}
                      editable={!exigeM2}
                      keyboardType="decimal-pad"
                      style={[styles.input, exigeM2 && styles.inputDisabled]}
                      testID="pedido-form-add-valor"
                    />
                  </View>
                </View>
                {it.promoAplicada ? (
                  <View style={promoStyles.badge} testID="pedido-form-add-promocao">
                    <Ionicons name="pricetag-outline" size={13} color={colors.brandPrimary} />
                    <Text style={promoStyles.badgeText}>
                      Promoção aplicada{it.promoAplicada.descricao_promocao ? `: ${it.promoAplicada.descricao_promocao}` : ""}
                    </Text>
                  </View>
                ) : null}
                {exigeM2 ? (
                  <View style={{ gap: spacing.sm }}>
                    <Text style={styles.fieldLabel}>Tipo de Preço</Text>
                    {it.precosM2Loading ? (
                      <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 4 }} />
                    ) : it.precosM2.length === 0 ? (
                      <Text style={[styles.emptyText, { color: colors.error }]}>
                        Nenhum tipo de preço m² cadastrado para este produto.
                      </Text>
                    ) : (
                      <View style={{ gap: 4 }}>
                        {it.precosM2.map((tp) => {
                          const ativo = it.addTipoPrecoM2 === tp.tipo;
                          return (
                            <Pressable
                              key={tp.tipo}
                              onPress={() => it.setAddTipoPrecoM2(tp.tipo)}
                              style={[modStyles.modRow, ativo && { backgroundColor: colors.brandTertiary, borderRadius: radius.sm }]}
                              testID={`pedido-form-tipopreco-m2-${tp.tipo}`}
                            >
                              <Ionicons
                                name={ativo ? "radio-button-on" : "radio-button-off"}
                                size={18}
                                color={ativo ? colors.brandPrimary : colors.muted}
                              />
                              <Text style={modStyles.modNome}>{tp.label}</Text>
                              <Text style={modStyles.modValor}>{formatBRL(tp.preco)}</Text>
                            </Pressable>
                          );
                        })}
                      </View>
                    )}
                    <View style={styles.qtdRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.fieldLabel}>Comprimento (m)</Text>
                        <TextInput
                          value={it.addComprimento}
                          onChangeText={it.setAddComprimento}
                          keyboardType="decimal-pad"
                          placeholder="0,00"
                          placeholderTextColor={colors.muted}
                          style={styles.input}
                          testID="pedido-form-add-comprimento"
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.fieldLabel}>Largura (m)</Text>
                        <TextInput
                          value={it.addLargura}
                          onChangeText={it.setAddLargura}
                          keyboardType="decimal-pad"
                          placeholder="0,00"
                          placeholderTextColor={colors.muted}
                          style={styles.input}
                          testID="pedido-form-add-largura"
                        />
                      </View>
                    </View>
                    {it.vidroControlaCabecaChapa ? (
                      <View style={styles.qtdRow}>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.fieldLabel}>Comprimento de Chapa (m)</Text>
                          <TextInput
                            value={it.addComprimentoChapa}
                            onChangeText={it.setAddComprimentoChapa}
                            keyboardType="decimal-pad"
                            placeholder="opcional"
                            placeholderTextColor={colors.muted}
                            style={styles.input}
                            testID="pedido-form-add-comprimento-chapa"
                          />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.fieldLabel}>Largura de Chapa (m)</Text>
                          <TextInput
                            value={it.addLarguraChapa}
                            onChangeText={it.setAddLarguraChapa}
                            keyboardType="decimal-pad"
                            placeholder="opcional"
                            placeholderTextColor={colors.muted}
                            style={styles.input}
                            testID="pedido-form-add-largura-chapa"
                          />
                        </View>
                      </View>
                    ) : null}
                    {it.previewM2Loading ? (
                      <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 4 }} />
                    ) : it.previewM2 ? (
                      <View style={promoStyles.badge}>
                        <Ionicons name="calculator-outline" size={13} color={colors.brandPrimary} />
                        <Text style={promoStyles.badgeText}>
                          Área calculada: {fmtNum(it.previewM2.area_venda)} m² · Valor unitário: {formatBRL(it.previewM2.valor_unitario)}
                        </Text>
                      </View>
                    ) : null}
                  </View>
                ) : null}
                <View style={styles.qtdRow}>
                  {canDesc ? (
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Desc. %</Text>
                    <TextInput
                      value={it.addDescPct}
                      onChangeText={(v) => { it.setAddDescPct(v); if (parseNum(v) > 0) it.setAddDescRs(""); }}
                      editable={parseNum(it.addDescRs) <= 0}
                      keyboardType="decimal-pad"
                      placeholder="0"
                      placeholderTextColor={colors.muted}
                      style={[styles.input, parseNum(it.addDescRs) > 0 && styles.inputDisabled]}
                      testID="pedido-form-add-descpct"
                    />
                  </View>
                  ) : null}
                  {canDesc ? (
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Desc. R$ (unit.)</Text>
                    <TextInput
                      value={it.addDescRs}
                      onChangeText={(v) => { it.setAddDescRs(v); if (parseNum(v) > 0) it.setAddDescPct(""); }}
                      editable={parseNum(it.addDescPct) <= 0}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      style={[styles.input, parseNum(it.addDescPct) > 0 && styles.inputDisabled]}
                      testID="pedido-form-add-descrs"
                    />
                  </View>
                  ) : null}
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Acrésc. R$ (unit.)</Text>
                    <TextInput
                      value={it.addAcr}
                      onChangeText={it.setAddAcr}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="pedido-form-add-acr"
                    />
                  </View>
                </View>

                {modificadoresOn && modLoading ? (
                  <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 8 }} />
                ) : null}
                {modificadoresOn && !modLoading && modCategorias.length > 0 ? (
                  <View style={modStyles.wrap}>
                    {modCategorias.map((cat) => {
                      const sel = modSelecionados.get(cat.codigo) || new Set<number>();
                      const faltando = categoriasObrigatoriasFaltando.some((c) => c.codigo === cat.codigo);
                      return (
                        <View key={cat.codigo} style={modStyles.categoria}>
                          <View style={modStyles.categoriaHeader}>
                            <Text style={modStyles.categoriaNome}>{cat.nome}</Text>
                            <View style={[modStyles.badge, cat.obrigatorio ? modStyles.badgeObrig : modStyles.badgeOpc]}>
                              <Text style={[modStyles.badgeText, cat.obrigatorio ? modStyles.badgeTextObrig : modStyles.badgeTextOpc]}>
                                {cat.obrigatorio ? "Obrigatório" : "Opcional"}{cat.selecao_multipla ? " · Vários" : ""}
                              </Text>
                            </View>
                          </View>
                          {faltando ? <Text style={modStyles.avisoFaltando}>Selecione uma opção.</Text> : null}
                          {cat.modificadores.map((mod) => {
                            const ativo = sel.has(mod.codigo);
                            return (
                              <Pressable
                                key={mod.codigo}
                                style={modStyles.modRow}
                                onPress={() => toggleModificador(cat, mod.codigo)}
                                testID={`pedido-form-mod-${cat.codigo}-${mod.codigo}`}
                              >
                                <Ionicons
                                  name={cat.selecao_multipla ? (ativo ? "checkbox" : "square-outline") : (ativo ? "radio-button-on" : "radio-button-off")}
                                  size={18}
                                  color={ativo ? colors.brandPrimary : colors.muted}
                                />
                                <Text style={modStyles.modNome}>{mod.nome}</Text>
                                {mod.acrescimo > 0 ? <Text style={modStyles.modValor}>+{formatBRL(mod.acrescimo)}</Text> : null}
                                {mod.desconto > 0 ? <Text style={[modStyles.modValor, { color: colors.error }]}>-{formatBRL(mod.desconto)}</Text> : null}
                              </Pressable>
                            );
                          })}
                        </View>
                      );
                    })}
                  </View>
                ) : null}

                <Text style={styles.fieldLabel}>Complemento (opcional)</Text>
                <TextInput
                  value={it.addCompl}
                  onChangeText={it.setAddCompl}
                  placeholder="Descrição complementar"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="pedido-form-add-compl"
                />
                {(() => {
                  const pNormal = parseNum(it.addValor);
                  const dUnit = calcDescUnit(pNormal, it.addDescPct, it.addDescRs) + modDescontoTotal;
                  const acr = parseNum(it.addAcr) + modAcrescimoTotal;
                  const pVenda = pNormal - dUnit + acr;
                  const qtd = parseNum(it.addQtd);
                  return (
                    <View style={styles.liquidoBox}>
                      <View style={styles.liquidoRow}>
                        <Text style={styles.liquidoLabel}>Preço líquido unit.</Text>
                        <Text style={styles.liquidoVal}>{formatBRL(pVenda)}</Text>
                      </View>
                      {dUnit > 0 ? (
                        <View style={styles.liquidoRow}>
                          <Text style={styles.liquidoLabel}>Desconto total ({fmtNum(qtd)}×)</Text>
                          <Text style={[styles.liquidoVal, { color: colors.error }]}>- {formatBRL(dUnit * qtd)}</Text>
                        </View>
                      ) : null}
                      <View style={styles.previewRow}>
                        <Text style={styles.subtotalLabel}>Total do item</Text>
                        <Text style={styles.subtotalValue}>{formatBRL(qtd * pVenda)}</Text>
                      </View>
                    </View>
                  );
                })()}
                <View style={styles.modalBtns}>
                  <Pressable
                    onPress={() => it.setSelProd(null)}
                    style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]}
                  >
                    <Text style={styles.secondaryBtnText}>Voltar</Text>
                  </Pressable>
                  <Pressable
                    onPress={handleConfirmar}
                    disabled={it.addSaving || (exigeNumSerie && !it.selNumSerie)}
                    style={({ pressed }) => [
                      styles.primaryBtn,
                      (pressed || it.addSaving || (exigeNumSerie && !it.selNumSerie)) && { opacity: 0.8 },
                    ]}
                    testID="pedido-form-add-confirm"
                  >
                    {it.addSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Adicionar</Text>}
                  </Pressable>
                </View>
              </View>
            </ScrollView>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const modStyles = StyleSheet.create({
  wrap: { gap: spacing.sm, marginTop: 4 },
  categoria: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    padding: spacing.sm, gap: 4,
  },
  categoriaHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  categoriaNome: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  badge: { borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  badgeObrig: { backgroundColor: "#FDECEC" },
  badgeOpc: { backgroundColor: colors.brandTertiary },
  badgeText: { fontSize: 10, fontWeight: "700" },
  badgeTextObrig: { color: colors.error },
  badgeTextOpc: { color: colors.brandPrimary },
  avisoFaltando: { fontSize: 11, color: colors.error },
  modRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 },
  modNome: { flex: 1, fontSize: 13, color: colors.onSurface },
  modValor: { fontSize: 12, fontWeight: "600", color: colors.success },
});

// Aviso "Promoção aplicada" (Variação de Preço, `pecas_promocao`) sob o
// campo Valor unitário — ver `usePedidoItens.verificarPromocao`.
const promoStyles = StyleSheet.create({
  badge: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: colors.brandTertiary, borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 4, marginTop: -2,
  },
  badgeText: { fontSize: 11, fontWeight: "600", color: colors.brandPrimary },
});

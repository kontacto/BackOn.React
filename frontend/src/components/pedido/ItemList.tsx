// Seção "Itens do Pedido": lista de itens + botões de desconto geral/concedidos + subtotal.
import { useState } from "react";
import { ActivityIndicator, Platform, Pressable, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
// Ícone de garçom/prato servido pra Taxa de Serviço (pedido explícito do
// usuário, com imagem de referência) — não existe em Ionicons, então usamos
// MaterialCommunityIcons direto (mesmo pacote @expo/vector-icons, sem nova
// dependência). Só via expo-font, que não roda no Windows RNW ainda (ver
// src/components/Ionicons.windows.tsx) — inofensivo hoje porque a
// plataforma Windows está pausada (CLAUDE.md > "Platform Scope").
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";

import { colors } from "@/src/theme/colors";
import { formatBRL, formatDateBR } from "@/src/utils/format";
import { usePermissions } from "@/src/permissions";
import { styles } from "./styles";
import { ItemRow } from "./types";
import { UsePedidoItens } from "./usePedidoItens";

type Props = {
  editing: boolean;
  isAberto: boolean;
  it: UsePedidoItens;
  // Tela dona da permissão — "PEDIDO" (rápido, default) ou "PEDIDO_COMP".
  tela?: string;
  // Navegação pro relatório de margem/descontos — a tela dona decide a
  // rota; o botão só aparece se informado e a permissão ANALISE existir.
  onAnalisar?: () => void;
  // Fechar o pedido — a tela dona decide a rotina (pré-venda mobile/bar vs.
  // pedido completo); o botão só aparece se informado e a permissão
  // SITUACAO existir. `fechando` reflete o loading do próprio salvamento.
  onFechar?: () => void;
  fechando?: boolean;
  // Faturar o pedido (gera Comanda, situação -> PG) — exclusivo do Pedido
  // Bar (FrmManPedBar.frm, Command111_Click; ver PENDENCIAS.md > "Pedido
  // Bar" — só a parte não-fiscal, sem emissão de NFC-e). Aparece com o
  // pedido Aberto OU Fechado (`isFechado`) — se ainda Aberto, o backend
  // fecha e fatura no mesmo clique (pedido explícito do usuário, não
  // exige passar por "Fechar Pedido" antes). Permissão própria FATURAR
  // (separada de SITUACAO — cada botão real da tela tem seu checkbox).
  onFaturar?: () => void;
  faturando?: boolean;
  isFechado?: boolean;
  // Abre o Gestor de Documentos (AnexosPedidoModal) — pill entre "Faturar
  // Pedido" e "Imprimir" (pedido explícito do usuário, 2026-07-16), só
  // Pedido Bar, permissão própria ANEXOS. Só aparece com cliente já
  // selecionado (anexo é gravado como anexo do Cliente, precisa do
  // código dele).
  onAnexos?: () => void;
  // Reabre o pedido (situação F -> A) — pill amarelo entre "Faturar Pedido"
  // e "Anexo", ao lado de "Cancelar" (pedido explícito do usuário,
  // 2026-07-16), réplica de `cmdReabrir_Click` (FrmManPedBar.frm). Só
  // aparece com o pedido Fechado (`isFechado`) — Aberto/Cancelado/Faturado
  // não podem ser reabertos. Permissão própria REABRIR.
  onReabrir?: () => void;
  reabrindo?: boolean;
  // Cancela o pedido (situação -> C) — pill vermelho ao lado de "Reabrir"
  // (pedido explícito do usuário, 2026-07-16), réplica de `Command9_Click`
  // (FrmManPedBar.frm). Só aparece com o pedido Aberto ou Fechado (mesmo
  // recorte do backend — um pedido já Faturado não pode ser cancelado).
  // Permissão própria CANCELAR.
  onCancelar?: () => void;
  cancelando?: boolean;
  // Abre o preview de impressão (ReciboPedidoModal, réplica de Pedido_48_COL)
  // — pill ao lado de Faturar Pedido (pedido explícito do usuário), só web
  // (window.print()), só Pedido Bar, permissão própria IMPRIMIR.
  onImprimir?: () => void;
};

const isWeb = Platform.OS === "web";

export default function ItemList({
  editing, isAberto, it, tela = "PEDIDO", onAnalisar, onFechar, fechando, onFaturar, faturando, isFechado,
  onAnexos, onReabrir, reabrindo, onCancelar, cancelando, onImprimir,
}: Props) {
  const { itens, subtotal, itensLoading, descTotalItens, geralAtual } = it;
  const { can } = usePermissions();
  const canEditItem = can(`${tela}.EDIT_ITEM`) || can(`${tela}.DEL_ITEM`) || can(`${tela}.DESC_ITEM`);
  const canAnalise = !!onAnalisar && can(`${tela}.ANALISE`);
  const canGeral = isAberto && can(`${tela}.DESC_GERAL`);
  const canFechar = !!onFechar && isAberto && can(`${tela}.SITUACAO`);
  const canFaturar = !!onFaturar && tela === "PEDIDO" && (isAberto || !!isFechado) && can(`${tela}.FATURAR`);
  const canAnexos = !!onAnexos && tela === "PEDIDO" && can(`${tela}.ANEXOS`);
  const canReabrir = !!onReabrir && tela === "PEDIDO" && !!isFechado && can(`${tela}.REABRIR`);
  const canCancelar = !!onCancelar && tela === "PEDIDO" && (isAberto || !!isFechado) && can(`${tela}.CANCELAR`);
  const canImprimir = isWeb && !!onImprimir && tela === "PEDIDO" && itens.length > 0 && can(`${tela}.IMPRIMIR`);
  // Botão "Imprimir Item" em cada linha (FrmManPedBar.frm, Command62_Click)
  // — sempre disponível, não depende de haver impressora configurada por
  // Finalidade (isso só decide o disparo automático ao adicionar, ver
  // usePedidoItens.checkAutoPrintItem).
  const canImprimirItem = isWeb && tela === "PEDIDO" && can(`${tela}.IMPRIMIR_ITEM`);
  const canVerDescontos = descTotalItens > 0 && can(`${tela}.VER_DESCONTOS`);
  const canTaxaServico = isAberto && can(`${tela}.TX_SERVICO`);
  const taxaServicoIncluida = itens.some((i) => i.produto === "S002");
  // "Pedido Totalizado" — relatório read-only (agrupa itens repetidos),
  // exclusivo do Pedido Bar (FrmManPedBar.frm; o Pedido Completo não tem
  // esse botão na origem) — sem permissão própria, mesmo precedente de
  // sub-tela só-leitura não precisar de BOTAO no catálogo.
  const showPedidoTotalizado = tela === "PEDIDO" && itens.length > 0;
  // Tooltip da etiqueta de desconto — um só de cada vez, compartilhado
  // entre as linhas (hover no web, toque no mobile já que não há hover).
  const [descTooltipCodauto, setDescTooltipCodauto] = useState<number | null>(null);

  return (
    <>
      {/* Ação de Fechar/Faturar Pedido — acima da lista, pra não exigir rolar
          até o fim do pedido pra achá-la. Faturar fica ao lado de Fechar
          (pedido explícito do usuário). */}
      {canFechar || canFaturar || canReabrir || canCancelar || canAnexos || canImprimir ? (
        <View style={styles.itensToolbar}>
          {canFechar ? (
            <TouchableOpacity
              onPress={onFechar}
              activeOpacity={0.8}
              disabled={fechando || itens.length === 0}
              style={[styles.toolbarPillFechar, (fechando || itens.length === 0) && { opacity: 0.5 }]}
              testID="pedido-form-fechar-btn"
            >
              {fechando ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Ionicons name="lock-closed-outline" size={16} color="#fff" />
              )}
              <Text style={styles.toolbarPillFecharText}>Fechar Pedido</Text>
            </TouchableOpacity>
          ) : null}
          {canFaturar ? (
            <TouchableOpacity
              onPress={onFaturar}
              activeOpacity={0.8}
              disabled={faturando || itens.length === 0}
              style={[styles.toolbarPillFaturar, (faturando || itens.length === 0) && { opacity: 0.5 }]}
              testID="pedido-form-faturar-btn"
            >
              {faturando ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Ionicons name="cash-outline" size={16} color="#fff" />
              )}
              <Text style={styles.toolbarPillFaturarText}>Faturar Pedido</Text>
            </TouchableOpacity>
          ) : null}
          {canReabrir ? (
            <TouchableOpacity
              onPress={onReabrir}
              activeOpacity={0.8}
              disabled={reabrindo}
              style={[styles.toolbarPillReabrir, reabrindo && { opacity: 0.5 }]}
              testID="pedido-form-reabrir-btn"
            >
              {reabrindo ? (
                <ActivityIndicator size="small" color={colors.onWarning} />
              ) : (
                <Ionicons name="lock-open-outline" size={16} color={colors.onWarning} />
              )}
              <Text style={styles.toolbarPillReabrirText}>Reabrir</Text>
            </TouchableOpacity>
          ) : null}
          {canCancelar ? (
            <TouchableOpacity
              onPress={onCancelar}
              activeOpacity={0.8}
              disabled={cancelando}
              style={[styles.toolbarPillCancelar, cancelando && { opacity: 0.5 }]}
              testID="pedido-form-cancelar-btn"
            >
              {cancelando ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Ionicons name="close-circle-outline" size={16} color="#fff" />
              )}
              <Text style={styles.toolbarPillCancelarText}>Cancelar</Text>
            </TouchableOpacity>
          ) : null}
          {canAnexos ? (
            <TouchableOpacity
              onPress={onAnexos}
              activeOpacity={0.8}
              style={styles.toolbarPillAnexo}
              testID="pedido-form-anexos-btn"
            >
              <Ionicons name="attach-outline" size={16} color={colors.brandPrimary} />
              <Text style={styles.toolbarPillAnexoText}>Anexo</Text>
            </TouchableOpacity>
          ) : null}
          {canImprimir ? (
            <TouchableOpacity
              onPress={onImprimir}
              activeOpacity={0.8}
              style={styles.toolbarPillImprimir}
              testID="pedido-form-imprimir-btn"
            >
              <Ionicons name="print-outline" size={16} color={colors.brandPrimary} />
              <Text style={styles.toolbarPillImprimirText}>Imprimir</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}

      <View style={styles.itensSummaryRow}>
        <View style={styles.itensSummaryLeft}>
          <Text style={styles.sectionTitle}>
            Itens do Pedido {itens.length ? `(${itens.length})` : ""}
          </Text>
          {canVerDescontos ? (
            <TouchableOpacity
              onPress={it.openDescontos}
              activeOpacity={0.8}
              style={styles.descPill}
              testID="pedido-form-descontos-btn"
            >
              <Ionicons name="pricetag" size={13} color={colors.error} />
              <Text style={styles.descPillLabel}>Descontos</Text>
              <Text style={styles.descPillValue}>- {formatBRL(descTotalItens)}</Text>
              <Ionicons name="chevron-forward" size={14} color={colors.error} />
            </TouchableOpacity>
          ) : null}
          {canAnalise ? (
            <TouchableOpacity
              onPress={onAnalisar}
              activeOpacity={0.8}
              style={styles.toolbarPill}
              testID="pedido-form-analise-btn"
            >
              <Ionicons name="bar-chart-outline" size={16} color={colors.brandPrimary} />
              <Text style={styles.toolbarPillText}>Margem</Text>
              <Ionicons name="chevron-forward" size={14} color={colors.brandPrimary} />
            </TouchableOpacity>
          ) : null}
          {canGeral ? (
            <TouchableOpacity
              onPress={it.openGeralModal}
              activeOpacity={0.8}
              style={styles.toolbarPill}
              testID="pedido-form-desconto-geral-btn"
            >
              <Ionicons name="cash-outline" size={16} color={colors.brandPrimary} />
              <Text style={styles.toolbarPillText}>
                Desconto geral{geralAtual > 0 ? ` (${formatBRL(geralAtual)})` : ""}
              </Text>
            </TouchableOpacity>
          ) : null}
          {canTaxaServico ? (
            <TouchableOpacity
              onPress={it.handleTaxaServico}
              activeOpacity={0.8}
              disabled={it.taxaServicoSaving || itens.length === 0}
              style={[
                styles.toolbarPill,
                taxaServicoIncluida && styles.toolbarPillActive,
                (it.taxaServicoSaving || itens.length === 0) && { opacity: 0.5 },
              ]}
              testID="pedido-form-taxa-servico-btn"
            >
              {it.taxaServicoSaving ? (
                <ActivityIndicator size="small" color={taxaServicoIncluida ? "#fff" : colors.brandPrimary} />
              ) : (
                <MaterialCommunityIcons
                  name="room-service"
                  size={15}
                  color={taxaServicoIncluida ? "#fff" : colors.brandPrimary}
                />
              )}
              <Text style={[styles.toolbarPillText, taxaServicoIncluida && styles.toolbarPillActiveText]}>
                Tx Serviço
              </Text>
            </TouchableOpacity>
          ) : null}
          {showPedidoTotalizado ? (
            <TouchableOpacity
              onPress={() => it.setPedidoTotalizadoOpen(true)}
              activeOpacity={0.8}
              style={styles.toolbarPill}
              testID="pedido-form-pedido-totalizado-btn"
            >
              <Ionicons name="receipt-outline" size={15} color={colors.brandPrimary} />
              <Text style={styles.toolbarPillText}>Pedido Totalizado</Text>
            </TouchableOpacity>
          ) : null}
        </View>
        <View style={styles.itensSummaryRight}>
          {editing && isAberto && can(`${tela}.ADD_ITEM`) ? (
            <Pressable
              onPress={it.openAddModal}
              style={({ pressed }) => [styles.addItemBtn, pressed && { opacity: 0.8 }]}
              testID="pedido-form-add-item"
            >
              <Ionicons name="add" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.addItemBtnText}>Adicionar</Text>
            </Pressable>
          ) : null}
          {itens.length > 0 ? (
            <View style={styles.subtotalPill}>
              <Text style={styles.subtotalPillLabel}>Subtotal</Text>
              <Text style={styles.subtotalPillValue}>{formatBRL(subtotal)}</Text>
            </View>
          ) : null}
        </View>
      </View>

      {!editing ? (
        <View style={styles.itensHint}>
          <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
          <Text style={styles.itensHintText}>Grave o pedido para adicionar itens.</Text>
        </View>
      ) : itensLoading && itens.length === 0 ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
      ) : itens.length === 0 ? (
        <View style={styles.itensHint}>
          <Ionicons name="cube-outline" size={18} color={colors.muted} />
          <Text style={styles.itensHintText}>Nenhum item adicionado.</Text>
        </View>
      ) : (
        <View style={{ gap: 8 }}>
          {itens.map((item: ItemRow) => {
            const desc = item.descricao || item.produto;
            const complementoDiferente =
              item.complemento && item.complemento.trim().toUpperCase() !== desc.trim().toUpperCase();
            return (
              <Pressable
                key={item.codauto}
                onPress={canEditItem ? () => it.openEditModal(item) : undefined}
                disabled={!canEditItem}
                style={({ pressed }) => [styles.itemRowCompact, pressed && canEditItem && { opacity: 0.8 }]}
                testID={`pedido-form-item-${item.codauto}`}
              >
                <View
                  style={[
                    styles.itemTipo,
                    item.produto === "S002" ? styles.tagTaxaServico : item.tipo === "P" ? styles.tagProd : styles.tagServ,
                  ]}
                >
                  {item.produto === "S002" ? (
                    <MaterialCommunityIcons name="room-service" size={16} color={colors.success} />
                  ) : (
                    <Ionicons
                      name={item.tipo === "P" ? "cube" : "construct"}
                      size={16}
                      color={item.tipo === "P" ? colors.brandPrimary : colors.warning}
                    />
                  )}
                </View>
                <Text style={styles.itemDescCompact} numberOfLines={1}>
                  {desc}{complementoDiferente ? ` — ${item.complemento}` : ""}
                </Text>
                {item.desconto > 0 ? (
                  <View style={{ position: "relative" }}>
                    <Pressable
                      onPress={(e) => {
                        e.stopPropagation();
                        setDescTooltipCodauto((c) => (c === item.codauto ? null : item.codauto));
                      }}
                      onHoverIn={() => setDescTooltipCodauto(item.codauto)}
                      onHoverOut={() => setDescTooltipCodauto((c) => (c === item.codauto ? null : c))}
                      style={styles.descTagCompact}
                      testID={`pedido-form-item-desconto-tag-${item.codauto}`}
                    >
                      <Ionicons name="pricetag" size={11} color="#fff" />
                    </Pressable>
                    {descTooltipCodauto === item.codauto ? (
                      <View style={styles.descTooltip} pointerEvents="none">
                        <Text style={styles.descTooltipText}>
                          Desconto: {formatBRL(item.desconto * item.qtd)}
                        </Text>
                      </View>
                    ) : null}
                  </View>
                ) : null}
                <Text style={styles.itemSubCompact} numberOfLines={1}>
                  {item.cod_fab ? `${item.cod_fab} · ` : ""}{item.qtd.toLocaleString("pt-BR")} {item.unidade} × {formatBRL(item.valor_unitario)}
                </Text>
                {item.data_inclusao ? (
                  <Text style={styles.itemIncluidoEmCompact} numberOfLines={1}>
                    Incluído em {formatDateBR(item.data_inclusao)}{item.hora_inclusao ? ` às ${item.hora_inclusao.slice(0, 5)}` : ""}
                  </Text>
                ) : null}
                {canImprimirItem ? (
                  <Pressable
                    onPress={(e) => {
                      e.stopPropagation();
                      it.setPrintItem(item);
                    }}
                    style={styles.imprimirItemTag}
                    testID={`pedido-form-item-imprimir-${item.codauto}`}
                  >
                    <Ionicons name="print-outline" size={13} color={colors.brandPrimary} />
                  </Pressable>
                ) : null}
                <Text style={[styles.itemTotal, styles.itemTotalCompact]}>{formatBRL(item.total)}</Text>
              </Pressable>
            );
          })}
        </View>
      )}
    </>
  );
}

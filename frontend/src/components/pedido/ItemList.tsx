// Seção "Itens do Pedido": lista de itens + botões de desconto geral/concedidos + subtotal.
import { useState, type ReactNode } from "react";
import { ActivityIndicator, Platform, Pressable, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
// Ícone de garçom/prato servido pra Taxa de Serviço (pedido explícito do
// usuário, com imagem de referência) — não existe em Ionicons, então usamos
// MaterialCommunityIcons direto (mesmo pacote @expo/vector-icons, sem nova
// dependência). Só via expo-font, que não roda no Windows RNW ainda (ver
// src/components/Ionicons.windows.tsx) — inofensivo hoje porque a
// plataforma Windows está pausada (CLAUDE.md > "Platform Scope").
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";

import { colors } from "@/src/theme/colors";
import { formatBRL, formatDateBR, fmtNum } from "@/src/utils/format";
import { usePermissions } from "@/src/permissions";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import { styles } from "./styles";
import { ItemRow } from "./types";

// Superfície mínima que o ItemList realmente usa do hook de itens — não o
// `UsePedidoItens` inteiro (que carrega kit/m²/clínica/num_serie/taxa de
// serviço, conceitos exclusivos do Pedido). Interseção estrutural: o
// retorno de `usePedidoItens` já satisfaz esta interface automaticamente
// (é um superset), e o retorno de `useOSItens` (O.S. Completa) só precisa
// implementar isto. `setAgendarItem` é real dos dois lados desde 2026-08-01
// (Agendar item de Serviço chegou na O.S. Completa via módulo Assistência,
// ver `os/useOSItens.ts` e `pedido/agendaTypes.ts`) — os campos
// verdadeiramente Pedido-only que restam (`taxaServicoSaving`,
// `handleTaxaServico`, `setPrintItem`, `setPedidoTotalizadoOpen`) nunca são
// de fato chamados pra `tela === "OS_COMP"` (os gates abaixo —
// `canTaxaServico`/`canImprimirItem`/`showPedidoTotalizado` — ficam todos
// falsos), mas o TypeScript ainda exige que a propriedade exista no objeto.
export type ItemListItens = {
  itens: ItemRow[];
  subtotal: number;
  itensLoading: boolean;
  descTotalItens: number;
  geralAtual: number;
  openDescontos: () => void;
  openAddModal: () => void;
  openEditModal: (item: ItemRow) => void;
  openGeralModal: () => void;
  taxaServicoSaving: boolean;
  handleTaxaServico: () => void;
  setPrintItem: (item: ItemRow) => void;
  setAgendarItem: (item: ItemRow) => void;
  setPedidoTotalizadoOpen: (open: boolean) => void;
  // Pontuação de Técnicos (O.S. Completa, exclusivo — `useOSItens.ts`) —
  // opcional (`?`) porque só a O.S. tem essa noção; `usePedidoItens` não
  // precisa implementar no-op nenhum, TS já aceita a ausência de campo
  // opcional. Ver "Pontuação inline na linha do serviço", 2026-08-13,
  // user-directed.
  savePontuacao?: (
    codOsProd: number,
    valores: { pontuacao_e?: number | null; pontuacao_v?: number | null; pontuacao_a?: number | null },
  ) => void;
  pontuacaoSaving?: boolean;
};

type Props = {
  editing: boolean;
  isAberto: boolean;
  it: ItemListItens;
  // Tela dona da permissão — "PEDIDO" (rápido, default), "PEDIDO_COMP" ou
  // "OS_COMP" (O.S. Completa reaproveita a barra de ações Fechar/Faturar/
  // Reabrir/Cancelar/Imprimir — ver `hasSituacaoActions` abaixo — mas nunca
  // Dividir/Imprimir Item/Agendar/Pedido Totalizado/Tx Serviço, que
  // continuam exclusivos do Pedido).
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
  // Abre o DividirPedidoModal — pill ao lado de "Fechar Pedido" (só com o
  // pedido Aberto, mesma condição), permissão própria DIVIDIR. Pedido
  // explícito do usuário, 2026-07-17 — funcionalidade nova, sem
  // equivalente no legado.
  onDividir?: () => void;
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
  // Conteúdo extra ao lado de Margem/Desconto Geral/Pedido Totalizado, no
  // rodapé (final da lista de itens) — a tela dona usa isso pra encaixar o
  // botão de WhatsApp na mesma linha (pedido explícito do usuário,
  // 2026-07-17), sem o ItemList precisar conhecer `conn`/`documentId`/etc.
  footerRight?: ReactNode;
  // Tempo Gasto por Serviço, acessível direto da linha (O.S. Completa,
  // exclusivo) — a tela dona decide como abrir o modal (pré-selecionando
  // o serviço do item clicado), o ItemList só avisa qual item foi tocado.
  // 2026-08-13, user-directed ("tempo gasto por serviço na linha do
  // serviço").
  onTempoGastoItem?: (item: ItemRow) => void;
};

const isWeb = Platform.OS === "web";

// Pontuação de Técnicos inline, direto na linha do item (O.S. Completa —
// 2026-08-13, user-directed: "coloque a pontuação do técnico na linha do
// serviço"). 3 campos numéricos bem estreitos (Técnico/Vendedor/Atendente,
// 0-999) + 1 ícone de salvar — mesma faixa 0-999 e mesmo formato de dado
// do `PontuacaoModal.tsx` (que continua existindo, pra consulta/edição em
// lote), só que sem precisar abrir modal pra pontuar um item isolado.
function clampPontos(v: string): number | null {
  const n = parseInt(v.replace(/\D/g, ""), 10);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(999, n));
}

function PontuacaoInline({
  item, saving, onSave,
}: {
  item: ItemRow;
  saving: boolean;
  onSave: NonNullable<ItemListItens["savePontuacao"]>;
}) {
  const [e, setE] = useState(item.pontuacao_e != null ? String(item.pontuacao_e) : "");
  const [v, setV] = useState(item.pontuacao_v != null ? String(item.pontuacao_v) : "");
  const [a, setA] = useState(item.pontuacao_a != null ? String(item.pontuacao_a) : "");
  const [hoverLabel, setHoverLabel] = useState<string | null>(null);

  const salvar = (ev: import("react-native").GestureResponderEvent) => {
    ev.stopPropagation();
    if (item.cod_os_prod == null) return;
    onSave(item.cod_os_prod, { pontuacao_e: clampPontos(e), pontuacao_v: clampPontos(v), pontuacao_a: clampPontos(a) });
  };

  const campo = (label: string, valor: string, setValor: (v: string) => void, testID: string) => (
    <View
      style={{ position: "relative" }}
      onStartShouldSetResponder={() => true}
      onResponderTerminationRequest={() => false}
    >
      <TextInput
        value={valor}
        onChangeText={setValor}
        onFocus={(ev: any) => ev.stopPropagation?.()}
        keyboardType="number-pad"
        maxLength={3}
        placeholder="0"
        onPressIn={(ev: any) => ev.stopPropagation?.()}
        {...(isWeb ? { onMouseEnter: () => setHoverLabel(label), onMouseLeave: () => setHoverLabel(null) } : {})}
        style={ps.input}
        testID={testID}
      />
      {isWeb && hoverLabel === label ? (
        <View style={ps.tooltip} pointerEvents="none">
          <Text style={ps.tooltipText}>{label}</Text>
        </View>
      ) : null}
    </View>
  );

  return (
    <View style={ps.wrap}>
      <Ionicons name="star-outline" size={12} color={colors.muted} />
      {campo("Técnico", e, setE, `pontuacao-inline-e-${item.cod_os_prod}`)}
      {campo("Vendedor", v, setV, `pontuacao-inline-v-${item.cod_os_prod}`)}
      {campo("Atendente", a, setA, `pontuacao-inline-a-${item.cod_os_prod}`)}
      <Pressable onPress={salvar} disabled={saving} style={[ps.saveBtn, saving && { opacity: 0.6 }]} testID={`pontuacao-inline-salvar-${item.cod_os_prod}`}>
        {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Ionicons name="checkmark" size={12} color={colors.onBrandPrimary} />}
      </Pressable>
    </View>
  );
}

const ps = {
  wrap: { flexDirection: "row" as const, alignItems: "center" as const, gap: 4 },
  input: {
    width: 34, height: 26, borderWidth: 1, borderColor: colors.border, borderRadius: 6,
    backgroundColor: colors.surface, textAlign: "center" as const, fontSize: 12, color: colors.onSurface,
    paddingHorizontal: 2, paddingVertical: 0,
  },
  saveBtn: {
    width: 22, height: 22, borderRadius: 5, backgroundColor: colors.brandPrimary,
    alignItems: "center" as const, justifyContent: "center" as const,
  },
  tooltip: {
    position: "absolute" as const, bottom: "100%" as const, left: 0, marginBottom: 3,
    backgroundColor: "#1a1a1a", borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2, zIndex: 1000,
  },
  tooltipText: { color: "#fff", fontSize: 10, fontWeight: "600" as const },
};

export default function ItemList({
  editing, isAberto, it, tela = "PEDIDO", onAnalisar, onFechar, fechando, onFaturar, faturando, isFechado,
  onDividir, onReabrir, reabrindo, onCancelar, cancelando, onImprimir, footerRight, onTempoGastoItem,
}: Props) {
  const router = useRouter();
  const { itens, subtotal, itensLoading, descTotalItens, geralAtual } = it;
  const { can, moduleOn } = usePermissions();
  const canEditItem = can(`${tela}.EDIT_ITEM`) || can(`${tela}.DEL_ITEM`) || can(`${tela}.DESC_ITEM`);
  const canAnalise = !!onAnalisar && can(`${tela}.ANALISE`);
  const canGeral = isAberto && can(`${tela}.DESC_GERAL`);
  // Botões trazidos do Pedido Bar pro Pedido Completo/Geral 2026-07-20
  // (pedido explícito do usuário: "aplicar... o layout e as funções do
  // pedido bar com exceção da taxa de serviço") — daí o `["PEDIDO",
  // "PEDIDO_COMP"].includes(tela)` em vez de `tela === "PEDIDO"` puro.
  // TX_SERVICO continua exclusivo do Bar (não checado aqui, ver mais
  // abaixo) — único item deliberadamente não generalizado.
  const isPedidoOuCompleto = tela === "PEDIDO" || tela === "PEDIDO_COMP";
  // Fechar/Faturar/Reabrir/Cancelar/Imprimir são a máquina de estados
  // compartilhada por Pedido E O.S. Completa (`os_service.py` reaproveita
  // literalmente `_fechar_os_sync`/`_faturar_os_sync`/etc. com
  // `tela="OS_COMP"`, ver os_completo_service.py) — Dividir/Imprimir Item/
  // Agendar/Pedido Totalizado/Tx Serviço continuam checados só por
  // `isPedidoOuCompleto`/`tela === "PEDIDO"`, sem equivalente na O.S.
  const hasSituacaoActions = isPedidoOuCompleto || tela === "OS_COMP";
  // Pedido Geral e O.S. Completa ("telas completas") compartilham 2 regras
  // que divergem do Pedido Bar: (1) só faturam já Fechado, sem o atalho
  // "fecha-e-fatura junto" (`_faturar_os_sync` nunca teve esse atalho,
  // igual ao Pedido Geral); (2) Cancelar reaproveita a permissão SITUACAO
  // em vez de uma CANCELAR própria (ver comentário de `canCancelar`).
  const isTelaCompleta = tela === "PEDIDO_COMP" || tela === "OS_COMP";
  const canFechar = !!onFechar && isAberto && can(`${tela}.SITUACAO`);
  const canDividir = !!onDividir && isPedidoOuCompleto && isAberto && itens.length > 0 && can(`${tela}.DIVIDIR`);
  // Diferença de regra confirmada pelo usuário, 2026-07-20: diferente do
  // Pedido Bar (fecha-e-fatura num clique só, aceita Aberto ou Fechado), o
  // Pedido Geral só pode faturar um pedido já Fechado — mesma restrição
  // aplicada no backend (`_faturar_pedido_sync`'s `exigir_fechado=True`).
  const canFaturar = !!onFaturar && hasSituacaoActions
    && (isTelaCompleta ? !!isFechado : (isAberto || !!isFechado))
    && can(`${tela}.FATURAR`);
  const canReabrir = !!onReabrir && hasSituacaoActions && !!isFechado && can(`${tela}.REABRIR`);
  // Pedido Geral e O.S. Completa cancelam reaproveitando a permissão
  // SITUACAO (não uma CANCELAR própria) — decisão deliberada pra não
  // exigir reconcessão de permissão em instalações já configuradas (ver
  // docstring de `pedidos_service._cancelar_pedido_sync`/
  // `os_service._cancelar_os_sync` e ACOES_PEDIDO_COMP/ACOES_OS_COMP em
  // permissoes_service.py, que por isso não têm a ação CANCELAR própria).
  // Checar `${tela}.CANCELAR` aqui sempre daria falso pra essas duas telas
  // — mesmo bug já corrigido pro Pedido Geral em 2026-07-20.
  const canCancelar = !!onCancelar && hasSituacaoActions && (isAberto || !!isFechado)
    && can(isTelaCompleta ? `${tela}.SITUACAO` : `${tela}.CANCELAR`);
  const canImprimir = isWeb && !!onImprimir && hasSituacaoActions && itens.length > 0 && can(`${tela}.IMPRIMIR`);
  // Botão "Imprimir Item" em cada linha (FrmManPedBar.frm, Command62_Click)
  // — sempre disponível, não depende de haver impressora configurada por
  // Finalidade (isso só decide o disparo automático ao adicionar, ver
  // usePedidoItens.checkAutoPrintItem).
  const canImprimirItem = isWeb && isPedidoOuCompleto && can(`${tela}.IMPRIMIR_ITEM`);
  // Agendar item de Serviço — Pedido Geral (Fase B, módulo Clínica OU
  // Assistência, user-directed 2026-07-28; mesmo escopo do desdobramento de
  // item, ver `pedido_completo_service._add_item_completo_sync`) E, desde
  // 2026-08-01, O.S. Completa (só módulo Assistência — Clínica é exclusiva
  // do segmento Pedido, sem equivalente na O.S.). Ver PENDENCIAS.md >
  // "O.S. Completa" > "Agendar item de Serviço" e "Transações" > "Pedido
  // Geral — Fase B: Clínica (Agendamento)".
  const canAgendar =
    (tela === "PEDIDO_COMP" && (moduleOn("CLINICA") || moduleOn("Assistencia")) && can(`${tela}.AGENDAR`)) ||
    (tela === "OS_COMP" && moduleOn("Assistencia") && can(`${tela}.AGENDAR`));
  // Pontuação de Técnicos inline na linha (2026-08-13, user-directed) —
  // substitui o modal em lote (PontuacaoModal) como forma PRINCIPAL de
  // pontuar; o modal continua existindo (consulta/edição em lote), só
  // deixou de ser o único caminho.
  const canPontuacaoInline = tela === "OS_COMP" && !!it.savePontuacao && can(`${tela}.PONTUACAO`);
  // Tempo Gasto acessível direto da linha (mesmo pedido, mesmo dia) — só
  // serviço, mesma restrição do combo do TempoGastoModal (peça nunca grava
  // em os_tempo, ver PENDENCIAS.md > "Tempo Gasto por Serviço").
  const canTempoGastoInline = tela === "OS_COMP" && !!onTempoGastoItem && can(`${tela}.TEMPO`);
  const canVerDescontos = descTotalItens > 0 && can(`${tela}.VER_DESCONTOS`);
  // Taxa de Serviço continua EXCLUSIVA do Pedido Bar — único recurso
  // deliberadamente não trazido ao Pedido Completo/Geral (pedido explícito
  // do usuário). `tela === "PEDIDO"` aqui, não `isPedidoOuCompleto`.
  const canTaxaServico = isAberto && tela === "PEDIDO" && can(`${tela}.TX_SERVICO`);
  const taxaServicoIncluida = itens.some((i) => i.produto === "S002");
  // "Pedido Totalizado" — relatório read-only (agrupa itens repetidos).
  // Exclusivo do Pedido Bar na origem (FrmManPedBar.frm; frmmanpedfor.frm
  // não tem esse botão) — trazido ao Pedido Completo/Geral por consistência
  // de layout mesmo assim (pedido explícito do usuário, 2026-07-20). Sem
  // permissão própria (sub-tela só-leitura), mesmo precedente de sempre.
  const showPedidoTotalizado = isPedidoOuCompleto && itens.length > 0;
  // Tooltip da etiqueta de desconto — um só de cada vez, compartilhado
  // entre as linhas (hover no web, toque no mobile já que não há hover).
  const [descTooltipCodauto, setDescTooltipCodauto] = useState<number | null>(null);
  // Rótulos "Pedido"/"O.S." nos textos da toolbar/título — só isso muda
  // entre as 3 telas que reaproveitam este componente, o resto do JSX é
  // igual (ver `hasSituacaoActions` acima pro porquê disso ser seguro).
  const entidadeLabel = tela === "OS_COMP" ? "O.S." : "Pedido";
  const itensLabel = tela === "OS_COMP" ? "Itens da O.S." : "Itens do Pedido";

  return (
    <>
      {/* Ação de Fechar/Faturar Pedido — acima da lista, pra não exigir rolar
          até o fim do pedido pra achá-la. Faturar fica ao lado de Fechar
          (pedido explícito do usuário). */}
      {canFechar || canDividir || canFaturar || canReabrir || canCancelar || canImprimir ? (
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
              <Text style={styles.toolbarPillFecharText}>Fechar {entidadeLabel}</Text>
            </TouchableOpacity>
          ) : null}
          {canDividir ? (
            <TouchableOpacity
              onPress={onDividir}
              activeOpacity={0.8}
              style={styles.toolbarPillAnexo}
              testID="pedido-form-dividir-btn"
            >
              <Ionicons name="git-branch-outline" size={16} color={colors.brandPrimary} />
              <Text style={styles.toolbarPillAnexoText}>Distribuir</Text>
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
              <Text style={styles.toolbarPillFaturarText}>Faturar {entidadeLabel}</Text>
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
            {itensLabel} {itens.length ? `(${itens.length})` : ""}
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
        </View>
        <View style={styles.itensSummaryRight}>
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
          <Text style={styles.itensHintText}>Grave {tela === "OS_COMP" ? "a O.S." : "o pedido"} para adicionar itens.</Text>
        </View>
      ) : itensLoading && itens.length === 0 ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
      ) : itens.length === 0 ? (
        <View style={styles.itensHint}>
          <Ionicons name="cube-outline" size={18} color={colors.muted} />
          <Text style={styles.itensHintText}>Nenhum item adicionado.</Text>
        </View>
      ) : (
        // `zIndex` aqui garante que a lista inteira (e qualquer tooltip que
        // escape de uma linha pra fora dos limites dela, ex.: "Agendar
        // atendimento" perto do fim da linha) pinte por cima do rodapé
        // seguinte (Margem/Desconto Geral/Pedido Totalizado) — os dois são
        // IRMÃOS no mesmo pai, então elevar só o wrapper interno do ícone
        // (já feito em `IconButtonWithTooltip`) não basta; a comparação de
        // stacking que importa aqui acontece neste nível, entre a lista e o
        // rodapé. Ver CLAUDE.md > "Modo Didático" > tooltip sempre por cima.
        <View style={{ gap: 8, zIndex: 1 }}>
          {itens.map((item: ItemRow) => {
            const desc = item.descricao || item.produto;
            const complementoDiferente =
              item.complemento && item.complemento.trim().toUpperCase() !== desc.trim().toUpperCase();
            return (
              <Pressable
                key={item.codauto}
                onPress={canEditItem ? () => it.openEditModal(item) : undefined}
                disabled={!canEditItem}
                style={({ pressed }) => [
                  styles.itemRowCompact,
                  // Design Desktop / Pontuação+Tempo Gasto inline: a O.S.
                  // Completa pode ter mais elementos na linha do que o
                  // Pedido — deixa quebrar linha em vez de estourar largura.
                  (canPontuacaoInline || canTempoGastoInline) && { flexWrap: "wrap" as const, rowGap: 6 },
                  pressed && canEditItem && { opacity: 0.8 },
                ]}
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
                  {/* Número de série vinculado (Fase B, só Pedido Geral) —
                      item.num_serie nunca vem preenchido pro Pedido Bar. */}
                  {item.num_serie ? ` · Nº Série: ${item.num_serie}` : ""}
                  {/* Dimensão m² (Fase B, só Pedido Geral) — item.comprimento/
                      largura nunca vêm preenchidos pro Pedido Bar. */}
                  {item.comprimento && item.largura ? ` · ${fmtNum(item.comprimento)} x ${fmtNum(item.largura)} m` : ""}
                  {item.agendamento ? ` · Agendado: ${formatDateBR(item.agendamento.data)} às ${item.agendamento.hora_ini} (${item.agendamento.profissional})` : ""}
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
                  <IconButtonWithTooltip
                    icon="print-outline"
                    label="Imprimir item"
                    size={13}
                    onPress={(e) => {
                      e.stopPropagation();
                      it.setPrintItem(item);
                    }}
                    style={styles.imprimirItemTag}
                    testID={`pedido-form-item-imprimir-${item.codauto}`}
                  />
                ) : null}
                {canAgendar && item.tipo === "S" ? (
                  <IconButtonWithTooltip
                    icon="calendar-outline"
                    label="Agendar atendimento"
                    size={13}
                    onPress={(e) => {
                      e.stopPropagation();
                      it.setAgendarItem(item);
                    }}
                    style={styles.imprimirItemTag}
                    testID={`pedido-form-item-agendar-${item.codauto}`}
                  />
                ) : null}
                {item.agendamento ? (
                  <IconButtonWithTooltip
                    icon="open-outline"
                    label="Ver na Agenda"
                    size={13}
                    onPress={(e) => {
                      e.stopPropagation();
                      router.push({
                        pathname: "/agenda",
                        params: { funcionario: String(item.agendamento!.funcionario), data: item.agendamento!.data },
                      } as never);
                    }}
                    style={styles.imprimirItemTag}
                    testID={`pedido-form-item-ver-agenda-${item.codauto}`}
                  />
                ) : null}
                {canTempoGastoInline && item.tipo === "S" ? (
                  <IconButtonWithTooltip
                    icon="time-outline"
                    label="Tempo Gasto"
                    size={13}
                    onPress={(e) => {
                      e.stopPropagation();
                      onTempoGastoItem!(item);
                    }}
                    style={styles.imprimirItemTag}
                    testID={`pedido-form-item-tempo-gasto-${item.codauto}`}
                  />
                ) : null}
                {canPontuacaoInline ? (
                  <PontuacaoInline item={item} saving={!!it.pontuacaoSaving} onSave={it.savePontuacao!} />
                ) : null}
                <Text style={[styles.itemTotal, styles.itemTotalCompact]}>{formatBRL(item.total)}</Text>
              </Pressable>
            );
          })}
        </View>
      )}

      {/* Rodapé — Margem/Desconto Geral/Pedido Totalizado no final da lista,
          ao lado do botão de WhatsApp (`footerRight`, injetado pela tela
          dona — pedido explícito do usuário, 2026-07-17). */}
      {canAnalise || canGeral || showPedidoTotalizado || footerRight ? (
        <View style={styles.itensFooterRow}>
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
          {footerRight}
        </View>
      ) : null}
    </>
  );
}

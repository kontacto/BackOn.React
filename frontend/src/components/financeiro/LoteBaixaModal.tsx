// Pagamento/Cancelamento em Lote (+ Baixa por Montante, só Contas a
// Receber) — réplica do painel "Por Data" de `Revenda/FrmManPar.frm`
// (Receber) / `Revenda/FrmManPap.frm` (Pagar), ver PENDENCIAS.md > "Baixa
// de Duplicatas — Achado Completo (2026-08-28)" pro rastreio completo.
// Compartilhado pelas duas telas (contas-receber.tsx/contas-pagar.tsx) —
// nunca duplicar esta lógica por tela.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";
import FornecedorSearchModal, { FornecedorRow } from "@/src/components/FornecedorSearchModal";
import { styles as ps } from "@/src/components/pedido/styles";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL, formatDateBR, parseNum, todayISO } from "@/src/utils/format";

const isWeb = Platform.OS === "web";

type VencimentoLote = {
  codigo: number; duplicata: number; desmembramento: number | null; dt_vencimento: string | null;
  valor: number; situacao: string; data_pag: string | null;
  cliente?: number; cliente_nome?: string; fornecedor?: number; fornecedor_nome?: string;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  apiBase: "contas-receber" | "contas-pagar";
  entidadeLabel: "Cliente" | "Fornecedor";
  permitirMontante?: boolean;
  contasOpts: SelectOption[];
  formaPagOpts: SelectOption[];
  usuarioCod: number;
  classe: number | null | undefined;
  onDone: () => void;
};

export default function LoteBaixaModal({
  visible, onClose, conn, apiBase, entidadeLabel, permitirMontante, contasOpts, formaPagOpts,
  usuarioCod, classe, onDone,
}: Props) {
  const feedback = useFeedback();
  const [modo, setModo] = useState<"baixar" | "cancelar">("baixar");
  const [tipoLote, setTipoLote] = useState<"parcela" | "montante">("parcela");
  const [dataIni, setDataIni] = useState<string | null>(todayISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [entidadeCod, setEntidadeCod] = useState<number | null>(null);
  const [entidadeNome, setEntidadeNome] = useState("");
  const [entidadeSearchOpen, setEntidadeSearchOpen] = useState(false);
  const [entidadeTerm, setEntidadeTerm] = useState("");
  const [entidadeResults, setEntidadeResults] = useState<(ClienteRow | FornecedorRow)[]>([]);
  const [entidadeLoading, setEntidadeLoading] = useState(false);

  const [buscando, setBuscando] = useState(false);
  const [items, setItems] = useState<VencimentoLote[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());

  const [loteDataPag, setLoteDataPag] = useState<string | null>(todayISO());
  const [loteConta, setLoteConta] = useState<number | null>(null);
  const [loteFormaPag, setLoteFormaPag] = useState<string | null>(null);
  const [montante, setMontante] = useState("");
  const [executando, setExecutando] = useState(false);

  const isReceber = apiBase === "contas-receber";

  useEffect(() => {
    if (!visible) return;
    setModo("baixar"); setTipoLote("parcela");
    setDataIni(todayISO()); setDataFim(todayISO());
    setEntidadeCod(null); setEntidadeNome("");
    setItems([]); setSelecionados(new Set());
    setLoteDataPag(todayISO()); setLoteConta(null); setLoteFormaPag(null); setMontante("");
  }, [visible]);

  useEffect(() => {
    if (!entidadeSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setEntidadeLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        if (isReceber) {
          const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(entidadeTerm)}`;
          const r = await fetch(`${base}/api/clientes/find/search?${qs}`);
          const j = await r.json();
          setEntidadeResults(j?.items || []);
        } else {
          const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(entidadeTerm)}`;
          const r = await fetch(`${base}/api/fornecedores?${qs}`);
          const j = await r.json();
          setEntidadeResults(j?.success ? (j.items || []) : []);
        }
      } catch { setEntidadeResults([]); } finally { setEntidadeLoading(false); }
    }, 350);
    return () => clearTimeout(t);
  }, [entidadeTerm, entidadeSearchOpen, conn, isReceber]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (tipoLote === "montante" && !entidadeCod) {
      feedback.showError(`Escolha um ${entidadeLabel.toLowerCase()} pra usar a baixa por Montante.`);
      return;
    }
    setBuscando(true);
    setSelecionados(new Set());
    try {
      const params: Record<string, string> = { modo };
      if (dataIni && dataFim) { params.data_ini = dataIni; params.data_fim = dataFim; }
      if (entidadeCod) params[isReceber ? "cliente" : "fornecedor"] = String(entidadeCod);
      const j = await apiGet(conn, `/api/${apiBase}/lote/vencimentos`, params);
      if (j?.success) {
        setItems(j.items || []);
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível buscar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBuscando(false);
    }
  }, [conn, apiBase, modo, tipoLote, dataIni, dataFim, entidadeCod, entidadeLabel, isReceber, feedback]);

  useEffect(() => { if (visible && conn) buscar(); }, [visible, conn, modo]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleSel = (codigo: number) => {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(codigo)) next.delete(codigo); else next.add(codigo);
      return next;
    });
  };
  const marcarTodos = () => setSelecionados(new Set(items.map((i) => i.codigo)));
  const desmarcarTodos = () => setSelecionados(new Set());

  const totalSelecionado = items.filter((i) => selecionados.has(i.codigo)).reduce((s, i) => s + i.valor, 0);

  const executar = useCallback(async () => {
    if (!conn || selecionados.size === 0) return;
    if (modo === "baixar" && tipoLote === "parcela" && (!loteFormaPag || !loteConta)) {
      feedback.showError("Selecione Forma de Pagamento e Conta.");
      return;
    }
    setExecutando(true);
    try {
      let j: any;
      if (tipoLote === "montante") {
        const valorNum = parseNum(montante);
        if (!valorNum || valorNum <= 0) { feedback.showError("Informe o Montante."); setExecutando(false); return; }
        j = await apiSend(conn, `/api/${apiBase}/montante`, "POST", {
          cliente: entidadeCod, vencimentos: Array.from(selecionados), montante: valorNum,
          data_pag: loteDataPag, conta: loteConta, forma_pag: loteFormaPag,
          usuario_alteracao: usuarioCod, classe, plataforma: "web",
        });
      } else {
        j = await apiSend(conn, `/api/${apiBase}/lote`, "POST", {
          modo, vencimentos: Array.from(selecionados),
          data_pag: modo === "baixar" ? loteDataPag : undefined,
          conta: modo === "baixar" ? loteConta : undefined,
          forma_pag: modo === "baixar" ? loteFormaPag : undefined,
          usuario_alteracao: usuarioCod, classe, plataforma: "web",
        });
      }
      if (j?.success) {
        if (tipoLote === "montante") {
          feedback.showSuccess(
            `${j.tocados?.length || 0} parcela(s) baixada(s). Saldo não utilizado: ${formatBRL(j.saldo_nao_utilizado || 0)}`,
            undefined, 5000,
          );
        } else {
          const falhas = j.falhas || [];
          feedback.showSuccess(
            `${j.processados || 0} processado(s)${falhas.length ? `, ${falhas.length} falha(s)` : ""}.`,
            undefined, falhas.length ? 5000 : undefined,
          );
        }
        onDone();
        buscar();
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível executar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setExecutando(false);
    }
  }, [conn, apiBase, modo, tipoLote, selecionados, loteDataPag, loteConta, loteFormaPag, montante, entidadeCod,
      usuarioCod, classe, feedback, onDone, buscar]);

  return (
    <>
      <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={onClose}>
          <Pressable style={[ps.modalCard, isWeb && localStyles.modalCardWebWide]} onPress={(e) => e.stopPropagation()}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Pagamento/Cancelamento em Lote</Text>
              <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>

            <View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm }}>
              {(["baixar", "cancelar"] as const).map((m) => (
                <Pressable key={m} onPress={() => setModo(m)} style={[localStyles.toggleChip, modo === m && localStyles.toggleChipSel]} testID={`lote-modo-${m}`}>
                  <Text style={[localStyles.toggleChipText, modo === m && localStyles.toggleChipTextSel]}>
                    {m === "baixar" ? "Pagamento" : "Cancelamento"}
                  </Text>
                </Pressable>
              ))}
              {permitirMontante && modo === "baixar" ? (["parcela", "montante"] as const).map((t) => (
                <Pressable key={t} onPress={() => setTipoLote(t)} style={[localStyles.toggleChip, tipoLote === t && localStyles.toggleChipSel]} testID={`lote-tipo-${t}`}>
                  <Text style={[localStyles.toggleChipText, tipoLote === t && localStyles.toggleChipTextSel]}>
                    {t === "parcela" ? "Por Parcela" : "Por Montante"}
                  </Text>
                </Pressable>
              )) : null}
            </View>

            <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "flex-end", marginBottom: spacing.sm }}>
              <View style={{ width: 150 }}>
                <Text style={localStyles.fieldLabel}>De</Text>
                <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="lote-data-ini" />
              </View>
              <View style={{ width: 150 }}>
                <Text style={localStyles.fieldLabel}>Até</Text>
                <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="lote-data-fim" />
              </View>
              <View style={{ minWidth: 200 }}>
                <Text style={localStyles.fieldLabel}>{entidadeLabel}{tipoLote === "montante" ? " *" : " (opcional)"}</Text>
                <Pressable onPress={() => setEntidadeSearchOpen(true)} style={localStyles.entidadeBtn} testID="lote-entidade-btn">
                  <Text style={{ color: entidadeNome ? colors.onSurface : colors.muted, fontSize: 13 }}>{entidadeNome || `Buscar ${entidadeLabel.toLowerCase()}…`}</Text>
                </Pressable>
              </View>
              <Pressable onPress={buscar} disabled={buscando} style={localStyles.buscarBtn} testID="lote-buscar-btn">
                {buscando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                  <><Ionicons name="search" size={16} color={colors.brandPrimary} /><Text style={{ color: colors.brandPrimary, fontWeight: "600", fontSize: 13 }}>Buscar</Text></>
                )}
              </Pressable>
            </View>

            {modo === "baixar" ? (
              <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", marginBottom: spacing.sm }}>
                <View style={{ width: 150 }}>
                  <Text style={localStyles.fieldLabel}>Data Pag. *</Text>
                  <WebDateField value={loteDataPag} onChange={(v) => setLoteDataPag(v || null)} testID="lote-data-pag" />
                </View>
                <View style={{ width: 200 }}>
                  <Text style={localStyles.fieldLabel}>Forma de Pagamento *</Text>
                  <SelectField value={loteFormaPag} onChange={(v) => setLoteFormaPag(v as string)} options={formaPagOpts} compactWeb allowClear testID="lote-forma-pag" />
                </View>
                <View style={{ width: 200 }}>
                  <Text style={localStyles.fieldLabel}>Conta *</Text>
                  <SelectField value={loteConta} onChange={(v) => setLoteConta(v == null ? null : Number(v))} options={contasOpts} compactWeb allowClear testID="lote-conta" />
                </View>
                {tipoLote === "montante" ? (
                  <View style={{ width: 150 }}>
                    <Text style={localStyles.fieldLabel}>Montante *</Text>
                    <TextInput value={montante} onChangeText={setMontante} keyboardType="numeric" style={localStyles.input} placeholder="0,00" testID="lote-montante" />
                  </View>
                ) : null}
              </View>
            ) : null}

            {tipoLote === "montante" ? (
              <Text style={localStyles.hint}>
                O valor do Montante é distribuído entre as parcelas marcadas, começando pela mais antiga — se sobrar parte
                do valor numa parcela, ela fica parcialmente paga e o restante vira um novo vencimento em aberto.
              </Text>
            ) : null}

            <View style={localStyles.topBar}>
              <Pressable onPress={marcarTodos} style={localStyles.miniBtn}><Text style={localStyles.miniBtnLabel}>Marcar todos</Text></Pressable>
              <Pressable onPress={desmarcarTodos} style={localStyles.miniBtn}><Text style={localStyles.miniBtnLabel}>Desmarcar todos</Text></Pressable>
              <View style={{ flex: 1 }} />
              <Text style={localStyles.totalText}>{selecionados.size} selecionado(s) · {formatBRL(totalSelecionado)}</Text>
              <Pressable onPress={executar} disabled={executando || selecionados.size === 0} style={[localStyles.execBtn, selecionados.size === 0 && { opacity: 0.5 }]} testID="lote-executar-btn">
                {executando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <Text style={{ color: colors.onBrandPrimary, fontWeight: "700", fontSize: 13 }}>
                    {modo === "baixar" ? "Pagar Selecionados" : "Cancelar Selecionados"}
                  </Text>
                )}
              </Pressable>
            </View>

            <ScrollView style={{ maxHeight: 320 }}>
              {items.length === 0 ? (
                <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.md, textAlign: "center" }}>
                  {buscando ? "Buscando…" : "Nenhum vencimento encontrado."}
                </Text>
              ) : (
                items.map((it) => (
                  <Pressable key={it.codigo} onPress={() => toggleSel(it.codigo)} style={localStyles.itemRow} testID={`lote-item-${it.codigo}`}>
                    <Ionicons name={selecionados.has(it.codigo) ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                    <View style={{ flex: 1, marginLeft: spacing.sm }}>
                      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>
                        {it.cliente_nome || it.fornecedor_nome} · Duplicata #{it.duplicata}/{it.desmembramento}
                      </Text>
                      <Text style={{ fontSize: 11, color: colors.muted }}>
                        {modo === "cancelar" ? `Pago em ${formatDateBR(it.data_pag)}` : `Venc. ${formatDateBR(it.dt_vencimento)}`}
                      </Text>
                    </View>
                    <Text style={{ fontSize: 13, fontWeight: "700", color: colors.onSurface }}>{formatBRL(it.valor)}</Text>
                  </Pressable>
                ))
              )}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {isReceber ? (
        <ClientSearchModal
          visible={entidadeSearchOpen} onClose={() => setEntidadeSearchOpen(false)}
          term={entidadeTerm} setTerm={setEntidadeTerm} loading={entidadeLoading} results={entidadeResults as ClienteRow[]}
          onPick={(c) => { setEntidadeCod(Number(c.codigo)); setEntidadeNome(c.nome); setEntidadeSearchOpen(false); }}
          onCreate={() => setEntidadeSearchOpen(false)}
        />
      ) : (
        <FornecedorSearchModal
          visible={entidadeSearchOpen} onClose={() => setEntidadeSearchOpen(false)}
          term={entidadeTerm} setTerm={setEntidadeTerm} loading={entidadeLoading} results={entidadeResults as FornecedorRow[]}
          onPick={(f) => { setEntidadeCod(Number(f.codigo_int)); setEntidadeNome(f.nome); setEntidadeSearchOpen(false); }}
        />
      )}
    </>
  );
}

const localStyles = {
  modalCardWebWide: {
    width: "100%" as const, maxWidth: 900, alignSelf: "center" as const,
    borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
  },
  toggleChip: {
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  toggleChipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  toggleChipText: { fontSize: 12, fontWeight: "600" as const, color: colors.onSurface },
  toggleChipTextSel: { color: colors.onBrandPrimary },
  fieldLabel: { fontSize: 11, color: colors.muted, marginBottom: 4, fontWeight: "500" as const },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.sm,
    paddingVertical: 10, fontSize: 14, color: colors.onSurface, backgroundColor: colors.surfaceSecondary,
  },
  entidadeBtn: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.sm,
    paddingVertical: 10, backgroundColor: colors.surfaceSecondary, justifyContent: "center" as const,
  },
  buscarBtn: {
    flexDirection: "row" as const, alignItems: "center" as const, gap: 6, borderWidth: 1, borderColor: colors.brandPrimary,
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 10, backgroundColor: colors.surface,
  },
  hint: { fontSize: 11, color: colors.muted, fontStyle: "italic" as const, marginBottom: spacing.sm },
  topBar: {
    flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm, flexWrap: "wrap" as const,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border, marginBottom: spacing.xs,
  },
  miniBtn: {
    paddingHorizontal: spacing.sm, paddingVertical: 6, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
  },
  miniBtnLabel: { fontSize: 12, fontWeight: "600" as const, color: colors.onSurface },
  totalText: { fontSize: 12, fontWeight: "600" as const, color: colors.onSurface },
  execBtn: {
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md,
    paddingVertical: 8, alignItems: "center" as const, justifyContent: "center" as const,
  },
  itemRow: {
    flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
};

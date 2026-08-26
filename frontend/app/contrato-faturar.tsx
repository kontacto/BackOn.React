// Transações > Contratos > Faturar Contratos — migração de
// FrmFatContrato2.frm/FrmFatContrato.frm (Clauwan, achado via .vbp — ver
// CLAUDE.md > "Nunca marcar uma rotina como não implementada..."). Escopo
// desta tela (confirmado com o usuário 2026-07-20): seleção de contratos
// do período com cálculo pró-rata + O.S. vinculada, Faturar (grava
// comanda/Receber/Duplicata_Receber, fiel ao legado) e Gerar Recibo.
// **2026-08-24**: contratos do tipo Nota Fiscal/Boleto ganharam botões
// "Emitir NF-e"/"Emitir NFS-e" — reaproveita o motor de Agrupar Comandas
// (no legado, os dois tipos de cobrança chamam a mesma rotina `EmiteNF`;
// o Boleto em si, arquivo CNAB/layout, já é coberto pela tela "Geração de
// Boletos"). **Nunca automático** — confirmado com o Leandro: "fica a
// critério do cliente se ele vai emitir a nota de produtos ou nota de
// serviços ou ambas ou nenhuma", regra que vale pra qualquer comanda com
// produto+serviço do sistema. Ver PENDENCIAS.md > "Contratos".
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { printHtml, escHtml } from "@/src/utils/printHtml";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

type Conn = Connection;

type ItemFaturar = {
  codigo: number; contrato: string; cliente: number; cliente_nome: string;
  inicio: string | null; fim: string | null; valor_contrato: number; os_fechada: number;
  valor_total: number; os_aberta: number; vencimento: string | null;
  tarifa_cobranca: boolean; cobra_iss: boolean; tipo_doc: string; tipo_cobranca: number; descr_nf: string;
};

type NfEResultado = {
  success: boolean; message?: string; numero?: number; chave_acesso?: string; nota_fisc?: number;
};

type ResultadoFaturar = {
  codigo: number; success: boolean; message?: string; comanda?: number; descreve_os?: string; vencimento?: string | null;
  tipo_doc?: string;
};

const TIPOS_COBRANCA = [
  { codigo: 0, label: "Recibo" },
  { codigo: 1, label: "Nota Fiscal" },
  { codigo: 2, label: "Boleto" },
];

function hojeIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ContratoFaturarScreen() {
  const router = useRouter();
  const { can, moduleOn, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Contratos está disponível apenas no web." testID="contrato-faturar-web-only" />;
  }
  if (!moduleOn("contratos")) {
    return <LockedView title="Módulo desativado" message="O módulo Contratos está desligado em Configurações > Módulos e Recursos." testID="contrato-faturar-module-off" />;
  }
  if (!can("FATURAR_CONTR.ABRIR")) {
    return <LockedView title="Sem permissão" message="Você não tem acesso a esta tela." testID="contrato-faturar-no-perm" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (c) setConn(c);
      setLoadingConn(false);
    })();
  }, [router]);

  const hoje = new Date();
  const [ano, setAno] = useState(String(hoje.getFullYear()));
  const [mes, setMes] = useState(String(hoje.getMonth() + 1));
  const [contratoIni, setContratoIni] = useState("");
  const [contratoFim, setContratoFim] = useState("");
  const [tiposCobranca, setTiposCobranca] = useState<number[]>([0, 1, 2]);
  const [somenteNaoFaturados, setSomenteNaoFaturados] = useState(true);
  const [dataEmissao, setDataEmissao] = useState<string | null>(hojeIso());
  const [mesVenc, setMesVenc] = useState(String(hoje.getMonth() + 1));
  const [anoVenc, setAnoVenc] = useState(String(hoje.getFullYear()));

  const [items, setItems] = useState<ItemFaturar[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [buscando, setBuscando] = useState(false);
  const [faturando, setFaturando] = useState(false);
  const [resultados, setResultados] = useState<ResultadoFaturar[]>([]);
  // Emissão de NF-e/NFS-e — ação SEPARADA e opcional (nunca automática ao
  // faturar, ver comentário no topo do arquivo). Chave = `${codigo}-nfe`
  // ou `${codigo}-nfse` (um contrato pode emitir os dois, um só, ou
  // nenhum — critério do usuário).
  const [emissoes, setEmissoes] = useState<Record<string, NfEResultado>>({});
  const [emitindo, setEmitindo] = useState<string | null>(null);

  // Tooltip dos botões que são só ícone (sem texto ao lado) — hover no web,
  // um só de cada vez. Mesmo padrão de PainelPedidoCard.tsx (`hoverBtn` +
  // `renderTooltip`), regra [GLOBAL] em CLAUDE.md > "Padrões de UI".
  const [hoverBtn, setHoverBtn] = useState<string | null>(null);
  // `below`: o botão de voltar fica colado no topo da tela — um tooltip
  // "acima" do ícone ficaria fora da viewport, invisível.
  const renderTooltip = (key: string, label: string, below = false) =>
    hoverBtn === key ? (
      <View style={[styles.tooltip, below && styles.tooltipBelow]} pointerEvents="none">
        <View style={styles.tooltipInner}>
          <Text style={styles.tooltipText}>{label}</Text>
        </View>
      </View>
    ) : null;

  const toggleTipoCobranca = (codigo: number) => {
    setTiposCobranca((prev) => (prev.includes(codigo) ? prev.filter((t) => t !== codigo) : [...prev, codigo]));
  };

  const selecionar = useCallback(async () => {
    if (!conn) return;
    if (!ano.trim() || !mes.trim() || Number(mes) < 1 || Number(mes) > 12) {
      fb.showError("Defina Ano e Mês de Referência corretamente!");
      return;
    }
    setBuscando(true);
    setResultados([]);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = new URLSearchParams({
        servidor: conn.servidor, banco: conn.banco,
        ano, mes,
        contrato_ini: contratoIni.trim(), contrato_fim: contratoFim.trim(),
        tipos_cobranca: tiposCobranca.join(","),
        somente_nao_faturados: String(somenteNaoFaturados),
        mes_venc: mesVenc || mes, ano_venc: anoVenc || ano,
        data_emissao: dataEmissao || hojeIso(),
      });
      const r = await fetch(`${base}/api/contratos/faturar/listar?${qs.toString()}`);
      const j = await r.json();
      if (j?.success) {
        setItems(j.items || []);
        setSelecionados(new Set((j.items || []).map((i: ItemFaturar) => i.codigo)));
        if (!(j.items || []).length) fb.showError("Nenhum contrato encontrado para o período/filtros informados.");
      } else {
        fb.showError(j?.message || "Falha ao buscar contratos.");
        setItems([]);
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBuscando(false);
    }
  }, [conn, ano, mes, contratoIni, contratoFim, tiposCobranca, somenteNaoFaturados, mesVenc, anoVenc, dataEmissao, fb]);

  const toggleSelecionado = (codigo: number) => {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(codigo)) next.delete(codigo); else next.add(codigo);
      return next;
    });
  };

  const marcarTodos = () => setSelecionados(new Set(items.map((i) => i.codigo)));
  const desmarcarTodos = () => setSelecionados(new Set());

  const totalSelecionado = items.filter((i) => selecionados.has(i.codigo)).reduce((s, i) => s + i.valor_total, 0);

  const faturar = useCallback(() => {
    if (!conn || selecionados.size === 0) return;
    fb.showConfirm(`Faturar ${selecionados.size} contrato(s), totalizando ${formatBRL(totalSelecionado)}?`, async () => {
      setFaturando(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const itens = items
          .filter((i) => selecionados.has(i.codigo))
          .map((i) => ({ codigo: i.codigo, valor_total: i.valor_total, vencimento: i.vencimento, tipo_doc: i.tipo_doc }));
        const r = await fetch(`${base}/api/contratos/faturar`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, ano: Number(ano), mes: Number(mes), itens, master: isMaster }),
        });
        const j = await r.json();
        if (j?.success) {
          const resultados: ResultadoFaturar[] = j.resultados || [];
          setResultados(resultados);
          setEmissoes({});
          const ok = resultados.filter((x) => x.success).length;
          const falhas = resultados.length - ok;
          if (falhas > 0) fb.showError(`${ok} contrato(s) faturado(s), ${falhas} com falha — veja o detalhe na lista.`);
          else fb.showSuccess(`${ok} contrato(s) faturado(s) com sucesso.`);
          await selecionar();
        } else {
          fb.showError(friendlyApiError(j, "Falha ao faturar."));
        }
      } catch (e) {
        fb.showError(friendlyCatchError(e, "Falha ao faturar."));
      } finally {
        setFaturando(false);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, selecionados, items, ano, mes, auditCtx, totalSelecionado, fb, selecionar, isMaster]);

  const [reciboGerando, setReciboGerando] = useState<number | null>(null);

  const gerarRecibo = useCallback(async (res: ResultadoFaturar) => {
    if (!conn || !res.comanda) return;
    setReciboGerando(res.codigo);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/faturar/recibo`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          contrato: res.codigo, comanda: res.comanda, ano_ref: Number(ano), mes_ref: Number(mes),
          descreve_os: res.descreve_os || "",
        }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Falha ao gerar recibo."); return; }
      const html = `
        <div class="center bold" style="font-size:20px;margin-bottom:12px;">Recibo de Pagamento Nº ${escHtml(j.numero)}</div>
        <p>Recebemos de <b>${escHtml(j.recebemos)}</b>.</p>
        <p>A importância de <b>R$ ${escHtml(formatBRL(j.valor))}</b> (${escHtml(j.valor_extenso)}).</p>
        <p>Referente à ${escHtml(j.referente)}</p>
        <p style="margin-top:24px;">${escHtml(formatDateBR(j.data))}</p>
        <p style="margin-top:48px;text-align:center;">____________________________________<br/>${escHtml(j.assinatura)}</p>
      `;
      printHtml(html, `Recibo ${j.numero}`);
      fb.showSuccess(`Recibo ${j.numero} gerado.`);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setReciboGerando(null);
    }
  }, [conn, ano, mes, auditCtx, fb]);

  // Emitir NF-e (produto) ou NFS-e (serviço) — ação sempre separada e
  // opcional (nunca automática, confirmado com o Leandro: "fica a
  // critério do cliente se ele vai emitir a nota de produtos ou nota de
  // serviços ou ambas ou nenhuma"). Reaproveita o mesmo motor de Agrupar
  // Comandas já usado em Gestor Fiscal.
  const emitirDocumento = useCallback(async (res: ResultadoFaturar, tipo: "nfe" | "nfse") => {
    if (!conn || !res.comanda) return;
    const chave = `${res.codigo}-${tipo}`;
    setEmitindo(chave);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/faturar/emitir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, tipo, comanda: res.comanda, master: isMaster }),
      });
      const j = await r.json();
      setEmissoes((cur) => ({ ...cur, [chave]: j }));
      if (j?.success) fb.showSuccess(`${tipo === "nfe" ? "NF-e" : "NFS-e"} nº ${j.numero} emitida.`);
      else fb.showError(friendlyApiError(j, `Falha ao emitir ${tipo === "nfe" ? "NF-e" : "NFS-e"}.`));
    } catch (e) {
      fb.showError(friendlyCatchError(e, `Falha ao emitir ${tipo === "nfe" ? "NF-e" : "NFS-e"}.`));
    } finally {
      setEmitindo(null);
    }
  }, [conn, auditCtx, isMaster, fb]);

  if (loadingConn) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contrato-faturar-screen">
      <View style={styles.header}>
        <View style={[styles.headerActionWrap, hoverBtn === "voltar" && styles.wrapHovered]}>
          <Pressable
            onPress={() => router.back()}
            onHoverIn={() => setHoverBtn("voltar")}
            onHoverOut={() => setHoverBtn(null)}
            hitSlop={12}
            style={styles.back}
            testID="cf-voltar"
          >
            <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
          </Pressable>
          {renderTooltip("voltar", "Voltar", true)}
        </View>
        <Text style={styles.headerTitle}>Faturar Contratos</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.shell}>
          <View style={styles.filterCard}>
            <Text style={styles.sectionTitle}>Referência do Faturamento</Text>
            <Text style={styles.helpText}>
              Escolha o mês/ano que está sendo cobrado (Mês/Ano) e clique em "Selecionar" para ver os
              contratos daquele período. O valor de contratos que começaram ou terminaram no meio do
              mês é calculado proporcionalmente aos dias — você não precisa ajustar isso na mão.
            </Text>
            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Mês</Text>
                <TextInput value={mes} onChangeText={setMes} keyboardType="number-pad" maxLength={2} style={styles.input} testID="cf-mes" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Ano</Text>
                <TextInput value={ano} onChangeText={setAno} keyboardType="number-pad" maxLength={4} style={styles.input} testID="cf-ano" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Contrato Inicial</Text>
                <TextInput value={contratoIni} onChangeText={setContratoIni} style={styles.input} testID="cf-contrato-ini" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Contrato Final</Text>
                <TextInput value={contratoFim} onChangeText={setContratoFim} style={styles.input} testID="cf-contrato-fim" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Data de Emissão</Text>
                <WebDateField value={dataEmissao} onChange={(v) => setDataEmissao(v || hojeIso())} testID="cf-data-emissao" />
              </View>
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Mês Venc.</Text>
                <TextInput value={mesVenc} onChangeText={setMesVenc} keyboardType="number-pad" maxLength={2} style={styles.input} testID="cf-mes-venc" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Ano Venc.</Text>
                <TextInput value={anoVenc} onChangeText={setAnoVenc} keyboardType="number-pad" maxLength={4} style={styles.input} testID="cf-ano-venc" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Tipo de Cobrança</Text>
                <View style={styles.chipsRow}>
                  {TIPOS_COBRANCA.map((t) => (
                    <Pressable
                      key={t.codigo}
                      onPress={() => toggleTipoCobranca(t.codigo)}
                      style={[styles.chip, tiposCobranca.includes(t.codigo) && styles.chipSel]}
                      testID={`cf-tipo-${t.codigo}`}
                    >
                      <Text style={[styles.chipText, tiposCobranca.includes(t.codigo) && styles.chipTextSel]}>{t.label}</Text>
                    </Pressable>
                  ))}
                  <Pressable
                    onPress={() => setSomenteNaoFaturados((v) => !v)}
                    style={[styles.chip, somenteNaoFaturados && styles.chipSel]}
                    testID="cf-nao-faturados"
                  >
                    <Text style={[styles.chipText, somenteNaoFaturados && styles.chipTextSel]}>Contratos não faturados</Text>
                  </Pressable>
                </View>
                <Text style={styles.helpText}>
                  "Tipo de Cobrança" filtra pela forma combinada com o cliente (Recibo, Nota Fiscal ou
                  Boleto) — mantenha todos marcados para ver todos. "Contratos não faturados" esconde
                  quem já foi faturado neste mesmo mês/ano, evitando cobrar duas vezes por engano.
                </Text>
              </View>
            </View>
            <Pressable onPress={selecionar} disabled={buscando} style={[styles.actionBtn, styles.actionBtnPrimary]} testID="cf-selecionar">
              {buscando ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.actionBtnPrimaryText}>Selecionar</Text>}
            </Pressable>
          </View>

          {items.length > 0 && (
            <View style={styles.filterCard}>
              <View style={styles.rowBetween}>
                <Text style={styles.sectionTitle}>Contratos Selecionados ({items.length})</Text>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <Pressable onPress={marcarTodos} style={styles.linkBtn}><Text style={styles.linkBtnText}>Marcar Todas</Text></Pressable>
                  <Pressable onPress={desmarcarTodos} style={styles.linkBtn}><Text style={styles.linkBtnText}>Desmarcar Todas</Text></Pressable>
                </View>
              </View>
              <Text style={styles.helpText}>
                O valor de cada contrato já vem calculado proporcionalmente aos dias do período (se o
                contrato começou ou terminou no meio do mês, o valor é ajustado). Quando o contrato
                também fatura Ordens de Serviço, "O.S. Fechada" já está somada ao valor total — "O.S.
                Aberta" é só um aviso, ainda não é cobrada porque o serviço não foi concluído.
              </Text>
              {items.map((it) => (
                <View key={it.codigo} style={styles.gridRow} testID={`cf-item-${it.codigo}`}>
                  <View style={[styles.cardActionWrap, hoverBtn === `sel-${it.codigo}` && styles.wrapHovered]}>
                    <Pressable
                      onPress={() => toggleSelecionado(it.codigo)}
                      onHoverIn={() => setHoverBtn(`sel-${it.codigo}`)}
                      onHoverOut={() => setHoverBtn(null)}
                      hitSlop={8}
                      testID={`cf-sel-${it.codigo}`}
                    >
                      <Ionicons name={selecionados.has(it.codigo) ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                    </Pressable>
                    {renderTooltip(`sel-${it.codigo}`, selecionados.has(it.codigo) ? "Remover da seleção" : "Incluir na seleção")}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowTitle}>#{it.contrato} · {it.cliente_nome} · {it.tipo_doc}</Text>
                    <Text style={styles.gridRowSub}>
                      {it.inicio ? formatDateBR(it.inicio) : "—"} a {it.fim ? formatDateBR(it.fim) : "—"} · Venc. {it.vencimento ? formatDateBR(it.vencimento) : "—"}
                      {it.os_fechada > 0 ? ` · O.S. Fechada: ${formatBRL(it.os_fechada)}` : ""}
                      {it.os_aberta > 0 ? ` · O.S. Aberta: ${formatBRL(it.os_aberta)}` : ""}
                    </Text>
                  </View>
                  <Text style={styles.gridRowValor}>{formatBRL(it.valor_total)}</Text>
                </View>
              ))}
              <View style={styles.divider} />
              <View style={styles.rowBetween}>
                <Text style={styles.totalLabel}>Total Selecionado ({selecionados.size})</Text>
                <Text style={styles.totalValor}>{formatBRL(totalSelecionado)}</Text>
              </View>
              <Pressable
                onPress={faturar}
                disabled={faturando || selecionados.size === 0 || !can("FATURAR_CONTR.FATURAR")}
                style={[styles.actionBtn, styles.actionBtnPrimary, { marginTop: spacing.md }]}
                testID="cf-faturar"
              >
                {faturando ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.actionBtnPrimaryText}>Faturar Selecionados</Text>}
              </Pressable>
              <Text style={styles.helpText}>
                "Faturar Selecionados" grava o lançamento definitivo em contas a receber para cada
                contrato marcado — não é uma simulação. Confira o total antes de confirmar.
              </Text>
            </View>
          )}

          {resultados.length > 0 && (
            <View style={styles.filterCard}>
              <Text style={styles.sectionTitle}>Resultado do Faturamento</Text>
              <Text style={styles.helpText}>
                Contratos com erro não foram lançados — corrija o motivo indicado e fature esse
                contrato de novo depois. "Gerar Recibo" imprime o comprovante de contratos do tipo
                Recibo. Contratos Nota Fiscal/Boleto NÃO emitem nada automaticamente — use os botões
                "Emitir NF-e"/"Emitir NFS-e" pra decidir se emite a nota de produtos, a de serviços,
                as duas, ou nenhuma; o faturamento (dinheiro em Contas a Receber) já ficou lançado
                independente dessa escolha.
              </Text>
              {resultados.map((r) => {
                const podeEmitir = r.success && (r.tipo_doc === "N" || r.tipo_doc === "B");
                const nfe = emissoes[`${r.codigo}-nfe`];
                const nfse = emissoes[`${r.codigo}-nfse`];
                return (
                  <View key={r.codigo} style={styles.gridRow} testID={`cf-resultado-${r.codigo}`}>
                    <Ionicons name={r.success ? "checkmark-circle" : "close-circle"} size={20} color={r.success ? colors.success : colors.error} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowTitle}>Contrato #{r.codigo}</Text>
                      <Text style={[styles.gridRowSub, !r.success && { color: colors.error }]}>
                        {r.success ? `Faturado — comanda ${r.comanda}` : r.message}
                      </Text>
                      {nfe ? (
                        <Text style={[styles.gridRowSub, { color: nfe.success ? colors.success : colors.error }]}>
                          {nfe.success ? `NF-e emitida — nº ${nfe.numero}` : `Falha ao emitir NF-e: ${nfe.message || "erro desconhecido"}`}
                        </Text>
                      ) : null}
                      {nfse ? (
                        <Text style={[styles.gridRowSub, { color: nfse.success ? colors.success : colors.error }]}>
                          {nfse.success ? `NFS-e emitida — nº ${nfse.numero}` : `Falha ao emitir NFS-e: ${nfse.message || "erro desconhecido"}`}
                        </Text>
                      ) : null}
                    </View>
                    <View style={{ flexDirection: "row", gap: spacing.xs }}>
                      {r.success && r.tipo_doc === "R" && can("FATURAR_CONTR.RECIBO") ? (
                        <Pressable onPress={() => gerarRecibo(r)} disabled={reciboGerando === r.codigo} style={styles.linkBtn} testID={`cf-recibo-${r.codigo}`}>
                          {reciboGerando === r.codigo ? <ActivityIndicator size="small" /> : <Text style={styles.linkBtnText}>Gerar Recibo</Text>}
                        </Pressable>
                      ) : null}
                      {podeEmitir && can("FATURAR_CONTR.EMITIR_NF") ? (
                        <>
                          <Pressable onPress={() => emitirDocumento(r, "nfe")} disabled={emitindo === `${r.codigo}-nfe` || nfe?.success} style={styles.linkBtn} testID={`cf-emitir-nfe-${r.codigo}`}>
                            {emitindo === `${r.codigo}-nfe` ? <ActivityIndicator size="small" /> : <Text style={styles.linkBtnText}>{nfe?.success ? "NF-e emitida" : "Emitir NF-e"}</Text>}
                          </Pressable>
                          <Pressable onPress={() => emitirDocumento(r, "nfse")} disabled={emitindo === `${r.codigo}-nfse` || nfse?.success} style={styles.linkBtn} testID={`cf-emitir-nfse-${r.codigo}`}>
                            {emitindo === `${r.codigo}-nfse` ? <ActivityIndicator size="small" /> : <Text style={styles.linkBtnText}>{nfse?.success ? "NFS-e emitida" : "Emitir NFS-e"}</Text>}
                          </Pressable>
                        </>
                      ) : null}
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerSpacer: { width: 40 },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  headerActionWrap: { position: "relative" },
  // Wrapper com position:relative pra ancorar o tooltip absoluto de um
  // botão-ícone — mesmo padrão de PainelPedidoCard.tsx.
  cardActionWrap: { position: "relative" },
  // Eleva o wrap (e seu tooltip absoluto) por cima dos irmãos seguintes —
  // sem isso, o tooltip ficava visualmente atrás do próximo elemento por
  // causa da ordem no DOM. Só aplicado enquanto o tooltip está visível.
  wrapHovered: { zIndex: 20 },
  tooltip: {
    position: "absolute", bottom: "100%", left: 0, right: 0, marginBottom: 4,
    alignItems: "center", zIndex: 10,
  },
  tooltipInner: {
    backgroundColor: "#1a1a1a", borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 4,
  },
  tooltipText: { color: "#fff", fontSize: 11, fontWeight: "600" },
  // Texto de ajuda em linguagem de usuário final, explicando campos/ações
  // não-óbvias desta tela — regra [GLOBAL] em CLAUDE.md > "Padrões de UI"
  // > "Telas complexas".
  helpText: { fontSize: 11, color: colors.muted, lineHeight: 15, marginTop: 2 },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  shell: WEB_CONTENT_SHELL,
  filterCard: { ...WEB_FILTER_CARD, marginBottom: spacing.md, gap: spacing.sm },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "flex-end" },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  colTiny: { width: 70 },
  colNarrow: { width: 140 },
  colFlex: { flex: 1, minWidth: 220 },
  label: { fontSize: 11, color: colors.muted, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 13, color: colors.onSurface },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, color: colors.onSurface },
  chipTextSel: { color: "#fff", fontWeight: "600" },
  actionBtn: { paddingVertical: 10, paddingHorizontal: spacing.lg, borderRadius: radius.md, alignItems: "center", alignSelf: "flex-start" },
  actionBtnPrimary: { backgroundColor: colors.brandPrimary },
  actionBtnPrimaryText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  linkBtn: { paddingVertical: 6, paddingHorizontal: spacing.sm },
  linkBtnText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "600" },
  gridRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  gridRowTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  gridRowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  gridRowValor: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.sm },
  totalLabel: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  totalValor: { fontSize: 16, fontWeight: "800", color: colors.brandPrimary },
});

// Agrupar Comandas em NF-e — migração de `Geral\FrmSelComandas.frm`
// (seleção de comandas) + o caminho de agrupamento de
// `NFe\FrmTraImpNFE.frm` (emissão real, modelo 55). Ver
// `backend/services/nfe_agrupada_service.py` e PENDENCIAS.md > "Agrupar
// Comandas em NF-e" pro racional completo (achados da fonte, 4 decisões
// de negócio confirmadas com o usuário).
//
// Seleciona 2+ (ou só 1 — "1 comanda é só o caso degenerado de lista de
// 1", mesmo achado da fonte) comandas FATURADAS do MESMO cliente e emite
// 1 única NF-e (modelo 55) cobrindo os itens de produto consolidados
// (soma automática por código+preço, exceto item com controle de número
// de série). Data de emissão é sempre hoje; rastreabilidade fica só em
// nível de comanda (não de quantidade) — decisões explícitas do usuário,
// replicando o legado.
import { useCallback, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { ClienteRow } from "@/src/components/pedido/types";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { showApoioFiscalError } from "@/src/utils/apoioFiscal";
import ApoioFiscalBackOnModal, { ApoioFiscalInfo } from "@/src/components/ApoioFiscalBackOnModal";
import { formatBRL } from "@/src/utils/format";
import { fetchEmpresaHeader } from "@/src/utils/print-report-header";
import { printFullHtml } from "@/src/utils/printHtml";
import { buildDanfeHtml } from "@/src/utils/danfeFacsimile";

function brDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}

type ComandaAgrupavel = {
  comanda: number;
  data: string | null;
  valor_venda: number;
  tem_nfce: boolean;
  ja_tem_nfe: boolean;
  ja_tem_nfse: boolean;
  tem_item_produto: boolean;
  tem_item_servico: boolean;
};

const NFE_AGRUPADA_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Selecionar Cliente",
    texto: "Busque o cliente cujas comandas faturadas você quer agrupar numa única NF-e. Só comandas do mesmo cliente podem entrar no mesmo agrupamento.",
    icon: { lib: "ion", name: "search-outline" },
  },
  {
    titulo: "Por que os itens são somados",
    texto: "Quando duas comandas selecionadas têm o mesmo produto pelo mesmo preço, a quantidade é somada numa única linha da nota — assim como o sistema antigo já fazia. Depois de emitida, não é mais possível saber exatamente quanto veio de qual comanda, só que aquela comanda entrou nesta NF-e.",
    icon: { lib: "ion", name: "layers-outline" },
  },
  {
    titulo: "Data de emissão",
    texto: "A NF-e agrupada sempre sai com a data de hoje, não a data original de cada venda.",
    icon: { lib: "ion", name: "calendar-outline" },
  },
  {
    titulo: "Cliente sem endereço cadastrado",
    texto: "Diferente da NFC-e, uma NF-e exige o endereço completo do cliente (comercial, se for empresa). Se faltar, a emissão é bloqueada até completar o cadastro do cliente.",
    icon: { lib: "ion", name: "alert-circle-outline" },
    cor: colors.warning,
  },
  {
    titulo: "Comanda já com NFC-e",
    texto: "Comandas que já têm uma NFC-e emitida ainda podem ser agrupadas numa NF-e, mas isso gera dois documentos fiscais cobrindo a mesma venda — confira com cuidado antes de confirmar.",
    icon: { lib: "ion", name: "warning-outline" },
    cor: colors.warning,
  },
  {
    titulo: "Emitir NF-e de Produtos / Emitir NFS-e de Serviços",
    texto: "São 2 ações fiscais independentes sobre a mesma seleção de comandas — marque uma, outra, ou as duas. A NF-e cobre só os itens de PRODUTO das comandas marcadas; a NFS-e cobre só os itens de SERVIÇO. Uma comanda com produto e serviço pode entrar nas duas emissões ao mesmo tempo, cada documento pegando só a parte que é dele. Ação irreversível — para desfazer depois, é preciso cancelar o documento fiscal.",
    icon: { lib: "ion", name: "receipt-outline" },
    cor: colors.brandPrimary,
  },
  {
    titulo: "Frete por Conta",
    texto: "Define quem é responsável pelo transporte da mercadoria — vai direto no XML da NF-e (campo obrigatório do SEFAZ). Só se aplica à NF-e de produtos. Se não escolher nada, a nota sai como \"Emitente (CIF)\".",
    icon: { lib: "ion", name: "car-outline" },
  },
];

// "Frete por conta" — grava em n_fiscal.paga_frete (smallint), traduzido
// pro código real <modFrete> na emissão (ver
// nfe_emissao_service._resolver_mod_frete). Réplica do seletor real do
// legado (`opFrete`, FrmTraImpNFE.frm) — achado 2026-08-21.
const OPCOES_PAGA_FRETE: SelectOption[] = [
  { value: "1", label: "Emitente (CIF)" },
  { value: "2", label: "Destinatário (FOB)" },
  { value: "3", label: "Terceiros" },
  { value: "4", label: "Próprio Remetente" },
  { value: "5", label: "Próprio Destinatário" },
  { value: "6", label: "Sem Transporte" },
];

export default function NfeAgrupadaScreen() {
  const router = useRouter();
  const { can, isMaster, classe, usuarioCodigo } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Gerar Nfe Comanda está disponível apenas no web." testID="nfe-agrupada-web-only" />;
  }

  const canAbrir = can("NFE_AGRUPADA.ABRIR") || isMaster;
  const canGravar = can("NFE_AGRUPADA.GRAVAR") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [emitindo, setEmitindo] = useState(false);
  const [itens, setItens] = useState<ComandaAgrupavel[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [ajudaVisivel, setAjudaVisivel] = useState(false);
  const [pagaFrete, setPagaFrete] = useState<string | null>(null);
  // 2 ações fiscais independentes — decisão direta do usuário (Leandro,
  // 2026-08-21): "emitir NF-e de produtos" e "emitir NFS-e de serviços"
  // são escolhas separadas, o usuário marca uma, outra, as duas, ou
  // nenhuma (nenhuma = simplesmente não clicar em Emitir).
  const [desejaNfe, setDesejaNfe] = useState(true);
  const [desejaNfse, setDesejaNfse] = useState(false);
  type ResultadoDoc = { chave_acesso: string; protocolo_sefaz: string | null; nota_fisc: number } | null;
  const [resultadoNfe, setResultadoNfe] = useState<ResultadoDoc>(null);
  const [resultadoNfse, setResultadoNfse] = useState<ResultadoDoc>(null);
  const [apoioFiscalInfo, setApoioFiscalInfo] = useState<ApoioFiscalInfo | null>(null);
  const resultado = resultadoNfe || resultadoNfse; // usado só pra decidir se o modal abre
  const [baixandoDanfe, setBaixandoDanfe] = useState(false);

  const [clienteSearchOpen, setClienteSearchOpen] = useState(false);
  const [clienteSearchTerm, setClienteSearchTerm] = useState("");
  const [clienteSearchLoading, setClienteSearchLoading] = useState(false);
  const [clienteSearchResults, setClienteSearchResults] = useState<ClienteRow[]>([]);

  const apiUrl = useCallback((path: string) => `${(conn?.api || "").replace(/\/+$/, "")}${path}`, [conn]);

  const ensureConn = useCallback(async (): Promise<Connection | null> => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
    if (c) setConn(c);
    return c;
  }, [conn, router]);

  const abrirBuscaCliente = async () => {
    await ensureConn();
    setClienteSearchTerm("");
    setClienteSearchResults([]);
    setClienteSearchOpen(true);
  };

  const buscarClientes = useCallback(async (termo: string) => {
    const c = await ensureConn();
    if (!c) return;
    setClienteSearchLoading(true);
    try {
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&term=${encodeURIComponent(termo)}`;
      const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/clientes/find/search?${qs}`);
      const j = await r.json();
      setClienteSearchResults(j?.items || []);
    } catch {
      setClienteSearchResults([]);
    } finally {
      setClienteSearchLoading(false);
    }
  }, [ensureConn]);

  const carregarComandas = useCallback(async (cli: ClienteRow) => {
    const c = await ensureConn();
    if (!c) return;
    setLoading(true);
    setSelecionados(new Set());
    try {
      const r = await fetch(apiUrl("/api/nfe-agrupada/comandas"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: c.servidor, banco: c.banco, cliente: cli.codigo, classe, master: isMaster }),
      });
      const j = await r.json();
      if (j?.success) setItens(j.itens || []);
      else { fb.showError(friendlyApiError(j, "Não foi possível consultar as comandas.")); setItens([]); }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
      setItens([]);
    } finally {
      setLoading(false);
    }
  }, [ensureConn, apiUrl, classe, isMaster, fb]);

  const selecionarCliente = (c: ClienteRow) => {
    setCliente(c);
    setClienteSearchOpen(false);
    carregarComandas(c);
  };

  const elegivel = (it: ComandaAgrupavel) => {
    const okProduto = desejaNfe && it.tem_item_produto && !it.ja_tem_nfe;
    const okServico = desejaNfse && it.tem_item_servico && !it.ja_tem_nfse;
    return okProduto || okServico;
  };

  const toggleSelecionado = (comanda: number) => {
    setSelecionados((cur) => {
      const next = new Set(cur);
      if (next.has(comanda)) next.delete(comanda); else next.add(comanda);
      return next;
    });
  };

  const elegiveis = itens.filter(elegivel);
  const todosSelecionados = elegiveis.length > 0 && selecionados.size === elegiveis.length;
  const alternarTodos = () => {
    setSelecionados(todosSelecionados ? new Set() : new Set(elegiveis.map((it) => it.comanda)));
  };

  const valorTotalSelecionado = itens
    .filter((it) => selecionados.has(it.comanda))
    .reduce((soma, it) => soma + it.valor_venda, 0);

  const emitir = async () => {
    if (!conn || !cliente || selecionados.size === 0) return;
    if (!desejaNfe && !desejaNfse) {
      fb.showError("Marque ao menos uma ação: Emitir NF-e de Produtos e/ou Emitir NFS-e de Serviços.");
      return;
    }
    setEmitindo(true);
    try {
      const body = {
        servidor: conn.servidor, banco: conn.banco, comandas: Array.from(selecionados),
        usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
        paga_frete: pagaFrete ? Number(pagaFrete) : null,
        emitir_nfe: desejaNfe, emitir_nfse: desejaNfse,
      };
      const r = await fetch(apiUrl("/api/nfe-agrupada/emitir"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      const rNfe = j?.resultado_nfe;
      const rNfse = j?.resultado_nfse;
      if (rNfe?.success) setResultadoNfe({ chave_acesso: rNfe.chave_acesso, protocolo_sefaz: rNfe.protocolo_sefaz, nota_fisc: rNfe.nota_fisc });
      if (rNfse?.success) setResultadoNfse({ chave_acesso: rNfse.chave_acesso, protocolo_sefaz: rNfse.protocolo_sefaz, nota_fisc: rNfse.nota_fisc });
      // Apoio Fiscal BackOn — cada resultado (NF-e/NFS-e) roda em sua
      // própria emissão, então o `apoio_fiscal` (quando houver) vem
      // aninhado dentro de `resultado_nfe`/`resultado_nfse`, nunca no `j`
      // de nível superior. Prioriza o primeiro que rejeitou com tradução —
      // caso raro dos dois falharem ao mesmo tempo, mostra só o 1º.
      const falhaComApoioFiscal = (!rNfe?.success && rNfe?.apoio_fiscal) ? rNfe
        : (!rNfse?.success && rNfse?.apoio_fiscal) ? rNfse : null;
      if (j?.success) {
        fb.showSuccess(j.message || "Documento(s) fiscal(is) emitido(s).", undefined, 5000);
      } else if (falhaComApoioFiscal) {
        const info = showApoioFiscalError(fb, falhaComApoioFiscal, "Não foi possível emitir.", 5000);
        if (info) setApoioFiscalInfo(info);
      } else if (rNfe?.success || rNfse?.success) {
        // sucesso parcial — uma das 2 ações deu certo, a outra não; nada
        // foi perdido (cada emissão roda em transação própria), mas o
        // usuário precisa saber qual falhou.
        fb.showWarning(j?.message || "Uma das ações não foi concluída — confira o resultado.", undefined, 5000);
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível emitir."), undefined, 5000);
      }
      if (rNfe?.success || rNfse?.success) carregarComandas(cliente);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setEmitindo(false);
    }
  };

  const baixarDanfe = async () => {
    if (!conn || !resultadoNfe?.nota_fisc) return;
    setBaixandoDanfe(true);
    try {
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(apiUrl(`/api/notas-fiscais/${resultadoNfe.nota_fisc}/danfe?${qs}`));
      const j = await r.json();
      if (!j?.success) { fb.showWarning(friendlyApiError(j, "Não foi possível gerar o DANFE.")); return; }
      const empresa = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
      printFullHtml(buildDanfeHtml(empresa, j.detalhe, j.modelo_danfe));
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setBaixandoDanfe(false);
    }
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Gerar Nfe Comanda." testID="nfe-agrupada-no-perm" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="nfe-agrupada-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Gerar Nfe Comanda</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
          size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="nfe-agrupada-ajuda"
        />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <AccordionSection title="Cliente" defaultExpanded testID="nfe-agrupada-cliente-section">
              {cliente ? (
                <View style={styles.clienteRow}>
                  <Ionicons name="person-circle-outline" size={22} color={colors.brandPrimary} />
                  <Text style={styles.clienteNome} numberOfLines={1}>{cliente.nome}</Text>
                  <Pressable onPress={abrirBuscaCliente} testID="nfe-agrupada-trocar-cliente">
                    <Text style={styles.trocarText}>Trocar</Text>
                  </Pressable>
                </View>
              ) : (
                <Pressable onPress={abrirBuscaCliente} style={styles.selecionarClienteBtn} testID="nfe-agrupada-selecionar-cliente">
                  <Ionicons name="search" size={18} color="#fff" />
                  <Text style={styles.selecionarClienteText}>Selecionar Cliente</Text>
                </Pressable>
              )}
            </AccordionSection>
          </View>

          {cliente ? (
            <View style={styles.card}>
              {loading ? (
                <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
              ) : itens.length === 0 ? (
                <Text style={styles.hint}>Nenhuma comanda faturada encontrada para este cliente.</Text>
              ) : (
                <>
                  <Pressable onPress={alternarTodos} style={styles.selectAllRow} testID="nfe-agrupada-selecionar-todos">
                    <Ionicons name={todosSelecionados ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                    <Text style={styles.checkLabel}>Selecionar todas as elegíveis ({elegiveis.length})</Text>
                  </Pressable>
                  {itens.map((it, idx) => {
                    const podeSelecionar = elegivel(it);
                    return (
                      <View
                        key={it.comanda}
                        style={[styles.itemRow, !podeSelecionar && styles.itemRowDisabled, { zIndex: itens.length - idx }]}
                        testID={`nfe-agrupada-item-${it.comanda}`}
                      >
                        <Pressable
                          onPress={() => podeSelecionar && toggleSelecionado(it.comanda)}
                          hitSlop={8}
                          disabled={!podeSelecionar}
                          testID={`nfe-agrupada-check-${it.comanda}`}
                        >
                          <Ionicons
                            name={selecionados.has(it.comanda) ? "checkbox" : "square-outline"}
                            size={20}
                            color={podeSelecionar ? colors.brandPrimary : colors.muted}
                          />
                        </Pressable>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.gridRowText}>
                            CMD #{it.comanda} · {brDate(it.data)} · <Text style={{ fontWeight: "700" }}>{formatBRL(it.valor_venda)}</Text>
                          </Text>
                          <Text style={styles.hint}>
                            {it.tem_item_produto ? (it.ja_tem_nfe ? "Já tem NF-e" : "Tem produto") : "Sem produto"}
                            {" · "}
                            {it.tem_item_servico ? (it.ja_tem_nfse ? "Já tem NFS-e" : "Tem serviço") : "Sem serviço"}
                            {it.tem_nfce ? " · Já tem NFC-e emitida (agrupar gera duplicidade de imposto)" : null}
                          </Text>
                        </View>
                      </View>
                    );
                  })}
                </>
              )}
            </View>
          ) : null}

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>O que emitir</Text>
            <Text style={styles.hint}>São 2 ações fiscais independentes — marque uma, outra, ou as duas.</Text>
            <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.sm, flexWrap: "wrap" }}>
              <Pressable onPress={() => setDesejaNfe((v) => !v)} style={styles.checkOptionRow} testID="nfe-agrupada-check-nfe">
                <Ionicons name={desejaNfe ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>Emitir NF-e de Produtos</Text>
              </Pressable>
              <Pressable onPress={() => setDesejaNfse((v) => !v)} style={styles.checkOptionRow} testID="nfe-agrupada-check-nfse">
                <Ionicons name={desejaNfse ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>Emitir NFS-e de Serviços</Text>
              </Pressable>
            </View>
          </View>

          {selecionados.size > 0 ? (
            <View style={styles.bulkBar} testID="nfe-agrupada-bulk-bar">
              <View>
                <Text style={styles.bulkBarLabel}>{selecionados.size} comanda{selecionados.size === 1 ? "" : "s"} selecionada{selecionados.size === 1 ? "" : "s"}</Text>
                <Text style={styles.hint}>Total: {formatBRL(valorTotalSelecionado)}</Text>
              </View>
              {desejaNfe ? (
                <View style={{ minWidth: 180 }}>
                  <Text style={styles.fieldLabel}>Frete por Conta (NF-e)</Text>
                  <SelectField
                    value={pagaFrete} onChange={(v) => setPagaFrete(v as string)} options={OPCOES_PAGA_FRETE}
                    compactWeb placeholder="Emitente (CIF)" testID="nfe-agrupada-paga-frete"
                  />
                </View>
              ) : null}
              {canGravar ? (
                <Pressable onPress={emitir} disabled={emitindo || (!desejaNfe && !desejaNfse)} style={styles.bulkBtn} testID="nfe-agrupada-emitir">
                  {emitindo ? <ActivityIndicator color="#fff" size="small" /> : (
                    <><Ionicons name="receipt-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>
                      {desejaNfe && desejaNfse ? "Emitir NF-e + NFS-e" : desejaNfse ? "Emitir NFS-e" : "Emitir NF-e"}
                    </Text></>
                  )}
                </Pressable>
              ) : null}
            </View>
          ) : null}
        </View>
      </ScrollView>

      <AppModal visible={!!resultado} transparent animationType="fade" onRequestClose={() => { setResultadoNfe(null); setResultadoNfse(null); }}>
        <Pressable style={styles.modalBg} onPress={() => { setResultadoNfe(null); setResultadoNfse(null); }}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Documento(s) fiscal(is) emitido(s)</Text>
              <Pressable onPress={() => { setResultadoNfe(null); setResultadoNfse(null); }} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {resultadoNfe ? (
              <View style={{ marginBottom: spacing.md }}>
                <Text style={styles.sectionTitle}>NF-e de Produtos</Text>
                <Text style={styles.hint}>Nota fiscal nº {resultadoNfe.nota_fisc}</Text>
                <Text style={styles.hint}>Protocolo SEFAZ: {resultadoNfe.protocolo_sefaz}</Text>
                <Text style={[styles.hint, { marginTop: spacing.sm }]}>Chave de acesso:</Text>
                <Text selectable style={styles.chaveAcesso}>{resultadoNfe.chave_acesso}</Text>
                <Pressable onPress={baixarDanfe} disabled={baixandoDanfe} style={[styles.bulkBtn, { marginTop: spacing.md, alignSelf: "flex-start" }, baixandoDanfe && { opacity: 0.7 }]} testID="nfe-agrupada-danfe">
                  {baixandoDanfe ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.bulkBtnText}>Baixar DANFE</Text>}
                </Pressable>
              </View>
            ) : null}
            {resultadoNfse ? (
              <View>
                <Text style={styles.sectionTitle}>NFS-e de Serviços</Text>
                <Text style={styles.hint}>Nota fiscal nº {resultadoNfse.nota_fisc}</Text>
                <Text style={[styles.hint, { marginTop: spacing.sm }]}>Chave de acesso:</Text>
                <Text selectable style={styles.chaveAcesso}>{resultadoNfse.chave_acesso}</Text>
              </View>
            ) : null}
          </Pressable>
        </Pressable>
      </AppModal>

      <ClientSearchModal
        visible={clienteSearchOpen}
        onClose={() => setClienteSearchOpen(false)}
        term={clienteSearchTerm}
        setTerm={(v) => { setClienteSearchTerm(v); buscarClientes(v); }}
        loading={clienteSearchLoading}
        results={clienteSearchResults}
        onPick={selecionarCliente}
        onCreate={() => setClienteSearchOpen(false)}
      />

      <AjudaPedidoModal visible={ajudaVisivel} onClose={() => setAjudaVisivel(false)} titulo="Gerar Nfe Comanda" itens={NFE_AGRUPADA_AJUDA_ITENS} />
      <ApoioFiscalBackOnModal visible={!!apoioFiscalInfo} info={apoioFiscalInfo} onClose={() => setApoioFiscalInfo(null)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm, zIndex: 100 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },

  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },

  clienteRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  clienteNome: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.onSurface },
  trocarText: { fontSize: 13, color: colors.brandPrimary, fontWeight: "600" },
  selecionarClienteBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 12, alignSelf: "flex-start", paddingHorizontal: spacing.lg },
  selecionarClienteText: { color: "#fff", fontWeight: "700", fontSize: 14 },

  fieldLabel: { fontSize: 11, color: colors.muted, marginBottom: 4 },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  checkLabel: { fontSize: 13, color: colors.onSurface },
  checkOptionRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  selectAllRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border, marginBottom: 4 },

  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border },
  itemRowDisabled: { opacity: 0.55 },
  gridRowText: { fontSize: 13, color: colors.onSurface },

  bulkBar: { ...WEB_FILTER_CARD, marginBottom: spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: spacing.sm, backgroundColor: colors.surfaceSecondary },
  bulkBarLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  bulkBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, backgroundColor: colors.brandPrimary },
  bulkBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },

  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center", paddingHorizontal: spacing.xl },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, width: "100%", maxWidth: 480, borderWidth: 1, borderColor: colors.border },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  chaveAcesso: { fontSize: 12, color: colors.onSurface, fontFamily: Platform.OS === "web" ? "monospace" : undefined, marginTop: 4, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, padding: spacing.sm },
});

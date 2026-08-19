// Alterar Comandas — migração de `FrmAltComNV.frm` ("Alteração de
// Vendas"). Só é acessada a partir de um botão em cada registro do Gestor
// de Comandas (`gestor-comandas.tsx`) — pedido explícito do usuário,
// 2026-07-21: "a tela alterar comanda só será chamada pelo gestor de
// comandas, através de um botão em cada registro da lista dela".
//
// Fase 2: Gravar (atendente/vendedor/área/cliente do cabeçalho), trocar
// vendedor de um item, Alterar Forma de Pagamento (só Cartão/Débito ainda
// não conciliados) e Números de Série. Fase 3: Cancelar — reverte estoque,
// Pedido/O.S., pagamentos, e cancela o documento fiscal real no SEFAZ
// quando houver protocolo — ver PENDENCIAS.md > "Gestor de Comandas" pro
// escopo exato (o que foi e não foi portado, e por quê).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import SelectField, { SelectOption } from "@/src/components/SelectField";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { friendlyApiError } from "@/src/utils/api";
import { formatBRL } from "@/src/utils/format";
import { useEmitirNotaFiscal } from "@/src/hooks/useEmitirNotaFiscal";
import NotaFiscalCard from "@/src/components/fiscal/NotaFiscalCard";

function brDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}

type ComandaDetalhe = {
  comanda: number; data: string | null; valor_venda: number; valor_liquido: number;
  situacao: string; situacao_label: string; cliente: number | null; cliente_nome: string;
  area_atuacao: number | null; area_atuacao_descricao: string; paga_comissao: boolean;
  atendente: number | null; atendente_nome: string; atendente_dav: number | null; atendente_dav_nome: string;
  faturar_para: number | null; pedido_vinculado: number | null; os_vinculada: number | null;
};
type ItemDetalhe = { id_mov: number; codigo_int: string | null; descricao: string | null; qtd: number; valor_unitario: number; vendedor: number | null; vendedor_nome: string };
type FormaPagDetalhe = { tipo: string; sequencia: number; forma_pag: string | null; forma_pag_descricao: string; valor: number; conciliado: boolean; alteravel: boolean };
type FormaPagOpt = { codigo: string; descricao: string; tipo: string };
type NumSerieVinculo = { sequencia: number; codigo: number; num_serie: string; codigo_int: string | null; descricao: string; data: string | null };
type ProdutoNumSerieOpt = { codigo_int: string; codigo_fab: string; descricao: string };
type NumSerieOpt = { codigo: number; num_serie: string; disponivel: boolean; detalhes: string };

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "Gravar", texto: "Salva as alterações de atendente, vendedor, área de atuação e cliente desta comanda.", icon: { lib: "ion", name: "checkmark" } },
  { titulo: "Editar vendedor do item", texto: "Troca o vendedor responsável por aquele item. Também é possível aplicar a mesma troca aos demais itens que tinham o vendedor anterior.", icon: { lib: "ion", name: "person-outline" } },
  { titulo: "Alterar (nas formas de pagamento)", texto: "Troca a forma de pagamento de um lançamento de Cartão ou Débito para outra da mesma modalidade — só é possível enquanto o lançamento ainda não foi conciliado no caixa/financeiro.", icon: { lib: "ion", name: "card-outline" } },
  { titulo: "Números de Série", texto: "Vincula ou remove números de série de produtos controlados (ex.: equipamentos com garantia) a esta comanda. Só números marcados como disponíveis podem ser vinculados; ao remover, o número volta a ficar disponível para uso em outra venda.", icon: { lib: "ion", name: "barcode-outline" } },
  { titulo: "Emitir NFC-e", texto: "Emite a nota fiscal de consumidor eletrônica real junto à Receita, com base nos itens de produto e no valor já faturados desta comanda. Só aparece quando a comanda ainda não tem nenhuma nota fiscal emitida. Ação irreversível — para desfazer depois de emitida, use Cancelar Comanda.", icon: { lib: "ion", name: "receipt-outline" } },
  { titulo: "Emitir NFS-e", texto: "Emite a nota fiscal de serviço eletrônica real junto ao Sefin Nacional, com base nos itens de serviço desta comanda (ex.: mão de obra). Exige o módulo SEFIN Nacional ativo. Ação irreversível.", icon: { lib: "ion", name: "construct-outline" } },
  { titulo: "Cancelar Comanda", texto: "Cancela a venda por completo: devolve os produtos ao estoque, reabre o Pedido/O.S. de origem (como Fechado, não Cancelado — pode ser corrigido e faturado de novo), remove os pagamentos lançados e, quando houver Nota Fiscal ou NFCe com protocolo emitido, cancela o documento junto à Receita. Não é possível cancelar se algum pagamento já foi conciliado no caixa/financeiro — nesse caso, ajuste manualmente antes. Ação definitiva, exige um motivo.", icon: { lib: "ion", name: "close-circle-outline" }, cor: colors.error },
];

export default function AlterarComandaScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ comanda?: string }>();
  const comandaId = params.comanda ? parseInt(String(params.comanda), 10) : null;
  const { can, isMaster } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Alterar Comandas está disponível apenas no web." testID="alterar-comanda-web-only" />;
  }

  const canAbrir = can("ALTERAR_COMANDA.ABRIR") || isMaster;
  const canGravar = can("ALTERAR_COMANDA.GRAVAR") || isMaster;
  const canFormaPag = can("ALTERAR_COMANDA.FORMA_PAG") || isMaster;
  const canNumSerie = can("ALTERAR_COMANDA.NUM_SERIE") || isMaster;
  const canCancelar = can("ALTERAR_COMANDA.CANCELAR") || isMaster;
  const canEmitirNf = can("ALTERAR_COMANDA.EMITIR_NF") || isMaster;
  const canEmitirNfse = can("ALTERAR_COMANDA.EMITIR_NFSE") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [session, setSession] = useState<{ usuarioCodigo?: number; classe?: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [ajudaVisivel, setAjudaVisivel] = useState(false);

  const [cab, setCab] = useState<ComandaDetalhe | null>(null);
  const [itens, setItens] = useState<ItemDetalhe[]>([]);
  const [formasPag, setFormasPag] = useState<FormaPagDetalhe[]>([]);

  const [areaAtuacao, setAreaAtuacao] = useState<number | null>(null);
  const [atendente, setAtendente] = useState<number | null>(null);
  const [atendenteDav, setAtendenteDav] = useState<number | null>(null);
  const [cliente, setCliente] = useState("");
  const [clienteNomeResolvido, setClienteNomeResolvido] = useState("");
  const [pagaComissao, setPagaComissao] = useState(true);

  const [areaAtuacaoOpts, setAreaAtuacaoOpts] = useState<SelectOption[]>([]);
  const [funcionarioOpts, setFuncionarioOpts] = useState<SelectOption[]>([]);

  const [itemVendedorModal, setItemVendedorModal] = useState<ItemDetalhe | null>(null);
  const [novoVendedor, setNovoVendedor] = useState("");
  const [aplicarDemais, setAplicarDemais] = useState(false);

  const [formaPagModal, setFormaPagModal] = useState<FormaPagDetalhe | null>(null);
  const [formaPagOpts, setFormaPagOpts] = useState<FormaPagOpt[]>([]);
  const [formaPagNova, setFormaPagNova] = useState<string | null>(null);

  const [numSerieItens, setNumSerieItens] = useState<NumSerieVinculo[]>([]);
  const [numSerieModal, setNumSerieModal] = useState(false);
  const [numSerieBuscaProduto, setNumSerieBuscaProduto] = useState("");
  const [numSerieProdutos, setNumSerieProdutos] = useState<ProdutoNumSerieOpt[]>([]);
  const [numSerieProdutoSel, setNumSerieProdutoSel] = useState<ProdutoNumSerieOpt | null>(null);
  const [numSerieDisponiveis, setNumSerieDisponiveis] = useState<NumSerieOpt[]>([]);

  const [cancelarModal, setCancelarModal] = useState(false);
  const [motivoCancelamento, setMotivoCancelamento] = useState("");
  const [cancelando, setCancelando] = useState(false);

  const { docFiscal, emitindoNfce, emitindoNfse, emitirNfce, emitirNfse, recarregar: recarregarDocFiscal } = useEmitirNotaFiscal({
    conn, session, comanda: comandaId, isMaster,
  });

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      setSession({ usuarioCodigo: (s as any).usuarioCodigo ?? (s as any).usuario_codigo, classe: (s as any).classe });
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      // Opções pra Área de Atuação/Atendente/Atendente DAV virarem combobox
      // por nome, não campo cru de código — pedido explícito do usuário,
      // 2026-07-21: "toda tela tem que apresentar os nomes das entidades e
      // não os seus códigos".
      try {
        const base = c.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
        const [rArea, rFunc] = await Promise.all([
          fetch(`${base}/api/area-atuacao?${qs}`).then((x) => x.json()).catch(() => null),
          fetch(`${base}/api/funcionarios?${qs}`).then((x) => x.json()).catch(() => null),
        ]);
        if (rArea?.success) setAreaAtuacaoOpts(rArea.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
        if (rFunc?.success) {
          // Só o codinome (nome_guerra) — pedido explícito do usuário
          // 2026-07-21, sem a legenda de nome completo (deixava os campos
          // Atendente/Atendente DAV mais altos que os demais da linha e
          // desalinhados, já que `rowFields` usa `alignItems: "flex-end"`).
          setFuncionarioOpts(
            rFunc.items.map((f: any) => ({
              value: f.codigo,
              label: f.nome_guerra || f.nome || `#${f.codigo}`,
            }))
          );
        }
      } catch {
        // combos ficam vazios — o campo continua funcional via código digitado
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const carregar = useCallback(async () => {
    if (!conn || !comandaId) return;
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/comandas/${comandaId}?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível carregar a comanda.")); router.back(); return; }
      setCab(j.comanda);
      setItens(j.itens || []);
      setFormasPag(j.formas_pagamento || []);
      setAreaAtuacao(j.comanda.area_atuacao ?? null);
      setAtendente(j.comanda.atendente ?? null);
      setAtendenteDav(j.comanda.atendente_dav ?? null);
      setCliente(j.comanda.cliente != null ? String(j.comanda.cliente) : "");
      setClienteNomeResolvido(j.comanda.cliente_nome || "");
      setPagaComissao(!!j.comanda.paga_comissao);
      const rns = await fetch(`${base}/api/comandas/${comandaId}/num-serie?${qs}`).then((x) => x.json()).catch(() => null);
      setNumSerieItens(rns?.success ? rns.items || [] : []);
      recarregarDocFiscal();
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, comandaId]);

  useEffect(() => { carregar(); }, [carregar]);

  const int_ = (s: string): number | null => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || null : null);

  // Resolve o nome do cliente ao trocar o código do campo (mesmo pedido
  // acima) — mostra o nome abaixo do campo em vez de deixar só o código
  // cru; não usa um seletor de busca completo aqui (lista de clientes é
  // grande demais pra um combobox simples), só o mesmo endpoint de resumo
  // já usado em outras telas.
  const resolverNomeCliente = async (codigoStr: string) => {
    const codigo = int_(codigoStr);
    if (!conn || !codigo) { setClienteNomeResolvido(""); return; }
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/clientes/${codigo}/resumo?${qs}`);
      const j = await r.json();
      setClienteNomeResolvido(j?.success ? (j.cliente?.nome || "") : "Cliente não encontrado");
    } catch {
      setClienteNomeResolvido("");
    }
  };

  const gravar = async () => {
    if (!conn || !comandaId || !session) return;
    setSalvando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco,
        area_atuacao: areaAtuacao, paga_comissao: pagaComissao,
        atendente: atendente, atendente_dav: atendenteDav, cliente: int_(cliente),
        faturar_para: cab?.faturar_para ?? null,
        usuario_alteracao: session.usuarioCodigo, classe: session.classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(`${base}/api/comandas/${comandaId}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess("Comanda gravada."); carregar(); }
      else fb.showError(friendlyApiError(j, "Não foi possível gravar a comanda."));
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSalvando(false);
    }
  };

  const abrirVendedorModal = (it: ItemDetalhe) => {
    setItemVendedorModal(it);
    setNovoVendedor(it.vendedor != null ? String(it.vendedor) : "");
    setAplicarDemais(false);
  };

  const salvarVendedorItem = async () => {
    if (!conn || !comandaId || !session || !itemVendedorModal) return;
    const vendedorNum = int_(novoVendedor);
    if (!vendedorNum) { fb.showWarning("Informe o código do vendedor."); return; }
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco, id_mov: itemVendedorModal.id_mov, vendedor: vendedorNum,
        aplicar_aos_demais_itens_do_vendedor_anterior: aplicarDemais,
        usuario_alteracao: session.usuarioCodigo, classe: session.classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(`${base}/api/comandas/${comandaId}/itens/${itemVendedorModal.id_mov}/vendedor`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess("Vendedor do item alterado."); setItemVendedorModal(null); carregar(); }
      else fb.showError(friendlyApiError(j, "Não foi possível alterar o vendedor."));
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const abrirFormaPagModal = async (fp: FormaPagDetalhe) => {
    setFormaPagModal(fp);
    setFormaPagNova(null);
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/forma-pagamento-completo?${qs}`);
      const j = await r.json();
      const opts: FormaPagOpt[] = (j?.items || []).filter((o: FormaPagOpt) => (o.tipo || "").toUpperCase() === fp.tipo);
      setFormaPagOpts(opts);
    } catch {
      setFormaPagOpts([]);
    }
  };

  const salvarFormaPag = async () => {
    if (!conn || !comandaId || !session || !formaPagModal || !formaPagNova) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco, sequencia: formaPagModal.sequencia, tipo: formaPagModal.tipo,
        forma_pag_nova: formaPagNova, usuario_alteracao: session.usuarioCodigo, classe: session.classe,
        plataforma: "web", master: isMaster,
      };
      const r = await fetch(`${base}/api/comandas/${comandaId}/forma-pagamento/${formaPagModal.sequencia}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess("Forma de pagamento alterada."); setFormaPagModal(null); carregar(); }
      else fb.showError(friendlyApiError(j, "Não foi possível alterar a forma de pagamento."));
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // Números de Série — vincula/desvincula `pecas_num_serie` (mesma tabela
  // auxiliar já gerenciada em Tabelas Auxiliares/Números de Série) a esta
  // comanda via `comanda_num_serie`. Reaproveita os endpoints de busca já
  // existentes (`/tabelas/num-serie/produtos`, `/tabelas/num-serie`) em vez
  // de duplicar a lógica de busca de produto/disponibilidade.
  const abrirNumSerieModal = () => {
    setNumSerieModal(true);
    setNumSerieBuscaProduto("");
    setNumSerieProdutos([]);
    setNumSerieProdutoSel(null);
    setNumSerieDisponiveis([]);
  };

  const buscarProdutosNumSerie = async (termo: string) => {
    setNumSerieBuscaProduto(termo);
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(termo)}`;
      const r = await fetch(`${base}/api/tabelas/num-serie/produtos?${qs}`);
      const j = await r.json();
      setNumSerieProdutos(j?.items || []);
    } catch {
      setNumSerieProdutos([]);
    }
  };

  const selecionarProdutoNumSerie = async (p: ProdutoNumSerieOpt) => {
    setNumSerieProdutoSel(p);
    setNumSerieDisponiveis([]);
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&codigo_int=${encodeURIComponent(p.codigo_int)}`;
      const r = await fetch(`${base}/api/tabelas/num-serie?${qs}`);
      const j = await r.json();
      setNumSerieDisponiveis((j?.items || []).filter((i: NumSerieOpt) => i.disponivel));
    } catch {
      setNumSerieDisponiveis([]);
    }
  };

  const vincularNumSerie = async (opt: NumSerieOpt) => {
    if (!conn || !comandaId || !session) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = { servidor: conn.servidor, banco: conn.banco, codigo: opt.codigo, usuario_alteracao: session.usuarioCodigo, classe: session.classe, plataforma: "web", master: isMaster };
      const r = await fetch(`${base}/api/comandas/${comandaId}/num-serie`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess("Número de série vinculado."); setNumSerieModal(false); carregar(); }
      else fb.showError(friendlyApiError(j, "Não foi possível vincular o número de série."));
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const desvincularNumSerie = async (v: NumSerieVinculo) => {
    if (!conn || !comandaId || !session) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&usuario_alteracao=${session.usuarioCodigo ?? ""}&classe=${session.classe ?? ""}&plataforma=web&master=${isMaster}`;
      const r = await fetch(`${base}/api/comandas/${comandaId}/num-serie/${v.sequencia}?${qs}`, { method: "DELETE" });
      const j = await r.json();
      if (j?.success) { fb.showSuccess("Número de série desvinculado."); carregar(); }
      else fb.showError(friendlyApiError(j, "Não foi possível desvincular o número de série."));
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // Emitir NFC-e/NFS-e — ver `useEmitirNotaFiscal.ts` (hook compartilhado,
  // extraído daqui; reaproveitado também por Pedido/O.S. depois de faturar).

  // Cancelar Comanda — reversão completa (estoque, Pedido/O.S., pagamentos
  // e, quando houver protocolo SEFAZ, cancelamento fiscal real). Ação
  // definitiva, exige motivo com pelo menos 15 caracteres (mesma regra do
  // backend) — ver `comanda_service._cancelar_comanda_sync`.
  const cancelarComanda = async () => {
    if (!conn || !comandaId || !session) return;
    if (motivoCancelamento.trim().length < 15) {
      fb.showWarning("Informe um motivo com pelo menos 15 caracteres.");
      return;
    }
    setCancelando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco, motivo: motivoCancelamento.trim(),
        usuario_alteracao: session.usuarioCodigo, classe: session.classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(`${base}/api/comandas/${comandaId}/cancelar`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess("Comanda cancelada.");
        setCancelarModal(false);
        carregar();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível cancelar a comanda."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setCancelando(false);
    }
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Alterar Comandas." testID="alterar-comanda-no-perm" />;
  }
  if (!comandaId) {
    return <LockedView title="Comanda não informada" message="Abra esta tela a partir de um registro do Gestor de Comandas." testID="alterar-comanda-sem-id" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="alterar-comanda-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Alterar Comanda #{comandaId}</Text>
        <View style={styles.headerActions}>
          <IconButtonWithTooltip
            icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
            size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="alterar-comanda-ajuda"
          />
          {canCancelar && cab && cab.situacao !== "C" ? (
            <Pressable
              onPress={() => { setMotivoCancelamento(""); setCancelarModal(true); }}
              style={styles.cancelBtn} hitSlop={8} testID="alterar-comanda-abrir-cancelar"
            >
              <Ionicons name="close-circle-outline" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.saveLabel}>Cancelar Comanda</Text>
            </Pressable>
          ) : null}
          {canGravar ? (
            <Pressable onPress={gravar} disabled={salvando || loading} style={styles.saveBtn} hitSlop={8} testID="alterar-comanda-gravar">
              {salvando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                <>
                  <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.saveLabel}>Gravar</Text>
                </>
              )}
            </Pressable>
          ) : null}
        </View>
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      ) : !cab ? (
        <Text style={styles.hint}>Comanda não encontrada.</Text>
      ) : (
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            <View style={styles.card}>
              <Text style={styles.gridRowText}>
                #{cab.comanda} · {brDate(cab.data)} · {cab.cliente_nome} · <Text style={{ fontWeight: "700" }}>{formatBRL(cab.valor_venda)}</Text>
              </Text>
              <Text style={styles.hint}>
                {cab.situacao_label}
                {cab.pedido_vinculado ? ` · Pedido #${cab.pedido_vinculado}` : ""}
                {cab.os_vinculada ? ` · O.S. #${cab.os_vinculada}` : ""}
              </Text>
            </View>

            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Cabeçalho</Text>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Área de Atuação</Text>
                  <SelectField
                    value={areaAtuacao}
                    onChange={(v) => setAreaAtuacao(v as number | null)}
                    options={areaAtuacaoOpts}
                    disabled={!canGravar}
                    allowClear
                    compactWeb
                    testID="alterar-comanda-area"
                    modalTitle="Área de Atuação"
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Atendente</Text>
                  <SelectField
                    value={atendente}
                    onChange={(v) => setAtendente(v as number | null)}
                    options={funcionarioOpts}
                    disabled={!canGravar}
                    allowClear
                    compactWeb
                    testID="alterar-comanda-atendente"
                    modalTitle="Atendente"
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Atendente DAV</Text>
                  <SelectField
                    value={atendenteDav}
                    onChange={(v) => setAtendenteDav(v as number | null)}
                    options={funcionarioOpts}
                    disabled={!canGravar}
                    allowClear
                    compactWeb
                    testID="alterar-comanda-atendente-dav"
                    modalTitle="Atendente DAV"
                  />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Cliente (código)</Text>
                  <TextInput
                    value={cliente}
                    onChangeText={(v) => setCliente(v.replace(/\D/g, ""))}
                    onBlur={() => resolverNomeCliente(cliente)}
                    style={styles.input}
                    keyboardType="number-pad"
                    editable={canGravar}
                    testID="alterar-comanda-cliente"
                  />
                  {clienteNomeResolvido ? (
                    <Text style={[styles.hint, { marginTop: 4 }]} numberOfLines={1}>{clienteNomeResolvido}</Text>
                  ) : null}
                </View>
                <View style={styles.colNarrow}>
                  <Pressable onPress={() => canGravar && setPagaComissao((v) => !v)} style={styles.checkRow} testID="alterar-comanda-paga-comissao">
                    <Ionicons name={pagaComissao ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                    <Text style={styles.checkLabel}>Paga Comissão</Text>
                  </Pressable>
                </View>
              </View>
            </View>

            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Itens</Text>
              {itens.length === 0 ? (
                <Text style={styles.hint}>Nenhum item encontrado.</Text>
              ) : itens.map((it, idx) => (
                // zIndex decrescente por linha — sem isso, o tooltip de um
                // ícone perto do fim de uma linha escapa (`top:"100%"`) por
                // trás da PRÓXIMA linha da lista (achado ao vivo 2026-07-21:
                // elevar só o wrapper do próprio ícone, já feito em
                // `IconButtonWithTooltip`, só resolve o ícone vizinho na
                // MESMA linha — não a linha seguinte). Ver CLAUDE.md > "Modo
                // Didático" > regra de tooltip sempre por cima.
                <View key={it.id_mov} style={[styles.itemRow, { zIndex: itens.length - idx }]} testID={`alterar-comanda-item-${it.id_mov}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText}>{it.descricao || it.codigo_int} · {it.qtd} × {formatBRL(it.valor_unitario)}</Text>
                    <Text style={styles.hint}>Vendedor: {it.vendedor_nome || it.vendedor || "—"}</Text>
                  </View>
                  {canGravar ? (
                    <IconButtonWithTooltip
                      icon="person-outline" label="Alterar vendedor do item" onPress={() => abrirVendedorModal(it)}
                      style={styles.itemActionBtn} testID={`alterar-comanda-item-vendedor-${it.id_mov}`}
                    />
                  ) : null}
                </View>
              ))}
            </View>

            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Formas de Pagamento</Text>
              {formasPag.length === 0 ? (
                <Text style={styles.hint}>Nenhuma forma de pagamento lançada.</Text>
              ) : formasPag.map((fp, idx) => (
                <View key={`${fp.tipo}-${fp.sequencia}`} style={[styles.itemRow, { zIndex: formasPag.length - idx }]} testID={`alterar-comanda-formapag-${fp.tipo}-${fp.sequencia}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText}>{fp.tipo} · {fp.forma_pag_descricao || fp.forma_pag} · {formatBRL(fp.valor)}</Text>
                    <Text style={styles.hint}>{fp.conciliado ? "Já conciliado no caixa/financeiro" : "Ainda não conciliado"}</Text>
                  </View>
                  {canFormaPag && fp.alteravel ? (
                    <IconButtonWithTooltip
                      icon="card-outline" label="Alterar forma de pagamento" onPress={() => abrirFormaPagModal(fp)}
                      style={styles.itemActionBtn} testID={`alterar-comanda-formapag-alterar-${fp.sequencia}`}
                    />
                  ) : null}
                </View>
              ))}
            </View>

            <View style={styles.card}>
              <View style={styles.itensHeaderRow}>
                <Text style={styles.sectionTitle}>Números de Série</Text>
                {canNumSerie ? (
                  <IconButtonWithTooltip
                    icon="add" label="Vincular número de série" onPress={abrirNumSerieModal}
                    style={styles.itemActionBtn} testID="alterar-comanda-num-serie-add"
                  />
                ) : null}
              </View>
              {numSerieItens.length === 0 ? (
                <Text style={styles.hint}>Nenhum número de série vinculado a esta comanda.</Text>
              ) : numSerieItens.map((v, idx) => (
                <View key={v.sequencia} style={[styles.itemRow, { zIndex: numSerieItens.length - idx }]} testID={`alterar-comanda-num-serie-${v.sequencia}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText}>{v.num_serie}{v.descricao ? ` · ${v.descricao}` : ""}</Text>
                    <Text style={styles.hint}>{brDate(v.data)}</Text>
                  </View>
                  {canNumSerie ? (
                    <IconButtonWithTooltip
                      icon="close" label="Desvincular número de série" color={colors.error} onPress={() => desvincularNumSerie(v)}
                      style={styles.itemActionBtn} testID={`alterar-comanda-num-serie-remover-${v.sequencia}`}
                    />
                  ) : null}
                </View>
              ))}
            </View>

            {cab?.situacao === "PG" ? (
              <NotaFiscalCard
                docFiscal={docFiscal} emitindoNfce={emitindoNfce} emitindoNfse={emitindoNfse}
                onEmitirNfce={emitirNfce} onEmitirNfse={emitirNfse}
                canEmitirNfce={canEmitirNf} canEmitirNfse={canEmitirNfse}
                testIDPrefix="alterar-comanda"
              />
            ) : null}
          </View>
        </ScrollView>
      )}

      <AppModal visible={!!itemVendedorModal} transparent animationType="fade" onRequestClose={() => setItemVendedorModal(null)}>
        <Pressable style={styles.modalBg} onPress={() => setItemVendedorModal(null)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Alterar Vendedor do Item</Text>
              <Pressable onPress={() => setItemVendedorModal(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.label}>Novo vendedor (código)</Text>
            <TextInput value={novoVendedor} onChangeText={(v) => setNovoVendedor(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="alterar-comanda-novo-vendedor" />
            <Pressable onPress={() => setAplicarDemais((v) => !v)} style={[styles.checkRow, { marginTop: spacing.sm }]} testID="alterar-comanda-aplicar-demais">
              <Ionicons name={aplicarDemais ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
              <Text style={styles.checkLabel}>Aplicar aos demais itens do vendedor anterior</Text>
            </Pressable>
            <View style={styles.modalActionsRow}>
              <Pressable onPress={salvarVendedorItem} style={styles.primaryBtn} testID="alterar-comanda-salvar-vendedor">
                <Text style={styles.primaryBtnText}>Salvar</Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={!!formaPagModal} transparent animationType="fade" onRequestClose={() => setFormaPagModal(null)}>
        <Pressable style={styles.modalBg} onPress={() => setFormaPagModal(null)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Alterar Forma de Pagamento</Text>
              <Pressable onPress={() => setFormaPagModal(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.hint}>Só é possível trocar por outra forma da mesma modalidade ({formaPagModal?.tipo}).</Text>
            <View style={{ marginTop: spacing.sm, gap: 6 }}>
              {formaPagOpts.map((o) => (
                <Pressable
                  key={o.codigo}
                  onPress={() => setFormaPagNova(o.codigo)}
                  style={[styles.pillBtn, formaPagNova === o.codigo && styles.pillBtnSel]}
                  testID={`alterar-comanda-formapag-opt-${o.codigo}`}
                >
                  <Text style={[styles.pillBtnText, formaPagNova === o.codigo && styles.pillBtnTextSel]}>{o.descricao}</Text>
                </Pressable>
              ))}
            </View>
            <View style={styles.modalActionsRow}>
              <Pressable onPress={salvarFormaPag} disabled={!formaPagNova} style={styles.primaryBtn} testID="alterar-comanda-salvar-formapag">
                <Text style={styles.primaryBtnText}>Salvar</Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={numSerieModal} transparent animationType="fade" onRequestClose={() => setNumSerieModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setNumSerieModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Vincular Número de Série</Text>
              <Pressable onPress={() => setNumSerieModal(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.label}>Produto</Text>
            <TextInput
              value={numSerieBuscaProduto}
              onChangeText={buscarProdutosNumSerie}
              placeholder="Buscar por código ou descrição…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="alterar-comanda-num-serie-busca-produto"
            />
            {numSerieProdutoSel ? (
              <Text style={[styles.hint, { marginTop: spacing.sm }]}>Produto selecionado: {numSerieProdutoSel.descricao}</Text>
            ) : (
              <View style={{ marginTop: spacing.sm, gap: 4, maxHeight: 160 }}>
                <ScrollView>
                  {numSerieProdutos.map((p) => (
                    <Pressable key={p.codigo_int} onPress={() => selecionarProdutoNumSerie(p)} style={styles.pillBtn} testID={`alterar-comanda-num-serie-produto-${p.codigo_int}`}>
                      <Text style={styles.pillBtnText}>{p.descricao}</Text>
                    </Pressable>
                  ))}
                </ScrollView>
              </View>
            )}
            {numSerieProdutoSel ? (
              <>
                <Text style={[styles.label, { marginTop: spacing.md }]}>Números disponíveis</Text>
                {numSerieDisponiveis.length === 0 ? (
                  <Text style={styles.hint}>Nenhum número de série disponível para este produto.</Text>
                ) : (
                  <View style={{ gap: 4, maxHeight: 160 }}>
                    <ScrollView>
                      {numSerieDisponiveis.map((o) => (
                        <Pressable key={o.codigo} onPress={() => vincularNumSerie(o)} style={styles.pillBtn} testID={`alterar-comanda-num-serie-opt-${o.codigo}`}>
                          <Text style={styles.pillBtnText}>{o.num_serie}</Text>
                        </Pressable>
                      ))}
                    </ScrollView>
                  </View>
                )}
              </>
            ) : null}
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={cancelarModal} transparent animationType="fade" onRequestClose={() => setCancelarModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setCancelarModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Cancelar Comanda #{comandaId}</Text>
              <Pressable onPress={() => setCancelarModal(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.hint}>
              Esta ação reverte o estoque, o Pedido/O.S. de origem e os pagamentos lançados — e cancela o documento
              fiscal (Nota/NFCe) junto ao SEFAZ quando houver protocolo emitido. Não pode ser desfeita.
            </Text>
            <Text style={[styles.label, { marginTop: spacing.sm }]}>Motivo do cancelamento (mínimo 15 caracteres)</Text>
            <TextInput
              value={motivoCancelamento}
              onChangeText={setMotivoCancelamento}
              style={[styles.input, { minHeight: 72 }]}
              multiline
              placeholder="Descreva o motivo do cancelamento…"
              placeholderTextColor={colors.muted}
              testID="alterar-comanda-motivo-cancelamento"
            />
            <View style={styles.modalActionsRow}>
              <Pressable
                onPress={cancelarComanda}
                disabled={cancelando || motivoCancelamento.trim().length < 15}
                style={[styles.primaryBtn, { backgroundColor: colors.error }]}
                testID="alterar-comanda-confirmar-cancelar"
              >
                {cancelando ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Cancelar Comanda</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </AppModal>

      <AjudaPedidoModal visible={ajudaVisivel} onClose={() => setAjudaVisivel(false)} titulo="Alterar Comandas" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  // zIndex alto — sem isso, o tooltip de um ícone do cabeçalho (Voltar/
  // Ajuda) que escapa pra baixo (`top:"100%"`) fica atrás do conteúdo
  // rolável logo abaixo (mesmo tipo de achado das linhas de lista — ver
  // comentário em `itemRow` acima). Cabeçalho sempre por cima de tudo.
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm, zIndex: 100 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)" },
  cancelBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,80,80,0.25)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  itensHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colNarrow: { width: 170 },
  colTiny: { width: 110 },

  checkRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 11 },
  checkLabel: { fontSize: 13, color: colors.onSurface },

  gridRowText: { fontSize: 13, color: colors.onSurface },
  itemRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border },
  itemActionBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },

  pillBtn: { paddingHorizontal: spacing.md, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignSelf: "flex-start" },
  pillBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  pillBtnText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  pillBtnTextSel: { color: colors.onBrandPrimary },

  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center", paddingHorizontal: spacing.xl },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, width: "100%", maxWidth: 420, borderWidth: 1, borderColor: colors.border },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  modalActionsRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.lg },
  primaryBtn: { paddingHorizontal: spacing.lg, paddingVertical: 11, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", minWidth: 130 },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
});

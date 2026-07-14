import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type TipoMovItem = { codigo: string; descricao: string; natureza: "E" | "S" };
type TipoMovDetalhe = {
  codigo: string; descricao: string; descricao_nf: string; origem_destino: string;
  atualiza_est: boolean; transf_livro: boolean; transf_pagar: boolean; transf_contabil: boolean; transf_caixa: boolean;
  cod_contabil_livro: number | null; cod_contabil_pag: number | null; cod_contabil_juros: number | null;
  cod_contabil_descontos: number | null; cod_contabil_acrescimos: number | null;
  tipo_mov_contra_partida: string | null; prazo_contra_partida: number | null; tipo_mov_origem: string | null;
  cfop: string; cfop_fora: string; tipo_doc: number | null; itens: boolean; centro_custo: number | null;
  tipo_nf: number | null; estoque_atual: boolean; estoque_cliente: boolean; estoque_fornecedor: boolean;
  altera_custo: boolean; altera_venda: boolean; emite_ecf: boolean; situacao: string | null; codigo_danfe: number | null;
};

const ORIGEM_DESTINO_OPTS: SelectOption[] = [
  { value: "C", label: "Cliente" },
  { value: "F", label: "Fornecedor" },
];

const num = (s: string) => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) : null);

// Cadastro/Tabelas Auxiliares > Tipo de Movimentação (tabela `tipo_mov`).
// Legado: FrmManTip ("Cadastro de Tipos de Movimentação"). Código = "E"/"S" +
// sequência de 2 dígitos (ex. E15/S20), sugerido automaticamente ao escolher
// a Natureza — travado depois de criado. Regras de negócio replicadas do VB6:
// faixa 00-07 nunca pode ser criada (nem pelo master) e só o master pode
// alterá-la; exclusão só permitida acima de 14; `atualiza_est` é imutável
// após criado; mudar Origem/Destino é bloqueado se já existir Nota Fiscal
// emitida; Movimentação Contra Partida e Movimentação Origem são mutuamente
// exclusivas. Simplificação assumida: "Código Danfe" (combo do legado cujos
// itens reais estão só no .frx binário, não no .frm texto) é exposto aqui
// como campo numérico simples.
export default function TipoMovScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Tipo de Movimentação está disponível apenas no web."
        testID="tipo-mov-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<TipoMovItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const [tipoDocOptions, setTipoDocOptions] = useState<SelectOption[]>([]);
  const [situacaoOptions, setSituacaoOptions] = useState<SelectOption[]>([]);
  const [centroCustoOptions, setCentroCustoOptions] = useState<SelectOption[]>([]);
  const [tipoNfOptions, setTipoNfOptions] = useState<SelectOption[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [natureza, setNatureza] = useState<"E" | "S">("E");
  const [codigo, setCodigo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [descricaoNf, setDescricaoNf] = useState("");
  const [origemDestino, setOrigemDestino] = useState<string | null>(null);
  const [tipoNf, setTipoNf] = useState<number | null>(null);
  const [cfop, setCfop] = useState("");
  const [cfopFora, setCfopFora] = useState("");
  const [centroCusto, setCentroCusto] = useState<number | null>(null);
  const [tipoDoc, setTipoDoc] = useState<number | null>(null);
  const [situacao, setSituacao] = useState<string | null>(null);
  const [codigoDanfe, setCodigoDanfe] = useState("0");

  const [atualizaEst, setAtualizaEst] = useState(false);
  const [transfLivro, setTransfLivro] = useState(false);
  const [transfPagar, setTransfPagar] = useState(false);
  const [transfContabil, setTransfContabil] = useState(false);
  const [transfCaixa, setTransfCaixa] = useState(false);
  const [itens, setItens] = useState(false);
  const [estoqueAtual, setEstoqueAtual] = useState(false);
  const [estoqueCliente, setEstoqueCliente] = useState(false);
  const [estoqueFornecedor, setEstoqueFornecedor] = useState(false);
  const [alteraCusto, setAlteraCusto] = useState(false);
  const [alteraVenda, setAlteraVenda] = useState(false);
  const [emiteEcf, setEmiteEcf] = useState(false);

  const [codContabilLivro, setCodContabilLivro] = useState("");
  const [codContabilPag, setCodContabilPag] = useState("");
  const [codContabilJuros, setCodContabilJuros] = useState("");
  const [codContabilDescontos, setCodContabilDescontos] = useState("");
  const [codContabilAcrescimos, setCodContabilAcrescimos] = useState("");
  const [tipoMovContraPartida, setTipoMovContraPartida] = useState<string | null>(null);
  const [prazoContraPartida, setPrazoContraPartida] = useState("");
  const [tipoMovOrigem, setTipoMovOrigem] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/tabelas/tipo-mov?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [rTipoDoc, rSituacao, rCentroCusto, rTipoNf] = await Promise.all([
        fetch(`${base}/api/tabelas/tipo-doc?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/tabelas/situacao?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/financeiro/centro-custo?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/tabelas/tipo-nf?${qs}`).then((r) => r.json()).catch(() => null),
      ]);
      if (rTipoDoc?.success) setTipoDocOptions((rTipoDoc.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rSituacao?.success) setSituacaoOptions((rSituacao.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rCentroCusto?.success) setCentroCustoOptions((rCentroCusto.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rTipoNf?.success) setTipoNfOptions((rTipoNf.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
    } catch {
      // silencioso — combos ficam vazios
    }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      load(cc, "");
      loadLookups(cc);
    })();
  }, [router, load, loadLookups]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const resetForm = () => {
    setDescricao(""); setDescricaoNf(""); setOrigemDestino(null); setTipoNf(null);
    setCfop(""); setCfopFora(""); setCentroCusto(null); setTipoDoc(null); setSituacao(null); setCodigoDanfe("0");
    setAtualizaEst(false); setTransfLivro(false); setTransfPagar(false); setTransfContabil(false); setTransfCaixa(false);
    setItens(false); setEstoqueAtual(false); setEstoqueCliente(false); setEstoqueFornecedor(false);
    setAlteraCusto(false); setAlteraVenda(false); setEmiteEcf(false);
    setCodContabilLivro(""); setCodContabilPag(""); setCodContabilJuros(""); setCodContabilDescontos(""); setCodContabilAcrescimos("");
    setTipoMovContraPartida(null); setPrazoContraPartida(""); setTipoMovOrigem(null);
  };

  const openNew = async (nat: "E" | "S") => {
    if (!conn) return;
    setEditing(false);
    setNatureza(nat);
    resetForm();
    setCodigo("…");
    setFormOpen(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&natureza=${nat}`;
      const r = await fetch(`${base}/api/tabelas/tipo-mov-proximo-codigo?${qs}`);
      const j = await r.json();
      setCodigo(j?.success ? j.codigo : "");
    } catch { setCodigo(""); }
  };

  const openEdit = async (item: TipoMovItem) => {
    if (!conn) return;
    setEditing(true);
    setNatureza(item.natureza);
    setCodigo(item.codigo);
    setFormOpen(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/tabelas/tipo-mov/${encodeURIComponent(item.codigo)}?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      const d: TipoMovDetalhe = j.tipo_mov;
      setDescricao(d.descricao); setDescricaoNf(d.descricao_nf); setOrigemDestino(d.origem_destino || null);
      setTipoNf(d.tipo_nf); setCfop(d.cfop); setCfopFora(d.cfop_fora); setCentroCusto(d.centro_custo);
      setTipoDoc(d.tipo_doc); setSituacao(d.situacao); setCodigoDanfe(String(d.codigo_danfe ?? 0));
      setAtualizaEst(d.atualiza_est); setTransfLivro(d.transf_livro); setTransfPagar(d.transf_pagar);
      setTransfContabil(d.transf_contabil); setTransfCaixa(d.transf_caixa); setItens(d.itens);
      setEstoqueAtual(d.estoque_atual); setEstoqueCliente(d.estoque_cliente); setEstoqueFornecedor(d.estoque_fornecedor);
      setAlteraCusto(d.altera_custo); setAlteraVenda(d.altera_venda); setEmiteEcf(d.emite_ecf);
      setCodContabilLivro(d.cod_contabil_livro != null ? String(d.cod_contabil_livro) : "");
      setCodContabilPag(d.cod_contabil_pag != null ? String(d.cod_contabil_pag) : "");
      setCodContabilJuros(d.cod_contabil_juros != null ? String(d.cod_contabil_juros) : "");
      setCodContabilDescontos(d.cod_contabil_descontos != null ? String(d.cod_contabil_descontos) : "");
      setCodContabilAcrescimos(d.cod_contabil_acrescimos != null ? String(d.cod_contabil_acrescimos) : "");
      setTipoMovContraPartida(d.tipo_mov_contra_partida);
      setPrazoContraPartida(d.prazo_contra_partida ? String(d.prazo_contra_partida) : "");
      setTipoMovOrigem(d.tipo_mov_origem);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      setFormOpen(false);
    }
  };

  const save = async () => {
    if (!conn || !codigo) return;
    if (!descricao.trim()) { fb.showWarning("O campo Descrição deve estar preenchido."); return; }
    if (!origemDestino) { fb.showWarning("Selecione Origem/Destino corretamente."); return; }
    if (!tipoDoc) { fb.showWarning("Selecione o Tipo de Documento."); return; }
    if (!cfop.trim()) { fb.showWarning("Informe o Cfop dentro do estado."); return; }
    if (!cfopFora.trim()) { fb.showWarning("Informe o Cfop fora do estado."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/tipo-mov`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, master: isMaster,
          codigo, descricao: descricao.trim(), descricao_nf: descricaoNf.trim(), origem_destino: origemDestino,
          atualiza_est: atualizaEst, transf_livro: transfLivro, transf_pagar: transfPagar,
          transf_contabil: transfContabil, transf_caixa: transfCaixa,
          cod_contabil_livro: num(codContabilLivro), cod_contabil_pag: num(codContabilPag),
          cod_contabil_juros: num(codContabilJuros), cod_contabil_descontos: num(codContabilDescontos),
          cod_contabil_acrescimos: num(codContabilAcrescimos),
          tipo_mov_contra_partida: tipoMovContraPartida, prazo_contra_partida: num(prazoContraPartida),
          tipo_mov_origem: tipoMovOrigem, cfop: cfop.trim().toUpperCase(), cfop_fora: cfopFora.trim().toUpperCase(),
          tipo_doc: tipoDoc, itens, centro_custo: centroCusto, tipo_nf: tipoNf,
          estoque_atual: estoqueAtual, estoque_cliente: estoqueCliente, estoque_fornecedor: estoqueFornecedor,
          altera_custo: alteraCusto, altera_venda: alteraVenda, emite_ecf: emiteEcf,
          situacao, codigo_danfe: num(codigoDanfe) ?? 0,
        }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Registro gravado."); setFormOpen(false); load(conn, search); }
      else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = (item: TipoMovItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão de "${item.codigo} - ${item.descricao}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/tabelas/tipo-mov/${encodeURIComponent(item.codigo)}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn, search); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  const canSave = can("TIPO_MOV.GRAVAR") || isMaster;
  const canDel = can("TIPO_MOV.EXCLUIR") || isMaster;

  const entradas = items.filter((i) => i.natureza === "E");
  const saidas = items.filter((i) => i.natureza === "S");

  const tipoMovOptions = (excluir: string | null): SelectOption[] => [
    { value: "", label: "Nenhum" },
    ...items.filter((i) => i.codigo !== excluir).map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })),
  ];

  const SwitchRow = ({ label, value, onValueChange, testID }: { label: string; value: boolean; onValueChange: (v: boolean) => void; testID: string }) => (
    <View style={styles.switchRow}>
      <Text style={styles.switchLabel}>{label}</Text>
      <Switch value={value} onValueChange={onValueChange} testID={testID} />
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="tipo-mov-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Tipo de Movimentação</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por descrição…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="tipo-mov-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading ? (
            <View style={styles.colunas}>
              <View style={styles.coluna}>
                <Text style={styles.colunaTitulo}>Entradas</Text>
                {entradas.length === 0 ? <Text style={styles.empty}>Nenhuma.</Text> : null}
                {entradas.map((i) => (
                  <View key={i.codigo} style={styles.row} testID={`tipo-mov-${i.codigo}`}>
                    <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(i)}>
                      <Text style={styles.rowTitle}>{i.codigo} - {i.descricao}</Text>
                    </Pressable>
                    {canDel ? (
                      <Pressable onPress={() => remove(i)} hitSlop={8} testID={`tipo-mov-del-${i.codigo}`}>
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    ) : null}
                  </View>
                ))}
                {canSave ? (
                  <Pressable onPress={() => openNew("E")} style={styles.addBtn} testID="tipo-mov-novo-entrada">
                    <Ionicons name="add" size={16} color={colors.brandPrimary} />
                    <Text style={styles.addBtnText}>Nova Entrada</Text>
                  </Pressable>
                ) : null}
              </View>

              <View style={styles.coluna}>
                <Text style={styles.colunaTitulo}>Saídas</Text>
                {saidas.length === 0 ? <Text style={styles.empty}>Nenhuma.</Text> : null}
                {saidas.map((i) => (
                  <View key={i.codigo} style={styles.row} testID={`tipo-mov-${i.codigo}`}>
                    <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(i)}>
                      <Text style={styles.rowTitle}>{i.codigo} - {i.descricao}</Text>
                    </Pressable>
                    {canDel ? (
                      <Pressable onPress={() => remove(i)} hitSlop={8} testID={`tipo-mov-del-${i.codigo}`}>
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    ) : null}
                  </View>
                ))}
                {canSave ? (
                  <Pressable onPress={() => openNew("S")} style={styles.addBtn} testID="tipo-mov-novo-saida">
                    <Ionicons name="add" size={16} color={colors.brandPrimary} />
                    <Text style={styles.addBtnText}>Nova Saída</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          ) : null}
        </ScrollView>
      </View>

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>{editing ? `Tipo de Movimentação ${codigo}` : `Nova ${natureza === "E" ? "Entrada" : "Saída"} — ${codigo}`}</Text>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.label}>Descrição *</Text>
              <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} maxLength={60} autoCapitalize="characters" testID="tipo-mov-descricao" />

              <Text style={styles.label}>Descrição Nota Fiscal</Text>
              <TextInput value={descricaoNf} onChangeText={setDescricaoNf} style={styles.input} maxLength={25} autoCapitalize="characters" testID="tipo-mov-descricao-nf" />

              <Text style={styles.label}>Origem/Destino *</Text>
              <SelectField value={origemDestino} onChange={(v) => setOrigemDestino(v as string)} options={ORIGEM_DESTINO_OPTS} testID="tipo-mov-origem-destino" modalTitle="Origem/Destino" compactWeb />

              <Text style={styles.label}>Tipo Nota Fiscal</Text>
              <SelectField value={tipoNf} onChange={(v) => setTipoNf(v as number)} options={tipoNfOptions} testID="tipo-mov-tipo-nf" modalTitle="Tipo Nota Fiscal" compactWeb />

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Cfop Estadual *</Text>
                  <TextInput value={cfop} onChangeText={(v) => setCfop(v.replace(/[^0-9]/g, ""))} style={styles.input} maxLength={4} keyboardType="number-pad" testID="tipo-mov-cfop" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Cfop Interestadual *</Text>
                  <TextInput value={cfopFora} onChangeText={(v) => setCfopFora(v.replace(/[^0-9]/g, ""))} style={styles.input} maxLength={4} keyboardType="number-pad" testID="tipo-mov-cfop-fora" />
                </View>
              </View>

              <Text style={styles.label}>Centro de Custo</Text>
              <SelectField value={centroCusto} onChange={(v) => setCentroCusto(v as number)} options={centroCustoOptions} allowClear testID="tipo-mov-centro-custo" modalTitle="Centro de Custo" compactWeb />

              <Text style={styles.sectionTitle}>Transferências</Text>
              <SwitchRow label="Livro" value={transfLivro} onValueChange={setTransfLivro} testID="tipo-mov-transf-livro" />
              <SwitchRow label="Pagar" value={transfPagar} onValueChange={setTransfPagar} testID="tipo-mov-transf-pagar" />
              <SwitchRow label="Contabilidade" value={transfContabil} onValueChange={setTransfContabil} testID="tipo-mov-transf-contabil" />
              <SwitchRow label="Caixa" value={transfCaixa} onValueChange={setTransfCaixa} testID="tipo-mov-transf-caixa" />

              <Text style={styles.sectionTitle}>Atualizações</Text>
              <SwitchRow label="Ítens" value={itens} onValueChange={setItens} testID="tipo-mov-itens" />
              <SwitchRow label="Atualiza Estoque" value={atualizaEst} onValueChange={setAtualizaEst} testID="tipo-mov-atualiza-est" />
              <SwitchRow label="Estoque Atual" value={estoqueAtual} onValueChange={setEstoqueAtual} testID="tipo-mov-estoque-atual" />
              <SwitchRow label="Est. em Poder 3º" value={estoqueCliente} onValueChange={setEstoqueCliente} testID="tipo-mov-estoque-cliente" />
              <SwitchRow label="Est. 3º em Nosso Poder" value={estoqueFornecedor} onValueChange={setEstoqueFornecedor} testID="tipo-mov-estoque-fornecedor" />
              <SwitchRow label="Altera Custo" value={alteraCusto} onValueChange={setAlteraCusto} testID="tipo-mov-altera-custo" />
              <SwitchRow label="Altera Venda" value={alteraVenda} onValueChange={setAlteraVenda} testID="tipo-mov-altera-venda" />
              <SwitchRow label="Emite Cupom" value={emiteEcf} onValueChange={setEmiteEcf} testID="tipo-mov-emite-ecf" />

              <Text style={styles.sectionTitle}>Códigos Contábeis</Text>
              <View style={styles.rowFields}>
                <View style={styles.colFifth}>
                  <Text style={styles.label}>Livro</Text>
                  <TextInput value={codContabilLivro} onChangeText={setCodContabilLivro} style={styles.input} keyboardType="number-pad" maxLength={5} testID="tipo-mov-cc-livro" />
                </View>
                <View style={styles.colFifth}>
                  <Text style={styles.label}>Pagamento</Text>
                  <TextInput value={codContabilPag} onChangeText={setCodContabilPag} style={styles.input} keyboardType="number-pad" maxLength={5} testID="tipo-mov-cc-pag" />
                </View>
                <View style={styles.colFifth}>
                  <Text style={styles.label}>Juros</Text>
                  <TextInput value={codContabilJuros} onChangeText={setCodContabilJuros} style={styles.input} keyboardType="number-pad" maxLength={5} testID="tipo-mov-cc-juros" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Descontos</Text>
                  <TextInput value={codContabilDescontos} onChangeText={setCodContabilDescontos} style={styles.input} keyboardType="number-pad" maxLength={5} testID="tipo-mov-cc-descontos" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Acréscimos</Text>
                  <TextInput value={codContabilAcrescimos} onChangeText={setCodContabilAcrescimos} style={styles.input} keyboardType="number-pad" maxLength={5} testID="tipo-mov-cc-acrescimos" />
                </View>
              </View>

              <Text style={styles.label}>Movimentação Contra Partida</Text>
              <SelectField
                value={tipoMovContraPartida || ""}
                onChange={(v) => setTipoMovContraPartida(v ? String(v) : null)}
                options={tipoMovOptions(codigo)}
                testID="tipo-mov-contra-partida"
                modalTitle="Movimentação Contra Partida"
                compactWeb
              />
              <Text style={styles.label}>Prazo</Text>
              <TextInput value={prazoContraPartida} onChangeText={setPrazoContraPartida} style={styles.input} keyboardType="number-pad" maxLength={3} testID="tipo-mov-prazo" />

              <Text style={styles.label}>Movimentação Origem</Text>
              <SelectField
                value={tipoMovOrigem || ""}
                onChange={(v) => setTipoMovOrigem(v ? String(v) : null)}
                options={tipoMovOptions(codigo)}
                testID="tipo-mov-origem"
                modalTitle="Movimentação Origem"
                compactWeb
              />

              <Text style={styles.label}>Tipo Doc. *</Text>
              <SelectField value={tipoDoc} onChange={(v) => setTipoDoc(v as number)} options={tipoDocOptions} testID="tipo-mov-tipo-doc" modalTitle="Tipo de Documento" compactWeb />

              <Text style={styles.label}>Situação</Text>
              <SelectField value={situacao} onChange={(v) => setSituacao(v as string)} options={situacaoOptions} allowClear testID="tipo-mov-situacao" modalTitle="Situação" compactWeb />

              <Text style={styles.label}>Código Danfe</Text>
              <TextInput value={codigoDanfe} onChangeText={setCodigoDanfe} style={styles.input} keyboardType="number-pad" maxLength={3} testID="tipo-mov-codigo-danfe" />

              {canSave ? (
                <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="tipo-mov-salvar">
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                </Pressable>
              ) : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { width: "100%", maxWidth: 900, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 40 },
  scrollWeb: WEB_SCROLL_CENTER,
  colunas: { flexDirection: "row", gap: spacing.md, width: "100%" },
  coluna: { flex: 1, gap: spacing.xs },
  colunaTitulo: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.sm,
  },
  rowTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8, marginBottom: 8, fontSize: 12 },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", marginTop: spacing.xs, padding: spacing.xs },
  addBtnText: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: Platform.OS === "web" ? "center" : "flex-end", paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0, paddingVertical: Platform.OS === "web" ? spacing.xl : 0 },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: Platform.OS === "web" ? radius.lg : 18,
    borderTopRightRadius: Platform.OS === "web" ? radius.lg : 18,
    borderBottomLeftRadius: Platform.OS === "web" ? radius.lg : 0,
    borderBottomRightRadius: Platform.OS === "web" ? radius.lg : 0,
    borderWidth: Platform.OS === "web" ? 1 : 0,
    borderColor: colors.border,
    width: "100%",
    maxWidth: Platform.OS === "web" ? 640 : undefined,
    maxHeight: "92%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.lg : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  colHalf: { flex: 1 },
  colFifth: { flex: 1 },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 4 },
  switchLabel: { fontSize: 13, color: colors.onSurface },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});

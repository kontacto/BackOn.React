// Digitação de Estoque (Inventário) — busca o produto (cascata código
// interno/de fábrica/de barras, ou chassi/código pra veículos) e grava a
// quantidade contada. Legado: `FrmInvDig.frm`. Só acessível com um balanço
// aberto (o backend também reforça essa checagem). Ver
// backend/services/inventario_service.py e PENDENCIAS.md > "Inventário".
//
// "Incluir" SOMA a quantidade à contagem já existente daquele item neste
// balanço (mesmo comportamento do legado — permite contar o mesmo produto
// em lotes/prateleiras diferentes ao longo do dia, sem perder a contagem
// anterior); "Alterar" SUBSTITUI a contagem pelo valor digitado. Essa
// diferença não é óbvia só pelo rótulo dos botões — por isso o texto de
// ajuda abaixo do campo Quantidade, além do ícone de Ajuda no cabeçalho.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaInventarioModal from "@/src/components/inventario/AjudaInventarioModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER, WEB_FILTER_CARD } from "@/src/theme/webLayout";

type ItemEncontrado = {
  codigo_interno: string;
  descricao: string;
  origem: "pecas" | "veiculos";
  estoque_atual: number;
  preco_custo: number;
  preco_venda: number;
  custo_inventario: number;
  custo_reposicao: number;
  ja_contado: boolean;
  estoque_balanco_atual: number;
};

type ItemContado = {
  codigo_interno: string;
  descricao: string;
  estoque_balanco: number;
  estoque_atual: number;
  usuario_digitacao: number | null;
  usuario_nome: string | null;
};

type ResumoUsuario = { usuario_digitacao: number | null; usuario_nome: string | null; total: number };

function grupoKey(usuarioDigitacao: number | null): string {
  return usuarioDigitacao === null ? "null" : String(usuarioDigitacao);
}

function fmt(n: number): string {
  // `String(10)` vira "10" (sem casas decimais) — errado pros campos de
  // Custo/Venda/Custo Inventário/Custo Reposição, que são sempre valores
  // monetários. `toFixed(2)` garante 2 casas sempre, igual ao resto do
  // sistema (achado ao vivo 2026-07-23: "10"/"100" na tela em vez de
  // "10,00"/"100,00").
  return (n ?? 0).toFixed(2).replace(".", ",");
}

export default function InventarioDigitacaoScreen() {
  const router = useRouter();
  const { can, isManagerFuncao, usuarioCodigo } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Digitação de Estoque está disponível apenas no web."
        testID="inventario-digitacao-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [item, setItem] = useState<ItemEncontrado | null>(null);

  const [qtd, setQtd] = useState("");
  const [precoCusto, setPrecoCusto] = useState("");
  const [precoVenda, setPrecoVenda] = useState("");
  const [custoInventario, setCustoInventario] = useState("");
  const [custoReposicao, setCustoReposicao] = useState("");
  // Qual ação está gravando agora (Incluir/Alterar são botões separados,
  // precisa saber qual delas pra não mostrar o spinner nos dois ao mesmo
  // tempo) — mesmo padrão/motivo já usado em `inventario.tsx`
  // (`processandoAcao`), regra [GLOBAL] de feedback visual >3s.
  const [salvandoAcao, setSalvandoAcao] = useState<"incluir" | "alterar" | null>(null);
  const salvando = salvandoAcao !== null;

  const [itensContados, setItensContados] = useState<ItemContado[]>([]); // não-gerente: lista plana, só a própria
  const [resumoUsuarios, setResumoUsuarios] = useState<ResumoUsuario[]>([]); // gerente: cabeçalhos dos accordions
  const [carregandoContados, setCarregandoContados] = useState(false);
  const [gruposExpandidos, setGruposExpandidos] = useState<Set<string>>(new Set());
  const [itensPorGrupo, setItensPorGrupo] = useState<Record<string, ItemContado[]>>({});
  const [gruposCarregando, setGruposCarregando] = useState<Set<string>>(new Set());

  const codigoInputRef = useRef<TextInput>(null);
  const qtdInputRef = useRef<TextInput>(null);

  const podeDigitar = can("INVENTARIO.DIGITACAO");

  const bootConn = useCallback(async () => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa);
    if (c) setConn(c);
    return c || null;
  }, [conn, router]);

  // Itens já contados neste balanço, com quem digitou cada um — pra vários
  // usuários digitando em paralelo (cada um cobrindo uma área/nível
  // diferente) saberem o que já foi coberto e por quem, evitando
  // recontagem ou item esquecido. Gerente/Supervisor/Master (mesmo critério
  // de `isManagerFuncao` já usado no filtro de vendedor do Painel de
  // Pedidos) veem só o RESUMO por usuário (nome + contagem) — accordions
  // fechados por padrão; os itens de um usuário só são buscados quando o
  // próprio accordion é clicado, pra não carregar a lista inteira de todo
  // mundo de uma vez (performance, com dezenas/centenas de itens contados
  // por vários digitadores ao mesmo tempo). Os demais usuários continuam
  // vendo a lista plana de sempre (já filtrada no backend, só a própria).
  // Pedido explícito do usuário, 2026-07-23.
  const carregarContados = useCallback(async (c: Connection) => {
    setCarregandoContados(true);
    try {
      if (isManagerFuncao) {
        const r = await apiGet(c, "/api/inventario/itens/resumo");
        if (r?.success) setResumoUsuarios(r.resumo || []);
      } else {
        const r = await apiGet(c, "/api/inventario/itens", { usuario: usuarioCodigo ?? undefined });
        if (r?.success) setItensContados(r.itens || []);
      }
    } finally {
      setCarregandoContados(false);
    }
  }, [isManagerFuncao, usuarioCodigo]);

  // Busca/atualiza os itens de UM grupo (usuário) — extraído do toggle pra
  // também ser chamado depois de gravar um item, quando o grupo já está
  // expandido (ver `refrescarGruposAbertos` abaixo).
  const carregarItensGrupo = useCallback(async (c: Connection, usuarioDigitacao: number | null) => {
    const key = grupoKey(usuarioDigitacao);
    setGruposCarregando((prev) => new Set(prev).add(key));
    try {
      const params = usuarioDigitacao === null ? { sem_usuario: true } : { usuario: usuarioDigitacao };
      const r = await apiGet(c, "/api/inventario/itens", params);
      if (r?.success) {
        setItensPorGrupo((prev) => ({ ...prev, [key]: r.itens || [] }));
      } else {
        fb.showError(friendlyApiError(r, "Não foi possível carregar os itens deste usuário."));
      }
    } finally {
      setGruposCarregando((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }, [fb]);

  // Expande/recolhe o accordion de um usuário. Só busca os itens de fato
  // na hora de EXPANDIR (nunca ao recolher, nunca de forma automática) —
  // "a quebra de lista só é atualizada se clicar no usuário", pedido
  // explícito do usuário, 2026-07-23.
  const toggleGrupoUsuario = useCallback(async (resumo: ResumoUsuario) => {
    const key = grupoKey(resumo.usuario_digitacao);
    if (gruposExpandidos.has(key)) {
      setGruposExpandidos((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
      return;
    }
    const c = await bootConn();
    if (!c) return;
    await carregarItensGrupo(c, resumo.usuario_digitacao);
    setGruposExpandidos((prev) => new Set(prev).add(key));
  }, [gruposExpandidos, bootConn, carregarItensGrupo]);

  // Achado ao vivo 2026-07-23: gravar um item não atualizava a lista de um
  // grupo já expandido (só o resumo/contagem do cabeçalho era refeito) —
  // quem estava com o próprio accordion aberto digitando vários itens
  // seguidos não via a lista crescer. Depois de gravar, refaz a busca de
  // TODO grupo que já estiver expandido (não só o do usuário atual — outro
  // gerente pode estar com o grupo de um colega aberto na tela ao mesmo
  // tempo), mantendo o princípio "só busca de novo o que já estava
  // visível", sem virar uma recarga geral de tudo.
  const refrescarGruposAbertos = useCallback(async (c: Connection) => {
    await Promise.all(
      Array.from(gruposExpandidos).map((key) =>
        carregarItensGrupo(c, key === "null" ? null : Number(key)),
      ),
    );
  }, [gruposExpandidos, carregarItensGrupo]);

  useEffect(() => {
    (async () => {
      const c = await bootConn();
      if (c) carregarContados(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Foca a Quantidade assim que o item é encontrado (o campo só existe no
  // DOM depois desse re-render — chamar `.focus()` direto dentro de
  // `buscar()`, logo após `setItem`, não funciona, o ref ainda está null
  // nesse momento). Fluxo inteiro (buscar Enter, digitar Enter) sem
  // precisar do mouse — pedido explícito do usuário, 2026-07-23.
  useEffect(() => {
    if (item) qtdInputRef.current?.focus();
  }, [item]);

  const limparForm = useCallback(() => {
    setCodigo(""); setItem(null); setQtd("");
    setPrecoCusto(""); setPrecoVenda(""); setCustoInventario(""); setCustoReposicao("");
    codigoInputRef.current?.focus();
  }, []);

  const buscarCodigo = useCallback(async (termoBusca: string) => {
    const c = await bootConn();
    if (!c) return;
    const termo = termoBusca.trim();
    if (!termo) return;
    setBuscando(true);
    try {
      const r = await apiGet(c, `/api/inventario/item/${encodeURIComponent(termo)}`);
      if (!r?.success) {
        fb.showError(friendlyApiError(r, "Não foi possível buscar o item."));
        return;
      }
      if (!r.found) {
        fb.showError("Este item não está cadastrado.");
        setItem(null);
        return;
      }
      setItem(r);
      setPrecoCusto(fmt(r.preco_custo));
      setPrecoVenda(fmt(r.preco_venda));
      setCustoInventario(fmt(r.custo_inventario));
      setCustoReposicao(fmt(r.custo_reposicao));
      // Item já contado: pré-preenche a Quantidade com o valor já digitado
      // (pronto pra corrigir com Alterar) — clicar num item da lista "Itens
      // já contados" cai aqui, é assim que vira uma edição direta. Item
      // novo continua começando em branco (pronto pra Incluir). Pedido
      // explícito do usuário, 2026-07-23.
      setQtd(r.ja_contado ? fmt(r.estoque_balanco_atual) : "");
    } finally {
      setBuscando(false);
    }
  }, [bootConn, fb]);

  const buscar = useCallback(() => buscarCodigo(codigo), [buscarCodigo, codigo]);

  const abrirParaEditar = useCallback((it: ItemContado) => {
    setCodigo(it.codigo_interno);
    buscarCodigo(it.codigo_interno);
  }, [buscarCodigo]);

  const gravar = useCallback(async (endpoint: "incluir" | "alterar") => {
    const c = await bootConn();
    if (!c || !item) return;
    const qtdNum = parseFloat((qtd || "0").replace(",", "."));
    if (!qtd.trim() || isNaN(qtdNum)) { fb.showError("Informe a quantidade contada."); return; }

    const doGravar = async () => {
      setSalvandoAcao(endpoint);
      try {
        const r = await apiSend(c, `/api/inventario/itens/${endpoint}`, "POST", {
          codigo: item.codigo_interno,
          qtd: qtdNum,
          preco_custo: parseFloat((precoCusto || "0").replace(",", ".")),
          preco_venda: parseFloat((precoVenda || "0").replace(",", ".")),
          custo_inventario: parseFloat((custoInventario || "0").replace(",", ".")),
          custo_reposicao: parseFloat((custoReposicao || "0").replace(",", ".")),
          ...auditCtx,
        });
        if (r?.success) {
          fb.showSuccess(`${item.descricao}: contagem gravada (${r.estoque_balanco}).`);
          limparForm();
          carregarContados(c);
          if (isManagerFuncao) refrescarGruposAbertos(c);
        } else {
          fb.showError(friendlyApiError(r, "Não foi possível gravar o item."));
        }
      } finally {
        setSalvandoAcao(null);
      }
    };

    if (endpoint === "incluir" && item.ja_contado) {
      fb.showConfirm(
        `Este item já consta no inventário com quantidade ${item.estoque_balanco_atual}. Confirma somar mais ${qtdNum}?`,
        doGravar,
      );
    } else {
      doGravar();
    }
  }, [
    bootConn, item, qtd, precoCusto, precoVenda, custoInventario, custoReposicao, auditCtx, fb,
    limparForm, carregarContados, refrescarGruposAbertos, isManagerFuncao,
  ]);

  // Ordem decrescente por quantidade digitada (maior contagem primeiro),
  // em toda lista de itens exibida — pedido explícito do usuário,
  // 2026-07-23.
  const ordenarPorQtd = useCallback(
    (lista: ItemContado[]) => [...lista].sort((a, b) => b.estoque_balanco - a.estoque_balanco),
    [],
  );
  const itensContadosOrdenados = useMemo(() => ordenarPorQtd(itensContados), [itensContados, ordenarPorQtd]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="inventario-digitacao-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Digitação de Estoque</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline"
          label="Ajuda"
          onPress={() => setAjudaOpen(true)}
          color={colors.onBrandPrimary}
          size={22}
          testID="inventario-digitacao-ajuda"
        />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <Text style={styles.label}>Código do produto (interno, de fábrica, de barras ou chassi)</Text>
            <View style={styles.inputWithBtn}>
              <TextInput
                ref={codigoInputRef}
                style={[styles.input, { flex: 1, minWidth: 0 }]}
                value={codigo}
                onChangeText={setCodigo}
                onSubmitEditing={buscar}
                autoFocus
                selectTextOnFocus
                placeholder="Digite e pressione Enter"
                autoComplete="new-password"
                autoCorrect={false}
                textContentType="none"
                importantForAutofill="no"
                testID="inventario-digitacao-codigo"
              />
              <Pressable style={styles.searchBtn} onPress={buscar} disabled={buscando} testID="inventario-digitacao-buscar">
                {buscando ? (
                  <ActivityIndicator size="small" color={colors.onBrandPrimary} />
                ) : (
                  <Ionicons name="search-outline" size={18} color={colors.onBrandPrimary} />
                )}
              </Pressable>
            </View>

            {item ? (
              <>
                <Text style={styles.itemDescricao}>{item.descricao}</Text>
                <Text style={styles.hint}>
                  Estoque atual do sistema: {item.estoque_atual}
                  {item.ja_contado ? `  ·  Já contado neste balanço: ${item.estoque_balanco_atual}` : ""}
                </Text>

                <View style={styles.rowFields}>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Quantidade</Text>
                    {/* Enter grava sem precisar do mouse: Incluir se o item
                        ainda não foi contado neste balanço, Alterar direto
                        (sem confirmação) se já foi — pedido explícito do
                        usuário, 2026-07-23. */}
                    <TextInput
                      ref={qtdInputRef}
                      style={styles.input}
                      value={qtd}
                      onChangeText={setQtd}
                      onSubmitEditing={() => gravar(item?.ja_contado ? "alterar" : "incluir")}
                      keyboardType="numeric"
                      returnKeyType="done"
                      selectTextOnFocus
                      autoComplete="new-password"
                      autoCorrect={false}
                      textContentType="none"
                      importantForAutofill="no"
                      testID="inventario-digitacao-qtd"
                    />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Custo</Text>
                    <TextInput style={styles.input} value={precoCusto} onChangeText={setPrecoCusto} keyboardType="numeric" />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Venda</Text>
                    <TextInput style={styles.input} value={precoVenda} onChangeText={setPrecoVenda} keyboardType="numeric" />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Custo Inventário</Text>
                    <TextInput style={styles.input} value={custoInventario} onChangeText={setCustoInventario} keyboardType="numeric" />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Custo Reposição</Text>
                    <TextInput style={styles.input} value={custoReposicao} onChangeText={setCustoReposicao} keyboardType="numeric" />
                  </View>
                </View>
                <Text style={styles.hint}>
                  Incluir soma a quantidade digitada à contagem já registrada deste item (use para contar em várias
                  passagens). Alterar substitui a contagem pelo valor digitado. Pressionar Enter no campo Quantidade já
                  grava direto — Incluir se o item ainda não foi contado, Alterar se já foi.
                </Text>

                {podeDigitar ? (
                  <View style={styles.actionsRow}>
                    <Pressable
                      style={[styles.primaryBtn, salvando && styles.btnDisabled]}
                      onPress={() => gravar("incluir")}
                      disabled={salvando}
                      testID="inventario-digitacao-incluir"
                    >
                      {salvandoAcao === "incluir" ? (
                        <ActivityIndicator size="small" color={colors.onBrandPrimary} />
                      ) : (
                        <Ionicons name="add-circle-outline" size={16} color={colors.onBrandPrimary} />
                      )}
                      <Text style={styles.primaryBtnText}>{salvandoAcao === "incluir" ? "Incluindo…" : "Incluir"}</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryBtn, salvando && styles.btnDisabled]}
                      onPress={() => gravar("alterar")}
                      disabled={salvando}
                      testID="inventario-digitacao-alterar"
                    >
                      {salvandoAcao === "alterar" ? (
                        <ActivityIndicator size="small" color={colors.onSurface} />
                      ) : (
                        <Ionicons name="create-outline" size={16} color={colors.onSurface} />
                      )}
                      <Text style={styles.secondaryBtnText}>{salvandoAcao === "alterar" ? "Alterando…" : "Alterar"}</Text>
                    </Pressable>
                    <Pressable style={styles.secondaryBtn} onPress={limparForm} testID="inventario-digitacao-limpar">
                      <Text style={styles.secondaryBtnText}>Limpar</Text>
                    </Pressable>
                  </View>
                ) : null}
              </>
            ) : null}
          </View>

          <View style={[styles.card, { marginTop: spacing.md }]}>
            <View style={styles.listHeader}>
              <Text style={styles.listTitle}>
                Itens já contados neste balanço
                {isManagerFuncao
                  ? (resumoUsuarios.length > 0 ? ` (${resumoUsuarios.reduce((s, r) => s + r.total, 0)})` : "")
                  : (itensContados.length > 0 ? ` (${itensContados.length})` : "")}
              </Text>
              <Pressable
                onPress={() => conn && carregarContados(conn)}
                disabled={carregandoContados || !conn}
                hitSlop={8}
                testID="inventario-digitacao-atualizar-lista"
              >
                <Ionicons name="refresh-outline" size={18} color={colors.brandPrimary} />
              </Pressable>
            </View>
            <Text style={styles.hint}>
              {isManagerFuncao
                ? "Como Gerente/Supervisor, você vê o total de todo mundo, quebrado por usuário — toque num usuário pra abrir a lista dele (só busca na hora que abre, pra não pesar a tela)."
                : "Mostra só os itens que você mesmo já contou neste balanço — cada usuário vê apenas a própria lista."}
              {" "}Toque num item pra corrigir a quantidade dele.
            </Text>

            {isManagerFuncao ? (
              resumoUsuarios.length === 0 ? (
                <Text style={[styles.hint, { marginTop: spacing.sm }]}>
                  {carregandoContados ? "Carregando…" : "Nenhum item contado ainda."}
                </Text>
              ) : (
                <View style={{ marginTop: spacing.sm }}>
                  {resumoUsuarios.map((resumo) => {
                    const key = grupoKey(resumo.usuario_digitacao);
                    const aberto = gruposExpandidos.has(key);
                    const carregandoGrupo = gruposCarregando.has(key);
                    const nome = resumo.usuario_nome || "Usuário não identificado";
                    return (
                      <View key={key} style={{ marginBottom: spacing.xs }}>
                        <Pressable
                          style={styles.accordionHeader}
                          onPress={() => toggleGrupoUsuario(resumo)}
                          testID={`inventario-digitacao-grupo-${key}`}
                        >
                          <Ionicons name={aberto ? "chevron-down" : "chevron-forward"} size={16} color={colors.brandPrimary} />
                          <Text style={styles.groupTitle}>{nome} ({resumo.total})</Text>
                          {carregandoGrupo ? (
                            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                              <ActivityIndicator size="small" color={colors.brandPrimary} />
                              <Text style={styles.hint}>Carregando…</Text>
                            </View>
                          ) : null}
                        </Pressable>
                        {aberto ? (
                          <View>
                            {ordenarPorQtd(itensPorGrupo[key] || []).map((it) => (
                              <Pressable
                                key={it.codigo_interno}
                                style={styles.listRow}
                                onPress={() => abrirParaEditar(it)}
                                testID={`inventario-digitacao-item-${it.codigo_interno}`}
                              >
                                <Text style={[styles.listRowTitle, { flex: 1 }]}>{it.codigo_interno} — {it.descricao}</Text>
                                <Text style={styles.listRowQtd}>{it.estoque_balanco}</Text>
                                <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                              </Pressable>
                            ))}
                          </View>
                        ) : null}
                      </View>
                    );
                  })}
                </View>
              )
            ) : itensContadosOrdenados.length === 0 ? (
              <Text style={[styles.hint, { marginTop: spacing.sm }]}>
                {carregandoContados ? "Carregando…" : "Nenhum item contado ainda."}
              </Text>
            ) : (
              <View style={{ marginTop: spacing.sm }}>
                {itensContadosOrdenados.map((it) => (
                  <Pressable
                    key={it.codigo_interno}
                    style={styles.listRow}
                    onPress={() => abrirParaEditar(it)}
                    testID={`inventario-digitacao-item-${it.codigo_interno}`}
                  >
                    <Text style={[styles.listRowTitle, { flex: 1 }]}>{it.codigo_interno} — {it.descricao}</Text>
                    <Text style={styles.listRowQtd}>{it.estoque_balanco}</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                ))}
              </View>
            )}
          </View>
        </View>
      </ScrollView>

      <AjudaInventarioModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, gap: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  hint: { fontSize: 12, color: colors.muted, marginTop: 2 },
  itemDescricao: { fontSize: 15, fontWeight: "600", color: colors.onSurface, marginTop: spacing.sm },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface,
  },
  inputWithBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  searchBtn: {
    width: 40, height: 40, borderRadius: radius.sm, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.brandPrimary,
  },
  listHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  listTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  accordionHeader: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingVertical: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  groupTitle: {
    fontSize: 12, fontWeight: "700", color: colors.brandPrimary,
    textTransform: "uppercase",
  },
  listRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  listRowTitle: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  listRowQtd: { fontSize: 14, fontWeight: "700", color: colors.brandPrimary },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap", marginTop: spacing.sm },
  colTiny: { width: 110 },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  secondaryBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  btnDisabled: { opacity: 0.6 },
});

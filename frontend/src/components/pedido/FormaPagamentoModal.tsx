// Modal "Forma de Pagamento" (FrmForPag.frm) — lança múltiplas formas de
// pagamento pra um Pedido ou O.S. quando o combobox simples do cabeçalho
// não é suficiente. Tela genérica no legado (mesmo Type_FormaPagPedOS),
// confirmada pelo usuário 2026-07-16 como compartilhada por Pedido Bar,
// Pedido Completo e O.S. — por isso este componente é parametrizado por
// `tipoDav`/`tela`, não duplicado por tela.
//
// Simplificações conscientes em relação ao legado (ver PENDENCIAS.md):
// F2 (Excluir) e Duplo Clique (Alterar) viraram botões de ícone na linha —
// keybinding de grid é convenção de UI do VB6, não regra de negócio (ver
// CLAUDE.md > "Não replicar truques VB6"). Editar uma linha recarrega
// forma/valor/vencimento; os campos extras (banco/cartão/etc.) não vêm
// pré-preenchidos na edição — o usuário redigita se precisar mudar algo
// além de forma/valor/vencimento.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { formatBRL, parseNum, fmtMoney2, round2 } from "@/src/utils/format";
import { apiGet, apiSend } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import { styles } from "./styles";

const isWeb = Platform.OS === "web";

type TipoDav = "PED" | "OS";

type FormaPagOption = { codigo: string; descricao: string; tipo: string };

type ItemLancado = {
  tipo: string;
  sequencia: number;
  forma_pag: string;
  descricao: string;
  valor: number;
  vencimento: string | null;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  tipoDav: TipoDav;
  documento: number | null;
  valorTotal: number;
  tela: string; // "PEDIDO" ou "OS" — dono da permissão FORMA_PAG
  onChanged?: () => void;
};

// Tipos que pedem "Bom Para"/"Vencimento" digitado (os que não calculam
// automático via forma_pag_prazo — DU sempre recebe vencimento calculado
// no backend quando a forma tem prazo cadastrado, mas aceita o campo como
// fallback quando não tem).
const TIPOS_COM_VENCIMENTO = new Set(["CH", "CC", "CD", "DU", "VA", "FI"]);

export default function FormaPagamentoModal({
  visible, onClose, conn, tipoDav, documento, valorTotal, tela, onChanged,
}: Props) {
  const { can } = usePermissions();
  const { showConfirm } = useFeedback();
  const canGravar = can(`${tela}.FORMA_PAG`);

  const [formas, setFormas] = useState<FormaPagOption[]>([]);
  const [itens, setItens] = useState<ItemLancado[]>([]);
  const [totalLancado, setTotalLancado] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [toast, setToast] = useState<string | null>(null);
  const tref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((m: string) => {
    setToast(m);
    if (tref.current) clearTimeout(tref.current);
    tref.current = setTimeout(() => setToast(null), 1000);
  }, []);

  const [formaSel, setFormaSel] = useState<string | null>(null);
  const [valor, setValor] = useState("");
  const [vencimento, setVencimento] = useState<string | null>(null);
  const [editSequencia, setEditSequencia] = useState<number | null>(null);
  const [editTipo, setEditTipo] = useState<string | null>(null);

  const [codBanco, setCodBanco] = useState("");
  const [agencia, setAgencia] = useState("");
  const [conta, setConta] = useState("");
  const [numeroCh, setNumeroCh] = useState("");
  const [nomeCheque, setNomeCheque] = useState("");
  const [telefone, setTelefone] = useState("");
  const [numCartao1, setNumCartao1] = useState("");
  const [numCartao2, setNumCartao2] = useState("");
  const [numCartao3, setNumCartao3] = useState("");
  const [numCartao4, setNumCartao4] = useState("");
  const [mesValidade, setMesValidade] = useState("");
  const [anoValidade, setAnoValidade] = useState("");
  const [parcelas, setParcelas] = useState("");
  const [codAdministradora, setCodAdministradora] = useState("");
  const [codParcelador, setCodParcelador] = useState("");

  const tipoAtual = (editTipo || formas.find((f) => f.codigo === formaSel)?.tipo || "").toUpperCase();
  const basePath = tipoDav === "OS" ? `/api/os/${documento}/formas-pagamento` : `/api/pedidos/${documento}/formas-pagamento`;

  // Sugere sempre o valor que falta pra fechar o total — evita o usuário
  // ter que calcular/digitar de cabeça (pedido explícito do usuário).
  //
  // `round2` (2 casas) e não `fmtNum` (3 casas, pensado pra QUANTIDADE de
  // item, não valor monetário) — bug real encontrado 2026-07-17: subtração
  // de ponto flutuante (`valorTotal - lancado`) sempre deixa ruído de
  // precisão binária (ex. 83.74 - 40 = 43.739999999999995), e formatando
  // com 3 casas esse ruído aparecia como um dígito visível de verdade
  // ("43,735"/"0,005" em vez de "43,74"/"0,01"). Se o usuário gravava esse
  // valor sugerido sem perceber o problema, a 3ª casa ia pro banco de
  // verdade e o pedido nunca fechava certinho (sobrava R$0,01 de "Falta"
  // pra sempre). `fmtMoney2` sempre imprime exatamente 2 casas.
  const sugerirValorFalta = (lancado: number) => {
    const falta = round2(valorTotal - lancado);
    setValor(falta > 0 ? fmtMoney2(falta) : "");
  };

  const resetForm = () => {
    setFormaSel(null); setVencimento(null);
    setEditSequencia(null); setEditTipo(null);
    setCodBanco(""); setAgencia(""); setConta(""); setNumeroCh(""); setNomeCheque(""); setTelefone("");
    setNumCartao1(""); setNumCartao2(""); setNumCartao3(""); setNumCartao4("");
    setMesValidade(""); setAnoValidade(""); setParcelas(""); setCodAdministradora(""); setCodParcelador("");
    sugerirValorFalta(totalLancado);
  };

  const carregar = useCallback(async () => {
    if (!conn || !documento) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, basePath);
      if (j?.success) {
        setItens(j.items || []);
        const lancado = j.total_lancado || 0;
        setTotalLancado(lancado);
        if (editSequencia === null) sugerirValorFalta(lancado);
      }
    } catch {
      /* silencioso */
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, documento, basePath, editSequencia, valorTotal]);

  useEffect(() => {
    if (!visible || !conn) return;
    resetForm();
    carregar();
    (async () => {
      const jf = await apiGet(conn, "/api/forma-pagamento-completo");
      if (jf?.success) setFormas(jf.items || []);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const handleEditar = (it: ItemLancado) => {
    setEditSequencia(it.sequencia);
    setEditTipo(it.tipo);
    setFormaSel(it.forma_pag);
    // fmtMoney2 (2 casas, valor monetário) — mesmo raciocínio de
    // `sugerirValorFalta` acima, não `fmtNum` (3 casas, pensado pra
    // quantidade de item).
    setValor(fmtMoney2(it.valor));
    setVencimento(it.vencimento);
  };

  const handleExcluir = (it: ItemLancado) => {
    showConfirm(`Excluir o lançamento de ${it.descricao || it.forma_pag} (${formatBRL(it.valor)})?`, async () => {
      if (!conn) return;
      try {
        const j = await apiSend(conn, `${basePath}/${it.sequencia}`, "DELETE", {
          tipo_dav: tipoDav, tela, tipo: it.tipo,
        });
        if (j?.success) {
          showToast("Lançamento excluído.");
          if (editSequencia === it.sequencia) resetForm();
          carregar();
          onChanged?.();
        } else {
          showToast(j?.message || "Não foi possível excluir.");
        }
      } catch (e) {
        showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      }
    });
  };

  const handleGravar = async () => {
    if (!conn || !documento) return;
    if (!formaSel) { showToast("Selecione a forma de pagamento."); return; }
    // round2 na gravação (defesa em profundidade) — mesmo raciocínio de
    // `sugerirValorFalta` acima: nunca deixar um valor monetário com mais
    // de 2 casas ir pro banco, mesmo que o campo tenha sido editado à mão.
    const v = round2(parseNum(valor));
    if (!v || v <= 0) { showToast("Informe um valor maior que zero."); return; }
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        tipo_dav: tipoDav, tela, tipo: tipoAtual, forma_pag: formaSel, valor: v,
        vencimento: vencimento || null,
        cod_banco: codBanco ? Number(codBanco) : null,
        agencia: agencia ? Number(agencia) : null,
        conta: conta || null,
        numero_ch: numeroCh ? Number(numeroCh) : null,
        nome_cheque: nomeCheque || null,
        telefone: telefone || null,
        num_cartao1: numCartao1 ? Number(numCartao1) : null,
        num_cartao2: numCartao2 ? Number(numCartao2) : null,
        num_cartao3: numCartao3 ? Number(numCartao3) : null,
        num_cartao4: numCartao4 ? Number(numCartao4) : null,
        mes_validade: mesValidade ? Number(mesValidade) : null,
        ano_validade: anoValidade ? Number(anoValidade) : null,
        parcelas: parcelas ? Number(parcelas) : null,
        cod_administradora: codAdministradora ? Number(codAdministradora) : null,
        cod_parcelador: codParcelador || null,
      };
      const j = editSequencia
        ? await apiSend(conn, `${basePath}/${editSequencia}`, "PUT", body)
        : await apiSend(conn, basePath, "POST", body);
      if (j?.success) {
        showToast(editSequencia ? "Forma de pagamento atualizada." : "Forma de pagamento lançada.");
        resetForm();
        carregar();
        onChanged?.();
      } else {
        showToast(j?.message || "Não foi possível gravar.");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const diferenca = valorTotal - totalLancado;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <View>
              <Text style={styles.modalTitle}>Forma de Pagamento</Text>
              <Text style={styles.headerMeta}>
                {tipoDav === "OS" ? "OS" : "Pedido"} nº {documento} · Valor Total {formatBRL(valorTotal)}
              </Text>
            </View>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <ScrollView style={{ maxHeight: 560 }} keyboardShouldPersistTaps="handled">
            {canGravar ? (
              <View style={{ gap: spacing.sm, marginBottom: spacing.md }}>
                <View style={styles.qtdRow}>
                  <View style={{ flex: 2 }}>
                    <Text style={styles.fieldLabel}>Forma de Pagamento</Text>
                    <SelectField
                      value={formaSel}
                      onChange={(v) => setFormaSel(v == null ? null : String(v))}
                      options={formas.map((f) => ({ value: f.codigo, label: f.descricao } as SelectOption))}
                      placeholder="Selecione"
                      modalTitle="Selecionar Forma de Pagamento"
                      compactWeb
                      testID="forma-pag-modal-forma"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Valor</Text>
                    <TextInput
                      value={valor}
                      onChangeText={setValor}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="forma-pag-modal-valor"
                    />
                  </View>
                </View>

                {tipoAtual && TIPOS_COM_VENCIMENTO.has(tipoAtual) ? (
                  <View style={{ maxWidth: 200 }}>
                    <Text style={styles.fieldLabel}>{tipoAtual === "DU" || tipoAtual === "FI" ? "Vencimento" : "Bom Para"}</Text>
                    {isWeb ? (
                      <WebDateField value={vencimento} onChange={setVencimento} type="date" testID="forma-pag-modal-vencimento" />
                    ) : (
                      <DateField value={vencimento} onChange={setVencimento} placeholder="DD/MM/AAAA" testID="forma-pag-modal-vencimento" />
                    )}
                  </View>
                ) : null}

                {tipoAtual === "CH" ? (
                  <>
                    <View style={styles.qtdRow}>
                      <View style={{ maxWidth: 110 }}>
                        <Text style={styles.fieldLabel}>Banco</Text>
                        <TextInput value={codBanco} onChangeText={setCodBanco} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-banco" />
                      </View>
                      <View style={{ maxWidth: 110 }}>
                        <Text style={styles.fieldLabel}>Agência</Text>
                        <TextInput value={agencia} onChangeText={setAgencia} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-agencia" />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.fieldLabel}>Conta</Text>
                        <TextInput value={conta} onChangeText={setConta} style={styles.input} testID="forma-pag-modal-conta" />
                      </View>
                      <View style={{ maxWidth: 130 }}>
                        <Text style={styles.fieldLabel}>Número</Text>
                        <TextInput value={numeroCh} onChangeText={setNumeroCh} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-numero-ch" />
                      </View>
                    </View>
                    <View style={styles.qtdRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.fieldLabel}>Nome</Text>
                        <TextInput value={nomeCheque} onChangeText={setNomeCheque} style={styles.input} testID="forma-pag-modal-nome-cheque" />
                      </View>
                      <View style={{ maxWidth: 160 }}>
                        <Text style={styles.fieldLabel}>Telefone</Text>
                        <TextInput value={telefone} onChangeText={setTelefone} keyboardType="phone-pad" style={styles.input} testID="forma-pag-modal-telefone" />
                      </View>
                    </View>
                  </>
                ) : null}

                {tipoAtual === "CC" || tipoAtual === "CD" || tipoAtual === "FI" ? (
                  <>
                    <View style={styles.qtdRow}>
                      <View style={{ maxWidth: 90 }}>
                        <Text style={styles.fieldLabel}>Cartão 1</Text>
                        <TextInput value={numCartao1} onChangeText={setNumCartao1} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-cartao1" />
                      </View>
                      <View style={{ maxWidth: 90 }}>
                        <Text style={styles.fieldLabel}>Cartão 2</Text>
                        <TextInput value={numCartao2} onChangeText={setNumCartao2} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-cartao2" />
                      </View>
                      <View style={{ maxWidth: 90 }}>
                        <Text style={styles.fieldLabel}>Cartão 3</Text>
                        <TextInput value={numCartao3} onChangeText={setNumCartao3} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-cartao3" />
                      </View>
                      <View style={{ maxWidth: 90 }}>
                        <Text style={styles.fieldLabel}>Cartão 4</Text>
                        <TextInput value={numCartao4} onChangeText={setNumCartao4} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-cartao4" />
                      </View>
                    </View>
                    <View style={styles.qtdRow}>
                      <View style={{ maxWidth: 80 }}>
                        <Text style={styles.fieldLabel}>Mês Val.</Text>
                        <TextInput value={mesValidade} onChangeText={setMesValidade} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-mes" />
                      </View>
                      <View style={{ maxWidth: 90 }}>
                        <Text style={styles.fieldLabel}>Ano Val.</Text>
                        <TextInput value={anoValidade} onChangeText={setAnoValidade} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-ano" />
                      </View>
                      {tipoAtual !== "FI" ? (
                        <View style={{ maxWidth: 90 }}>
                          <Text style={styles.fieldLabel}>Parcelas</Text>
                          <TextInput value={parcelas} onChangeText={setParcelas} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-parcelas" />
                        </View>
                      ) : null}
                      <View style={{ flex: 1 }}>
                        <Text style={styles.fieldLabel}>Administradora</Text>
                        <TextInput value={codAdministradora} onChangeText={setCodAdministradora} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-adm" />
                      </View>
                    </View>
                  </>
                ) : null}

                {tipoAtual === "CD" ? (
                  <View style={styles.qtdRow}>
                    <View style={{ maxWidth: 110 }}>
                      <Text style={styles.fieldLabel}>Banco</Text>
                      <TextInput value={codBanco} onChangeText={setCodBanco} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-banco-cd" />
                    </View>
                    <View style={{ maxWidth: 110 }}>
                      <Text style={styles.fieldLabel}>Agência</Text>
                      <TextInput value={agencia} onChangeText={setAgencia} keyboardType="number-pad" style={styles.input} testID="forma-pag-modal-agencia-cd" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Conta</Text>
                      <TextInput value={conta} onChangeText={setConta} style={styles.input} testID="forma-pag-modal-conta-cd" />
                    </View>
                  </View>
                ) : null}

                <View style={styles.modalBtns}>
                  {editSequencia ? (
                    <Pressable onPress={resetForm} style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]} testID="forma-pag-modal-novo">
                      <Text style={styles.secondaryBtnText}>Novo</Text>
                    </Pressable>
                  ) : null}
                  <Pressable
                    onPress={handleGravar}
                    disabled={saving}
                    style={({ pressed }) => [styles.primaryBtn, (pressed || saving) && { opacity: 0.8 }]}
                    testID="forma-pag-modal-gravar"
                  >
                    {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                  </Pressable>
                </View>
              </View>
            ) : null}

            <View style={[styles.subtotalRow, { marginBottom: spacing.sm }]}>
              <Text style={styles.subtotalLabel}>Lançado {formatBRL(totalLancado)}</Text>
              <Text style={[styles.subtotalValue, diferenca !== 0 && { color: colors.error }]}>
                {diferenca === 0 ? "Confere" : `Falta ${formatBRL(diferenca)}`}
              </Text>
            </View>

            {loading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.md }} />
            ) : itens.length === 0 ? (
              <Text style={styles.emptyText}>Nenhuma forma de pagamento lançada.</Text>
            ) : (
              <View style={{ gap: spacing.sm }}>
                {itens.map((it) => (
                  <View key={`${it.tipo}-${it.sequencia}`} style={styles.itemRowCompact}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={styles.itemDescCompact} numberOfLines={1}>{it.descricao || it.forma_pag}</Text>
                      <Text style={styles.itemSubCompact}>
                        {formatBRL(it.valor)}{it.vencimento ? ` · vence ${it.vencimento.split("-").reverse().join("/")}` : ""}
                      </Text>
                    </View>
                    {canGravar ? (
                      <>
                        <TouchableOpacity onPress={() => handleEditar(it)} hitSlop={6} testID={`forma-pag-modal-editar-${it.sequencia}`}>
                          <Ionicons name="create-outline" size={18} color={colors.brandPrimary} />
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => handleExcluir(it)} hitSlop={6} testID={`forma-pag-modal-excluir-${it.sequencia}`}>
                          <Ionicons name="trash-outline" size={18} color={colors.error} />
                        </TouchableOpacity>
                      </>
                    ) : null}
                  </View>
                ))}
              </View>
            )}
          </ScrollView>

          {toast ? (
            <View style={{ marginTop: spacing.sm, alignItems: "center" }}>
              <Text style={{ color: colors.muted, fontSize: 12 }}>{toast}</Text>
            </View>
          ) : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

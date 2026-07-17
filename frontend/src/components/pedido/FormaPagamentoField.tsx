// Campo "Forma de Pagamento" compartilhado: combobox simples + botão de
// múltiplas formas + tooltip + destaque de cor quando há forma(s) já
// selecionada(s)/lançada(s). Usado por Pedido Bar (web e mobile), Pedido
// Completo e O.S. — encapsula a busca da lista de lançamentos (pro
// tooltip) e o próprio FormaPagamentoModal, pra não duplicar essa lógica
// em 4 telas (pedido explícito do usuário `[GLOBAL]`).
import { useCallback, useEffect, useState } from "react";
import { Platform, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { apiGet, apiSend } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import FormaPagamentoModal from "./FormaPagamentoModal";
import { styles } from "./styles";

type TipoDav = "PED" | "OS";

// Objeto de estilo isolado (não StyleSheet.create) — ver comentário no local
// de uso: sobrescrever `left`/`bottom` de uma classe já registrada não some
// com a regra CSS original no react-native-web.
const tooltipBoxStyle = {
  position: "absolute" as const,
  top: "100%" as const,
  right: 0,
  marginTop: 4,
  minWidth: 140,
  maxWidth: 260,
  backgroundColor: "#1a1a1a",
  borderRadius: radius.sm,
  paddingHorizontal: spacing.sm,
  paddingVertical: 6,
  gap: 2,
  zIndex: 10,
};

type Props = {
  conn: Connection | null;
  tipoDav: TipoDav;
  documento: number | null;
  tela: string; // PEDIDO / PEDIDO_COMP / OS — permissão FORMA_PAG
  valorTotal: number;
  formaPag: string;
  onFormaPagChange: (v: string) => void;
  formaPagOptions: SelectOption[];
  onChanged?: () => void; // avisa a tela dona que algo mudou (recarrega cabeçalho)
  compactWeb?: boolean;
  fieldWidth?: number; // se informado, campo com largura fixa em vez de flex:1
  disabled?: boolean;
  testIDPrefix?: string;
};

export default function FormaPagamentoField({
  conn, tipoDav, documento, tela, valorTotal, formaPag, onFormaPagChange, formaPagOptions,
  onChanged, compactWeb, fieldWidth, disabled, testIDPrefix = "forma-pag-field",
}: Props) {
  const { can, classe, usuarioCodigo } = usePermissions();
  const { showError } = useFeedback();
  const [modalOpen, setModalOpen] = useState(false);
  const [lancamentos, setLancamentos] = useState<{ descricao: string; forma_pag: string }[]>([]);
  const [tooltip, setTooltip] = useState(false);

  const basePath = tipoDav === "OS" ? `/api/os/${documento}/formas-pagamento` : `/api/pedidos/${documento}/formas-pagamento`;
  // Endpoint dedicado só pra este campo (combobox simples do cabeçalho) —
  // sem ele, escolher a forma aqui só ficava em estado local até o
  // usuário clicar em "Gravar" separadamente; se ele clicasse direto em
  // "Faturar Pedido" (ou "Fechar Pedido") antes disso, o backend ainda via
  // `forma_pag` vazio e bloqueava com "Defina a Forma de Pagamento do
  // Pedido!" — mesmo com uma forma já "selecionada" na tela (bug
  // reportado pelo usuário 2026-07-16, com print mostrando exatamente
  // esse fluxo). Agora a escolha já grava direto no banco.
  const simplesPath = tipoDav === "OS" ? `/api/os/${documento}/forma-pag-simples` : `/api/pedidos/${documento}/forma-pag-simples`;

  const carregarLancamentos = useCallback(async () => {
    if (!conn || !documento) { setLancamentos([]); return; }
    try {
      const j = await apiGet(conn, basePath);
      if (j?.success) setLancamentos(j.items || []);
    } catch {
      /* silencioso */
    }
  }, [conn, documento, basePath]);

  useEffect(() => { carregarLancamentos(); }, [carregarLancamentos]);

  const handleChangeCombobox = useCallback((v: string | number | null) => {
    const val = v == null ? "" : String(v);
    onFormaPagChange(val);
    if (!conn || !documento) return; // pedido novo — só grava no Gravar normal
    apiSend(conn, simplesPath, "POST", {
      forma_pag: val,
      usuario_alteracao: usuarioCodigo,
      classe,
      plataforma: Platform.OS,
    })
      .then((j) => {
        if (!j?.success) showError(j?.message || "Não foi possível salvar a forma de pagamento.");
      })
      .catch((e) => showError(`Falha ao salvar forma de pagamento: ${e instanceof Error ? e.message : String(e)}`));
  }, [conn, documento, simplesPath, onFormaPagChange, usuarioCodigo, classe, showError]);

  const temFormaSelecionada = !!formaPag || lancamentos.length > 0;
  // Uma forma por linha no tooltip (não concatenado com " + ") — juntar
  // tudo numa string só quebrava de forma confusa quando havia várias
  // formas (2+ lançamentos do mesmo tipo, ex. "PIX" duas vezes, ficava
  // "PIX + PIX +..." cortado no meio do "+" ao quebrar linha).
  const descricoesList = lancamentos.length > 0
    ? lancamentos.map((l) => (l.descricao || l.forma_pag || "").trim()).filter(Boolean)
    : (() => {
        const label = formaPagOptions.find((o) => o.value === formaPag)?.label;
        return label ? [label] : [];
      })();

  const canMultipla = !!documento && can(`${tela}.FORMA_PAG`);

  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
      <View
        style={[
          { borderRadius: radius.md, ...(fieldWidth ? { width: fieldWidth } : { flex: 1 }) },
          temFormaSelecionada && {
            borderWidth: 1, borderColor: colors.success, backgroundColor: colors.success + "14",
          },
        ]}
      >
        <SelectField
          value={formaPag || null}
          onChange={handleChangeCombobox}
          options={formaPagOptions}
          placeholder="Selecione"
          modalTitle="Forma de Pagamento"
          allowClear
          compactWeb={compactWeb}
          disabled={disabled}
          testID={`${testIDPrefix}-combobox`}
        />
      </View>
      {canMultipla ? (
        <View style={{ position: "relative" }}>
          <Pressable
            onPress={() => setModalOpen(true)}
            onHoverIn={() => setTooltip(true)}
            onHoverOut={() => setTooltip(false)}
            hitSlop={6}
            style={[
              { width: 36, height: 36, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
              temFormaSelecionada && { backgroundColor: colors.success + "1f" },
            ]}
            testID={`${testIDPrefix}-multipla`}
          >
            <Ionicons name="list-outline" size={20} color={temFormaSelecionada ? colors.success : colors.brandPrimary} />
          </Pressable>
          {tooltip ? (
            // Estilo próprio (não reaproveita styles.descTooltip) — esse é
            // uma classe StyleSheet.create no react-native-web, e sobrescrever
            // uma propriedade dela (left) com `undefined` num array de estilo
            // não remove a regra CSS já gerada pra classe; precisa de um
            // objeto de estilo isolado pra "top/right" funcionarem de verdade.
            <View style={tooltipBoxStyle} pointerEvents="none">
              {descricoesList.length > 0 ? (
                descricoesList.map((d, i) => (
                  <Text key={i} style={styles.descTooltipText}>{d}</Text>
                ))
              ) : (
                <Text style={styles.descTooltipText}>Múltiplas Formas de Pagamento</Text>
              )}
            </View>
          ) : null}
        </View>
      ) : null}
      <FormaPagamentoModal
        visible={modalOpen}
        onClose={() => setModalOpen(false)}
        conn={conn}
        tipoDav={tipoDav}
        documento={documento}
        valorTotal={valorTotal}
        tela={tela}
        onChanged={() => { carregarLancamentos(); onChanged?.(); }}
      />
    </View>
  );
}

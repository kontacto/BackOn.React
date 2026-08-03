import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { AppModal } from "@/src/components/AppModal";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_PRODUTO } from "@/src/components/GestorDocumentosSection";
import ModificadoresSection from "@/src/components/ModificadoresSection";
import NiveisModal from "@/src/components/NiveisModal";
import { buildNivelBreadcrumb } from "@/src/utils/nivelTree";
import FornecedorSearchModal, { FornecedorRow } from "@/src/components/FornecedorSearchModal";
import ProdutoSearchModal, { ProdutoRow } from "@/src/components/ProdutoSearchModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import WebDateField from "@/src/components/WebDateField";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import {
  useProdutoCompletoForm, ProdutoForm, FornecedorItem, SimilarItem, SecundarioItem, XmlVinculoItem, toFloat,
} from "@/src/hooks/useProdutoCompletoForm";

// Cadastro de Produtos (completo) — tabela `pecas`. Legado: FrmManPec.frm
// (Kontacto, "Cadastro de Produtos"), rastreado campo-a-campo 2026-07-14 —
// ver backend/services/produto_completo_service.py e PENDENCIAS.md >
// "Produtos (Cadastro Completo)" pro relatório de rastreio e as decisões
// tomadas (Tray real, Grade/Livro condicionados a módulo).
//
// Web-only, tela cheia (não modal) — mesmo padrão de cliente-completo.tsx/
// fornecedores.tsx/servicos.tsx (header com Gravar no topo direito, abas
// com ícone). Diferente de Cliente/Fornecedor, esta tela é ACESSADA por
// código na URL (`?codigo=P123`), não tem lista+form no mesmo arquivo — a
// lista já existe em produtos.tsx (buscador compartilhado com o picker de
// item de Pedido/O.S.), que agora navega pra cá ao tocar num item.
//
// Fornecedores/Fotografia/Anexos/Excluir são ícones no CABEÇALHO (não
// abas nem botões de conteúdo) que abrem modal — pedido explícito do
// usuário 2026-07-29 ("colocar os botões inclusive anexo na barra de
// título"); Anexos deixou de ser aba (era `GestorDocumentosSection` inline)
// e virou `AnexosModal`, mesmo componente, só reembalado em modal mais
// largo (`modalCardWebWide`, 960px — o painel lista+preview cramped no
// tier de modal compacto de 560px). Similares/Secundários e Grade
// continuam abas de verdade (mesmo padrão do legado), inalterado.

type TabKey = "principal" | "descontos" | "fiscal" | "secundarios" | "grade" | "similares" | "livro" | "modificadores" | "anexos";

type FieldProps = { form: ProdutoForm; setField: (k: string, v: string | boolean) => void };

function Txt({ form, setField, campo, label, placeholder, maxLength, disabled = false, half = false, narrow = false }: FieldProps & {
  campo: string; label: string; placeholder?: string; maxLength?: number; disabled?: boolean; half?: boolean; narrow?: boolean;
}) {
  return (
    <View style={narrow ? styles.colNarrow : (half ? styles.colHalf : styles.colFlex)}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={String(form[campo] ?? "")}
        onChangeText={(v) => setField(campo, v)}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={[styles.input, disabled && styles.inputDisabled]}
        maxLength={maxLength}
        editable={!disabled}
        testID={`produto-${campo}`}
      />
    </View>
  );
}

// `money`/`pct`: campo de Preço ou percentual — ao perder o foco, normaliza
// o valor pra 3 casas decimais (evita expor artefato de ponto flutuante cru
// vindo do backend, ex.: "118.19999694824219"); `pct` também mostra um "%"
// no final (só na exibição — nunca gravado no state/form, pra não afetar o
// parse de `toFloat` no save). Enquanto o campo está com foco, mostra o
// texto exatamente como o usuário está digitando — só reformata ao sair.
function Num({ form, setField, campo, label, placeholder, narrow = false, disabled = false, half = false, money = false, pct = false, onEmptyBlur }: FieldProps & {
  campo: string; label: string; placeholder?: string; narrow?: boolean; disabled?: boolean; half?: boolean; money?: boolean; pct?: boolean;
  // Calcula um valor de reposição quando o campo perde o foco vazio (ex.:
  // Preço de Venda/Tabela recalculados a partir de Custo Reposição × Margem
  // — CalculaPrecoVenda do legado). `null`/`undefined` = não calcula nada.
  onEmptyBlur?: () => number | null | undefined;
}) {
  const [focused, setFocused] = useState(false);
  const raw = String(form[campo] ?? "");
  const displayValue = !focused && money ? fmtMoedaInput(raw) : !focused && pct ? `${fmtPctInput(raw)}${raw.trim() ? "%" : ""}` : raw;
  const hasBlurBehavior = money || pct || !!onEmptyBlur;
  return (
    <View style={narrow ? styles.colNarrow : (half ? styles.colHalf : styles.colFlex)}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={displayValue}
        onChangeText={(v) => setField(campo, v.replace(/[^0-9,.-]/g, ""))}
        onFocus={(money || pct) ? () => setFocused(true) : undefined}
        onBlur={hasBlurBehavior ? () => {
          setFocused(false);
          if (!raw.trim() && onEmptyBlur) {
            const computed = onEmptyBlur();
            if (computed !== null && computed !== undefined && computed > 0) {
              setField(campo, money ? fmtMoeda(computed) : pct ? fmtPct(computed) : String(computed));
              return;
            }
          }
          if (raw.trim()) setField(campo, money ? fmtMoedaInput(raw) : pct ? fmtPctInput(raw) : raw);
        } : undefined}
        keyboardType="decimal-pad"
        placeholder={placeholder ?? "0,000"}
        placeholderTextColor={colors.muted}
        editable={!disabled}
        style={[styles.input, disabled && styles.inputDisabled]}
        testID={`produto-${campo}`}
      />
    </View>
  );
}

function Chk({ form, setField, campo, label, inline = false }: FieldProps & { campo: string; label: string; inline?: boolean }) {
  return (
    <View style={inline ? styles.switchRowInline : styles.switchRow}>
      <Switch value={!!form[campo]} onValueChange={(v) => setField(campo, v)} testID={`produto-${campo}-switch`} />
      <Text style={styles.switchLabel}>{label}</Text>
    </View>
  );
}

const SITUACAO_OPTS: SelectOption[] = [
  { value: "A", label: "Ativo" },
  { value: "I", label: "Inativo" },
];
// Tipo Preço (`politica_preco`, 1 char no banco — `Left(Campo(33), 1)` no
// legado) — define se o preço do produto é recalculado automaticamente a
// cada entrada de estoque (Recebimento de Produto) ou se a mudança de
// preço é sempre manual. Regra explicada pelo usuário 2026-07-29.
const TIPO_PRECO_OPTS: SelectOption[] = [
  { value: "E", label: "Entrada" },
  { value: "C", label: "Controlado" },
];

// Nível de classificação mercadológica — mesma árvore/mesmo modal de
// seleção já usado em servicos.tsx (NiveisModal, sem CRUD de árvore aqui).
type NivelFlat = { codigo: string; descricao: string; niveis: string[] };

const fmtPct = (n: number): string => n.toFixed(3).replace(".", ",");
const fmtMoeda = (n: number): string => n.toFixed(3).replace(".", ",");
// Normaliza um valor digitado (string crua, vírgula ou ponto) pra "0,000" —
// usado no `onBlur` dos campos `money`/`pct` do Num, e também pra evitar
// mostrar artefato de ponto flutuante cru vindo do backend (ex.:
// "118.19999694824219").
const fmtMoedaInput = (raw: string): string => {
  if (!raw.trim()) return raw;
  const n = parseFloat(raw.replace(",", "."));
  return Number.isFinite(n) ? fmtMoeda(n) : raw;
};
const fmtPctInput = (raw: string): string => {
  if (!raw.trim()) return raw;
  const n = parseFloat(raw.replace(",", "."));
  return Number.isFinite(n) ? fmtPct(n) : raw;
};

// Modo Didático (CLAUDE.md) — ícone único de Ajuda no cabeçalho, reunindo a
// explicação de campos/ações com efeito não-óbvio em linguagem de usuário
// final. Reaproveita o `AjudaPedidoModal` já usado em Serviços/Pedido, em
// vez de duplicar o componente.
const PRODUTO_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Estoque Atual / Reservado / Reservado OS",
    texto: "Calculados automaticamente pelas movimentações do produto (vendas, compras, O.S.) — não são digitados aqui. Só o Estoque Mínimo é editável, usado pra avisar quando o produto precisa ser reposto.",
    icon: { lib: "ion", name: "cube-outline" },
  },
  {
    titulo: "Margem Real x Margem Preço",
    texto: "\"Margem Real\" é só um cálculo automático (quanto o preço de venda/tabela está acima do custo de reposição), não pode ser editada. \"Margem Preço\" é o valor de margem que você digita — usado por outras rotinas (como reajuste de preço) como referência.",
    icon: { lib: "ion", name: "trending-up-outline" },
  },
  {
    titulo: "Preço Unidade Compra / Custo Médio",
    texto: "Preço Unidade Compra é calculado (Preço Compra Unitário × Qtd Unid Compra) — só informativo. Custo Médio é atualizado automaticamente pelas entradas de estoque, também não é digitado.",
    icon: { lib: "ion", name: "calculator-outline" },
  },
  {
    titulo: "Variações de Preços",
    texto: "Cadastra promoções para este produto — quantidade mínima, preço promocional e um código de promoção (gerado automaticamente se não informado). Dias da semana, período de data e horário são opcionais e combináveis: deixe em branco pra não restringir por aquele critério.",
    icon: { lib: "ion", name: "pricetags-outline" },
  },
  {
    titulo: "Preço por Quantidade",
    texto: "Define preços diferentes conforme a quantidade comprada (ex.: acima de 10 unidades, preço menor). A linha de quantidade 1 sempre mostra o Preço de Venda cadastrado na aba principal.",
    icon: { lib: "ion", name: "layers-outline" },
  },
  {
    titulo: "Buscar NCM/CEST",
    texto: "Ícone de lupa ao lado do campo NCM — ainda não disponível nesta versão da tela. Por enquanto, digite o código NCM/CEST diretamente.",
    icon: { lib: "ion", name: "search-outline" },
  },
  {
    titulo: "Tributos Federais % — Total",
    texto: "Soma automática de Pis + Cofins + IPI + Outros — mas se Estadual ou Federal tiver algum valor preenchido, o Total passa a mostrar só a soma desses dois. É só um resumo calculado, não precisa preencher.",
    icon: { lib: "ion", name: "stats-chart-outline" },
  },
  {
    titulo: "Definir Nível",
    texto: "Escolhe a categoria deste produto na árvore de Classificação Mercadológica (a mesma usada em relatórios e filtros de outras telas) — clique pra abrir a árvore e selecionar o nível certo.",
    icon: { lib: "ion", name: "pricetags-outline" },
  },
  {
    titulo: "Produto Web / Dias da Semana",
    texto: "\"Produto Web\" libera este produto para aparecer na listagem Web para convidados. Marcando essa opção, o ícone de calendário ao lado abre a configuração de em quais dias da semana o produto aparece — deixe todos desmarcados para aparecer todos os dias.",
    icon: { lib: "ion", name: "calendar-outline" },
  },
  {
    titulo: "Fabricante/Distribuidor",
    texto: "Código do fornecedor tratado como fabricante/marca deste produto — usado, por exemplo, ao montar a pasta de fotos do produto.",
    icon: { lib: "ion", name: "briefcase-outline" },
  },
  {
    titulo: "Fornecedores",
    texto: "Lista de fornecedores que também vendem este mesmo produto, além do fabricante principal.",
    icon: { lib: "ion", name: "people-outline" },
  },
  {
    titulo: "Fotografia",
    texto: "Anexa fotos do produto. Com o módulo Grade ligado, também permite associar uma cor a cada foto e publicar o produto no site (Tray).",
    icon: { lib: "ion", name: "image-outline" },
  },
  {
    titulo: "Grade do Produto",
    texto: "Gera produtos-filhos de verdade (cada combinação de cor/tamanho vira um produto novo, com seu próprio código) — só aparece com o módulo Grade ligado pra empresa.",
    icon: { lib: "ion", name: "grid-outline" },
  },
  {
    titulo: "Anexos",
    texto: "Documentos e imagens relacionados a este produto, guardados no Gestor de Documentos.",
    icon: { lib: "ion", name: "attach-outline" },
  },
  {
    titulo: "Excluir",
    texto: "Remove definitivamente o cadastro deste produto. Bloqueado se o produto já tiver movimentação (venda, compra, O.S.).",
    icon: { lib: "ion", name: "trash-outline" },
    cor: colors.error,
  },
];

export default function ProdutoCompletoScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ codigo?: string }>();
  const { can, moduleOn } = usePermissions();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="O Cadastro de Produtos completo está disponível apenas no web."
        testID="produto-completo-web-only"
      />
    );
  }

  const f = useProdutoCompletoForm(params.codigo);
  const [tab, setTab] = useState<TabKey>("principal");
  const [fornecedorModal, setFornecedorModal] = useState(false);
  const [fotografiaModal, setFotografiaModal] = useState(false);
  const [gradeModal, setGradeModal] = useState(false);

  const [nivelList, setNivelList] = useState<NivelFlat[]>([]);
  const [nivelModalOpen, setNivelModalOpen] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [unidadeOptions, setUnidadeOptions] = useState<SelectOption[]>([]);
  const [origemOptions, setOrigemOptions] = useState<SelectOption[]>([]);
  const [cstPisOptions, setCstPisOptions] = useState<SelectOption[]>([]);
  const [cstCofinsOptions, setCstCofinsOptions] = useState<SelectOption[]>([]);
  const [grupoPisCofinsOptions, setGrupoPisCofinsOptions] = useState<SelectOption[]>([]);

  // [Regras Globais] Campo Fabricante/Distribuidor referencia uma entidade
  // de identidade (Fornecedor) — precisa de mecanismo de busca, não só
  // digitação de código cru. Ver CLAUDE.md > "[Regras Globais]".
  const [fornecedorSearchOpen, setFornecedorSearchOpen] = useState(false);
  const [fornecedorSearchTerm, setFornecedorSearchTerm] = useState("");
  const [fornecedorSearchResults, setFornecedorSearchResults] = useState<FornecedorRow[]>([]);
  const [fornecedorSearchLoading, setFornecedorSearchLoading] = useState(false);

  useEffect(() => {
    if (!fornecedorSearchOpen || !f.conn) return;
    const term = fornecedorSearchTerm.trim();
    if (term.length < 2) { setFornecedorSearchResults([]); return; }
    const c = f.conn;
    setFornecedorSearchLoading(true);
    const timer = setTimeout(async () => {
      try {
        const base = c.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(term)}`;
        const r = await fetch(`${base}/api/fornecedores?${qs}`);
        const j = await r.json();
        setFornecedorSearchResults(j?.success ? (j.items || []) : []);
      } catch {
        setFornecedorSearchResults([]);
      } finally {
        setFornecedorSearchLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [fornecedorSearchOpen, fornecedorSearchTerm, f.conn]);

  const [anexosModalOpen, setAnexosModalOpen] = useState(false);
  const [precoQtdModalOpen, setPrecoQtdModalOpen] = useState(false);
  const [promocaoModalOpen, setPromocaoModalOpen] = useState(false);
  const [diasSemanaWebModalOpen, setDiasSemanaWebModalOpen] = useState(false);

  const handleFornecedorPick = (item: FornecedorRow) => {
    f.setField("fornecedor", item.codigo_int);
    f.setFornecedorNome(item.fantasia || item.nome);
    setFornecedorSearchOpen(false);
    setFornecedorSearchTerm("");
    setFornecedorSearchResults([]);
  };

  useEffect(() => {
    if (!f.conn) return;
    (async () => {
      try {
        const c = f.conn!;
        const base = c.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
        const r = await fetch(`${base}/api/relatorios/margem-lucro/niveis?${qs}`);
        const j = await r.json();
        if (j?.success) setNivelList(j.niveis || []);
      } catch {
        // silencioso — seletor de nível fica sem opção de resolver o label atual
      }
    })();
  }, [f.conn]);

  // Unidade Compra/Unidade Venda passam a puxar da tabela auxiliar Unidade
  // de Medida (`unid`, mesma tela `unidade-medida.tsx`) em vez de texto
  // livre — pedido explícito do usuário, 2026-07-29. Não existe endpoint de
  // lookup enxuto pra essa tabela ainda (só o CRUD completo, já leve o
  // bastante: codigo/descricao/permite_decimais), então reaproveita
  // `GET /api/tabelas/unid` direto.
  useEffect(() => {
    if (!f.conn) return;
    (async () => {
      try {
        const c = f.conn!;
        const base = c.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
        const r = await fetch(`${base}/api/tabelas/unid?${qs}`);
        const j = await r.json();
        if (j?.success) {
          setUnidadeOptions((j.items || []).map((u: any) => ({ value: u.codigo, label: `${u.codigo} · ${u.descricao}` })));
        }
      } catch {
        // silencioso — combobox fica sem opções, campo continua editável por código
      }
    })();
  }, [f.conn]);

  // Origem passa a exibir a descrição da tabela auxiliar `origem` (ex.: "0 ·
  // Mercadorias Nacionais") em vez do código cru — pedido explícito do
  // usuário, 2026-07-29.
  useEffect(() => {
    if (!f.conn) return;
    (async () => {
      try {
        const c = f.conn!;
        const base = c.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
        const r = await fetch(`${base}/api/tabelas/origem?${qs}`);
        const j = await r.json();
        if (j?.success) {
          setOrigemOptions((j.items || []).map((o: any) => ({ value: o.codigo, label: `${o.codigo} · ${o.descricao}` })));
        }
      } catch {
        // silencioso — combobox fica vazio, campo continua gravando o código
      }
    })();
  }, [f.conn]);

  // Pis→Cst / Cofins→Cst / Grupo PIS/COFINS — mesmos lookups já usados em
  // servicos.tsx (CST Pis/Cofins são vocabulário fixo da legislação; Grupo
  // PIS/COFINS é a tabela auxiliar já com CRUD completo) — reaproveitados
  // aqui em vez de texto livre, mesmo princípio da regra "Campos de
  // Identidade Precisam de Mecanismo de Busca".
  useEffect(() => {
    if (!f.conn) return;
    (async () => {
      try {
        const c = f.conn!;
        const base = c.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
        const [rPis, rCofins, rGrupo] = await Promise.all([
          fetch(`${base}/api/cst-pis?${qs}`).then((r) => r.json()).catch(() => null),
          fetch(`${base}/api/cst-cofins?${qs}`).then((r) => r.json()).catch(() => null),
          fetch(`${base}/api/tabelas/grupo-pis-cofins?${qs}`).then((r) => r.json()).catch(() => null),
        ]);
        if (rPis?.success) setCstPisOptions(rPis.items.map((i: any) => ({ value: i.codigo, label: `${i.codigo} — ${i.descricao}` })));
        if (rCofins?.success) setCstCofinsOptions(rCofins.items.map((i: any) => ({ value: i.codigo, label: `${i.codigo} — ${i.descricao}` })));
        if (rGrupo?.success) setGrupoPisCofinsOptions(rGrupo.items.map((i: any) => ({ value: i.codigo, label: `${i.codigo} · ${i.descricao}` })));
      } catch {
        // silencioso — combos ficam vazios, campos continuam gravando o código
      }
    })();
  }, [f.conn]);

  // "UN" como padrão só em produto NOVO (nunca sobrescreve um produto já
  // gravado carregado pra edição).
  useEffect(() => {
    if (f.editingCodigo) return;
    if (!f.form.un_compra) f.setField("un_compra", "UN");
    if (!f.form.unidade_medida) f.setField("unidade_medida", "UN");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.editingCodigo]);

  const nivelSegments = ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"].map((k) => String(f.form[k] || ""));
  const nivelCodigoAtual = nivelSegments.filter((p) => p.trim()).join("");
  const nivelLabel = nivelCodigoAtual ? (buildNivelBreadcrumb(nivelList, nivelCodigoAtual) || nivelCodigoAtual) : "";

  // "Total" do card Tributos Federais % — replica a fórmula do legado
  // (`Federais_Change`, FrmManPec.frm): soma Pis+Cofins+IPI+Outros, mas se
  // Estadual OU Federal tiver valor, o total passa a ser só a soma desses
  // dois. "Icms" do legado (lookup em `taxas` por `cod_icms`) não entra
  // aqui — não portado, ver PENDENCIAS.md.
  const tribEstadual = toFloat(f.form.IBPT_ESTADUAIS);
  const tribFederal = toFloat(f.form.IBPT_FEDERAIS);
  const tributosFederaisTotal = (tribEstadual || tribFederal)
    ? tribEstadual + tribFederal
    : toFloat(f.form.perc_valor_pis) + toFloat(f.form.perc_valor_cofins) + toFloat(f.form.perc_ipi) + toFloat(f.form.outros_trib_federais);

  const handleNivelPick = (codigoNivel: string, label: string) => {
    setNivelModalOpen(false);
    const found = codigoNivel ? nivelList.find((n) => n.codigo === codigoNivel) : undefined;
    const segs = found ? found.niveis : ["", "", "", "", ""];
    f.setField("nivel1", segs[0] || "");
    f.setField("nivel2", segs[1] || "");
    f.setField("nivel3", segs[2] || "");
    f.setField("nivel4", segs[3] || "");
    f.setField("nivel5", segs[4] || "");
  };

  const canSave = can("PRODUTO_COMP.GRAVAR");
  const gradeOn = moduleOn("grade");
  const livroOn = moduleOn("Livraria");
  // Modificadores só faz sentido com o módulo Bar ligado — pedido explícito
  // do usuário, 2026-07-23 (ver modificadores.tsx e PENDENCIAS.md).
  const modificadoresOn = moduleOn("Bar");

  const TABS: { key: TabKey; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { key: "principal", label: "Dados Principais", icon: "cube-outline" },
    { key: "descontos", label: "Descontos e Comissões", icon: "pricetag-outline" },
    { key: "fiscal", label: "Configurações Fiscais", icon: "receipt-outline" },
    { key: "secundarios", label: "Dados Secundários", icon: "layers-outline" },
    ...(gradeOn ? [{ key: "grade" as TabKey, label: "Grade do Produto", icon: "grid-outline" as const }] : []),
    { key: "similares", label: "Similares e Equivalentes", icon: "git-compare-outline" },
    ...(livroOn ? [{ key: "livro" as TabKey, label: "Livro", icon: "book-outline" as const }] : []),
    ...(modificadoresOn ? [{ key: "modificadores" as TabKey, label: "Modificadores", icon: "options-outline" as const }] : []),
  ];

  const handleSave = async () => {
    const result = await f.save();
    if (result && !result.wasEditing) {
      router.replace({ pathname: "/produto-completo", params: { codigo: result.codigo_int } });
    }
  };

  const handleDelete = () => {
    Alert.alert("Excluir", `Confirma a exclusão do produto "${f.editingCodigo}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          if (await f.deleteProduto()) router.back();
        },
      },
    ]);
  };

  if (f.loadingInit) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="produto-completo-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]} hitSlop={12} testID="produto-completo-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {String(f.form.descricao || "") || "Novo Produto"}
        </Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 14 }}>
          <IconButtonWithTooltip
            icon="briefcase-outline"
            label={`Fornecedores (${f.fornecedores.length})`}
            onPress={() => (f.editingCodigo ? setFornecedorModal(true) : Alert.alert("Grave o produto primeiro"))}
            disabled={!can("PRODUTO_COMP.FORNECEDORES")}
            color={colors.onBrandPrimary}
            badge={f.fornecedores.length > 0}
            testID="produto-completo-btn-fornecedores"
          />
          <IconButtonWithTooltip
            icon="image-outline"
            label="Fotografia"
            onPress={() => (f.editingCodigo ? setFotografiaModal(true) : Alert.alert("Grave o produto primeiro"))}
            disabled={!can("PRODUTO_COMP.FOTOGRAFIA")}
            color={colors.onBrandPrimary}
            testID="produto-completo-btn-fotografia"
          />
          {f.editingCodigo ? (
            <IconButtonWithTooltip
              icon="attach-outline"
              label="Anexos"
              onPress={() => setAnexosModalOpen(true)}
              color={colors.onBrandPrimary}
              testID="produto-completo-btn-anexos"
            />
          ) : null}
          {f.editingCodigo && can("PRODUTO_COMP.EXCLUIR") ? (
            <IconButtonWithTooltip
              icon="trash-outline"
              label="Excluir"
              onPress={handleDelete}
              color={colors.onBrandPrimary}
              testID="produto-completo-btn-excluir"
            />
          ) : null}
          <IconButtonWithTooltip
            icon="information-circle-outline"
            label="Ajuda"
            onPress={() => setAjudaOpen(true)}
            color={colors.onBrandPrimary}
            testID="produto-completo-ajuda"
          />
          {canSave ? (
            <Pressable onPress={handleSave} disabled={f.saving} style={({ pressed }) => [styles.saveBtn, (pressed || f.saving) && { opacity: 0.7 }]} testID="produto-completo-save">
              {f.saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                <>
                  <Ionicons name="save-outline" size={16} color={colors.onBrandPrimary} />
                  <Text style={styles.saveLabel}>Gravar</Text>
                </>
              )}
            </Pressable>
          ) : null}
        </View>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          {/* Identidade do produto — sempre visível, qualquer que seja a aba
              selecionada (mesmo padrão do FrmManPec.frm legado: código,
              descrição e aplicação ficam ACIMA da barra de abas, nunca
              escondidos ao trocar de aba). Ver CLAUDE.md > "Produto Completo". */}
          <View style={styles.card}>
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Código Interno</Text>
                <TextInput
                  value={String(f.form.codigo_int || "")}
                  onChangeText={(v) => f.setField("codigo_int", v.toUpperCase())}
                  onBlur={() => {
                    const val = String(f.form.codigo_int || "").trim();
                    if (val) f.buscarPorCodigoInt(val);
                  }}
                  placeholder="novo"
                  placeholderTextColor={colors.muted}
                  autoCapitalize="characters"
                  style={styles.input}
                  testID="produto-codigo_int"
                />
              </View>
              <Txt form={f.form} setField={f.setField} campo="codigo_fab" label="Código de Fábrica/Referência" />
              <Txt form={f.form} setField={f.setField} campo="codigo_bar" label="Código de Barras" />
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Situação</Text>
                <SelectField value={String(f.form.situacao || "A")} onChange={(v) => f.setField("situacao", String(v))} options={SITUACAO_OPTS} testID="produto-situacao" compactWeb />
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "flex-end", paddingBottom: 11, gap: spacing.sm }}>
                <Chk form={f.form} setField={f.setField} campo="Produto_web" label="Produto Web" inline />
                <IconButtonWithTooltip
                  icon="calendar-outline"
                  label="Dias da Semana (Web Convidado)"
                  disabled={!f.form.Produto_web}
                  onPress={() => (f.editingCodigo ? setDiasSemanaWebModalOpen(true) : f.fb.showWarning("Grave o produto primeiro"))}
                  testID="produto-btn-dias-semana-web"
                />
              </View>
            </View>

            <Text style={styles.label}>Descrição</Text>
            <TextInput value={String(f.form.descricao || "")} onChangeText={(v) => f.setField("descricao", v)} style={styles.input} testID="produto-descricao" />

            <Text style={styles.label}>Aplicação/Observações</Text>
            <TextInput value={String(f.form.Descricao_Completa || "")} onChangeText={(v) => f.setField("Descricao_Completa", v)} style={[styles.input, { minHeight: 70 }]} multiline testID="produto-aplicacao" />
          </View>

          <View style={styles.tabBar}>
            {TABS.map((t) => {
              const sel = tab === t.key;
              return (
                <Pressable key={t.key} onPress={() => setTab(t.key)} style={({ pressed }) => [styles.tabBtn, sel && styles.tabBtnSel, pressed && { opacity: 0.85 }]} testID={`produto-completo-tab-${t.key}`}>
                  <Ionicons name={t.icon} size={16} color={sel ? colors.onBrandPrimary : colors.muted} />
                  <Text style={[styles.tabLabel, sel && styles.tabLabelSel]}>{t.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {tab === "principal" ? (
            <View style={styles.card}>
              {/* Grupos abaixo replicam os campos do legado FrmManPec.frm
                  (Aba "Dados Principais": Frames Estoques/Unidades de
                  Medida/Margens/Preço de Compra e Custos/Preços/
                  Classificação Mercadológica) — pedido explícito do
                  usuário, ver CLAUDE.md > "Produto Completo". Disposição em
                  2 colunas (não a grade 3-colunas do legado) e ordem das
                  colunas ajustadas ao vivo pelo usuário, mesma seção do
                  CLAUDE.md. */}
              <View style={styles.groupColumns}>
                <View style={styles.groupColumn}>
                  <View style={styles.groupBox}>
                    <Text style={styles.groupTitle}>Margens</Text>
                    <View style={styles.groupFieldsRow}>
                      <View style={styles.colHalf}>
                        <Text style={styles.label}>Margem Real de Venda</Text>
                        <Text style={styles.readonlyValue}>
                          {fmtPct(toFloat(f.form.custo_reposicao) > 0 ? ((toFloat(f.form.p_venda) - toFloat(f.form.custo_reposicao)) * 100) / toFloat(f.form.custo_reposicao) : 0)}%
                        </Text>
                      </View>
                      <View style={styles.colHalf}>
                        <Text style={styles.label}>Margem Real de Tabela</Text>
                        <Text style={styles.readonlyValue}>
                          {fmtPct(toFloat(f.form.custo_reposicao) > 0 ? ((toFloat(f.form.preco_lista) - toFloat(f.form.custo_reposicao)) * 100) / toFloat(f.form.custo_reposicao) : 0)}%
                        </Text>
                      </View>
                      <Num form={f.form} setField={f.setField} campo="margem_lucro" label="Margem Preço Venda" half pct />
                      <Num form={f.form} setField={f.setField} campo="margem_tabela" label="Margem Preço Tabela" half pct />
                    </View>
                  </View>

                  <View style={styles.groupBox}>
                    <Text style={styles.groupTitle}>Unidades de Medida</Text>
                    <View style={styles.groupFieldsRow}>
                      <View style={styles.colHalf}>
                        <Text style={styles.label}>Unidade Compra</Text>
                        <SelectField value={String(f.form.un_compra || "UN")} onChange={(v) => f.setField("un_compra", String(v))} options={unidadeOptions} testID="produto-un_compra" compactWeb />
                      </View>
                      <View style={styles.colHalf}>
                        <Text style={styles.label}>Unidade Venda</Text>
                        <SelectField value={String(f.form.unidade_medida || "UN")} onChange={(v) => f.setField("unidade_medida", String(v))} options={unidadeOptions} testID="produto-unidade_medida" compactWeb />
                      </View>
                      <Num form={f.form} setField={f.setField} campo="qtd_un_compra" label="Qtd Unid Compra" half />
                      <Num form={f.form} setField={f.setField} campo="QTD_UN_VENDA" label="Qtd Unid. Venda" half />
                    </View>
                  </View>

                  <View style={styles.groupBox}>
                    <Text style={styles.groupTitle}>Preço de Compra e Custos</Text>
                    <View style={styles.groupFieldsRow}>
                      <Num form={f.form} setField={f.setField} campo="desconto_compra" label="Desconto Compra" half pct />
                      <Num form={f.form} setField={f.setField} campo="perc_ipi" label="Perc. IPI" half pct />
                      <Num form={f.form} setField={f.setField} campo="valor_substituicao" label="Substituição Tributária" half money />
                      <View style={styles.colHalf}>
                        <Text style={styles.label}>Preço Unidade Compra</Text>
                        <Text style={styles.readonlyValue}>{fmtMoeda(toFloat(f.form.p_custo) * (toFloat(f.form.qtd_un_compra) || 1))}</Text>
                      </View>
                      <Num form={f.form} setField={f.setField} campo="p_custo" label="Preço Compra (Unitário)" half money />
                      <Num form={f.form} setField={f.setField} campo="custo_reposicao" label="Custo Reposição" half money />
                      <Num form={f.form} setField={f.setField} campo="custo_inventario" label="Custo Inventário" half money />
                      <View style={styles.colHalf}><Text style={styles.label}>Custo Médio</Text><Text style={styles.readonlyValue}>{fmtMoeda(toFloat(f.form.custo_medio))}</Text></View>
                    </View>
                  </View>
                </View>

                <View style={styles.groupColumn}>
                  <View style={styles.groupBox}>
                    <View style={styles.groupTitleRow}>
                      <Text style={styles.groupTitle}>Preços</Text>
                      <View style={{ flexDirection: "row", gap: spacing.sm }}>
                        <IconButtonWithTooltip
                          icon="pricetags-outline"
                          label="Variações de Preços"
                          onPress={() => (f.editingCodigo ? setPromocaoModalOpen(true) : f.fb.showWarning("Grave o produto primeiro"))}
                          testID="produto-btn-variacoes-precos"
                        />
                        <IconButtonWithTooltip
                          icon="layers-outline"
                          label="Preço por Quantidade"
                          onPress={() => (f.editingCodigo ? setPrecoQtdModalOpen(true) : f.fb.showWarning("Grave o produto primeiro"))}
                          testID="produto-btn-preco-quantidade"
                        />
                      </View>
                    </View>
                    {/* Preço de Venda/Tabela vazios se auto-calculam no
                        blur a partir de Custo Reposição × Margem — mesma
                        fórmula do legado `CalculaPrecoVenda` (variante sem
                        dedução de PIS/COFINS/Simples, mesma decisão já
                        tomada pra "Margem Real" acima), pedido explícito do
                        usuário 2026-07-29. Nunca sobrescreve um valor já
                        digitado. */}
                    <View style={styles.groupFieldsRow}>
                      <Num
                        form={f.form} setField={f.setField} campo="p_venda" label="Preço de Venda" half money
                        onEmptyBlur={() => {
                          const custo = toFloat(f.form.custo_reposicao);
                          return custo > 0 ? custo * (1 + toFloat(f.form.margem_lucro) / 100) : null;
                        }}
                      />
                      <Num
                        form={f.form} setField={f.setField} campo="preco_lista" label="Preço de Tabela" half money
                        onEmptyBlur={() => {
                          const custo = toFloat(f.form.custo_reposicao);
                          return custo > 0 ? custo * (1 + toFloat(f.form.margem_tabela) / 100) : null;
                        }}
                      />
                      <View style={styles.colHalf}>
                        <Text style={styles.label}>Tipo Preço</Text>
                        <SelectField value={String(f.form.politica_preco || "")} onChange={(v) => f.setField("politica_preco", String(v))} options={TIPO_PRECO_OPTS} allowClear testID="produto-politica_preco" compactWeb />
                      </View>
                    </View>
                  </View>

                  <View style={styles.groupBox}>
                    <Text style={styles.groupTitle}>Classificação Mercadológica / Fabricante</Text>
                    <Text style={styles.label}>Fabricante/Distribuidor</Text>
                    <Pressable onPress={() => setFornecedorSearchOpen(true)} style={styles.nivelBox} testID="produto-fabricante-selecionar">
                      <Text style={f.form.fornecedor ? styles.nivelValue : styles.nivelPlaceholder}>
                        {f.form.fornecedor ? `${f.form.fornecedor}${f.fornecedorNome ? ` · ${f.fornecedorNome}` : ""}` : "Buscar fornecedor…"}
                      </Text>
                      <Ionicons name="search-outline" size={18} color={colors.muted} />
                    </Pressable>
                    <Pressable onPress={() => setNivelModalOpen(true)} style={styles.nivelBox} testID="produto-nivel-selecionar">
                      <Text style={nivelLabel ? styles.nivelValue : styles.nivelPlaceholder}>
                        {nivelLabel || "Definir Nível"}
                      </Text>
                      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                    </Pressable>
                  </View>

                  <View style={styles.groupBox}>
                    <Text style={styles.groupTitle}>Estoques</Text>
                    <View style={styles.groupFieldsRow}>
                      <View style={[styles.colHalf, styles.statInlineRow]}>
                        <Text style={styles.statLabel}>Estoque Atual</Text>
                        <Text style={styles.statValue}>{String(f.form.qtd || 0)}</Text>
                      </View>
                      <View style={[styles.colHalf, styles.statInlineRow]}>
                        <Text style={styles.statLabel}>Reservado OS</Text>
                        <Text style={styles.statValue}>{String(f.form.reservado_os || 0)}</Text>
                      </View>
                      <View style={styles.colHalf}><Text style={styles.label}>Reservado</Text><Text style={styles.readonlyValue}>{String(f.form.reservado || 0)}</Text></View>
                      <Num form={f.form} setField={f.setField} campo="estoque_minimo" label="Estoque Mínimo" half />
                    </View>
                  </View>
                </View>
              </View>
            </View>
          ) : null}

          {tab === "descontos" ? (
            <View style={styles.card}>
              <View style={styles.sectionTitleRow}>
                <Text style={[styles.sectionTitle, { marginTop: 0, marginBottom: 0 }]}>Descontos</Text>
                <Chk form={f.form} setField={f.setField} campo="aceita_desconto" label="Aceita Desconto" inline />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="desc_g" label="Desconto Grupo" narrow pct />
                <Num form={f.form} setField={f.setField} campo="desc_s" label="Desconto Subgrupo" narrow pct />
                <Num form={f.form} setField={f.setField} campo="desc_v" label="Desconto Vendedor" narrow pct />
              </View>

              <View style={styles.sectionTitleRow}>
                <Text style={[styles.sectionTitle, { marginTop: 0, marginBottom: 0 }]}>Comissões</Text>
                <Chk form={f.form} setField={f.setField} campo="paga_comissao" label="Paga Comissão" inline />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="comissao" label="Comissão" narrow pct />
                <Num form={f.form} setField={f.setField} campo="comissao_e" label="Comissão Executor" narrow pct />
                <Num form={f.form} setField={f.setField} campo="comissao_a" label="Comissão Atendente" narrow pct />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="valor_comissao" label="Valor Comissão" money />
                <Num form={f.form} setField={f.setField} campo="Valor_Comissão_E" label="Valor Comissão Executor" money />
                <Num form={f.form} setField={f.setField} campo="Valor_Comissão_A" label="Valor Comissão Atendente" money />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="valor_desc_base_comissao" label="Desc. Base Comissão" pct />
                <Num form={f.form} setField={f.setField} campo="valor_desc_base_comissao_e" label="Desc. Base Com. Executor" pct />
                <Num form={f.form} setField={f.setField} campo="valor_desc_base_comissao_a" label="Desc. Base Com. Atendente" pct />
              </View>
            </View>
          ) : null}

          {tab === "fiscal" ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Descrições</Text>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="descricao_pdv" label="Descrição NFCe" />
                <Txt form={f.form} setField={f.setField} campo="descricao_embarque" label="Descrição Embarque" />
              </View>
              <Text style={styles.label}>Descrição NF</Text>
              <TextInput value={String(f.form.descricao_nf || "")} onChangeText={(v) => f.setField("descricao_nf", v)} style={[styles.input, { minHeight: 44 }]} multiline testID="produto-descricao-nf" />

              {/* Classificações Fiscais/Impostos replicam a disposição
                  compacta do legado (Frame13/Frame38/Frame29 do
                  FrmManPec.frm) — campos estreitos, agrupados na mesma
                  linha, com busca em tabela auxiliar onde o legado tinha
                  lupa. Ver CLAUDE.md > "Produto Completo". */}
              <Text style={styles.sectionTitle}>Classificações Fiscais</Text>
              <View style={styles.rowFields}>
                <View style={[styles.colNarrow, { marginRight: spacing.md }]}>
                  <Text style={styles.label}>NCM</Text>
                  <View style={styles.inlineSearchRow}>
                    <TextInput
                      value={String(f.form.codigo_mercosul || "")}
                      onChangeText={(v) => f.setField("codigo_mercosul", v)}
                      style={[styles.input, { flex: 1 }]}
                      testID="produto-codigo_mercosul"
                    />
                    <IconButtonWithTooltip
                      icon="search-outline"
                      label="Buscar NCM/CEST"
                      onPress={() => f.fb.showInfo("Busca de NCM/CEST ainda não disponível nesta versão da tela.")}
                      testID="produto-btn-busca-ncm"
                    />
                  </View>
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>CEST</Text>
                  <TextInput value={String(f.form.codigo_cest || "")} onChangeText={(v) => f.setField("codigo_cest", v)} style={styles.input} testID="produto-codigo_cest" />
                </View>
                <View style={[styles.colNarrow, { width: 220 }]}>
                  <Text style={styles.label}>Origem</Text>
                  <SelectField value={String(f.form.origem || "0")} onChange={(v) => f.setField("origem", String(v))} options={origemOptions} testID="produto-origem" compactWeb />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Cód. ICMS</Text>
                  <TextInput value={String(f.form.cod_icms || "")} onChangeText={(v) => f.setField("cod_icms", v)} style={styles.input} testID="produto-cod_icms" />
                </View>
                <Num form={f.form} setField={f.setField} campo="perc_mva" label="% MVA" narrow pct />
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Código ANP</Text>
                  <TextInput value={String(f.form.cod_anp || "")} onChangeText={(v) => f.setField("cod_anp", v)} style={styles.input} testID="produto-cod_anp" />
                </View>
                <Txt form={f.form} setField={f.setField} campo="BENEFICIO_FISCAL" label="Benefício Fiscal" />
              </View>
              <ProtocoloStSection protocoloSt={f.protocoloSt} setProtocoloSt={f.setProtocoloSt} />
              <XmlVinculosSection xmlVinculos={f.xmlVinculos} setXmlVinculos={f.setXmlVinculos} />

              <Text style={styles.sectionTitle}>Impostos (PIS, Cofins, IPI)</Text>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Pis → Cst</Text>
                  <SelectField value={String(f.form.tributacao_pis || "")} onChange={(v) => f.setField("tributacao_pis", String(v))} options={cstPisOptions} allowClear testID="produto-tributacao_pis" modalTitle="CST PIS" compactWeb />
                </View>
                <Num form={f.form} setField={f.setField} campo="perc_valor_pis" label="% PIS" narrow pct />
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Cofins → Cst</Text>
                  <SelectField value={String(f.form.tributacao_cofins || "")} onChange={(v) => f.setField("tributacao_cofins", String(v))} options={cstCofinsOptions} allowClear testID="produto-tributacao_cofins" modalTitle="CST COFINS" compactWeb />
                </View>
                <Num form={f.form} setField={f.setField} campo="perc_valor_cofins" label="% COFINS" narrow pct />
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Grupo PIS/COFINS</Text>
                  <SelectField value={String(f.form.cod_grupo_pis_cofins || "")} onChange={(v) => f.setField("cod_grupo_pis_cofins", String(v))} options={grupoPisCofinsOptions} allowClear testID="produto-cod_grupo_pis_cofins" compactWeb />
                </View>
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="valor_ipi" label="Valor IPI" narrow money />
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>CST IPI Entrada</Text>
                  <TextInput value={String(f.form.cst_ipi_entrada || "")} onChangeText={(v) => f.setField("cst_ipi_entrada", v)} style={styles.input} testID="produto-cst_ipi_entrada" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>CST IPI Saída</Text>
                  <TextInput value={String(f.form.cst_ipi_saida || "")} onChangeText={(v) => f.setField("cst_ipi_saida", v)} style={styles.input} testID="produto-cst_ipi_saida" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Enquadramento IPI</Text>
                  <TextInput value={String(f.form.ENQUADRAMENTO_IPI || "")} onChangeText={(v) => f.setField("ENQUADRAMENTO_IPI", v)} style={styles.input} testID="produto-enquadramento_ipi" />
                </View>
              </View>

              <Text style={styles.sectionTitle}>Tributos Federais %</Text>
              <View style={styles.groupBox}>
                <View style={styles.rowFields}>
                  <View style={styles.colNarrow}><Text style={styles.label}>Pis</Text><Text style={styles.readonlyValue}>{fmtPct(toFloat(f.form.perc_valor_pis))}%</Text></View>
                  <View style={styles.colNarrow}><Text style={styles.label}>Cofins</Text><Text style={styles.readonlyValue}>{fmtPct(toFloat(f.form.perc_valor_cofins))}%</Text></View>
                  <View style={styles.colNarrow}><Text style={styles.label}>IPI</Text><Text style={styles.readonlyValue}>{fmtPct(toFloat(f.form.perc_ipi))}%</Text></View>
                  <Num form={f.form} setField={f.setField} campo="outros_trib_federais" label="Outros" narrow pct />
                  <View style={styles.colNarrow}><Text style={styles.label}>Total</Text><Text style={styles.readonlyValue}>{fmtPct(tributosFederaisTotal)}%</Text></View>
                  <Num form={f.form} setField={f.setField} campo="IBPT_ESTADUAIS" label="Estadual" narrow pct />
                  <Num form={f.form} setField={f.setField} campo="IBPT_FEDERAIS" label="Federal" narrow pct />
                </View>
              </View>
            </View>
          ) : null}

          {tab === "secundarios" ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Unidades e Dimensões</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="comprimento" label="Comprimento" narrow />
                <Num form={f.form} setField={f.setField} campo="largura" label="Largura" narrow />
                <Num form={f.form} setField={f.setField} campo="altura" label="Altura" narrow />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="peso_liquido" label="Peso Líquido" narrow />
                <Num form={f.form} setField={f.setField} campo="peso_bruto" label="Peso Bruto" narrow />
                <Chk form={f.form} setField={f.setField} campo="peso_variado" label="Peso Variado" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="un_embarque" label="Unidade Embarque" />
                <Num form={f.form} setField={f.setField} campo="qtd_un_embarque" label="Qtd Un. Embarque" narrow />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="un_fracao" label="Un. Fração Venda" />
                <Num form={f.form} setField={f.setField} campo="prazo_entrega" label="Prazo Entrega" narrow />
                <Num form={f.form} setField={f.setField} campo="prazo_fornecedor" label="Prazo Fornecedor" narrow />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="prazo_garantia" label="Prazo Garantia" narrow />
                <Num form={f.form} setField={f.setField} campo="tipo_garantia" label="Tipo Garantia" narrow />
                <Chk form={f.form} setField={f.setField} campo="controla_num_serie" label="Controla Número de Série" />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="percent_frete" label="% Frete" narrow pct />
                <Num form={f.form} setField={f.setField} campo="valor_frete" label="Valor Frete" narrow money />
              </View>

              <Text style={styles.sectionTitle}>Estoque</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="estoque_maximo" label="Estoque Máximo" narrow />
                <Num form={f.form} setField={f.setField} campo="estoque_ressuprimento" label="Ressuprimento" narrow />
              </View>

              <Text style={styles.sectionTitle}>Localização / Categorias</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="area" label="Área" narrow />
                <Txt form={f.form} setField={f.setField} campo="prateleira" label="Prateleira" />
                <Num form={f.form} setField={f.setField} campo="escaninho" label="Escaninho" narrow />
                <Num form={f.form} setField={f.setField} campo="tipo" label="Tipo" narrow />
                <Num form={f.form} setField={f.setField} campo="tipo_peca" label="Tipo Peça" narrow />
                <Txt form={f.form} setField={f.setField} campo="indice_preco" label="Índice de Preço" />
              </View>

              <Text style={styles.sectionTitle}>Pontuação</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="pontuacao_a" label="Atendente" narrow />
                <Num form={f.form} setField={f.setField} campo="pontuacao_e" label="Executor" narrow />
                <Num form={f.form} setField={f.setField} campo="pontuacao_v" label="Vendedor" narrow />
              </View>

              <Text style={styles.sectionTitle}>Outras Informações</Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="p_sugestao" label="Preço Sugestão" money />
                <Num form={f.form} setField={f.setField} campo="p_garantia" label="Preço Garantia" money />
                <Num form={f.form} setField={f.setField} campo="p_sugerido" label="Preço Sugerido" money />
                <Num form={f.form} setField={f.setField} campo="preco_base" label="Preço Base" money />
                <Num form={f.form} setField={f.setField} campo="preco_promocional" label="Preço Promocional" money />
              </View>
              <Chk form={f.form} setField={f.setField} campo="preco_variado" label="Preço Variado" />
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="marca_produto" label="Marca (código)" />
                <Txt form={f.form} setField={f.setField} campo="modelo_produto" label="Modelo (código)" />
                <Txt form={f.form} setField={f.setField} campo="cod_anp" label="Código ANP" />
              </View>
              <Chk form={f.form} setField={f.setField} campo="FRETE_GRATIS_SITE" label="Frete Grátis Site" />
            </View>
          ) : null}

          {tab === "grade" ? (
            <View style={styles.card}>
              <Text style={styles.sectionHint}>
                Cada combinação de cor/tamanho gera um produto-filho de verdade, vinculado a este produto principal.
              </Text>
              {f.grade.length === 0 ? (
                <Text style={styles.empty}>Nenhum item de grade gerado ainda.</Text>
              ) : (
                f.grade.map((g) => (
                  <View key={g.equivalente} style={styles.gridRow} testID={`produto-grade-${g.equivalente}`}>
                    <Text style={styles.gridRowText}>{g.equivalente} — {g.descricao} (Cor {g.cor}, Tam. {g.tamanho})</Text>
                  </View>
                ))
              )}
              {f.editingCodigo && can("PRODUTO_COMP.GRADE") ? (
                <Pressable onPress={() => setGradeModal(true)} style={[styles.secondaryBtn, { marginTop: spacing.md }]} testID="produto-btn-inclui-grade">
                  <Ionicons name="add-circle-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.secondaryBtnText}>Inclusão de Itens na Grade</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          {tab === "similares" ? (
            <View style={styles.card}>
              <SimilaresSection similares={f.similares} setSimilares={f.setSimilares} conn={f.conn} />
              <SecundariosSection secundarios={f.secundarios} setSecundarios={f.setSecundarios} conn={f.conn} />
            </View>
          ) : null}

          {tab === "livro" ? (
            <View style={styles.card}>
              <Text style={styles.sectionHint}>
                Campos específicos do ramo livraria/editora — reaproveitam Fornecedor (Editora), Tipo Peça e Desconto Compra/Venda já definidos nas outras abas.
              </Text>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="autor" label="Autor (código)" narrow />
                <Num form={f.form} setField={f.setField} campo="serie" label="Série (código)" narrow />
              </View>
              <Text style={styles.label}>Sinopse</Text>
              <TextInput value={String(f.form.sinopse || "")} onChangeText={(v) => f.setField("sinopse", v)} style={[styles.input, { minHeight: 90 }]} multiline testID="produto-sinopse" />
              <View style={styles.checkRowGroup}>
                <Chk form={f.form} setField={f.setField} campo="lancamento" label="Lançamento" />
                <Chk form={f.form} setField={f.setField} campo="esgotado" label="Esgotado" />
              </View>
            </View>
          ) : null}


          {tab === "modificadores" ? (
            <View style={styles.card}>
              {f.conn && f.editingCodigo ? (
                <ModificadoresSection
                  api={f.conn.api} servidor={f.conn.servidor} banco={f.conn.banco}
                  tipo="P" codigo={f.editingCodigo} podeGravar={canSave}
                />
              ) : (
                <Text style={styles.empty}>Grave o produto para vincular modificadores.</Text>
              )}
            </View>
          ) : null}
        </View>
      </ScrollView>

      {f.conn && f.editingCodigo ? (
        <FornecedorModal visible={fornecedorModal} onClose={() => setFornecedorModal(false)} fornecedores={f.fornecedores} setFornecedores={f.setFornecedores} conn={f.conn} />
      ) : null}
      {f.conn && f.editingCodigo ? (
        <FotografiaModal
          visible={fotografiaModal}
          onClose={() => setFotografiaModal(false)}
          conn={f.conn}
          codigoInt={f.editingCodigo}
          gradeOn={gradeOn}
          canEnviarSite={can("PRODUTO_COMP.ENVIAR_SITE")}
          onEnviarSite={f.enviarSite}
        />
      ) : null}
      {f.editingCodigo ? (
        <GradeIncluiModal visible={gradeModal} onClose={() => setGradeModal(false)} onConfirm={f.criarItensGrade} />
      ) : null}
      {f.conn && f.editingCodigo ? (
        <AnexosModal visible={anexosModalOpen} onClose={() => setAnexosModalOpen(false)} conn={f.conn} codigoInt={f.editingCodigo} />
      ) : null}
      {f.conn && f.editingCodigo ? (
        <PrecoQtdModal
          visible={precoQtdModalOpen}
          onClose={() => setPrecoQtdModalOpen(false)}
          conn={f.conn}
          codigoInt={f.editingCodigo}
          codigoFab={String(f.form.codigo_fab || "")}
          descricao={String(f.form.descricao || "")}
          precoVenda={toFloat(f.form.p_venda)}
        />
      ) : null}
      {f.conn && f.editingCodigo ? (
        <PromocaoModal
          visible={promocaoModalOpen}
          onClose={() => setPromocaoModalOpen(false)}
          conn={f.conn}
          codigoInt={f.editingCodigo}
          codigoFab={String(f.form.codigo_fab || "")}
          descricao={String(f.form.descricao || "")}
          precoVenda={toFloat(f.form.p_venda)}
        />
      ) : null}
      {f.conn && f.editingCodigo ? (
        <DiasSemanaWebModal
          visible={diasSemanaWebModalOpen}
          onClose={() => setDiasSemanaWebModalOpen(false)}
          conn={f.conn}
          codigoInt={f.editingCodigo}
          descricao={String(f.form.descricao || "")}
        />
      ) : null}
      <NiveisModal visible={nivelModalOpen} conn={f.conn} onClose={() => setNivelModalOpen(false)} onPick={handleNivelPick} />
      <FornecedorSearchModal
        visible={fornecedorSearchOpen}
        onClose={() => setFornecedorSearchOpen(false)}
        term={fornecedorSearchTerm}
        setTerm={setFornecedorSearchTerm}
        loading={fornecedorSearchLoading}
        results={fornecedorSearchResults}
        onPick={handleFornecedorPick}
      />
      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Cadastro de Produtos" itens={PRODUTO_AJUDA_ITENS} />
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Similares / Secundários (aba "Similares e Equivalentes") — duas seções
// independentes no legado (Pecaseq/pecas_secundaria), replace-all no save.
// ---------------------------------------------------------------------------

// Hook local — busca de produto debounced (350ms), reaproveitado pelas
// seções Similares/Secundários abaixo. Mesmo padrão do topo do arquivo
// (busca de Fornecedor), só parametrizado por `tipo=P` fixo.
function useProdutoSearch(conn: { servidor: string; banco: string; api: string } | null) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<ProdutoRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !conn) return;
    const t = term.trim();
    if (t.length < 2) { setResults([]); return; }
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(t)}&tipo=P&page=1&size=30`;
        const r = await fetch(`${base}/api/produtos-servicos?${qs}`);
        const j = await r.json();
        setResults(j?.success ? (j.items || []) : []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [open, term, conn]);

  return { open, setOpen, term, setTerm, results, setResults, loading };
}

// Produtos Similares: substitutos oferecidos na venda quando o produto
// principal está sem estoque (rastreado em `Geral\frmvendas.frm` —
// `pecaseq`, consultada bidirecionalmente ao faltar estoque). Precisa de
// busca de produto no campo (não só código de fábrica cru), mesmo
// princípio de "Campos de Identidade Precisam de Mecanismo de Busca".
function SimilaresSection({ similares, setSimilares, conn }: {
  similares: SimilarItem[]; setSimilares: (v: SimilarItem[]) => void;
  conn: { servidor: string; banco: string; api: string } | null;
}) {
  const s = useProdutoSearch(conn);
  const handlePick = (p: ProdutoRow) => {
    if (!similares.some((x) => x.equivalente === p.codigo)) {
      setSimilares([...similares, { equivalente: p.codigo, descricao: p.descricao }]);
    }
    s.setOpen(false); s.setTerm(""); s.setResults([]);
  };
  return (
    <View>
      <Text style={styles.sectionTitle}>Produtos Similares</Text>
      <Text style={styles.sectionHint}>
        Substitutos oferecidos automaticamente na venda quando este produto está sem estoque.
      </Text>
      {similares.map((sim, i) => (
        <View key={`${sim.equivalente}-${i}`} style={styles.gridRow} testID={`produto-similar-${sim.equivalente}`}>
          <Text style={styles.gridRowText}>{sim.equivalente} {sim.descricao ? `— ${sim.descricao}` : ""}</Text>
          <Pressable onPress={() => setSimilares(similares.filter((_, idx) => idx !== i))} hitSlop={8}>
            <Ionicons name="trash-outline" size={18} color={colors.error} />
          </Pressable>
        </View>
      ))}
      <Pressable onPress={() => s.setOpen(true)} style={[styles.nivelBox, { marginTop: spacing.sm }]} testID="produto-similar-buscar">
        <Text style={styles.nivelPlaceholder}>Buscar produto…</Text>
        <Ionicons name="search-outline" size={18} color={colors.muted} />
      </Pressable>
      <ProdutoSearchModal visible={s.open} onClose={() => s.setOpen(false)} term={s.term} setTerm={s.setTerm} loading={s.loading} results={s.results} onPick={handlePick} />
    </View>
  );
}

// Produtos Secundários: alternates sempre oferecidos ao vender este produto
// (não só quando falta estoque, diferença confirmada em `frmvendas.frm` —
// `pecas_secundaria` é checada incondicionalmente, ao contrário de
// `pecaseq`/Similares). Mesmo mecanismo de busca de produto.
function SecundariosSection({ secundarios, setSecundarios, conn }: {
  secundarios: SecundarioItem[]; setSecundarios: (v: SecundarioItem[]) => void;
  conn: { servidor: string; banco: string; api: string } | null;
}) {
  const s = useProdutoSearch(conn);
  const handlePick = (p: ProdutoRow) => {
    if (!secundarios.some((x) => x.peca_secundaria === p.codigo)) {
      setSecundarios([...secundarios, { peca_secundaria: p.codigo, descricao: p.descricao }]);
    }
    s.setOpen(false); s.setTerm(""); s.setResults([]);
  };
  return (
    <View>
      <Text style={styles.sectionTitle}>Produtos Secundários</Text>
      <Text style={styles.sectionHint}>
        Alternativas sempre oferecidas junto com este produto ao vender, independente de estoque.
      </Text>
      {secundarios.map((sec, i) => (
        <View key={`${sec.peca_secundaria}-${i}`} style={styles.gridRow} testID={`produto-secundario-${sec.peca_secundaria}`}>
          <Text style={styles.gridRowText}>{sec.peca_secundaria} {sec.descricao ? `— ${sec.descricao}` : ""}</Text>
          <Pressable onPress={() => setSecundarios(secundarios.filter((_, idx) => idx !== i))} hitSlop={8}>
            <Ionicons name="trash-outline" size={18} color={colors.error} />
          </Pressable>
        </View>
      ))}
      <Pressable onPress={() => s.setOpen(true)} style={[styles.nivelBox, { marginTop: spacing.sm }]} testID="produto-secundario-buscar">
        <Text style={styles.nivelPlaceholder}>Buscar produto…</Text>
        <Ionicons name="search-outline" size={18} color={colors.muted} />
      </Pressable>
      <ProdutoSearchModal visible={s.open} onClose={() => s.setOpen(false)} term={s.term} setTerm={s.setTerm} loading={s.loading} results={s.results} onPick={handlePick} />
    </View>
  );
}

function XmlVinculosSection({ xmlVinculos, setXmlVinculos }: { xmlVinculos: XmlVinculoItem[]; setXmlVinculos: (v: XmlVinculoItem[]) => void }) {
  const [codXml, setCodXml] = useState("");
  return (
    <View>
      <Text style={styles.sectionTitle}>Vínculos XML do Fornecedor</Text>
      {xmlVinculos.map((x, i) => (
        <View key={`${x.codigo_xml}-${i}`} style={styles.gridRow} testID={`produto-xml-${i}`}>
          <Text style={styles.gridRowText}>{x.codigo_xml} {x.nome ? `— ${x.nome}` : ""}</Text>
          <Pressable onPress={() => setXmlVinculos(xmlVinculos.filter((_, idx) => idx !== i))} hitSlop={8}>
            <Ionicons name="trash-outline" size={18} color={colors.error} />
          </Pressable>
        </View>
      ))}
      <View style={styles.rowFields}>
        <Txt form={{ codXml }} setField={(_, v) => setCodXml(String(v))} campo="codXml" label="Código XML" />
        <Pressable
          onPress={() => { if (codXml.trim()) { setXmlVinculos([...xmlVinculos, { codigo_xml: codXml.trim(), fornecedor_xml: null }]); setCodXml(""); } }}
          style={[styles.secondaryBtn, { alignSelf: "flex-end" }]}
          testID="produto-xml-vincular"
        >
          <Text style={styles.secondaryBtnText}>Vincular</Text>
        </Pressable>
      </View>
    </View>
  );
}

const UF_LIST = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];

function ProtocoloStSection({ protocoloSt, setProtocoloSt }: { protocoloSt: string[]; setProtocoloSt: (v: string[]) => void }) {
  return (
    <View>
      <Text style={styles.sectionTitle}>Protocolo ST por UF</Text>
      <View style={styles.chipsRow}>
        {UF_LIST.map((uf) => {
          const sel = protocoloSt.includes(uf);
          return (
            <Pressable
              key={uf}
              onPress={() => setProtocoloSt(sel ? protocoloSt.filter((u) => u !== uf) : [...protocoloSt, uf])}
              style={[styles.chip, sel && styles.chipSel]}
              testID={`produto-protocolo-st-${uf}`}
            >
              <Text style={[styles.chipText, sel && { color: colors.onBrandPrimary }]}>{uf}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Fornecedores — modal (Command23_Click no legado, tabela pecas_fornecedor).
// ---------------------------------------------------------------------------

function FornecedorModal({ visible, onClose, fornecedores, setFornecedores, conn }: {
  visible: boolean; onClose: () => void; fornecedores: FornecedorItem[]; setFornecedores: (v: FornecedorItem[]) => void;
  conn: { servidor: string; banco: string; api: string } | null;
}) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<FornecedorRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    if (!searchOpen || !conn) return;
    const term = searchTerm.trim();
    if (term.length < 2) { setSearchResults([]); return; }
    setSearchLoading(true);
    const timer = setTimeout(async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(term)}`;
        const r = await fetch(`${base}/api/fornecedores?${qs}`);
        const j = await r.json();
        setSearchResults(j?.success ? (j.items || []) : []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [searchOpen, searchTerm, conn]);

  const handlePick = (item: FornecedorRow) => {
    const n = parseInt(item.codigo_int, 10);
    if (n && !fornecedores.some((f) => f.fornecedor === n)) {
      setFornecedores([...fornecedores, { fornecedor: n, sequencia: fornecedores.length + 1, nome: item.fantasia || item.nome }]);
    }
    setSearchOpen(false);
    setSearchTerm("");
    setSearchResults([]);
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Fornecedores</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          <ScrollView style={{ maxHeight: 360 }}>
            {fornecedores.map((f, i) => (
              <View key={`${f.fornecedor}-${i}`} style={styles.gridRow} testID={`produto-fornecedor-${f.fornecedor}`}>
                <Text style={styles.gridRowText}>{f.fornecedor} {f.nome ? `— ${f.nome}` : ""}</Text>
                <Pressable onPress={() => setFornecedores(fornecedores.filter((_, idx) => idx !== i))} hitSlop={8}>
                  <Ionicons name="trash-outline" size={18} color={colors.error} />
                </Pressable>
              </View>
            ))}
            {fornecedores.length === 0 ? <Text style={styles.empty}>Nenhum fornecedor vinculado.</Text> : null}
          </ScrollView>
          <Pressable onPress={() => setSearchOpen(true)} style={[styles.nivelBox, { marginTop: spacing.sm }]} testID="produto-fornecedor-buscar">
            <Text style={styles.nivelPlaceholder}>Buscar fornecedor…</Text>
            <Ionicons name="search-outline" size={18} color={colors.muted} />
          </Pressable>
          <FornecedorSearchModal
            visible={searchOpen}
            onClose={() => setSearchOpen(false)}
            term={searchTerm}
            setTerm={setSearchTerm}
            loading={searchLoading}
            results={searchResults}
            onPick={handlePick}
          />
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// ---------------------------------------------------------------------------
// Fotografia — modal (Command15_Click no legado). Módulo Grade desligado:
// só o Gestor de Documentos (Imagens). Módulo Grade ligado: FrmAsoFot
// equivalente — associar cor por foto + enviar/atualizar na Tray (ver
// backend/services/tray_service.py, "Aviso de teste" na docstring).
// ---------------------------------------------------------------------------

function FotografiaModal({ visible, onClose, conn, codigoInt, gradeOn, canEnviarSite, onEnviarSite }: {
  visible: boolean; onClose: () => void; conn: { servidor: string; banco: string; api: string };
  codigoInt: string; gradeOn: boolean; canEnviarSite: boolean; onEnviarSite: (idTray?: number) => Promise<boolean>;
}) {
  const [enviando, setEnviando] = useState(false);
  // Este modal é só pra fotos — trava o sub-grupo sempre em "Imagens" (não
  // deixa o usuário escolher outro), pedido explícito do usuário. Resolve/
  // cria o sub-grupo "Imagens" do grupo Produtos (find-or-create já existe
  // no backend, mesmo endpoint usado pra criar sub-grupo novo na aba
  // Anexos) na abertura do modal.
  const [subGrupoImagens, setSubGrupoImagens] = useState<number | null>(null);
  useEffect(() => {
    if (!visible) return;
    (async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const r = await fetch(`${base}/api/gestor-documentos/sub-grupos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, cod_grupo: GESTOR_DOC_GRUPO_PRODUTO, descricao: "Imagens" }),
        });
        const j = await r.json();
        if (j?.success) setSubGrupoImagens(j.cod_sub_grupo);
      } catch {
        // silencioso — sub-grupo fica livre (comportamento anterior) se a resolução falhar
      }
    })();
  }, [visible, conn]);
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebWide, { maxHeight: "85%" }]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Fotografia</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          <ScrollView style={{ maxHeight: 480 }}>
            <GestorDocumentosSection api={conn.api} servidor={conn.servidor} banco={conn.banco} codGrupo={GESTOR_DOC_GRUPO_PRODUTO} codigoEntidade={codigoInt} codSubGrupo={subGrupoImagens ?? undefined} />
            {gradeOn ? (
              <Text style={styles.sectionHint}>
                Depois de anexar as fotos acima, use "Cadastrar/Atualizar no Site" para publicar na Tray — a cor de
                cada foto é ajustada diretamente no Gestor de Documentos (campo "Cor").
              </Text>
            ) : null}
            {canEnviarSite ? (
              <Pressable
                onPress={async () => { setEnviando(true); await onEnviarSite(); setEnviando(false); }}
                disabled={enviando}
                style={[styles.secondaryBtn, { marginTop: spacing.md, opacity: enviando ? 0.6 : 1 }]}
                testID="produto-btn-enviar-site"
              >
                {enviando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="cloud-upload-outline" size={16} color={colors.brandPrimary} />
                    <Text style={styles.secondaryBtnText}>Cadastrar/Atualizar Produto no Site</Text>
                  </>
                )}
              </Pressable>
            ) : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// ---------------------------------------------------------------------------
// Anexos — modal aberto pelo ícone do cabeçalho (não mais aba), pedido
// explícito do usuário 2026-07-29: "Anexo é uma tela única (modal) para
// todas as telas do sistema, que muda as regras e tratamento de acordo com
// a entidade que o chamou" — mesmo `GestorDocumentosSection` que já era
// usado na aba antiga, só reembalado num modal mais largo que o padrão
// `modalCardWebCompact` (560px) porque o componente renderiza lista +
// preview lado a lado, precisa de mais espaço (ver CLAUDE.md > "Full CRUD
// Form Screen Standard" sobre esse motivo já ter travado uma tentativa
// anterior de usar modal estreito aqui).
// ---------------------------------------------------------------------------

function AnexosModal({ visible, onClose, conn, codigoInt }: {
  visible: boolean; onClose: () => void; conn: { servidor: string; banco: string; api: string }; codigoInt: string;
}) {
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebWide]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Anexos</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          <ScrollView style={{ maxHeight: 560 }}>
            <GestorDocumentosSection api={conn.api} servidor={conn.servidor} banco={conn.banco} codGrupo={GESTOR_DOC_GRUPO_PRODUTO} codigoEntidade={codigoInt} />
          </ScrollView>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// ---------------------------------------------------------------------------
// Grade — modal "Inclusão de Itens na Grade" (Command12 no legado).
// ---------------------------------------------------------------------------

function GradeIncluiModal({ visible, onClose, onConfirm }: {
  visible: boolean; onClose: () => void; onConfirm: (combinacoes: { cor: string; tamanho: string }[]) => Promise<boolean>;
}) {
  const [cor, setCor] = useState("");
  const [tamanho, setTamanho] = useState("");
  const [combinacoes, setCombinacoes] = useState<{ cor: string; tamanho: string }[]>([]);
  const [saving, setSaving] = useState(false);

  const add = () => {
    if (!cor.trim()) return;
    setCombinacoes([...combinacoes, { cor: cor.trim(), tamanho: tamanho.trim() }]);
    setCor(""); setTamanho("");
  };

  const confirm = async () => {
    if (combinacoes.length === 0) return;
    setSaving(true);
    const ok = await onConfirm(combinacoes);
    setSaving(false);
    if (ok) { setCombinacoes([]); onClose(); }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Inclusão de Itens na Grade</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          {combinacoes.map((c, i) => (
            <View key={i} style={styles.gridRow}>
              <Text style={styles.gridRowText}>Cor {c.cor} — Tamanho {c.tamanho || "—"}</Text>
              <Pressable onPress={() => setCombinacoes(combinacoes.filter((_, idx) => idx !== i))} hitSlop={8}>
                <Ionicons name="trash-outline" size={18} color={colors.error} />
              </Pressable>
            </View>
          ))}
          <View style={styles.rowFields}>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Cor (código)</Text>
              <TextInput value={cor} onChangeText={setCor} style={styles.input} testID="produto-grade-cor" />
            </View>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Tamanho</Text>
              <TextInput value={tamanho} onChangeText={setTamanho} style={styles.input} testID="produto-grade-tamanho" />
            </View>
            <Pressable onPress={add} style={[styles.secondaryBtn, { alignSelf: "flex-end" }]} testID="produto-grade-add">
              <Text style={styles.secondaryBtnText}>Adicionar</Text>
            </Pressable>
          </View>
          <Pressable onPress={confirm} disabled={saving || combinacoes.length === 0} style={[styles.saveBtnModal, (saving || combinacoes.length === 0) && { opacity: 0.6 }]} testID="produto-grade-gravar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// ---------------------------------------------------------------------------
// Preço por Quantidade — modal (Command39 no legado, `FrmValQtd`/
// `pecas_preco_qtd`). A linha de quantidade 1 vem do backend (união com
// `pecas.p_venda`, mesma query do legado) e é sempre somente-leitura aqui —
// editar o preço-base é feito na aba Dados Principais, não neste modal.
// ---------------------------------------------------------------------------

type PrecoQtdItem = { qtd: number; p_venda: number };

function PrecoQtdModal({ visible, onClose, conn, codigoInt, codigoFab, descricao, precoVenda }: {
  visible: boolean; onClose: () => void; conn: { servidor: string; banco: string; api: string };
  codigoInt: string; codigoFab: string; descricao: string; precoVenda: number;
}) {
  const fb = useFeedback();
  const [items, setItems] = useState<PrecoQtdItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [qtd, setQtd] = useState("");
  const [preco, setPreco] = useState("");
  const [saving, setSaving] = useState(false);
  const base = conn.api.replace(/\/+$/, "");

  const carregar = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/preco-qtd?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`);
      const j = await r.json();
      if (j?.success) setItems(j.items || []);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (visible) carregar(); }, [visible]);

  const gravar = async () => {
    const qtdN = toFloat(qtd);
    if (qtdN <= 0) { fb.showWarning("Defina a quantidade!"); return; }
    setSaving(true);
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/preco-qtd`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, qtd: qtdN, p_venda: toFloat(preco) }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Gravado.");
        setQtd(""); setPreco("");
        await carregar();
      } else {
        fb.showError(friendlyApiError(j, "Falha ao gravar."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setSaving(false);
    }
  };

  const excluir = async (item: PrecoQtdItem) => {
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/preco-qtd/excluir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, qtd: item.qtd }),
      });
      const j = await r.json();
      if (j?.success) await carregar();
      else fb.showError(friendlyApiError(j, "Falha ao excluir."));
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Preço por Quantidade</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          <Text style={styles.sectionHint}>{codigoInt} {codigoFab ? `· ${codigoFab}` : ""} — {descricao} — {fmtMoeda(precoVenda)}</Text>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.md }} /> : (
            <ScrollView style={{ maxHeight: 260, marginTop: spacing.sm }}>
              {items.map((it, i) => (
                <View key={`${it.qtd}-${i}`} style={styles.gridRow} testID={`produto-preco-qtd-${it.qtd}`}>
                  <Text style={styles.gridRowText}>Qtd {it.qtd} — {fmtMoeda(it.p_venda)}</Text>
                  {it.qtd !== 1 ? (
                    <Pressable onPress={() => excluir(it)} hitSlop={8}>
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                    </Pressable>
                  ) : <Text style={styles.sectionHint}>base</Text>}
                </View>
              ))}
              {items.length === 0 ? <Text style={styles.empty}>Nenhuma faixa cadastrada.</Text> : null}
            </ScrollView>
          )}

          <View style={styles.rowFields}>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Quantidade</Text>
              <TextInput value={qtd} onChangeText={(v) => setQtd(v.replace(/[^0-9,.-]/g, ""))} keyboardType="decimal-pad" style={styles.input} testID="produto-preco-qtd-qtd" />
            </View>
            <Num form={{ preco }} setField={(_, v) => setPreco(String(v))} campo="preco" label="Preço" narrow money />
          </View>
          <Pressable onPress={gravar} disabled={saving} style={[styles.saveBtnModal, saving && { opacity: 0.6 }]} testID="produto-preco-qtd-gravar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// ---------------------------------------------------------------------------
// Variações de Preços (Promoções) — modal (Command333 no legado,
// `FrmValPro`/`pecas_promocao`). `codigo_promocao` é auto-gerado
// ("{codigo}-{sequência}") quando deixado em branco — mesma regra do
// legado. Tocar numa linha carrega ela pro formulário pra editar (mesmo
// papel do campo oculto `sequencia` do legado); "Novo" limpa o formulário
// sem fechar o modal.
// ---------------------------------------------------------------------------

type PromocaoItem = {
  sequencia: number; codigo_promocao: string; descricao_promocao: string; qtd: number; p_venda: number;
  dias_semana?: string | null; data_inicio?: string | null; data_fim?: string | null;
  hora_inicio?: string | null; hora_fim?: string | null;
};

const DIAS_SEMANA_LABELS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

function descricaoPeriodoPromocao(it: PromocaoItem): string {
  const partes: string[] = [];
  if (it.dias_semana) {
    const dias = it.dias_semana.split(",").map((s) => DIAS_SEMANA_LABELS[Number(s.trim())]).filter(Boolean);
    if (dias.length) partes.push(dias.join("/"));
  }
  if (it.data_inicio || it.data_fim) partes.push(`${it.data_inicio || "…"} a ${it.data_fim || "…"}`);
  if (it.hora_inicio || it.hora_fim) partes.push(`${it.hora_inicio || "…"}–${it.hora_fim || "…"}`);
  return partes.join(" · ");
}

function PromocaoModal({ visible, onClose, conn, codigoInt, codigoFab, descricao, precoVenda }: {
  visible: boolean; onClose: () => void; conn: { servidor: string; banco: string; api: string };
  codigoInt: string; codigoFab: string; descricao: string; precoVenda: number;
}) {
  const fb = useFeedback();
  const [items, setItems] = useState<PromocaoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sequencia, setSequencia] = useState<number | null>(null);
  const [descricaoPromocao, setDescricaoPromocao] = useState("");
  const [quant, setQuant] = useState("");
  const [preco, setPreco] = useState("");
  const [codigoPromocao, setCodigoPromocao] = useState("");
  // Período opcional/combinável — sem precedente no legado, pedido
  // explícito do usuário 2026-07-29. Vazio em qualquer um = sem restrição
  // nesse critério (promoção sempre válida quanto a ele).
  const [diasSemana, setDiasSemana] = useState<string[]>([]);
  const [dataInicio, setDataInicio] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);
  const [horaInicio, setHoraInicio] = useState<string | null>(null);
  const [horaFim, setHoraFim] = useState<string | null>(null);
  const base = conn.api.replace(/\/+$/, "");

  const limpar = () => {
    setSequencia(null); setDescricaoPromocao(""); setQuant(""); setPreco(""); setCodigoPromocao("");
    setDiasSemana([]); setDataInicio(null); setDataFim(null); setHoraInicio(null); setHoraFim(null);
  };

  const toggleDia = (d: string) => {
    setDiasSemana((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  const carregar = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/promocoes?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`);
      const j = await r.json();
      if (j?.success) setItems(j.items || []);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (visible) { carregar(); limpar(); } }, [visible]);

  const editar = (it: PromocaoItem) => {
    setSequencia(it.sequencia);
    setDescricaoPromocao(it.descricao_promocao || "");
    setQuant(String(it.qtd));
    setPreco(String(it.p_venda));
    setCodigoPromocao(it.codigo_promocao || "");
    setDiasSemana((it.dias_semana || "").split(",").map((s) => s.trim()).filter(Boolean));
    setDataInicio(it.data_inicio || null);
    setDataFim(it.data_fim || null);
    setHoraInicio(it.hora_inicio || null);
    setHoraFim(it.hora_fim || null);
  };

  const gravar = async () => {
    const qtdN = toFloat(quant);
    if (qtdN <= 0) { fb.showWarning("Defina a quantidade!"); return; }
    setSaving(true);
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/promocoes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, sequencia,
          qtd: qtdN, p_venda: toFloat(preco), codigo_promocao: codigoPromocao, descricao_promocao: descricaoPromocao,
          dias_semana: diasSemana.join(","), data_inicio: dataInicio, data_fim: dataFim,
          hora_inicio: horaInicio || "", hora_fim: horaFim || "",
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Gravado.");
        limpar();
        await carregar();
      } else {
        fb.showError(friendlyApiError(j, "Falha ao gravar."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setSaving(false);
    }
  };

  const excluir = async (it: PromocaoItem) => {
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/promocoes/excluir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, sequencia: it.sequencia }),
      });
      const j = await r.json();
      if (j?.success) { if (sequencia === it.sequencia) limpar(); await carregar(); }
      else fb.showError(friendlyApiError(j, "Falha ao excluir."));
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Variações de Preços</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          <Text style={styles.sectionHint}>{codigoInt} {codigoFab ? `· ${codigoFab}` : ""} — {descricao} — {fmtMoeda(precoVenda)}</Text>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.md }} /> : (
            <ScrollView style={{ maxHeight: 220, marginTop: spacing.sm }}>
              {items.map((it) => {
                const periodo = descricaoPeriodoPromocao(it);
                return (
                  <Pressable key={it.sequencia} onPress={() => editar(it)} style={styles.gridRow} testID={`produto-promocao-${it.sequencia}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowText}>
                        {it.codigo_promocao} {it.descricao_promocao ? `— ${it.descricao_promocao}` : ""} (qtd {it.qtd}, {fmtMoeda(it.p_venda)})
                      </Text>
                      {periodo ? <Text style={styles.rowSubHint}>{periodo}</Text> : null}
                    </View>
                    <Pressable onPress={() => excluir(it)} hitSlop={8}>
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                    </Pressable>
                  </Pressable>
                );
              })}
              {items.length === 0 ? <Text style={styles.empty}>Nenhuma promoção cadastrada.</Text> : null}
            </ScrollView>
          )}

          <Text style={styles.label}>Descrição da Promoção</Text>
          <TextInput value={descricaoPromocao} onChangeText={setDescricaoPromocao} style={styles.input} testID="produto-promocao-descricao" />
          <View style={styles.rowFields}>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Quant.</Text>
              <TextInput value={quant} onChangeText={(v) => setQuant(v.replace(/[^0-9,.-]/g, ""))} keyboardType="decimal-pad" style={styles.input} testID="produto-promocao-qtd" />
            </View>
            <Num form={{ preco }} setField={(_, v) => setPreco(String(v))} campo="preco" label="Preço" narrow money />
            <View style={styles.colFlex}>
              <Text style={styles.label}>Código Promoção</Text>
              <TextInput value={codigoPromocao} onChangeText={setCodigoPromocao} placeholder="gerado automaticamente" style={styles.input} testID="produto-promocao-codigo" />
            </View>
          </View>

          <Text style={styles.sectionHint}>
            Tudo abaixo é opcional e combinável — deixe em branco pra não restringir por esse critério. Ex.: só dias
            da semana, só período de data, ou os dois junto com um horário.
          </Text>
          <Text style={styles.label}>Dias da Semana</Text>
          <View style={styles.chipsRow}>
            {DIAS_SEMANA_LABELS.map((diaLabel, i) => {
              const d = String(i);
              const sel = diasSemana.includes(d);
              return (
                <Pressable key={d} onPress={() => toggleDia(d)} style={[styles.chip, sel && styles.chipSel]} testID={`produto-promocao-dia-${d}`}>
                  <Text style={[styles.chipText, sel && { color: colors.onBrandPrimary }]}>{diaLabel}</Text>
                </Pressable>
              );
            })}
          </View>
          <View style={styles.rowFields}>
            <View style={[styles.colNarrow, { width: 120 }]}>
              <Text style={styles.label}>Data Início</Text>
              <WebDateField value={dataInicio} onChange={(v) => setDataInicio(v || null)} testID="produto-promocao-data-inicio" />
            </View>
            <View style={[styles.colNarrow, { width: 120 }]}>
              <Text style={styles.label}>Data Fim</Text>
              <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="produto-promocao-data-fim" />
            </View>
            <View style={[styles.colNarrow, { width: 120 }]}>
              <Text style={styles.label}>Hora Início</Text>
              <WebDateField value={horaInicio} onChange={(v) => setHoraInicio(v || null)} type="time" testID="produto-promocao-hora-inicio" />
            </View>
            <View style={[styles.colNarrow, { width: 120 }]}>
              <Text style={styles.label}>Hora Fim</Text>
              <WebDateField value={horaFim} onChange={(v) => setHoraFim(v || null)} type="time" testID="produto-promocao-hora-fim" />
            </View>
          </View>
          <View style={[styles.toolbarRow, { alignItems: "stretch" }]}>
            <Pressable onPress={limpar} style={[styles.secondaryBtn, styles.modalBtnEven]} testID="produto-promocao-novo">
              <Ionicons name="add-outline" size={16} color={colors.brandPrimary} />
              <Text style={styles.secondaryBtnText}>Novo</Text>
            </Pressable>
            <Pressable onPress={gravar} disabled={saving} style={[styles.saveBtnModal, styles.modalBtnEven, { marginTop: 0 }, saving && { opacity: 0.6 }]} testID="produto-promocao-gravar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

// Dias da Semana (Web Convidado) — botão ao lado do checkbox "Produto Web",
// só habilitado quando ele está marcado. Configura em quais dias da semana
// este produto aparece no cardápio do Web Convidado (módulo em fase de
// análise, ver WebConvidado.md — este cadastro específico foi liberado pro
// usuário implementar desde já, 2026-07-30). Tabela nova `Web_DiasSemana`
// (uma linha por produto+dia selecionado, replace-all-on-save — mesmo
// padrão de telefones/endereços/contatos deste projeto).
function DiasSemanaWebModal({ visible, onClose, conn, codigoInt, descricao }: {
  visible: boolean; onClose: () => void; conn: { servidor: string; banco: string; api: string };
  codigoInt: string; descricao: string;
}) {
  const fb = useFeedback();
  const [dias, setDias] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const base = conn.api.replace(/\/+$/, "");

  const carregar = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/dias-semana-web?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`);
      const j = await r.json();
      if (j?.success) setDias((j.dias || []).map((d: number) => String(d)));
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (visible) carregar(); }, [visible]);

  const toggleDia = (d: string) => {
    setDias((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  const gravar = async () => {
    setSaving(true);
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(codigoInt)}/dias-semana-web`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, dias: dias.map(Number) }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Gravado.");
        onClose();
      } else {
        fb.showError(friendlyApiError(j, "Falha ao gravar."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Dias da Semana</Text>
            <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
          </View>
          <Text style={styles.sectionHint}>{codigoInt} — {descricao}</Text>
          <Text style={styles.sectionHint}>
            Marque em quais dias da semana este produto aparece no cardápio do Web Convidado. Nenhum dia marcado
            significa que o produto aparece todos os dias.
          </Text>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.md }} /> : (
            <View style={styles.chipsRow}>
              {DIAS_SEMANA_LABELS.map((diaLabel, i) => {
                const d = String(i);
                const sel = dias.includes(d);
                return (
                  <Pressable key={d} onPress={() => toggleDia(d)} style={[styles.chip, sel && styles.chipSel]} testID={`produto-dias-semana-web-dia-${d}`}>
                    <Text style={[styles.chipText, sel && { color: colors.onBrandPrimary }]}>{diaLabel}</Text>
                  </Pressable>
                );
              })}
            </View>
          )}
          <Pressable onPress={gravar} disabled={saving} style={[styles.saveBtnModal, saving && { opacity: 0.6 }]} testID="produto-dias-semana-web-gravar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center",
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  tabBar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.lg },
  tabBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabLabel: { fontSize: 13, fontWeight: "500", color: colors.muted },
  tabLabelSel: { color: colors.onBrandPrimary },
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: spacing.xs },
  sectionTitleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.xs },
  sectionHint: { fontSize: 11, color: colors.muted, marginTop: spacing.md, fontStyle: "italic" },
  groupColumns: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.md, alignItems: "flex-start" },
  groupColumn: { flexGrow: 1, flexBasis: 280, minWidth: 260, gap: spacing.md },
  groupBox: {
    width: "100%",
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    padding: spacing.md, backgroundColor: colors.surfaceSecondary,
  },
  groupTitle: { fontSize: 11, fontWeight: "700", color: colors.brandPrimary, textTransform: "uppercase", letterSpacing: 0.4, marginBottom: spacing.xs },
  groupTitleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  groupFieldsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  colHalf: { flexGrow: 1, flexBasis: "45%", minWidth: 100 },
  nivelBox: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 12, marginTop: spacing.sm,
  },
  nivelValue: { fontSize: 13, color: colors.onSurface, fontWeight: "500", flex: 1 },
  nivelPlaceholder: { fontSize: 13, color: colors.muted, flex: 1 },
  inlineSearchRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceTertiary, color: colors.muted },
  readonlyValue: { fontSize: 14, color: colors.onSurface, paddingVertical: 11 },
  statInlineRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingVertical: 11 },
  statLabel: { fontSize: 12, color: colors.muted, fontWeight: "700" },
  statValue: { fontSize: 14, color: colors.onSurface, fontWeight: "700" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 140 },
  switchRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md },
  switchRowInline: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  switchLabel: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  checkRowGroup: { flexDirection: "row", gap: spacing.lg, marginTop: spacing.md, flexWrap: "wrap" },
  toolbarRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, flexWrap: "wrap" },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.surface,
  },
  dangerBtn: { borderColor: colors.error },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "500", fontSize: 13 },
  gridRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  gridRowText: { fontSize: 13, color: colors.onSurface, flex: 1 },
  rowSubHint: { fontSize: 11, color: colors.brandPrimary, marginTop: 2 },
  empty: { fontSize: 12, color: colors.muted, textAlign: "center", paddingVertical: spacing.md },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: spacing.xs },
  chip: { paddingHorizontal: spacing.sm, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, color: colors.onSurface, fontWeight: "500" },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modalBgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  modalCard: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
  },
  modalCardWebCompact: {
    width: "100%", maxWidth: 560, alignSelf: "center",
    borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
  },
  // Anexos/Fotografia embutem GestorDocumentosSection (lista + preview lado
  // a lado) — precisa de mais largura que o tier de "seleção" padrão (560px)
  // pra não cramped o painel de preview, ver CLAUDE.md > "Padrões de UI".
  modalCardWebWide: {
    width: "100%", maxWidth: 960, alignSelf: "center",
    borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
  },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  saveBtnModal: {
    marginTop: spacing.md, backgroundColor: colors.brandPrimary, borderRadius: radius.md,
    paddingVertical: 12, alignItems: "center",
  },
  // Botões lado a lado no rodapé de um modal (ex.: "Novo" + "Gravar") —
  // mesma altura/proporção pros dois, nenhum esticado sozinho nem menor
  // que o outro. Ver CLAUDE.md > "Padrões de UI" (botões agrupados).
  modalBtnEven: { flex: 1, justifyContent: "center", paddingVertical: 12 },
});

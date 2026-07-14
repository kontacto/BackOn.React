import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import DateField from "@/src/components/DateField";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_FORNECEDOR } from "@/src/components/GestorDocumentosSection";
import { detectDocType, maskCgcCpf, onlyAlnumUpper, validCNPJ, validCPF } from "@/src/hooks/useClienteForm";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = Connection;

type FornecedorItem = { codigo_int: number; codigo: string; nome: string; fantasia: string; situacao: string };

type Telefone = { ddd: string; tel: string; descricao: string };
type Endereco = {
  endereco: string; numero: string; complemento: string; bairro: string; cidade: string;
  uf: string; cep: string; pais: string; tipo: number;
};
type Contato = {
  contato: string; setor: string; cargo: string; ddd: string; telefone: string;
  ddd_fax: string; fax: string; ddd_celular: string; celular: string; e_mail: string; sexo: string;
};

const TELEFONE_VAZIO: Telefone = { ddd: "", tel: "", descricao: "" };
const ENDERECO_VAZIO: Endereco = {
  endereco: "", numero: "", complemento: "", bairro: "", cidade: "", uf: "", cep: "", pais: "BRASIL", tipo: 0,
};
const CONTATO_VAZIO: Contato = {
  contato: "", setor: "", cargo: "", ddd: "", telefone: "", ddd_fax: "", fax: "", ddd_celular: "", celular: "", e_mail: "", sexo: "",
};

const num = (s: string): number => (s.trim() ? parseFloat(s.replace(",", ".")) || 0 : 0);
const int_ = (s: string): number => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || 0 : 0);
const isCompactWeb = Platform.OS === "web";

// Cadastro > Fornecedores (tabela `fornecedor`). Legado: FrmmanForn.frm
// ("Manutenção de Fornecedores"). Ao contrário de Cliente/Serviços, esta
// tela é intencionalmente COMPACTA e sem abas — o legado já apresenta tudo
// (Identificação, Telefones, Endereços, Dados Complementares) numa única
// tela sem navegação, pedido explícito do usuário ("Perceba como a tela de
// cadastro é compacta"). Ver memória de projeto "Fornecedores — Manutenção"
// para o mapeamento completo de campos e o que ficou fora de escopo.
export default function FornecedoresScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Fornecedores está disponível apenas no web."
        testID="fornecedores-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<FornecedorItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const [situacaoOptions, setSituacaoOptions] = useState<SelectOption[]>([]);
  const [atividadeOptions, setAtividadeOptions] = useState<SelectOption[]>([]);
  const [contasOptions, setContasOptions] = useState<SelectOption[]>([]);
  const [classesOptions, setClassesOptions] = useState<SelectOption[]>([]);
  const [subClassesOptions, setSubClassesOptions] = useState<SelectOption[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editingCodigoInt, setEditingCodigoInt] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const [codigo, setCodigo] = useState("");
  const [codigoTouched, setCodigoTouched] = useState(false);
  const [nome, setNome] = useState("");
  const [fantasia, setFantasia] = useState("");
  const [inscrEst, setInscrEst] = useState("");
  const [dataCadastro, setDataCadastro] = useState<string | null>(null);
  const [credIcms, setCredIcms] = useState(true); // tipo: S/N
  const [situacao, setSituacao] = useState<string | null>("A");

  const [obsForn, setObsForn] = useState("");
  const [atividade, setAtividade] = useState<number | null>(null);
  const [distribuidorTexto, setDistribuidorTexto] = useState("");
  const [shipperTexto, setShipperTexto] = useState("");
  const [email, setEmail] = useState("");
  const [prazoPgto, setPrazoPgto] = useState("");
  const [desconto, setDesconto] = useState("");
  const [nossaConta, setNossaConta] = useState("");
  const [dadosBancarios, setDadosBancarios] = useState("");

  const [contaTransfCaixa, setContaTransfCaixa] = useState<number | null>(null);
  const [classeCaixa, setClasseCaixa] = useState<number | null>(null);
  const [subClasseCaixa, setSubClasseCaixa] = useState<number | null>(null);

  const [telefones, setTelefones] = useState<Telefone[]>([]);
  const [telefoneDraft, setTelefoneDraft] = useState<Telefone>(TELEFONE_VAZIO);
  const [telefoneEditIdx, setTelefoneEditIdx] = useState<number | null>(null);

  const [enderecos, setEnderecos] = useState<Endereco[]>([]);
  const [enderecoDraft, setEnderecoDraft] = useState<Endereco>(ENDERECO_VAZIO);
  const [enderecoEditIdx, setEnderecoEditIdx] = useState<number | null>(null);
  const [cepLoading, setCepLoading] = useState(false);

  const [contatos, setContatos] = useState<Contato[]>([]);
  const [contatoDraft, setContatoDraft] = useState<Contato>(CONTATO_VAZIO);
  const [contatoEditIdx, setContatoEditIdx] = useState<number | null>(null);

  const [caixaModalOpen, setCaixaModalOpen] = useState(false);
  const [contatosModalOpen, setContatosModalOpen] = useState(false);
  const [gravandoComoCliente, setGravandoComoCliente] = useState(false);

  const docType = detectDocType(codigo);
  const labelInscre = docType === "CPF" ? "Identidade" : "Insc. Estadual";
  const enderecoTipos = docType === "CPF"
    ? [{ value: 0, label: "Residencial" }, { value: 1, label: "Comercial" }, { value: 2, label: "Entrega" }]
    : [{ value: 0, label: "Comercial" }, { value: 1, label: "Cobrança" }, { value: 2, label: "Entrega" }];

  // Crivo de documento válido (CPF 11 dígitos / CNPJ 14, alfanumérico
  // 2026) — regra global do usuário: todo campo de CPF/CNPJ do projeto
  // passa por essa validação, mesmo algoritmo já usado em Cliente
  // (useClienteForm.ts).
  const codigoError = (() => {
    if (!codigoTouched) return null;
    const raw = onlyAlnumUpper(codigo);
    if (!raw) return null;
    if (raw.length === 11) return validCPF(raw) ? null : "CPF inválido.";
    if (raw.length === 14) return validCNPJ(raw) ? null : "CNPJ inválido.";
    return "CPF/CGC deve ter 11 (CPF) ou 14 (CNPJ) caracteres.";
  })();

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(search)}`;
      const r = await fetch(`${base}/api/fornecedores?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, [search]);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [rSit, rAtiv, rContas, rClasses, rSubClasses] = await Promise.all([
        fetch(`${base}/api/tabelas/situacao?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/tipo-cliente?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/contas?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/classes?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/sub-classes?${qs}`).then((r) => r.json()).catch(() => null),
      ]);
      if (rSit?.success) setSituacaoOptions(rSit.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rAtiv?.success) setAtividadeOptions(rAtiv.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rContas?.success) setContasOptions(rContas.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rClasses?.success) setClassesOptions(rClasses.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rSubClasses?.success) setSubClassesOptions(rSubClasses.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
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
      setConn(c);
      load(c);
      loadLookups(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (conn) load(conn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const resetForm = () => {
    setCodigo(""); setCodigoTouched(false); setNome(""); setFantasia(""); setInscrEst(""); setDataCadastro(null);
    setCredIcms(true); setSituacao("A");
    setObsForn(""); setAtividade(null); setDistribuidorTexto(""); setShipperTexto("");
    setEmail(""); setPrazoPgto(""); setDesconto(""); setNossaConta(""); setDadosBancarios("");
    setContaTransfCaixa(null); setClasseCaixa(null); setSubClasseCaixa(null);
    setTelefones([]); setTelefoneDraft(TELEFONE_VAZIO); setTelefoneEditIdx(null);
    setEnderecos([]); setEnderecoDraft(ENDERECO_VAZIO); setEnderecoEditIdx(null);
    setContatos([]); setContatoDraft(CONTATO_VAZIO); setContatoEditIdx(null);
  };

  const openNew = () => {
    setEditingCodigoInt(null);
    resetForm();
    setFormOpen(true);
  };

  const openEdit = async (item: FornecedorItem) => {
    if (!conn) return;
    setEditingCodigoInt(item.codigo_int);
    setFormOpen(true);
    setCodigoTouched(false);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/fornecedores/${item.codigo_int}?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      const d = j.item;
      setCodigo(maskCgcCpf(d.codigo || "")); setNome(d.nome || ""); setFantasia(d.fantasia || ""); setInscrEst(d.inscr_est || "");
      setDataCadastro(d.data); setCredIcms((d.tipo || "S").toUpperCase() !== "N"); setSituacao(d.situacao || "A");
      setObsForn(d.obs_forn || ""); setAtividade(d.cliente_forn ?? null);
      setEmail(d.e_mail || ""); setPrazoPgto(String(d.prazo_pgto ?? "")); setDesconto(String(d.desconto ?? ""));
      setNossaConta(d.nossa_conta || ""); setDadosBancarios(d.dados_bancarios || "");
      setContaTransfCaixa(d.conta_transf_caixa ?? null); setClasseCaixa(d.classe_caixa ?? null); setSubClasseCaixa(d.sub_classe_caixa ?? null);
      setDistribuidorTexto(""); setShipperTexto(""); // resolvidos só na gravação — exibição do vínculo atual fica pra uma próxima iteração
      setTelefones((d.telefones || []).map((t: any) => ({ ddd: t.ddd || "", tel: t.tel || "", descricao: t.descricao || "" })));
      setEnderecos((d.enderecos || []).map((e: any) => ({
        endereco: e.endereco || "", numero: String(e.numero ?? ""), complemento: e.complemento || "", bairro: e.bairro || "",
        cidade: e.cidade || "", uf: e.uf || "", cep: e.cep || "", pais: e.pais || "BRASIL", tipo: e.tipo ?? 0,
      })));
      setContatos((d.contatos || []).map((c: any) => ({
        contato: c.contato || "", setor: c.setor || "", cargo: c.cargo || "", ddd: String(c.ddd || ""), telefone: c.telefone || "",
        ddd_fax: String(c.ddd_fax || ""), fax: c.fax || "", ddd_celular: String(c.ddd_celular || ""), celular: c.celular || "",
        e_mail: c.e_mail || "", sexo: c.sexo || "",
      })));
      setTelefoneDraft(TELEFONE_VAZIO); setTelefoneEditIdx(null);
      setEnderecoDraft(ENDERECO_VAZIO); setEnderecoEditIdx(null);
      setContatoDraft(CONTATO_VAZIO); setContatoEditIdx(null);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      setFormOpen(false);
    }
  };

  // Autoload no blur do CPF/CNPJ: se o documento é válido e ainda estamos
  // criando um fornecedor novo (não editando), busca se já existe um
  // fornecedor com esse código e carrega pra edição — mesmo padrão já
  // usado em Cliente (`useClienteForm.buscarPorCgc`), regra global do
  // usuário (2026-07-10).
  const buscarPorCodigo = useCallback(async () => {
    setCodigoTouched(true);
    if (editingCodigoInt !== null) return;
    const raw = onlyAlnumUpper(codigo);
    if (!raw) return;
    const isValid = (raw.length === 11 && validCPF(raw)) || (raw.length === 14 && validCNPJ(raw));
    if (!isValid || !conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `codigo=${encodeURIComponent(raw)}&servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/fornecedores/find/by-codigo?${qs}`);
      const j = await r.json();
      if (j?.success && j?.found && j?.codigo_int) {
        fb.showWarning(`Fornecedor já cadastrado: ${j.nome || `#${j.codigo_int}`}. Carregando...`);
        openEdit({ codigo_int: j.codigo_int, codigo: raw, nome: j.nome || "", fantasia: "", situacao: "" });
      }
    } catch {
      // silencioso — busca é opcional
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codigo, conn, editingCodigoInt]);

  // ---- Telefones ----
  const incluirTelefone = () => {
    if (!telefoneDraft.tel.trim()) { fb.showWarning("Informe o telefone."); return; }
    setTelefones((prev) => [...prev, telefoneDraft]);
    setTelefoneDraft(TELEFONE_VAZIO);
  };
  const selecionarTelefone = (idx: number) => { setTelefoneEditIdx(idx); setTelefoneDraft(telefones[idx]); };
  const alterarTelefone = () => {
    if (telefoneEditIdx === null) return;
    setTelefones((prev) => prev.map((t, i) => (i === telefoneEditIdx ? telefoneDraft : t)));
    setTelefoneEditIdx(null); setTelefoneDraft(TELEFONE_VAZIO);
  };
  const excluirTelefone = () => {
    if (telefoneEditIdx === null) return;
    setTelefones((prev) => prev.filter((_, i) => i !== telefoneEditIdx));
    setTelefoneEditIdx(null); setTelefoneDraft(TELEFONE_VAZIO);
  };
  const limparTelefoneForm = () => { setTelefoneEditIdx(null); setTelefoneDraft(TELEFONE_VAZIO); };

  // ---- Endereços ----
  const buscarCEP = async (cepRaw: string) => {
    const cep = cepRaw.replace(/\D/g, "");
    if (cep.length !== 8 || !conn) return;
    setCepLoading(true);
    try {
      const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      const j = await r.json();
      if (!j?.erro) {
        setEnderecoDraft((prev) => ({
          ...prev, endereco: j.logradouro || prev.endereco, bairro: j.bairro || prev.bairro,
          cidade: j.localidade || prev.cidade, uf: j.uf || prev.uf,
        }));
      } else {
        fb.showWarning("CEP não encontrado.");
      }
    } catch (e) {
      fb.showError(`Falha ViaCEP: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setCepLoading(false); }
  };
  const incluirEndereco = () => {
    if (!enderecoDraft.endereco.trim()) { fb.showWarning("Informe o Endereço."); return; }
    if ((enderecoDraft.tipo === 0 || enderecoDraft.tipo === 1) && enderecos.some((e, i) => e.tipo === enderecoDraft.tipo && i !== enderecoEditIdx)) {
      fb.showWarning("Só é permitido um endereço desse tipo por fornecedor.");
      return;
    }
    setEnderecos((prev) => [...prev, enderecoDraft]);
    setEnderecoDraft({ ...ENDERECO_VAZIO, pais: "BRASIL" });
  };
  const selecionarEndereco = (idx: number) => { setEnderecoEditIdx(idx); setEnderecoDraft(enderecos[idx]); };
  const alterarEndereco = () => {
    if (enderecoEditIdx === null) return;
    if ((enderecoDraft.tipo === 0 || enderecoDraft.tipo === 1) && enderecos.some((e, i) => e.tipo === enderecoDraft.tipo && i !== enderecoEditIdx)) {
      fb.showWarning("Só é permitido um endereço desse tipo por fornecedor.");
      return;
    }
    setEnderecos((prev) => prev.map((e, i) => (i === enderecoEditIdx ? enderecoDraft : e)));
    setEnderecoEditIdx(null); setEnderecoDraft({ ...ENDERECO_VAZIO, pais: "BRASIL" });
  };
  const excluirEndereco = () => {
    if (enderecoEditIdx === null) return;
    setEnderecos((prev) => prev.filter((_, i) => i !== enderecoEditIdx));
    setEnderecoEditIdx(null); setEnderecoDraft({ ...ENDERECO_VAZIO, pais: "BRASIL" });
  };

  // ---- Contatos ----
  const incluirContato = () => {
    if (!contatoDraft.contato.trim()) { fb.showWarning("Informe o Contato."); return; }
    setContatos((prev) => [...prev, contatoDraft]);
    setContatoDraft(CONTATO_VAZIO);
  };
  const selecionarContato = (idx: number) => { setContatoEditIdx(idx); setContatoDraft(contatos[idx]); };
  const alterarContato = () => {
    if (contatoEditIdx === null) return;
    setContatos((prev) => prev.map((c, i) => (i === contatoEditIdx ? contatoDraft : c)));
    setContatoEditIdx(null); setContatoDraft(CONTATO_VAZIO);
  };
  const excluirContato = () => {
    if (contatoEditIdx === null) return;
    setContatos((prev) => prev.filter((_, i) => i !== contatoEditIdx));
    setContatoEditIdx(null); setContatoDraft(CONTATO_VAZIO);
  };
  const limparContatoForm = () => { setContatoEditIdx(null); setContatoDraft(CONTATO_VAZIO); };

  const save = async () => {
    if (!conn) return;
    if (!codigo.trim()) { fb.showWarning("Defina o CPF/CGC!"); return; }
    setCodigoTouched(true);
    const rawCodigo = onlyAlnumUpper(codigo);
    const codigoValido = (rawCodigo.length === 11 && validCPF(rawCodigo)) || (rawCodigo.length === 14 && validCNPJ(rawCodigo));
    if (!codigoValido) { fb.showWarning("CPF/CGC inválido — confira o documento antes de gravar."); return; }
    if (!nome.trim()) { fb.showWarning("Defina o Nome/Razão Social!"); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/fornecedores`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo_int: editingCodigoInt,
          dados: {
            codigo: onlyAlnumUpper(codigo), nome: nome.trim(), fantasia: fantasia.trim(), inscr_est: inscrEst.trim(),
            data: dataCadastro, tipo: credIcms ? "S" : "N", situacao: (situacao || "A").toUpperCase(),
            obs_forn: obsForn, cliente_forn: atividade,
            distribuidor_texto: distribuidorTexto.trim(), shipper_texto: shipperTexto.trim(),
            e_mail: email.trim(), prazo_pgto: int_(prazoPgto), desconto: num(desconto), nossa_conta: nossaConta.trim(),
            dados_bancarios: dadosBancarios,
            conta_transf_caixa: contaTransfCaixa, classe_caixa: classeCaixa, sub_classe_caixa: subClasseCaixa,
            telefones: telefones.map((t) => ({ ddd: t.ddd.trim(), tel: t.tel.trim(), descricao: t.descricao.trim() })),
            enderecos: enderecos.map((e) => ({
              endereco: e.endereco.trim(), numero: int_(e.numero), complemento: e.complemento.trim(), bairro: e.bairro.trim(),
              cidade: e.cidade.trim(), uf: e.uf.trim(), cep: e.cep.replace(/\D/g, ""), pais: e.pais.trim(), tipo: e.tipo,
            })),
            contatos: contatos.map((c) => ({
              contato: c.contato.trim(), setor: c.setor.trim(), cargo: c.cargo.trim(), ddd: int_(c.ddd), telefone: c.telefone.trim(),
              ddd_fax: int_(c.ddd_fax), fax: c.fax.trim(), ddd_celular: int_(c.ddd_celular), celular: c.celular.trim(),
              e_mail: c.e_mail.trim(), sexo: c.sexo || "M",
            })),
          },
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Fornecedor gravado.");
        setEditingCodigoInt(j.codigo_int);
        load(conn);
      } else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = (item: FornecedorItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão do fornecedor "${item.nome}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/fornecedores/${item.codigo_int}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  // "Gravar Como Cliente" — legado FrmmanForn.CmdCopComo_Click: clona o
  // fornecedor já salvo pra um registro de Cliente (upsert por CPF/CGC).
  const gravarComoCliente = async () => {
    if (!conn || !editingCodigoInt) return;
    Alert.alert("Gravar Como Cliente", "Confirma gravar este fornecedor também como cliente?", [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Confirmar",
        onPress: async () => {
          setGravandoComoCliente(true);
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/fornecedores/${editingCodigoInt}/gravar-como-cliente`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) fb.showSuccess(j.message || "Gravado como cliente.");
            else fb.showError(j?.message || "Falha ao gravar como cliente.");
          } catch (e) {
            fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
          } finally {
            setGravandoComoCliente(false);
          }
        },
      },
    ]);
  };

  const canSave = can("FORNECEDOR.GRAVAR") || isMaster;
  const canDel = can("FORNECEDOR.EXCLUIR") || isMaster;

  // ============================================================
  // Formulário (tela cheia, compacta — sem abas)
  // ============================================================
  if (formOpen) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="fornecedores-form-screen">
        <View style={styles.header}>
          <Pressable onPress={() => setFormOpen(false)} style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]} hitSlop={12} testID="fornecedores-form-back-button">
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
          <Text style={styles.headerTitle} numberOfLines={1}>{editingCodigoInt ? `Fornecedor #${editingCodigoInt}` : "Novo Fornecedor"}</Text>
          {canSave ? (
            <Pressable onPress={save} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]} hitSlop={8} testID="fornecedores-salvar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                <>
                  <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.saveLabel}>Gravar</Text>
                </>
              )}
            </Pressable>
          ) : <View style={{ width: 40 }} />}
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            {/* ---- Identificação ---- */}
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>CPF / CGC *</Text>
                  <TextInput
                    value={codigo}
                    onChangeText={(v) => { setCodigo(maskCgcCpf(v)); setCodigoTouched(false); }}
                    onBlur={buscarPorCodigo}
                    style={[styles.input, codigoError && styles.inputError]}
                    autoCapitalize="characters"
                    maxLength={18}
                    testID="fornecedores-codigo"
                  />
                  {codigoError ? <Text style={styles.errorText} testID="fornecedores-codigo-error">{codigoError}</Text> : null}
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Nome / Razão Social *</Text>
                  <TextInput value={nome} onChangeText={setNome} style={styles.input} maxLength={60} testID="fornecedores-nome" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Situação</Text>
                  <SelectField value={situacao} onChange={(v) => setSituacao(v as string)} options={situacaoOptions} testID="fornecedores-situacao" modalTitle="Situação" compactWeb />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Nome Fantasia</Text>
                  <TextInput value={fantasia} onChangeText={setFantasia} style={[styles.input, docType === "CPF" && styles.inputDisabled]} editable={docType !== "CPF"} maxLength={30} testID="fornecedores-fantasia" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>{labelInscre}</Text>
                  <TextInput value={inscrEst} onChangeText={setInscrEst} style={styles.input} maxLength={18} testID="fornecedores-inscr-est" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data Cadastro</Text>
                  <DateField value={dataCadastro} onChange={setDataCadastro} testID="fornecedores-data" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Cred. ICMS</Text>
                  <View style={styles.switchInline}>
                    <Switch value={credIcms} onValueChange={setCredIcms} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="fornecedores-cred-icms" />
                  </View>
                </View>
              </View>
            </View>

            {/* ---- Telefones / Endereços — dependem do fornecedor já ter
                 sido gravado (regra global do usuário: cadastros
                 relacionados à entidade principal não podem ser criados
                 antes dela existir). ---- */}
            {!editingCodigoInt ? (
              <View style={styles.card}>
                <View style={styles.lockedRow}>
                  <Ionicons name="lock-closed-outline" size={18} color={colors.muted} />
                  <Text style={styles.lockedText}>
                    Grave os dados de Identificação primeiro para cadastrar telefones, endereços e as demais informações do fornecedor.
                  </Text>
                </View>
              </View>
            ) : (
              <>
            {/* ---- Telefones ---- */}
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Telefones</Text></View>
            <View style={styles.card}>
              {telefones.length === 0 ? <Text style={styles.hint}>Nenhum telefone cadastrado.</Text> : telefones.map((t, idx) => (
                <Pressable key={idx} onPress={() => selecionarTelefone(idx)} style={[styles.gridRow, telefoneEditIdx === idx && styles.gridRowSel]} testID={`fornecedores-telefone-${idx}`}>
                  <Text style={styles.gridRowText}>({t.ddd || "--"}) {t.tel}{t.descricao ? ` — ${t.descricao}` : ""}</Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>
              ))}
              <View style={styles.divider} />
              <View style={styles.rowFields}>
                <View style={{ width: 70 }}>
                  <Text style={styles.label}>DDD</Text>
                  <TextInput value={telefoneDraft.ddd} onChangeText={(v) => setTelefoneDraft((p) => ({ ...p, ddd: v.replace(/\D/g, "").slice(0, 4) }))} style={styles.input} keyboardType="number-pad" testID="fornecedores-tel-ddd" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Telefone</Text>
                  <TextInput value={telefoneDraft.tel} onChangeText={(v) => setTelefoneDraft((p) => ({ ...p, tel: v.replace(/\D/g, "").slice(0, 10) }))} style={styles.input} keyboardType="phone-pad" testID="fornecedores-tel-numero" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Descrição</Text>
                  <TextInput value={telefoneDraft.descricao} onChangeText={(v) => setTelefoneDraft((p) => ({ ...p, descricao: v }))} style={styles.input} testID="fornecedores-tel-descricao" />
                </View>
              </View>
              <View style={styles.crudBtnRow}>
                {telefoneEditIdx === null ? (
                  <Pressable onPress={incluirTelefone} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="fornecedores-tel-incluir"><Text style={styles.crudBtnPrimaryText}>Incluir</Text></Pressable>
                ) : (
                  <>
                    <Pressable onPress={alterarTelefone} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="fornecedores-tel-alterar"><Text style={styles.crudBtnPrimaryText}>Alterar</Text></Pressable>
                    <Pressable onPress={excluirTelefone} style={[styles.crudBtn, styles.crudBtnDanger]} testID="fornecedores-tel-excluir"><Text style={styles.crudBtnDangerText}>Excluir</Text></Pressable>
                    <Pressable onPress={limparTelefoneForm} style={styles.crudBtn} testID="fornecedores-tel-limpar"><Text style={styles.crudBtnText}>Limpar</Text></Pressable>
                  </>
                )}
              </View>
            </View>

            {/* ---- Endereços ---- */}
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Endereços</Text></View>
            <View style={styles.card}>
              {enderecos.length === 0 ? <Text style={styles.hint}>Nenhum endereço cadastrado.</Text> : enderecos.map((e, idx) => (
                <Pressable key={idx} onPress={() => selecionarEndereco(idx)} style={[styles.gridRow, enderecoEditIdx === idx && styles.gridRowSel]} testID={`fornecedores-endereco-${idx}`}>
                  <Text style={styles.gridRowText} numberOfLines={1}>
                    [{enderecoTipos.find((t) => t.value === e.tipo)?.label}] {e.endereco}{e.numero ? `, ${e.numero}` : ""}{e.bairro ? ` - ${e.bairro}` : ""}{e.cidade ? ` - ${e.cidade}` : ""}{e.uf ? `/${e.uf}` : ""}
                  </Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>
              ))}
              <View style={styles.divider} />
              <View style={styles.radioRow}>
                {enderecoTipos.map((opt) => (
                  <Pressable key={opt.value} onPress={() => setEnderecoDraft((p) => ({ ...p, tipo: opt.value }))} style={[styles.radioBtn, enderecoDraft.tipo === opt.value && styles.radioBtnSel]} testID={`fornecedores-end-tipo-${opt.value}`}>
                    <View style={[styles.radioCircle, enderecoDraft.tipo === opt.value && styles.radioCircleSel]}>{enderecoDraft.tipo === opt.value ? <View style={styles.radioDot} /> : null}</View>
                    <Text style={[styles.radioLabel, enderecoDraft.tipo === opt.value && { color: colors.brandPrimary }]}>{opt.label}</Text>
                  </Pressable>
                ))}
              </View>
              <View style={styles.rowFields}>
                <View style={{ width: 190 }}>
                  <Text style={styles.label}>CEP</Text>
                  <View style={styles.inputWithBtn}>
                    <TextInput
                      value={enderecoDraft.cep}
                      onChangeText={(v) => setEnderecoDraft((p) => ({ ...p, cep: v.replace(/\D/g, "").slice(0, 8) }))}
                      onBlur={() => buscarCEP(enderecoDraft.cep)}
                      style={[styles.input, { flex: 1, minWidth: 0 }]}
                      keyboardType="number-pad"
                      testID="fornecedores-end-cep"
                    />
                    {cepLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginLeft: 8 }} /> : (
                      <Pressable onPress={() => buscarCEP(enderecoDraft.cep)} style={styles.cepBtn} testID="fornecedores-end-buscar-cep"><Ionicons name="search" size={16} color={colors.onBrandPrimary} /></Pressable>
                    )}
                  </View>
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Endereço</Text>
                  <TextInput value={enderecoDraft.endereco} onChangeText={(v) => setEnderecoDraft((p) => ({ ...p, endereco: v }))} style={styles.input} maxLength={64} testID="fornecedores-end-logradouro" />
                </View>
                <View style={{ width: 100 }}>
                  <Text style={styles.label}>Número</Text>
                  <TextInput value={enderecoDraft.numero} onChangeText={(v) => setEnderecoDraft((p) => ({ ...p, numero: v.replace(/\D/g, "") }))} style={styles.input} keyboardType="number-pad" testID="fornecedores-end-numero" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Complemento</Text>
                  <TextInput value={enderecoDraft.complemento} onChangeText={(v) => setEnderecoDraft((p) => ({ ...p, complemento: v }))} style={styles.input} testID="fornecedores-end-complemento" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Bairro</Text>
                  <TextInput value={enderecoDraft.bairro} onChangeText={(v) => setEnderecoDraft((p) => ({ ...p, bairro: v }))} style={styles.input} maxLength={35} testID="fornecedores-end-bairro" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Cidade</Text>
                  <TextInput value={enderecoDraft.cidade} onChangeText={(v) => setEnderecoDraft((p) => ({ ...p, cidade: v }))} style={styles.input} maxLength={35} testID="fornecedores-end-cidade" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>UF</Text>
                  <TextInput value={enderecoDraft.uf} onChangeText={(v) => setEnderecoDraft((p) => ({ ...p, uf: v.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2) }))} style={styles.input} autoCapitalize="characters" maxLength={2} testID="fornecedores-end-uf" />
                </View>
              </View>
              <View style={styles.crudBtnRow}>
                {enderecoEditIdx === null ? (
                  <Pressable onPress={incluirEndereco} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="fornecedores-end-incluir"><Text style={styles.crudBtnPrimaryText}>Adicionar</Text></Pressable>
                ) : (
                  <>
                    <Pressable onPress={alterarEndereco} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="fornecedores-end-alterar"><Text style={styles.crudBtnPrimaryText}>Alterar</Text></Pressable>
                    <Pressable onPress={excluirEndereco} style={[styles.crudBtn, styles.crudBtnDanger]} testID="fornecedores-end-excluir"><Text style={styles.crudBtnDangerText}>Excluir</Text></Pressable>
                  </>
                )}
              </View>
            </View>
              </>
            )}

            {/* ---- Dados Complementares ---- */}
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Dados Complementares</Text></View>
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Distribuidor</Text>
                  <TextInput value={distribuidorTexto} onChangeText={setDistribuidorTexto} style={styles.input} placeholder="Nome/fantasia/código de outro fornecedor" placeholderTextColor={colors.muted} testID="fornecedores-distribuidor" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Transportador</Text>
                  <TextInput value={shipperTexto} onChangeText={setShipperTexto} style={styles.input} placeholder="Nome/fantasia/código de outro fornecedor" placeholderTextColor={colors.muted} testID="fornecedores-shipper" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Email</Text>
                  <TextInput value={email} onChangeText={setEmail} style={styles.input} keyboardType="email-address" autoCapitalize="none" testID="fornecedores-email" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Atividade</Text>
                  <SelectField value={atividade} onChange={(v) => setAtividade(v as number)} options={atividadeOptions} allowClear testID="fornecedores-atividade" modalTitle="Atividade" compactWeb />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Prazo</Text>
                  <TextInput value={prazoPgto} onChangeText={(v) => setPrazoPgto(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="fornecedores-prazo" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Desconto</Text>
                  <TextInput value={desconto} onChangeText={setDesconto} style={styles.input} keyboardType="decimal-pad" testID="fornecedores-desconto" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Nossa Conta</Text>
                  <TextInput value={nossaConta} onChangeText={setNossaConta} style={styles.input} maxLength={30} testID="fornecedores-nossa-conta" />
                </View>
              </View>
              <Text style={styles.label}>Contato</Text>
              <TextInput value={obsForn} onChangeText={setObsForn} style={[styles.input, { minHeight: 50 }]} multiline testID="fornecedores-contato-obs" />
              <Text style={styles.label}>Dados Bancários</Text>
              <TextInput value={dadosBancarios} onChangeText={setDadosBancarios} style={[styles.input, { minHeight: 50 }]} multiline testID="fornecedores-dados-bancarios" />
            </View>

            {/* ---- Ações secundárias: Caixa/Contabilidade e Contatos abrem em
                 slide próprio, fiel ao legado (Command24/Command15 do
                 FrmmanForn.frm abrem um Frame flutuante cada, não campos
                 inline na tela principal). Só disponíveis com o fornecedor
                 já gravado (mesma regra global de "não criar cadastro
                 relacionado antes da entidade principal existir"). ---- */}
            {editingCodigoInt ? (
              <View style={styles.card}>
                <View style={styles.rowFields}>
                  <Pressable onPress={() => setCaixaModalOpen(true)} style={styles.secondaryActionBtn} testID="fornecedores-abrir-caixa">
                    <Ionicons name="cash-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.secondaryActionText}>Caixa / Contabilidade</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                  <Pressable onPress={() => setContatosModalOpen(true)} style={styles.secondaryActionBtn} testID="fornecedores-abrir-contatos">
                    <Ionicons name="people-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.secondaryActionText}>Contatos{contatos.length ? ` (${contatos.length})` : ""}</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                  <Pressable onPress={gravarComoCliente} disabled={gravandoComoCliente} style={[styles.secondaryActionBtn, gravandoComoCliente && { opacity: 0.6 }]} testID="fornecedores-gravar-como-cliente">
                    {gravandoComoCliente ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Ionicons name="person-add-outline" size={18} color={colors.brandPrimary} />}
                    <Text style={styles.secondaryActionText}>Gravar Como Cliente</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}

            {/* ---- Anexos ---- */}
            {conn && editingCodigoInt ? (
              <>
                <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Documentos Anexados</Text></View>
                <View style={styles.card}>
                  <GestorDocumentosSection api={conn.api} servidor={conn.servidor} banco={conn.banco} codGrupo={GESTOR_DOC_GRUPO_FORNECEDOR} codigoEntidade={editingCodigoInt} />
                </View>
              </>
            ) : null}
          </View>
        </ScrollView>

        <AppModal visible={caixaModalOpen} transparent animationType="slide" onRequestClose={() => setCaixaModalOpen(false)}>
          <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setCaixaModalOpen(false)}>
            <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
              <View style={styles.slideHeader}>
                <Text style={styles.slideTitle}>Caixa / Contabilidade</Text>
                <Pressable onPress={() => setCaixaModalOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <Text style={styles.label}>Conta p/ Transf. Caixa</Text>
              <SelectField value={contaTransfCaixa} onChange={(v) => setContaTransfCaixa(v as number)} options={contasOptions} allowClear testID="fornecedores-conta-transf" modalTitle="Conta" compactWeb />
              <Text style={styles.label}>Classe Caixa</Text>
              <SelectField value={classeCaixa} onChange={(v) => setClasseCaixa(v as number)} options={classesOptions} allowClear testID="fornecedores-classe-caixa" modalTitle="Classe" compactWeb />
              <Text style={styles.label}>Sub-Classe Caixa</Text>
              <SelectField value={subClasseCaixa} onChange={(v) => setSubClasseCaixa(v as number)} options={subClassesOptions} allowClear testID="fornecedores-sub-classe-caixa" modalTitle="Sub-Classe" compactWeb />
              <Text style={styles.hint}>Conta de transferência contábil (plano de contas por ano-exercício) ainda não está disponível nesta versão da tela.</Text>
              <Pressable onPress={() => setCaixaModalOpen(false)} style={[styles.addBtn, { marginTop: spacing.lg }]} testID="fornecedores-caixa-ok">
                <Text style={styles.addBtnText}>OK</Text>
              </Pressable>
            </Pressable>
          </Pressable>
        </AppModal>

        <AppModal visible={contatosModalOpen} transparent animationType="slide" onRequestClose={() => setContatosModalOpen(false)}>
          <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setContatosModalOpen(false)}>
            <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
              <View style={styles.slideHeader}>
                <Text style={styles.slideTitle}>Contatos</Text>
                <Pressable onPress={() => setContatosModalOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <ScrollView style={{ maxHeight: 460 }} keyboardShouldPersistTaps="handled">
                {contatos.length === 0 ? <Text style={styles.hint}>Nenhum contato cadastrado.</Text> : contatos.map((c, idx) => (
                  <Pressable key={idx} onPress={() => selecionarContato(idx)} style={[styles.gridRow, contatoEditIdx === idx && styles.gridRowSel]} testID={`fornecedores-contato-${idx}`}>
                    <Text style={styles.gridRowText} numberOfLines={1}>{c.contato}{c.setor || c.cargo ? ` — ${[c.setor, c.cargo].filter(Boolean).join(" / ")}` : ""}{c.telefone || c.celular ? ` — ${c.telefone || c.celular}` : ""}</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                ))}
                <View style={styles.divider} />
                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Contato *</Text>
                    <TextInput value={contatoDraft.contato} onChangeText={(v) => setContatoDraft((p) => ({ ...p, contato: v }))} style={styles.input} maxLength={30} testID="fornecedores-contato-nome" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Setor</Text>
                    <TextInput value={contatoDraft.setor} onChangeText={(v) => setContatoDraft((p) => ({ ...p, setor: v }))} style={styles.input} maxLength={15} testID="fornecedores-contato-setor" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Cargo</Text>
                    <TextInput value={contatoDraft.cargo} onChangeText={(v) => setContatoDraft((p) => ({ ...p, cargo: v }))} style={styles.input} maxLength={15} testID="fornecedores-contato-cargo" />
                  </View>
                </View>
                <View style={styles.rowFields}>
                  <View style={{ width: 60 }}>
                    <Text style={styles.label}>DDD</Text>
                    <TextInput value={contatoDraft.ddd} onChangeText={(v) => setContatoDraft((p) => ({ ...p, ddd: v.replace(/\D/g, "").slice(0, 3) }))} style={styles.input} keyboardType="number-pad" testID="fornecedores-contato-ddd" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Telefone</Text>
                    <TextInput value={contatoDraft.telefone} onChangeText={(v) => setContatoDraft((p) => ({ ...p, telefone: v }))} style={styles.input} keyboardType="phone-pad" testID="fornecedores-contato-telefone" />
                  </View>
                  <View style={{ width: 130 }}>
                    <Text style={styles.label}>Sexo</Text>
                    <SelectField value={contatoDraft.sexo || null} onChange={(v) => setContatoDraft((p) => ({ ...p, sexo: v == null ? "" : String(v) }))} options={[{ value: "M", label: "Masculino" }, { value: "F", label: "Feminino" }]} placeholder="—" allowClear compactWeb testID="fornecedores-contato-sexo" modalTitle="Sexo" />
                  </View>
                </View>
                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Celular</Text>
                    <TextInput value={contatoDraft.celular} onChangeText={(v) => setContatoDraft((p) => ({ ...p, celular: v }))} style={styles.input} keyboardType="phone-pad" testID="fornecedores-contato-celular" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Email</Text>
                    <TextInput value={contatoDraft.e_mail} onChangeText={(v) => setContatoDraft((p) => ({ ...p, e_mail: v }))} style={styles.input} keyboardType="email-address" autoCapitalize="none" testID="fornecedores-contato-email" />
                  </View>
                </View>
                <View style={styles.crudBtnRow}>
                  {contatoEditIdx === null ? (
                    <Pressable onPress={incluirContato} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="fornecedores-contato-incluir"><Text style={styles.crudBtnPrimaryText}>Incluir</Text></Pressable>
                  ) : (
                    <>
                      <Pressable onPress={alterarContato} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="fornecedores-contato-alterar"><Text style={styles.crudBtnPrimaryText}>Alterar</Text></Pressable>
                      <Pressable onPress={excluirContato} style={[styles.crudBtn, styles.crudBtnDanger]} testID="fornecedores-contato-excluir"><Text style={styles.crudBtnDangerText}>Excluir</Text></Pressable>
                      <Pressable onPress={limparContatoForm} style={styles.crudBtn} testID="fornecedores-contato-limpar"><Text style={styles.crudBtnText}>Limpar</Text></Pressable>
                    </>
                  )}
                </View>
              </ScrollView>
            </Pressable>
          </Pressable>
        </AppModal>
      </SafeAreaView>
    );
  }

  // ============================================================
  // Lista
  // ============================================================
  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="fornecedores-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Fornecedores</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.listShell}>
        <View style={styles.filterBox}>
          <TextInput value={search} onChangeText={setSearch} placeholder="Buscar por nome, fantasia ou CPF/CNPJ…" placeholderTextColor={colors.muted} style={styles.input} testID="fornecedores-search" />
        </View>

        <ScrollView contentContainerStyle={[styles.listScroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum fornecedor cadastrado.</Text> : null}
          {items.map((f) => (
            <View key={f.codigo_int} style={styles.row} testID={`fornecedores-${f.codigo_int}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(f)}>
                <Text style={styles.rowTitle}>{f.nome || "—"}</Text>
                <Text style={styles.rowSub}>{f.fantasia ? `${f.fantasia} · ` : ""}{f.codigo}{f.situacao && f.situacao !== "A" ? ` · ${f.situacao}` : ""}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(f)} hitSlop={8} testID={`fornecedores-del-${f.codigo_int}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="fornecedores-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  listShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  listScroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: { flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8, marginBottom: 8, fontSize: 12 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },

  scroll: { paddingBottom: spacing.xxxl },
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm, width: "100%", maxWidth: 1120, alignSelf: "center" },
  sectionTitle: { fontSize: 14, fontWeight: "500", color: colors.onSurface, textTransform: "uppercase", letterSpacing: 0.5 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, opacity: 0.65 },
  inputError: { borderColor: colors.error },
  errorText: { fontSize: 11, color: colors.error, marginTop: 4 },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 160 },
  colTiny: { width: 90 },
  switchInline: { paddingVertical: 11, alignItems: "flex-start" },
  hint: { fontSize: 12, color: colors.muted, marginTop: spacing.sm, fontStyle: "italic" },
  lockedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  lockedText: { flex: 1, fontSize: 13, color: colors.muted, fontStyle: "italic" },
  divider: { borderTopWidth: 1, borderTopColor: colors.border, marginTop: spacing.sm, marginBottom: spacing.md },
  gridRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 10, paddingHorizontal: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: "transparent", marginBottom: 6 },
  gridRowSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  gridRowText: { fontSize: 13, color: colors.onSurface, flex: 1, marginRight: spacing.sm },
  crudBtnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  crudBtn: { paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  crudBtnText: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  crudBtnPrimary: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  crudBtnPrimaryText: { fontSize: 13, fontWeight: "600", color: colors.onBrandPrimary },
  crudBtnDanger: { backgroundColor: colors.surface, borderColor: colors.error },
  crudBtnDangerText: { fontSize: 13, fontWeight: "600", color: colors.error },
  radioRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: spacing.sm },
  radioBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  radioBtnSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  radioCircle: { width: 16, height: 16, borderRadius: 8, borderWidth: 1.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioCircleSel: { borderColor: colors.brandPrimary },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  inputWithBtn: { flexDirection: "row", alignItems: "center", minWidth: 0 },
  cepBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.brandPrimary, marginLeft: 8 },

  secondaryActionBtn: {
    flexDirection: "row", alignItems: "center", gap: 8, flexGrow: 1, minWidth: 200,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12,
  },
  secondaryActionText: { flex: 1, fontSize: 13, fontWeight: "600", color: colors.onSurface },

  slideBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  slideBgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  slideCard: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
  },
  slideCardWebCompact: {
    width: "100%", maxWidth: 640, alignSelf: "center", maxHeight: "85%",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  slideHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  slideTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },

  addBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 10 },
  addBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },
});

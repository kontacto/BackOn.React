import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Platform } from "react-native";
import { useRouter } from "expo-router";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { colors } from "@/src/theme/colors";

// ---------- Tipos ----------
export type TipoCliente = { codigo: number; descricao: string };
export type LookupItem = { codigo: number | string; descricao: string };
export type Telefone = { ddd: string; tel: string; descricao: string };
export type Endereco = {
  tipo: number; // 0=Comercial, 1=Cobrança, 2=Entrega
  cep: string;
  endereco: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  uf: string;
};
export type Contato = {
  contato: string;
  setor: string;
  cargo: string;
  ddd: string;
  telefone: string;
  ddd_fax: string;
  fax: string;
  ddd_celular: string;
  celular: string;
  e_mail: string;
  sexo: string;
};

export const ENDERECO_TIPOS = [
  { value: 0, label: "Comercial" },
  { value: 1, label: "Cobrança" },
  { value: 2, label: "Entrega" },
];

// Nomes das rotas de lookup (codigo, descricao) usadas na aba Dados Secundários.
const LOOKUP_ROUTES = {
  segmentos: "segmentos",
  rotas: "rotas",
  regioes: "regioes",
  formaPagamento: "forma-pagamento",
  canalAquisicao: "canal-aquisicao-cliente",
  diaSemana: "dia-semana",
  centroCusto: "centro-custo",
  contas: "contas",
  classes: "classes",
  subClasses: "sub-classes",
  statusCliente: "status-cliente",
} as const;

// ---------- Validação CPF/CNPJ (espelha backend) ----------
export function onlyAlnumUpper(s: string): string {
  return (s || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function validCPF(s: string): boolean {
  const d = s.replace(/\D/g, "");
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
  for (const len of [9, 10]) {
    let sum = 0;
    for (let j = 0; j < len; j++) sum += parseInt(d[j], 10) * (len + 1 - j);
    let dv = (sum * 10) % 11;
    if (dv === 10) dv = 0;
    if (dv !== parseInt(d[len], 10)) return false;
  }
  return true;
}

export function validCNPJ(s: string): boolean {
  const v = onlyAlnumUpper(s);
  if (v.length !== 14) return false;
  if (!/^[A-Z0-9]{12}\d{2}$/.test(v)) return false;
  if (new Set(v.split("")).size === 1) return false;
  const val = (c: string) => c.charCodeAt(0) - "0".charCodeAt(0);
  const p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  let s1 = 0;
  for (let i = 0; i < 12; i++) s1 += val(v[i]) * p1[i];
  let dv1 = s1 % 11;
  dv1 = dv1 < 2 ? 0 : 11 - dv1;
  if (dv1 !== parseInt(v[12], 10)) return false;
  let s2 = 0;
  for (let i = 0; i < 13; i++) s2 += val(v[i]) * p2[i];
  let dv2 = s2 % 11;
  dv2 = dv2 < 2 ? 0 : 11 - dv2;
  if (dv2 !== parseInt(v[13], 10)) return false;
  return true;
}

export function detectDocType(raw: string): "CPF" | "CNPJ" | "UNKNOWN" {
  const v = onlyAlnumUpper(raw);
  if (v.length === 0) return "UNKNOWN";
  if (/[A-Z]/.test(v)) return "CNPJ";
  if (v.length <= 11) return "CPF";
  return "CNPJ";
}

export function maskCgcCpf(raw: string): string {
  const v = onlyAlnumUpper(raw).slice(0, 14);
  const tipo = detectDocType(v);
  if (tipo === "CPF") {
    // 000.000.000-00
    return v
      .slice(0, 11)
      .replace(/^(\d{0,3})(\d{0,3})?(\d{0,3})?(\d{0,2})?.*/, (_m, a, b, c, d) => {
        let out = a;
        if (b) out += "." + b;
        if (c) out += "." + c;
        if (d) out += "-" + d;
        return out;
      });
  }
  // CNPJ (numérico ou alfanumérico): XX.XXX.XXX/XXXX-DD
  const padded = v.padEnd(14, " ").slice(0, 14);
  let out = "";
  for (let i = 0; i < v.length; i++) {
    if (i === 2 || i === 5) out += ".";
    if (i === 8) out += "/";
    if (i === 12) out += "-";
    out += padded[i];
  }
  return out;
}

export function emailValido(s: string): boolean {
  if (!s) return true; // opcional
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());
}

// ---------- Toast simples ----------
export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const [tone, setTone] = useState<"info" | "error" | "success">("info");
  const tRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const show = useCallback(
    (m: string, t: "info" | "error" | "success" = "info") => {
      setMsg(m);
      setTone(t);
      if (tRef.current) clearTimeout(tRef.current);
      tRef.current = setTimeout(() => setMsg(null), 3500);
    },
    []
  );
  return { msg, tone, show };
}

const TOAST_COLORS = {
  info: colors.brandSecondary,
  error: colors.error,
  success: colors.success,
};

export function toastBackgroundColor(tone: "info" | "error" | "success"): string {
  return TOAST_COLORS[tone];
}

// ============================================================
// Hook principal: estado e lógica de cadastro/edição de cliente,
// compartilhado entre o formulário rápido (mobile+web) e o
// cadastro completo (web-only).
// ============================================================
export function useClienteForm(opts: {
  editing: boolean;
  codigo: number | null;
  initialNome?: string;
  selfRoute: string; // rota da própria tela, usada ao redirecionar para edição após localizar cliente existente
}) {
  const { editing, codigo, initialNome, selfRoute } = opts;
  const router = useRouter();
  const auditCtx = useAuditContext();

  const [conn, setConn] = useState<Connection | null>(null);
  const [vendedor, setVendedor] = useState<number | null>(null);
  const [loadingInit, setLoadingInit] = useState(true);
  const [saving, setSaving] = useState(false);
  const { show: showToast, msg: toastMsg, tone: toastTone } = useToast();

  // Dados principais
  const [cgcCpf, setCgcCpf] = useState("");
  const [nome, setNome] = useState(initialNome || "");
  const [email, setEmail] = useState("");
  const [inscre, setInscre] = useState("");
  const [tipo, setTipo] = useState<string>(""); // codigo string FK
  const [aceitaEmail, setAceitaEmail] = useState(false);
  const [nomeFantasia, setNomeFantasia] = useState("");
  const [sexo, setSexo] = useState(""); // CPF apenas: M/F
  const [dataNasc, setDataNasc] = useState<string | null>(null); // CPF=nasc, CNPJ=abertura
  const [inscrMun, setInscrMun] = useState(""); // CNPJ apenas
  const [site, setSite] = useState("");
  const [historico, setHistorico] = useState("");
  const [situacao, setSituacao] = useState<"A" | "I">("A");
  const [status, setStatus] = useState<string>("A"); // FK STATUS_CLIENTE.codigo — Ativo por padrão
  const [inativoEm, setInativoEm] = useState<string | null>(null);

  // Dados secundários
  const [contatoPrincipal, setContatoPrincipal] = useState("");
  const [limiteCredito, setLimiteCredito] = useState("");
  const [desconto, setDesconto] = useState("");
  const [regimeTributario, setRegimeTributario] = useState("");
  const [creditaIcms, setCreditaIcms] = useState(false);
  const [consumidorFinal, setConsumidorFinal] = useState(false);
  const [tributaIssForaMunicipio, setTributaIssForaMunicipio] = useState(false);
  const [faturaPara, setFaturaPara] = useState(false);
  const [clientePrincipal, setClientePrincipal] = useState<string>("");
  const [clientePrincipalNome, setClientePrincipalNome] = useState("");
  const [prazoFaturamento, setPrazoFaturamento] = useState("");
  const [indpres, setIndpres] = useState("");
  const [canalAquisicaoCliente, setCanalAquisicaoCliente] = useState<string>("");
  const [diaContato, setDiaContato] = useState<string>("");
  const [diaEntrega, setDiaEntrega] = useState<string>("");
  const [formaPagamento, setFormaPagamento] = useState<string>("");
  const [segmento, setSegmento] = useState<string>("");
  const [rota, setRota] = useState<string>("");
  const [regiao, setRegiao] = useState<string>("");
  const [emailCobranca, setEmailCobranca] = useState("");
  const [emailNfe, setEmailNfe] = useState("");
  const [centroCustoCliente, setCentroCustoCliente] = useState<string>("");
  const [contaTransfCaixa, setContaTransfCaixa] = useState<string>("");
  const [cobraTarifaBancaria, setCobraTarifaBancaria] = useState(false);
  const [tipoCobrancaTarifa, setTipoCobrancaTarifa] = useState<"B" | "N" | "">(""); // B=Boleto, N=NFe (coluna nvarchar(1))
  const [valorFrete, setValorFrete] = useState("");
  const [classeCaixa, setClasseCaixa] = useState<string>("");
  const [subClasseCaixa, setSubClasseCaixa] = useState<string>("");

  // Contatos (pessoas de contato — entidade separada dos telefones)
  const blankContato = (): Contato => ({
    contato: "", setor: "", cargo: "", ddd: "", telefone: "",
    ddd_fax: "", fax: "", ddd_celular: "", celular: "", e_mail: "", sexo: "",
  });
  const [contatos, setContatos] = useState<Contato[]>([]);
  const [contatoDraft, setContatoDraft] = useState<Contato>(blankContato());
  const [contatoEditIdx, setContatoEditIdx] = useState<number | null>(null);

  // Tipos disponíveis
  const [tiposCliente, setTiposCliente] = useState<TipoCliente[]>([]);

  // Lookups da aba Dados Secundários
  const [segmentos, setSegmentos] = useState<LookupItem[]>([]);
  const [rotas, setRotas] = useState<LookupItem[]>([]);
  const [regioes, setRegioes] = useState<LookupItem[]>([]);
  const [formasPagamento, setFormasPagamento] = useState<LookupItem[]>([]);
  const [canaisAquisicao, setCanaisAquisicao] = useState<LookupItem[]>([]);
  const [diasSemana, setDiasSemana] = useState<LookupItem[]>([]);
  const [centrosCusto, setCentrosCusto] = useState<LookupItem[]>([]);
  const [contasLista, setContasLista] = useState<LookupItem[]>([]);
  const [classes, setClasses] = useState<LookupItem[]>([]);
  const [subClasses, setSubClasses] = useState<LookupItem[]>([]);
  const [statusClienteOptions, setStatusClienteOptions] = useState<LookupItem[]>([]);

  // Telefones (até 3). Duas APIs coexistem sobre o mesmo estado `telefones`:
  //  - índice direto (addTelefone/removeTelefone/updateTelefone) — usada pelo
  //    cadastro rápido (cliente-form.tsx, mobile+web), que edita in-line sem grade.
  //  - rascunho + grade (telefoneDraft/incluir/alterar/excluir) — usada pelo
  //    cadastro completo (cliente-completo.tsx, web-only), que espelha o padrão
  //    legado GridT/CmdTel (lista de gravados + formulário único).
  const blankTelefone = (): Telefone => ({ ddd: "", tel: "", descricao: "" });
  const [telefones, setTelefones] = useState<Telefone[]>([blankTelefone()]);
  const [telefoneDraft, setTelefoneDraft] = useState<Telefone>(blankTelefone());
  const [telefoneEditIdx, setTelefoneEditIdx] = useState<number | null>(null);

  // Endereços (cliente pode ter vários — residencial, entrega, cobrança...) — mesma
  // coexistência de APIs (índice direto vs. rascunho+grade GridE/CmdAdd-Alter-Exc).
  const blankEndereco = (): Endereco => ({
    tipo: 0,
    cep: "",
    endereco: "",
    numero: "",
    complemento: "",
    bairro: "",
    cidade: "",
    uf: "",
  });
  const [enderecos, setEnderecos] = useState<Endereco[]>([blankEndereco()]);
  const [enderecoDraft, setEnderecoDraft] = useState<Endereco>(blankEndereco());
  const [enderecoEditIdx, setEnderecoEditIdx] = useState<number | null>(null);
  const [cepLoadingIdx, setCepLoadingIdx] = useState<number | null>(null);
  const [cepLoadingDraft, setCepLoadingDraft] = useState(false);

  // -------- Init: carrega conexão, vendedor, tipos, e (se editando) cliente
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const session = await getSession();
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === session?.empresa) || null;
      if (cancelled) return;
      if (!c) {
        showToast("Conexão não encontrada.", "error");
        setLoadingInit(false);
        return;
      }
      setConn(c);

      const codInt = session?.funcionario?.codigo_int;
      if (typeof codInt === "number") setVendedor(codInt);
      else if (typeof codInt === "string" && /^\d+$/.test(codInt)) setVendedor(parseInt(codInt, 10));

      // Carrega dropdown tipo_cliente
      try {
        const url = `${c.api.replace(/\/+$/, "")}/api/tipo-cliente?servidor=${encodeURIComponent(
          c.servidor
        )}&banco=${encodeURIComponent(c.banco)}`;
        const r = await fetch(url);
        const j = await r.json();
        if (!cancelled && j?.success && Array.isArray(j.items)) {
          setTiposCliente(j.items as TipoCliente[]);
        } else if (!cancelled) {
          showToast(j?.message || "Falha ao carregar tipos de cliente.", "error");
        }
      } catch (e) {
        if (!cancelled)
          showToast(`Erro ao carregar tipos: ${e instanceof Error ? e.message : e}`, "error");
      }

      // Carrega lookups da aba Dados Secundários (falhas individuais são silenciosas —
      // o campo correspondente simplesmente fica sem opções).
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const loadLookup = async (path: string, setter: (items: LookupItem[]) => void) => {
        try {
          const r = await fetch(`${base}/api/${path}?${qs}`);
          const j = await r.json();
          if (!cancelled && j?.success && Array.isArray(j.items)) setter(j.items as LookupItem[]);
        } catch {
          /* silencioso — lookup opcional */
        }
      };
      await Promise.all([
        loadLookup(LOOKUP_ROUTES.segmentos, setSegmentos),
        loadLookup(LOOKUP_ROUTES.rotas, setRotas),
        loadLookup(LOOKUP_ROUTES.regioes, setRegioes),
        loadLookup(LOOKUP_ROUTES.formaPagamento, setFormasPagamento),
        loadLookup(LOOKUP_ROUTES.canalAquisicao, setCanaisAquisicao),
        loadLookup(LOOKUP_ROUTES.diaSemana, setDiasSemana),
        loadLookup(LOOKUP_ROUTES.centroCusto, setCentrosCusto),
        loadLookup(LOOKUP_ROUTES.contas, setContasLista),
        loadLookup(LOOKUP_ROUTES.classes, setClasses),
        loadLookup(LOOKUP_ROUTES.subClasses, setSubClasses),
        loadLookup(LOOKUP_ROUTES.statusCliente, setStatusClienteOptions),
      ]);

      // Se editando, carrega cliente
      if (editing && codigo) {
        try {
          const url = `${c.api.replace(/\/+$/, "")}/api/clientes/${codigo}?servidor=${encodeURIComponent(
            c.servidor
          )}&banco=${encodeURIComponent(c.banco)}`;
          const r = await fetch(url);
          const j = await r.json();
          if (cancelled) return;
          if (!j?.success) {
            showToast(j?.message || "Erro ao carregar cliente.", "error");
          } else {
            const cli = j.cliente || {};
            setCgcCpf(maskCgcCpf(cli.cgc_cpf || ""));
            setNome(cli.nome || "");
            setEmail(cli.e_mail || "");
            setInscre(cli.inscre || "");
            setTipo(cli.tipo ? String(cli.tipo).trim() : "");
            setAceitaEmail(!!cli.aceita_email);

            // Dados Principais adicionais
            setNomeFantasia(cli.nome_fantasia || "");
            setSexo(cli.sexo || "");
            setDataNasc(cli.data_nasc ? String(cli.data_nasc).slice(0, 10) : null);
            setInscrMun(cli.inscr_mun || "");
            setSite(cli.site || "");
            setHistorico(cli.historico || "");
            setSituacao(cli.situacao === "I" ? "I" : "A");
            setStatus(cli.status || "A");
            setInativoEm(cli.inativo_em ? String(cli.inativo_em).slice(0, 10) : null);

            // Dados Secundários
            setContatoPrincipal(cli.contato || "");
            setLimiteCredito(cli.limite_credito != null ? String(cli.limite_credito) : "");
            setDesconto(cli.desconto != null ? String(cli.desconto) : "");
            setRegimeTributario(cli.regime_tributario != null ? String(cli.regime_tributario) : "");
            setCreditaIcms(!!cli.credita_icms);
            setConsumidorFinal(!!cli.consumidor_final);
            setTributaIssForaMunicipio(!!cli.tributa_iss_fora_municipio);
            setFaturaPara(!!cli.fatura_para);
            setClientePrincipal(cli.cliente_principal != null ? String(cli.cliente_principal) : "");
            setPrazoFaturamento(cli.prazo_faturamento != null ? String(cli.prazo_faturamento) : "");
            setIndpres(cli.indpres != null ? String(cli.indpres) : "");
            setCanalAquisicaoCliente(cli.canal_aquisicao_cliente != null ? String(cli.canal_aquisicao_cliente) : "");
            setDiaContato(cli.dia_contato != null ? String(cli.dia_contato) : "");
            setDiaEntrega(cli.dia_entrega != null ? String(cli.dia_entrega) : "");
            setFormaPagamento(cli.forma_pagamento != null ? String(cli.forma_pagamento) : "");
            setSegmento(cli.segmento != null ? String(cli.segmento) : "");
            setRota(cli.rota != null ? String(cli.rota) : "");
            setRegiao(cli.regiao != null ? String(cli.regiao) : "");
            setEmailCobranca(cli.email_cobranca || "");
            setEmailNfe(cli.email_nfe || "");
            setCentroCustoCliente(cli.centro_custo_cliente != null ? String(cli.centro_custo_cliente) : "");
            setContaTransfCaixa(cli.conta_transf_caixa != null ? String(cli.conta_transf_caixa) : "");
            setCobraTarifaBancaria(!!cli.cobra_tarifa_bancaria);
            setTipoCobrancaTarifa(cli.tipo_cobranca_tarifa === "N" ? "N" : cli.tipo_cobranca_tarifa === "B" ? "B" : "");
            setValorFrete(cli.valor_frete != null ? String(cli.valor_frete) : "");
            setClasseCaixa(cli.classe_caixa != null ? String(cli.classe_caixa) : "");
            setSubClasseCaixa(cli.sub_classe_caixa != null ? String(cli.sub_classe_caixa) : "");

            // Endereços
            const ends: Endereco[] = Array.isArray(j.enderecos)
              ? j.enderecos.map(
                  (e: {
                    tipo?: number;
                    cep?: string;
                    endereco?: string;
                    numero?: number | string;
                    complemento?: string;
                    bairro?: string;
                    cidade?: string;
                    uf?: string;
                  }) => ({
                    tipo: typeof e.tipo === "number" ? e.tipo : 0,
                    cep: e.cep || "",
                    endereco: e.endereco || "",
                    numero: e.numero != null ? String(e.numero) : "",
                    complemento: e.complemento || "",
                    bairro: e.bairro || "",
                    cidade: e.cidade || "",
                    uf: e.uf || "",
                  })
                )
              : [];
            setEnderecos(ends.length > 0 ? ends : [blankEndereco()]);

            // Telefones (puxa de cliente_tel; se vazio mas cliente tem ddd_cli/telefone_cli, usa esses)
            const tels: Telefone[] = Array.isArray(j.telefones)
              ? j.telefones.map((t: { ddd?: string; tel?: string; descricao?: string }) => ({
                  ddd: t.ddd || "",
                  tel: t.tel || "",
                  descricao: t.descricao || "",
                }))
              : [];
            if (tels.length === 0 && (cli.ddd_cli || cli.telefone_cli)) {
              tels.push({
                ddd: cli.ddd_cli || "",
                tel: cli.telefone_cli || "",
                descricao: "Principal",
              });
            }
            setTelefones(tels.length > 0 ? tels : [blankTelefone()]);

            // Contatos (pessoas de contato — entidade separada dos telefones)
            const conts: Contato[] = Array.isArray(j.contatos)
              ? j.contatos.map((ct: Partial<Contato>) => ({
                  contato: ct.contato || "",
                  setor: ct.setor || "",
                  cargo: ct.cargo || "",
                  ddd: ct.ddd || "",
                  telefone: ct.telefone || "",
                  ddd_fax: ct.ddd_fax || "",
                  fax: ct.fax || "",
                  ddd_celular: ct.ddd_celular || "",
                  celular: ct.celular || "",
                  e_mail: ct.e_mail || "",
                  sexo: ct.sexo || "",
                }))
              : [];
            setContatos(conts);

            // Resolve nome do cliente principal (faturamento centralizado), se houver
            if (cli.cliente_principal) {
              fetch(
                `${c.api.replace(/\/+$/, "")}/api/clientes/${cli.cliente_principal}/resumo?servidor=${encodeURIComponent(
                  c.servidor
                )}&banco=${encodeURIComponent(c.banco)}`
              )
                .then((r) => r.json())
                .then((jr) => {
                  if (!cancelled && jr?.success) setClientePrincipalNome(jr.cliente?.nome || "");
                })
                .catch(() => {});
            }
          }
        } catch (e) {
          if (!cancelled)
            showToast(`Erro ao carregar: ${e instanceof Error ? e.message : e}`, "error");
        }
      }

      if (!cancelled) setLoadingInit(false);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------- Label dinâmico do campo "inscre"
  const docType = useMemo(() => detectDocType(cgcCpf), [cgcCpf]);
  const labelInscre = docType === "CPF" ? "Identidade" : "Insc. Estadual";

  // -------- Validação do CGC/CPF (crivo CPF 11 dígitos / CNPJ 14, alfanumérico 2026)
  const [cgcCpfTouched, setCgcCpfTouched] = useState(false);
  const cgcCpfError = useMemo(() => {
    if (!cgcCpfTouched) return null;
    const raw = onlyAlnumUpper(cgcCpf);
    if (!raw) return null;
    if (raw.length === 11) return validCPF(raw) ? null : "CPF inválido.";
    if (raw.length === 14) return validCNPJ(raw) ? null : "CNPJ inválido.";
    return "CGC/CPF deve ter 11 (CPF) ou 14 (CNPJ) caracteres.";
  }, [cgcCpf, cgcCpfTouched]);

  // -------- Tipo cliente selecionado (descrição para exibir)
  const tipoSelecionadoLabel = useMemo(() => {
    if (!tipo) return "";
    const t = tiposCliente.find((x) => String(x.codigo) === tipo);
    return t ? t.descricao : `Código ${tipo}`;
  }, [tipo, tiposCliente]);

  // -------- ViaCEP por índice (cadastro rápido — edita enderecos[idx] direto)
  const buscarCEP = useCallback(
    async (idx: number, cepRaw: string) => {
      const cep = cepRaw.replace(/\D/g, "").slice(0, 8);
      if (cep.length !== 8) return;
      setCepLoadingIdx(idx);
      try {
        const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
        const j = await r.json();
        if (j?.erro) {
          showToast("CEP não encontrado.", "error");
        } else {
          setEnderecos((prev) =>
            prev.map((e, i) =>
              i === idx
                ? {
                    ...e,
                    cep,
                    endereco: j.logradouro || e.endereco,
                    bairro: j.bairro || e.bairro,
                    cidade: j.localidade || e.cidade,
                    uf: (j.uf || e.uf || "").toUpperCase().slice(0, 2),
                  }
                : e
            )
          );
        }
      } catch (e) {
        showToast(`Falha ViaCEP: ${e instanceof Error ? e.message : e}`, "error");
      } finally {
        setCepLoadingIdx(null);
      }
    },
    [showToast]
  );

  // -------- ViaCEP do rascunho (cadastro completo — grade + formulário único)
  const buscarCEPDraft = useCallback(
    async (cepRaw: string) => {
      const cep = cepRaw.replace(/\D/g, "").slice(0, 8);
      if (cep.length !== 8) return;
      setCepLoadingDraft(true);
      try {
        const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
        const j = await r.json();
        if (j?.erro) {
          showToast("CEP não encontrado.", "error");
        } else {
          setEnderecoDraft((e) => ({
            ...e,
            cep,
            endereco: j.logradouro || e.endereco,
            bairro: j.bairro || e.bairro,
            cidade: j.localidade || e.cidade,
            uf: (j.uf || e.uf || "").toUpperCase().slice(0, 2),
          }));
        }
      } catch (e) {
        showToast(`Falha ViaCEP: ${e instanceof Error ? e.message : e}`, "error");
      } finally {
        setCepLoadingDraft(false);
      }
    },
    [showToast]
  );

  // -------- Handlers
  const handleCgcCpfChange = (txt: string) => {
    setCgcCpf(maskCgcCpf(txt));
    setCgcCpfTouched(false); // limpa erro exibido enquanto o usuário volta a digitar
  };

  // -------- Busca cliente existente por CGC/CPF (ao perder foco / blur).
  // Se encontrado e ainda estamos em novo cadastro, oferece carregar para edição.
  const buscarPorCgc = useCallback(async () => {
    setCgcCpfTouched(true); // habilita exibição de erro de validação (crivo CPF/CNPJ)
    if (editing) return; // já editando, nada a fazer
    const raw = onlyAlnumUpper(cgcCpf);
    if (!raw) return;
    // Só busca se passou pela validação (CPF 11 ou CNPJ 14)
    const isValid =
      (raw.length === 11 && validCPF(raw)) ||
      (raw.length === 14 && validCNPJ(raw));
    if (!isValid) return;
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const url =
        `${base}/api/clientes/find/by-cgc` +
        `?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}` +
        `&cgc=${encodeURIComponent(raw)}`;
      const r = await fetch(url);
      const j = await r.json();
      if (j?.success && j?.found && j?.codigo) {
        // Recarrega a tela em modo edição (substitui rota — assim o efeito inicial roda)
        showToast(`Cliente já cadastrado: #${j.codigo}. Carregando...`, "info");
        setTimeout(() => {
          router.replace({
            pathname: selfRoute,
            params: { codigo: String(j.codigo) },
          } as never);
        }, 600);
      }
    } catch {
      /* silencioso — busca é opcional */
    }
  }, [cgcCpf, conn, editing, router, selfRoute, showToast]);

  // Dispara a busca por CGC/CPF AUTOMATICAMENTE quando o número fica válido
  // (debounce 350ms para evitar muitas chamadas durante a digitação).
  useEffect(() => {
    if (editing) return;
    const raw = onlyAlnumUpper(cgcCpf);
    const isValid =
      (raw.length === 11 && validCPF(raw)) ||
      (raw.length === 14 && validCNPJ(raw));
    if (!isValid) return;
    const t = setTimeout(() => {
      buscarPorCgc();
    }, 350);
    return () => clearTimeout(t);
    // buscarPorCgc é estável (useCallback) — deps são cgcCpf e editing
  }, [cgcCpf, editing, buscarPorCgc]);

  // -------- Cadastro rápido: CEP + telefones/endereços por índice direto
  const handleCepChange = (idx: number, txt: string) => {
    const d = txt.replace(/\D/g, "").slice(0, 8);
    setEnderecos((prev) => prev.map((e, i) => (i === idx ? { ...e, cep: d } : e)));
    if (d.length === 8) buscarCEP(idx, d);
  };

  const handleCepChangeDraft = (txt: string) => {
    const d = txt.replace(/\D/g, "").slice(0, 8);
    setEnderecoDraft((e) => ({ ...e, cep: d }));
    if (d.length === 8) buscarCEPDraft(d);
  };

  const addTelefone = () => {
    if (telefones.length >= 3) {
      showToast("Máximo de 3 telefones.", "info");
      return;
    }
    setTelefones((prev) => [...prev, blankTelefone()]);
  };

  const removeTelefone = (idx: number) => {
    setTelefones((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      return next.length === 0 ? [blankTelefone()] : next;
    });
  };

  const updateTelefone = (idx: number, patch: Partial<Telefone>) => {
    setTelefones((prev) => prev.map((t, i) => (i === idx ? { ...t, ...patch } : t)));
  };

  const addEndereco = () => {
    setEnderecos((prev) => [...prev, blankEndereco()]);
  };

  const removeEndereco = (idx: number) => {
    setEnderecos((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      return next.length === 0 ? [blankEndereco()] : next;
    });
  };

  const updateEndereco = (idx: number, patch: Partial<Endereco>) => {
    setEnderecos((prev) => prev.map((e, i) => (i === idx ? { ...e, ...patch } : e)));
  };

  // -------- Cadastro completo: Telefones — grade + formulário único (Incluir/Alterar/Excluir/Limpar)
  const updateTelefoneDraft = (patch: Partial<Telefone>) => {
    setTelefoneDraft((t) => ({ ...t, ...patch }));
  };

  const selecionarTelefone = (idx: number) => {
    setTelefoneEditIdx(idx);
    setTelefoneDraft({ ...telefones[idx] });
  };

  const limparTelefoneForm = () => {
    setTelefoneEditIdx(null);
    setTelefoneDraft(blankTelefone());
  };

  const incluirTelefone = () => {
    if (!telefoneDraft.tel.trim()) {
      showToast("Informe o telefone.", "error");
      return;
    }
    if (telefones.length >= 3) {
      showToast("Máximo de 3 telefones.", "info");
      return;
    }
    setTelefones((prev) => [...prev, telefoneDraft]);
    limparTelefoneForm();
  };

  const alterarTelefone = () => {
    if (telefoneEditIdx === null) return;
    if (!telefoneDraft.tel.trim()) {
      showToast("Informe o telefone.", "error");
      return;
    }
    setTelefones((prev) => prev.map((t, i) => (i === telefoneEditIdx ? telefoneDraft : t)));
    limparTelefoneForm();
  };

  const excluirTelefone = () => {
    if (telefoneEditIdx === null) return;
    setTelefones((prev) => prev.filter((_, i) => i !== telefoneEditIdx));
    limparTelefoneForm();
  };

  // -------- Endereços: grade + formulário único (Incluir/Alterar/Excluir/Limpar)
  const updateEnderecoDraft = (patch: Partial<Endereco>) => {
    setEnderecoDraft((e) => ({ ...e, ...patch }));
  };

  const selecionarEndereco = (idx: number) => {
    setEnderecoEditIdx(idx);
    setEnderecoDraft({ ...enderecos[idx] });
  };

  const limparEnderecoForm = () => {
    setEnderecoEditIdx(null);
    setEnderecoDraft(blankEndereco());
  };

  const validarEnderecoDraft = (): string | null => {
    if (!enderecoDraft.endereco.trim() && !enderecoDraft.cep.trim() && !enderecoDraft.cidade.trim()) {
      return "Informe ao menos CEP, endereço ou cidade.";
    }
    if (enderecoDraft.uf && enderecoDraft.uf.trim().length !== 2) return "UF deve ter 2 caracteres.";
    if (enderecoDraft.cep && enderecoDraft.cep.replace(/\D/g, "").length !== 8) return "CEP deve ter 8 dígitos.";
    return null;
  };

  const incluirEndereco = () => {
    const err = validarEnderecoDraft();
    if (err) {
      showToast(err, "error");
      return;
    }
    setEnderecos((prev) => [...prev, enderecoDraft]);
    limparEnderecoForm();
  };

  const alterarEndereco = () => {
    if (enderecoEditIdx === null) return;
    const err = validarEnderecoDraft();
    if (err) {
      showToast(err, "error");
      return;
    }
    setEnderecos((prev) => prev.map((e, i) => (i === enderecoEditIdx ? enderecoDraft : e)));
    limparEnderecoForm();
  };

  const excluirEndereco = () => {
    if (enderecoEditIdx === null) return;
    setEnderecos((prev) => prev.filter((_, i) => i !== enderecoEditIdx));
    limparEnderecoForm();
  };

  // -------- Contatos (pessoas de contato) — grade + formulário único
  // (Incluir/Alterar/Excluir/Limpar), mesmo padrão de Telefones/Endereços.
  const updateContatoDraft = (patch: Partial<Contato>) => {
    setContatoDraft((ct) => ({ ...ct, ...patch }));
  };

  const selecionarContato = (idx: number) => {
    setContatoEditIdx(idx);
    setContatoDraft({ ...contatos[idx] });
  };

  const limparContatoForm = () => {
    setContatoEditIdx(null);
    setContatoDraft(blankContato());
  };

  const incluirContato = () => {
    if (!contatoDraft.contato.trim()) {
      showToast("Informe o nome do contato.", "error");
      return;
    }
    setContatos((prev) => [...prev, contatoDraft]);
    limparContatoForm();
  };

  const alterarContato = () => {
    if (contatoEditIdx === null) return;
    if (!contatoDraft.contato.trim()) {
      showToast("Informe o nome do contato.", "error");
      return;
    }
    setContatos((prev) => prev.map((ct, i) => (i === contatoEditIdx ? contatoDraft : ct)));
    limparContatoForm();
  };

  const excluirContato = () => {
    if (contatoEditIdx === null) return;
    setContatos((prev) => prev.filter((_, i) => i !== contatoEditIdx));
    limparContatoForm();
  };

  // -------- Resolve nome do cliente principal (faturamento centralizado) ao informar o código
  const buscarClientePrincipal = useCallback(
    async (cod: string) => {
      const n = parseInt(cod, 10);
      if (!conn || !cod || Number.isNaN(n)) {
        setClientePrincipalNome("");
        return;
      }
      try {
        const base = conn.api.replace(/\/+$/, "");
        const url = `${base}/api/clientes/${n}/resumo?servidor=${encodeURIComponent(
          conn.servidor
        )}&banco=${encodeURIComponent(conn.banco)}`;
        const r = await fetch(url);
        const j = await r.json();
        setClientePrincipalNome(j?.success ? j.cliente?.nome || "" : "");
      } catch {
        setClientePrincipalNome("");
      }
    },
    [conn]
  );

  // -------- Validações pré-save
  const validateAll = (): string | null => {
    if (!nome.trim()) return "Nome é obrigatório.";
    if (nome.trim().length > 60) return "Nome excede 60 caracteres.";
    const raw = onlyAlnumUpper(cgcCpf);
    if (raw) {
      if (raw.length === 11) {
        if (!validCPF(raw)) return "CPF inválido.";
      } else if (raw.length === 14) {
        if (!validCNPJ(raw)) return "CNPJ inválido.";
      } else {
        return "CGC/CPF deve ter 11 (CPF) ou 14 (CNPJ) caracteres.";
      }
    }
    if (!emailValido(email)) return "E-mail inválido.";
    for (const e of enderecos) {
      const preenchido = e.cep || e.endereco || e.cidade;
      if (!preenchido) continue;
      if (e.uf && e.uf.trim().length !== 2) return "UF deve ter 2 caracteres.";
      if (e.cep && e.cep.replace(/\D/g, "").length !== 8) return "CEP deve ter 8 dígitos.";
    }
    const telsValidos = telefones.filter((t) => (t.tel || "").trim().length > 0);
    for (const t of telsValidos) {
      if (!/^\d{0,4}$/.test((t.ddd || "").trim())) return "DDD inválido (até 4 dígitos).";
    }
    return null;
  };

  // -------- Gravar
  const handleSave = async (onSaved?: (codigo?: number, wasEditing?: boolean) => void) => {
    const err = validateAll();
    if (err) {
      showToast(err, "error");
      return;
    }
    if (!conn) {
      showToast("Conexão indisponível.", "error");
      return;
    }
    setSaving(true);
    try {
      const telsToSend = telefones
        .filter((t) => (t.tel || "").trim().length > 0)
        .slice(0, 3)
        .map((t) => ({
          ddd: (t.ddd || "").trim(),
          tel: (t.tel || "").trim(),
          descricao: (t.descricao || "").trim(),
        }));

      const enderecosToSend = enderecos
        .filter((e) => e.cep || e.endereco || e.cidade)
        .map((e) => ({
          tipo: e.tipo,
          cep: e.cep.replace(/\D/g, ""),
          endereco: e.endereco.trim(),
          numero: e.numero ? parseInt(e.numero, 10) || null : null,
          complemento: e.complemento.trim(),
          bairro: e.bairro.trim(),
          cidade: e.cidade.trim(),
          uf: e.uf.trim().toUpperCase(),
        }));

      const contatosToSend = contatos
        .filter((ct) => ct.contato.trim())
        .map((ct) => ({
          contato: ct.contato.trim(),
          setor: ct.setor.trim(),
          cargo: ct.cargo.trim(),
          ddd: ct.ddd.trim(),
          telefone: ct.telefone.trim(),
          ddd_fax: ct.ddd_fax.trim(),
          fax: ct.fax.trim(),
          ddd_celular: ct.ddd_celular.trim(),
          celular: ct.celular.trim(),
          e_mail: ct.e_mail.trim(),
          sexo: ct.sexo.trim(),
        }));

      const toFloat = (s: string): number | null => {
        const v = parseFloat(s.replace(",", "."));
        return Number.isFinite(v) ? v : null;
      };
      const toInt = (s: string): number | null => {
        const v = parseInt(s, 10);
        return Number.isFinite(v) ? v : null;
      };

      const body = {
        servidor: conn.servidor,
        banco: conn.banco,
        cgc_cpf: onlyAlnumUpper(cgcCpf),
        nome: nome.trim(),
        e_mail: email.trim(),
        inscre: inscre.trim(),
        tipo: tipo,
        aceita_email: aceitaEmail,
        vendedor: vendedor,
        usuario_cadastro: vendedor,
        usuario_alteracao: vendedor,
        classe: auditCtx.classe,
        plataforma: auditCtx.plataforma,
        enderecos: enderecosToSend,
        telefones: telsToSend,
        contatos: contatosToSend,
        nome_fantasia: nomeFantasia.trim(),
        sexo: sexo.trim(),
        data_nasc: dataNasc,
        inscr_mun: inscrMun.trim(),
        site: site.trim(),
        historico: historico.trim(),
        situacao: situacao,
        status: status.trim(),
        inativo_em: inativoEm,
        contato: contatoPrincipal.trim(),
        limite_credito: limiteCredito ? toFloat(limiteCredito) : null,
        desconto: desconto ? toFloat(desconto) : null,
        regime_tributario: regimeTributario ? toInt(regimeTributario) : null,
        credita_icms: creditaIcms,
        consumidor_final: consumidorFinal,
        tributa_iss_fora_municipio: tributaIssForaMunicipio,
        fatura_para: faturaPara,
        cliente_principal: clientePrincipal ? toInt(clientePrincipal) : null,
        prazo_faturamento: prazoFaturamento ? toInt(prazoFaturamento) : null,
        indpres: indpres.trim(),
        canal_aquisicao_cliente: canalAquisicaoCliente ? toInt(canalAquisicaoCliente) : null,
        dia_contato: diaContato ? toInt(diaContato) : null,
        dia_entrega: diaEntrega ? toInt(diaEntrega) : null,
        forma_pagamento: formaPagamento.trim(),
        segmento: segmento.trim(),
        rota: rota ? toInt(rota) : null,
        regiao: regiao ? toInt(regiao) : null,
        email_cobranca: emailCobranca.trim(),
        email_nfe: emailNfe.trim(),
        centro_custo_cliente: centroCustoCliente ? toInt(centroCustoCliente) : null,
        conta_transf_caixa: contaTransfCaixa ? toInt(contaTransfCaixa) : null,
        cobra_tarifa_bancaria: cobraTarifaBancaria,
        tipo_cobranca_tarifa: tipoCobrancaTarifa,
        valor_frete: valorFrete ? toFloat(valorFrete) : null,
        classe_caixa: classeCaixa ? toInt(classeCaixa) : null,
        sub_classe_caixa: subClasseCaixa ? toInt(subClasseCaixa) : null,
      };

      const base = conn.api.replace(/\/+$/, "");
      const url = editing && codigo ? `${base}/api/clientes/${codigo}` : `${base}/api/clientes/create`;
      const method = editing && codigo ? "PUT" : "POST";

      const r = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j?.success) {
        showToast(j?.message || "Falha ao gravar.", "error");
      } else {
        showToast(editing ? "Cliente atualizado." : "Cliente cadastrado.", "success");
        // Repassa o código e se era edição pro chamador decidir a navegação —
        // cada tela que usa este hook (cliente-completo.tsx x
        // cliente-form.tsx) tem uma resposta diferente pro "acabei de criar
        // um cliente novo" (a completa fica na tela pra destravar
        // Telefones/Endereços/Contatos/Anexos — regra global em CLAUDE.md >
        // "Global Entity Rules"; a rápida só quer voltar pro fluxo de
        // Pedido/O.S. que a chamou).
        setTimeout(() => onSaved?.(j.codigo, editing), 700);
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally {
      setSaving(false);
    }
  };

  return {
    isWeb: Platform.OS === "web",
    loadingInit,
    saving,
    toastMsg,
    toastTone,
    showToast,
    vendedor,
    cgcCpf,
    handleCgcCpfChange,
    buscarPorCgc,
    nome,
    setNome,
    email,
    setEmail,
    inscre,
    setInscre,
    tipo,
    setTipo,
    aceitaEmail,
    setAceitaEmail,
    tiposCliente,
    docType,
    cgcCpfError,
    labelInscre,
    tipoSelecionadoLabel,
    telefones,
    addTelefone,
    removeTelefone,
    updateTelefone,
    telefoneDraft,
    telefoneEditIdx,
    updateTelefoneDraft,
    selecionarTelefone,
    limparTelefoneForm,
    incluirTelefone,
    alterarTelefone,
    excluirTelefone,
    enderecos,
    addEndereco,
    removeEndereco,
    updateEndereco,
    enderecoDraft,
    enderecoEditIdx,
    updateEnderecoDraft,
    selecionarEndereco,
    limparEnderecoForm,
    incluirEndereco,
    alterarEndereco,
    excluirEndereco,
    cepLoadingIdx,
    buscarCEP,
    handleCepChange,
    cepLoadingDraft,
    buscarCEPDraft,
    handleCepChangeDraft,
    handleSave,

    // Dados Principais adicionais
    nomeFantasia,
    setNomeFantasia,
    sexo,
    setSexo,
    dataNasc,
    setDataNasc,
    inscrMun,
    setInscrMun,
    site,
    setSite,
    historico,
    setHistorico,
    situacao,
    setSituacao,
    status,
    setStatus,
    statusClienteOptions,
    inativoEm,
    setInativoEm,

    // Contatos
    contatos,
    contatoDraft,
    contatoEditIdx,
    updateContatoDraft,
    selecionarContato,
    limparContatoForm,
    incluirContato,
    alterarContato,
    excluirContato,

    // Dados Secundários
    contatoPrincipal,
    setContatoPrincipal,
    limiteCredito,
    setLimiteCredito,
    desconto,
    setDesconto,
    regimeTributario,
    setRegimeTributario,
    creditaIcms,
    setCreditaIcms,
    consumidorFinal,
    setConsumidorFinal,
    tributaIssForaMunicipio,
    setTributaIssForaMunicipio,
    faturaPara,
    setFaturaPara,
    clientePrincipal,
    setClientePrincipal,
    clientePrincipalNome,
    buscarClientePrincipal,
    prazoFaturamento,
    setPrazoFaturamento,
    indpres,
    setIndpres,
    canalAquisicaoCliente,
    setCanalAquisicaoCliente,
    diaContato,
    setDiaContato,
    diaEntrega,
    setDiaEntrega,
    formaPagamento,
    setFormaPagamento,
    segmento,
    setSegmento,
    rota,
    setRota,
    regiao,
    setRegiao,
    emailCobranca,
    setEmailCobranca,
    emailNfe,
    setEmailNfe,
    centroCustoCliente,
    setCentroCustoCliente,
    contaTransfCaixa,
    setContaTransfCaixa,
    cobraTarifaBancaria,
    setCobraTarifaBancaria,
    tipoCobrancaTarifa,
    setTipoCobrancaTarifa,
    valorFrete,
    setValorFrete,
    classeCaixa,
    setClasseCaixa,
    subClasseCaixa,
    setSubClasseCaixa,

    // Lookups Dados Secundários
    segmentos,
    rotas,
    regioes,
    formasPagamento,
    canaisAquisicao,
    diasSemana,
    centrosCusto,
    contasLista,
    classes,
    subClasses,

    // Conexão ativa (servidor/banco/api) — usado por seções que fazem sua
    // própria chamada HTTP direta (ex.: GestorDocumentosSection).
    conn,
  };
}

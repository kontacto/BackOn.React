import { useCallback, useEffect, useState } from "react";
import { useRouter } from "expo-router";

import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";

// Cadastro de Produtos (completo) — tabela `pecas`. Legado: FrmManPec.frm
// (Kontacto), rastreado campo-a-campo 2026-07-14 — ver
// backend/services/produto_completo_service.py pro mapeamento completo e
// PENDENCIAS.md pro relatório de rastreio. Mesmo padrão de "form dict +
// setField" já usado em useControleSistemaForm.ts — evita ~130 useState
// individuais pra um form deste tamanho.

export type Conn = { servidor: string; banco: string; api: string };
export type ProdutoForm = Record<string, string | boolean>;

const BOOL_FIELDS = [
  "preco_variado", "Produto_web", "FRETE_GRATIS_SITE", "paga_comissao", "aceita_desconto",
  "controla_num_serie", "peso_variado", "lancamento", "esgotado",
] as const;

const TEXT_FIELDS = [
  "codigo_fab", "codigo_bar", "codigo_mercosul", "descricao", "descricao_pdv", "descricao_embarque",
  "descricao_nf", "Descricao_Completa", "cod_anp", "marca_produto", "modelo_produto",
  "nivel1", "nivel2", "nivel3", "nivel4", "nivel5", "situacao", "politica_preco",
  "codigo_cest", "BENEFICIO_FISCAL", "origem", "cst_ipi_entrada", "cst_ipi_saida", "ENQUADRAMENTO_IPI",
  "cod_icms", "cod_grupo_pis_cofins", "unidade_medida", "un_compra", "un_embarque", "un_fracao",
  "prateleira", "indice_preco", "sinopse",
] as const;

const NUM_FIELDS = [
  "p_custo", "p_venda", "p_sugestao", "p_garantia", "p_sugerido", "preco_base", "preco_promocional", "preco_lista",
  "desc_g", "desc_s", "desc_v", "comissao", "comissao_a", "comissao_e",
  "valor_comissao", "Valor_Comissão_E", "Valor_Comissão_A",
  "valor_desc_base_comissao", "valor_desc_base_comissao_e", "valor_desc_base_comissao_a",
  "perc_ipi", "valor_ipi", "cod_grupo_pis_cofins", "tributacao_pis", "perc_valor_pis",
  "tributacao_cofins", "perc_valor_cofins", "outros_trib_federais", "IBPT_FEDERAIS", "IBPT_ESTADUAIS",
  "valor_substituicao", "perc_mva",
  "comprimento", "largura", "altura", "peso_liquido", "peso_bruto",
  "qtd_un_compra", "qtd_un_embarque", "QTD_UN_VENDA",
  "prazo_entrega", "prazo_fornecedor", "prazo_garantia", "tipo_garantia",
  "estoque_minimo", "estoque_maximo", "estoque_ressuprimento",
  "area", "escaninho", "tipo", "tipo_peca",
  "custo_inventario", "custo_reposicao", "desconto_compra", "percent_frete", "valor_frete",
  "margem_lucro", "margem_tabela", "pontuacao_a", "pontuacao_e", "pontuacao_v",
  "fornecedor", "autor", "serie",
] as const;

// Só leitura (nunca enviados no save) — mostrados na tela por contexto.
const READONLY_FIELDS = ["codigo_int", "qtd", "reservado", "reservado_os", "custo_medio", "data_cadastro"] as const;

export const emptyProdutoForm = (): ProdutoForm => {
  const f: ProdutoForm = {};
  for (const k of BOOL_FIELDS) f[k] = false;
  for (const k of TEXT_FIELDS) f[k] = "";
  for (const k of NUM_FIELDS) f[k] = "";
  for (const k of READONLY_FIELDS) f[k] = "";
  f.situacao = "A";
  return f;
};

export const toFloat = (s: string | boolean): number => {
  const v = parseFloat(String(s ?? "0").replace(",", "."));
  return Number.isFinite(v) ? v : 0;
};
const toIntOrNull = (s: string | boolean): number | null => {
  const v = parseInt(String(s ?? ""), 10);
  return Number.isFinite(v) ? v : null;
};

export type FornecedorItem = { fornecedor: number; sequencia?: number; nome?: string };
export type SimilarItem = { equivalente: string; descricao?: string };
export type SecundarioItem = { peca_secundaria: string; descricao?: string };
export type XmlVinculoItem = { codigo_xml: string; fornecedor_xml: number | null; nome?: string };
export type GradeItem = { equivalente: string; cor: string; tamanho: string; descricao?: string; p_venda?: number; qtd?: number };

export function useProdutoCompletoForm(codigoParam?: string) {
  const router = useRouter();
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingInit, setLoadingInit] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingCodigo, setEditingCodigo] = useState<string | null>(codigoParam || null);
  const [form, setForm] = useState<ProdutoForm>(emptyProdutoForm());

  const [fornecedores, setFornecedores] = useState<FornecedorItem[]>([]);
  const [similares, setSimilares] = useState<SimilarItem[]>([]);
  const [secundarios, setSecundarios] = useState<SecundarioItem[]>([]);
  const [xmlVinculos, setXmlVinculos] = useState<XmlVinculoItem[]>([]);
  const [protocoloSt, setProtocoloSt] = useState<string[]>([]);
  const [grade, setGrade] = useState<GradeItem[]>([]);

  const setField = useCallback((k: string, v: string | boolean) => {
    setForm((f) => ({ ...f, [k]: v }));
  }, []);

  const base = conn ? conn.api.replace(/\/+$/, "") : "";

  const aplicarDetalhe = useCallback((j: any) => {
    const d = j.produto || {};
    const next = emptyProdutoForm();
    for (const k of Object.keys(next)) {
      if (d[k] !== undefined && d[k] !== null) next[k] = typeof next[k] === "boolean" ? !!d[k] : String(d[k]);
    }
    setForm(next);
    setFornecedores(j.fornecedores || []);
    setSimilares(j.similares || []);
    setSecundarios(j.secundarios || []);
    setXmlVinculos(j.xml_vinculos || []);
    setProtocoloSt(j.protocolo_st || []);
    setGrade(j.grade || []);
  }, []);

  const carregarDetalhe = useCallback(
    async (c: Conn, codigo: string) => {
      try {
        const r = await fetch(
          `${c.api.replace(/\/+$/, "")}/api/produto-completo/${encodeURIComponent(codigo)}?servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`
        );
        const j = await r.json();
        if (!j?.success) {
          fb.showError(j?.message || "Produto não encontrado.");
          return;
        }
        aplicarDetalhe(j);
      } catch (e) {
        fb.showError(`Erro ao carregar: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
    [fb, aplicarDetalhe]
  );

  // Código Interno é editável (pedido do usuário, 2026-07-14) — ao perder o
  // foco com um valor preenchido, busca silenciosamente (sem toast de erro
  // se não encontrar — o campo pode ser só o início de digitação de um
  // código novo). Se encontrar, carrega o produto existente pra edição —
  // mesmo princípio de "buscarPorCgc" em useClienteForm.ts, adaptado pro
  // código interno do produto em vez de CPF/CNPJ.
  const buscarPorCodigoInt = useCallback(
    async (codigo: string): Promise<boolean> => {
      if (!conn) return false;
      const c = codigo.trim().toUpperCase();
      if (!c || c === editingCodigo) return false;
      try {
        const r = await fetch(
          `${base}/api/produto-completo/${encodeURIComponent(c)}?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`
        );
        const j = await r.json();
        if (j?.success) {
          setEditingCodigo(c);
          aplicarDetalhe(j);
          fb.showInfo(`Produto ${c} já cadastrado — carregado para edição.`);
          return true;
        }
        return false;
      } catch {
        return false;
      }
    },
    [conn, base, editingCodigo, aplicarDetalhe, fb]
  );

  useEffect(() => {
    (async () => {
      setLoadingInit(true);
      const session = await getSession();
      if (!session) {
        router.replace("/login");
        return;
      }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === session.empresa) || null;
      if (!c) {
        fb.showError("Conexão não encontrada.");
        setLoadingInit(false);
        return;
      }
      setConn(c);
      if (codigoParam) {
        await carregarDetalhe(c, codigoParam);
      }
      setLoadingInit(false);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    })();
  }, [codigoParam]);

  const buildDados = useCallback(() => {
    const dados: Record<string, unknown> = {};
    for (const k of BOOL_FIELDS) dados[k] = !!form[k];
    for (const k of TEXT_FIELDS) dados[k] = String(form[k] ?? "").trim();
    for (const k of NUM_FIELDS) {
      if (["tributacao_pis", "tributacao_cofins", "prazo_entrega", "prazo_fornecedor", "prazo_garantia",
           "tipo_garantia", "area", "escaninho", "tipo", "tipo_peca", "pontuacao_a", "pontuacao_e",
           "pontuacao_v", "fornecedor", "autor", "serie"].includes(k)) {
        dados[k] = toIntOrNull(form[k]);
      } else {
        dados[k] = toFloat(form[k]);
      }
    }
    dados.fornecedores = fornecedores.map((f) => ({ fornecedor: f.fornecedor, sequencia: f.sequencia || 0 }));
    dados.similares = similares.map((s) => ({ equivalente: s.equivalente }));
    dados.secundarios = secundarios.map((s) => ({ peca_secundaria: s.peca_secundaria }));
    dados.xml_vinculos = xmlVinculos.map((x) => ({ codigo_xml: x.codigo_xml, fornecedor_xml: x.fornecedor_xml }));
    dados.protocolo_st = protocoloSt;
    return dados;
  }, [form, fornecedores, similares, secundarios, xmlVinculos, protocoloSt]);

  const save = useCallback(async (): Promise<{ codigo_int: string; wasEditing: boolean } | null> => {
    if (!conn) return null;
    if (!String(form.descricao || "").trim()) {
      fb.showWarning("Defina a Descrição!");
      return null;
    }
    setSaving(true);
    try {
      const dados = buildDados();
      const wasEditing = !!editingCodigo;
      const r = await fetch(`${base}/api/produto-completo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo_int: editingCodigo, dados }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Produto gravado.");
        setEditingCodigo(j.codigo_int);
        setField("codigo_int", j.codigo_int);
        return { codigo_int: j.codigo_int, wasEditing };
      }
      fb.showError(j?.message || (Array.isArray(j?.detail) ? j.detail.map((d: any) => d.msg).join("; ") : "Falha ao gravar."));
      return null;
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      return null;
    } finally {
      setSaving(false);
    }
  }, [conn, base, form, editingCodigo, auditCtx, buildDados, fb, setField]);

  const deleteProduto = useCallback(async (): Promise<boolean> => {
    if (!conn || !editingCodigo) return false;
    try {
      const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(editingCodigo)}/excluir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Produto excluído.");
        return true;
      }
      fb.showError(j?.message || "Falha ao excluir.");
      return false;
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      return false;
    }
  }, [conn, base, editingCodigo, auditCtx, fb]);

  const criarItensGrade = useCallback(
    async (combinacoes: { cor: string; tamanho: string }[]): Promise<boolean> => {
      if (!conn || !editingCodigo) return false;
      try {
        const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(editingCodigo)}/grade`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, combinacoes }),
        });
        const j = await r.json();
        if (j?.success) {
          fb.showSuccess(j.message || "Grade gerada.");
          await carregarDetalhe(conn, editingCodigo);
          return true;
        }
        fb.showError(j?.message || "Falha ao gerar grade.");
        return false;
      } catch (e) {
        fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
        return false;
      }
    },
    [conn, base, editingCodigo, auditCtx, fb, carregarDetalhe]
  );

  const enviarSite = useCallback(
    async (idTrayExistente?: number): Promise<boolean> => {
      if (!conn || !editingCodigo) return false;
      try {
        const r = await fetch(`${base}/api/produto-completo/${encodeURIComponent(editingCodigo)}/enviar-site`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, id_tray_existente: idTrayExistente || null }),
        });
        const j = await r.json();
        if (j?.success) {
          fb.showSuccess(j.message || "Enviado à Tray.");
          return true;
        }
        fb.showError(j?.message || "Falha ao enviar à Tray.");
        return false;
      } catch (e) {
        fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
        return false;
      }
    },
    [conn, base, editingCodigo, auditCtx, fb]
  );

  return {
    conn, base, router, fb,
    loadingInit, saving, form, setField, editingCodigo,
    fornecedores, setFornecedores, similares, setSimilares, secundarios, setSecundarios,
    xmlVinculos, setXmlVinculos, protocoloSt, setProtocoloSt, grade,
    save, deleteProduto, criarItensGrade, enviarSite, carregarDetalhe, buscarPorCodigoInt,
  };
}

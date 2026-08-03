// Hook do Relatório de Pedidos: filtros, busca e análise (margem/descontos) por pedido.
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "expo-router";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet } from "@/src/utils/api";
import { SelectOption } from "@/src/components/SelectField";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";

export type PedidoItem = {
  pedido: number; data: string | null; situacao: string; situacao_label: string;
  total: number; cliente: string; vendedor_cod: number | null; vendedor_nome: string;
};
export type DescItem = {
  cod: number; tipo_label: string; descricao: string;
  percentual: number; valor_unitario: number; qtd: number; valor_total: number;
};
export type MargemTotais = { venda: number; desconto: number; custo: number; margem: number; margem_pct: number };
export type RelTotais = MargemTotais & { qtd_pedidos: number; produtos: number; servicos: number };
export type Analise = { loading: boolean; error?: string | null; margem?: MargemTotais | null; descontos?: DescItem[] };

function firstOfMonthISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function useRelatorioPedidos() {
  const router = useRouter();
  const feedback = useFeedback();
  const [conn, setConn] = useState<Connection | null>(null);
  const [dataIni, setDataIni] = useState<string | null>(firstOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [situacao, setSituacao] = useState<string>("");
  // Filtro "Projeto" — Gestor de Projetos Fase 4 (recurso extra, sem
  // equivalente no legado). Restringe aos Pedidos vinculados àquele
  // projeto (`projetos_documentos`).
  const [projeto, setProjeto] = useState<string>("");

  const [loading, setLoading] = useState(false);
  // `error` não é mais renderizado como banner inline (regra [GLOBAL]
  // "mensagens do sistema sempre no meio da tela" — pedido explícito do
  // usuário, 2026-07-18); a mensagem em si vai via `feedback.showError`
  // (toast centralizado), e este state só continua existindo pra suprimir
  // "Nenhum pedido..." quando a última busca falhou.
  const [error, setError] = useState<string | null>(null);
  const [pedidos, setPedidos] = useState<PedidoItem[]>([]);
  const [totais, setTotais] = useState<RelTotais | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [analises, setAnalises] = useState<Record<number, Analise>>({});

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { setError("Conexão não encontrada."); feedback.showError("Conexão não encontrada."); return; }
      setConn(c);
      try {
        const j = await apiGet(c, "/api/funcionarios");
        const arr = Array.isArray(j) ? j : j?.items || [];
        setVendedorOpts(arr.map((f: { codigo: string | number; nome: string }) => ({
          value: String(f.codigo), label: (f.nome || "").trim() || `#${f.codigo}`,
        })));
      } catch {
        // sem lista de vendedores
      }
    })();
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { setError("Informe o período."); feedback.showError("Informe o período."); return; }
    setLoading(true); setError(null); setExpandedId(null); setAnalises({});
    try {
      const j = await apiGet(conn, "/api/relatorios/pedidos", {
        data_ini: dataIni, data_fim: dataFim,
        vendedor: vendedor ? String(vendedor) : undefined,
        situacao: situacao || undefined,
        projeto: projeto.trim() ? projeto.trim() : undefined,
      });
      if (!j?.success) {
        const msg = j?.message || "Falha ao gerar relatório.";
        setError(msg); feedback.showError(msg);
        setPedidos([]); setTotais(null);
      } else { setPedidos(Array.isArray(j.pedidos) ? j.pedidos : []); setTotais(j.totais || null); }
    } catch (e) {
      const msg = `Falha de rede: ${e instanceof Error ? e.message : String(e)}`;
      setError(msg); feedback.showError(msg);
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, vendedor, situacao, projeto, feedback.showError]);

  const loadAnalise = useCallback(async (pedido: number) => {
    if (!conn) return;
    setAnalises((prev) => ({ ...prev, [pedido]: { loading: true } }));
    try {
      const [mJ, dJ] = await Promise.all([
        apiGet(conn, "/api/relatorios/descontos-margem", { data_ini: "2000-01-01", data_fim: "2100-12-31", pedido }),
        apiGet(conn, `/api/pedidos/${pedido}/descontos`),
      ]);
      setAnalises((prev) => ({
        ...prev,
        [pedido]: {
          loading: false,
          margem: mJ?.success ? (mJ.totais as MargemTotais) : null,
          descontos: dJ?.success && Array.isArray(dJ.items) ? (dJ.items as DescItem[]) : [],
        },
      }));
    } catch (e) {
      setAnalises((prev) => ({ ...prev, [pedido]: { loading: false, error: e instanceof Error ? e.message : String(e) } }));
    }
  }, [conn]);

  const toggleExpand = useCallback((pedido: number) => {
    setExpandedId((cur) => {
      const next = cur === pedido ? null : pedido;
      if (next !== null && !analises[pedido]) loadAnalise(pedido);
      return next;
    });
  }, [analises, loadAnalise]);

  return {
    router,
    dataIni, setDataIni, dataFim, setDataFim,
    vendedorOpts, vendedor, setVendedor, situacao, setSituacao, projeto, setProjeto,
    loading, error, pedidos, totais, expandedId, analises,
    buscar, toggleExpand,
  };
}

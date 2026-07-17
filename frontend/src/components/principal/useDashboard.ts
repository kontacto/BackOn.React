// Hook do Dashboard (tela principal): sessão, filtros e carga dos totais/pedidos.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useFocusEffect, useRouter } from "expo-router";

import {
  Session, clearSession, getSession,
  getSituacaoFiltro as getSituacaoPref,
  setSituacaoFiltro as setSituacaoPref,
} from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { apiGet } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";

export type DashboardTotals = {
  pedidos: number; os: number; produtos: number; servicos: number; descontos: number; margem: number; margem_pct: number;
};
export type MovimentoItem = {
  tipo: "PED" | "OS"; doc: number; cliente: string; vendedor: string; valor: number;
  // Situação do registro (A/F/PG/C + rótulo já traduzido) — usado pra
  // mostrar um selo por linha quando o filtro "Todos" está ativo (sem
  // filtro nenhum, os registros da lista têm situações diferentes entre
  // si). Pedido explícito do usuário, 2026-07-16.
  situacao: string; situacaoLabel: string;
};

const ZERO: DashboardTotals = { pedidos: 0, os: 0, produtos: 0, servicos: 0, descontos: 0, margem: 0, margem_pct: 0 };

export function pickFirst(obj: Record<string, unknown> | null | undefined, keys: string[]): string | null {
  if (!obj) return null;
  for (const k of keys) {
    const v = obj[k];
    if (v !== undefined && v !== null && String(v).trim() !== "") return String(v);
  }
  return null;
}

export function useDashboard() {
  const router = useRouter();
  const { can, isManagerFuncao } = usePermissions();
  const [session, setSessionState] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  const [totais, setTotais] = useState<DashboardTotals>(ZERO);
  const [movimento, setMovimento] = useState<MovimentoItem[]>([]);
  const [dashLoading, setDashLoading] = useState(false);
  const [dashError, setDashError] = useState<string | null>(null);
  const [situacaoFiltro, setSituacaoFiltro] = useState<string>("");
  const [fantasia, setFantasia] = useState<string | null>(null);

  const handleSituacao = useCallback((value: string) => {
    setSituacaoFiltro(value);
    setSituacaoPref(value);
  }, []);

  // "Ver todos os vendedores": cod_funcao 01/02 ou KONTACTO. Os demais veem só os próprios.
  const canSeeAll = isManagerFuncao;
  const showTotais = useMemo(() => can("GERENCIAL.TOTAIS"), [can]);
  const showMargem = useMemo(() => can("GERENCIAL.MARGEM"), [can]);
  const showDescontos = useMemo(() => can("GERENCIAL.DESCONTOS"), [can]);

  const loadSession = useCallback(async () => {
    setLoading(true);
    const s = await getSession();
    if (!s) { router.replace("/login"); return; }
    setSessionState(s);
    setLoading(false);
  }, [router]);

  const connFor = useCallback(async (s: Session) => {
    const conns = await listConnections();
    return conns.find((c) => c.empresa === s.empresa) || null;
  }, []);

  const loadEmpresa = useCallback(async (s: Session) => {
    try {
      const conn = await connFor(s);
      if (!conn) return;
      const j = await apiGet(conn, "/api/controle/empresa");
      if (j?.success) setFantasia(j.fantasia || j.rz_social || null);
    } catch {
      // silencioso
    }
  }, [connFor]);

  useEffect(() => {
    (async () => {
      const saved = await getSituacaoPref();
      if (saved) setSituacaoFiltro(saved);
    })();
  }, []);

  const loadDashboard = useCallback(
    async (s: Session, situacaoOverride?: string) => {
      setDashLoading(true);
      setDashError(null);
      try {
        const conn = await connFor(s);
        if (!conn) { setDashError("Conexão não encontrada."); return; }
        let vendedorParam: string;
        if (canSeeAll) {
          vendedorParam = "all";
        } else {
          const own = s.funcionario?.codigo_int;
          if (own === undefined || own === null) { setDashError("Vendedor não identificado na sessão."); return; }
          vendedorParam = String(own);
        }
        const sit = situacaoOverride !== undefined ? situacaoOverride : situacaoFiltro;
        const j = await apiGet(conn, "/api/dashboard/me", { vendedor: vendedorParam, situacao: sit || undefined });
        if (!j?.success) setDashError(j?.message || "Não foi possível obter os totais.");
        setTotais(j?.totais || ZERO);
        const rawMov = Array.isArray(j?.movimento) ? j.movimento : (Array.isArray(j?.pedidos) ? j.pedidos : []);
        const normalizedMov: MovimentoItem[] = rawMov.map((m: any) => {
          const tipoRaw = String(m?.tipo ?? "PED").toUpperCase();
          const tipo = tipoRaw === "OS" ? "OS" : "PED";
          const doc = Number(m?.doc ?? m?.documento ?? m?.pedido ?? m?.os ?? 0);
          const cliente = String(m?.cliente ?? m?.nome_cliente ?? "").trim();
          const vendedor = String(
            // `vendedor_nome` é o campo real mandado por
            // `relatorios_service._dashboard_sync` — faltava aqui, por
            // isso a coluna Vendedor sempre aparecia vazia (bug achado
            // 2026-07-16, a pedido do usuário: "apresentar o vendedor de
            // cada pré-venda").
            m?.vendedor_nome ??
            m?.funcionario?.nome_guerra ??
            m?.funcionario_nome_guerra ??
            m?.vendedor ??
            m?.nome_guerra ??
            m?.funcionario?.nome ??
            ""
          ).trim();
          const valor = Number(m?.valor ?? m?.total ?? 0);
          const situacao = String(m?.situacao ?? "").trim().toUpperCase();
          const situacaoLabel = String(m?.situacao_label ?? situacao).trim();
          return { tipo, doc, cliente, vendedor, valor, situacao, situacaoLabel };
        });
        setMovimento(normalizedMov);
      } catch (e) {
        setDashError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setDashLoading(false);
      }
    },
    [canSeeAll, connFor, situacaoFiltro]
  );

  useFocusEffect(useCallback(() => { loadSession(); }, [loadSession]));
  useEffect(() => { loadSession(); }, [loadSession]);

  useEffect(() => {
    if (session) {
      loadDashboard(session);
      loadEmpresa(session);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, canSeeAll, loadDashboard, loadEmpresa]);

  useEffect(() => {
    if (session) loadDashboard(session, situacaoFiltro);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [situacaoFiltro]);

  const handleLogout = useCallback(async () => {
    await clearSession();
    router.replace("/login");
  }, [router]);

  const displayName = useMemo(() => {
    if (!session) return "";
    const funcName = pickFirst(session.funcionario, ["nome", "nome_guerra", "nome_completo", "apelido"]);
    const usrName = pickFirst(session.usuario, ["nome", "usuario"]);
    return funcName || usrName || "";
  }, [session]);

  const nomeGuerra = useMemo(() => pickFirst(session?.funcionario, ["nome_guerra"]) || null, [session]);
  const totalMovimento = useMemo(() => movimento.reduce((s, p) => s + (p.valor || 0), 0), [movimento]);
  const classe = useMemo(() => pickFirst(session?.usuario, ["classe_descricao", "classe_label", "classe"]) || null, [session]);

  return {
    session, loading, totais, movimento, dashLoading, dashError,
    situacaoFiltro, handleSituacao,
    fantasia, canSeeAll, showTotais, showMargem, showDescontos,
    handleLogout, displayName, nomeGuerra, totalMovimento, classe,
  };
}

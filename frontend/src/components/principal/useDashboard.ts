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
import { SelectOption } from "@/src/components/SelectField";

export type DashboardTotals = {
  pedidos: number; produtos: number; servicos: number; descontos: number; margem: number; margem_pct: number;
};
export type DashboardPedido = { pedido: number; cliente: string; valor: number };

const ZERO: DashboardTotals = { pedidos: 0, produtos: 0, servicos: 0, descontos: 0, margem: 0, margem_pct: 0 };

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
  const { can } = usePermissions();
  const [session, setSessionState] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  const [totais, setTotais] = useState<DashboardTotals>(ZERO);
  const [pedidos, setPedidos] = useState<DashboardPedido[]>([]);
  const [dashLoading, setDashLoading] = useState(false);
  const [dashError, setDashError] = useState<string | null>(null);
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedorFiltro, setVendedorFiltro] = useState<string | number | null>(null);
  const [situacaoFiltro, setSituacaoFiltro] = useState<string>("");
  const [fantasia, setFantasia] = useState<string | null>(null);

  const handleSituacao = useCallback((value: string) => {
    setSituacaoFiltro(value);
    setSituacaoPref(value);
  }, []);

  const canSeeAll = useMemo(() => can("GERENCIAL.TODOS_VEND"), [can]);
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

  const loadVendedores = useCallback(async (s: Session) => {
    try {
      const conn = await connFor(s);
      if (!conn) return;
      const j = await apiGet(conn, "/api/funcionarios");
      const items: { codigo: number; nome: string; nome_guerra: string }[] = Array.isArray(j?.items) ? j.items : [];
      setVendedorOpts(items.map((f) => ({
        value: f.codigo,
        label: f.nome || f.nome_guerra || `#${f.codigo}`,
        sub: f.nome_guerra && f.nome_guerra !== f.nome ? `@${f.nome_guerra}` : undefined,
      })));
    } catch {
      // silencioso
    }
  }, [connFor]);

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
    async (s: Session, vendedorOverride?: string | number | null, situacaoOverride?: string) => {
      setDashLoading(true);
      setDashError(null);
      try {
        const conn = await connFor(s);
        if (!conn) { setDashError("Conexão não encontrada."); return; }
        let vendedorParam: string;
        if (canSeeAll) {
          vendedorParam = vendedorOverride === undefined || vendedorOverride === null ? "all" : String(vendedorOverride);
        } else {
          const own = s.funcionario?.codigo_int;
          if (own === undefined || own === null) { setDashError("Vendedor não identificado na sessão."); return; }
          vendedorParam = String(own);
        }
        const sit = situacaoOverride !== undefined ? situacaoOverride : situacaoFiltro;
        const j = await apiGet(conn, "/api/dashboard/me", { vendedor: vendedorParam, situacao: sit || undefined });
        if (!j?.success) setDashError(j?.message || "Não foi possível obter os totais.");
        setTotais(j?.totais || ZERO);
        setPedidos(Array.isArray(j?.pedidos) ? j.pedidos : []);
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
      loadDashboard(session, vendedorFiltro);
      loadEmpresa(session);
      if (canSeeAll) loadVendedores(session);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, canSeeAll, loadDashboard, loadVendedores, loadEmpresa]);

  useEffect(() => {
    if (session) loadDashboard(session, vendedorFiltro, situacaoFiltro);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vendedorFiltro, situacaoFiltro]);

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
  const totalPedidos = useMemo(() => pedidos.reduce((s, p) => s + (p.valor || 0), 0), [pedidos]);
  const classe = useMemo(() => pickFirst(session?.usuario, ["classe_descricao", "classe_label", "classe"]) || null, [session]);

  return {
    session, loading, totais, pedidos, dashLoading, dashError,
    vendedorOpts, vendedorFiltro, setVendedorFiltro, situacaoFiltro, handleSituacao,
    fantasia, canSeeAll, showTotais, showMargem, showDescontos,
    handleLogout, displayName, nomeGuerra, totalPedidos, classe,
  };
}

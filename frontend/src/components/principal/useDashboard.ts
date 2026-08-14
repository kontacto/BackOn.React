// Hook do Dashboard (tela principal): sessão, filtros e carga dos totais/pedidos.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFocusEffect, useRouter } from "expo-router";

import {
  Session, clearSession, getSession,
  getSituacaoFiltro as getSituacaoPref,
  setSituacaoFiltro as setSituacaoPref,
} from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { apiGet, apiSend } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { ResumoProjetos } from "@/src/components/principal/ProjetosResumoCard";

export type DashboardTotals = {
  pedidos: number; os: number;
  // Vendas lançadas 100% dentro do Checkout, sem Pedido/O.S. por trás —
  // pedido explícito do usuário, 2026-08-06 ("incluir vendas direto da
  // tela de vendas tb"). Opcional/`?? 0` no consumo — backends antigos (ou
  // ainda não reiniciados) não mandam essa chave.
  checkout?: number;
  produtos: number; servicos: number; descontos: number; margem: number; margem_pct: number;
};
export type MovimentoItem = {
  tipo: "PED" | "OS" | "CHECKOUT"; doc: number; cliente: string; vendedor: string; valor: number;
  // Situação do registro (A/F/PG/C + rótulo já traduzido) — usado pra
  // mostrar um selo por linha quando o filtro "Todos" está ativo (sem
  // filtro nenhum, os registros da lista têm situações diferentes entre
  // si). Pedido explícito do usuário, 2026-07-16.
  situacao: string; situacaoLabel: string;
};

const ZERO: DashboardTotals = { pedidos: 0, os: 0, checkout: 0, produtos: 0, servicos: 0, descontos: 0, margem: 0, margem_pct: 0 };

// Resumo dos 3 alertas de estoque (Controle do Sistema > aba Diversos) —
// card na Tela Principal, só pra Gerente/Supervisor/Master. `ativo=false`
// quando o módulo Curva ABC/Compras está desligado (card nem aparece
// nesse caso). Cada tipo é `null` quando o toggle correspondente está
// desligado em Controle do Sistema, ou `{count}` quando ligado. Pedido
// explícito do usuário, 2026-07-20.
export type ResumoAlertasEstoque = {
  ativo: boolean;
  minimo: { count: number } | null;
  ressuprimento: { count: number } | null;
  zerado: { count: number } | null;
  // "Modo Didático" — true quando a Curva ABC/Estoques não é gerada ou
  // reprocessada há mais de 6 meses (ou nunca foi rodada) — os valores de
  // estoque mínimo/ressuprimento por trás destes alertas podem estar
  // desatualizados. Pedido explícito do usuário, 2026-07-20.
  curva_abc_desatualizada: boolean;
  curva_abc_ultima_geracao: string | null;
  // Quando o cache compartilhado (`alertas_estoque_cache`, back-end) foi
  // gravado pela última vez — igual pra TODOS os usuários com acesso ao
  // card, não por sessão/navegador. Pedido explícito do usuário,
  // 2026-07-21 ("guarde o último resultado para todos os usuários").
  atualizado_em: string | null;
};

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
  const { can, isManagerFuncao, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const [session, setSessionState] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  const feedback = useFeedback();
  const [totais, setTotais] = useState<DashboardTotals>(ZERO);
  const [movimento, setMovimento] = useState<MovimentoItem[]>([]);
  const [dashLoading, setDashLoading] = useState(false);
  const [situacaoFiltro, setSituacaoFiltro] = useState<string>("");
  const [fantasia, setFantasia] = useState<string | null>(null);
  const [alertasEstoque, setAlertasEstoque] = useState<ResumoAlertasEstoque | null>(null);
  // Quando os alertas foram buscados pela última vez — mostrado sempre,
  // mesmo desatualizado (o dado ainda é um alerta válido, só não é ao
  // vivo). Pedido explícito do usuário, 2026-07-21.
  const [alertasAtualizadoEm, setAlertasAtualizadoEm] = useState<Date | null>(null);
  const [alertasCarregando, setAlertasCarregando] = useState(false);
  // Card "Projetos" — Gestor de Projetos Fase 4 (recurso extra,
  // 2026-08-02, confirmado explicitamente pelo usuário). Diferente do
  // card de estoque acima, não usa cache compartilhado/"1x por sessão" —
  // a consulta é barata, recarrega junto com o resto do dashboard.
  const [resumoProjetos, setResumoProjetos] = useState<ResumoProjetos | null>(null);
  // Cada consulta de alertas abre conexão nova com o banco, e a primeira
  // query numa conexão nova custa vários segundos (medido: ~7s, mesmo pra
  // uma tabela pequena — custo da conexão em si, não da query). Recarregar
  // sozinho em todo foco da Tela Principal multiplicava esse custo a cada
  // navegação. Agora só carrega automaticamente UMA vez por sessão do app
  // — atualização seguinte é sempre por ação do usuário (botão "Atualizar"
  // no card). Pedido explícito do usuário, 2026-07-21 ("retire o
  // recarregamento automático").
  const alertasAutoCarregadoRef = useRef(false);

  // Fase 3 do Inventário (2026-07-23) — ver definição da função logo
  // abaixo de `connFor` (precisa dela já declarada).
  const rotinasAutomaticasInventarioRef = useRef(false);

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

  // Fase 3 do Inventário (2026-07-23) — dispara as rotinas automáticas do
  // legado (snapshot mensal + diário contábil, ver
  // backend/services/inventario_service.py::executar_rotinas_automaticas)
  // uma vez por sessão do app, silenciosamente — "primeiro acesso do dia/
  // mês de QUALQUER usuário" (decisão já registrada em PENDENCIAS.md >
  // Inventário, opção (a): sem Tarefa Agendada nem worker separado). O
  // endpoint já é idempotente sozinho (reverifica se já rodou antes de
  // fazer qualquer coisa), o ref acima só evita repetir a chamada de rede
  // a cada foco da Tela Principal dentro da mesma sessão do app.
  const dispararRotinasAutomaticasInventario = useCallback(async (s: Session) => {
    try {
      const conn = await connFor(s);
      if (!conn) return;
      await apiSend(conn, "/api/inventario/rotinas-automaticas", "POST", {});
    } catch {
      // silencioso — não é uma ação do usuário, não deve gerar toast nenhum
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

  // Card de alertas de estoque — só carrega pra Gerente/Supervisor/Master
  // (`isManagerFuncao`) E com a permissão `ALERTAS_ESTOQUE.ABRIR` concedida
  // (catálogo, menu Compra) — as duas precisam estar de acordo, mesmo
  // princípio de reforço já usado no gating por módulo ativo. Evita a
  // chamada extra pros demais funcionários/grupos, que nunca veem o card.
  // Pedido explícito do usuário, 2026-07-20 (card) e mesma sessão
  // (permissão adicionada depois, a pedido do usuário, vendo a árvore de
  // permissões do menu Compra).
  const podeVerAlertasEstoque = isManagerFuncao && can("ALERTAS_ESTOQUE.ABRIR");
  // Botão "Atualizar" só aparece com a permissão própria concedida (grava
  // no cache compartilhado, visto por todo mundo — reforçada também no
  // backend). Quem só tem ABRIR vê o card, mas não recalcula.
  const podeAtualizarAlertasEstoque = podeVerAlertasEstoque && can("ALERTAS_ESTOQUE.ATUALIZAR");
  // GET só lê o cache compartilhado no back-end (`alertas_estoque_cache`)
  // — não recalcula nada, então `atualizado_em` vem do servidor (igual pra
  // todo mundo com acesso ao card), não de `new Date()` local. Pedido
  // explícito do usuário, 2026-07-21 ("guarde o último resultado para
  // todos os usuários... teriam os resultados da última atualização").
  const loadAlertasEstoque = useCallback(async (s: Session) => {
    if (!podeVerAlertasEstoque) { setAlertasEstoque(null); return; }
    setAlertasCarregando(true);
    try {
      const conn = await connFor(s);
      if (!conn) return;
      const j = await apiGet(conn, "/api/gestao-compras/alertas-estoque");
      if (j?.success) {
        setAlertasEstoque(j as ResumoAlertasEstoque);
        setAlertasAtualizadoEm(j.atualizado_em ? new Date(j.atualizado_em) : null);
      }
    } catch {
      // silencioso — card mantém o último valor carregado se a chamada falhar
    } finally {
      setAlertasCarregando(false);
    }
  }, [connFor, podeVerAlertasEstoque]);

  // Atualização manual (botão "Atualizar" no card) — chama o endpoint que
  // RECALCULA de verdade e grava no cache compartilhado, pra todo mundo
  // com acesso ao card ver o mesmo resultado (não uma busca isolada por
  // sessão/navegador). Diferente do GET automático acima, mostra erro
  // visível se falhar (ação explícita do usuário, não uma carga silenciosa
  // de fundo) e é gated pela permissão `ALERTAS_ESTOQUE.ATUALIZAR` (também
  // reforçada no backend).
  // Mesmo gating de "manager" do card de estoque, mais o módulo
  // `gestor_projetos` ligado e a permissão `PROJETOS.ABRIR` (reaproveitada
  // — nenhuma permissão nova, o card só reflete o que a tela de Projetos
  // já mostraria pra esse usuário).
  const podeVerResumoProjetos = isManagerFuncao && moduleOn("gestor_projetos") && can("PROJETOS.ABRIR");
  const loadResumoProjetos = useCallback(async (s: Session) => {
    if (!podeVerResumoProjetos) { setResumoProjetos(null); return; }
    try {
      const conn = await connFor(s);
      if (!conn) return;
      const j = await apiGet(conn, "/api/projetos-resumo");
      if (j?.success) setResumoProjetos(j as ResumoProjetos);
    } catch {
      // silencioso — card só some se não carregar, não trava o resto do dashboard
    }
  }, [connFor, podeVerResumoProjetos]);

  const reloadAlertasEstoque = useCallback(async () => {
    if (!session || !podeVerAlertasEstoque) return;
    setAlertasCarregando(true);
    try {
      const conn = await connFor(session);
      if (!conn) return;
      const j = await apiSend(conn, "/api/gestao-compras/alertas-estoque/atualizar", "POST", {
        master: isMaster, ...auditCtx,
      });
      if (j?.success) {
        setAlertasEstoque(j as ResumoAlertasEstoque);
        setAlertasAtualizadoEm(j.atualizado_em ? new Date(j.atualizado_em) : new Date());
      } else {
        feedback.showError(j?.message || "Não foi possível atualizar os alertas de estoque.");
      }
    } catch {
      feedback.showError("Falha de rede ao atualizar os alertas de estoque.");
    } finally {
      setAlertasCarregando(false);
    }
  }, [session, podeVerAlertasEstoque, connFor, isMaster, auditCtx, feedback]);

  useEffect(() => {
    (async () => {
      const saved = await getSituacaoPref();
      if (saved) setSituacaoFiltro(saved);
    })();
  }, []);

  const loadDashboard = useCallback(
    async (s: Session, situacaoOverride?: string) => {
      setDashLoading(true);
      try {
        const conn = await connFor(s);
        if (!conn) { feedback.showError("Conexão não encontrada."); return; }
        let vendedorParam: string;
        if (canSeeAll) {
          vendedorParam = "all";
        } else {
          const own = s.funcionario?.codigo_int;
          if (own === undefined || own === null) { feedback.showError("Vendedor não identificado na sessão."); return; }
          vendedorParam = String(own);
        }
        const sit = situacaoOverride !== undefined ? situacaoOverride : situacaoFiltro;
        const j = await apiGet(conn, "/api/dashboard/me", { vendedor: vendedorParam, situacao: sit || undefined });
        if (!j?.success) feedback.showError(j?.message || "Não foi possível obter os totais.");
        setTotais(j?.totais || ZERO);
        const rawMov = Array.isArray(j?.movimento) ? j.movimento : (Array.isArray(j?.pedidos) ? j.pedidos : []);
        const normalizedMov: MovimentoItem[] = rawMov.map((m: any) => {
          const tipoRaw = String(m?.tipo ?? "PED").toUpperCase();
          const tipo = tipoRaw === "OS" ? "OS" : tipoRaw === "CHECKOUT" ? "CHECKOUT" : "PED";
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
        feedback.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setDashLoading(false);
      }
    },
    // `feedback.showError` é referencialmente estável entre renders do
    // FeedbackProvider (useCallback com deps fixas lá dentro) mesmo que o
    // objeto `feedback` inteiro não seja — usar só o método específico na
    // dependência evita recriar `loadDashboard` (e disparar o
    // `useEffect([session, ..., loadDashboard])` abaixo em loop) toda vez
    // que QUALQUER toast do app inteiro dispara.
    [canSeeAll, connFor, situacaoFiltro, feedback.showError]
  );

  useFocusEffect(useCallback(() => { loadSession(); }, [loadSession]));
  useEffect(() => { loadSession(); }, [loadSession]);

  useEffect(() => {
    if (session) {
      loadDashboard(session);
      loadEmpresa(session);
      if (!alertasAutoCarregadoRef.current) {
        alertasAutoCarregadoRef.current = true;
        loadAlertasEstoque(session);
      }
      if (!rotinasAutomaticasInventarioRef.current) {
        rotinasAutomaticasInventarioRef.current = true;
        dispararRotinasAutomaticasInventario(session);
      }
      loadResumoProjetos(session);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, canSeeAll, loadDashboard, loadEmpresa, loadAlertasEstoque, loadResumoProjetos, dispararRotinasAutomaticasInventario]);

  useEffect(() => {
    if (session) loadDashboard(session, situacaoFiltro);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [situacaoFiltro]);

  // Atualização automática do "Movimento de Hoje" — pedido explícito do
  // usuário, 2026-08-11 ("o painel não está atualizando a venda de
  // checkout"). Vendas fechadas no KPDV (app desktop separado) não têm
  // nenhum canal de push/websocket pra este painel web — sem isso, o
  // usuário só via a venda nova ao sair e voltar pra tela (useFocusEffect).
  // Poll simples a cada 30s enquanto a sessão está ativa, mesmo padrão já
  // usado noutros painéis do projeto (sem infraestrutura de socket).
  useEffect(() => {
    if (!session) return;
    const id = setInterval(() => loadDashboard(session, situacaoFiltro), 30000);
    return () => clearInterval(id);
  }, [session, situacaoFiltro, loadDashboard]);

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
    session, loading, totais, movimento, dashLoading,
    situacaoFiltro, handleSituacao,
    fantasia, canSeeAll, showTotais, showMargem, showDescontos,
    handleLogout, displayName, nomeGuerra, totalMovimento, classe,
    alertasEstoque, alertasAtualizadoEm, alertasCarregando, reloadAlertasEstoque,
    podeAtualizarAlertasEstoque,
    resumoProjetos,
  };
}

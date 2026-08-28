// Menu vertical persistente (web). Renderizado uma única vez no layout raiz
// (`app/_layout.tsx`), ao lado do Stack — não dentro do navigator de Tabs —
// para ficar visível em QUALQUER tela do sistema, não só nas 7 abas
// principais. Objetivo: permitir voltar para "Início" (ou qualquer outra
// aba) direto de qualquer lugar, sem precisar navegar pra trás tela por
// tela. Pedido do usuário 2026-07-13.
//
// O Tabs em `(tabs)/_layout.tsx` continua controlando a navegação entre as
// 7 abas (principal/cadastros/transacoes/financeiro/posto/configuracoes/
// relatorios) — só a barra visual dele é escondida no web (`tabBarStyle:
// display:none`) pra não duplicar este componente.
import { useState } from "react";
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter, usePathname } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAtualizacaoPendente } from "@/src/hooks/useAtualizacaoPendente";
import { useAplicarAtualizacao } from "@/src/hooks/useAplicarAtualizacao";
import { useTransferenciaPendenteCount } from "@/src/hooks/useTransferenciaPendenteCount";
import { useSessionWelcome } from "@/src/hooks/useSessionWelcome";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";

// Preferência de menu recolhido (só ícones) — lembrada no navegador entre
// sessões, mesmo padrão de outras preferências de UI já persistidas no
// app (ex.: pedidosFilters.ts), mas aqui é global (não por empresa+banco,
// é só uma preferência visual de janela). `window.localStorage` direto é
// seguro aqui: este componente só é montado com `Platform.OS === "web"`
// (ver app/_layout.tsx). Pedido explícito do usuário, 2026-07-18.
const COLLAPSE_KEY = "sidebar_collapsed";
const SIDEBAR_WIDTH_EXPANDED = 188;
const SIDEBAR_WIDTH_COLLAPSED = 56;

type NavItem = {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  href: string;
  visible: boolean;
  badge?: boolean;
};

// "Pendências do Sistema" — grupo separado do menu de navegação normal
// (`items` acima), visualmente destacado no final da sidebar (borda
// superior + rótulo). Regra `[GLOBAL]` nova, 2026-08-28, user-directed:
// só entram aqui botões de ação DIRETA (disparam algo, não navegam pra
// uma tela) que só aparecem quando existe algo pendente precisando de
// INTERVENÇÃO do usuário — nunca um atalho permanente. "Atualizar
// Sistema" é o primeiro; mais itens previstos (ex.: Transferência
// disponível do Contas a Pagar/Receber, Transferência pro Fluxo de
// Caixa) — esses futuros, gateados por permissão normal (`can(...)`),
// não pelo critério especial do primeiro. O grupo inteiro some quando
// nenhum item está `visible` (nunca mostra o rótulo "vazio"). Ao
// adicionar um item novo, seguir este mesmo formato (`ShortcutItem`) em
// vez de inventar outro padrão.
type ShortcutItem = {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  visible: boolean;
  loading?: boolean;
  onPress: () => void;
};

// Telas fora do grupo (tabs) mapeadas pra aba "lógica" a que pertencem, só
// pra manter o item certo destacado quando o usuário está numa tela de
// detalhe/CRUD (que não é, ela mesma, uma rota de aba). Não precisa ser
// exaustivo — uma tela não mapeada aqui simplesmente não acende nenhum
// item, o menu continua funcional do mesmo jeito.
const DETAIL_TO_TAB: Record<string, string> = {
  "/clientes": "/cadastros",
  "/cliente-completo": "/cadastros",
  "/cliente-form": "/cadastros",
  "/fornecedores": "/cadastros",
  "/servicos": "/cadastros",
  "/produtos": "/cadastros",
  "/produtos-niveis": "/cadastros",
  "/contatos": "/cadastros",
  "/equipamentos": "/cadastros",
  "/entrada-saida-caixa": "/cadastros",
  "/telemarketing": "/cadastros",
  "/funcionarios": "/cadastros",
  "/funcionario-completo": "/cadastros",
  "/veiculos": "/cadastros",
  "/tabelas-auxiliares": "/cadastros",
  "/notas-fiscais": "/cadastros",
  "/pedido-form": "/transacoes",
  "/os-form": "/transacoes",
  "/pedidos": "/transacoes",
  "/os": "/transacoes",
  "/contas-pagar": "/financeiro",
  "/contas-receber": "/financeiro",
  "/fluxo-caixa": "/financeiro",
  "/plano-contas": "/financeiro",
  "/centro-custo": "/financeiro",
  "/controle-sistema": "/configuracoes",
  "/permissoes": "/configuracoes",
  "/modulos-recursos": "/configuracoes",
  "/grupo-usuario": "/configuracoes",
  "/log-auditoria": "/configuracoes",
  "/whatsapp-config": "/configuracoes",
  "/servico-sistema": "/configuracoes",
  "/mensagens": "/configuracoes",
  "/mensagens-pdv": "/configuracoes",
  "/relatorio-descontos": "/relatorios",
  "/relatorio-margem-lucro": "/relatorios",
  "/relatorio-os-descontos": "/relatorios",
  "/relatorio-os": "/relatorios",
  "/relatorio-pedidos": "/relatorios",
};

const TABELAS_AUXILIARES_ROTAS = [
  "/area", "/area-atuacao", "/marcas", "/modelos", "/segmentos",
  "/regioes", "/rotas", "/forma-pagamento", "/situacao", "/tamanho",
  "/cores", "/origem", "/tipo-cliente", "/tipo-doc", "/tipo-mov",
  "/tipo-mov-mensagens", "/tipo-os", "/tipo-os-prod", "/tipo-peca",
  "/tipo-servico", "/tributacao", "/unidade-medida", "/executor-padrao",
  "/status-os", "/cfop", "/cfop-pis-cofins", "/grupo-pis-cofins",
  "/grupo-mercadologico", "/icms", "/taxas", "/num-serie",
];
for (const rota of TABELAS_AUXILIARES_ROTAS) DETAIL_TO_TAB[rota] = "/cadastros";

const POSTO_ROTAS = [
  "/posto-meta", "/posto-ilhas", "/posto-combustiveis", "/posto-tanques",
  "/posto-estoque", "/posto-custo", "/posto-bombas", "/posto-tanque-estoque",
  "/posto-tanque-nf", "/posto-mov-encerrantes", "/posto-fechamento-turno",
  "/posto-reabertura-turno", "/posto-afericoes", "/posto-placeholder",
];
for (const rota of POSTO_ROTAS) DETAIL_TO_TAB[rota] = "/posto-combustivel";

DETAIL_TO_TAB["/cilindro-cadastro"] = "/cilindros";

// Rotas pré-autenticação — o menu não faz sentido aqui (usuário ainda não
// escolheu conexão/logou).
const HIDDEN_ON: string[] = ["/", "/login", "/connections", "/perfil-usuario"];

export default function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { can, moduleOn, isManagerFuncao } = usePermissions();
  const feedback = useFeedback();
  const atualizacao = useAtualizacaoPendente();
  const { aplicando, aplicar } = useAplicarAtualizacao();
  const transferenciaPendenteCount = useTransferenciaPendenteCount();
  const welcome = useSessionWelcome();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch {
      return false;
    }
  });
  // Tooltip com o rótulo — só faz sentido com o menu recolhido (label
  // escondido); um só hover de cada vez, mesmo padrão já usado no card do
  // Painel de Pedidos. Pedido explícito do usuário, 2026-07-18.
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  if (HIDDEN_ON.includes(pathname)) return null;

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        // silencioso — preferência só não persiste, não impede o toggle
      }
      return next;
    });
  };

  // Item "Início" removido da lista (pedido explícito do usuário,
  // 2026-08-26, "retirar esse") — a própria logo/marca no topo já navega
  // pra `/principal` (ver Pressable acima), tornando um item de menu
  // dedicado redundante. `activeHref`/`DETAIL_TO_TAB` continuam
  // funcionando normalmente pras outras 7 rotas.
  const items: NavItem[] = [
    { key: "cadastros", label: "Cadastros", icon: "albums-outline", href: "/cadastros", visible: true },
    { key: "transacoes", label: "Transações", icon: "swap-horizontal-outline", href: "/transacoes", visible: true },
    { key: "financeiro", label: "Financeiro", icon: "cash-outline", href: "/financeiro", visible: true },
    { key: "posto-combustivel", label: "Posto", icon: "water-outline", href: "/posto-combustivel", visible: moduleOn("Posto") },
    { key: "cilindros", label: "Cilindros", icon: "flame-outline", href: "/cilindros", visible: moduleOn("Cilindro") },
    { key: "configuracoes", label: "Configurações", icon: "settings-outline", href: "/configuracoes", visible: true, badge: atualizacao.pendente },
    { key: "relatorios", label: "Relatórios", icon: "bar-chart-outline", href: "/relatorios", visible: true },
  ];

  // "Atualizar Sistema" — aplica a atualização pendente direto daqui, sem
  // entrar em Configurações > Serviço do Sistema (essa tela continua
  // existindo, restrita ao Master, só pra CONFIGURAR chave do
  // blob/pastas/intervalo).
  //
  // Regra de acesso do grupo inteiro `[GLOBAL]`, formalizada pelo
  // usuário 2026-08-28: TODO item de "Pendências do Sistema" (presente
  // ou futuro) é visível só quando `can("<TELA>.<ACAO>") ||
  // isManagerFuncao` — a pendência de uma tela nunca aparece pra quem
  // não teria acesso à própria tela (ex. do usuário: sem acesso a
  // Transferência Contas a Pagar/Receber, não recebe o aviso dela).
  // "Atualizar Sistema" não tem tela/permissão própria no catálogo
  // (`SERVICO_SISTEMA` não existe lá — visibilidade da tela completa já
  // é só-Master por decisão própria) — a fórmula degenera pra só
  // `isManagerFuncao` aqui, não porque a regra deste item é diferente.
  // "Os três magníficos" (apelido do usuário) = Supervisor, Gerente e
  // Kontacto (Master) = `isManagerFuncao` já existente
  // (`isMaster || cod_funcao 1 || cod_funcao 2`) — nenhum mecanismo novo
  // de permissão foi necessário. Ver CLAUDE.md > "Padrões de UI" > seção
  // 10 pro desenho completo do grupo.
  const handleAtualizarSistema = () => {
    if (aplicando) return;
    feedback.showConfirm(
      "Aplicar a atualização pendente agora? O backend vai reiniciar em instantes — qualquer pessoa usando o sistema perde a conexão por alguns segundos.",
      async () => {
        const r = await aplicar();
        if (r.success) {
          feedback.showSuccess(r.message || "Atualização aplicada — o sistema está reiniciando.", undefined, 5000);
        } else {
          feedback.showError(r.message || "Falha ao aplicar a atualização.");
        }
      },
      { title: "Atualizar Sistema", confirmText: "Aplicar agora" },
    );
  };

  const shortcuts: ShortcutItem[] = [
    {
      key: "atualizar-sistema", label: "Atualizar Sistema", icon: "cloud-download-outline",
      // Só canal Produção — Homologação aplica exclusivamente pela tela
      // completa (Serviço do Sistema > Atualização), nunca por aqui. Ver
      // CLAUDE.md > "Padrões de UI" > seção 13.
      visible: atualizacao.pendente && atualizacao.canal === "P" && isManagerFuncao,
      loading: aplicando, onPress: handleAtualizarSistema,
    },
    // 2º item do grupo — navega pra tela de revisão (não é ação de 1
    // clique como "Atualizar Sistema": transferir exige o usuário
    // marcar quais Notas Fiscais/Comandas entram, então o atalho leva
    // até `/transferencia-contas` em vez de disparar algo direto daqui.
    // Mesma fórmula de acesso `[GLOBAL]` da seção 10 do CLAUDE.md:
    // `can("TRANSF_CONTAS.ABRIR") || isManagerFuncao`.
    {
      key: "transferencia-pendente", label: `Transferência Pendente (${transferenciaPendenteCount})`, icon: "swap-horizontal-outline",
      visible: transferenciaPendenteCount > 0 && (can("TRANSF_CONTAS.ABRIR") || isManagerFuncao),
      onPress: () => router.push("/transferencia-contas" as never),
    },
  ];

  const activeHref = DETAIL_TO_TAB[pathname] ?? pathname;

  return (
    <View
      style={[styles.sidebar, { width: collapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH_EXPANDED }]}
      testID="app-sidebar"
    >
      {/* Logo — único lugar do app que mostra a marca agora (retirado do
          cabeçalho de cada tela, pedido explícito do usuário 2026-07-30).
          Telas sem sidebar (`HIDDEN_ON` acima — splash/login/connections/
          perfil-usuario) mantêm seu próprio logo local, já que não têm
          este menu pra herdar dele. Versão colorida (fundo claro) — a
          `kontacto-logo.png` usada nos cabeçalhos antigos é branca, feita
          pra fundo escuro, e ficaria invisível aqui. Expandido mostra a
          marca completa (~6:1, não cabe legível nos 56px do menu
          recolhido); recolhido troca pro ícone circular (`kontacto-icon.png`,
          mesmo "K" da marca, formato quadrado — cabe no menu estreito). */}
      {/* Logo também navega pra Início (mesma rota do item "Início" logo
          abaixo) — convenção padrão de app/web (clicar na marca volta pro
          começo), pedido explícito do usuário 2026-08-26. Tooltip "Início"
          só no modo recolhido, mesmo padrão já usado nos itens de menu. */}
      <Pressable
        onPress={() => router.push("/principal" as never)}
        onHoverIn={() => setHoveredKey("logo")}
        onHoverOut={() => setHoveredKey(null)}
        style={styles.logoWrap}
        testID="sidebar-logo-home"
      >
        {!collapsed ? (
          <Image
            source={require("../../assets/images/kontacto-logo-color.png")}
            style={styles.logo}
            resizeMode="contain"
            accessibilityLabel="Kontacto Sistemas — Início"
            testID="sidebar-logo"
          />
        ) : (
          <Image
            source={require("../../assets/images/kontacto-icon.png")}
            style={styles.logoIcon}
            resizeMode="contain"
            accessibilityLabel="Kontacto Sistemas — Início"
            testID="sidebar-logo-icon"
          />
        )}
        {collapsed && hoveredKey === "logo" ? (
          <View style={styles.tooltip} pointerEvents="none">
            <View style={styles.tooltipInner}>
              <Text style={styles.tooltipText}>Início</Text>
            </View>
          </View>
        ) : null}
      </Pressable>
      <Pressable
        onPress={toggleCollapsed}
        style={[styles.collapseBtn, collapsed && styles.collapseBtnCollapsed]}
        hitSlop={6}
        testID="sidebar-toggle-collapse"
      >
        <Ionicons name={collapsed ? "chevron-forward" : "chevron-back"} size={16} color={colors.muted} />
      </Pressable>
      {/* Card "Bem-vindo" (empresa/usuário/grupo/conexão) — pedido
          explícito do usuário, 2026-08-28: "não ficou bom na parte
          inferior. colocar na parte superior, logo acima do menu
          lateral" (1ª versão ficava no rodapé — revertido pra cá, logo
          abaixo do botão de recolher, acima de Cadastros/Transações/
          etc). */}
      {welcome ? (
        <Pressable
          onHoverIn={() => setHoveredKey("welcome")}
          onHoverOut={() => setHoveredKey(null)}
          style={[styles.welcomeCard, collapsed && styles.welcomeCardCollapsed]}
          testID="sidebar-welcome"
        >
          {welcome.logo ? (
            <Image source={{ uri: welcome.logo }} style={styles.welcomeAvatar} resizeMode="cover" testID="sidebar-welcome-logo" />
          ) : (
            <View style={[styles.welcomeAvatar, styles.welcomeAvatarFallback]}>
              <Ionicons name="person" size={16} color={colors.onBrandPrimary} />
            </View>
          )}
          {!collapsed ? (
            <View style={{ flex: 1, minWidth: 0 }}>
              {/* Codnome (nome_guerra) no lugar do nome completo, mesma
                  formatação — pedido explícito do usuário, 2026-08-28
                  ("exibir o codnome do usuário... no lugar do nome com a
                  mesma formatação"). Cai pro nome completo só quando não
                  há nome_guerra cadastrado. */}
              <Text style={styles.welcomeName} numberOfLines={1}>{welcome.nomeGuerra || welcome.displayName}</Text>
              {welcome.classe ? <Text style={styles.welcomeSub} numberOfLines={1}>Grupo: {welcome.classe}</Text> : null}
              {welcome.empresa ? <Text style={styles.welcomeSub} numberOfLines={1}>{welcome.empresa}</Text> : null}
            </View>
          ) : null}
          {collapsed && hoveredKey === "welcome" ? (
            <View style={styles.tooltip} pointerEvents="none">
              <View style={styles.tooltipInner}>
                <Text style={styles.tooltipText}>
                  {welcome.nomeGuerra || welcome.displayName}
                  {welcome.classe ? ` — Grupo: ${welcome.classe}` : ""}
                  {welcome.empresa ? ` — ${welcome.empresa}` : ""}
                </Text>
              </View>
            </View>
          ) : null}
        </Pressable>
      ) : null}
      {items
        .filter((i) => i.visible)
        .map((item) => {
          const active = activeHref === item.href;
          return (
            <Pressable
              key={item.key}
              onPress={() => router.push(item.href as never)}
              onHoverIn={() => setHoveredKey(item.key)}
              onHoverOut={() => setHoveredKey(null)}
              style={[styles.item, active && styles.itemActive, collapsed && styles.itemCollapsed]}
              testID={`sidebar-${item.key}`}
            >
              <View style={styles.iconWrap}>
                <Ionicons name={item.icon} size={20} color={active ? colors.brandPrimary : colors.muted} />
                {item.badge ? (
                  <View pointerEvents="none" style={styles.badge} testID={`sidebar-${item.key}-badge`} />
                ) : null}
              </View>
              {!collapsed ? (
                <Text style={[styles.label, active && styles.labelActive]} numberOfLines={1}>
                  {item.label}
                </Text>
              ) : null}
              {collapsed && hoveredKey === item.key ? (
                <View style={styles.tooltip} pointerEvents="none">
                  <View style={styles.tooltipInner}>
                    <Text style={styles.tooltipText}>{item.label}</Text>
                  </View>
                </View>
              ) : null}
            </Pressable>
          );
        })}
      {shortcuts.some((s) => s.visible) ? (
        <View style={styles.shortcutsGroup}>
          {!collapsed ? <Text style={styles.shortcutsLabel} numberOfLines={1}>Pendências do Sistema</Text> : null}
          {shortcuts
            .filter((s) => s.visible)
            .map((s) => (
              <Pressable
                key={s.key}
                onPress={s.onPress}
                disabled={s.loading}
                onHoverIn={() => setHoveredKey(s.key)}
                onHoverOut={() => setHoveredKey(null)}
                style={[styles.item, styles.shortcutItem]}
                testID={`sidebar-shortcut-${s.key}`}
              >
                <View style={styles.iconWrap}>
                  {s.loading ? (
                    <ActivityIndicator size="small" color={colors.brandPrimary} />
                  ) : (
                    <Ionicons name={s.icon} size={20} color={colors.brandPrimary} />
                  )}
                </View>
                {/* Sempre só ícone, independente de recolhido/expandido —
                    pedido explícito do usuário, 2026-08-28 ("colocar
                    somente icones nas pendências, pois o espaço é
                    curto"). Tooltip SEMPRE disponível no hover (não só
                    quando recolhido, diferente do menu normal acima) —
                    é a única forma de saber o que o ícone faz. */}
                {hoveredKey === s.key ? (
                  <View style={styles.tooltip} pointerEvents="none">
                    <View style={styles.tooltipInner}>
                      <Text style={styles.tooltipText}>{s.loading ? "Atualizando…" : s.label}</Text>
                    </View>
                  </View>
                ) : null}
              </Pressable>
            ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  sidebar: {
    width: 188,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
    gap: 2,
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderRightColor: colors.border,
    // zIndex explícito — sem isso, o tooltip (absoluto, escapa a largura
    // estreita da sidebar) renderiza ATRÁS do painel de conteúdo: eles são
    // View irmãs em app/_layout.tsx (Sidebar antes, content depois no
    // JSX), e react-native-web dá position:relative padrão a toda View, então
    // o irmão mais tarde no DOM (content) pinta por cima por padrão. Mesma
    // causa raiz já corrigida no tooltip do nome do card do Painel de
    // Pedidos. Pedido explícito do usuário, 2026-07-18 ("está por trás da
    // tela").
    zIndex: 20,
  },
  logoWrap: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: spacing.sm,
    marginBottom: spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    // position:relative pra ancorar o tooltip "Início" no modo recolhido —
    // mesmo motivo já documentado em `item` acima.
    position: "relative",
  },
  // Proporção real do arquivo (~6:1, bem mais largo que alto) — 150x25
  // preenche quase toda a largura útil do menu expandido (188px - padding)
  // sem estourar.
  logo: { width: 150, height: 25 },
  // Ícone quadrado (1:1) — cabe nos 56px do menu recolhido com folga pro padding.
  logoIcon: { width: 32, height: 32 },
  collapseBtn: {
    alignSelf: "flex-end",
    width: 28,
    height: 28,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.md,
    marginBottom: spacing.xs,
  },
  collapseBtnCollapsed: {
    alignSelf: "center",
  },
  item: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: radius.md,
    // position:relative pra ancorar o tooltip do menu recolhido — sem
    // efeito visual quando expandido (não usa tooltip nesse caso).
    position: "relative",
  },
  itemCollapsed: {
    justifyContent: "center",
    paddingHorizontal: 0,
  },
  // Itens de "Pendências do Sistema" — sempre ícone-só, mesmo estilo de
  // `itemCollapsed` mas aplicado incondicionalmente (não só quando o
  // menu está recolhido).
  shortcutItem: {
    justifyContent: "center",
    paddingHorizontal: 0,
  },
  itemActive: {
    backgroundColor: colors.surfaceSecondary,
  },
  // Wrapper só pro ícone, pra ancorar o badge de aviso (ver `badge` abaixo)
  // exatamente no canto do ícone — não do item inteiro, que muda de largura
  // entre recolhido/expandido.
  iconWrap: { position: "relative" },
  badge: {
    position: "absolute", top: -2, right: -2,
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: "#ff5252", borderWidth: 1, borderColor: colors.surface,
  },
  // Tooltip do rótulo no menu recolhido — à direita do ícone, verticalmente
  // centralizado (spans a altura inteira do item via top:0/bottom:0 +
  // justifyContent:center, evita precisar de transform pra centralizar).
  tooltip: {
    position: "absolute", left: "100%", top: 0, bottom: 0,
    marginLeft: 8, justifyContent: "center", zIndex: 20,
  },
  tooltipInner: {
    backgroundColor: "#1a1a1a", borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 4,
  },
  tooltipText: { color: "#fff", fontSize: 12, fontWeight: "600" },
  label: {
    fontSize: 13,
    fontWeight: "500",
    color: colors.muted,
  },
  labelActive: {
    color: colors.brandPrimary,
  },
  // Grupo "Pendências do Sistema" — visualmente separado da navegação
  // normal (borda superior, mesmo padrão já usado em `logoWrap`), fica no
  // final da sidebar. O `View` inteiro só é montado quando existe pelo
  // menos 1 item pendente visível (ver JSX) — nunca aparece "vazio".
  shortcutsGroup: {
    marginTop: spacing.xs,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: 2,
  },
  shortcutsLabel: {
    fontSize: 10,
    fontWeight: "700",
    color: colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    paddingHorizontal: 12,
    marginBottom: 4,
  },
  // Card "Bem-vindo" (empresa/avatar/nome/grupo) — pedido explícito do
  // usuário, 2026-08-28, pra ficar sempre visível na base da sidebar
  // (mesmo card já usado na Tela Principal, `WelcomeHero.tsx`, versão
  // compacta pro espaço estreito do menu).
  welcomeCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: spacing.sm,
    marginBottom: spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    position: "relative",
  },
  // Menu recolhido — só o avatar é exibido (sem nome/grupo/conexão ao
  // lado), então centraliza e zera o padding horizontal — mesmo padrão
  // já usado por `itemCollapsed`/`shortcutItem`. Pedido explícito do
  // usuário, 2026-08-28 ("quando o menu recuar, centralizar o avatar...
  // somente nesse caso. Expandido manter como está").
  welcomeCardCollapsed: {
    justifyContent: "center",
    paddingHorizontal: 0,
  },
  welcomeAvatar: { width: 28, height: 28, borderRadius: 14 },
  welcomeAvatarFallback: { backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  welcomeName: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  welcomeSub: { fontSize: 10, color: colors.muted, marginTop: 1 },
});

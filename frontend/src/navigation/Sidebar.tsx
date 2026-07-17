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
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter, usePathname } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { colors, radius, spacing } from "@/src/theme/colors";

type NavItem = {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  href: string;
  visible: boolean;
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
  const { moduleOn } = usePermissions();

  if (HIDDEN_ON.includes(pathname)) return null;

  const items: NavItem[] = [
    { key: "principal", label: "Início", icon: "home-outline", href: "/principal", visible: true },
    { key: "cadastros", label: "Cadastros", icon: "albums-outline", href: "/cadastros", visible: true },
    { key: "transacoes", label: "Transações", icon: "swap-horizontal-outline", href: "/transacoes", visible: true },
    { key: "financeiro", label: "Financeiro", icon: "cash-outline", href: "/financeiro", visible: true },
    { key: "posto-combustivel", label: "Posto", icon: "water-outline", href: "/posto-combustivel", visible: moduleOn("Posto") },
    { key: "cilindros", label: "Cilindros", icon: "flame-outline", href: "/cilindros", visible: moduleOn("Cilindro") },
    { key: "configuracoes", label: "Configurações", icon: "settings-outline", href: "/configuracoes", visible: true },
    { key: "relatorios", label: "Relatórios", icon: "bar-chart-outline", href: "/relatorios", visible: true },
  ];

  const activeHref = DETAIL_TO_TAB[pathname] ?? pathname;

  return (
    <View style={styles.sidebar} testID="app-sidebar">
      {items
        .filter((i) => i.visible)
        .map((item) => {
          const active = activeHref === item.href;
          return (
            <Pressable
              key={item.key}
              onPress={() => router.push(item.href as never)}
              style={[styles.item, active && styles.itemActive]}
              testID={`sidebar-${item.key}`}
            >
              <Ionicons name={item.icon} size={20} color={active ? colors.brandPrimary : colors.muted} />
              <Text style={[styles.label, active && styles.labelActive]}>{item.label}</Text>
            </Pressable>
          );
        })}
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
  },
  item: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: radius.md,
  },
  itemActive: {
    backgroundColor: colors.surfaceSecondary,
  },
  label: {
    fontSize: 13,
    fontWeight: "500",
    color: colors.muted,
  },
  labelActive: {
    color: colors.brandPrimary,
  },
});

// Chave de Renovação do Sistema — migração de ChaveRenovacao.vbp (ferramenta
// interna da Kontacto que gera/envia a chave de liberação dos clientes
// conforme baixa em Contas a Receber). Pedido explícito do usuário,
// 2026-08-17: fica dentro do menu Financeiro, mas NÃO entra na regra de
// Permissões (catálogo de classe) — acesso é só por ser usuário master
// (Kontacto), mesmo padrão de "Módulos e Recursos" em configuracoes.tsx.
// Ainda sem implementação real — depende do módulo Contas a Receber (geral)
// existir primeiro. Ver PENDENCIAS.md > "Chave de Renovação do Sistema".
import { Platform } from "react-native";

import LockedView from "@/src/components/LockedView";
import ComingSoonScreen from "@/src/components/ComingSoonScreen";
import { usePermissions } from "@/src/permissions";

export default function ChaveRenovacaoScreen() {
  const { isMaster } = usePermissions();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Chave de Renovação está disponível apenas no web."
        testID="chave-renovacao-web-only"
      />
    );
  }
  if (!isMaster) {
    return (
      <LockedView
        title="Uso restrito"
        message="Chave de Renovação é de uso exclusivo da Kontacto."
        testID="chave-renovacao-restrito"
      />
    );
  }

  return (
    <ComingSoonScreen
      title="Chave de Renovação"
      icon="key-outline"
      message="Gera e envia a chave de liberação do sistema para os clientes conforme o pagamento em Contas a Receber. Aguardando o módulo de Contas a Receber para ser implementado."
      testID="chave-renovacao-screen"
    />
  );
}

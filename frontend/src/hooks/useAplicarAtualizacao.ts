import { useCallback, useState } from "react";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { useAuditContext } from "@/src/hooks/useAuditContext";

// Atalho "Atualizar Sistema" do Sidebar — dispara
// `POST /servico-sistema/atualizacao/aplicar` direto, sem passar pela tela
// completa (Configurações > Serviço do Sistema > Atualização, que continua
// existindo, restrita ao Master, pra configurar chave do blob/pastas/
// intervalo). Resolve a conexão do jeito mais simples possível (mesmo
// padrão de `useAtualizacaoPendente.ts`) porque o Sidebar é montado uma
// vez no layout raiz, fora do contexto de qualquer tela específica.
export function useAplicarAtualizacao() {
  const [aplicando, setAplicando] = useState(false);
  const auditCtx = useAuditContext();

  const aplicar = useCallback(async (): Promise<{ success: boolean; message?: string }> => {
    setAplicando(true);
    try {
      const s = await getSession();
      if (!s) return { success: false, message: "Sessão não encontrada." };
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return { success: false, message: "Conexão não encontrada." };
      const conn: Connection = c;
      const j = await apiSend(conn, "/api/servico-sistema/atualizacao/aplicar", "POST", { ...auditCtx });
      if (!j?.success) {
        return { success: false, message: friendlyApiError(j, "Falha ao aplicar a atualização.") };
      }
      return { success: true, message: j.message };
    } catch (e) {
      return { success: false, message: friendlyCatchError(e, "Falha ao aplicar a atualização.") };
    } finally {
      setAplicando(false);
    }
  }, [auditCtx]);

  return { aplicando, aplicar };
}

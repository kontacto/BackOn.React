// Campos a espalhar em qualquer corpo de POST de gravar/excluir, pro backend
// atribuir a ação no log de auditoria (`log_auditoria`, ver
// `backend/services/log_auditoria_service.py`). Centraliza aqui em vez de
// repetir a mesma lógica (usuário + classe + plataforma) em cada tela.
import { Platform } from "react-native";
import { usePermissions } from "@/src/permissions";

export type AuditContext = {
  usuario_alteracao: number | null;
  classe: number | null;
  plataforma: string;
};

export function useAuditContext(): AuditContext {
  const { usuarioCodigo, classe } = usePermissions();
  return { usuario_alteracao: usuarioCodigo, classe, plataforma: Platform.OS };
}

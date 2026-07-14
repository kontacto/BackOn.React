"""Log de Auditoria — tabela `log_auditoria` (não confundir com as tabelas
legadas do VB6 `logs`/`tipo_log`/`log_sistema`, que continuam em uso pelo
sistema antigo e não devem ser tocadas). Tela/comando usam o mesmo vocabulário
do catálogo de permissões (`services/permissoes_service.CATALOGO`)."""
from typing import Optional

from pydantic import BaseModel


class CampoAlterado(BaseModel):
    campo: str
    antes: Optional[str] = None
    depois: Optional[str] = None


class AuditFields(BaseModel):
    """Mixin pra qualquer Save/Delete request que precise identificar quem fez
    a ação, pro log de auditoria — sem exigir checagem de permissão (classe
    aqui é só contexto histórico, não é validado com `tem_permissao`)."""
    usuario_alteracao: Optional[int] = None  # funcionarios.codigo_int
    classe: Optional[int] = None             # grupo do usuário no momento da ação
    plataforma: Optional[str] = None         # "web"/"android"/"ios"

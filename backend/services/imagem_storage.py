"""Driver de armazenamento PLUGÁVEL para fotos de produto (`produto_imagem_
service.py`) — desenho aprovado no documento de arquitetura
"Arquitetura de Fotos de Produtos" (ver PENDENCIAS.md > "Fotos de Produto").

Mesma ideia de dual-mode já usada pelo Gestor de Documentos
(`gestor_documentos_service.py` — local disco/rede OU Azure Blob, decidido
pelo *valor* de uma coluna em `controle_aux`), aqui generalizada atrás de
uma interface real (`ImagemStorageDriver`) em vez de `if`/`else` espalhado
pelo service — trocar de driver no futuro (outro fornecedor de Blob
Storage compatível: AWS S3, Google Cloud Storage, MinIO) significa
implementar uma classe nova aqui, sem tocar em `produto_imagem_service.py`,
rotas ou frontend.

**Escopo atual: 2 drivers reais** (`LocalDiskDriver`, `BlobStorageDriver`
via `azure-storage-blob`, já pinado no requirements.txt e já validado
ponta-a-ponta pelo Gestor de Documentos) — um driver S3-compatível fica
pra quando houver credencial/endpoint real pra testar contra (`boto3` já é
dependência transitiva presente, mas não usado ainda).

Configuração: `controle_aux.path_produto_imagem` (path local OU URL de
container Blob, mesma regex de detecção do Gestor de Documentos, mas
INDEPENDENTE de `path_gestor_documentos` — uma instalação pode apontar
documento de produto pro disco local e foto pro Blob, ou vice-versa) +
`controle_aux.Azure_ConnectionString` (mesma credencial já existente,
reaproveitada quando o path resolvido for Blob — não pede segredo novo).
Campo exposto em Controle do Sistema, aba Kontacto (mesma vizinhança de
`path_gestor_documentos`).
"""
import re
from pathlib import Path
from typing import Optional, Protocol
from urllib.parse import unquote, urlparse

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient

from db.connection import _open_conn

EMPRESA_AUX = 0

# Mesma detecção já usada por gestor_documentos_service.py — duplicada aqui
# de propósito (3 linhas, não vale acoplar duas features independentes por
# isso) em vez de importar símbolos privados de um módulo não relacionado.
_BLOB_HOST_RE = re.compile(r"^https?://[^./]+\.blob\.core\.windows\.net/", re.IGNORECASE)


def _is_blob_target(path_ou_url: str) -> bool:
    return bool(_BLOB_HOST_RE.match((path_ou_url or "").strip()))


def _parse_blob_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    partes = parsed.path.lstrip("/").split("/", 1)
    container = partes[0]
    prefixo = unquote(partes[1]).strip("/") if len(partes) > 1 else ""
    return container, prefixo


def _ensure_path_produto_imagem_col(cur) -> None:
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='path_produto_imagem' AND Object_ID=Object_ID('controle_aux')) "
        "ALTER TABLE controle_aux ADD path_produto_imagem NVARCHAR(255) NULL"
    )


class ImagemStorageDriver(Protocol):
    def salvar(self, caminho: str, conteudo: bytes, content_type: str) -> None: ...

    def ler(self, caminho: str) -> bytes: ...

    def excluir(self, caminho: str) -> None: ...  # best-effort, nunca levanta


class LocalDiskDriver:
    def __init__(self, base_path: str):
        self._base = Path(base_path)

    def salvar(self, caminho: str, conteudo: bytes, content_type: str) -> None:
        destino = self._base / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)

    def ler(self, caminho: str) -> bytes:
        return (self._base / caminho).read_bytes()

    def excluir(self, caminho: str) -> None:
        try:
            (self._base / caminho).unlink(missing_ok=True)
        except OSError:
            pass


class BlobStorageDriver:
    def __init__(self, connection_string: str, container: str, prefixo: str = ""):
        self._conn_str = connection_string
        self._container = container
        self._prefixo = prefixo.strip("/")

    def _blob_name(self, caminho: str) -> str:
        return "/".join(p for p in [self._prefixo, caminho.strip("/")] if p)

    def salvar(self, caminho: str, conteudo: bytes, content_type: str) -> None:
        service = BlobServiceClient.from_connection_string(self._conn_str)
        blob = service.get_blob_client(container=self._container, blob=self._blob_name(caminho))
        blob.upload_blob(conteudo, overwrite=True)

    def ler(self, caminho: str) -> bytes:
        service = BlobServiceClient.from_connection_string(self._conn_str)
        blob = service.get_blob_client(container=self._container, blob=self._blob_name(caminho))
        return blob.download_blob().readall()

    def excluir(self, caminho: str) -> None:
        try:
            service = BlobServiceClient.from_connection_string(self._conn_str)
            service.get_blob_client(container=self._container, blob=self._blob_name(caminho)).delete_blob()
        except AzureError:
            pass


def resolver_driver_sync(servidor: str, banco: str) -> ImagemStorageDriver:
    """Lê `controle_aux.path_produto_imagem`/`Azure_ConnectionString` e
    devolve o driver correspondente. Levanta `ValueError` com mensagem
    amigável quando a configuração está ausente/incompleta — quem chama
    (sempre dentro de um `try/except Exception` mais amplo no service)
    converte isso em `{"success": False, "message": ...}`."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT path_produto_imagem, Azure_ConnectionString FROM controle_aux WHERE empresa_aux=%s",
            (EMPRESA_AUX,),
        )
        row = cur.fetchone() or {}
        cur.close()
    finally:
        conn.close()

    path_base = (row.get("path_produto_imagem") or "").strip()
    if not path_base:
        raise ValueError(
            "Armazenamento de fotos de produto não configurado — defina o path local ou a URL do "
            "container Blob em Controle do Sistema (aba Kontacto)."
        )
    if _is_blob_target(path_base):
        azure_conn_str = (row.get("Azure_ConnectionString") or "").strip()
        if not azure_conn_str:
            raise ValueError("Azure_ConnectionString não configurada em Controle do Sistema.")
        container, prefixo = _parse_blob_url(path_base)
        return BlobStorageDriver(azure_conn_str, container, prefixo)
    return LocalDiskDriver(path_base)

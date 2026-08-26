"""CLI de migração (Fase 4 do documento de arquitetura de Fotos de
Produto, ver PENDENCIAS.md > "Fotos de Produto") — copia as fotos já
anexadas via Gestor de Documentos (grupo Produtos, cod_grupo=4) para o
sistema novo `produto_imagem`.

**Nunca automático** — roda manualmente, por empresa (`--servidor
--banco`), sempre primeiro contra uma conexão de teste (ARGEN-TESTE/
GERDELL) antes de qualquer instalação de produção. **Não apaga nada do
Gestor de Documentos** — só lê e copia; os registros antigos continuam
lá, intactos, servindo de histórico.

Idempotente por reexecução: compara `hash_conteudo` do arquivo baixado
contra o que já existe em `produto_imagem` antes de migrar de novo — rodar
duas vezes não duplica.

Uso:
    python scripts/migrar_fotos_produto.py --servidor X --banco Y [--dry-run]
"""
import argparse
import hashlib
import sys
from pathlib import Path as FSPath

ROOT_DIR = FSPath(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT_DIR / ".env")

from azure.storage.blob import BlobServiceClient  # noqa: E402

from db.connection import _open_conn  # noqa: E402
from services.gestor_documentos_service import (  # noqa: E402
    GRUPO_PRODUTO, _get_storage_config_sync, _is_blob_target, _parse_blob_url,
)
from services.produto_imagem_service import _upload_imagem_sync  # noqa: E402


def _baixar_arquivo_local_ou_blob(servidor: str, banco: str, stored_path: str):
    if not stored_path:
        return None
    if _is_blob_target(stored_path):
        _, azure_conn_str = _get_storage_config_sync(servidor, banco)
        if not azure_conn_str:
            return None
        container, blob_name = _parse_blob_url(stored_path)
        try:
            service = BlobServiceClient.from_connection_string(azure_conn_str)
            return service.get_blob_client(container=container, blob=blob_name).download_blob().readall()
        except Exception:
            return None
    p = FSPath(stored_path)
    if not p.is_file():
        return None
    return p.read_bytes()


def migrar(servidor: str, banco: str, dry_run: bool) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, referencia_texto AS codigo_int, path, path_origem, cor FROM gestor_documentos "
            "WHERE cod_grupo=%s AND (situacao_arquivo IS NULL OR situacao_arquivo<>'D')",
            (GRUPO_PRODUTO,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    print(f"{len(rows)} documento(s) de Produtos encontrados em {servidor}/{banco}.")

    conn2 = _open_conn(servidor, banco)
    try:
        cur2 = conn2.cursor(as_dict=True)
        cur2.execute("SELECT hash_conteudo FROM produto_imagem WHERE hash_conteudo IS NOT NULL")
        ja_migrados = {r["hash_conteudo"] for r in cur2.fetchall() if r.get("hash_conteudo")}
        cur2.close()
    finally:
        conn2.close()

    migrados = pulados = erros = 0
    for row in rows:
        codigo_int = (row.get("codigo_int") or "").strip()
        if not codigo_int:
            pulados += 1
            continue
        conteudo = _baixar_arquivo_local_ou_blob(servidor, banco, row.get("path") or "")
        if not conteudo:
            print(f"  [pulado] gestor_documentos #{row['codigo']} — arquivo não encontrado.")
            pulados += 1
            continue
        if hashlib.sha256(conteudo).hexdigest() in ja_migrados:
            pulados += 1
            continue
        if dry_run:
            print(f"  [dry-run] migraria produto {codigo_int} (gestor_documentos #{row['codigo']})")
            migrados += 1
            continue
        result = _upload_imagem_sync(
            servidor, banco, codigo_int=codigo_int, conteudo=conteudo,
            nome_original=row.get("path_origem") or "foto.jpg", cor=row.get("cor"),
        )
        if result.get("success"):
            migrados += 1
        else:
            print(f"  [erro] produto {codigo_int} (gestor_documentos #{row['codigo']}): {result.get('message')}")
            erros += 1

    print(f"Concluído: {migrados} migrada(s), {pulados} pulada(s), {erros} com erro.")
    return {"migrados": migrados, "pulados": pulados, "erros": erros}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migra fotos de Produtos do Gestor de Documentos para produto_imagem (não apaga nada)."
    )
    parser.add_argument("--servidor", required=True)
    parser.add_argument("--banco", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Só lista o que seria migrado, sem gravar nada.")
    args = parser.parse_args()
    migrar(args.servidor, args.banco, args.dry_run)


if __name__ == "__main__":
    main()

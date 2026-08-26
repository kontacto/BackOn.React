"""Fotos de Produto — sistema NOVO e ISOLADO do Gestor de Documentos
genérico (`gestor_documentos_service.py`), que continua ativo pra Produtos
cobrindo DOCUMENTO (manual, certificado, ficha técnica) — ver documento de
arquitetura aprovado em PENDENCIAS.md > "Fotos de Produto" pro raciocínio
completo. Motivo da separação: imagem de produto é lida em alta frequência
(catálogo/PDV/mobile, a mesma foto reexibida centenas de vezes) e precisa
de variantes por tamanho — perfil de acesso oposto ao de um PDF de
contrato, que o Gestor de Documentos foi desenhado pra servir bem.

Storage plugável via `services/imagem_storage.py` (`resolver_driver_sync`)
— disco local OU qualquer Blob Storage compatível, decidido por
`controle_aux.path_produto_imagem`. Todo consumo (upload/leitura) passa
por este service, nunca por URL direta do driver — mesma decisão do
Gestor de Documentos, deixa CDN como um passo de infraestrutura futuro na
frente da rota de download, sem mudar nenhum consumidor.

Cada upload gera 3 variantes WebP (thumb/medium/web, geradas uma vez, no
momento do upload) além de preservar o ORIGINAL sem recompressão — ver
`_VARIANTES`. `ImageOps.exif_transpose` corrige a orientação da foto E
descarta o EXIF de cada variante como efeito colateral (nunca vaza GPS/
modelo do aparelho nas imagens servidas publicamente); o original mantém
o EXIF intacto (auditoria/impressão).

`storage_key` é um UUID novo por upload (nunca o nome original do
arquivo) — resolve a colisão silenciosa que existe no Gestor de
Documentos (dois uploads com o mesmo nome de arquivo se sobrescrevem lá).

Exclusão (`_excluir_imagem_sync`): marca `situacao='C'` (mantém a linha —
histórico/dedupe por hash no script de migração) **e** remove o objeto
físico (original + 3 variantes) do storage — pedido explícito do usuário
2026-08-26, diferente do Gestor de Documentos (que só faz soft-delete pra
Produtos, sem tocar no arquivo). Remoção física é best-effort: se falhar,
não desfaz nem bloqueia a exclusão lógica já confirmada.
"""
import asyncio
import hashlib
import io
import uuid
from typing import Optional

from PIL import Image, ImageOps, UnidentifiedImageError

from db.connection import _open_conn
from services.imagem_storage import resolver_driver_sync

TAMANHO_MAX_BYTES = 10 * 1024 * 1024  # 10MB

# nome da variante -> maior dimensão (px), mantendo proporção
_VARIANTES = {"thumb": 150, "medium": 600, "web": 1200}

_MIME_POR_FORMATO = {
    "JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp",
    "GIF": "image/gif", "BMP": "image/bmp",
}
_EXT_POR_FORMATO = {
    "JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp",
}


def _sanitizar(texto: str) -> str:
    texto = (texto or "").strip()
    for ch in '\\/:*?"<>| ':
        texto = texto.replace(ch, "_")
    return texto or "_"


def _ensure_produto_imagem_table(cur) -> None:
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'produto_imagem') "
        "BEGIN "
        "CREATE TABLE produto_imagem ("
        "codigo INT IDENTITY(1,1) PRIMARY KEY, "
        "codigo_int NVARCHAR(30) NOT NULL, "
        "storage_key NVARCHAR(36) NOT NULL, "
        "nome_original NVARCHAR(255) NULL, "
        "content_type NVARCHAR(50) NOT NULL, "
        "largura INT NULL, "
        "altura INT NULL, "
        "tamanho_bytes INT NOT NULL, "
        "hash_conteudo CHAR(64) NULL, "
        "cor INT NULL, "
        "principal BIT NOT NULL DEFAULT 0, "
        "ordem INT NOT NULL DEFAULT 0, "
        "situacao NVARCHAR(2) NOT NULL DEFAULT 'A', "
        "usuario_inclusao INT NULL, "
        "data_inclusao DATETIME NOT NULL DEFAULT GETDATE()"
        "); "
        "CREATE INDEX IX_produto_imagem_codigo_int ON produto_imagem(codigo_int); "
        "END"
    )
    # Índice filtrado — no máximo 1 imagem principal ATIVA por produto, sem
    # precisar de trigger. Statement separado (CREATE INDEX ... WHERE não
    # entra dentro do BEGIN/END acima porque a tabela pode já existir de
    # uma execução anterior desta própria migração).
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_produto_imagem_principal') "
        "CREATE UNIQUE INDEX UX_produto_imagem_principal ON produto_imagem(codigo_int) "
        "WHERE principal = 1 AND situacao = 'A'"
    )


def _preparar_variantes(conteudo: bytes) -> Image.Image:
    """`exif_transpose` corrige a rotação (foto de celular) E descarta o
    EXIF de origem como efeito colateral — nunca vaza GPS/modelo do
    aparelho nas variantes servidas publicamente."""
    base = ImageOps.exif_transpose(Image.open(io.BytesIO(conteudo)))
    if base.mode not in ("RGB", "RGBA"):
        base = base.convert("RGBA" if "A" in (base.getbands() or ()) else "RGB")
    return base


def _upload_imagem_sync(
    servidor: str, banco: str, *, codigo_int: str, conteudo: bytes, nome_original: str,
    cor: Optional[int] = None, principal: bool = False, usuario_inclusao: Optional[int] = None,
) -> dict:
    codigo_int = (codigo_int or "").strip()
    if not codigo_int:
        return {"success": False, "message": "Código do produto não informado."}
    if not conteudo:
        return {"success": False, "message": "Selecione uma imagem para enviar."}
    if len(conteudo) > TAMANHO_MAX_BYTES:
        return {"success": False, "message": "Arquivo maior que o limite de 10MB."}

    try:
        im = Image.open(io.BytesIO(conteudo))
        im.verify()
    except (UnidentifiedImageError, OSError):
        return {"success": False, "message": "O arquivo enviado não é uma imagem válida."}

    # `verify()` deixa o objeto original inutilizável para leitura de
    # pixels — reabre pra extrair dimensões/formato reais.
    im = Image.open(io.BytesIO(conteudo))
    largura, altura = im.size
    formato = (im.format or "").upper()
    content_type = _MIME_POR_FORMATO.get(formato, "application/octet-stream")
    ext = _EXT_POR_FORMATO.get(formato, "bin")

    try:
        driver = resolver_driver_sync(servidor, banco)
    except ValueError as e:
        return {"success": False, "message": str(e)}

    storage_key = str(uuid.uuid4())
    prefixo = f"{_sanitizar(servidor)}/{_sanitizar(banco)}/{_sanitizar(codigo_int)}/{storage_key}"

    try:
        driver.salvar(f"{prefixo}/original.{ext}", conteudo, content_type)
        base_variante = _preparar_variantes(conteudo)
        for nome_variante, tamanho in _VARIANTES.items():
            var_img = base_variante.copy()
            var_img.thumbnail((tamanho, tamanho), Image.LANCZOS)
            buf = io.BytesIO()
            var_img.save(buf, format="WEBP", quality=82)
            driver.salvar(f"{prefixo}/{nome_variante}.webp", buf.getvalue(), "image/webp")
    except Exception as e:
        return {"success": False, "message": f"Falha ao gravar a imagem no armazenamento: {e}"}

    hash_conteudo = hashlib.sha256(conteudo).hexdigest()

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT ISNULL(MAX(ordem), -1) + 1 AS prox FROM produto_imagem WHERE codigo_int=%s AND situacao='A'",
            (codigo_int,),
        )
        ordem = int(cur.fetchone()["prox"])
        # Primeira foto ativa do produto (ordem=0, nenhuma outra existente)
        # sempre vira principal automaticamente — pedido explícito do
        # usuário 2026-08-26, evita produto ficar sem foto principal só
        # porque ninguém marcou o checkbox no primeiro envio.
        if ordem == 0:
            principal = True
        if principal:
            cur.execute(
                "UPDATE produto_imagem SET principal=0 WHERE codigo_int=%s AND principal=1",
                (codigo_int,),
            )
        cur.execute(
            "INSERT INTO produto_imagem (codigo_int, storage_key, nome_original, content_type, largura, "
            "altura, tamanho_bytes, hash_conteudo, cor, principal, ordem, usuario_inclusao) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                codigo_int, storage_key, (nome_original or "").strip()[:255] or None, content_type,
                largura, altura, len(conteudo), hash_conteudo, cor, 1 if principal else 0, ordem,
                usuario_inclusao,
            ),
        )
        conn.commit()
        cur.execute("SELECT @@IDENTITY AS codigo")
        codigo = int(cur.fetchone()["codigo"])
        cur.close()
        return {"success": True, "message": "Foto enviada com sucesso.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar registro da foto: {e}"}
    finally:
        conn.close()


def _list_imagens_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, storage_key, nome_original, content_type, largura, altura, tamanho_bytes, "
            "cor, principal, ordem, data_inclusao FROM produto_imagem "
            "WHERE codigo_int=%s AND situacao='A' ORDER BY principal DESC, ordem ASC",
            (codigo_int,),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "storage_key": r["storage_key"],
            "nome_original": (r.get("nome_original") or "").strip(),
            "content_type": r.get("content_type"),
            "largura": r.get("largura"),
            "altura": r.get("altura"),
            "tamanho_bytes": r.get("tamanho_bytes"),
            "cor": r.get("cor"),
            "principal": bool(r.get("principal")),
            "ordem": r.get("ordem"),
            "data_inclusao": r["data_inclusao"].isoformat() if r.get("data_inclusao") else None,
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _extensao_original(content_type: str) -> str:
    ext_por_mime = {v: k.lower() for k, v in _MIME_POR_FORMATO.items()}
    return {"jpeg": "jpg"}.get(ext_por_mime.get(content_type, ""), ext_por_mime.get(content_type, "bin"))


def _prefixo_storage(servidor: str, banco: str, codigo_int: str, storage_key: str) -> str:
    return f"{_sanitizar(servidor)}/{_sanitizar(banco)}/{_sanitizar(codigo_int)}/{storage_key}"


def _arquivo_sync(servidor: str, banco: str, codigo: int, variante: str) -> dict:
    if variante not in (*_VARIANTES.keys(), "original"):
        return {"success": False, "message": "Variante inválida."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo_int, storage_key, content_type, nome_original FROM produto_imagem WHERE codigo=%s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    if not row:
        return {"success": False, "message": "Foto não encontrada."}

    content_type = row.get("content_type") or "application/octet-stream"
    if variante == "original":
        ext = _extensao_original(content_type)
    else:
        ext = "webp"
        content_type = "image/webp"

    prefixo = _prefixo_storage(servidor, banco, row["codigo_int"], row["storage_key"])
    caminho = f"{prefixo}/{variante}.{ext}"
    try:
        driver = resolver_driver_sync(servidor, banco)
        conteudo = driver.ler(caminho)
    except Exception as e:
        return {"success": False, "message": f"Não foi possível ler a imagem no armazenamento: {e}"}
    return {
        "success": True, "conteudo": conteudo, "content_type": content_type,
        "nome_arquivo": row.get("nome_original") or f"foto-{codigo}.{ext}",
    }


def _excluir_imagem_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo_int, storage_key, content_type FROM produto_imagem WHERE codigo=%s AND situacao='A'",
            (codigo,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Foto não encontrada."}
        # A linha fica marcada como cancelada (situacao='C') — mantém o
        # histórico/metadado (auditoria, dedupe por hash no script de
        # migração), mas deixa de contar como foto ativa em qualquer
        # listagem/uso. Pedido explícito do usuário 2026-08-26: excluir
        # também remove o objeto FÍSICO (original + 3 variantes) — decisão
        # que reverte o padrão conservador original (soft-delete sem tocar
        # no arquivo, mesmo que o Gestor de Documentos ainda faça isso pra
        # Produtos) especificamente pra este sistema novo.
        cur.execute("UPDATE produto_imagem SET situacao='C', principal=0 WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()

        try:
            driver = resolver_driver_sync(servidor, banco)
            prefixo = _prefixo_storage(servidor, banco, row["codigo_int"], row["storage_key"])
            ext_original = _extensao_original(row.get("content_type") or "")
            driver.excluir(f"{prefixo}/original.{ext_original}")
            for variante in _VARIANTES:
                driver.excluir(f"{prefixo}/{variante}.webp")
        except Exception:
            # Best-effort — a exclusão lógica (situacao='C') já está
            # gravada e é o que decide se a foto aparece em algum lugar;
            # uma falha ao remover o arquivo físico (driver reconfigurado
            # nesse meio-tempo, permissão de pasta, etc.) não pode reverter
            # nem travar a exclusão já confirmada ao usuário.
            pass
        return {"success": True, "message": "Foto removida."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _marcar_principal_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo_int FROM produto_imagem WHERE codigo=%s AND situacao='A'", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Foto não encontrada."}
        cur.execute(
            "UPDATE produto_imagem SET principal=0 WHERE codigo_int=%s AND principal=1",
            (row["codigo_int"],),
        )
        cur.execute("UPDATE produto_imagem SET principal=1 WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Foto definida como principal."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao definir foto principal: {e}"}
    finally:
        conn.close()


async def upload_imagem(servidor, banco, **kwargs):
    return await asyncio.to_thread(_upload_imagem_sync, servidor, banco, **kwargs)


async def list_imagens(servidor, banco, codigo_int):
    return await asyncio.to_thread(_list_imagens_sync, servidor, banco, codigo_int)


async def arquivo(servidor, banco, codigo, variante):
    return await asyncio.to_thread(_arquivo_sync, servidor, banco, codigo, variante)


async def excluir_imagem(servidor, banco, codigo):
    return await asyncio.to_thread(_excluir_imagem_sync, servidor, banco, codigo)


async def marcar_principal(servidor, banco, codigo):
    return await asyncio.to_thread(_marcar_principal_sync, servidor, banco, codigo)

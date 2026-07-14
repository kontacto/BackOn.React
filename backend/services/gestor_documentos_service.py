"""Gestor de Documentos (Anexos) — genérico, chamado por várias telas
"identidade" (Cliente, Fornecedor, Funcionário, Produto, Serviço), sem menu
próprio. Legado: `FrmGesDoc.frm` — ver memória de projeto para o desenho
completo (grupos/sub-grupos, decisões de arquitetura confirmadas com o
usuário em 2026-07-10).

Schema real (conferido ao vivo em GERDELL/BARESTELA, não assumido do VB6):
- `gestor_docs_grupos(codigo, grupo)`: 1=Clientes 2=Fornecedores
  3=Funcionários 4=Produtos 5=Serviços.
- `gestor_docs_sub_grupos(cod_sub_grupo PK, cod_grupo FK, descricao)` —
  cadastrado sob demanda por grupo (ex.: grupo 1/Clientes já tem "Pedidos de
  Venda" e "Ordens de Serviço" semeados — é assim que Pedido/O.S. usam este
  gestor sem tabela própria, fiel ao legado).
- `gestor_documentos(codigo PK, cod_grupo, cod_sub_grupo, path, descricao,
  path_origem, adicionado_por, data, hora, computador, validade,
  referencia_texto, referencia_codigo, referencia, situacao_arquivo, cor)`.
  Campos `PATH_NUVEM`/`ENVIADA_SITE`/`FOTO_PRINCIPAL_SITE`/`upload` existem
  na tabela mas são de uma integração de nuvem/site não implementada neste
  app (mesmo critério de outras telas) — fora de escopo, não usados aqui.
- Tabela de junção por grupo, populada em paralelo a `gestor_documentos`
  (duplicação proposital, fiel ao legado): `cliente_anexos(codigo,
  cod_gestor)`, `fornecedor_anexos(codigo, cod_gestor)`,
  `funcionario_anexos(codigo, cod_gestor)`, `pecas_anexos(codigo_int
  nvarchar(8), cod_gestor)`, `servicos_anexos(codigo_int nvarchar(8),
  cod_gestor)` — grupos 1/2/3 usam código inteiro (`referencia_codigo`),
  4/5 usam código texto (`referencia_texto`, peças/serviços têm
  `codigo_int` string).

Armazenamento: local (disco/rede) OU Azure Blob Storage — decidido em
tempo real pelo *valor* de `controle_aux.path_gestor_documentos`, não é
uma escolha fixa por instalação (usuário: "não vai ser fixo, ou vai ser
na nuvem ou local do backend"). Se o valor for uma URL de container Blob
(`https://<conta>.blob.core.windows.net/<container>[/prefixo]`), sobe pro
Azure usando `controle_aux.Azure_ConnectionString` (campo legado já
existente, nunca usado até então) para autenticar; senão, é tratado como
path de disco/rede local, igual ao legado. Em ambos os casos o "path
virtual" dentro do destino segue a mesma convenção do legado: `<nome do
grupo>/<nome do sub-grupo>/<código da entidade> - <nome original>`.
`gestor_documentos.path` sempre grava o destino final completo (path
absoluto OU URL do blob) — cada registro é autodescritivo sobre COMO
buscar aquele arquivo depois (local vs. blob), então uma troca de
`path_gestor_documentos` não quebra retroativamente documentos já
anexados (mesma proteção documentada na memória de projeto). Isso não
cobre a troca da própria Connection String do Azure — se ela mudar/for
revogada, anexos antigos em blob ficam inacessíveis (limitação inerente a
credencial de nuvem, sem equivalente pro caso local).

Azure_Container/Azure_folder/Azure_prefixo (também legados, também nunca
usados) ficam FORA de uso neste fluxo — o container e o prefixo vêm
inteiramente da própria URL em `path_gestor_documentos`, não desses
campos separados (decisão do usuário: "a Connection String autentica, o
resto vem da URL").

Upload sempre chega por multipart HTTP no backend (não tem como o
navegador escrever num path de rede nem falar com o Azure Blob
diretamente) e o backend decide pra onde mandar.

Exclusão: hard delete em geral. Exceção fiel ao legado só para Produtos
(grupo 4) — soft delete (`situacao_arquivo='D'`, mantém arquivo e
registro). O legado condicionava isso a uma flag `Dados_Controle_
Configuracao.Grade` sem equivalente claro neste sistema; simplificado aqui
para: grupo 4 sempre soft-delete, sem essa condição extra (assunção
registrada aqui, não confirmada campo-a-campo com o usuário).
"""
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient

from db.connection import _open_conn

EMPRESA = 0

_BLOB_HOST_RE = re.compile(r"^https?://[^./]+\.blob\.core\.windows\.net/", re.IGNORECASE)


def _is_blob_target(path_ou_url: str) -> bool:
    return bool(_BLOB_HOST_RE.match((path_ou_url or "").strip()))


def _parse_blob_url(url: str) -> tuple[str, str]:
    """https://<conta>.blob.core.windows.net/<container>/<prefixo...> ->
    (container, prefixo). Prefixo pode ser vazio (URL só do container)."""
    parsed = urlparse(url.strip())
    partes = parsed.path.lstrip("/").split("/", 1)
    container = partes[0]
    prefixo = unquote(partes[1]).strip("/") if len(partes) > 1 else ""
    return container, prefixo

GRUPO_CLIENTE = 1
GRUPO_FORNECEDOR = 2
GRUPO_FUNCIONARIO = 3
GRUPO_PRODUTO = 4
GRUPO_SERVICO = 5

# grupo -> (tabela de junção, coluna do código da entidade, tipo da coluna)
_JUNCAO = {
    GRUPO_CLIENTE: ("cliente_anexos", "codigo"),
    GRUPO_FORNECEDOR: ("fornecedor_anexos", "codigo"),
    GRUPO_FUNCIONARIO: ("funcionario_anexos", "codigo"),
    GRUPO_PRODUTO: ("pecas_anexos", "codigo_int"),
    GRUPO_SERVICO: ("servicos_anexos", "codigo_int"),
}

# grupos cujo código de entidade é texto (codigo_int), não int
_GRUPOS_CODIGO_TEXTO = {GRUPO_PRODUTO, GRUPO_SERVICO}


def _sanitize_path_component(texto: str) -> str:
    """Nomes de grupo/sub-grupo/arquivo viram parte de um path de arquivo —
    tira caracteres que o Windows não aceita em nome de pasta/arquivo."""
    texto = (texto or "").strip()
    for ch in '\\/:*?"<>|':
        texto = texto.replace(ch, "_")
    return texto or "Sem_Nome"


def _get_storage_config_sync(servidor: str, banco: str) -> tuple[Optional[str], Optional[str]]:
    """(path_base, azure_connection_string). `path_base` decide o modo (ver
    docstring do módulo); `azure_connection_string` só é necessária/usada
    quando `path_base` for uma URL de Blob."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT path_gestor_documentos, Azure_ConnectionString FROM controle_aux WHERE empresa_aux=%s",
            (EMPRESA,),
        )
        row = cur.fetchone() or {}
        cur.close()
        path_base = (row.get("path_gestor_documentos") or "").strip() or None
        conn_str = (row.get("Azure_ConnectionString") or "").strip() or None
        return path_base, conn_str
    finally:
        conn.close()


def _list_grupos_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, grupo FROM gestor_docs_grupos ORDER BY codigo")
        items = [{"codigo": int(r["codigo"]), "grupo": (r.get("grupo") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _list_sub_grupos_sync(servidor: str, banco: str, cod_grupo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cod_sub_grupo, descricao FROM gestor_docs_sub_grupos WHERE cod_grupo=%s ORDER BY descricao",
            (cod_grupo,),
        )
        items = [
            {"cod_sub_grupo": int(r["cod_sub_grupo"]), "descricao": (r.get("descricao") or "").strip()}
            for r in cur.fetchall()
        ]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _get_or_create_sub_grupo_sync(servidor: str, banco: str, cod_grupo: int, descricao: str) -> dict:
    """Legado permite cadastrar sub-grupo novo "sob demanda" (Form_Load do
    FrmGesDoc insere se não existir) — mesma ideia aqui, usada pela tela de
    Controle do Sistema quando o usuário digita um sub-grupo novo."""
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Informe a descrição do sub-grupo."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cod_sub_grupo FROM gestor_docs_sub_grupos WHERE cod_grupo=%s AND UPPER(descricao)=%s",
            (cod_grupo, desc.upper()),
        )
        row = cur.fetchone()
        if row:
            cur.close()
            return {"success": True, "cod_sub_grupo": int(row["cod_sub_grupo"])}
        cur.execute(
            "INSERT INTO gestor_docs_sub_grupos (cod_grupo, descricao) VALUES (%s,%s)",
            (cod_grupo, desc),
        )
        conn.commit()
        cur.execute(
            "SELECT cod_sub_grupo FROM gestor_docs_sub_grupos WHERE cod_grupo=%s AND UPPER(descricao)=%s",
            (cod_grupo, desc.upper()),
        )
        novo = cur.fetchone()
        cur.close()
        return {"success": True, "cod_sub_grupo": int(novo["cod_sub_grupo"])}
    finally:
        conn.close()


def _list_documentos_sync(
    servidor: str, banco: str, cod_grupo: int, codigo_entidade: str,
    referencia: Optional[int] = None, cod_sub_grupo: Optional[int] = None,
) -> dict:
    """`cod_grupo` é sempre a entidade PRINCIPAL (Cliente/Fornecedor/...).
    Quando quem chama não é uma entidade principal (ex.: Pedido de Venda,
    O.S. — que são anexos do Cliente, filtrados por sub-grupo + número),
    filtrar só por `referencia` não basta: um Pedido nº100 e uma O.S. nº100
    do MESMO cliente colidiriam. `cod_sub_grupo` é o filtro extra que
    desambiguiza — ver memória de projeto sobre o Gestor de Documentos."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ["gdoc.cod_grupo=%s", "gdoc.situacao_arquivo IS NULL OR gdoc.situacao_arquivo<>'D'"]
        params: list = [cod_grupo]
        if cod_grupo in _GRUPOS_CODIGO_TEXTO:
            where.append("gdoc.referencia_texto=%s")
            params.append(codigo_entidade)
        else:
            where.append("gdoc.referencia_codigo=%s")
            params.append(int(codigo_entidade))
        if cod_sub_grupo:
            where.append("gdoc.cod_sub_grupo=%s")
            params.append(cod_sub_grupo)
        if referencia:
            where.append("gdoc.referencia=%s")
            params.append(referencia)
        sql = (
            "SELECT gdoc.codigo, gdoc.cod_sub_grupo, sg.descricao AS sub_grupo, gdoc.descricao, "
            "gdoc.adicionado_por, gdoc.data, gdoc.hora, gdoc.computador, gdoc.validade, gdoc.path_origem "
            "FROM gestor_documentos gdoc "
            "LEFT JOIN gestor_docs_sub_grupos sg ON sg.cod_sub_grupo = gdoc.cod_sub_grupo "
            f"WHERE ({where[0]}) AND ({where[1]})" + ("".join(f" AND {w}" for w in where[2:]))
            + " ORDER BY gdoc.data DESC, gdoc.hora DESC"
        )
        cur.execute(sql, tuple(params))
        items = [{
            "codigo": int(r["codigo"]),
            "cod_sub_grupo": int(r["cod_sub_grupo"]) if r.get("cod_sub_grupo") is not None else None,
            "sub_grupo": (r.get("sub_grupo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "adicionado_por": (r.get("adicionado_por") or "").strip(),
            "data": r["data"].isoformat() if r.get("data") else None,
            "hora": (r.get("hora") or "").strip(),
            "computador": (r.get("computador") or "").strip(),
            "validade": r["validade"].isoformat() if r.get("validade") else None,
            "path_origem": (r.get("path_origem") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_documento_sync(
    servidor: str, banco: str, *, cod_grupo: int, cod_sub_grupo: int, codigo_entidade: str,
    descricao: str, adicionado_por: str, computador: str, conteudo: bytes, nome_arquivo: str,
    referencia: Optional[int] = None, validade: Optional[str] = None,
) -> dict:
    if cod_grupo not in _JUNCAO:
        return {"success": False, "message": "Grupo inválido."}
    if not (codigo_entidade or "").strip():
        return {"success": False, "message": "Código da entidade não informado."}
    if not (descricao or "").strip():
        return {"success": False, "message": "Defina a descrição do documento."}
    if not conteudo:
        return {"success": False, "message": "Selecione um arquivo para anexar."}

    path_base, azure_conn_str = _get_storage_config_sync(servidor, banco)
    if not path_base:
        return {"success": False, "message": "Caminho do Gestor de Documentos não definido em Controle do Sistema."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT grupo FROM gestor_docs_grupos WHERE codigo=%s", (cod_grupo,))
        grupo_row = cur.fetchone()
        cur.execute("SELECT descricao FROM gestor_docs_sub_grupos WHERE cod_sub_grupo=%s", (cod_sub_grupo,))
        sub_grupo_row = cur.fetchone()
        if not grupo_row or not sub_grupo_row:
            cur.close()
            return {"success": False, "message": "Grupo ou sub-grupo não encontrado."}

        pasta_grupo = _sanitize_path_component(grupo_row["grupo"])
        pasta_sub_grupo = _sanitize_path_component(sub_grupo_row["descricao"])
        nome_final = _sanitize_path_component(f"{codigo_entidade} - {nome_arquivo}")

        if _is_blob_target(path_base):
            if not azure_conn_str:
                cur.close()
                return {"success": False, "message": "Azure_ConnectionString não configurada em Controle do Sistema."}
            container, prefixo = _parse_blob_url(path_base)
            blob_name = "/".join(p for p in [prefixo, pasta_grupo, pasta_sub_grupo, nome_final] if p)
            try:
                service = BlobServiceClient.from_connection_string(azure_conn_str)
                blob_client = service.get_blob_client(container=container, blob=blob_name)
                blob_client.upload_blob(conteudo, overwrite=True)
                caminho_final = blob_client.url
            except AzureError as e:
                cur.close()
                return {"success": False, "message": f"Não foi possível enviar o arquivo para o Azure Blob Storage: {e}"}
        else:
            destino = Path(path_base) / pasta_grupo / pasta_sub_grupo
            try:
                destino.mkdir(parents=True, exist_ok=True)
                arquivo_path = destino / nome_final
                arquivo_path.write_bytes(conteudo)
                caminho_final = str(arquivo_path)
            except OSError as e:
                cur.close()
                return {"success": False, "message": f"Não foi possível gravar o arquivo em '{destino}': {e}"}

        agora = datetime.now()
        is_texto = cod_grupo in _GRUPOS_CODIGO_TEXTO
        cur.execute(
            "INSERT INTO gestor_documentos (cod_grupo, cod_sub_grupo, path, descricao, path_origem, "
            "adicionado_por, data, hora, computador, referencia_texto, referencia_codigo, referencia"
            + (", validade" if validade else "") + ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s"
            + (",%s" if validade else "") + ")",
            (
                cod_grupo, cod_sub_grupo, caminho_final, descricao.strip(), nome_arquivo,
                (adicionado_por or "").strip().upper(), agora.date(), agora.strftime("%H:%M:%S"),
                (computador or "").strip(),
                codigo_entidade if is_texto else None,
                None if is_texto else int(codigo_entidade),
                referencia or None,
            ) + ((validade,) if validade else ()),
        )
        conn.commit()
        cur.execute("SELECT @@IDENTITY AS codigo")
        cod_gestor = int(cur.fetchone()["codigo"])

        tabela_junc, col_codigo = _JUNCAO[cod_grupo]
        cur.execute(
            f"INSERT INTO {tabela_junc} ({col_codigo}, cod_gestor) VALUES (%s,%s)",
            (codigo_entidade, cod_gestor),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Documento anexado com sucesso.", "codigo": cod_gestor}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao anexar: {e}"}
    finally:
        conn.close()


def _delete_documento_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cod_grupo, referencia_codigo, referencia_texto, path FROM gestor_documentos WHERE codigo=%s",
            (codigo,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Documento não encontrado."}
        cod_grupo = int(row["cod_grupo"])

        if cod_grupo == GRUPO_PRODUTO:
            # Exceção fiel ao legado: Produtos usa soft-delete, sem remover
            # arquivo nem o registro de junção — ver docstring do módulo.
            cur.execute("UPDATE gestor_documentos SET situacao_arquivo='D' WHERE codigo=%s", (codigo,))
            conn.commit()
            cur.close()
            return {"success": True, "message": "Documento removido."}

        tabela_junc, col_codigo = _JUNCAO.get(cod_grupo, (None, None))
        codigo_entidade = row["referencia_texto"] if cod_grupo in _GRUPOS_CODIGO_TEXTO else row["referencia_codigo"]
        cur.execute("DELETE FROM gestor_documentos WHERE codigo=%s", (codigo,))
        if tabela_junc and codigo_entidade is not None:
            cur.execute(f"DELETE FROM {tabela_junc} WHERE {col_codigo}=%s AND cod_gestor=%s", (codigo_entidade, codigo))
        conn.commit()

        # Remoção do arquivo físico é best-effort — se já sumiu, ou a
        # credencial/pasta mudou desde o upload, não impede a exclusão do
        # registro (mesmo raciocínio do gestor_documentos.path autodescritivo:
        # cada documento sabe como foi armazenado, local ou blob).
        stored_path = row.get("path") or ""
        if _is_blob_target(stored_path):
            try:
                _, azure_conn_str = _get_storage_config_sync(servidor, banco)
                if azure_conn_str:
                    container, blob_name = _parse_blob_url(stored_path)
                    service = BlobServiceClient.from_connection_string(azure_conn_str)
                    service.get_blob_client(container=container, blob=blob_name).delete_blob()
            except AzureError:
                pass
        elif stored_path:
            try:
                Path(stored_path).unlink(missing_ok=True)
            except OSError:
                pass

        cur.close()
        return {"success": True, "message": "Documento removido."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _get_arquivo_path_sync(servidor: str, banco: str, codigo: int) -> Optional[dict]:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT path, path_origem FROM gestor_documentos WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        cur.close()
        return row
    finally:
        conn.close()


def _baixar_blob_sync(servidor: str, banco: str, blob_url: str) -> dict:
    _, azure_conn_str = _get_storage_config_sync(servidor, banco)
    if not azure_conn_str:
        return {"success": False, "message": "Azure_ConnectionString não configurada em Controle do Sistema."}
    try:
        container, blob_name = _parse_blob_url(blob_url)
        service = BlobServiceClient.from_connection_string(azure_conn_str)
        conteudo = service.get_blob_client(container=container, blob=blob_name).download_blob().readall()
        return {"success": True, "conteudo": conteudo}
    except AzureError as e:
        return {
            "success": False,
            "message": f"Não foi possível baixar o arquivo do Azure Blob Storage: {e}. "
                       "A Connection String pode ter mudado desde que o arquivo foi anexado.",
        }


async def list_grupos(servidor, banco):
    return await asyncio.to_thread(_list_grupos_sync, servidor, banco)


async def list_sub_grupos(servidor, banco, cod_grupo):
    return await asyncio.to_thread(_list_sub_grupos_sync, servidor, banco, cod_grupo)


async def get_or_create_sub_grupo(servidor, banco, cod_grupo, descricao):
    return await asyncio.to_thread(_get_or_create_sub_grupo_sync, servidor, banco, cod_grupo, descricao)


async def list_documentos(servidor, banco, cod_grupo, codigo_entidade, referencia=None, cod_sub_grupo=None):
    return await asyncio.to_thread(
        _list_documentos_sync, servidor, banco, cod_grupo, codigo_entidade, referencia, cod_sub_grupo
    )


async def save_documento(servidor, banco, **kwargs):
    return await asyncio.to_thread(_save_documento_sync, servidor, banco, **kwargs)


async def delete_documento(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_documento_sync, servidor, banco, codigo)


async def get_arquivo_path(servidor, banco, codigo):
    return await asyncio.to_thread(_get_arquivo_path_sync, servidor, banco, codigo)


async def baixar_blob(servidor, banco, blob_url):
    return await asyncio.to_thread(_baixar_blob_sync, servidor, banco, blob_url)


def is_blob_target(path_ou_url: str) -> bool:
    return _is_blob_target(path_ou_url)

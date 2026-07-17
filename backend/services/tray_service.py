"""Integração Tray (cadastro/atualização de produto no site) — botão
"Fotografia" > "Cadastrar/Atualizar Produto no Site" do Cadastro de Produtos.

Legado: `C:\\Desenv\\VB6\\SQLSERVER\\Geral\\FrmAsoFot.frm` (Command3/Command6) chama
a DLL COM `Backon_Controllers.Controller_Tray.CadastraProdutoTray` (VB.NET,
`C:\\Desenv\\VB6\\vb.net\\APICamadas\\BackOn\\Backon.Controllers\\Controller_Tray.vb`),
que troca `consumer_key`/`consumer_secret`/`code` por um `access_token` OAuth
e faz POST HTTPS pra API da Tray (`{url_api}/products?access_token=...` pra
criar, `/products/{id}` pra atualizar, `/products/variants/` pra grade).

Credenciais já existem em `controle_aux` (achadas no legado `FrmIntTray.frm`,
já expostas em Configurações > Controle do Sistema > Integração TRAY):
`integracao_tray` (liga/desliga), `TRAY_ID_LOJA`, `TRAY_url_api`,
`TRAY_Consumer_Key`, `TRAY_Consumer_Secret`, `TRAY_code`.

Diferença deliberada do legado quanto a hospedagem de imagem: o legado
suportava Amazon S3 OU Azure Blob (`TRAY_TIPO_BLOB`), com credenciais e
bucket/pasta próprios (`TRAY_S3_*`/`TRAY_AZURE_*`) nunca migrados pra cá.
Esta migração usa SEMPRE Azure Blob, reaproveitando a MESMA
`controle_aux.Azure_ConnectionString` que o Gestor de Documentos já usa
(`gestor_documentos_service.py`) — evita introduzir um segundo conjunto de
credenciais de nuvem só pra isso. Se o produto tiver menos escopo de
hospedagem de imagem que o legado permitia (S3), é uma simplificação
deliberada, não uma lacuna descoberta depois.

**Aviso de teste**: esta integração foi implementada seguindo o contrato de
API descrito no código-fonte VB.NET (`Controller_Tray.vb`/`DAO_Tray.vb`) e o
padrão documentado publicamente da API da Tray (OAuth por `code`, endpoints
REST `/products`), mas **nunca foi exercitada contra a API real da Tray**
(sem credenciais de sandbox disponíveis neste ambiente). Antes de usar em
produção, validar o payload/resposta reais com uma loja de teste — ver
PENDENCIAS.md > "Produtos (Cadastro Completo)".
"""
import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import unquote, urlparse
from uuid import uuid4

import requests
from azure.storage.blob import BlobServiceClient

from db.connection import _open_conn

_TOKEN_CACHE: dict[str, tuple[str, datetime]] = {}  # chave "servidor|banco" -> (token, expira_em)


def _get_tray_config_sync(cur) -> dict:
    cur.execute(
        "SELECT integracao_tray, TRAY_ID_LOJA, TRAY_url_api, TRAY_Consumer_Key, "
        "TRAY_Consumer_Secret, TRAY_code, Azure_ConnectionString FROM controle_aux"
    )
    row = cur.fetchone() or {}
    return {
        "ativo": bool(row.get("integracao_tray")),
        "id_loja": (row.get("TRAY_ID_LOJA") or "").strip(),
        "url_api": (row.get("TRAY_url_api") or "").strip().rstrip("/"),
        "consumer_key": (row.get("TRAY_Consumer_Key") or "").strip(),
        "consumer_secret": (row.get("TRAY_Consumer_Secret") or "").strip(),
        "code": (row.get("TRAY_code") or "").strip(),
        "azure_conn_str": (row.get("Azure_ConnectionString") or "").strip() or None,
    }


def _get_access_token_sync(servidor: str, banco: str, cfg: dict) -> dict:
    cache_key = f"{servidor}|{banco}"
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and cached[1] > datetime.utcnow():
        return {"success": True, "access_token": cached[0]}
    if not (cfg["url_api"] and cfg["consumer_key"] and cfg["consumer_secret"] and cfg["code"]):
        return {"success": False, "message": "Integração Tray incompleta — configure URL/Consumer Key/Secret/Code em Controle do Sistema."}
    try:
        resp = requests.post(
            f"{cfg['url_api']}/auth",
            json={
                "consumer_key": cfg["consumer_key"],
                "consumer_secret": cfg["consumer_secret"],
                "code": cfg["code"],
            },
            timeout=20,
        )
        data = resp.json()
        token = data.get("access_token")
        if not token:
            return {"success": False, "message": f"Tray não retornou access_token: {data}"}
        # Tray costuma informar validade em `date_expiration_access_token` — sem
        # confiar no formato exato, usamos um TTL conservador de 2h e deixamos
        # o cache expirar cedo (uma nova troca de token é barata).
        _TOKEN_CACHE[cache_key] = (token, datetime.utcnow() + timedelta(hours=2))
        return {"success": True, "access_token": token}
    except Exception as e:
        return {"success": False, "message": f"Falha ao autenticar na Tray: {e}"}


# ---------------------------------------------------------------------------
# Upload de imagem pra Azure Blob (reaproveita a mesma connection string do
# Gestor de Documentos — ver docstring do módulo).
# ---------------------------------------------------------------------------

def _upload_imagem_blob_sync(azure_conn_str: str, container: str, nome_arquivo: str, conteudo: bytes) -> dict:
    if not azure_conn_str:
        return {"success": False, "message": "Azure_ConnectionString não configurada em Controle do Sistema."}
    try:
        service = BlobServiceClient.from_connection_string(azure_conn_str)
        blob_name = f"Produtos/Site/{uuid4().hex}-{_sanitize(nome_arquivo)}"
        client = service.get_blob_client(container=container, blob=blob_name)
        client.upload_blob(conteudo, overwrite=True)
        return {"success": True, "url": client.url}
    except Exception as e:
        return {"success": False, "message": f"Falha no upload da imagem: {e}"}


def _sanitize(nome: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nome or "arquivo")


# ---------------------------------------------------------------------------
# Payload do produto — campos essenciais confirmados no fluxo do legado
# (nome, preço, custo, estoque, peso/dimensões, EAN). Estrutura pensada pra
# ser extensível: novos campos da API Tray (categorias, atributos, SEO) podem
# ser adicionados em `_montar_payload_produto` sem mudar o resto do fluxo.
# ---------------------------------------------------------------------------

def _montar_payload_produto(produto: dict) -> dict:
    return {
        "product": {
            "name": (produto.get("descricao") or "").strip(),
            "reference": (produto.get("codigo_int") or "").strip(),
            "brand": (produto.get("marca_produto") or "").strip() or None,
            "price": float(produto.get("p_venda") or 0),
            "cost_price": float(produto.get("p_custo") or 0),
            "stock": float(produto.get("qtd") or 0),
            "weight": float(produto.get("peso_bruto") or 0),
            "width": float(produto.get("largura") or 0),
            "height": float(produto.get("altura") or 0),
            "length": float(produto.get("comprimento") or 0),
            "ean": (produto.get("codigo_bar") or "").strip() or None,
            "available": bool((produto.get("situacao") or "").strip().upper() == "A"),
        }
    }


def _cadastrar_ou_atualizar_tray_sync(
    servidor: str, banco: str, codigo_int: str, id_tray_existente: Optional[int]
) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cfg = _get_tray_config_sync(cur)
        if not cfg["ativo"]:
            cur.close()
            return {"success": False, "message": "Integração Tray desativada em Controle do Sistema."}

        token_res = _get_access_token_sync(servidor, banco, cfg)
        if not token_res["success"]:
            cur.close()
            return token_res
        token = token_res["access_token"]

        cur.execute("SELECT * FROM pecas WHERE codigo_int=%s", (codigo_int,))
        produto = cur.fetchone()
        if not produto:
            cur.close()
            return {"success": False, "message": "Produto não encontrado."}

        payload = _montar_payload_produto(produto)
        acao = "A" if id_tray_existente else "I"
        url = (
            f"{cfg['url_api']}/products/{id_tray_existente}?access_token={token}"
            if id_tray_existente
            else f"{cfg['url_api']}/products?access_token={token}"
        )
        metodo = requests.put if id_tray_existente else requests.post
        resp = metodo(url, json=payload, timeout=30)
        resp_json = {}
        try:
            resp_json = resp.json()
        except Exception:
            pass

        sucesso = resp.status_code in (200, 201)
        novo_id_tray = resp_json.get("id") or id_tray_existente or 0
        log_linha = f"{datetime.utcnow().isoformat()} [{acao}] status={resp.status_code} resp={resp_json}"

        cur.execute(
            "UPDATE pecas SET ID_TRAY=%s, log_tray = ISNULL(log_tray,'') + %s + CHAR(13)+CHAR(10) WHERE codigo_int=%s",
            (novo_id_tray, log_linha, codigo_int),
        )
        conn.commit()
        cur.close()
        if not sucesso:
            return {"success": False, "message": f"Tray respondeu {resp.status_code}: {resp_json}"}
        return {"success": True, "message": "Produto enviado à Tray.", "id_tray": novo_id_tray}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro na integração Tray: {e}"}
    finally:
        conn.close()


def _upload_imagens_pendentes_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    """Sobe pra Azure Blob as imagens do produto (via Gestor de Documentos)
    que ainda não têm PATH_NUVEM — usadas depois no envio à Tray."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cfg = _get_tray_config_sync(cur)
        cur.execute(
            "SELECT gd.codigo, gd.path, gd.descricao FROM gestor_documentos gd "
            "JOIN pecas_anexos pa ON pa.cod_gestor = gd.codigo "
            "WHERE pa.codigo_int=%s AND gd.cod_grupo=4 AND (gd.PATH_NUVEM IS NULL OR gd.PATH_NUVEM='')",
            (codigo_int,),
        )
        pendentes = cur.fetchall()
        enviados = 0
        for doc in pendentes:
            path_local = doc.get("path") or ""
            if not path_local or path_local.lower().startswith("http"):
                continue
            try:
                with open(unquote(urlparse(path_local).path or path_local), "rb") as fh:
                    conteudo = fh.read()
            except OSError:
                continue
            up = _upload_imagem_blob_sync(cfg["azure_conn_str"], "produtos-site", doc.get("descricao") or "imagem.jpg", conteudo)
            if up.get("success"):
                cur.execute("UPDATE gestor_documentos SET PATH_NUVEM=%s WHERE codigo=%s", (up["url"], doc["codigo"]))
                enviados += 1
        conn.commit()
        cur.close()
        return {"success": True, "enviados": enviados, "total": len(pendentes)}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro no upload de imagens: {e}"}
    finally:
        conn.close()


async def cadastrar_ou_atualizar_produto(servidor: str, banco: str, codigo_int: str, id_tray_existente: Optional[int] = None) -> dict:
    return await asyncio.to_thread(_cadastrar_ou_atualizar_tray_sync, servidor, banco, codigo_int, id_tray_existente)


async def upload_imagens_pendentes(servidor: str, banco: str, codigo_int: str) -> dict:
    return await asyncio.to_thread(_upload_imagens_pendentes_sync, servidor, banco, codigo_int)

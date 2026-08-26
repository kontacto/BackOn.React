"""Produtos (pecas) + Serviços — lista unificada para uso em pedidos."""
import asyncio

from db.connection import _open_conn
from services.pedido_common import _preco_promocional, TIPOS_PRECO_M2, _area_preco, _config_m2


def _list_produtos_servicos_sync(
    servidor: str, banco: str, search: str, page: int, size: int, tipo: str
) -> dict:
    """tipo: 'all' | 'P' (produto/pecas) | 'S' (servico)"""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        items: list[dict] = []
        total = 0
        like = f"%{search.strip()}%" if search else None
        offset = max(0, (page - 1) * size)

        if tipo in ("all", "P"):
            # PRODUTOS (pecas) — busca por Código Interno, Código de
            # Fábrica, Descrição, Aplicação/Observações (Descricao_Completa)
            # e Níveis (nivel1..5, classificação mercadológica), pedido
            # explícito do usuário 2026-07-20 (busca de item no Pedido
            # Geral precisava aceitar mais que só descrição/código interno
            # — ex.: buscar por "WR-245" código de fábrica não achava nada).
            # Prioriza no ORDER BY quem bate EXATO no código interno/fábrica
            # (digitar um código específico traz ele primeiro, não perdido
            # no meio de uma lista alfabética por descrição).
            where_p = ""
            order_p = "p.descricao"
            params_p: tuple = ()
            order_params_p: tuple = ()
            if like:
                termo = search.strip()
                prefix = f"{termo}%"
                where_p = (
                    "WHERE CAST(p.codigo_int AS NVARCHAR(20)) LIKE %s OR p.codigo_fab LIKE %s "
                    "OR p.descricao LIKE %s OR p.Descricao_Completa LIKE %s "
                    "OR p.nivel1 LIKE %s OR p.nivel2 LIKE %s OR p.nivel3 LIKE %s "
                    "OR p.nivel4 LIKE %s OR p.nivel5 LIKE %s"
                )
                params_p = (like,) * 9
                order_p = (
                    "CASE "
                    "WHEN UPPER(CAST(p.codigo_int AS NVARCHAR(20))) = UPPER(%s) THEN 0 "
                    "WHEN UPPER(p.codigo_fab) = UPPER(%s) THEN 1 "
                    "WHEN CAST(p.codigo_int AS NVARCHAR(20)) LIKE %s THEN 2 "
                    "WHEN p.codigo_fab LIKE %s THEN 3 "
                    "ELSE 4 END, p.descricao"
                )
                order_params_p = (termo, termo, prefix, prefix)
            cur.execute(
                f"SELECT 'P' AS tipo, p.codigo_int AS codigo, p.descricao, "
                f"       p.p_venda AS valor, p.qtd, p.reservado, p.reservado_os, p.codigo_fab, p.uni, "
                f"       p.controla_num_serie, pi.codigo AS imagem_codigo "
                f"FROM pecas p "
                f"LEFT JOIN produto_imagem pi ON pi.codigo_int = p.codigo_int AND pi.principal = 1 AND pi.situacao = 'A' "
                f"{where_p} "
                f"ORDER BY {order_p}",
                params_p + order_params_p,
            )
            for r in cur.fetchall():
                qtd = float(r.get("qtd") or 0)
                reservado = float(r.get("reservado") or 0)
                reservado_os = float(r.get("reservado_os") or 0)
                items.append({
                    "tipo": "P",
                    "codigo": (r.get("codigo") or "").strip() if isinstance(r.get("codigo"), str) else str(r.get("codigo") or ""),
                    "descricao": (r.get("descricao") or "").strip(),
                    "valor": float(r.get("valor") or 0),
                    "estoque": qtd,                       # disponível = pecas.qtd
                    "qtd": qtd,
                    "reservado": reservado,               # reservado p/ Pedido
                    "reservado_os": reservado_os,         # reservado p/ O.S.
                    "estoque_total": round(qtd + reservado + reservado_os, 3),
                    "cod_fab": (r.get("codigo_fab") or "").strip(),
                    "unidade": (r.get("uni") or "").strip(),
                    # Campo extra pro Pedido Geral (Fase B — número de série),
                    # ver PENDENCIAS.md > "Transações". O Pedido Bar e o
                    # picker de Produtos ignoram este campo, comportamento
                    # deles inalterado.
                    "controla_num_serie": bool(r.get("controla_num_serie")),
                    "imagem_codigo": int(r["imagem_codigo"]) if r.get("imagem_codigo") is not None else None,
                })

        if tipo in ("all", "S"):
            # SERVIÇOS
            where_s = ""
            params_s: tuple = ()
            if like:
                where_s = "WHERE s.descricao LIKE %s OR CAST(s.codigo AS NVARCHAR(20)) LIKE %s"
                params_s = (like, like)
            cur.execute(
                f"SELECT 'S' AS tipo, s.codigo, s.descricao, s.valor_hora AS valor "
                f"FROM servicos s {where_s} "
                f"ORDER BY s.descricao",
                params_s,
            )
            for r in cur.fetchall():
                items.append({
                    "tipo": "S",
                    "codigo": (r.get("codigo") or "").strip() if isinstance(r.get("codigo"), str) else str(r.get("codigo") or ""),
                    "descricao": (r.get("descricao") or "").strip(),
                    "valor": float(r.get("valor") or 0),
                    "estoque": None,
                })

        total = len(items)
        # Paginação em memória (BARESTEL fica abaixo de alguns milhares, ok p/ MVP).
        items_page = items[offset:offset + size]

        cur.close()
        conn.close()
        return {"success": True, "items": items_page, "total": total, "page": page, "size": size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


async def list_produtos_servicos(servidor: str, banco: str, search: str,
                                  page: int, size: int, tipo: str) -> dict:
    return await asyncio.to_thread(
        _list_produtos_servicos_sync, servidor, banco, search, page, size, tipo
    )



def _reservas_produto_sync(servidor: str, banco: str, codigo: str, tipo: str) -> dict:
    """Documentos reais que reservam a peça `codigo`.
    tipo='PED' -> Pedidos Fechados; tipo='OS' -> O.S. Abertas/Fechadas.
    Lê os ITENS dos documentos (não usa os campos agregados pecas.reservado*).
    Agrupa por documento e soma a quantidade do produto naquele documento."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if tipo == "PED":
            cur.execute(
                "SELECT i.pedido AS doc, MAX(c.nome) AS cliente, MAX(p.data) AS data, "
                "       MAX(p.situacao) AS situacao, SUM(i.qtd_pedida) AS qtd "
                "FROM pedido_venda_prod i "
                "JOIN pedido_venda p ON p.pedido = i.pedido "
                "LEFT JOIN cliente c ON c.codigo = p.cliente "
                "WHERE i.produto = %s AND p.situacao = 'F' AND ISNULL(i.item_cancelado,0)=0 "
                "GROUP BY i.pedido ORDER BY i.pedido DESC",
                (codigo,),
            )
        else:  # OS
            cur.execute(
                "SELECT i.os AS doc, MAX(c.nome) AS cliente, MAX(o.data_entrada) AS data, "
                "       MAX(o.situacao) AS situacao, SUM(i.quant) AS qtd "
                "FROM os_produto i "
                "JOIN os o ON o.codigo = i.os "
                "LEFT JOIN cliente c ON c.codigo = o.cliente "
                "WHERE i.codigo_interno = %s AND o.situacao IN ('A','F') AND ISNULL(i.item_cancelado,0)=0 "
                "GROUP BY i.os ORDER BY i.os DESC",
                (codigo,),
            )
        labels = {"A": "Aberta", "F": "Fechada", "PG": "Faturada", "C": "Cancelada"}
        items = []
        for r in cur.fetchall():
            d = r.get("data")
            sit = (r.get("situacao") or "").strip().upper()
            items.append({
                "doc": int(r.get("doc") or 0),
                "cliente": (r.get("cliente") or "").strip() or "—",
                "data": d.isoformat() if hasattr(d, "isoformat") else (str(d) if d else None),
                "situacao": sit,
                "situacao_label": labels.get(sit, sit or "—"),
                "qtd": float(r.get("qtd") or 0),
            })
        cur.close(); conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def reservas_produto(servidor: str, banco: str, codigo: str, tipo: str) -> dict:
    return await asyncio.to_thread(_reservas_produto_sync, servidor, banco, codigo, tipo)


def _preco_promocional_sync(servidor: str, banco: str, codigo: str, qtd: float) -> dict:
    """Consultada pelo frontend (`usePedidoItens.ts`) ao escolher um produto
    ou mudar a quantidade no "Adicionar Item" de qualquer Pedido, pra saber
    se uma Variação de Preço (`pecas_promocao`) se aplica agora — ver
    `pedido_common._preco_promocional` pra regra completa."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "promocao": None}
    try:
        cur = conn.cursor(as_dict=True)
        promo = _preco_promocional(cur, codigo, qtd)
        conn.commit()  # _ensure_promocao_periodo_cols pode ter alterado o schema
        cur.close()
        return {"success": True, "promocao": promo}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "promocao": None}
    finally:
        conn.close()


async def preco_promocional(servidor: str, banco: str, codigo: str, qtd: float) -> dict:
    return await asyncio.to_thread(_preco_promocional_sync, servidor, banco, codigo, qtd)


def _tipos_preco_m2_sync(servidor: str, banco: str, codigo: str) -> dict:
    """Consultada pelo Pedido Geral (`AddItemModal.tsx`) ao escolher um
    produto m²/ml/m³ — devolve os tipos de preço cadastrados pro produto
    (`pedido_common.TIPOS_PRECO_M2`), só os que têm valor > 0 na coluna
    correspondente de `pecas` (mesmo filtro do legado, `ListPrecos` em
    `frmmanpedfor.frm`), mais o flag `vidro_controla_cabeca_chapa` (decide
    se a tela mostra os campos avançados de Comprimento/Largura de Chapa).
    Ver PENDENCIAS.md > "Transações" > "Pedido Geral — Metro Quadrado"."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "vidro_controla_cabeca_chapa": False}
    try:
        cur = conn.cursor(as_dict=True)
        colunas = ", ".join(t[2] for t in TIPOS_PRECO_M2)
        cur.execute(f"SELECT {colunas} FROM pecas WHERE codigo_int=%s", (codigo,))
        row = cur.fetchone()
        vidro_chapa = _config_m2(cur)["vidro_controla_cabeca_chapa"]
        cur.close()
        if not row:
            return {"success": True, "items": [], "vidro_controla_cabeca_chapa": vidro_chapa}
        items = []
        for tipo, label, coluna_preco, _coluna_area_minima in TIPOS_PRECO_M2:
            preco = float(row.get(coluna_preco) or 0)
            if preco > 0:
                items.append({"tipo": tipo, "label": label, "preco": preco})
        return {"success": True, "items": items, "vidro_controla_cabeca_chapa": vidro_chapa}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": [], "vidro_controla_cabeca_chapa": False}
    finally:
        conn.close()


async def tipos_preco_m2(servidor: str, banco: str, codigo: str) -> dict:
    return await asyncio.to_thread(_tipos_preco_m2_sync, servidor, banco, codigo)


def _preco_m2_preview_sync(
    servidor: str, banco: str, codigo: str, tipo_preco: int, comprimento: float, largura: float,
    comprimento_chapa: float = 0, largura_chapa: float = 0, controla_num_serie: bool = False,
) -> dict:
    """Preview do preço m² (área calculada × preço do tipo escolhido) ANTES
    de incluir o item — chamada pelo "Confirmar Item" do Pedido Geral
    enquanto o usuário digita comprimento/largura, pra mostrar o valor real
    sem duplicar `_area_preco`/`ArredondaPBox` em JS (mesma lógica que o
    backend usa de verdade ao gravar, `_add_item_completo_sync`)."""
    tipo_m2 = next((t for t in TIPOS_PRECO_M2 if t[0] == tipo_preco), None)
    if not tipo_m2:
        return {"success": False, "message": "Tipo de preço inválido.", "area_venda": 0, "valor_unitario": 0}
    _, _, coluna_preco, coluna_area_minima = tipo_m2
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "area_venda": 0, "valor_unitario": 0}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(f"SELECT {coluna_preco} AS preco FROM pecas WHERE codigo_int=%s", (codigo,))
        preco_row = cur.fetchone()
        preco_tipo = float((preco_row.get("preco") if preco_row else None) or 0)
        cfg_m2 = _config_m2(cur)
        cur.close()
        modo_arredondamento = 10 if controla_num_serie else 5
        area_venda = _area_preco(
            comprimento, largura, cfg_m2[coluna_area_minima], modo_arredondamento,
            comprimento_chapa or comprimento, largura_chapa or largura,
            cfg_m2["vidro_controla_cabeca_chapa"], cfg_m2["metro_quadrado_minima_metragem"],
        )
        return {"success": True, "area_venda": area_venda, "valor_unitario": round(preco_tipo * area_venda, 4)}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "area_venda": 0, "valor_unitario": 0}
    finally:
        conn.close()


async def preco_m2_preview(
    servidor: str, banco: str, codigo: str, tipo_preco: int, comprimento: float, largura: float,
    comprimento_chapa: float = 0, largura_chapa: float = 0, controla_num_serie: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _preco_m2_preview_sync, servidor, banco, codigo, tipo_preco, comprimento, largura,
        comprimento_chapa, largura_chapa, controla_num_serie,
    )

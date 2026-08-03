"""Cotação de Compra (Transações > Gestão de Compras > Compra). Aba
"Cotações" do `FrmGesCom.frm` — **nunca foi desenvolvida no legado**
(`Tab(1).ControlCount = 0` no próprio `.frm`, confirmado direto no
source). Construída do zero a partir de anotações manuscritas do usuário
("Projeto em Andamento — Compras Mapa de Cotação", datado 03/05/2013,
recuperadas do histórico da sessão e transcritas — ver PENDENCIAS.md >
"Gestão de Compras" > "Cotação" pro texto completo) — não há `.frm` pra
rastrear campo-a-campo aqui, todo o desenho abaixo é novo.

Fluxo (confirmado com o usuário via pergunta direta, 2026-07-18):
  1. Cria-se uma Cotação com um ou mais itens (produtos) a cotar.
  2. Para cada item, lança-se manualmente a resposta de cada fornecedor
     consultado (valor, marca, prazo, condição de pagamento) — o envio da
     solicitação ao fornecedor continua fora do sistema por enquanto
     (telefone/e-mail/WhatsApp externos); **envio automático de e-mail
     com planilha anexa foi confirmado como FORA de escopo** desta rodada
     (não existe infraestrutura de SMTP real no backend hoje, só campos
     de configuração salvos e nunca usados para enviar).
  3. Marca-se o fornecedor vencedor por item (menor preço/melhores
     condições).
  4. Finaliza-se a cotação. **Não gera Pedido de Compra formal** — essa
     tela está deliberadamente parada nesta migração (ver PENDENCIAS.md);
     o vencedor fica só registrado como decisão de compra, coerente com o
     racional já confirmado pelo usuário de que os clientes reais usam a
     futura importação de XML de NF de entrada em vez de um Pedido de
     Compra formal.

Tabelas novas (não existem no schema legado — criadas sob demanda via
`ensure_tables`, mesmo padrão já usado por `whatsapp/repository.py`):
`cotacao_compra` (cabeçalho), `cotacao_compra_item` (produtos a cotar),
`cotacao_compra_resposta` (resposta de cada fornecedor por item).

Situação da cotação (`cotacao_compra.situacao`): 'A' Aberta (em cotação),
'F' Finalizada (decisão tomada), 'C' Cancelada — mesmo vocabulário de
Requisição.

Fora de escopo desta rodada (ver PENDENCIAS.md pro detalhe): envio de
e-mail; geração de Pedido de Compra; grid de compras/produtos no cadastro
do Fornecedor; campo de % de atraso/pontualidade do fornecedor (depende
de um Pedido de Compra real que não existe); tela de Alçada de compra.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services.pedido_common import _modulo_curva_abc_ativo

_MODULO_OFF_MSG = "Módulo Curva ABC/Compras está desativado — fale com o administrador em Configurações > Módulos e Recursos."

DDL_COTACAO = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'cotacao_compra')
BEGIN
    CREATE TABLE cotacao_compra (
        codigo INT IDENTITY(1,1) PRIMARY KEY,
        data DATE NOT NULL DEFAULT CAST(GETDATE() AS DATE),
        descricao NVARCHAR(200) NULL,
        situacao CHAR(1) NOT NULL DEFAULT 'A',
        usuario INT NULL
    );
END
"""

DDL_ITEM = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'cotacao_compra_item')
BEGIN
    CREATE TABLE cotacao_compra_item (
        cod INT IDENTITY(1,1) PRIMARY KEY,
        cotacao INT NOT NULL,
        produto NVARCHAR(20) NOT NULL,
        qtd DECIMAL(15,3) NOT NULL,
        fornecedor_vencedor INT NULL,
        valor_vencedor DECIMAL(15,2) NULL
    );
    CREATE INDEX IX_cci_cotacao ON cotacao_compra_item (cotacao);
END
"""

DDL_RESPOSTA = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'cotacao_compra_resposta')
BEGIN
    CREATE TABLE cotacao_compra_resposta (
        cod INT IDENTITY(1,1) PRIMARY KEY,
        cotacao_item INT NOT NULL,
        fornecedor INT NOT NULL,
        valor_unit DECIMAL(15,2) NOT NULL,
        marca NVARCHAR(60) NULL,
        prazo NVARCHAR(60) NULL,
        cond_pagamento NVARCHAR(100) NULL,
        data_resposta DATE NOT NULL DEFAULT CAST(GETDATE() AS DATE)
    );
    CREATE INDEX IX_ccr_item ON cotacao_compra_resposta (cotacao_item);
END
"""


def _ensure_tables(cur) -> None:
    cur.execute(DDL_COTACAO)
    cur.execute(DDL_ITEM)
    cur.execute(DDL_RESPOSTA)


def _row_to_dict(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _find_produto_sync(servidor: str, banco: str, codigo: str) -> dict:
    """Busca produto (pecas: codigo_int -> codigo_fab -> codigo_bar) e devolve,
    junto, as referências que a "Autorização de Cotação" das anotações do
    usuário pede antes de cotar: custo médio, estoque atual e a última
    compra registrada (data/valor unitário)."""
    termo = (codigo or "").strip()
    if not termo:
        return {"success": True, "found": False}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "found": False}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        row = None
        for col in ("codigo_int", "codigo_fab", "codigo_bar"):
            cur.execute(
                f"SELECT codigo_int, descricao, custo_medio, qtd FROM pecas WHERE {col}=%s",
                (termo,),
            )
            row = cur.fetchone()
            if row:
                break
        if not row:
            return {"success": True, "found": False}

        codigo_int = (row.get("codigo_int") or "").strip()
        cur.execute(
            "SELECT TOP 1 nf.data_mov, nfi.qtd, nfi.qtd_un_compra, nfi.valor_total "
            "FROM n_fiscal nf JOIN n_fiscal_itens nfi ON nfi.codigo = nf.codigo "
            "WHERE nf.mov = 'E01' AND nf.situacao = 'A' AND nfi.codigo_int = %s "
            "ORDER BY nf.data_mov DESC",
            (codigo_int,),
        )
        ultima = cur.fetchone()
        ultima_compra_data, ultima_compra_valor = None, None
        if ultima:
            qtd_total = float(ultima.get("qtd") or 0) * float(ultima.get("qtd_un_compra") or 1)
            if qtd_total:
                ultima_compra_valor = float(ultima.get("valor_total") or 0) / qtd_total
            data_mov = ultima.get("data_mov")
            ultima_compra_data = data_mov.isoformat() if hasattr(data_mov, "isoformat") else data_mov

        return {
            "success": True, "found": True,
            "codigo": codigo_int,
            "descricao": (row.get("descricao") or "").strip(),
            "custo_medio": float(row.get("custo_medio") or 0),
            "estoque": float(row.get("qtd") or 0),
            "ultima_compra_data": ultima_compra_data,
            "ultima_compra_valor": ultima_compra_valor,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "found": False}
    finally:
        conn.close()


def _list_cotacoes_sync(
    servidor: str, banco: str,
    situacoes: Optional[list] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    descricao: Optional[str] = None,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        conn.commit()

        where = []
        params: list = []
        situacoes = [s for s in (situacoes or []) if s]
        if situacoes:
            placeholders = ",".join(["%s"] * len(situacoes))
            where.append(f"c.situacao IN ({placeholders})")
            params.extend(situacoes)
        if data_ini:
            where.append("c.data >= %s")
            params.append(data_ini)
        if data_fim:
            where.append("c.data <= %s")
            params.append(data_fim)
        if descricao:
            where.append("c.descricao LIKE %s")
            params.append(f"%{descricao.strip()}%")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        cur.execute(
            "SELECT c.codigo, c.data, c.descricao, c.situacao, "
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS usuario_nome, "
            "(SELECT COUNT(*) FROM cotacao_compra_item WHERE cotacao=c.codigo) AS total_itens, "
            "(SELECT COUNT(*) FROM cotacao_compra_item WHERE cotacao=c.codigo AND fornecedor_vencedor IS NOT NULL) AS total_decididos "
            "FROM cotacao_compra c LEFT JOIN funcionarios f ON f.codigo_int = c.usuario "
            f"{where_sql} ORDER BY c.codigo DESC",
            tuple(params),
        )
        items = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _get_cotacao_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        conn.commit()

        cur.execute(
            "SELECT c.codigo, c.data, c.descricao, c.situacao, "
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS usuario_nome "
            "FROM cotacao_compra c LEFT JOIN funcionarios f ON f.codigo_int = c.usuario "
            "WHERE c.codigo=%s",
            (codigo,),
        )
        cot = cur.fetchone()
        if not cot:
            return {"success": False, "message": "Cotação não encontrada."}

        cur.execute(
            "SELECT ci.cod, ci.produto, ci.qtd, ci.fornecedor_vencedor, ci.valor_vencedor, "
            "p.descricao AS produto_descricao, "
            "COALESCE(NULLIF(fv.fantasia,''), fv.nome) AS fornecedor_vencedor_nome "
            "FROM cotacao_compra_item ci "
            "LEFT JOIN pecas p ON p.codigo_int = ci.produto "
            "LEFT JOIN fornecedor fv ON fv.codigo_int = ci.fornecedor_vencedor "
            "WHERE ci.cotacao=%s ORDER BY ci.cod",
            (codigo,),
        )
        itens = [_row_to_dict(r) for r in cur.fetchall()]

        if itens:
            ids = [it["cod"] for it in itens]
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                "SELECT cr.cod, cr.cotacao_item, cr.fornecedor, cr.valor_unit, cr.marca, "
                "cr.prazo, cr.cond_pagamento, cr.data_resposta, "
                "COALESCE(NULLIF(f.fantasia,''), f.nome) AS fornecedor_nome "
                "FROM cotacao_compra_resposta cr JOIN fornecedor f ON f.codigo_int = cr.fornecedor "
                f"WHERE cr.cotacao_item IN ({placeholders}) ORDER BY cr.valor_unit ASC",
                tuple(ids),
            )
            respostas_por_item: dict = {}
            for r in cur.fetchall():
                rd = _row_to_dict(r)
                respostas_por_item.setdefault(rd["cotacao_item"], []).append(rd)
            for it in itens:
                it["respostas"] = respostas_por_item.get(it["cod"], [])

        cur.close()
        out = _row_to_dict(cot)
        out["itens"] = itens
        return {"success": True, "item": out}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _incluir_item_sync(
    servidor: str, banco: str, codigo: Optional[int], descricao: str,
    produto: str, qtd: float, usuario: Optional[int],
) -> dict:
    produto = (produto or "").strip()
    if not produto:
        return {"success": False, "message": "Informe o produto."}
    if not qtd or qtd <= 0:
        return {"success": False, "message": "Informe uma quantidade válida."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)

        if codigo:
            cur.execute("SELECT situacao FROM cotacao_compra WHERE codigo=%s", (codigo,))
            cot = cur.fetchone()
            if not cot:
                return {"success": False, "message": "Cotação não encontrada."}
            if (cot.get("situacao") or "A") != "A":
                return {"success": False, "message": "Só é possível incluir itens em cotações Abertas."}
        else:
            cur.execute(
                "INSERT INTO cotacao_compra (data, descricao, usuario, situacao) "
                "OUTPUT INSERTED.codigo "
                "VALUES (CONVERT(date, GETDATE()), %s, %s, 'A')",
                (descricao, usuario),
            )
            codigo = int(cur.fetchone()["codigo"])

        cur.execute("SELECT TOP 1 1 AS ok FROM pecas WHERE codigo_int=%s", (produto,))
        if not cur.fetchone():
            conn.rollback()
            return {"success": False, "message": "Produto não cadastrado."}

        cur.execute(
            "INSERT INTO cotacao_compra_item (cotacao, produto, qtd) "
            "OUTPUT INSERTED.cod "
            "VALUES (%s, %s, %s)",
            (codigo, produto, qtd),
        )
        cod_item = int(cur.fetchone()["cod"])

        conn.commit()
        cur.close()
        return {"success": True, "message": "Item incluído.", "codigo": codigo, "cod_item": cod_item}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _excluir_item_sync(servidor: str, banco: str, cod_item: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute(
            "SELECT ci.cotacao, c.situacao FROM cotacao_compra_item ci "
            "JOIN cotacao_compra c ON c.codigo = ci.cotacao WHERE ci.cod=%s",
            (cod_item,),
        )
        item = cur.fetchone()
        if not item:
            return {"success": False, "message": "Item não encontrado."}
        if (item.get("situacao") or "A") != "A":
            return {"success": False, "message": "Só é possível excluir itens de cotações Abertas."}

        cur.execute("DELETE FROM cotacao_compra_resposta WHERE cotacao_item=%s", (cod_item,))
        cur.execute("DELETE FROM cotacao_compra_item WHERE cod=%s", (cod_item,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Item excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _incluir_resposta_sync(
    servidor: str, banco: str, cotacao_item: int, fornecedor: int, valor_unit: float,
    marca: Optional[str], prazo: Optional[str], cond_pagamento: Optional[str],
) -> dict:
    if not fornecedor:
        return {"success": False, "message": "Informe o fornecedor."}
    if valor_unit is None or valor_unit <= 0:
        return {"success": False, "message": "Informe um valor unitário válido."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute(
            "SELECT ci.cod, c.situacao FROM cotacao_compra_item ci "
            "JOIN cotacao_compra c ON c.codigo = ci.cotacao WHERE ci.cod=%s",
            (cotacao_item,),
        )
        item = cur.fetchone()
        if not item:
            return {"success": False, "message": "Item da cotação não encontrado."}
        if (item.get("situacao") or "A") != "A":
            return {"success": False, "message": "Só é possível lançar respostas em cotações Abertas."}

        cur.execute("SELECT TOP 1 1 AS ok FROM fornecedor WHERE codigo_int=%s", (fornecedor,))
        if not cur.fetchone():
            conn.rollback()
            return {"success": False, "message": "Fornecedor não cadastrado."}

        cur.execute(
            "INSERT INTO cotacao_compra_resposta "
            "(cotacao_item, fornecedor, valor_unit, marca, prazo, cond_pagamento) "
            "OUTPUT INSERTED.cod "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (cotacao_item, fornecedor, valor_unit, marca, prazo, cond_pagamento),
        )
        cod_resposta = int(cur.fetchone()["cod"])

        conn.commit()
        cur.close()
        return {"success": True, "message": "Resposta lançada.", "cod_resposta": cod_resposta}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _excluir_resposta_sync(servidor: str, banco: str, cod_resposta: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute(
            "SELECT cr.cotacao_item, c.situacao FROM cotacao_compra_resposta cr "
            "JOIN cotacao_compra_item ci ON ci.cod = cr.cotacao_item "
            "JOIN cotacao_compra c ON c.codigo = ci.cotacao WHERE cr.cod=%s",
            (cod_resposta,),
        )
        resp = cur.fetchone()
        if not resp:
            return {"success": False, "message": "Resposta não encontrada."}
        if (resp.get("situacao") or "A") != "A":
            return {"success": False, "message": "Só é possível excluir respostas de cotações Abertas."}

        cur.execute(
            "UPDATE cotacao_compra_item SET fornecedor_vencedor=NULL, valor_vencedor=NULL "
            "WHERE cod=%s AND fornecedor_vencedor = (SELECT fornecedor FROM cotacao_compra_resposta WHERE cod=%s)",
            (resp["cotacao_item"], cod_resposta),
        )
        cur.execute("DELETE FROM cotacao_compra_resposta WHERE cod=%s", (cod_resposta,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Resposta excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _marcar_vencedor_sync(servidor: str, banco: str, cod_resposta: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute(
            "SELECT cr.cotacao_item, cr.fornecedor, cr.valor_unit, c.situacao "
            "FROM cotacao_compra_resposta cr "
            "JOIN cotacao_compra_item ci ON ci.cod = cr.cotacao_item "
            "JOIN cotacao_compra c ON c.codigo = ci.cotacao WHERE cr.cod=%s",
            (cod_resposta,),
        )
        resp = cur.fetchone()
        if not resp:
            return {"success": False, "message": "Resposta não encontrada."}
        if (resp.get("situacao") or "A") != "A":
            return {"success": False, "message": "Só é possível marcar vencedor em cotações Abertas."}

        cur.execute(
            "UPDATE cotacao_compra_item SET fornecedor_vencedor=%s, valor_vencedor=%s WHERE cod=%s",
            (resp["fornecedor"], resp["valor_unit"], resp["cotacao_item"]),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Fornecedor vencedor marcado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _finalizar_cotacao_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute("SELECT situacao FROM cotacao_compra WHERE codigo=%s", (codigo,))
        cot = cur.fetchone()
        if not cot:
            return {"success": False, "message": "Cotação não encontrada."}
        if (cot.get("situacao") or "") != "A":
            return {"success": False, "message": "Disponível somente para cotações em Aberto."}

        cur.execute("SELECT TOP 1 1 AS ok FROM cotacao_compra_item WHERE cotacao=%s", (codigo,))
        if not cur.fetchone():
            return {"success": False, "message": "Inclua ao menos um item antes de finalizar."}

        cur.execute("UPDATE cotacao_compra SET situacao='F' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Cotação finalizada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _reabrir_cotacao_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute("SELECT situacao FROM cotacao_compra WHERE codigo=%s", (codigo,))
        cot = cur.fetchone()
        if not cot:
            return {"success": False, "message": "Cotação não encontrada."}
        if (cot.get("situacao") or "") != "F":
            return {"success": False, "message": "Disponível somente para cotações Finalizadas."}

        cur.execute("UPDATE cotacao_compra SET situacao='A' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Cotação reaberta."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _cancelar_cotacao_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute("SELECT situacao FROM cotacao_compra WHERE codigo=%s", (codigo,))
        cot = cur.fetchone()
        if not cot:
            return {"success": False, "message": "Cotação não encontrada."}
        if (cot.get("situacao") or "") == "C":
            return {"success": False, "message": "Esta cotação já foi cancelada."}

        cur.execute("UPDATE cotacao_compra SET situacao='C' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Cotação cancelada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def find_produto(servidor: str, banco: str, codigo: str) -> dict:
    return await asyncio.to_thread(_find_produto_sync, servidor, banco, codigo)


async def list_cotacoes(
    servidor: str, banco: str,
    situacoes: Optional[list] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    descricao: Optional[str] = None,
) -> dict:
    return await asyncio.to_thread(_list_cotacoes_sync, servidor, banco, situacoes, data_ini, data_fim, descricao)


async def get_cotacao(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_cotacao_sync, servidor, banco, codigo)


async def incluir_item(
    servidor: str, banco: str, codigo: Optional[int], descricao: str,
    produto: str, qtd: float, usuario: Optional[int],
) -> dict:
    return await asyncio.to_thread(_incluir_item_sync, servidor, banco, codigo, descricao, produto, qtd, usuario)


async def excluir_item(servidor: str, banco: str, cod_item: int) -> dict:
    return await asyncio.to_thread(_excluir_item_sync, servidor, banco, cod_item)


async def incluir_resposta(
    servidor: str, banco: str, cotacao_item: int, fornecedor: int, valor_unit: float,
    marca: Optional[str], prazo: Optional[str], cond_pagamento: Optional[str],
) -> dict:
    return await asyncio.to_thread(
        _incluir_resposta_sync, servidor, banco, cotacao_item, fornecedor, valor_unit, marca, prazo, cond_pagamento
    )


async def excluir_resposta(servidor: str, banco: str, cod_resposta: int) -> dict:
    return await asyncio.to_thread(_excluir_resposta_sync, servidor, banco, cod_resposta)


async def marcar_vencedor(servidor: str, banco: str, cod_resposta: int) -> dict:
    return await asyncio.to_thread(_marcar_vencedor_sync, servidor, banco, cod_resposta)


async def finalizar_cotacao(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_finalizar_cotacao_sync, servidor, banco, codigo)


async def reabrir_cotacao(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_reabrir_cotacao_sync, servidor, banco, codigo)


async def cancelar_cotacao(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_cancelar_cotacao_sync, servidor, banco, codigo)

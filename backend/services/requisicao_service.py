"""Requisição (Transações > Movimentações) — pedido interno de
produtos/serviços com fechamento (baixa de estoque), reabertura e
cancelamento. Legado: `FrmManReq.frm` (colado completo pelo usuário).
Tabelas: `requisicao`, `rec_prod` (mais leitura/escrita cruzada em
`pecas`/`servicos`/`movimentacao`, iguais ao legado).

Estado da requisição (`requisicao.situacao`): 'A' Aberta, 'F' Fechada
(estoque já baixado), 'C' Cancelada.

Decisões conscientes em relação ao `.frm` original (não re-derivar do
zero numa sessão futura — ver PENDENCIAS.md > "Movimentações" pro
detalhe completo):
  • **O fluxo de autorização em 2 etapas (`Frame6`/`Grid_Prod_Man`/
    `Command19`, variável `Autoriza` 1/2/3) é código MORTO no próprio
    `.frm`** — `PrepGrid_Prod_Man` é definida mas nunca chamada por
    nenhum botão ativo; `Command14` ("Fechar") chama `FechaRequisicao`
    diretamente, sem passar por nenhuma etapa de autorização. Não
    implementado porque não roda nem no legado hoje.
  • **NFe de Requisição/Devolução** (`Command17`/`Command25`/`Command26`,
    tabela `requisicao_config_nfe`, `FrmTraNFe.ImportaRequisicao`) — fora
    de escopo, esta migração ainda não tem nenhuma emissão fiscal.
  • **Vínculo com O.S.** (`Campo(0)`/`Campo(4)`, tabela `os_requisicao`) —
    fora de escopo, a tela "O.S. Completa" desta migração ainda não
    existe. Toda requisição criada aqui é avulsa (`tipo_mov_requisicao`/
    `codigo_requisicao` ficam NULL).
  • **Vínculo com Projeto** (`ExisteDAVProjeto`) — não existe conceito de
    "Gestor de Projetos" ligado a Requisição nesta migração; guarda não
    replicada.
  • **"Senha superior" quando qtd requisitada > estoque** — não existe
    infra de senha de gerente nesta migração; o aviso é feito no
    FRONTEND (confirma antes de enviar), não bloqueia no backend.
  • **"Gerar Planilha"/Excel da lista** — não implementado nesta rodada
    (não pedido explicitamente); Cilindros > Borderô já tem o padrão de
    export via SheetJS se for pedido depois.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _row_to_dict(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _find_item_sync(servidor: str, banco: str, codigo: str) -> dict:
    """Busca produto (pecas: codigo_int -> codigo_fab -> codigo_bar) e,
    não achando, serviço (servicos: codigo) — mesma cascata de
    `Campo_LostFocus(1)` no `.frm`."""
    termo = (codigo or "").strip()
    if not termo:
        return {"success": True, "found": False}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "found": False}
    try:
        cur = conn.cursor(as_dict=True)
        for col in ("codigo_int", "codigo_fab", "codigo_bar"):
            cur.execute(
                f"SELECT codigo_int, descricao, p_custo, qtd FROM pecas WHERE {col}=%s",
                (termo,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "success": True, "found": True, "tipo": "P",
                    "codigo": (row.get("codigo_int") or "").strip(),
                    "descricao": (row.get("descricao") or "").strip(),
                    "preco": float(row.get("p_custo") or 0),
                    "estoque": float(row.get("qtd") or 0),
                }
        cur.execute(
            "SELECT codigo, descricao, valor_hora FROM servicos WHERE codigo=%s",
            (termo,),
        )
        row = cur.fetchone()
        if row:
            return {
                "success": True, "found": True, "tipo": "S",
                "codigo": (row.get("codigo") or "").strip() if isinstance(row.get("codigo"), str) else str(row.get("codigo") or ""),
                "descricao": (row.get("descricao") or "").strip(),
                "preco": float(row.get("valor_hora") or 0),
                "estoque": None,
            }
        return {"success": True, "found": False}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "found": False}
    finally:
        conn.close()


def _list_requisicoes_sync(
    servidor: str, banco: str,
    situacoes: Optional[list] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    descricao: Optional[str] = None, usuario: Optional[str] = None,
    produto: Optional[str] = None,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        situacoes = [s for s in (situacoes or []) if s]
        if situacoes:
            placeholders = ",".join(["%s"] * len(situacoes))
            where.append(f"r.situacao IN ({placeholders})")
            params.extend(situacoes)
        if data_ini:
            where.append("r.data >= %s")
            params.append(data_ini)
        if data_fim:
            where.append("r.data <= %s")
            params.append(data_fim)
        if descricao:
            where.append("r.descricao LIKE %s")
            params.append(f"%{descricao.strip()}%")
        if usuario:
            where.append(
                "r.usuario IN (SELECT codigo_int FROM funcionarios WHERE nome_guerra LIKE %s OR nome LIKE %s)"
            )
            params.extend([f"%{usuario.strip()}%", f"%{usuario.strip()}%"])
        if produto:
            where.append("r.codigo IN (SELECT requisicao FROM rec_prod WHERE prod=%s)")
            params.append(produto.strip())
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        cur.execute(
            "SELECT r.codigo, r.data, r.descricao, r.situacao, "
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS usuario_nome, "
            "(SELECT ISNULL(SUM(qtd*p_unit),0) FROM rec_prod WHERE requisicao=r.codigo) AS total "
            "FROM requisicao r LEFT JOIN funcionarios f ON f.codigo_int = r.usuario "
            f"{where_sql} ORDER BY r.codigo DESC",
            tuple(params),
        )
        items = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _get_requisicao_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT r.codigo, r.data, r.descricao, r.situacao, r.nfe, "
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS usuario_nome "
            "FROM requisicao r LEFT JOIN funcionarios f ON f.codigo_int = r.usuario "
            "WHERE r.codigo=%s",
            (codigo,),
        )
        req = cur.fetchone()
        if not req:
            return {"success": False, "message": "Requisição não encontrada."}
        cur.execute(
            "SELECT rp.cod, rp.prod, rp.qtd, rp.p_unit, "
            "COALESCE(p.descricao, s.descricao) AS descricao "
            "FROM rec_prod rp "
            "LEFT JOIN pecas p ON p.codigo_int = rp.prod "
            "LEFT JOIN servicos s ON s.codigo = rp.prod "
            "WHERE rp.requisicao=%s ORDER BY rp.cod",
            (codigo,),
        )
        itens = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        out = _row_to_dict(req)
        out["itens"] = itens
        return {"success": True, "item": out}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _incluir_item_sync(
    servidor: str, banco: str, codigo: Optional[int], descricao: str,
    produto: str, qtd: float, p_unit: float, usuario: Optional[int],
) -> dict:
    produto = (produto or "").strip()
    if not produto:
        return {"success": False, "message": "Informe o produto ou serviço."}
    if not qtd or qtd <= 0:
        return {"success": False, "message": "Informe uma quantidade válida."}
    if p_unit is None or p_unit < 0:
        return {"success": False, "message": "Preço unitário inválido."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        if codigo:
            cur.execute("SELECT situacao FROM requisicao WHERE codigo=%s", (codigo,))
            req = cur.fetchone()
            if not req:
                return {"success": False, "message": "Requisição não encontrada."}
            if (req.get("situacao") or "A") != "A":
                return {"success": False, "message": "Só é possível incluir itens em requisições Abertas."}
        else:
            cur.execute(
                "INSERT INTO requisicao (data, descricao, usuario, situacao) "
                "OUTPUT INSERTED.codigo "
                "VALUES (CONVERT(date, GETDATE()), %s, %s, 'A')",
                (descricao, usuario),
            )
            codigo = int(cur.fetchone()["codigo"])

        cur.execute(
            "SELECT TOP 1 1 AS ok FROM pecas WHERE codigo_int=%s "
            "UNION ALL SELECT TOP 1 1 FROM servicos WHERE codigo=%s",
            (produto, produto),
        )
        if not cur.fetchone():
            conn.rollback()
            return {"success": False, "message": "Produto ou serviço não cadastrado."}

        cur.execute(
            "INSERT INTO rec_prod (requisicao, prod, qtd, p_unit) "
            "OUTPUT INSERTED.cod "
            "VALUES (%s, %s, %s, %s)",
            (codigo, produto, qtd, p_unit),
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
        cur.execute(
            "SELECT rp.requisicao, r.situacao FROM rec_prod rp "
            "JOIN requisicao r ON r.codigo = rp.requisicao WHERE rp.cod=%s",
            (cod_item,),
        )
        item = cur.fetchone()
        if not item:
            return {"success": False, "message": "Item não encontrado."}
        if (item.get("situacao") or "A") != "A":
            return {"success": False, "message": "Só é possível excluir itens de requisições Abertas."}

        cur.execute("DELETE FROM rec_prod WHERE cod=%s", (cod_item,))
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


def _fechar_requisicao_sync(servidor: str, banco: str, codigo: int, usuario: Optional[int]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM requisicao WHERE codigo=%s", (codigo,))
        req = cur.fetchone()
        if not req:
            return {"success": False, "message": "Requisição não encontrada."}
        if (req.get("situacao") or "") != "A":
            return {"success": False, "message": "Disponível somente para requisições em Aberto."}

        cur.execute("SELECT prod, qtd, p_unit FROM rec_prod WHERE requisicao=%s", (codigo,))
        itens = cur.fetchall()
        if not itens:
            return {"success": False, "message": "Inclua ao menos um item antes de fechar."}

        for it in itens:
            prod = (it.get("prod") or "").strip()
            qtd = float(it.get("qtd") or 0)
            p_unit = float(it.get("p_unit") or 0)
            cur.execute("UPDATE pecas SET qtd = qtd - %s WHERE codigo_int=%s", (qtd, prod))
            cur.execute(
                "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, p_unit, num_nf, serie_nf, vendedor) "
                "VALUES (CONVERT(date, GETDATE()), 'S07', %s, %s, %s, %s, 'RQ', %s)",
                (prod, qtd, p_unit, codigo, usuario),
            )

        cur.execute("UPDATE requisicao SET situacao='F' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Requisição fechada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _reabrir_requisicao_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao, nfe FROM requisicao WHERE codigo=%s", (codigo,))
        req = cur.fetchone()
        if not req:
            return {"success": False, "message": "Requisição não encontrada."}
        if (req.get("situacao") or "") != "F":
            return {"success": False, "message": "Disponível somente para requisições Fechadas."}
        if req.get("nfe"):
            return {"success": False, "message": "Requisição com NFe emitida. Cancele a NFe primeiro."}

        cur.execute("SELECT prod, qtd FROM rec_prod WHERE requisicao=%s", (codigo,))
        itens = cur.fetchall()
        for it in itens:
            prod = (it.get("prod") or "").strip()
            qtd = float(it.get("qtd") or 0)
            cur.execute("UPDATE pecas SET qtd = qtd + %s WHERE codigo_int=%s", (qtd, prod))

        cur.execute("DELETE FROM movimentacao WHERE num_nf=%s AND serie_nf='RQ'", (codigo,))
        cur.execute(
            "UPDATE requisicao SET situacao='A', usr_aprova1=NULL, dt_aprova1=NULL WHERE codigo=%s",
            (codigo,),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Requisição reaberta."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _cancelar_requisicao_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM requisicao WHERE codigo=%s", (codigo,))
        req = cur.fetchone()
        if not req:
            return {"success": False, "message": "Requisição não encontrada."}
        situacao = req.get("situacao") or ""
        if situacao == "C":
            return {"success": False, "message": "Esta requisição já foi cancelada."}

        if situacao == "F":
            cur.execute("SELECT prod, qtd FROM rec_prod WHERE requisicao=%s", (codigo,))
            for it in cur.fetchall():
                prod = (it.get("prod") or "").strip()
                qtd = float(it.get("qtd") or 0)
                cur.execute("UPDATE pecas SET qtd = qtd + %s WHERE codigo_int=%s", (qtd, prod))

        cur.execute("UPDATE requisicao SET situacao='C' WHERE codigo=%s", (codigo,))
        cur.execute("DELETE FROM movimentacao WHERE num_nf=%s AND serie_nf='RQ'", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Requisição cancelada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def find_item(servidor: str, banco: str, codigo: str) -> dict:
    return await asyncio.to_thread(_find_item_sync, servidor, banco, codigo)


async def list_requisicoes(
    servidor: str, banco: str,
    situacoes: Optional[list] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    descricao: Optional[str] = None, usuario: Optional[str] = None,
    produto: Optional[str] = None,
) -> dict:
    return await asyncio.to_thread(
        _list_requisicoes_sync, servidor, banco, situacoes, data_ini, data_fim, descricao, usuario, produto
    )


async def get_requisicao(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_requisicao_sync, servidor, banco, codigo)


async def incluir_item(
    servidor: str, banco: str, codigo: Optional[int], descricao: str,
    produto: str, qtd: float, p_unit: float, usuario: Optional[int],
) -> dict:
    return await asyncio.to_thread(
        _incluir_item_sync, servidor, banco, codigo, descricao, produto, qtd, p_unit, usuario
    )


async def excluir_item(servidor: str, banco: str, cod_item: int) -> dict:
    return await asyncio.to_thread(_excluir_item_sync, servidor, banco, cod_item)


async def fechar_requisicao(servidor: str, banco: str, codigo: int, usuario: Optional[int]) -> dict:
    return await asyncio.to_thread(_fechar_requisicao_sync, servidor, banco, codigo, usuario)


async def reabrir_requisicao(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_reabrir_requisicao_sync, servidor, banco, codigo)


async def cancelar_requisicao(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_cancelar_requisicao_sync, servidor, banco, codigo)

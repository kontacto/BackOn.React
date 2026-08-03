"""Pedido de Compra (Transações > Gestão de Compras > Compra). Legado:
`FrmPedCom.frm` ("Cadastro de Pedido de Compra de Material"), colado
completo pelo usuário e recuperado do histórico da sessão para retomar
este trabalho — rastreado por completo antes de implementar (ver
PENDENCIAS.md > "Gestão de Compras" > "Pedido de Compra" pro relatório
campo-a-campo, não re-rastrear do zero numa sessão futura).

Tabelas: `pedido` (cabeçalho) e `pedido_itens` (itens) — **já existem no
schema** (confirmado ao vivo em GERDELL/BARESTELA, 0 linhas — mesmas
tabelas usadas pelas variantes Revenda/ValPorto/KIFESTA do `.frm`), não
são criadas por esta migração. `pedido_itens.SEQUENCIA_PEDIDO_ITENS` é o
PK real de cada linha (IDENTITY) — `codigo`+`codigo_int` NÃO é chave
única (o legado permite lançar o mesmo produto mais de uma vez, cada
lançamento tem sua própria pergunta "já existe, quer alterar?"; aqui cada
inclusão sempre cria uma linha nova, edição é uma ação própria por
`SEQUENCIA_PEDIDO_ITENS`).

Situação (`pedido.situacao`): 'A' Aberto/Em Aprovação, 'F' Aprovado, 'C'
Rejeitado. Mesmo vocabulário A/F/C de Requisição e Cotação de Compra —
**divergência consciente do texto literal do legado**: o botão
"Aprovar Pedido" (`Command21_Click`) grava `situacao='F'` mas a
`MsgBox` de confirmação do próprio legado ainda diz "Pedido fechado com
sucesso" (nome antigo do botão antes de virar "Aprovar", nunca
atualizado) — usei o sentido real do botão (Aprovar), não o texto da
mensagem obsoleta. Da mesma forma "Rejeitar Pedido" (`Command9_Click`)
grava `situacao='C'` (mesmo valor de Cancelado). `R`/`RP` (recebido
parcial/total) existem na tabela mas **nenhum botão deste form os
aciona** — pertencem a uma tela de recebimento de mercadoria que este
`.frm` não tem e que esta migração não implementa ainda (fica pra quando
a importação de XML de NF de entrada existir) — não portado.

Decisões conscientes de escopo (não re-abrir sem pedido explícito do
usuário — ver PENDENCIAS.md):
  • **"Excluir Pedido" não foi portado** — no próprio `.frm` esse botão
    está `Visible = 0 'False`, nunca aparece pro usuário (código morto).
  • **"Rateio Desp/Desc"** (`Command7`/`Command10`/`Command11` — ratear
    frete/seguro/despesas/desconto proporcionalmente entre os itens do
    pedido) não foi portado — feature real, mas secundária; os mesmos
    campos continuam editáveis diretamente por item.
  • **"Importar DAV"** (`Command14`/`Command16` — importar itens de um
    Pedido de Venda/Orçamento/O.S. existente) não foi portado — depende
    de `orc_produto` (Orçamento, que não existe nesta migração) e das
    telas "Completo" de Pedido/O.S., que ainda não têm essa integração.
  • Composição fiscal completa por item (Base/Valor de ICMS, IPI (com
    alíquota), ICMS-ST, ISS, mais frete/seguro/despesas/desconto) **foi
    incluída** — decisão explícita do usuário via pergunta direta
    (2026-07-18), mesmas colunas do schema legado (`pedido_itens`).
  • `qtd_barra`/`qtd_tijuca` (colunas existentes na tabela) não são
    usadas — nomes de filial específicos de um cliente antigo (workaround,
    não regra de negócio geral, ver "Não replicar truques VB6" no
    CLAUDE.md). `frete_fora`/`tipo_pedido`/`enviado`/`exportado` também
    não usados — sem regra de negócio documentada por trás deles no
    trecho do `.frm` disponível.
  • `pedido.resumo` (o "Histórico do pedido" do formulário) fica como um
    log textual simples, append-only, de mudanças de situação — o
    controle de quem fez o quê já é coberto pelo log de auditoria
    (`log_auditoria_service`), este campo é só o texto exibido na própria
    tela do pedido.
"""
import asyncio
from datetime import datetime
from typing import Optional

from db.connection import _open_conn
from services.pedido_common import _modulo_curva_abc_ativo

_MODULO_OFF_MSG = "Módulo Curva ABC/Compras está desativado — fale com o administrador em Configurações > Módulos e Recursos."

SIT_LABEL = {"A": "Aberto", "F": "Aprovado", "C": "Rejeitado", "R": "Recebido", "RP": "Recebido Parcial"}


def _row_to_dict(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _append_resumo(cur, codigo: int, linha: str) -> None:
    cur.execute("SELECT resumo FROM pedido WHERE codigo=%s", (codigo,))
    row = cur.fetchone()
    atual = (row.get("resumo") or "") if row else ""
    novo = f"{datetime.now().strftime('%d/%m/%Y %H:%M')} - {linha}"
    texto = f"{atual}\r\n{novo}" if atual.strip() else novo
    cur.execute("UPDATE pedido SET resumo=%s WHERE codigo=%s", (texto, codigo))


def _find_produto_sync(servidor: str, banco: str, codigo: str) -> dict:
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
            cur.execute(f"SELECT codigo_int, descricao, custo_medio, qtd FROM pecas WHERE {col}=%s", (termo,))
            row = cur.fetchone()
            if row:
                break
        if not row:
            return {"success": True, "found": False}
        return {
            "success": True, "found": True,
            "codigo": (row.get("codigo_int") or "").strip(),
            "descricao": (row.get("descricao") or "").strip(),
            "custo_medio": float(row.get("custo_medio") or 0),
            "estoque": float(row.get("qtd") or 0),
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "found": False}
    finally:
        conn.close()


def _find_fornecedor_info_sync(servidor: str, banco: str, codigo_int: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "found": False}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT nome, fantasia, prazo_pgto FROM fornecedor WHERE codigo_int=%s", (codigo_int,))
        row = cur.fetchone()
        if not row:
            return {"success": True, "found": False}
        return {
            "success": True, "found": True,
            "nome": (row.get("nome") or "").strip(),
            "fantasia": (row.get("fantasia") or "").strip(),
            "prazo_pgto": row.get("prazo_pgto"),
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "found": False}
    finally:
        conn.close()


def _list_pedidos_sync(
    servidor: str, banco: str,
    situacoes: Optional[list] = None, fornecedor: Optional[int] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None, termo: Optional[str] = None,
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
        where = []
        params: list = []
        situacoes = [s for s in (situacoes or []) if s]
        if situacoes:
            placeholders = ",".join(["%s"] * len(situacoes))
            where.append(f"p.situacao IN ({placeholders})")
            params.extend(situacoes)
        if fornecedor:
            where.append("p.fornecedor = %s")
            params.append(fornecedor)
        if data_ini:
            where.append("p.data >= %s")
            params.append(data_ini)
        if data_fim:
            where.append("p.data <= %s")
            params.append(data_fim)
        if termo:
            where.append("(p.pedido_fornecedor LIKE %s OR p.obs_pedido LIKE %s)")
            params.extend([f"%{termo.strip()}%", f"%{termo.strip()}%"])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        cur.execute(
            "SELECT p.codigo, p.data, p.situacao, p.pedido_fornecedor, p.fornecedor, "
            "COALESCE(NULLIF(f.fantasia,''), f.nome) AS fornecedor_nome, "
            "(SELECT ISNULL(SUM(qtd*p_unit),0) FROM pedido_itens WHERE codigo=p.codigo) AS total, "
            "(SELECT COUNT(*) FROM pedido_itens WHERE codigo=p.codigo) AS total_itens "
            "FROM pedido p LEFT JOIN fornecedor f ON f.codigo_int = p.fornecedor "
            f"{where_sql} ORDER BY p.codigo DESC",
            tuple(params),
        )
        items = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _get_pedido_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute(
            "SELECT p.codigo, p.data, p.situacao, p.fornecedor, p.pedido_fornecedor, p.prazo, "
            "p.forma_pagamento, p.ac_cliente, p.transportadora, p.data_entrega, p.obs_pedido, "
            "p.tipo_frete, p.resumo, "
            "COALESCE(NULLIF(f.fantasia,''), f.nome) AS fornecedor_nome "
            "FROM pedido p LEFT JOIN fornecedor f ON f.codigo_int = p.fornecedor "
            "WHERE p.codigo=%s",
            (codigo,),
        )
        ped = cur.fetchone()
        if not ped:
            return {"success": False, "message": "Pedido não encontrado."}

        cur.execute(
            "SELECT pi.SEQUENCIA_PEDIDO_ITENS AS seq, pi.codigo_int, pi.qtd, pi.qtd_un_compra, pi.p_unit, "
            "pi.base_icms, pi.valor_icms, pi.base_ipi, pi.alqt_ipi, pi.valor_ipi, "
            "pi.base_sub, pi.valor_sub, pi.base_iss, pi.valor_iss, "
            "pi.frete, pi.seguro, pi.despesas, pi.desconto, "
            "pe.descricao AS produto_descricao "
            "FROM pedido_itens pi LEFT JOIN pecas pe ON pe.codigo_int = pi.codigo_int "
            "WHERE pi.codigo=%s ORDER BY pi.SEQUENCIA_PEDIDO_ITENS",
            (codigo,),
        )
        itens = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        out = _row_to_dict(ped)
        out["itens"] = itens
        out["total"] = sum(float(it.get("qtd") or 0) * float(it.get("p_unit") or 0) for it in itens)
        return {"success": True, "item": out}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _gravar_cabecalho_sync(
    servidor: str, banco: str, codigo: Optional[int], data: str, fornecedor: int,
    pedido_fornecedor: Optional[str], prazo: Optional[int], forma_pagamento: Optional[str],
    ac_cliente: Optional[str], transportadora: Optional[str], data_entrega: Optional[str],
    obs_pedido: Optional[str], tipo_frete: int, usuario: Optional[int],
) -> dict:
    if not fornecedor:
        return {"success": False, "message": "Selecione o fornecedor."}
    if not data:
        return {"success": False, "message": "Informe a data do pedido."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}

        if codigo:
            cur.execute("SELECT situacao FROM pedido WHERE codigo=%s", (codigo,))
            ped = cur.fetchone()
            if not ped:
                return {"success": False, "message": "Pedido não encontrado."}
            if (ped.get("situacao") or "A") != "A":
                return {"success": False, "message": "Alterações não permitidas para este pedido — só pedidos em Aberto podem ser alterados."}

        cur.execute("SELECT TOP 1 1 AS ok FROM fornecedor WHERE codigo_int=%s", (fornecedor,))
        if not cur.fetchone():
            conn.rollback()
            return {"success": False, "message": "Fornecedor não cadastrado."}

        if not codigo:
            cur.execute(
                "INSERT INTO pedido (data, fornecedor, pedido_fornecedor, prazo, forma_pagamento, ac_cliente, "
                "transportadora, data_entrega, obs_pedido, tipo_frete, situacao, usuario) "
                "OUTPUT INSERTED.codigo "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'A',%s)",
                (data, fornecedor, pedido_fornecedor, prazo, forma_pagamento, ac_cliente,
                 transportadora, data_entrega, obs_pedido, tipo_frete, usuario),
            )
            codigo = int(cur.fetchone()["codigo"])
            _append_resumo(cur, codigo, "Pedido criado.")
        else:
            cur.execute(
                "UPDATE pedido SET data=%s, fornecedor=%s, pedido_fornecedor=%s, prazo=%s, forma_pagamento=%s, "
                "ac_cliente=%s, transportadora=%s, data_entrega=%s, obs_pedido=%s, tipo_frete=%s WHERE codigo=%s",
                (data, fornecedor, pedido_fornecedor, prazo, forma_pagamento, ac_cliente,
                 transportadora, data_entrega, obs_pedido, tipo_frete, codigo),
            )

        conn.commit()
        cur.close()
        return {"success": True, "message": "Pedido gravado.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


_ITEM_FIELDS = (
    "qtd_un_compra", "base_icms", "valor_icms", "base_ipi", "alqt_ipi", "valor_ipi",
    "base_sub", "valor_sub", "base_iss", "valor_iss", "frete", "seguro", "despesas", "desconto",
)


def _incluir_item_sync(servidor: str, banco: str, codigo: int, produto: str, qtd: float, p_unit: float, extras: dict) -> dict:
    produto = (produto or "").strip()
    if not produto:
        return {"success": False, "message": "Informe o produto."}
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
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT situacao FROM pedido WHERE codigo=%s", (codigo,))
        ped = cur.fetchone()
        if not ped:
            return {"success": False, "message": "Pedido não encontrado."}
        if (ped.get("situacao") or "A") != "A":
            return {"success": False, "message": "Alterações não permitidas para este pedido — só pedidos em Aberto podem ser alterados."}

        cur.execute("SELECT TOP 1 1 AS ok FROM pecas WHERE codigo_int=%s", (produto,))
        if not cur.fetchone():
            conn.rollback()
            return {"success": False, "message": "Produto não cadastrado."}

        valores = [extras.get(f) or 0 for f in _ITEM_FIELDS]
        cols = ", ".join(["codigo", "codigo_int", "qtd", "qtd_recebida", "p_unit"] + list(_ITEM_FIELDS))
        placeholders = ", ".join(["%s"] * (5 + len(_ITEM_FIELDS)))
        cur.execute(
            f"INSERT INTO pedido_itens ({cols}) OUTPUT INSERTED.SEQUENCIA_PEDIDO_ITENS VALUES ({placeholders})",
            tuple([codigo, produto, qtd, 0, p_unit] + valores),
        )
        seq = int(cur.fetchone()["SEQUENCIA_PEDIDO_ITENS"])

        conn.commit()
        cur.close()
        return {"success": True, "message": "Item incluído.", "seq": seq}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _editar_item_sync(servidor: str, banco: str, seq: int, qtd: float, p_unit: float, extras: dict) -> dict:
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
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute(
            "SELECT pi.codigo, p.situacao FROM pedido_itens pi "
            "JOIN pedido p ON p.codigo = pi.codigo WHERE pi.SEQUENCIA_PEDIDO_ITENS=%s",
            (seq,),
        )
        item = cur.fetchone()
        if not item:
            return {"success": False, "message": "Item não encontrado."}
        if (item.get("situacao") or "A") != "A":
            return {"success": False, "message": "Alterações não permitidas para este pedido — só pedidos em Aberto podem ser alterados."}

        sets = ["qtd=%s", "p_unit=%s"] + [f"{f}=%s" for f in _ITEM_FIELDS]
        valores = [qtd, p_unit] + [extras.get(f) or 0 for f in _ITEM_FIELDS]
        valores.append(seq)
        cur.execute(f"UPDATE pedido_itens SET {', '.join(sets)} WHERE SEQUENCIA_PEDIDO_ITENS=%s", tuple(valores))

        conn.commit()
        cur.close()
        return {"success": True, "message": "Item atualizado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _excluir_item_sync(servidor: str, banco: str, seq: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute(
            "SELECT pi.codigo, p.situacao FROM pedido_itens pi "
            "JOIN pedido p ON p.codigo = pi.codigo WHERE pi.SEQUENCIA_PEDIDO_ITENS=%s",
            (seq,),
        )
        item = cur.fetchone()
        if not item:
            return {"success": False, "message": "Item não encontrado."}
        if (item.get("situacao") or "A") != "A":
            return {"success": False, "message": "Alterações não permitidas para este pedido — só pedidos em Aberto podem ser alterados."}

        cur.execute("DELETE FROM pedido_itens WHERE SEQUENCIA_PEDIDO_ITENS=%s", (seq,))
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


def _aprovar_sync(servidor: str, banco: str, codigo: int, usuario_nome: Optional[str]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT situacao FROM pedido WHERE codigo=%s", (codigo,))
        ped = cur.fetchone()
        if not ped:
            return {"success": False, "message": "Pedido não encontrado."}
        situacao = ped.get("situacao") or ""
        if situacao == "C":
            return {"success": False, "message": "Pedidos rejeitados não podem ser aprovados."}
        if situacao == "F":
            return {"success": False, "message": "Este pedido já está aprovado."}

        cur.execute("SELECT TOP 1 1 AS ok FROM pedido_itens WHERE codigo=%s", (codigo,))
        if not cur.fetchone():
            return {"success": False, "message": "Inclua ao menos um item antes de aprovar."}

        cur.execute("UPDATE pedido SET situacao='F' WHERE codigo=%s", (codigo,))
        _append_resumo(cur, codigo, f"Pedido aprovado{f' por {usuario_nome}' if usuario_nome else ''}.")
        conn.commit()
        cur.close()
        return {"success": True, "message": "Pedido aprovado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _rejeitar_sync(servidor: str, banco: str, codigo: int, usuario_nome: Optional[str]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT situacao FROM pedido WHERE codigo=%s", (codigo,))
        ped = cur.fetchone()
        if not ped:
            return {"success": False, "message": "Pedido não encontrado."}
        situacao = ped.get("situacao") or ""
        if situacao == "C":
            return {"success": False, "message": "Este pedido já foi rejeitado."}
        if situacao == "F":
            return {"success": False, "message": "Pedidos já aprovados não podem ser rejeitados — reabra o pedido primeiro."}

        cur.execute("UPDATE pedido SET situacao='C' WHERE codigo=%s", (codigo,))
        _append_resumo(cur, codigo, f"Pedido rejeitado{f' por {usuario_nome}' if usuario_nome else ''}.")
        conn.commit()
        cur.close()
        return {"success": True, "message": "Pedido rejeitado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _reabrir_sync(servidor: str, banco: str, codigo: int, usuario_nome: Optional[str]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT situacao FROM pedido WHERE codigo=%s", (codigo,))
        ped = cur.fetchone()
        if not ped:
            return {"success": False, "message": "Pedido não encontrado."}
        situacao = ped.get("situacao") or ""
        if situacao == "C":
            return {"success": False, "message": "Pedidos rejeitados não podem ser reabertos."}
        if situacao == "A":
            return {"success": False, "message": "Este pedido já está aberto."}

        cur.execute("UPDATE pedido SET situacao='A' WHERE codigo=%s", (codigo,))
        _append_resumo(cur, codigo, f"Pedido reaberto{f' por {usuario_nome}' if usuario_nome else ''}.")
        conn.commit()
        cur.close()
        return {"success": True, "message": "Pedido reaberto."}
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


async def find_fornecedor_info(servidor: str, banco: str, codigo_int: int) -> dict:
    return await asyncio.to_thread(_find_fornecedor_info_sync, servidor, banco, codigo_int)


async def list_pedidos(
    servidor: str, banco: str,
    situacoes: Optional[list] = None, fornecedor: Optional[int] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None, termo: Optional[str] = None,
) -> dict:
    return await asyncio.to_thread(_list_pedidos_sync, servidor, banco, situacoes, fornecedor, data_ini, data_fim, termo)


async def get_pedido(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_pedido_sync, servidor, banco, codigo)


async def gravar_cabecalho(
    servidor: str, banco: str, codigo: Optional[int], data: str, fornecedor: int,
    pedido_fornecedor: Optional[str], prazo: Optional[int], forma_pagamento: Optional[str],
    ac_cliente: Optional[str], transportadora: Optional[str], data_entrega: Optional[str],
    obs_pedido: Optional[str], tipo_frete: int, usuario: Optional[int],
) -> dict:
    return await asyncio.to_thread(
        _gravar_cabecalho_sync, servidor, banco, codigo, data, fornecedor, pedido_fornecedor, prazo,
        forma_pagamento, ac_cliente, transportadora, data_entrega, obs_pedido, tipo_frete, usuario,
    )


async def incluir_item(servidor: str, banco: str, codigo: int, produto: str, qtd: float, p_unit: float, extras: dict) -> dict:
    return await asyncio.to_thread(_incluir_item_sync, servidor, banco, codigo, produto, qtd, p_unit, extras)


async def editar_item(servidor: str, banco: str, seq: int, qtd: float, p_unit: float, extras: dict) -> dict:
    return await asyncio.to_thread(_editar_item_sync, servidor, banco, seq, qtd, p_unit, extras)


async def excluir_item(servidor: str, banco: str, seq: int) -> dict:
    return await asyncio.to_thread(_excluir_item_sync, servidor, banco, seq)


async def aprovar(servidor: str, banco: str, codigo: int, usuario_nome: Optional[str]) -> dict:
    return await asyncio.to_thread(_aprovar_sync, servidor, banco, codigo, usuario_nome)


async def rejeitar(servidor: str, banco: str, codigo: int, usuario_nome: Optional[str]) -> dict:
    return await asyncio.to_thread(_rejeitar_sync, servidor, banco, codigo, usuario_nome)


async def reabrir(servidor: str, banco: str, codigo: int, usuario_nome: Optional[str]) -> dict:
    return await asyncio.to_thread(_reabrir_sync, servidor, banco, codigo, usuario_nome)

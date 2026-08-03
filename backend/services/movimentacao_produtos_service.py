"""Movimentação de Produtos (Transações > Movimentações) — lançamento manual
avulso de entrada/saída de estoque, fora do fluxo de Pedido/O.S./Notas
Fiscais. Legado: `frmEntPro.frm` ("Movimentação de Produtos").

Tabelas: `movimentacao`, `pecas`, `tipo_mov`. Toda linha gravada por esta
tela usa `serie_nf='MV'` — mesma convenção já em uso ao vivo no banco de
testes (confirmado via `INFORMATION_SCHEMA`/consulta direta, 2026-07-18)
para distinguir de outras origens: 'CM' = comanda/Pedido Bar, num_nf de
Nota Fiscal, etc. `Consultar`/`Excluir` desta tela só enxergam linhas
`serie_nf='MV'` — nunca tocam movimentações geradas por outra tela.

Decisões conscientes em relação ao `.frm` original (ver PENDENCIAS.md >
"Movimentações" pro detalhe completo de cada uma):
  • "Alterar" (`CmdAltera`) — o próprio legado desabilita incondicionalmente
    ("Excluir a movimentação e lançar novamente!"). Não portado.
  • "Excluir" (`CmdApaga`) — o legado mostra o mesmo aviso de "função
    desabilitada" mas o `Exit Sub` que a desabilitaria está comentado no
    código-fonte; a exclusão de fato acontece. Mantido HABILITADO aqui,
    com reversão de estoque — mesmo padrão já usado em outros pontos deste
    backend que apagam `movimentacao` e desfazem o efeito no estoque
    (`notas_fiscais_service.py`).
  • Filtro "código começa com P ou A" do Consultar do legado — não
    replicado: no schema atual `pecas.codigo_int` é 100% prefixo 'P'
    (confirmado ao vivo), e nenhum outro service deste backend aplica esse
    filtro; mais seguro não esconder produtos por um prefixo que pode não
    valer pra toda instalação.
  • Faixa de quantidade -32767..32767 do `Critica()` — era limite de tipo
    Integer/Single do VB6; as colunas atuais (`movimentacao.qtd` e
    `pecas.qtd`) são `real`/`float`, sem essa limitação. Não replicado (ver
    "Não replicar truques VB6" no CLAUDE.md).
  • Baixa automática de ingredientes via tabela `receita` quando
    tipo='E50' e `ModFatPedido` é 6 ou 41 — feature de Ficha Técnica
    amarrada a um "modelo de pedido" legado sem equivalente na arquitetura
    nova, e a tabela `receita` não foi citada pelo usuário no escopo desta
    tela. Fora de escopo — registrado em PENDENCIAS.md, não implementado.
  • `FrmManMov` (import/export de CI, "Requisição" com aprovação em lote)
    é uma tela client-exclusive, maior e distinta — fora de escopo aqui.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services.posto_common import data_movimento as _data_movimento_atual


def _row_to_dict(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _list_tipos_mov_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "tipos": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, descricao FROM tipo_mov WHERE atualiza_est='S' ORDER BY codigo"
        )
        tipos = [
            {"codigo": (r.get("codigo") or "").strip(), "descricao": (r.get("descricao") or "").strip()}
            for r in cur.fetchall()
        ]
        data_sistema = _data_movimento_atual(cur)
        cur.close()
        return {
            "success": True,
            "tipos": tipos,
            "data_sistema": data_sistema.isoformat() if data_sistema else None,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "tipos": []}
    finally:
        conn.close()


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
        cur.execute(
            "SELECT codigo_int, descricao, p_custo, qtd FROM pecas WHERE codigo_int=%s",
            (termo,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT codigo_int, descricao, p_custo, qtd FROM pecas WHERE codigo_fab=%s",
                (termo,),
            )
            row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": True, "found": False}
        return {
            "success": True,
            "found": True,
            "codigo_int": (row.get("codigo_int") or "").strip(),
            "descricao": (row.get("descricao") or "").strip(),
            "p_custo": float(row.get("p_custo") or 0),
            "qtd": float(row.get("qtd") or 0),
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "found": False}
    finally:
        conn.close()


def _list_movimentacoes_sync(
    servidor: str, banco: str,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    tipo: Optional[str] = None, codigo_int: Optional[str] = None,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        where = ["m.serie_nf='MV'"]
        params: list = []
        if data_ini:
            where.append("m.data >= %s")
            params.append(data_ini)
        if data_fim:
            where.append("m.data <= %s")
            params.append(data_fim)
        if tipo:
            where.append("m.tipo = %s")
            params.append(tipo.strip())
        if codigo_int:
            where.append("m.codigo_int = %s")
            params.append(codigo_int.strip())
        cur.execute(
            "SELECT m.id_mov, m.data, m.codigo_int, p.descricao, m.qtd, m.p_unit, "
            "m.tipo, tm.descricao AS tipo_descricao, m.num_nf "
            "FROM movimentacao m "
            "LEFT JOIN pecas p ON p.codigo_int = m.codigo_int "
            "LEFT JOIN tipo_mov tm ON tm.codigo = m.tipo "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY m.data DESC, m.id_mov DESC",
            tuple(params),
        )
        items = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _incluir_movimentacao_sync(servidor: str, banco: str, dados: dict) -> dict:
    tipo = (dados.get("tipo") or "").strip().upper()
    codigo_int = (dados.get("codigo_int") or "").strip()
    qtd = float(dados.get("qtd") or 0)
    p_unit = float(dados.get("p_unit") or 0)
    data = dados.get("data")
    num_nf = dados.get("num_nf")

    if not data:
        return {"success": False, "message": "Informe a data de entrada."}
    if not tipo:
        return {"success": False, "message": "Selecione o tipo de movimentação."}
    if not codigo_int:
        return {"success": False, "message": "Informe o produto."}
    if qtd <= 0:
        return {"success": False, "message": "Informe uma quantidade válida."}
    if p_unit < 0:
        return {"success": False, "message": "Preço unitário inválido."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        data_sistema = _data_movimento_atual(cur)
        if data_sistema and str(data) > data_sistema.isoformat():
            return {
                "success": False,
                "message": f"A data de movimentação deve ter valor máximo {data_sistema.strftime('%d/%m/%Y')}.",
            }

        cur.execute("SELECT TOP 1 1 AS ok FROM tipo_mov WHERE codigo=%s AND atualiza_est='S'", (tipo,))
        if not cur.fetchone():
            return {"success": False, "message": "Tipo de movimentação inválido."}

        cur.execute("SELECT qtd FROM pecas WHERE codigo_int=%s", (codigo_int,))
        peca = cur.fetchone()
        if not peca:
            return {"success": False, "message": "Produto não cadastrado."}
        estoque_atual = float(peca.get("qtd") or 0)

        cur.execute(
            "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, p_unit, num_nf, serie_nf) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'MV')",
            (data, tipo, codigo_int, qtd, p_unit, num_nf if num_nf else None),
        )

        if tipo.startswith("E"):
            novo_estoque = estoque_atual + qtd
            cur.execute(
                "UPDATE pecas SET qtd=%s, p_custo=%s, data_ultima_compra=%s WHERE codigo_int=%s",
                (novo_estoque, p_unit, data, codigo_int),
            )
        elif tipo.startswith("S"):
            novo_estoque = estoque_atual - qtd
            cur.execute(
                "UPDATE pecas SET qtd=%s, p_custo=%s, data_ultima_venda=%s WHERE codigo_int=%s",
                (novo_estoque, p_unit, data, codigo_int),
            )
        else:
            novo_estoque = estoque_atual
            cur.execute("UPDATE pecas SET p_custo=%s WHERE codigo_int=%s", (p_unit, codigo_int))

        conn.commit()
        cur.close()
        return {"success": True, "message": "Estoque atualizado.", "estoque": novo_estoque}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _excluir_movimentacao_sync(servidor: str, banco: str, id_mov: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT tipo, codigo_int, qtd FROM movimentacao WHERE id_mov=%s AND serie_nf='MV'",
            (id_mov,),
        )
        mov = cur.fetchone()
        if not mov:
            return {"success": False, "message": "Movimentação não encontrada."}

        tipo = (mov.get("tipo") or "").strip().upper()
        codigo_int = (mov.get("codigo_int") or "").strip()
        qtd = float(mov.get("qtd") or 0)

        cur.execute("SELECT qtd FROM pecas WHERE codigo_int=%s", (codigo_int,))
        peca = cur.fetchone()
        if peca:
            estoque_atual = float(peca.get("qtd") or 0)
            if tipo.startswith("S"):
                novo_estoque = estoque_atual + qtd
            elif tipo.startswith("E"):
                novo_estoque = estoque_atual - qtd
            else:
                novo_estoque = estoque_atual
            cur.execute("UPDATE pecas SET qtd=%s WHERE codigo_int=%s", (novo_estoque, codigo_int))

        cur.execute("DELETE FROM movimentacao WHERE id_mov=%s AND serie_nf='MV'", (id_mov,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Movimentação excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def list_tipos_mov(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipos_mov_sync, servidor, banco)


async def find_produto(servidor: str, banco: str, codigo: str) -> dict:
    return await asyncio.to_thread(_find_produto_sync, servidor, banco, codigo)


async def list_movimentacoes(
    servidor: str, banco: str,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    tipo: Optional[str] = None, codigo_int: Optional[str] = None,
) -> dict:
    return await asyncio.to_thread(
        _list_movimentacoes_sync, servidor, banco, data_ini, data_fim, tipo, codigo_int
    )


async def incluir_movimentacao(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_incluir_movimentacao_sync, servidor, banco, dados)


async def excluir_movimentacao(servidor: str, banco: str, id_mov: int) -> dict:
    return await asyncio.to_thread(_excluir_movimentacao_sync, servidor, banco, id_mov)

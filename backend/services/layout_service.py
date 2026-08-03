"""Motor de Formulário Dinâmico (Cadastro de Layout + Preenchimento) —
`FrmCadLay.frm` (cadastro dos templates) + lógica COMENTADA/desativada de
`FrmPreLay2.frm` usada como especificação funcional (decisão do usuário,
2026-07-28 — mesmo o form estando 82% comentado no legado real, ver
PENDENCIAS.md). Usado primeiro pela Agenda (módulo Clínica), mas desenhado
genérico — qualquer entidade pode reaproveitar as mesmas rotas passando
`entidade`/`codentidade` diferentes.

Escopo desta rodada: só o modo "grade de campos" (`estilo_layout=0`) — o
modo RTF livre (`estilo_layout=1`, editor de texto rico com tags tipo
"[[Nome do Cliente]]") fica de fora (ver PENDENCIAS.md > "Motor de Layout").
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

# entidade (código fixo do legado, comentário de `frmmanpedfor.frm`/
# `FrmPreLay2.frm`) -> coluna boolean em `layout` que marca esse layout como
# aplicável àquela entidade. Agenda (8) não tem coluna própria — usa vínculo
# por serviço/profissional (`layout_servico`/`layout_profissional`), tratado
# à parte em `_list_possiveis_sync`.
_ENTIDADE_COLUNA = {
    1: "cliente", 2: "fornecedor", 3: "funcionario", 4: "produto",
    5: "servico", 6: "pedido_venda", 7: "os", 9: "contrato",
}
ENTIDADE_AGENDA = 8


def _to_layout_dict(r: dict) -> dict:
    return {
        "codigo": int(r["codigo"]),
        "descricao": (r.get("descricao") or "").strip(),
        "cliente": bool(r.get("cliente")), "fornecedor": bool(r.get("fornecedor")),
        "funcionario": bool(r.get("funcionario")), "produto": bool(r.get("produto")),
        "servico": bool(r.get("servico")), "pedido_venda": bool(r.get("pedido_venda")),
        "os": bool(r.get("os")), "profissional": bool(r.get("profissional")),
        "contrato": bool(r.get("contrato")),
    }


def _list_layouts_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, descricao, cliente, fornecedor, funcionario, produto, servico, "
            "pedido_venda, os, profissional, contrato FROM layout ORDER BY descricao"
        )
        items = [_to_layout_dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao listar layouts: {e}"}


def _save_layout_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return {"success": False, "message": "Descrição do layout é obrigatória."}
    colunas_flag = list(_ENTIDADE_COLUNA.values()) + ["profissional"]
    flags = {c: (1 if dados.get(c) else 0) for c in colunas_flag}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if codigo:
            cur.execute(
                "UPDATE layout SET descricao=%s, cliente=%s, fornecedor=%s, funcionario=%s, produto=%s, "
                "servico=%s, pedido_venda=%s, os=%s, profissional=%s, contrato=%s WHERE codigo=%s",
                (
                    descricao, flags["cliente"], flags["fornecedor"], flags["funcionario"], flags["produto"],
                    flags["servico"], flags["pedido_venda"], flags["os"], flags["profissional"], flags["contrato"],
                    codigo,
                ),
            )
        else:
            cur.execute(
                "INSERT INTO layout (descricao, estilo_layout, layout_impressao, cliente, fornecedor, "
                "funcionario, produto, servico, pedido_venda, os, profissional, contrato, paginas) "
                "OUTPUT INSERTED.codigo VALUES (%s,0,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
                (
                    descricao, flags["cliente"], flags["fornecedor"], flags["funcionario"], flags["produto"],
                    flags["servico"], flags["pedido_venda"], flags["os"], flags["profissional"], flags["contrato"],
                ),
            )
            row = cur.fetchone()
            codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar layout: {e}"}


def _delete_layout_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM layout_entidade WHERE codlayout=%s", (codigo,))
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Layout já tem preenchimentos — exclusão não permitida."}
        cur.execute("DELETE FROM layout_campos WHERE layout=%s", (codigo,))
        cur.execute("DELETE FROM layout WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir layout: {e}"}


def _list_tipos_campo_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, tipo FROM layout_tipo_campo ORDER BY codigo")
        items = [{"codigo": int(r["codigo"]), "tipo": (r.get("tipo") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao listar tipos: {e}"}


def _list_campos_sync(servidor: str, banco: str, layout: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT lc.codigo, lc.campo1, lc.campo2, lc.tipo, lc.calculado, lc.calc_campo1, lc.calc_campo2, "
            "lc.operador, lc.valor_minimo, lc.valor_maximo, lc.unidade_medida, lc.decimais, lc.tamanho, "
            "lc.campo_agrupado, ltc.tipo AS tipo_descricao "
            "FROM layout_campos lc JOIN layout_tipo_campo ltc ON ltc.codigo = lc.tipo "
            "WHERE lc.layout=%s ORDER BY lc.codigo",
            (layout,),
        )
        items = [_campo_dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao listar campos: {e}"}


def _campo_dict(r: dict) -> dict:
    return {
        "codigo": int(r["codigo"]), "campo1": (r.get("campo1") or "").strip(),
        "campo2": (r.get("campo2") or "").strip(), "tipo": int(r["tipo"]),
        "tipo_descricao": (r.get("tipo_descricao") or "").strip(),
        "calculado": bool(r.get("calculado")),
        "calc_campo1": r.get("calc_campo1"), "calc_campo2": r.get("calc_campo2"),
        "operador": (r.get("operador") or "").strip(),
        "valor_minimo": float(r["valor_minimo"]) if r.get("valor_minimo") is not None else None,
        "valor_maximo": float(r["valor_maximo"]) if r.get("valor_maximo") is not None else None,
        "unidade_medida": (r.get("unidade_medida") or "").strip(),
        "decimais": int(r.get("decimais") or 0), "tamanho": int(r.get("tamanho") or 0),
        "campo_agrupado": bool(r.get("campo_agrupado")),
    }


def _save_campo_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    layout = dados.get("layout")
    campo1 = (dados.get("campo1") or "").strip()
    if not layout or not campo1:
        return {"success": False, "message": "Layout e nome do campo são obrigatórios."}
    campo2 = (dados.get("campo2") or "").strip() or None
    tipo = dados.get("tipo")
    calculado = 1 if dados.get("calculado") else 0
    params = (
        campo1, campo2, tipo, calculado,
        dados.get("calc_campo1"), dados.get("calc_campo2"), (dados.get("operador") or "").strip() or None,
        dados.get("valor_minimo"), dados.get("valor_maximo"), (dados.get("unidade_medida") or "").strip() or None,
        int(dados.get("decimais") or 0), int(dados.get("tamanho") or 0),
        1 if dados.get("campo_agrupado") else 0,
    )
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if codigo:
            cur.execute(
                "UPDATE layout_campos SET campo1=%s, campo2=%s, tipo=%s, calculado=%s, calc_campo1=%s, "
                "calc_campo2=%s, operador=%s, valor_minimo=%s, valor_maximo=%s, unidade_medida=%s, "
                "decimais=%s, tamanho=%s, campo_agrupado=%s WHERE codigo=%s",
                params + (codigo,),
            )
        else:
            cur.execute(
                "INSERT INTO layout_campos (layout, campo1, campo2, tipo, calculado, calc_campo1, calc_campo2, "
                "operador, valor_minimo, valor_maximo, unidade_medida, decimais, tamanho, campo_agrupado) "
                "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (layout,) + params,
            )
            row = cur.fetchone()
            codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar campo: {e}"}


def _delete_campo_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM layout_campos WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir campo: {e}"}


def _list_possiveis_sync(servidor: str, banco: str, entidade: int, codentidade: int) -> dict:
    """Layouts aplicáveis à entidade. Pra Agenda (8), o legado associa por
    serviço/profissional do próprio agendamento (`layout_servico`/
    `layout_profissional` — réplica de `FrmPreLay2.frm`'s `Case 8`
    comentado), não por um flag direto "agenda" em `layout` (que não
    existe)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if entidade == ENTIDADE_AGENDA:
            cur.execute("SELECT servico, funcionario FROM AGENDA WHERE codagenda=%s", (codentidade,))
            ag = cur.fetchone()
            if not ag:
                cur.close()
                conn.close()
                return {"success": True, "items": []}
            cur.execute(
                "SELECT DISTINCT l.codigo, l.descricao FROM layout l "
                "LEFT JOIN layout_servico ls ON ls.codlayout = l.codigo "
                "LEFT JOIN layout_profissional lp ON lp.codlayout = l.codigo "
                "WHERE ls.servico = %s OR lp.profissional = %s",
                (ag.get("servico"), ag.get("funcionario")),
            )
        else:
            coluna = _ENTIDADE_COLUNA.get(entidade)
            if not coluna:
                cur.close()
                conn.close()
                return {"success": True, "items": []}
            cur.execute(f"SELECT codigo, descricao FROM layout WHERE {coluna}=1 ORDER BY descricao")
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao buscar layouts possíveis: {e}"}


def _list_preenchidos_sync(servidor: str, banco: str, entidade: int, codentidade: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT le.codigo, le.data, l.descricao FROM layout_entidade le "
            "JOIN layout l ON l.codigo = le.codlayout "
            "WHERE le.entidade=%s AND le.codentidade=%s ORDER BY le.codigo DESC",
            (entidade, codentidade),
        )
        items = []
        for r in cur.fetchall():
            data_v = r.get("data")
            items.append({
                "codigo": int(r["codigo"]),
                "descricao": (r.get("descricao") or "").strip(),
                "data": data_v.isoformat() if hasattr(data_v, "isoformat") else str(data_v),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao buscar preenchimentos: {e}"}


def _get_preenchimento_sync(servidor: str, banco: str, codigo: int) -> dict:
    """`codigo` é o código de um `layout_entidade` (um preenchimento já
    existente) — monta a lista de campos do layout com o `conteudo` já
    preenchido."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, codlayout, data, obs, obs_descricao FROM layout_entidade WHERE codigo=%s",
            (codigo,),
        )
        le = cur.fetchone()
        if not le:
            cur.close()
            conn.close()
            return {"success": False, "message": "Preenchimento não encontrado."}
        cur.execute(
            "SELECT campo1, campo2, conteudo, codlayoutcampo FROM layout_preenchido WHERE codlayoutentidade=%s",
            (codigo,),
        )
        respostas = {
            int(r["codlayoutcampo"]): (r.get("conteudo") or "")
            for r in cur.fetchall() if r.get("codlayoutcampo") is not None
        }
        cur.execute(
            "SELECT lc.codigo, lc.campo1, lc.campo2, lc.tipo, lc.calculado, lc.calc_campo1, lc.calc_campo2, "
            "lc.operador, lc.valor_minimo, lc.valor_maximo, lc.unidade_medida, lc.decimais, lc.tamanho, "
            "lc.campo_agrupado, ltc.tipo AS tipo_descricao "
            "FROM layout_campos lc JOIN layout_tipo_campo ltc ON ltc.codigo = lc.tipo "
            "WHERE lc.layout=%s ORDER BY lc.codigo",
            (int(le["codlayout"]),),
        )
        campos = [_campo_dict(r) for r in cur.fetchall()]
        for c in campos:
            c["conteudo"] = respostas.get(c["codigo"], "")
        cur.close()
        conn.close()
        data_v = le.get("data")
        return {
            "success": True,
            "codigo": int(le["codigo"]), "codlayout": int(le["codlayout"]),
            "data": data_v.isoformat() if hasattr(data_v, "isoformat") else str(data_v),
            "obs": (le.get("obs") or "").strip(), "obs_descricao": (le.get("obs_descricao") or "").strip(),
            "campos": campos,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao buscar preenchimento: {e}"}


def _preencher_sync(servidor: str, banco: str, dados: dict) -> dict:
    """Grava/atualiza um preenchimento — réplica da lógica COMENTADA de
    `FrmPreLay2.frm`'s `Command1_Click` (modo "grade de campos"): sem
    `codigo` (de `layout_entidade`), cria um novo; com `codigo`, apaga e
    regrava as respostas (`layout_preenchido`) — mesmo padrão de
    "replace-all-on-save" já usado em Telefones/Endereços/Contatos do
    Cliente Completo."""
    entidade = dados.get("entidade")
    codentidade = dados.get("codentidade")
    codlayout = dados.get("codlayout")
    codigo = dados.get("codigo")
    respostas = dados.get("respostas") or []  # [{codigo_campo, conteudo}]
    usuario = dados.get("usuario_alteracao") or 0
    obs = (dados.get("obs") or "").strip()
    if not entidade or not codentidade or not codlayout:
        return {"success": False, "message": "Entidade/layout são obrigatórios."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if codigo:
            cur.execute(
                "UPDATE layout_entidade SET data=CAST(GETDATE() AS DATE), obs=%s WHERE codigo=%s",
                (obs, codigo),
            )
            cur.execute("DELETE FROM layout_preenchido WHERE codlayoutentidade=%s", (codigo,))
        else:
            cur.execute(
                "INSERT INTO layout_entidade (entidade, codentidade, codlayout, data, obs, preenchido_por) "
                "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,CAST(GETDATE() AS DATE),%s,%s)",
                (entidade, codentidade, codlayout, obs, usuario),
            )
            row = cur.fetchone()
            codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        for resp in respostas:
            codigo_campo = resp.get("codigo_campo")
            conteudo = resp.get("conteudo")
            if codigo_campo is None or conteudo in (None, ""):
                continue
            cur.execute(
                "SELECT campo1, campo2, tipo, calculado, calc_campo1, calc_campo2, operador "
                "FROM layout_campos WHERE codigo=%s",
                (codigo_campo,),
            )
            campo = cur.fetchone()
            if not campo:
                continue
            cur.execute(
                "INSERT INTO layout_preenchido (codlayoutentidade, campo1, campo2, conteudo, codlayoutcampo, "
                "tipo, calculado, calc_campo1, calc_campo2, operador) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo, campo.get("campo1"), campo.get("campo2"), str(conteudo), codigo_campo,
                    campo.get("tipo"), campo.get("calculado"), campo.get("calc_campo1"),
                    campo.get("calc_campo2"), campo.get("operador"),
                ),
            )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao preencher layout: {e}"}


async def list_layouts(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_layouts_sync, servidor, banco)


async def save_layout(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_layout_sync, servidor, banco, codigo, dados)


async def delete_layout(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_layout_sync, servidor, banco, codigo)


async def list_tipos_campo(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipos_campo_sync, servidor, banco)


async def list_campos(servidor: str, banco: str, layout: int) -> dict:
    return await asyncio.to_thread(_list_campos_sync, servidor, banco, layout)


async def save_campo(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_campo_sync, servidor, banco, codigo, dados)


async def delete_campo(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_campo_sync, servidor, banco, codigo)


async def list_possiveis(servidor: str, banco: str, entidade: int, codentidade: int) -> dict:
    return await asyncio.to_thread(_list_possiveis_sync, servidor, banco, entidade, codentidade)


async def list_preenchidos(servidor: str, banco: str, entidade: int, codentidade: int) -> dict:
    return await asyncio.to_thread(_list_preenchidos_sync, servidor, banco, entidade, codentidade)


async def get_preenchimento(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_preenchimento_sync, servidor, banco, codigo)


async def preencher(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_preencher_sync, servidor, banco, dados)

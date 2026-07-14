"""Lookups auxiliares — área de atuação e funcionários (vendedores)."""
import asyncio

from db.connection import _open_conn


def _list_area_atuacao_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT area AS codigo, descricao FROM area_atuacao ORDER BY descricao")
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _list_funcionarios_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo_int AS codigo, nome, nome_guerra, cod_funcao "
            "FROM funcionarios WHERE ISNULL(situacao,'A') <> 'I' ORDER BY nome"
        )
        items = [{
            "codigo": int(r["codigo"]),
            "nome": (r.get("nome") or "").strip(),
            "nome_guerra": (r.get("nome_guerra") or "").strip(),
            "cod_funcao": (r.get("cod_funcao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def list_area_atuacao(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_area_atuacao_sync, servidor, banco)


async def list_funcionarios(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_funcionarios_sync, servidor, banco)


# =====================================================================
# Lookups genéricos (codigo, descricao) — tabelas auxiliares da aba
# Dados Secundários do cadastro completo de cliente.
# =====================================================================
def _list_codigo_descricao_sync(
    servidor: str, banco: str, tabela: str, codigo_col: str = "codigo", where: str = "", desc_col: str = "descricao"
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(f"SELECT {codigo_col} AS codigo, {desc_col} AS descricao FROM {tabela} {where} ORDER BY {desc_col}")
        items = [{"codigo": r["codigo"], "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def list_segmentos(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "segmentos")


async def list_rotas(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "rotas")


async def list_regioes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "regioes")


async def list_forma_pagamento(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "forma_pagamento")


async def list_canal_aquisicao_cliente(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "canal_aquisicao_cliente")


async def list_dia_semana(servidor: str, banco: str) -> dict:
    # PK da tabela é "dia", não "codigo".
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "dia_semana", "dia")


async def list_status_cliente(servidor: str, banco: str) -> dict:
    # Tabela dedicada STATUS_CLIENTE (A=Ativo, C=Cancelado, D=Desativado, E=Excluido,
    # F=Fechado, R=Reservado, S=Suspenso) — não confundir com a tabela genérica `situacao`.
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "STATUS_CLIENTE")


async def list_centro_custo(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "centro_custo")


async def list_contas(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "contas")


async def list_classes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "classes")


async def list_sub_classes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "sub_classes")


async def list_favorecidos(servidor: str, banco: str) -> dict:
    # favorecidos(codigo IDENTITY, descricao, ...) — usado pela tela Entrada/
    # Saída de Caixa (favorecido do lançamento). Sem lookup próprio até então.
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "favorecidos")


async def list_tipo_cliente_contato(servidor: str, banco: str) -> dict:
    # tipo_cliente_contato(codigo IDENTITY, nome) — situação/estágio do
    # contato (Contato, Fechado, Não Contactado, Prospect, Sem Possibilidade).
    # Usado pela tela Contatos. Coluna de descrição é `nome`, não `descricao`
    # — não confundir com a tabela `tipo_cliente` (Cliente/Fornecedor).
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "tipo_cliente_contato", desc_col="nome")


async def list_codigo_contabil(servidor: str, banco: str) -> dict:
    # codigo_contabil(codigo int PK, conta_deb int, conta_cred int, descricao) —
    # usado no combo "Código Contábil" da tela de CFOP (Tabelas Auxiliares).
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "codigo_contabil")


async def list_cst_pis(servidor: str, banco: str) -> dict:
    # cst_pis(CST_Pis nvarchar(2) PK, Descricao) — tabela padronizada de
    # Situação Tributária do PIS (vocabulário fixo da legislação, ex.: "01",
    # "04"...). Usada no combo "CST Pis" da tela CFOP x Pis/Cofins.
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "cst_pis", "CST_Pis")


async def list_cst_cofins(servidor: str, banco: str) -> dict:
    # cst_cofins(CST_Cofins nvarchar(2) PK, Descricao) — idem, para COFINS.
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "cst_cofins", "CST_Cofins")


async def list_tipo_peca(servidor: str, banco: str) -> dict:
    # tipo_peca(codigo int PK, descricao nvarchar(30)) — combo "Finalidade" em
    # Alterações Cadastro de Produtos Níveis (pecas.tipo_peca).
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "tipo_peca")


async def list_uf(servidor: str, banco: str) -> dict:
    # uf(codigo nvarchar(2) PK, descricao nvarchar(25), cod_ibge) — combo "UF
    # Protocolo ST" em Alterações Cadastro de Produtos Níveis.
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "uf")


async def list_tipo_mov(servidor: str, banco: str) -> dict:
    # Tabela `tipo_mov` (codigo nvarchar(3), ex.: "S01"/"VENDA") — usada em
    # area_atuacao.TIPO_MOV_AREA_ATUACAO. Só tipos ativos (situacao <> 'I').
    return await asyncio.to_thread(
        _list_codigo_descricao_sync, servidor, banco, "tipo_mov",
        "codigo", "WHERE ISNULL(situacao,'A') <> 'I'",
    )


def _list_tipo_mov_nf_sync(servidor: str, banco: str) -> dict:
    # Versão "completa" de tipo_mov pra tela Notas Fiscais — além de
    # codigo/descricao, traz as colunas que o legado (Combo1_Click /
    # combo1_LostFocus do FrmManRec.frm) usa pra decidir automaticamente:
    # origem_destino (C=Cliente/F=Fornecedor — define qual busca abrir),
    # atualiza_est (se a movimentação mexe em estoque), transf_pagar (se
    # exige vencimento pro contas a pagar/receber) e cfop/cfop_fora (CFOP
    # padrão dentro do estado / fora do estado).
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, descricao, origem_destino, atualiza_est, transf_pagar, "
            "cfop, cfop_fora, tipo_doc, itens FROM tipo_mov "
            "WHERE ISNULL(situacao,'A') <> 'I' ORDER BY codigo"
        )
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "origem_destino": (r.get("origem_destino") or "").strip(),
            "atualiza_est": (r.get("atualiza_est") or "").strip(),
            "transf_pagar": (r.get("transf_pagar") or "").strip(),
            "cfop": (r.get("cfop") or "").strip(),
            "cfop_fora": (r.get("cfop_fora") or "").strip(),
            "tipo_doc": r.get("tipo_doc"),
            "itens": (r.get("itens") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def list_tipo_mov_nf(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipo_mov_nf_sync, servidor, banco)


async def list_tipo_doc(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "tipo_doc")


async def list_modelo_os(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "modelo_os")


async def list_modelo_pedido(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "modelo_pedido")


async def list_funcoes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "Funcoes")


async def list_cargos(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "cargos", "codigo_cargo")


async def list_especialidades(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_codigo_descricao_sync, servidor, banco, "especialidades", "codigo_especialidade")

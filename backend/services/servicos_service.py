"""Manutenção de Serviços — CRUD completo. Legado: `FrmManSer2.frm`.

Schema real (conferido ao vivo em GERDELL/BARESTELA, não assumido do VB6):
- `servicos.codigo` é `nvarchar(8)`, sempre prefixado "S" (fiel ao legado).
- `aceita_desconto`/`paga_comissao` são `smallint`, gravados **invertidos**
  em relação ao checkbox: marcado (aceita/paga) -> grava 0; desmarcado ->
  grava -1. Confirmado contra os 2 registros já existentes no banco de
  teste (S002: aceita_desconto=0/paga_comissao=-1; S003: idem) — bate com
  a fórmula do legado `(Check.Value - 1)`.
- **`INDOP_NFSE`** ("Indicador Operação", Campo(33) no legado): não existia
  na tabela quando este módulo foi escrito — confirmado pelo usuário que é
  um campo recente, criado só na abertura do sistema (por isso ausente
  neste banco de teste até ser criado manualmente). Adicionado via `ALTER
  TABLE SERVICOS ADD INDOP_NFSE NVARCHAR(10)` em 2026-07-10, agora
  implementado normalmente.
- Tabelas auxiliares desta tela ainda fora de escopo nesta primeira leva
  (fase CRUD principal): `servicos_preco_qtd` (Preço por Quantidade),
  `produtos_compostos` (Previsão de Produtos). "Layouts do Serviço" e
  "Exceções da Comissão" são **frames da própria FrmManSer2** (não forms
  separados — confirmado pelo usuário), então não são "sub-telas" a
  migrar independentemente: Layouts é um vínculo N:N simples
  (`layout`/`layout_servico`) que pode virar uma seção inline aqui;
  Exceções de Comissão (`comissao_excecao`) em FrmManSer2 é **somente
  leitura** (Command4_Click só faz SELECT, sem INSERT/UPDATE) — a edição
  de verdade acontece no cadastro de Funcionários (aba Comissões, ainda
  não migrado). Anexos já reaproveita o Gestor de Documentos existente
  (grupo 5 = Serviços).
- `servicos_func`/`servicos_pecas`: **descartadas pelo usuário**, não são
  usadas por esta tela.

Guards de exclusão (fiel ao legado, `Command5_Click`): bloqueia se o
serviço tiver `movimentacao`, orçamento não cancelado (`orc_produto`+
`orcamento.situacao<>'C'`), O.S. não cancelada (`os_produto`+
`os.situacao<>'C'`), ou nota fiscal (`nf_aux_itens`) vinculados.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services.pedido_common import _modulo_servicos_ativo

_MODULO_DESATIVADO_MSG = (
    "Módulo Serviço está desativado em Configurações do Sistema > Módulos. "
    "Ative-o para cadastrar, consultar ou movimentar serviços."
)

_CAMPOS_SERVICO = [
    "descricao", "descricao_nf", "codigo_especialidade", "tipo", "situacao",
    "valor_hora", "custo_hora", "preco_variado",
    "prazo_garantia", "tipo_garantia",
    "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "cod_lista_servico", "cod_servico_municipio", "cod_icms", "indop_nfse",
    "codigo_mercosul", "classificacao_fiscal", "construcao_civil",
    "tributacao_pis", "perc_valor_pis", "tributacao_cofins", "perc_valor_cofins",
    "aceita_desconto", "desc_g", "desc_s", "desc_v",
    "paga_comissao", "comissao", "comissao_e", "comissao_a",
    "valor_comissao", "valor_comissao_e", "valor_comissao_a",
    "perc_desc_base_comissao", "perc_desc_base_comissao_e", "perc_desc_base_comissao_a",
]


def _to_int_ou_none(v):
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _row_to_dict(r: dict) -> dict:
    return {
        "codigo": (r.get("codigo") or "").strip(),
        "descricao": (r.get("descricao") or "").strip(),
        "descricao_nf": r.get("descricao_nf") or "",
        "codigo_especialidade": r.get("codigo_especialidade"),
        "tipo": r.get("tipo"),
        "situacao": (r.get("situacao") or "A").strip(),
        "valor_hora": float(r.get("valor_hora") or 0),
        "custo_hora": float(r.get("custo_hora") or 0),
        "preco_variado": bool(r.get("preco_variado")),
        "prazo_garantia": int(r.get("prazo_garantia") or 0),
        "tipo_garantia": int(r.get("tipo_garantia") or 0),
        "nivel1": (r.get("nivel1") or "").strip(),
        "nivel2": (r.get("nivel2") or "").strip(),
        "nivel3": (r.get("nivel3") or "").strip(),
        "nivel4": (r.get("nivel4") or "").strip(),
        "nivel5": (r.get("nivel5") or "").strip(),
        "cod_lista_servico": (r.get("cod_lista_servico") or "").strip(),
        "cod_servico_municipio": (r.get("cod_servico_municipio") or "").strip(),
        "cod_icms": (r.get("cod_icms") or "").strip(),
        "indop_nfse": (r.get("indop_nfse") or "").strip(),
        "codigo_mercosul": (r.get("codigo_mercosul") or "").strip(),
        "classificacao_fiscal": (r.get("classificacao_fiscal") or "").strip(),
        "construcao_civil": bool(r.get("construcao_civil")),
        "tributacao_pis": (f"{int(r['tributacao_pis']):02d}" if r.get("tributacao_pis") is not None else None),
        "perc_valor_pis": float(r.get("perc_valor_pis") or 0),
        "tributacao_cofins": (f"{int(r['tributacao_cofins']):02d}" if r.get("tributacao_cofins") is not None else None),
        "perc_valor_cofins": float(r.get("perc_valor_cofins") or 0),
        "aceita_desconto": (r.get("aceita_desconto") == 0),
        "desc_g": float(r.get("desc_g") or 0),
        "desc_s": float(r.get("desc_s") or 0),
        "desc_v": float(r.get("desc_v") or 0),
        "paga_comissao": (r.get("paga_comissao") == 0),
        "comissao": float(r.get("comissao") or 0),
        "comissao_e": float(r.get("comissao_e") or 0),
        "comissao_a": float(r.get("comissao_a") or 0),
        "valor_comissao": float(r.get("valor_comissao") or 0),
        "valor_comissao_e": float(r.get("valor_comissao_e") or 0),
        "valor_comissao_a": float(r.get("valor_comissao_a") or 0),
        "perc_desc_base_comissao": float(r.get("perc_desc_base_comissao") or 0),
        "perc_desc_base_comissao_e": float(r.get("perc_desc_base_comissao_e") or 0),
        "perc_desc_base_comissao_a": float(r.get("perc_desc_base_comissao_a") or 0),
    }


def _list_servicos_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_servicos_ativo(cur):
            return {"success": False, "message": _MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT codigo, descricao, situacao, valor_hora, cod_lista_servico, cod_servico_municipio "
            "FROM servicos ORDER BY codigo"
        )
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "situacao": (r.get("situacao") or "").strip(),
            "valor_hora": float(r.get("valor_hora") or 0),
            "cod_lista_servico": (r.get("cod_lista_servico") or "").strip(),
            "cod_servico_municipio": (r.get("cod_servico_municipio") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _get_servico_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_servicos_ativo(cur):
            return {"success": False, "message": _MODULO_DESATIVADO_MSG}
        cols = "codigo," + ",".join(_CAMPOS_SERVICO)
        cur.execute(f"SELECT {cols} FROM servicos WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": False, "message": "Serviço não encontrado."}
        return {"success": True, "item": _row_to_dict(row)}
    finally:
        conn.close()


def _save_servico_sync(servidor: str, banco: str, codigo: str, dados: dict) -> dict:
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return {"success": False, "message": "Informe o código do serviço."}
    if not codigo.startswith("S"):
        if len(codigo) > 7:
            return {"success": False, "message": "O código do serviço deve ter o prefixo 'S' (máx. 7 caracteres após o prefixo)."}
        codigo = "S" + codigo
    if len(codigo) > 8:
        return {"success": False, "message": "Código de serviço muito longo (máx. 8 caracteres, incluindo o prefixo 'S')."}

    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return {"success": False, "message": "Informe a descrição."}
    if dados.get("valor_hora") is None:
        return {"success": False, "message": "Informe o Preço/Hora."}
    if not (dados.get("situacao") or "").strip():
        return {"success": False, "message": "Informe a Situação."}
    tipo = dados.get("tipo")
    if tipo is None or not (0 <= int(tipo) <= 255):
        return {"success": False, "message": "Tipo inválido — valor mínimo 0 e máximo 255."}

    for campo, rotulo, limite in (("comissao", "Comissão Vendedor", 99.999), ("comissao_e", "Comissão Executor", 99.999), ("comissao_a", "Comissão Atendente", 99.999)):
        if float(dados.get(campo) or 0) > limite:
            return {"success": False, "message": f"{rotulo} inválida (máx. {limite}%)."}

    desc_g = float(dados.get("desc_g") or 0)
    desc_s = float(dados.get("desc_s") or 0)
    desc_v = float(dados.get("desc_v") or 0)
    if desc_g > 100:
        return {"success": False, "message": "Desconto Gerente inválido (máx. 100%)."}
    if desc_s > desc_g:
        return {"success": False, "message": "Desconto Supervisor não pode ser maior que o do Gerente."}
    if desc_v > max(desc_s, desc_g):
        return {"success": False, "message": "Desconto Vendedor não pode ser maior que o do Supervisor/Gerente."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_servicos_ativo(cur):
            return {"success": False, "message": _MODULO_DESATIVADO_MSG}
        cur.execute("SELECT codigo FROM servicos WHERE codigo=%s", (codigo,))
        existe = cur.fetchone() is not None

        valores = dict(dados)
        valores["aceita_desconto"] = 0 if dados.get("aceita_desconto") else -1
        valores["paga_comissao"] = 0 if dados.get("paga_comissao") else -1
        valores["preco_variado"] = 1 if dados.get("preco_variado") else 0
        valores["construcao_civil"] = 1 if dados.get("construcao_civil") else 0
        # cst_pis/cst_cofins chegam como string ("06", igual ao lookup
        # cst_pis.CST_Pis nvarchar(2)) mas a coluna servicos.tributacao_pis/
        # tributacao_cofins é smallint — converter antes de gravar.
        valores["tributacao_pis"] = _to_int_ou_none(dados.get("tributacao_pis"))
        valores["tributacao_cofins"] = _to_int_ou_none(dados.get("tributacao_cofins"))
        # Descontos/comissões zerados quando a flag correspondente está
        # desligada — fiel ao legado (Command1_Click limpa os campos).
        if not dados.get("aceita_desconto"):
            valores["desc_g"] = valores["desc_s"] = valores["desc_v"] = 0
        if not dados.get("paga_comissao"):
            for c in ("comissao", "comissao_e", "comissao_a", "valor_comissao", "valor_comissao_e", "valor_comissao_a"):
                valores[c] = 0

        if existe:
            set_clause = ", ".join(f"{c}=%s" for c in _CAMPOS_SERVICO)
            params = [valores.get(c) for c in _CAMPOS_SERVICO] + [codigo]
            cur.execute(f"UPDATE servicos SET {set_clause} WHERE codigo=%s", params)
        else:
            cols = ["codigo"] + _CAMPOS_SERVICO
            placeholders = ",".join(["%s"] * len(cols))
            params = [codigo] + [valores.get(c) for c in _CAMPOS_SERVICO]
            cur.execute(f"INSERT INTO servicos ({','.join(cols)}) VALUES ({placeholders})", params)
        conn.commit()
        cur.close()
        return {"success": True, "message": "Serviço gravado.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_servico_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_servicos_ativo(cur):
            return {"success": False, "message": _MODULO_DESATIVADO_MSG}
        cur.execute("SELECT TOP 1 1 AS ok FROM movimentacao WHERE codigo_int=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Existem registros de Movimentação para este serviço — não pode ser excluído."}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM orc_produto op JOIN orcamento o ON o.orc=op.orc "
            "WHERE o.situacao<>'C' AND op.prod=%s", (codigo,),
        )
        if cur.fetchone():
            return {"success": False, "message": "Existem registros de Orçamento para este serviço — não pode ser excluído."}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM os_produto op JOIN os o ON o.codigo=op.os "
            "WHERE o.situacao<>'C' AND op.codigo_interno=%s", (codigo,),
        )
        if cur.fetchone():
            return {"success": False, "message": "Existem registros de Ordem de Serviço para este serviço — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM nf_aux_itens WHERE codigo_int=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Existem registros de Nota Fiscal para este serviço — não pode ser excluído."}

        cur.execute("DELETE FROM servicos WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Serviço não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Serviço excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_servicos(servidor, banco):
    return await asyncio.to_thread(_list_servicos_sync, servidor, banco)


async def get_servico(servidor, banco, codigo):
    return await asyncio.to_thread(_get_servico_sync, servidor, banco, codigo)


async def save_servico(servidor, banco, codigo, dados):
    return await asyncio.to_thread(_save_servico_sync, servidor, banco, codigo, dados)


async def delete_servico(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_servico_sync, servidor, banco, codigo)

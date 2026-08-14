"""Listagem de Clientes — Painel de Relatórios > Clientes.

Migração de `Geral\\FrmRelClie.frm` (692 linhas). 6 modos de filtro
mutuamente exclusivos (Código Interno/CPF-CNPJ/Nome-Razão Social/Data de
Cadastro/Data de Nascimento/Tipo), mais um filtro adicional Pessoa Física/
Jurídica por tamanho de `cgc_cpf` (≤11 = CPF, >11 = CNPJ — mesma
convenção já usada em `useClienteForm.detectDocType`).

**"Tipo"** no legado é `cliente.tipo`, uma coluna char solta que **não
existe nesta migração** (confirmado por grep — `clientes_service.py` só
conhece `cliente.cliente_forn`, a FK real pra `tipo_cliente`). Generalizado
pra filtrar por `cliente.cliente_forn` (o campo Tipo Cliente real e já
usado em todo o resto do sistema), não um char cru inventado.

Diferença real entre Imprimir e Gerar Planilha replicada: o PDF impresso
mostra, por cliente, contato (e-mail + telefones de `cliente_tel`) e
endereço(s) completo(s) de `cliente_end` — dado que a grade em tela (e o
Excel) não mostra; a tela/Excel ficam só nas 7 colunas básicas (Código
Interno, CPF/CNPJ, Nome, Data Cadastro, Data Nascimento, Tipo, Situação).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

MODOS = {"codigo", "cgc", "nome", "data_cadastro", "data_nasc", "tipo"}


def _listar_clientes_sync(
    servidor: str, banco: str, modo: str, termo: Optional[str],
    data_ini: Optional[str], data_fim: Optional[str],
    pessoa_fisica: bool, pessoa_juridica: bool, ordem: str,
) -> dict:
    if modo not in MODOS:
        return {"success": False, "message": "Modo de filtro inválido.", "clientes": []}
    if not pessoa_fisica and not pessoa_juridica:
        return {"success": True, "clientes": []}

    where = []
    params: list = []
    if modo == "codigo" and termo:
        where.append("c.codigo = %s")
        params.append(termo.strip())
    elif modo == "cgc" and termo:
        where.append("LEFT(c.cgc_cpf, %s) = %s")
        t = termo.strip()
        params.extend([len(t), t])
    elif modo == "nome" and termo:
        where.append("LEFT(c.nome, %s) = %s")
        t = termo.strip()
        params.extend([len(t), t])
    elif modo == "data_cadastro" and data_ini and data_fim:
        where.append("CAST(c.data AS DATE) BETWEEN %s AND %s")
        params.extend([data_ini, data_fim])
    elif modo == "data_nasc" and data_ini and data_fim:
        where.append("CAST(c.data_nasc AS DATE) BETWEEN %s AND %s")
        params.extend([data_ini, data_fim])
    elif modo == "tipo" and termo:
        where.append("c.cliente_forn = %s")
        params.append(termo.strip())

    if pessoa_fisica and not pessoa_juridica:
        where.append("LEN(ISNULL(c.cgc_cpf,'')) <= 11")
    elif pessoa_juridica and not pessoa_fisica:
        where.append("LEN(ISNULL(c.cgc_cpf,'')) > 11")

    if not where:
        return {"success": True, "clientes": []}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        ordem_sql = "ASC" if ordem != "desc" else "DESC"
        cur.execute(
            "SELECT TOP 500 c.codigo, c.cgc_cpf, c.nome, c.e_mail, "
            "  CONVERT(VARCHAR(10), c.data, 103) AS data_cad, "
            "  CONVERT(VARCHAR(10), c.data_nasc, 103) AS data_nasc, "
            "  c.cliente_forn AS tipo, c.situacao "
            f"FROM cliente c WHERE {' AND '.join(where)} "
            f"ORDER BY c.nome {ordem_sql}",
            tuple(params),
        )
        clientes = [
            {
                "codigo": r["codigo"], "cgc_cpf": (r.get("cgc_cpf") or "").strip(),
                "nome": (r.get("nome") or "").strip(), "e_mail": (r.get("e_mail") or "").strip(),
                "data_cad": r.get("data_cad"), "data_nasc": r.get("data_nasc"),
                "tipo": r.get("tipo"), "situacao": (r.get("situacao") or "").strip(),
            }
            for r in cur.fetchall()
        ]
        cur.close()
        return {"success": True, "clientes": clientes}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "clientes": []}
    finally:
        conn.close()


def _detalhe_contato_endereco_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Contatos/endereços de UM cliente, pro PDF impresso (não aparece na tela/Excel)."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT ddd, tel FROM cliente_tel WHERE codigo=%s", (codigo,))
        telefones = [f"({r.get('ddd') or ''}) {(r.get('tel') or '').strip()}" for r in cur.fetchall()]
        cur.execute(
            "SELECT endereco, numero, bairro, cep FROM cliente_end WHERE codigo=%s",
            (codigo,),
        )
        enderecos = []
        for r in cur.fetchall():
            numero = "S/Num" if (r.get("numero") is None or int(r.get("numero") or 0) == -1) else str(r.get("numero"))
            enderecos.append(f"{(r.get('endereco') or '').strip()}, {numero} - {(r.get('bairro') or '').strip()} / CEP: {(r.get('cep') or '').strip()}")
        cur.close()
        return {"success": True, "telefones": telefones, "enderecos": enderecos}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "telefones": [], "enderecos": []}
    finally:
        conn.close()


async def listar_clientes(servidor, banco, modo, termo, data_ini, data_fim, pessoa_fisica, pessoa_juridica, ordem):
    return await asyncio.to_thread(
        _listar_clientes_sync, servidor, banco, modo, termo, data_ini, data_fim, pessoa_fisica, pessoa_juridica, ordem
    )


async def detalhe_contato_endereco(servidor, banco, codigo):
    return await asyncio.to_thread(_detalhe_contato_endereco_sync, servidor, banco, codigo)

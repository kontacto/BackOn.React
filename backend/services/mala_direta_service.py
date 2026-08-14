"""Mala Direta — Painel de Relatórios > Clientes.

Migração de `Geral\\FrmMalDir2.FRM` (2741 linhas). O legado imprime
etiqueta de endereço em folha Pimaco (mesmo mecanismo GDI de
`FrmEtqProd.frm`) — **decisão do usuário (2026-08-07, `AskUserQuestion`)**:
substituir COMPLETAMENTE a impressão física por envio em massa via
WhatsApp e E-mail, reaproveitando o mecanismo já existente e testado desta
migração (`services/envio_massa_service.py` — recurso pensado pra ser
reutilizável por qualquer tela com uma lista de clientes, não só esta,
"esse recurso de envio vai ser introduzido em consulta de clientes entre
outros").

**Modos de seleção de destinatário** (escopo desta rodada, decisão do
usuário — "Todos os modos de Cliente + Fornecedores"): Todos os Clientes,
Aniversário (dia/mês, ano-agnóstico), Data de Cadastro, Tipo Cliente
(generalizado pra `cliente.cliente_forn`, mesma correção já aplicada em
Listagem de Clientes — o legado usa uma coluna `cliente.tipo` que não
existe nesta migração), Fornecedores, Clientes e Fornecedores juntos. Fora
do escopo: "Clientes que Compraram" (cruzamento com Pedido+O.S., mais
complexo) e "Etiqueta Personalizada" (texto livre repetido — não faz mais
sentido sem impressão de etiqueta).

**Canal por tipo de destinatário**: WhatsApp só é oferecido pra Clientes
— o motor de envio (`document_type='CLI'`) só resolve telefone contra a
tabela `cliente`, não `fornecedor` (ver docstring de `envio_massa_
service.py`). E-mail funciona pra Clientes E Fornecedores (ambos têm
coluna `e_mail` própria). Este service só RESOLVE a lista de
destinatários com os dados necessários (codigo/nome/e-mail/indicador de
telefone) — quem dispara o envio em si é `envio_massa_service.py`,
chamado separadamente pelo frontend.

**Decisão de escopo própria desta migração, sem precedente no legado**
(que não filtrava situação em nenhum dos modos de "Mala Direta"): todo
modo de cliente/fornecedor aqui exige `situacao = 'A'` — um envio em
massa de verdade (WhatsApp/e-mail, ao contrário de imprimir uma etiqueta
que pode simplesmente não ser usada) não deveria alcançar cadastro
inativo/cancelado por padrão. Reavaliar se o usuário pedir explicitamente
o contrário.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

SUB_MODOS_CLIENTE = {"todos", "aniversario", "cadastro", "tipo"}


def _clientes_where(sub_modo: str, termo: Optional[str], data_ini: Optional[str], data_fim: Optional[str]) -> tuple[str, list]:
    if sub_modo == "aniversario" and data_ini and data_fim:
        return " AND FORMAT(c.data_nasc, 'MM-dd') BETWEEN %s AND %s", [data_ini, data_fim]
    if sub_modo == "cadastro" and data_ini and data_fim:
        return " AND CAST(c.data AS DATE) BETWEEN %s AND %s", [data_ini, data_fim]
    if sub_modo == "tipo" and termo:
        return " AND c.cliente_forn = %s", [termo]
    return "", []


def _selecionar_destinatarios_sync(
    servidor: str, banco: str, incluir_clientes: bool, incluir_fornecedores: bool,
    sub_modo_cliente: str, termo: Optional[str], data_ini: Optional[str], data_fim: Optional[str],
) -> dict:
    if not incluir_clientes and not incluir_fornecedores:
        return {"success": False, "message": "Selecione Clientes e/ou Fornecedores.", "destinatarios": []}
    if incluir_clientes and sub_modo_cliente not in SUB_MODOS_CLIENTE:
        return {"success": False, "message": "Modo de seleção de cliente inválido.", "destinatarios": []}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        destinatarios = []

        if incluir_clientes:
            where_extra, params = _clientes_where(sub_modo_cliente, termo, data_ini, data_fim)
            cur.execute(
                "SELECT TOP 1000 c.codigo, c.nome, c.e_mail AS email, "
                "  CASE WHEN LEN(ISNULL(c.telefone_cli,'')) > 0 THEN 1 ELSE 0 END AS tem_telefone "
                "FROM cliente c WHERE c.situacao = 'A'" + where_extra + " ORDER BY c.nome",
                tuple(params),
            )
            for r in cur.fetchall():
                destinatarios.append({
                    "tipo": "cliente", "codigo": r["codigo"], "nome": (r.get("nome") or "").strip(),
                    "email": (r.get("email") or "").strip() or None,
                    "tem_telefone": bool(r.get("tem_telefone")),
                })

        if incluir_fornecedores:
            cur.execute(
                "SELECT codigo_int, nome, e_mail AS email FROM fornecedor WHERE situacao = 'A' ORDER BY nome"
            )
            for r in cur.fetchall():
                destinatarios.append({
                    "tipo": "fornecedor", "codigo": r["codigo_int"], "nome": (r.get("nome") or "").strip(),
                    "email": (r.get("email") or "").strip() or None,
                    "tem_telefone": False,
                })

        cur.close()
        return {"success": True, "destinatarios": destinatarios}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "destinatarios": []}
    finally:
        conn.close()


async def selecionar_destinatarios(servidor, banco, incluir_clientes, incluir_fornecedores, sub_modo_cliente, termo, data_ini, data_fim):
    return await asyncio.to_thread(
        _selecionar_destinatarios_sync, servidor, banco, incluir_clientes, incluir_fornecedores,
        sub_modo_cliente, termo, data_ini, data_fim,
    )

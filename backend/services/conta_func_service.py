"""Financeiro > Fluxo de Caixa > Contas x Funcionário (`FrmConFunc.frm`,
"Acesso das Contas Por Funcionários...") — configura quais `Contas`
(caixa/banco, ver `contas_service.py`) cada funcionário pode visualizar.

Tabela `conta_func` (conta, func) — já existente no schema, já referenciada
como delete-guard em `funcionarios_service._delete_funcionario_sync`
("Contas de Funcionário"), sem CRUD próprio até esta tela.

**Réplica fiel do padrão "replace-all-on-save" do legado**
(`Command3_Click`): salvar sempre apaga todos os vínculos do funcionário e
reinsere a lista atual — mesmo padrão já usado em telefones/endereços/
contatos de Cliente neste app, não uma invenção nova daqui.

**Consumida pela primeira tela em 2026-07-25 (Geração de Boletos, campo
Conta da aba Importação Retorno)** — ver `_list_visiveis_sync` abaixo.
Regras confirmadas com o usuário via `AskUserQuestion` na hora de ligar o
crivo: (1) funcionário sem NENHUM vínculo em `conta_func` não vê nenhuma
conta (padrão restritivo, não permissivo — precisa ser configurado
explicitamente em "Contas x Funcionário" antes de enxergar qualquer
conta); (2) o usuário master sempre vê todas as contas ativas,
independente de configuração (mesmo padrão de bypass já usado em
`can()` — ver "Master User Has Full Permission" em CLAUDE.md). O bypass
de master é decidido a partir de um flag (`is_master`) enviado pelo
frontend (mesmo nível de confiança já usado no resto do app pra decisões
de UI/visibilidade — não é um limite de segurança rígido, é consistente
com o restante do modelo de permissões deste projeto)."""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _get_vinculo_sync(servidor: str, banco: str, funcionario: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, descricao FROM Contas WHERE situacao='A' ORDER BY descricao")
        contas = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.execute("SELECT conta FROM conta_func WHERE func=%s", (funcionario,))
        vinculadas = [int(r["conta"]) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "contas": contas, "vinculadas": vinculadas}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _salvar_vinculo_sync(servidor: str, banco: str, funcionario: int, contas: list) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM funcionarios WHERE codigo_int=%s", (funcionario,))
        if not cur.fetchone():
            return {"success": False, "message": "Funcionário não encontrado."}

        cur.execute("DELETE FROM conta_func WHERE func=%s", (funcionario,))
        for codigo_conta in contas:
            cur.execute("INSERT INTO conta_func (conta, func) VALUES (%s, %s)", (int(codigo_conta), funcionario))

        conn.commit()
        cur.close()
        return {"success": True, "qtd": len(contas)}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _list_visiveis_sync(servidor: str, banco: str, funcionario: Optional[int], is_master: bool) -> dict:
    """Contas que o funcionário logado pode ver em telas consumidoras (ex.:
    campo "Conta" da Geração de Boletos) — ver regras na docstring do
    módulo. `is_master=True` ignora `funcionario` e devolve tudo."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if is_master:
            cur.execute("SELECT codigo, descricao, ContaPrincipalPainel FROM Contas WHERE situacao='A' ORDER BY descricao")
        elif funcionario:
            cur.execute(
                "SELECT c.codigo, c.descricao, c.ContaPrincipalPainel FROM Contas c "
                "JOIN conta_func cf ON cf.conta = c.codigo "
                "WHERE cf.func=%s AND c.situacao='A' ORDER BY c.descricao",
                (funcionario,),
            )
        else:
            cur.close()
            return {"success": True, "items": []}
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
            "conta_principal_painel": bool(r.get("ContaPrincipalPainel")),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def get_vinculo(servidor: str, banco: str, funcionario: int) -> dict:
    return await asyncio.to_thread(_get_vinculo_sync, servidor, banco, funcionario)


async def salvar_vinculo(servidor: str, banco: str, funcionario: int, contas: list) -> dict:
    return await asyncio.to_thread(_salvar_vinculo_sync, servidor, banco, funcionario, contas)


async def list_visiveis(servidor: str, banco: str, funcionario: Optional[int], is_master: bool) -> dict:
    return await asyncio.to_thread(_list_visiveis_sync, servidor, banco, funcionario, is_master)

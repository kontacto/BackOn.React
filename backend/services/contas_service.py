"""Financeiro > Fluxo de Caixa > Contas (`FrmManConta.frm`, "Conta") —
cadastro de contas de caixa/banco usadas em todo o fluxo financeiro
(Entrada/Saída de Caixa, Fechamento de Caixa, "Conta" na Importação do
Arquivo de Retorno, `cliente.conta_transf_caixa`, etc.). Tabela `Contas`
já existente e já consumida por vários pontos do app (ver
`lookups_service.list_contas`) — esta tela é o primeiro CRUD completo
sobre ela.

**Regra de negócio real, replicada fielmente** (`Command6_Click`, ramo de
UPDATE): ao editar o Saldo Inicial de uma conta já existente, o Saldo
Atual é recalculado proporcionalmente pela diferença —
`saldo_atual_novo = saldo_atual_atual + (saldo_inicial_novo -
saldo_inicial_atual)` — preserva o "extrato" (soma de movimentações) já
lançado, só desloca o ponto de partida. O legado escreve isso como duas
ramificações `If`/`Else` (si > novo / si <= novo); aqui simplificado pra
uma soma só, matematicamente equivalente (conferido a mão durante o
rastreio). Mudança no Saldo Inicial grava um log de auditoria dedicado —
o legado usa a tabela própria `Logs`; aqui usa `log_auditoria_service`,
mesmo padrão do resto do app.

**Não replicado** ("Não replicar truques VB6"): o botão "Alterar
Descrição" (`Command2_Click`, um `InputBox` dedicado) era um workaround
pro campo `Nome` do legado ser um ComboBox vinculado à lista de contas
existentes, não um campo de texto livre — não dava pra editar o nome
"no lugar". Aqui o Nome/Descrição é só mais um campo do formulário normal,
editável e gravado pelo Gravar padrão. A regra real por trás daquele botão
(não permitir duas contas com o mesmo nome) foi preservada, aplicada de
forma mais consistente que o legado — lá só rodava dentro do fluxo
"Alterar Descrição"; aqui roda sempre que a descrição muda (criação ou
edição), não só nesse caso específico.

**Fora de escopo** ("Contabilidade", `Campo(20)`/`conta_transf_contabil`,
FK pra `Plano_<ano_exercicio>` — tabela ano a ano): mesma decisão já
tomada em `financeiro_service.py` pro campo homônimo de Classes/
Sub-Classes — qual "ano_exercicio" usar é uma pergunta em aberto (ver
CLAUDE.md > Cliente Completo, mesma pendência).

**Delete guard** (`Command3_Click`): bloqueia exclusão se a conta tiver
lançamentos em `previsoes` OU `movimentacoes` — `(tipo<>2 AND
conta=codigo) OR (tipo=2 AND classe=codigo)` nas duas tabelas (`tipo=2`
marca transferência entre contas, onde a coluna `classe` é reaproveitada
pra guardar a conta de destino — mesmo truque de reaproveitamento de
coluna já documentado em `entrada_saida_caixa_service.py`, não uma
invenção nova daqui). `previsoes` não é escrita por nenhuma tela já
migrada deste app (só `movimentacoes`, via Entrada/Saída de Caixa) — a
checagem continua incluída porque a tabela é real e compartilhada com o
legado.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

CAMPOS_TEXT = {"descricao", "banco", "agencia", "numero", "moeda", "situacao"}


def _row_to_item(r: dict) -> dict:
    return {
        "codigo": int(r["codigo"]),
        "descricao": (r.get("descricao") or "").strip(),
        "banco": (r.get("banco") or "").strip(),
        "agencia": (r.get("agencia") or "").strip(),
        "numero": (r.get("numero") or "").strip(),
        "saldo_inicial": float(r.get("saldo_inicial") or 0),
        "saldo_atual": float(r.get("saldo_atual") or 0),
        "moeda": (r.get("moeda") or "Real").strip(),
        "tipo": int(r.get("tipo") or 0),
        "situacao": (r.get("situacao") or "A").strip() or "A",
        "conta_principal_painel": bool(r.get("ContaPrincipalPainel")),
    }


def _list_sync(servidor: str, banco: str, busca: Optional[str]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if busca and busca.strip():
            termo = busca.strip()
            if termo.isdigit():
                cur.execute(
                    "SELECT codigo, descricao, banco, agencia, numero, saldo_inicial, saldo_atual, "
                    "moeda, tipo, situacao, ContaPrincipalPainel FROM Contas WHERE codigo=%s ORDER BY descricao",
                    (int(termo),),
                )
            else:
                like = f"%{termo}%"
                cur.execute(
                    "SELECT codigo, descricao, banco, agencia, numero, saldo_inicial, saldo_atual, "
                    "moeda, tipo, situacao, ContaPrincipalPainel FROM Contas WHERE descricao LIKE %s ORDER BY descricao",
                    (like,),
                )
        else:
            cur.execute(
                "SELECT codigo, descricao, banco, agencia, numero, saldo_inicial, saldo_atual, "
                "moeda, tipo, situacao, ContaPrincipalPainel FROM Contas ORDER BY descricao"
            )
        items = [_row_to_item(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _get_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, descricao, banco, agencia, numero, saldo_inicial, saldo_atual, "
            "moeda, tipo, situacao, ContaPrincipalPainel FROM Contas WHERE codigo=%s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": False, "message": "Conta não encontrada."}
        return {"success": True, **_row_to_item(row)}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _save_sync(servidor: str, banco: str, dados: dict) -> dict:
    codigo = dados.get("codigo")
    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return {"success": False, "message": "Informe a descrição da conta."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute(
            "SELECT TOP 1 codigo FROM Contas WHERE descricao=%s AND codigo<>%s",
            (descricao, int(codigo) if codigo else 0),
        )
        if cur.fetchone():
            return {"success": False, "message": "Já existe uma conta com essa descrição."}

        banco_txt = (dados.get("banco_nome") or "").strip()
        agencia = (dados.get("agencia") or "").strip()
        numero = (dados.get("numero") or "").strip()
        moeda = (dados.get("moeda") or "Real").strip()
        tipo = 1 if int(dados.get("tipo") or 0) == 1 else 0
        situacao = (dados.get("situacao") or "A").strip().upper() or "A"
        conta_principal = 1 if dados.get("conta_principal_painel") else 0
        saldo_inicial_novo = float(dados.get("saldo_inicial") or 0)

        if not codigo:
            cur.execute(
                "INSERT INTO Contas (Descricao, Banco, Agencia, Numero, Saldo_Inicial, Saldo_Atual, "
                "Moeda, Tipo, Situacao, ContaPrincipalPainel) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (descricao, banco_txt, agencia, numero, saldo_inicial_novo, saldo_inicial_novo,
                 moeda, tipo, situacao, conta_principal),
            )
            cur.execute("SELECT TOP 1 codigo FROM Contas WHERE descricao=%s ORDER BY codigo DESC", (descricao,))
            novo = cur.fetchone()
            conn.commit()
            cur.close()
            return {"success": True, "codigo": int(novo["codigo"]) if novo else None, "message": "Conta gravada."}

        cur.execute("SELECT saldo_inicial, saldo_atual FROM Contas WHERE codigo=%s", (int(codigo),))
        atual = cur.fetchone()
        if not atual:
            return {"success": False, "message": "Conta não encontrada."}
        saldo_inicial_atual = float(atual.get("saldo_inicial") or 0)
        saldo_atual_atual = float(atual.get("saldo_atual") or 0)
        saldo_atual_novo = saldo_atual_atual + (saldo_inicial_novo - saldo_inicial_atual)

        cur.execute(
            "UPDATE Contas SET Descricao=%s, Banco=%s, Agencia=%s, Numero=%s, Saldo_Inicial=%s, "
            "Saldo_Atual=%s, Moeda=%s, Tipo=%s, Situacao=%s, ContaPrincipalPainel=%s WHERE codigo=%s",
            (descricao, banco_txt, agencia, numero, saldo_inicial_novo, saldo_atual_novo,
             moeda, tipo, situacao, conta_principal, int(codigo)),
        )
        conn.commit()
        cur.close()

        houve_ajuste_saldo = saldo_inicial_novo != saldo_inicial_atual
        return {
            "success": True, "codigo": int(codigo), "message": "Conta gravada.",
            "ajuste_saldo": houve_ajuste_saldo,
            "saldo_inicial_anterior": saldo_inicial_atual, "saldo_atual_novo": saldo_atual_novo,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM previsoes WHERE (tipo<>2 AND conta=%s) OR (tipo=2 AND classe=%s)",
            (codigo, codigo),
        )
        if cur.fetchone():
            return {"success": False, "message": "Esta conta possui previsões associadas. Exclusão não permitida."}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM movimentacoes WHERE (tipo<>2 AND conta=%s) OR (tipo=2 AND classe=%s)",
            (codigo, codigo),
        )
        if cur.fetchone():
            return {"success": False, "message": "Esta conta possui movimentações associadas. Exclusão não permitida."}
        cur.execute("DELETE FROM Contas WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Conta excluída."}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def list_contas(servidor: str, banco: str, busca: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, busca)


async def get_conta(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_sync, servidor, banco, codigo)


async def save_conta(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, dados)


async def delete_conta(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, codigo)

"""Financeiro > Fluxo de Caixa: Plano de Contas + Centro de Custo.

Plano de Contas — duas tabelas em relação pai/filho:
  classes(codigo IDENTITY, descricao, tipo, conta_transf_contabil)
  sub_classes(codigo IDENTITY, classe FK -> classes.codigo, descricao, tipo,
              conta_transf_contabil, situacao_sub_classe)

`tipo` é 'R' (Receita) ou 'D' (Despesa) — em ambos os níveis, independentemente
(o legado deixa herdar o tipo da classe ao trocar de combo, mas grava o campo em
cada nível). `situacao_sub_classe` ('A'/'D') só existe em sub_classes — não há
campo equivalente em classes.

Fora de escopo por enquanto: `conta_transf_contabil` (conta contábil de
transferência, FK para `Plano_<ano_exercicio>` — tabela ano a ano cujo
"ano_exercicio" usar já está marcado como não resolvido em CLAUDE.md para o
cadastro de cliente; mesma decisão aqui).

Delete guard (Classe/SubClasse): o legado varre dezenas de tabelas próprias
(movimentacoes, pagar_custo, receber_custo, n_fiscal_custo, niveis,
contratos_centro_custo, controle...) que não existem/não são usadas por este
app ainda. Aqui checamos só o que este app de fato grava: `cliente.classe_caixa`
/ `sub_classe_caixa` (cadastro completo de cliente), `forma_pagamento.classe_caixa`
/ `sub_classe_caixa` (tela Forma de Pagamento) e `centro_custo.classe_entrada` /
`sub_classe_entrada` / `classe_saida` / `sub_classe_saida` (tela Centro de Custo,
abaixo). Diferente do legado (que permite excluir uma Classe cascateando suas
SubClasses), aqui bloqueamos a exclusão da Classe enquanto ela tiver
SubClasses — mesmo padrão de bloqueio (sem cascata) já usado em Marca/Modelo.

Centro de Custo — tabela única:
  centro_custo(codigo int PK **não-identity, digitado pelo usuário**, descricao,
               classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida)
Diferente de Classes/SubClasses, `codigo` aqui não é gerado automaticamente — é
natural key digitada pelo usuário (mesmo padrão do legado FrmManCeC), e a
gravação é upsert-by-codigo (grava se não existe, atualiza se já existe), não
create/update por presença de parâmetro. Uma vez criado, o código fica travado
no frontend (não pode virar um registro novo por engano). Existem também as
colunas `conta`/`grau` na tabela, não usadas em lugar nenhum do formulário
legado e por isso fora de escopo aqui.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc

TIPOS_VALIDOS = ("R", "D")


def _norm_tipo(tipo: Optional[str]) -> str:
    t = (tipo or "").strip().upper()
    return t if t in TIPOS_VALIDOS else "D"


def _list_plano_contas_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, descricao, tipo, conta_transf_contabil FROM classes ORDER BY descricao")
        classes = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
            "tipo": _norm_tipo(r.get("tipo")),
            "sub_classes": [],
        } for r in cur.fetchall()]

        cur.execute(
            "SELECT codigo, classe, descricao, tipo, situacao_sub_classe "
            "FROM sub_classes ORDER BY descricao"
        )
        by_classe: dict = {}
        for r in cur.fetchall():
            classe_cod = int(r["classe"]) if r.get("classe") is not None else None
            by_classe.setdefault(classe_cod, []).append({
                "codigo": int(r["codigo"]),
                "classe": classe_cod,
                "descricao": (r.get("descricao") or "").strip(),
                "tipo": _norm_tipo(r.get("tipo")),
                "ativa": (r.get("situacao_sub_classe") or "A").strip().upper() != "D",
            })
        for c in classes:
            c["sub_classes"] = by_classe.get(c["codigo"], [])

        cur.close()

        term = (search or "").strip().lower()
        if term:
            classes = [
                c for c in classes
                if term in c["descricao"].lower()
                or any(term in sc["descricao"].lower() for sc in c["sub_classes"])
            ]

        return {"success": True, "items": classes}
    finally:
        conn.close()


def _save_classe_sync(servidor: str, banco: str, codigo: Optional[int], descricao: str, tipo: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    tipo_v = _norm_tipo(tipo)
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 codigo FROM classes WHERE descricao=%s AND codigo<>%s",
            (desc, codigo or 0),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Já existe uma classe com essa descrição."}

        if codigo:  # update
            cur.execute("UPDATE classes SET descricao=%s, tipo=%s WHERE codigo=%s", (desc, tipo_v, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Classe não encontrada."}
            novo = codigo
        else:  # create — codigo é IDENTITY
            cur.execute(
                "INSERT INTO classes (descricao, tipo) OUTPUT INSERTED.codigo VALUES (%s, %s)",
                (desc, tipo_v),
            )
            row = cur.fetchone()
            novo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Classe gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_classe_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM sub_classes WHERE classe=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Classe possui SubClasses vinculadas — exclua-as primeiro."}
        cur.execute("SELECT TOP 1 1 AS ok FROM cliente WHERE classe_caixa=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Classe vinculada a clientes — não pode ser excluída."}
        cur.execute("SELECT TOP 1 1 AS ok FROM forma_pagamento WHERE classe_caixa=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Classe vinculada a formas de pagamento — não pode ser excluída."}
        cur.execute("SELECT TOP 1 1 AS ok FROM centro_custo WHERE classe_entrada=%s OR classe_saida=%s", (codigo, codigo))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Classe vinculada a centros de custo — não pode ser excluída."}
        cur.execute("DELETE FROM classes WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Classe excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _save_subclasse_sync(
    servidor: str, banco: str, codigo: Optional[int], classe: int, descricao: str, tipo: str, ativa: bool,
) -> dict:
    desc = (descricao or "").strip()
    if not classe:
        return {"success": False, "message": "Selecione a classe."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    tipo_v = _norm_tipo(tipo)
    situacao = "A" if ativa else "D"
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM classes WHERE codigo=%s", (classe,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Classe inexistente."}
        cur.execute(
            "SELECT TOP 1 codigo FROM sub_classes WHERE descricao=%s AND classe=%s AND codigo<>%s",
            (desc, classe, codigo or 0),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Já existe uma SubClasse com essa descrição nesta classe."}

        if codigo:  # update
            cur.execute(
                "UPDATE sub_classes SET classe=%s, descricao=%s, tipo=%s, situacao_sub_classe=%s WHERE codigo=%s",
                (classe, desc, tipo_v, situacao, codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "SubClasse não encontrada."}
            novo = codigo
        else:  # create — codigo é IDENTITY
            cur.execute(
                "INSERT INTO sub_classes (classe, descricao, tipo, situacao_sub_classe) "
                "OUTPUT INSERTED.codigo VALUES (%s, %s, %s, %s)",
                (classe, desc, tipo_v, situacao),
            )
            row = cur.fetchone()
            novo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "SubClasse gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_subclasse_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT classe FROM sub_classes WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "SubClasse não encontrada."}
        classe = row["classe"]
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM cliente WHERE classe_caixa=%s AND sub_classe_caixa=%s",
            (classe, codigo),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "SubClasse vinculada a clientes — não pode ser excluída."}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM forma_pagamento WHERE classe_caixa=%s AND sub_classe_caixa=%s",
            (classe, codigo),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "SubClasse vinculada a formas de pagamento — não pode ser excluída."}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM centro_custo WHERE sub_classe_entrada=%s OR sub_classe_saida=%s",
            (codigo, codigo),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "SubClasse vinculada a centros de custo — não pode ser excluída."}
        cur.execute("DELETE FROM sub_classes WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "SubClasse excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- CENTRO DE CUSTO ----------------
def _list_centro_custo_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR CAST(codigo AS NVARCHAR) LIKE %s"
            params = (like, like)
        cur.execute(
            "SELECT codigo, descricao, classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida "
            f"FROM centro_custo {where} ORDER BY codigo",
            params,
        )
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
            "classe_entrada": r.get("classe_entrada"),
            "sub_classe_entrada": r.get("sub_classe_entrada"),
            "classe_saida": r.get("classe_saida"),
            "sub_classe_saida": r.get("sub_classe_saida"),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_centro_custo_sync(
    servidor: str, banco: str, codigo: int, descricao: str,
    classe_entrada: Optional[int], sub_classe_entrada: Optional[int],
    classe_saida: Optional[int], sub_classe_saida: Optional[int],
) -> dict:
    desc = (descricao or "").strip()
    if not codigo:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "centro_custo")
        desc_v = _trunc(desc, sz, "descricao", 30)
        cur.execute("SELECT TOP 1 1 AS ok FROM centro_custo WHERE codigo=%s", (codigo,))
        exists = cur.fetchone() is not None
        params = (desc_v, classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida)
        if exists:  # upsert-by-codigo: codigo não é IDENTITY (digitado pelo usuário)
            cur.execute(
                "UPDATE centro_custo SET descricao=%s, classe_entrada=%s, sub_classe_entrada=%s, "
                "classe_saida=%s, sub_classe_saida=%s WHERE codigo=%s",
                params + (codigo,),
            )
        else:
            cur.execute(
                "INSERT INTO centro_custo (codigo, descricao, classe_entrada, sub_classe_entrada, "
                "classe_saida, sub_classe_saida) VALUES (%s,%s,%s,%s,%s,%s)",
                (codigo,) + params,
            )
        conn.commit()
        cur.close()
        return {"success": True, "codigo": codigo, "message": "Centro de custo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_centro_custo_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM centro_custo WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Centro de custo não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Centro de custo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def list_plano_contas(servidor, banco, search):
    return await asyncio.to_thread(_list_plano_contas_sync, servidor, banco, search)


async def save_classe(servidor, banco, codigo, descricao, tipo):
    return await asyncio.to_thread(_save_classe_sync, servidor, banco, codigo, descricao, tipo)


async def delete_classe(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_classe_sync, servidor, banco, codigo)


async def save_subclasse(servidor, banco, codigo, classe, descricao, tipo, ativa):
    return await asyncio.to_thread(_save_subclasse_sync, servidor, banco, codigo, classe, descricao, tipo, ativa)


async def delete_subclasse(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_subclasse_sync, servidor, banco, codigo)


async def list_centro_custo(servidor, banco, search):
    return await asyncio.to_thread(_list_centro_custo_sync, servidor, banco, search)


async def save_centro_custo(servidor, banco, codigo, descricao, classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida):
    return await asyncio.to_thread(
        _save_centro_custo_sync, servidor, banco, codigo, descricao,
        classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida,
    )


async def delete_centro_custo(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_centro_custo_sync, servidor, banco, codigo)

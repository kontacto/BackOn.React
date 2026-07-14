"""Combustíveis (Posto de Combustível) — tabela `combustivel`.

Legado: `FRMMANCOM.FRM` ("Cadastro de Combustível"). `codigo` é `smallint`
(0-255, estilo "byte" do VB6), chave própria — confirmado por FK real de
`bomba`/`estoque`/`tanque`/`mov_bomba`/`abastecimento` apontando pra
`combustivel.codigo` (GERDELL/BARESTELA, `sys.foreign_keys`).

**Campos deliberadamente fora de escopo** (lidos no código-fonte, não
implementados aqui, com justificativa):
- `estoque`: campo oculto no `.frm` (`Visible=0`, fora da área visível da
  tela) — sempre 0 na inclusão, nunca editado pelo usuário nesta tela;
  gerenciado por outro fluxo (tela "Estoque Combustível"/abastecimentos).
  Não exposto como campo editável aqui, fiel ao legado.
- `custo`: o código de `CmDinclui_Click` referencia `Campo(4)` como
  obrigatório, mas **não existe nenhum `TextBox`/`MaskEdBox` com Index=4
  declarado no `.frm`** — nem em `Campo_LostFocus` nem em nenhum outro
  lugar do formulário. E o bloco equivalente em `CmDaltera_Click` está
  **inteiramente comentado** (`'If Not IsNumeric(Campo(4))...`). Ou seja,
  na prática Custo não é editável nesta tela — é dead code (talvez um
  campo removido do form numa versão anterior, sem remover o código).
  Custo de combustível é gerenciado pela tela separada "Custo
  Combustível" (`frmmancus.frm`/`Custo_Combustivel`, não migrada ainda).
  Esta tela NÃO grava em `combustivel.custo` (nem no insert nem no
  update) — evita replicar o bug de zerar o custo a cada alteração que o
  legado tinha (`TbCom("Custo") = NumCus` com `NumCus` sempre 0 no
  Altera, já que o bloco que o preenche está comentado).
- `grupo` (FK conceitual pra `combustivel_grupo`, usada por Metas
  Combustível): `FRMMANCOM.FRM` nunca lê nem grava essa coluna — deixado
  de fora, registrado como dúvida aberta em PENDENCIAS.md (onde esse
  vínculo é definido, se é que é usado por alguma tela ainda não
  fornecida).
- Cascata pra `pecas`/`estoque` (o legado, ao Alterar preço, também roda
  `UPDATE pecas SET p_venda=... WHERE codigo_fab=<código>` e `UPDATE
  estoque SET venda=...`, tratando o combustível como um produto/pecas
  em paralelo) e o push de preço pro hardware (Wayne Fusion) — fora de
  escopo desta fase, ver PENDENCIAS.md.

Guard de exclusão replicado fielmente: bloqueia se houver `movimentacao`
vinculada via `pecas.codigo_fab = <código>` (mesmo JOIN do
`CmDexclui_Click` original).
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG

_CAMPOS = [
    "descricao", "venda", "venda2", "codigo_automacao", "indImport", "cUFOrig", "pOrig",
]


def _row_to_dict(r: dict) -> dict:
    return {
        "codigo": int(r["codigo"]),
        "descricao": (r.get("descricao") or "").strip(),
        "venda": float(r.get("venda") or 0),
        "venda2": float(r.get("venda2") or 0),
        "codigo_automacao": int(r["codigo_automacao"]) if r.get("codigo_automacao") is not None else None,
        "indImport": (r.get("indImport") or "").strip(),
        "cUFOrig": (r.get("cUFOrig") or "").strip(),
        "pOrig": float(r.get("pOrig") or 0),
    }


def _list_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        cur.execute("SELECT codigo, descricao, venda, venda2 FROM combustivel ORDER BY codigo")
        items = [
            {
                "codigo": int(r["codigo"]),
                "descricao": (r.get("descricao") or "").strip(),
                "venda": float(r.get("venda") or 0),
                "venda2": float(r.get("venda2") or 0),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _get_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cols = "codigo," + ",".join(_CAMPOS)
        cur.execute(f"SELECT {cols} FROM combustivel WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Combustível não encontrado."}
        return {"success": True, "item": _row_to_dict(row)}
    finally:
        conn.close()


def _save_sync(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    if codigo is None or not (0 <= int(codigo) <= 255):
        return {"success": False, "message": "Código inválido — deve estar entre 0 e 255."}
    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return {"success": False, "message": "Informe a descrição."}
    if dados.get("venda") is None:
        return {"success": False, "message": "Informe o preço de venda."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT 1 AS ok FROM combustivel WHERE codigo=%s", (codigo,))
        existe = cur.fetchone() is not None

        valores = {
            "descricao": descricao,
            "venda": float(dados.get("venda") or 0),
            "venda2": float(dados.get("venda2") or 0),
            "codigo_automacao": dados.get("codigo_automacao"),
            "indImport": (dados.get("indImport") or "").strip() or None,
            "cUFOrig": (dados.get("cUFOrig") or "").strip() or None,
            "pOrig": float(dados.get("pOrig") or 0),
        }

        if existe:
            set_clause = ", ".join(f"{c}=%s" for c in _CAMPOS)
            params = [valores.get(c) for c in _CAMPOS] + [codigo]
            cur.execute(f"UPDATE combustivel SET {set_clause} WHERE codigo=%s", params)
        else:
            cols = ["codigo", "estoque"] + _CAMPOS
            placeholders = ",".join(["%s"] * len(cols))
            params = [codigo, 0] + [valores.get(c) for c in _CAMPOS]
            cur.execute(f"INSERT INTO combustivel ({','.join(cols)}) VALUES ({placeholders})", params)
        conn.commit()
        return {"success": True, "message": "Combustível gravado.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM MOVIMENTACAO m JOIN PECAS p ON p.CODIGO_INT = m.CODIGO_INT "
            "WHERE p.CODIGO_FAB=%s",
            (str(codigo),),
        )
        if cur.fetchone():
            return {"success": False, "message": "Existem vendas associadas a este combustível — não pode ser excluído."}
        cur.execute("DELETE FROM combustivel WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Combustível não encontrado."}
        conn.commit()
        return {"success": True, "message": "Combustível excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_combustiveis(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco)


async def get_combustivel(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_sync, servidor, banco, codigo)


async def save_combustivel(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, codigo, dados)


async def delete_combustivel(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, codigo)

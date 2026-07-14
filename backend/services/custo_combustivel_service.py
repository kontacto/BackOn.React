"""Custo de Combustível (Posto de Combustível) — tabela `Custo_Combustivel`.

Legado: `frmmancus.frm` ("Custo Combustível"). **Só tem botão "Altera"** —
não existe Incluir nem Excluir neste `.frm` (só navegação
Anterior/Próximo/Primeiro/Último por um recordset filtrado por
combustível, com edição da Data/Entrada/Saída/Custo do registro
"corrente"). Migrado fielmente: esta tela só **lista e atualiza**
registros já existentes — a criação de linhas novas em
`Custo_Combustivel` é feita por outro processo/tela não fornecido (é
razoável supor que seja o lançamento de Nota Fiscal de compra de
combustível — ver "Tanque/Nota Fiscal", ainda não migrada — mas isso não
está confirmado no código-fonte disponível; registrado como dúvida em
PENDENCIAS.md).

Schema conferido ao vivo em GERDELL/BARESTELA: `Custo_Combustivel`
(cod_cus int IDENTITY — confirmado via `COLUMNPROPERTY`; combustivel
smallint, data date, seq smallint, entrada float, saida float, custo
float). Sendo IDENTITY, a criação de linhas é responsabilidade de outro
processo/tela que faz o INSERT (sem especificar `cod_cus`) — esta tela
migrada não precisa nem deve tentar gerar esse código.
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG


def _list_sync(servidor: str, banco: str, combustivel: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT cod_cus, combustivel, data, seq, entrada, saida, custo "
            "FROM Custo_Combustivel WHERE combustivel=%s ORDER BY data, seq",
            (combustivel,),
        )
        items = [
            {
                "cod_cus": int(r["cod_cus"]),
                "combustivel": int(r["combustivel"]) if r.get("combustivel") is not None else None,
                "data": str(r["data"]) if r.get("data") else None,
                "seq": int(r["seq"]) if r.get("seq") is not None else None,
                "entrada": float(r.get("entrada") or 0),
                "saida": float(r.get("saida") or 0),
                "custo": float(r.get("custo") or 0),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _update_sync(servidor: str, banco: str, cod_cus: int, data: str, entrada: float, saida: float, custo: float) -> dict:
    if not data:
        return {"success": False, "message": "Informe a data."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute(
            "UPDATE Custo_Combustivel SET data=%s, entrada=%s, saida=%s, custo=%s WHERE cod_cus=%s",
            (data, entrada, saida, custo, cod_cus),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Registro não encontrado."}
        conn.commit()
        return {"success": True, "message": "Custo atualizado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


async def list_custos(servidor: str, banco: str, combustivel: int) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, combustivel)


async def update_custo(servidor: str, banco: str, cod_cus: int, data: str, entrada: float, saida: float, custo: float) -> dict:
    return await asyncio.to_thread(_update_sync, servidor, banco, cod_cus, data, entrada, saida, custo)

"""Cadastros > Contatos.

Migração de `FrmContatos.frm` (VB6, "Cadastro de Contatos...") — registro
de contatos/leads (não necessariamente clientes já cadastrados; os
`tipo_cliente_contato` incluem "Prospect"/"Não Contactado"/"Sem
Possibilidade", ou seja, pessoas que podem nunca ter virado cliente de
fato). Tabela `contatos`.

Fora de escopo / inferido sem fonte completa (ver PENDENCIAS.md pro
detalhe de cada item):
  • `FrmConCli2.frm` (seletor de cliente via F2 no legado) não foi
    fornecido — mas `contatos.cliente` já era **texto livre** no legado
    (nvarchar(60), nunca validado contra a tabela `cliente`), então aqui
    vira busca (reaproveita `GET /api/clientes/find/search` +
    `ClientSearchModal`, componente já usado em Pedido/O.S.) que só
    preenche o nome digitado — não trava o valor a um cliente cadastrado.
  • `CHAMA2()` (sub declarada no `.frm` mas sem nenhum call site visível
    no código fornecido) parece existir pra auto-preencher Telefone a
    partir do cliente selecionado (lê `cliente_tel` por nome) — replicado
    por inferência no frontend (preenche Telefone só se ainda vazio, ao
    escolher um cliente na busca), não confirmado contra o
    `FrmConCli2.frm` real.
  • `FrmConsContatos.frm` (tela de consulta, botão "Consultar" no
    cadastro) não foi fornecido — os filtros replicados aqui vêm do
    screenshot fornecido + do setup em `Command9_Click` de
    `FrmContatos.frm`, não de um `.frm` de consulta rastreado linha a
    linha.
  • `Command2_Click` (botão "Imprimir" oculto, `Visible=False` no `.frm`)
    é um caminho de INSERT morto/inalcançável pela UI (usa ADO
    AddNew/Update, grava `telefone_1` — campo que nenhum controle visível
    do form preenche) — não replicado.
  • Coluna `Telefone_1` existe na tabela mas não é escrita nem lida pelo
    caminho de gravação realmente usado pela UI (`Command20_Click`, nem
    exibida em `chama()`, onde a linha que a leria está comentada) — não
    implementada aqui.

Melhoria aplicada (não é regra de negócio, é robustez técnica): o legado
(`Command20_Click`) edita um registro existente **apagando a linha e
inserindo outra nova** (`DELETE` seguido de `INSERT`, perdendo o
`codigo` original a cada edição). Aqui vira um `UPDATE` de verdade,
preservando o `codigo` — seguro porque nenhuma FK aponta pra
`contatos.codigo` (conferido ao vivo em GERDELL/BARESTELA).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _list_sync(
    servidor: str, banco: str,
    data_de: Optional[str], data_ate: Optional[str],
    prev_de: Optional[str], prev_ate: Optional[str],
    cliente: Optional[str], contato: Optional[str], telefone: Optional[str],
    tipo_cliente: Optional[int], profissional: Optional[int],
) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if data_de:
            where.append("c.data >= %s"); params.append(data_de)
        if data_ate:
            where.append("c.data <= %s"); params.append(data_ate)
        if prev_de:
            where.append("c.data_prev >= %s"); params.append(prev_de)
        if prev_ate:
            where.append("c.data_prev <= %s"); params.append(prev_ate)
        if cliente and cliente.strip():
            where.append("c.cliente LIKE %s"); params.append(f"%{cliente.strip()}%")
        if contato and contato.strip():
            where.append("c.contato LIKE %s"); params.append(f"%{contato.strip()}%")
        if telefone and telefone.strip():
            like = f"%{telefone.strip()}%"
            where.append("(c.telefone LIKE %s OR c.Telefone_2 LIKE %s)")
            params += [like, like]
        if tipo_cliente:
            where.append("c.tipo_cliente = %s"); params.append(tipo_cliente)
        if profissional:
            where.append("c.profissional = %s"); params.append(profissional)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        cur.execute(
            "SELECT c.codigo, c.data, c.cliente, c.telefone, c.Telefone_2 AS telefone_2, "
            "c.tipo_cliente, tc.nome AS tipo_cliente_nome, c.contato, c.profissional, "
            "f.nome_guerra AS profissional_nome, c.data_prev, c.hora_prev, c.obs, "
            "c.e_mail, c.endereco, c.bairro, c.Indicacao AS indicacao "
            "FROM contatos c "
            "LEFT JOIN tipo_cliente_contato tc ON tc.codigo = c.tipo_cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = c.profissional "
            f"{where_sql} ORDER BY c.data DESC, c.codigo DESC",
            tuple(params),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "data": r["data"].isoformat() if r.get("data") else None,
            "cliente": (r.get("cliente") or "").strip(),
            "telefone": (r.get("telefone") or "").strip(),
            "telefone_2": (r.get("telefone_2") or "").strip(),
            "tipo_cliente": r.get("tipo_cliente"),
            "tipo_cliente_nome": (r.get("tipo_cliente_nome") or "").strip() or None,
            "contato": (r.get("contato") or "").strip(),
            "profissional": r.get("profissional"),
            "profissional_nome": (r.get("profissional_nome") or "").strip() or None,
            "data_prev": r["data_prev"].isoformat() if r.get("data_prev") else None,
            "hora_prev": (r.get("hora_prev") or "").strip() or None,
            "obs": r.get("obs") or "",
            "e_mail": (r.get("e_mail") or "").strip(),
            "endereco": (r.get("endereco") or "").strip(),
            "bairro": (r.get("bairro") or "").strip(),
            "indicacao": (r.get("indicacao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _save_sync(
    servidor: str, banco: str, codigo: Optional[int],
    data: Optional[str], cliente: Optional[str], telefone: Optional[str], telefone_2: Optional[str],
    tipo_cliente: Optional[int], contato: Optional[str], profissional: Optional[int],
    data_prev: Optional[str], hora_prev: Optional[str], obs: Optional[str],
    e_mail: Optional[str], endereco: Optional[str], bairro: Optional[str], indicacao: Optional[str],
) -> dict:
    if not data:
        return {"success": False, "message": "Defina a data corretamente."}
    if not (cliente or "").strip():
        return {"success": False, "message": "Defina o cliente corretamente."}
    if not tipo_cliente:
        return {"success": False, "message": "Defina o tipo de cliente corretamente."}
    if not profissional:
        return {"success": False, "message": "Defina o profissional corretamente."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        params = (
            data, cliente.strip(), (telefone or "").strip(), tipo_cliente, (contato or "").strip(),
            profissional, (e_mail or "").strip(), (obs or "").strip() or " ",
            (endereco or "").strip(), (bairro or "").strip(), (indicacao or "").strip(),
            (telefone_2 or "").strip() or None, data_prev or None, (hora_prev or "").strip() or None,
        )
        if codigo:
            cur.execute(
                "UPDATE contatos SET data=%s, cliente=%s, telefone=%s, tipo_cliente=%s, contato=%s, "
                "profissional=%s, e_mail=%s, obs=%s, endereco=%s, bairro=%s, Indicacao=%s, "
                "Telefone_2=%s, data_prev=%s, hora_prev=%s WHERE codigo=%s",
                params + (codigo,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                cur.close()
                return {"success": False, "message": "Contato não encontrado."}
            novo_codigo = codigo
        else:
            cur.execute(
                "INSERT INTO contatos (data, cliente, telefone, tipo_cliente, contato, profissional, "
                "e_mail, obs, endereco, bairro, Indicacao, Telefone_2, data_prev, hora_prev) "
                "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                params,
            )
            row = cur.fetchone()
            novo_codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo_codigo, "message": "Contato gravado."}
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
        cur.execute("DELETE FROM contatos WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Contato não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Contato excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def list_contatos(
    servidor, banco, data_de=None, data_ate=None, prev_de=None, prev_ate=None,
    cliente=None, contato=None, telefone=None, tipo_cliente=None, profissional=None,
):
    return await asyncio.to_thread(
        _list_sync, servidor, banco, data_de, data_ate, prev_de, prev_ate,
        cliente, contato, telefone, tipo_cliente, profissional,
    )


async def save_contato(
    servidor, banco, codigo, data, cliente, telefone, telefone_2, tipo_cliente, contato,
    profissional, data_prev, hora_prev, obs, e_mail, endereco, bairro, indicacao,
):
    return await asyncio.to_thread(
        _save_sync, servidor, banco, codigo, data, cliente, telefone, telefone_2, tipo_cliente,
        contato, profissional, data_prev, hora_prev, obs, e_mail, endereco, bairro, indicacao,
    )


async def delete_contato(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_sync, servidor, banco, codigo)

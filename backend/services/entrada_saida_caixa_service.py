"""Cadastros > Entrada/Saída de Caixa.

Fica em Cadastros, não em Financeiro — é o caixa OPERACIONAL da loja
(recebe as vendas do dia), não o caixa financeiro (Financeiro > Fluxo de
Caixa, tabela `movimentacoes`); pedido explícito do usuário.

Migração de `FrmManESC.frm` (VB6) — lançamentos do **caixa operacional da
loja** (recebe as vendas do dia), não o caixa financeiro. Duas tabelas
físicas, mesmo shape:
  entrada_caixa(codigo IDENTITY, data, atendente, turno, valor, descricao,
                transf_caixa, centro_custo, classe, sub_classe, favorecido,
                conta, cod_movimentacao, forma_pag, transferencia)
  saida_caixa(codigo IDENTITY, data, atendente, valor, descricao,
              transf_caixa, centro_custo, classe, sub_classe, favorecido,
              conta, cod_movimentacao, forma_pag, transferencia)
  (saida_caixa não tem `turno`.)

Uma única tela no legado (radio Entrada/Saída escolhe a tabela) — mantido
aqui como um único service/rota, `tipo` ("E"/"S") escolhe `entrada_caixa` x
`saida_caixa` a cada chamada, igual ao `IIf(...)` do VB6.

Fora de escopo desta migração (não tocado, não inventado — ver PENDENCIAS.md):
  • `turno` (entrada_caixa) e `transf_caixa` — nenhuma tela/rotina do .frm
    original grava esses dois campos; ficam de fora até rastrear onde são
    preenchidos no legado.
  • A transferência de fato para `movimentacoes` (o que populariza
    `cod_movimentacao`) — o .frm só CONSULTA `cod_movimentacao` pra bloquear
    edição/exclusão de um lançamento já transferido; a rotina que cria a
    movimentação em si não está neste form, é outro processo ainda não
    localizado no legado.
  • Recibo de impressão (Sangria_Suprimento, no VB6) usa impressora térmica
    local via COM — aqui vira uma visualização imprimível (impressão real de
    POS ainda não está implementada no projeto, ver memória
    "Impressão automática por Finalidade").

Regra de negócio preservada tal como está no legado (não é bug, é o dado
real da tabela): quando há Conta Destino (transferência entre duas contas),
o campo `classe` é reaproveitado para guardar o código da conta destino e
`sub_classe` é zerado, com `transferencia='2'`. Sem Conta Destino, `classe`/
`sub_classe` gravam os valores reais selecionados. Ver nota em
"Melhorias propostas" — candidato a virar uma coluna `conta_destino`
dedicada numa 2ª fase, não decidido/aplicado aqui.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

TIPOS_VALIDOS = ("E", "S")


def _tabela(tipo: str) -> str:
    return "entrada_caixa" if tipo == "E" else "saida_caixa"


def _resolve_favorecido_sync(cur, descricao: str) -> int:
    """Busca Favorecido por descrição; cria se não existir — mesmo
    comportamento do legado (Command1_Click), inclusive sem bloquear
    favorecido desconhecido (a checagem de existência do VB6 está comentada
    no form original)."""
    cur.execute("SELECT TOP 1 codigo FROM favorecidos WHERE descricao=%s", (descricao,))
    row = cur.fetchone()
    if row:
        return int(row["codigo"])
    cur.execute("INSERT INTO favorecidos (descricao) OUTPUT INSERTED.codigo VALUES (%s)", (descricao,))
    row = cur.fetchone()
    return int(row["codigo"] if isinstance(row, dict) else row[0])


def _get_config_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT transf_ent_sai_caixa FROM controle_aux")
        row = cur.fetchone()
        cur.close()
        flag = bool(row["transf_ent_sai_caixa"]) if row and row.get("transf_ent_sai_caixa") is not None else False
        return {"success": True, "transf_ent_sai_caixa": flag}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "transf_ent_sai_caixa": False}
    finally:
        conn.close()


def _list_sync(
    servidor: str, banco: str,
    data_de: Optional[str], data_ate: Optional[str],
    entradas: bool, saidas: bool,
) -> dict:
    # Mesma regra do legado (Command34_Click): nunca deixa a listagem vazia
    # por checkbox zerado — se os dois vierem desmarcados, força os dois.
    if not entradas and not saidas:
        entradas = saidas = True
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if data_de:
            where.append("data >= %s")
            params.append(data_de)
        if data_ate:
            where.append("data <= %s")
            params.append(data_ate)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        def _select(tipo: str, tabela: str, alias: str) -> str:
            return (
                f"SELECT '{tipo}' AS tipo, {alias}.codigo, {alias}.data, {alias}.atendente, "
                f"f.nome_guerra AS atendente_nome, {alias}.valor, {alias}.descricao, "
                f"{alias}.forma_pag, {alias}.conta, {alias}.centro_custo, {alias}.classe, "
                f"{alias}.sub_classe, {alias}.favorecido, {alias}.transferencia, {alias}.cod_movimentacao "
                f"FROM {tabela} {alias} LEFT JOIN funcionarios f ON f.codigo_int = {alias}.atendente {where_sql}"
            )

        parts = []
        all_params: list = []
        if entradas:
            parts.append(_select("E", "entrada_caixa", "ec"))
            all_params += params
        if saidas:
            parts.append(_select("S", "saida_caixa", "sc"))
            all_params += params
        query = " UNION ALL ".join(parts) + " ORDER BY data DESC, codigo DESC"
        cur.execute(query, tuple(all_params))
        items = [{
            "tipo": r["tipo"],
            "codigo": int(r["codigo"]),
            "data": r["data"].isoformat() if r.get("data") else None,
            "atendente": r.get("atendente"),
            "atendente_nome": (r.get("atendente_nome") or "").strip() or None,
            "valor": float(r["valor"]) if r.get("valor") is not None else 0.0,
            "descricao": (r.get("descricao") or "").strip(),
            "forma_pag": (r.get("forma_pag") or "").strip() or None,
            "conta": r.get("conta"),
            "centro_custo": r.get("centro_custo"),
            "classe": r.get("classe"),
            "sub_classe": r.get("sub_classe"),
            "favorecido": r.get("favorecido"),
            "transferencia": (r.get("transferencia") or "").strip() or None,
            "cod_movimentacao": r.get("cod_movimentacao"),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _save_sync(
    servidor: str, banco: str,
    codigo: Optional[int], tipo: str, valor, descricao: str, forma_pag: Optional[str],
    conta: Optional[int], conta_destino: Optional[int], favorecido_descricao: Optional[str],
    classe: Optional[int], sub_classe: Optional[int], centro_custo: Optional[int],
    atendente: Optional[int],
) -> dict:
    tipo_v = (tipo or "").strip().upper()
    if tipo_v not in TIPOS_VALIDOS:
        return {"success": False, "message": "Defina se é uma Entrada ou Saída de Caixa."}
    try:
        valor_v = float(valor)
    except (TypeError, ValueError):
        valor_v = 0
    if valor_v <= 0:
        return {"success": False, "message": "Defina o valor da Entrada/Saída de Caixa."}
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Defina a descrição da Entrada/Saída de Caixa."}
    if conta_destino and conta and int(conta_destino) == int(conta):
        return {"success": False, "message": "Conta origem e destino não podem ser a mesma."}

    tabela = _tabela(tipo_v)
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT transf_ent_sai_caixa FROM controle_aux")
        row = cur.fetchone()
        transf_ativo = bool(row["transf_ent_sai_caixa"]) if row and row.get("transf_ent_sai_caixa") is not None else False
        if transf_ativo:
            if not conta:
                cur.close()
                return {"success": False, "message": "Defina a conta do lançamento."}
            if not (favorecido_descricao or "").strip():
                cur.close()
                return {"success": False, "message": "Defina o favorecido do lançamento."}

        if codigo:
            cur.execute(f"SELECT cod_movimentacao FROM {tabela} WHERE codigo=%s", (codigo,))
            row = cur.fetchone()
            if not row:
                cur.close()
                return {"success": False, "message": "Lançamento não encontrado."}
            cod_mov = row.get("cod_movimentacao")
            if cod_mov:
                cur.execute("SELECT TOP 1 1 AS ok FROM movimentacoes WHERE codigo=%s", (cod_mov,))
                if cur.fetchone():
                    cur.close()
                    return {
                        "success": False,
                        "message": "Este lançamento já foi transferido para a movimentação financeira, "
                                    "portanto não pode ser alterado. Exclua-o primeiro no Financeiro.",
                    }
            cur.execute(f"UPDATE {tabela} SET valor=%s, descricao=%s WHERE codigo=%s", (valor_v, desc, codigo))
            novo_codigo = codigo
        else:
            cur.execute(
                f"INSERT INTO {tabela} (data, atendente, valor, descricao) "
                "OUTPUT INSERTED.codigo VALUES (CAST(GETDATE() AS DATE), %s, %s, %s)",
                (atendente, valor_v, desc),
            )
            row = cur.fetchone()
            novo_codigo = int(row["codigo"] if isinstance(row, dict) else row[0])

        favorecido_cod = None
        if (favorecido_descricao or "").strip():
            favorecido_cod = _resolve_favorecido_sync(cur, favorecido_descricao.strip())

        if conta_destino:
            cur.execute(
                f"UPDATE {tabela} SET conta=%s, centro_custo=%s, favorecido=%s, "
                "classe=%s, sub_classe=0, forma_pag=%s, transferencia='2' WHERE codigo=%s",
                (conta, centro_custo, favorecido_cod, conta_destino, forma_pag, novo_codigo),
            )
        else:
            cur.execute(
                f"UPDATE {tabela} SET conta=%s, centro_custo=%s, favorecido=%s, "
                "classe=%s, sub_classe=%s, forma_pag=%s WHERE codigo=%s",
                (conta, centro_custo, favorecido_cod, classe, sub_classe, forma_pag, novo_codigo),
            )
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo_codigo, "tipo": tipo_v, "message": "Lançamento gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, tipo: str, codigo: int) -> dict:
    tipo_v = (tipo or "").strip().upper()
    if tipo_v not in TIPOS_VALIDOS:
        return {"success": False, "message": "Tipo inválido."}
    tabela = _tabela(tipo_v)
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(f"SELECT cod_movimentacao FROM {tabela} WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Lançamento não encontrado."}
        cod_mov = row.get("cod_movimentacao")
        if cod_mov:
            cur.execute("SELECT TOP 1 1 AS ok FROM movimentacoes WHERE codigo=%s", (cod_mov,))
            if cur.fetchone():
                cur.close()
                return {
                    "success": False,
                    "message": "Este lançamento já foi transferido para a movimentação financeira, "
                                "portanto não pode ser excluído. Exclua-o primeiro no Financeiro.",
                }
        cur.execute(f"DELETE FROM {tabela} WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Lançamento excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def get_config(servidor, banco):
    return await asyncio.to_thread(_get_config_sync, servidor, banco)


async def list_lancamentos(servidor, banco, data_de, data_ate, entradas, saidas):
    return await asyncio.to_thread(_list_sync, servidor, banco, data_de, data_ate, entradas, saidas)


async def save_lancamento(
    servidor, banco, codigo, tipo, valor, descricao, forma_pag,
    conta, conta_destino, favorecido_descricao, classe, sub_classe, centro_custo, atendente,
):
    return await asyncio.to_thread(
        _save_sync, servidor, banco, codigo, tipo, valor, descricao, forma_pag,
        conta, conta_destino, favorecido_descricao, classe, sub_classe, centro_custo, atendente,
    )


async def delete_lancamento(servidor, banco, tipo, codigo):
    return await asyncio.to_thread(_delete_sync, servidor, banco, tipo, codigo)

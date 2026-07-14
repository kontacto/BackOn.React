"""Cadastros > Equipamentos.

Migração de `FrmManEquip.frm` (VB6, "Manutenção de Equipamentos.") — cada
equipamento pertence a um cliente (`equipamentos.cliente`, FK não
declarada mas sempre tratada como `cliente.codigo` no legado — diferente
de `contatos.cliente`, que é texto livre; aqui é sempre um código real).

Tabela `equipamentos` tem MUITAS outras colunas (casco, horas, aquisicao,
revenda, nf_compra, ano, fabricacao, passo, oleo, lancha, marinheiro) que
este `.frm` NUNCA lê nem grava — pertencem a outro domínio de equipamento
(embarcações?) fora do escopo desta tela. Não tocadas aqui.

Marca/Modelo reaproveitam os lookups já migrados de Tabelas Auxiliares
(`GET /api/tabelas/marcas`, `GET /api/tabelas/modelos?cod_marca=...`) —
`marcas.codigo`/`modelos.codigo` são texto de 3 chars, não IDENTITY.

Regras replicadas do legado:
  • `numero_de_serie` é ÚNICO GLOBALMENTE (entre TODOS os clientes), não
    só por cliente — a mensagem de erro do legado ("já cadastrado para
    este cliente") é enganosa; a query real (`Command1_Click`) não filtra
    por cliente. Replicado fielmente (a mensagem nova é mais clara sobre
    o motivo real).
  • Se Número de Série Interno vier vazio, grava igual ao Número de Série.
  • Excluir um equipamento também remove as linhas relacionadas em
    `contratos_produtos_disponiveis`/`contratos_produtos` (produto =
    numero_de_serie) — cascata deliberada do legado, não um guard de
    bloqueio (equipamento excluído não faz sentido continuar "disponível
    para contrato").
  • "Disponibilizar para Contrato": insere em
    `contratos_produtos_disponiveis` (qtd=1, qtd_alocada=0, preco=0,
    situacao='A') se ainda não existir uma linha para aquele produto.
  • "Alterar Número de Série": renomeia o número de série (e opcionalmente
    reatribui o cliente), cascateando pra `contratos_produtos_disponiveis`,
    `contratos_produtos`, `retifica` e `os.numero_de_serie`.
    **Confirmado pelo usuário (2026-07-12): o campo equivalente hoje é
    `os.numero_de_serie`, não `os.chassi`.** O legado só tinha um campo
    (`chassi`) porque ainda não existia a separação Oficina/Assistência
    Técnica; este projeto já migrou essa separação —
    `os.chassi` é exclusivo de OS de Oficina (veículo) e
    `os.numero_de_serie` é o de Assistência Técnica (equipamento), ver
    `models/schemas.py::OSSaveRequest` (comentários `# os.chassi
    (Oficina)` / `# os.numero_de_serie (Assistência)`). A cascata aqui
    usa exclusivamente `os.numero_de_serie` — nunca toca `os.chassi`.

Fora de escopo (não implementado, ver PENDENCIAS.md):
  • `Pos_Sistema` (checagem de estado do legado antes de Incluir/Alterar/
    Excluir/Disponibilizar) — não localizado no código fornecido, parece
    ligado a estado de sessão de caixa/PDV específico do legado; a nova
    arquitetura é stateless por requisição, não há equivalente óbvio.
  • Impressão com 4 níveis de ordenação configurável (Frame3 do `.frm`) —
    vira impressão simples da lista já filtrada na tela nova (mesma
    decisão de escopo já tomada em Entrada/Saída de Caixa e Contatos).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc

TIPOS_VALIDOS = ("A", "C")


def _find_by_serie_sync(servidor: str, banco: str, numero_de_serie: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, cliente FROM equipamentos WHERE numero_de_serie=%s",
            (numero_de_serie,),
        )
        row = cur.fetchone()
        cur.close()
        return {"success": True, "found": row is not None, "codigo": row.get("codigo") if row else None}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "found": False}
    finally:
        conn.close()


def _list_sync(
    servidor: str, banco: str, cliente: int,
    busca: Optional[str], tipo: Optional[str], situacao: Optional[str],
) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ["e.cliente = %s"]
        params: list = [cliente]
        if busca and busca.strip():
            like = f"%{busca.strip()}%"
            where.append("(e.numero_de_serie LIKE %s OR e.descricao_equipamento LIKE %s OR e.portador LIKE %s OR e.local LIKE %s)")
            params += [like, like, like, like]
        if tipo in TIPOS_VALIDOS:
            where.append("e.tipo_equipamento = %s"); params.append(tipo)
        if situacao in ("A", "D"):
            where.append("ISNULL(e.situacao_equipamento,'A') = %s"); params.append(situacao)
        where_sql = " AND ".join(where)
        cur.execute(
            "SELECT e.codigo, e.cliente, e.numero_de_serie, e.numero_de_serie_int, "
            "e.marca, ma.descricao AS marca_descricao, e.modelo, mo.descricao AS modelo_descricao, "
            "e.portador, e.local, e.tipo_equipamento, e.detalhe_equipamento, "
            "ISNULL(e.situacao_equipamento,'A') AS situacao_equipamento, "
            "e.descricao_equipamento, e.valor, e.revisao "
            "FROM equipamentos e "
            "LEFT JOIN marcas ma ON ma.codigo = e.marca "
            "LEFT JOIN modelos mo ON mo.codigo = e.modelo AND mo.cod_marca = e.marca "
            f"WHERE {where_sql} ORDER BY e.numero_de_serie",
            tuple(params),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "cliente": r.get("cliente"),
            "numero_de_serie": (r.get("numero_de_serie") or "").strip(),
            "numero_de_serie_int": (r.get("numero_de_serie_int") or "").strip(),
            "marca": (r.get("marca") or "").strip(),
            "marca_descricao": (r.get("marca_descricao") or "").strip() or None,
            "modelo": (r.get("modelo") or "").strip(),
            "modelo_descricao": (r.get("modelo_descricao") or "").strip() or None,
            "portador": (r.get("portador") or "").strip(),
            "local": (r.get("local") or "").strip(),
            "tipo_equipamento": (r.get("tipo_equipamento") or "A").strip() or "A",
            "detalhe_equipamento": r.get("detalhe_equipamento") or "",
            "situacao_equipamento": (r.get("situacao_equipamento") or "A").strip(),
            "descricao_equipamento": (r.get("descricao_equipamento") or "").strip(),
            "valor": float(r["valor"]) if r.get("valor") is not None else 0.0,
            "revisao": r["revisao"].isoformat() if r.get("revisao") else None,
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _save_sync(
    servidor: str, banco: str, codigo: Optional[int],
    cliente: Optional[int], numero_de_serie: Optional[str], numero_de_serie_int: Optional[str],
    marca: Optional[str], modelo: Optional[str], portador: Optional[str], local: Optional[str],
    tipo_equipamento: Optional[str], detalhe_equipamento: Optional[str],
    situacao_equipamento: Optional[str], descricao_equipamento: Optional[str],
    valor, revisao: Optional[str],
) -> dict:
    if not cliente:
        return {"success": False, "message": "Cliente ainda não definido."}
    num_serie = (numero_de_serie or "").strip()
    if not num_serie:
        return {"success": False, "message": "Insira o Número de Série."}
    if not (marca or "").strip():
        return {"success": False, "message": "Defina a Marca."}
    if not (modelo or "").strip():
        return {"success": False, "message": "Defina o Modelo."}
    tipo_v = (tipo_equipamento or "A").strip().upper()
    if tipo_v not in TIPOS_VALIDOS:
        tipo_v = "A"
    situacao_v = "A" if (situacao_equipamento or "A").strip().upper() == "A" else "D"
    try:
        valor_v = float(valor) if valor not in (None, "") else 0.0
    except (TypeError, ValueError):
        valor_v = 0.0
    num_serie_int = (numero_de_serie_int or "").strip() or num_serie

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "equipamentos")
        portador_v = _trunc((portador or "").strip(), sz, "portador", 40)
        local_v = _trunc((local or "").strip(), sz, "local", 40)
        descricao_v = _trunc((descricao_equipamento or "").strip(), sz, "descricao_equipamento", 50)

        # numero_de_serie é único GLOBALMENTE (entre todos os clientes) — mesma
        # regra do legado (Command1_Click), mensagem mais clara sobre o motivo.
        cur.execute("SELECT codigo FROM equipamentos WHERE numero_de_serie=%s", (num_serie,))
        existente = cur.fetchone()
        if existente and (not codigo or int(existente["codigo"]) != int(codigo)):
            cur.close()
            return {"success": False, "message": "Já existe um equipamento cadastrado com este Número de Série (em qualquer cliente)."}

        params = (
            cliente, num_serie, marca.strip()[:3], modelo.strip()[:3], portador_v, local_v,
            tipo_v, (detalhe_equipamento or "").strip(), num_serie_int, situacao_v,
            descricao_v, valor_v, revisao or None,
        )
        if codigo:
            cur.execute(
                "UPDATE equipamentos SET cliente=%s, numero_de_serie=%s, marca=%s, modelo=%s, "
                "portador=%s, local=%s, tipo_equipamento=%s, detalhe_equipamento=%s, "
                "numero_de_serie_int=%s, situacao_equipamento=%s, descricao_equipamento=%s, "
                "valor=%s, revisao=%s WHERE codigo=%s",
                params + (codigo,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                cur.close()
                return {"success": False, "message": "Equipamento não encontrado."}
            novo_codigo = codigo
        else:
            cur.execute(
                "INSERT INTO equipamentos (cliente, numero_de_serie, marca, modelo, portador, local, "
                "tipo_equipamento, detalhe_equipamento, numero_de_serie_int, situacao_equipamento, "
                "descricao_equipamento, valor, revisao) "
                "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                params,
            )
            row = cur.fetchone()
            novo_codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo_codigo, "message": "Equipamento gravado."}
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
        cur.execute("SELECT numero_de_serie FROM equipamentos WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Equipamento não encontrado."}
        num_serie = row["numero_de_serie"]
        cur.execute("DELETE FROM equipamentos WHERE codigo=%s", (codigo,))
        # Cascata deliberada do legado — ver docstring do módulo.
        cur.execute("DELETE FROM contratos_produtos_disponiveis WHERE produto=%s", (num_serie,))
        cur.execute("DELETE FROM contratos_produtos WHERE produto=%s", (num_serie,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Equipamento excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _disponibilizar_contrato_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT numero_de_serie FROM equipamentos WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Equipamento não encontrado."}
        num_serie = row["numero_de_serie"]
        cur.execute("SELECT TOP 1 1 AS ok FROM contratos_produtos_disponiveis WHERE produto=%s", (num_serie,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Este equipamento já está disponível para contrato."}
        cur.execute(
            "INSERT INTO contratos_produtos_disponiveis (produto, qtd, qtd_alocada, preco, obs, situacao) "
            "VALUES (%s, 1, 0, 0, '', 'A')",
            (num_serie,),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Equipamento disponibilizado para contrato."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _alterar_numero_serie_sync(
    servidor: str, banco: str, codigo: int, novo_numero_de_serie: str, novo_cliente: Optional[int],
) -> dict:
    novo_serie = (novo_numero_de_serie or "").strip()
    if not novo_serie:
        return {"success": False, "message": "Defina o novo Número de Série."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT numero_de_serie, cliente FROM equipamentos WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Equipamento não encontrado."}
        antigo_serie = row["numero_de_serie"]
        cliente_v = novo_cliente or row["cliente"]

        if novo_serie != antigo_serie:
            cur.execute("SELECT TOP 1 1 AS ok FROM equipamentos WHERE numero_de_serie=%s AND codigo<>%s", (novo_serie, codigo))
            if cur.fetchone():
                cur.close()
                return {"success": False, "message": "Já existe outro equipamento com este Número de Série."}

        cur.execute(
            "UPDATE equipamentos SET numero_de_serie=%s, cliente=%s WHERE codigo=%s",
            (novo_serie, cliente_v, codigo),
        )
        cur.execute("UPDATE contratos_produtos_disponiveis SET produto=%s WHERE produto=%s", (novo_serie, antigo_serie))
        cur.execute("UPDATE contratos_produtos SET produto=%s WHERE produto=%s", (novo_serie, antigo_serie))
        cur.execute("UPDATE retifica SET numero_de_serie=%s WHERE numero_de_serie=%s", (novo_serie, antigo_serie))
        # os.numero_de_serie é o campo de Assistência Técnica (equivalente
        # moderno do `chassi` do legado, que era só de Oficina — confirmado
        # pelo usuário). Casa por cliente ORIGINAL + numero_de_serie antigo,
        # mesma cautela do legado (nunca toca os.chassi).
        cur.execute(
            "UPDATE os SET numero_de_serie=%s, cliente=%s WHERE cliente=%s AND numero_de_serie=%s",
            (novo_serie, cliente_v, row["cliente"], antigo_serie),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Número de série alterado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def find_by_serie(servidor, banco, numero_de_serie):
    return await asyncio.to_thread(_find_by_serie_sync, servidor, banco, numero_de_serie)


async def list_equipamentos(servidor, banco, cliente, busca=None, tipo=None, situacao=None):
    return await asyncio.to_thread(_list_sync, servidor, banco, cliente, busca, tipo, situacao)


async def save_equipamento(
    servidor, banco, codigo, cliente, numero_de_serie, numero_de_serie_int, marca, modelo,
    portador, local, tipo_equipamento, detalhe_equipamento, situacao_equipamento,
    descricao_equipamento, valor, revisao,
):
    return await asyncio.to_thread(
        _save_sync, servidor, banco, codigo, cliente, numero_de_serie, numero_de_serie_int, marca, modelo,
        portador, local, tipo_equipamento, detalhe_equipamento, situacao_equipamento,
        descricao_equipamento, valor, revisao,
    )


async def delete_equipamento(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_sync, servidor, banco, codigo)


async def disponibilizar_contrato(servidor, banco, codigo):
    return await asyncio.to_thread(_disponibilizar_contrato_sync, servidor, banco, codigo)


async def alterar_numero_serie(servidor, banco, codigo, novo_numero_de_serie, novo_cliente):
    return await asyncio.to_thread(_alterar_numero_serie_sync, servidor, banco, codigo, novo_numero_de_serie, novo_cliente)

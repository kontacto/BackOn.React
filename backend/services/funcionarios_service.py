"""Funcionários — Cadastro completo (tabela `funcionarios` + sub-tabelas).

Legado: FrmManPro ("Manutenção de Funcionários"). Tela de Cadastros própria
(não Tabela Auxiliar), comparável em complexidade ao Cadastro Completo de
Cliente — várias tabelas relacionadas gravadas junto com o registro principal.

`codigo_int` NÃO é IDENTITY — atribuído via MAX+1 na inclusão, mesmo padrão
do legado (`Select Max(Codigo_Int) As Maximo From Funcionarios` + 1).

**Escopo excluído desta porta** (documentado aqui, não esquecido):
- Fotografia/webcam (Command24/26/27, capCreateCaptureWindow) — sem infra de
  upload/webcam neste app ainda (mesma limitação já documentada pra Cliente).
- Anexos (Command15, Gestor de Documentos) — subsistema de gestão de
  documentos não implementado neste app.
- Layouts (aba Especialidades, Layout1/Layout2, tabela `layout_profissional`)
  — sistema de layouts de impressão não implementado neste app.
- Posto/Tag (Posto1/Posto2, ligado a `Dados_Controle_Configuracao.Posto` e
  `abastecimento`) — subsistema de posto de combustível não implementado.
- Campos de folha de pagamento (salário base, valor hora, valor hora extra,
  INSS, FGTS, outros proventos/descontos, percentual vales mensal, turno,
  tipo profissional, "Por Meta"/tabela de metas) — TODOS esses controles já
  estão com `Visible = 0` no próprio `.frm` legado (confirmado lendo o
  arquivo fonte), ou seja, o legado já os escondeu da tela — não fazem parte
  da tela realmente usada hoje. Replicados apenas como colunas que existem
  no banco mas sem UI (deixadas em branco/default no INSERT).
- `funcionarios_dia_trab` — tabela citada pelo usuário, mas o código que a
  usa (`Command3_Click`/`Command6_Click`, ligados a um `Frame5`/`Command5`
  antigos) não corresponde a NENHUM botão visível no `.frm` atual (não há
  `Begin VB.CommandButton Command3` declarado) — é código morto de uma
  versão anterior do formulário. O horário semanal realmente usado hoje é
  `funcionarios_horarios`, gravado por `GravaHorarios()`/exibido pela grade
  Dias/Disponibilidade/Intervalo/Pausa/Encaixe (bate com o print da tela).
- `funcionarios_agenda` — tabela citada pelo usuário, mas não referenciada
  em NENHUM lugar deste `.frm` — pertence a outra funcionalidade (agenda de
  atendimento a clientes, não ao cadastro do funcionário). Fora de escopo
  desta tela.

**Correção de bug do legado**: `Command17_Click` grava `tipo_ps` como
`Left(CodExcecao, 1)` — mas `CodExcecao` nesse ponto já é o `codigo_int`
numérico do produto/serviço (resolvido antes), então isso grava só o
primeiro dígito do código, não um indicador real de Produto/Serviço. Aqui
`tipo_ps` é gravado corretamente ('P' ou 'S') conforme a tabela onde o item
foi de fato encontrado.
"""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn, _to_json_safe

CAMPOS_FUNCIONARIO = [
    "nome_guerra", "situacao", "nome", "cod_funcao", "email",
    "liberar_pedido_lista_negra", "liberar_pedido_limite_excedido",
    "admissao", "cpf_prof", "ident_prof", "cart_prof", "data_nasc", "sexo_prof",
    "CODIGO_DEP", "docespecial", "numespecial", "conselho", "numconselho", "codcargo",
    "cep_prof", "bairr_prof", "endereco", "cid_prof", "est_prof", "tel_prof",
    "Controla_Carteira",
    "tipo_comissao", "comissaop", "comissaos", "COMISSAO_PRIORIDADE_VENDEDOR",
    "tipo_comissao_e", "comissaop_e", "comissaos_e", "COMISSAO_PRIORIDADE_EXECUTOR",
    "tipo_comissao_a", "comissaop_a", "comissaos_a", "COMISSAO_PRIORIDADE_ATENDENTE",
    "DESCONTA_DESCARTAVEIS",
]


def _norm_nome_guerra(v: str) -> str:
    return (v or "").strip().upper()


def _coerce_vals(dados: dict) -> dict:
    def s(key, maxlen=None):
        v = (dados.get(key) or "").strip()
        return (v[:maxlen] if maxlen else v) or None

    def b(key):
        return 1 if dados.get(key) else 0

    def i(key):
        v = dados.get(key)
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def f(key):
        v = dados.get(key)
        try:
            return float(v) if v not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0

    return {
        "nome_guerra": _norm_nome_guerra(dados.get("nome_guerra"))[:15],
        "situacao": s("situacao", 2),
        "nome": (dados.get("nome") or "").strip()[:40],
        "cod_funcao": s("cod_funcao", 3),
        "email": (dados.get("email") or "").strip() or None,
        "liberar_pedido_lista_negra": b("liberar_pedido_lista_negra"),
        "liberar_pedido_limite_excedido": b("liberar_pedido_limite_excedido"),
        "admissao": dados.get("admissao") or None,
        "cpf_prof": s("cpf_prof", 11),
        "ident_prof": s("ident_prof", 10),
        "cart_prof": s("cart_prof", 13),
        "data_nasc": dados.get("data_nasc") or None,
        "sexo_prof": s("sexo_prof", 1),
        "CODIGO_DEP": s("codigo_dep", 50),
        "docespecial": i("docespecial"),
        "numespecial": s("numespecial", 15),
        "conselho": s("conselho", 15),
        "numconselho": s("numconselho", 15),
        "codcargo": i("codcargo"),
        "cep_prof": s("cep_prof", 8),
        "bairr_prof": s("bairr_prof", 50),
        "endereco": s("endereco", 60),
        "cid_prof": s("cid_prof", 20),
        "est_prof": s("est_prof", 2),
        "tel_prof": s("tel_prof", 15),
        "Controla_Carteira": b("controla_carteira"),
        "tipo_comissao": s("tipo_comissao", 1) or "S",
        "comissaop": f("comissaop"),
        "comissaos": f("comissaos"),
        "COMISSAO_PRIORIDADE_VENDEDOR": b("comissao_prioridade_vendedor"),
        "tipo_comissao_e": s("tipo_comissao_e", 1) or "S",
        "comissaop_e": f("comissaop_e"),
        "comissaos_e": f("comissaos_e"),
        "COMISSAO_PRIORIDADE_EXECUTOR": b("comissao_prioridade_executor"),
        "tipo_comissao_a": s("tipo_comissao_a", 1) or "S",
        "comissaop_a": f("comissaop_a"),
        "comissaos_a": f("comissaos_a"),
        "COMISSAO_PRIORIDADE_ATENDENTE": b("comissao_prioridade_atendente"),
        "DESCONTA_DESCARTAVEIS": b("desconta_comissao"),
    }


def _list_funcionarios_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE f.nome_guerra LIKE %s OR f.nome LIKE %s"
            params = (like, like)
        cur.execute(f"""
            SELECT f.codigo_int, f.nome_guerra, f.nome, f.situacao, fc.descricao AS funcao_descricao
            FROM funcionarios f
            LEFT JOIN Funcoes fc ON fc.codigo = f.cod_funcao
            {where}
            ORDER BY f.nome_guerra
        """, params)
        items = [{
            "codigo": int(r["codigo_int"]),
            "nome_guerra": (r.get("nome_guerra") or "").strip(),
            "nome": (r.get("nome") or "").strip(),
            "situacao": (r.get("situacao") or "").strip(),
            "funcao_descricao": (r.get("funcao_descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _get_funcionario_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cols = ", ".join(CAMPOS_FUNCIONARIO)
        cur.execute(f"SELECT codigo_int, {cols} FROM funcionarios WHERE codigo_int=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Funcionário não encontrado."}
        funcionario = _to_json_safe(row)
        for k, v in funcionario.items():
            if isinstance(v, str):
                funcionario[k] = v.strip()

        cur.execute("SELECT area FROM funcionarios_area WHERE func=%s", (codigo,))
        funcionario["areas_estoque"] = [int(r["area"]) for r in cur.fetchall()]

        cur.execute("SELECT area FROM funcionarios_area_atuacao WHERE func=%s", (codigo,))
        funcionario["areas_atuacao"] = [int(r["area"]) for r in cur.fetchall()]

        cur.execute("SELECT carteira FROM funcionarios_carteiras WHERE func=%s", (codigo,))
        funcionario["carteiras"] = [int(r["carteira"]) for r in cur.fetchall()]

        cur.execute("SELECT codigo_especialidade FROM funcionario_especialidades WHERE funcionario=%s", (codigo,))
        funcionario["especialidades"] = [int(r["codigo_especialidade"]) for r in cur.fetchall()]

        cur.execute(
            "SELECT dia, disp_ini, disp_fim, intervalo1, pausa_ini, pausa_fim, encaixe "
            "FROM funcionarios_horarios WHERE funcionario=%s ORDER BY dia",
            (codigo,),
        )
        funcionario["horarios"] = [_to_json_safe(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT codigo_funcionarios_ausencias, data_ini, data_fim, hora_ini, hora_fim, intervalo1, obs "
            "FROM funcionarios_ausencias WHERE funcionario=%s ORDER BY codigo_funcionarios_ausencias DESC",
            (codigo,),
        )
        funcionario["ausencias"] = [_to_json_safe(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT ce.cod_comissao_excecao, ce.item, ce.tipo, ce.tipo_ps, ce.comissao,
                   COALESCE(p.descricao, s.descricao) AS descricao
            FROM comissao_excecao ce
            LEFT JOIN pecas p ON ce.tipo_ps='P' AND p.codigo_int = ce.item
            LEFT JOIN servicos s ON ce.tipo_ps='S' AND s.codigo = ce.item
            WHERE ce.codigo_funcionario=%s
        """, (codigo,))
        funcionario["comissao_excecoes"] = [_to_json_safe(r) for r in cur.fetchall()]

        cur.close()
        return {"success": True, "funcionario": funcionario}
    finally:
        conn.close()


def _grava_relacionados(cur, codigo: int, dados: dict) -> None:
    cur.execute("DELETE FROM funcionarios_area WHERE func=%s", (codigo,))
    for area_id in dados.get("areas_estoque") or []:
        cur.execute("INSERT INTO funcionarios_area (func, area) VALUES (%s,%s)", (codigo, area_id))

    cur.execute("DELETE FROM funcionarios_area_atuacao WHERE func=%s", (codigo,))
    for area_id in dados.get("areas_atuacao") or []:
        cur.execute("INSERT INTO funcionarios_area_atuacao (func, area) VALUES (%s,%s)", (codigo, area_id))

    cur.execute("DELETE FROM funcionarios_carteiras WHERE func=%s", (codigo,))
    for cart_id in dados.get("carteiras") or []:
        cur.execute("INSERT INTO funcionarios_carteiras (func, carteira) VALUES (%s,%s)", (codigo, cart_id))

    cur.execute("DELETE FROM funcionario_especialidades WHERE funcionario=%s", (codigo,))
    for esp_id in dados.get("especialidades") or []:
        cur.execute(
            "INSERT INTO funcionario_especialidades (funcionario, codigo_especialidade) VALUES (%s,%s)",
            (codigo, esp_id),
        )

    cur.execute("DELETE FROM funcionarios_horarios WHERE funcionario=%s", (codigo,))
    for h in dados.get("horarios") or []:
        cur.execute(
            "INSERT INTO funcionarios_horarios "
            "(funcionario, dia, disp_ini, disp_fim, intervalo1, pausa_ini, pausa_fim, encaixe) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                codigo, h.get("dia"), h.get("disp_ini") or None, h.get("disp_fim") or None,
                h.get("intervalo1") or 0, h.get("pausa_ini") or None, h.get("pausa_fim") or None,
                h.get("encaixe") or 0,
            ),
        )


def _save_funcionario_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    nome_guerra = _norm_nome_guerra(dados.get("nome_guerra"))
    nome = (dados.get("nome") or "").strip()
    if not nome_guerra:
        return {"success": False, "message": "Preencha CodiNome Apropriadamente"}
    if not nome:
        return {"success": False, "message": "Preencha Nome Apropriadamente"}
    if not (dados.get("cod_funcao") or "").strip():
        return {"success": False, "message": "Preencha a Função Apropriadamente"}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo_int FROM funcionarios WHERE nome_guerra=%s", (nome_guerra,))
        existing = cur.fetchone()
        if existing and (not codigo or int(existing["codigo_int"]) != int(codigo)):
            cur.close()
            return {"success": False, "message": f"CodiNome {nome_guerra} Já Cadastrado"}

        vals = _coerce_vals(dados)
        vals["nome_guerra"] = nome_guerra

        if codigo:
            set_sql = ", ".join(f"{c}=%s" for c in CAMPOS_FUNCIONARIO)
            cur.execute(
                f"UPDATE funcionarios SET {set_sql} WHERE codigo_int=%s",
                tuple(vals[c] for c in CAMPOS_FUNCIONARIO) + (codigo,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Funcionário não encontrado."}
            novo_codigo = codigo
            acao = "alterado"
        else:
            cur.execute("SELECT ISNULL(MAX(codigo_int),0)+1 AS novo FROM funcionarios")
            novo_codigo = cur.fetchone()["novo"]
            cols_sql = ", ".join(["codigo_int"] + CAMPOS_FUNCIONARIO)
            placeholders = ", ".join(["%s"] * (len(CAMPOS_FUNCIONARIO) + 1))
            cur.execute(
                f"INSERT INTO funcionarios ({cols_sql}) VALUES ({placeholders})",
                (novo_codigo,) + tuple(vals[c] for c in CAMPOS_FUNCIONARIO),
            )
            acao = "incluído"

        _grava_relacionados(cur, novo_codigo, dados)

        conn.commit()
        cur.close()
        return {
            "success": True, "codigo": novo_codigo,
            "message": f"O Funcionário {nome_guerra} Foi {acao.capitalize()} Corretamente",
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_funcionario_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT nome_guerra FROM funcionarios WHERE codigo_int=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Funcionário não encontrado."}
        nome_guerra = (row.get("nome_guerra") or "").strip()

        cur.execute("SELECT TOP 1 1 AS ok FROM usuarios WHERE usuario=%s", (nome_guerra,))
        if cur.fetchone():
            cur.close()
            return {
                "success": False,
                "message": f"O Funcionário {nome_guerra} também está cadastrado como Usuário — "
                           "exclua o usuário primeiro em Configurações > Perfil de Usuário.",
            }

        guards = [
            ("comanda", "atendente", "AND situacao <> 'C'", "Comandas"),
            ("movimentacao", "vendedor", "", "Movimentações de Estoque"),
            ("os_produto", "vendedor", "", "Itens de O.S. (Vendedor)"),
            ("os_produto", "executor", "", "Itens de O.S. (Executor)"),
            ("orc_produto", "vendedor", "", "Itens de Orçamento"),
            ("os", "atendente", "AND situacao <> 'C'", "Ordens de Serviço"),
            ("pecas", "usuario_cadastro", "", "Produtos (cadastrado por)"),
            ("pecas", "usuario_alteracao", "", "Produtos (alterado por)"),
            ("cliente", "usuario_cadastro", "", "Clientes (cadastrado por)"),
            ("cliente", "usuario_alteracao", "", "Clientes (alterado por)"),
            ("viagem", "motorista", "", "Viagens (Motorista)"),
            ("viagem", "ajudante", "", "Viagens (Ajudante)"),
            ("mov_bomba", "funcionario", "", "Movimentações de Bomba"),
            ("ilha", "funcionario", "", "Ilhas"),
            ("os_tempo", "funcionario", "", "Tempo de O.S."),
            ("conta_func", "func", "", "Contas de Funcionário"),
        ]
        for tabela, coluna, extra, rotulo in guards:
            cur.execute(f"SELECT TOP 1 1 AS ok FROM {tabela} WHERE {coluna}=%s {extra}", (codigo,))
            if cur.fetchone():
                return {
                    "success": False,
                    "message": f"Existem {rotulo} relativas ao Funcionário {nome_guerra} — "
                               "não será possível excluí-lo.",
                }

        for tabela, coluna in (
            ("funcionarios_area", "func"), ("funcionarios_area_atuacao", "func"),
            ("funcionarios_carteiras", "func"), ("funcionario_especialidades", "funcionario"),
            ("funcionarios_horarios", "funcionario"), ("funcionarios_ausencias", "funcionario"),
            ("comissao_excecao", "codigo_funcionario"),
        ):
            cur.execute(f"DELETE FROM {tabela} WHERE {coluna}=%s", (codigo,))
        # Vínculos de carteira ONDE este funcionário é a carteira de outro
        # (soft, mera preferência de portfólio) — cascata, não guard.
        cur.execute("DELETE FROM funcionarios_carteiras WHERE carteira=%s", (codigo,))

        cur.execute("DELETE FROM funcionarios WHERE codigo_int=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": f"O Funcionário {nome_guerra} Foi Excluído Corretamente"}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _list_vendedores_sync(servidor: str, banco: str, excluir_codigo: Optional[int]) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("""
            SELECT f.codigo_int, f.nome_guerra FROM funcionarios f
            JOIN Funcoes fc ON fc.codigo = f.cod_funcao
            WHERE f.situacao='A' AND fc.descricao='VENDEDOR' AND f.codigo_int <> %s
            ORDER BY f.nome_guerra
        """, (excluir_codigo or 0,))
        items = [{"codigo": int(r["codigo_int"]), "nome": (r.get("nome_guerra") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _add_ausencia_sync(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    data_ini = dados.get("data_ini")
    data_fim = dados.get("data_fim")
    hora_ini = dados.get("hora_ini")
    hora_fim = dados.get("hora_fim")
    obs = (dados.get("obs") or "").strip()
    if not data_ini or not data_fim:
        return {"success": False, "message": "Preencha início e término corretamente!"}
    if not hora_ini or not hora_fim:
        return {"success": False, "message": "Preencha início e término corretamente!"}
    if not obs:
        return {"success": False, "message": "Preencha o motivo corretamente!"}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM funcionarios WHERE codigo_int=%s", (codigo,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Funcionário não Cadastrado!"}
        cur.execute(
            "INSERT INTO funcionarios_ausencias (funcionario, data_ini, data_fim, hora_ini, hora_fim, intervalo1, obs) "
            "OUTPUT INSERTED.codigo_funcionarios_ausencias VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (codigo, data_ini, data_fim, hora_ini, hora_fim, dados.get("intervalo1") or 0, obs),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        return {"success": True, "codigo": int(row["codigo_funcionarios_ausencias"]), "message": "Ausência registrada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_ausencia_sync(servidor: str, banco: str, ausencia_id: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM funcionarios_ausencias WHERE codigo_funcionarios_ausencias=%s", (ausencia_id,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Ausência não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Ausência excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _resolve_item_comissao(cur, item: str):
    """Procura `item` em pecas (por codigo_fab/descricao/codigo_int) e depois
    em servicos (por codigo/descricao) — mesma cascata de `CodExcecao_LostFocus`
    do legado. Devolve (codigo_resolvido, descricao, tipo_ps) ou (None, None, None)."""
    item = (item or "").strip()
    if not item:
        return None, None, None
    for col in ("codigo_fab", "descricao", "codigo_int"):
        cur.execute(f"SELECT TOP 1 codigo_int, descricao FROM pecas WHERE {col}=%s", (item,))
        row = cur.fetchone()
        if row:
            return (row["codigo_int"] or "").strip(), (row.get("descricao") or "").strip(), "P"
    for col in ("codigo", "descricao"):
        cur.execute(f"SELECT TOP 1 codigo, descricao FROM servicos WHERE {col}=%s", (item,))
        row = cur.fetchone()
        if row:
            return (row["codigo"] or "").strip(), (row.get("descricao") or "").strip(), "S"
    return None, None, None


def _save_comissao_excecao_sync(servidor: str, banco: str, codigo_funcionario: int, item: str, tipo: str, comissao: float) -> dict:
    if tipo not in ("V", "E", "A"):
        return {"success": False, "message": "Tipo inválido."}
    if not comissao or float(comissao) <= 0:
        return {"success": False, "message": "Preencha a Comissão Apropriadamente"}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM funcionarios WHERE codigo_int=%s", (codigo_funcionario,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Preencha CodiNome Apropriadamente"}
        codigo_resolvido, descricao, tipo_ps = _resolve_item_comissao(cur, item)
        if not codigo_resolvido:
            cur.close()
            return {"success": False, "message": "Produto/Serviços não cadastrado!"}
        cur.execute(
            "DELETE FROM comissao_excecao WHERE codigo_funcionario=%s AND item=%s AND tipo=%s",
            (codigo_funcionario, codigo_resolvido, tipo),
        )
        cur.execute(
            "INSERT INTO comissao_excecao (codigo_funcionario, item, tipo, tipo_ps, comissao) "
            "OUTPUT INSERTED.cod_comissao_excecao VALUES (%s,%s,%s,%s,%s)",
            (codigo_funcionario, codigo_resolvido, tipo, tipo_ps, comissao),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        return {
            "success": True, "codigo": int(row["cod_comissao_excecao"]), "descricao": descricao,
            "message": "Exceção gravada.",
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_comissao_excecao_sync(servidor: str, banco: str, excecao_id: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM comissao_excecao WHERE cod_comissao_excecao=%s", (excecao_id,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Exceção não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Exceção excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def list_funcionarios(servidor, banco, search):
    return await asyncio.to_thread(_list_funcionarios_sync, servidor, banco, search)


async def get_funcionario(servidor, banco, codigo):
    return await asyncio.to_thread(_get_funcionario_sync, servidor, banco, codigo)


async def save_funcionario(servidor, banco, codigo, dados):
    return await asyncio.to_thread(_save_funcionario_sync, servidor, banco, codigo, dados)


async def delete_funcionario(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_funcionario_sync, servidor, banco, codigo)


async def list_vendedores(servidor, banco, excluir_codigo):
    return await asyncio.to_thread(_list_vendedores_sync, servidor, banco, excluir_codigo)


async def add_ausencia(servidor, banco, codigo, dados):
    return await asyncio.to_thread(_add_ausencia_sync, servidor, banco, codigo, dados)


async def delete_ausencia(servidor, banco, ausencia_id):
    return await asyncio.to_thread(_delete_ausencia_sync, servidor, banco, ausencia_id)


async def save_comissao_excecao(servidor, banco, codigo_funcionario, item, tipo, comissao):
    return await asyncio.to_thread(_save_comissao_excecao_sync, servidor, banco, codigo_funcionario, item, tipo, comissao)


async def delete_comissao_excecao(servidor, banco, excecao_id):
    return await asyncio.to_thread(_delete_comissao_excecao_sync, servidor, banco, excecao_id)

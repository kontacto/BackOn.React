"""Manutenção de Viagens (módulo Cilindros). Tabelas `Viagem`,
`Viagem_Cilindro`, `Viagem_Retorno`, `Viagem_Contrato`, `Contratos`,
`Contratos_Produtos`, `Contratos_Centro_Custo`. Legado: `FrmManViagens.frm`
("Manutenção de Viagens..."). Ver PENDENCIAS.md > "Cilindros" > "Fase 3"
para o rastreio campo-a-campo completo, incluindo dúvidas registradas.

É a tela que efetivamente grava `Viagem`/`Viagem_Cilindro`/`Viagem_Retorno`
— o Borderô de Cilindros (Fase 3c, ainda não implementado) só lê essas
tabelas; esta tela é quem as popula.

Status de item (`Cilindro_Situacao`, tabela dedicada — não confundir com a
`Situacao` genérica): LT=Livre Troca, AP=Aplicação, APT=Aplicação
Temporária, DP=Devolução de Propriedade, DPT=Devolução Temporária,
DT=Devolução de Terceiros, RT=Recolha de Terceiros, CA=Cancelado —
confirmado pelo usuário 2026-07-14.

Diferenças deliberadas em relação ao legado (ver "Não replicar" em
PENDENCIAS.md — gambiarra de linguagem antiga / hardcode de instalação
específica, não regra de negócio):
- Hardcode de empresa "Guerengases"/`EmpresaCusto` removido — quando falta
  configuração de centro de custo padrão (`Controle.tipo_mov_contrato_
  servico`), bloqueia com mensagem clara em vez de usar um centro de custo
  adivinhado (`1088`/`134` no legado).
- `ModeloPedido = 40` (gating por número de modelo de impressão herdado de
  `Controle.modelo_pedido`) removido — O.S. é sempre obrigatória para itens
  com status AP/APT/RT.
- Exclusão de item exige Saída ainda não fechada, sem a exceção pouco clara
  do legado (`Cilindro_1 = 0 And Cilindro_2 <> 0` em `Command29_Click`) —
  ver PENDENCIAS.md, dúvida em aberto não resolvida.
- Número do contrato (`Contratos.contrato`) é atribuído = `codigo` (IDENTITY)
  logo após o insert, em vez de pré-calculado por `SELECT MAX(codigo)+1`
  como o legado faz (`RetornaNumeroContrato`) — essa pré-checagem é segura
  em uma instalação VB6 single-user por empresa, mas esta API atende vários
  usuários concorrentes na mesma base.
- Log de auditoria é feito via `log_auditoria_service` (padrão do projeto),
  não pela tabela `Logs` do legado (`Insert into Logs (...)`), que não é
  replicada.

Schema conferido ao vivo (2026-07-14) contra GERDELL/BARESTELA — pontos que
divergem do que um chute só-do-VB6 produziria, mas que não afetam o SQL
abaixo (nenhuma coluna usada aqui foi renomeada): `Viagem_Contrato` tem PK
própria `cod` (nunca referenciada diretamente, só `viagem`/`contrato`);
`Contratos_Centro_Custo` tem PK `cc_auto` (idem, só `contrato` é usado);
`Contratos_Produtos.produto` é `nvarchar(20)` (código de produto como
texto), não um FK inteiro — este código grava o `Cilindro.cod` (numérico)
nesse campo, igual ao legado, via conversão implícita de string.

Não implementado nesta rodada (ver PENDENCIAS.md): "Adicionar Pedidos"
(Frame3 — inclusão em massa a partir de `Pedido_Venda`), "Adicionar Itens
do Pátio" (Frame10 — só para Tipo Fábrica), "Itens Avulsos de Entrada"
(Frame14 — baixa de itens de OUTRA viagem), impressão formatada (NF/relação
de viagens/resumos) e o motor de "críticas" com relatório dedicado (aqui as
críticas voltam como lista de mensagens na resposta, exibidas pelo
frontend). O núcleo (cabeçalho, item manual, Fechar Saída, Fechar Entrada,
Reabrir, Cancelar) está completo.
"""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn

STATUS_VALIDOS = {"LT", "AP", "APT", "DP", "DPT", "DT", "RT", "CA"}
STATUS_EXIGE_OS = {"AP", "APT", "RT"}


def _row(r) -> dict:
    return dict(r)


def _parse_date(d):
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def _mes(d) -> int:
    return _parse_date(d).month


def _dia(d) -> int:
    return _parse_date(d).day


def _fmt(d) -> str:
    return _parse_date(d).strftime("%d/%m/%Y")


# ============================================================
# Cabeçalho da Viagem
# ============================================================

def _list_viagens_sync(servidor: str, banco: str, filtros: dict) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = "1=1"
        params: list = []
        if filtros.get("codigo"):
            where += " AND v.codigo=%s"; params.append(filtros["codigo"])
        if filtros.get("veiculo"):
            where += " AND v.veiculo=%s"; params.append(filtros["veiculo"])
        if filtros.get("motorista"):
            where += " AND v.motorista=%s"; params.append(filtros["motorista"])
        if filtros.get("tipo_viagem") is not None:
            where += " AND v.tipo_viagem=%s"; params.append(filtros["tipo_viagem"])
        if filtros.get("situacao"):
            where += " AND v.situacao=%s"; params.append(filtros["situacao"])
        if filtros.get("saida_de"):
            where += " AND v.saida>=%s"; params.append(filtros["saida_de"])
        if filtros.get("saida_ate"):
            where += " AND v.saida<=%s"; params.append(filtros["saida_ate"])
        cur.execute(
            f"SELECT v.codigo, v.tipo_viagem, v.situacao, v.saida, v.hora_saida, v.retorno, v.hora_retorno, "
            f"v.saida_fechada, v.entrada_fechada, vt.placa, vt.descricao AS veiculo_descricao, "
            f"f1.nome_guerra AS motorista_nome, f2.nome_guerra AS ajudante_nome "
            f"FROM Viagem v "
            f"LEFT JOIN veiculos_transp vt ON vt.codigo=v.veiculo "
            f"LEFT JOIN funcionarios f1 ON f1.codigo_int=v.motorista "
            f"LEFT JOIN funcionarios f2 ON f2.codigo_int=v.ajudante "
            f"WHERE {where} ORDER BY v.codigo DESC",
            tuple(params),
        )
        items = [_row(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _get_viagem_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT v.*, vt.placa, vt.descricao AS veiculo_descricao, "
            "f1.nome_guerra AS motorista_nome, f2.nome_guerra AS ajudante_nome "
            "FROM Viagem v "
            "LEFT JOIN veiculos_transp vt ON vt.codigo=v.veiculo "
            "LEFT JOIN funcionarios f1 ON f1.codigo_int=v.motorista "
            "LEFT JOIN funcionarios f2 ON f2.codigo_int=v.ajudante "
            "WHERE v.codigo=%s",
            (codigo,),
        )
        v = cur.fetchone()
        if not v:
            cur.close()
            return {"success": False, "message": "Viagem não encontrada."}

        cur.execute(
            "SELECT vc.*, "
            "cil.codigo AS cil_codigo, cil.capacidade AS cil_capacidade, cil.pressao AS cil_pressao, "
            "cil.padrao AS cil_padrao, cil.descricao AS cil_descricao, "
            "cilr.codigo AS cilr_codigo, cilr.capacidade AS cilr_capacidade, cilr.pressao AS cilr_pressao, "
            "cilr.padrao AS cilr_padrao, cilr.descricao AS cilr_descricao, "
            "cs1.numero_de_serie AS nds_saida, cs2.numero_de_serie AS nds_retorno, "
            "(CASE WHEN %s=1 THEN (SELECT nome FROM Fornecedor WHERE codigo_int=vc.cliente) "
            "ELSE (SELECT nome FROM Cliente WHERE codigo=vc.cliente) END) AS cliente_nome "
            "FROM Viagem_Cilindro vc "
            "LEFT JOIN Cilindro cil ON cil.cod=vc.cilindro "
            "LEFT JOIN Cilindro cilr ON cilr.cod=vc.cilindro_retorno "
            "LEFT JOIN Cilindro_Serie cs1 ON cs1.codigo=vc.num_serie "
            "LEFT JOIN Cilindro_Serie cs2 ON cs2.codigo=vc.num_serie_retorno "
            "WHERE vc.viagem=%s ORDER BY vc.ordem",
            (v["tipo_viagem"], codigo),
        )
        itens = [_row(r) for r in cur.fetchall()]
        cur.close()
        item = _row(v)
        item["itens"] = itens
        return {"success": True, "item": item}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _save_viagem_header_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    veiculo = dados.get("veiculo") or 0
    tipo_viagem = dados.get("tipo_viagem")
    if tipo_viagem not in (0, 1):
        return {"success": False, "message": "Informe o Tipo de Viagem."}
    if not codigo and not veiculo:
        return {"success": False, "message": "Preencher o Veículo."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        if not codigo:
            cur.execute(
                "INSERT INTO Viagem (veiculo, motorista, ajudante, tipo_viagem, descricao, obs, saida, hora_saida, "
                "km_saida, saida_fechada, entrada_fechada, situacao) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,'A')",
                (
                    veiculo, dados.get("motorista") or None, dados.get("ajudante") or None, tipo_viagem,
                    dados.get("descricao") or "", dados.get("obs") or "", dados.get("saida") or None,
                    dados.get("hora_saida") or None, dados.get("km_saida") or 0,
                ),
            )
            conn.commit()
            cur.execute("SELECT @@IDENTITY AS codigo")
            codigo = cur.fetchone()["codigo"]
        else:
            cur.execute("SELECT saida_fechada, entrada_fechada, situacao FROM Viagem WHERE codigo=%s", (codigo,))
            row = cur.fetchone()
            if not row:
                cur.close()
                return {"success": False, "message": "Viagem não encontrada."}
            if row["situacao"] not in ("A",):
                cur.close()
                return {"success": False, "message": "Operação permitida somente para viagens abertas."}
            if not row["saida_fechada"]:
                cur.execute(
                    "UPDATE Viagem SET veiculo=%s, motorista=%s, ajudante=%s, saida=%s, hora_saida=%s, km_saida=%s, "
                    "descricao=%s WHERE codigo=%s",
                    (
                        veiculo, dados.get("motorista") or None, dados.get("ajudante") or None,
                        dados.get("saida") or None, dados.get("hora_saida") or None, dados.get("km_saida") or 0,
                        dados.get("descricao") or "", codigo,
                    ),
                )
            elif not row["entrada_fechada"]:
                cur.execute(
                    "UPDATE Viagem SET retorno=%s, hora_retorno=%s, km_retorno=%s WHERE codigo=%s",
                    (dados.get("retorno") or None, dados.get("hora_retorno") or None, dados.get("km_retorno") or 0, codigo),
                )
            cur.execute("UPDATE Viagem SET tipo_viagem=%s, obs=%s WHERE codigo=%s", (tipo_viagem, dados.get("obs") or "", codigo))

        conn.commit()
        cur.close()
        return {"success": True, "message": "Dados da viagem gravados com sucesso.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


# ============================================================
# Itens da Viagem (Viagem_Cilindro)
# ============================================================

def _add_item_sync(servidor: str, banco: str, viagem_codigo: int, dados: dict) -> dict:
    cliente = dados.get("cliente") or 0
    cilindro_cod = dados.get("cilindro") or 0
    status_saida = (dados.get("status_saida") or "").strip().upper()
    numero_serie = (dados.get("numero_serie") or "").strip()
    doc_saida = dados.get("doc_saida") or 0
    tipo_doc_saida = dados.get("tipo_doc_saida", 3)
    carga_saida = 1 if dados.get("carga_saida") == "VAZIO" else 0
    os_saida = (dados.get("os_saida") or "").strip()
    obs_saida = dados.get("obs_saida") or ""

    if not cliente:
        return {"success": False, "message": "Selecione o Destinatário."}
    if not cilindro_cod:
        return {"success": False, "message": "Selecione o Cilindro."}
    if status_saida not in STATUS_VALIDOS:
        return {"success": False, "message": "Status de Saída inválido."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT saida_fechada, entrada_fechada, situacao, tipo_viagem FROM Viagem WHERE codigo=%s", (viagem_codigo,))
        viagem = cur.fetchone()
        if not viagem:
            cur.close()
            return {"success": False, "message": "Viagem não encontrada."}
        if viagem["situacao"] != "A":
            cur.close()
            return {"success": False, "message": "Operação permitida somente para viagens abertas."}
        if viagem["saida_fechada"] or viagem["entrada_fechada"]:
            cur.close()
            return {"success": False, "message": "Inclusão de itens não permitida — a Saída já foi fechada."}

        cur.execute("SELECT cod FROM Cilindro WHERE cod=%s", (cilindro_cod,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Cilindro não cadastrado."}

        num_serie_id = None
        if numero_serie:
            cur.execute("SELECT codigo FROM Cilindro_Serie WHERE cilindro=%s AND numero_de_serie=%s", (cilindro_cod, numero_serie))
            row = cur.fetchone()
            if row:
                num_serie_id = row["codigo"]
            else:
                cur.execute(
                    "INSERT INTO Cilindro_Serie (numero_de_serie, cilindro, destino, tipo_destino) VALUES (%s,%s,0,%s)",
                    (numero_serie, cilindro_cod, 1 if viagem["tipo_viagem"] == 1 else 0),
                )
                conn.commit()
                cur.execute("SELECT @@IDENTITY AS codigo")
                num_serie_id = cur.fetchone()["codigo"]

        cur.execute("SELECT ISNULL(MAX(ordem),0) AS maior FROM Viagem_Cilindro WHERE viagem=%s", (viagem_codigo,))
        ordem = (cur.fetchone()["maior"] or 0) + 1

        cur.execute(
            "INSERT INTO Viagem_Cilindro (viagem, ordem, doc_saida, tipo_doc_saida, cliente, cilindro, num_serie, "
            "status_saida, os_saida, carga_saida, obs_saida) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (viagem_codigo, ordem, doc_saida, tipo_doc_saida, cliente, cilindro_cod, num_serie_id, status_saida, os_saida, carga_saida, obs_saida),
        )
        conn.commit()
        cur.execute("SELECT @@IDENTITY AS codigo")
        item_codigo = cur.fetchone()["codigo"]
        cur.close()
        return {"success": True, "message": "Item adicionado.", "codigo": item_codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}
    finally:
        conn.close()


def _save_item_retorno_sync(servidor: str, banco: str, item_codigo: int, dados: dict) -> dict:
    cilindro_retorno_cod = dados.get("cilindro_retorno") or 0
    status_retorno = (dados.get("status_retorno") or "").strip().upper()
    numero_serie_retorno = (dados.get("numero_serie_retorno") or "").strip()
    nf_retorno = dados.get("nf_retorno") or 0
    os_retorno = (dados.get("os_retorno") or "").strip()
    carga_retorno = 1 if dados.get("carga_retorno") == "VAZIO" else 0
    obs_retorno = dados.get("obs_retorno") or ""

    if not cilindro_retorno_cod:
        return {"success": False, "message": "Selecione o Cilindro de Retorno."}
    if status_retorno not in STATUS_VALIDOS:
        return {"success": False, "message": "Status de Retorno inválido."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT vc.*, v.tipo_viagem, v.saida_fechada, v.entrada_fechada, v.situacao "
            "FROM Viagem_Cilindro vc JOIN Viagem v ON v.codigo=vc.viagem WHERE vc.codigo=%s",
            (item_codigo,),
        )
        item = cur.fetchone()
        if not item:
            cur.close()
            return {"success": False, "message": "Item não encontrado."}
        if item["situacao"] != "A":
            cur.close()
            return {"success": False, "message": "Operação permitida somente para viagens abertas."}
        if not item["saida_fechada"]:
            cur.close()
            return {"success": False, "message": "A Saída desta viagem ainda não foi fechada."}
        if item["entrada_fechada"]:
            cur.close()
            return {"success": False, "message": "A Entrada desta viagem já foi fechada."}

        cur.execute("SELECT cod FROM Cilindro WHERE cod=%s", (cilindro_retorno_cod,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Cilindro de retorno não cadastrado."}

        if status_retorno in STATUS_EXIGE_OS:
            if not os_retorno:
                cur.close()
                return {"success": False, "message": "Preencher o Nº de O.S."}
            cur.execute(
                "SELECT viagem, ordem FROM Viagem_Cilindro WHERE status_retorno=%s AND os_retorno=%s AND codigo<>%s",
                (status_retorno, os_retorno, item_codigo),
            )
            dup = cur.fetchone()
            if dup:
                cur.close()
                return {"success": False, "message": f"Nº de O.S. já lançado na Viagem {dup['viagem']}, nº de ordem {dup['ordem']}."}

        num_serie_retorno_id = None
        if numero_serie_retorno:
            cur.execute(
                "SELECT codigo FROM Cilindro_Serie WHERE cilindro=%s AND numero_de_serie=%s",
                (cilindro_retorno_cod, numero_serie_retorno),
            )
            row = cur.fetchone()
            if row:
                num_serie_retorno_id = row["codigo"]
            else:
                cur.execute(
                    "INSERT INTO Cilindro_Serie (numero_de_serie, cilindro, destino, tipo_destino) VALUES (%s,%s,0,%s)",
                    (numero_serie_retorno, cilindro_retorno_cod, 1 if item["tipo_viagem"] == 1 else 0),
                )
                conn.commit()
                cur.execute("SELECT @@IDENTITY AS codigo")
                num_serie_retorno_id = cur.fetchone()["codigo"]
        elif status_retorno not in ("AP", "APT"):
            cur.close()
            return {"success": False, "message": "Preencher o Número de Série de Retorno."}

        if status_retorno in ("DP", "DT", "DPT") and not nf_retorno:
            cur.close()
            return {"success": False, "message": "Preencher o Nº do Documento de Retorno."}

        cur.execute(
            "UPDATE Viagem_Cilindro SET nf_retorno=%s, num_serie_retorno=%s, status_retorno=%s, "
            "os_retorno=%s, carga_retorno=%s, obs_retorno=%s, cilindro_retorno=%s WHERE codigo=%s",
            (nf_retorno, num_serie_retorno_id, status_retorno, os_retorno, carga_retorno, obs_retorno, cilindro_retorno_cod, item_codigo),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Retorno do item gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar retorno: {e}"}
    finally:
        conn.close()


def _delete_item_sync(servidor: str, banco: str, item_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT vc.viagem, v.saida_fechada, v.situacao FROM Viagem_Cilindro vc "
            "JOIN Viagem v ON v.codigo=vc.viagem WHERE vc.codigo=%s",
            (item_codigo,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Item não encontrado."}
        if row["situacao"] != "A":
            cur.close()
            return {"success": False, "message": "Operação permitida somente para viagens abertas."}
        if row["saida_fechada"]:
            cur.close()
            return {"success": False, "message": "Saída já fechada — não é permitida a exclusão de itens."}
        cur.execute("DELETE FROM Viagem_Cilindro WHERE codigo=%s", (item_codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Item excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _alterar_cilindro_sync(servidor: str, banco: str, item_codigo: int, novo_cilindro_cod: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cod FROM Cilindro WHERE cod=%s", (novo_cilindro_cod,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Cilindro não cadastrado."}
        cur.execute("SELECT TOP 1 1 FROM Viagem_Retorno WHERE viagem_saida=%s AND viagem_retorno<>0", (item_codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Cilindro já baixado em outra viagem — alteração não permitida."}
        cur.execute("UPDATE Viagem_Cilindro SET cilindro=%s, cilindro_retorno=%s WHERE codigo=%s", (novo_cilindro_cod, novo_cilindro_cod, item_codigo))
        cur.execute(
            "UPDATE cp SET cp.produto=%s FROM Contratos_Produtos cp JOIN Viagem_Contrato vcx ON vcx.contrato=cp.codigo WHERE vcx.viagem=%s",
            (novo_cilindro_cod, item_codigo),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Cilindro alterado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao alterar cilindro: {e}"}
    finally:
        conn.close()


def _renumerar_itens_sync(servidor: str, banco: str, viagem_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT saida_fechada, entrada_fechada, situacao FROM Viagem WHERE codigo=%s", (viagem_codigo,))
        v = cur.fetchone()
        if not v:
            cur.close()
            return {"success": False, "message": "Viagem não encontrada."}
        if v["situacao"] != "A":
            cur.close()
            return {"success": False, "message": "Operação permitida somente para viagens abertas."}
        if v["saida_fechada"] or v["entrada_fechada"]:
            cur.close()
            return {"success": False, "message": "Renumeração não permitida — a Saída já foi fechada."}
        cur.execute("SELECT codigo FROM Viagem_Cilindro WHERE viagem=%s ORDER BY ordem", (viagem_codigo,))
        rows = cur.fetchall()
        ordem = 1
        for r in rows:
            cur.execute("UPDATE Viagem_Cilindro SET ordem=%s WHERE codigo=%s", (ordem, r["codigo"]))
            ordem += 1
        conn.commit()
        cur.close()
        return {"success": True, "message": "Itens renumerados."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao renumerar: {e}"}
    finally:
        conn.close()


# ============================================================
# Fechar Saída
# ============================================================

def _atualiza_tipo_doc_saida_sync(cur, viagem_codigo: int) -> bool:
    """Promove item de Comanda/Pedido pra NF quando já emitida; bloqueia se
    algum Pedido ainda não tiver comanda/NF associada. Retorna False (não
    pode liberar) se algum item de Pedido não resolveu."""
    cur.execute(
        "SELECT codigo, doc_saida, tipo_doc_saida FROM Viagem_Cilindro WHERE viagem=%s AND (tipo_doc_saida=1 OR tipo_doc_saida=2)",
        (viagem_codigo,),
    )
    itens = cur.fetchall()
    pode_liberar = True
    for it in itens:
        if it["tipo_doc_saida"] == 1:
            cur.execute(
                "SELECT TOP 1 cnf.nota_fisc FROM Comanda_NF cnf JOIN N_Fiscal nf ON nf.codigo=cnf.nota_fisc "
                "WHERE nf.situacao='A' AND cnf.comanda=%s",
                (it["doc_saida"],),
            )
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE Viagem_Cilindro SET tipo_doc_saida=0, doc_saida=%s WHERE codigo=%s", (row["nota_fisc"], it["codigo"]))
        elif it["tipo_doc_saida"] == 2:
            cur.execute(
                "SELECT (SELECT TOP 1 cp.comanda FROM Comanda_Ped cp WHERE cp.ped=pv.pedido) AS comanda_ped, "
                "(SELECT TOP 1 cnf.nota_fisc FROM Comanda_NF cnf JOIN Comanda_Ped cp2 ON cp2.comanda=cnf.comanda "
                " JOIN N_Fiscal nf ON nf.codigo=cnf.nota_fisc WHERE nf.situacao='A' AND cp2.ped=pv.pedido) AS nf_ped "
                "FROM Pedido_Venda pv WHERE pv.pedido=%s",
                (it["doc_saida"],),
            )
            row = cur.fetchone()
            if not row or not row.get("comanda_ped"):
                pode_liberar = False
                continue
            if row.get("nf_ped"):
                cur.execute("UPDATE Viagem_Cilindro SET tipo_doc_saida=0, doc_saida=%s WHERE codigo=%s", (row["nf_ped"], it["codigo"]))
            else:
                cur.execute("UPDATE Viagem_Cilindro SET tipo_doc_saida=1, doc_saida=%s WHERE codigo=%s", (row["comanda_ped"], it["codigo"]))
    return pode_liberar


def _fechar_saida_sync(servidor: str, banco: str, viagem_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM Viagem WHERE codigo=%s", (viagem_codigo,))
        v = cur.fetchone()
        if not v:
            cur.close()
            return {"success": False, "message": "Viagem não encontrada."}
        if v["situacao"] != "A":
            cur.close()
            return {"success": False, "message": "Operação permitida somente para viagens abertas."}
        if v["saida_fechada"]:
            cur.close()
            return {"success": False, "message": "A saída desta viagem já foi fechada anteriormente."}
        if not v.get("saida"):
            cur.close()
            return {"success": False, "message": "Preencher a data de saída."}
        if not v.get("hora_saida"):
            cur.close()
            return {"success": False, "message": "Preencher a hora de saída."}
        if not v.get("motorista"):
            cur.close()
            return {"success": False, "message": "Preencher o Motorista do Veículo."}

        if v["tipo_viagem"] == 0:
            if not _atualiza_tipo_doc_saida_sync(cur, viagem_codigo):
                conn.rollback()
                cur.close()
                return {"success": False, "message": "Esta viagem não pode ser liberada — possui itens de Pedidos ainda não faturados."}

        cur.execute("UPDATE Viagem SET saida_fechada=1 WHERE codigo=%s", (viagem_codigo,))
        cur.execute(
            "UPDATE cs SET cs.tipo_destino=%s, cs.destino=vc.cliente FROM Cilindro_Serie cs "
            "JOIN Viagem_Cilindro vc ON vc.num_serie=cs.codigo WHERE vc.viagem=%s",
            (v["tipo_viagem"], viagem_codigo),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Saída fechada com sucesso."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar saída: {e}"}
    finally:
        conn.close()


# ============================================================
# Fechar Entrada — motor de críticas + reconciliação de estoque/contratos
# ============================================================

def _verifica_contrato_ativo_sync(cur, cliente) -> bool:
    cur.execute("SELECT TOP 1 codigo FROM Contratos WHERE cliente=%s AND situacao='A'", (cliente,))
    return cur.fetchone() is not None


def _localiza_pendencia_sync(cur, tipo_viagem, cliente, cil_codigo, capacidade, pressao, status_esperado, os_ref=None, num_serie_ref=None):
    sql = (
        "SELECT vr.viagem_saida, vc.codigo AS item_codigo FROM Viagem_Retorno vr "
        "JOIN Viagem_Cilindro vc ON vc.codigo=vr.viagem_saida "
        "JOIN Viagem v ON v.codigo=vc.viagem "
        "JOIN Cilindro cil ON cil.cod=vc.cilindro_retorno "
        "WHERE v.tipo_viagem=%s AND vc.status_retorno=%s AND vr.viagem_retorno=0 "
        "AND vc.cliente=%s AND cil.codigo=%s AND cil.capacidade=%s AND cil.pressao=%s"
    )
    params = [tipo_viagem, status_esperado, cliente, cil_codigo, capacidade, pressao]
    if os_ref:
        sql += " AND vc.os_retorno=%s"
        params.append(os_ref)
    if num_serie_ref:
        sql += " AND vc.num_serie_retorno=%s"
        params.append(num_serie_ref)
    cur.execute(sql, tuple(params))
    return cur.fetchone()


def _atualiza_centro_custo_sync(cur, contrato_id, valor, somar: bool):
    cur.execute("SELECT contrato FROM Contratos_Centro_Custo WHERE contrato=%s", (contrato_id,))
    if cur.fetchone():
        op = "+" if somar else "-"
        cur.execute(f"UPDATE Contratos_Centro_Custo SET valor = valor {op} %s WHERE contrato=%s", (valor, contrato_id))
        return
    if not somar:
        return
    cur.execute(
        "SELECT tm.centro_custo, cc.classe_saida, cc.sub_classe_saida FROM Controle c "
        "JOIN Tipo_Mov tm ON tm.codigo=c.tipo_mov_contrato_servico "
        "JOIN Centro_Custo cc ON cc.codigo=tm.centro_custo"
    )
    cfg = cur.fetchone()
    if not cfg:
        raise RuntimeError(
            "Configuração de centro de custo padrão para contratos de locação de cilindro não encontrada "
            "(Controle.tipo_mov_contrato_servico) — configure antes de fechar a entrada."
        )
    cur.execute(
        "INSERT INTO Contratos_Centro_Custo (contrato, centro_custo, valor, cc_classe, cc_sub_classe) VALUES (%s,%s,%s,%s,%s)",
        (contrato_id, cfg["centro_custo"], valor, cfg["classe_saida"], cfg["sub_classe_saida"]),
    )


def _cadastra_contrato_cilindro_sync(cur, cliente, cilindro_cod, item_codigo, os_retorno, data_retorno, viagem_codigo):
    cur.execute("SELECT codigo FROM Contratos WHERE cliente=%s AND situacao='A'", (cliente,))
    contrato = cur.fetchone()
    if not contrato:
        cur.execute(
            "INSERT INTO Contratos (cliente, mes_reajuste, dia_vencimento, valor_inicial, valor_ant, valor_atual, "
            "desc_venc, tipo_cobranca, tipo_contrato, periodo_faturar, mes_faturar, tipo_reajuste, multa, mora_dia, "
            "fatura_os, tarifa_cobranca, cobra_iss, agrupa_nf, obs, historico, situacao) VALUES "
            "(%s,%s,%s,0,0,0,0,1,0,0,%s,1,0,0,0,0,0,0,'CONTRATO DE LOCAÇÃO DE CILINDRO','','A')",
            (cliente, _mes(data_retorno), _dia(data_retorno), _mes(data_retorno)),
        )
        cur.execute("SELECT @@IDENTITY AS codigo")
        contrato_id = cur.fetchone()["codigo"]
        cur.execute("UPDATE Contratos SET contrato=%s WHERE codigo=%s", (contrato_id, contrato_id))
    else:
        contrato_id = contrato["codigo"]

    hist = f"Cilindro Aplicado no dia {_fmt(data_retorno)} (Viagem Código {viagem_codigo})"
    cur.execute(
        "UPDATE Contratos SET historico = CASE WHEN ISNULL(historico,'')='' THEN %s ELSE historico + '; ' + %s END, "
        "inicio = CASE WHEN ISNULL(inicio,'')='' THEN %s ELSE inicio END WHERE codigo=%s",
        (hist, hist, data_retorno, contrato_id),
    )

    cur.execute("SELECT preco_locacao FROM Cilindro WHERE cod=%s", (cilindro_cod,))
    row = cur.fetchone()
    preco = row["preco_locacao"] if row else 0

    cur.execute("SELECT codigo, preco FROM Contratos_Produtos WHERE contrato=%s AND ISNULL(data_inicio,'')=''", (contrato_id,))
    vaga = cur.fetchone()
    obs = f"Nº OS: {os_retorno} (Viagem {viagem_codigo})" if os_retorno else f"(Viagem {viagem_codigo})"
    if not vaga:
        cur.execute(
            "INSERT INTO Contratos_Produtos (contrato, produto, data_inicio, preco, qtd, obs, situacao) VALUES (%s,%s,%s,%s,1,%s,'A')",
            (contrato_id, cilindro_cod, data_retorno, preco, obs),
        )
        cur.execute("SELECT @@IDENTITY AS codigo")
        cp_id = cur.fetchone()["codigo"]
    else:
        cp_id = vaga["codigo"]
        preco = vaga["preco"] or preco
        cur.execute("UPDATE Contratos_Produtos SET data_inicio=%s, produto=%s, obs=%s WHERE codigo=%s", (data_retorno, cilindro_cod, obs, cp_id))

    cur.execute("SELECT 1 FROM Viagem_Contrato WHERE viagem=%s AND contrato=%s", (item_codigo, cp_id))
    if not cur.fetchone():
        cur.execute("INSERT INTO Viagem_Contrato (viagem, contrato) VALUES (%s,%s)", (item_codigo, cp_id))

    cur.execute("UPDATE Contratos SET valor_atual = valor_atual + %s WHERE codigo=%s", (preco, contrato_id))
    _atualiza_centro_custo_sync(cur, contrato_id, preco, somar=True)


def _encerra_contrato_sync(cur, item_codigo_saida, data_retorno, viagem_codigo):
    cur.execute(
        "SELECT cp.codigo, cp.contrato, cp.preco FROM Viagem_Contrato vcx "
        "JOIN Contratos_Produtos cp ON cp.codigo=vcx.contrato WHERE vcx.viagem=%s",
        (item_codigo_saida,),
    )
    row = cur.fetchone()
    if not row:
        return
    cur.execute("UPDATE Contratos_Produtos SET data_encerramento=%s WHERE codigo=%s", (data_retorno, row["codigo"]))
    hist = f"; Cilindro Devolvido no dia {_fmt(data_retorno)} (Viagem Código {viagem_codigo})"
    cur.execute("UPDATE Contratos SET historico = historico + %s, valor_atual = valor_atual - %s WHERE codigo=%s", (hist, row["preco"], row["contrato"]))
    _atualiza_centro_custo_sync(cur, row["contrato"], row["preco"], somar=False)


def _fechar_entrada_sync(servidor: str, banco: str, viagem_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM Viagem WHERE codigo=%s", (viagem_codigo,))
        v = cur.fetchone()
        if not v:
            cur.close()
            return {"success": False, "message": "Viagem não encontrada."}
        if v["situacao"] != "A":
            cur.close()
            return {"success": False, "message": "Operação permitida somente para viagens abertas."}
        if not v["saida_fechada"]:
            cur.close()
            return {"success": False, "message": "A saída desta viagem ainda não foi fechada."}
        if v["entrada_fechada"]:
            cur.close()
            return {"success": False, "message": "A entrada desta viagem já foi fechada anteriormente."}
        if not v.get("retorno"):
            cur.close()
            return {"success": False, "message": "Preencher a data de retorno."}
        if not v.get("hora_retorno"):
            cur.close()
            return {"success": False, "message": "Preencher a hora de retorno."}

        cur.execute(
            "SELECT vc.*, cil.codigo AS cil_codigo, cil.capacidade AS cil_capacidade, cil.pressao AS cil_pressao "
            "FROM Viagem_Cilindro vc LEFT JOIN Cilindro cil ON cil.cod=vc.cilindro_retorno "
            "WHERE vc.viagem=%s ORDER BY vc.os_retorno DESC",
            (viagem_codigo,),
        )
        itens = cur.fetchall()

        criticas = []
        for it in itens:
            status_retorno = it.get("status_retorno")
            status_saida = it.get("status_saida")
            if not it.get("cilindro_retorno"):
                criticas.append(f"Ordem {it['ordem']}: o retorno deste item não foi confirmado ou cancelado.")
                continue
            if status_retorno in ("AP", "APT") and v["tipo_viagem"] == 0:
                if not _verifica_contrato_ativo_sync(cur, it["cliente"]):
                    criticas.append(f"Ordem {it['ordem']}: item é uma aplicação, mas o cliente ainda não tem contrato cadastrado.")
                    continue
            if status_retorno != "CA":
                if status_saida in ("DP", "RT", "DT", "DPT"):
                    if status_saida != status_retorno:
                        criticas.append(f"Ordem {it['ordem']}: status inválido para o retorno (saída {status_saida}, retorno {status_retorno}).")
                        continue
                elif status_saida in ("AP", "LT", "APT"):
                    if status_retorno not in ("AP", "APT", "LT"):
                        criticas.append(f"Ordem {it['ordem']}: status inválido para o retorno (saída {status_saida}, retorno {status_retorno}).")
                        continue
            if status_retorno in ("DP", "DT", "DPT"):
                pend = _localiza_pendencia_sync(
                    cur, v["tipo_viagem"], it["cliente"], it["cil_codigo"], it["cil_capacidade"], it["cil_pressao"],
                    {"DP": "AP", "DPT": "APT", "DT": "DT"}[status_retorno],
                    os_ref=it.get("os_retorno") or None, num_serie_ref=it.get("num_serie_retorno") or None,
                )
                if not pend:
                    criticas.append(f"Ordem {it['ordem']}: não existe registro de saída em aberto para baixar este item.")

        if criticas:
            cur.close()
            return {"success": False, "message": "Existem críticas pendentes — corrija antes de fechar a entrada.", "criticas": criticas}

        for it in itens:
            status = it.get("status_retorno")
            cliente = it["cliente"]
            cil_ret = it["cilindro_retorno"]
            nds_ret = it.get("num_serie_retorno")

            if status == "CA":
                pass
            elif status in ("AP", "APT"):
                if nds_ret:
                    cur.execute("UPDATE Cilindro_Serie SET cilindro_na_fabrica=0 WHERE codigo=%s", (nds_ret,))
                cur.execute("UPDATE Cilindro SET estoque=estoque-1, estoque_em_cliente=estoque_em_cliente+1 WHERE cod=%s", (cil_ret,))
                if v["tipo_viagem"] == 0:
                    _cadastra_contrato_cilindro_sync(cur, cliente, cil_ret, it["codigo"], it.get("os_retorno"), v["retorno"], viagem_codigo)
                cur.execute(
                    "INSERT INTO Viagem_Retorno (viagem_saida, viagem_retorno, situacao, obs) VALUES (%s,0,'A',%s)",
                    (it["codigo"], it.get("obs_saida") or ""),
                )
            elif status in ("DP", "DPT"):
                pend = _localiza_pendencia_sync(
                    cur, v["tipo_viagem"], cliente, it["cil_codigo"], it["cil_capacidade"], it["cil_pressao"],
                    "AP" if status == "DP" else "APT",
                    os_ref=it.get("os_retorno") or None, num_serie_ref=nds_ret or None,
                )
                if pend:
                    cur.execute("UPDATE Viagem_Retorno SET viagem_retorno=%s WHERE viagem_saida=%s", (it["codigo"], pend["item_codigo"]))
                    if v["tipo_viagem"] == 0:
                        _encerra_contrato_sync(cur, pend["item_codigo"], v["retorno"], viagem_codigo)
                if nds_ret:
                    cur.execute("UPDATE Cilindro_Serie SET cilindro_na_fabrica=1 WHERE codigo=%s", (nds_ret,))
                cur.execute("UPDATE Cilindro SET estoque=estoque+1, estoque_em_cliente=estoque_em_cliente-1 WHERE cod=%s", (cil_ret,))
            elif status == "DT":
                if nds_ret:
                    cur.execute("UPDATE Cilindro_Serie SET cilindro_na_fabrica=1 WHERE codigo=%s", (nds_ret,))
                cur.execute("UPDATE Cilindro SET estoque=estoque-1, estoque_de_terceiro=estoque_de_terceiro-1 WHERE cod=%s", (cil_ret,))
                cur.execute(
                    "INSERT INTO Viagem_Retorno (viagem_saida, viagem_retorno, situacao, obs) VALUES (%s,0,'A',%s)",
                    (it["codigo"], it.get("obs_saida") or ""),
                )
            elif status == "RT":
                pend = _localiza_pendencia_sync(
                    cur, v["tipo_viagem"], cliente, it["cil_codigo"], it["cil_capacidade"], it["cil_pressao"], "DT",
                    os_ref=it.get("os_retorno") or None, num_serie_ref=nds_ret or None,
                )
                if pend:
                    cur.execute("UPDATE Viagem_Retorno SET viagem_retorno=%s WHERE viagem_saida=%s", (it["codigo"], pend["item_codigo"]))
                if nds_ret:
                    cur.execute("UPDATE Cilindro_Serie SET cilindro_na_fabrica=0 WHERE codigo=%s", (nds_ret,))
                cur.execute("UPDATE Cilindro SET estoque=estoque+1, estoque_de_terceiro=estoque_de_terceiro+1 WHERE cod=%s", (cil_ret,))
            elif status == "LT":
                if nds_ret:
                    cur.execute(
                        "UPDATE Cilindro_Serie SET cilindro_na_fabrica=0, tipo_destino=%s, destino=%s WHERE codigo=%s",
                        (v["tipo_viagem"], cliente, nds_ret),
                    )

            if status != "CA" and v["tipo_viagem"] == 0:
                cur.execute("SELECT 1 FROM Cilindro_Cliente WHERE cliente=%s AND cilindro=%s", (cliente, cil_ret))
                if not cur.fetchone():
                    cur.execute("INSERT INTO Cilindro_Cliente (cliente, cilindro) VALUES (%s,%s)", (cliente, cil_ret))

        cur.execute("UPDATE Viagem SET situacao='F', entrada_fechada=1 WHERE codigo=%s", (viagem_codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Entrada fechada com sucesso."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar entrada: {e}"}
    finally:
        conn.close()


# ============================================================
# Reabrir Saída/Retorno
# ============================================================

def _reabrir_sync(servidor: str, banco: str, viagem_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM Viagem WHERE codigo=%s", (viagem_codigo,))
        v = cur.fetchone()
        if not v:
            cur.close()
            return {"success": False, "message": "Viagem não encontrada."}

        if v["entrada_fechada"]:
            cur.execute(
                "SELECT vc.*, cil.codigo AS cil_codigo, cil.capacidade AS cil_capacidade, cil.pressao AS cil_pressao "
                "FROM Viagem_Cilindro vc LEFT JOIN Cilindro cil ON cil.cod=vc.cilindro_retorno WHERE vc.viagem=%s",
                (viagem_codigo,),
            )
            itens = cur.fetchall()

            for it in itens:
                status = it.get("status_retorno")
                if status in ("RT", "AP", "APT"):
                    cur.execute("SELECT 1 FROM Viagem_Retorno WHERE viagem_saida=%s AND viagem_retorno<>0", (it["codigo"],))
                    if cur.fetchone():
                        cur.close()
                        return {"success": False, "message": "Esta viagem possui item(ns) já devolvidos em outra viagem — não pode ser reaberta."}

            for it in itens:
                status = it.get("status_retorno")
                cil_ret = it["cilindro_retorno"]
                nds_ret = it.get("num_serie_retorno")
                if status in (None, "CA", "LT"):
                    continue
                if status == "RT":
                    if nds_ret:
                        cur.execute("UPDATE Cilindro_Serie SET cilindro_na_fabrica=1 WHERE codigo=%s", (nds_ret,))
                    cur.execute("DELETE FROM Viagem_Retorno WHERE viagem_saida=%s", (it["codigo"],))
                    cur.execute("UPDATE Cilindro SET estoque=estoque-1, estoque_de_terceiro=estoque_de_terceiro-1 WHERE cod=%s", (cil_ret,))
                elif status == "DT":
                    if nds_ret:
                        cur.execute("UPDATE Cilindro_Serie SET cilindro_na_fabrica=0 WHERE codigo=%s", (nds_ret,))
                    cur.execute("UPDATE Cilindro SET estoque=estoque+1, estoque_de_terceiro=estoque_de_terceiro+1 WHERE cod=%s", (cil_ret,))
                    cur.execute("UPDATE Viagem_Retorno SET viagem_retorno=0 WHERE viagem_saida=%s", (it["codigo"],))
                elif status in ("AP", "APT"):
                    if v["tipo_viagem"] == 0:
                        cur.execute(
                            "SELECT cp.codigo, cp.contrato, cp.preco FROM Viagem_Contrato vcx "
                            "JOIN Contratos_Produtos cp ON cp.codigo=vcx.contrato WHERE vcx.viagem=%s",
                            (it["codigo"],),
                        )
                        cp = cur.fetchone()
                        if cp:
                            cur.execute("UPDATE Contratos SET valor_atual = valor_atual - %s WHERE codigo=%s", (cp["preco"], cp["contrato"]))
                            cur.execute("UPDATE Contratos_Produtos SET data_inicio=NULL, obs=NULL WHERE codigo=%s", (cp["codigo"],))
                            _atualiza_centro_custo_sync(cur, cp["contrato"], cp["preco"], somar=False)
                        cur.execute("DELETE FROM Viagem_Retorno WHERE viagem_saida=%s", (it["codigo"],))
                        cur.execute("DELETE FROM Viagem_Contrato WHERE viagem=%s", (it["codigo"],))
                    if nds_ret:
                        cur.execute("UPDATE Cilindro_Serie SET cilindro_na_fabrica=0 WHERE codigo=%s", (nds_ret,))
                    cur.execute("UPDATE Cilindro SET estoque=estoque+1, estoque_em_cliente=estoque_em_cliente-1 WHERE cod=%s", (cil_ret,))
                elif status in ("DP", "DPT"):
                    if v["tipo_viagem"] == 0:
                        cur.execute("SELECT viagem_saida FROM Viagem_Retorno WHERE viagem_retorno=%s", (it["codigo"],))
                        pend = cur.fetchone()
                        if pend:
                            cur.execute(
                                "SELECT cp.codigo, cp.contrato, cp.preco FROM Viagem_Contrato vcx "
                                "JOIN Contratos_Produtos cp ON cp.codigo=vcx.contrato WHERE vcx.viagem=%s",
                                (pend["viagem_saida"],),
                            )
                            cp = cur.fetchone()
                            if cp:
                                cur.execute("UPDATE Contratos SET valor_atual = valor_atual + %s WHERE codigo=%s", (cp["preco"], cp["contrato"]))
                                cur.execute("UPDATE Contratos_Produtos SET data_encerramento=NULL WHERE codigo=%s", (cp["codigo"],))
                                _atualiza_centro_custo_sync(cur, cp["contrato"], cp["preco"], somar=True)
                            cur.execute("UPDATE Viagem_Retorno SET viagem_retorno=0 WHERE viagem_saida=%s", (pend["viagem_saida"],))
                    if nds_ret:
                        cur.execute("UPDATE Cilindro_Serie SET cilindro_na_fabrica=1 WHERE codigo=%s", (nds_ret,))
                    cur.execute("UPDATE Cilindro SET estoque=estoque-1, estoque_em_cliente=estoque_em_cliente+1 WHERE cod=%s", (cil_ret,))

            cur.execute("UPDATE Viagem SET situacao='A', entrada_fechada=0 WHERE codigo=%s", (viagem_codigo,))
            conn.commit()
            cur.close()
            return {"success": True, "message": "Viagem reaberta com sucesso (entrada)."}

        elif v["saida_fechada"]:
            cur.execute("UPDATE Viagem SET saida_fechada=0 WHERE codigo=%s", (viagem_codigo,))
            conn.commit()
            cur.close()
            return {"success": True, "message": "Viagem reaberta com sucesso (saída)."}

        else:
            cur.close()
            return {"success": False, "message": "A saída/entrada desta viagem já se encontram abertas."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao reabrir: {e}"}
    finally:
        conn.close()


# ============================================================
# Cancelar Viagem
# ============================================================

def _cancelar_viagem_sync(servidor: str, banco: str, viagem_codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM Viagem WHERE codigo=%s", (viagem_codigo,))
        v = cur.fetchone()
        if not v:
            cur.close()
            return {"success": False, "message": "Viagem não encontrada."}
        if v["situacao"] != "A":
            cur.close()
            return {"success": False, "message": "Operação permitida somente para viagens abertas."}
        if v["saida_fechada"]:
            cur.close()
            return {"success": False, "message": "O cancelamento só é permitido para viagens sem a saída fechada."}

        if v["tipo_viagem"] == 1:
            cur.execute(
                "UPDATE cs SET cs.cilindro_na_fabrica=0 FROM Cilindro_Serie cs "
                "JOIN Viagem_Cilindro vc ON vc.num_serie=cs.codigo WHERE vc.viagem=%s",
                (viagem_codigo,),
            )
        cur.execute("DELETE FROM Viagem_Cilindro WHERE viagem=%s", (viagem_codigo,))
        cur.execute("UPDATE Viagem SET situacao='C' WHERE codigo=%s", (viagem_codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Viagem cancelada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar: {e}"}
    finally:
        conn.close()


# ============================================================
# Wrappers assíncronos
# ============================================================

async def list_viagens(servidor: str, banco: str, filtros: dict) -> dict:
    return await asyncio.to_thread(_list_viagens_sync, servidor, banco, filtros)


async def get_viagem(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_viagem_sync, servidor, banco, codigo)


async def save_viagem_header(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_viagem_header_sync, servidor, banco, codigo, dados)


async def add_item(servidor: str, banco: str, viagem_codigo: int, dados: dict) -> dict:
    return await asyncio.to_thread(_add_item_sync, servidor, banco, viagem_codigo, dados)


async def save_item_retorno(servidor: str, banco: str, item_codigo: int, dados: dict) -> dict:
    return await asyncio.to_thread(_save_item_retorno_sync, servidor, banco, item_codigo, dados)


async def delete_item(servidor: str, banco: str, item_codigo: int) -> dict:
    return await asyncio.to_thread(_delete_item_sync, servidor, banco, item_codigo)


async def alterar_cilindro_item(servidor: str, banco: str, item_codigo: int, novo_cilindro_cod: int) -> dict:
    return await asyncio.to_thread(_alterar_cilindro_sync, servidor, banco, item_codigo, novo_cilindro_cod)


async def renumerar_itens(servidor: str, banco: str, viagem_codigo: int) -> dict:
    return await asyncio.to_thread(_renumerar_itens_sync, servidor, banco, viagem_codigo)


async def fechar_saida(servidor: str, banco: str, viagem_codigo: int) -> dict:
    return await asyncio.to_thread(_fechar_saida_sync, servidor, banco, viagem_codigo)


async def fechar_entrada(servidor: str, banco: str, viagem_codigo: int) -> dict:
    return await asyncio.to_thread(_fechar_entrada_sync, servidor, banco, viagem_codigo)


async def reabrir(servidor: str, banco: str, viagem_codigo: int) -> dict:
    return await asyncio.to_thread(_reabrir_sync, servidor, banco, viagem_codigo)


async def cancelar_viagem(servidor: str, banco: str, viagem_codigo: int) -> dict:
    return await asyncio.to_thread(_cancelar_viagem_sync, servidor, banco, viagem_codigo)

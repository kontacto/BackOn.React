"""Pedidos (pedido_venda) — listagem, leitura e CRUD do cabeçalho."""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.schemas import (
    PedidosListRequest, PedidoSaveRequest, FecharRequest, PedidoEntregueRequest, FormaPagSimplesRequest,
    DividirPedidoRequest, QtdPessoasRequest,
)
from services.constants import SITUACAO_LABEL
from services.pedido_common import (
    _check_cliente_ativo, _mover_estoque, _liberar_reservado, _fechar_pedido_itens,
    _ensure_hora_inclusao_item_col, _recalc_pedido_total, _ensure_qtd_pessoas_col,
)
from services.itens_service import TAXA_SERVICO_CODIGO, sincroniza_taxa_servico_apos_alteracao
from services.permissoes_service import tem_permissao


def _list_pedidos_sync(req: PedidosListRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_qtd_pessoas_col(cur)
        where_parts: list[str] = []
        params: list = []
        term = (req.search or "").strip()
        if term:
            like = f"%{term}%"
            # Busca por nome também bate no nome fantasia — [GLOBAL] em toda
            # busca de cliente do sistema, pedido explícito do usuário,
            # 2026-07-18.
            where_parts.append(
                "(c.nome LIKE %s OR c.fantasia LIKE %s OR c.cgc_cpf LIKE %s OR p.NOME_CLIENTE LIKE %s "
                "OR p.TELEFONE_CLIENTE LIKE %s OR CAST(p.pedido AS NVARCHAR(20)) LIKE %s "
                "OR CAST(c.codigo AS NVARCHAR(20)) LIKE %s)"
            )
            params.extend([like, like, like, like, like, like, like])
        if req.situacao:
            where_parts.append("p.situacao = %s")
            params.append(req.situacao)
        if req.vendedor and str(req.vendedor).lower() != "all":
            where_parts.append("p.vendedor = %s")
            params.append(req.vendedor)
        # Pedido tipo FIADO ainda Aberto nunca é escondido pelo filtro de
        # data — uma comanda fiado (fiado de verdade, tipo do CLIENTE
        # também prevalece via o mesmo COALESCE/NULLIF já usado pro filtro
        # de tipo acima) pode ficar aberta por semanas, e a tela de Pedidos
        # agora carrega sempre com o filtro de data do dia atual (ver
        # `_list_req`/pedidos.tsx) — sem essa exceção, fiados antigos
        # sumiriam da lista todo santo dia. Pedido explícito do usuário,
        # 2026-07-18.
        fiado_aberto_exempt = (
            "(p.situacao = 'A' AND (SELECT descricao FROM tipo_cliente wt "
            "WHERE wt.codigo = COALESCE(NULLIF(p.tipo, 0), c.cliente_forn)) = 'FIADO')"
        )
        if req.data_ini:
            where_parts.append(f"(p.data >= %s OR {fiado_aberto_exempt})")
            params.append(req.data_ini)
        if req.data_fim:
            where_parts.append(f"(p.data <= %s OR {fiado_aberto_exempt})")
            params.append(req.data_fim)
        if req.tipos_cliente:
            # Filtra pelo tipo do PEDIDO (pedido_venda.tipo), caindo pro
            # tipo do cliente quando o pedido não tem tipo próprio definido
            # — mesma regra da listagem/colunas do Painel de Pedidos.
            # `NULLIF(p.tipo, 0)` é necessário porque TODO pedido gravado
            # antes desta feature (2026-07-18) tem `tipo=0` hardcoded (não
            # NULL) — sem isso, `COALESCE` nunca cai pro tipo do cliente
            # pra esses pedidos antigos (0 não é NULL), e como não existe
            # `tipo_cliente.codigo=0`, o JOIN falha silenciosamente e o
            # pedido some de todas as colunas/filtros por tipo. Bug real
            # reportado pelo usuário ao ver a lista virar "Pedidos (0)"
            # depois desta feature. Pedido explícito do usuário, 2026-07-18.
            placeholders = ",".join(["%s"] * len(req.tipos_cliente))
            where_parts.append(f"COALESCE(NULLIF(p.tipo, 0), c.cliente_forn) IN ({placeholders})")
            params.extend(req.tipos_cliente)
        if req.data_entrega:
            where_parts.append("p.previsao_entrega <= %s")
            params.append(req.data_entrega)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # Total
        cur.execute(
            f"SELECT COUNT(*) c FROM pedido_venda p "
            f"LEFT JOIN cliente c ON c.codigo = p.cliente {where}",
            params,
        )
        total = int(cur.fetchone()["c"] or 0)

        # "Ordenar por" do painel Pedidos Abertos (Option7/8/9 no legado):
        # abertura = data/hora de abertura; tipo = tipo do cliente + nome;
        # cliente (default, igual já era) = nome do cliente. Sem
        # `ordenar_por`, mantém o comportamento já existente (mais recente
        # primeiro) — não muda o comportamento de quem já usa esta lista.
        if req.ordenar_por == "abertura":
            order_by = "p.data, p.hora_aberto"
        elif req.ordenar_por == "tipo":
            order_by = "tc.descricao, c.nome"
        elif req.ordenar_por == "cliente":
            order_by = "c.nome"
        else:
            order_by = "p.pedido DESC"

        offset = max(0, (req.page - 1) * req.size)
        # Nome do vendedor sempre exibe nome_guerra (apelido), caindo pro
        # nome completo só quando nome_guerra está vazio/nulo — regra
        # [GLOBAL] pra qualquer exibição de vendedor no sistema, pedido
        # explícito do usuário, 2026-07-17. Mesmo raciocínio já aplicado a
        # atendente/executor em os_service.py/os_itens_service.py.
        cur.execute(
            f"SELECT p.pedido, p.data, p.validade, p.situacao, p.total, p.cliente, "
            f"       COALESCE(c.nome, p.NOME_CLIENTE) AS cliente_nome, c.fantasia AS cliente_fantasia, "
            f"       p.vendedor, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome, "
            f"       p.hora_aberto, tc.descricao AS tipo_cliente_descricao, "
            f"       l.descricao AS localizacao_descricao, p.qtd_pessoas, "
            # Taxa de Serviço (S002) já lançada neste pedido — usado pelo
            # Painel de Pedidos pra colorir o ícone do botão "Tx Serviço" de
            # verde sem precisar carregar os itens de cada card. Pedido
            # explícito do usuário, 2026-07-17.
            f"       CASE WHEN EXISTS ("
            f"         SELECT 1 FROM pedido_venda_prod ip "
            f"         WHERE ip.pedido = p.pedido AND ip.produto = 'S002' AND ISNULL(ip.item_cancelado,0) = 0"
            f"       ) THEN 1 ELSE 0 END AS taxa_servico_incluida, "
            # Tem ao menos 1 item de produto/serviço (fora a própria S002)
            # — usado pra desabilitar o botão "Tx Serviço" do Painel de
            # Pedidos quando o pedido ainda está vazio (mesmo bloqueio
            # aplicado no backend, `_add_taxa_servico_sync`). Pedido
            # explícito do usuário, 2026-07-18.
            f"       CASE WHEN EXISTS ("
            f"         SELECT 1 FROM pedido_venda_prod ip2 "
            f"         WHERE ip2.pedido = p.pedido AND ip2.produto <> 'S002' AND ISNULL(ip2.item_cancelado,0) = 0"
            f"       ) THEN 1 ELSE 0 END AS tem_itens "
            f"FROM pedido_venda p "
            f"LEFT JOIN cliente c ON c.codigo = p.cliente "
            f"LEFT JOIN funcionarios f ON f.codigo_int = p.vendedor "
            # Tipo do PEDIDO prevalece sobre o tipo do cliente — só cai pro
            # tipo do cliente quando o pedido não tem tipo próprio (NULL OU
            # 0 — pedidos gravados antes desta feature têm `tipo=0`
            # hardcoded, tratado como "sem tipo" aqui). Pedido explícito do
            # usuário, 2026-07-18 ("caso o tipo de pedido seja nulo,
            # prevalecerá o tipo de cliente").
            f"LEFT JOIN tipo_cliente tc ON tc.codigo = COALESCE(NULLIF(p.tipo, 0), c.cliente_forn) "
            f"LEFT JOIN localizacao l ON l.codigo = p.LOCALIZACAO "
            f"{where} "
            f"ORDER BY {order_by} OFFSET {offset} ROWS FETCH NEXT {req.size} ROWS ONLY",
            params,
        )
        items: list[dict] = []
        for r in cur.fetchall():
            sit = (r.get("situacao") or "").strip()
            tipo_desc = (r.get("tipo_cliente_descricao") or "").strip()
            nome = (r.get("cliente_nome") or "").strip()
            fantasia = (r.get("cliente_fantasia") or "").strip()
            # Cliente Mesa/Comanda: mostra o nome fantasia ("MESA 15") em vez
            # do nome bruto ("M15") — mesmo efeito de
            # `_nome_exibicao_mesa_comanda` (clientes_service.py), mas
            # decidido aqui pelo TIPO DO CLIENTE já resolvido (tipo_cliente_
            # descricao), não pelo padrão regex do nome. Pedido explícito do
            # usuário, 2026-07-17.
            if tipo_desc.upper() in ("MESA", "COMANDA") and fantasia:
                nome = fantasia
            items.append({
                "pedido": int(r["pedido"] or 0),
                "data": r["data"].isoformat() if r.get("data") else None,
                "validade": r["validade"].isoformat() if r.get("validade") else None,
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(r.get("total") or 0),
                "cliente": int(r["cliente"] or 0) if r.get("cliente") else None,
                "cliente_nome": nome,
                "vendedor": int(r["vendedor"] or 0) if r.get("vendedor") else None,
                "vendedor_nome": (r.get("vendedor_nome") or "").strip(),
                "hora_aberto": (r.get("hora_aberto") or "").strip(),
                "tipo_cliente_descricao": tipo_desc,
                "localizacao_descricao": (r.get("localizacao_descricao") or "").strip(),
                "qtd_pessoas": int(r["qtd_pessoas"]) if r.get("qtd_pessoas") else None,
                "taxa_servico_incluida": bool(r.get("taxa_servico_incluida")),
                "tem_itens": bool(r.get("tem_itens")),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "total": total, "page": req.page, "size": req.size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


def _get_pedido_sync(servidor: str, banco: str, pedido: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_qtd_pessoas_col(cur)
        cur.execute(
            "SELECT p.pedido, p.cliente, p.data, p.validade, p.vendedor, p.hora_aberto, "
            "       p.obs, p.situacao, p.total, p.NOME_CLIENTE, p.TELEFONE_CLIENTE, p.area_atuacao, "
            "       p.previsao_entrega, p.hora_entrega, p.pedido_entregue, p.forma_pag, p.LOCALIZACAO, "
            "       p.num_ped_cliente, p.qtd_pessoas, p.tipo, "
            "       fp.descricao AS forma_pag_descricao, l.descricao AS localizacao_descricao, "
            "       c.nome AS cliente_nome, c.cgc_cpf AS cliente_cgc, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome, a.descricao AS area_descricao, "
            # Descrição do tipo efetivo do pedido — cai pro tipo do cliente
            # quando p.tipo é NULL, mesma regra de _list_pedidos_sync.
            "       tc.descricao AS tipo_descricao "
            "FROM pedido_venda p "
            "LEFT JOIN cliente c ON c.codigo = p.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = p.vendedor "
            "LEFT JOIN area_atuacao a ON a.area = p.area_atuacao "
            "LEFT JOIN forma_pagamento fp ON fp.codigo = p.forma_pag "
            "LEFT JOIN localizacao l ON l.codigo = p.LOCALIZACAO "
            "LEFT JOIN tipo_cliente tc ON tc.codigo = COALESCE(NULLIF(p.tipo, 0), c.cliente_forn) "
            "WHERE p.pedido = %s",
            (pedido,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}

        # Pedidos da mesma divisão (mesma mesa) — rastreados via
        # num_ped_cliente=str(pedido_raiz) (reaproveitado, não uma FK
        # própria, ver _dividir_pedido_sync). A "raiz" é sempre o pedido
        # original: se ESTE pedido tem uma referência numérica, ele é um
        # filho, então a raiz é o número apontado por ela; senão, ele mesmo
        # é a raiz. Consultando por raiz (não só "quem aponta pra mim"), a
        # lista fica igual não importa a partir de qual pedido da mesma
        # divisão a tela foi aberta — mantém a referência da mesa visível o
        # tempo todo, até o fechamento total de todos eles (pedido explícito
        # do usuário, 2026-07-17).
        referencia_atual = (row.get("num_ped_cliente") or "").strip()
        raiz = int(referencia_atual) if referencia_atual.isdigit() else pedido
        cur.execute(
            "SELECT pedido, situacao, total FROM pedido_venda "
            "WHERE (num_ped_cliente = %s OR pedido = %s) AND pedido <> %s "
            "ORDER BY pedido",
            (str(raiz), raiz, pedido),
        )
        pedidos_relacionados = [
            {
                "pedido": int(r["pedido"]),
                "situacao": (r.get("situacao") or "").strip(),
                "situacao_label": SITUACAO_LABEL.get((r.get("situacao") or "").strip(), (r.get("situacao") or "").strip()),
                "total": float(r.get("total") or 0),
            }
            for r in cur.fetchall()
        ]
        cur.close()
        conn.close()
        sit = (row.get("situacao") or "").strip()
        return {
            "success": True,
            "pedido": {
                "pedido": int(row["pedido"] or 0),
                "cliente": int(row["cliente"] or 0) if row.get("cliente") else None,
                "cliente_nome": (row.get("cliente_nome") or row.get("NOME_CLIENTE") or "").strip(),
                "cliente_cgc": (row.get("cliente_cgc") or "").strip(),
                "data": row["data"].isoformat() if row.get("data") else None,
                "validade": row["validade"].isoformat() if row.get("validade") else None,
                "vendedor": int(row["vendedor"] or 0) if row.get("vendedor") else None,
                "vendedor_nome": (row.get("vendedor_nome") or "").strip(),
                "hora_aberto": (row.get("hora_aberto") or "").strip(),
                "obs": row.get("obs") or "",
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(row.get("total") or 0),
                "area_atuacao": int(row["area_atuacao"]) if row.get("area_atuacao") is not None else None,
                "area_descricao": (row.get("area_descricao") or "").strip(),
                "previsao_entrega": row["previsao_entrega"].isoformat() if row.get("previsao_entrega") else None,
                "hora_entrega": (row.get("hora_entrega") or "").strip(),
                "pedido_entregue": bool(row.get("pedido_entregue")),
                "forma_pag": (row.get("forma_pag") or "").strip(),
                "forma_pag_descricao": (row.get("forma_pag_descricao") or "").strip(),
                "localizacao_descricao": (row.get("localizacao_descricao") or "").strip(),
                "qtd_pessoas": int(row["qtd_pessoas"]) if row.get("qtd_pessoas") else None,
                # Combobox "Tipo" do Pedido Bar (tipo_cliente.codigo) — `tipo`
                # é o que foi explicitamente selecionado nesse pedido (None =
                # nenhum, cai pro tipo do cliente); `tipo_descricao` já vem
                # resolvido (pedido ou, na falta, cliente). Pedido explícito
                # do usuário, 2026-07-18.
                "tipo": int(row["tipo"]) if row.get("tipo") is not None else None,
                "tipo_descricao": (row.get("tipo_descricao") or "").strip(),
                "referencia": (row.get("num_ped_cliente") or "").strip(),
                "pedidos_relacionados": pedidos_relacionados,
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# Pedido aberto (situacao='A') mais recente de um cliente — usado pelo
# campo Cliente do Pedido Bar pra "reabrir" a Comanda em vez de começar um
# pedido novo do zero quando o cliente já tem uma em andamento (mesma
# lógica de `Command1_Click`/`Campo_LostFocus(6)` em FrmManPedBar.frm).
def _pedido_aberto_por_cliente_sync(servidor: str, banco: str, cliente: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "pedido": None}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 pedido FROM pedido_venda WHERE cliente = %s AND situacao = 'A' ORDER BY pedido DESC",
            (cliente,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return {"success": True, "pedido": int(row["pedido"]) if row else None}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "pedido": None}


def _save_pedido_sync(req: PedidoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        # Se for update, verifica situação — só pedido em 'A' (Aberto) pode ser editado.
        if pedido_codigo is not None:
            cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido_codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            sit_atual = (ex.get("situacao") or "").strip().upper()
            if sit_atual != "A":
                conn.close()
                label = SITUACAO_LABEL.get(sit_atual, sit_atual)
                return {"success": False, "message": f"Pedido com situação '{label}' não pode ser alterado."}
        else:
            # Novo pedido — cliente com STATUS_CLIENTE diferente de Ativo não pode
            # gerar movimentação (venda/pré-venda).
            ok, label = _check_cliente_ativo(cur, req.cliente)
            if not ok:
                conn.close()
                return {
                    "success": False,
                    "message": f"Cliente com situação '{label}' não pode gerar novo pedido.",
                }
        # Busca o nome/telefone do cliente (denormalizados em NOME_CLIENTE /
        # TELEFONE_CLIENTE) + fantasia/cliente_forn, usados logo abaixo pra
        # resolver o campo "Tipo" do pedido.
        cur.execute(
            "SELECT TOP 1 c.nome, c.fantasia, c.cliente_forn, "
            "  COALESCE((SELECT TOP 1 LTRIM(RTRIM(CAST(ddd AS NVARCHAR(4))) + tel) "
            "            FROM cliente_tel WHERE codigo=c.codigo ORDER BY sequencia), "
            "           LTRIM(RTRIM(CAST(c.ddd_cli AS NVARCHAR(4))) + ISNULL(c.telefone_cli,''))) AS tel "
            "FROM cliente c WHERE c.codigo = %s",
            (req.cliente,),
        )
        cli_row = cur.fetchone() or {}
        nome_cli = (cli_row.get("nome") or "").strip()[:60]
        tel_cli = (cli_row.get("tel") or "").strip()[:60]

        # Campo "Tipo" do pedido (pedido_venda.tipo, combobox do Pedido Bar,
        # FK tipo_cliente.codigo) — separado do tipo do CLIENTE
        # (cliente.cliente_forn): um cliente Entrega pode ser lançado como
        # Comanda na lista (o tipo do cliente não muda, só o do pedido), e
        # vice-versa. EXCEÇÃO: cliente reservado — nome fantasia contendo
        # "MESA"/"COMANDA"/"BALCÃO" (mesa/comanda/balcão físicos do
        # estabelecimento, mesmo critério de texto já usado em
        # `clientes_service._cliente_mesa_ou_comanda`, aqui estendido pros
        # 3 tipos em vez de só Mesa) — sempre trava o pedido no seu
        # próprio tipo (cliente_forn), ignorando o que foi pedido: não faz
        # sentido uma "MESA 7" virar um pedido de Entrega. Sem cliente
        # reservado e sem `req.tipo` informado, o campo fica NULL — a
        # listagem cai pro tipo do cliente nesse caso
        # (`COALESCE(p.tipo, c.cliente_forn)`, ver `_list_pedidos_sync`).
        # Pedido explícito do usuário, 2026-07-18.
        fantasia_up = (cli_row.get("fantasia") or "").strip().upper()
        cliente_reservado = any(k in fantasia_up for k in ("MESA", "COMANDA", "BALCÃO", "BALCAO"))
        if cliente_reservado:
            tipo_final = cli_row.get("cliente_forn")
        else:
            tipo_final = req.tipo

        validade = req.validade or None
        obs = req.obs or ""
        previsao_entrega = req.previsao_entrega or None
        hora_entrega = (req.hora_entrega or "").strip() or None
        forma_pag = (req.forma_pag or "")[:3] or None
        referencia = (req.referencia or "")[:64] or None

        if pedido_codigo is None:
            # pedido é IDENTITY — deixar o SQL gerar e retornar via OUTPUT INSERTED.pedido
            cur.execute(
                "INSERT INTO pedido_venda "
                "(cliente, data, validade, vendedor, hora_aberto, obs, situacao, "
                " NOME_CLIENTE, TELEFONE_CLIENTE, abertopor, total, tipo, area_atuacao, "
                " previsao_entrega, hora_entrega, forma_pag, num_ped_cliente) "
                "OUTPUT INSERTED.pedido "
                "VALUES (%s, CAST(GETDATE() AS DATE), %s, %s, "
                "        CONVERT(NVARCHAR(8), GETDATE(), 108), %s, 'A', %s, %s, %s, 0, %s, %s, %s, %s, %s, %s)",
                (req.cliente, validade, req.vendedor, obs, nome_cli, tel_cli, req.vendedor, tipo_final,
                 req.area_atuacao, previsao_entrega, hora_entrega, forma_pag, referencia),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Falha ao obter número do pedido."}
            pedido_id = int(row["pedido"] if isinstance(row, dict) else row[0])
        else:
            # Update apenas dos campos editáveis (não mexe em situacao aqui).
            cur.execute(
                "UPDATE pedido_venda SET "
                " cliente=%s, validade=%s, vendedor=%s, obs=%s, "
                " NOME_CLIENTE=%s, TELEFONE_CLIENTE=%s, tipo=%s, area_atuacao=%s, "
                " previsao_entrega=%s, hora_entrega=%s, forma_pag=%s, num_ped_cliente=%s "
                "WHERE pedido=%s",
                (req.cliente, validade, req.vendedor, obs, nome_cli, tel_cli, tipo_final, req.area_atuacao,
                 previsao_entrega, hora_entrega, forma_pag, referencia, pedido_codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            pedido_id = pedido_codigo
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "pedido": pedido_id}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _toggle_entregue_sync(req: PedidoEntregueRequest, pedido: int) -> dict:
    """Checkbox 'Pedido Entregue' (FrmManPedBar.frm, Check88_Click) — grava
    direto no clique, fora do fluxo normal de Gravar (mesmo comportamento
    do legado)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "UPDATE pedido_venda SET pedido_entregue=%s WHERE pedido=%s",
            (1 if req.entregue else 0, pedido),
        )
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "entregue": req.entregue}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar entrega: {e}"}


def _set_forma_pag_simples_sync(req: FormaPagSimplesRequest, pedido: int) -> dict:
    """Combobox simples 'Forma de Pagamento' do cabeçalho — grava direto ao
    trocar, fora do fluxo normal de Gravar (mesmo raciocínio de
    `_toggle_entregue_sync`). Só permitido com o pedido ainda Aberto ou
    Fechado (mesma janela em que o próprio Faturar/Fecha_FPAG_Dav aceita
    ajustar a forma de pagamento) — ver PedidoBar/PedidoCompleto/O.S.,
    `FormaPagSimplesRequest`."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit not in ("A", "F"):
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}
        forma_pag = (req.forma_pag or "")[:3] or None
        cur.execute("UPDATE pedido_venda SET forma_pag=%s WHERE pedido=%s", (forma_pag, pedido))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar forma de pagamento: {e}"}


def _set_qtd_pessoas_sync(req: QtdPessoasRequest, pedido: int) -> dict:
    """Painel de Pedidos — quantidade de pessoas na mesa/comanda/balcão,
    grava direto ao editar no card (mesmo raciocínio de
    `_set_forma_pag_simples_sync` acima). Só permitido com o pedido ainda
    Aberto ou Fechado."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_qtd_pessoas_col(cur)
        cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit not in ("A", "F"):
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}
        qtd = req.qtd_pessoas if (req.qtd_pessoas or 0) > 0 else None
        cur.execute("UPDATE pedido_venda SET qtd_pessoas=%s WHERE pedido=%s", (qtd, pedido))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar quantidade de pessoas: {e}"}


async def list_pedidos(req: PedidosListRequest) -> dict:
    return await asyncio.to_thread(_list_pedidos_sync, req)


async def get_pedido(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_get_pedido_sync, servidor, banco, pedido)


async def pedido_aberto_por_cliente(servidor: str, banco: str, cliente: int) -> dict:
    return await asyncio.to_thread(_pedido_aberto_por_cliente_sync, servidor, banco, cliente)


async def save_pedido(req: PedidoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_pedido_sync, req, pedido_codigo)


async def toggle_entregue(req: PedidoEntregueRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_toggle_entregue_sync, req, pedido)


async def set_forma_pag_simples(req: FormaPagSimplesRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_set_forma_pag_simples_sync, req, pedido)


async def set_qtd_pessoas(req: QtdPessoasRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_set_qtd_pessoas_sync, req, pedido)


def _fechar_pedido_sync(req: FecharRequest, pedido: int) -> dict:
    """Fecha o Pedido (situação A -> F). Valida itens e permissão e baixa o
    estoque das PEÇAS (qtd -= q ; reservado += q). Serviços não movem estoque.
    Tudo numa única transação."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao, total, forma_pag FROM pedido_venda WHERE pedido=%s", (pedido,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser fechado."}
        # Permissão (master ignora)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO", "SITUACAO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar o pedido."}
        erro = _fechar_pedido_itens(cur, pedido, float(ex.get("total") or 0), (ex.get("forma_pag") or "").strip())
        if erro:
            conn.close()
            return {"success": False, "message": erro}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pré-venda Fechada.", "situacao": "F"}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar: {e}"}


async def fechar_pedido(req: FecharRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_fechar_pedido_sync, req, pedido)


def _faturar_pedido_sync(req: FecharRequest, pedido: int) -> dict:
    """Fatura o Pedido Bar: gera a Comanda (comanda, movimentacao S01,
    COMANDA_PED), libera o estoque reservado das PEÇAS e marca o pedido
    como pago (situação PG). Portado de `Command111_Click`/`GeraComanda`
    (FrmManPedBar.frm) — SEM a parte fiscal (emissão de NFC-e via
    Backon_Controllers.Nfe), que fica bloqueada por decisão explícita do
    usuário (ver PENDENCIAS.md > "Pedido Bar" e CLAUDE.md §12). Também não
    imprime (impressão térmica ainda não existe nesta migração — ver
    project_impressao_automatica_finalidade).

    Se o pedido ainda estiver Aberto (situação A), fecha primeiro (mesma
    rotina de `/pedidos/{pedido}/fechar`) e já emenda o faturamento — não
    exige que o usuário clique em "Fechar Pedido" antes (pedido explícito
    do usuário, replica o `Command111_Click` do legado, que faz o mesmo:
    só pula o fechamento se o pedido já estiver Fechado). Tudo numa única
    transação — se o faturamento falhar depois, o fechamento também é
    desfeito."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT situacao, cliente, total, area_atuacao, vendedor, forma_pag "
            "FROM pedido_venda WHERE pedido=%s",
            (pedido,),
        )
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit == "PG":
            conn.close()
            return {"success": False, "message": "Pedido já faturado."}
        if sit not in ("A", "F"):
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser faturado."}
        # Permissão (master ignora) — ação própria "FATURAR", separada de
        # SITUACAO (cada botão real da tela tem seu checkbox próprio).
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO", "FATURAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para faturar o pedido."}

        subtotal = float(ex.get("total") or 0)
        if sit == "A":
            # Valida/ajusta a forma de pagamento (Fecha_FPAG_Dav) só na
            # transição A->F — igual ao legado, que não revalida um pedido
            # já Fechado ao Faturar.
            erro = _fechar_pedido_itens(cur, pedido, subtotal, (ex.get("forma_pag") or "").strip())
            if erro:
                conn.close()
                return {"success": False, "message": erro}

        cliente = ex.get("cliente")
        area_atuacao = ex.get("area_atuacao") or 0
        vendedor = ex.get("vendedor") or 0

        cur.execute(
            "INSERT INTO comanda (data, cliente, valor_venda, situacao, atendente, hora_comanda, area_atuacao) "
            "OUTPUT INSERTED.comanda "
            "VALUES (CONVERT(date, GETDATE()), %s, %s, 'PG', %s, CONVERT(varchar(8), GETDATE(), 108), %s)",
            (cliente, subtotal, req.usuario_alteracao or 0, area_atuacao),
        )
        comanda_id = int(cur.fetchone()["comanda"])

        cur.execute(
            "SELECT produto, qtd_pedida, p_venda, custo_ped FROM pedido_venda_prod "
            "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
            (pedido,),
        )
        itens = cur.fetchall()
        for it in itens:
            produto = (it.get("produto") or "").strip()
            qtd = float(it.get("qtd_pedida") or 0)
            p_venda = float(it.get("p_venda") or 0)
            custo = float(it.get("custo_ped") or 0)
            _liberar_reservado(cur, produto, qtd)
            cur.execute(
                "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, p_unit, num_nf, serie_nf, vendedor, custo_mov) "
                "VALUES (CONVERT(date, GETDATE()), 'S01', %s, %s, %s, %s, 'CM', %s, %s)",
                (produto, qtd, p_venda, comanda_id, vendedor, custo),
            )

        cur.execute("INSERT INTO COMANDA_PED (comanda, ped) VALUES (%s, %s)", (comanda_id, pedido))
        cur.execute("UPDATE pedido_venda SET situacao='PG' WHERE pedido=%s", (pedido,))
        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "message": "Pedido faturado.", "situacao": "PG",
            "comanda": comanda_id, "situacao_antes": sit,
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao faturar: {e}"}


async def faturar_pedido(req: FecharRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_faturar_pedido_sync, req, pedido)


def _cancelar_pedido_sync(req: FecharRequest, pedido: int) -> dict:
    """Cancela o Pedido Bar (situação -> C). Portado de `Command9_Click`
    (FrmManPedBar.frm): só permite cancelar pedido Aberto ou Fechado — um
    pedido já Faturado (PG) não pode ser cancelado (o legado bloqueia com
    a mesma mensagem; não desfaz Comanda/COMANDA_PED). Se o pedido estava
    Fechado (situação F), o Fechar já tinha baixado o estoque das PEÇAS
    (`_mover_estoque`, qtd -= q / reservado += q) — cancelar reverte esse
    movimento (`_mover_estoque` com delta negativo: qtd += q / reservado
    -= q), réplica exata do UPDATE de estorno do legado. Se ainda estava
    Aberto, nada foi baixado, então não há nada para reverter.

    O legado exige senha de gerente antes de cancelar (`frGerente`); esta
    migração usa o mesmo mecanismo de permissão de grupo (`CANCELAR`, ação
    própria — cada botão real da tela tem seu checkbox, não reaproveita
    SITUACAO) em vez de senha ad-hoc — decisão consistente com o resto da
    migração (ver "Não replicar truques VB6" no CLAUDE.md)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit not in ("A", "F"):
            conn.close()
            return {"success": False, "message": "Somente pedidos em Aberto/Fechado poderão ser Cancelados!"}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO", "CANCELAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar o pedido."}

        if sit == "F":
            cur.execute(
                "SELECT produto, qtd_pedida FROM pedido_venda_prod "
                "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
                (pedido,),
            )
            for it in cur.fetchall():
                _mover_estoque(cur, (it.get("produto") or "").strip(), -float(it.get("qtd_pedida") or 0), "reservado")

        cur.execute("UPDATE pedido_venda SET situacao='C' WHERE pedido=%s", (pedido,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pedido Cancelado!", "situacao": "C", "situacao_antes": sit}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar: {e}"}


async def cancelar_pedido(req: FecharRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_cancelar_pedido_sync, req, pedido)


def _reabrir_pedido_sync(req: FecharRequest, pedido: int) -> dict:
    """Reabre o Pedido Bar (situação F -> A). Portado de `cmdReabrir_Click`
    (FrmManPedBar.frm): só permite reabrir pedido Fechado — o legado
    bloqueia Aberto/Cancelado/Faturado com a mesma mensagem (o ramo "C" no
    `Select Case` do legado é código morto, nunca alcançado, porque o guard
    anterior já rejeita qualquer situação diferente de "F"; não replicado
    aqui — ver "Não replicar truques VB6" no CLAUDE.md). Reverte a baixa de
    estoque que o Fechar tinha feito (`_mover_estoque` com delta negativo:
    qtd += q / reservado -= q), mesmo idioma exato já usado pelo estorno do
    Cancelar-a-partir-de-Fechado. Diferente do Cancelar, o legado não exige
    senha de gerente aqui — mesmo assim esta migração usa uma permissão de
    grupo própria (`REABRIR`), consistente com "cada botão real da tela tem
    seu checkbox"."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit != "F":
            conn.close()
            return {"success": False, "message": "Somente pedidos fechados podem ser reabertos!"}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO", "REABRIR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para reabrir o pedido."}

        cur.execute(
            "SELECT produto, qtd_pedida FROM pedido_venda_prod "
            "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
            (pedido,),
        )
        for it in cur.fetchall():
            _mover_estoque(cur, (it.get("produto") or "").strip(), -float(it.get("qtd_pedida") or 0), "reservado")

        cur.execute("UPDATE pedido_venda SET situacao='A' WHERE pedido=%s", (pedido,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pedido Reaberto!", "situacao": "A"}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao reabrir: {e}"}


async def reabrir_pedido(req: FecharRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_reabrir_pedido_sync, req, pedido)


def _dividir_pedido_sync(req: DividirPedidoRequest, pedido: int) -> dict:
    """Dividir Pedido — funcionalidade NOVA, sem precedente no legado
    (pesquisado em toda a árvore VB6, nenhum "Dividir/Separar Conta" existe
    em nenhuma linha de negócio; ver PENDENCIAS.md > "Pedido Bar" >
    "Dividir Pedido"). Decisões confirmadas com o usuário (2026-07-17):

    - Só pedido Aberto pode ser dividido (nada de estoque/comanda/forma de
      pagamento foi lançado ainda — mais simples e seguro).
    - Cada grupo em `req.grupos` vira um pedido NOVO, sob o MESMO cliente do
      pedido original (a Mesa/Comanda) — relaxa de propósito a invariante de
      "1 pedido aberto por cliente" só para pedidos originados de uma
      divisão (`_pedido_aberto_por_cliente_sync` continua trazendo só o
      pedido mais recente quando há mais de um; ver docstring lá).
    - Divisão de item compartilhado por VALOR fracionário de uma unidade
      indivisível é a MESMA mecânica que dividir por quantidade inteira —
      `qtd_pedida` já é numérico/decimal (produtos vendidos por m²/kg já
      usam fração), então qtd=0.25 em 4 pedidos representa exatamente 25%
      do valor (e, futuramente, 25% da baixa de estoque, cada pedido
      baixando a sua fração no PRÓPRIO Fechar) sem precisar de nenhuma
      coluna nova de "valor fracionado".
    - Rastreabilidade: reaproveita `pedido_venda.num_ped_cliente` (coluna já
      existente, já exposta no Pedido Completo como "Nº Pedido do Cliente")
      — cada pedido filho grava ali o nº do pedido original, em vez de criar
      uma coluna nova (mesmo raciocínio de reaproveitar schema legado já
      usado no módulo Cilindro, ver CLAUDE.md "Não replicar truques VB6").

    O que fica no pedido original nunca é listado explicitamente pelo
    chamador — é sempre "o que sobrar" depois de descontar o que foi movido
    pra cada grupo. Se um item fica com quantidade zero no original, a linha
    é excluída; se o pedido original fica sem nenhum item além da Taxa de
    Serviço, a taxa também é removida e o pedido original é cancelado
    automaticamente (evita um pedido "Aberto" vazio sobrando na lista)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT situacao, cliente, vendedor, area_atuacao, forma_pag, obs, "
            "NOME_CLIENTE, TELEFONE_CLIENTE, LOCALIZACAO, num_ped_cliente "
            "FROM pedido_venda WHERE pedido=%s",
            (pedido,),
        )
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit != "A":
            conn.close()
            return {"success": False, "message": "Somente pedidos em Aberto podem ser divididos."}
        # Pedido FILHO de uma divisão (referência numérica aponta pro
        # original) não pode ser dividido de novo — evita uma cadeia de
        # múltiplos níveis (filho de filho), que a resolução de "raiz" em
        # `_get_pedido_sync`/o retorno de item ao original em
        # `_delete_item_sync` não foram desenhados pra acompanhar. Pedido
        # explícito do usuário, 2026-07-17.
        if (ex.get("num_ped_cliente") or "").strip().isdigit():
            conn.close()
            return {"success": False, "message": "Este pedido já é resultado de uma distribuição — não pode ser distribuído novamente."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO", "DIVIDIR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para dividir o pedido."}

        grupos = [g for g in req.grupos if g.itens]
        if not grupos:
            conn.close()
            return {"success": False, "message": "Informe ao menos um grupo com itens para dividir."}

        cur.execute(
            "SELECT codauto, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
            "descricao_produto, unidade_pedido "
            "FROM pedido_venda_prod WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
            (pedido,),
        )
        itens_originais = {int(r["codauto"]): r for r in cur.fetchall()}

        somas: dict[int, float] = {}
        for g in grupos:
            for it in g.itens:
                if it.codauto not in itens_originais:
                    conn.close()
                    return {"success": False, "message": f"Item #{it.codauto} não pertence a este pedido."}
                if it.qtd <= 0:
                    conn.close()
                    return {"success": False, "message": "Quantidade dividida deve ser maior que zero."}
                produto = (itens_originais[it.codauto].get("produto") or "").strip().upper()
                if produto == TAXA_SERVICO_CODIGO:
                    conn.close()
                    return {"success": False, "message": "Taxa de Serviço é recalculada automaticamente em cada pedido — não pode ser dividida manualmente."}
                somas[it.codauto] = somas.get(it.codauto, 0.0) + it.qtd
        for codauto, soma in somas.items():
            qtd_original = float(itens_originais[codauto].get("qtd_pedida") or 0)
            if soma > qtd_original + 0.0001:
                conn.close()
                return {"success": False, "message": "A quantidade dividida de um item não pode exceder a quantidade do pedido original."}

        _ensure_hora_inclusao_item_col(cur)
        referencia_original = str(pedido)
        novos_pedidos: list[int] = []

        for g in grupos:
            cur.execute(
                "INSERT INTO pedido_venda "
                "(cliente, data, vendedor, hora_aberto, obs, situacao, "
                " NOME_CLIENTE, TELEFONE_CLIENTE, abertopor, total, tipo, area_atuacao, "
                " forma_pag, LOCALIZACAO, num_ped_cliente) "
                "OUTPUT INSERTED.pedido "
                "VALUES (%s, CAST(GETDATE() AS DATE), %s, CONVERT(NVARCHAR(8), GETDATE(), 108), %s, 'A', "
                "        %s, %s, %s, 0, 0, %s, %s, %s, %s)",
                (
                    ex["cliente"], ex.get("vendedor"), ex.get("obs") or "",
                    ex.get("NOME_CLIENTE") or "", ex.get("TELEFONE_CLIENTE") or "", ex.get("vendedor"),
                    ex.get("area_atuacao"), ex.get("forma_pag"), ex.get("LOCALIZACAO"),
                    referencia_original,
                ),
            )
            novo_pedido = int(cur.fetchone()["pedido"])
            novos_pedidos.append(novo_pedido)

            for it in g.itens:
                original = itens_originais[it.codauto]
                cur.execute(
                    "INSERT INTO pedido_venda_prod "
                    "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
                    " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
                    " hora_inclusao_item) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE),"
                    "        CONVERT(NVARCHAR(8), GETDATE(), 108))",
                    (
                        novo_pedido, original["produto"], it.qtd, original["p_venda"], original["p_normal"],
                        original["desconto"], original["acrescimo"], original["custo_ped"],
                        original.get("descricao_produto"), original.get("unidade_pedido"),
                    ),
                )

        # Reduz/remove o que foi movido no pedido original.
        itens_zerados_ou_taxa_apenas = True
        for codauto, original in itens_originais.items():
            movido = somas.get(codauto, 0.0)
            restante = round(float(original.get("qtd_pedida") or 0) - movido, 4)
            if restante <= 0.0001:
                cur.execute("DELETE FROM pedido_venda_prod WHERE codauto=%s", (codauto,))
            else:
                cur.execute("UPDATE pedido_venda_prod SET qtd_pedida=%s WHERE codauto=%s", (restante, codauto))
                if (original.get("produto") or "").strip().upper() != TAXA_SERVICO_CODIGO:
                    itens_zerados_ou_taxa_apenas = False

        sincroniza_taxa_servico_apos_alteracao(cur, pedido)
        for novo_pedido in novos_pedidos:
            sincroniza_taxa_servico_apos_alteracao(cur, novo_pedido)
            _recalc_pedido_total(cur, novo_pedido)

        original_cancelado = False
        if itens_zerados_ou_taxa_apenas:
            # Só sobrou (no máximo) a linha de Taxa de Serviço, sem nenhum
            # produto/serviço real — remove ela também e cancela o pedido
            # original, em vez de deixar um "Aberto" vazio na lista.
            cur.execute(
                "DELETE FROM pedido_venda_prod WHERE pedido=%s AND produto=%s",
                (pedido, TAXA_SERVICO_CODIGO),
            )
            cur.execute("UPDATE pedido_venda SET situacao='C', total=0 WHERE pedido=%s", (pedido,))
            original_cancelado = True
        else:
            _recalc_pedido_total(cur, pedido)

        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True,
            "message": f"Pedido dividido em {len(novos_pedidos)} pedido(s) novo(s).",
            "novos_pedidos": novos_pedidos,
            "original_cancelado": original_cancelado,
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao dividir pedido: {e}"}


async def dividir_pedido(req: DividirPedidoRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_dividir_pedido_sync, req, pedido)

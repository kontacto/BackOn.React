"""Pedido Completo (web) — cabeçalho + itens sobre a MESMA tabela
`pedido_venda`/`pedido_venda_prod` do Pedido rápido mobile
(`pedidos_service.py`/`itens_service.py`), Fase A (núcleo) do plano
faseado em PENDENCIAS.md > "Transações" > "Pedido Completo".

Arquivo próprio, deliberadamente sem alterar `pedidos_service.py`/
`itens_service.py` — a tela rápida mobile continua com seu próprio
conjunto (menor) de campos e sua própria lógica de Fechar, comprovada em
uso. Aqui vive só o que é genuinamente NOVO/maior pro Pedido Completo:
- Cabeçalho com o conjunto de campos real de `frmmanpedfor.frm` (Frame2):
  forma_pag, local_entrega, previsao_entrega, num_ped_cliente, infoentrega
  — nenhum existe no fluxo rápido.
- Item com a cadeia de resolução mais rica (`_resolve_produto_completo`) e
  expansão de kit (`_kit_componentes`), ver `pedido_common.py`.
- Cancelar (não existe no fluxo rápido).
Consulta/exclusão de item individual, e o Fechar em si (mesma regra A->F,
mesma baixa de estoque — agora m²-aware, ver `_fechar_pedido_itens` em
`pedido_common.py`), são idênticos ao fluxo rápido — reaproveitados
diretamente de `itens_service`/`pedidos_service` pelas rotas
(`routes/pedido_completo.py`), não duplicados aqui. Edição de item
(`_update_item_completo_sync`) NÃO é mais reaproveitada de
`itens_service.update_item` — precisa reconhecer item m² (recalcular a
área ao editar dimensões/tipo de preço); item sem dimensão segue exatamente
o mesmo comportamento que `itens_service.update_item` já tinha.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.schemas import PedidoCompletoSaveRequest, ItemSaveRequest, FecharRequest, DividirPedidoRequest
from services.constants import SITUACAO_LABEL
from services.descontos_service import _validar_limite_desconto, _log_desconto_item
from services.pedido_common import (
    _check_cliente_ativo, _check_pedido_aberto, _item_total, _recalc_pedido_total,
    _modulo_servicos_ativo, _modulo_agenda_ativo, _resolve_produto_completo, _kit_componentes,
    _ensure_hora_inclusao_item_col, _fechar_pedido_itens, _resolve_tipo_pedido,
    _modulo_metro_quadrado_ativo, _config_m2, _area_preco, TIPOS_PRECO_M2,
    TIPO_EFETIVO_PEDIDO_SQL,
)
from services.permissoes_service import tem_permissao
from services.itens_service import (
    TAXA_SERVICO_CODIGO, sincroniza_taxa_servico_apos_alteracao,
    _list_itens_sync as _list_itens_bar_shared,
)
# Faturar/Reabrir/Dividir/Cancelar NÃO são reimplementados aqui — o Pedido
# Geral/Completo reaproveita literalmente as mesmas funções do Pedido Bar
# (`pedidos_service`, mesma tabela `pedido_venda`), só passando
# `tela="PEDIDO_COMP"` pra checar a permissão certa no catálogo. Pedido
# explícito do usuário, 2026-07-20 ("tente usar as mesmas funções para não
# replicar o mesmo código entre telas") — ver docstring de cada função em
# `pedidos_service.py` (`_faturar_pedido_sync` etc.) pro detalhe da regra.
from services.pedidos_service import (
    faturar_pedido as _faturar_pedido_bar_shared,
    reabrir_pedido as _reabrir_pedido_bar_shared,
    dividir_pedido as _dividir_pedido_bar_shared,
    cancelar_pedido as _cancelar_pedido_bar_shared,
    toggle_entregue as _toggle_entregue_bar_shared,
)


def _get_pedido_completo_sync(servidor: str, banco: str, pedido: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT p.pedido, p.cliente, p.data, p.validade, p.vendedor, p.hora_aberto, "
            "       p.obs, p.situacao, p.total, p.NOME_CLIENTE, p.TELEFONE_CLIENTE, p.area_atuacao, "
            "       p.forma_pag, p.local_entrega, p.previsao_entrega, p.num_ped_cliente, p.infoentrega, "
            "       p.hora_entrega, p.pedido_entregue, p.tipo, "
            "       c.nome AS cliente_nome, c.cgc_cpf AS cliente_cgc, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome, "
            "       a.descricao AS area_descricao, fp.descricao AS forma_pag_descricao, "
            "       tc.descricao AS tipo_descricao "
            "FROM pedido_venda p "
            "LEFT JOIN cliente c ON c.codigo = p.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = p.vendedor "
            "LEFT JOIN area_atuacao a ON a.area = p.area_atuacao "
            "LEFT JOIN forma_pagamento fp ON fp.codigo = p.forma_pag "
            f"LEFT JOIN tipo_cliente tc ON tc.codigo = {TIPO_EFETIVO_PEDIDO_SQL} "
            "WHERE p.pedido = %s",
            (pedido,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}

        # Pedidos da mesma divisão (Dividir Pedido) — mesma lógica do Pedido
        # Bar (`pedidos_service._get_pedido_sync`), reaproveitada aqui pra
        # não duplicar: `num_ped_cliente` rastreia o pedido-pai; consultar
        # pela raiz (não só "quem aponta pra mim") mantém a lista igual não
        # importa a partir de qual pedido da divisão a tela foi aberta.
        # Trazido ao Pedido Geral 2026-07-20 junto com Dividir Pedido.
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
        sit = (row.get("situacao") or "").strip().upper()
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
                "forma_pag": (row.get("forma_pag") or "").strip(),
                "forma_pag_descricao": (row.get("forma_pag_descricao") or "").strip(),
                "local_entrega": row.get("local_entrega") or "",
                "previsao_entrega": row["previsao_entrega"].isoformat() if row.get("previsao_entrega") else None,
                "hora_entrega": (row.get("hora_entrega") or "").strip(),
                "pedido_entregue": bool(row.get("pedido_entregue")),
                # Combobox "Tipo" (Mesa/Comanda/Balcão/Entrega) — trazido do
                # Pedido Bar 2026-07-20, mesma regra (ver `_resolve_tipo_pedido`).
                "tipo": int(row["tipo"]) if row.get("tipo") is not None else None,
                "tipo_descricao": (row.get("tipo_descricao") or "").strip(),
                # "Nº Pedido do Cliente" — campo real do Pedido Geral desde a
                # Fase A; também reaproveitado pelo Dividir Pedido pra
                # registrar o nº do pedido-pai nos pedidos filhos (mesmo
                # mecanismo do Pedido Bar, ver `_dividir_pedido_sync`). Um
                # valor puramente numérico aqui indica pedido filho de uma
                # divisão — a tela usa isso pra travar o campo, mesmo
                # critério já usado no Pedido Bar (`isPedidoFilho`).
                "num_ped_cliente": (row.get("num_ped_cliente") or "").strip(),
                "infoentrega": row.get("infoentrega") or "",
                "editavel": sit == "A",
                "pedidos_relacionados": pedidos_relacionados,
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_pedido_completo_sync(req: PedidoCompletoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        sit_atual = None
        if pedido_codigo is not None:
            cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido_codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            sit_atual = (ex.get("situacao") or "").strip().upper()
            # Regra real (frmmanpedfor.frm): pedido Fechado só permite editar
            # vendedor/forma de pagamento; Aberto permite editar tudo.
            if sit_atual not in ("A", "F"):
                conn.close()
                label = SITUACAO_LABEL.get(sit_atual, sit_atual)
                return {"success": False, "message": f"Pedido com situação '{label}' não pode ser alterado."}
        else:
            ok, label = _check_cliente_ativo(cur, req.cliente)
            if not ok:
                conn.close()
                return {
                    "success": False,
                    "message": f"Cliente com situação '{label}' não pode gerar novo pedido.",
                }

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
        # Combobox "Tipo" (Mesa/Comanda/Balcão/Entrega) — mesma regra do
        # Pedido Bar, extraída pra `_resolve_tipo_pedido` (pedido_common.py)
        # pra não duplicar. Pedido explícito do usuário, 2026-07-20.
        tipo_final = _resolve_tipo_pedido(cli_row.get("fantasia"), cli_row.get("cliente_forn"), req.tipo)

        validade = req.validade or None
        previsao_entrega = req.previsao_entrega or None
        hora_entrega = (req.hora_entrega or "").strip() or None
        obs = req.obs or ""
        forma_pag = (req.forma_pag or "")[:3]
        local_entrega = req.local_entrega or ""
        infoentrega = req.infoentrega or ""
        num_ped_cliente = (req.num_ped_cliente or "")[:64]

        if pedido_codigo is None:
            cur.execute(
                "INSERT INTO pedido_venda "
                "(cliente, data, validade, vendedor, forma_pag, previsao_entrega, hora_entrega, local_entrega, "
                " infoentrega, num_ped_cliente, hora_aberto, obs, situacao, "
                " NOME_CLIENTE, TELEFONE_CLIENTE, abertopor, total, tipo, area_atuacao) "
                "OUTPUT INSERTED.pedido "
                "VALUES (%s, CAST(GETDATE() AS DATE), %s, %s, %s, %s, %s, %s, "
                "        %s, %s, CONVERT(NVARCHAR(8), GETDATE(), 108), %s, 'A', %s, %s, %s, 0, %s, %s)",
                (
                    req.cliente, validade, req.vendedor, forma_pag, previsao_entrega, hora_entrega, local_entrega,
                    infoentrega, num_ped_cliente, obs, nome_cli, tel_cli, req.vendedor, tipo_final, req.area_atuacao,
                ),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Falha ao obter número do pedido."}
            pedido_id = int(row["pedido"] if isinstance(row, dict) else row[0])
        elif sit_atual == "F":
            # Fechado: só vendedor/forma_pag são editáveis (regra real do legado).
            cur.execute(
                "UPDATE pedido_venda SET vendedor=%s, forma_pag=%s WHERE pedido=%s",
                (req.vendedor, forma_pag, pedido_codigo),
            )
            pedido_id = pedido_codigo
        else:
            cur.execute(
                "UPDATE pedido_venda SET "
                " cliente=%s, validade=%s, vendedor=%s, forma_pag=%s, previsao_entrega=%s, hora_entrega=%s, "
                " local_entrega=%s, infoentrega=%s, num_ped_cliente=%s, obs=%s, tipo=%s, "
                " NOME_CLIENTE=%s, TELEFONE_CLIENTE=%s, area_atuacao=%s "
                "WHERE pedido=%s",
                (
                    req.cliente, validade, req.vendedor, forma_pag, previsao_entrega, hora_entrega,
                    local_entrega, infoentrega, num_ped_cliente, obs, tipo_final,
                    nome_cli, tel_cli, req.area_atuacao, pedido_codigo,
                ),
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


def _add_item_completo_sync(req: ItemSaveRequest, pedido: int) -> dict:
    """Como `itens_service._add_item_sync`, mas com a cadeia de resolução
    mais rica (`_resolve_produto_completo`) e expansão de kit
    (`produtos_compostos`) — ver docstring do módulo."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}
        _ensure_hora_inclusao_item_col(cur)

        codigo = (req.produto or "").strip()
        if not codigo:
            conn.close()
            return {"success": False, "message": "Produto/serviço obrigatório."}
        if codigo.upper() == TAXA_SERVICO_CODIGO:
            conn.close()
            return {
                "success": False,
                "message": "Taxa de Serviço não pode ser adicionada manualmente — use o botão 'Tx Serviço'.",
            }
        prod = _resolve_produto_completo(cur, codigo)
        if not prod:
            conn.close()
            return {"success": False, "message": f"Produto/serviço '{codigo}' não encontrado."}
        if prod["tipo"] == "S" and not _modulo_servicos_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Serviço está desativado — não é possível incluir serviços no Pedido."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}

        # Número de série (Fase B do plano faseado — `PECAS.controla_num_serie`,
        # padrão `CmbNDS`/`FrmNDS` em frmmanpedfor.frm): produto controlado por
        # série sempre lança quantidade=1 e exige a escolha de um número de
        # série disponível ANTES de incluir o item. Ver PENDENCIAS.md >
        # "Transações" > "Pedido Geral — Fase B: número de série" pro rastreio
        # completo — inclusive a dúvida em aberto sobre se/quando
        # `pecas_num_serie.disponivel` deveria ser zerado (decisão desta rodada:
        # NÃO zerar aqui, só grava o vínculo — mesmo padrão já usado pela
        # Comanda, que só reserva de fato no faturamento).
        cod_num_serie = None
        if prod.get("controla_num_serie"):
            qtd = 1
            cod_num_serie = req.cod_num_serie
            if not cod_num_serie:
                conn.close()
                return {
                    "success": False,
                    "message": f"'{prod['descricao']}' controla número de série — selecione um número de série disponível.",
                }
            cur.execute(
                "SELECT codigo FROM pecas_num_serie WHERE codigo=%s AND codigo_int=%s AND disponivel=1",
                (cod_num_serie, prod["codigo"]),
            )
            if not cur.fetchone():
                conn.close()
                return {"success": False, "message": "Número de série inválido ou não está mais disponível para este produto."}

        componentes = _kit_componentes(cur, prod["codigo"]) if prod["tipo"] == "P" else []
        codautos: list[int] = []

        # Clínica OU Assistência: item de Serviço vira N linhas (qtd_pedida=1
        # cada), uma por unidade — cada linha é 1 sessão agendável (ver
        # `agenda_service.py` e PENDENCIAS.md > "Transações" > "Pedido Geral
        # — Fase B: Clínica (Agendamento)"). Réplica de
        # `frmmanpedfor.frm:8241-8280` (`For QTDCLINICA = 1 To Campo(4)`) —
        # sem exceção por serviço, sem limite superior (legado não tem, não
        # inventar um). Assistência habilita o MESMO comportamento (user-
        # directed 2026-07-28: "é só chamar a tela", não é uma variação
        # nova) — ver `_modulo_agenda_ativo`.
        clinica_split = prod["tipo"] == "S" and _modulo_agenda_ativo(cur)

        if clinica_split:
            if qtd != int(qtd):
                conn.close()
                return {"success": False, "message": "Quantidade deve ser um número inteiro para item de Serviço (cada unidade vira uma sessão agendável)."}
            qtd_int = int(qtd)
            p_normal = req.valor_unitario if req.valor_unitario is not None else prod["valor"]
            p_normal = float(p_normal or 0)
            desc = float(req.desconto or 0)
            acr = float(req.acrescimo or 0)
            if desc and not prod.get("aceita_desconto", True):
                conn.close()
                return {"success": False, "message": f"Produto '{prod['codigo']}' não aceita desconto."}
            lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
            if lim_err:
                conn.close()
                return {"success": False, "message": lim_err}
            p_venda = round(p_normal - desc + acr, 4)
            complemento = (req.complemento or "").strip()
            for _ in range(qtd_int):
                cur.execute(
                    "INSERT INTO pedido_venda_prod "
                    "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
                    " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
                    " hora_inclusao_item) "
                    "OUTPUT INSERTED.codauto "
                    "VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE),"
                    "        CONVERT(NVARCHAR(8), GETDATE(), 108))",
                    (pedido, prod["codigo"], p_venda, p_normal, desc, acr, prod["custo"], complemento, prod["unidade"]),
                )
                row = cur.fetchone()
                codauto = int(row["codauto"] if isinstance(row, dict) else row[0])
                codautos.append(codauto)
                _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)
        elif componentes:
            # Kit: expande em N linhas (uma por componente), sem gravar linha
            # própria pro código principal — regra real (não workaround), ver
            # PENDENCIAS.md > "Pedido Completo" item 3.
            for comp in componentes:
                sub_codigo = (comp.get("vinculado") or "").strip()
                sub = _resolve_produto_completo(cur, sub_codigo)
                if not sub:
                    conn.rollback()
                    conn.close()
                    return {"success": False, "message": f"Componente '{sub_codigo}' do kit '{prod['codigo']}' não encontrado."}
                sub_qtd = round(qtd * float(comp.get("qtd") or 0), 4)
                if sub_qtd <= 0:
                    continue
                valor_no_kit = comp.get("valor_no_kit")
                p_normal = float(valor_no_kit) if valor_no_kit is not None else sub["valor"]
                p_venda = round(p_normal, 4)
                descricao = (comp.get("descricao_no_kit") or "").strip() or sub["descricao"]
                cur.execute(
                    "INSERT INTO pedido_venda_prod "
                    "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
                    " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
                    " hora_inclusao_item, Produto_composto) "
                    "OUTPUT INSERTED.codauto "
                    "VALUES (%s,%s,%s,%s,%s,0,0,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE),"
                    "        CONVERT(NVARCHAR(8), GETDATE(), 108),%s)",
                    (pedido, sub["codigo"], sub_qtd, p_venda, p_normal, sub["custo"], descricao, sub["unidade"], prod["codigo"][:8]),
                )
                row = cur.fetchone()
                codautos.append(int(row["codauto"] if isinstance(row, dict) else row[0]))
            if not codautos:
                conn.close()
                return {"success": False, "message": "Kit sem componentes válidos para a quantidade informada."}
        else:
            # Metro Quadrado (m²/ml/m³) — só produto (tipo "P"), unidade
            # M2/ML/M3, e módulo ligado (ver `_modulo_metro_quadrado_ativo`
            # em pedido_common.py — desligado não bloqueia, só faz o item
            # entrar pelo caminho normal abaixo, réplica do `Else` do
            # legado). Ver PENDENCIAS.md > "Transações" > "Pedido Geral —
            # Metro Quadrado" pro rastreio completo.
            comprimento = largura = area_venda = comprimento_chapa = largura_chapa = None
            eh_produto_m2 = prod["tipo"] == "P" and (prod.get("unidade") or "").strip().upper() in ("M2", "ML", "M3")
            if eh_produto_m2 and _modulo_metro_quadrado_ativo(cur):
                if req.tipo_preco_m2 is None or not req.comprimento or not req.largura:
                    conn.close()
                    return {"success": False, "message": "Informe o tipo de preço e as dimensões (comprimento/largura) para este produto."}
                tipo_m2 = next((t for t in TIPOS_PRECO_M2 if t[0] == req.tipo_preco_m2), None)
                if not tipo_m2:
                    conn.close()
                    return {"success": False, "message": "Tipo de preço inválido."}
                _, _, coluna_preco, coluna_area_minima = tipo_m2
                cur.execute(f"SELECT {coluna_preco} AS preco FROM pecas WHERE codigo_int=%s", (prod["codigo"],))
                preco_row = cur.fetchone()
                preco_tipo = float((preco_row.get("preco") if preco_row else None) or 0)
                if preco_tipo <= 0:
                    conn.close()
                    return {"success": False, "message": "Este tipo de preço não está cadastrado para o produto."}
                cfg_m2 = _config_m2(cur)
                comprimento = float(req.comprimento)
                largura = float(req.largura)
                comprimento_chapa = float(req.comprimento_chapa) if req.comprimento_chapa else comprimento
                largura_chapa = float(req.largura_chapa) if req.largura_chapa else largura
                modo_arredondamento = 10 if prod.get("controla_num_serie") else 5
                area_venda = _area_preco(
                    comprimento, largura, cfg_m2[coluna_area_minima], modo_arredondamento,
                    comprimento_chapa, largura_chapa, cfg_m2["vidro_controla_cabeca_chapa"],
                    cfg_m2["metro_quadrado_minima_metragem"],
                )
                # Decisão de arquitetura (ver PENDENCIAS.md): dobra a área
                # dentro do preço unitário, em vez de replicar a
                # multiplicação de 3 fatores (qtd × área × preço) espalhada
                # pelo legado em ~25 pontos diferentes — assim
                # `qtd_pedida × p_venda` (fórmula já usada em todo o app)
                # já dá o total certo.
                valor_unitario_efetivo = round(preco_tipo * area_venda, 4)
            else:
                valor_unitario_efetivo = req.valor_unitario if req.valor_unitario is not None else prod["valor"]

            p_normal = float(valor_unitario_efetivo or 0)
            desc = float(req.desconto or 0)
            acr = float(req.acrescimo or 0)
            if desc and not prod.get("aceita_desconto", True):
                conn.close()
                return {"success": False, "message": f"Produto '{prod['codigo']}' não aceita desconto."}
            lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
            if lim_err:
                conn.close()
                return {"success": False, "message": lim_err}
            p_venda = round(p_normal - desc + acr, 4)
            complemento = (req.complemento or "").strip()
            cur.execute(
                "INSERT INTO pedido_venda_prod "
                "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
                " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
                " hora_inclusao_item, cod_num_serie, comprimento, largura, area_venda, "
                " comprimento_chapa, largura_chapa) "
                "OUTPUT INSERTED.codauto "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE),"
                "        CONVERT(NVARCHAR(8), GETDATE(), 108),%s,%s,%s,%s,%s,%s)",
                (
                    pedido, prod["codigo"], qtd, p_venda, p_normal, desc, acr, prod["custo"], complemento,
                    prod["unidade"], cod_num_serie, comprimento, largura, area_venda, comprimento_chapa, largura_chapa,
                ),
            )
            row = cur.fetchone()
            codauto = int(row["codauto"] if isinstance(row, dict) else row[0])
            codautos.append(codauto)
            _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)

        # `prod["codigo"]`/componentes do kit nunca são TAXA_SERVICO_CODIGO
        # aqui — bloqueado mais acima.
        sincroniza_taxa_servico_apos_alteracao(cur, pedido)
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "codautos": codautos, "kit": bool(componentes),
            "clinica_split": clinica_split, "total": novo_total,
        }
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}


def _update_item_completo_sync(req: ItemSaveRequest, pedido: int, codauto: int) -> dict:
    """Como `itens_service._update_item_sync`, mas reconhece item m²
    (`comprimento`/`largura` já gravados na linha) e recalcula a área
    quando o atendente edita as dimensões/tipo de preço — a "Editar Item"
    genérica original nunca soube fazer isso, só reaproveitava o mesmo
    UPDATE de qtd/desconto/acréscimo de qualquer item. Item SEM dimensão
    (produto normal) segue exatamente o mesmo caminho de antes. Ver
    PENDENCIAS.md > "Transações" > "Pedido Geral — Metro Quadrado"."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        cur.execute(
            "SELECT produto, comprimento, largura FROM pedido_venda_prod WHERE codauto=%s AND pedido=%s",
            (codauto, pedido),
        )
        row_atual = cur.fetchone()
        if not row_atual:
            conn.close()
            return {"success": False, "message": "Item não encontrado."}
        produto_atual = (row_atual.get("produto") or "").strip().upper()
        era_item_m2 = row_atual.get("comprimento") is not None and row_atual.get("largura") is not None

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        if produto_atual == TAXA_SERVICO_CODIGO and qtd != 1:
            conn.close()
            return {"success": False, "message": "Taxa de Serviço deve ter sempre 1 unidade."}

        comprimento = largura = area_venda = comprimento_chapa = largura_chapa = None
        if era_item_m2:
            if req.tipo_preco_m2 is None or not req.comprimento or not req.largura:
                conn.close()
                return {"success": False, "message": "Informe o tipo de preço e as dimensões (comprimento/largura) para este produto."}
            tipo_m2 = next((t for t in TIPOS_PRECO_M2 if t[0] == req.tipo_preco_m2), None)
            if not tipo_m2:
                conn.close()
                return {"success": False, "message": "Tipo de preço inválido."}
            _, _, coluna_preco, coluna_area_minima = tipo_m2
            cur.execute(f"SELECT {coluna_preco} AS preco FROM pecas WHERE codigo_int=%s", (produto_atual,))
            preco_row = cur.fetchone()
            preco_tipo = float((preco_row.get("preco") if preco_row else None) or 0)
            if preco_tipo <= 0:
                conn.close()
                return {"success": False, "message": "Este tipo de preço não está cadastrado para o produto."}
            cur.execute("SELECT controla_num_serie FROM pecas WHERE codigo_int=%s", (produto_atual,))
            pcs_row = cur.fetchone()
            modo_arredondamento = 10 if (pcs_row and pcs_row.get("controla_num_serie")) else 5
            cfg_m2 = _config_m2(cur)
            comprimento = float(req.comprimento)
            largura = float(req.largura)
            comprimento_chapa = float(req.comprimento_chapa) if req.comprimento_chapa else comprimento
            largura_chapa = float(req.largura_chapa) if req.largura_chapa else largura
            area_venda = _area_preco(
                comprimento, largura, cfg_m2[coluna_area_minima], modo_arredondamento,
                comprimento_chapa, largura_chapa, cfg_m2["vidro_controla_cabeca_chapa"],
                cfg_m2["metro_quadrado_minima_metragem"],
            )
            p_normal = round(preco_tipo * area_venda, 4)
        else:
            p_normal = float(req.valor_unitario or 0)

        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
        if lim_err:
            conn.close()
            return {"success": False, "message": lim_err}
        p_venda = round(p_normal - desc + acr, 4)
        complemento = (req.complemento or "").strip()

        cur.execute(
            "UPDATE pedido_venda_prod SET "
            " qtd_pedida=%s, p_normal=%s, p_venda=%s, desconto=%s, acrescimo=%s, "
            " descricao_produto=%s, data_alteracao_item=CAST(GETDATE() AS DATE), "
            " comprimento=%s, largura=%s, area_venda=%s, comprimento_chapa=%s, largura_chapa=%s "
            "WHERE codauto=%s AND pedido=%s",
            (qtd, p_normal, p_venda, desc, acr, complemento, comprimento, largura, area_venda,
             comprimento_chapa, largura_chapa, codauto, pedido),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao atualizar item: {e}"}


def _fechar_pedido_completo_sync(req: FecharRequest, pedido: int) -> dict:
    """Igual à regra de Fechar do Pedido rápido (A->F + valida/ajusta forma
    de pagamento + baixa de estoque das peças — via `_fechar_pedido_itens`,
    compartilhado com `pedidos_service.py` pra não duplicar a lógica), mas
    checando a permissão própria da tela PEDIDO_COMP."""
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
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO_COMP", "SITUACAO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar o pedido."}
        erro = _fechar_pedido_itens(cur, pedido, float(ex.get("total") or 0), (ex.get("forma_pag") or "").strip())
        if erro:
            conn.close()
            return {"success": False, "message": erro}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pedido Fechado.", "situacao": "F"}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar: {e}"}


def _list_itens_completo_sync(servidor: str, banco: str, pedido: int) -> dict:
    """Reaproveita a listagem do Pedido Bar (`itens_service._list_itens_sync`,
    NÃO duplicada) e só enriquece o resultado com o número de série vinculado
    (`pedido_venda_prod.cod_num_serie` -> `pecas_num_serie.num_serie`), quando
    houver — campo extra que o Bar nunca lê/exibe, comportamento dele
    inalterado. Ver PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B:
    número de série"."""
    result = _list_itens_bar_shared(servidor, banco, pedido)
    if not result.get("success") or not result.get("items"):
        return result
    try:
        conn = _open_conn(servidor, banco)
    except Exception:
        return result  # falha ao enriquecer não deve derrubar a listagem em si
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT i.codauto, ns.num_serie FROM pedido_venda_prod i "
            "JOIN pecas_num_serie ns ON ns.codigo = i.cod_num_serie "
            "WHERE i.pedido = %s AND i.cod_num_serie IS NOT NULL",
            (pedido,),
        )
        por_codauto = {int(r["codauto"]): (r.get("num_serie") or "").strip() for r in cur.fetchall()}
        if por_codauto:
            for item in result["items"]:
                ns = por_codauto.get(item.get("codauto"))
                if ns:
                    item["num_serie"] = ns

        # Dimensão m² (Fase B — módulo Metro Quadrado, ver "Pedido Geral —
        # Metro Quadrado" em PENDENCIAS.md) — mesmo padrão de enriquecimento
        # do Nº de Série acima, sem duplicar a query base.
        cur.execute(
            "SELECT codauto, comprimento, largura, area_venda FROM pedido_venda_prod "
            "WHERE pedido=%s AND comprimento IS NOT NULL AND largura IS NOT NULL",
            (pedido,),
        )
        dimensoes = {
            int(r["codauto"]): {
                "comprimento": float(r.get("comprimento") or 0),
                "largura": float(r.get("largura") or 0),
                "area_venda": float(r.get("area_venda") or 0),
            }
            for r in cur.fetchall()
        }
        if dimensoes:
            for item in result["items"]:
                dim = dimensoes.get(item.get("codauto"))
                if dim:
                    item.update(dim)

        # Agendamento (Fase B — módulo Clínica, ver agenda_service.py): mesmo
        # padrão de enriquecimento acima, sem duplicar a query base.
        cur.execute(
            "SELECT ap.CODPEDIDO AS codauto, a.codagenda, a.data, a.hora_ini, a.situacao_atendimento, "
            "       a.funcionario, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS profissional "
            "FROM AGENDA_PEDIDO ap "
            "JOIN AGENDA a ON a.codagenda = ap.CODAGENDA "
            "JOIN funcionarios f ON f.codigo_int = a.funcionario "
            "JOIN pedido_venda_prod i ON i.codauto = ap.CODPEDIDO "
            "WHERE i.pedido = %s",
            (pedido,),
        )
        for r in cur.fetchall():
            data_v = r.get("data")
            hora_v = r.get("hora_ini")
            agendamento = {
                "codagenda": int(r["codagenda"]),
                "data": data_v.isoformat() if hasattr(data_v, "isoformat") else str(data_v),
                "hora_ini": hora_v.strftime("%H:%M") if hasattr(hora_v, "strftime") else str(hora_v)[:5],
                "profissional": (r.get("profissional") or "").strip(),
                # Código do funcionário (não só o nome) — usado pra levar o
                # usuário direto da tela do Pedido pra Agenda daquele
                # profissional/data, sem precisar resolver o nome de volta
                # pro código na tela seguinte (user-directed 2026-07-28).
                "funcionario": int(r["funcionario"]),
                "situacao": (r.get("situacao_atendimento") or "").strip(),
            }
            codauto = int(r["codauto"])
            for item in result["items"]:
                if item.get("codauto") == codauto:
                    item["agendamento"] = agendamento
                    break
        cur.close()
        conn.close()
        return result
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return result


async def get_pedido_completo(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_get_pedido_completo_sync, servidor, banco, pedido)


async def save_pedido_completo(req: PedidoCompletoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_pedido_completo_sync, req, pedido_codigo)


async def add_item_completo(req: ItemSaveRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_add_item_completo_sync, req, pedido)


async def update_item_completo(req: ItemSaveRequest, pedido: int, codauto: int) -> dict:
    return await asyncio.to_thread(_update_item_completo_sync, req, pedido, codauto)


async def list_itens_completo(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_list_itens_completo_sync, servidor, banco, pedido)


async def fechar_pedido_completo(req: FecharRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_fechar_pedido_completo_sync, req, pedido)


async def cancelar_pedido_completo(req: FecharRequest, pedido: int) -> dict:
    """Réplica de `Command9_Click`/`_cancelar_pedido_sync` do Pedido Bar —
    reaproveitada diretamente (não duplicada), só com `acao="SITUACAO"` pra
    preservar a permissão já concedida em instalações existentes (o Pedido
    Completo cancelava reaproveitando SITUACAO antes desta unificação,
    2026-07-20 — ver docstring de `pedidos_service._cancelar_pedido_sync`)."""
    return await _cancelar_pedido_bar_shared(req, pedido, "PEDIDO_COMP", "SITUACAO")


async def faturar_pedido_completo(req: FecharRequest, pedido: int) -> dict:
    """Réplica de `_faturar_pedido_sync` do Pedido Bar — mesma função,
    reaproveitada com `tela="PEDIDO_COMP"` (ver docstring lá pro detalhe da
    regra: gera Comanda, libera estoque reservado, marca PG, sem NFC-e).
    Pedido explícito do usuário, 2026-07-20. **Diferença confirmada pelo
    usuário no mesmo dia**: diferente do Pedido Bar, o Pedido Geral só pode
    faturar um pedido já Fechado — `exigir_fechado=True` bloqueia a
    transição direta A->PG que o Bar permite."""
    return await _faturar_pedido_bar_shared(req, pedido, "PEDIDO_COMP", exigir_fechado=True)


async def reabrir_pedido_completo(req: FecharRequest, pedido: int) -> dict:
    """Réplica de `_reabrir_pedido_sync` do Pedido Bar — mesma função,
    reaproveitada com `tela="PEDIDO_COMP"`."""
    return await _reabrir_pedido_bar_shared(req, pedido, "PEDIDO_COMP")


async def dividir_pedido_completo(req: DividirPedidoRequest, pedido: int) -> dict:
    """Réplica de `_dividir_pedido_sync` do Pedido Bar — mesma função,
    reaproveitada com `tela="PEDIDO_COMP"`, incluindo o reaproveitamento de
    `num_ped_cliente` pro rastreio do pedido-pai (ver docstring lá pra a
    ressalva sobre esse campo também ser o "Nº Pedido do Cliente" real do
    Pedido Geral)."""
    return await _dividir_pedido_bar_shared(req, pedido, "PEDIDO_COMP")


async def toggle_entregue_completo(req, pedido: int) -> dict:
    """Checkbox 'Pedido Entregue' — mesma função do Pedido Bar
    (`pedidos_service.toggle_entregue`), tela-agnóstica (não checa
    permissão própria hoje), reaproveitada sem alteração."""
    return await _toggle_entregue_bar_shared(req, pedido)

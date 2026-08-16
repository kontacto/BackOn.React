"""Inventário de Estoque (Transações > Inventário) — Fase 1: núcleo manual.
Legado: `FrmInvAbe.frm` (Abertura), `FrmInvDig.frm` (Digitação),
`Geral\\Inventario.bas::Fecha_Inventario`/`Cancela_Inventario`. Ver
PENDENCIAS.md > "Inventário" pro levantamento completo do ecossistema
(regras de negócio, tabelas confirmadas ao vivo em GERDELL/BARESTELA,
decisões de escopo) antes de mexer neste arquivo.

Decisões conscientes em relação ao `.frm`/`.bas` original:
  • Checkboxes "Revenda/Consumo/Imobilizado" da Abertura legada
    (`Check1`/`Check2`/`Check3` em `FrmInvAbe`) são código morto no VB6 —
    a variável `Vtipos` é recalculada a partir delas e IMEDIATAMENTE
    sobrescrita/descartada antes de entrar em qualquer branch G/C (ver
    `cmbok_Click`: `Vtipos = ""` logo depois do cálculo, ou
    `Vtipos = " (pecas.tipo_peca>=0) "` incondicional no branch C) — o
    filtro nunca teve efeito real na consulta. Não replicado (nem os
    checkboxes, nem um filtro equivalente) — ver "Não replicar truques
    VB6" no CLAUDE.md.
  • Bloco do `Check5` ("incluir código de fábrica" + export pra .mdb via
    Jet/PAF-ECF) — infraestrutura de arquivo local Access, sem
    equivalente nesta arquitetura web; mesmo escopo já declarado fora de
    alcance pra PAF-ECF em Produto Completo. Não portado.
  • Integração Tray disparada dentro do `Fecha_Inventario` legado
    (reagenda atualização de estoque no site) — não portada nesta
    rodada; Produto Completo já tem o mecanismo de sincronização Tray
    real, um gatilho a mais no Fechamento fica pra quando for pedido.
  • "Registro de Inventário" (item do menu legado) — código que o
    populava (`Vid_Rel_Inventario`) está inteiramente comentado no VB6
    atual (código morto). Não portado.
  • Ajuste de estoque no Fechamento para itens de `veiculos`: o legado
    insere a `Movimentacao` mas o trecho que atualizaria a tabela
    `veiculos` está comentado (`Tbv.Find`/`Tbv.Update`) — ou seja, pra
    itens de veículo o legado grava uma `Movimentacao` órfã sem nenhum
    efeito real. Não replicado — divergências de item de veículo entram
    no cálculo/exibição normalmente, mas não geram `movimentacao` nem
    tentam atualizar tabela nenhuma (não há o que atualizar).
  • `movimentacao.serie_nf` desta tela usa `'IV'` (Inventário) — mesma
    convenção de série própria por tela de origem já usada por
    `movimentacao_produtos_service.py` (`'MV'`) e Pedido Bar (`'CM'`).

Coluna nova (não existe no legado, pedido explícito do usuário
2026-07-23): `inventario.usuario_digitacao` (funcionarios.codigo_int) —
grava quem incluiu/alterou a contagem de cada item, pra permitir vários
usuários digitando o mesmo balanço em paralelo (cada um cobrindo um nível/
área diferente) saber quem contou o quê. Migração idempotente
(`_ensure_usuario_digitacao_col`), mesmo padrão de
`pedido_common._ensure_qtd_pessoas_col`. A tabela `inventario` já não tem
nenhuma outra coluna assim no legado (Abertura/Fechamento têm
`inventario_controle.usuario_*`, mas por ITEM contado não existia rastro
nenhum) — é a primeira coluna genuinamente nova deste módulo.
"""
import asyncio
from datetime import date, timedelta
from typing import Optional

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo


TIPOS_BALANCO = {"G": "Geral", "C": "Contábil", "P": "Parcial"}
TIPOS_PECA = {0: "Revenda", 1: "Consumo", 2: "Imobilizado"}


def _ensure_usuario_digitacao_col(cur) -> None:
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='usuario_digitacao' AND Object_ID=Object_ID('inventario')) "
        "ALTER TABLE inventario ADD usuario_digitacao INT NULL"
    )
    # `contado_em` (2026-07-23) — carimbo de quando o item foi de fato
    # contado por um humano (Incluir/Alterar), NULL até lá. Precisa ser uma
    # coluna própria, separada de `usuario_digitacao`: esta última pode
    # LEGITIMAMENTE ficar NULL num item já contado (o campo
    # `usuario_alteracao` do request é opcional — `models/schemas.py`), e
    # `estoque_balanco<>0` (critério original) só funciona pro tipo Geral,
    # onde a coluna nasce em 0 (DEFAULT do banco); no tipo Contábil a
    # Abertura já pré-carrega `estoque_balanco` = saldo do sistema
    # (não-zero) pra TODO item, então esse critério antigo marcava "já
    # contado" pra tudo, mesmo sem ninguém ter digitado nada — achado ao
    # vivo 2026-07-23 pelo usuário, num balanço Contábil recém-aberto
    # ("Total Digitados: 236 de 236" sem ter digitado nada). `contado_em
    # IS NOT NULL` é o único critério que funciona pros 2 tipos de balanço
    # E independe de sabermos quem contou.
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='contado_em' AND Object_ID=Object_ID('inventario')) "
        "ALTER TABLE inventario ADD contado_em DATETIME NULL"
    )
    # Backfill em execute() PRÓPRIO, separado do ALTER TABLE acima — o SQL
    # Server faz bind de nome de coluna em tempo de PARSE do batch inteiro,
    # então referenciar `contado_em` no mesmo batch do ALTER que a cria
    # falha com "Invalid column name" mesmo dentro de um IF/BEGIN/END
    # (achado ao vivo testando contra GERDELL/BARESTELA). Só pra não
    # "zerar" a contagem de um balanço que já tinha itens digitados antes
    # desta coluna existir — `usuario_digitacao IS NOT NULL` é sinal
    # inequívoco de uma digitação real (só Incluir/Alterar grava ali, nunca
    # a Abertura). Autolimitante: assim que 1 linha ganha `contado_em`, o
    # `NOT EXISTS` abaixo já para de rodar o UPDATE nas próximas chamadas.
    # Linhas digitadas com `usuario_alteracao` ausente (campo opcional) e
    # ainda sem `contado_em` ficam de fora do backfill — não tem como
    # distinguir retroativamente "pré-carregado pela Abertura Contábil" de
    # "digitado sem usuário conhecido"; subcontar é bem menos confuso do
    # que o bug original (supercontar).
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM inventario WHERE contado_em IS NOT NULL) "
        "UPDATE inventario SET contado_em=GETDATE() WHERE usuario_digitacao IS NOT NULL"
    )


def _row_to_dict(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def _controle_sync(cur) -> dict:
    cur.execute("SELECT TOP 1 data_balanco, situacao_balanco, tipo_balanco FROM controle")
    row = cur.fetchone() or {}
    return {
        "data_balanco": row.get("data_balanco"),
        "situacao_balanco": (row.get("situacao_balanco") or "").strip(),
        "tipo_balanco": (row.get("tipo_balanco") or "").strip(),
    }


def _status_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_usuario_digitacao_col(cur)
        ctrl = _controle_sync(cur)
        total_itens = 0
        itens_digitados = 0
        if ctrl["situacao_balanco"] == "A":
            cur.execute("SELECT COUNT(*) AS c FROM inventario")
            total_itens = int((cur.fetchone() or {}).get("c") or 0)
            # `contado_em IS NOT NULL` — ver nota em `_ensure_usuario_digitacao_col`.
            cur.execute("SELECT COUNT(*) AS c FROM inventario WHERE contado_em IS NOT NULL")
            itens_digitados = int((cur.fetchone() or {}).get("c") or 0)
        cur.close()
        return {
            "success": True,
            "aberto": ctrl["situacao_balanco"] == "A",
            "situacao_balanco": ctrl["situacao_balanco"],
            "tipo_balanco": ctrl["tipo_balanco"],
            "tipo_balanco_descricao": TIPOS_BALANCO.get(ctrl["tipo_balanco"], ctrl["tipo_balanco"]),
            "data_balanco": ctrl["data_balanco"].isoformat() if ctrl["data_balanco"] else None,
            "total_itens": total_itens,
            "itens_digitados": itens_digitados,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _upsert_inventario_controle_abertura_sync(cur, data: str, usuario: Optional[int], tipo: str) -> None:
    cur.execute("SELECT TOP 1 1 AS ok FROM inventario_controle WHERE data=%s", (data,))
    if cur.fetchone():
        cur.execute(
            "UPDATE inventario_controle SET reabertura=GETDATE(), hora_reabertura=CONVERT(varchar(8),GETDATE(),108), "
            "usuario_reabertura=%s, tipo_balanco=%s WHERE data=%s",
            (usuario, tipo, data),
        )
    else:
        cur.execute(
            "INSERT INTO inventario_controle (data, abertura, hora_abertura, usuario_abertura, tipo_balanco) "
            "VALUES (%s, GETDATE(), CONVERT(varchar(8),GETDATE(),108), %s, %s)",
            (data, usuario, tipo),
        )


def _abrir_sync(servidor: str, banco: str, data: str, tipo: str, usuario: Optional[int]) -> dict:
    tipo = (tipo or "").strip().upper()
    if tipo not in TIPOS_BALANCO:
        return {"success": False, "message": "Selecione o tipo de balanço (Geral, Contábil ou Parcial)."}
    if not data:
        return {"success": False, "message": "Informe a data do balanço."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        ctrl = _controle_sync(cur)
        if ctrl["situacao_balanco"] == "A":
            data_fmt = ctrl["data_balanco"].strftime("%d/%m/%Y") if ctrl["data_balanco"] else "?"
            return {
                "success": False,
                "message": f"O Inventário do dia {data_fmt} está em aberto. Feche ou cancele o inventário atual antes de abrir outro.",
            }

        # Arquiva o balanço corrente (se sobrou algo de um Cancelamento
        # anterior) e limpa a tabela "corrente" antes de popular de novo —
        # mesmo padrão do legado (INSERT INTO inventario_old SELECT * FROM
        # inventario; DELETE FROM inventario).
        cur.execute(
            "INSERT INTO inventario_old (data, codigo_interno, preco_custo, preco_venda, custo_inventario, "
            "custo_reposicao, estoque_atual, custo_medio, estoque_balanco, reservado, reservado_os, "
            "estoque_cli, estoque_for) "
            "SELECT data, codigo_interno, preco_custo, preco_venda, custo_inventario, custo_reposicao, "
            "estoque_atual, custo_medio, estoque_balanco, reservado, reservado_os, estoque_cli, estoque_for "
            "FROM inventario"
        )
        cur.execute("DELETE FROM inventario")

        if tipo == "G":
            # Geral: pré-carrega o estoque atual inteiro (revenda+consumo+
            # imobilizado, sem filtro — ver nota de topo do arquivo sobre os
            # checkboxes serem código morto no legado). Itens não digitados
            # de novo permanecem com o valor do snapshot inicial.
            cur.execute(
                "INSERT INTO inventario (codigo_interno, preco_custo, preco_venda, custo_inventario, "
                "custo_reposicao, estoque_atual, reservado, reservado_os, estoque_cli, estoque_for, data) "
                "SELECT DISTINCT codigo_int, CAST(p_custo AS numeric(15,3)), CAST(p_venda AS numeric(15,3)), "
                "CAST(custo_inventario AS numeric(15,3)), CAST(custo_reposicao AS numeric(15,3)), qtd, "
                "reservado, reservado_os, estoque_cli, estoque_for, %s "
                "FROM pecas WHERE (qtd<>0 OR reservado<>0 OR reservado_os<>0 OR estoque_cli>0 OR estoque_for>0)",
                (data,),
            )
            cur.execute(
                "INSERT INTO inventario (codigo_interno, preco_custo, preco_venda, custo_inventario, "
                "custo_reposicao, estoque_atual, reservado, reservado_os, estoque_cli, estoque_for, data) "
                "SELECT DISTINCT codigo_int, CAST(val_custo AS numeric(15,2)), CAST(preco_venda AS numeric(15,2)), "
                "CAST(custo_inventario AS numeric(15,2)), CAST(custo_reposicao AS numeric(15,2)), 1, 0, 0, "
                "estoque_cli, estoque_for, %s "
                "FROM veiculos WHERE nf_compra<>0 AND nf_venda=0",
                (data,),
            )
        elif tipo == "C":
            # Contábil: pré-carrega estoque_atual/estoque_balanco JÁ IGUAIS
            # (soma qtd+reservado+reservado_os) — não é uma contagem física
            # item a item, é o saldo do sistema assumido como "conferido"
            # até que a Digitação sobrescreva algum item manualmente.
            # Fechamento NUNCA ajusta estoque nesse tipo (ver `_fechar_sync`,
            # `tipo_balanco != "C"`) — puramente informativo/de conferência.
            cur.execute(
                "INSERT INTO inventario (codigo_interno, preco_custo, preco_venda, custo_inventario, "
                "custo_reposicao, estoque_atual, reservado, reservado_os, estoque_cli, estoque_for, "
                "estoque_balanco, data) "
                "SELECT DISTINCT codigo_int, CAST(p_custo AS numeric(15,3)), CAST(p_venda AS numeric(15,3)), "
                "CAST(custo_inventario AS numeric(15,3)), CAST(custo_reposicao AS numeric(15,3)), "
                "CAST((qtd+reservado+reservado_os) AS numeric(15,3)), 0, 0, estoque_cli, estoque_for, "
                "CAST((qtd+reservado+reservado_os) AS numeric(15,3)), %s "
                "FROM pecas WHERE (qtd+reservado+reservado_os)>0 OR estoque_cli>0 OR estoque_for>0",
                (data,),
            )
            cur.execute(
                "INSERT INTO inventario (codigo_interno, preco_custo, preco_venda, custo_inventario, "
                "custo_reposicao, estoque_atual, reservado, reservado_os, estoque_cli, estoque_for, "
                "estoque_balanco, data) "
                "SELECT DISTINCT codigo_int, val_custo, preco_venda, custo_inventario, custo_reposicao, "
                "1, 0, 0, estoque_cli, estoque_for, 1, %s "
                "FROM veiculos WHERE nf_compra<>0 AND nf_venda=0",
                (data,),
            )
            cur.execute("UPDATE inventario SET estoque_balanco=0 WHERE estoque_balanco<0")
            cur.execute("UPDATE inventario SET estoque_atual=0 WHERE estoque_atual<0")
        # tipo == "P" (Parcial, 2026-07-23, user-directed — "o mais
        # importante"): NÃO pré-carrega nada — `inventario` fica vazio até a
        # Digitação de Estoque incluir item por item (mesmo padrão já
        # documentado como possibilidade no levantamento original desta
        # tela, regra 4: "se o combo tiver uma 3ª opção... a abertura não
        # insere NADA em inventario — os itens só entram por Inclui um a
        # um"). Efeito prático no Fechamento: como `_fechar_sync` faz
        # `INNER JOIN pecas` contra `inventario`, só os itens que TÊM linha
        # (ou seja, que foram digitados) entram no ajuste de estoque — um
        # item nunca contado simplesmente não aparece na query, não é
        # zerado nem alterado de forma nenhuma. Diferente do Geral, que
        # pré-carrega TODO o estoque e por isso "zera" (ajusta pra baixo) o
        # que não foi recontado — no Parcial o usuário só precisa contar o
        # que quer conferir, o resto do estoque não é tocado.

        _upsert_inventario_controle_abertura_sync(cur, data, usuario, tipo)
        cur.execute(
            "UPDATE controle SET data_balanco=%s, situacao_balanco='A', tipo_balanco=%s",
            (data, tipo),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": f"Inventário {TIPOS_BALANCO[tipo]} aberto para {data}."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _buscar_produto_pecas_sync(cur, termo: str) -> Optional[dict]:
    for coluna in ("codigo_int", "codigo_fab", "codigo_bar"):
        cur.execute(
            f"SELECT codigo_int, descricao, qtd, p_custo, p_venda, custo_inventario, custo_reposicao "
            f"FROM pecas WHERE {coluna}=%s",
            (termo,),
        )
        r = cur.fetchone()
        if r:
            return {
                "origem": "pecas",
                "codigo_interno": (r.get("codigo_int") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "estoque_atual": float(r.get("qtd") or 0),
                "preco_custo": float(r.get("p_custo") or 0),
                "preco_venda": float(r.get("p_venda") or 0),
                "custo_inventario": float(r.get("custo_inventario") or 0),
                "custo_reposicao": float(r.get("custo_reposicao") or 0),
            }
    return None


def _buscar_produto_veiculos_sync(cur, termo: str) -> Optional[dict]:
    for coluna in ("chassi", "codigo_int"):
        cur.execute(
            f"SELECT codigo_int, chassi, descricao, val_custo, preco_venda, custo_inventario, custo_reposicao "
            f"FROM veiculos WHERE {coluna}=%s",
            (termo,),
        )
        r = cur.fetchone()
        if r:
            return {
                "origem": "veiculos",
                "codigo_interno": (r.get("codigo_int") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "estoque_atual": 0.0,
                "preco_custo": float(r.get("val_custo") or 0),
                "preco_venda": float(r.get("preco_venda") or 0),
                "custo_inventario": float(r.get("custo_inventario") or 0),
                "custo_reposicao": float(r.get("custo_reposicao") or 0),
            }
    return None


def _buscar_item_sync(servidor: str, banco: str, termo: str) -> dict:
    termo = (termo or "").strip()
    if not termo:
        return {"success": True, "found": False}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "found": False}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_usuario_digitacao_col(cur)
        ctrl = _controle_sync(cur)
        if ctrl["situacao_balanco"] != "A":
            return {"success": False, "message": "Não existe Inventário em aberto.", "found": False}

        produto = _buscar_produto_pecas_sync(cur, termo) or _buscar_produto_veiculos_sync(cur, termo)
        if not produto:
            cur.close()
            return {"success": True, "found": False}

        cur.execute(
            "SELECT preco_custo, preco_venda, custo_inventario, custo_reposicao, estoque_balanco, contado_em "
            "FROM inventario WHERE codigo_interno=%s AND data=%s",
            (produto["codigo_interno"], ctrl["data_balanco"]),
        )
        linha_inventario = cur.fetchone()
        cur.close()
        if linha_inventario:
            produto["preco_custo"] = float(linha_inventario.get("preco_custo") or 0)
            produto["preco_venda"] = float(linha_inventario.get("preco_venda") or 0)
            produto["custo_inventario"] = float(linha_inventario.get("custo_inventario") or 0)
            produto["custo_reposicao"] = float(linha_inventario.get("custo_reposicao") or 0)
            # "Já contado" é `contado_em IS NOT NULL` — ver nota em
            # `_ensure_usuario_digitacao_col` pro histórico completo do
            # porquê (critério antigo, `estoque_balanco<>0`, quebrava tanto
            # pro tipo Contábil quanto pro caso "usuário contou 0 de
            # propósito").
            produto["ja_contado"] = linha_inventario.get("contado_em") is not None
            produto["estoque_balanco_atual"] = float(linha_inventario.get("estoque_balanco") or 0)
        else:
            produto["ja_contado"] = False
            produto["estoque_balanco_atual"] = 0.0
        produto["success"] = True
        produto["found"] = True
        return produto
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "found": False}
    finally:
        conn.close()


def _gravar_item_sync(servidor: str, banco: str, dados: dict, somar: bool, usuario: Optional[int] = None) -> dict:
    codigo = (dados.get("codigo") or "").strip()
    qtd = dados.get("qtd")
    if not codigo:
        return {"success": False, "message": "Informe o produto."}
    if qtd is None:
        return {"success": False, "message": "Informe a quantidade contada."}
    try:
        qtd = float(qtd)
    except (TypeError, ValueError):
        return {"success": False, "message": "Quantidade inválida."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_usuario_digitacao_col(cur)
        ctrl = _controle_sync(cur)
        if ctrl["situacao_balanco"] != "A":
            return {"success": False, "message": "Não existe Inventário em aberto."}

        produto = _buscar_produto_pecas_sync(cur, codigo) or _buscar_produto_veiculos_sync(cur, codigo)
        if not produto:
            return {"success": False, "message": "Este item não está cadastrado."}

        preco_custo = dados.get("preco_custo")
        preco_venda = dados.get("preco_venda")
        custo_inventario = dados.get("custo_inventario")
        custo_reposicao = dados.get("custo_reposicao")
        preco_custo = float(preco_custo) if preco_custo is not None else produto["preco_custo"]
        preco_venda = float(preco_venda) if preco_venda is not None else produto["preco_venda"]
        custo_inventario = float(custo_inventario) if custo_inventario is not None else produto["custo_inventario"]
        custo_reposicao = float(custo_reposicao) if custo_reposicao is not None else produto["custo_reposicao"]

        cur.execute(
            "SELECT estoque_balanco FROM inventario WHERE codigo_interno=%s AND data=%s",
            (produto["codigo_interno"], ctrl["data_balanco"]),
        )
        existente = cur.fetchone()

        if not existente:
            if not somar:
                return {"success": False, "message": "Este item não se encontra cadastrado em Inventário."}
            cur.execute(
                "INSERT INTO inventario (codigo_interno, data, preco_custo, preco_venda, custo_inventario, "
                "custo_reposicao, estoque_atual, estoque_balanco, reservado, reservado_os, usuario_digitacao, "
                "contado_em) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 0, %s, GETDATE())",
                (
                    produto["codigo_interno"], ctrl["data_balanco"], preco_custo, preco_venda,
                    custo_inventario, custo_reposicao, produto["estoque_atual"], qtd, usuario,
                ),
            )
            novo_balanco = qtd
        else:
            balanco_atual = float(existente.get("estoque_balanco") or 0)
            novo_balanco = (balanco_atual + qtd) if somar else qtd
            cur.execute(
                "UPDATE inventario SET preco_custo=%s, preco_venda=%s, custo_inventario=%s, "
                "custo_reposicao=%s, estoque_balanco=%s, usuario_digitacao=%s, contado_em=GETDATE() "
                "WHERE codigo_interno=%s AND data=%s",
                (
                    preco_custo, preco_venda, custo_inventario, custo_reposicao, novo_balanco, usuario,
                    produto["codigo_interno"], ctrl["data_balanco"],
                ),
            )

        conn.commit()
        cur.close()
        return {
            "success": True,
            "message": "Item gravado no inventário.",
            "codigo_interno": produto["codigo_interno"],
            "estoque_balanco": novo_balanco,
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _relatorio_contagem_sync(
    servidor: str, banco: str, tipos: Optional[list] = None, somente_ativos: bool = False,
    niveis: Optional[list] = None,
) -> dict:
    """Relatório de Contagem (Fase 2, 2026-07-23, user-directed) — lista em
    branco (sem quantidade) pro conferente escrever a contagem física no
    papel; o digitador depois passa pro sistema via Digitação de Estoque.
    Não depende de balanço aberto nem do que já está em `inventario` —
    lista direto de `pecas`+`veiculos`, mesma fonte que `Fecha_Inventario`
    usaria pra popular um balanço Geral.

    `tipos`: lista de `pecas.tipo_peca` a incluir (0=Revenda, 1=Consumo,
    2=Imobilizado) — vazio/None inclui todos os 3.

    `niveis`: lista de até 5 posições (`[nivel1, nivel2, nivel3, nivel4,
    nivel5]`, qualquer sufixo pode faltar/vir vazio) — a cascata de Nível é
    à ESCOLHA do usuário, mesmo padrão dos seletores em cascata
    List(0)..List(4) do legado (`FrmRelInvCon.frm`): cada posição
    preenchida filtra exatamente aquele nível; deixar uma posição vazia
    (ou a lista inteira vazia) não filtra por nível nenhum ("TODOS", igual
    ao legado). O agrupamento na resposta (`grupo`) continua sempre por
    Nível 1 (a descrição do nó raiz) independente de quão fundo o filtro
    desceu — só MUDA quais itens aparecem dentro de cada grupo."""
    tipos = tipos if tipos else [0, 1, 2]
    niveis = niveis or []
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "itens": []}
    try:
        cur = conn.cursor(as_dict=True)
        placeholders = ",".join(["%s"] * len(tipos))
        situacao_sql = " AND situacao='A'" if somente_ativos else ""
        nivel_sql = ""
        nivel_params: list = []
        for idx, valor in enumerate(niveis[:5], start=1):
            if valor:
                nivel_sql += f" AND nivel{idx}=%s"
                nivel_params.append(valor)
        cur.execute(
            "SELECT codigo_int AS codigo_interno, descricao, "
            "COALESCE(NULLIF(nivel1,''), '') AS nivel1 "
            f"FROM pecas WHERE tipo_peca IN ({placeholders}){situacao_sql}{nivel_sql} "
            "UNION ALL "
            "SELECT codigo_int AS codigo_interno, descricao, "
            "COALESCE(NULLIF(nivel1,''), '') AS nivel1 "
            f"FROM veiculos WHERE tipo_peca IN ({placeholders}){situacao_sql}{nivel_sql}",
            tuple(tipos) + tuple(nivel_params) + tuple(tipos) + tuple(nivel_params),
        )
        linhas = cur.fetchall()

        niveis1 = {row.get("nivel1") for row in linhas if row.get("nivel1")}
        descr_por_nivel1: dict = {}
        if niveis1:
            ph2 = ",".join(["%s"] * len(niveis1))
            cur.execute(
                f"SELECT nivel1, descr FROM niveis WHERE nivel1 IN ({ph2}) "
                "AND (nivel2='' OR nivel2 IS NULL)",
                tuple(niveis1),
            )
            for row in cur.fetchall():
                descr_por_nivel1[row.get("nivel1")] = (row.get("descr") or "").strip()
        cur.close()

        itens = []
        for row in linhas:
            nivel1 = row.get("nivel1") or ""
            itens.append({
                "codigo_interno": (row.get("codigo_interno") or "").strip(),
                "descricao": (row.get("descricao") or "").strip(),
                "grupo": descr_por_nivel1.get(nivel1) or (f"Nível {nivel1}" if nivel1 else "Sem Nível"),
            })
        itens.sort(key=lambda it: (it["grupo"], it["descricao"]))
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


def _niveis_where_sql(niveis: Optional[list], alias: str = "") -> tuple:
    """Mesmo filtro em cascata Nível 1-5 usado em `_relatorio_contagem_sync`
    (posição vazia = "TODOS", sem filtrar aquele nível) — extraído aqui pra
    reaproveitar nos 4 relatórios de Fase 2 abaixo, todos com a mesma
    cascata (`List(0)..List(4)` no legado)."""
    prefix = f"{alias}." if alias else ""
    where_sql = ""
    params: list = []
    for idx, valor in enumerate((niveis or [])[:5], start=1):
        if valor:
            where_sql += f" AND {prefix}nivel{idx}=%s"
            params.append(valor)
    return where_sql, params


def _descr_por_nivel1_sync(cur, valores: set) -> dict:
    if not valores:
        return {}
    ph = ",".join(["%s"] * len(valores))
    cur.execute(
        f"SELECT nivel1, descr FROM niveis WHERE nivel1 IN ({ph}) AND (nivel2='' OR nivel2 IS NULL)",
        tuple(valores),
    )
    return {r.get("nivel1"): (r.get("descr") or "").strip() for r in cur.fetchall()}


def _grupo_nome(nivel1: str, descr_por_nivel1: dict) -> str:
    return descr_por_nivel1.get(nivel1) or (f"Nível {nivel1}" if nivel1 else "Sem Nível")


def _resolve_balanco_tabela_sync(cur, data: Optional[str]) -> tuple:
    """Relatórios de Fase 2 (Crítica/Resultado/Divergência) podem consultar
    um balanço diferente do corrente, mesma ideia do `DataDif`/`DataBal` do
    legado (`FrmRelInv`/`FrmRelInvDiv`): sem `data` informado (ou igual à
    corrente), lê de `inventario` (`controle.data_balanco`); com `data`
    diferente, lê de `inventario_old` (histórico de balanços já fechados).
    Conferência nunca usa isto — sempre a data corrente (ver trace VB6)."""
    ctrl = _controle_sync(cur)
    atual = ctrl["data_balanco"]
    atual_iso = atual.isoformat() if atual else None
    if data and str(data) != atual_iso:
        return "inventario_old", data
    return "inventario", atual_iso


def _arred2(v) -> float:
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _trunca2(v) -> float:
    from decimal import ROUND_DOWN, Decimal
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def _relatorio_conferencia_sync(
    servidor: str, banco: str, tipos: Optional[list] = None, listar_zerados: bool = False,
    niveis: Optional[list] = None,
) -> dict:
    """Relatório de Conferência (Fase 2) — lista `codigo_interno`/
    `descricao`/`estoque_balanco` do balanço CORRENTE (nunca de
    `inventario_old` — o legado (`FrmRelInvConf`) não permite escolher
    outra data pra este relatório em especial), separado por
    Revenda/Consumo/Imobilizado (`tipos`, 3 listas independentes — nunca
    somadas entre si, mesmo comportamento das 3 abas fixas do
    `FrmRelInvConf` legado) e agrupado por Nível 1 dentro de cada tipo. Sem
    filtro de "somente ativos" (o legado não tem essa opção aqui, diferente
    do Relatório de Contagem)."""
    tipos = tipos if tipos else [0, 1, 2]
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "itens": []}
    try:
        cur = conn.cursor(as_dict=True)
        ctrl = _controle_sync(cur)
        if not ctrl["data_balanco"]:
            return {"success": True, "itens": []}
        nivel_sql, nivel_params = _niveis_where_sql(niveis)
        zerado_sql = "" if listar_zerados else " AND i.estoque_balanco<>0"
        itens: list = []
        for tipo in tipos:
            cur.execute(
                "SELECT i.codigo_interno, p.descricao, i.estoque_balanco, "
                "COALESCE(NULLIF(p.nivel1,''),'') AS nivel1 "
                "FROM inventario i INNER JOIN pecas p ON p.codigo_int = i.codigo_interno "
                f"WHERE p.tipo_peca=%s AND i.data=%s{nivel_sql}{zerado_sql} "
                "UNION ALL "
                "SELECT i.codigo_interno, v.descricao, i.estoque_balanco, "
                "COALESCE(NULLIF(v.nivel1,''),'') AS nivel1 "
                "FROM inventario i INNER JOIN veiculos v ON v.codigo_int = i.codigo_interno "
                f"WHERE v.tipo_peca=%s AND i.data=%s{nivel_sql}{zerado_sql}",
                (tipo, ctrl["data_balanco"]) + tuple(nivel_params) +
                (tipo, ctrl["data_balanco"]) + tuple(nivel_params),
            )
            linhas = cur.fetchall()
            descr_por_nivel1 = _descr_por_nivel1_sync(cur, {r.get("nivel1") for r in linhas if r.get("nivel1")})
            for row in linhas:
                itens.append({
                    "tipo_peca": tipo,
                    "tipo_descricao": TIPOS_PECA.get(tipo, str(tipo)),
                    "codigo_interno": (row.get("codigo_interno") or "").strip(),
                    "descricao": (row.get("descricao") or "").strip(),
                    "estoque_balanco": float(row.get("estoque_balanco") or 0),
                    "grupo": _grupo_nome(row.get("nivel1") or "", descr_por_nivel1),
                })
        cur.close()
        itens.sort(key=lambda it: (it["tipo_descricao"], it["grupo"], it["descricao"]))
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


def _relatorio_critica_sync(
    servidor: str, banco: str, niveis: Optional[list] = None, data: Optional[str] = None,
) -> dict:
    """Relatório de Crítica (Fase 2) — só itens DIVERGENTES (`estoque_balanco
    <> estoque_atual+reservado`) e REALMENTE CONTADOS (`contado_em IS NOT
    NULL`), com uma coluna de "Recontagem" em branco pro conferente anotar
    à mão (mesmo padrão do `FrmRelInvCrit` legado, que propositalmente
    esconde a quantidade "esperada" do sistema pra forçar uma recontagem
    cega — aqui o valor do sistema também é devolvido em `estoque_sistema`,
    mas a tela decide se mostra ou não). Suporta consultar um balanço
    fechado antigo via `data` (ver `_resolve_balanco_tabela_sync`).

    O filtro `contado_em IS NOT NULL` só é aplicado quando lendo o balanço
    CORRENTE (`inventario` — a única tabela que tem essa coluna;
    `inventario_old` não guarda isso, então um balanço histórico continua
    sem essa distinção). Achado ao vivo 2026-07-23: sem esse filtro, TODO
    item de um balanço Geral recém-aberto (ou parcialmente digitado) com
    `estoque_atual<>0` aparecia como "divergente" só por ainda não ter sido
    contado (`estoque_balanco` continua no default 0 até alguém digitar) —
    mesma causa raiz do bug já corrigido no contador "Total Digitados",
    aqui vazando pro relatório de Crítica."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "itens": []}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_usuario_digitacao_col(cur)
        tabela, data_resolvida = _resolve_balanco_tabela_sync(cur, data)
        if not data_resolvida:
            return {"success": True, "itens": []}
        nivel_sql, nivel_params = _niveis_where_sql(niveis)
        contado_sql = " AND i.contado_em IS NOT NULL" if tabela == "inventario" else ""
        cur.execute(
            f"SELECT i.codigo_interno, p.descricao, i.estoque_balanco, "
            "(i.estoque_atual+i.reservado) AS estoque_sistema, "
            "COALESCE(NULLIF(p.nivel1,''),'') AS nivel1 "
            f"FROM {tabela} i INNER JOIN pecas p ON p.codigo_int = i.codigo_interno "
            f"WHERE i.estoque_balanco<>(i.estoque_atual+i.reservado){contado_sql} AND i.data=%s{nivel_sql} "
            "UNION ALL "
            "SELECT i.codigo_interno, v.descricao, i.estoque_balanco, "
            "(i.estoque_atual+i.reservado) AS estoque_sistema, "
            "COALESCE(NULLIF(v.nivel1,''),'') AS nivel1 "
            f"FROM {tabela} i INNER JOIN veiculos v ON v.codigo_int = i.codigo_interno "
            f"WHERE i.estoque_balanco<>(i.estoque_atual+i.reservado){contado_sql} AND i.data=%s{nivel_sql}",
            (data_resolvida,) + tuple(nivel_params) + (data_resolvida,) + tuple(nivel_params),
        )
        linhas = cur.fetchall()
        descr_por_nivel1 = _descr_por_nivel1_sync(cur, {r.get("nivel1") for r in linhas if r.get("nivel1")})
        cur.close()
        itens = [{
            "codigo_interno": (row.get("codigo_interno") or "").strip(),
            "descricao": (row.get("descricao") or "").strip(),
            "estoque_balanco": float(row.get("estoque_balanco") or 0),
            "estoque_sistema": float(row.get("estoque_sistema") or 0),
            "grupo": _grupo_nome(row.get("nivel1") or "", descr_por_nivel1),
        } for row in linhas]
        itens.sort(key=lambda it: (it["grupo"], it["descricao"]))
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


def _relatorio_resultado_sync(
    servidor: str, banco: str, niveis: Optional[list] = None, data: Optional[str] = None,
    fonte_estoque: str = "inventario",
) -> dict:
    """Relatório de Resultado (Fase 2) — valoriza o estoque contado nos 3
    preços/custos CONGELADOS no momento do balanço (`inventario.preco_venda`
    /`custo_inventario`/`custo_reposicao` — não o preço/custo atual de
    `pecas`, ver achado do rastreio VB6). `fonte_estoque="fornecedor"`
    reproduz a opção "Estoque Fornecedor" do legado (`FrmRelInvRes`) — troca
    a quantidade usada (só do lado `pecas`; o lado `veiculos` sempre usa
    `estoque_balanco+reservado_os`, mesmo comportamento do legado, que nunca
    aplicava essa opção a veículos). Cálculo replica a assimetria real do
    legado: preço unitário ARREDONDADO primeiro, total = quantidade × esse
    unitário já arredondado, TRUNCADO em seguida (não os dois arredondados
    nem os dois truncados)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "itens": []}
    try:
        cur = conn.cursor(as_dict=True)
        tabela, data_resolvida = _resolve_balanco_tabela_sync(cur, data)
        if not data_resolvida:
            return {"success": True, "itens": []}
        nivel_sql, nivel_params = _niveis_where_sql(niveis)
        estoque_pecas_sql = (
            "(i.estoque_for)" if fonte_estoque == "fornecedor"
            else "(i.estoque_balanco+i.reservado_os+i.estoque_cli-i.estoque_for)"
        )
        cur.execute(
            f"SELECT i.codigo_interno, p.descricao, {estoque_pecas_sql} AS estoque, "
            "i.preco_venda, i.custo_inventario, i.custo_reposicao, "
            "COALESCE(NULLIF(p.nivel1,''),'') AS nivel1 "
            f"FROM {tabela} i INNER JOIN pecas p ON p.codigo_int = i.codigo_interno "
            f"WHERE {estoque_pecas_sql}>0 AND i.data=%s{nivel_sql} "
            "UNION ALL "
            "SELECT i.codigo_interno, v.descricao, (i.estoque_balanco+i.reservado_os) AS estoque, "
            "i.preco_venda, i.custo_inventario, i.custo_reposicao, "
            "COALESCE(NULLIF(v.nivel1,''),'') AS nivel1 "
            f"FROM {tabela} i INNER JOIN veiculos v ON v.codigo_int = i.codigo_interno "
            f"WHERE (i.estoque_balanco+i.reservado_os)<>0 AND i.data=%s{nivel_sql}",
            (data_resolvida,) + tuple(nivel_params) + (data_resolvida,) + tuple(nivel_params),
        )
        linhas = cur.fetchall()
        descr_por_nivel1 = _descr_por_nivel1_sync(cur, {r.get("nivel1") for r in linhas if r.get("nivel1")})
        cur.close()
        itens = []
        for row in linhas:
            estoque = float(row.get("estoque") or 0)
            pu_venda = _arred2(row.get("preco_venda") or 0)
            pu_custo_inv = _arred2(row.get("custo_inventario") or 0)
            pu_custo_rep = _arred2(row.get("custo_reposicao") or 0)
            itens.append({
                "codigo_interno": (row.get("codigo_interno") or "").strip(),
                "descricao": (row.get("descricao") or "").strip(),
                "estoque": estoque,
                "preco_unit_venda": pu_venda,
                "preco_unit_custo_inventario": pu_custo_inv,
                "preco_unit_custo_reposicao": pu_custo_rep,
                "total_venda": _trunca2(estoque * pu_venda),
                "total_custo_inventario": _trunca2(estoque * pu_custo_inv),
                "total_custo_reposicao": _trunca2(estoque * pu_custo_rep),
                "grupo": _grupo_nome(row.get("nivel1") or "", descr_por_nivel1),
            })
        itens.sort(key=lambda it: (it["grupo"], it["descricao"]))
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


_DIVERGENCIA_PRECO_COL = {
    "venda": "preco_venda", "custo_inventario": "custo_inventario", "custo_reposicao": "custo_reposicao",
}
_DIVERGENCIA_ORDEM = {
    "codigo": "codigo_interno", "descricao": "descricao", "diferenca": "diferenca",
    "preco_unitario": "preco_unitario", "preco_total": "preco_total",
}


def _relatorio_divergencia_sync(
    servidor: str, banco: str, niveis: Optional[list] = None, data: Optional[str] = None,
    preco: str = "venda", ordenar: str = "codigo",
) -> dict:
    """Relatório de Divergência (Fase 2) — a mesma condição de divergência
    de Crítica (`estoque_balanco <> estoque_atual+reservado`), mas mostrando
    os dois valores lado a lado e valorizados (1 dos 3 preços/custos
    congelados no balanço, à escolha). Corrige um bug real do legado
    (`FrmRelInvDiv`): o lado `veiculos` do UNION usava uma variável `um`
    nunca declarada/atribuída em nenhum lugar do projeto — SQL malformado,
    quebrava a query sempre que existisse algum veículo no filtro. Aqui o
    lado `veiculos` usa a mesma fórmula do lado `pecas`
    (`estoque_atual+reservado`), que é claramente a intenção original (ver
    PENDENCIAS.md > Inventário pro detalhe do achado).

    Só considera DIVERGENTE um item REALMENTE CONTADO (`contado_em IS NOT
    NULL`, e só quando lendo o balanço corrente — `inventario_old` não tem
    essa coluna). Achado ao vivo 2026-07-23: sem esse filtro, um balanço
    Geral recém-aberto (0 itens digitados) já mostrava vários itens como
    "divergentes" só porque `estoque_balanco` ainda estava no default 0
    (não digitado) enquanto `estoque_atual` tinha saldo real — mesma causa
    raiz do bug já corrigido no contador "Total Digitados" (ver
    `_ensure_usuario_digitacao_col`), aqui vazando pro relatório/pro badge
    de prévia de divergência do Painel (mesmo endpoint)."""
    preco_col = _DIVERGENCIA_PRECO_COL.get(preco, "preco_venda")
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "itens": []}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_usuario_digitacao_col(cur)
        tabela, data_resolvida = _resolve_balanco_tabela_sync(cur, data)
        if not data_resolvida:
            return {"success": True, "itens": []}
        nivel_sql, nivel_params = _niveis_where_sql(niveis)
        contado_sql = " AND i.contado_em IS NOT NULL" if tabela == "inventario" else ""
        cur.execute(
            f"SELECT i.codigo_interno, p.descricao, (i.estoque_atual+i.reservado) AS estoque_sistema, "
            f"i.estoque_balanco, (i.estoque_balanco-(i.estoque_atual+i.reservado)) AS diferenca, "
            f"i.{preco_col} AS preco_unitario, "
            f"((i.estoque_balanco-(i.estoque_atual+i.reservado))*i.{preco_col}) AS preco_total, "
            "COALESCE(NULLIF(p.nivel1,''),'') AS nivel1 "
            f"FROM {tabela} i INNER JOIN pecas p ON p.codigo_int = i.codigo_interno "
            f"WHERE i.estoque_balanco<>(i.estoque_atual+i.reservado){contado_sql} AND i.data=%s{nivel_sql} "
            "UNION ALL "
            "SELECT i.codigo_interno, v.descricao, (i.estoque_atual+i.reservado) AS estoque_sistema, "
            f"i.estoque_balanco, (i.estoque_balanco-(i.estoque_atual+i.reservado)) AS diferenca, "
            f"i.{preco_col} AS preco_unitario, "
            f"((i.estoque_balanco-(i.estoque_atual+i.reservado))*i.{preco_col}) AS preco_total, "
            "COALESCE(NULLIF(v.nivel1,''),'') AS nivel1 "
            f"FROM {tabela} i INNER JOIN veiculos v ON v.codigo_int = i.codigo_interno "
            f"WHERE i.estoque_balanco<>(i.estoque_atual+i.reservado){contado_sql} AND i.data=%s{nivel_sql}",
            (data_resolvida,) + tuple(nivel_params) + (data_resolvida,) + tuple(nivel_params),
        )
        linhas = cur.fetchall()
        descr_por_nivel1 = _descr_por_nivel1_sync(cur, {r.get("nivel1") for r in linhas if r.get("nivel1")})
        cur.close()
        itens = [{
            "codigo_interno": (row.get("codigo_interno") or "").strip(),
            "descricao": (row.get("descricao") or "").strip(),
            "estoque_sistema": float(row.get("estoque_sistema") or 0),
            "estoque_balanco": float(row.get("estoque_balanco") or 0),
            "diferenca": float(row.get("diferenca") or 0),
            "preco_unitario": _trunca2(row.get("preco_unitario") or 0),
            "preco_total": _trunca2(row.get("preco_total") or 0),
            "grupo": _grupo_nome(row.get("nivel1") or "", descr_por_nivel1),
        } for row in linhas]
        campo_ordem = _DIVERGENCIA_ORDEM.get(ordenar, "codigo_interno")
        itens.sort(key=lambda it: (it[campo_ordem], it["codigo_interno"]))
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


def _resumo_por_usuario_sync(servidor: str, banco: str) -> dict:
    """Só a contagem por usuário (nome + total de itens), sem trazer os
    itens em si — pro Painel de Gerente/Supervisor/Master montar os
    accordions fechados por padrão, sem carregar tudo de uma vez.
    Performance: cada grupo só busca os itens de verdade quando o usuário
    clica pra abrir aquele accordion (`_listar_itens_sync` com `usuario`/
    `sem_usuario`, chamado à parte). Pedido explícito do usuário,
    2026-07-23."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "resumo": []}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_usuario_digitacao_col(cur)
        ctrl = _controle_sync(cur)
        if ctrl["situacao_balanco"] != "A":
            return {"success": True, "resumo": []}
        cur.execute(
            "SELECT i.usuario_digitacao, "
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS usuario_nome, "
            "COUNT(*) AS total "
            "FROM inventario i "
            "LEFT JOIN funcionarios f ON f.codigo_int = i.usuario_digitacao "
            "WHERE i.data=%s AND i.contado_em IS NOT NULL "
            "GROUP BY i.usuario_digitacao, COALESCE(NULLIF(f.nome_guerra,''), f.nome) "
            "ORDER BY CASE WHEN i.usuario_digitacao IS NULL THEN 1 ELSE 0 END, usuario_nome",
            (ctrl["data_balanco"],),
        )
        resumo = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "resumo": resumo}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "resumo": []}
    finally:
        conn.close()


def _listar_itens_sync(
    servidor: str, banco: str, usuario: Optional[int] = None, sem_usuario: bool = False,
) -> dict:
    """`usuario` filtra pra só os itens digitados por ele — quem chama decide
    se filtra (Gerente/Supervisor/Master veem tudo, "quebrado por usuário";
    os demais só a própria lista). Regra de visibilidade, não de segurança
    de dados sensíveis — mesmo espírito do filtro de vendedor em Pedidos
    (`isManagerFuncao`), decidido no frontend; aqui o parâmetro só existe
    pra a REDUÇÃO ser real (a query já filtra, não é só esconder na tela).
    `sem_usuario=True` filtra o grupo "Usuário não identificado"
    (`usuario_digitacao IS NULL`) — `usuario=%s` nunca bate com NULL em
    SQL, precisa de uma cláusula própria. Pedido explícito do usuário,
    2026-07-23."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "itens": []}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_usuario_digitacao_col(cur)
        ctrl = _controle_sync(cur)
        if ctrl["situacao_balanco"] != "A":
            return {"success": True, "itens": []}

        # `descricao` cai em cascata pecas -> veiculos (mesma cascata de
        # busca) porque o item pode ter vindo de qualquer uma das duas.
        # Nome do usuário sempre nome_guerra primeiro, mesmo padrão
        # `[GLOBAL]` já usado em toda exibição de nome de funcionário deste
        # backend (não é o campo "vendedor" estritamente, mas o mesmo
        # critério nome_guerra-primeiro já era seguido por outros papéis
        # antes da regra ser escrita explicitamente — ver CLAUDE.md).
        where = ["i.data=%s", "i.contado_em IS NOT NULL"]
        params: list = [ctrl["data_balanco"]]
        if sem_usuario:
            where.append("i.usuario_digitacao IS NULL")
        elif usuario is not None:
            where.append("i.usuario_digitacao=%s")
            params.append(usuario)
        cur.execute(
            "SELECT i.codigo_interno, "
            "COALESCE(p.descricao, v.descricao, '') AS descricao, "
            "i.estoque_balanco, i.estoque_atual, i.usuario_digitacao, "
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS usuario_nome "
            "FROM inventario i "
            "LEFT JOIN pecas p ON p.codigo_int = i.codigo_interno "
            "LEFT JOIN veiculos v ON v.codigo_int = i.codigo_interno "
            "LEFT JOIN funcionarios f ON f.codigo_int = i.usuario_digitacao "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY CASE WHEN i.usuario_digitacao IS NULL THEN 1 ELSE 0 END, i.codigo_interno",
            tuple(params),
        )
        itens = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


def _fechar_sync(servidor: str, banco: str, usuario: Optional[int]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        ctrl = _controle_sync(cur)
        if ctrl["situacao_balanco"] != "A":
            return {"success": False, "message": "Não existe Inventário em aberto."}
        data_balanco = ctrl["data_balanco"]

        if ctrl["tipo_balanco"] != "C":
            # Geral E Parcial geram ajuste real de estoque no Fechamento —
            # Contábil só formaliza o balanço sem tocar em pecas.qtd (mesma
            # regra do legado: `If tipo_balanco="C" Then GoTo fecha`, aqui
            # invertida pra cobrir os outros tipos de uma vez). O `INNER
            # JOIN pecas`/`INNER JOIN inventario i` abaixo, contra a tabela
            # `inventario`, já é o que faz o Parcial funcionar certo sem
            # nenhum código extra: pro tipo Parcial, `inventario` só tem
            # linha pros itens que FORAM digitados (a Abertura não
            # pré-carrega nada nesse tipo — ver `_abrir_sync`), então o
            # ajuste automaticamente só toca nesses itens, nunca nos que
            # não foram contados. Pro Geral, que pré-carrega TUDO, o mesmo
            # JOIN cobre o catálogo inteiro — daí a diferença de
            # comportamento ("zera o não digitado" no Geral, "não toca no
            # não digitado" no Parcial) vir de graça, sem `if` a mais aqui.
            #
            # SET-BASED, não loop-por-item: a versão original fazia até 3
            # idas-ao-banco POR ITEM DIVERGENTE (SELECT pecas + INSERT
            # movimentacao + UPDATE pecas, tudo dentro de um `for` em
            # Python) — contra uma conexão de verdade (não localhost), com
            # milhares de itens ainda não digitados numa Abertura Geral
            # (todo item vira "divergente" até ser contado, porque
            # `estoque_balanco` nasce em 0), isso virava milhares de
            # round-trips sequenciais — trava a tela sem erro nenhum
            # aparecer (achado ao vivo 2026-07-23, reportado pelo usuário
            # como "cliquei e não aconteceu nada" na conexão Pajé). Ver
            # "Não replicar truques VB6" no CLAUDE.md — loop-por-registro é
            # workaround de linguagem procedural sem SQL de verdade, não
            # regra de negócio; aqui viram só 2 comandos (INSERT...SELECT +
            # UPDATE...FROM), o SQL Server resolve tudo de uma vez.
            # `INNER JOIN pecas` já exclui sozinho os itens de `veiculos`
            # (mesmo comportamento de antes — ver nota de topo do arquivo).
            cur.execute(
                "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, p_unit, num_nf, serie_nf) "
                "SELECT %s, "
                "CASE WHEN (i.estoque_balanco - (i.estoque_atual + i.reservado)) > 0 THEN 'E00' ELSE 'S00' END, "
                "i.codigo_interno, "
                "ABS(i.estoque_balanco - (i.estoque_atual + i.reservado)), "
                "i.custo_reposicao, 0, 'IV' "
                "FROM inventario i "
                "INNER JOIN pecas p ON p.codigo_int = i.codigo_interno "
                "WHERE i.data=%s AND ABS(i.estoque_balanco - (i.estoque_atual + i.reservado)) > 0.0001",
                (data_balanco, data_balanco),
            )
            cur.execute(
                "UPDATE p SET p.qtd = p.qtd + (i.estoque_balanco - (i.estoque_atual + i.reservado)) "
                "FROM pecas p "
                "INNER JOIN inventario i ON i.codigo_interno = p.codigo_int "
                "WHERE i.data=%s AND ABS(i.estoque_balanco - (i.estoque_atual + i.reservado)) > 0.0001",
                (data_balanco,),
            )

        cur.execute(
            "SELECT TOP 1 fechamento FROM inventario_controle WHERE data=%s", (data_balanco,),
        )
        row = cur.fetchone()
        if row and row.get("fechamento"):
            cur.execute(
                "UPDATE inventario_controle SET refechado=GETDATE(), "
                "hora_refechado=CONVERT(varchar(8),GETDATE(),108), usuario_refechado=%s WHERE data=%s",
                (usuario, data_balanco),
            )
        else:
            cur.execute(
                "UPDATE inventario_controle SET fechamento=GETDATE(), "
                "hora_fechamento=CONVERT(varchar(8),GETDATE(),108), usuario_fechamento=%s WHERE data=%s",
                (usuario, data_balanco),
            )
        cur.execute("UPDATE controle SET situacao_balanco='F'")
        conn.commit()
        cur.close()
        return {"success": True, "message": "Inventário fechado com sucesso."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _cancelar_sync(servidor: str, banco: str, usuario: Optional[int]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        ctrl = _controle_sync(cur)
        if ctrl["situacao_balanco"] != "A":
            return {"success": False, "message": "Não existe Inventário em aberto."}
        data_balanco = ctrl["data_balanco"]

        cur.execute("DELETE FROM inventario WHERE data=%s", (data_balanco,))
        cur.execute("UPDATE controle SET situacao_balanco='C'")
        cur.execute(
            "UPDATE inventario_controle SET cancelamento=GETDATE(), "
            "hora_cancelamento=CONVERT(varchar(8),GETDATE(),108), usuario_cancelamento=%s WHERE data=%s",
            (usuario, data_balanco),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Inventário cancelado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _ensure_automatico_col(cur) -> None:
    """`inventario_controle.automatico` (Fase 3, 2026-07-23) — marca linhas
    geradas pelas rotinas automáticas mensal/diária, substituindo o
    sentinela mágico `usuario_abertura=-2` do legado (melhoria já proposta
    em PENDENCIAS.md > Inventário > "Funções de inicialização automática").
    Migração idempotente, mesmo padrão de `_ensure_usuario_digitacao_col`."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='automatico' AND Object_ID=Object_ID('inventario_controle')) "
        "ALTER TABLE inventario_controle ADD automatico BIT NULL"
    )


def _primeiro_dia_mes(hoje: date) -> date:
    return hoje.replace(day=1)


def _inventario_automatico_mensal_sync(cur, hoje: date) -> bool:
    """Fase 3 — porta `InventarioAutomatico` (`Geral\\Mdl_Proc.bas` linha
    ~26305), só para o segmento SEM módulo Posto ativo (regra de negócio
    confirmada pelo usuário 2026-07-22 — sobrepõe o próprio gate interno
    do código VB6, que também rodava com Posto ativo excluindo os códigos
    de combustível; aqui `InventarioPostoAutomatico` cobre esse caso
    inteiramente, nunca os dois juntos). Snapshot mensal (1x por mês, no
    primeiro acesso do mês) de TODO o estoque de `pecas` direto em
    `inventario_old` — não abre um balanço "de verdade" (não mexe em
    `inventario`/`controle`), é só arquivo histórico, zero efeito em
    `pecas.qtd`/`movimentacao` (diferente do Fechamento manual).
    `qtd<1000000` é guarda de qualidade de dado do legado, não regra de
    negócio (mesma nota já registrada pro Abrir manual). Retorna True se
    rodou agora, False se já tinha rodado este mês (idempotente)."""
    primeiro_dia = _primeiro_dia_mes(hoje)
    cur.execute(
        "SELECT TOP 1 1 AS ok FROM inventario_controle WHERE data=%s AND automatico=1 AND tipo_balanco='K'",
        (primeiro_dia,),
    )
    if cur.fetchone():
        return False
    cur.execute(
        "INSERT INTO inventario_controle (data, abertura, hora_abertura, tipo_balanco, automatico) "
        "VALUES (%s, GETDATE(), CONVERT(varchar(8),GETDATE(),108), 'K', 1)",
        (primeiro_dia,),
    )
    cur.execute(
        "INSERT INTO inventario_old (codigo_interno, preco_custo, preco_venda, custo_inventario, "
        "custo_reposicao, estoque_atual, reservado, reservado_os, estoque_cli, estoque_for, "
        "estoque_balanco, data, tipo_sped) "
        "SELECT DISTINCT codigo_int, CAST(p_custo AS numeric(15,3)), CAST(p_venda AS numeric(15,3)), "
        "CAST(custo_inventario AS numeric(15,3)), CAST(custo_reposicao AS numeric(15,3)), "
        "CAST((qtd+reservado+reservado_os) AS numeric(15,3)), 0, 0, estoque_cli, estoque_for, "
        "CAST((qtd+reservado+reservado_os) AS numeric(15,3)), %s, 'K' "
        "FROM pecas WHERE ((qtd+reservado+reservado_os)>0 OR estoque_cli>0 OR estoque_for>0) "
        "AND tipo_peca>=0 AND qtd<1000000",
        (primeiro_dia,),
    )
    cur.execute(
        "UPDATE inventario_controle SET fechamento=GETDATE(), "
        "hora_fechamento=CONVERT(varchar(8),GETDATE(),108) "
        "WHERE data=%s AND automatico=1 AND tipo_balanco='K'",
        (primeiro_dia,),
    )
    return True


def _inventario_posto_automatico_mensal_sync(cur, hoje: date) -> bool:
    """Fase 3 — porta `InventarioPostoAutomatico` (`Mdl_Proc.bas` linha
    ~26233), só para o segmento COM módulo Posto ativo (substitui
    inteiramente `_inventario_automatico_mensal_sync` nesse caso — nunca os
    dois juntos, regra confirmada pelo usuário). Snapshot mensal do estoque
    de combustível calculado a partir de `tanque_estoque` (mesma fonte já
    lida diariamente pelo módulo Posto, ver `tanque_estoque_service.py`),
    não de `pecas.qtd`. Só marca o controle como fechado quando TODO
    combustível cadastrado já teve alguma leitura de tanque no mês —
    senão fica em aberto e tenta de novo na próxima chamada (mesmo
    comportamento do legado). Diferente do legado: idempotência também
    POR COMBUSTÍVEL (checa se já existe uma linha em `inventario_old` pro
    código/data antes de inserir) — o original reinseria tudo de novo a
    cada tentativa incompleta, sem checar duplicata; isso é gambiarra de
    falta de rastreio granular, não regra de negócio (ver "Não replicar
    truques VB6")."""
    primeiro_dia = _primeiro_dia_mes(hoje)
    cur.execute(
        "SELECT TOP 1 fechamento FROM inventario_controle WHERE data=%s AND automatico=1 AND tipo_balanco='M'",
        (primeiro_dia,),
    )
    row = cur.fetchone()
    if row and row.get("fechamento"):
        return False
    if not row:
        cur.execute(
            "INSERT INTO inventario_controle (data, abertura, hora_abertura, tipo_balanco, automatico) "
            "VALUES (%s, GETDATE(), CONVERT(varchar(8),GETDATE(),108), 'M', 1)",
            (primeiro_dia,),
        )

    cur.execute("SELECT codigo FROM combustivel")
    combustiveis = [r.get("codigo") for r in cur.fetchall()]
    qtd_comb = len(combustiveis)
    combustiveis_com_leitura: set = set()
    for cod_comb in combustiveis:
        cur.execute(
            "SELECT p.codigo_int, p.custo_medio, SUM(te.estoque) AS totvolume "
            "FROM pecas p, tanque t, tanque_estoque te "
            "WHERE p.codigo_fab=CONVERT(nvarchar,t.combustivel) AND t.tanque=te.tanque "
            "AND t.combustivel=%s AND te.data>=%s "
            "GROUP BY p.custo_medio, p.codigo_int",
            (cod_comb, primeiro_dia),
        )
        linhas = cur.fetchall()
        for linha in linhas:
            totvolume = linha.get("totvolume")
            if totvolume is None:
                continue
            codigo_int = linha.get("codigo_int")
            combustiveis_com_leitura.add(cod_comb)
            cur.execute(
                "SELECT TOP 1 1 AS ok FROM inventario_old WHERE codigo_interno=%s AND data=%s",
                (codigo_int, primeiro_dia),
            )
            if cur.fetchone():
                continue
            custo = linha.get("custo_medio") or 0
            cur.execute(
                "INSERT INTO inventario_old (codigo_interno, preco_custo, preco_venda, custo_inventario, "
                "custo_reposicao, estoque_atual, reservado, reservado_os, estoque_cli, estoque_for, "
                "estoque_balanco, data) VALUES (%s, %s, 0, %s, %s, %s, 0, 0, 0, 0, %s, %s)",
                (codigo_int, custo, custo, custo, totvolume, totvolume, primeiro_dia),
            )

    if len(combustiveis_com_leitura) >= qtd_comb:
        cur.execute(
            "UPDATE inventario_controle SET fechamento=GETDATE(), "
            "hora_fechamento=CONVERT(varchar(8),GETDATE(),108) "
            "WHERE data=%s AND automatico=1 AND tipo_balanco='M'",
            (primeiro_dia,),
        )
    return True


def _inventario_contabil_diario_sync(cur, hoje: date) -> bool:
    """Fase 3 — porta o ramo `inventario_contabil` de `MudaDataSistema`
    (`Mdl_Proc.bas` linha ~6933), só para o segmento SEM módulo Posto
    ativo (regra confirmada pelo usuário — o ramo irmão dessa mesma rotina,
    de reconciliação de estoque hardcoded por CNPJ, foi descartado por
    completo, "pode ser desconsiderada"). Snapshot diário (1x por dia) de
    TODO `pecas` ativo + itens de O.S. aberta/fechada cujo código começa
    com "P", em `inventario_contabil`/`inventario_contabil_os` — puro
    arquivo histórico, zero efeito em `pecas.qtd`/`movimentacao`. Retenção
    de 60 dias (mesma regra do legado, `DELETE ... WHERE data<=hoje-60`).

    Corrige um bug real do legado: o INSERT de `inventario_contabil_os`
    usava data/hora HARDCODED (`'2021-04-15','12:27:39'` — claramente sobra
    de teste/desenvolvimento nunca corrigida, já que o INSERT irmão de
    `inventario_contabil`, logo acima no mesmo bloco, usa `Date`/`Time`
    dinâmicos normalmente) — aqui os dois usam a data/hora de HOJE."""
    cur.execute("DELETE FROM inventario_contabil WHERE data<=%s", (hoje - timedelta(days=60),))
    cur.execute("SELECT TOP 1 1 AS ok FROM inventario_contabil WHERE data=%s", (hoje,))
    if cur.fetchone():
        return False
    cur.execute(
        "INSERT INTO inventario_contabil (data, hora_abertura, codigo_interno, estoque_atual, reservado, reservado_os) "
        "SELECT %s, CONVERT(varchar(8),GETDATE(),108), codigo_int, qtd, reservado, reservado_os "
        "FROM pecas WHERE situacao='A'",
        (hoje,),
    )
    cur.execute(
        "INSERT INTO inventario_contabil_os (data, hora_abertura, os, situacao, codigo_interno, quant) "
        "SELECT %s, CONVERT(varchar(8),GETDATE(),108), os.codigo, os.situacao, os_produto.codigo_interno, os_produto.quant "
        "FROM os, os_produto WHERE os.codigo=os_produto.os AND (os.situacao='A' OR os.situacao='F') "
        "AND LEFT(os_produto.codigo_interno,1)='P'",
        (hoje,),
    )
    return True


def _controla_abertura_dia_ativo(cur) -> bool:
    """`controle_configuracao.CONTROLA_ABERTURA_DIA` — espelha o global VB6
    `Dados_Controle_Configuracao.Abertura_do_dia`, lido uma vez no boot do
    app legado a partir desta mesma coluna pra decidir se o dia abre
    sozinho ou não. Aqui, decide se as rotinas automáticas de Abertura do
    Dia (Fase 3 abaixo — snapshots mensal/diário) rodam sozinhas no
    primeiro acesso, ou ficam totalmente desligadas (empresa que não quer
    abertura automática). Leitura fresca por request, mesmo padrão de
    `posto_common.modulo_posto_ativo` — nunca cache global de processo."""
    cur.execute("SELECT TOP 1 CONTROLA_ABERTURA_DIA FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("CONTROLA_ABERTURA_DIA") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _executar_rotinas_automaticas_sync(servidor: str, banco: str) -> dict:
    """Fase 3 (2026-07-23) — dispara as rotinas automáticas do legado
    (mensal + diária contábil) no primeiro acesso do dia/mês de QUALQUER
    usuário, sem Tarefa Agendada do Windows nem worker separado (decisão já
    registrada em PENDENCIAS.md > Inventário > "Funções de inicialização
    automática" — opção (a), confirmada pelo usuário). Chamada pelo
    frontend uma vez por sessão (`useDashboard.ts`), silenciosa — o usuário
    nunca vê isso rodar. Idempotente: cada chamada reverifica se já rodou
    este mês/dia antes de fazer qualquer coisa, sem depender de nenhum
    estado de processo (mesmo princípio de `posto_common.data_movimento` —
    leitura fresca por request, nunca cache global).

    Gate por `CONTROLA_ABERTURA_DIA` (2026-08-16, user-directed — a coluna
    já existia como toggle em Módulos e Recursos, mas não tinha efeito
    algum aqui): com o flag desligado, nenhuma rotina automática roda —
    empresa que optou por não ter abertura automática do dia fica só com
    o fluxo manual (Abertura/Digitação/Fechar já existentes).

    Módulo Posto ativo → só `_inventario_posto_automatico_mensal_sync`
    (sem o diário contábil pra esse segmento). Sem Posto → o mensal
    genérico E o diário contábil, os dois. Regra de negócio confirmada pelo
    usuário 2026-07-22, sobrepõe a leitura literal do gate original do VB6
    (`Posto And NFCe_Ws`, que o próprio usuário indicou não refletir a
    intenção real)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _controla_abertura_dia_ativo(cur):
            cur.close()
            return {"success": True, "abertura_dia_ativa": False, "mensal_executado": False, "diario_executado": False}
        _ensure_automatico_col(cur)
        hoje = date.today()
        posto_ativo = modulo_posto_ativo(cur)
        if posto_ativo:
            mensal_executado = _inventario_posto_automatico_mensal_sync(cur, hoje)
            diario_executado = False
        else:
            mensal_executado = _inventario_automatico_mensal_sync(cur, hoje)
            diario_executado = _inventario_contabil_diario_sync(cur, hoje)
        conn.commit()
        cur.close()
        return {
            "success": True,
            "abertura_dia_ativa": True,
            "mensal_executado": mensal_executado,
            "diario_executado": diario_executado,
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def status(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_status_sync, servidor, banco)


async def executar_rotinas_automaticas(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_executar_rotinas_automaticas_sync, servidor, banco)


async def abrir(servidor: str, banco: str, data: str, tipo: str, usuario: Optional[int]) -> dict:
    return await asyncio.to_thread(_abrir_sync, servidor, banco, data, tipo, usuario)


async def buscar_item(servidor: str, banco: str, termo: str) -> dict:
    return await asyncio.to_thread(_buscar_item_sync, servidor, banco, termo)


async def resumo_por_usuario(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_resumo_por_usuario_sync, servidor, banco)


async def listar_itens(
    servidor: str, banco: str, usuario: Optional[int] = None, sem_usuario: bool = False,
) -> dict:
    return await asyncio.to_thread(_listar_itens_sync, servidor, banco, usuario, sem_usuario)


async def relatorio_contagem(
    servidor: str, banco: str, tipos: Optional[list] = None, somente_ativos: bool = False,
    niveis: Optional[list] = None,
) -> dict:
    return await asyncio.to_thread(_relatorio_contagem_sync, servidor, banco, tipos, somente_ativos, niveis)


async def relatorio_conferencia(
    servidor: str, banco: str, tipos: Optional[list] = None, listar_zerados: bool = False,
    niveis: Optional[list] = None,
) -> dict:
    return await asyncio.to_thread(_relatorio_conferencia_sync, servidor, banco, tipos, listar_zerados, niveis)


async def relatorio_critica(servidor: str, banco: str, niveis: Optional[list] = None, data: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_relatorio_critica_sync, servidor, banco, niveis, data)


async def relatorio_resultado(
    servidor: str, banco: str, niveis: Optional[list] = None, data: Optional[str] = None,
    fonte_estoque: str = "inventario",
) -> dict:
    return await asyncio.to_thread(_relatorio_resultado_sync, servidor, banco, niveis, data, fonte_estoque)


async def relatorio_divergencia(
    servidor: str, banco: str, niveis: Optional[list] = None, data: Optional[str] = None,
    preco: str = "venda", ordenar: str = "codigo",
) -> dict:
    return await asyncio.to_thread(_relatorio_divergencia_sync, servidor, banco, niveis, data, preco, ordenar)


async def incluir_item(servidor: str, banco: str, dados: dict, usuario: Optional[int] = None) -> dict:
    return await asyncio.to_thread(_gravar_item_sync, servidor, banco, dados, True, usuario)


async def alterar_item(servidor: str, banco: str, dados: dict, usuario: Optional[int] = None) -> dict:
    return await asyncio.to_thread(_gravar_item_sync, servidor, banco, dados, False, usuario)


async def fechar(servidor: str, banco: str, usuario: Optional[int]) -> dict:
    return await asyncio.to_thread(_fechar_sync, servidor, banco, usuario)


async def cancelar(servidor: str, banco: str, usuario: Optional[int]) -> dict:
    return await asyncio.to_thread(_cancelar_sync, servidor, banco, usuario)

"""Gestão de Compras > Ressuprimento (Transações > Gestão de Compras). Legado:
`FrmGesCom.frm` ("Gestor de Compras..."), aba "Ressuprimento" — relatório de
reposição de estoque cruzando Curva ABC + filtros de fornecedor/nível +
posição de estoque, com painel de "Últimas Compras" por produto.

Escopo desta rodada (decisão do usuário, 2026-07-18): esta é a prioridade
real — "hoje o cliente precisa de um relatório do que precisa comprar,
porque pedido de compra em si os clientes já aboliram, depois que temos a
opção de importar o xml da nota fiscal de entrada". Por isso:
  • A aba "Ressuprimento" do legado é a única implementada aqui.
  • A aba "Cotações" do legado (`FrmGesCom.frm`, `Tab(1).ControlCount = 0`
    no próprio `.frm` — nunca foi desenvolvida) e o painel "Últimas
    Cotações" (`LV3`, também nunca populado por nenhum código do legado —
    `PrepLV3` é definida mas nada faz `SELECT`/`INSERT` nela) ficam de fora
    desta migração — ver PENDENCIAS.md > "Gestão de Compras".
  • `FrmCotacao.frm` ("Cadastro de Cotações" — na verdade orçamento de
    VENDA pro cliente, tabelas `orcamento`/`orc_produto`/`comanda`, não
    cotação de compra — confirmado por investigação direta do
    código-fonte) fica fora desta rodada — ver PENDENCIAS.md.
    **Correção 2026-07-20**: `FrmPedCom.frm` (Pedido de Compra) FOI
    implementado numa sessão posterior (`pedido_compra_service.py`,
    ver `project_gestao_compras` na memória) — o parágrafo acima ficou
    desatualizado quando isso aconteceu; `_gerar_pedidos_ressuprimento_sync`
    logo abaixo reaproveita essa implementação (não duplica).

Os valores de `curva_abc`/`estoque_minimo`/`estoque_ressuprimento`/
`estoque_maximo`/`Consumo_Medio_Mensal` em `pecas` são calculados pela tela
"Curva ABC Estoques" (`services/curva_abc_service.py`) — este service só
LÊ esses campos, nunca os grava.
"""
import asyncio
from datetime import date, datetime
from typing import Optional

from db.connection import _open_conn
from models.pedido_compra import AtualizarAlertasEstoqueRequest, GerarPedidosRessuprimentoRequest
from services import pedido_compra_service
from services.margem_lucro_service import _nivel_clause
from services.pedido_common import _modulo_curva_abc_ativo
from services.permissoes_service import tem_permissao

_MODULO_OFF_MSG = "Módulo Curva ABC/Compras está desativado — fale com o administrador em Configurações > Módulos e Recursos."

ORDER_MAP = {
    "descricao": "p.descricao",
    "estoque": "p.qtd, p.descricao",
    "consumo": "p.Consumo_Medio_Mensal, p.descricao",
}


def _list_curvas_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "curva_abc": [], "curva_abc_fin": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute("SELECT DISTINCT curva_abc FROM pecas WHERE curva_abc IS NOT NULL AND curva_abc <> '' ORDER BY curva_abc")
        curva_abc = [(r.get("curva_abc") or "").strip() for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT curva_abc_fin FROM pecas WHERE curva_abc_fin IS NOT NULL AND curva_abc_fin <> '' ORDER BY curva_abc_fin")
        curva_abc_fin = [(r.get("curva_abc_fin") or "").strip() for r in cur.fetchall()]
        cur.close()
        return {"success": True, "curva_abc": curva_abc, "curva_abc_fin": curva_abc_fin}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "curva_abc": [], "curva_abc_fin": []}
    finally:
        conn.close()


def _list_ressuprimento_sync(
    servidor: str, banco: str,
    curva_abc: Optional[str] = None, curva_abc_fin: Optional[str] = None,
    fornecedor: Optional[int] = None, nivel: Optional[str] = None,
    abaixo_minimo: bool = False, abaixo_ressuprimento: bool = False, acima_maximo: bool = False,
    zerado_negativo: bool = False,
    order_by: str = "descricao",
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        where = ["p.situacao = 'A'"]
        params: list = []
        if curva_abc:
            where.append("p.curva_abc = %s")
            params.append(curva_abc)
        if curva_abc_fin:
            where.append("p.curva_abc_fin = %s")
            params.append(curva_abc_fin)
        if fornecedor:
            where.append("p.codigo_int IN (SELECT peca FROM pecas_fornecedor WHERE fornecedor = %s)")
            params.append(fornecedor)
        nc, npar = _nivel_clause("p", nivel)
        where += nc
        params += npar
        if abaixo_minimo:
            where.append("p.qtd < p.estoque_minimo")
        if abaixo_ressuprimento:
            where.append("p.qtd < p.estoque_ressuprimento")
        if acima_maximo:
            where.append("p.qtd > p.estoque_maximo AND p.estoque_maximo <> 0")
        if zerado_negativo:
            where.append("p.qtd <= 0")

        order_sql = ORDER_MAP.get(order_by, ORDER_MAP["descricao"])
        cur.execute(
            "SELECT p.curva_abc, p.curva_abc_fin, p.codigo_fab, p.codigo_int, p.descricao, p.qtd, "
            "p.Consumo_Medio_Mensal AS cmm, p.estoque_minimo, p.estoque_ressuprimento, p.estoque_maximo "
            f"FROM pecas p WHERE {' AND '.join(where)} ORDER BY {order_sql}",
            tuple(params),
        )
        items = []
        for r in cur.fetchall():
            qtd = float(r.get("qtd") or 0)
            cmm = float(r.get("cmm") or 0)
            cmm_diario = cmm / 30
            prev_dia = int(qtd / cmm_diario) if cmm_diario and qtd >= 0 else 0
            prev_mes = int(qtd / cmm) if cmm and qtd >= 0 else 0
            items.append({
                "curva_abc": (r.get("curva_abc") or "").strip(),
                "curva_abc_fin": (r.get("curva_abc_fin") or "").strip(),
                "codigo_fab": (r.get("codigo_fab") or "").strip(),
                "codigo_int": (r.get("codigo_int") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "qtd": qtd,
                "consumo_medio_mensal": cmm,
                "estoque_minimo": float(r.get("estoque_minimo") or 0),
                "estoque_ressuprimento": float(r.get("estoque_ressuprimento") or 0),
                "estoque_maximo": float(r.get("estoque_maximo") or 0),
                "prev_mes": prev_mes,
                "prev_dia": prev_dia,
            })
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


# Cache compartilhado dos contadores de alerta de estoque — pedido
# explícito do usuário, 2026-07-21 ("guarde o último resultado para todos
# os usuários que tenha acesso gerencial... ao clicar traz as listas...
# como já faz"). Antes, cada navegador/sessão calculava por conta própria
# (uma vez por sessão do app, ver useDashboard.ts) — mas o cálculo em si é
# caro (medido: até ~13s pra primeira query numa conexão nova com este
# banco, mesmo já reduzido a 1 query só). Agora o cálculo só roda quando
# alguém aperta "Atualizar" (`ALERTAS_ESTOQUE.ATUALIZAR`) e grava aqui — o
# card, pra todo mundo com acesso (`ALERTAS_ESTOQUE.ABRIR`), só LÊ essa
# tabela (leitura de 1 linha, praticamente instantânea). Igual ao padrão
# mono-empresa de `controle_aux` (não existe coluna servidor/banco — cada
# empresa já é o próprio banco desta conexão) e ao padrão de migração
# idempotente já usado em `log_auditoria_service`/`whatsapp/repository.py`.
_DDL_ALERTAS_ESTOQUE_CACHE = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'alertas_estoque_cache')
BEGIN
    CREATE TABLE alertas_estoque_cache (
        id INT IDENTITY(1,1) PRIMARY KEY,
        minimo INT NOT NULL DEFAULT 0,
        ressuprimento INT NOT NULL DEFAULT 0,
        zerado INT NOT NULL DEFAULT 0,
        curva_abc_ultima_geracao DATETIME NULL,
        curva_abc_desatualizada BIT NOT NULL DEFAULT 0,
        atualizado_em DATETIME NOT NULL DEFAULT GETDATE(),
        atualizado_por INT NULL
    );
END
"""


def _ensure_alertas_estoque_cache_table(cur) -> None:
    cur.execute(_DDL_ALERTAS_ESTOQUE_CACHE)


def _ler_flags_alertas_sync(cur) -> dict:
    cur.execute(
        "SELECT TOP 1 ALERTA_ESTOQUE_MINIMO, ALERTA_ESTOQUE_RESSUPRIMENTO, ALERTA_ESTOQUE_ZERADO "
        "FROM controle_aux WHERE empresa_aux=0"
    )
    row = cur.fetchone() or {}
    return {
        "minimo": bool(row.get("ALERTA_ESTOQUE_MINIMO")),
        "ressuprimento": bool(row.get("ALERTA_ESTOQUE_RESSUPRIMENTO")),
        "zerado": bool(row.get("ALERTA_ESTOQUE_ZERADO")),
    }


def _calcular_contadores_pecas_sync(cur) -> dict:
    """Sempre calcula os 3 contadores juntos (independente de qual alerta
    está ligado) — é a parte cara desta funcionalidade (medido: até ~13s
    numa conexão nova), só deve rodar quando alguém aperta "Atualizar", não
    a cada leitura do card. UMA query com agregação condicional (`SUM(CASE
    WHEN ...)`), não 3 `COUNT(*)` separados — mesmas expressões já usadas
    em `_list_ressuprimento_sync` (reaproveitadas, não duplicadas: uma
    mudança na regra de "abaixo do mínimo" também precisa valer aqui)."""
    cur.execute(
        "SELECT "
        "SUM(CASE WHEN p.qtd < p.estoque_minimo THEN 1 ELSE 0 END) AS minimo, "
        "SUM(CASE WHEN p.qtd < p.estoque_ressuprimento THEN 1 ELSE 0 END) AS ressuprimento, "
        "SUM(CASE WHEN p.qtd <= 0 THEN 1 ELSE 0 END) AS zerado "
        "FROM pecas p WHERE p.situacao='A'"
    )
    r = cur.fetchone() or {}
    return {
        "minimo": int(r.get("minimo") or 0),
        "ressuprimento": int(r.get("ressuprimento") or 0),
        "zerado": int(r.get("zerado") or 0),
    }


def _calcular_curva_abc_status_sync(cur) -> dict:
    """"Modo Didático" — se a Curva ABC/Estoques não é gerada/reprocessada
    há mais de 6 meses (ou nunca foi), os valores de estoque_minimo/
    estoque_ressuprimento/consumo_medio_mensal usados nos alertas podem
    estar desatualizados — avisa no mesmo card, mesmo sem nenhum alerta
    ativo no momento. Pedido explícito do usuário, 2026-07-20.
    `log_auditoria` já registra toda geração/reprocessamento (`tela=
    'CURVA_ABC'`, comandos GERAR/REPROCESSAR) — reaproveitado em vez de
    criar uma coluna nova só pra isso. Best-effort: bases mais antigas/de
    teste podem não ter a tabela `log_auditoria` ainda (ela não faz parte
    do schema legado) — sem isso, o card inteiro quebrava por causa só
    deste aviso, que é um extra. Descoberto testando contra a conexão PAGÉ
    MINIMACHINE/BD_PAJE, 2026-07-20."""
    try:
        cur.execute(
            "SELECT TOP 1 data_hora FROM log_auditoria WHERE tela='CURVA_ABC' ORDER BY data_hora DESC"
        )
        ultima = cur.fetchone()
        ultima_data = ultima.get("data_hora") if ultima else None
        if ultima_data is None:
            return {"curva_abc_ultima_geracao": None, "curva_abc_desatualizada": True}
        cur.execute("SELECT CASE WHEN %s < DATEADD(month, -6, GETDATE()) THEN 1 ELSE 0 END AS desatualizada", (ultima_data,))
        r = cur.fetchone()
        return {"curva_abc_ultima_geracao": ultima_data, "curva_abc_desatualizada": bool(r.get("desatualizada")) if r else False}
    except Exception:
        return {"curva_abc_ultima_geracao": None, "curva_abc_desatualizada": True}


def _ler_cache_alertas_estoque_sync(cur) -> Optional[dict]:
    _ensure_alertas_estoque_cache_table(cur)
    cur.execute(
        "SELECT TOP 1 minimo, ressuprimento, zerado, curva_abc_ultima_geracao, "
        "curva_abc_desatualizada, atualizado_em FROM alertas_estoque_cache ORDER BY id DESC"
    )
    return cur.fetchone()


def _gravar_cache_alertas_estoque_sync(
    cur, contadores: dict, curva: dict, atualizado_por: Optional[int],
) -> datetime:
    _ensure_alertas_estoque_cache_table(cur)
    agora = datetime.now()
    # Cache de 1 linha só (mono-empresa, mesmo padrão de `controle_aux`) —
    # apaga e regrava em vez de UPDATE, mais simples que lidar com
    # @@ROWCOUNT/upsert pra uma tabela que nunca tem mais de 1 registro.
    cur.execute("DELETE FROM alertas_estoque_cache")
    cur.execute(
        "INSERT INTO alertas_estoque_cache "
        "(minimo, ressuprimento, zerado, curva_abc_ultima_geracao, curva_abc_desatualizada, atualizado_em, atualizado_por) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (
            contadores["minimo"], contadores["ressuprimento"], contadores["zerado"],
            curva["curva_abc_ultima_geracao"], curva["curva_abc_desatualizada"], agora, atualizado_por,
        ),
    )
    return agora


def _montar_resposta_alertas(flags: dict, contadores: dict, curva: dict, atualizado_em: Optional[datetime]) -> dict:
    return {
        "success": True, "ativo": True,
        "minimo": {"count": contadores["minimo"]} if flags["minimo"] else None,
        "ressuprimento": {"count": contadores["ressuprimento"]} if flags["ressuprimento"] else None,
        "zerado": {"count": contadores["zerado"]} if flags["zerado"] else None,
        "curva_abc_ultima_geracao": curva["curva_abc_ultima_geracao"].isoformat() if curva["curva_abc_ultima_geracao"] else None,
        "curva_abc_desatualizada": curva["curva_abc_desatualizada"],
        "atualizado_em": atualizado_em.isoformat() if atualizado_em else None,
    }


def _resumo_alertas_estoque_sync(servidor: str, banco: str) -> dict:
    """Resumo pra card de alerta na Tela Principal (Gerente/Supervisor/
    Master) — pedido explícito do usuário, 2026-07-20: "caso esteja true,
    exibir... um card com esses alertas... chamando a atenção dos produtos".
    Lê os 3 toggles de `controle_aux` (Controle do Sistema > aba Diversos)
    pra decidir o que exibir, mas os CONTADORES em si vêm do cache
    compartilhado (`alertas_estoque_cache`) — só lido aqui, nunca
    recalculado (ver `_atualizar_alertas_estoque_sync` pra isso). Pedido
    explícito do usuário, 2026-07-21: "guarde o último resultado para
    todos os usuários... teriam os resultados da última atualização". Na
    primeira vez pra uma empresa (cache ainda vazio), calcula e grava uma
    vez só, pra o card não ficar sempre vazio até alguém clicar
    "Atualizar"."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": True, "ativo": False, "minimo": None, "ressuprimento": None, "zerado": None}
        flags = _ler_flags_alertas_sync(cur)
        cache = _ler_cache_alertas_estoque_sync(cur)
        if cache is None:
            contadores = _calcular_contadores_pecas_sync(cur)
            curva = _calcular_curva_abc_status_sync(cur)
            atualizado_em = _gravar_cache_alertas_estoque_sync(cur, contadores, curva, atualizado_por=None)
            conn.commit()
        else:
            contadores = {"minimo": cache["minimo"], "ressuprimento": cache["ressuprimento"], "zerado": cache["zerado"]}
            curva = {"curva_abc_ultima_geracao": cache["curva_abc_ultima_geracao"], "curva_abc_desatualizada": bool(cache["curva_abc_desatualizada"])}
            atualizado_em = cache["atualizado_em"]
        resultado = _montar_resposta_alertas(flags, contadores, curva, atualizado_em)
        cur.close()
        return resultado
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _atualizar_alertas_estoque_sync(req: AtualizarAlertasEstoqueRequest) -> dict:
    """Recalcula os contadores de estoque de verdade (a parte cara) e grava
    no cache compartilhado — só roda quando o usuário aperta "Atualizar",
    nunca automaticamente. Gate de permissão reforçado aqui (não só no
    frontend), mesmo padrão de `produtos_niveis_service.py`."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "ALERTAS_ESTOQUE", "ATUALIZAR"):
            cur.close()
            return {"success": False, "message": "Sem permissão para atualizar os alertas de estoque."}
        flags = _ler_flags_alertas_sync(cur)
        contadores = _calcular_contadores_pecas_sync(cur)
        curva = _calcular_curva_abc_status_sync(cur)
        atualizado_em = _gravar_cache_alertas_estoque_sync(cur, contadores, curva, atualizado_por=req.usuario_alteracao)
        conn.commit()
        resultado = _montar_resposta_alertas(flags, contadores, curva, atualizado_em)
        cur.close()
        return resultado
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _ultimas_compras_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        cur.execute(
            "SELECT TOP 20 nf.num_nf, nf.data_mov, f.fantasia, "
            "nfi.qtd, nfi.qtd_un_compra, nfi.valor_total, "
            "nfi.valor_ipi, nfi.seguro, nfi.frete, nfi.despesas, nfi.valor_sub, nfi.valor_iss "
            "FROM n_fiscal nf "
            "JOIN n_fiscal_itens nfi ON nfi.codigo = nf.codigo "
            "JOIN fornecedor f ON f.codigo_int = nf.fornecedor "
            "WHERE nf.mov = 'E01' AND nf.situacao = 'A' AND nfi.codigo_int = %s "
            "ORDER BY nf.data_mov DESC",
            (codigo_int,),
        )
        items = []
        for r in cur.fetchall():
            qtd_total = float(r.get("qtd") or 0) * float(r.get("qtd_un_compra") or 1)
            valor_total = float(r.get("valor_total") or 0)
            impostos = (
                float(r.get("valor_ipi") or 0) + float(r.get("seguro") or 0) + float(r.get("frete") or 0)
                + float(r.get("despesas") or 0) + float(r.get("valor_sub") or 0) + float(r.get("valor_iss") or 0)
            )
            items.append({
                "num_nf": r.get("num_nf"),
                "data_mov": r.get("data_mov").isoformat() if r.get("data_mov") else None,
                "fornecedor": (r.get("fantasia") or "").strip(),
                "qtd": qtd_total,
                "valor_unit": (valor_total / qtd_total) if qtd_total else 0,
                "impostos_unit": (impostos / qtd_total) if qtd_total else 0,
            })
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


async def list_curvas(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_curvas_sync, servidor, banco)


async def list_ressuprimento(
    servidor: str, banco: str,
    curva_abc: Optional[str] = None, curva_abc_fin: Optional[str] = None,
    fornecedor: Optional[int] = None, nivel: Optional[str] = None,
    abaixo_minimo: bool = False, abaixo_ressuprimento: bool = False, acima_maximo: bool = False,
    zerado_negativo: bool = False,
    order_by: str = "descricao",
) -> dict:
    return await asyncio.to_thread(
        _list_ressuprimento_sync, servidor, banco, curva_abc, curva_abc_fin, fornecedor, nivel,
        abaixo_minimo, abaixo_ressuprimento, acima_maximo, zerado_negativo, order_by,
    )


async def ultimas_compras(servidor: str, banco: str, codigo_int: str) -> dict:
    return await asyncio.to_thread(_ultimas_compras_sync, servidor, banco, codigo_int)


async def resumo_alertas_estoque(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_resumo_alertas_estoque_sync, servidor, banco)


async def atualizar_alertas_estoque(req: AtualizarAlertasEstoqueRequest) -> dict:
    return await asyncio.to_thread(_atualizar_alertas_estoque_sync, req)


def _resolver_fornecedores_e_custos_sync(cur, codigos: list[str]) -> tuple[dict[str, int], dict[str, float]]:
    """Fornecedor preferencial de cada produto = o 1º cadastrado em
    `pecas_fornecedor` (`ORDER BY sequencia`, mesmo critério já usado pelo
    Cadastro de Produtos — não existe coluna "principal"/"padrão" nessa
    tabela). Custo unitário sugerido = `pecas.custo_reposicao` (mesmo
    campo usado como custo em todo o resto do sistema — Pedido/O.S./
    relatórios de margem). Produto sem nenhum fornecedor cadastrado
    simplesmente não aparece no dict de retorno — quem chama decide o que
    fazer (aqui: reportar como "sem_fornecedor" pro usuário resolver
    manualmente)."""
    fornecedor_por_produto: dict[str, int] = {}
    custo_por_produto: dict[str, float] = {}
    if not codigos:
        return fornecedor_por_produto, custo_por_produto
    placeholders = ",".join(["%s"] * len(codigos))
    cur.execute(
        f"SELECT codigo_int, custo_reposicao FROM pecas WHERE codigo_int IN ({placeholders})",
        tuple(codigos),
    )
    for r in cur.fetchall():
        custo_por_produto[(r.get("codigo_int") or "").strip()] = float(r.get("custo_reposicao") or 0)
    for codigo in codigos:
        cur.execute(
            "SELECT TOP 1 fornecedor FROM pecas_fornecedor WHERE peca=%s ORDER BY sequencia",
            (codigo,),
        )
        r = cur.fetchone()
        if r and r.get("fornecedor"):
            fornecedor_por_produto[codigo] = int(r["fornecedor"])
    return fornecedor_por_produto, custo_por_produto


async def gerar_pedidos_ressuprimento(req: GerarPedidosRessuprimentoRequest) -> dict:
    """"Gerar Pedido de Compra" a partir da seleção na tela de Ressuprimento
    — pedido explícito do usuário, 2026-07-20 ("surpresa" sugerida e aceita
    em cima do alerta de estoque na Tela Principal): fecha o ciclo
    alerta → ação sem o comprador digitar tudo de novo numa tela separada.

    Agrupa os produtos selecionados por fornecedor preferencial e cria UM
    Pedido de Compra por fornecedor (situação 'A'/Aberto — rascunho,
    revisável na tela normal de Pedido de Compra antes de aprovar), com a
    quantidade que o chamador sugeriu (ex.: `estoque_ressuprimento - qtd`,
    calculado no frontend a partir do que `_list_ressuprimento_sync` já
    retorna) e o custo de reposição como preço unitário inicial.

    Reaproveita `pedido_compra_service.gravar_cabecalho`/`incluir_item`
    (as MESMAS funções da tela de Pedido de Compra, não duplica a lógica
    de INSERT/validação) — cada pedido/item é sua própria transação
    (mesmo comportamento dessas funções quando chamadas normalmente pela
    tela), então uma falha num item não desfaz os pedidos/itens já
    criados com sucesso antes dele; a resposta relata exatamente o que
    foi criado."""
    itens_validos = [i for i in req.itens if (i.codigo_int or "").strip() and (i.qtd or 0) > 0]
    if not itens_validos:
        return {"success": False, "message": "Selecione ao menos um produto com quantidade válida."}

    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_curva_abc_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        codigos = [i.codigo_int.strip() for i in itens_validos]
        fornecedor_por_produto, custo_por_produto = _resolver_fornecedores_e_custos_sync(cur, codigos)
        cur.close()
    finally:
        conn.close()

    sem_fornecedor = sorted({c for c in codigos if c not in fornecedor_por_produto})
    grupos: dict[int, list] = {}
    for item in itens_validos:
        codigo = item.codigo_int.strip()
        fornecedor = fornecedor_por_produto.get(codigo)
        if fornecedor is None:
            continue
        grupos.setdefault(fornecedor, []).append(item)

    hoje = date.today().isoformat()
    pedidos_criados = []
    for fornecedor, grupo_itens in grupos.items():
        header = await pedido_compra_service.gravar_cabecalho(
            req.servidor, req.banco, None, hoje, fornecedor,
            None, None, None, None, None, None,
            "Gerado automaticamente a partir dos alertas de estoque (Ressuprimento).",
            0, req.usuario_alteracao,
        )
        if not header.get("success"):
            continue
        codigo_pedido = header["codigo"]
        itens_incluidos = 0
        for item in grupo_itens:
            codigo_produto = item.codigo_int.strip()
            custo = custo_por_produto.get(codigo_produto, 0.0)
            r = await pedido_compra_service.incluir_item(
                req.servidor, req.banco, codigo_pedido, codigo_produto, item.qtd, custo, {},
            )
            if r.get("success"):
                itens_incluidos += 1
        pedidos_criados.append({
            "codigo": codigo_pedido, "fornecedor": fornecedor,
            "itens": itens_incluidos, "itens_total": len(grupo_itens),
        })

    return {
        "success": True,
        "pedidos_criados": pedidos_criados,
        "sem_fornecedor": sem_fornecedor,
    }

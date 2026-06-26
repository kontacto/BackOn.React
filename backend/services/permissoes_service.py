"""Serviço do módulo de Permissões.

Modelo de dados (tabela SQL `permissoes`):
  codigo IDENTITY, classe int, nome nvarchar(20), tipo nvarchar(5),
  sistema smallint, tela nvarchar(15), comando nvarchar(15), FORMULARIO nvarchar(30)

Regras:
  • Este projeto = sistema 50.
  • A presença de uma linha (classe, tela, comando) significa PERMITIDO.
  • As permissões ficam ligadas ao GRUPO do usuário (classes_usuarios.codigo == permissoes.classe == usuarios.classe).

O catálogo de telas/ações é declarativo (abaixo): ao adicionar uma nova tela ou
ação aqui, ela aparece automaticamente na árvore do app — sem cadastro manual.
"""
import asyncio

from db.connection import _open_conn
from models.permissoes import SalvarPermissoesRequest

SISTEMA = 50

# Ações (botões) padrão de cada tela — pedido do usuário (5a).
ACOES_PADRAO = [
    ("ABRIR", "Abrir Tela"),
    ("GRAVAR", "Gravar"),
    ("EXCLUIR", "Excluir"),
    ("IMPRIMIR", "Imprimir"),
    ("EXPORTAR", "Exportar"),
]


# Ações específicas da tela de Pedido (reflete TODOS os botões reais da tela).
# Obs.: o Pedido NÃO pode ser excluído — sua SITUAÇÃO é que muda
# (Aberto/Fechado/Faturado/Cancelado), por isso há "Alterar situação" e não "Excluir".
ACOES_PEDIDO = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar pedido"),
    ("WHATSAPP", "Enviar por WhatsApp"),
    ("ADD_ITEM", "Adicionar item"),
    ("EDIT_ITEM", "Editar item"),
    ("DEL_ITEM", "Excluir item"),
    ("DESC_ITEM", "Desconto no item"),
    ("DESC_GERAL", "Desconto geral"),
    ("VER_DESCONTOS", "Ver descontos"),
    ("ANALISE", "Analisar margem"),
    ("SITUACAO", "Alterar situação"),
]


# Ações da Ordem de Serviço (os / os_produto). Vendedor e executor são por item.
ACOES_OS = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar OS"),
    ("WHATSAPP", "Enviar por WhatsApp"),
    ("ADD_ITEM", "Adicionar item"),
    ("EDIT_ITEM", "Editar item"),
    ("DEL_ITEM", "Excluir item"),
    ("DESC_ITEM", "Desconto no item"),
    ("VER_DESCONTOS", "Ver descontos"),
    ("ANALISE", "Analisar margem"),
    ("SITUACAO", "Alterar situação"),
]


def _tela(tela: str, nome: str, acoes=ACOES_PADRAO) -> dict:
    return {
        "tipo": "TELA",
        "tela": tela,
        "comando": "",
        "nome": nome,
        "children": [
            {"tipo": "BOTAO", "tela": tela, "comando": c, "nome": lbl, "children": []}
            for c, lbl in acoes
        ],
    }


def _menu(tela: str, nome: str, telas: list) -> dict:
    return {"tipo": "MENU", "tela": tela, "comando": "", "nome": nome, "children": telas}


# Árvore declarativa (Menu > Tela > Botões).
CATALOGO = [
    _menu("CADASTROS", "Cadastros", [
        _tela("CLIENTE", "Clientes"),
        _tela("PRODUTO", "Produtos & Serviços"),
    ]),
    _menu("MOVIMENTO", "Movimento", [
        _tela("PEDIDO", "Pedidos", ACOES_PEDIDO),
        _tela("OS", "Ordem de Serviço", ACOES_OS),
    ]),
    _menu("GERENCIAL", "Gerencial", [
        _tela("GERENCIAL", "Painel Gerencial", [
            ("TOTAIS", "Ver totais do dia"),
            ("MARGEM", "Ver margem média"),
            ("DESCONTOS", "Ver descontos concedidos"),
            ("TODOS_VEND", "Ver todos os vendedores"),
        ]),
    ]),
    _menu("RELATORIOS", "Relatórios", [
        _tela("REL_PEDIDOS", "Relatório de Pedidos"),
        _tela("REL_DESCONTOS", "Descontos & Margem"),
        _tela("REL_OS", "Relatório de OS"),
        _tela("REL_OS_DESCONTOS", "OS · Descontos & Margem"),
    ]),
    _menu("CONFIG", "Configurações", [
        _tela("CONEXAO", "Conexões"),
    ]),
]


# ---------------- DB ----------------
def tem_permissao(cur, classe: int, tela: str, comando: str) -> bool:
    """True se existe a linha (classe, sistema=50, tela, comando) em `permissoes`.
    Usa um cursor já aberto (mesma transação)."""
    cur.execute(
        "SELECT TOP 1 1 AS ok FROM permissoes "
        "WHERE sistema=%s AND classe=%s AND tela=%s AND comando=%s",
        (SISTEMA, classe, tela, comando),
    )
    return cur.fetchone() is not None


def _list_classes_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, classe FROM classes_usuarios ORDER BY classe")
        items = [
            {"codigo": int(r["codigo"]), "classe": (r.get("classe") or "").strip()}
            for r in cur.fetchall()
        ]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _list_permissoes_sync(servidor: str, banco: str, classe: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT tipo, tela, ISNULL(comando,'') AS comando "
            "FROM permissoes WHERE sistema = %s AND classe = %s",
            (SISTEMA, classe),
        )
        items = [
            {
                "tipo": (r.get("tipo") or "").strip(),
                "tela": (r.get("tela") or "").strip(),
                "comando": (r.get("comando") or "").strip(),
            }
            for r in cur.fetchall()
        ]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _salvar_sync(payload: SalvarPermissoesRequest) -> dict:
    try:
        conn = _open_conn(payload.servidor, payload.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor()
        # Estratégia idempotente: limpa as permissões desta classe/sistema e
        # reinsere apenas as marcadas (presença = permitido).
        cur.execute(
            "DELETE FROM permissoes WHERE sistema = %s AND classe = %s",
            (SISTEMA, payload.classe),
        )
        for it in payload.itens:
            cur.execute(
                "INSERT INTO permissoes (classe, nome, tipo, sistema, tela, comando, FORMULARIO) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    payload.classe,
                    (it.nome or "")[:20],
                    (it.tipo or "")[:5],
                    SISTEMA,
                    (it.tela or "")[:15],
                    (it.comando or "")[:15],
                    (it.formulario or it.tela or "")[:30],
                ),
            )
        conn.commit()
        gravadas = len(payload.itens)
        cur.close()
        conn.close()
        return {"success": True, "message": f"{gravadas} permissão(ões) salva(s).", "total": gravadas}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao salvar: {e}"}


async def list_classes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_classes_sync, servidor, banco)


async def list_permissoes(servidor: str, banco: str, classe: int) -> dict:
    return await asyncio.to_thread(_list_permissoes_sync, servidor, banco, classe)


async def salvar_permissoes(payload: SalvarPermissoesRequest) -> dict:
    return await asyncio.to_thread(_salvar_sync, payload)


# ---------------- Filtro por módulos (controle_configuracao) ----------------
def disabled_telas(flags: dict) -> set:
    """Telas desligadas por módulo (flag controle_configuracao = False)."""
    from services.controle_config_service import MODULE_TELAS

    disabled = set()
    for modulo, telas in MODULE_TELAS.items():
        if not flags.get(modulo, False):
            disabled.update(telas)
    # Ordem de Serviço: habilitada se Oficina OU Assistência estiver ligada.
    if not (flags.get("Oficina", False) or flags.get("Assistencia", False)):
        disabled.add("OS")
    return disabled


def filter_catalogo(disabled: set) -> list:
    """Remove telas desligadas; menus que ficam sem telas também somem."""
    out = []
    for menu in CATALOGO:
        telas = [t for t in menu["children"] if t["tela"] not in disabled]
        if telas:
            novo = dict(menu)
            novo["children"] = telas
            out.append(novo)
    return out

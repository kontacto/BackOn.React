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
        _tela("PEDIDO", "Pedidos"),
    ]),
    _menu("RELATORIOS", "Relatórios", [
        _tela("REL_PEDIDOS", "Relatório de Pedidos"),
        _tela("REL_DESCONTOS", "Descontos & Margem"),
    ]),
    _menu("CONFIG", "Configurações", [
        _tela("CONEXAO", "Conexões"),
    ]),
]


# ---------------- DB ----------------
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

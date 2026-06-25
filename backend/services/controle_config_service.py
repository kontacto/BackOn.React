"""Serviço de Módulos e Recursos (tabela `controle_configuracao`, registro único).

Cada coluna `bit` libera (1) ou bloqueia (0) um módulo/recurso do sistema para a
empresa. Estes flags SOBREPÕEM as permissões de grupo: se o módulo estiver
desligado aqui, ele some do sistema inteiro (inclusive da árvore de permissões),
independente do que o grupo tiver liberado.

Somente o usuário KONTACTO acessa/edita esta tela (regra aplicada no app).
"""
import asyncio

from db.connection import _open_conn

# Colunas bit (módulos/recursos) com rótulos amigáveis, na ordem de exibição.
CAMPOS = [
    ("Pedido_venda", "Pedido de Venda"),
    ("orcamento", "Orçamento"),
    ("Clientes", "Clientes"),
    ("Fornecedores", "Fornecedores"),
    ("Estoque", "Estoque"),
    ("Locais_Estoque", "Locais de Estoque"),
    ("inventario", "Inventário"),
    ("devolucao", "Devolução"),
    ("requisicao", "Requisição"),
    ("kits", "Kits"),
    ("servicos", "Serviços"),
    ("contratos", "Contratos"),
    ("Curva_abc", "Curva ABC"),
    ("grade", "Grade"),
    ("digita_total", "Digita Total"),
    ("metro_quadrado", "Metro Quadrado"),
    ("exportacao_normal", "Exportação Normal"),
    ("exportacao_codigo", "Exportação por Código"),
    ("Oficina", "Oficina"),
    ("Assistencia", "Assistência"),
    ("Cilindro", "Cilindro"),
    ("Posto", "Posto"),
    ("Bar", "Bar"),
    ("Livraria", "Livraria"),
    ("biroska", "Biroska"),
    ("CLINICA", "Clínica"),
    ("EVENTOS", "Eventos"),
    ("gestor_projetos", "Gestor de Projetos"),
    ("CONTROLA_CARTOES", "Controla Cartões"),
    ("CONTROLA_ABERTURA_DIA", "Controla Abertura do Dia"),
    ("caixa_analitico", "Caixa Analítico"),
    ("kash", "Kash"),
    ("sped", "SPED"),
    ("emite_mdfe", "Emite MDF-e"),
    ("sefin_nacional", "SEFIN Nacional"),
    ("TSO", "TSO"),
    ("DMC", "DMC"),
    ("Alterdata", "Alterdata"),
]

_CAMPOS_SET = {c for c, _ in CAMPOS}

# Mapa: módulo (coluna) -> telas do catálogo de permissões que ele controla.
# Conforme novos módulos forem desenvolvidos, adicionar aqui.
MODULE_TELAS = {
    "Pedido_venda": ["PEDIDO"],
    "Clientes": ["CLIENTE"],
}


def _read_config_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "valores": {}}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 * FROM controle_configuracao")
        row = cur.fetchone() or {}
        valores = {c: bool(row.get(c)) for c, _ in CAMPOS}
        cur.close()
        conn.close()
        return {"success": True, "valores": valores}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "valores": {}}


def _save_config_sync(servidor: str, banco: str, valores: dict) -> dict:
    campos = [(c, valores[c]) for c in valores if c in _CAMPOS_SET]
    if not campos:
        return {"success": False, "message": "Nenhum campo válido para salvar."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor()
        sets = ", ".join(f"[{c}] = %s" for c, _ in campos)
        params = [1 if v else 0 for _, v in campos]
        cur.execute(f"UPDATE controle_configuracao SET {sets}", tuple(params))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Módulos e recursos salvos."}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao salvar: {e}"}


async def read_config(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_read_config_sync, servidor, banco)


async def save_config(servidor: str, banco: str, valores: dict) -> dict:
    return await asyncio.to_thread(_save_config_sync, servidor, banco, valores)

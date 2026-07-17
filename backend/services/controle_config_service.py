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

# "Bar", "Cilindro" e "Pedido de Venda" são 3 versões diferentes da mesma tela
# de Pedido de Venda (segmentos de negócio distintos) — mutuamente exclusivos,
# nunca mais de um ligado ao mesmo tempo. [GLOBAL], 2026-07-15, user-directed.
# Reforço aqui é defesa em profundidade — a tela já impede isso interativamente
# (marcar um desmarca os outros dois), ver modulos-recursos.tsx.
SEGMENTOS_PEDIDO_EXCLUSIVOS = ["Bar", "Cilindro", "Pedido_venda"]

# Mapa: módulo (coluna) -> telas do catálogo de permissões que ele controla.
# Conforme novos módulos forem desenvolvidos, adicionar aqui.
#
# "PEDIDO" (tela "Pedido Bar") e "PEDIDO_COMP" (tela "Pedido Completo") são as
# duas versões da tela de Pedido de Venda ligadas aos segmentos mutuamente
# exclusivos acima ([GLOBAL], 2026-07-15, user-directed): com o módulo "Bar"
# ligado, só "Pedido Bar" aparece no catálogo de permissões; com "Pedido de
# Venda" ligado, só "Pedido Completo" aparece — nunca os dois ao mesmo tempo,
# já que Bar/Pedido_venda são exclusivos entre si (SEGMENTOS_PEDIDO_EXCLUSIVOS
# acima). Cilindro tem sua própria versão de Pedido (ver unificação Pedido de
# Cilindro em CLAUDE.md) mas ainda não trocou de tela própria — segue sem
# entrada aqui até essa unificação ser implementada.
MODULE_TELAS = {
    "Pedido_venda": ["PEDIDO_COMP"],
    "Bar": ["PEDIDO"],
    "Clientes": ["CLIENTE"],
    "servicos": ["SERVICO", "TIPO_SERVICO"],
    "Posto": [
        "POSTO_BOMBA", "POSTO_ENCERR", "POSTO_AFERICAO", "POSTO_FEC_TURNO",
        "POSTO_REA_TURNO", "POSTO_META", "POSTO_COMBUST", "POSTO_ESTOQUE",
        "POSTO_CUSTO", "POSTO_ILHA", "POSTO_TANQUE", "POSTO_TQ_EST", "POSTO_TQ_NF",
    ],
    "Cilindro": ["CILINDRO", "CIL_CLIENTE", "CILINDRO_SERIE", "BORDERO_CIL"],
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
    ligados = [c for c, v in campos if v and c in SEGMENTOS_PEDIDO_EXCLUSIVOS]
    if len(ligados) > 1:
        return {
            "success": False,
            "message": "Bar, Cilindro e Pedido de Venda são segmentos diferentes da mesma "
                       "tela de Pedido de Venda — só um pode ficar ativo por vez.",
        }
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

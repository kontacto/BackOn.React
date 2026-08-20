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
    # **Correção 2026-08-20, user-directed**: uma tentativa anterior, no
    # mesmo dia, reaproveitou esta coluna como módulo "NFCe" — ERRADO,
    # revertido. Rastreio da fonte real (`Geral\FrmGerKon.frm`, "Módulos do
    # Cliente", confirmado contra `backon.vbp`) mostrou que `DMC` nunca foi
    # campo fiscal: é "Exportação do DMC Combustíveis" (ligado a Posto),
    # ainda gravado/exibido/reportado por e-mail de auditoria pela tela VB6
    # viva — reaproveitar geraria cross-talk visível com o legado rodando
    # em paralelo sobre o mesmo banco. Ver CLAUDE.md > "Sempre checar regras
    # reais de controle/controle_aux/controle_configuracao" pro racional
    # completo. Rótulo alinhado à caption real do legado ("DMC (Posto)").
    ("DMC", "DMC (Posto)"),
    ("Alterdata", "Alterdata"),
    # Grupo "Automação Comercial" (2026-08-10, user-directed) — balança
    # conectada ao caixa (leitura ao vivo, protocolo compatível Toledo) e
    # balança de pré-pesagem com etiqueta (carga de PLU via MGV6/MGV7).
    # Únicas colunas GENUINAMENTE novas desta tabela até hoje — todo o resto
    # de CAMPOS já vinha do schema legado VB6 (ver _ensure_balanca_cols).
    ("balanca_toledo", "Balança Toledo"),
    ("balanca_pre_pesagem", "Balança de Pré-Pesagem (Etiqueta)"),
]

_CAMPOS_SET = {c for c, _ in CAMPOS}

# Campos fiscais que JÁ EXISTIAM no legado, mas numa tabela IRMÃ
# (`controle_aux`, não `controle_configuracao`) — achado 2026-08-20,
# user-directed, rastreando `Geral\FrmGerKon.frm` ("Módulos do Cliente")
# depois que uma tentativa anterior tinha criado colunas novas por engano
# (ver CLAUDE.md > "Sempre checar regras reais de controle/controle_aux/
# controle_configuracao"). Mesmo formulário VB6 grava a maioria dos
# checkboxes em `controle_configuracao` (`tbconfig`) mas estes 3
# especificamente em `controle_aux` (`tbconfig2`) — por isso vivem numa
# lista separada aqui, mas aparecem pro frontend misturados com `CAMPOS`
# (mesma UX, tabela de origem é um detalhe de implementação).
CAMPOS_CONTROLE_AUX = [
    ("emite_nfce", "NFCe"),
    # "NFe via Webservice" no legado — também liga `imprime_nfe` junto
    # (`FrmGerKon.frm`), não replicado aqui (fora do escopo desta correção,
    # sem consumidor Python ainda).
    ("nfe_ws", "NFe (Webservice)"),
    ("emite_nfse", "NFSe (via PC-RJ)"),
]
_CAMPOS_CONTROLE_AUX_SET = {c for c, _ in CAMPOS_CONTROLE_AUX}

# "Bar", "Cilindro", "Pedido de Venda", "Metro Quadrado" e "Clínica" são 5
# versões/segmentos diferentes da mesma tela de Pedido de Venda — mutuamente
# exclusivos, nunca mais de um ligado ao mesmo tempo. [GLOBAL], 2026-07-15,
# user-directed (Metro Quadrado e Clínica adicionados 2026-07-27, também
# user-directed — rastreados a partir do `frmmanpedfor.frm` legado: cada um
# liga um comportamento próprio dentro da MESMA tela "Pedido Geral"
# — Metro Quadrado habilita Comprimento/Largura + seleção de tipo de preço
# por m² nos itens; Clínica habilita agendamento por item de serviço e
# desdobra quantidade > 1 em linhas individuais agendáveis — não são telas
# à parte). Reforço aqui é defesa em profundidade — a tela já impede isso
# interativamente (marcar um desmarca os outros quatro), ver
# modulos-recursos.tsx.
SEGMENTOS_PEDIDO_EXCLUSIVOS = ["Bar", "Cilindro", "Pedido_venda", "metro_quadrado", "CLINICA"]

# Mapa: módulo (coluna) -> telas do catálogo de permissões que ele controla.
# Conforme novos módulos forem desenvolvidos, adicionar aqui.
#
# "PEDIDO" (tela "Pedido Bar") e "PEDIDO_COMP" (tela "Pedido Geral") são as
# duas versões da tela de Pedido de Venda ligadas aos segmentos mutuamente
# exclusivos acima ([GLOBAL], 2026-07-15, user-directed): com o módulo "Bar"
# ligado, só "Pedido Bar" aparece no catálogo de permissões; com qualquer um
# de "Pedido de Venda"/"Metro Quadrado"/"Clínica" ligado, "Pedido Geral"
# aparece — nunca junto com "Pedido Bar", já que são exclusivos entre si
# (SEGMENTOS_PEDIDO_EXCLUSIVOS acima). Como PEDIDO_COMP precisa ficar
# habilitado se QUALQUER UM dos 3 estiver ligado (não dá pra expressar "OU"
# nesta estrutura de dict, que só faz "E" implícito ao unir os disabled de
# cada módulo), só "Pedido_venda" aparece como chave aqui — a correção pro
# caso Metro Quadrado/Clínica ligado é feita explicitamente logo abaixo, em
# `disabled_telas()` (permissoes_service.py), do mesmo jeito que a regra de
# Ordem de Serviço (Oficina OU Assistência) já faz. Cilindro tem sua própria
# versão de Pedido (ver unificação Pedido de Cilindro em CLAUDE.md) mas
# ainda não trocou de tela própria — segue sem entrada aqui até essa
# unificação ser implementada.
MODULE_TELAS = {
    "Pedido_venda": ["PEDIDO_COMP"],
    # "MODIFICADORES" (Tabelas Auxiliares > Modificadores) entrou aqui
    # 2026-07-23, user-directed: "colocar o modificador ligado ao módulo de
    # Pedido Bar. Só aparecerá para esse módulo ativo em configurações" —
    # hoje o único lugar com o seletor de modificador na venda é o Pedido
    # Bar (ver modificadores_service.py e PENDENCIAS.md > "Modificadores").
    "Bar": ["PEDIDO", "MODIFICADORES"],
    "Clientes": ["CLIENTE"],
    "servicos": ["SERVICO", "TIPO_SERVICO"],
    "Posto": [
        "POSTO_BOMBA", "POSTO_ENCERR", "POSTO_AFERICAO", "POSTO_FEC_TURNO",
        "POSTO_REA_TURNO", "POSTO_META", "POSTO_COMBUST", "POSTO_ESTOQUE",
        "POSTO_CUSTO", "POSTO_ILHA", "POSTO_TANQUE", "POSTO_TQ_EST", "POSTO_TQ_NF",
    ],
    "Cilindro": ["CILINDRO", "CIL_CLIENTE", "CILINDRO_SERIE", "BORDERO_CIL"],
    # "Contratos" (2026-07-19, user-directed) — gateia as telas do
    # submenu Transações > Contratos. FATURAR_CONTR adicionado
    # 2026-07-20 junto com o motor de faturamento.
    "contratos": ["TIPO_CONTRATO", "TIPO_REAJUSTE", "INDICE_REAJUSTE", "CONTR_PROD_DISP", "CONTRATO", "FATURAR_CONTR"],
    # "Curva_abc" (2026-07-19, user-directed — "o módulo Compras deve ser
    # habilitado em Configurações > Módulo Curva ABC") — gateia todo o
    # submenu Transações > Compra. Não existe um flag "Compras" separado;
    # o flag legado já existente pra essa área é literalmente Curva_abc.
    "Curva_abc": ["CURVA_ABC", "GESTAO_COMPRAS", "COTACAO_COMPRA", "PEDIDO_COMPRA"],
    # "gestor_projetos" (2026-08-02, user-directed) — gateia a tela
    # Transações > Gestor de Projetos.
    "gestor_projetos": ["PROJETOS"],
    # "balanca_pre_pesagem" (2026-08-10, user-directed) — gateia o Cadastro
    # de Balanças (Cadastros > Balanças). "balanca_toledo" não entra aqui —
    # não gateia nenhuma tela do catálogo, só muda comportamento em runtime
    # no KPDV (leitura ao vivo de peso).
    "balanca_pre_pesagem": ["BALANCA"],
    # "emite_nfce"/"nfe_ws" (`controle_aux`, campos reais do legado — ver
    # CAMPOS_CONTROLE_AUX acima) — gateiam Gestor NFCe e as 2 telas de
    # emissão de NF-e modelo 55, respectivamente. Emissão de NFC-e/NFS-e
    # via comanda (BOTAO dentro da tela COMANDA, não tela própria) é
    # gateada em runtime (`nfe_fiscal_common.modulo_nfce_ativo_sync`/
    # `modulo_nfe_ativo_sync`), não por MODULE_TELAS.
    "emite_nfce": ["GESTOR_NFCE"],
    "nfe_ws": ["NFE_AGRUPADA", "NFE_AVULSA"],
}


def _ensure_balanca_cols(cur) -> None:
    """`balanca_toledo`/`balanca_pre_pesagem` são as primeiras colunas
    genuinamente novas desta tabela (todo o resto de CAMPOS já vinha do
    schema legado VB6) — este backend atende múltiplas empresas sem executor
    de migração central, então a coluna é criada sob demanda (mesmo padrão
    de `pedido_common._ensure_qtd_pessoas_col`)."""
    for col in ("balanca_toledo", "balanca_pre_pesagem"):
        cur.execute(
            "IF NOT EXISTS (SELECT 1 FROM sys.columns "
            f"WHERE Name='{col}' AND Object_ID=Object_ID('controle_configuracao')) "
            f"ALTER TABLE controle_configuracao ADD {col} BIT NULL"
        )


def _read_config_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "valores": {}}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_balanca_cols(cur)
        conn.commit()
        cur.execute("SELECT TOP 1 * FROM controle_configuracao")
        row = cur.fetchone() or {}
        valores = {c: bool(row.get(c)) for c, _ in CAMPOS}
        # Campos fiscais reais do legado, tabela irmã `controle_aux` (ver
        # CAMPOS_CONTROLE_AUX) — mesclados na mesma resposta, tabela de
        # origem é transparente pro frontend.
        cur.execute("SELECT TOP 1 emite_nfce, nfe_ws, emite_nfse FROM controle_aux")
        row_aux = cur.fetchone() or {}
        for c, _ in CAMPOS_CONTROLE_AUX:
            valores[c] = bool(row_aux.get(c))
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
    campos_aux = [(c, valores[c]) for c in valores if c in _CAMPOS_CONTROLE_AUX_SET]
    if not campos and not campos_aux:
        return {"success": False, "message": "Nenhum campo válido para salvar."}
    ligados = [c for c, v in campos if v and c in SEGMENTOS_PEDIDO_EXCLUSIVOS]
    if len(ligados) > 1:
        return {
            "success": False,
            "message": "Bar, Cilindro, Pedido de Venda, Metro Quadrado e Clínica são segmentos "
                       "diferentes da mesma tela de Pedido de Venda — só um pode ficar ativo por vez.",
        }
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor()
        _ensure_balanca_cols(cur)
        conn.commit()
        if campos:
            sets = ", ".join(f"[{c}] = %s" for c, _ in campos)
            params = [1 if v else 0 for _, v in campos]
            cur.execute(f"UPDATE controle_configuracao SET {sets}", tuple(params))
        if campos_aux:
            sets_aux = ", ".join(f"[{c}] = %s" for c, _ in campos_aux)
            params_aux = [1 if v else 0 for _, v in campos_aux]
            cur.execute(f"UPDATE controle_aux SET {sets_aux}", tuple(params_aux))
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

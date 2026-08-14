"""Motor de Formulário Dinâmico (Cadastro de Layout + Preenchimento) —
`FrmCadLay.frm` (cadastro dos templates) + lógica COMENTADA/desativada de
`FrmPreLay2.frm` usada como especificação funcional (decisão do usuário,
2026-07-28 — mesmo o form estando 82% comentado no legado real, ver
PENDENCIAS.md). Usado primeiro pela Agenda (módulo Clínica), mas desenhado
genérico — qualquer entidade pode reaproveitar as mesmas rotas passando
`entidade`/`codentidade` diferentes.

Escopo desta rodada: só o modo "grade de campos" (`estilo_layout=0`) — o
modo RTF livre (`estilo_layout=1`, editor de texto rico com tags tipo
"[[Nome do Cliente]]") fica de fora (ver PENDENCIAS.md > "Motor de Layout").

**`layout_campos.campo_agrupado` — semântica definida 2026-08-12,
user-directed**: `true` significa "este campo compartilha a mesma linha
visual (2 colunas) com o PRÓXIMO campo da lista" — usado pra preservar a
posição/disposição original de um documento importado via "Importar
Formulário" (ver `_importar_formulario_sync`), que pode ter perguntas
emparelhadas lado a lado. `campo2` continua com seu significado original
(subcampo/qualificador do MESMO campo, ex.: "Peso"/"Kg" — usado só no
cadastro manual), não é reaproveitado pra representar a 2ª pergunta de um
par — cada pergunta emparelhada é sua PRÓPRIA linha em `layout_campos`,
com seu próprio `tipo`/`unidade_medida` (2 perguntas lado a lado podem ter
tipos diferentes, ex.: uma numérica e outra Sim/Não — um único `tipo` por
linha não daria conta disso)."""
import asyncio
import json
import logging
from typing import Optional

from db.connection import _open_conn

_log = logging.getLogger(__name__)

# Modelo padrão do motor de importação por IA — ver "Importar Formulário"
# mais abaixo. Segue a orientação do skill claude-api: usar claude-opus-5
# a menos que o usuário peça outro modelo explicitamente.
_IA_IMPORT_MODEL = "claude-opus-5"
# Preço público da Anthropic por 1M tokens (claude-opus-5) — usado só pra
# estimar o custo de cada chamada de IA exibido na tela (pedido explícito do
# usuário, "MOSTRAR SALDO A CADA USO DO RECURSO"). A API da Anthropic não
# expõe saldo/crédito de conta (isso só existe no Console, aba Billing) —
# então em vez de "saldo restante" mostramos o custo estimado da própria
# chamada, a partir de `response.usage` (tokens realmente consumidos).
_IA_PRECO_ENTRADA_POR_1M = 5.00
_IA_PRECO_SAIDA_POR_1M = 25.00


def _estimar_custo_ia(usage) -> dict:
    tokens_entrada = int(getattr(usage, "input_tokens", 0) or 0)
    tokens_saida = int(getattr(usage, "output_tokens", 0) or 0)
    usd = (tokens_entrada * _IA_PRECO_ENTRADA_POR_1M + tokens_saida * _IA_PRECO_SAIDA_POR_1M) / 1_000_000
    return {"tokens_entrada": tokens_entrada, "tokens_saida": tokens_saida, "usd": round(usd, 4)}


def _friendly_query_error(acao: str, e: Exception) -> str:
    """Traduz uma falha de QUERY (já com conexão aberta — ex.: coluna/tabela
    inexistente, violação de constraint) para uma mensagem em português sem
    jargão técnico, em vez de expor o texto cru do driver (DB-Lib/pymssql)
    direto pro usuário final — mesmo princípio de `friendly_db_error()`
    (`db/connection.py`), que só cobre falha de CONEXÃO. Achado ao vivo
    (2026-08-12): "Erro ao gravar layout: (207, b\"Invalid column name
    'paginas'...\")" chegando cru na tela. O texto técnico completo é
    logado aqui para depuração — só a mensagem devolvida ao cliente muda."""
    _log.warning("Falha ao %s: %s", acao, e, exc_info=True)
    return f"Não foi possível {acao} agora. Tente novamente ou contate o suporte."

# entidade (código fixo do legado, comentário de `frmmanpedfor.frm`/
# `FrmPreLay2.frm`) -> coluna boolean em `layout` que marca esse layout como
# aplicável àquela entidade. Agenda (8) não tem coluna própria — usa vínculo
# por serviço/profissional (`layout_servico`/`layout_profissional`), tratado
# à parte em `_list_possiveis_sync`.
_ENTIDADE_COLUNA = {
    1: "cliente", 2: "fornecedor", 3: "funcionario", 4: "produto",
    5: "servico", 6: "pedido_venda", 7: "os", 9: "contrato",
}
ENTIDADE_AGENDA = 8


def _ensure_layout_paginas_col(cur) -> None:
    """Migração idempotente: coluna `paginas` em `layout` — achada faltando
    ao vivo (2026-08-12, banco de teste KONTACTO), erro cru "Invalid column
    name 'paginas'" ao gravar um Layout novo. A tabela `layout` em si é
    herdada do legado (`FrmCadLay.frm`), mas esta coluna não estava presente
    nesta instalação específica — mesmo cenário de versionamento de schema
    entre clientes que motivou "Cada app precisa se auto-atualizar no banco"
    no CLAUDE.md. Mesmo padrão de `pedido_common._ensure_qtd_pessoas_col`."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='paginas' AND Object_ID=Object_ID('layout')) "
        "ALTER TABLE layout ADD paginas INT NOT NULL DEFAULT 1"
    )


def _to_layout_dict(r: dict) -> dict:
    return {
        "codigo": int(r["codigo"]),
        "descricao": (r.get("descricao") or "").strip(),
        "cliente": bool(r.get("cliente")), "fornecedor": bool(r.get("fornecedor")),
        "funcionario": bool(r.get("funcionario")), "produto": bool(r.get("produto")),
        "servico": bool(r.get("servico")), "pedido_venda": bool(r.get("pedido_venda")),
        "os": bool(r.get("os")), "profissional": bool(r.get("profissional")),
        "contrato": bool(r.get("contrato")),
    }


def _list_layouts_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, descricao, cliente, fornecedor, funcionario, produto, servico, "
            "pedido_venda, os, profissional, contrato FROM layout ORDER BY descricao"
        )
        items = [_to_layout_dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("listar os layouts", e)}


def _save_layout_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return {"success": False, "message": "Descrição do layout é obrigatória."}
    colunas_flag = list(_ENTIDADE_COLUNA.values()) + ["profissional"]
    flags = {c: (1 if dados.get(c) else 0) for c in colunas_flag}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if codigo:
            cur.execute(
                "UPDATE layout SET descricao=%s, cliente=%s, fornecedor=%s, funcionario=%s, produto=%s, "
                "servico=%s, pedido_venda=%s, os=%s, profissional=%s, contrato=%s WHERE codigo=%s",
                (
                    descricao, flags["cliente"], flags["fornecedor"], flags["funcionario"], flags["produto"],
                    flags["servico"], flags["pedido_venda"], flags["os"], flags["profissional"], flags["contrato"],
                    codigo,
                ),
            )
        else:
            cur.execute(
                "INSERT INTO layout (descricao, estilo_layout, layout_impressao, cliente, fornecedor, "
                "funcionario, produto, servico, pedido_venda, os, profissional, contrato, paginas) "
                "OUTPUT INSERTED.codigo VALUES (%s,0,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
                (
                    descricao, flags["cliente"], flags["fornecedor"], flags["funcionario"], flags["produto"],
                    flags["servico"], flags["pedido_venda"], flags["os"], flags["profissional"], flags["contrato"],
                ),
            )
            row = cur.fetchone()
            codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("gravar o layout", e)}


def _importar_formulario_sync(
    servidor: str, banco: str, arquivo_b64: str, media_type: str, nome_arquivo: str,
) -> dict:
    """"Importar Formulário" — usa IA (Claude, Anthropic API) para ler um
    documento pronto (PDF ou foto de um formulário/checklist, ex.: relatório
    de visita técnica) e propor os Campos do Layout automaticamente, em vez
    do usuário digitar cada campo manualmente em "+ Campo". Pedido explícito
    do usuário, 2026-08-12.

    **Só PROPÕE — nunca grava direto.** Devolve a lista de campos sugeridos
    pra tela revisar (e o usuário confirmar/editar/remover) antes de chamar
    `save_campo` campo a campo, um por um, exatamente como o fluxo manual já
    faz — não existe endpoint de gravação em lote separado. Mesma cautela já
    documentada no projeto: nunca confiar cegamente numa extração de IA sem
    revisão humana antes de persistir.

    O `tipo` de cada campo sugerido é restrito (via enum no schema
    estruturado da API) aos tipos JÁ CADASTRADOS em `layout_tipo_campo` neste
    banco — a IA nunca inventa um tipo que não existe no sistema.

    **A chave de API vem de `controle.ANTHROPIC_API_KEY`** (tela "IA Key",
    Configurações > Administração, master-only — ver
    `services/ia_config_service.py`), não de variável de ambiente — decisão
    do usuário 2026-08-12, pra não depender de editar `backend/.env` a mão
    em cada instalação de cliente."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 ANTHROPIC_API_KEY FROM controle")
        row = cur.fetchone()
        api_key = ((row.get("ANTHROPIC_API_KEY") if row else None) or "").strip()
        cur.execute("SELECT tipo FROM layout_tipo_campo ORDER BY codigo")
        tipos = [(r.get("tipo") or "").strip() for r in cur.fetchall() if (r.get("tipo") or "").strip()]
        cur.close()
        conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("carregar os tipos de campo", e)}
    if not api_key:
        return {
            "success": False,
            "message": "A importação por IA não está configurada — cadastre a chave em "
                       "Configurações > Administração > IA Key.",
        }
    if not tipos:
        return {
            "success": False,
            "message": "Nenhum tipo de campo cadastrado neste banco — cadastre ao menos um "
                       "tipo de campo antes de importar um formulário.",
        }

    schema = {
        "type": "object",
        "properties": {
            "campos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "secao": {
                            "type": "string",
                            "description": (
                                "Nome da seção/bloco a que esta pergunta pertence no "
                                "documento original (o título do quadro que a agrupa, ex.: "
                                "'Instalação - Ar Condicionado'). Usado só pra organizar a "
                                "revisão na tela — não corresponde a nenhuma coluna do banco."
                            ),
                        },
                        "campo1": {"type": "string", "description": "Texto da pergunta/campo — UMA pergunta por item, nunca duas juntas."},
                        "tipo": {
                            "type": "string",
                            "enum": tipos,
                            "description": (
                                "Tipo de campo mais adequado, escolhido exatamente entre os "
                                "tipos já cadastrados no sistema. Se a pergunta espera "
                                "resposta binária (ex.: 'está funcionando?', 'foi concluído?') "
                                "e existir um tipo equivalente a Sim/Não na lista, use-o."
                            ),
                        },
                        "unidade_medida": {
                            "type": ["string", "null"],
                            "description": "Unidade de medida da resposta (ex.: m², ºC), se aplicável; null se não houver.",
                        },
                        "agrupar_com_proximo": {
                            "type": "boolean",
                            "description": (
                                "true quando esta pergunta aparece lado a lado com a PRÓXIMA "
                                "pergunta da lista, na MESMA linha/posição do documento "
                                "original (2 colunas) — preserva o layout visual original. "
                                "false quando a pergunta ocupa a linha inteira sozinha."
                            ),
                        },
                    },
                    "required": ["secao", "campo1", "tipo", "unidade_medida", "agrupar_com_proximo"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["campos"],
        "additionalProperties": False,
    }

    is_pdf = (media_type or "").lower() == "application/pdf"
    content_block = (
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": arquivo_b64}}
        if is_pdf
        else {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": arquivo_b64}}
    )
    prompt = (
        "Este documento é um formulário/checklist de atendimento (ex.: relatório de "
        "visita técnica), preenchido ou em branco. Extraia TODAS as perguntas/campos "
        "do documento, UMA por item da lista (nunca combine 2 perguntas num só item).\n\n"
        "ORDEM — a mais importante das regras abaixo: percorra o documento PÁGINA POR "
        "PÁGINA, de CIMA PRA BAIXO e da ESQUERDA PRA DIREITA, exatamente na ordem física "
        "em que cada pergunta aparece no papel — a mesma ordem que um leitor humano "
        "seguiria com o dedo na página. NUNCA reagrupe/reordene perguntas por tipo, por "
        "categoria de resposta (ex.: juntar todas as Sim/Não primeiro) ou por importância "
        "— a posição de cada item na lista de saída tem que corresponder 1:1 à posição "
        "física no documento, seção por seção, na ordem em que as seções aparecem. Se o "
        "documento tiver uma tabela com várias linhas (ex.: lista de peças/materiais "
        "usados), extraia cada CÉLULA de cada LINHA como um item próprio, na mesma ordem "
        "de leitura da tabela (linha 1 completa, depois linha 2, etc.) — nunca resuma ou "
        "pule linhas da tabela.\n\n"
        "SEÇÃO — preserve o agrupamento por seção (cada bloco com título próprio, ex.: "
        "'Instalação - Ar Condicionado' ou 'PASSOS RECOMENDADOS PARA REALIZAÇÃO DO PMOC "
        "1', vira um valor de 'secao') — é só um rótulo pra organizar a revisão na tela, "
        "não motivo pra reordenar itens de seções diferentes.\n\n"
        "POSIÇÃO/DISPOSIÇÃO visual: quando duas perguntas aparecerem lado a lado na "
        "mesma linha do documento (2 colunas), marque 'agrupar_com_proximo=true' na "
        "PRIMEIRA delas — não marque como agrupada uma pergunta que ocupa a linha "
        "inteira sozinha no original.\n\n"
        "IGNORAR: valores de resposta já preenchidos (queremos só a pergunta/rótulo do "
        "campo, não o conteúdo respondido), blocos de assinatura/foto que não são "
        "perguntas de texto, e:\n"
        "1) o cabeçalho de identificação do próprio documento (nome/telefone/"
        "endereço da empresa que emitiu o formulário); 2) dados de identificação do "
        "cliente/atendimento que já existem cadastrados no sistema que vai usar este "
        "formulário — nome do cliente, CPF/CNPJ, e-mail, endereço, telefone, técnico/"
        "quem executou, data/hora do atendimento, status/situação — esses dados são "
        "preenchidos automaticamente pelo sistema a partir do cadastro, não fazem parte "
        "do checklist. Extraia normalmente as perguntas de conteúdo/diagnóstico do "
        "atendimento em si (ex.: relato de execução, itens de checklist técnico), mesmo "
        "que apareçam perto desses dados de identificação no documento — só pule o item "
        "se ele for literalmente um desses dados de identificação, nunca por estar perto "
        "deles."
    )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=_IA_IMPORT_MODEL,
            max_tokens=16000,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": [content_block, {"type": "text", "text": prompt}]}],
        ) as stream:
            response = stream.get_final_message()
        custo = _estimar_custo_ia(response.usage)
        if response.stop_reason == "refusal":
            return {
                "success": False,
                "message": "Não foi possível processar este documento (recusado pelos "
                           "filtros de segurança). Tente outro arquivo.",
                "custo": custo,
            }
        texto = next((b.text for b in response.content if b.type == "text"), "")
        campos = (json.loads(texto) if texto else {}).get("campos") or []
    except Exception as e:
        return {"success": False, "message": _friendly_query_error("importar o formulário", e)}
    return {"success": True, "items": campos, "custo": custo}


def _delete_layout_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM layout_entidade WHERE codlayout=%s", (codigo,))
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Layout já tem preenchimentos — exclusão não permitida."}
        cur.execute("DELETE FROM layout_campos WHERE layout=%s", (codigo,))
        cur.execute("DELETE FROM layout WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("excluir o layout", e)}


def _list_tipos_campo_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, tipo FROM layout_tipo_campo ORDER BY codigo")
        items = [{"codigo": int(r["codigo"]), "tipo": (r.get("tipo") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("listar os tipos de campo", e)}


def _list_campos_sync(servidor: str, banco: str, layout: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT lc.codigo, lc.campo1, lc.campo2, lc.tipo, lc.calculado, lc.calc_campo1, lc.calc_campo2, "
            "lc.operador, lc.valor_minimo, lc.valor_maximo, lc.unidade_medida, lc.decimais, lc.tamanho, "
            "lc.campo_agrupado, ltc.tipo AS tipo_descricao "
            "FROM layout_campos lc JOIN layout_tipo_campo ltc ON ltc.codigo = lc.tipo "
            "WHERE lc.layout=%s ORDER BY lc.codigo",
            (layout,),
        )
        items = [_campo_dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("listar os campos", e)}


def _campo_dict(r: dict) -> dict:
    return {
        "codigo": int(r["codigo"]), "campo1": (r.get("campo1") or "").strip(),
        "campo2": (r.get("campo2") or "").strip(), "tipo": int(r["tipo"]),
        "tipo_descricao": (r.get("tipo_descricao") or "").strip(),
        "calculado": bool(r.get("calculado")),
        "calc_campo1": r.get("calc_campo1"), "calc_campo2": r.get("calc_campo2"),
        "operador": (r.get("operador") or "").strip(),
        "valor_minimo": float(r["valor_minimo"]) if r.get("valor_minimo") is not None else None,
        "valor_maximo": float(r["valor_maximo"]) if r.get("valor_maximo") is not None else None,
        "unidade_medida": (r.get("unidade_medida") or "").strip(),
        "decimais": int(r.get("decimais") or 0), "tamanho": int(r.get("tamanho") or 0),
        "campo_agrupado": bool(r.get("campo_agrupado")),
    }


def _save_campo_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    layout = dados.get("layout")
    campo1 = (dados.get("campo1") or "").strip()
    if not layout or not campo1:
        return {"success": False, "message": "Layout e nome do campo são obrigatórios."}
    campo2 = (dados.get("campo2") or "").strip() or None
    tipo = dados.get("tipo")
    calculado = 1 if dados.get("calculado") else 0
    params = (
        campo1, campo2, tipo, calculado,
        dados.get("calc_campo1"), dados.get("calc_campo2"), (dados.get("operador") or "").strip() or None,
        dados.get("valor_minimo"), dados.get("valor_maximo"), (dados.get("unidade_medida") or "").strip() or None,
        int(dados.get("decimais") or 0), int(dados.get("tamanho") or 0),
        1 if dados.get("campo_agrupado") else 0,
    )
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if codigo:
            cur.execute(
                "UPDATE layout_campos SET campo1=%s, campo2=%s, tipo=%s, calculado=%s, calc_campo1=%s, "
                "calc_campo2=%s, operador=%s, valor_minimo=%s, valor_maximo=%s, unidade_medida=%s, "
                "decimais=%s, tamanho=%s, campo_agrupado=%s WHERE codigo=%s",
                params + (codigo,),
            )
        else:
            cur.execute(
                "INSERT INTO layout_campos (layout, campo1, campo2, tipo, calculado, calc_campo1, calc_campo2, "
                "operador, valor_minimo, valor_maximo, unidade_medida, decimais, tamanho, campo_agrupado) "
                "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (layout,) + params,
            )
            row = cur.fetchone()
            codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("gravar o campo", e)}


def _delete_campo_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM layout_campos WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("excluir o campo", e)}


def _list_possiveis_sync(servidor: str, banco: str, entidade: int, codentidade: int) -> dict:
    """Layouts aplicáveis à entidade. Pra Agenda (8), o legado associa por
    serviço/profissional do próprio agendamento (`layout_servico`/
    `layout_profissional` — réplica de `FrmPreLay2.frm`'s `Case 8`
    comentado), não por um flag direto "agenda" em `layout` (que não
    existe)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if entidade == ENTIDADE_AGENDA:
            cur.execute("SELECT servico, funcionario FROM AGENDA WHERE codagenda=%s", (codentidade,))
            ag = cur.fetchone()
            if not ag:
                cur.close()
                conn.close()
                return {"success": True, "items": []}
            cur.execute(
                "SELECT DISTINCT l.codigo, l.descricao FROM layout l "
                "LEFT JOIN layout_servico ls ON ls.codlayout = l.codigo "
                "LEFT JOIN layout_profissional lp ON lp.codlayout = l.codigo "
                "WHERE ls.servico = %s OR lp.profissional = %s",
                (ag.get("servico"), ag.get("funcionario")),
            )
        else:
            coluna = _ENTIDADE_COLUNA.get(entidade)
            if not coluna:
                cur.close()
                conn.close()
                return {"success": True, "items": []}
            cur.execute(f"SELECT codigo, descricao FROM layout WHERE {coluna}=1 ORDER BY descricao")
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("buscar os layouts disponíveis", e)}


def _list_preenchidos_sync(servidor: str, banco: str, entidade: int, codentidade: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT le.codigo, le.data, l.descricao FROM layout_entidade le "
            "JOIN layout l ON l.codigo = le.codlayout "
            "WHERE le.entidade=%s AND le.codentidade=%s ORDER BY le.codigo DESC",
            (entidade, codentidade),
        )
        items = []
        for r in cur.fetchall():
            data_v = r.get("data")
            items.append({
                "codigo": int(r["codigo"]),
                "descricao": (r.get("descricao") or "").strip(),
                "data": data_v.isoformat() if hasattr(data_v, "isoformat") else str(data_v),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("buscar os preenchimentos", e)}


def _get_preenchimento_sync(servidor: str, banco: str, codigo: int) -> dict:
    """`codigo` é o código de um `layout_entidade` (um preenchimento já
    existente) — monta a lista de campos do layout com o `conteudo` já
    preenchido."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, codlayout, data, obs, obs_descricao FROM layout_entidade WHERE codigo=%s",
            (codigo,),
        )
        le = cur.fetchone()
        if not le:
            cur.close()
            conn.close()
            return {"success": False, "message": "Preenchimento não encontrado."}
        cur.execute(
            "SELECT campo1, campo2, conteudo, codlayoutcampo FROM layout_preenchido WHERE codlayoutentidade=%s",
            (codigo,),
        )
        respostas = {
            int(r["codlayoutcampo"]): (r.get("conteudo") or "")
            for r in cur.fetchall() if r.get("codlayoutcampo") is not None
        }
        cur.execute(
            "SELECT lc.codigo, lc.campo1, lc.campo2, lc.tipo, lc.calculado, lc.calc_campo1, lc.calc_campo2, "
            "lc.operador, lc.valor_minimo, lc.valor_maximo, lc.unidade_medida, lc.decimais, lc.tamanho, "
            "lc.campo_agrupado, ltc.tipo AS tipo_descricao "
            "FROM layout_campos lc JOIN layout_tipo_campo ltc ON ltc.codigo = lc.tipo "
            "WHERE lc.layout=%s ORDER BY lc.codigo",
            (int(le["codlayout"]),),
        )
        campos = [_campo_dict(r) for r in cur.fetchall()]
        for c in campos:
            c["conteudo"] = respostas.get(c["codigo"], "")
        cur.close()
        conn.close()
        data_v = le.get("data")
        return {
            "success": True,
            "codigo": int(le["codigo"]), "codlayout": int(le["codlayout"]),
            "data": data_v.isoformat() if hasattr(data_v, "isoformat") else str(data_v),
            "obs": (le.get("obs") or "").strip(), "obs_descricao": (le.get("obs_descricao") or "").strip(),
            "campos": campos,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("buscar o preenchimento", e)}


def _preencher_sync(servidor: str, banco: str, dados: dict) -> dict:
    """Grava/atualiza um preenchimento — réplica da lógica COMENTADA de
    `FrmPreLay2.frm`'s `Command1_Click` (modo "grade de campos"): sem
    `codigo` (de `layout_entidade`), cria um novo; com `codigo`, apaga e
    regrava as respostas (`layout_preenchido`) — mesmo padrão de
    "replace-all-on-save" já usado em Telefones/Endereços/Contatos do
    Cliente Completo."""
    entidade = dados.get("entidade")
    codentidade = dados.get("codentidade")
    codlayout = dados.get("codlayout")
    codigo = dados.get("codigo")
    respostas = dados.get("respostas") or []  # [{codigo_campo, conteudo}]
    usuario = dados.get("usuario_alteracao") or 0
    obs = (dados.get("obs") or "").strip()
    if not entidade or not codentidade or not codlayout:
        return {"success": False, "message": "Entidade/layout são obrigatórios."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if codigo:
            cur.execute(
                "UPDATE layout_entidade SET data=CAST(GETDATE() AS DATE), obs=%s WHERE codigo=%s",
                (obs, codigo),
            )
            cur.execute("DELETE FROM layout_preenchido WHERE codlayoutentidade=%s", (codigo,))
        else:
            cur.execute(
                "INSERT INTO layout_entidade (entidade, codentidade, codlayout, data, obs, preenchido_por) "
                "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,CAST(GETDATE() AS DATE),%s,%s)",
                (entidade, codentidade, codlayout, obs, usuario),
            )
            row = cur.fetchone()
            codigo = int(row["codigo"] if isinstance(row, dict) else row[0])
        for resp in respostas:
            codigo_campo = resp.get("codigo_campo")
            conteudo = resp.get("conteudo")
            if codigo_campo is None or conteudo in (None, ""):
                continue
            cur.execute(
                "SELECT campo1, campo2, tipo, calculado, calc_campo1, calc_campo2, operador "
                "FROM layout_campos WHERE codigo=%s",
                (codigo_campo,),
            )
            campo = cur.fetchone()
            if not campo:
                continue
            cur.execute(
                "INSERT INTO layout_preenchido (codlayoutentidade, campo1, campo2, conteudo, codlayoutcampo, "
                "tipo, calculado, calc_campo1, calc_campo2, operador) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo, campo.get("campo1"), campo.get("campo2"), str(conteudo), codigo_campo,
                    campo.get("tipo"), campo.get("calculado"), campo.get("calc_campo1"),
                    campo.get("calc_campo2"), campo.get("operador"),
                ),
            )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("salvar o preenchimento", e)}


def _excluir_preenchimento_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Exclui um preenchimento já gravado (`layout_entidade` + suas
    respostas em `layout_preenchido`). Pedido explícito do usuário,
    2026-08-12 — não havia forma de remover um preenchimento errado/de
    teste na tela."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM layout_preenchido WHERE codlayoutentidade=%s", (codigo,))
        cur.execute("DELETE FROM layout_entidade WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly_query_error("excluir o preenchimento", e)}


async def list_layouts(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_layouts_sync, servidor, banco)


async def save_layout(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_layout_sync, servidor, banco, codigo, dados)


async def importar_formulario(
    servidor: str, banco: str, arquivo_b64: str, media_type: str, nome_arquivo: str,
) -> dict:
    return await asyncio.to_thread(
        _importar_formulario_sync, servidor, banco, arquivo_b64, media_type, nome_arquivo,
    )


async def delete_layout(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_layout_sync, servidor, banco, codigo)


async def list_tipos_campo(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipos_campo_sync, servidor, banco)


async def list_campos(servidor: str, banco: str, layout: int) -> dict:
    return await asyncio.to_thread(_list_campos_sync, servidor, banco, layout)


async def save_campo(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_campo_sync, servidor, banco, codigo, dados)


async def delete_campo(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_campo_sync, servidor, banco, codigo)


async def list_possiveis(servidor: str, banco: str, entidade: int, codentidade: int) -> dict:
    return await asyncio.to_thread(_list_possiveis_sync, servidor, banco, entidade, codentidade)


async def list_preenchidos(servidor: str, banco: str, entidade: int, codentidade: int) -> dict:
    return await asyncio.to_thread(_list_preenchidos_sync, servidor, banco, entidade, codentidade)


async def get_preenchimento(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_preenchimento_sync, servidor, banco, codigo)


async def preencher(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_preencher_sync, servidor, banco, dados)


async def excluir_preenchimento(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_excluir_preenchimento_sync, servidor, banco, codigo)

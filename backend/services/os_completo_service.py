"""O.S. Completa (`FrmTraOsNew.frm`) — Fase 1 (núcleo), módulo Assistência
Técnica. Cabeçalho com os campos extras da tela completa (referência,
técnico responsável, tipo O.S., status O.S. via lookup real, previsão/
término, hora de fechamento) além dos já existentes na O.S. Mobile.

Itens, Forma de Pagamento, Desconto Geral, Descontos Concedidos e Análise
de Margem são reaproveitados DIRETO pelas rotas já existentes
(`/api/os/{codigo}/...`, `routes/os.py`) — nenhuma view própria aqui, ver
PENDENCIAS.md > "O.S. Completa". Fechar/Faturar/Reabrir/Cancelar
reaproveitam (import direto) as funções de `os_service.py`, só passando
`tela="OS_COMP"` pra checar a permissão certa — mesmo padrão já usado por
`pedido_completo_service.py` em relação a `pedidos_service.py`.
"""
import asyncio
from datetime import date, timedelta
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc
from models.schemas import OSCompletoSaveRequest, FecharRequest, FaturarOSRequest
from services.constants import SITUACAO_LABEL
from services.pedido_common import (
    _check_cliente_ativo, _check_area_atuacao, _auto_abrir_dia_se_necessario, _chassi_obrigatorio_ok,
    _exige_aprovacao_itens_os_ativo, _exige_expedicao_itens_os_ativo,
    _ensure_os_doc_origem_cols, _ensure_osrevisao_table, _validar_doc_origem,
    _controla_revisao_os_ativo, _exige_os_original_garantia_ativo, _mover_estoque,
    _ensure_os_forma_pagamento_garantia_col,
)
from services.os_itens_service import _recalc_os_total
from services.permissoes_service import tem_permissao
from services import os_service
from services.agenda_service import _validar_disponibilidade, _somar_minutos


def _ensure_os_auxiliar_tecnico_col(cur) -> None:
    """Auxiliar do Técnico (regra 11, AssistenciaTecnicaCampo.md) — campo
    OPCIONAL, só o cadastro nesta rodada (o fluxo completo de "auxiliar
    edita com a credencial do titular" fica pra depois). Sem precedente no
    legado (diferente de `tecnico_responsavel`, coluna original do schema
    — que, achado ao vivo em ARGEN-TESTE, já tem índice `os_2`) — precisa
    de migração de verdade, mesmo padrão de `os_service._ensure_os_
    checkin_cols`.

    Índice incluído na MESMA migração (não uma função separada) — a
    coluna é usada em filtro (`_list_os_sync`'s `tecnico`/`auxiliar`) e na
    restrição de visibilidade (`OS_COMP.VER_TODAS`) desde que nasceu,
    então "coluna nova pra filtro" e "índice pra esse filtro" são uma
    unidade só de migração, não duas."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='auxiliar_tecnico' AND Object_ID=Object_ID('os')) "
        "ALTER TABLE os ADD auxiliar_tecnico INT NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
        "WHERE name='IX_os_auxiliar_tecnico' AND object_id=Object_ID('os')) "
        "CREATE INDEX IX_os_auxiliar_tecnico ON os(auxiliar_tecnico)"
    )


def _ensure_os_codagenda_atendimento_col(cur) -> None:
    """Soft-FK opcional pra `AGENDA.codagenda` — rastreia o compromisso
    REAL da Agenda vinculado ao cabeçalho da OS (não a um item de
    serviço), criado/atualizado por `_sincronizar_agendamento_cabecalho_
    sync` quando "Data Agendada"/"Hora Agendada" são preenchidos
    diretamente em `os-geral.tsx` — user-directed 2026-08-15 ("data e hora
    agendada deverá ser alimentada pela agenda ou imputada diretamente no
    campo de acordo com a disponibilidade da agenda"). Quando setada, tem
    PRECEDÊNCIA sobre a agregação por item (`_recalc_data_agendamento_os_
    sync`, agenda_service.py) — ver comentário lá."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='codagenda_atendimento' AND Object_ID=Object_ID('os')) "
        "ALTER TABLE os ADD codagenda_atendimento INT NULL"
    )


def _sincronizar_agendamento_cabecalho_sync(
    cur, codigo: int, cliente: Optional[int], tecnico_responsavel: Optional[int],
    data_agendamento: Optional[str], hora_agendamento: Optional[str], usuario_alteracao: Optional[int],
) -> tuple[Optional[str], Optional[int]]:
    """Sincroniza Data/Hora Agendada do CABEÇALHO da OS com um compromisso
    REAL na Agenda — user-directed 2026-08-15 ("data e hora agendada
    deverá ser alimentada pela agenda ou imputada diretamente no campo de
    acordo com a disponibilidade da agenda"). Reaproveita só a peça de
    validação do módulo Agenda (`_validar_disponibilidade`) — NÃO
    reaproveita `_salvar_agendamento_sync` literalmente, porque aquela
    função exige um `servico`/checagem de especialidade (agendamento por
    ITEM de serviço), conceito que não existe pra um compromisso de
    cabeçalho (a visita inteira, sem uma linha de serviço específica).

    Retorna `(mensagem_de_erro, novo_codagenda_atendimento)` — chamada de
    dentro de `_save_os_completo_sync` ANTES do UPDATE principal da OS,
    pra poder abortar o Gravar inteiro se a disponibilidade não bater
    (`mensagem_de_erro` não-None). Sem mudança nos campos em relação ao
    que já está gravado: no-op, retorna o `codagenda_atendimento` atual
    sem tocar a Agenda.

    Nota de implementação: diferente do fluxo de agendamento por item
    (`AgendarModal`/`_salvar_agendamento_sync`), esta função NÃO checa
    permissão `OS_COMP.AGENDAR` — `_save_os_completo_sync` não tem acesso
    a `master` (só a `classe`, "só pro log de auditoria" segundo o
    schema) e bloquear por `tem_permissao` sem bypass de master quebraria
    o usuário master (que nunca tem linha própria em `permissoes`, o
    bypass é só frontend — ver "Master Has Full Permission" em
    CLAUDE.md). O Gravar da OS Completa como um todo já é gated só no
    frontend (`can("OS_COMP.GRAVAR")`), mesmo padrão que o resto desta
    função já segue (nenhum outro campo daqui checa permissão granular
    própria)."""
    hora = (hora_agendamento or "").strip()[:5] or None
    data = data_agendamento or None

    cur.execute(
        "SELECT data_agendamento, hora_agendamento, codagenda_atendimento FROM os WHERE codigo=%s",
        (codigo,),
    )
    atual = cur.fetchone() or {}
    data_atual_raw = atual.get("data_agendamento")
    data_atual = data_atual_raw.isoformat() if hasattr(data_atual_raw, "isoformat") else data_atual_raw
    hora_atual = str(atual.get("hora_agendamento") or "").strip()[:5] or None
    codagenda_atual = int(atual["codagenda_atendimento"]) if atual.get("codagenda_atendimento") else None

    if data == data_atual and hora == hora_atual:
        return None, codagenda_atual

    if not data and not hora:
        # Campos limpos — cancela o compromisso existente (mantém como
        # histórico, mesmo padrão de `_cancelar_agendamento_sync`).
        if codagenda_atual:
            cur.execute(
                "UPDATE AGENDA SET SITUACAO_ATENDIMENTO='Desistência' WHERE codagenda=%s",
                (codagenda_atual,),
            )
        return None, None

    if not tecnico_responsavel:
        return "Defina o Técnico Responsável antes de marcar Data/Hora Agendada.", codagenda_atual
    if not data or not hora:
        return "Informe Data e Hora Agendada juntas.", codagenda_atual

    horario, erro = _validar_disponibilidade(cur, tecnico_responsavel, data, hora, excluir_codagenda=codagenda_atual)
    if erro:
        return erro, codagenda_atual

    hora_fim = _somar_minutos(hora, int(horario.get("intervalo1") or 30))
    if codagenda_atual:
        cur.execute(
            "UPDATE AGENDA SET funcionario=%s, cliente=%s, data=%s, hora_ini=%s, hora_fim=%s, "
            "SITUACAO_ATENDIMENTO='Confirmado' WHERE codagenda=%s",
            (tecnico_responsavel, cliente, data, hora, hora_fim, codagenda_atual),
        )
        return None, codagenda_atual

    cur.execute(
        "INSERT INTO AGENDA (funcionario, cliente, data, hora_ini, hora_fim, valor, VALOR_ORIGINAL, "
        "encaixe, revisao, data_agenda, hora_agenda, usuario_agenda, situacao, SITUACAO_ATENDIMENTO, SITUACAO_CAIXA) "
        "OUTPUT INSERTED.codagenda "
        "VALUES (%s,%s,%s,%s,%s,0,0,0,0,GETDATE(),CONVERT(VARCHAR(8),GETDATE(),108),%s,'A','Confirmado','A')",
        (tecnico_responsavel, cliente, data, hora, hora_fim, usuario_alteracao or 0),
    )
    row = cur.fetchone()
    novo_codagenda = int(row["codagenda"] if isinstance(row, dict) else row[0])
    return None, novo_codagenda


def _get_os_completo_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Chama `os_service._get_os_sync` (cabeçalho base) e ENRIQUECE com os
    campos extras da tela completa — mesmo padrão de "só enriquece, sem
    duplicar" já usado pro Nº de Série no Pedido Completo."""
    base = os_service._get_os_sync(servidor, banco, codigo)
    if not base.get("success"):
        return base
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_os_doc_origem_cols(cur)
        _ensure_osrevisao_table(cur)
        _ensure_os_forma_pagamento_garantia_col(cur)
        _ensure_os_auxiliar_tecnico_col(cur)
        _ensure_os_codagenda_atendimento_col(cur)
        cur.execute(
            "SELECT o.referencia_os, o.tecnico_responsavel, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS tecnico_nome, "
            "       o.auxiliar_tecnico, COALESCE(NULLIF(fa.nome_guerra,''), fa.nome) AS auxiliar_nome, "
            "       o.posicao_os, t.descricao AS tipo_os_descricao, "
            "       o.previsao_termino, o.data_termino, o.hora_entrada, o.hora_fechamento, "
            "       o.data_agendamento, o.hora_agendamento, "
            "       s.descricao AS status_os_descricao, "
            "       o.os_original, o.Tipo_Doc_Original, o.VALIDOU_GARANTIA, o.QtdRevisoes, "
            "       o.forma_pagamento_garantia, fpg.descricao AS forma_pagamento_garantia_descricao "
            "FROM os o "
            "LEFT JOIN funcionarios f ON f.codigo_int = o.tecnico_responsavel "
            "LEFT JOIN funcionarios fa ON fa.codigo_int = o.auxiliar_tecnico "
            "LEFT JOIN tipo_os t ON t.codigo = o.posicao_os "
            "LEFT JOIN status_os s ON s.codigo = o.status_os "
            "LEFT JOIN forma_pagamento fpg ON fpg.codigo = o.forma_pagamento_garantia "
            "WHERE o.codigo=%s",
            (codigo,),
        )
        row = cur.fetchone()
        # Flags de empresa que decidem se a aba "Autorização de Itens" deve
        # aparecer no frontend e se os itens reservam estoque na inclusão
        # ou só na Autorização (ver os_itens_service._add_item_sync).
        exige_aprovacao = _exige_aprovacao_itens_os_ativo(cur)
        exige_expedicao = _exige_expedicao_itens_os_ativo(cur)
        # Flags que decidem se os campos "Doc. Origem"/"Tipo" aparecem
        # habilitados no frontend pro Tipo O.S. atual (ver
        # `pedido_common._validar_doc_origem` — a mesma decisão de ramo
        # replicada aqui só pra exibição, o backend revalida tudo de novo
        # no Gravar).
        controla_revisao_os = _controla_revisao_os_ativo(cur)
        exige_os_original_garantia = _exige_os_original_garantia_ativo(cur)
        # Doc. Origem / Revisão Programada — lista de datas geradas por ESTA
        # O.S. (`osrevisao.os = codigo`), disponível (`osrevisao=0`) ou já
        # consumida por outra O.S. (mostra o código de quem consumiu, mesmo
        # padrão do combo `RevisoesOS` do legado).
        cur.execute(
            "SELECT sequencia, data, osrevisao FROM osrevisao WHERE os=%s ORDER BY data", (codigo,),
        )
        revisoes = [
            {
                "sequencia": int(r["sequencia"]),
                "data": r["data"].isoformat() if hasattr(r.get("data"), "isoformat") else str(r.get("data")),
                "consumida_por": int(r["osrevisao"]) if r.get("osrevisao") else None,
            }
            for r in cur.fetchall()
        ]
        cur.close()
        conn.close()
        base["os"]["exige_aprovacao_itens_os"] = exige_aprovacao
        base["os"]["exige_expedicao_itens_os"] = exige_expedicao
        base["os"]["controla_revisao_os"] = controla_revisao_os
        base["os"]["exige_os_original_garantia"] = exige_os_original_garantia
        base["os"]["revisoes_programadas"] = revisoes
        if row:
            base["os"]["referencia_os"] = (row.get("referencia_os") or "").strip()
            base["os"]["tecnico_responsavel"] = (
                int(row["tecnico_responsavel"]) if row.get("tecnico_responsavel") else None
            )
            base["os"]["tecnico_responsavel_nome"] = (row.get("tecnico_nome") or "").strip()
            base["os"]["auxiliar_tecnico"] = (
                int(row["auxiliar_tecnico"]) if row.get("auxiliar_tecnico") else None
            )
            base["os"]["auxiliar_tecnico_nome"] = (row.get("auxiliar_nome") or "").strip()
            base["os"]["posicao_os"] = int(row["posicao_os"]) if row.get("posicao_os") is not None else None
            base["os"]["tipo_os_descricao"] = (row.get("tipo_os_descricao") or "").strip()
            base["os"]["previsao_termino"] = (
                row["previsao_termino"].isoformat() if row.get("previsao_termino") else None
            )
            base["os"]["data_termino"] = row["data_termino"].isoformat() if row.get("data_termino") else None
            base["os"]["hora_entrada"] = (row.get("hora_entrada") or "").strip()
            base["os"]["hora_fechamento"] = (row.get("hora_fechamento") or "").strip()
            base["os"]["data_agendamento"] = (
                row["data_agendamento"].isoformat() if row.get("data_agendamento") else None
            )
            base["os"]["hora_agendamento"] = str(row.get("hora_agendamento") or "").strip()[:5]
            base["os"]["status_os_descricao"] = (row.get("status_os_descricao") or "").strip()
            base["os"]["os_original"] = int(row["os_original"]) if row.get("os_original") else None
            base["os"]["tipo_doc_original"] = (row.get("Tipo_Doc_Original") or "").strip() or None
            base["os"]["validou_garantia"] = bool(row.get("VALIDOU_GARANTIA"))
            base["os"]["qtd_revisoes"] = int(row["QtdRevisoes"]) if row.get("QtdRevisoes") else None
            base["os"]["forma_pagamento_garantia"] = (row.get("forma_pagamento_garantia") or "").strip()
            base["os"]["forma_pagamento_garantia_descricao"] = (
                row.get("forma_pagamento_garantia_descricao") or ""
            ).strip()
        return base
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def get_os_completo(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_os_completo_sync, servidor, banco, codigo)


def _save_os_completo_sync(req: OSCompletoSaveRequest, codigo: Optional[int]) -> dict:
    """Implementação própria (não delega a `os_service._save_os_sync`) —
    mesmo padrão já usado por `pedido_completo_service._save_pedido_completo_sync`
    em relação a `pedidos_service._save_pedido_sync`: os campos extras
    fazem parte do mesmo INSERT/UPDATE, evitando uma segunda instrução que
    arriscaria sobrescrever `hora_entrada` (gravada automaticamente via
    `GETDATE()` na criação)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_os_doc_origem_cols(cur)
        _ensure_osrevisao_table(cur)
        _ensure_os_forma_pagamento_garantia_col(cur)
        _ensure_os_auxiliar_tecnico_col(cur)
        _ensure_os_codagenda_atendimento_col(cur)

        if codigo is not None:
            cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "OS não encontrada."}
            sit_atual = (ex.get("situacao") or "").strip().upper()
            if sit_atual != "A":
                conn.close()
                label = SITUACAO_LABEL.get(sit_atual, sit_atual)
                return {"success": False, "message": f"OS com situação '{label}' não pode ser alterada."}
        else:
            ok, label = _check_cliente_ativo(cur, req.cliente)
            if not ok:
                conn.close()
                return {
                    "success": False,
                    "message": f"Cliente com situação '{label}' não pode gerar nova O.S.",
                }
            ok, label = _check_area_atuacao(cur, req.usuario_alteracao, req.area_atuacao)
            if not ok:
                conn.close()
                return {
                    "success": False,
                    "message": f"Você não está vinculado à Área de Atuação '{label}' — não é possível abrir O.S. nela.",
                }
            _auto_abrir_dia_se_necessario(cur)

        # Doc. Origem / Revisão Programada (`FrmTraOsNew.frm`, `Campo(150)`/
        # `Campo(151)`/`Option9`/`Option10`) — validação cruzada de OS/Pedido
        # de origem só se aplica quando o Tipo O.S. escolhido é Garantia/
        # Revisão E o respectivo flag de empresa está ligado (ver
        # `_validar_doc_origem`, pedido_common.py). `req.posicao_os is None`
        # (nenhum Tipo O.S. escolhido) pula a validação inteira, sem query
        # extra — mesmo comportamento de "campo novo, sem tipo definido
        # ainda não valida nada".
        tipo_os_desc = ""
        if req.posicao_os is not None:
            cur.execute("SELECT descricao FROM tipo_os WHERE codigo=%s", (req.posicao_os,))
            trow = cur.fetchone()
            tipo_os_desc = (trow.get("descricao") or "").strip() if trow else ""

        os_original = int(req.os_original) if req.os_original else 0
        tipo_doc_original = (req.tipo_doc_original or "O").strip().upper()
        if tipo_doc_original not in ("O", "P"):
            tipo_doc_original = "O"
        qtd_revisoes = int(req.qtd_revisoes) if req.qtd_revisoes else 0

        validou_garantia = False
        if tipo_os_desc:
            ok_doc, validou_garantia, tipo_doc_original, erro_doc = _validar_doc_origem(
                cur, codigo, req.cliente, tipo_os_desc, os_original, tipo_doc_original, req.autorizado_por,
            )
            if not ok_doc:
                conn.close()
                return {"success": False, "message": erro_doc, "requer_autorizacao": True}

        sizes = _get_col_sizes(conn, req.banco, "os")
        descricao_cliente = req.descricao_cliente or ""
        obs = req.obs or ""
        resumo = req.resumo or ""
        placa = _trunc(req.placa or "", sizes, "placa", 8)
        marca = _trunc(req.marca or "", sizes, "marca", 3)
        modelo = _trunc(req.modelo or "", sizes, "modelo", 3)
        ano = _trunc(req.ano or "", sizes, "ano", 9)
        chassi = _trunc(req.chassi or "", sizes, "chassi", 20)
        if not _chassi_obrigatorio_ok(cur, chassi):
            conn.close()
            return {"success": False, "message": "Chassi é obrigatório para O.S. do segmento Oficina."}
        num_serie = _trunc(req.numero_de_serie or "", sizes, "numero_de_serie", 20)
        km = int(req.km) if req.km is not None else 0
        status_os = req.status_os if req.status_os is not None else 0
        situacao = (req.situacao or "A").strip().upper() if req.situacao else "A"
        forma_pagamento = (req.forma_pagamento or "")[:3]
        forma_pagamento_garantia = (req.forma_pagamento_garantia or "")[:3] or None
        referencia = _trunc(req.referencia_os or "", sizes, "REFERENCIA_OS", 20)
        previsao_termino = req.previsao_termino or None
        data_termino = req.data_termino or None
        hora_fechamento = (req.hora_fechamento or "").strip() or None
        data_agendamento = req.data_agendamento or None
        hora_agendamento = (req.hora_agendamento or "").strip() or None

        if codigo is None:
            cur.execute("SELECT ISNULL(MAX(codigo),0)+1 AS novo FROM os")
            novo = int(cur.fetchone()["novo"] or 1)
            cur.execute(
                "INSERT INTO os "
                "(codigo, cliente, data_entrada, hora_entrada, situacao, valor, "
                " area_atuacao, descricao_cliente, obs, resumo, status_os, atendente, "
                " placa, marca, modelo, km, ano, chassi, numero_de_serie, forma_pagamento, "
                " forma_pagamento_garantia, referencia_os, tecnico_responsavel, auxiliar_tecnico, posicao_os, previsao_termino, "
                " data_termino, hora_fechamento, data_agendamento, hora_agendamento, OS_ORIGINAL, Tipo_Doc_Original, "
                " VALIDOU_GARANTIA, QtdRevisoes) "
                "VALUES (%s, %s, CAST(GETDATE() AS DATE), CONVERT(NVARCHAR(8), GETDATE(), 108), "
                "        %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    novo, req.cliente, situacao, req.area_atuacao, descricao_cliente, obs, resumo,
                    status_os, req.atendente, placa, marca, modelo, km, ano, chassi, num_serie, forma_pagamento,
                    forma_pagamento_garantia, referencia, req.tecnico_responsavel, req.auxiliar_tecnico, req.posicao_os, previsao_termino,
                    data_termino, hora_fechamento, data_agendamento, hora_agendamento, os_original, tipo_doc_original,
                    1 if validou_garantia else 0, qtd_revisoes,
                ),
            )
            os_id = novo
        else:
            # Data/Hora Agendada — sincroniza com um compromisso REAL na
            # Agenda ANTES do UPDATE principal, pra poder abortar o Gravar
            # inteiro se a disponibilidade do Técnico Responsável não
            # bater (user-directed 2026-08-15, ver função pra detalhe).
            erro_agenda, codagenda_atendimento = _sincronizar_agendamento_cabecalho_sync(
                cur, codigo, req.cliente, req.tecnico_responsavel,
                data_agendamento, hora_agendamento, req.usuario_alteracao,
            )
            if erro_agenda:
                conn.rollback()
                conn.close()
                return {"success": False, "message": erro_agenda}
            cur.execute(
                "UPDATE os SET cliente=%s, area_atuacao=%s, descricao_cliente=%s, obs=%s, "
                " resumo=%s, status_os=%s, atendente=%s, situacao=%s, "
                " placa=%s, marca=%s, modelo=%s, km=%s, ano=%s, chassi=%s, numero_de_serie=%s, "
                " forma_pagamento=%s, forma_pagamento_garantia=%s, referencia_os=%s, tecnico_responsavel=%s, auxiliar_tecnico=%s, posicao_os=%s, "
                " previsao_termino=%s, data_termino=%s, hora_fechamento=%s, data_agendamento=%s, hora_agendamento=%s, codagenda_atendimento=%s, OS_ORIGINAL=%s, "
                " Tipo_Doc_Original=%s, VALIDOU_GARANTIA=%s, QtdRevisoes=%s "
                "WHERE codigo=%s",
                (
                    req.cliente, req.area_atuacao, descricao_cliente, obs, resumo, status_os,
                    req.atendente, situacao, placa, marca, modelo, km, ano, chassi, num_serie,
                    forma_pagamento, forma_pagamento_garantia, referencia, req.tecnico_responsavel, req.auxiliar_tecnico, req.posicao_os,
                    previsao_termino, data_termino, hora_fechamento, data_agendamento, hora_agendamento, codagenda_atendimento, os_original,
                    tipo_doc_original, 1 if validou_garantia else 0, qtd_revisoes, codigo,
                ),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "OS não encontrada."}
            os_id = codigo

        # Consumo de data de revisão programada — só no ramo "revisao"
        # (tipo contém REVISÃO/REVISAO E `os_original` de fato preenchido):
        # libera qualquer vínculo anterior desta O.S. e reivindica a data
        # mais antiga ainda disponível da O.S. de origem. Réplica de
        # `Command2_Click`, linhas 10043-10051 de `FrmTraOsNew.frm`.
        if "REVIS" in tipo_os_desc.upper() and os_original:
            cur.execute("UPDATE osrevisao SET osrevisao=0 WHERE osrevisao=%s", (os_id,))
            cur.execute(
                "SELECT TOP 1 sequencia FROM osrevisao WHERE os=%s AND ISNULL(osrevisao,0)=0 ORDER BY data",
                (os_original,),
            )
            disponivel = cur.fetchone()
            if disponivel:
                seq = disponivel["sequencia"] if isinstance(disponivel, dict) else disponivel[0]
                cur.execute("UPDATE osrevisao SET osrevisao=%s WHERE sequencia=%s", (os_id, seq))

        # Regenera as datas de revisão PROGRAMADAS POR esta O.S. (Campo 151/
        # `qtd_revisoes` — N datas futuras, a cada 30 dias, pulando domingo,
        # réplica de `Campo_LostFocus(151)`, linhas 5753-5764). Desvio
        # DELIBERADO do legado (que apaga e recria TODAS as linhas, inclusive
        # já consumidas, a cada Gravar — perderia o vínculo de consumo em
        # qualquer edição da O.S. de origem, mesmo sem mexer em "Revisões");
        # aqui só as linhas AINDA DISPONÍVEIS são recriadas, preservando o
        # histórico de quem já consumiu uma data. Ver PENDENCIAS.md > "O.S.
        # Completa" > "Doc. Origem / Revisão Programada".
        cur.execute("DELETE FROM osrevisao WHERE os=%s AND ISNULL(osrevisao,0)=0", (os_id,))
        if qtd_revisoes > 0:
            data_ref = date.today()
            for _ in range(qtd_revisoes):
                data_ref = data_ref + timedelta(days=30)
                if data_ref.isoweekday() == 7:  # domingo
                    data_ref = data_ref + timedelta(days=1)
                cur.execute(
                    "INSERT INTO osrevisao (os, data, osrevisao) VALUES (%s, %s, 0)",
                    (os_id, data_ref.isoformat()),
                )

        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": os_id}
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


async def save_os_completo(req: OSCompletoSaveRequest, codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_os_completo_sync, req, codigo)


async def fechar_os_completo(req: FecharRequest, codigo: int) -> dict:
    return await os_service.fechar_os(req, codigo, tela="OS_COMP")


async def faturar_os_completo(req: FaturarOSRequest, codigo: int) -> dict:
    return await os_service.faturar_os(req, codigo, tela="OS_COMP")


async def reabrir_os_completo(req: FecharRequest, codigo: int) -> dict:
    return await os_service.reabrir_os(req, codigo, tela="OS_COMP")


async def cancelar_os_completo(req: FecharRequest, codigo: int) -> dict:
    return await os_service.cancelar_os(req, codigo, tela="OS_COMP", acao="SITUACAO")


def _list_requisicoes_vinculadas_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Requisições vinculadas a esta O.S. — aba "Requisições vinculadas a
    O.S." (`GridReq`, `Sub Requisicoes()`) em `Revenda\\FrmTraOsNew.frm`.
    100% somente leitura no legado (sem `Click`/`DblClick` na grade, sem
    outro controle no frame) — replicado aqui como leitura pura, sem
    nenhuma rota de escrita.

    A query une os DOIS mecanismos de vínculo que o legado usa (confirmado
    no rastreio, ver PENDENCIAS.md > "O.S. Completa" > "Requisições
    Vinculadas"): a tabela de junção `os_requisicao` (histórica, nenhuma
    tela desta migração grava nela ainda) e as colunas escalares
    `requisicao.tipo_mov_requisicao`/`codigo_requisicao` (o mecanismo que
    `Geral\\frmmanreq.frm` de fato usa, campo "Documento vinculado" —
    ainda não implementado no `requisicao_service.py` desta migração,
    então hoje esta grade normalmente vem vazia; a leitura já está pronta
    pro dia em que esse campo for implementado). Só mostra PRODUTOS (join
    com `pecas`), nunca serviços — o legado nunca junta com `servicos`
    aqui, mesmo a Requisição em si aceitando os dois tipos."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM os WHERE codigo=%s", (codigo,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "OS não encontrada.", "items": []}
        cur.execute(
            "SELECT requisicao.codigo AS requisicao, requisicao.data AS data, "
            "       rec_prod.qtd AS qtd, rec_prod.p_unit AS p_unit, "
            "       pecas.descricao AS descricao, pecas.codigo_fab AS cod_fab "
            "FROM pecas, os_requisicao, requisicao, rec_prod "
            "WHERE pecas.codigo_int = rec_prod.prod "
            "  AND requisicao.situacao IN ('A','F','OS') "
            "  AND requisicao.codigo = rec_prod.requisicao "
            "  AND os_requisicao.os = %s "
            "  AND requisicao.codigo = os_requisicao.requisicao "
            "UNION ALL "
            "SELECT requisicao.codigo AS requisicao, requisicao.data AS data, "
            "       rec_prod.qtd AS qtd, rec_prod.p_unit AS p_unit, "
            "       pecas.descricao AS descricao, pecas.codigo_fab AS cod_fab "
            "FROM pecas, requisicao, rec_prod "
            "WHERE pecas.codigo_int = rec_prod.prod "
            "  AND requisicao.situacao IN ('A','F','OS') "
            "  AND requisicao.codigo = rec_prod.requisicao "
            "  AND requisicao.tipo_mov_requisicao = 'OS' "
            "  AND requisicao.codigo_requisicao = %s "
            "ORDER BY requisicao DESC",
            (codigo, codigo),
        )
        items = []
        total = 0.0
        for r in cur.fetchall():
            qtd = float(r.get("qtd") or 0)
            p_unit = float(r.get("p_unit") or 0)
            p_total = round(qtd * p_unit, 2)
            total += p_total
            items.append({
                "requisicao": int(r["requisicao"]),
                "data": r["data"].isoformat() if r.get("data") else None,
                "cod_fab": (r.get("cod_fab") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "qtd": qtd,
                "p_unit": p_unit,
                "p_total": p_total,
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "total": round(total, 2)}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def list_requisicoes_vinculadas(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_list_requisicoes_vinculadas_sync, servidor, banco, codigo)


def _criar_copia_os_sync(
    servidor: str, banco: str, codigo_origem: int,
    usuario_alteracao: Optional[int], classe: Optional[int], master: bool,
) -> dict:
    """"Criar Cópia" (`Command49_Click`, `Revenda\\FrmTraOsNew.frm`, linhas
    11337-11383) — cria uma O.S. nova, sempre Aberta, a partir do
    cabeçalho + itens da O.S. `codigo_origem`. Disponível em QUALQUER
    Situação da O.S. de origem (legado não restringe), sem confirmação
    prévia — a confirmação (se pedida) fica a cargo do frontend, mesmo
    espírito de outras ações desta tela.

    Fiel ao legado nestes pontos: nova O.S. nasce com `situacao='A'`,
    número novo (aqui via `MAX(codigo)+1`, o gerador já padrão desta
    migração — não o contador `CONTROLE.numero_os` do legado, workaround
    de era VB6 sem equivalente aqui); itens só são copiados se o
    produto/serviço mestre ainda está ATIVO no cadastro
    (`pecas.situacao='A'`/`servicos.situacao='A'`); preço do item
    recalculado pelo CADASTRO ATUAL (não o preço congelado da O.S.
    original); desconto/acréscimo do item sempre zerados na cópia.
    Formas de pagamento NÃO são copiadas nesta migração (só o código
    simples `forma_pagamento` do cabeçalho, via cópia normal de coluna) —
    ver PENDENCIAS.md > "O.S. Completa" > "Criar Cópia" pro racional
    completo (inclusive quais colunas do cabeçalho legado ficaram de fora
    por nunca terem sido modeladas em nenhuma outra tela desta migração).
    Doc. Origem/Revisão/Log/Agendamento/Anexos também não são copiados —
    mesmo comportamento do legado, a cópia nasce "limpa" nesses campos."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not master and classe is not None and not tem_permissao(cur, classe, "OS_COMP", "COPIAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para criar cópia da O.S."}

        cur.execute(
            "SELECT cliente, area_atuacao, descricao_cliente, obs, resumo, status_os, atendente, "
            "       placa, marca, modelo, km, ano, chassi, numero_de_serie, forma_pagamento, "
            "       referencia_os, tecnico_responsavel, posicao_os "
            "FROM os WHERE codigo=%s",
            (codigo_origem,),
        )
        origem = cur.fetchone()
        if not origem:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}

        cur.execute("SELECT ISNULL(MAX(codigo),0)+1 AS novo FROM os")
        novo = int(cur.fetchone()["novo"] or 1)

        cur.execute(
            "INSERT INTO os "
            "(codigo, cliente, data_entrada, hora_entrada, situacao, valor, "
            " area_atuacao, descricao_cliente, obs, resumo, status_os, atendente, "
            " placa, marca, modelo, km, ano, chassi, numero_de_serie, forma_pagamento, "
            " referencia_os, tecnico_responsavel, posicao_os, OS_ORIGINAL) "
            "VALUES (%s, %s, CAST(GETDATE() AS DATE), CONVERT(NVARCHAR(8), GETDATE(), 108), "
            "        'A', 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)",
            (
                novo, origem["cliente"], origem.get("area_atuacao"), origem.get("descricao_cliente") or "",
                origem.get("obs") or "", origem.get("resumo") or "", origem.get("status_os"),
                origem.get("atendente"), origem.get("placa") or "", origem.get("marca") or "",
                origem.get("modelo") or "", origem.get("km"), origem.get("ano") or "",
                origem.get("chassi") or "", origem.get("numero_de_serie") or "",
                origem.get("forma_pagamento") or "", origem.get("referencia_os") or "",
                origem.get("tecnico_responsavel"), origem.get("posicao_os"),
            ),
        )

        exige_aprovacao = _exige_aprovacao_itens_os_ativo(cur)
        for tabela_mestre, coluna_preco in (("pecas", "p_venda"), ("servicos", "valor_hora")):
            coluna_codigo = "codigo_int" if tabela_mestre == "pecas" else "codigo"
            cur.execute(
                f"INSERT INTO os_produto "
                f"(os, codigo_interno, quant, p_venda, preco_unitario, desconto, acrescimo, custo_os, "
                f" vendedor, executor, situacao, item_cancelado, faturado, "
                f" Pontuacao_A, Pontuacao_E, Pontuacao_V, data_inclusao_item) "
                f"SELECT %s, op.codigo_interno, op.quant, m.{coluna_preco}, m.{coluna_preco}, 0, 0, "
                f"       op.custo_os, op.vendedor, op.executor, op.situacao, op.item_cancelado, op.faturado, "
                f"       op.Pontuacao_A, op.Pontuacao_E, op.Pontuacao_V, CAST(GETDATE() AS DATE) "
                f"FROM os_produto op "
                f"JOIN {tabela_mestre} m ON m.{coluna_codigo} = op.codigo_interno AND m.situacao='A' "
                f"WHERE op.os=%s",
                (novo, codigo_origem),
            )

        # Reserva de estoque das PEÇAS copiadas — mesmo padrão condicional
        # já usado em `os_itens_service._add_item_sync` (não reserva se a
        # empresa exige Autorização de Itens; a autorização é quem reserva
        # nesse caso). Legado sempre reserva na cópia, sem essa condição —
        # adaptação deliberada pra manter consistência com o resto desta
        # migração, não uma omissão.
        if not exige_aprovacao:
            cur.execute("SELECT codigo_interno, quant FROM os_produto WHERE os=%s", (novo,))
            for item in cur.fetchall():
                _mover_estoque(cur, (item.get("codigo_interno") or "").strip(), float(item.get("quant") or 0), "reservado_os")

        _recalc_os_total(cur, novo)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": novo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao criar cópia: {e}"}


async def criar_copia_os(
    servidor: str, banco: str, codigo_origem: int,
    usuario_alteracao: Optional[int] = None, classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(_criar_copia_os_sync, servidor, banco, codigo_origem, usuario_alteracao, classe, master)

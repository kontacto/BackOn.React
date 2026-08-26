"""Ordem de Serviço (tabela `os`) — listagem, leitura e CRUD do cabeçalho.

Diferenças importantes em relação ao pedido_venda:
  • `os.codigo` NÃO é IDENTITY → geramos MAX(codigo)+1 dentro da transação.
  • Vendedor/executor ficam no nível do ITEM (os_produto), não no cabeçalho.
  • Colunas NOT NULL sem default: codigo, km, OS_ORIGINAL → preenchidas no insert.
Situações reutilizam os mesmos códigos do pedido (A/F/PG/C).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc
from models.schemas import (
    OSListRequest, OSSaveRequest, FecharRequest, FaturarOSRequest, FormaPagSimplesRequest, OSCheckinRequest,
    LimparLocalizacaoRequest,
)
from services.constants import SITUACAO_LABEL
from services.pedido_common import (
    _check_cliente_ativo, _check_area_atuacao, _auto_abrir_dia_se_necessario, _chassi_obrigatorio_ok,
    DavPagamento, DAV_OS, _fecha_fpag_dav, _qtd_formas, _liberar_reservado, _mover_estoque,
    _ensure_os_forma_pagamento_garantia_col, _checklist_veiculo_pendente_bloqueia,
)
from services.permissoes_service import tem_permissao
from services.os_itens_service import _recalc_os_total, _check_os_aberta


def _ensure_os_checkin_cols(cur) -> None:
    """Check-in/check-out por geolocalização da tela de Atendimento de Campo
    (Assistência Técnica — ver AssistenciaTecnicaCampo.md regra 2). Um único
    par de check-in/check-out por OS (decisão do usuário, 2026-08-14) — sem
    tabela nova, direto em `os`. Migração idempotente, mesmo padrão de
    `_ensure_qtd_pessoas_col` (pedido_common.py)."""
    for nome, tipo in (
        ("checkin_em", "DATETIME NULL"),
        ("checkin_lat", "FLOAT NULL"),
        ("checkin_lng", "FLOAT NULL"),
        ("checkin_usuario", "INT NULL"),
        ("checkout_em", "DATETIME NULL"),
        ("checkout_lat", "FLOAT NULL"),
        ("checkout_lng", "FLOAT NULL"),
        ("checkout_usuario", "INT NULL"),
    ):
        cur.execute(
            f"IF NOT EXISTS (SELECT 1 FROM sys.columns "
            f"WHERE Name='{nome}' AND Object_ID=Object_ID('os')) "
            f"ALTER TABLE os ADD {nome} {tipo}"
        )


def _ensure_os_versao_atendimento_col(cur) -> None:
    """Concorrência otimista pra sincronização OFFLINE da tela de
    Atendimento de Campo (Assistência Técnica — ver
    AssistenciaTecnicaCampo.md, "Sincronização Offline"). `ROWVERSION` é
    tipo nativo do SQL Server: auto-incrementa sozinho em QUALQUER UPDATE
    da linha (não pode ser setado manualmente), e o `ALTER TABLE ... ADD`
    já auto-preenche todas as linhas existentes — não precisa de `NULL`/
    `DEFAULT` como as outras migrações deste arquivo. Só 1 coluna
    `ROWVERSION` é permitida por tabela (limite do próprio SQL Server),
    confirmado que `os` ainda não tem nenhuma.

    Uso: o app cacheia este valor (hex) ao carregar uma OS pra uso
    offline; ao sincronizar uma mutação da fila local, manda de volta
    como `versao_esperada` — se o valor atual da linha mudou nesse
    meio-tempo, a gravação é bloqueada com um aviso de conflito em vez de
    sobrescrever silenciosamente (decisão do usuário, 2026-08-14: nunca
    merge automático)."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='versao_atendimento' AND Object_ID=Object_ID('os')) "
        "ALTER TABLE os ADD versao_atendimento ROWVERSION"
    )


def _versao_atendimento_hex(valor) -> Optional[str]:
    """`pymssql` devolve ROWVERSION como `bytes` — converte pra hex
    (string) pra trafegar em JSON. Token opaco: nunca decodificado nem
    interpretado no frontend, só comparado byte-a-byte (como string)."""
    if valor is None:
        return None
    if isinstance(valor, (bytes, bytearray)):
        return valor.hex()
    return str(valor)


def _checar_conflito_versao(cur, codigo: int, versao_esperada: Optional[str]) -> Optional[dict]:
    """Concorrência otimista pra mutações vindas da fila offline (ver
    `_ensure_os_versao_atendimento_col`) — chamado com o cursor já aberto,
    ANTES do UPDATE de negócio. `versao_esperada` vazio/None = gravação
    online direta, nunca checa (comportamento de sempre, inalterado).
    Retorna um dict de erro pronto pra devolver quando há conflito, ou
    `None` quando pode prosseguir."""
    if not versao_esperada:
        return None
    cur.execute("SELECT versao_atendimento FROM os WHERE codigo=%s", (codigo,))
    row = cur.fetchone()
    atual = _versao_atendimento_hex(row.get("versao_atendimento")) if row else None
    if atual != versao_esperada:
        return {
            "success": False,
            "conflito": True,
            "message": "Esta OS foi alterada desde a última vez que você a carregou. "
                       "Abra a OS de novo pra ver os dados atuais antes de tentar sincronizar.",
        }
    return None


def _list_os_sync(req: OSListRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        where_parts: list[str] = []
        params: list = []
        term = (req.search or "").strip()
        if term:
            like = f"%{term}%"
            # Busca por nome também bate no nome fantasia — [GLOBAL] em toda
            # busca de cliente do sistema, pedido explícito do usuário,
            # 2026-07-18.
            where_parts.append(
                "(c.nome LIKE %s OR c.fantasia LIKE %s OR c.cgc_cpf LIKE %s OR CAST(o.codigo AS NVARCHAR(20)) LIKE %s)"
            )
            params.extend([like, like, like, like])
        if req.situacao:
            where_parts.append("o.situacao = %s")
            params.append(req.situacao)
        if req.data_ini:
            where_parts.append("o.data_entrada >= %s")
            params.append(req.data_ini)
        if req.data_fim:
            where_parts.append("o.data_entrada <= %s")
            params.append(req.data_fim)
        # Data de Faturamento — via `comanda_os`/`comanda.data` (ver
        # OSListRequest.data_fat_ini/fim acima pro porquê de não existir
        # coluna própria em `os`). Usa EXISTS em vez de JOIN direto pra não
        # multiplicar linhas se uma O.S. algum dia tiver mais de uma comanda.
        if req.data_fat_ini:
            where_parts.append(
                "EXISTS (SELECT 1 FROM comanda_os co JOIN comanda cm ON cm.comanda = co.comanda "
                "WHERE co.os = o.codigo AND cm.data >= %s)"
            )
            params.append(req.data_fat_ini)
        if req.data_fat_fim:
            where_parts.append(
                "EXISTS (SELECT 1 FROM comanda_os co JOIN comanda cm ON cm.comanda = co.comanda "
                "WHERE co.os = o.codigo AND cm.data <= %s)"
            )
            params.append(req.data_fat_fim)
        if req.tecnico:
            where_parts.append("o.tecnico_responsavel = %s")
            params.append(req.tecnico)
        if req.auxiliar:
            where_parts.append("o.auxiliar_tecnico = %s")
            params.append(req.auxiliar)
        if req.data_agenda:
            where_parts.append("o.data_agendamento = %s")
            params.append(req.data_agenda)
        # Restrição de visibilidade da Lista de Atendimento (os-lista.tsx) —
        # opt-in: só ativa quando o chamador manda classe+usuario_codigo (só
        # os-lista.tsx manda; os.tsx/os-form.tsx nunca preenchem esses campos,
        # então não são afetados). Sem `OS_COMP.VER_TODAS` (e sem ser master),
        # só enxerga O.S. onde é técnico responsável ou auxiliar — ver
        # AssistenciaTecnicaCampo.md.
        if req.classe is not None and req.usuario_codigo is not None and not req.master:
            if not tem_permissao(cur, req.classe, "OS_COMP", "VER_TODAS"):
                where_parts.append("(o.tecnico_responsavel = %s OR o.auxiliar_tecnico = %s)")
                params.extend([req.usuario_codigo, req.usuario_codigo])
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        cur.execute(
            f"SELECT COUNT(*) c FROM os o LEFT JOIN cliente c ON c.codigo = o.cliente {where}",
            params,
        )
        total = int(cur.fetchone()["c"] or 0)

        offset = max(0, (req.page - 1) * req.size)
        cur.execute(
            f"SELECT o.codigo, o.cliente, o.data_entrada, o.hora_entrada, o.situacao, "
            f"       ISNULL((SELECT SUM(p.quant * p.p_venda) FROM os_produto p "
            f"               WHERE p.os = o.codigo AND ISNULL(p.item_cancelado,0)=0), 0) AS valor_calc, "
            f"       o.area_atuacao, c.nome AS cliente_nome, "
            f"       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS atendente_nome, "
            f"       o.tecnico_responsavel, COALESCE(NULLIF(ft.nome_guerra,''), ft.nome) AS tecnico_nome, "
            f"       o.auxiliar_tecnico, COALESCE(NULLIF(fa.nome_guerra,''), fa.nome) AS auxiliar_nome, "
            f"       o.checkin_em, o.checkout_em, "
            f"       o.data_agendamento, o.hora_agendamento, "
            f"       (SELECT MIN(a.data) FROM AGENDA_OS ao "
            f"        JOIN os_produto op ON op.cod_os_prod = ao.CODOS "
            f"        JOIN AGENDA a ON a.codagenda = ao.CODAGENDA "
            f"        WHERE op.os = o.codigo) AS proxima_agenda "
            f"FROM os o "
            f"LEFT JOIN cliente c ON c.codigo = o.cliente "
            f"LEFT JOIN funcionarios f ON f.codigo_int = o.atendente "
            f"LEFT JOIN funcionarios ft ON ft.codigo_int = o.tecnico_responsavel "
            f"LEFT JOIN funcionarios fa ON fa.codigo_int = o.auxiliar_tecnico "
            f"{where} "
            f"ORDER BY o.codigo DESC OFFSET {offset} ROWS FETCH NEXT {req.size} ROWS ONLY",
            params,
        )
        items: list[dict] = []
        for r in cur.fetchall():
            sit = (r.get("situacao") or "").strip()
            items.append({
                "codigo": int(r["codigo"] or 0),
                "cliente": int(r["cliente"] or 0) if r.get("cliente") else None,
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "data": r["data_entrada"].isoformat() if r.get("data_entrada") else None,
                "hora": (r.get("hora_entrada") or "").strip(),
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                # Somado a partir de os_produto, não `os.valor` — muitos
                # registros legados (importados/gravados fora deste backend)
                # têm `os.valor` desatualizado/zerado mesmo com itens reais
                # (achado ao vivo em KONTACTO-TESTE: 583 O.S. Faturadas com
                # valor=0). `os.valor` continua sendo a fonte de verdade
                # pra ESCRITA (Faturar/etc — `_recalc_os_total` mantém em
                # sincronia pra tudo criado/editado por este backend); aqui
                # é só EXIBIÇÃO, mais robusta a dado legado divergente.
                "total": float(r.get("valor_calc") or 0),
                "atendente_nome": (r.get("atendente_nome") or "").strip(),
                "tecnico_responsavel": int(r["tecnico_responsavel"]) if r.get("tecnico_responsavel") else None,
                "tecnico_nome": (r.get("tecnico_nome") or "").strip(),
                "auxiliar_tecnico": int(r["auxiliar_tecnico"]) if r.get("auxiliar_tecnico") else None,
                "auxiliar_nome": (r.get("auxiliar_nome") or "").strip(),
                "checkin_em": r["checkin_em"].isoformat() if r.get("checkin_em") else None,
                "checkout_em": r["checkout_em"].isoformat() if r.get("checkout_em") else None,
                "data_agendamento": (
                    r["data_agendamento"].isoformat() if hasattr(r.get("data_agendamento"), "isoformat") else None
                ),
                "hora_agendamento": (str(r.get("hora_agendamento") or "").strip()[:5]),
                "proxima_agenda": (
                    r["proxima_agenda"].isoformat() if hasattr(r.get("proxima_agenda"), "isoformat") else None
                ),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "total": total, "page": req.page, "size": req.size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


def _get_os_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT o.codigo, o.cliente, o.data_entrada, o.hora_entrada, o.situacao, "
            "       ISNULL((SELECT SUM(p.quant * p.p_venda) FROM os_produto p "
            "               WHERE p.os = o.codigo AND ISNULL(p.item_cancelado,0)=0), 0) AS valor_calc, "
            "       o.area_atuacao, o.descricao_cliente, o.obs, o.resumo, o.status_os, o.atendente, "
            "       o.placa, o.marca, o.modelo, o.km, o.ano, o.chassi, o.numero_de_serie, "
            "       o.forma_pagamento, fp.descricao AS forma_pagamento_descricao, "
            "       o.checkin_em, o.checkin_lat, o.checkin_lng, o.checkin_usuario, "
            "       o.checkout_em, o.checkout_lat, o.checkout_lng, o.checkout_usuario, "
            "       o.versao_atendimento, "
            "       c.nome AS cliente_nome, c.cgc_cpf AS cliente_cgc, "
            "       a.descricao AS area_descricao, "
            "       f.nome AS atendente_nome, f.nome_guerra AS atendente_guerra "
            "FROM os o "
            "LEFT JOIN cliente c ON c.codigo = o.cliente "
            "LEFT JOIN area_atuacao a ON a.area = o.area_atuacao "
            "LEFT JOIN funcionarios f ON f.codigo_int = o.atendente "
            "LEFT JOIN forma_pagamento fp ON fp.codigo = o.forma_pagamento "
            "WHERE o.codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "OS não encontrada."}
        sit = (row.get("situacao") or "").strip()
        return {
            "success": True,
            "os": {
                "codigo": int(row["codigo"] or 0),
                "cliente": int(row["cliente"] or 0) if row.get("cliente") else None,
                "cliente_nome": (row.get("cliente_nome") or "").strip(),
                "cliente_cgc": (row.get("cliente_cgc") or "").strip(),
                "data": row["data_entrada"].isoformat() if row.get("data_entrada") else None,
                "hora": (row.get("hora_entrada") or "").strip(),
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                # Somado a partir de os_produto — ver comentário em
                # `_list_os_sync` sobre `os.valor` legado desatualizado.
                "total": float(row.get("valor_calc") or 0),
                "area_atuacao": int(row["area_atuacao"]) if row.get("area_atuacao") is not None else None,
                "area_descricao": (row.get("area_descricao") or "").strip(),
                "descricao_cliente": row.get("descricao_cliente") or "",
                "obs": row.get("obs") or "",
                "resumo": row.get("resumo") or "",
                "status_os": int(row["status_os"]) if row.get("status_os") is not None else None,
                "atendente": int(row["atendente"]) if row.get("atendente") else None,
                "atendente_nome": (row.get("atendente_guerra") or row.get("atendente_nome") or "").strip(),
                "placa": (row.get("placa") or "").strip(),
                "marca": (row.get("marca") or "").strip(),
                "modelo": (row.get("modelo") or "").strip(),
                "km": int(row["km"]) if row.get("km") is not None else None,
                "ano": (row.get("ano") or "").strip(),
                "chassi": (row.get("chassi") or "").strip(),
                "numero_de_serie": (row.get("numero_de_serie") or "").strip(),
                "forma_pagamento": (row.get("forma_pagamento") or "").strip(),
                "forma_pagamento_descricao": (row.get("forma_pagamento_descricao") or "").strip(),
                "checkin_em": row["checkin_em"].isoformat() if row.get("checkin_em") else None,
                "checkin_lat": float(row["checkin_lat"]) if row.get("checkin_lat") is not None else None,
                "checkin_lng": float(row["checkin_lng"]) if row.get("checkin_lng") is not None else None,
                "checkin_usuario": int(row["checkin_usuario"]) if row.get("checkin_usuario") is not None else None,
                "checkout_em": row["checkout_em"].isoformat() if row.get("checkout_em") else None,
                "checkout_lat": float(row["checkout_lat"]) if row.get("checkout_lat") is not None else None,
                "checkout_lng": float(row["checkout_lng"]) if row.get("checkout_lng") is not None else None,
                "checkout_usuario": int(row["checkout_usuario"]) if row.get("checkout_usuario") is not None else None,
                "versao_atendimento": _versao_atendimento_hex(row.get("versao_atendimento")),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_os_sync(req: OSSaveRequest, codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        # Update: só OS Aberta ('A') pode ser alterada.
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
            # Nova O.S. — cliente com STATUS_CLIENTE diferente de Ativo não pode
            # gerar movimentação (venda/pré-venda).
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

        if codigo is None:
            # codigo NÃO é identity → gera MAX+1. km e OS_ORIGINAL são NOT NULL.
            cur.execute("SELECT ISNULL(MAX(codigo),0)+1 AS novo FROM os")
            novo = int(cur.fetchone()["novo"] or 1)
            cur.execute(
                "INSERT INTO os "
                "(codigo, cliente, data_entrada, hora_entrada, situacao, valor, "
                " area_atuacao, descricao_cliente, obs, resumo, status_os, atendente, "
                " placa, marca, modelo, km, ano, chassi, numero_de_serie, forma_pagamento, OS_ORIGINAL) "
                "VALUES (%s, %s, CAST(GETDATE() AS DATE), CONVERT(NVARCHAR(8), GETDATE(), 108), "
                "        %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)",
                (novo, req.cliente, situacao, req.area_atuacao, descricao_cliente, obs, resumo,
                 status_os, req.atendente, placa, marca, modelo, km, ano, chassi, num_serie, forma_pagamento),
            )
            os_id = novo
        else:
            cur.execute(
                "UPDATE os SET cliente=%s, area_atuacao=%s, descricao_cliente=%s, obs=%s, "
                " resumo=%s, status_os=%s, atendente=%s, situacao=%s, "
                " placa=%s, marca=%s, modelo=%s, km=%s, ano=%s, chassi=%s, numero_de_serie=%s, "
                " forma_pagamento=%s "
                "WHERE codigo=%s",
                (req.cliente, req.area_atuacao, descricao_cliente, obs, resumo, status_os,
                 req.atendente, situacao, placa, marca, modelo, km, ano, chassi, num_serie,
                 forma_pagamento, codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "OS não encontrada."}
            os_id = codigo
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


def _set_forma_pag_simples_sync(req: FormaPagSimplesRequest, codigo: int) -> dict:
    """Combobox simples 'Forma de Pagamento' do cabeçalho — grava direto ao
    trocar, fora do fluxo normal de Gravar. Mesmo raciocínio/nome de
    `pedidos_service._set_forma_pag_simples_sync`, só a tabela/coluna
    muda (`os.forma_pagamento`, não `pedido_venda.forma_pag`)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit not in ("A", "F"):
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        forma_pag = (req.forma_pag or "")[:3] or None
        cur.execute("UPDATE os SET forma_pagamento=%s WHERE codigo=%s", (forma_pag, codigo))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar forma de pagamento: {e}"}


def _checkin_os_sync(req: OSCheckinRequest, codigo: int) -> dict:
    """Check-in do técnico em campo (tela de Atendimento — Assistência
    Técnica, ver AssistenciaTecnicaCampo.md regra 2). Um único check-in por
    OS — se já houver um registrado, bloqueia em vez de sobrescrever (o
    usuário confirmou 'um único par de check-in/check-out por OS', não um
    conceito de visita repetível)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode receber check-in."}
        cur.execute("SELECT checkin_em FROM os WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if row and row.get("checkin_em"):
            conn.close()
            return {"success": False, "message": f"Check-in já registrado nesta OS em {row['checkin_em']}."}
        conflito = _checar_conflito_versao(cur, codigo, req.versao_esperada)
        if conflito:
            conn.close()
            return conflito
        cur.execute(
            "UPDATE os SET checkin_em=GETDATE(), checkin_lat=%s, checkin_lng=%s, checkin_usuario=%s WHERE codigo=%s",
            (req.latitude, req.longitude, req.usuario_alteracao, codigo),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao registrar check-in: {e}"}


def _checkout_os_sync(req: OSCheckinRequest, codigo: int) -> dict:
    """Check-out do técnico em campo — exige check-in prévio nesta mesma OS."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao, checkin_em, checkout_em FROM os WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if not row.get("checkin_em"):
            conn.close()
            return {"success": False, "message": "Faça o check-in antes do check-out."}
        if row.get("checkout_em"):
            conn.close()
            return {"success": False, "message": f"Check-out já registrado nesta OS em {row['checkout_em']}."}
        conflito = _checar_conflito_versao(cur, codigo, req.versao_esperada)
        if conflito:
            conn.close()
            return conflito
        cur.execute(
            "UPDATE os SET checkout_em=GETDATE(), checkout_lat=%s, checkout_lng=%s, checkout_usuario=%s WHERE codigo=%s",
            (req.latitude, req.longitude, req.usuario_alteracao, codigo),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao registrar check-out: {e}"}


async def list_os(req: OSListRequest) -> dict:
    return await asyncio.to_thread(_list_os_sync, req)


async def get_os(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_os_sync, servidor, banco, codigo)


async def save_os(req: OSSaveRequest, codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_os_sync, req, codigo)


async def set_forma_pag_simples(req: FormaPagSimplesRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_set_forma_pag_simples_sync, req, codigo)


async def checkin_os(req: OSCheckinRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_checkin_os_sync, req, codigo)


async def checkout_os(req: OSCheckinRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_checkout_os_sync, req, codigo)


def _limpar_localizacao_sync(req: LimparLocalizacaoRequest, codigo: int) -> dict:
    """Remove as coordenadas de GPS de check-in/check-out (mantém os
    horários) — ferramenta de conformidade LGPD, ver
    `LimparLocalizacaoRequest`. Permissão própria (`OS_COMP.LIMPAR_
    LOCALIZACAO`), checada aqui (não no frontend) porque é dado sensível —
    mesmo princípio de reforço no backend já usado em `_fechar_os_sync`."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM os WHERE codigo=%s", (codigo,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "OS_COMP", "LIMPAR_GEO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para remover a localização."}
        cur.execute(
            "UPDATE os SET checkin_lat=NULL, checkin_lng=NULL, checkout_lat=NULL, checkout_lng=NULL WHERE codigo=%s",
            (codigo,),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao remover localização: {e}"}


async def limpar_localizacao(req: LimparLocalizacaoRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_limpar_localizacao_sync, req, codigo)



def _fechar_os_sync(req: FecharRequest, codigo: int, tela: str = "OS") -> dict:
    """Fecha a O.S. (situação A -> F). Valida itens, permissão e forma de
    pagamento (réplica de `Fecha_FPAG_Dav`, mesmo `Type_FormaPagPedOS`
    compartilhado com o Pedido — ver `pedido_common.DavPagamento`).
    O estoque das peças já foi movido na INCLUSÃO do item (reservado_os),
    portanto o fechamento NÃO movimenta estoque novamente.

    `tela` (default "OS", O.S. Mobile) decide qual permissão é checada —
    a O.S. Completa (`os_completo_service.py`) chama esta mesma função
    passando `tela="OS_COMP"`, mesmo padrão já usado em
    `pedidos_service._faturar_pedido_sync`/`_reabrir_pedido_sync` pro
    Pedido Completo, pra não duplicar a regra."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao, valor, forma_pagamento FROM os WHERE codigo=%s", (codigo,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser fechada."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, "SITUACAO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar a O.S."}
        if tela == "OS_COMP" and not req.master:
            bloqueio_checklist = _checklist_veiculo_pendente_bloqueia(cur, codigo, req.classe)
            if bloqueio_checklist:
                conn.close()
                return {"success": False, "message": bloqueio_checklist}
        conflito = _checar_conflito_versao(cur, codigo, req.versao_esperada)
        if conflito:
            conn.close()
            return conflito
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM os_produto WHERE os=%s AND ISNULL(item_cancelado,0)=0",
            (codigo,),
        )
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Inclua pelo menos um produto ou serviço antes de fechar."}
        # Recalcula de os_produto em vez de confiar em os.valor: itens
        # incluídos/editados antes desta correção (ou por outro processo)
        # podem ter deixado essa coluna desatualizada — ver PENDENCIAS.md
        # > "O.S. Completa" > "Risco identificado".
        subtotal = _recalc_os_total(cur, codigo)
        forma_padrao = (ex.get("forma_pagamento") or "").strip()
        dav = DavPagamento(tipo=DAV_OS, documento=codigo, situacao="A", valor=subtotal, forma_padrao=forma_padrao)
        erro = _fecha_fpag_dav(cur, dav)
        if erro:
            conn.close()
            return {"success": False, "message": erro}
        if _qtd_formas(cur, dav) == 0 and subtotal > 0:
            conn.close()
            return {"success": False, "message": "Defina a Forma de Pagamento da O.S.!"}
        cur.execute("UPDATE os SET situacao='F' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pré-venda Fechada.", "situacao": "F"}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar: {e}"}


async def fechar_os(req: FecharRequest, codigo: int, tela: str = "OS") -> dict:
    return await asyncio.to_thread(_fechar_os_sync, req, codigo, tela)


def _faturar_bucket_os(cur, req: FaturarOSRequest, codigo: int, cliente, area_atuacao, bucket: str, total: float) -> int:
    """Fatura UM bloco de itens da O.S. (`bucket` = "cliente" ou
    "garantia") numa Comanda própria — réplica de `GeraComanda` (FlagOS
    "C"/"G"): mesma tabela de itens `os_produto`, filtrada por
    `situacao=0` (cliente) ou `situacao<>0 AND faturado=0` (garantia/
    interno/contrato). Sempre fatura pro `os.cliente` (o legado fatura
    garantia pro `cliente_garantia` quando preenchido, campo nunca
    modelado nesta migração — ver "Não replicar truques VB6"). Marca
    `os_produto.faturado=1` só nos itens do bloco garantia — o bloco
    cliente não precisa dessa marcação porque, uma vez faturado, a O.S.
    inteira vira `PG` e o bloco cliente nunca é reconsultado de novo."""
    cur.execute(
        "INSERT INTO comanda (data, cliente, valor_venda, situacao, atendente, hora_comanda, area_atuacao) "
        "OUTPUT INSERTED.comanda "
        "VALUES (CONVERT(date, GETDATE()), %s, %s, 'PG', %s, CONVERT(varchar(8), GETDATE(), 108), %s)",
        (cliente, total, req.usuario_alteracao or 0, area_atuacao),
    )
    comanda_id = int(cur.fetchone()["comanda"])

    if bucket == "cliente":
        cur.execute(
            "SELECT cod_os_prod, codigo_interno, quant, p_venda, custo_os, vendedor FROM os_produto "
            "WHERE os=%s AND situacao=0 AND ISNULL(item_cancelado,0)=0",
            (codigo,),
        )
    else:
        cur.execute(
            "SELECT cod_os_prod, codigo_interno, quant, p_venda, custo_os, vendedor FROM os_produto "
            "WHERE os=%s AND situacao<>0 AND ISNULL(faturado,0)=0 AND ISNULL(item_cancelado,0)=0",
            (codigo,),
        )
    itens = cur.fetchall()
    for it in itens:
        produto = (it.get("codigo_interno") or "").strip()
        qtd = float(it.get("quant") or 0)
        p_venda = float(it.get("p_venda") or 0)
        custo = float(it.get("custo_os") or 0)
        vendedor = it.get("vendedor") or 0
        _liberar_reservado(cur, produto, qtd, campo="reservado_os")
        cur.execute(
            "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, p_unit, num_nf, serie_nf, vendedor, custo_mov) "
            "VALUES (CONVERT(date, GETDATE()), 'S01', %s, %s, %s, %s, 'CM', %s, %s)",
            (produto, qtd, p_venda, comanda_id, vendedor, custo),
        )
        if bucket == "garantia":
            cur.execute("UPDATE os_produto SET faturado=1 WHERE cod_os_prod=%s", (it["cod_os_prod"],))

    cur.execute("INSERT INTO COMANDA_OS (comanda, os) VALUES (%s, %s)", (comanda_id, codigo))
    return comanda_id


def _faturar_os_sync(req: FaturarOSRequest, codigo: int, tela: str = "OS") -> dict:
    """Fatura a O.S.: gera a Comanda (`comanda`, `movimentacao` S01/CM,
    `COMANDA_OS`), libera o estoque reservado das PEÇAS (`reservado_os` —
    a baixa de `qtd` já aconteceu na inclusão do item, ver
    `os_itens_service._add_item_sync`) e marca a OS como paga (situação
    PG). Réplica do mesmo padrão de `pedidos_service._faturar_pedido_sync`,
    pedido explícito do usuário 2026-07-21 — mas **exige a OS já Fechada**
    (sem o atalho "fecha-e-fatura junto" do Pedido Bar): O.S. hoje só tem
    Fechar (`_fechar_os_sync`), nunca teve um "fecha e fatura" combinado
    rastreado, então a transição A->F continua exigindo o botão Fechar
    normalmente antes de Faturar.

    Vendedor de cada linha de `movimentacao` vem do próprio item
    (`os_produto.vendedor`), não de um campo único no cabeçalho — diferente
    de `pedido_venda`, que guarda um vendedor só no cabeçalho e o repete
    pra todo item ao faturar; O.S. já guarda vendedor por item desde a
    inclusão (ver `os_itens_service.py`), então é isso que se usa aqui.

    **Bifurcação de faturamento Garantia×Cliente** (`Command2_Click`/
    `GeraComanda`, `FrmTraOsNew.frm`) — itens são divididos em 2 blocos por
    `os_produto.situacao`: bloco "cliente" (situação=0) e bloco "garantia"
    (situação IN 1/2/3 — Garantia/Interno/Contrato), cada um faturado numa
    Comanda PRÓPRIA, com sua própria forma de pagamento
    (`os.forma_pagamento_garantia` pro bloco garantia). Quando os 2 blocos
    têm valor pendente ao mesmo tempo e `req.faturar_bucket` não veio
    definido, a função NÃO fatura nada — devolve `needs_choice=True` com
    os 2 totais, pra tela perguntar ao usuário o que faturar agora (mesmo
    efeito da tela bloqueante `Frame5`/`Check3`/`Check5` do legado). Sem
    ambiguidade (só um bloco com valor), decide sozinha, sem perguntar.

    Uma O.S. já Faturada (`PG`) pode voltar aqui pra faturar itens de
    Garantia/Interno/Contrato incluídos DEPOIS do primeiro faturamento
    (`situacao<>0 AND faturado=0` ainda pendente) — o bloco cliente nunca
    é reconsultado nesse caso (já foi resolvido no primeiro faturamento, o
    legado nunca reabre esse bloco)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_os_forma_pagamento_garantia_col(cur)
        cur.execute(
            "SELECT situacao, cliente, valor, area_atuacao, forma_pagamento_garantia FROM os WHERE codigo=%s",
            (codigo,),
        )
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit not in ("A", "F", "PG"):
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser faturada."}
        if sit == "A":
            conn.close()
            return {"success": False, "message": "Feche a OS antes de faturar."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, "FATURAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para faturar a O.S."}
        if tela == "OS_COMP" and not req.master:
            bloqueio_checklist = _checklist_veiculo_pendente_bloqueia(cur, codigo, req.classe)
            if bloqueio_checklist:
                conn.close()
                return {"success": False, "message": bloqueio_checklist}

        # Mesmo recálculo defensivo do Fechar — não confiar em os.valor cru.
        _recalc_os_total(cur, codigo)
        cliente = ex.get("cliente")
        area_atuacao = ex.get("area_atuacao") or 0
        forma_pagamento_garantia = (ex.get("forma_pagamento_garantia") or "").strip()

        if sit == "PG":
            # Já faturada — só sobra o bloco garantia pendente (itens
            # incluídos depois do primeiro faturamento).
            cur.execute(
                "SELECT COALESCE(SUM(quant*p_venda),0) AS total FROM os_produto "
                "WHERE os=%s AND situacao<>0 AND ISNULL(faturado,0)=0 AND ISNULL(item_cancelado,0)=0",
                (codigo,),
            )
            total_garantia = float((cur.fetchone() or {}).get("total") or 0)
            if total_garantia <= 0:
                conn.close()
                return {"success": False, "message": "OS já faturada."}
            if not forma_pagamento_garantia:
                conn.close()
                return {
                    "success": False,
                    "message": "Defina a Forma de Pagamento de Garantia da O.S. antes de faturar os itens pendentes.",
                }
            comanda_garantia = _faturar_bucket_os(cur, req, codigo, cliente, area_atuacao, "garantia", total_garantia)
            conn.commit()
            cur.close()
            conn.close()
            return {
                "success": True, "message": "Itens de Garantia/Interno/Contrato faturados.", "situacao": "PG",
                "comanda_garantia": comanda_garantia, "situacao_antes": sit,
            }

        # sit == "F": calcula os 2 blocos de uma vez.
        cur.execute(
            "SELECT "
            "  COALESCE(SUM(CASE WHEN situacao=0 THEN quant*p_venda ELSE 0 END),0) AS total_cliente, "
            "  COALESCE(SUM(CASE WHEN situacao<>0 AND ISNULL(faturado,0)=0 THEN quant*p_venda ELSE 0 END),0) AS total_garantia "
            "FROM os_produto WHERE os=%s AND ISNULL(item_cancelado,0)=0",
            (codigo,),
        )
        tot = cur.fetchone() or {}
        total_cliente = float(tot.get("total_cliente") or 0)
        total_garantia = float(tot.get("total_garantia") or 0)
        if total_cliente <= 0 and total_garantia <= 0:
            conn.close()
            return {"success": False, "message": "OS sem produtos/serviços a serem faturados."}

        bucket = (req.faturar_bucket or "").strip().lower() or None
        if bucket not in (None, "cliente", "garantia", "ambos"):
            bucket = None
        if total_cliente > 0 and total_garantia > 0:
            if bucket is None:
                conn.close()
                return {
                    "success": False, "needs_choice": True,
                    "total_cliente": total_cliente, "total_garantia": total_garantia,
                    "message": (
                        "Esta O.S. tem itens de Cliente e de Garantia/Interno/Contrato pendentes — "
                        "escolha o que faturar agora."
                    ),
                }
        elif total_garantia > 0:
            bucket = "garantia"
        else:
            bucket = "cliente"

        if bucket in ("garantia", "ambos") and total_garantia > 0 and not forma_pagamento_garantia:
            conn.close()
            return {
                "success": False,
                "message": "Defina a Forma de Pagamento de Garantia da O.S. antes de faturar.",
            }

        comanda_cliente = None
        comanda_garantia = None
        if bucket in ("cliente", "ambos") and total_cliente > 0:
            comanda_cliente = _faturar_bucket_os(cur, req, codigo, cliente, area_atuacao, "cliente", total_cliente)
        if bucket in ("garantia", "ambos") and total_garantia > 0:
            comanda_garantia = _faturar_bucket_os(cur, req, codigo, cliente, area_atuacao, "garantia", total_garantia)

        cur.execute("UPDATE os SET situacao='PG' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "message": "OS faturada.", "situacao": "PG",
            "comanda": comanda_cliente, "comanda_garantia": comanda_garantia, "situacao_antes": sit,
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao faturar: {e}"}


async def faturar_os(req: FaturarOSRequest, codigo: int, tela: str = "OS") -> dict:
    return await asyncio.to_thread(_faturar_os_sync, req, codigo, tela)


def _reabrir_os_sync(req: FecharRequest, codigo: int, tela: str = "OS") -> dict:
    """Reabre a O.S. (situação F -> A). Só permite reabrir Fechada — o
    legado (`FrmTraOsNew.frm`, `cmdReabrir_Click`) só habilita o botão
    nesse estado, então o branch de código que trataria reabertura de
    Cancelada nunca é alcançável na prática e não foi replicado (ver
    "Não replicar truques VB6" no CLAUDE.md). Não reverte nenhuma
    movimentação de estoque — o Fechar de O.S. não movimenta estoque (só o
    Faturar libera a reserva), então reabrir também não precisa."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit != "F":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser reaberta."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, "REABRIR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para reabrir a O.S."}
        cur.execute("UPDATE os SET situacao='A' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "O.S. Reaberta.", "situacao": "A"}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao reabrir: {e}"}


async def reabrir_os(req: FecharRequest, codigo: int, tela: str = "OS") -> dict:
    return await asyncio.to_thread(_reabrir_os_sync, req, codigo, tela)


def _cancelar_os_sync(req: FecharRequest, codigo: int, tela: str = "OS", acao: str = "SITUACAO") -> dict:
    """Cancela a O.S. (situação A/F -> C, nunca Paga). Estorna a reserva de
    estoque de cada item não-cancelado (`_mover_estoque` com delta
    negativo — devolve a peça a `pecas.qtd` e remove de `reservado_os`,
    espelho exato do que a inclusão de item faz ao reservar). `acao`
    default "SITUACAO" reaproveita a mesma permissão de Fechar/Reabrir
    (mesmo raciocínio já usado por `pedidos_service._cancelar_pedido_sync`
    pro Pedido Completo — evita exigir reconcessão de permissão numa ação
    nova)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit not in ("A", "F"):
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser cancelada."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, acao):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar a O.S."}
        cur.execute(
            "SELECT codigo_interno, quant FROM os_produto WHERE os=%s AND ISNULL(item_cancelado,0)=0",
            (codigo,),
        )
        itens = cur.fetchall()
        for it in itens:
            produto = (it.get("codigo_interno") or "").strip()
            qtd = float(it.get("quant") or 0)
            _mover_estoque(cur, produto, -qtd, "reservado_os")
        cur.execute("UPDATE os SET situacao='C' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "O.S. Cancelada.", "situacao": "C"}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar: {e}"}


async def cancelar_os(req: FecharRequest, codigo: int, tela: str = "OS", acao: str = "SITUACAO") -> dict:
    return await asyncio.to_thread(_cancelar_os_sync, req, codigo, tela, acao)
"""Financeiro > Contas a Receber — gerencia o que já foi lançado em
`Duplicata_Receber`/`Duplicata_Rec_Venc` (via Transferência p/Contas Pagar/
Receber, Contratos/Faturar, ou lançamento manual avulso desta própria
tela).

Fonte VB6 rastreada (linhagem real `backon.vbp`, ver PENDENCIAS.md >
"Contas a Receber" pro rastreio completo campo-a-campo):
- `Geral/FRMCONNFREC.frm` ("Consulta de Notas Fiscais a Receber") — busca
  sobre `Receber`.
- `Geral/frmTraNFRec.frm` ("Notas Fiscais a Receber...") — CRUD de
  `Receber`, inclusive lançamento manual avulso (sem Nota Fiscal real por
  trás), e botão "Gerar Duplicata" (split de parcelas).
- `Revenda/FrmManDur.frm` ("Duplicatas a Receber...", referenciado por
  `backon.vbp` — não existe em `Geral`, esta é a versão viva real) —
  manutenção de `Duplicata_Receber`/`Duplicata_Rec_Venc`.

**Escopo desta 1ª rodada** (decidido com o usuário via `AskUserQuestion`,
2026-08-28): listar/gerenciar duplicatas + lançamento avulso + baixa
manual + exclusão com guarda. Boleto avulso (já coberto por Geração de
Boletos/Cobranças), Centro de Resultados (rateio) e "Emitir Fatura" ficam
de fora — usuário vai confirmar com Leandro antes de decidir escopo
dessas 3 sub-telas.

**Baixa/Cancelamento/Lote/Montante — CORREÇÃO 2026-08-28**: a afirmação
anterior ("baixa manual é funcionalidade NOVA, sem precedente") estava
ERRADA — eu tinha rastreado só `FrmManDur.frm`/`frmmandup.frm` (que são
as telas "Duplicatas", só manutenção, sem baixa mesmo). A baixa/
cancelamento vive em 2 forms separados, nunca antes localizados:
`Revenda/FrmManPar.frm` (Receber) e `Revenda/FrmManPap.frm` (Pagar), cada
um com 2 modos (flag global `CancelaPg`/`CancelaPgP`: `"P"`=Pagamento,
`"C"`=Cancelamento). Ver PENDENCIAS.md > "Baixa de Duplicatas — Achado
Completo (2026-08-28)" pro rastreio completo campo-a-campo, e a decisão
de escopo desta rodada (inclui lote "Por Data" e Montante; exclui guarda
de caixa fechado e reversão de saldo/movimentações — infraestrutura que
ainda não existe nesta migração, ver a mesma seção).

**Regra real replicada de `FrmManDur.frm`**: parcela com `situacao='PG'` é
imutável — nunca editada por `_editar_parcela_sync`, só através de
cancelar a baixa e refazer.

**Melhoria deliberada em relação ao legado**: `frmTraNFRec.frm`'s
`cmdExcluir_Click` deleta `Receber` direto sem checar se já existe
Duplicata/parcela paga vinculada — aqui a exclusão bloqueia se qualquer
parcela já estiver paga (mesmo princípio de "Delete guards required" já
padrão neste projeto)."""
import asyncio
from datetime import date, datetime

from db.connection import _open_conn
from services.transferencia_contas_service import _controle_flags_sync, _resolver_numero_duplicata_sync


# =============================================================================
# Listagem
# =============================================================================

def _listar_sync(servidor: str, banco: str, filtros: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        where = ["1=1"]
        params: list = []

        if filtros.get("cliente"):
            where.append("dr.cliente = %s")
            params.append(filtros["cliente"])

        if filtros.get("busca"):
            termo = f"%{filtros['busca']}%"
            where.append("(c.nome LIKE %s OR c.fantasia LIKE %s OR CAST(dr.duplicata AS VARCHAR(20)) LIKE %s)")
            params.extend([termo, termo, termo])

        situacao = (filtros.get("situacao") or "").upper()
        if situacao == "PG":
            where.append("dr.situacao = 'PG'")
        elif situacao == "A":
            where.append("dr.situacao = 'A'")
        elif situacao == "V":
            where.append(
                "dr.situacao = 'A' AND EXISTS (SELECT 1 FROM Duplicata_Rec_Venc v "
                "WHERE v.duplicata = dr.codigo AND v.situacao <> 'PG' AND v.dt_vencimento < CAST(GETDATE() AS DATE))"
            )

        if filtros.get("data_ini") and filtros.get("data_fim"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Rec_Venc v WHERE v.duplicata = dr.codigo "
                "AND v.dt_vencimento BETWEEN %s AND %s)"
            )
            params.extend([filtros["data_ini"], filtros["data_fim"]])

        sql = (
            "SELECT dr.codigo, dr.cliente, c.nome AS cliente_nome, c.fantasia AS cliente_fantasia, "
            "dr.duplicata, dr.desmembramento, dr.dt_emissao, dr.valor, dr.situacao, "
            "dr.num_parcelas, dr.parcelas_pagas, "
            "(SELECT MIN(v.dt_vencimento) FROM Duplicata_Rec_Venc v WHERE v.duplicata = dr.codigo AND v.situacao <> 'PG') AS proximo_vencimento, "
            "(SELECT SUM(v.valor) FROM Duplicata_Rec_Venc v WHERE v.duplicata = dr.codigo AND v.situacao <> 'PG') AS valor_em_aberto "
            "FROM Duplicata_Receber dr LEFT JOIN Cliente c ON c.codigo = dr.cliente "
            f"WHERE {' AND '.join(where)} ORDER BY dr.dt_emissao DESC, dr.codigo DESC"
        )
        cur.execute(sql, tuple(params))
        items = []
        for r in cur.fetchall():
            vencido = False
            if r.get("proximo_vencimento") and r.get("situacao") == "A":
                venc = r["proximo_vencimento"]
                venc_date = venc if isinstance(venc, date) else datetime.strptime(str(venc)[:10], "%Y-%m-%d").date()
                vencido = venc_date < date.today()
            items.append({
                "codigo": r["codigo"],
                "cliente": r["cliente"],
                "cliente_nome": r.get("cliente_fantasia") or r.get("cliente_nome"),
                "duplicata": r["duplicata"],
                "desmembramento": r.get("desmembramento"),
                "dt_emissao": str(r["dt_emissao"]) if r.get("dt_emissao") else None,
                "valor": float(r.get("valor") or 0),
                "situacao": r.get("situacao"),
                "num_parcelas": r.get("num_parcelas"),
                "parcelas_pagas": r.get("parcelas_pagas"),
                "proximo_vencimento": str(r["proximo_vencimento"]) if r.get("proximo_vencimento") else None,
                "valor_em_aberto": float(r.get("valor_em_aberto") or 0),
                "vencido": vencido,
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _detalhe_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT dr.codigo, dr.cliente, c.nome AS cliente_nome, c.fantasia AS cliente_fantasia, "
            "dr.duplicata, dr.desmembramento, dr.dt_emissao, dr.valor, dr.situacao, "
            "dr.num_parcelas, dr.parcelas_pagas "
            "FROM Duplicata_Receber dr LEFT JOIN Cliente c ON c.codigo = dr.cliente WHERE dr.codigo = %s",
            (codigo,),
        )
        header = cur.fetchone()
        if not header:
            cur.close(); conn.close()
            return {"success": False, "message": "Duplicata não encontrada."}
        header["cliente_nome"] = header.pop("cliente_fantasia") or header["cliente_nome"]
        header["dt_emissao"] = str(header["dt_emissao"]) if header.get("dt_emissao") else None
        header["valor"] = float(header.get("valor") or 0)

        cur.execute(
            "SELECT codigo, duplicata, desmembramento, dt_vencimento, valor, situacao, "
            "data_pag, valor_pag, desconto_pag, juros_pag, conta, forma_pag, obs_vencimento "
            "FROM Duplicata_Rec_Venc WHERE duplicata = %s ORDER BY desmembramento",
            (codigo,),
        )
        parcelas = []
        for p in cur.fetchall():
            parcelas.append({
                "codigo": p["codigo"],
                "desmembramento": p["desmembramento"],
                "dt_vencimento": str(p["dt_vencimento"]) if p.get("dt_vencimento") else None,
                "valor": float(p.get("valor") or 0),
                "situacao": p.get("situacao"),
                "data_pag": str(p["data_pag"]) if p.get("data_pag") else None,
                "valor_pag": float(p["valor_pag"]) if p.get("valor_pag") is not None else None,
                "desconto_pag": float(p["desconto_pag"]) if p.get("desconto_pag") is not None else None,
                "juros_pag": float(p["juros_pag"]) if p.get("juros_pag") is not None else None,
                "conta": p.get("conta"),
                "forma_pag": p.get("forma_pag"),
                "observacao": p.get("obs_vencimento"),
            })

        cur.execute(
            "SELECT r.codigo, r.nota_fiscal, r.serie, r.tipo_mov, r.cod_n_fiscal "
            "FROM Duplicata_Rec_Nf drn JOIN Receber r ON r.codigo = drn.nf_fiscal WHERE drn.duplicata = %s",
            (codigo,),
        )
        notas = cur.fetchall() or []

        cur.close(); conn.close()
        return {"success": True, "header": header, "parcelas": parcelas, "notas": notas}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# =============================================================================
# Lançamento avulso — réplica de `frmTraNFRec.frm`'s CmdGravar (TemNF=False)
# + Command7_Click ("Gerar Duplicata", split de parcelas).
# =============================================================================

def _avancar_vencimento_mensal(venc: date, dia_original: int) -> date:
    """Avança 1 mês, mantendo o mesmo dia; se o dia não existir no mês
    seguinte (ex.: 31 num mês de 30), decrementa até achar data válida —
    réplica exata do loop `repete:` em `frmTraNFRec.frm`'s Command7."""
    mes, ano = venc.month + 1, venc.year
    if mes == 13:
        mes, ano = 1, ano + 1
    dia = dia_original
    while True:
        try:
            return date(ano, mes, dia)
        except ValueError:
            dia -= 1


def _split_parcelas(valor: float, qtd: int, primeiro_venc: date) -> list[tuple[date, float]]:
    """Divide `valor` em `qtd` parcelas iguais (2 casas), a ÚLTIMA absorve
    a diferença de arredondamento — mesma regra de `Command7_Click`."""
    valor_parcela = round(valor / qtd, 2)
    ajuste = round(valor - (valor_parcela * qtd), 2)
    parcelas = []
    venc = primeiro_venc
    dia_original = primeiro_venc.day
    for k in range(1, qtd + 1):
        v = round(valor_parcela + ajuste, 2) if k == qtd else valor_parcela
        parcelas.append((venc, v))
        venc = _avancar_vencimento_mensal(venc, dia_original)
    return parcelas


def _criar_avulsa_sync(servidor: str, banco: str, req: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT nome FROM Cliente WHERE codigo = %s", (req["cliente"],))
        cliente = cur.fetchone()
        if not cliente:
            cur.close(); conn.close()
            return {"success": False, "message": "Cliente não encontrado."}

        cur.execute(
            "SELECT codigo FROM Receber WHERE cliente = %s AND nota_fiscal = %s AND ISNULL(serie,'') = %s",
            (req["cliente"], req["numero"], (req.get("serie") or "").strip()),
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": (
                f"Já existe um lançamento com Número {req['numero']} Série {req.get('serie') or ''} "
                "para este cliente."
            )}

        parcelas_qtd = max(1, int(req.get("parcelas") or 1))
        valor = float(req["valor"])
        dt_emissao = req["dt_emissao"]
        primeiro_venc = datetime.strptime(req["dt_primeiro_vencimento"][:10], "%Y-%m-%d").date()
        parcelas = _split_parcelas(valor, parcelas_qtd, primeiro_venc)

        # `cod_n_fiscal` gravado EXPLICITAMENTE como NULL (não só omitido) —
        # achado ao vivo contra ARGEN TESTE 2026-08-28: a coluna tem
        # `DEFAULT 0` no schema real, então omiti-la faz o SQL Server
        # preencher com 0, não NULL, mesmo sendo nullable. `_excluir_sync`
        # usa `cod_n_fiscal IS NULL` pra distinguir avulso (apaga o Receber
        # junto) de originado de NF real (só reabre `situacao='A'`) — sem
        # essa gravação explícita, todo avulso seria tratado como se
        # viesse de NF real.
        cur.execute(
            "INSERT INTO Receber (cliente, nota_fiscal, serie, dt_emissao, dt_entrada, valor, "
            "tipo_mov, cod_n_fiscal, valor_contabilizado, situacao, dt_vencimento) "
            "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,%s,'DU',%s)",
            (req["cliente"], req["numero"], req.get("serie") or "", dt_emissao, dt_emissao, valor,
             req["tipo_mov"], valor, primeiro_venc.isoformat()),
        )
        receber_codigo = cur.fetchone()["codigo"]

        flags = _controle_flags_sync(cur)
        duplicata, desmembramento = _resolver_numero_duplicata_sync(cur, flags, req["numero"])
        cur.execute(
            "INSERT INTO Duplicata_Receber (cliente, duplicata, desmembramento, dt_emissao, "
            "num_parcelas, parcelas_pagas, valor, situacao) "
            "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,0,%s,'A')",
            (req["cliente"], duplicata, desmembramento or (req.get("serie") or ""), dt_emissao,
             parcelas_qtd, valor),
        )
        dup_codigo = cur.fetchone()["codigo"]

        for i, (venc, v) in enumerate(parcelas, start=1):
            cur.execute(
                "INSERT INTO Duplicata_Rec_Venc (duplicata, desmembramento, dt_vencimento, valor, "
                "situacao, obs_vencimento) VALUES (%s,%s,%s,%s,'A',%s)",
                (dup_codigo, i, venc.isoformat(), v, req.get("observacao") or ""),
            )

        cur.execute("INSERT INTO Duplicata_Rec_Nf (duplicata, nf_fiscal) VALUES (%s,%s)", (dup_codigo, receber_codigo))

        conn.commit()
        cur.close(); conn.close()
        return {"success": True, "codigo": dup_codigo}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# =============================================================================
# Baixa / Cancelamento / Lote "Por Data" / Montante — réplica de
# `Revenda/FrmManPar.frm` (Receber) e `Revenda/FrmManPap.frm` (Pagar), ver
# docstring do módulo. O núcleo (`_baixar_parcela_core`/
# `_cancelar_baixa_core`/`_gerar_vencimento_residual`/`_rollup_cabecalho`)
# é parametrizado por nome de tabela — `contas_pagar_service.py` importa e
# reaproveita, sem duplicar a lógica (mesmo padrão já usado pra
# `_split_parcelas`).
# =============================================================================

def _rollup_cabecalho(cur, tabela_venc: str, tabela_cabecalho: str, dup_codigo: int) -> str:
    """Recalcula `parcelas_pagas`/`situacao` do cabeçalho a partir das
    parcelas reais — usado depois de toda baixa/cancelamento (individual,
    lote ou montante), garante consistência mesmo em cenários que o
    `Situacao='A'` fixo do VB6 não cobre (ex.: cancelar 1 de 3 parcelas
    pagas de uma duplicata que nunca chegou a `'PG'`)."""
    cur.execute(
        f"SELECT COUNT(*) AS total, SUM(CASE WHEN situacao = 'PG' THEN 1 ELSE 0 END) AS pagas "
        f"FROM {tabela_venc} WHERE duplicata = %s",
        (dup_codigo,),
    )
    contagem = cur.fetchone()
    nova_situacao = "PG" if contagem["pagas"] == contagem["total"] else "A"
    cur.execute(
        f"UPDATE {tabela_cabecalho} SET parcelas_pagas = %s, situacao = %s WHERE codigo = %s",
        (contagem["pagas"], nova_situacao, dup_codigo),
    )
    return nova_situacao


def _gerar_vencimento_residual(cur, tabela_venc: str, tabela_cabecalho: str, dup_codigo: int, dt_vencimento, saldo: float) -> None:
    """Pagamento parcial gera um novo vencimento com o saldo restante —
    réplica real do legado (`valor = <Campo(8)>`/`Valor_Pag = <Campo(16)>`
    distintos, ambos os forms): mesma duplicata, próximo `desmembramento`,
    mesma `dt_vencimento` da parcela original (o legado não redefine outra
    data). Incrementa `num_parcelas` no cabeçalho."""
    cur.execute(f"SELECT ISNULL(MAX(desmembramento), 0) AS m FROM {tabela_venc} WHERE duplicata = %s", (dup_codigo,))
    novo_desm = (cur.fetchone()["m"] or 0) + 1
    cur.execute(
        f"INSERT INTO {tabela_venc} (duplicata, desmembramento, dt_vencimento, valor, situacao) "
        "VALUES (%s,%s,%s,%s,'A')",
        (dup_codigo, novo_desm, dt_vencimento, round(saldo, 2)),
    )
    cur.execute(f"UPDATE {tabela_cabecalho} SET num_parcelas = num_parcelas + 1 WHERE codigo = %s", (dup_codigo,))


def _baixar_parcela_core(cur, tabela_venc: str, tabela_cabecalho: str, req: dict,
                          validar_valor_max: bool, campos_extra: tuple = ()) -> dict:
    """Núcleo da baixa — assume cursor/transação já abertos por quem
    chama (baixa individual, lote, ou montante); não comita/fecha
    conexão. `campos_extra` lista colunas específicas de um dos lados
    (hoje só `num_doc_pag`, exclusivo do Pagar — não existe em
    `Duplicata_Rec_Venc`)."""
    codigo_venc = req["codigo_venc"]
    cur.execute(
        f"SELECT codigo, duplicata, situacao, valor, dt_vencimento FROM {tabela_venc} WHERE codigo = %s",
        (codigo_venc,),
    )
    parcela = cur.fetchone()
    if not parcela:
        return {"success": False, "message": "Parcela não encontrada."}
    if parcela["situacao"] == "PG":
        return {"success": False, "message": "Esta parcela já está paga."}

    valor_pag = float(req["valor_pag"])
    valor_parcela = float(parcela["valor"] or 0)
    if validar_valor_max and valor_pag > valor_parcela + 0.005:
        return {"success": False, "message": (
            "O valor não pode ser superior ao do vencimento. "
            "Use os campos Juros/Outros Acréscimo."
        )}

    campos = [
        "situacao = 'PG'", "data_pag = %s", "valor_pag = %s", "desconto_pag = %s",
        "outros_desc_pag = %s", "juros_pag = %s", "outros_acres_pag = %s", "tarifa_banco = %s",
        "banco_cedente = %s", "agencia_cedente = %s", "numero_boleto = %s", "conta = %s",
        "forma_pag = %s", "obs_vencimento = %s",
    ]
    valores = [
        req["data_pag"], valor_pag, req.get("desconto_pag") or 0, req.get("outros_desc_pag") or 0,
        req.get("juros_pag") or 0, req.get("outros_acres_pag") or 0, req.get("tarifa_banco"),
        req.get("banco_cedente"), req.get("agencia_cedente"), req.get("numero_boleto"),
        req.get("conta"), req.get("forma_pag"), req.get("observacao") or "",
    ]
    if "num_doc_pag" in campos_extra:
        campos.append("num_doc_pag = %s")
        valores.append(req.get("num_doc_pag"))
    valores.append(codigo_venc)
    cur.execute(f"UPDATE {tabela_venc} SET {', '.join(campos)} WHERE codigo = %s", tuple(valores))

    dup_codigo = parcela["duplicata"]
    if valor_pag < valor_parcela - 0.005:
        saldo = round(valor_parcela - valor_pag, 2)
        _gerar_vencimento_residual(cur, tabela_venc, tabela_cabecalho, dup_codigo, parcela["dt_vencimento"], saldo)

    _rollup_cabecalho(cur, tabela_venc, tabela_cabecalho, dup_codigo)
    return {"success": True}


def _cancelar_baixa_core(cur, tabela_venc: str, tabela_cabecalho: str, codigo_venc: int) -> dict:
    """Núcleo do cancelamento — mesmo princípio de `_baixar_parcela_core`
    (cursor já aberto, não comita). Zera exatamente os campos que o
    legado zera (`Command2_Click`, modo `"C"`) — não limpa banco/agência/
    forma/conta/tarifa/boleto/documento/observação, réplica fiel."""
    cur.execute(f"SELECT codigo, duplicata, situacao FROM {tabela_venc} WHERE codigo = %s", (codigo_venc,))
    parcela = cur.fetchone()
    if not parcela:
        return {"success": False, "message": "Parcela não encontrada."}
    if parcela["situacao"] != "PG":
        return {"success": False, "message": "Esta parcela não está paga."}
    cur.execute(
        f"UPDATE {tabela_venc} SET situacao = 'A', data_pag = NULL, valor_pag = 0, desconto_pag = 0, "
        "outros_desc_pag = 0, juros_pag = 0, outros_acres_pag = 0 WHERE codigo = %s",
        (codigo_venc,),
    )
    _rollup_cabecalho(cur, tabela_venc, tabela_cabecalho, parcela["duplicata"])
    return {"success": True}


def _baixar_parcela_sync(servidor: str, banco: str, req: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        resultado = _baixar_parcela_core(
            cur, "Duplicata_Rec_Venc", "Duplicata_Receber", req, validar_valor_max=True,
        )
        if not resultado["success"]:
            cur.close(); conn.close()
            return resultado
        conn.commit()
        cur.close(); conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _cancelar_baixa_sync(servidor: str, banco: str, req: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        resultado = _cancelar_baixa_core(cur, "Duplicata_Rec_Venc", "Duplicata_Receber", req["codigo_venc"])
        if not resultado["success"]:
            cur.close(); conn.close()
            return resultado
        conn.commit()
        cur.close(); conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _listar_vencimentos_lote_sync(servidor: str, banco: str, filtros: dict) -> dict:
    """Alimenta o modal de Pagamento/Cancelamento em Lote — réplica do
    painel "Por Data" (`Command9_Click`/"Mostra"): modo `baixar` lista
    parcelas em aberto por `dt_vencimento`, modo `cancelar` lista pagas
    por `data_pag`."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        modo = filtros.get("modo") or "baixar"
        where = ["1=1"]
        params: list = []
        if modo == "cancelar":
            where.append("v.situacao = 'PG'")
            if filtros.get("data_ini") and filtros.get("data_fim"):
                where.append("v.data_pag BETWEEN %s AND %s")
                params.extend([filtros["data_ini"], filtros["data_fim"]])
        else:
            where.append("v.situacao = 'A'")
            if filtros.get("data_ini") and filtros.get("data_fim"):
                where.append("v.dt_vencimento BETWEEN %s AND %s")
                params.extend([filtros["data_ini"], filtros["data_fim"]])
        if filtros.get("cliente"):
            where.append("dr.cliente = %s")
            params.append(filtros["cliente"])
        sql = (
            "SELECT v.codigo, v.duplicata, v.desmembramento, v.dt_vencimento, v.valor, v.situacao, "
            "v.data_pag, dr.cliente, COALESCE(c.fantasia, c.nome) AS cliente_nome "
            "FROM Duplicata_Rec_Venc v JOIN Duplicata_Receber dr ON dr.codigo = v.duplicata "
            "LEFT JOIN Cliente c ON c.codigo = dr.cliente "
            f"WHERE {' AND '.join(where)} ORDER BY v.dt_vencimento, v.codigo"
        )
        cur.execute(sql, tuple(params))
        items = []
        for r in cur.fetchall():
            items.append({
                "codigo": r["codigo"], "duplicata": r["duplicata"], "desmembramento": r.get("desmembramento"),
                "dt_vencimento": str(r["dt_vencimento"]) if r.get("dt_vencimento") else None,
                "valor": float(r.get("valor") or 0), "situacao": r.get("situacao"),
                "data_pag": str(r["data_pag"]) if r.get("data_pag") else None,
                "cliente": r.get("cliente"), "cliente_nome": r.get("cliente_nome"),
            })
        cur.close(); conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _processar_lote_sync(servidor: str, banco: str, req: dict) -> dict:
    """Pagamento/Cancelamento em lote — 1 transação, mas cada vencimento
    isolado em seu próprio try/except (não aborta o lote inteiro por 1
    falha pontual, mesmo princípio já usado em `ensure_all_schema`). Lote
    de pagamento sempre quita o valor CHEIO de cada parcela marcada (sem
    parcial — réplica de `Command7_Click`'s uso direto do valor do
    vencimento)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        modo = req.get("modo") or "baixar"
        processados = 0
        falhas: list = []
        for codigo_venc in (req.get("vencimentos") or []):
            try:
                if modo == "cancelar":
                    r = _cancelar_baixa_core(cur, "Duplicata_Rec_Venc", "Duplicata_Receber", codigo_venc)
                else:
                    cur.execute("SELECT valor FROM Duplicata_Rec_Venc WHERE codigo = %s", (codigo_venc,))
                    row = cur.fetchone()
                    if not row:
                        falhas.append({"codigo_venc": codigo_venc, "message": "Parcela não encontrada."})
                        continue
                    item_req = {
                        "codigo_venc": codigo_venc, "data_pag": req.get("data_pag"),
                        "valor_pag": float(row["valor"] or 0),
                        "conta": req.get("conta"), "forma_pag": req.get("forma_pag"),
                    }
                    r = _baixar_parcela_core(cur, "Duplicata_Rec_Venc", "Duplicata_Receber", item_req, validar_valor_max=False)
                if r["success"]:
                    processados += 1
                else:
                    falhas.append({"codigo_venc": codigo_venc, "message": r["message"]})
            except Exception as e:
                falhas.append({"codigo_venc": codigo_venc, "message": str(e)})
        conn.commit()
        cur.close(); conn.close()
        return {"success": True, "processados": processados, "falhas": falhas}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _baixar_montante_sync(servidor: str, banco: str, req: dict) -> dict:
    """Baixa por "Montante" — exclusiva do lado Receber (`Data(5)` de
    `FrmManPar.frm`). Distribui `req['montante']` sequencialmente sobre
    `req['vencimentos']` (ordem recebida = prioridade), quitando cada
    parcela até o limite do saldo restante; se sobrar parte do saldo
    numa parcela sem cobrir 100%, `_baixar_parcela_core` já gera o
    vencimento residual sozinho (mesma lógica da baixa individual)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        saldo_restante = round(float(req["montante"]), 2)
        tocados: list = []
        for codigo_venc in (req.get("vencimentos") or []):
            if saldo_restante <= 0:
                break
            cur.execute(
                "SELECT codigo, situacao, valor FROM Duplicata_Rec_Venc WHERE codigo = %s",
                (codigo_venc,),
            )
            parcela = cur.fetchone()
            if not parcela or parcela["situacao"] == "PG":
                continue
            valor_parcela = float(parcela["valor"] or 0)
            valor_aplicado = round(min(saldo_restante, valor_parcela), 2)
            item_req = {
                "codigo_venc": codigo_venc, "data_pag": req.get("data_pag"), "valor_pag": valor_aplicado,
                "conta": req.get("conta"), "forma_pag": req.get("forma_pag"),
            }
            r = _baixar_parcela_core(cur, "Duplicata_Rec_Venc", "Duplicata_Receber", item_req, validar_valor_max=False)
            if r["success"]:
                saldo_restante = round(saldo_restante - valor_aplicado, 2)
                tocados.append(codigo_venc)
        conn.commit()
        cur.close(); conn.close()
        return {"success": True, "tocados": tocados, "saldo_nao_utilizado": saldo_restante}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _editar_parcela_sync(servidor: str, banco: str, req: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM Duplicata_Rec_Venc WHERE codigo = %s", (req["codigo_venc"],))
        parcela = cur.fetchone()
        if not parcela:
            cur.close(); conn.close()
            return {"success": False, "message": "Parcela não encontrada."}
        if parcela["situacao"] == "PG":
            cur.close(); conn.close()
            return {"success": False, "message": "Esta parcela já está paga. Alterações não permitidas."}
        cur.execute(
            "UPDATE Duplicata_Rec_Venc SET dt_vencimento = %s, valor = %s, obs_vencimento = %s WHERE codigo = %s",
            (req["dt_vencimento"], req["valor"], req.get("observacao") or "", req["codigo_venc"]),
        )
        conn.commit()
        cur.close(); conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# =============================================================================
# Exclusão — com guarda (melhoria deliberada vs. o legado, ver docstring).
# =============================================================================

def _excluir_sync(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM Duplicata_Receber WHERE codigo = %s", (codigo_duplicata,))
        if not cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Duplicata não encontrada."}

        cur.execute(
            "SELECT COUNT(*) AS qtd FROM Duplicata_Rec_Venc WHERE duplicata = %s AND situacao = 'PG'",
            (codigo_duplicata,),
        )
        if cur.fetchone()["qtd"] > 0:
            cur.close(); conn.close()
            return {"success": False, "message": (
                "Não é possível excluir: existem parcelas já pagas nesta duplicata."
            )}

        cur.execute("SELECT nf_fiscal FROM Duplicata_Rec_Nf WHERE duplicata = %s", (codigo_duplicata,))
        receber_codigos = [r["nf_fiscal"] for r in (cur.fetchall() or [])]

        cur.execute("DELETE FROM Duplicata_Rec_Venc WHERE duplicata = %s", (codigo_duplicata,))
        cur.execute("DELETE FROM Duplicata_Rec_Nf WHERE duplicata = %s", (codigo_duplicata,))
        cur.execute("DELETE FROM Duplicata_Receber WHERE codigo = %s", (codigo_duplicata,))

        for rc in receber_codigos:
            cur.execute("SELECT cod_n_fiscal FROM Receber WHERE codigo = %s", (rc,))
            r = cur.fetchone()
            if r and r.get("cod_n_fiscal") is None:
                # Avulso (sem Nota Fiscal real por trás) — apaga junto.
                cur.execute("DELETE FROM Receber WHERE codigo = %s", (rc,))
            else:
                # Originado de NF real (via Transferência) — mantém o
                # registro, volta pra 'A' pra permitir gerar duplicata de
                # novo no futuro.
                cur.execute("UPDATE Receber SET situacao = 'A' WHERE codigo = %s", (rc,))

        conn.commit()
        cur.close(); conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# =============================================================================
# Lookup — Tipo de Movimentação elegível (réplica do combo de
# `Cmb_Click`/`OptTipoMov_Click`: só tipos de Saída marcados pra transferir).
# =============================================================================

def _list_tipos_mov_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, descricao FROM tipo_mov WHERE LEFT(codigo,1) = 'S' AND TRANSF_PAGAR = 'S' "
            "ORDER BY codigo"
        )
        items = cur.fetchall() or []
        cur.close(); conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


# =============================================================================
# Wrappers async
# =============================================================================

async def listar(servidor: str, banco: str, filtros: dict) -> dict:
    return await asyncio.to_thread(_listar_sync, servidor, banco, filtros)


async def detalhe(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_detalhe_sync, servidor, banco, codigo)


async def criar_avulsa(servidor: str, banco: str, req: dict) -> dict:
    return await asyncio.to_thread(_criar_avulsa_sync, servidor, banco, req)


async def baixar_parcela(servidor: str, banco: str, req: dict) -> dict:
    return await asyncio.to_thread(_baixar_parcela_sync, servidor, banco, req)


async def cancelar_baixa(servidor: str, banco: str, req: dict) -> dict:
    return await asyncio.to_thread(_cancelar_baixa_sync, servidor, banco, req)


async def listar_vencimentos_lote(servidor: str, banco: str, filtros: dict) -> dict:
    return await asyncio.to_thread(_listar_vencimentos_lote_sync, servidor, banco, filtros)


async def processar_lote(servidor: str, banco: str, req: dict) -> dict:
    return await asyncio.to_thread(_processar_lote_sync, servidor, banco, req)


async def baixar_montante(servidor: str, banco: str, req: dict) -> dict:
    return await asyncio.to_thread(_baixar_montante_sync, servidor, banco, req)


async def editar_parcela(servidor: str, banco: str, req: dict) -> dict:
    return await asyncio.to_thread(_editar_parcela_sync, servidor, banco, req)


async def excluir(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    return await asyncio.to_thread(_excluir_sync, servidor, banco, codigo_duplicata)


async def list_tipos_mov(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipos_mov_sync, servidor, banco)

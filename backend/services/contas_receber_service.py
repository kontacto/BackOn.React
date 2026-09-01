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
de fora — **confirmado com o Leandro, mesmo dia**: os 3 ficam fora desta
migração (Boleto avulso já tinha sido confirmado antes; Centro de
Resultados e Emitir Fatura vieram depois, resposta direta "também ficam
de fora").

**Baixa/Cancelamento/Lote/Montante — CORREÇÃO 2026-08-28**: a afirmação
anterior ("baixa manual é funcionalidade NOVA, sem precedente") estava
ERRADA — eu tinha rastreado só `FrmManDur.frm`/`frmmandup.frm` (que são
as telas "Duplicatas", só manutenção, sem baixa mesmo). A baixa/
cancelamento vive em 2 forms separados, nunca antes localizados:
`Revenda/FrmManPar.frm` (Receber) e `Revenda/FrmManPap.frm` (Pagar), cada
um com 2 modos (flag global `CancelaPg`/`CancelaPgP`: `"P"`=Pagamento,
`"C"`=Cancelamento). Ver PENDENCIAS.md > "Baixa de Duplicatas — Achado
Completo (2026-08-28)" pro rastreio completo campo-a-campo.

**Guardas de "caixa fechado" e "Forma de Pagamento/Conta obrigatórios" —
IMPLEMENTADAS 2026-08-28, mesmo dia**: confirmadas com o Leandro ("deve
usar os mesmos critérios de bloqueio que existem hoje, incluíndo bloqueio
por caixa já fechado") — ver `_caixa_fechado_sync`/`_baixar_parcela_core`
abaixo. `controle.data_fecha_cx` (não `data_fecha_pagar`, coluna
diferente na mesma tabela — confirmado direto na fonte VB6) é o mesmo
global `Data_Fecha_Cx` que o legado usa nos 2 lados, sem bypass de
usuário master (esse bypass só existe no botão de LOTE do legado,
inconsistência não replicada de propósito — ver "Não replicar truques
VB6" no CLAUDE.md). **Reversão de saldo/movimentações ao cancelar
continua fora de escopo** — Leandro esclareceu que baixa/cancelamento de
duplicata NUNCA deveria mexer no saldo do Fluxo de Caixa mesmo; quem faz
essa ponte é uma tela separada e ainda não migrada, "Transferência para o
Fluxo de Caixa" (`FrmTransfCaixa.frm` — ver "Pendências do Sistema" >
item 3 no CLAUDE.md e "Teste de ecossistema Contas a Pagar/Receber/Fluxo
de Caixa" no PENDENCIAS.md). Ou seja, o achado anterior ("Fluxo de Caixa
não reflete baixa") não era um bug de escopo desta tela — é a arquitetura
correta, só falta a tela de transferência que fecha o ciclo.

**Regra real replicada de `FrmManDur.frm`**: parcela com `situacao='PG'` é
imutável — nunca editada por `_editar_parcela_sync`, só através de
cancelar a baixa e refazer.

**Melhoria deliberada em relação ao legado**: `frmTraNFRec.frm`'s
`cmdExcluir_Click` deleta `Receber` direto sem checar se já existe
Duplicata/parcela paga vinculada — aqui a exclusão bloqueia se qualquer
parcela já estiver paga (mesmo princípio de "Delete guards required" já
padrão neste projeto)."""
import asyncio
import logging
from datetime import date, datetime, timedelta

from db.connection import _open_conn
from services import recibo_service
from services.contratos_service import _valor_por_extenso
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

        # Filtros extras, rastreados de `FRMCONDUr.frm` ("Consulta de
        # Duplicatas à Receber...") — achado do usuário 2026-08-31,
        # integrados na tela de listagem já existente (não uma tela
        # separada, réplica 1:1 do legado). Subconjunto de alto valor:
        # Duplicata/Valor/Nº Boleto vivem em `Duplicata_Rec_Venc`, por
        # isso entram como EXISTS (mesmo padrão já usado acima pro
        # período) — Duplicata (nº) é exceção, mora direto em
        # `Duplicata_Receber.duplicata`. Fora desta rodada, registrado:
        # Banco de Faturamento, Segmento/Região/Rota/Tipo Cliente/
        # Vendedor/Município/Bairro (comboboxes cruzando Cliente/
        # Cliente_End), e o sub-filtro "Detalhado" por Orçamento/OS/
        # Pedido/Nº Pedido Cliente (junta com `comanda_*`, específico do
        # módulo Bar) — mais complexos, menor valor pra esta tela
        # financeira, não pedidos explicitamente.
        if filtros.get("duplicata_num"):
            where.append("dr.duplicata = %s")
            params.append(filtros["duplicata_num"])

        if filtros.get("valor"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Rec_Venc v WHERE v.duplicata = dr.codigo "
                "AND CAST(v.valor + ISNULL(v.tarifa_banco,0) + ISNULL(v.outros_acres_pag,0) AS NUMERIC(15,2)) = %s)"
            )
            params.append(filtros["valor"])

        if filtros.get("numero_boleto"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Rec_Venc v WHERE v.duplicata = dr.codigo "
                "AND v.numero_boleto = %s)"
            )
            params.append(filtros["numero_boleto"])

        if filtros.get("situacao_duplicata") is not None:
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Rec_Venc v WHERE v.duplicata = dr.codigo "
                "AND ISNULL(v.situacao_duplicata,0) = %s)"
            )
            params.append(int(filtros["situacao_duplicata"]))

        if filtros.get("recebido_ini") and filtros.get("recebido_fim"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Rec_Venc v WHERE v.duplicata = dr.codigo "
                "AND v.data_pag BETWEEN %s AND %s)"
            )
            params.extend([filtros["recebido_ini"], filtros["recebido_fim"]])

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
            "data_pag, valor_pag, desconto_pag, juros_pag, conta, forma_pag, obs_vencimento, "
            "ISNULL(situacao_duplicata,0) AS situacao_duplicata "
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
                # 0=Normal, 1=Jurídico, 2=Protestado — ver
                # `_alterar_situacao_vencimento_sync` pro rastreio completo.
                "situacao_duplicata": int(p.get("situacao_duplicata") or 0),
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
# "Notas Fiscais" — vincular/desvincular NF adicional numa duplicata já
# existente. Réplica de `FrmManDur.frm::Command5_Click` (busca) +
# `NF2_DblClick` (vincular) + `NF_DblClick` (desvincular). Achado do
# usuário 2026-08-31.
#
# **Escopo desta rodada**: só "Notas Fiscais" (Receber). "N.F. de
# Desconto" (Command6/`NFD_DblClick`, vincula uma nota de PAGAR como
# abatimento — cruza módulo, incomum) fica de fora, registrado, não
# construído sem confirmação.
#
# **Achado real, não presumido**: nem `NF2_DblClick` nem `NF_DblClick`
# tocam `Duplicata_Receber.valor` nem `Duplicata_Rec_Venc` — só o grid em
# tela (`TotNF`/`TotGeral`) é recalculado, informativo. Isso significa
# que vincular/desvincular uma NF NÃO ajusta automaticamente o valor
# total nem as parcelas da duplicata no legado — replicado fielmente
# aqui: só a ligação (`Duplicata_Rec_Nf`) e o status da NF
# (`Receber.situacao`) mudam. Se o valor da duplicata/parcelas precisar
# refletir a NF nova, isso é responsabilidade separada do usuário (editar
# parcela/vencimentos manualmente) — mesma divisão de responsabilidade já
# existente no legado.
# =============================================================================

def _notas_disponiveis_sync(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT dr.cliente FROM Duplicata_Receber dr WHERE dr.codigo = %s",
            (codigo_duplicata,),
        )
        dup = cur.fetchone()
        if not dup:
            cur.close(); conn.close()
            return {"success": False, "message": "Duplicata não encontrada.", "items": []}

        cur.execute("SELECT cgc_cpf FROM Cliente WHERE codigo = %s", (dup["cliente"],))
        row = cur.fetchone()
        cgc_cpf_raiz = (row.get("cgc_cpf") or "")[:8] if row else ""

        # Mesmo critério do legado: outras NFs em aberto (`situacao='A'`)
        # de QUALQUER cliente com a mesma raiz de CGC/CPF (matriz/filiais),
        # não só do cliente exato da duplicata.
        cur.execute(
            "SELECT r.codigo, c.codigo AS codigo_cliente, c.nome, r.nota_fiscal, r.serie, r.valor "
            "FROM Receber r JOIN Cliente c ON c.codigo = r.cliente "
            "WHERE r.situacao = 'A' AND LEFT(c.cgc_cpf,8) = %s",
            (cgc_cpf_raiz,),
        )
        items = [
            {
                "codigo": r["codigo"], "codigo_cliente": r["codigo_cliente"], "cliente_nome": r["nome"],
                "nota_fiscal": r["nota_fiscal"], "serie": r.get("serie"), "valor": float(r.get("valor") or 0),
            }
            for r in (cur.fetchall() or [])
        ]
        cur.close(); conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _vincular_nf_sync(servidor: str, banco: str, codigo_duplicata: int, nf_fiscal: int) -> dict:
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
            "SELECT duplicata FROM Duplicata_Rec_Nf WHERE duplicata = %s AND nf_fiscal = %s",
            (codigo_duplicata, nf_fiscal),
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Nota Fiscal já vinculada a esta duplicata."}

        cur.execute("SELECT situacao FROM Receber WHERE codigo = %s", (nf_fiscal,))
        nf = cur.fetchone()
        if not nf:
            cur.close(); conn.close()
            return {"success": False, "message": "Nota Fiscal não encontrada."}
        if nf.get("situacao") != "A":
            cur.close(); conn.close()
            return {"success": False, "message": "Esta Nota Fiscal não está mais em aberto."}

        cur.execute("INSERT INTO Duplicata_Rec_Nf (duplicata, nf_fiscal) VALUES (%s,%s)", (codigo_duplicata, nf_fiscal))
        cur.execute("UPDATE Receber SET situacao = 'DU' WHERE codigo = %s", (nf_fiscal,))
        conn.commit()
        cur.close(); conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _desvincular_nf_sync(servidor: str, banco: str, codigo_duplicata: int, nf_fiscal: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT COUNT(*) AS qtd FROM Duplicata_Rec_Venc WHERE duplicata = %s AND situacao = 'PG'",
            (codigo_duplicata,),
        )
        if cur.fetchone()["qtd"] > 0:
            cur.close(); conn.close()
            return {"success": False, "message": (
                "Esta duplicata já possui vencimentos pagos — só é possível alterar dados sobre os vencimentos."
            )}

        cur.execute(
            "SELECT duplicata FROM Duplicata_Rec_Nf WHERE duplicata = %s AND nf_fiscal = %s",
            (codigo_duplicata, nf_fiscal),
        )
        if not cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Esta Nota Fiscal não está vinculada a esta duplicata."}

        cur.execute("DELETE FROM Duplicata_Rec_Nf WHERE duplicata = %s AND nf_fiscal = %s", (codigo_duplicata, nf_fiscal))
        cur.execute("UPDATE Receber SET situacao = 'A' WHERE codigo = %s", (nf_fiscal,))
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


def _caixa_fechado_sync(cur, data_pag: str) -> bool:
    """`controle.data_fecha_cx` — mesmo princípio de "Porting VB6 global
    state" (CLAUDE.md): no legado é um global (`Data_Fecha_Cx`, setado uma
    vez no login), aqui é re-derivado por chamada, nunca cacheado, porque
    este backend atende múltiplas empresas/conexões concorrentes. Réplica
    de `FrmManPap.frm`/`FrmManPar.frm`'s `Command2_Click`
    (`CDate(Campo(5)) <= CDate(Data_Fecha_Cx)`) — bloqueia baixa com data
    de pagamento igual ou anterior ao fechamento. Confirmado ao vivo
    (ARGEN TESTE) que a coluna existe e tem dado real (`data_fecha_cx`,
    não `data_fecha_pagar` — essa outra coluna existe na mesma tabela mas
    não é a lida por este guard, confirmado direto na fonte). `data_pag`
    sempre chega como `str` (`ContasReceberBaixaRequest.data_pag: str`),
    formato `AAAA-MM-DD` — comparação lexicográfica basta."""
    if not data_pag:
        return False
    cur.execute("SELECT TOP 1 data_fecha_cx FROM controle")
    row = cur.fetchone()
    data_fecha = row.get("data_fecha_cx") if row else None
    if not data_fecha:
        return False
    data_fecha_str = data_fecha.isoformat() if hasattr(data_fecha, "isoformat") else str(data_fecha)
    return data_pag[:10] <= data_fecha_str


# =============================================================================
# Cronograma de repasse de Cartão de Crédito/Débito — réplica de
# `Gestor_Cartoes.bas::AtualizadrvCartao`, achado do usuário 2026-08-31
# ("o que falta no ecossistema Receber"). RECEBER-ONLY — confirmado
# rastreando a fonte que este mecanismo não existe do lado Pagar
# (`FrmManPap.frm` nunca chama essa rotina). Chamado nos mesmos 2 pontos
# do legado (`FrmManPar.frm::Command2_Click`): depois de toda baixa E
# depois de todo cancelamento de baixa — idempotente (sempre apaga e
# regrava o cronograma daquele vencimento).
# =============================================================================

def _ajustar_dia_util_sync(cur, data: date) -> date:
    """Réplica exata da rolagem de `AtualizadrvCartao`: primeiro empurra
    fim de semana (sábado +2, domingo +1) uma vez; depois, em loop,
    empurra +1 dia enquanto a data cair num feriado cadastrado —
    reaplicando a mesma regra de fim de semana a cada empurrão (mesmo
    algoritmo do `.bas`, não uma versão "melhorada")."""
    def _rola_fim_de_semana(d: date) -> date:
        if d.weekday() == 5:  # sábado
            return d + timedelta(days=2)
        if d.weekday() == 6:  # domingo
            return d + timedelta(days=1)
        return d

    data = _rola_fim_de_semana(data)
    while True:
        cur.execute("SELECT 1 AS achou FROM feriados WHERE data = %s", (data,))
        if not cur.fetchone():
            return data
        data = _rola_fim_de_semana(data + timedelta(days=1))


def _atualizar_cartao_sync(cur, duplicata: int, codigo_venc: int = 0) -> None:
    """`codigo_venc=0` recalcula TODOS os vencimentos da duplicata (réplica
    de `CodRecVenc=0` no `.bas`); um código específico recalcula só esse.
    Nunca propaga exceção pro chamador — é um recurso complementar
    (cronograma informativo de repasse), uma falha aqui não pode derrubar
    a baixa/cancelamento em si (mesmo princípio de isolamento já usado em
    `_get_empresa_sync`/`ensure_all_schema`)."""
    try:
        if codigo_venc:
            cur.execute("SELECT codigo FROM Duplicata_Rec_Venc WHERE duplicata = %s AND codigo = %s", (duplicata, codigo_venc))
        else:
            cur.execute("SELECT codigo FROM Duplicata_Rec_Venc WHERE duplicata = %s", (duplicata,))
        vencs = [r["codigo"] for r in cur.fetchall()]
        data_limite = date.today() - timedelta(days=350)
        for venc in vencs:
            cur.execute("DELETE FROM duplicata_rec_venc_cartao WHERE sequencia_drv = %s", (venc,))
            cur.execute("DELETE FROM duplicata_rec_venc_debito WHERE sequencia_drv = %s", (venc,))
            for tipo_fp, tabela_destino in (("CC", "duplicata_rec_venc_cartao"), ("CD", "duplicata_rec_venc_debito")):
                cur.execute(
                    "SELECT drv.valor_pag, drv.data_pag, fp.prazo, fp.prazo_rec, fp.parcela_max "
                    "FROM Duplicata_Rec_Venc drv JOIN forma_pagamento fp ON fp.codigo = drv.forma_pag "
                    "WHERE drv.codigo = %s AND drv.data_pag >= %s AND drv.situacao = 'PG' AND fp.tipo = %s",
                    (venc, data_limite, tipo_fp),
                )
                row = cur.fetchone()
                if not row or not row.get("data_pag"):
                    continue
                parcelas = int(row.get("parcela_max") or 0) or 1
                valor_parcela = round(float(row.get("valor_pag") or 0) / parcelas, 2)
                data_corrente = row["data_pag"]
                prazo = int(row.get("prazo") or 0)
                prazo_rec = int(row.get("prazo_rec") or 0)
                for _ in range(parcelas):
                    data_corrente = data_corrente + timedelta(days=prazo)
                    data_grava = _ajustar_dia_util_sync(cur, data_corrente + timedelta(days=prazo_rec))
                    cur.execute(
                        f"INSERT INTO {tabela_destino} (sequencia_drv, valor, bom_para) VALUES (%s, %s, %s)",
                        (venc, valor_parcela, data_grava),
                    )
    except Exception:
        logging.getLogger(__name__).warning(
            "Falha ao recalcular cronograma de cartão/débito da duplicata %s", duplicata, exc_info=True,
        )


# =============================================================================
# Cheque(s) pré-datado(s) recebido(s) na própria Baixa — réplica de
# `FrmManPar.frm::Command2_Click`'s `GridCheques`/`GravaChequePre`
# (`Geral/mdl_proc.bas`), achado do usuário 2026-08-31. RECEBER-ONLY —
# mesma confirmação de `_atualizar_cartao_sync` acima (não existe em
# `FrmManPap.frm`). Nunca chamado em Lote/Montante (o legado também só
# tem essa grade na baixa individual).
# =============================================================================

def _gravar_cheque_pre_sync(cur, codigo_venc: int, data_pag: str, cheque: dict) -> None:
    cur.execute(
        "INSERT INTO cheque (tipo, banco, agencia, conta, numero_ch, valor, data, bom_para, origem, "
        "doc_origem, obs, situacao, telefone, nome_cheque) VALUES (1, %s, %s, %s, %s, %s, %s, %s, 'R', %s, '', 1, %s, %s)",
        (
            cheque.get("banco"), cheque.get("agencia") or "", cheque.get("conta") or "",
            cheque.get("numero_ch"), cheque.get("valor"), data_pag, cheque.get("bom_para") or data_pag,
            codigo_venc, cheque.get("telefone") or "", cheque.get("nome_cheque") or "",
        ),
    )


def _baixar_parcela_core(cur, tabela_venc: str, tabela_cabecalho: str, req: dict,
                          validar_valor_max: bool, campos_extra: tuple = ()) -> dict:
    """Núcleo da baixa — assume cursor/transação já abertos por quem
    chama (baixa individual, lote, ou montante); não comita/fecha
    conexão. `campos_extra` lista colunas específicas de um dos lados
    (hoje só `num_doc_pag`, exclusivo do Pagar — não existe em
    `Duplicata_Rec_Venc`).

    **Guardas confirmadas com Leandro, 2026-08-28** ("deve usar os mesmos
    critérios de bloqueio que existem hoje, incluíndo bloqueio por caixa
    já fechado") — réplica de `Command2_Click` nos 2 forms legados
    (`FrmManPap.frm`/`FrmManPar.frm`): caixa fechado bloqueia SEMPRE
    (nenhum dos dois `Command2_Click` tem bypass de usuário master — só o
    botão de LOTE, `Command7_Click`, tinha um bypass pra `UsuarioAtual =
    "KONTACTO"`, inconsistência que não é replicada aqui de propósito,
    ver "Não replicar truques VB6" no CLAUDE.md — a mesma regra vale pra
    baixa individual, lote e Montante, todos passam por este núcleo).
    Forma de Pagamento e Conta obrigatórios (só no modo baixa — nunca no
    cancelamento, que é uma função à parte, `_cancelar_baixa_core`)."""
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

    if _caixa_fechado_sync(cur, req.get("data_pag")):
        return {"success": False, "message": "Caixa já fechado! Transação não permitida."}
    if not req.get("forma_pag"):
        return {"success": False, "message": "Defina a Forma de Pagamento."}
    if not req.get("conta"):
        return {"success": False, "message": "Defina a Conta."}

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
    return {"success": True, "duplicata": dup_codigo}


def _cancelar_baixa_core(cur, tabela_venc: str, tabela_cabecalho: str, codigo_venc: int,
                          origem_cheque: str = None, excluir_cheques: bool = None) -> dict:
    """Núcleo do cancelamento — mesmo princípio de `_baixar_parcela_core`
    (cursor já aberto, não comita). Zera exatamente os campos que o
    legado zera (`Command2_Click`, modo `"C"`) — não limpa banco/agência/
    forma/conta/tarifa/boleto/documento/observação, réplica fiel.

    `origem_cheque` ('R' só quando chamado do lado Receber, `None` no
    Pagar) liga as 2 guardas exclusivas do lado Receber, rastreadas em
    `Revenda\\FrmManPar.frm::Command2_Click` (modo Cancelamento) —
    ver PENDENCIAS.md > "Baixa de Duplicatas" pro trecho VB6 completo:
    1. **Agrupamento de comandas no caixa** (`movimentacoes_agrupadas.
       cod_transf_comanda`) — bloqueio incondicional, sem exceção pro
       usuário master (mesmo padrão já usado no resto desta migração pra
       guarda de negócio real, não de permissão).
    2. **Cheque pré-datado vinculado** (`cheque` `origem='R'`) — nunca
       bloqueia sozinho, só PERGUNTA no legado (`MsgBox vbYesNo`). Numa
       API stateless isso vira 2 passos: 1ª chamada sem `excluir_cheques`
       devolve `exige_confirmacao_cheque=True` sem mexer em nada; a
       chamada seguinte já manda `excluir_cheques` (True/False) decidido
       pelo usuário, e só aí o cancelamento prossegue de verdade — mesmo
       padrão 2-passos já usado em `previsoes_service._delete_sync` pra
       "exige_autorizacao" de gerente."""
    cur.execute(f"SELECT codigo, duplicata, situacao FROM {tabela_venc} WHERE codigo = %s", (codigo_venc,))
    parcela = cur.fetchone()
    if not parcela:
        return {"success": False, "message": "Parcela não encontrada."}
    if parcela["situacao"] != "PG":
        return {"success": False, "message": "Esta parcela não está paga."}

    qtd_cheques = 0
    if origem_cheque:
        cur.execute("SELECT COUNT(*) AS qtd FROM movimentacoes_agrupadas WHERE cod_transf_comanda = %s", (codigo_venc,))
        if (cur.fetchone() or {}).get("qtd", 0) > 0:
            return {"success": False, "message": "Este lançamento faz parte de um agrupamento de comandas no caixa, impossibilitando a exclusão!"}

        cur.execute("SELECT COUNT(*) AS qtd FROM cheque WHERE origem = %s AND doc_origem = %s", (origem_cheque, codigo_venc))
        qtd_cheques = (cur.fetchone() or {}).get("qtd", 0)
        if qtd_cheques > 0 and excluir_cheques is None:
            return {
                "success": False,
                "exige_confirmacao_cheque": True,
                "qtd_cheques": qtd_cheques,
                "message": f"Existe(m) {qtd_cheques} cheque(s) associado(s) a esta duplicata. Deseja excluir também?",
            }

    cur.execute(
        f"UPDATE {tabela_venc} SET situacao = 'A', data_pag = NULL, valor_pag = 0, desconto_pag = 0, "
        "outros_desc_pag = 0, juros_pag = 0, outros_acres_pag = 0 WHERE codigo = %s",
        (codigo_venc,),
    )
    _rollup_cabecalho(cur, tabela_venc, tabela_cabecalho, parcela["duplicata"])

    if origem_cheque and qtd_cheques > 0 and excluir_cheques:
        cur.execute("DELETE FROM cheque WHERE origem = %s AND doc_origem = %s", (origem_cheque, codigo_venc))

    return {"success": True, "duplicata": parcela["duplicata"]}


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
        # Cheque(s) pré-datado(s) informado(s) na própria baixa — réplica
        # de `GridCheques`/`GravaChequePre`, achado do usuário 2026-08-31.
        for cheque in (req.get("cheques") or []):
            _gravar_cheque_pre_sync(cur, req["codigo_venc"], req["data_pag"], cheque)
        _atualizar_cartao_sync(cur, resultado["duplicata"], req["codigo_venc"])
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
        resultado = _cancelar_baixa_core(
            cur, "Duplicata_Rec_Venc", "Duplicata_Receber", req["codigo_venc"],
            origem_cheque="R", excluir_cheques=req.get("excluir_cheques"),
        )
        if not resultado["success"]:
            cur.close(); conn.close()
            return resultado
        _atualizar_cartao_sync(cur, resultado["duplicata"], req["codigo_venc"])
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
                    # excluir_cheques nunca é passado aqui — lote não pode
                    # perguntar; item com cheque vinculado vira falha
                    # isolada (mensagem já explica o motivo), usuário
                    # decide cancelando esse item individualmente.
                    r = _cancelar_baixa_core(cur, "Duplicata_Rec_Venc", "Duplicata_Receber", codigo_venc, origem_cheque="R")
                    if r["success"]:
                        _atualizar_cartao_sync(cur, r["duplicata"], codigo_venc)
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
                        _atualizar_cartao_sync(cur, r["duplicata"], codigo_venc)
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
                _atualizar_cartao_sync(cur, r["duplicata"], codigo_venc)
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


# "Cadastro de Vencimentos" — combo Situação (`FrmManDur.frm`, Situacao)
# grava só `duplicata_rec_venc.situacao_duplicata`, 0-based (`ListIndex`
# gravado direto): 0=Normal, 1=Jurídico, 2=Protestado. Endpoint dedicado,
# nunca reaproveita `_editar_parcela_sync` (aquele sobrescreve dt_vencimento/
# valor incondicionalmente). Achado do usuário 2026-08-31: essa situação é
# o que `_alertas_sync` (Painel Financeiro) já filtra pra "Contas a Receber
# em Atraso/Hoje" (`ISNULL(situacao_duplicata,0)=0` — só Normal entra).
def _alterar_situacao_vencimento_sync(servidor: str, banco: str, codigo_venc: int, situacao_duplicata: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM Duplicata_Rec_Venc WHERE codigo = %s", (codigo_venc,))
        if not cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Vencimento não encontrado."}
        cur.execute(
            "UPDATE Duplicata_Rec_Venc SET situacao_duplicata = %s WHERE codigo = %s",
            (situacao_duplicata, codigo_venc),
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

        # Bug real corrigido 2026-08-31, achado do usuário (#017, "previsões
        # com memorando cosmético"): esta função apagava `Duplicata_Rec_Venc`
        # sem antes limpar as previsões vinculadas por Transferência p/Fluxo
        # de Caixa (`cod_transf_caixa` aponta pro `codigo` do vencimento) —
        # deixava a previsão órfã, referenciando um vencimento que não
        # existe mais. Mesma limpeza já usada em `_alterar_numero_sync`
        # (#028), aplicada aqui também, ANTES do DELETE de Duplicata_Rec_Venc
        # (senão o JOIN não teria mais o que casar).
        cur.execute(
            "DELETE p FROM Previsoes p INNER JOIN Duplicata_Rec_Venc v ON v.codigo = p.cod_transf_caixa "
            "WHERE p.flag_transf_caixa = 'R' AND v.duplicata = %s",
            (codigo_duplicata,),
        )

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
# Alterar Número da Duplicata — réplica de `FrmManDur.frm::Command15_Click`.
# Achado do usuário 2026-08-31. Efeito colateral real do legado, replicado
# fielmente (não é gambiarra de VB6, é regra de negócio real): o vínculo
# previsão→vencimento embute o NÚMERO ANTIGO da duplicata no memorando/
# referência (`Transferência p/Fluxo de Caixa`, `cod_transf_caixa` aponta
# pro `Duplicata_Rec_Venc.codigo`, mas o texto/contexto da previsão fica
# referenciando a duplicata antiga) — renumerar sem limpar deixaria a
# previsão órfã/desatualizada. Por isso: apaga as previsões vinculadas
# (`flag_transf_caixa='R'`) de TODOS os vencimentos desta duplicata, e
# reseta `transf_previsao` pra permitir gerar uma transferência nova sob o
# número atualizado.
# =============================================================================

def _alterar_numero_sync(servidor: str, banco: str, codigo_duplicata: int, novo_numero: int) -> dict:
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
            "SELECT codigo FROM Duplicata_Receber WHERE codigo <> %s AND duplicata = %s",
            (codigo_duplicata, novo_numero),
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Já existe uma duplicata cadastrada com esse número."}

        cur.execute("UPDATE Duplicata_Receber SET duplicata = %s WHERE codigo = %s", (novo_numero, codigo_duplicata))
        cur.execute(
            "DELETE p FROM Previsoes p INNER JOIN Duplicata_Rec_Venc v ON v.codigo = p.cod_transf_caixa "
            "WHERE p.flag_transf_caixa = 'R' AND v.duplicata = %s",
            (codigo_duplicata,),
        )
        cur.execute("UPDATE Duplicata_Rec_Venc SET transf_previsao = '' WHERE duplicata = %s", (codigo_duplicata,))

        conn.commit()
        cur.close(); conn.close()
        return {"success": True, "duplicata": novo_numero}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# =============================================================================
# "Emitir Recibo" — achado de análise 2026-08-31 (Áureo/Carlos): a tela de
# Baixa do legado (`Revenda/FrmManPar.frm`) já tem um botão "&Emitir
# Recibo" (Command13) — mas o Command13_Click está inteiramente comentado/
# morto na fonte real, nunca chega a abrir `FrmManRecibo`. O comentário
# morto já documenta a intenção original: pré-preencher Recebemos/Valor/
# Data a partir do pagamento em questão. Esta função completa essa
# intenção — não é comportamento inventado sem precedente na fonte, só
# termina o que ficou desligado por lá. Numeração/gravação reaproveitam o
# núcleo compartilhado `recibo_service._gravar_recibo_numerado_sync`
# (extraído de `contratos_service._gerar_recibo_sync`, que já emite Recibo
# pra Faturar Contratos com a mesma tabela/numeração).
#
# Emitido pra QUALQUER parcela já paga (`Duplicata_Rec_Venc.situacao =
# 'PG'`), não só logo após a baixa — o usuário revisa/edita Recebemos/
# Valor/Referente/Assinatura antes de confirmar (mesmo princípio do
# formulário legado standalone `frmmanrecibo.frm`, que também nunca grava
# sem esses campos preenchidos manualmente).
# =============================================================================

def _emitir_recibo_sync(
    servidor: str, banco: str, *, recebemos: str, valor: float, referente: str,
    data_recibo: str | None = None, assinatura: str | None = None,
) -> dict:
    recebemos = (recebemos or "").strip()
    referente = (referente or "").strip()
    if not recebemos:
        return {"success": False, "message": "Informe quem está pagando (Recebemos de)."}
    if not valor or valor <= 0:
        return {"success": False, "message": "Informe um valor válido para o recibo."}
    if not referente:
        return {"success": False, "message": "Informe a que o recibo se refere."}
    dt = None
    if data_recibo:
        try:
            dt = date.fromisoformat(data_recibo)
        except ValueError:
            dt = None
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        resultado = recibo_service._gravar_recibo_numerado_sync(
            cur, recebemos=recebemos, valor=valor, referente=referente,
            data_recibo=dt, assinatura=(assinatura or "").strip() or None,
        )
        conn.commit()
        cur.close(); conn.close()
        resultado["success"] = True
        resultado["valor_extenso"] = _valor_por_extenso(valor)
        return resultado
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao emitir recibo: {e}"}


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


async def alterar_situacao_vencimento(servidor: str, banco: str, codigo_venc: int, situacao_duplicata: int) -> dict:
    return await asyncio.to_thread(_alterar_situacao_vencimento_sync, servidor, banco, codigo_venc, situacao_duplicata)


def _alterar_situacao_vencimento_lote_sync(servidor: str, banco: str, codigos_venc: list, situacao_duplicata: int) -> dict:
    # Alteração em lote (achado do usuário 2026-08-31, "permitir fazer
    # essa alteração em lote") — mesma UPDATE de `_alterar_situacao_
    # vencimento_sync`, só que pra vários vencimentos de uma vez, cada um
    # isolado em seu próprio try/except (mesmo padrão de `_efetivar_sync`
    # em previsoes_service.py — um item falhar não derruba o lote inteiro).
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        sucesso, falhas = [], []
        for codigo_venc in codigos_venc:
            try:
                cur.execute("SELECT codigo FROM Duplicata_Rec_Venc WHERE codigo = %s", (int(codigo_venc),))
                if not cur.fetchone():
                    falhas.append({"codigo": codigo_venc, "message": "Vencimento não encontrado."})
                    continue
                cur.execute(
                    "UPDATE Duplicata_Rec_Venc SET situacao_duplicata = %s WHERE codigo = %s",
                    (situacao_duplicata, int(codigo_venc)),
                )
                sucesso.append(codigo_venc)
            except Exception as e:
                falhas.append({"codigo": codigo_venc, "message": str(e)})
        conn.commit()
        cur.close(); conn.close()
        return {"success": len(falhas) == 0, "alterados": sucesso, "falhas": falhas}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def alterar_situacao_vencimento_lote(servidor: str, banco: str, codigos_venc: list, situacao_duplicata: int) -> dict:
    return await asyncio.to_thread(_alterar_situacao_vencimento_lote_sync, servidor, banco, codigos_venc, situacao_duplicata)


async def excluir(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    return await asyncio.to_thread(_excluir_sync, servidor, banco, codigo_duplicata)


async def alterar_numero(servidor: str, banco: str, codigo_duplicata: int, novo_numero: int) -> dict:
    return await asyncio.to_thread(_alterar_numero_sync, servidor, banco, codigo_duplicata, novo_numero)


async def notas_disponiveis(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    return await asyncio.to_thread(_notas_disponiveis_sync, servidor, banco, codigo_duplicata)


async def vincular_nf(servidor: str, banco: str, codigo_duplicata: int, nf_fiscal: int) -> dict:
    return await asyncio.to_thread(_vincular_nf_sync, servidor, banco, codigo_duplicata, nf_fiscal)


async def desvincular_nf(servidor: str, banco: str, codigo_duplicata: int, nf_fiscal: int) -> dict:
    return await asyncio.to_thread(_desvincular_nf_sync, servidor, banco, codigo_duplicata, nf_fiscal)


async def list_tipos_mov(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipos_mov_sync, servidor, banco)


async def emitir_recibo(
    servidor: str, banco: str, *, recebemos: str, valor: float, referente: str,
    data_recibo: str | None = None, assinatura: str | None = None,
) -> dict:
    return await asyncio.to_thread(
        _emitir_recibo_sync, servidor, banco, recebemos=recebemos, valor=valor,
        referente=referente, data_recibo=data_recibo, assinatura=assinatura,
    )

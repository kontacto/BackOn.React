"""Financeiro > Contas a Pagar — espelho de contas_receber_service.py pro
lado Pagar. Ver aquele módulo pro rastreio/decisões compartilhadas; este
docstring cobre só as diferenças reais do lado Pagar.

Fonte VB6 rastreada (linhagem real `backon.vbp`):
- `Geral/FRMCONNFPAG.frm` ("Consulta de Notas Fiscais a Pagar...") —
  busca sobre `Pagar`, mesmo padrão de `FRMCONNFREC.frm`.
- `Geral/frmTraNFPag.frm` ("Notas Fiscais a Pagar...") — CRUD de `Pagar` +
  lançamento avulso, mesmo padrão de `frmTraNFRec.frm`.
- `Revenda/frmmandup.frm` ("Duplicatas a Pagar...", 3021 linhas,
  referenciado por `backon.vbp` — não existe em `Geral`) — manutenção de
  `Duplicata_Pagar`/`Duplicata_Pag_Venc`. **Sem botão "Imprimir Boleto"
  nem "Centro de Resultados"** (confirmado por leitura completa dos Tags
  dos botões — 15 Command buttons contra os 18 do lado Receber) — não é
  gap de migração, o legado nunca teve essas 2 ações aqui (faz sentido:
  não se emite boleto pra pagar, e a tela de rateio de custo do lado
  Pagar nunca foi exposta nesta tela específica).

**Baixa/Cancelamento/Lote — CORREÇÃO 2026-08-28** (mesmo erro do lado
Receber, ver aquele módulo pro detalhe completo): a baixa/cancelamento
não vive em `frmmandup.frm` (só manutenção, sem baixa mesmo) — vive num
form separado, `Revenda/FrmManPap.frm` (2 modos via flag global
`CancelaPgP`: `"P"`=Pagamento, `"C"`=Cancelamento). Núcleo compartilhado
(`_baixar_parcela_core`/`_cancelar_baixa_core`/`_gerar_vencimento_
residual`/`_rollup_cabecalho`) importado de `contas_receber_service.py`
— mesmo padrão já usado pra `_split_parcelas`. **Sem Montante** —
exclusivo do lado Receber, confirmado pela fonte (`Data(5)` só existe no
painel "Por Data" de `FrmManPar.frm`).

**Schema real, verificado ao vivo contra ARGEN TESTE** antes de escrever
qualquer SQL — inclusive o `DEFAULT ((0))` de `Pagar.cod_n_fiscal` (mesmo
padrão do lado Receber, já corrigido lá) replicado aqui desde o início:
`cod_n_fiscal` sempre gravado como `NULL` explícito no avulso, nunca
omitido. `Duplicata_Pagar.duplicata` é `float` (não `int`, diferente do
lado Receber — já documentado em `transferencia_contas_service.py`),
respeitado tal como o schema real é."""
import asyncio
from datetime import datetime

from db.connection import _open_conn
from services.transferencia_contas_service import _controle_flags_sync, _resolver_numero_duplicata_sync
from services.contas_receber_service import _split_parcelas, _baixar_parcela_core, _cancelar_baixa_core


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

        if filtros.get("fornecedor"):
            where.append("dp.fornecedor = %s")
            params.append(filtros["fornecedor"])

        if filtros.get("busca"):
            termo = f"%{filtros['busca']}%"
            where.append("(f.nome LIKE %s OR f.fantasia LIKE %s OR CAST(dp.duplicata AS VARCHAR(20)) LIKE %s)")
            params.extend([termo, termo, termo])

        situacao = (filtros.get("situacao") or "").upper()
        if situacao == "PG":
            where.append("dp.situacao = 'PG'")
        elif situacao == "A":
            where.append("dp.situacao = 'A'")
        elif situacao == "V":
            where.append(
                "dp.situacao = 'A' AND EXISTS (SELECT 1 FROM Duplicata_Pag_Venc v "
                "WHERE v.duplicata = dp.codigo AND v.situacao <> 'PG' AND v.dt_vencimento < CAST(GETDATE() AS DATE))"
            )

        if filtros.get("data_ini") and filtros.get("data_fim"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Pag_Venc v WHERE v.duplicata = dp.codigo "
                "AND v.dt_vencimento BETWEEN %s AND %s)"
            )
            params.extend([filtros["data_ini"], filtros["data_fim"]])

        # Filtros extras, rastreados de `Revenda/frmcondup.frm` ("Consulta
        # de Duplicatas a Pagar..."), mirror dos que já existem em
        # `contas_receber_service._listar_sync` a partir de
        # `FRMCONDur.frm` — ver AJUSTES.md #039. `emissao_ini`/`emissao_fim`
        # é filtro NOVO em relação ao lado Receber (esse campo existe na
        # fonte real de Pagar, `Campo(0)`/`Campo(1)`).
        if filtros.get("duplicata_num"):
            where.append("dp.duplicata = %s")
            params.append(filtros["duplicata_num"])

        if filtros.get("desmembramento"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Pag_Venc v WHERE v.duplicata = dp.codigo "
                "AND v.desmembramento = %s)"
            )
            params.append(filtros["desmembramento"])

        if filtros.get("valor"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Pag_Venc v WHERE v.duplicata = dp.codigo "
                "AND CAST(v.valor AS NUMERIC(15,2)) = %s)"
            )
            params.append(filtros["valor"])

        if filtros.get("numero_boleto"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Pag_Venc v WHERE v.duplicata = dp.codigo "
                "AND v.numero_boleto = %s)"
            )
            params.append(filtros["numero_boleto"])

        if filtros.get("num_doc_pag"):
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Pag_Venc v WHERE v.duplicata = dp.codigo "
                "AND v.num_doc_pag LIKE %s)"
            )
            params.append(f"%{filtros['num_doc_pag']}%")

        if filtros.get("emissao_ini") and filtros.get("emissao_fim"):
            where.append("dp.dt_emissao BETWEEN %s AND %s")
            params.extend([filtros["emissao_ini"], filtros["emissao_fim"]])

        sql = (
            "SELECT dp.codigo, dp.fornecedor, f.nome AS fornecedor_nome, f.fantasia AS fornecedor_fantasia, "
            "dp.duplicata, dp.desmembramento, dp.dt_emissao, dp.valor, dp.situacao, "
            "dp.num_parcelas, dp.parcelas_pagas, "
            "(SELECT MIN(v.dt_vencimento) FROM Duplicata_Pag_Venc v WHERE v.duplicata = dp.codigo AND v.situacao <> 'PG') AS proximo_vencimento, "
            "(SELECT SUM(v.valor) FROM Duplicata_Pag_Venc v WHERE v.duplicata = dp.codigo AND v.situacao <> 'PG') AS valor_em_aberto "
            "FROM Duplicata_Pagar dp LEFT JOIN Fornecedor f ON f.codigo_int = dp.fornecedor "
            f"WHERE {' AND '.join(where)} ORDER BY dp.dt_emissao DESC, dp.codigo DESC"
        )
        cur.execute(sql, tuple(params))
        items = []
        for r in cur.fetchall():
            vencido = False
            if r.get("proximo_vencimento") and r.get("situacao") == "A":
                venc = r["proximo_vencimento"]
                venc_date = venc if hasattr(venc, "isoformat") and not isinstance(venc, str) else datetime.strptime(str(venc)[:10], "%Y-%m-%d").date()
                vencido = venc_date < datetime.now().date()
            items.append({
                "codigo": r["codigo"],
                "fornecedor": r["fornecedor"],
                "fornecedor_nome": r.get("fornecedor_fantasia") or r.get("fornecedor_nome"),
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


def _notas_disponiveis_sync(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    """"Incluir Nota Fiscal" — réplica de `frmmandup.frm::Command5_Click`.
    Mirror de `contas_receber_service._notas_disponiveis_sync`: outras
    Notas em aberto de QUALQUER fornecedor com a mesma raiz de documento
    (matriz/filiais) — no lado Fornecedor, o documento mora direto na
    coluna `Fornecedor.codigo` (nvarchar), não numa `cgc_cpf` separada
    como em `Cliente` (confirmado ao vivo contra GERDELL/BARESTELA,
    2026-08-31). Achado do usuário — ver AJUSTES.md #039."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT dp.fornecedor FROM Duplicata_Pagar dp WHERE dp.codigo = %s", (codigo_duplicata,))
        dup = cur.fetchone()
        if not dup:
            cur.close(); conn.close()
            return {"success": False, "message": "Duplicata não encontrada.", "items": []}

        cur.execute("SELECT codigo FROM Fornecedor WHERE codigo_int = %s", (dup["fornecedor"],))
        row = cur.fetchone()
        doc_raiz = (row.get("codigo") or "")[:8] if row else ""

        cur.execute(
            "SELECT p.codigo, f.codigo_int AS codigo_fornecedor, f.nome, p.nota_fiscal, p.serie, p.valor "
            "FROM Pagar p JOIN Fornecedor f ON f.codigo_int = p.fornecedor "
            "WHERE p.situacao = 'A' AND LEFT(f.codigo,8) = %s",
            (doc_raiz,),
        )
        items = [
            {
                "codigo": r["codigo"], "codigo_fornecedor": r["codigo_fornecedor"], "fornecedor_nome": r["nome"],
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
        cur.execute("SELECT codigo FROM Duplicata_Pagar WHERE codigo = %s", (codigo_duplicata,))
        if not cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Duplicata não encontrada."}

        cur.execute(
            "SELECT duplicata FROM Duplicata_Pag_Nf WHERE duplicata = %s AND nf_fiscal = %s",
            (codigo_duplicata, nf_fiscal),
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Nota Fiscal já vinculada a esta duplicata."}

        cur.execute("SELECT situacao FROM Pagar WHERE codigo = %s", (nf_fiscal,))
        nf = cur.fetchone()
        if not nf:
            cur.close(); conn.close()
            return {"success": False, "message": "Nota Fiscal não encontrada."}
        if nf.get("situacao") != "A":
            cur.close(); conn.close()
            return {"success": False, "message": "Esta Nota Fiscal não está mais em aberto."}

        cur.execute("INSERT INTO Duplicata_Pag_Nf (duplicata, nf_fiscal) VALUES (%s,%s)", (codigo_duplicata, nf_fiscal))
        cur.execute("UPDATE Pagar SET situacao = 'DU' WHERE codigo = %s", (nf_fiscal,))
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
            "SELECT COUNT(*) AS qtd FROM Duplicata_Pag_Venc WHERE duplicata = %s AND situacao = 'PG'",
            (codigo_duplicata,),
        )
        if cur.fetchone()["qtd"] > 0:
            cur.close(); conn.close()
            return {"success": False, "message": (
                "Esta duplicata já possui vencimentos pagos — só é possível alterar dados sobre os vencimentos."
            )}

        cur.execute(
            "SELECT duplicata FROM Duplicata_Pag_Nf WHERE duplicata = %s AND nf_fiscal = %s",
            (codigo_duplicata, nf_fiscal),
        )
        if not cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Esta Nota Fiscal não está vinculada a esta duplicata."}

        cur.execute("DELETE FROM Duplicata_Pag_Nf WHERE duplicata = %s AND nf_fiscal = %s", (codigo_duplicata, nf_fiscal))
        cur.execute("UPDATE Pagar SET situacao = 'A' WHERE codigo = %s", (nf_fiscal,))
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
# "Alterar Nº Duplicata" — réplica de `frmmandup.frm::Command15_Click`.
# Mirror de `contas_receber_service._alterar_numero_sync` — mesma limpeza
# de previsões de Transferência p/Fluxo de Caixa vinculadas ao número
# antigo, com `flag_transf_caixa = 'P'` (Pagar, confirmado em
# `previsoes_service.py`) em vez de `'R'`.
# =============================================================================

def _alterar_numero_sync(servidor: str, banco: str, codigo_duplicata: int, novo_numero: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM Duplicata_Pagar WHERE codigo = %s", (codigo_duplicata,))
        if not cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Duplicata não encontrada."}

        cur.execute(
            "SELECT codigo FROM Duplicata_Pagar WHERE codigo <> %s AND duplicata = %s",
            (codigo_duplicata, novo_numero),
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Já existe uma duplicata cadastrada com esse número."}

        cur.execute("UPDATE Duplicata_Pagar SET duplicata = %s WHERE codigo = %s", (novo_numero, codigo_duplicata))
        cur.execute(
            "DELETE p FROM Previsoes p INNER JOIN Duplicata_Pag_Venc v ON v.codigo = p.cod_transf_caixa "
            "WHERE p.flag_transf_caixa = 'P' AND v.duplicata = %s",
            (codigo_duplicata,),
        )
        cur.execute("UPDATE Duplicata_Pag_Venc SET transf_previsao = '' WHERE duplicata = %s", (codigo_duplicata,))

        conn.commit()
        cur.close(); conn.close()
        return {"success": True, "duplicata": novo_numero}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _detalhe_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT dp.codigo, dp.fornecedor, f.nome AS fornecedor_nome, f.fantasia AS fornecedor_fantasia, "
            "dp.duplicata, dp.desmembramento, dp.dt_emissao, dp.valor, dp.situacao, "
            "dp.num_parcelas, dp.parcelas_pagas "
            "FROM Duplicata_Pagar dp LEFT JOIN Fornecedor f ON f.codigo_int = dp.fornecedor WHERE dp.codigo = %s",
            (codigo,),
        )
        header = cur.fetchone()
        if not header:
            cur.close(); conn.close()
            return {"success": False, "message": "Duplicata não encontrada."}
        header["fornecedor_nome"] = header.pop("fornecedor_fantasia") or header["fornecedor_nome"]
        header["dt_emissao"] = str(header["dt_emissao"]) if header.get("dt_emissao") else None
        header["valor"] = float(header.get("valor") or 0)

        cur.execute(
            "SELECT codigo, duplicata, desmembramento, dt_vencimento, valor, situacao, "
            "data_pag, valor_pag, desconto_pag, juros_pag, conta, forma_pag, obs_vencimento "
            "FROM Duplicata_Pag_Venc WHERE duplicata = %s ORDER BY desmembramento",
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
            "SELECT p.codigo, p.nota_fiscal, p.serie, p.tipo_mov, p.cod_n_fiscal "
            "FROM Duplicata_Pag_Nf dpn JOIN Pagar p ON p.codigo = dpn.nf_fiscal WHERE dpn.duplicata = %s",
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
# Lançamento avulso — réplica de `frmTraNFPag.frm`'s CmdGravar (TemNF=False)
# + botão "Gerar Duplicata" (split de parcelas, mesma regra do lado Receber).
# =============================================================================

def _criar_avulsa_sync(servidor: str, banco: str, req: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT nome FROM Fornecedor WHERE codigo_int = %s", (req["fornecedor"],))
        fornecedor = cur.fetchone()
        if not fornecedor:
            cur.close(); conn.close()
            return {"success": False, "message": "Fornecedor não encontrado."}

        cur.execute(
            "SELECT codigo FROM Pagar WHERE fornecedor = %s AND nota_fiscal = %s AND ISNULL(serie,'') = %s",
            (req["fornecedor"], req["numero"], (req.get("serie") or "").strip()),
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": (
                f"Já existe um lançamento com Número {req['numero']} Série {req.get('serie') or ''} "
                "para este fornecedor."
            )}

        parcelas_qtd = max(1, int(req.get("parcelas") or 1))
        valor = float(req["valor"])
        dt_emissao = req["dt_emissao"]
        primeiro_venc = datetime.strptime(req["dt_primeiro_vencimento"][:10], "%Y-%m-%d").date()
        parcelas = _split_parcelas(valor, parcelas_qtd, primeiro_venc)

        # `cod_n_fiscal` gravado EXPLICITAMENTE como NULL — mesmo achado
        # (e mesmo fix) já confirmado ao vivo no lado Receber: a coluna
        # tem `DEFAULT 0`, omiti-la gravaria 0 em vez de NULL e quebraria
        # a guarda de exclusão (avulso vs. NF real).
        cur.execute(
            "INSERT INTO Pagar (fornecedor, nota_fiscal, serie, dt_emissao, dt_entrada, valor, "
            "tipo_mov, cod_n_fiscal, valor_contabilizado, situacao, dt_vencimento) "
            "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,%s,'DU',%s)",
            (req["fornecedor"], req["numero"], req.get("serie") or "", dt_emissao, dt_emissao, valor,
             req["tipo_mov"], valor, primeiro_venc.isoformat()),
        )
        pagar_codigo = cur.fetchone()["codigo"]

        flags = _controle_flags_sync(cur)
        duplicata, desmembramento = _resolver_numero_duplicata_sync(cur, flags, req["numero"])
        cur.execute(
            "INSERT INTO Duplicata_Pagar (fornecedor, duplicata, desmembramento, dt_emissao, "
            "num_parcelas, parcelas_pagas, valor, situacao) "
            "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,0,%s,'A')",
            (req["fornecedor"], duplicata, desmembramento or (req.get("serie") or ""), dt_emissao,
             parcelas_qtd, valor),
        )
        dup_codigo = cur.fetchone()["codigo"]

        for i, (venc, v) in enumerate(parcelas, start=1):
            cur.execute(
                "INSERT INTO Duplicata_Pag_Venc (duplicata, desmembramento, dt_vencimento, valor, "
                "situacao, obs_vencimento) VALUES (%s,%s,%s,%s,'A',%s)",
                (dup_codigo, i, venc.isoformat(), v, req.get("observacao") or ""),
            )

        cur.execute("INSERT INTO Duplicata_Pag_Nf (duplicata, nf_fiscal) VALUES (%s,%s)", (dup_codigo, pagar_codigo))

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
# Baixa / Cancelamento / Lote "Por Data" — réplica de
# `Revenda/FrmManPap.frm`, núcleo compartilhado com o lado Receber (ver
# docstring do módulo). Sem trava de "valor máximo" (confirmado ausente
# no lado Pagar) e sem Montante (exclusivo Receber).
# =============================================================================

def _baixar_parcela_sync(servidor: str, banco: str, req: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        resultado = _baixar_parcela_core(
            cur, "Duplicata_Pag_Venc", "Duplicata_Pagar", req, validar_valor_max=False,
            campos_extra=("num_doc_pag",),
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
        resultado = _cancelar_baixa_core(cur, "Duplicata_Pag_Venc", "Duplicata_Pagar", req["codigo_venc"])
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
        if filtros.get("fornecedor"):
            where.append("dp.fornecedor = %s")
            params.append(filtros["fornecedor"])
        sql = (
            "SELECT v.codigo, v.duplicata, v.desmembramento, v.dt_vencimento, v.valor, v.situacao, "
            "v.data_pag, dp.fornecedor, COALESCE(f.fantasia, f.nome) AS fornecedor_nome "
            "FROM Duplicata_Pag_Venc v JOIN Duplicata_Pagar dp ON dp.codigo = v.duplicata "
            "LEFT JOIN Fornecedor f ON f.codigo_int = dp.fornecedor "
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
                "fornecedor": r.get("fornecedor"), "fornecedor_nome": r.get("fornecedor_nome"),
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
                    r = _cancelar_baixa_core(cur, "Duplicata_Pag_Venc", "Duplicata_Pagar", codigo_venc)
                else:
                    cur.execute("SELECT valor FROM Duplicata_Pag_Venc WHERE codigo = %s", (codigo_venc,))
                    row = cur.fetchone()
                    if not row:
                        falhas.append({"codigo_venc": codigo_venc, "message": "Parcela não encontrada."})
                        continue
                    item_req = {
                        "codigo_venc": codigo_venc, "data_pag": req.get("data_pag"),
                        "valor_pag": float(row["valor"] or 0),
                        "conta": req.get("conta"), "forma_pag": req.get("forma_pag"),
                    }
                    r = _baixar_parcela_core(cur, "Duplicata_Pag_Venc", "Duplicata_Pagar", item_req, validar_valor_max=False)
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


def _editar_parcela_sync(servidor: str, banco: str, req: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM Duplicata_Pag_Venc WHERE codigo = %s", (req["codigo_venc"],))
        parcela = cur.fetchone()
        if not parcela:
            cur.close(); conn.close()
            return {"success": False, "message": "Parcela não encontrada."}
        if parcela["situacao"] == "PG":
            cur.close(); conn.close()
            return {"success": False, "message": "Esta parcela já está paga. Alterações não permitidas."}
        cur.execute(
            "UPDATE Duplicata_Pag_Venc SET dt_vencimento = %s, valor = %s, obs_vencimento = %s WHERE codigo = %s",
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
# Exclusão — com guarda (mesma melhoria deliberada do lado Receber).
# =============================================================================

def _excluir_sync(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM Duplicata_Pagar WHERE codigo = %s", (codigo_duplicata,))
        if not cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "message": "Duplicata não encontrada."}

        cur.execute(
            "SELECT COUNT(*) AS qtd FROM Duplicata_Pag_Venc WHERE duplicata = %s AND situacao = 'PG'",
            (codigo_duplicata,),
        )
        if cur.fetchone()["qtd"] > 0:
            cur.close(); conn.close()
            return {"success": False, "message": (
                "Não é possível excluir: existem parcelas já pagas nesta duplicata."
            )}

        cur.execute("SELECT nf_fiscal FROM Duplicata_Pag_Nf WHERE duplicata = %s", (codigo_duplicata,))
        pagar_codigos = [r["nf_fiscal"] for r in (cur.fetchall() or [])]

        cur.execute("DELETE FROM Duplicata_Pag_Venc WHERE duplicata = %s", (codigo_duplicata,))
        cur.execute("DELETE FROM Duplicata_Pag_Nf WHERE duplicata = %s", (codigo_duplicata,))
        cur.execute("DELETE FROM Duplicata_Pagar WHERE codigo = %s", (codigo_duplicata,))

        for pc in pagar_codigos:
            cur.execute("SELECT cod_n_fiscal FROM Pagar WHERE codigo = %s", (pc,))
            r = cur.fetchone()
            if r and r.get("cod_n_fiscal") is None:
                cur.execute("DELETE FROM Pagar WHERE codigo = %s", (pc,))
            else:
                cur.execute("UPDATE Pagar SET situacao = 'A' WHERE codigo = %s", (pc,))

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
# Lookup — Tipo de Movimentação elegível (Entrada, `left(codigo,1)='E'`,
# mesmo padrão do combo em `frmTraNFPag.frm`).
# =============================================================================

def _list_tipos_mov_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, descricao FROM tipo_mov WHERE LEFT(codigo,1) = 'E' AND TRANSF_PAGAR = 'S' "
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


async def editar_parcela(servidor: str, banco: str, req: dict) -> dict:
    return await asyncio.to_thread(_editar_parcela_sync, servidor, banco, req)


async def excluir(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    return await asyncio.to_thread(_excluir_sync, servidor, banco, codigo_duplicata)


async def list_tipos_mov(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipos_mov_sync, servidor, banco)


async def notas_disponiveis(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    return await asyncio.to_thread(_notas_disponiveis_sync, servidor, banco, codigo_duplicata)


async def vincular_nf(servidor: str, banco: str, codigo_duplicata: int, nf_fiscal: int) -> dict:
    return await asyncio.to_thread(_vincular_nf_sync, servidor, banco, codigo_duplicata, nf_fiscal)


async def desvincular_nf(servidor: str, banco: str, codigo_duplicata: int, nf_fiscal: int) -> dict:
    return await asyncio.to_thread(_desvincular_nf_sync, servidor, banco, codigo_duplicata, nf_fiscal)


async def alterar_numero(servidor: str, banco: str, codigo_duplicata: int, novo_numero: int) -> dict:
    return await asyncio.to_thread(_alterar_numero_sync, servidor, banco, codigo_duplicata, novo_numero)

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

**Mesmo achado do lado Receber, confirmado de novo aqui**: procurei toda
gravação de `situacao='PG'` em `frmmandup.frm` inteiro — só leituras/
guardas, nunca uma escrita. Baixa manual é NOVA aqui também (não é
exclusividade do lado Receber) — mesma decisão de escopo já aprovada
pelo usuário se estende naturalmente, mesmo desenho de colunas
(`data_pag`/`valor_pag`/`desconto_pag`/`juros_pag`/`conta`/`forma_pag`,
todas existem em `Duplicata_Pag_Venc` com os mesmos nomes).

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
from services.contas_receber_service import _split_parcelas


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
# Baixa manual — funcionalidade NOVA (ver docstring do módulo).
# =============================================================================

def _baixar_parcela_sync(servidor: str, banco: str, req: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, duplicata, situacao FROM Duplicata_Pag_Venc WHERE codigo = %s",
            (req["codigo_venc"],),
        )
        parcela = cur.fetchone()
        if not parcela:
            cur.close(); conn.close()
            return {"success": False, "message": "Parcela não encontrada."}
        if parcela["situacao"] == "PG":
            cur.close(); conn.close()
            return {"success": False, "message": "Esta parcela já está paga."}

        cur.execute(
            "UPDATE Duplicata_Pag_Venc SET situacao = 'PG', data_pag = %s, valor_pag = %s, "
            "desconto_pag = %s, juros_pag = %s, conta = %s, forma_pag = %s WHERE codigo = %s",
            (req["data_pag"], req["valor_pag"], req.get("desconto_pag") or 0, req.get("juros_pag") or 0,
             req.get("conta"), req.get("forma_pag"), req["codigo_venc"]),
        )

        dup_codigo = parcela["duplicata"]
        cur.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN situacao = 'PG' THEN 1 ELSE 0 END) AS pagas "
            "FROM Duplicata_Pag_Venc WHERE duplicata = %s",
            (dup_codigo,),
        )
        contagem = cur.fetchone()
        nova_situacao = "PG" if contagem["pagas"] == contagem["total"] else "A"
        cur.execute(
            "UPDATE Duplicata_Pagar SET parcelas_pagas = %s, situacao = %s WHERE codigo = %s",
            (contagem["pagas"], nova_situacao, dup_codigo),
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


async def editar_parcela(servidor: str, banco: str, req: dict) -> dict:
    return await asyncio.to_thread(_editar_parcela_sync, servidor, banco, req)


async def excluir(servidor: str, banco: str, codigo_duplicata: int) -> dict:
    return await asyncio.to_thread(_excluir_sync, servidor, banco, codigo_duplicata)


async def list_tipos_mov(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipos_mov_sync, servidor, banco)

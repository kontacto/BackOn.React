"""Borderô de Cilindros (Fase 3c do módulo Cilindros) — relatório de
consulta sobre `Viagem`/`Viagem_Cilindro`/`Viagem_Retorno`, populadas pela
tela de Manutenção de Viagens (`viagem_service.py`). Legado:
`FrmManCil.frm`, `Frame11` "Bordero de Cilindros". Ver PENDENCIAS.md >
"Cilindros" > "Fase 3c" para o rastreio completo dos filtros.

Diferença deliberada do legado (confirmado com o usuário via pergunta
direta): saída é **consulta em tela + exportação Excel**, sem impressão
formatada. O resumo cruzado por status usa `GROUP BY` real (SQL), não a
tabela temporária por máquina (`temp_cilindros_<computador>`) que o legado
usa só por limitação de uma era sem essa capacidade fácil em Access/DAO —
ver "Não replicar truques VB6" no CLAUDE.md.

"Em Aberto" (radio do legado) = o item ainda tem uma baixa pendente em
`Viagem_Retorno` (`viagem_retorno=0`) — só os status que geram pendência
(AP/APT/DT/RT) têm essa marca; um item que já É a baixa de outro
(DP/DPT) nunca aparece como "em aberto" por definição.
"""
import asyncio

from db.connection import _open_conn


def _row(r) -> dict:
    return dict(r)


_JOINS = (
    "FROM Viagem_Cilindro vc "
    "JOIN Viagem v ON v.codigo=vc.viagem "
    "LEFT JOIN Cilindro cil ON cil.cod=vc.cilindro_retorno "
    "LEFT JOIN Cilindro_Serie cs ON cs.codigo=vc.num_serie_retorno "
    "LEFT JOIN Cliente cli ON cli.codigo=vc.cliente AND v.tipo_viagem=0 "
    "LEFT JOIN Viagem_Contrato vctx ON vctx.viagem=vc.codigo "
    "LEFT JOIN Contratos_Produtos cp ON cp.codigo=vctx.contrato "
    "LEFT JOIN Contratos ctr ON ctr.codigo=cp.contrato "
)


def _build_where(filtros: dict):
    where = "1=1"
    params: list = []
    if filtros.get("tipo_viagem") is not None:
        where += " AND v.tipo_viagem=%s"
        params.append(filtros["tipo_viagem"])
    status = filtros.get("status") or []
    if status:
        placeholders = ",".join(["%s"] * len(status))
        where += f" AND vc.status_retorno IN ({placeholders})"
        params += list(status)
    if filtros.get("saida_de"):
        where += " AND v.saida>=%s"
        params.append(filtros["saida_de"])
    if filtros.get("saida_ate"):
        where += " AND v.saida<=%s"
        params.append(filtros["saida_ate"])
    if filtros.get("retorno_de"):
        where += " AND v.retorno>=%s"
        params.append(filtros["retorno_de"])
    if filtros.get("retorno_ate"):
        where += " AND v.retorno<=%s"
        params.append(filtros["retorno_ate"])
    if filtros.get("grupo_gas"):
        where += " AND cil.grupo_gas=%s"
        params.append(filtros["grupo_gas"])
    if filtros.get("capacidade"):
        where += " AND cil.capacidade=%s"
        params.append(filtros["capacidade"])
    if filtros.get("pressao"):
        where += " AND cil.pressao=%s"
        params.append(filtros["pressao"])
    if filtros.get("padrao"):
        where += " AND cil.padrao=%s"
        params.append(filtros["padrao"])
    doc = (filtros.get("documento") or "").strip()
    if doc:
        where += " AND (vc.os_saida=%s OR vc.os_retorno=%s OR CAST(vc.nf_retorno AS NVARCHAR(20))=%s OR cs.numero_de_serie=%s)"
        params += [doc, doc, doc, doc]
    if filtros.get("segmento") and filtros.get("tipo_viagem") != 1:
        where += " AND cli.segmento=%s"
        params.append(filtros["segmento"])
    if filtros.get("situacao_contrato"):
        where += " AND ctr.situacao=%s"
        params.append(filtros["situacao_contrato"])
    return where, params


def _list_bordero_sync(servidor: str, banco: str, filtros: dict) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where, params = _build_where(filtros)

        em_aberto = filtros.get("em_aberto")
        having_aberto = ""
        if em_aberto is True:
            having_aberto = " AND EXISTS (SELECT 1 FROM Viagem_Retorno vry WHERE vry.viagem_saida=vc.codigo AND vry.viagem_retorno=0)"
        elif em_aberto is False:
            having_aberto = " AND NOT EXISTS (SELECT 1 FROM Viagem_Retorno vry WHERE vry.viagem_saida=vc.codigo AND vry.viagem_retorno=0)"

        sql = (
            "SELECT vc.codigo, vc.ordem, vc.status_saida, vc.status_retorno, vc.os_saida, vc.os_retorno, "
            "vc.nf_retorno, vc.cliente, v.codigo AS viagem_codigo, v.tipo_viagem, v.saida, v.retorno, "
            "cil.codigo AS cil_codigo, cil.capacidade, cil.pressao, cil.padrao, cil.descricao, cil.grupo_gas, "
            "cs.numero_de_serie AS nds_retorno, "
            "(CASE WHEN v.tipo_viagem=1 THEN (SELECT nome FROM Fornecedor WHERE codigo_int=vc.cliente) "
            "ELSE (SELECT nome FROM Cliente WHERE codigo=vc.cliente) END) AS cliente_nome, "
            "(CASE WHEN EXISTS (SELECT 1 FROM Viagem_Retorno vry WHERE vry.viagem_saida=vc.codigo AND vry.viagem_retorno=0) THEN 1 ELSE 0 END) AS em_aberto "
            f"{_JOINS}WHERE {where}{having_aberto} "
            "ORDER BY cliente_nome, v.codigo, vc.ordem"
        )
        cur.execute(sql, tuple(params))
        rows = [_row(r) for r in cur.fetchall()]
        cur.close()

        # Agrupamento por cliente com subtotais feito em Python — o detalhe
        # por item já precisa estar na resposta pra exibir na tela, então uma
        # segunda consulta agregada só duplicaria a mesma leitura.
        grupos: list = []
        atual = None
        for r in rows:
            chave = r.get("cliente_nome") or f"#{r['cliente']}"
            if atual is None or atual["cliente"] != chave:
                atual = {"cliente": chave, "itens": [], "saida": 0, "retorno": 0, "em_aberto": 0}
                grupos.append(atual)
            atual["itens"].append(r)
            atual["saida"] += 1
            if r["em_aberto"]:
                atual["em_aberto"] += 1
            else:
                atual["retorno"] += 1

        total = {
            "saida": len(rows),
            "retorno": sum(g["retorno"] for g in grupos),
            "em_aberto": sum(g["em_aberto"] for g in grupos),
        }
        return {"success": True, "grupos": grupos, "total": total}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "grupos": [], "total": {}}
    finally:
        conn.close()


def _resumo_bordero_sync(servidor: str, banco: str, filtros: dict) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where, params = _build_where(filtros)
        sql = (
            "SELECT cil.grupo_gas, cil.capacidade, cil.pressao, cil.padrao, cil.descricao, "
            "vc.status_retorno AS status, COUNT(*) AS total "
            f"{_JOINS}WHERE {where} "
            "GROUP BY cil.grupo_gas, cil.capacidade, cil.pressao, cil.padrao, cil.descricao, vc.status_retorno "
            "ORDER BY cil.grupo_gas, cil.capacidade, cil.pressao, cil.padrao"
        )
        cur.execute(sql, tuple(params))
        items = [_row(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


async def list_bordero(servidor: str, banco: str, filtros: dict) -> dict:
    return await asyncio.to_thread(_list_bordero_sync, servidor, banco, filtros)


async def resumo_bordero(servidor: str, banco: str, filtros: dict) -> dict:
    return await asyncio.to_thread(_resumo_bordero_sync, servidor, banco, filtros)

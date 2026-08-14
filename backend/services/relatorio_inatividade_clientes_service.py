"""Inatividade de Clientes — Painel de Relatórios > Clientes.

Migração de `Geral\\FrmRelCliSMV.frm` (1065 linhas). Detecta clientes sem
compra num período, com 3 "ciclos" de frequência de compra (janelas de
dias configuráveis contadas a partir de uma data-base), sub-checks de
faturamento de Contrato, e filtro "com/sem patrimônio" (linha de produto
de contrato ativa).

**Generalização Pedido/OS** (mesma diretriz 2026-08-07 já usada em todo o
grupo Vendas): "compra" nesta migração é `pedido_venda`(situação 'PG')
OU `os`(situação 'PG'), não `comanda`+`movimentacao` — o legado só via
`comanda` porque era o único ledger que existia; aqui `comanda` é só o
envelope de fechamento (contratos/checkout), Pedido e O.S. já são
documentos próprios. Como Contrato não passa por `pedido_venda`/`os`
nesta migração, a exclusão explícita de `codigo_int <> Cod_Servico_
Contrato` do legado já não é necessária — naturalmente contrato nunca
aparece nessas duas tabelas.

**Ciclos 1/2/3**: réplica fiel do legado — só contam `pedido_venda`
(não O.S.), já que no legado "frequência de compra" também era só sobre
Pedido, mesmo antes desta migração generalizar o resto. Data-base do
ciclo: "Última Compra do Cliente" (por padrão, cada cliente usa sua
própria última compra antes do período) ou "Especificar" (uma data única
pra todos).

**"Acima de" (nome do campo no legado, na prática um filtro de DATA)**:
quando informado, exclui do relatório clientes cuja última compra antes
do período seja anterior a essa data — funciona como um piso de
recência, não um valor mínimo de compra (apesar do rótulo sugerir isso).

**Sub-checks de Contrato** (tabelas confirmadas reais e já usadas pelo
módulo Contratos desta migração — `contratos`/`contratos_produtos`,
`comanda_contrato`, `Receber`/`Duplicata_Receber`/`Duplicata_Rec_Venc`/
`Duplicata_Rec_Nf`):
- **Patrimônio** = linha de `contratos_produtos` com `data_inicio`
  preenchida e `data_encerramento` vazia (produto/equipamento sob
  contrato ainda ativo), opcionalmente restrita por situação do
  contrato ('A'=Aberto/'F'=Finalizado — códigos reais já usados em
  `contratos_service.py`, não os do legado que usava texto livre).
- **Último faturamento de contrato**: última `comanda.data` (situação
  'PG') ligada via `comanda_contrato` a um contrato do cliente.
  **Diferença real de série confirmada nesta migração**: o legado filtra
  `receber.serie='CM'`, mas `_faturar_contratos_sync` desta migração
  grava com `serie='CO'` — usado `'CO'`, o valor real, não o do legado.
- **Último faturamento de contrato PAGO**: data de pagamento
  (`Duplicata_Rec_Venc.data_pag`, situação 'PG') da duplicata gerada
  daquele faturamento, via a cadeia `Receber`→`Duplicata_Rec_Nf`→
  `Duplicata_Receber`→`Duplicata_Rec_Venc`.

**Simplificação consciente de performance**: o candidato é resolvido em
lote (uma query), mas os sub-checks por cliente (última compra, ciclos,
contrato) são feitos num loop — mesmo formato N+1 do legado (ele também
fazia sub-consulta por cliente candidato), aceitável porque a lista de
"clientes inativos" tende a ser pequena/moderada, não a base inteira.
Um `TOP 200` no candidato final evita um request web preso numa base
muito grande — o legado (fat client) não tinha esse limite porque
rodava localmente sem timeout de HTTP.

**Não portado**: filtro "Tabela Preço" — confirmado no legado que o
combo é `Visible=0` (nunca aparece na tela, morto na prática).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _geral_where(cur, vendedor, regiao, segmento, rota, tipo_cliente) -> tuple[str, list]:
    partes = []
    params: list = []
    if vendedor:
        partes.append("c.vendedor = %s")
        params.append(vendedor)
    if regiao:
        partes.append("c.regiao = %s")
        params.append(regiao)
    if segmento:
        partes.append("c.segmento = %s")
        params.append(segmento)
    if rota:
        partes.append("c.rota = %s")
        params.append(rota)
    if tipo_cliente:
        partes.append("c.cliente_forn = %s")
        params.append(tipo_cliente)
    return (" AND " + " AND ".join(partes)) if partes else "", params


def _inatividade_clientes_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[int], regiao: Optional[int], segmento: Optional[str], rota: Optional[int],
    tipo_cliente: Optional[int], situacao_cadastro: str,
    situacao_contrato: str, patrimonio: str,
    modo_base: str, data_base: Optional[str],
    fator1: int, fator2: int, fator3: int,
    ultima_compra_desde: Optional[str],
    exibir_contrato_faturamento: bool, exibir_contrato_pago: bool,
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "clientes": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        geral_sql, geral_p = _geral_where(cur, vendedor, regiao, segmento, rota, tipo_cliente)

        sit_sql = ""
        if situacao_cadastro == "ativo":
            sit_sql = " AND c.situacao = 'A'"
        elif situacao_cadastro == "inativo":
            sit_sql = " AND c.situacao <> 'A'"

        cur.execute(
            "SELECT TOP 200 c.codigo, c.nome, c.situacao "
            "FROM cliente c "
            "WHERE c.codigo NOT IN ("
            "  SELECT cliente FROM pedido_venda WHERE situacao='PG' AND CAST(data AS DATE) BETWEEN %s AND %s "
            "  UNION "
            "  SELECT cliente FROM os WHERE situacao='PG' AND CAST(data_entrada AS DATE) BETWEEN %s AND %s"
            ") " + geral_sql + sit_sql + " ORDER BY c.nome",
            tuple([data_ini, data_fim, data_ini, data_fim] + geral_p),
        )
        candidatos = cur.fetchall()

        clientes = []
        for cand in candidatos:
            codigo = cand["codigo"]

            # Última compra antes do período (Pedido ou O.S.)
            cur.execute(
                "SELECT MAX(data) AS ultima FROM ("
                "  SELECT data FROM pedido_venda WHERE cliente=%s AND situacao='PG' AND CAST(data AS DATE) < %s"
                "  UNION ALL "
                "  SELECT data_entrada FROM os WHERE cliente=%s AND situacao='PG' AND CAST(data_entrada AS DATE) < %s"
                ") x",
                (codigo, data_ini, codigo, data_ini),
            )
            ultima_row = cur.fetchone()
            ultima_compra = ultima_row.get("ultima") if ultima_row else None

            if ultima_compra_desde:
                if not ultima_compra or str(ultima_compra)[:10] < ultima_compra_desde:
                    continue

            # Patrimônio / situação de contrato
            if patrimonio in ("com", "sem") or situacao_contrato in ("A", "F"):
                sit_contrato_sql = ""
                params_pat = [codigo]
                if situacao_contrato in ("A", "F"):
                    sit_contrato_sql = " AND contratos.situacao = %s"
                    params_pat.append(situacao_contrato)
                cur.execute(
                    "SELECT COUNT(1) AS n FROM contratos, contratos_produtos "
                    "WHERE contratos.cliente = %s AND contratos.codigo = contratos_produtos.contrato "
                    "  AND ISNULL(contratos_produtos.data_inicio,'') <> '' "
                    "  AND ISNULL(contratos_produtos.data_encerramento,'') = ''" + sit_contrato_sql,
                    tuple(params_pat),
                )
                tem_patrimonio = int((cur.fetchone() or {}).get("n") or 0) > 0
                if patrimonio == "com" and not tem_patrimonio:
                    continue
                if patrimonio == "sem" and tem_patrimonio:
                    continue

            # Ciclos (só Pedido, mesma fidelidade do legado)
            if modo_base == "especificar" and data_base:
                databaseciclo = data_base
            else:
                databaseciclo = str(ultima_compra)[:10] if ultima_compra else data_fim

            ciclos = []
            for fator in (fator1, fator2, fator3):
                cur.execute(
                    "SELECT COUNT(1) AS qtd FROM pedido_venda "
                    "WHERE cliente=%s AND situacao='PG' "
                    "  AND CAST(data AS DATE) BETWEEN DATEADD(day, -%s, %s) AND %s",
                    (codigo, fator, databaseciclo, databaseciclo),
                )
                qtd = int((cur.fetchone() or {}).get("qtd") or 0)
                dias_medio = round(fator / qtd, 0) if qtd else None
                ciclos.append({"qtd_pedidos": qtd, "dias_medio": dias_medio})

            item = {
                "codigo": codigo, "nome": (cand.get("nome") or "").strip(),
                "situacao": (cand.get("situacao") or "").strip(),
                "ultima_compra": str(ultima_compra)[:10] if ultima_compra else None,
                "ciclos": ciclos,
            }

            if exibir_contrato_faturamento:
                cur.execute(
                    "SELECT TOP 1 c.data FROM comanda c "
                    "JOIN comanda_contrato cc ON cc.comanda = c.comanda "
                    "JOIN contratos co ON co.codigo = cc.contrato "
                    "WHERE co.cliente = %s AND c.situacao = 'PG' ORDER BY c.data DESC",
                    (codigo,),
                )
                r = cur.fetchone()
                item["ultimo_faturamento_contrato"] = str(r["data"])[:10] if r and r.get("data") else None

            if exibir_contrato_pago:
                cur.execute(
                    "SELECT TOP 1 drv.data_pag FROM Receber r "
                    "JOIN Duplicata_Rec_Nf drnf ON drnf.nf_fiscal = r.codigo "
                    "JOIN Duplicata_Receber dr ON dr.codigo = drnf.duplicata "
                    "JOIN Duplicata_Rec_Venc drv ON drv.duplicata = dr.codigo "
                    "WHERE r.cliente = %s AND r.serie = 'CO' AND drv.situacao = 'PG' "
                    "  AND r.cod_n_fiscal IN (SELECT comanda FROM comanda_contrato) "
                    "ORDER BY drv.data_pag DESC",
                    (codigo,),
                )
                r = cur.fetchone()
                item["ultimo_faturamento_contrato_pago"] = str(r["data_pag"])[:10] if r and r.get("data_pag") else None

            cur.execute(
                "SELECT ddd, tel FROM cliente_tel WHERE codigo=%s",
                (codigo,),
            )
            item["telefones"] = [f"({r.get('ddd') or ''}) {(r.get('tel') or '').strip()}" for r in cur.fetchall()]

            clientes.append(item)

        cur.close()
        return {"success": True, "clientes": clientes}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "clientes": []}
    finally:
        conn.close()


async def inatividade_clientes(
    servidor, banco, data_ini, data_fim, vendedor, regiao, segmento, rota, tipo_cliente,
    situacao_cadastro, situacao_contrato, patrimonio, modo_base, data_base,
    fator1, fator2, fator3, ultima_compra_desde, exibir_contrato_faturamento, exibir_contrato_pago,
):
    return await asyncio.to_thread(
        _inatividade_clientes_sync, servidor, banco, data_ini, data_fim, vendedor, regiao, segmento, rota,
        tipo_cliente, situacao_cadastro, situacao_contrato, patrimonio, modo_base, data_base,
        fator1, fator2, fator3, ultima_compra_desde, exibir_contrato_faturamento, exibir_contrato_pago,
    )

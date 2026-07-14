"""Cadastros > Notas Fiscais.

Migração de `FrmManRec.frm` ("Manutenção de Nota Fiscal") — a tela mais
complexa já migrada neste projeto até agora. Escopo desta primeira fase
(**Fase 1, decidido com o usuário em 2026-07-13**): CRUD completo do
documento fiscal (cabeçalho, itens, vencimentos, observações, resumo
tributário, centro de custo, consulta com filtros, crítica, cancelamento,
exclusão) **sem emissão fiscal real** — DANFE, XML, Carta de Correção,
Cancelamento/Inutilização online no SEFAZ, Consulta de Situação SEFAZ e
Contingência dependem da DLL .NET `Backon_Controllers.Nfe`/`NFSe`, que não
tem equivalente Python neste projeto. Ver "Notas Fiscais" em
`PENDENCIAS.md` (raiz do repo) para a lista completa do que fica de fora
desta fase.

Todos os nomes de coluna abaixo foram confirmados via
`INFORMATION_SCHEMA.COLUMNS` ao vivo em GERDELL/BARESTELA (2026-07-13) —
`n_fiscal` tem 101 colunas e `n_fiscal_itens` 162 (incluindo campos da
Reforma Tributária 2026 — IBS/CBS/IS — que o `.frm` original nem conhece).
Esta Fase 1 só expõe os campos que o próprio `.frm` legado realmente
mostra como controles editáveis (`Campo()` indexado) — o restante das
colunas (Reforma Tributária, DIFAL, PIS/COFINS-ST, transporte/frete
detalhado, engine de emissão) fica de fora, registrado como pendência.

A tela "Consulta de Notas Fiscais" do 2º print do usuário é `FrmConNF.frm`
— um form **diferente** de `FrmManRec.frm`. Localizado e lido em
`C:/Desenv/VB6/Diario Access-SQL/SQLSERVER/.../Geral/FrmConNF.frm`
(2026-07-13, `Sub Command2_Click`/`VCRITERIO`) — `_list_consulta_sync`
abaixo reflete os filtros REAIS desse form, não mais uma inferência do
print. Correção feita nesta rodada: dois filtros da primeira versão
("UF" e faixa de "Vencimento") não existem no `.frm` real e foram
removidos; "Código da NF" (`nf.codigo`) existe no real e foi adicionado;
a restrição `tipo_mov.origem_destino` foi adicionada porque o legado só
aplica o filtro de Cliente/Fornecedor junto com ela (evita colisão de
`nf.fornecedor`, que é um ID ambíguo — cliente.codigo OU
fornecedor.codigo_int, dependendo do tipo de movimentação). Não
implementado (ver PENDENCIAS.md): modo "NF's não Impressas" (Check3 do
`.frm` — troca a query inteira pra consultar `nf_aux` em vez de
`n_fiscal`, caso de uso mais raro/específico não investigado a fundo) e
o resumo agrupado "Totais por Movimentação"/"Total Geral" que a grade do
legado mostra ao final da lista.

Regras replicadas do legado:
  • Tipo de Movimentação (`tipo_mov`) determina se a "parte contrária" da
    nota é Cliente ou Fornecedor (`origem_destino`), CFOP padrão (dentro/
    fora do estado, conforme a UF do cliente/fornecedor bater com a UF da
    empresa) e se exige vencimento(s) pro contas a pagar/receber
    (`transf_pagar`).
  • Duplicidade: não permite duas notas com mesmo (num_nf, serie_nf,
    fornecedor) — mesma checagem do legado em `Campo_LostFocus(Index=2)`.
  • Nota cancelada (`situacao='C'`) não pode ser alterada — o legado tem um
    fluxo de "reabertura" condicionado a integração com contas a pagar/
    receber (`pagar='T'`); como esse módulo de duplicatas AINDA NÃO EXISTE
    nesta arquitetura nova (ver `project_faturamento_parcelas` na memória),
    a reabertura fica de fora — bloqueio é sempre definitivo por ora.
  • Criticar: soma dos itens deve bater com o Valor Total da nota — se não
    bater, `situacao` vira 'E' (erro de crítica) em vez de 'A' (ativa).
  • Cancelar: bloqueado se já cancelada, ou se nota de consignação com
    itens já devolvidos/faturados (`consignacao.qtd_devolvida`/
    `qtd_faturada` > 0). Reverte estoque (`pecas`/`veiculos`, conforme
    Entrada soma ou Saída subtrai), remove vínculo com comanda
    (`comanda_nf`), remove movimentação de estoque (`movimentacao`).
    **NÃO reverte duplicatas de contas a pagar/receber** — esse módulo
    ainda não existe nesta arquitetura (mesma nota do bloqueio acima);
    registrado como pendência (risco de inconsistência financeira quando
    o módulo de duplicatas for implementado).
  • Excluir: só permitido com `situacao='C'` — apaga em cascata itens,
    vencimentos, resumo tributário (`n_fiscal_icms`) e centro de custo
    (`n_fiscal_custo`), depois o cabeçalho.
  • "Alterar Número/Série/Fornecedor da Nota" — o próprio legado tem esses
    3 botões **desabilitados "PELO PAF-ECF"** (MsgBox crítico seguido de
    código morto/inalcançável) — restrição fiscal real, não implementado
    aqui de propósito, não é uma lacuna de migração.

Fora de escopo desta fase (ver PENDENCIAS.md):
  • Emissão fiscal real (DANFE, XML, Carta de Correção, Cancelamento/
    Inutilização SEFAZ, Consulta de Situação SEFAZ, Contingência) — precisa
    de um provedor NFe/NFSe Python (ou algum bridge pra DLL .NET), a
    decidir.
  • Efeitos colaterais específicos de estoque por tipo de movimentação de
    consignação (`Sub consignacoes` no legado — E03/E05/S05/E06/S06/S07/
    S08/E07/E08, grava/atualiza `consignacao`/`consignacao_baixa`) — muito
    específico e arriscado de replicar sem dados reais de consignação pra
    testar; a tabela `consignacao` não é tocada por esta migração.
  • Vínculo com Cupom Fiscal (ECF/`comanda_cupom`) — ligado ao módulo Bar/
    PDV, fora do escopo desta tela.
  • Envio por email do XML/DANFE.
  • Motor automático de cálculo de ICMS/Substituição por CFOP+UF+cod_icms
    (tabela `taxas`, função `ProcuraProdbkp`/`ProcuraProd` do legado) — os
    campos fiscais dos itens são de entrada manual nesta fase (mesmo
    padrão que o próprio `.frm` já permite quando "Label10 = 'L'").
  • Campos de transporte detalhado (placa, motorista, volumes, peso) e os
    campos da Reforma Tributária 2026 (IBS/CBS/IS) — existem na tabela mas
    não são controles visíveis no `.frm` original.
"""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn

SITUACOES_VALIDAS = ("D", "A", "C", "E", "L")

# Campos do cabeçalho realmente expostos como controles editáveis no
# `.frm` (ver docstring do módulo) — usado tanto no INSERT/UPDATE quanto
# no SELECT de carregamento.
_CAB_CAMPOS = [
    "num_nf", "serie_nf", "fornecedor", "mov", "cfop", "uf",
    "data_nf", "data_mov", "data_saida",
    "valor_total", "base_icms", "valor_icms", "base_ipi", "valor_ipi",
    "base_iss", "valor_iss", "base_sub", "valor_sub",
    "frete", "seguro", "despesas", "desconto",
    "BASE_FCP", "VALOR_FCP", "BASE_FCP_RETIDO", "VALOR_FCP_RETIDO",
    "BASE_FCP_ST", "VALOR_FCP_ST",
    "livro", "pagar", "contabilidade", "num_lcto_contabil",
    "tipo_doc", "especie", "selo_fiscal", "passe_fiscal",
    "chave_acesso", "protocolo_sefaz", "obs", "obs_livro", "cupom_fiscal",
]

_ITEM_CAMPOS = [
    "codigo_int", "cod_fiscal", "cod_contabil", "tributacao",
    "qtd", "qtd_un_compra", "p_unit", "desconto", "valor_total",
    "alqt_icms", "reducao_base_icms", "base_icms", "valor_icms",
    "base_ipi", "alqt_ipi", "valor_ipi",
    "base_sub", "valor_sub", "base_iss", "valor_iss",
    "frete", "seguro", "despesas",
    "tributacao_pis", "base_pis", "alqt_pis", "valor_pis",
    "tributacao_cofins", "base_cofins", "alqt_cofins", "valor_cofins",
]


def _to_date(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


# ============ Cabeçalho ============
def _get_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cols = ", ".join(["codigo", "situacao", "situacao_nfe"] + _CAB_CAMPOS)
        cur.execute(f"SELECT {cols} FROM n_fiscal WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Nota Fiscal não encontrada."}

        cur.execute(
            f"SELECT id, codigo, {', '.join(_ITEM_CAMPOS)} FROM n_fiscal_itens "
            "WHERE codigo=%s ORDER BY id",
            (codigo,),
        )
        itens = list(cur.fetchall())

        cur.execute(
            "SELECT SEQUENCIA_NF_VENCIMENTO AS sequencia, data_venc, valor "
            "FROM nf_vencimento WHERE codigo=%s ORDER BY data_venc",
            (codigo,),
        )
        vencimentos = list(cur.fetchall())

        cur.execute(
            "SELECT cod_fiscal, cod_contabil, tributacao, alqt_icms, valor_contabil, "
            "valor_base, valor_icms, valor_base_retido, valor_icms_retido, "
            "valor_base_recolher, valor_icms_recolher, dif_icms_bens, "
            "reducao_base_icms, transf_contab, obs "
            "FROM n_fiscal_icms WHERE n_fiscal=%s",
            (codigo,),
        )
        resumo_tributario = list(cur.fetchall())

        cur.execute(
            "SELECT sequencial, custo, valor_contabil, valor_icms, valor_icms_retido, "
            "dif_icms_bens, nf_classe, nf_sub_classe "
            "FROM n_fiscal_custo WHERE n_fiscal=%s",
            (codigo,),
        )
        centro_custo = list(cur.fetchall())

        cur.close()
        return {
            "success": True, "cabecalho": row, "itens": itens,
            "vencimentos": vencimentos, "resumo_tributario": resumo_tributario,
            "centro_custo": centro_custo,
        }
    finally:
        conn.close()


def _save_cabecalho_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    fornecedor = dados.get("fornecedor")
    mov = (dados.get("mov") or "").strip()
    num_nf = dados.get("num_nf")
    serie_nf = (dados.get("serie_nf") or "").strip()
    if not fornecedor:
        return {"success": False, "message": "Selecione o Cliente/Fornecedor."}
    if not mov:
        return {"success": False, "message": "Selecione o Tipo de Movimentação."}
    if not num_nf:
        return {"success": False, "message": "Informe o Número da NF."}
    if not serie_nf:
        return {"success": False, "message": "Informe a Série."}
    if not dados.get("data_nf"):
        return {"success": False, "message": "Informe a Data de Emissão."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT codigo, origem_destino, transf_pagar FROM tipo_mov WHERE codigo=%s", (mov,))
        tm = cur.fetchone()
        if not tm:
            cur.close()
            return {"success": False, "message": "Tipo de Movimentação não cadastrado."}

        cur.execute(
            "SELECT codigo, situacao FROM n_fiscal WHERE num_nf=%s AND serie_nf=%s AND fornecedor=%s",
            (num_nf, serie_nf, fornecedor),
        )
        existente = cur.fetchone()
        if existente and existente["codigo"] != (codigo or 0):
            cur.close()
            return {
                "success": False,
                "message": f"Já existe uma Nota Fiscal com Número {num_nf}, Série {serie_nf} "
                           "para este Cliente/Fornecedor.",
            }

        if codigo:
            cur.execute("SELECT situacao FROM n_fiscal WHERE codigo=%s", (codigo,))
            atual = cur.fetchone()
            if not atual:
                cur.close()
                return {"success": False, "message": "Nota Fiscal não encontrada."}
            if atual["situacao"] == "C":
                cur.close()
                return {"success": False, "message": "Não é permitido alterar notas canceladas."}

            sets = ", ".join(f"{c}=%s" for c in _CAB_CAMPOS)
            valores = [dados.get(c) for c in _CAB_CAMPOS]
            cur.execute(f"UPDATE n_fiscal SET {sets} WHERE codigo=%s", (*valores, codigo))
            conn.commit()
            cur.close()
            return {"success": True, "codigo": codigo, "message": "Nota Fiscal atualizada."}
        else:
            cols = ", ".join(_CAB_CAMPOS)
            marcas = ", ".join(["%s"] * len(_CAB_CAMPOS))
            valores = [dados.get(c) for c in _CAB_CAMPOS]
            cur.execute(
                f"INSERT INTO n_fiscal ({cols}, situacao) OUTPUT INSERTED.codigo "
                f"VALUES ({marcas}, 'D')",
                valores,
            )
            novo_codigo = cur.fetchone()["codigo"]
            conn.commit()
            cur.close()
            return {"success": True, "codigo": novo_codigo, "message": "Nota Fiscal criada."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


# ============ Itens (replace-all) ============
def _save_itens_sync(servidor: str, banco: str, codigo: int, itens: list) -> dict:
    if not codigo:
        return {"success": False, "message": "Grave o cabeçalho da Nota Fiscal antes de lançar itens."}
    for it in itens:
        if not (it.get("codigo_int") or "").strip():
            return {"success": False, "message": "Todo item precisa de um Código de Produto/Serviço."}
        if not it.get("qtd"):
            return {"success": False, "message": "Todo item precisa de Quantidade maior que zero."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM n_fiscal WHERE codigo=%s", (codigo,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Nota Fiscal não encontrada."}

        cur.execute("DELETE FROM n_fiscal_itens WHERE codigo=%s", (codigo,))
        cols = ", ".join(_ITEM_CAMPOS)
        marcas = ", ".join(["%s"] * len(_ITEM_CAMPOS))
        for it in itens:
            valores = [it.get(c) for c in _ITEM_CAMPOS]
            cur.execute(f"INSERT INTO n_fiscal_itens (codigo, {cols}) VALUES (%s, {marcas})", (codigo, *valores))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Itens gravados."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar itens: {e}"}
    finally:
        conn.close()


# ============ Vencimentos (replace-all) ============
def _save_vencimentos_sync(servidor: str, banco: str, codigo: int, vencimentos: list) -> dict:
    if not codigo:
        return {"success": False, "message": "Grave o cabeçalho da Nota Fiscal antes de lançar vencimentos."}
    for v in vencimentos:
        if not v.get("data_venc") or not v.get("valor"):
            return {"success": False, "message": "Todo vencimento precisa de Data e Valor."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM nf_vencimento WHERE codigo=%s", (codigo,))
        for v in vencimentos:
            cur.execute(
                "INSERT INTO nf_vencimento (codigo, data_venc, valor) VALUES (%s, %s, %s)",
                (codigo, v["data_venc"], v["valor"]),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Vencimentos gravados."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar vencimentos: {e}"}
    finally:
        conn.close()


# ============ Resumo Tributário (replace-all) ============
def _save_resumo_tributario_sync(servidor: str, banco: str, codigo: int, linhas: list) -> dict:
    if not codigo:
        return {"success": False, "message": "Grave o cabeçalho da Nota Fiscal antes de lançar o resumo tributário."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM n_fiscal_icms WHERE n_fiscal=%s", (codigo,))
        for r in linhas:
            cur.execute(
                "INSERT INTO n_fiscal_icms (n_fiscal, cod_fiscal, cod_contabil, tributacao, alqt_icms, "
                "valor_contabil, valor_base, valor_icms, valor_base_retido, valor_icms_retido, "
                "valor_base_recolher, valor_icms_recolher, dif_icms_bens, reducao_base_icms, "
                "transf_contab, obs) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo, r.get("cod_fiscal") or "", r.get("cod_contabil") or 0,
                    r.get("tributacao") or 0, r.get("alqt_icms") or 0,
                    r.get("valor_contabil"), r.get("valor_base"), r.get("valor_icms"),
                    r.get("valor_base_retido"), r.get("valor_icms_retido"),
                    r.get("valor_base_recolher"), r.get("valor_icms_recolher"),
                    r.get("dif_icms_bens"), r.get("reducao_base_icms"),
                    r.get("transf_contab") or False, r.get("obs"),
                ),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Resumo tributário gravado."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar resumo tributário: {e}"}
    finally:
        conn.close()


# ============ Centro de Custo (replace-all) ============
def _save_centro_custo_sync(servidor: str, banco: str, codigo: int, linhas: list) -> dict:
    if not codigo:
        return {"success": False, "message": "Grave o cabeçalho da Nota Fiscal antes de lançar o centro de custo."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM n_fiscal_custo WHERE n_fiscal=%s", (codigo,))
        for r in linhas:
            cur.execute(
                "INSERT INTO n_fiscal_custo (n_fiscal, custo, valor_contabil, valor_icms, "
                "valor_icms_retido, dif_icms_bens, nf_classe, nf_sub_classe) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo, r.get("custo"), r.get("valor_contabil"), r.get("valor_icms"),
                    r.get("valor_icms_retido"), r.get("dif_icms_bens"),
                    r.get("nf_classe"), r.get("nf_sub_classe"),
                ),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Centro de custo gravado."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar centro de custo: {e}"}
    finally:
        conn.close()


# ============ Consulta ============
# Filtros confirmados contra o código-fonte real de FrmConNF.frm
# (C:\Desenv\VB6\Diario Access-SQL\SQLSERVER\...\Geral\FrmConNF.frm,
# Sub Command2_Click / VCRITERIO — lido em 2026-07-13, ver "Notas Fiscais"
# em PENDENCIAS.md). Corrigido depois de uma primeira versão que tinha
# inferido os filtros só pelo print de tela: removidos dois filtros que eu
# tinha inventado e NÃO existem no `.frm` real ("UF" e faixa de
# "Vencimento"), adicionado "Código da NF" (Campo(8), `nf.codigo`) que
# existe no real e eu tinha deixado de fora, e adicionada a restrição
# `tipo_mov.origem_destino` — o legado só aplica o filtro de Cliente/
# Fornecedor junto com essa restrição (evita colisão: `nf.fornecedor`
# guarda ora um `cliente.codigo`, ora um `fornecedor.codigo_int`,
# dependendo do tipo de movimentação).
def _list_consulta_sync(servidor: str, banco: str, f: dict) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ["1=1"]
        params = []

        if f.get("codigo"):
            where.append("nf.codigo=%s")
            params.append(f["codigo"])
        if f.get("num_nf"):
            where.append("nf.num_nf=%s")
            params.append(f["num_nf"])
        if (f.get("serie_nf") or "").strip():
            where.append("nf.serie_nf=%s")
            params.append(f["serie_nf"].strip())
        if f.get("valor_total"):
            where.append("nf.valor_total=%s")
            params.append(f["valor_total"])
        if (f.get("cfop") or "").strip():
            where.append("nf.cfop=%s")
            params.append(f["cfop"].strip())
        if (f.get("mov") or "").strip():
            where.append("nf.mov=%s")
            params.append(f["mov"].strip())
        if f.get("entrada") and not f.get("saida"):
            where.append("LEFT(nf.mov,1)='E'")
        elif f.get("saida") and not f.get("entrada"):
            where.append("LEFT(nf.mov,1)='S'")

        situ = f.get("situacao")
        if situ == "A":
            where.append("nf.situacao='A'")
        elif situ == "C":
            where.append("nf.situacao='C'")

        termo = (f.get("cliente_fornecedor_termo") or "").strip()
        if termo:
            tabela_termo = "cliente" if f.get("tipo_pessoa") == "C" else "fornecedor"
            col_nome = "nome"
            col_codigo = "codigo" if tabela_termo == "cliente" else "codigo_int"
            # Mesma restrição do legado: só considera a nota se o tipo de
            # movimentação bater com Cliente/Fornecedor escolhido no rádio
            # (`nf.fornecedor` é um ID ambíguo — ora cliente.codigo, ora
            # fornecedor.codigo_int — sem isso duas notas de origens
            # diferentes com o mesmo número de ID colidiriam).
            where.append("tm.origem_destino=%s")
            params.append(f.get("tipo_pessoa") or "C")
            if termo.isdigit():
                where.append("nf.fornecedor=%s")
                params.append(int(termo))
            else:
                where.append(
                    f"nf.fornecedor IN (SELECT {col_codigo} FROM {tabela_termo} WHERE {col_nome} LIKE %s)"
                )
                params.append(f"%{termo}%")

        for de_key, ate_key, col in [
            ("data_nf_de", "data_nf_ate", "nf.data_nf"),
            ("data_mov_de", "data_mov_ate", "nf.data_mov"),
        ]:
            if f.get(de_key):
                where.append(f"{col} >= %s")
                params.append(_to_date(f[de_key]))
            if f.get(ate_key):
                where.append(f"{col} <= %s")
                params.append(_to_date(f[ate_key]))

        query = (
            "SELECT nf.codigo, nf.num_nf, nf.serie_nf, nf.fornecedor, nf.mov, nf.cfop, "
            "nf.uf, nf.data_nf, nf.data_mov, nf.valor_total, nf.situacao, nf.chave_acesso, nf.obs, "
            "tm.descricao AS mov_descricao, tm.origem_destino "
            "FROM n_fiscal nf LEFT JOIN tipo_mov tm ON tm.codigo = nf.mov "
            f"WHERE {' AND '.join(where)} ORDER BY nf.data_nf DESC, nf.codigo DESC"
        )
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        codigos_pessoa = {r["fornecedor"] for r in rows if r.get("fornecedor")}
        nomes = {}
        if codigos_pessoa:
            marcas = ", ".join(["%s"] * len(codigos_pessoa))
            cur.execute(f"SELECT codigo, nome FROM cliente WHERE codigo IN ({marcas})", tuple(codigos_pessoa))
            for r in cur.fetchall():
                nomes[("C", r["codigo"])] = r["nome"]
            cur.execute(f"SELECT codigo_int AS codigo, nome FROM fornecedor WHERE codigo_int IN ({marcas})", tuple(codigos_pessoa))
            for r in cur.fetchall():
                nomes[("F", r["codigo"])] = r["nome"]

        items = []
        for r in rows:
            fornecedor_id = r.get("fornecedor")
            # origem_destino=='F' -> fornecedor; qualquer outra coisa (inclui
            # nulo/legado sem tipo_mov) segue o padrão do legado (default 'C').
            tipo = "F" if (r.get("origem_destino") or "") == "F" else "C"
            nome = nomes.get((tipo, fornecedor_id)) or ""
            items.append({**r, "cliente_fornecedor_nome": (nome or "").strip()})

        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


# ============ Criticar ============
def _criticar_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT valor_total FROM n_fiscal WHERE codigo=%s", (codigo,))
        nf = cur.fetchone()
        if not nf:
            cur.close()
            return {"success": False, "message": "Nota Fiscal não encontrada."}

        cur.execute("SELECT SUM(valor_total) AS soma FROM n_fiscal_itens WHERE codigo=%s", (codigo,))
        soma_itens = cur.fetchone()["soma"] or 0.0
        valor_total = nf["valor_total"] or 0.0

        divergencias = []
        if round(soma_itens, 2) != round(valor_total, 2):
            divergencias.append({
                "descricao": "O Valor Total não confere com a Soma dos Itens",
                "valor_nota": valor_total, "valor_itens": soma_itens,
            })

        nova_situacao = "E" if divergencias else "A"
        cur.execute("UPDATE n_fiscal SET situacao=%s WHERE codigo=%s", (nova_situacao, codigo))
        conn.commit()
        cur.close()
        return {"success": True, "situacao": nova_situacao, "divergencias": divergencias}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao criticar: {e}"}
    finally:
        conn.close()


# ============ Cancelar ============
def _cancelar_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao, mov FROM n_fiscal WHERE codigo=%s", (codigo,))
        nf = cur.fetchone()
        if not nf:
            cur.close()
            return {"success": False, "message": "Nota Fiscal não encontrada."}
        if nf["situacao"] == "C":
            cur.close()
            return {"success": False, "message": "Esta Nota Fiscal já foi cancelada anteriormente."}

        cur.execute("SELECT qtd_devolvida, qtd_faturada FROM consignacao WHERE nota_fiscal=%s", (codigo,))
        consig = cur.fetchall()
        if any((c.get("qtd_devolvida") or 0) > 0 or (c.get("qtd_faturada") or 0) > 0 for c in consig):
            cur.close()
            return {
                "success": False,
                "message": "Esta Nota Fiscal de consignação já possui itens devolvidos e/ou "
                           "faturados! Cancelamento não permitido.",
            }

        cur.execute(
            "SELECT codigo_int, qtd, tipo FROM movimentacao WHERE num_nf=%s "
            "AND LTRIM(RTRIM(ISNULL(serie_nf,''))) = ''",
            (codigo,),
        )
        movs = cur.fetchall()
        for m in movs:
            codigo_int = (m.get("codigo_int") or "").strip()
            sinal = 1 if (m.get("tipo") or "").upper().startswith("S") else -1
            if codigo_int[:1] in ("P", "A"):
                cur.execute("UPDATE pecas SET qtd = qtd + %s WHERE codigo_int=%s", (sinal * (m["qtd"] or 0), codigo_int))
            elif codigo_int[:1] == "V":
                cur.execute("UPDATE veiculos SET nf_venda=0, nf_compra=0 WHERE codigo_int=%s", (codigo_int,))
        cur.execute(
            "DELETE FROM movimentacao WHERE num_nf=%s AND LTRIM(RTRIM(ISNULL(serie_nf,''))) = ''",
            (codigo,),
        )
        cur.execute("DELETE FROM comanda_nf WHERE nota_fisc=%s", (codigo,))
        cur.execute("UPDATE n_fiscal SET situacao='C' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {
            "success": True,
            "message": "Nota Fiscal cancelada. Se esta nota possui chave de acesso/protocolo SEFAZ, "
                       "o cancelamento oficial junto à Receita ainda precisa ser feito por fora deste "
                       "sistema (emissão fiscal real não faz parte desta fase).",
        }
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao cancelar: {e}"}
    finally:
        conn.close()


# ============ Excluir ============
def _excluir_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM n_fiscal WHERE codigo=%s", (codigo,))
        nf = cur.fetchone()
        if not nf:
            cur.close()
            return {"success": False, "message": "Nota Fiscal não encontrada."}
        if nf["situacao"] != "C":
            cur.close()
            return {"success": False, "message": "Efetue, primeiramente, o cancelamento da Nota Fiscal."}

        cur.execute("DELETE FROM n_fiscal_itens WHERE codigo=%s", (codigo,))
        cur.execute("DELETE FROM nf_vencimento WHERE codigo=%s", (codigo,))
        cur.execute("DELETE FROM n_fiscal_icms WHERE n_fiscal=%s", (codigo,))
        cur.execute("DELETE FROM n_fiscal_custo WHERE n_fiscal=%s", (codigo,))
        cur.execute("DELETE FROM n_fiscal WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Nota Fiscal excluída."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ============ Buscar produto (descrição, só leitura) ============
def _buscar_produto_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        for tabela, col_desc, col_fiscal in [
            ("pecas", "descricao", "cod_fiscal"),
            ("veiculos", "descricao", "cod_fiscal"),
            ("servicos", "descricao", None),
        ]:
            cols = f"{col_desc} AS descricao" + (f", {col_fiscal} AS cod_fiscal" if col_fiscal else ", NULL AS cod_fiscal")
            pk = "codigo" if tabela == "servicos" else "codigo_int"
            try:
                cur.execute(f"SELECT {cols} FROM {tabela} WHERE {pk}=%s", (codigo_int,))
                row = cur.fetchone()
            except Exception:
                row = None
            if row:
                cur.close()
                return {"success": True, "found": True, "descricao": (row.get("descricao") or "").strip(),
                        "cod_fiscal": (row.get("cod_fiscal") or "").strip() if row.get("cod_fiscal") else ""}
        cur.close()
        return {"success": True, "found": False}
    finally:
        conn.close()


# ============ Wrappers async ============
async def get(servidor, banco, codigo):
    return await asyncio.to_thread(_get_sync, servidor, banco, codigo)


async def save_cabecalho(servidor, banco, codigo, dados):
    return await asyncio.to_thread(_save_cabecalho_sync, servidor, banco, codigo, dados)


async def save_itens(servidor, banco, codigo, itens):
    return await asyncio.to_thread(_save_itens_sync, servidor, banco, codigo, itens)


async def save_vencimentos(servidor, banco, codigo, vencimentos):
    return await asyncio.to_thread(_save_vencimentos_sync, servidor, banco, codigo, vencimentos)


async def save_resumo_tributario(servidor, banco, codigo, linhas):
    return await asyncio.to_thread(_save_resumo_tributario_sync, servidor, banco, codigo, linhas)


async def save_centro_custo(servidor, banco, codigo, linhas):
    return await asyncio.to_thread(_save_centro_custo_sync, servidor, banco, codigo, linhas)


async def list_consulta(servidor, banco, filtros):
    return await asyncio.to_thread(_list_consulta_sync, servidor, banco, filtros)


async def criticar(servidor, banco, codigo):
    return await asyncio.to_thread(_criticar_sync, servidor, banco, codigo)


async def cancelar(servidor, banco, codigo):
    return await asyncio.to_thread(_cancelar_sync, servidor, banco, codigo)


async def excluir(servidor, banco, codigo):
    return await asyncio.to_thread(_excluir_sync, servidor, banco, codigo)


async def buscar_produto(servidor, banco, codigo_int):
    return await asyncio.to_thread(_buscar_produto_sync, servidor, banco, codigo_int)

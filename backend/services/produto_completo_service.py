"""Cadastro de Produtos (completo) — tabela `pecas` (~150 colunas), web-only.

Legado: `C:\\Desenv\\VB6\\SQLSERVER\\Kontacto\\FrmManPec.frm` (12.838 linhas) —
única cópia do form que bate com as 7 abas migradas aqui (Dados Principais,
Descontos e Comissões, Configurações Fiscais, Dados Secundários, Grade do
Produto, Similares e Equivalentes, Livro). Verificação feita 2026-07-14,
campo a campo, contra o código-fonte real (não contra rótulos de tela) —
ver PENDENCIAS.md > "Produtos (Cadastro Completo)" pro relatório completo.

Diferença desta tela para as já existentes:
- `produtos_service.py` (`/api/produtos`) é o BUSCADOR/seletor usado tanto
  pelo picker de item em Pedido/O.S. quanto pela navegação rápida em
  Cadastros no mobile — continua existindo e não muda.
- `produtos_niveis_service.py` é edição EM MASSA de preço/margem/fiscal por
  nível/faixa de NCM — também não muda.
- Este módulo é o cadastro de UM produto por vez, completo, só web —
  mesmo padrão de "Cliente Completo"/Fornecedores/Serviços.

Módulos que gateiam abas (company-wide, não por produto — confirmado no
Form_Load do legado: `Dados_Controle_Configuracao.Grade`/`.livraria`, que
já existem como colunas bit em `controle_configuracao` desta migração:
`grade` e `Livraria`):
- Aba "Grade do Produto": só habilitada se `controle_configuracao.grade`.
- Aba "Livro": só habilitada se `controle_configuracao.Livraria`.
Ambos os checks batem no banco a cada chamada (nunca cacheados) — mesmo
princípio de "Porting VB6 global state" do CLAUDE.md.

Campos da aba "Livro" que são as MESMAS colunas de outras abas (não
duplicadas aqui): `fornecedor` (rótulo "Editora"), `tipo_peca` (rótulo
"Tipo"), `desconto_compra` e `desc_v` (rótulo "Desconto Venda") — o
legado reaproveita essas colunas via controles diferentes na aba Livro;
o front end só precisa reexibir os mesmos campos lá, sem enviar valor
duplicado.

Campos do legado propositalmente NÃO replicados (código morto/gambiarra
de linguagem, ver "Não replicar truques VB6" no CLAUDE.md):
- `Option3`/`Option5` (lançamento/esgotado) tinham controles ausentes
  nesta cópia do form mas a coluna existe (`lancamento`, `esgotado`) —
  optamos por expor de verdade como checkbox nesta migração (melhoria,
  não uma regra nova inventada — a coluna já existia pra isso).
- Múltiplos códigos de barra por produto (`codbarra_auxiliar`) — o
  screenshot do usuário mostra só um campo de código de barras; a tabela
  auxiliar existe no legado mas não foi pedida aqui. Fora de escopo por
  ora.
- Botão "Anexos" abria o Gestor de Documentos com `Grupo=3` no legado
  (Funcionários, pelo mapeamento já validado ao vivo neste app) — isso é
  claramente um bug/cópia-colada do form original. Aqui usa-se Grupo=4
  (Produtos), mesmo padrão já usado em Fornecedores/Serviços.
"""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn

# ---------------------------------------------------------------------------
# Módulos (gates de aba)
# ---------------------------------------------------------------------------

def _modulo_ativo_sync(cur, coluna: str) -> bool:
    cur.execute(f"SELECT TOP 1 {coluna} AS v FROM controle_configuracao")
    row = cur.fetchone()
    return bool(row and row.get("v"))


def _modulo_grade_ativo(cur) -> bool:
    return _modulo_ativo_sync(cur, "grade")


def _modulo_livraria_ativo(cur) -> bool:
    return _modulo_ativo_sync(cur, "Livraria")


# ---------------------------------------------------------------------------
# Geração de código interno (controle.cod_peca, int sequencial — legado
# gera codigo_int = 'P' + próximo número, sem zero-padding; confirmado ao
# vivo: valores existentes como 'P9', 'P91' convivem sem padding).
# ---------------------------------------------------------------------------

def _gerar_codigo_int_sync(cur) -> str:
    cur.execute("UPDATE controle SET cod_peca = cod_peca + 1")
    cur.execute("SELECT cod_peca FROM controle")
    n = cur.fetchone()["cod_peca"]
    return f"P{n}"


# ---------------------------------------------------------------------------
# Campos escalares de `pecas` — únicos por aba (Livro reaproveita
# fornecedor/tipo_peca/desconto_compra/desc_v de outras abas, ver docstring).
# ---------------------------------------------------------------------------

CAMPOS_PRINCIPAIS = [
    "codigo_fab", "codigo_bar", "codigo_mercosul", "descricao", "descricao_pdv",
    "descricao_embarque", "descricao_nf", "Descricao_Completa",
    "p_custo", "p_venda", "p_sugestao", "p_garantia", "p_sugerido", "preco_base",
    "preco_promocional", "preco_lista", "preco_variado", "cod_anp",
    "marca_produto", "modelo_produto", "fornecedor",
    "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "Produto_web", "FRETE_GRATIS_SITE", "situacao",
]

CAMPOS_DESCONTOS_COMISSOES = [
    "desc_g", "desc_s", "desc_v", "comissao", "comissao_a", "comissao_e",
    "valor_comissao", "Valor_Comissão_E", "Valor_Comissão_A",
    "valor_desc_base_comissao", "valor_desc_base_comissao_e", "valor_desc_base_comissao_a",
    "paga_comissao", "aceita_desconto", "politica_preco",
]

CAMPOS_FISCAIS = [
    "codigo_cest", "BENEFICIO_FISCAL", "origem", "perc_ipi", "valor_ipi",
    "cst_ipi_entrada", "cst_ipi_saida", "ENQUADRAMENTO_IPI", "cod_icms",
    "cod_grupo_pis_cofins", "tributacao_pis", "perc_valor_pis",
    "tributacao_cofins", "perc_valor_cofins", "outros_trib_federais",
    "IBPT_FEDERAIS", "IBPT_ESTADUAIS", "valor_substituicao", "perc_mva",
]

CAMPOS_SECUNDARIOS = [
    "unidade_medida", "comprimento", "largura", "altura", "peso_liquido", "peso_bruto",
    "un_compra", "qtd_un_compra", "un_embarque", "qtd_un_embarque", "QTD_UN_VENDA",
    "un_fracao", "prazo_entrega", "prazo_fornecedor", "prazo_garantia", "tipo_garantia",
    "estoque_minimo", "estoque_maximo", "estoque_ressuprimento",
    "area", "prateleira", "escaninho", "tipo", "tipo_peca", "indice_preco",
    "custo_inventario", "custo_reposicao", "desconto_compra", "percent_frete",
    "valor_frete", "margem_lucro", "margem_tabela",
    "pontuacao_a", "pontuacao_e", "pontuacao_v", "controla_num_serie", "peso_variado",
]

# Só gravados se controle_configuracao.Livraria estiver ligado (fiéis ao
# legado — no legado o UPDATE inteiro dessas colunas só roda com esse
# módulo ligado, ver docstring do módulo).
CAMPOS_LIVRO = ["autor", "serie", "sinopse", "lancamento", "esgotado"]

CAMPOS_TODOS = CAMPOS_PRINCIPAIS + CAMPOS_DESCONTOS_COMISSOES + CAMPOS_FISCAIS + CAMPOS_SECUNDARIOS

_COLS_READONLY = {"qtd", "reservado", "reservado_os", "custo_medio", "usuario_cadastro", "data_cadastro"}


def _row_to_dict(r: dict) -> dict:
    out = dict(r)
    for k, v in list(out.items()):
        if isinstance(v, (date,)):
            out[k] = v.isoformat()
    return out


# ---------------------------------------------------------------------------
# Listagem / consulta
# ---------------------------------------------------------------------------

def _list_produtos_sync(servidor: str, banco: str, search: str, page: int, size: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = "1=1"
        params: list = []
        term = (search or "").strip()
        if term:
            where += " AND (descricao LIKE %s OR codigo_int LIKE %s OR codigo_fab LIKE %s)"
            like = f"%{term}%"
            params += [like, like, like]
        cur.execute(f"SELECT COUNT(*) AS n FROM pecas WHERE {where}", tuple(params))
        total = cur.fetchone()["n"]
        offset = max(0, (page - 1) * size)
        cur.execute(
            f"SELECT codigo_int, codigo_fab, descricao, p_venda, situacao, qtd FROM pecas "
            f"WHERE {where} ORDER BY descricao "
            f"OFFSET {offset} ROWS FETCH NEXT {size} ROWS ONLY",
            tuple(params),
        )
        items = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items, "total": total}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}
    finally:
        conn.close()


def _get_produto_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM pecas WHERE codigo_int=%s", (codigo_int,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Produto não encontrado."}
        produto = _row_to_dict(row)

        cur.execute(
            "SELECT pf.fornecedor, pf.sequencia, f.nome FROM pecas_fornecedor pf "
            "LEFT JOIN fornecedor f ON f.codigo_int = pf.fornecedor WHERE pf.peca=%s ORDER BY pf.sequencia",
            (codigo_int,),
        )
        fornecedores = [_row_to_dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT s.equivalente, p.descricao FROM pecaseq s "
            "LEFT JOIN pecas p ON p.codigo_int = s.equivalente WHERE s.codigo=%s",
            (codigo_int,),
        )
        similares = [_row_to_dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT s.peca_secundaria, p.descricao FROM pecas_secundaria s "
            "LEFT JOIN pecas p ON p.codigo_int = s.peca_secundaria WHERE s.peca_principal=%s",
            (codigo_int,),
        )
        secundarios = [_row_to_dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT codigo_xml, fornecedor_xml, f.nome FROM pecas_xml x "
            "LEFT JOIN fornecedor f ON f.codigo_int = x.fornecedor_xml WHERE x.codigo_int=%s",
            (codigo_int,),
        )
        xml_vinculos = [_row_to_dict(r) for r in cur.fetchall()]

        cur.execute("SELECT UF FROM pecas_protocolo_st WHERE codigo_int=%s ORDER BY UF", (codigo_int,))
        protocolo_st = [r["UF"] for r in cur.fetchall()]

        cur.execute(
            "SELECT g.equivalente, g.cor, g.tamanho, p.descricao, p.p_venda, p.qtd "
            "FROM pecas_grade g LEFT JOIN pecas p ON p.codigo_int = g.equivalente "
            "WHERE g.codigo=%s ORDER BY g.cor, g.tamanho",
            (codigo_int,),
        )
        grade = [_row_to_dict(r) for r in cur.fetchall()]

        cur.close()
        return {
            "success": True, "produto": produto, "fornecedores": fornecedores,
            "similares": similares, "secundarios": secundarios,
            "xml_vinculos": xml_vinculos, "protocolo_st": protocolo_st, "grade": grade,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------

def _save_produto_sync(servidor: str, banco: str, codigo_int: Optional[str], dados: dict) -> dict:
    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return {"success": False, "message": "Informe a Descrição."}
    if not (dados.get("situacao") or "").strip():
        return {"success": False, "message": "Informe a Situação."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        campos = {c: dados.get(c) for c in CAMPOS_TODOS if c in dados}
        campos["descricao"] = descricao
        campos["situacao"] = dados["situacao"].strip().upper()[:2]
        for bool_col in ("preco_variado", "Produto_web", "FRETE_GRATIS_SITE", "paga_comissao",
                          "aceita_desconto", "controla_num_serie", "peso_variado"):
            if bool_col in campos:
                campos[bool_col] = bool(campos[bool_col])

        if _modulo_livraria_ativo(cur):
            for c in CAMPOS_LIVRO:
                if c in dados:
                    campos[c] = bool(dados[c]) if c in ("lancamento", "esgotado") else dados[c]

        novo = False
        if codigo_int:
            set_clause = ", ".join(f"[{c}]=%s" for c in campos)
            cur.execute(f"UPDATE pecas SET {set_clause} WHERE codigo_int=%s", (*campos.values(), codigo_int))
        else:
            novo = True
            codigo_int = _gerar_codigo_int_sync(cur)
            campos["codigo_int"] = codigo_int
            campos.setdefault("data_cadastro", date.today().isoformat())
            cols = list(campos.keys())
            placeholders = ",".join(["%s"] * len(cols))
            cur.execute(
                f"INSERT INTO pecas ([{'],['.join(cols)}]) VALUES ({placeholders})",
                tuple(campos.values()),
            )

        # Fornecedores — replace-all
        cur.execute("DELETE FROM pecas_fornecedor WHERE peca=%s", (codigo_int,))
        for i, f in enumerate(dados.get("fornecedores") or [], start=1):
            forn = f.get("fornecedor")
            if not forn:
                continue
            cur.execute(
                "INSERT INTO pecas_fornecedor (peca, fornecedor, sequencia) VALUES (%s,%s,%s)",
                (codigo_int, int(forn), int(f.get("sequencia") or i)),
            )

        # Similares — replace-all
        cur.execute("DELETE FROM pecaseq WHERE codigo=%s", (codigo_int,))
        for s in dados.get("similares") or []:
            equiv = (s.get("equivalente") or "").strip()
            if equiv:
                cur.execute("INSERT INTO pecaseq (codigo, equivalente) VALUES (%s,%s)", (codigo_int, equiv))

        # Secundários — replace-all
        cur.execute("DELETE FROM pecas_secundaria WHERE peca_principal=%s", (codigo_int,))
        for s in dados.get("secundarios") or []:
            sec = (s.get("peca_secundaria") or "").strip()
            if sec:
                cur.execute(
                    "INSERT INTO pecas_secundaria (peca_principal, peca_secundaria) VALUES (%s,%s)",
                    (codigo_int, sec),
                )

        # Vínculos XML — replace-all
        cur.execute("DELETE FROM pecas_xml WHERE codigo_int=%s", (codigo_int,))
        for x in dados.get("xml_vinculos") or []:
            cod_xml = (x.get("codigo_xml") or "").strip()
            if not cod_xml:
                continue
            cur.execute(
                "INSERT INTO pecas_xml (codigo_int, codigo_fab, codigo_xml, fornecedor_xml) VALUES (%s,%s,%s,%s)",
                (codigo_int, campos.get("codigo_fab") or "", cod_xml, x.get("fornecedor_xml") or None),
            )

        # Protocolo ST por UF — replace-all
        cur.execute("DELETE FROM pecas_protocolo_st WHERE codigo_int=%s", (codigo_int,))
        for uf in dados.get("protocolo_st") or []:
            uf = (uf or "").strip().upper()[:2]
            if uf:
                cur.execute("INSERT INTO pecas_protocolo_st (codigo_int, UF) VALUES (%s,%s)", (codigo_int, uf))

        conn.commit()
        cur.close()
        return {"success": True, "message": "Produto gravado.", "codigo_int": codigo_int, "novo": novo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Exclusão — checa dependências reais antes de excluir (regra de negócio
# genuína do legado, ver CmDexclui_Click no relatório de rastreio).
# ---------------------------------------------------------------------------

_DEP_CHECKS = [
    ("movimentação", "SELECT TOP 1 1 FROM movimentacao WHERE codigo_int=%s"),
    ("orçamentos", "SELECT TOP 1 1 FROM orc_produto WHERE prod=%s"),
    ("pedidos", "SELECT TOP 1 1 FROM pedido_venda_prod WHERE produto=%s"),
    ("ordens de serviço", "SELECT TOP 1 1 FROM os_produto WHERE codigo_interno=%s"),
    ("notas fiscais de entrada", "SELECT TOP 1 1 FROM nf_recebimento_itens WHERE codigo_int=%s"),
]


def _delete_produto_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT qtd, reservado, reservado_os FROM pecas WHERE codigo_int=%s", (codigo_int,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Produto não encontrado."}
        if float(row.get("qtd") or 0) != 0 or float(row.get("reservado") or 0) != 0 or float(row.get("reservado_os") or 0) != 0:
            cur.close()
            return {"success": False, "message": "Produto tem estoque ou reserva — não pode ser excluído."}
        for label, sql in _DEP_CHECKS:
            try:
                cur.execute(sql, (codigo_int,))
                if cur.fetchone():
                    cur.close()
                    return {"success": False, "message": f"Existem registros de {label} para este produto — não pode ser excluído."}
            except Exception:
                # tabela pode não existir nesta instalação — não bloqueia a exclusão por isso
                continue
        for tbl, col in [
            ("pecas_fornecedor", "peca"), ("pecaseq", "codigo"), ("pecas_secundaria", "peca_principal"),
            ("pecas_xml", "codigo_int"), ("pecas_protocolo_st", "codigo_int"), ("pecas_anexos", "codigo_int"),
        ]:
            cur.execute(f"DELETE FROM {tbl} WHERE {col}=%s", (codigo_int,))
        cur.execute("DELETE FROM pecas WHERE codigo_int=%s", (codigo_int,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Produto excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Grade do Produto — gerada como produtos-filhos de verdade (mesma regra
# do legado: cada combinação cor x tamanho vira um novo registro em
# `pecas`, com preço/fiscal copiados do produto principal). Só permitido
# se controle_configuracao.grade estiver ligado.
# ---------------------------------------------------------------------------

def _criar_itens_grade_sync(servidor: str, banco: str, codigo_int: str, combinacoes: list) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_grade_ativo(cur):
            cur.close()
            return {"success": False, "message": "Módulo Grade desativado — ative em Configurações > Módulos e Recursos."}

        cur.execute("SELECT * FROM pecas WHERE codigo_int=%s", (codigo_int,))
        principal = cur.fetchone()
        if not principal:
            cur.close()
            return {"success": False, "message": "Produto principal não encontrado."}

        criados = []
        for combo in combinacoes:
            cor = (combo.get("cor") or "").strip()
            tamanho = (combo.get("tamanho") or "").strip()
            if not cor:
                continue
            novo_codigo = _gerar_codigo_int_sync(cur)
            campos = {k: v for k, v in principal.items() if k not in ("codigo_int", "AutoNumProdutos")}
            campos["codigo_fab"] = f"{(principal.get('codigo_fab') or '').strip()}-{cor}-{tamanho}".strip("-")
            campos["codigo_int"] = novo_codigo
            campos["qtd"] = 0
            campos["reservado"] = 0
            campos["reservado_os"] = 0
            cols = list(campos.keys())
            placeholders = ",".join(["%s"] * len(cols))
            cur.execute(f"INSERT INTO pecas ([{'],['.join(cols)}]) VALUES ({placeholders})", tuple(campos.values()))

            cur.execute(
                "INSERT INTO pecas_xml (codigo_int, codigo_fab, codigo_xml, fornecedor_xml) "
                "SELECT %s, %s, codigo_xml, fornecedor_xml FROM pecas_xml WHERE codigo_int=%s",
                (novo_codigo, campos["codigo_fab"], codigo_int),
            )
            cur.execute(
                "INSERT INTO pecas_grade (codigo, equivalente, cor, tamanho) VALUES (%s,%s,%s,%s)",
                (codigo_int, novo_codigo, cor, tamanho),
            )
            criados.append({"codigo_int": novo_codigo, "cor": cor, "tamanho": tamanho})

        conn.commit()
        cur.close()
        return {"success": True, "message": f"{len(criados)} item(ns) de grade criado(s).", "itens": criados}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao criar grade: {e}"}
    finally:
        conn.close()


def _list_cores_grade_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    """Cores já usadas na grade deste produto — mesma query do legado
    (FrmAsoFot.CarregaLista), reaproveitada aqui pro seletor de cor da
    aba Grade e do modal de fotos."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT DISTINCT cores.codigo, cores.descricao FROM cores, pecas_grade "
            "WHERE pecas_grade.cor = cores.codigo AND pecas_grade.codigo=%s ORDER BY cores.descricao",
            (codigo_int,),
        )
        return {"success": True, "items": [_row_to_dict(r) for r in cur.fetchall()]}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Wrappers async
# ---------------------------------------------------------------------------

async def list_produtos(servidor: str, banco: str, search: str = "", page: int = 1, size: int = 20) -> dict:
    return await asyncio.to_thread(_list_produtos_sync, servidor, banco, search, page, size)


async def get_produto(servidor: str, banco: str, codigo_int: str) -> dict:
    return await asyncio.to_thread(_get_produto_sync, servidor, banco, codigo_int)


async def save_produto(servidor: str, banco: str, codigo_int: Optional[str], dados: dict) -> dict:
    return await asyncio.to_thread(_save_produto_sync, servidor, banco, codigo_int, dados)


async def delete_produto(servidor: str, banco: str, codigo_int: str) -> dict:
    return await asyncio.to_thread(_delete_produto_sync, servidor, banco, codigo_int)


async def criar_itens_grade(servidor: str, banco: str, codigo_int: str, combinacoes: list) -> dict:
    return await asyncio.to_thread(_criar_itens_grade_sync, servidor, banco, codigo_int, combinacoes)


async def list_cores_grade(servidor: str, banco: str, codigo_int: str) -> dict:
    return await asyncio.to_thread(_list_cores_grade_sync, servidor, banco, codigo_int)

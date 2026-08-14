"""Etiquetas de Produto — Painel de Relatórios > Estoque.

Migração de `Geral\\FrmEtqProd.frm` (2989 linhas, o maior form já rastreado
nesta migração) — impressão de etiquetas de estoque, carregadas a partir
de uma Nota Fiscal de Entrada (recebimento) ou adicionadas manualmente por
código, com um combobox de "Modelo de Etiqueta" que no legado despacha pra
3 mecanismos de impressão completamente diferentes: `Printer` GDI puro
(2 modelos "Identificação", folha laser tipo Pimaco), uma DLL COM .NET via
GDI+ (2 modelos "Gôndola", com código de barras EAN), e comandos EPL crus
escritos direto num compartilhamento de rede fixo `\\\\<computador>\\ZEBRA`
(4 modelos térmicos Zebra GC420/TLP2844).

**Decisões do usuário (2026-08-07, `AskUserQuestion`)**:
- **Zebra (térmica)**: não implementado nesta rodada — só documentado no
  Modo Didático da tela (ícone "i"), explicando que precisa de uma extensão
  do print-agent local (`project_impressao_silenciosa`) capaz de falar EPL
  cru com a impressora, que ainda não existe. Os 4 modelos continuam
  cadastrados em `modelo_etiqueta` (pra já aparecerem no combobox e não
  precisar de migração de schema depois), mas o endpoint de impressão
  bloqueia com mensagem clara se um deles for escolhido.
- **Botões "Excluir"/"Limpar Todos"**: no legado são inertes (nenhuma Sub
  por trás, confirmado por rastreio completo do arquivo) — implementados
  de verdade aqui (não é regra de negócio a preservar, é lacuna real do
  legado).
- **Matriz de Grade (Cor×Tamanho)**: incluída nesta rodada — ver
  `listar_grade`.
- **Paginação do modelo "Gôndola Não Fiscal"**: o legado tem um bug real
  (sem `HasMorePages`, conteúdo desenha além da página no GDI+) — não
  relevante aqui, impressão via HTML/CSS no navegador pagina sozinha por
  conteúdo (`@page`), nada a replicar nem corrigir.

**Tabela nova `modelo_etiqueta`** (arquitetura pedida pelo usuário — "já
preparar tabela de modelos" em vez de só constantes no código, deixando a
porta aberta pra cadastro de modelo customizado no futuro sem migração de
schema): `codigo` (mesmo índice do combobox legado, 0-7, PK), `nome`,
`formato` (`grade_laser` = grade de etiquetas pequenas em folha comum,
paginada, com margem/salto — os 2 modelos "Identificação"; `gondola` =
cartão maior com código de barras, os 2 modelos "Gôndola"; `termica` = EPL
cru, os 4 Zebra, não implementados), `especificacao` (texto de ajuda),
`colunas`, `linhas_por_folha` (NULL pra gôndola-não-fiscal, que não pagina
por posição fixa), `largura_cm`, `altura_cm`, `margem_lateral_cm`,
`margem_superior_cm` (só editável/gravável em `formato='grade_laser'` —
os outros formatos ignoram margem por completo no legado também, não é
limitação arbitrária desta migração), `tem_barcode` (bit).

**Simplificações conscientes vs. o legado** (ver "Não replicar truques
VB6" em CLAUDE.md):
- A subquery de cor/tamanho no caminho "Selecionar" (via `pecaseq`) não é
  portada — no legado ela nunca aparece de fato na etiqueta impressa
  (colunas ocultas do grid, sem uso downstream confirmado no rastreio),
  puro dado morto.
- `pecas.DESCRICAO_PDV`/checkbox "Usar descrição NFCe" só se aplica ao
  caminho manual (`adicionar_manual`) — replica exatamente a assimetria
  real do legado (o caminho por NF nunca lê essa coluna).
- O default hardcoded do checkbox por CNPJ específico (`cgc = '1524116...'`)
  não foi portado — claramente um ajuste de cliente único, não regra
  geral.
- A resolução Cor×Tamanho é feita numa única query (JOIN direto,
  `pecas_grade`+`cores`+`pecas`), não no padrão 2-etapas do legado (listar
  matriz vazia → resolver célula por célula sob demanda) — evita N+1
  chamadas, mesmo dado final.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

MODELOS_SEED = [
    (0, "IDENTIFICAÇÃO (4 POR LINHA)", "grade_laser",
     "ETIQUETA 1,27CM X 2,24CM 8X20 160 ETIQUETAS P/FOLHA", 4, 20, 4.75, 1.27, 0.850, 0.950, 0),
    (1, "IDENTIFICAÇÃO (8 POR LINHA)", "grade_laser",
     "ETIQUETA 1,27CM X 2,10CM 8X20 160 ETIQUETAS P/FOLHA", 8, 20, 2.10, 1.27, 0.850, 0.950, 0),
    (2, "ETIQUETA DE GÔNDOLA", "gondola",
     "Cartão com código de barras — até 20 itens por folha (2 colunas × 10 linhas)", 2, 10, 9.0, 4.0, None, None, 1),
    (3, "ZEBRA GC420 3 COLUNAS", "termica",
     "Impressora térmica Zebra GC420, 3 colunas — requer agente de impressão dedicado (não disponível ainda)", 3, None, None, None, None, None, 1),
    (4, "ZEBRA TLP2844 3 COLUNAS", "termica",
     "Impressora térmica Zebra TLP2844, 3 colunas — requer agente de impressão dedicado (não disponível ainda)", 3, None, None, None, None, None, 1),
    (5, "ETIQUETA DE GÔNDOLA NÃO FISCAL", "gondola",
     "Cartão com código de barras — 1 coluna, sem limite de itens por folha", 1, None, 9.0, 4.0, None, None, 1),
    (6, "ZEBRA GC420 2 COLUNAS", "termica",
     "Impressora térmica Zebra GC420, 2 colunas — requer agente de impressão dedicado (não disponível ainda)", 2, None, None, None, None, None, 1),
    (7, "ZEBRA TLP2844 2 COLUNAS", "termica",
     "Impressora térmica Zebra TLP2844, 2 colunas — requer agente de impressão dedicado (não disponível ainda)", 2, None, None, None, None, None, 1),
]


def _ensure_modelo_etiqueta_table(cur) -> None:
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'modelo_etiqueta') "
        "CREATE TABLE modelo_etiqueta ("
        " codigo INT PRIMARY KEY, nome NVARCHAR(60) NOT NULL, formato NVARCHAR(20) NOT NULL,"
        " especificacao NVARCHAR(200) NULL, colunas INT NOT NULL, linhas_por_folha INT NULL,"
        " largura_cm DECIMAL(6,3) NULL, altura_cm DECIMAL(6,3) NULL,"
        " margem_lateral_cm DECIMAL(6,3) NULL, margem_superior_cm DECIMAL(6,3) NULL,"
        " tem_barcode BIT NOT NULL DEFAULT 0)"
    )
    cur.execute("SELECT COUNT(1) AS n FROM modelo_etiqueta")
    if int((cur.fetchone() or {}).get("n") or 0) == 0:
        for row in MODELOS_SEED:
            cur.execute(
                "INSERT INTO modelo_etiqueta (codigo, nome, formato, especificacao, colunas, "
                " linhas_por_folha, largura_cm, altura_cm, margem_lateral_cm, margem_superior_cm, tem_barcode) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                row,
            )


def _listar_modelos_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_modelo_etiqueta_table(cur)
        cur.execute("SELECT * FROM modelo_etiqueta ORDER BY codigo")
        modelos = cur.fetchall()
        cur.close()
        conn.commit()
        return {"success": True, "modelos": modelos}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "modelos": []}
    finally:
        conn.close()


def _gravar_margem_sync(servidor: str, banco: str, codigo: int, margem_lateral: float, margem_superior: float) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_modelo_etiqueta_table(cur)
        cur.execute("SELECT formato FROM modelo_etiqueta WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Modelo de etiqueta não encontrado."}
        if row["formato"] != "grade_laser":
            return {"success": False, "message": "Este modelo de etiqueta não usa margem configurável."}
        cur.execute(
            "UPDATE modelo_etiqueta SET margem_lateral_cm=%s, margem_superior_cm=%s WHERE codigo=%s",
            (margem_lateral, margem_superior, codigo),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Configurações gravadas!"}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _buscar_nf_sync(servidor: str, banco: str, num_nf: str, serie_nf: str, fornecedor: int) -> dict:
    if not num_nf or not serie_nf or not fornecedor:
        return {"success": False, "message": "Informe NF, Série e Fornecedor.", "itens": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, data_mov FROM n_fiscal WHERE num_nf=%s AND serie_nf=%s AND fornecedor=%s",
            (num_nf, serie_nf, fornecedor),
        )
        nf = cur.fetchone()
        if not nf:
            return {"success": False, "message": "Nota Fiscal não cadastrada — impressão não permitida.", "itens": []}
        cur.execute(
            "SELECT p.codigo_int, p.codigo_fab, p.descricao, p.codigo_bar, p.p_venda, "
            "  nfi.qtd_un_compra, nfi.qtd "
            "FROM n_fiscal_itens nfi JOIN pecas p ON p.codigo_int = nfi.codigo_int "
            "WHERE nfi.codigo=%s ORDER BY nfi.id",
            (nf["codigo"],),
        )
        itens = []
        for r in cur.fetchall():
            qtd_compra = float(r.get("qtd_un_compra") or 1)
            qtd = float(r.get("qtd") or 0)
            itens.append({
                "codigo_int": (r.get("codigo_int") or "").strip(),
                "codigo_fab": (r.get("codigo_fab") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "codigo_bar": (r.get("codigo_bar") or "").strip(),
                "p_venda": float(r.get("p_venda") or 0),
                "quant": int(qtd_compra * qtd),
            })
        cur.close()
        return {
            "success": True, "itens": itens,
            "data_mov": nf["data_mov"].isoformat() if hasattr(nf.get("data_mov"), "isoformat") else nf.get("data_mov"),
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


def _buscar_produto_sync(servidor: str, banco: str, termo: str) -> dict:
    termo = (termo or "").strip()
    if not termo:
        return {"success": False, "message": "Informe o código do produto."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        row = None
        for coluna in ("codigo_int", "codigo_fab", "codigo_bar"):
            cur.execute(
                f"SELECT codigo_int, codigo_fab, descricao, descricao_pdv, codigo_bar, p_venda "
                f"FROM pecas WHERE {coluna} = %s",
                (termo,),
            )
            row = cur.fetchone()
            if row:
                break
        if not row:
            return {"success": False, "message": "Produto não encontrado."}
        cur.execute("SELECT COUNT(1) AS n FROM pecas_grade WHERE codigo=%s", (row["codigo_int"],))
        tem_grade = int((cur.fetchone() or {}).get("n") or 0) > 0
        cur.close()
        return {
            "success": True,
            "produto": {
                "codigo_int": (row.get("codigo_int") or "").strip(),
                "codigo_fab": (row.get("codigo_fab") or "").strip(),
                "descricao": (row.get("descricao") or "").strip(),
                "descricao_pdv": (row.get("descricao_pdv") or "").strip(),
                "codigo_bar": (row.get("codigo_bar") or "").strip(),
                "p_venda": float(row.get("p_venda") or 0),
                "tem_grade": tem_grade,
            },
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _listar_grade_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    if not codigo_int:
        return {"success": False, "message": "Informe o produto.", "grade": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT g.cor, c.descricao AS cor_descricao, g.tamanho, g.equivalente AS codigo_int, "
            "  p.codigo_fab, p.descricao, p.codigo_bar, p.p_venda "
            "FROM pecas_grade g "
            "JOIN cores c ON c.codigo = g.cor "
            "JOIN pecas p ON p.codigo_int = g.equivalente "
            "WHERE g.codigo=%s AND p.situacao='A' "
            "ORDER BY c.descricao, g.tamanho",
            (codigo_int,),
        )
        grade = []
        for r in cur.fetchall():
            grade.append({
                "cor": r.get("cor"),
                "cor_descricao": (r.get("cor_descricao") or "").strip(),
                "tamanho": (r.get("tamanho") or "").strip(),
                "codigo_int": (r.get("codigo_int") or "").strip(),
                "codigo_fab": (r.get("codigo_fab") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "codigo_bar": (r.get("codigo_bar") or "").strip(),
                "p_venda": float(r.get("p_venda") or 0),
            })
        cur.close()
        return {"success": True, "grade": grade}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "grade": []}
    finally:
        conn.close()


async def listar_modelos(servidor, banco):
    return await asyncio.to_thread(_listar_modelos_sync, servidor, banco)


async def gravar_margem(servidor, banco, codigo, margem_lateral, margem_superior):
    return await asyncio.to_thread(_gravar_margem_sync, servidor, banco, codigo, margem_lateral, margem_superior)


async def buscar_nf(servidor, banco, num_nf, serie_nf, fornecedor):
    return await asyncio.to_thread(_buscar_nf_sync, servidor, banco, num_nf, serie_nf, fornecedor)


async def buscar_produto(servidor, banco, termo):
    return await asyncio.to_thread(_buscar_produto_sync, servidor, banco, termo)


async def listar_grade(servidor, banco, codigo_int):
    return await asyncio.to_thread(_listar_grade_sync, servidor, banco, codigo_int)

"""MDF-e (Manifesto Eletrônico de Documentos Fiscais) — Fase A: cadastro
do manifesto (cabeçalho + veículo/motorista/percurso) + anexar NF-e/
NFC-e, SEM emissão real ao SEFAZ. Migração de `Kontacto\\FrmTraMDF.frm`
(3681 linhas, única cópia no projeto).

**Fase B (fora de escopo aqui, registrada em PENDENCIAS.md)**: emissão
real (`GeraMDFe`), Encerrar (`EncerraMDFe`), Cancelar (`CancelaMDFe`),
Consultar Situação (`ConsultaSituacaoMDFe`), Gerar XML
(`MontaXMLMDFe`), DAMDFE impresso, alocação de número/série
(`controle_aux.numero_MDFE`/`serie_MDFE`, já existem e já são
editáveis via Controle do Sistema — só não são tocados nesta fase). Ver
`Backon.Controllers/NFe.vb:4952-6784` pra referência de quando essa fase
começar.

**Tabelas reaproveitadas, já migradas antes desta rodada**:
`veiculos_transp` (Veículo/Reboque — `veiculos_service.py`),
`funcionarios` (Motorista/Ajudante), `n_fiscal` (já tem `volumes`/
`peso_bruto`/`peso_liquido`, adicionados numa rodada anterior desta
mesma sessão pro Transportador da NF-e Avulsa).

**Achado real que já antecipava este módulo**: `veiculos_service.py`'s
guard de exclusão já checa a tabela `MDFe` (`WHERE veiculo=%s`) antes de
permitir excluir um veículo — confirma que essa é a grafia/nome real da
tabela de cabeçalho já usado neste código (não inventado agora).

**Regras reais portadas desta fase** (`FrmTraMDF.frm`):
- Carga é SEMPRE o endereço da própria empresa (`:2152-2155`) — não é
  resolvido por nota, é fixo pro manifesto inteiro.
- Descarga é resolvida da CONTRAPARTE de cada nota via `tipo_mov.
  origem_destino` (`'C'`→Cliente, `'F'`→Fornecedor, `:2113-2149`),
  casando `cidade`/`uf` do cadastro contra `municipio`/`UF` reais. Como
  não foi possível confirmar ao vivo nesta sessão (conexão de teste
  instável) se a tabela `municipio` desta instalação tem o mesmo
  formato/dado usado pelo legado, a resolução tenta o JOIN real
  primeiro e cai pro seed conhecido de `nfe_fiscal_common.
  resolver_cod_municipio_ibge` se não achar — nunca bloqueia a tela,
  só deixa a descarga em branco com aviso (mesmo comportamento do
  legado: a lista de opções fica vazia, sem trava explícita).
- `volumes`/`peso_bruto`/`peso_liquido` de cada nota vêm da própria nota
  (`:2097-2111`, fallback 0 se não numérico).
- Obrigatório pra gravar: Veículo e Motorista (`:1932-1941`). Reboque/
  Ajudante opcionais. UF Início/Fim default pra UF da empresa
  (`controle.uf`) se não escolhidos.
- Notas só podem ser incluídas/excluídas do manifesto enquanto
  `situacao='A'` (`:1410`/`:2075`/`:2772`/`:2887`) — nesta Fase A a
  situação NUNCA sai de `'A'` (não existe ação que mude), a regra é só
  documentada aqui pra Fase B reaplicar quando os outros estados
  existirem.
- Busca de notas elegíveis exige `nf.situacao='A'` (`Command2_Click,
  :1739`) — sem bloqueio de `situacao_nfe`/`protocolo_sefaz`, só aviso
  visual (mesmo padrão já usado em `notas_fiscais_service._list_
  consulta_sync` pra rótulos de nota problemática).
- Percurso: lista livre de UFs adicionais, sem limite nesta fase (o
  limite "só 1 UF além da UF da empresa" encontrado no `.frm` é regra
  de EMISSÃO, `Command7_Click`, Fase B).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services import nfe_fiscal_common

_DDL_MDFE = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'MDFe')
BEGIN
    CREATE TABLE MDFe (
        codigo INT IDENTITY(1,1) PRIMARY KEY,
        situacao CHAR(1) NOT NULL DEFAULT 'A',
        data_mdfe DATE NULL,
        data_saida DATE NULL,
        hora_saida VARCHAR(5) NULL,
        veiculo INT NOT NULL,
        reboque INT NULL,
        motorista INT NOT NULL,
        ajudante INT NULL,
        ufini CHAR(2) NULL,
        uffim CHAR(2) NULL,
        percurso NVARCHAR(200) NULL,
        tptransp SMALLINT NULL,
        obs NVARCHAR(500) NULL,
        criado_em DATETIME NOT NULL DEFAULT GETDATE(),
        usuario NVARCHAR(50) NULL
    );
END
"""
_DDL_MDFE_NOTAS = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mdfe_notas')
BEGIN
    CREATE TABLE mdfe_notas (
        codigo INT IDENTITY(1,1) PRIMARY KEY,
        cod_mdfe INT NOT NULL,
        nota INT NOT NULL,
        origem INT NULL,
        destino INT NULL,
        volumes INT NULL,
        peso_bruto DECIMAL(12,3) NULL,
        peso_liquido DECIMAL(12,3) NULL
    );
    CREATE INDEX IX_mdfe_notas_cod_mdfe ON mdfe_notas (cod_mdfe);
END
"""
# Colunas desta Fase A que podem estar faltando numa `MDFe` já existente
# (instalação que já tem a tabela do legado, mas talvez sem alguma coluna
# nova) — checagem idempotente por coluna, mesmo padrão de sempre.
_COLUNAS_MDFE_FASE_A = [
    ("situacao", "CHAR(1) NOT NULL DEFAULT 'A'"),
    ("data_mdfe", "DATE NULL"),
    ("data_saida", "DATE NULL"),
    ("hora_saida", "VARCHAR(5) NULL"),
    ("veiculo", "INT NULL"),
    ("reboque", "INT NULL"),
    ("motorista", "INT NULL"),
    ("ajudante", "INT NULL"),
    ("ufini", "CHAR(2) NULL"),
    ("uffim", "CHAR(2) NULL"),
    ("percurso", "NVARCHAR(200) NULL"),
    ("tptransp", "SMALLINT NULL"),
    ("obs", "NVARCHAR(500) NULL"),
]

# Colunas da Fase B (emissão real, encerramento, cancelamento, consulta,
# gerar XML) — mesmo padrão idempotente por coluna. `serie_mdfe`/`tp_amb`
# congelam o número de série e o ambiente (produção/homologação) usados
# NA EMISSÃO deste manifesto específico — nunca re-derivados depois (o
# ambiente/série da empresa podem mudar entre a emissão e uma consulta/
# encerramento posteriores). Ver `mdfe_emissao_service.py`.
_COLUNAS_MDFE_FASE_B = [
    ("num_mdfe", "INT NULL"),
    ("serie_mdfe", "VARCHAR(3) NULL"),
    ("chave_acesso", "CHAR(44) NULL"),
    ("dhemi", "DATETIME NULL"),
    ("tp_amb", "CHAR(1) NULL"),
    ("protocolo_sefaz", "VARCHAR(20) NULL"),
    ("dhRecbto", "DATETIME NULL"),
    ("xml_protMDFe", "NVARCHAR(MAX) NULL"),
    ("xml", "NVARCHAR(MAX) NULL"),
    ("urlqrcode", "NVARCHAR(300) NULL"),
    ("cstat", "VARCHAR(5) NULL"),
    ("municipio_encerra", "INT NULL"),
    ("data_encerramento", "DATE NULL"),
    ("xml_retEventoMDFe_encerra", "NVARCHAR(MAX) NULL"),
    ("xml_retEventoMDFe_Cancela", "NVARCHAR(MAX) NULL"),
    ("motivo_cancelamento", "NVARCHAR(300) NULL"),
    ("historico", "NVARCHAR(MAX) NULL"),
]


def _ensure_mdfe_tables(cur) -> None:
    """Idempotente — se `MDFe`/`mdfe_notas` já existirem (bem provável,
    dado que o legado VB6 já usa essas tabelas ativamente), só garante
    que as colunas das Fases A/B existem, sem recriar nada."""
    cur.execute(_DDL_MDFE)
    cur.execute(_DDL_MDFE_NOTAS)
    for col, ddl in _COLUNAS_MDFE_FASE_A + _COLUNAS_MDFE_FASE_B:
        cur.execute(
            "IF NOT EXISTS (SELECT 1 FROM sys.columns "
            f"WHERE Name='{col}' AND Object_ID=Object_ID('MDFe')) "
            f"ALTER TABLE MDFe ADD {col} {ddl}"
        )


# ============ Listagem ============
def _list_mdfe_sync(servidor: str, banco: str, situacao: Optional[str] = None) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_mdfe_tables(cur)
        where = "WHERE m.situacao=%s" if situacao else ""
        params = (situacao,) if situacao else ()
        cur.execute(
            f"""
            SELECT m.codigo, m.situacao, m.data_mdfe, m.veiculo, v.placa,
                   m.motorista, f.nome_guerra AS motorista_nome, m.ufini, m.uffim,
                   (SELECT COUNT(*) FROM mdfe_notas mn WHERE mn.cod_mdfe = m.codigo) AS qtd_notas
            FROM MDFe m
            LEFT JOIN veiculos_transp v ON v.codigo = m.veiculo
            LEFT JOIN funcionarios f ON f.codigo_int = m.motorista
            {where}
            ORDER BY m.codigo DESC
            """,
            params,
        )
        items = cur.fetchall()
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _get_mdfe_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_mdfe_tables(cur)
        cur.execute(
            """
            SELECT m.*, v.placa AS placa_veiculo, f.nome_guerra AS motorista_nome
            FROM MDFe m
            LEFT JOIN veiculos_transp v ON v.codigo = m.veiculo
            LEFT JOIN funcionarios f ON f.codigo_int = m.motorista
            WHERE m.codigo=%s
            """,
            (codigo,),
        )
        cab = cur.fetchone()
        if not cab:
            cur.close()
            return {"success": False, "message": "MDF-e não encontrado."}
        cur.execute(
            """
            SELECT mn.codigo, mn.nota, mn.origem, mn.destino, mn.volumes, mn.peso_bruto, mn.peso_liquido,
                   nf.num_nf, nf.serie_nf, nf.valor_total, nf.data_nf, nf.fornecedor, nf.mov,
                   tm.origem_destino
            FROM mdfe_notas mn
            JOIN n_fiscal nf ON nf.codigo = mn.nota
            LEFT JOIN tipo_mov tm ON tm.codigo = nf.mov
            WHERE mn.cod_mdfe=%s
            ORDER BY mn.codigo
            """,
            (codigo,),
        )
        notas = cur.fetchall()
        cur.close()
        return {"success": True, "mdfe": cab, "notas": notas}
    finally:
        conn.close()


# ============ Gravar cabeçalho ============
def _save_mdfe_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict, usuario: Optional[str]) -> dict:
    if not dados.get("veiculo"):
        return {"success": False, "message": "Preencher o Veículo !"}
    if not dados.get("motorista"):
        return {"success": False, "message": "Preencher o Motorista !"}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_mdfe_tables(cur)

        ufini = (dados.get("ufini") or "").strip().upper()
        uffim = (dados.get("uffim") or "").strip().upper()
        if not ufini or not uffim:
            cur.execute("SELECT TOP 1 uf FROM controle")
            row = cur.fetchone() or {}
            uf_empresa = (row.get("uf") or "").strip().upper()
            ufini = ufini or uf_empresa
            uffim = uffim or uf_empresa

        vals = {
            "data_mdfe": dados.get("data_mdfe"),
            "veiculo": dados["veiculo"],
            "reboque": dados.get("reboque") or None,
            "motorista": dados["motorista"],
            "ajudante": dados.get("ajudante") or None,
            "ufini": ufini or None,
            "uffim": uffim or None,
            "percurso": (dados.get("percurso") or "").strip()[:200] or None,
            "tptransp": dados.get("tptransp") or None,
            "obs": (dados.get("obs") or "").strip()[:500] or None,
        }

        if codigo:
            cur.execute("SELECT situacao FROM MDFe WHERE codigo=%s", (codigo,))
            existente = cur.fetchone()
            if not existente:
                cur.close()
                return {"success": False, "message": "MDF-e não encontrado."}
            if existente.get("situacao") not in ("A", "N"):
                cur.close()
                return {"success": False, "message": "Só é possível alterar manifestos em edição ou não transmitidos."}
            sets = ", ".join(f"{k}=%s" for k in vals)
            cur.execute(f"UPDATE MDFe SET {sets} WHERE codigo=%s", (*vals.values(), codigo))
            novo_codigo = codigo
        else:
            cols = ", ".join(["situacao", "usuario", *vals.keys()])
            placeholders = ", ".join(["%s"] * (len(vals) + 2))
            cur.execute(
                f"INSERT INTO MDFe ({cols}) VALUES ({placeholders})",
                ("A", usuario, *vals.values()),
            )
            cur.execute("SELECT @@IDENTITY AS codigo")
            row = cur.fetchone()
            novo_codigo = int(row["codigo"] if isinstance(row, dict) else row[0])

        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo_codigo, "message": "MDF-e gravado."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_mdfe_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM MDFe WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "MDF-e não encontrado."}
        if row.get("situacao") != "A":
            cur.close()
            return {"success": False, "message": "Só é possível excluir manifestos em edição (sem MDF-e emitido)."}
        cur.execute("DELETE FROM mdfe_notas WHERE cod_mdfe=%s", (codigo,))
        cur.execute("DELETE FROM MDFe WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "MDF-e excluído."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ============ Buscar notas elegíveis ============
_SITUACAO_NFE_LABEL = {
    3: "NFE INUTILIZADA NO SEFAZ",
    5: "NFE DENEGADA",
}


def _rotulo_aviso_nota(row: dict) -> Optional[str]:
    """Réplica simplificada dos rótulos de aviso visual do legado
    (`FrmConNf`/`Command2_Click` — inutilizada/denegada/não validada/
    contingência) — nunca bloqueia a seleção, só avisa."""
    situacao_nfe = row.get("situacao_nfe") or 0
    protocolo = (row.get("protocolo_sefaz") or "").strip()
    if situacao_nfe in _SITUACAO_NFE_LABEL:
        return _SITUACAO_NFE_LABEL[situacao_nfe]
    if situacao_nfe == 2:
        return "NFE EMITIDA EM CONTINGÊNCIA"
    if situacao_nfe in (1, 2) and not protocolo:
        return "NFE NÃO VALIDADA"
    return None


def _buscar_notas_elegiveis_sync(servidor: str, banco: str, f: dict) -> dict:
    """Réplica de `Command2_Click` (`FrmTraMDF.frm:1724-1760`) — só notas
    `situacao='A'` (ativas, não canceladas) entram na busca; notas com
    problema de SEFAZ (inutilizada/denegada/não validada/contingência)
    aparecem com um aviso, mas continuam selecionáveis (mesmo
    comportamento do legado)."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ["nf.situacao='A'"]
        params: list = []

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

        termo = (f.get("cliente_fornecedor_termo") or "").strip()
        if termo:
            tabela_termo = "cliente" if f.get("tipo_pessoa") == "C" else "fornecedor"
            col_nome = "nome"
            col_codigo = "codigo" if tabela_termo == "cliente" else "codigo_int"
            where.append("tm.origem_destino=%s")
            params.append(f.get("tipo_pessoa") or "C")
            if termo.isdigit():
                where.append("nf.fornecedor=%s")
                params.append(int(termo))
            else:
                where.append(f"nf.fornecedor IN (SELECT {col_codigo} FROM {tabela_termo} WHERE {col_nome} LIKE %s)")
                params.append(f"%{termo}%")

        for de_key, ate_key, col in [("data_nf_de", "data_nf_ate", "nf.data_nf")]:
            if f.get(de_key):
                where.append(f"{col} >= %s")
                params.append(f[de_key])
            if f.get(ate_key):
                where.append(f"{col} <= %s")
                params.append(f[ate_key])

        cur.execute(
            "SELECT nf.codigo, nf.num_nf, nf.serie_nf, nf.fornecedor, nf.mov, nf.valor_total, "
            "nf.data_nf, nf.situacao_nfe, nf.protocolo_sefaz, nf.volumes, nf.peso_bruto, nf.peso_liquido, "
            "tm.descricao AS mov_descricao, tm.origem_destino "
            "FROM n_fiscal nf LEFT JOIN tipo_mov tm ON tm.codigo = nf.mov "
            f"WHERE {' AND '.join(where)} ORDER BY nf.data_nf DESC, nf.codigo DESC",
            tuple(params),
        )
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
            tipo = "F" if (r.get("origem_destino") or "") == "F" else "C"
            nome = nomes.get((tipo, r.get("fornecedor"))) or ""
            items.append({**r, "cliente_fornecedor_nome": (nome or "").strip(), "aviso": _rotulo_aviso_nota(r)})

        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


# ============ Anexar/remover nota ============
def _resolver_municipio_contraparte_sync(cur, tipo: str, codigo: int) -> dict:
    """Resolve cidade/UF/código de município da CONTRAPARTE de uma nota
    (Cliente ou Fornecedor) — réplica de `FrmTraMDF.frm:2113-2149`.
    Tenta o JOIN real contra `municipio`/`UF` primeiro (mesma consulta do
    legado); se a tabela não existir nesta instalação ou não achar
    casamento, cai pro seed conhecido de `nfe_fiscal_common.
    resolver_cod_municipio_ibge`. Nunca lança exceção — devolve
    `cod_municipio=None` + `aviso` se nada resolver.

    **Confirmado ao vivo 2026-08-22 contra ARGEN TESTE** (tabelas
    `MDFe`/`mdfe_notas`/`municipio`/`UF` existem de verdade — só leitura
    de schema, nenhuma emissão fiscal chamada): `municipio.codigo` é
    `FLOAT` no banco real (não `INT` como presumido antes de confirmar),
    por isso o valor é sempre normalizado com `_normalizar_cod_municipio`
    antes de devolver — tanto o JOIN real (float) quanto o fallback do
    seed (string) precisam virar `int` puro pra caber em `mdfe_notas.
    origem`/`.destino` (essas sim `INT`, confirmado)."""
    if tipo == "F":
        cur.execute("SELECT TOP 1 cidade, uf FROM fornecedor_end WHERE codigo=%s ORDER BY tipo_endereco", (codigo,))
    else:
        cur.execute("SELECT TOP 1 cidade, uf FROM cliente_end WHERE codigo=%s ORDER BY tipo", (codigo,))
    end = cur.fetchone()
    if not end:
        return {"cidade": None, "uf": None, "cod_municipio": None, "aviso": "Sem endereço cadastrado para resolver a descarga."}

    cidade = (end.get("cidade") or "").strip()
    uf = (end.get("uf") or "").strip().upper()

    cod_municipio = None
    try:
        cur.execute(
            "SELECT TOP 1 municipio.codigo AS codmun FROM municipio, UF "
            "WHERE municipio.descricao = %s AND UF.codigo = %s "
            "AND LEFT(RTRIM(LTRIM(STR(municipio.codigo))), 2) = UF.Cod_Ibge",
            (cidade, uf),
        )
        row = cur.fetchone()
        if row:
            cod_municipio = row.get("codmun")
    except Exception:
        # Tabela `municipio` pode não existir/ter formato diferente nalguma
        # instalação — nunca propaga, cai pro fallback abaixo.
        cod_municipio = None

    if not cod_municipio:
        cod_municipio = nfe_fiscal_common.resolver_cod_municipio_ibge(cidade, uf)
    cod_municipio = _normalizar_cod_municipio(cod_municipio)

    aviso = None if cod_municipio else f"Município '{cidade}/{uf}' não pôde ser resolvido — descarga ficará em branco para esta nota."
    return {"cidade": cidade, "uf": uf, "cod_municipio": cod_municipio, "aviso": aviso}


def _normalizar_cod_municipio(valor) -> Optional[int]:
    """`municipio.codigo` é FLOAT no banco real (confirmado ao vivo,
    ARGEN TESTE), mas `nfe_fiscal_common.resolver_cod_municipio_ibge`
    (fallback) devolve string, e `mdfe_notas.origem`/`.destino` são INT
    — normaliza os dois formatos possíveis pra um `int` puro antes de
    gravar, nunca deixa um float/string cru chegar no INSERT."""
    if valor is None:
        return None
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def _buscar_municipios_sync(servidor: str, banco: str, termo: str) -> dict:
    """Busca por nome na tabela `municipio` real (confirmada ao vivo,
    2026-08-22, ARGEN TESTE) — usada pelo seletor de "Município de
    Encerramento" (Fase B, `mdfe_emissao_service.encerrar_mdfe_sync`).
    Mesma regra `[GLOBAL]` de "todo campo de identidade precisa de busca"
    já aplicada a Cliente/Produto/Fornecedor/Nível."""
    termo = (termo or "").strip()
    if len(termo) < 2:
        return {"success": True, "items": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 30 municipio.codigo, municipio.descricao, UF.codigo AS uf "
            "FROM municipio, UF "
            "WHERE municipio.descricao LIKE %s "
            "AND LEFT(RTRIM(LTRIM(STR(municipio.codigo))), 2) = UF.Cod_Ibge "
            "ORDER BY municipio.descricao",
            (f"%{termo}%",),
        )
        items = [
            {**r, "codigo": _normalizar_cod_municipio(r.get("codigo"))}
            for r in cur.fetchall()
        ]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro ao buscar município: {e}"}
    finally:
        conn.close()


async def buscar_municipios(servidor, banco, termo):
    return await asyncio.to_thread(_buscar_municipios_sync, servidor, banco, termo)


def _resolver_origem_empresa_sync(cur) -> dict:
    """Carga é sempre o endereço da própria empresa (`FrmTraMDF.frm:2152-
    2155`)."""
    cur.execute("SELECT TOP 1 cidade, uf FROM controle")
    row = cur.fetchone() or {}
    cidade = (row.get("cidade") or "").strip()
    uf = (row.get("uf") or "").strip().upper()
    cod_municipio = None
    try:
        cur.execute(
            "SELECT TOP 1 municipio.codigo AS codmun FROM municipio, UF "
            "WHERE municipio.descricao = %s AND UF.codigo = %s "
            "AND LEFT(RTRIM(LTRIM(STR(municipio.codigo))), 2) = UF.Cod_Ibge",
            (cidade, uf),
        )
        r = cur.fetchone()
        if r:
            cod_municipio = r.get("codmun")
    except Exception:
        cod_municipio = None
    if not cod_municipio:
        cod_municipio = nfe_fiscal_common.resolver_cod_municipio_ibge(cidade, uf)
    return {"cidade": cidade, "uf": uf, "cod_municipio": _normalizar_cod_municipio(cod_municipio)}


def _anexar_nota_sync(servidor: str, banco: str, cod_mdfe: int, nota: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_mdfe_tables(cur)

        cur.execute("SELECT situacao FROM MDFe WHERE codigo=%s", (cod_mdfe,))
        mdfe = cur.fetchone()
        if not mdfe:
            cur.close()
            return {"success": False, "message": "MDF-e não encontrado."}
        if mdfe.get("situacao") not in ("A", "N"):
            cur.close()
            return {"success": False, "message": "Somente manifestos em edição ou não transmitidos podem ser editados!"}

        cur.execute(
            "SELECT nf.fornecedor, nf.volumes, nf.peso_bruto, nf.peso_liquido, tm.origem_destino "
            "FROM n_fiscal nf LEFT JOIN tipo_mov tm ON tm.codigo = nf.mov WHERE nf.codigo=%s",
            (nota,),
        )
        nf = cur.fetchone()
        if not nf:
            cur.close()
            return {"success": False, "message": "Nota Fiscal não encontrada."}

        origem = _resolver_origem_empresa_sync(cur)
        tipo = "F" if (nf.get("origem_destino") or "") == "F" else "C"
        destino = _resolver_municipio_contraparte_sync(cur, tipo, nf.get("fornecedor"))

        volumes = nf.get("volumes") if isinstance(nf.get("volumes"), (int, float)) else 0
        peso_bruto = nf.get("peso_bruto") if isinstance(nf.get("peso_bruto"), (int, float)) else 0
        peso_liquido = nf.get("peso_liquido") if isinstance(nf.get("peso_liquido"), (int, float)) else 0

        cur.execute("DELETE FROM mdfe_notas WHERE cod_mdfe=%s AND nota=%s", (cod_mdfe, nota))
        cur.execute(
            "INSERT INTO mdfe_notas (cod_mdfe, nota, origem, destino, volumes, peso_bruto, peso_liquido) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (cod_mdfe, nota, origem.get("cod_municipio"), destino.get("cod_municipio"), volumes, peso_bruto, peso_liquido),
        )
        conn.commit()
        cur.close()
        avisos = [a for a in (destino.get("aviso"),) if a]
        return {"success": True, "message": "Nota anexada ao manifesto.", "avisos": avisos}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao anexar nota: {e}"}
    finally:
        conn.close()


def _remover_nota_sync(servidor: str, banco: str, cod_mdfe: int, nota: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM MDFe WHERE codigo=%s", (cod_mdfe,))
        mdfe = cur.fetchone()
        if not mdfe:
            cur.close()
            return {"success": False, "message": "MDF-e não encontrado."}
        if mdfe.get("situacao") not in ("A", "N"):
            cur.close()
            return {"success": False, "message": "Somente manifestos em edição ou não transmitidos podem ser editados!"}
        cur.execute("DELETE FROM mdfe_notas WHERE cod_mdfe=%s AND nota=%s", (cod_mdfe, nota))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Nota removida do manifesto."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao remover nota: {e}"}
    finally:
        conn.close()


# ============ Wrappers async ============
async def list_mdfe(servidor, banco, situacao=None):
    return await asyncio.to_thread(_list_mdfe_sync, servidor, banco, situacao)


async def get_mdfe(servidor, banco, codigo):
    return await asyncio.to_thread(_get_mdfe_sync, servidor, banco, codigo)


async def save_mdfe(servidor, banco, codigo, dados, usuario):
    return await asyncio.to_thread(_save_mdfe_sync, servidor, banco, codigo, dados, usuario)


async def delete_mdfe(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_mdfe_sync, servidor, banco, codigo)


async def buscar_notas_elegiveis(servidor, banco, filtros):
    return await asyncio.to_thread(_buscar_notas_elegiveis_sync, servidor, banco, filtros)


async def anexar_nota(servidor, banco, cod_mdfe, nota):
    return await asyncio.to_thread(_anexar_nota_sync, servidor, banco, cod_mdfe, nota)


async def remover_nota(servidor, banco, cod_mdfe, nota):
    return await asyncio.to_thread(_remover_nota_sync, servidor, banco, cod_mdfe, nota)

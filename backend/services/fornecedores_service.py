"""Manutenção de Fornecedores — CRUD completo. Legado: `FrmmanForn.frm`.

Schema real (conferido ao vivo em GERDELL/BARESTELA, não assumido do VB6):
- `fornecedor.codigo_int` (int, PK real) / `fornecedor.codigo` (nvarchar(14),
  CPF ou CNPJ, sem máscara) — mesma convenção de `cliente.cgc_cpf`.
- **Mismatches rótulo/coluna do legado** (confirmados ao vivo, não apenas
  supostos do VB6 — mesmo padrão de discrepância já visto no mapeamento de
  Cliente): o campo rotulado "Cred.Icms" na tela grava na coluna
  `fornecedor.tipo` (nvarchar(1), S/N); o campo rotulado "Contato" (memo)
  grava em `fornecedor.obs_forn`. Replicados aqui com os rótulos do legado
  na UI, mas as colunas reais abaixo.
- `fornecedor.tipo` (S/N) é o ÚNICO uso desse nome de coluna aqui — não
  confundir com `servicos.tipo`/`pecas.tipo_peca` (campos "Tipo" de outras
  telas, sem relação).
- Colunas legadas SEM uso nesta tela (confirmadas existentes na tabela mas
  não referenciadas em nenhum SQL de `FrmmanForn.frm`): `obs` (distinto de
  `obs_forn`), `site`, `data_nasc`, `consumidor_final`, `INDPRES`, e o bloco
  de endereço/telefone "achatado" legado (`end_for`, `numero_for`,
  `complemento_for`, `bairro_for`, `cidade_for`, `uf_for`, `cep_for`,
  `ddd_for`, `telefone_for`, `fax_for` — superado por `fornecedor_end`/
  `fornecedor_tel`, tabelas multi-linha). Nenhum desses é lido/gravado
  aqui — não inventar UI para colunas que a tela original nunca usou.
- `fornecedor_tel`/`fornecedor_end`/`fornecedor_contato` têm PK real
  própria (`SEQUENCIA_FORNECEDOR_*` IDENTITY) — `codigo` nessas tabelas é
  só a FK pra `fornecedor.codigo_int`. Gravação é replace-all-on-save
  (delete tudo + reinsert), mesmo padrão já usado em Cliente — sem
  endpoint de update por linha.
- `distribuidor`/`shipper` ("Transportador" na tela) são FKs
  auto-referenciadas pra outro `fornecedor.codigo_int`, resolvidas na
  gravação por nome/fantasia/código (replicando `Campo_LostFocus`
  Index=20/14 do legado).
- `cliente_forn` ("Atividade" na tela) é FK pra `tipo_cliente.codigo` —
  MESMA tabela de lookup já usada por Cliente ("Tipo Cliente", também
  coluna `cliente_forn` lá) — reaproveita `/api/tipo-cliente`.
- `conta_transf_caixa`/`classe_caixa`/`sub_classe_caixa` reaproveitam os
  mesmos lookups (`contas`/`classes`/`sub_classes`) já usados em Cliente.
- **Fora de escopo nesta leva** (documentado, não implementado):
  `conta_transf_contabil` (plano de contas ano-a-ano — mesmo gap já
  registrado em Cliente, "qual ano_exercicio usar" não resolvido);
  "Gravar Como Cliente" (`CmdCopComo_Click` — clona o fornecedor pra
  `cliente`, tabelas não mencionadas pelo usuário nesta tarefa); "Alterar
  CPF/CNPJ" como fluxo dedicado (o campo já é editável no formulário
  normal, com checagem de duplicidade no save — cobre a mesma proteção
  central sem o modal InputBox do legado); autoload ao perder foco de um
  CPF/CNPJ já cadastrado (o legado carrega o registro existente
  automaticamente; aqui a duplicidade é bloqueada no save, mas sem
  autoload de conveniência — ver PENDENCIAS/memória se isso for pedido
  depois); o bloco `Frame7`/`GridF`/`Command7`/`Command8` ("converter
  Cliente em Fornecedor") parece código morto/inatingível no form colado
  (nenhum handler visível que o exibe) — não implementado.

Guards de exclusão (fiel ao legado, `PodeExcluirFornecedor`): bloqueia se
houver `pecas_fornecedor` (produto x fornecedor), `n_fiscal`/
`nf_recebimento` vinculados a um `tipo_mov` com `origem_destino='F'`
(movimentação real de compra), ou `pecas.fornecedor` (produto tendo esse
fornecedor como fabricante/fornecedor direto).

Regra de negócio real (`TipoEndereco`, `FrmmanForn.CmdOkEnd_Click`): no
máximo UM endereço tipo 0 (Residencial/Comercial, rótulo varia por CPF x
CNPJ) e UM tipo 1 (Comercial/Cobrança) por fornecedor — tipo 2 (Entrega)
não tem esse limite.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

TIPO_ENDERECO_UNICO = {0, 1}


def _row_to_dict(r: dict) -> dict:
    return {
        "codigo_int": int(r["codigo_int"]),
        "codigo": (r.get("codigo") or "").strip(),
        "nome": (r.get("nome") or "").strip(),
        "fantasia": (r.get("fantasia") or "").strip(),
        "inscr_est": (r.get("inscr_est") or "").strip(),
        "data": r["data"].isoformat() if r.get("data") else None,
        "tipo": (r.get("tipo") or "S").strip().upper(),
        "situacao": (r.get("situacao") or "A").strip(),
        "obs_forn": (r.get("obs_forn") or ""),
        "cliente_forn": r.get("cliente_forn"),
        "distribuidor": int(r["distribuidor"]) if r.get("distribuidor") else None,
        "shipper": int(r["shipper"]) if r.get("shipper") else None,
        "e_mail": (r.get("e_mail") or ""),
        "prazo_pgto": int(r.get("prazo_pgto") or 0),
        "desconto": float(r.get("desconto") or 0),
        "nossa_conta": (r.get("nossa_conta") or "").strip(),
        "dados_bancarios": (r.get("dados_bancarios") or ""),
        "conta_transf_caixa": int(r["conta_transf_caixa"]) if r.get("conta_transf_caixa") else None,
        "classe_caixa": int(r["classe_caixa"]) if r.get("classe_caixa") else None,
        "sub_classe_caixa": int(r["sub_classe_caixa"]) if r.get("sub_classe_caixa") else None,
    }


def _list_fornecedores_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where, params = "", ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE nome LIKE %s OR fantasia LIKE %s OR codigo LIKE %s"
            params = (like, like, like)
        cur.execute(
            f"SELECT codigo_int, codigo, nome, fantasia, situacao FROM fornecedor {where} ORDER BY nome",
            params,
        )
        items = [{
            "codigo_int": int(r["codigo_int"]),
            "codigo": (r.get("codigo") or "").strip(),
            "nome": (r.get("nome") or "").strip(),
            "fantasia": (r.get("fantasia") or "").strip(),
            "situacao": (r.get("situacao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _get_fornecedor_sync(servidor: str, banco: str, codigo_int: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo_int, codigo, nome, fantasia, inscr_est, data, tipo, situacao, obs_forn, "
            "cliente_forn, distribuidor, shipper, e_mail, prazo_pgto, desconto, nossa_conta, "
            "dados_bancarios, conta_transf_caixa, classe_caixa, sub_classe_caixa "
            "FROM fornecedor WHERE codigo_int=%s",
            (codigo_int,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Fornecedor não encontrado."}
        item = _row_to_dict(row)

        cur.execute(
            "SELECT ddd, tel, descricao FROM fornecedor_tel WHERE codigo=%s ORDER BY SEQUENCIA_FORNECEDOR_TEL",
            (codigo_int,),
        )
        item["telefones"] = [{
            "ddd": (r.get("ddd") or "").strip(), "tel": (r.get("tel") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]

        cur.execute(
            "SELECT endereco, numero, complemento, bairro, cidade, uf, cep, pais, tipo_endereco "
            "FROM fornecedor_end WHERE codigo=%s ORDER BY SEQUENCIA_FORNECEDOR_END",
            (codigo_int,),
        )
        item["enderecos"] = [{
            "endereco": (r.get("endereco") or "").strip(), "numero": int(r.get("numero") or 0),
            "complemento": (r.get("complemento") or "").strip(), "bairro": (r.get("bairro") or "").strip(),
            "cidade": (r.get("cidade") or "").strip(), "uf": (r.get("uf") or "").strip(),
            "cep": (r.get("cep") or "").strip(), "pais": (r.get("pais") or "").strip(),
            "tipo": int(r.get("tipo_endereco") or 0),
        } for r in cur.fetchall()]

        cur.execute(
            "SELECT contato, setor, cargo, ddd, telefone, ddd_fax, fax, ddd_celular, celular, e_mail, sexo "
            "FROM fornecedor_contato WHERE codigo=%s ORDER BY SEQUENCIA_FORNECEDOR_CONTATO",
            (codigo_int,),
        )
        item["contatos"] = [{
            "contato": (r.get("contato") or "").strip(), "setor": (r.get("setor") or "").strip(),
            "cargo": (r.get("cargo") or "").strip(), "ddd": r.get("ddd") or 0,
            "telefone": (r.get("telefone") or "").strip(), "ddd_fax": r.get("ddd_fax") or 0,
            "fax": (r.get("fax") or "").strip(), "ddd_celular": r.get("ddd_celular") or 0,
            "celular": (r.get("celular") or "").strip(), "e_mail": (r.get("e_mail") or "").strip(),
            "sexo": (r.get("sexo") or "").strip(),
        } for r in cur.fetchall()]

        cur.close()
        return {"success": True, "item": item}
    finally:
        conn.close()


def _resolver_fornecedor_ref_sync(cur, texto: str) -> Optional[int]:
    """Resolve Distribuidor/Transportador por fantasia -> nome -> codigo
    (mesma prioridade do legado, Campo_LostFocus Index 20/14)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for coluna in ("fantasia", "nome", "codigo"):
        cur.execute(f"SELECT codigo_int FROM fornecedor WHERE {coluna}=%s", (texto,))
        row = cur.fetchone()
        if row:
            return int(row["codigo_int"])
    return None


def _save_fornecedor_sync(servidor: str, banco: str, codigo_int: Optional[int], dados: dict) -> dict:
    codigo = (dados.get("codigo") or "").strip()
    if not codigo:
        return {"success": False, "message": "Informe o CPF/CGC."}
    if len(codigo) not in (11, 14):
        return {"success": False, "message": "CPF (11) ou CNPJ (14) inválido."}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return {"success": False, "message": "Informe o Nome/Razão Social."}
    if not (dados.get("situacao") or "").strip():
        return {"success": False, "message": "Informe a Situação."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT codigo FROM situacao WHERE codigo=%s", (dados["situacao"].strip().upper(),))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Situação inválida."}

        cur.execute(
            "SELECT codigo_int FROM fornecedor WHERE codigo=%s" + (" AND codigo_int<>%s" if codigo_int else ""),
            (codigo, codigo_int) if codigo_int else (codigo,),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Já existe um fornecedor cadastrado com esse CPF/CNPJ."}

        distribuidor = _resolver_fornecedor_ref_sync(cur, dados.get("_distribuidor_texto") or "")
        shipper = _resolver_fornecedor_ref_sync(cur, dados.get("_shipper_texto") or "")

        campos = {
            "codigo": codigo, "nome": nome, "fantasia": (dados.get("fantasia") or "").strip(),
            "inscr_est": (dados.get("inscr_est") or "").strip(), "data": dados.get("data") or None,
            "tipo": (dados.get("tipo") or "S").strip().upper()[:1],
            "situacao": dados["situacao"].strip().upper(),
            "obs_forn": dados.get("obs_forn") or "",
            "cliente_forn": dados.get("cliente_forn"),
            "distribuidor": distribuidor or 0, "shipper": shipper or 0,
            "e_mail": dados.get("e_mail") or "", "prazo_pgto": int(dados.get("prazo_pgto") or 0),
            "desconto": float(dados.get("desconto") or 0), "nossa_conta": (dados.get("nossa_conta") or "").strip(),
            "dados_bancarios": dados.get("dados_bancarios") or "",
            "conta_transf_caixa": dados.get("conta_transf_caixa") or 0,
            "classe_caixa": dados.get("classe_caixa") or 0,
            "sub_classe_caixa": dados.get("sub_classe_caixa") or 0,
        }

        if codigo_int:
            set_clause = ", ".join(f"{c}=%s" for c in campos)
            cur.execute(f"UPDATE fornecedor SET {set_clause} WHERE codigo_int=%s", (*campos.values(), codigo_int))
        else:
            cols = list(campos.keys())
            placeholders = ",".join(["%s"] * len(cols))
            cur.execute(
                f"INSERT INTO fornecedor ({','.join(cols)}) VALUES ({placeholders})",
                tuple(campos.values()),
            )
            conn.commit()
            cur.execute("SELECT @@IDENTITY AS codigo_int")
            codigo_int = int(cur.fetchone()["codigo_int"])

        # Telefones — replace-all
        cur.execute("DELETE FROM fornecedor_tel WHERE codigo=%s", (codigo_int,))
        for t in dados.get("telefones") or []:
            if not (t.get("tel") or "").strip():
                continue
            cur.execute(
                "INSERT INTO fornecedor_tel (codigo, ddd, tel, descricao) VALUES (%s,%s,%s,%s)",
                (codigo_int, (t.get("ddd") or "").strip(), (t.get("tel") or "").strip(), (t.get("descricao") or "").strip()),
            )

        # Endereços — replace-all, com guard de tipo único (0 e 1)
        enderecos = [e for e in (dados.get("enderecos") or []) if (e.get("endereco") or "").strip()]
        vistos_unicos = set()
        for e in enderecos:
            tipo_e = int(e.get("tipo") or 0)
            if tipo_e in TIPO_ENDERECO_UNICO:
                if tipo_e in vistos_unicos:
                    cur.close()
                    return {"success": False, "message": "Só é permitido um endereço desse tipo por fornecedor."}
                vistos_unicos.add(tipo_e)
        cur.execute("DELETE FROM fornecedor_end WHERE codigo=%s", (codigo_int,))
        for e in enderecos:
            cur.execute(
                "INSERT INTO fornecedor_end (codigo, endereco, numero, complemento, bairro, cidade, uf, cep, pais, tipo_endereco) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo_int, e["endereco"].strip(), int(e.get("numero") or 0), (e.get("complemento") or "").strip(),
                    (e.get("bairro") or "").strip(), (e.get("cidade") or "").strip(), (e.get("uf") or "").strip(),
                    (e.get("cep") or "").strip(), (e.get("pais") or "").strip(), int(e.get("tipo") or 0),
                ),
            )

        # Contatos — replace-all
        cur.execute("DELETE FROM fornecedor_contato WHERE codigo=%s", (codigo_int,))
        for c in dados.get("contatos") or []:
            if not (c.get("contato") or "").strip():
                continue
            cur.execute(
                "INSERT INTO fornecedor_contato (codigo, contato, setor, cargo, ddd, telefone, ddd_fax, fax, ddd_celular, celular, e_mail, sexo) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo_int, c["contato"].strip(), (c.get("setor") or "").strip(), (c.get("cargo") or "").strip(),
                    int(c.get("ddd") or 0), (c.get("telefone") or "").strip(), int(c.get("ddd_fax") or 0),
                    (c.get("fax") or "").strip(), int(c.get("ddd_celular") or 0), (c.get("celular") or "").strip(),
                    (c.get("e_mail") or "").strip(), (c.get("sexo") or "").strip() or "M",
                ),
            )

        conn.commit()
        cur.close()
        return {"success": True, "message": "Fornecedor gravado.", "codigo_int": codigo_int}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _find_by_codigo_sync(servidor: str, banco: str, codigo: str) -> dict:
    """Busca fornecedor por CPF/CGC (alfanumérico, sem máscara) — mesmo
    padrão de `clientes_service._find_by_cgc_sync`, usada pro autoload no
    blur do campo CPF/CNPJ (regra global do usuário, 2026-07-10)."""
    raw = (codigo or "").strip().upper()
    if not raw:
        return {"success": False, "message": "CPF/CGC vazio."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 codigo_int, nome FROM fornecedor WHERE codigo=%s", (raw,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": True, "found": False}
        return {"success": True, "found": True, "codigo_int": int(row["codigo_int"]), "nome": (row.get("nome") or "").strip()}
    finally:
        conn.close()


def _gravar_como_cliente_sync(servidor: str, banco: str, codigo_int: int) -> dict:
    """"Gravar Como Cliente" — legado `FrmmanForn.CmdCopComo_Click`: clona o
    fornecedor pra `cliente` (upsert por `cgc_cpf`), copiando telefones e
    endereços. Melhoria em relação ao legado: copia TODOS os endereços
    (o legado original só copiava o primeiro — `Linha = 1` fixo, sem loop,
    ao contrário do loop usado pros telefones logo acima no mesmo handler;
    parece um descuido do legado, não uma regra de negócio intencional)."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, nome, fantasia, inscr_est, situacao FROM fornecedor WHERE codigo_int=%s",
            (codigo_int,),
        )
        forn = cur.fetchone()
        if not forn:
            cur.close()
            return {"success": False, "message": "Fornecedor não encontrado."}
        cgc = (forn.get("codigo") or "").strip()
        nome = (forn.get("nome") or "").strip()
        if not cgc or not nome:
            cur.close()
            return {"success": False, "message": "Fornecedor sem CPF/CGC ou Nome definidos — grave o fornecedor primeiro."}
        fantasia = (forn.get("fantasia") or "").strip() or None
        inscr_est = (forn.get("inscr_est") or "").strip() or None
        situacao = (forn.get("situacao") or "A").strip() or "A"

        cur.execute("SELECT codigo FROM cliente WHERE cgc_cpf=%s", (cgc,))
        existe = cur.fetchone()
        if existe:
            cliente_codigo = int(existe["codigo"])
            cur.execute(
                "UPDATE cliente SET nome=%s, fantasia=%s, inscr_est=%s, situacao=%s WHERE codigo=%s",
                (nome, fantasia, inscr_est, situacao, cliente_codigo),
            )
        else:
            cur.execute(
                "INSERT INTO cliente (cgc_cpf, nome, fantasia, inscr_est, situacao, data) "
                "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s, CAST(GETDATE() AS DATE))",
                (cgc, nome, fantasia, inscr_est, situacao),
            )
            cliente_codigo = int(cur.fetchone()["codigo"])

        cur.execute("DELETE FROM cliente_tel WHERE codigo=%s", (cliente_codigo,))
        cur.execute("SELECT ddd, tel, descricao FROM fornecedor_tel WHERE codigo=%s", (codigo_int,))
        for t in cur.fetchall():
            if not (t.get("tel") or "").strip():
                continue
            cur.execute(
                "INSERT INTO cliente_tel (codigo, ddd, tel, descricao) VALUES (%s,%s,%s,%s)",
                (cliente_codigo, (t.get("ddd") or "").strip() or "21", (t.get("tel") or "").strip(), (t.get("descricao") or "").strip() or None),
            )

        cur.execute("DELETE FROM cliente_end WHERE codigo=%s", (cliente_codigo,))
        cur.execute(
            "SELECT tipo_endereco, endereco, numero, complemento, bairro, cidade, uf, cep FROM fornecedor_end WHERE codigo=%s",
            (codigo_int,),
        )
        for e in cur.fetchall():
            if not (e.get("endereco") or "").strip():
                continue
            cur.execute(
                "INSERT INTO cliente_end (codigo, tipo, endereco, numero, complemento, bairro, cidade, uf, cep) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    cliente_codigo, int(e.get("tipo_endereco") or 0), (e.get("endereco") or "").strip(),
                    e.get("numero"), (e.get("complemento") or "").strip() or None, (e.get("bairro") or "").strip() or None,
                    (e.get("cidade") or "").strip() or None, (e.get("uf") or "").strip() or None, (e.get("cep") or "").strip() or None,
                ),
            )

        conn.commit()
        cur.close()
        return {"success": True, "message": "Fornecedor gravado como cliente.", "cliente_codigo": cliente_codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar como cliente: {e}"}
    finally:
        conn.close()


def _delete_fornecedor_sync(servidor: str, banco: str, codigo_int: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT TOP 1 1 AS ok FROM pecas_fornecedor WHERE fornecedor=%s", (codigo_int,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Fornecedor com produtos associados — exclusão não permitida."}

        cur.execute(
            "SELECT TOP 1 1 AS ok FROM n_fiscal, tipo_mov WHERE n_fiscal.mov = tipo_mov.codigo "
            "AND tipo_mov.origem_destino='F' AND n_fiscal.fornecedor=%s",
            (codigo_int,),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Fornecedor com notas fiscais vinculadas — exclusão não permitida."}

        cur.execute(
            "SELECT TOP 1 1 AS ok FROM nf_recebimento, tipo_mov WHERE nf_recebimento.mov = tipo_mov.codigo "
            "AND tipo_mov.origem_destino='F' AND nf_recebimento.fornecedor=%s",
            (codigo_int,),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Fornecedor com recebimentos de NF vinculados — exclusão não permitida."}

        cur.execute("SELECT TOP 1 1 AS ok FROM pecas WHERE fornecedor=%s", (codigo_int,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Fornecedor é fabricante/fornecedor direto de produtos — exclusão não permitida."}

        cur.execute("DELETE FROM fornecedor WHERE codigo_int=%s", (codigo_int,))
        cur.execute("DELETE FROM fornecedor_tel WHERE codigo=%s", (codigo_int,))
        cur.execute("DELETE FROM fornecedor_end WHERE codigo=%s", (codigo_int,))
        cur.execute("DELETE FROM fornecedor_contato WHERE codigo=%s", (codigo_int,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Fornecedor excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_fornecedores(servidor: str, banco: str, search: str = "") -> dict:
    return await asyncio.to_thread(_list_fornecedores_sync, servidor, banco, search)


async def get_fornecedor(servidor: str, banco: str, codigo_int: int) -> dict:
    return await asyncio.to_thread(_get_fornecedor_sync, servidor, banco, codigo_int)


async def save_fornecedor(servidor: str, banco: str, codigo_int: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_fornecedor_sync, servidor, banco, codigo_int, dados)


async def delete_fornecedor(servidor: str, banco: str, codigo_int: int) -> dict:
    return await asyncio.to_thread(_delete_fornecedor_sync, servidor, banco, codigo_int)


async def find_by_codigo(servidor: str, banco: str, codigo: str) -> dict:
    return await asyncio.to_thread(_find_by_codigo_sync, servidor, banco, codigo)


async def gravar_como_cliente(servidor: str, banco: str, codigo_int: int) -> dict:
    return await asyncio.to_thread(_gravar_como_cliente_sync, servidor, banco, codigo_int)

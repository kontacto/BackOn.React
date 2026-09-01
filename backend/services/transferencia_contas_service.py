"""Financeiro > Transferência p/Contas Pagar/Receber (`Geral\\FrmTransfContas.frm`,
caption real "Transferência para o Contas a Pagar / Receber...").

Rastreado via agente de pesquisa (achado documentado em PENDENCIAS.md >
"Transferência Contas a Pagar/Receber" — não é uma tela de mover saldo
entre Contas de caixa/banco, isso é `FrmTransfCaixa.frm`, tela IRMÃ e
DIFERENTE no mesmo menu Financeiro, fora do escopo desta implementação).

**O que esta tela realmente faz**: promove Notas Fiscais já emitidas
(`N_fiscal`, `pagar='S'` e `situacao='A'` — ainda não lançadas no
livro-razão formal) e Comandas do Bar já pagas (`situacao='PG'`, ainda não
transferidas) pro Contas a Pagar/Receber de verdade. Nota de Saída
(`LEFT(mov,1)='S'`) vira Contas a Receber; Nota de Entrada (`'E'`) vira
Contas a Pagar. Sem digitação manual nenhuma — o usuário só marca as
linhas e confirma.

**Tabelas de destino** (as 2 famílias, confirmadas ao vivo contra ARGEN
TESTE — todas as colunas abaixo existem de verdade, checadas via
`INFORMATION_SCHEMA.COLUMNS` antes de escrever este arquivo):
- Receita: `Receber` → `receber_custo` (rateio por centro de custo) →
  `Duplicata_Receber` → `Duplicata_Rec_Venc` (1 por vencimento) →
  `Duplicata_Rec_Nf` (liga duplicata↔nota). Mesma família já usada pelo
  módulo de Boletos/CNAB (`bancos_service.py`/`cnab_*_service.py`).
- Pagar: `Pagar` → `pagar_custo` → `Duplicata_Pagar` → `Duplicata_Pag_Venc`
  → `Duplicata_Pag_Nf` — família espelhada, **nunca tocada nesta migração
  antes desta tela**. Não é simétrica em tudo (`Duplicata_Pagar.duplicata`
  é `float`, `Duplicata_Receber.duplicata` é `int`; `Duplicata_Pag_Venc`
  não tem `multa_atraso`/`registrado`/`impresso`/`transf_banco` que
  `Duplicata_Rec_Venc` tem, mas tem `banco_pag`/`agencia_pag`/`chegou_dup`
  que o lado Receber não tem) — respeitado tal como o schema real é, sem
  inventar simetria que não existe.

**Bug real corrigido em 2026-08-28** (achado ao especificar a tela "Contas
a Receber" em cima desta tabela): `Duplicata_Rec_Nf.nf_fiscal`/
`Duplicata_Pag_Nf.nf_fiscal` — apesar do nome da coluna — armazenam o
`codigo` do registro em `Receber`/`Pagar`, **não** o `codigo` de `N_fiscal`
(confirmado contra 2 fontes legadas independentes: o JOIN de
`Geral/FRMCONNFREC.frm` faz `duplicata_rec_nf.nf_fiscal = Receber.Codigo`,
e o `INSERT` de `Revenda/FrmManDur.frm`'s `Command2_Click`/`frmTraNFRec.
frm`'s `Command7_Click` grava `Campo(0)` = `Receber.Codigo` nessa coluna).
`_nf_recebe_sync`/`_nf_paga_sync` gravavam `codigo_nota` (o `N_fiscal.
codigo` de origem) em vez de `receber_codigo`/`pagar_codigo` — qualquer
consulta que tentasse resolver "qual NF está ligada a esta duplicata"
juntando de volta com `Receber`/`Pagar` batia com o registro errado (ou
nenhum). Corrigido para gravar `receber_codigo`/`pagar_codigo`.

**Regras condicionais replicadas por completo** (decisão do usuário via
`AskUserQuestion`, 2026-08-27 — "Replicar as 2 regras por completo"):
- `controle.agrupa_nf_receber` (bit): quando ligado, várias notas do MESMO
  cliente/fornecedor com uma `Duplicata_Receber`/`Duplicata_Pagar` ainda
  ABERTA (`situacao='A'`) somam no MESMO registro em vez de criar um novo
  por nota.
- `controle.geranumerodup` (bit) + `controle.numero_dup` (int) +
  `controle.desmembramento_dup` (nvarchar): quando ligado, o número da
  duplicata é sequenciado a partir de `controle.numero_dup` (incrementado
  a cada uso) em vez de usar o próprio número da nota fiscal.

**Notas ligadas a Comanda** (decisão do usuário — "Incluir agora"):
`comanda_nf` liga uma Nota Fiscal a uma Comanda de origem
(`comanda, nota_fisc, tipo, situacao, sequencia`). Se a nota estiver
ligada a uma Comanda que JÁ foi transferida por outro caminho
(`comanda.transf_caixa` preenchido), bloqueia com a mensagem real do
legado — replica a trava de segurança, que é o achado central e
verificável do rastreio. **Simplificação consciente, registrada em
PENDENCIAS.md**: o split/merge fino de uma nota ligada a uma Comanda
PARCIALMENTE transferida (`Verifica_CM_Contas`/`Dados_CM_Contas` em
`Mod_Pagar.bas`) não foi replicado — o agente de pesquisa não trouxe o
SQL exato desse ramo, só a descrição de que ele existe; implementar isso
sem o SQL real violaria a regra do projeto de nunca supor. O caminho
comum (Comanda paga → ainda não lançada) está implementado por completo.

**Duplicidade bloqueada** — mesmo critério do legado: já existe
`Receber`/`Pagar` para essa combinação cliente/fornecedor+nota+série?
Bloqueia com a mesma mensagem, não deixa duplicar.
"""
import asyncio
import logging
from typing import Optional

from db.connection import _open_conn

logger = logging.getLogger(__name__)


# =============================================================================
# Helpers de leitura
# =============================================================================

def _controle_flags_sync(cur) -> dict:
    cur.execute(
        "SELECT TOP 1 agrupa_nf_receber, geranumerodup, numero_dup, desmembramento_dup, fantasia "
        "FROM controle"
    )
    r = cur.fetchone() or {}
    return {
        "agrupa_nf_receber": bool(r.get("agrupa_nf_receber")),
        "geranumerodup": bool(r.get("geranumerodup")),
        "numero_dup": r.get("numero_dup"),
        "desmembramento_dup": (r.get("desmembramento_dup") or "").strip(),
    }


def _listar_pendentes_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        # Réplica literal da consulta 3-em-1 de `FrmTransfContas.frm::Preenche`
        # — Nota de Saída (pagar='S', situacao='A', mov começa com 'S') vira
        # Contas a Receber; Comanda paga ainda não transferida vira "Comanda";
        # Nota de Entrada ('E') vira Contas a Pagar. `origem_destino='C'`
        # decide se o nome exibido vem de `cliente` ou `fornecedor` — mesma
        # coluna `N_fiscal.fornecedor` é reaproveitada pros dois papéis
        # (FK dupla de propósito no legado, não erro de digitação aqui).
        #
        # **Divergência deliberada do legado, pedido explícito do usuário
        # (2026-08-28)**: o `.frm` original NUNCA excluía da listagem uma
        # Nota de Saída cuja comanda vinculada já tinha sido baixada no
        # Contas a Receber por outro caminho (`comanda.transf_caixa`) — a
        # nota aparecia como "pendente" e SEMPRE falhava ao transferir
        # (`_bloqueio_comanda_ja_transferida` abaixo, mesmo bloqueio já
        # existente no legado). Confirmado como réplica fiel, mas o usuário
        # decidiu conscientemente MELHORAR isso aqui: "se está baixada não
        # pode listar" — o `NOT EXISTS` abaixo tira essas notas da
        # listagem desde o início, em vez de deixar o usuário descobrir o
        # bloqueio só depois de marcar e clicar Transferir.
        cur.execute(
            """
            SELECT (SELECT TOP 1 nfv.data_venc FROM nf_vencimento nfv WHERE nfv.codigo = nf.codigo) AS vencimento,
                   nf.codigo AS codnota, 'Contas a Receber' AS flag, nf.valor_total AS valor_total,
                   nf.num_nf AS num_nf, nf.serie_nf AS serie_nf, nf.data_mov AS data_mov,
                   tm.descricao AS tipo_mov_descricao, tm.codigo AS tipo_mov_codigo,
                   CASE WHEN tm.origem_destino = 'C' THEN (SELECT nome FROM cliente WHERE codigo = nf.fornecedor)
                        ELSE (SELECT nome FROM fornecedor WHERE codigo_int = nf.fornecedor) END AS cliforn
            FROM N_fiscal nf JOIN tipo_mov tm ON nf.mov = tm.codigo
            WHERE nf.pagar = 'S' AND LEFT(nf.mov, 1) = 'S' AND nf.situacao = 'A'
              AND NOT EXISTS (
                  SELECT 1 FROM comanda_nf cn JOIN comanda c ON c.comanda = cn.comanda
                  WHERE cn.nota_fisc = nf.codigo AND ISNULL(c.transf_caixa, '') <> ''
              )

            UNION ALL

            SELECT CAST(NULL AS date) AS vencimento, c.comanda AS codnota, 'Comanda' AS flag,
                   c.valor_venda AS valor_total, c.comanda AS num_nf, 'CM' AS serie_nf, c.data AS data_mov,
                   'S01 VENDA' AS tipo_mov_descricao, 'S01' AS tipo_mov_codigo,
                   (SELECT nome FROM cliente WHERE codigo = c.cliente) AS cliforn
            FROM comanda c
            WHERE (ISNULL(c.transf_caixa, '') = '') AND c.situacao = 'PG'

            UNION ALL

            SELECT (SELECT TOP 1 nfv.data_venc FROM nf_vencimento nfv WHERE nfv.codigo = nf.codigo) AS vencimento,
                   nf.codigo AS codnota, 'Contas a Pagar' AS flag, nf.valor_total AS valor_total,
                   nf.num_nf AS num_nf, nf.serie_nf AS serie_nf, nf.data_mov AS data_mov,
                   tm.descricao AS tipo_mov_descricao, tm.codigo AS tipo_mov_codigo,
                   CASE WHEN tm.origem_destino = 'C' THEN (SELECT nome FROM cliente WHERE codigo = nf.fornecedor)
                        ELSE (SELECT nome FROM fornecedor WHERE codigo_int = nf.fornecedor) END AS cliforn
            FROM N_fiscal nf JOIN tipo_mov tm ON nf.mov = tm.codigo
            WHERE nf.pagar = 'S' AND LEFT(nf.mov, 1) = 'E' AND nf.situacao = 'A'

            ORDER BY data_mov, num_nf
            """
        )
        items = []
        for r in cur.fetchall():
            items.append({
                "codnota": int(r["codnota"]),
                "flag": r["flag"],
                "valor_total": float(r.get("valor_total") or 0),
                "num_nf": int(r["num_nf"]) if r.get("num_nf") is not None else None,
                "serie_nf": (r.get("serie_nf") or "").strip(),
                "data_mov": r["data_mov"].isoformat() if r.get("data_mov") else None,
                "vencimento": r["vencimento"].isoformat() if r.get("vencimento") else None,
                "tipo_mov_descricao": (r.get("tipo_mov_descricao") or "").strip(),
                "tipo_mov_codigo": (r.get("tipo_mov_codigo") or "").strip(),
                "cliforn": (r.get("cliforn") or "").strip(),
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


async def listar_pendentes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_listar_pendentes_sync, servidor, banco)


# =============================================================================
# Trava de Nota ligada a Comanda já transferida por outro caminho — réplica
# da mensagem real do legado (`Mod_Pagar.bas`).
# =============================================================================

def _bloqueio_comanda_ja_transferida(cur, codigo_nota: int) -> Optional[str]:
    cur.execute(
        "SELECT cn.comanda, c.transf_caixa FROM comanda_nf cn "
        "JOIN comanda c ON c.comanda = cn.comanda WHERE cn.nota_fisc = %s",
        (codigo_nota,),
    )
    row = cur.fetchone()
    if row and (row.get("transf_caixa") or "").strip():
        return (
            "Esta comanda já está baixada no Contas a Receber! Cancelar o "
            "recebimento da comanda e executar novamente a transferência!"
        )
    return None


def _rateio_custo_sync(cur, codigo_nota: int) -> list[dict]:
    cur.execute(
        "SELECT custo, valor_contabil, nf_classe, nf_sub_classe FROM n_fiscal_custo WHERE n_fiscal = %s",
        (codigo_nota,),
    )
    return cur.fetchall() or []


def _resolver_numero_duplicata_sync(cur, flags: dict, num_nf: int) -> tuple:
    """Retorna (duplicata, desmembramento) — `geranumerodup` sequencia a
    partir de `controle.numero_dup` (e incrementa), senão usa o próprio
    número da nota fiscal. `desmembramento_dup` (config) tem prioridade
    sobre a série da nota quando preenchido."""
    if flags["geranumerodup"]:
        numero = int(flags["numero_dup"] or 1)
        cur.execute("UPDATE controle SET numero_dup = %s", (numero + 1,))
        return numero, flags["desmembramento_dup"]
    return num_nf, flags["desmembramento_dup"]


# =============================================================================
# Contas a Receber — réplica de `NF_RECEBE` (Mod_Pagar.bas)
# =============================================================================

def _nf_recebe_sync(cur, codigo_nota: int, flags: dict) -> dict:
    cur.execute("SELECT * FROM N_fiscal WHERE codigo = %s", (codigo_nota,))
    nf = cur.fetchone()
    if not nf:
        return {"success": False, "message": f"Nota Fiscal {codigo_nota} não encontrada."}
    if (nf.get("pagar") or "").strip() == "T":
        return {"success": False, "message": f"Nota Fiscal {codigo_nota} já foi transferida."}

    fornecedor = nf.get("fornecedor")
    num_nf = int(nf["num_nf"]) if nf.get("num_nf") is not None else None
    serie_nf = (nf.get("serie_nf") or "").strip()

    cur.execute(
        "SELECT codigo FROM Receber WHERE cliente = %s AND nota_fiscal = %s AND ISNULL(serie,'') = %s",
        (fornecedor, num_nf, serie_nf),
    )
    if cur.fetchone():
        return {"success": False, "message": (
            f"Não foi possível transferir a Nota Fiscal {num_nf} pois já existe tal "
            "Nota Fiscal em Contas a Receber."
        )}

    bloqueio = _bloqueio_comanda_ja_transferida(cur, codigo_nota)
    if bloqueio:
        return {"success": False, "message": bloqueio}

    cur.execute(
        "INSERT INTO Receber (cliente, nota_fiscal, serie, dt_emissao, dt_entrada, valor, "
        "tipo_mov, cod_n_fiscal, valor_contabilizado, situacao) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'DU')",
        (fornecedor, num_nf, serie_nf, nf.get("data_nf"), nf.get("data_mov"),
         nf.get("valor_total"), nf.get("mov"), codigo_nota, nf.get("valor_total")),
    )
    receber_codigo = cur.fetchone()["codigo"]

    for c in _rateio_custo_sync(cur, codigo_nota):
        cur.execute(
            "INSERT INTO receber_custo (nota, custo, valor, rc_classe, rc_sub_classe) VALUES (%s,%s,%s,%s,%s)",
            (receber_codigo, c.get("custo"), c.get("valor_contabil"), c.get("nf_classe"), c.get("nf_sub_classe")),
        )

    dup_codigo = None
    if flags["agrupa_nf_receber"]:
        cur.execute(
            "SELECT TOP 1 codigo FROM Duplicata_Receber WHERE cliente = %s AND situacao = 'A' ORDER BY codigo DESC",
            (fornecedor,),
        )
        existente = cur.fetchone()
        if existente:
            dup_codigo = existente["codigo"]
            cur.execute("UPDATE Duplicata_Receber SET valor = valor + %s WHERE codigo = %s",
                        (nf.get("valor_total"), dup_codigo))

    cur.execute(
        "SELECT data_venc, valor FROM nf_vencimento WHERE codigo = %s ORDER BY data_venc",
        (codigo_nota,),
    )
    vencimentos = cur.fetchall() or [{"data_venc": nf.get("data_mov"), "valor": nf.get("valor_total")}]

    if dup_codigo is None:
        duplicata, desmembramento = _resolver_numero_duplicata_sync(cur, flags, num_nf)
        cur.execute(
            "INSERT INTO Duplicata_Receber (cliente, duplicata, desmembramento, dt_emissao, "
            "num_parcelas, parcelas_pagas, valor, situacao) "
            "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,0,%s,'A')",
            (fornecedor, duplicata, desmembramento or serie_nf, nf.get("data_nf"),
             len(vencimentos), nf.get("valor_total")),
        )
        dup_codigo = cur.fetchone()["codigo"]

    for i, venc in enumerate(vencimentos, start=1):
        cur.execute(
            "INSERT INTO Duplicata_Rec_Venc (duplicata, desmembramento, dt_vencimento, valor, situacao) "
            "VALUES (%s,%s,%s,%s,'A')",
            (dup_codigo, i, venc.get("data_venc"), venc.get("valor")),
        )

    cur.execute("INSERT INTO Duplicata_Rec_Nf (duplicata, nf_fiscal) VALUES (%s,%s)", (dup_codigo, receber_codigo))
    cur.execute("UPDATE N_fiscal SET pagar = 'T' WHERE codigo = %s", (codigo_nota,))
    return {"success": True}


# =============================================================================
# Contas a Pagar — réplica de `Nf_PAGA` (Mod_Pagar.bas), família de tabelas
# espelhada (Pagar/Duplicata_Pagar/Duplicata_Pag_Venc/Duplicata_Pag_Nf)
# =============================================================================

def _nf_paga_sync(cur, codigo_nota: int, flags: dict) -> dict:
    cur.execute("SELECT * FROM N_fiscal WHERE codigo = %s", (codigo_nota,))
    nf = cur.fetchone()
    if not nf:
        return {"success": False, "message": f"Nota Fiscal {codigo_nota} não encontrada."}
    if (nf.get("pagar") or "").strip() == "T":
        return {"success": False, "message": f"Nota Fiscal {codigo_nota} já foi transferida."}

    fornecedor = nf.get("fornecedor")
    num_nf = int(nf["num_nf"]) if nf.get("num_nf") is not None else None
    serie_nf = (nf.get("serie_nf") or "").strip()

    cur.execute(
        "SELECT codigo FROM Pagar WHERE fornecedor = %s AND nota_fiscal = %s AND ISNULL(serie,'') = %s",
        (fornecedor, num_nf, serie_nf),
    )
    if cur.fetchone():
        return {"success": False, "message": (
            f"Não foi possível transferir a Nota Fiscal {num_nf} pois já existe tal "
            "Nota Fiscal em Contas a Pagar."
        )}

    cur.execute(
        "INSERT INTO Pagar (fornecedor, nota_fiscal, serie, dt_emissao, dt_entrada, valor, "
        "tipo_mov, cod_n_fiscal, valor_contabilizado, situacao) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'DU')",
        (fornecedor, num_nf, serie_nf, nf.get("data_nf"), nf.get("data_mov"),
         nf.get("valor_total"), nf.get("mov"), codigo_nota, nf.get("valor_total")),
    )
    pagar_codigo = cur.fetchone()["codigo"]

    for c in _rateio_custo_sync(cur, codigo_nota):
        cur.execute(
            "INSERT INTO pagar_custo (nota, custo, valor, pc_classe, pc_sub_classe) VALUES (%s,%s,%s,%s,%s)",
            (pagar_codigo, c.get("custo"), c.get("valor_contabil"), c.get("nf_classe"), c.get("nf_sub_classe")),
        )

    # `Duplicata_Pagar` não tem coluna de agrupamento própria documentada no
    # rastreio (Nf_PAGA não menciona um branch de "já existe duplicata
    # aberta pra este fornecedor") — o agrupamento (`agrupa_nf_receber`) é
    # uma regra do lado RECEBER especificamente; aplicado só lá, não aqui.
    duplicata, desmembramento = _resolver_numero_duplicata_sync(cur, flags, num_nf)
    cur.execute(
        "INSERT INTO Duplicata_Pagar (fornecedor, duplicata, desmembramento, dt_emissao, "
        "num_parcelas, parcelas_pagas, valor, situacao) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,0,%s,'A')",
        (fornecedor, duplicata, desmembramento or serie_nf, nf.get("data_nf"), 1, nf.get("valor_total")),
    )
    dup_codigo = cur.fetchone()["codigo"]

    cur.execute(
        "SELECT data_venc, valor FROM nf_vencimento WHERE codigo = %s ORDER BY data_venc",
        (codigo_nota,),
    )
    vencimentos = cur.fetchall() or [{"data_venc": nf.get("data_mov"), "valor": nf.get("valor_total")}]
    for i, venc in enumerate(vencimentos, start=1):
        cur.execute(
            "INSERT INTO Duplicata_Pag_Venc (duplicata, desmembramento, dt_vencimento, valor, situacao) "
            "VALUES (%s,%s,%s,%s,'A')",
            (dup_codigo, i, venc.get("data_venc"), venc.get("valor")),
        )

    cur.execute("INSERT INTO Duplicata_Pag_Nf (duplicata, nf_fiscal) VALUES (%s,%s)", (dup_codigo, pagar_codigo))
    cur.execute("UPDATE N_fiscal SET pagar = 'T' WHERE codigo = %s", (codigo_nota,))
    return {"success": True}


# =============================================================================
# Comanda paga → Contas a Receber — réplica simplificada de `transferecomanda`
# (caminho comum: comanda fechada/paga, ainda sem nota vinculada)
# =============================================================================

def _transferir_comanda_sync(cur, codigo_comanda: int, flags: dict) -> dict:
    cur.execute("SELECT * FROM comanda WHERE comanda = %s", (codigo_comanda,))
    c = cur.fetchone()
    if not c:
        return {"success": False, "message": f"Comanda {codigo_comanda} não encontrada."}
    if (c.get("transf_caixa") or "").strip():
        return {"success": False, "message": f"Comanda {codigo_comanda} já foi transferida."}
    if (c.get("situacao") or "").strip() != "PG":
        return {"success": False, "message": f"Comanda {codigo_comanda} não está paga."}

    cliente = c.get("cliente")
    valor = c.get("valor_venda")

    dup_codigo = None
    if flags["agrupa_nf_receber"] and cliente:
        cur.execute(
            "SELECT TOP 1 codigo FROM Duplicata_Receber WHERE cliente = %s AND situacao = 'A' ORDER BY codigo DESC",
            (cliente,),
        )
        existente = cur.fetchone()
        if existente:
            dup_codigo = existente["codigo"]
            cur.execute("UPDATE Duplicata_Receber SET valor = valor + %s WHERE codigo = %s", (valor, dup_codigo))

    if dup_codigo is None:
        duplicata, desmembramento = _resolver_numero_duplicata_sync(cur, flags, codigo_comanda)
        cur.execute(
            "INSERT INTO Duplicata_Receber (cliente, duplicata, desmembramento, dt_emissao, "
            "num_parcelas, parcelas_pagas, valor, situacao) "
            "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,1,0,%s,'A')",
            (cliente, duplicata, desmembramento or "CM", c.get("data")),
        )
        dup_codigo = cur.fetchone()["codigo"]

    cur.execute(
        "INSERT INTO Duplicata_Rec_Venc (duplicata, desmembramento, dt_vencimento, valor, situacao) "
        "VALUES (%s,1,%s,%s,'A')",
        (dup_codigo, c.get("data"), valor),
    )
    cur.execute("UPDATE comanda SET transf_caixa = 'S' WHERE comanda = %s", (codigo_comanda,))
    return {"success": True}


# =============================================================================
# Ponto de entrada — dispara vários itens numa transação só, isola falha por
# item (mesmo princípio de `ensure_all_schema`: 1 item ruim não derruba os
# outros que já eram válidos).
# =============================================================================

def _transferir_sync(servidor: str, banco: str, itens: list) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        flags = _controle_flags_sync(cur)
        sucesso, falhas = [], []
        for item in itens:
            codnota = int(item["codnota"])
            flag = item["flag"]
            try:
                if flag == "Contas a Receber":
                    resultado = _nf_recebe_sync(cur, codnota, flags)
                elif flag == "Contas a Pagar":
                    resultado = _nf_paga_sync(cur, codnota, flags)
                elif flag == "Comanda":
                    resultado = _transferir_comanda_sync(cur, codnota, flags)
                else:
                    resultado = {"success": False, "message": f"Tipo desconhecido: {flag}"}
            except Exception as e:
                # [GLOBAL] Mensagens de Erro — Linguagem Não-Técnica: nunca
                # despejar o texto cru da exceção (pode ser erro de driver/
                # SQL Server) pro usuário final — loga o real pro suporte
                # investigar, devolve uma frase genérica e acionável.
                logger.warning("transferencia_contas: falha ao transferir item %s (%s)", codnota, flag, exc_info=True)
                resultado = {
                    "success": False,
                    "message": f"Não foi possível transferir o item {codnota} — tente novamente ou avise o suporte se persistir.",
                }
            if resultado.get("success"):
                sucesso.append(codnota)
            else:
                falhas.append({"codnota": codnota, "flag": flag, "message": resultado.get("message")})

        conn.commit()
        cur.close()
        conn.close()
        # Log de auditoria fica a cargo da camada de rota (mesmo padrão já
        # estabelecido no resto do backend — ver routes/devolucao.py), não
        # deste service.
        return {"success": len(falhas) == 0, "transferidos": sucesso, "falhas": falhas}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def transferir(servidor: str, banco: str, itens: list) -> dict:
    return await asyncio.to_thread(_transferir_sync, servidor, banco, itens)

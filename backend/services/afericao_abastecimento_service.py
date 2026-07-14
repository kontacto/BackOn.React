"""Aferições/Despesas (Posto de Combustível) — tabela `abastecimento`.

Legado: `FrmBaiABc2.frm` ("Baixa de Abastecimentos..."). Revisa
abastecimentos pendentes (`status_abastecimento LIKE 'PENDEN%'`),
marcando-os como aferidos (opcionalmente lançados como despesa), e lista
os já aferidos com filtro por período.

**Achado importante — sem caminho de inclusão manual**: nem esta tela nem
nenhuma outra fornecida cria linhas em `abastecimento` — em produção elas
vêm do polling do concentrador Wayne Fusion (`AbastecimentosFusion`, ver
`Controller_HW_Concentradores_Wayne.vb`), fora de escopo desta fase (ver
PENDENCIAS.md). Esta tela funciona normalmente, só que a lista de
pendentes fica vazia até a automação de hardware existir (ou até algum
outro processo popular a tabela).

**Melhoria sobre o legado, não regra removida**: o join do legado pra
descobrir a descrição do combustível passa por `pecas.codigo_fab`
(tratando o combustível como produto, via uma string comparando
`LTRIM(RTRIM(pecas.codigo_fab)) = LTRIM(RTRIM(STR(bomba.combustivel)))`)
— aqui usamos `abastecimento.combustivel` direto (a própria coluna já
existe, `JOIN combustivel ON codigo`), mais simples e correto, sem
depender de uma correspondência textual frágil.

**Regra real replicada**: máximo de 10 abastecimentos por lote de
aferição (`Command10_Click`, `qtds > 10` bloqueia).

**Bug do legado corrigido, não replicado**: o `F3` (reverter aferição)
original só reseta `abastecimento` de volta pra `PENDENTE`, mas **nunca
desfaz o incremento em `mov_bomba.afericao`** que a aferição original
tinha feito — um lançamento revertido ficava com o valor de aferição
"fantasma" no turno. Aqui, reverter também decrementa `mov_bomba.afericao`
(e `valor_despesas`, se aplicável) pelo mesmo valor que foi somado.

Schema conferido ao vivo: `abastecimento` (num int IDENTITY, ponto,
posicao, combustivel smallint, valor/volume/preco_un real, encerrante/
encerrante_inicial float, data, hora, turno smallint, situacao smallint,
status_abastecimento nvarchar, valor_despesa float, data_afericao,
obs_afericao, hora_afericao nvarchar, usuario_afericao int).
"""
import asyncio
from datetime import date, datetime

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG

MAX_LOTE = 10


def _row_to_dict(r: dict) -> dict:
    return {
        "num": int(r["num"]),
        "ponto": int(r["ponto"]) if r.get("ponto") is not None else None,
        "posicao": int(r["posicao"]) if r.get("posicao") is not None else None,
        "combustivel": int(r["combustivel"]) if r.get("combustivel") is not None else None,
        "combustivel_descricao": (r.get("combustivel_descricao") or "").strip(),
        "valor": float(r.get("valor") or 0),
        "volume": float(r.get("volume") or 0),
        "preco_un": float(r.get("preco_un") or 0),
        "data": str(r["data"]) if r.get("data") else None,
        "hora": (r.get("hora") or "").strip(),
        "turno": int(r["turno"]) if r.get("turno") is not None else None,
        "valor_despesa": float(r.get("valor_despesa") or 0),
        "obs_afericao": (r.get("obs_afericao") or "").strip(),
    }


def _list_pendentes_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT a.num, a.ponto, a.posicao, a.combustivel, a.valor, a.volume, a.preco_un, "
            "a.data, a.hora, a.turno, c.descricao AS combustivel_descricao "
            "FROM abastecimento a LEFT JOIN combustivel c ON c.codigo = a.combustivel "
            "WHERE a.status_abastecimento LIKE 'PENDEN%' ORDER BY a.num DESC"
        )
        return {"success": True, "items": [_row_to_dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()


def _list_afericoes_sync(servidor: str, banco: str, data_ini: str, data_fim: str, incluir_afericoes: bool, incluir_despesas: bool) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        where = ["a.status_abastecimento='AFERIÇÃO'"]
        params: list = []
        if data_ini and data_fim:
            where.append("a.data BETWEEN %s AND %s")
            params += [data_ini, data_fim]
        if incluir_afericoes and not incluir_despesas:
            where.append("ISNULL(a.valor_despesa,0)=0")
        elif incluir_despesas and not incluir_afericoes:
            where.append("ISNULL(a.valor_despesa,0)>0")
        cur.execute(
            f"SELECT a.num, a.ponto, a.posicao, a.combustivel, a.valor, a.volume, a.preco_un, "
            f"a.data, a.hora, a.turno, a.valor_despesa, a.obs_afericao, c.descricao AS combustivel_descricao "
            f"FROM abastecimento a LEFT JOIN combustivel c ON c.codigo = a.combustivel "
            f"WHERE {' AND '.join(where)} ORDER BY a.num DESC",
            tuple(params),
        )
        items = [_row_to_dict(r) for r in cur.fetchall()]
        total = round(sum(i["valor"] for i in items), 2)
        return {"success": True, "items": items, "total": total}
    finally:
        conn.close()


def _aferir_sync(servidor: str, banco: str, nums: list, lancar_despesa: bool, motivo: str, usuario: int) -> dict:
    if not nums:
        return {"success": False, "message": "Nenhum abastecimento selecionado."}
    if len(nums) > MAX_LOTE:
        return {"success": False, "message": f"Só é permitido aferir no máximo {MAX_LOTE} abastecimentos por vez."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}

        hoje = date.today()
        hora = datetime.now().strftime("%H:%M:%S")
        afericoes_ok = 0
        for num in nums:
            cur.execute(
                "SELECT ponto, posicao, combustivel, valor, volume, data, turno, status_abastecimento "
                "FROM abastecimento WHERE num=%s",
                (num,),
            )
            row = cur.fetchone()
            if not row or (row.get("status_abastecimento") or "").upper() != "PENDENTE":
                continue
            valor = float(row.get("valor") or 0)
            volume = float(row.get("volume") or 0)
            despesa_incremento = valor if lancar_despesa else 0

            cur.execute(
                "UPDATE abastecimento SET status_abastecimento='AFERIÇÃO', data_afericao=%s, hora_afericao=%s, "
                "usuario_afericao=%s, obs_afericao=%s, valor_despesa=ISNULL(valor_despesa,0)+%s WHERE num=%s",
                (hoje, hora, usuario, motivo, despesa_incremento, num),
            )

            cur.execute("SELECT codigo FROM bomba WHERE ponto=%s AND posicao=%s", (row.get("ponto"), row.get("posicao")))
            bomba_row = cur.fetchone()
            if bomba_row:
                cur.execute(
                    "UPDATE mov_bomba SET afericao=ISNULL(afericao,0)+%s, valor_despesas=ISNULL(valor_despesas,0)+%s "
                    "WHERE bomba=%s AND data=%s AND turno=%s",
                    (volume, despesa_incremento, bomba_row["codigo"], row.get("data"), row.get("turno")),
                )
            afericoes_ok += 1

        if afericoes_ok == 0:
            conn.rollback()
            return {"success": False, "message": "Nenhum dos abastecimentos selecionados estava pendente."}
        conn.commit()
        return {"success": True, "message": f"{afericoes_ok} abastecimento(s) aferido(s)."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao aferir: {e}"}
    finally:
        conn.close()


def _reverter_sync(servidor: str, banco: str, num: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}

        cur.execute(
            "SELECT ponto, posicao, combustivel, volume, data, turno, valor_despesa, status_abastecimento "
            "FROM abastecimento WHERE num=%s",
            (num,),
        )
        row = cur.fetchone()
        if not row or (row.get("status_abastecimento") or "").upper() != "AFERIÇÃO":
            return {"success": False, "message": "Aferição não encontrada."}

        volume = float(row.get("volume") or 0)
        despesa = float(row.get("valor_despesa") or 0)

        cur.execute(
            "UPDATE abastecimento SET status_abastecimento='PENDENTE', usuario_afericao=NULL, hora_afericao=NULL, "
            "obs_afericao=NULL, data_afericao=NULL, valor_despesa=0 WHERE num=%s",
            (num,),
        )
        cur.execute("SELECT codigo FROM bomba WHERE ponto=%s AND posicao=%s", (row.get("ponto"), row.get("posicao")))
        bomba_row = cur.fetchone()
        if bomba_row:
            cur.execute(
                "UPDATE mov_bomba SET afericao=ISNULL(afericao,0)-%s, valor_despesas=ISNULL(valor_despesas,0)-%s "
                "WHERE bomba=%s AND data=%s AND turno=%s",
                (volume, despesa, bomba_row["codigo"], row.get("data"), row.get("turno")),
            )
        conn.commit()
        return {"success": True, "message": "Aferição revertida."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao reverter: {e}"}
    finally:
        conn.close()


async def list_pendentes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_pendentes_sync, servidor, banco)


async def list_afericoes(servidor: str, banco: str, data_ini: str, data_fim: str, incluir_afericoes: bool, incluir_despesas: bool) -> dict:
    return await asyncio.to_thread(_list_afericoes_sync, servidor, banco, data_ini, data_fim, incluir_afericoes, incluir_despesas)


async def aferir(servidor: str, banco: str, nums: list, lancar_despesa: bool, motivo: str, usuario: int) -> dict:
    return await asyncio.to_thread(_aferir_sync, servidor, banco, nums, lancar_despesa, motivo, usuario)


async def reverter(servidor: str, banco: str, num: int) -> dict:
    return await asyncio.to_thread(_reverter_sync, servidor, banco, num)

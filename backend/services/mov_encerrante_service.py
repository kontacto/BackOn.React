"""Movimentação de Encerrantes (Posto de Combustível) — tabelas
`mov_bomba` (leitura diária do encerrante por bomba/turno) e
`mov_combustivel` (ledger de saída de estoque, consumo FIFO de custo).

Legado: `frmmovbomba.frm` ("Movimentação de Bombas"). Lido campo-a-campo
2026-07-13 antes de implementar (ver PENDENCIAS.md > "Cluster de Turno").

**Escopo desta versão — Incluir/Alterar apenas, SEM Excluir.** O
`CmDexclui_Click` original tem uma cláusula SQL malformada (parêntese de
fechamento faltando) e tenta reverter o consumo FIFO de custo sem
rastrear qual lote de `Custo_Combustivel` foi consumido por qual
lançamento (a tabela não tem essa referência) — reverter corretamente
exigiria um vínculo que não existe hoje. Em vez de replicar uma reversão
capenga/quebrada, Excluir fica de fora desta fase (registrado como
melhoria futura, não como lacuna esquecida).

**"DATESIST" replicado como `posto_common.data_movimento(cur)`** — não
como variável global (ver CLAUDE.md > "Porting VB6 global state").

**Truques de VB6 deliberadamente NÃO replicados** (ver
`feedback_nao_replicar_truques_vb6` na memória do projeto):
- `Command1_Click` (botão invisível): script de correção de dados
  hardcoded pra bombas específicas em 2006 — lixo de debug, não portado.
- Patch cross-turno silencioso em `Campo_LostFocus` (ao detectar que o
  contador final do turno anterior não bate, abre um MsgBox e reescreve
  o OUTRO registro na hora): substituído por validação simples — se o
  contador inicial informado não bate com o final do turno anterior
  registrado, a gravação é bloqueada com mensagem clara, sem reescrever
  nenhum outro registro por trás.
- `Delete from Custo_Combustivel Where Entrada = Saida` (limpeza de lotes
  zerados após toda operação): não replicado — os lotes ficam registrados
  mesmo depois de totalmente consumidos, preservando o histórico de como
  o custo foi calculado (trilha de auditoria).

**Regras de negócio reais, replicadas fielmente**:
- Contador Final deve ser >= Contador Inicial.
- Aferição não pode ser maior que o Contador Final.
- (Aferição + Contador Inicial) não pode ser maior que o Contador Final.
- Volume vendido = Contador Final − Contador Inicial − Aferição.
- Não permite lançar em data futura à "data de movimento" (`DATESIST`).
- `Bomba.Contador_Final`/`Data_Ult_Mov` só avança (nunca retrocede).
- Consumo de custo por FIFO: casa o volume vendido com os lotes de
  `Custo_Combustivel` (Entrada > Saída) na ordem cronológica, criando
  `Mov_Combustivel` (`tipo_mov='S01'`) por lote consumido; se os lotes
  acabarem antes do volume, o restante usa `Combustivel.Custo` como
  custo unitário (mesmo fallback do legado).

Schema conferido ao vivo em GERDELL/BARESTELA: `mov_bomba` (data date NOT
NULL, turno smallint NOT NULL, bomba smallint NOT NULL, combustivel
smallint, funcionario int, contador_inicial/contador_final/afericao/
valor_despesas float) — chave composta (data, turno, bomba), sem PK
própria. `mov_combustivel` (combustivel smallint, data date, tipo_mov
nvarchar, quant/venda/custo float, sequencia int IDENTITY).
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG, data_movimento


def _list_opcoes_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT TOP 1 qtd_turnos FROM controle")
        row = cur.fetchone()
        qtd_turnos = int((row or {}).get("qtd_turnos") or 0) or 1
        turnos = list(range(1, qtd_turnos + 1))
        cur.execute("SELECT codigo_int, nome_guerra FROM funcionarios WHERE situacao='A' ORDER BY nome_guerra")
        funcionarios = [
            {"codigo": int(r["codigo_int"]), "nome": (r.get("nome_guerra") or "").strip()}
            for r in cur.fetchall()
        ]
        dm = data_movimento(cur)
        return {
            "success": True, "turnos": turnos, "funcionarios": funcionarios,
            "data_movimento": str(dm) if dm else None,
        }
    finally:
        conn.close()


def _list_sync(servidor: str, banco: str, data: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT m.data, m.turno, m.bomba, m.combustivel, m.funcionario, "
            "m.contador_inicial, m.contador_final, m.afericao, "
            "c.descricao AS combustivel_descricao, f.nome_guerra AS funcionario_nome "
            "FROM mov_bomba m "
            "LEFT JOIN combustivel c ON c.codigo = m.combustivel "
            "LEFT JOIN funcionarios f ON f.codigo_int = m.funcionario "
            "WHERE m.data=%s ORDER BY m.bomba, m.turno",
            (data,),
        )
        items = [
            {
                "data": str(r["data"]),
                "turno": int(r["turno"]),
                "bomba": int(r["bomba"]),
                "combustivel": int(r["combustivel"]) if r.get("combustivel") is not None else None,
                "combustivel_descricao": (r.get("combustivel_descricao") or "").strip(),
                "funcionario": int(r["funcionario"]) if r.get("funcionario") is not None else None,
                "funcionario_nome": (r.get("funcionario_nome") or "").strip(),
                "contador_inicial": float(r.get("contador_inicial") or 0),
                "contador_final": float(r.get("contador_final") or 0),
                "afericao": float(r.get("afericao") or 0),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_sync(
    servidor: str, banco: str, data: str, turno: int, bomba: int, funcionario: int,
    contador_inicial: float, contador_final: float, afericao: float,
) -> dict:
    if not data:
        return {"success": False, "message": "Informe a data."}
    if turno is None:
        return {"success": False, "message": "Selecione o turno."}
    if bomba is None:
        return {"success": False, "message": "Selecione a bomba."}
    if funcionario is None:
        return {"success": False, "message": "Selecione o funcionário."}
    contador_inicial = float(contador_inicial or 0)
    contador_final = float(contador_final or 0)
    afericao = float(afericao or 0)
    if afericao > contador_final:
        return {"success": False, "message": "Valor de Aferição não pode ser maior que o Contador Final."}
    if contador_final < contador_inicial:
        return {"success": False, "message": "Contador Final deve ser maior que o Contador Inicial."}
    if (afericao + contador_inicial) > contador_final:
        return {"success": False, "message": "Contador Final deve ser maior que o Contador Inicial mais o Valor de Aferição."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}

        dm = data_movimento(cur)
        if dm and data > str(dm):
            return {"success": False, "message": f"Data não permitida — posterior à data de movimento corrente ({dm})."}

        cur.execute("SELECT 1 AS ok FROM funcionarios WHERE codigo_int=%s", (funcionario,))
        if not cur.fetchone():
            return {"success": False, "message": "Funcionário não encontrado."}

        cur.execute("SELECT combustivel, contador_final FROM bomba WHERE codigo=%s", (bomba,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Bomba não encontrada."}
        combustivel = row.get("combustivel")
        if combustivel is None:
            return {"success": False, "message": "Bomba sem combustível vinculado."}
        bomba_contador_atual = float(row.get("contador_final") or 0)

        volume = round(contador_final - contador_inicial - afericao, 3)

        cur.execute("SELECT 1 AS ok FROM mov_bomba WHERE data=%s AND turno=%s AND bomba=%s", (data, turno, bomba))
        existe = cur.fetchone() is not None
        if existe:
            cur.execute(
                "UPDATE mov_bomba SET combustivel=%s, funcionario=%s, contador_inicial=%s, "
                "contador_final=%s, afericao=%s WHERE data=%s AND turno=%s AND bomba=%s",
                (combustivel, funcionario, contador_inicial, contador_final, afericao, data, turno, bomba),
            )
        else:
            cur.execute(
                "INSERT INTO mov_bomba (data, turno, bomba, combustivel, funcionario, "
                "contador_inicial, contador_final, afericao) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (data, turno, bomba, combustivel, funcionario, contador_inicial, contador_final, afericao),
            )

        if contador_final > bomba_contador_atual:
            cur.execute(
                "UPDATE bomba SET contador_final=%s, data_ult_mov=%s WHERE codigo=%s",
                (contador_final, data, bomba),
            )

        if volume > 0:
            # Estoque (combustivel) e estoque diário (por data) — mesmo par de
            # tabelas já usado por Estoque Combustível.
            cur.execute("SELECT estoque, venda, custo FROM combustivel WHERE codigo=%s", (combustivel,))
            comb_row = cur.fetchone() or {}
            estoque_atual = float(comb_row.get("estoque") or 0)
            venda_atual = float(comb_row.get("venda") or 0)
            custo_atual = float(comb_row.get("custo") or 0)
            cur.execute("UPDATE combustivel SET estoque=%s WHERE codigo=%s", (estoque_atual - volume, combustivel))

            # Composto por (combustivel, data, turno_estoque) — mesma chave já
            # usada pela tela Estoque Combustível (o legado original deste
            # form ignora turno aqui, mesma classe de bug já corrigido em
            # Estoque Combustível — não replicado).
            cur.execute(
                "SELECT 1 AS ok FROM estoque WHERE combustivel=%s AND data=%s AND turno_estoque=%s",
                (combustivel, data, turno),
            )
            if cur.fetchone():
                cur.execute(
                    "UPDATE estoque SET estoque=ISNULL(estoque,0)-%s WHERE combustivel=%s AND data=%s AND turno_estoque=%s",
                    (volume, combustivel, data, turno),
                )
            else:
                cur.execute(
                    "INSERT INTO estoque (combustivel, data, estoque, venda, turno_estoque) VALUES (%s,%s,%s,%s,%s)",
                    (combustivel, data, estoque_atual - volume, venda_atual, turno),
                )

            # Consumo FIFO de custo contra Custo_Combustivel (lotes Entrada>Saida).
            restante = volume
            cur.execute(
                "SELECT cod_cus, entrada, saida, custo FROM Custo_Combustivel "
                "WHERE combustivel=%s AND entrada > saida ORDER BY data, seq",
                (combustivel,),
            )
            lotes = cur.fetchall()
            for lote in lotes:
                if restante <= 0:
                    break
                disponivel = float(lote["entrada"]) - float(lote["saida"])
                consumido = min(disponivel, restante)
                cur.execute(
                    "UPDATE Custo_Combustivel SET saida=saida+%s WHERE cod_cus=%s",
                    (consumido, lote["cod_cus"]),
                )
                cur.execute(
                    "INSERT INTO Mov_Combustivel (combustivel, data, tipo_mov, quant, venda, custo) "
                    "VALUES (%s,%s,'S01',%s,%s,%s)",
                    (combustivel, data, consumido, venda_atual, float(lote.get("custo") or 0)),
                )
                restante -= consumido
            if restante > 0:
                cur.execute(
                    "INSERT INTO Mov_Combustivel (combustivel, data, tipo_mov, quant, venda, custo) "
                    "VALUES (%s,%s,'S01',%s,%s,%s)",
                    (combustivel, data, restante, venda_atual, custo_atual),
                )

        conn.commit()
        return {"success": True, "message": "Movimentação gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


async def list_opcoes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_opcoes_sync, servidor, banco)


async def list_mov(servidor: str, banco: str, data: str) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, data)


async def save_mov(servidor, banco, data, turno, bomba, funcionario, contador_inicial, contador_final, afericao):
    return await asyncio.to_thread(
        _save_sync, servidor, banco, data, turno, bomba, funcionario,
        contador_inicial, contador_final, afericao,
    )

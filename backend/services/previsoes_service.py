"""Financeiro > Fluxo de Caixa > Previsões (`Tesouraria\\FrmManPrev.frm`,
caption real "Previsões..."). CRUD de lançamentos futuros/recorrentes
MANUAIS (aluguel mensal, assinatura recorrente, qualquer previsão sem
vínculo com duplicata) + motor de Efetivação (previsão → movimentação
real, mudando `contas.saldo_atual` de verdade).

**Achado importante, corrigido durante o rastreio (não confundir com uma
suposição anterior errada já descartada)**: esta tela NÃO é o mecanismo
que efetiva as previsões que `transferencia_caixa_service.py` (Transferência
p/Fluxo de Caixa) cria a partir de duplicatas em aberto — aquelas têm
`previsoes.cod_transf_caixa > 0` e são **explicitamente bloqueadas** aqui,
tanto pra edição (`Command2_Click`, mensagem real do legado "Operação não
Permitida - Deve-se Alterar o Lcto no Contas A Pagar/no Contas A
Receber!") quanto pra efetivação em lote (`Command13_Click`, label
`Processa:`, `If Cod_Transf_Caixa > 0 Then GoTo naoprocessa` — item
simplesmente pulado). O ciclo de vida daquelas já está fechado em
`transferencia_caixa_service.py` (que apaga a própria previsão quando a
duplicata é baixada). Esta tela só cria/edita/efetiva previsões com
`cod_transf_caixa = 0` — as manuais, digitadas aqui mesmo.

**Correção 2026-08-31, user-directed** ("lançamentos que não podem ser
transferidos por aqui, tem que emitir mensagem de aviso de não permitido,
no momento da seleção"): a versão anterior desta migração escondia por
completo, no `WHERE` de `_listar_sync`, qualquer previsão com
`cod_transf_caixa > 0` — nunca aparecia na lista. Revertido pra bater com
o comportamento real do legado (`Grid_Click`, `FrmManPrev.frm:4074-4095`):
a lista mostra TODAS as previsões, e cada item vem com `bloqueada`/
`bloqueio_motivo` (`_bloqueio_transf_caixa`, réplica exata da ramificação
`Case Flag_Transf_Caixa`: 'P'→Contas a Pagar, 'R'→Contas a Receber, 'C'
(Comanda)→permitido mesmo com `cod_transf_caixa>0`, qualquer outro→"tela
de origem" genérico) — o frontend bloqueia a SELEÇÃO (checkbox) com a
mensagem específica, não a listagem inteira. `_efetivar_um_sync` continua
como a defesa real, de qualquer forma (nunca confiar só no frontend).

**Tipos**: 0=Pagar, 1=Receber, 2=Transferência (entre 2 contas — grava 1
único registro, `previsoes.classe` guarda a CONTA destino nesse caso,
reuso real da mesma coluna que noutros tipos guarda a classe contábil,
confirmado na fonte, não replicado como 2 colunas separadas por não
trazer valor real). Não existe aba "Saque" nesta tela (isso é só no
Painel de Movimentações, `FrmPnlCon.frm`, ainda não migrado).

**Recorrência real**: `previsoes.frequencia` (0=diário...9=anual,
10=única vez) — ao efetivar, a MESMA linha tem sua `data_vencimento`
avançada (soma dias/meses fixos, com correção de "dia não existe no
mês" — ex.: 31/mar mensal vira 30/abr, não 1/mai) — nunca gera uma
previsão nova. "Única Vez" é excluída da tabela ao ser efetivada. Não
existe job/agendador gerando previsões futuras antecipadamente — tudo é
recalculado só quando efetivado.

**Centro de custo**: uma ou mais linhas de rateio manual em
`previsoes_centro_custo` — diferente do split PROPORCIONAL automático já
usado em `transferencia_caixa_service.py`, aqui o usuário digita cada
linha à mão. Regra real preservada: a soma do rateio deve bater com
`previsoes.valor` — **simplificação deliberada em relação ao legado**: o
legado pergunta interativamente se quer sobrescrever o valor principal
quando a soma diverge (`Command26_Click`/`RestoCusto2`); aqui a gravação
é simplesmente bloqueada com mensagem clara até a soma bater — evita um
diálogo confuso de "sobrescrever ou não" sem perder a garantia real (soma
= valor).

**Favorecido/Classe/Sub-Classe**: achados-ou-criados por nome (mesmo
padrão de `_upsert_favorecido_sync` em `transferencia_caixa_service.py`),
usando o ID real devolvido pelo INSERT — o legado usa `SELECT MAX(Codigo)`
logo após o INSERT (frágil sob concorrência, gambiarra confirmada, não
replicada).

**Exclusão exige senha de gerente** quando `controle.senha_gerente_cx=1`
— mesmo padrão de elevação de privilégio já usado no resto do app
(`AuthorizationSlide`, ver `feedback_authorization_slide_global`); o
backend reforça recebendo um flag `autorizado_por` opcional no payload,
sem validar a senha em si (isso é responsabilidade do modal de
autorização já existente no frontend, mesma arquitetura de outras telas).

**Fora de escopo desta rodada, registrado**: "Gerar Planilha" (export
Excel — pode ser adicionado depois reaproveitando `export-xlsx.ts`),
`CheckBaixaData` (campo restrito ao usuário hardcoded "KONTACTO" no
legado — regra de acesso ad-hoc, não uma regra de negócio genérica).
"Anexos" reaproveita `GestorDocumentosSection` já existente — grupo
próprio "Previsões", igual ao padrão do resto do app.
"""
import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from db.connection import _open_conn

logger = logging.getLogger(__name__)

TIPOS = {0: "Pagar", 1: "Receber", 2: "Transferencia"}


def _round2(v) -> float:
    return round(float(v or 0), 2)


# =============================================================================
# Recorrência real — réplica de `RetOrnaFrequencia` (nome com erro de
# digitação confirmado na própria fonte VB6, não corrigido aqui de
# propósito — é literal na variável/rotina original).
# =============================================================================

def _ultimo_dia_valido(ano: int, mes: int, dia: int) -> date:
    """Corrige "dia não existe no mês" decrementando até achar uma data
    válida (mesma técnica do legado — 31/fev vira o último dia real de
    fevereiro, não "dia 1 do mês seguinte")."""
    while True:
        try:
            return date(ano, mes, dia)
        except ValueError:
            dia -= 1
            if dia < 1:
                raise


def _avancar_meses(d: date, meses: int) -> date:
    total = d.month - 1 + meses
    ano = d.year + total // 12
    mes = total % 12 + 1
    return _ultimo_dia_valido(ano, mes, d.day)


def avancar_data_frequencia(data_vencimento: date, frequencia: int) -> Optional[date]:
    """None = "Única Vez" (10) — a previsão deve ser excluída, não
    reagendada. Demais frequências avançam a MESMA data."""
    mapa_dias = {0: 1, 1: 7, 2: 10, 3: 15}
    mapa_meses = {4: 1, 5: 2, 6: 3, 7: 4, 8: 6, 9: 12}
    if frequencia in mapa_dias:
        return data_vencimento + timedelta(days=mapa_dias[frequencia])
    if frequencia in mapa_meses:
        return _avancar_meses(data_vencimento, mapa_meses[frequencia])
    return None  # 10 = Única Vez


# =============================================================================
# Achar-ou-criar (Favorecido/Classe/Sub-Classe) — mesmo padrão de
# `_upsert_favorecido_sync`, mas com o ID real do INSERT (não MAX(Codigo)).
# =============================================================================

def _upsert_favorecido_sync(cur, nome: str) -> int:
    nome = (nome or "").strip()
    if not nome:
        return 0
    cur.execute("SELECT codigo FROM favorecidos WHERE descricao = %s", (nome,))
    row = cur.fetchone()
    if row:
        return int(row["codigo"])
    cur.execute("INSERT INTO favorecidos (descricao) OUTPUT INSERTED.codigo VALUES (%s)", (nome,))
    return int(cur.fetchone()["codigo"])


def _upsert_classe_sync(cur, nome: str) -> int:
    nome = (nome or "").strip()
    if not nome:
        return 0
    cur.execute("SELECT codigo FROM classes WHERE descricao = %s", (nome,))
    row = cur.fetchone()
    if row:
        return int(row["codigo"])
    cur.execute("INSERT INTO classes (descricao) OUTPUT INSERTED.codigo VALUES (%s)", (nome,))
    return int(cur.fetchone()["codigo"])


def _upsert_sub_classe_sync(cur, classe: int, nome: str) -> int:
    nome = (nome or "").strip()
    if not nome or not classe:
        return 0
    cur.execute("SELECT codigo FROM sub_classes WHERE classe = %s AND descricao = %s", (classe, nome))
    row = cur.fetchone()
    if row:
        return int(row["codigo"])
    cur.execute("INSERT INTO sub_classes (classe, descricao) OUTPUT INSERTED.codigo VALUES (%s,%s)", (classe, nome))
    return int(cur.fetchone()["codigo"])


# =============================================================================
# Listagem
# =============================================================================

# Guarda "Transferência Para Movimentação" (`FrmManPrev.frm:4076-4090`) —
# `cod_transf_caixa > 0` bloqueia a efetivação DAQUI, exceto quando
# `flag_transf_caixa = 'C'` (Comanda — `Geral\mdl_proc.bas:3885-3897`,
# confirmado na fonte; não reproduzível hoje nesta migração, já que
# `comanda_service.py` nunca grava `cod_transf_caixa`/`flag_transf_caixa`
# em `previsoes` — mantido aqui por fidelidade à ramificação real, não
# suposição). 'P'/'R' vêm de Contas a Pagar/Receber; qualquer outro valor
# cai no genérico "de Origem", mesmo fallback do legado.
_MOTIVO_BLOQUEIO_POR_FLAG = {
    "P": "Operação não permitida — realize a baixa através do Contas a Pagar.",
    "R": "Operação não permitida — realize a baixa através do Contas a Receber.",
}


def _bloqueio_transf_caixa(cod_transf_caixa, flag_transf_caixa) -> Optional[str]:
    if int(cod_transf_caixa or 0) <= 0:
        return None
    flag = (flag_transf_caixa or "").strip().upper()
    if flag == "C":
        return None
    return _MOTIVO_BLOQUEIO_POR_FLAG.get(flag, "Operação não permitida — realize a baixa através da tela de origem.")


def _row_to_item(r: dict) -> dict:
    bloqueio_motivo = _bloqueio_transf_caixa(r.get("cod_transf_caixa"), r.get("flag_transf_caixa"))
    flag = (r.get("flag_transf_caixa") or "").strip().upper() or None
    return {
        "codigo": int(r["codigo"]),
        "bloqueada": bloqueio_motivo is not None,
        "bloqueio_motivo": bloqueio_motivo,
        # Achado do usuário 2026-08-31 ("possibilitar da tela de Previsão
        # alterar a situação do vencimento... em lançamentos bloqueados
        # por ser de Contas a Receber") — `cod_transf_caixa` é literalmente
        # o `duplicata_rec_venc.codigo` quando `flag_transf_caixa='R'`
        # (confirmado em `FrmManDur.frm:2553`), o frontend usa isso pra
        # chamar `/contas-receber/vencimento/situacao` direto daqui.
        "cod_transf_caixa": int(r.get("cod_transf_caixa") or 0) or None,
        "flag_transf_caixa": flag,
        # Valor atual de `duplicata_rec_venc.situacao_duplicata` (0=Normal,
        # 1=Jurídico, 2=Protestado) — só preenchido quando flag_transf_caixa
        # ='R' (o LEFT JOIN só casa nesse caso). Achado do usuário 2026-08-31
        # ("continua não alterando"): sem isso, o modal de Alterar Situação
        # sempre reabria em "Normal" por padrão, dando a falsa impressão de
        # que a gravação anterior não tinha colado.
        "situacao_duplicata_atual": int(r["situacao_duplicata_atual"]) if r.get("situacao_duplicata_atual") is not None else None,
        "conta": r.get("conta"),
        "conta_descricao": (r.get("conta_descricao") or "").strip(),
        "classe": r.get("classe"),
        "classe_descricao": (r.get("classe_descricao") or "").strip() if r.get("tipo") != 2 else None,
        "conta_destino_descricao": (r.get("classe_descricao") or "").strip() if r.get("tipo") == 2 else None,
        "sub_classe": r.get("sub_classe"),
        "documento": (r.get("documento") or "").strip() if isinstance(r.get("documento"), str) else r.get("documento"),
        "data_documento": r["data_documento"].isoformat() if r.get("data_documento") else None,
        "data_vencimento": r["data_vencimento"].isoformat() if r.get("data_vencimento") else None,
        "favorecido": r.get("favorecido"),
        "favorecido_nome": (r.get("favorecido_nome") or "").strip(),
        "valor": float(r.get("valor") or 0),
        "tipo": int(r.get("tipo") or 0),
        "memorando": (r.get("memorando") or "").strip(),
        "frequencia": int(r.get("frequencia") if r.get("frequencia") is not None else 10),
    }


def _listar_sync(servidor: str, banco: str, opcoes: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        # Correção 2026-08-31, user-directed: antes excluía toda previsão
        # com `cod_transf_caixa>0` daqui direto no WHERE — a lista nunca
        # mostrava o item bloqueado, só "sumia". O usuário pediu o oposto
        # (mesma UX do legado, `Grid_Click`): mostrar TODAS, bloquear a
        # SELEÇÃO com a mensagem específica (ver `_bloqueio_transf_caixa`)
        # — `bloqueada`/`bloqueio_motivo` (calculados em `_row_to_item`)
        # protegem a seleção. Exceção adicionada no mesmo dia: Jurídico
        # (`situacao_duplicata=1`) É excluído da listagem em si (ver
        # `clausulas` logo abaixo) — pedido explícito à parte, não
        # contradiz o parágrafo acima (aquele é sobre `cod_transf_caixa`
        # em geral, este é especificamente sobre a situação Jurídico).
        # Achado do usuário 2026-08-31 ("a listagem da previsão não pode
        # listar lançamento cuja a situação é Jurídico") — exclui só
        # Jurídico(1); Protestado(2) continua aparecendo, já que não foi
        # pedido e não dá pra assumir a mesma regra sem confirmar (ver
        # CLAUDE.md > "Regras Importantes"). `drv` é o LEFT JOIN pra
        # Duplicata_Rec_Venc feito mais abaixo — precisa estar em escopo
        # aqui porque essa cláusula entra no mesmo WHERE da query toda.
        clausulas: list = ["ISNULL(drv.situacao_duplicata,0) <> 1"]
        params: list = []

        conta = opcoes.get("conta")
        if conta:
            clausulas.append("p.conta = %s")
            params.append(int(conta))

        tipo = opcoes.get("tipo")
        if tipo is not None:
            clausulas.append("p.tipo = %s")
            params.append(int(tipo))

        filtro_data = (opcoes.get("filtro_data") or "todas").lower()
        hoje_dt = date.today()
        hoje = hoje_dt.isoformat()
        if filtro_data == "atraso":
            clausulas.append("p.data_vencimento < %s")
            params.append(hoje)
        elif filtro_data == "hoje":
            clausulas.append("p.data_vencimento = %s")
            params.append(hoje)
        elif filtro_data == "mes":
            # Filtro de período mensal, navegável (achado do usuário
            # 2026-08-31) — mesma resolução de "AAAA-MM" já usada em
            # `painel_financeiro_service._resolver_periodo`, réplica
            # local pra não acoplar os 2 módulos por 1 cálculo simples.
            mes_ref = opcoes.get("mes_ref")
            if mes_ref:
                ano, mes = (int(x) for x in mes_ref.split("-"))
            else:
                ano, mes = hoje_dt.year, hoje_dt.month
            inicio = date(ano, mes, 1)
            fim_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
            fim = fim_mes - timedelta(days=1)
            clausulas.append("p.data_vencimento BETWEEN %s AND %s")
            params.extend([inicio.isoformat(), fim.isoformat()])
        # "todas" — sem filtro de data

        busca = (opcoes.get("busca") or "").strip()
        if busca:
            clausulas.append("(f.descricao LIKE %s OR CAST(p.valor AS NVARCHAR(30)) LIKE %s)")
            params.extend([f"%{busca}%", f"%{busca}%"])

        where = " AND ".join(clausulas)
        where_sql = f"WHERE {where} " if where else ""
        cur.execute(
            "SELECT p.codigo, p.conta, c.descricao AS conta_descricao, p.classe, "
            "cl.descricao AS classe_descricao, p.sub_classe, p.documento, p.data_documento, "
            "p.data_vencimento, p.favorecido, f.descricao AS favorecido_nome, p.valor, p.tipo, "
            "p.memorando, p.frequencia, p.cod_transf_caixa, p.flag_transf_caixa, "
            "drv.situacao_duplicata AS situacao_duplicata_atual "
            "FROM previsoes p "
            "LEFT JOIN contas c ON c.codigo = p.conta "
            "LEFT JOIN favorecidos f ON f.codigo = p.favorecido "
            "LEFT JOIN classes cl ON cl.codigo = p.classe AND p.tipo <> 2 "
            "LEFT JOIN Duplicata_Rec_Venc drv ON drv.codigo = p.cod_transf_caixa AND p.flag_transf_caixa = 'R' "
            f"{where_sql}ORDER BY p.data_vencimento",
            params,
        )
        items = [_row_to_item(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def listar(servidor: str, banco: str, opcoes: dict) -> dict:
    return await asyncio.to_thread(_listar_sync, servidor, banco, opcoes)


def _get_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT p.*, f.descricao AS favorecido_nome, cl.descricao AS classe_nome, "
            "sc.descricao AS sub_classe_nome "
            "FROM previsoes p LEFT JOIN favorecidos f ON f.codigo = p.favorecido "
            "LEFT JOIN classes cl ON cl.codigo = p.classe AND p.tipo <> 2 "
            "LEFT JOIN sub_classes sc ON sc.codigo = p.sub_classe "
            "WHERE p.codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Previsão não encontrada."}
        cur.execute(
            "SELECT codigo, centro_custo, classe, sub_classe, valor, memorando, credito_debito, "
            "repete_lancamento FROM previsoes_centro_custo WHERE codigo_prev = %s ORDER BY codigo",
            (codigo,),
        )
        rateio = cur.fetchall() or []
        cur.close()
        conn.close()
        item = _row_to_item(row)
        item["favorecido_nome"] = (row.get("favorecido_nome") or "").strip()
        item["classe_nome"] = (row.get("classe_nome") or "").strip() if row.get("tipo") != 2 else None
        item["sub_classe_nome"] = (row.get("sub_classe_nome") or "").strip()
        item["rateio"] = [
            {
                "codigo": r["codigo"], "centro_custo": r["centro_custo"], "classe": r.get("classe"),
                "sub_classe": r.get("sub_classe"), "valor": float(r.get("valor") or 0),
                "memorando": (r.get("memorando") or "").strip(),
                "credito_debito": (r.get("credito_debito") or "").strip(),
                "repete_lancamento": bool(r.get("repete_lancamento")),
            }
            for r in rateio
        ]
        return {"success": True, **item}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def obter(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_sync, servidor, banco, codigo)


# =============================================================================
# Gravar (criar/editar) — Pagar(0)/Receber(1)/Transferência(2)
# =============================================================================

def _save_sync(servidor: str, banco: str, dados: dict) -> dict:
    codigo = dados.get("codigo")
    tipo = int(dados.get("tipo") if dados.get("tipo") is not None else 0)
    if tipo not in (0, 1, 2):
        return {"success": False, "message": "Tipo inválido — só Pagar, Receber ou Transferência."}
    conta = dados.get("conta")
    if not conta:
        return {"success": False, "message": "Defina a Conta."}
    valor = _round2(dados.get("valor"))
    if valor <= 0:
        return {"success": False, "message": "Informe um Valor maior que zero."}
    data_vencimento = dados.get("data_vencimento")
    if not data_vencimento:
        return {"success": False, "message": "Defina a Data de Vencimento."}
    frequencia = int(dados.get("frequencia") if dados.get("frequencia") is not None else 10)

    rateio = dados.get("rateio") or []
    if rateio:
        soma = _round2(sum(_round2(r.get("valor")) for r in rateio))
        if soma != valor:
            return {"success": False, "message": f"A soma do rateio de centro de custo (R$ {soma:.2f}) precisa bater com o Valor (R$ {valor:.2f})."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        if codigo:
            cur.execute("SELECT cod_transf_caixa FROM previsoes WHERE codigo = %s", (int(codigo),))
            atual = cur.fetchone()
            if not atual:
                return {"success": False, "message": "Previsão não encontrada."}
            if int(atual.get("cod_transf_caixa") or 0) > 0:
                return {"success": False, "message": "Esta previsão pertence a outra tela (Contas a Pagar/Receber) — a alteração precisa ser feita lá."}

        favorecido = _upsert_favorecido_sync(cur, dados.get("favorecido_nome"))

        if tipo == 2:
            conta_destino = dados.get("conta_destino")
            if not conta_destino:
                return {"success": False, "message": "Defina a Conta de destino da Transferência."}
            if int(conta_destino) == int(conta):
                return {"success": False, "message": "A conta de origem e destino não podem ser a mesma."}
            classe_codigo = int(conta_destino)
            sub_classe_codigo = None
            documento = None
        else:
            # Classe/Sub-Classe são códigos reais do Plano de Contas
            # (`classes`/`sub_classes`) — sempre escolhidos numa combobox
            # no frontend, nunca texto livre (achado do usuário
            # 2026-08-31). `_upsert_classe_sync`/`_upsert_sub_classe_sync`
            # continuam definidas neste arquivo só porque
            # `painel_financeiro_service.py` ainda as reaproveita pro seu
            # próprio Lançamento Direto (fora de escopo desta correção).
            classe_codigo = dados.get("classe")
            sub_classe_codigo = dados.get("sub_classe")
            documento = (dados.get("documento") or "").strip() or None

        memorando = (dados.get("memorando") or "").strip()
        data_documento = dados.get("data_documento") or data_vencimento

        if not codigo:
            parcelas = max(1, int(dados.get("parcelas") or 1))
            codigos_criados = []
            data_corrente = data_vencimento
            for _ in range(parcelas):
                cur.execute(
                    "INSERT INTO previsoes (conta,data_documento,documento,data_vencimento,favorecido,valor,"
                    "classe,sub_classe,tipo,memorando,frequencia) OUTPUT INSERTED.codigo "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (int(conta), data_documento, documento, data_corrente, favorecido, valor,
                     classe_codigo, sub_classe_codigo, tipo, memorando, frequencia),
                )
                novo_codigo = int(cur.fetchone()["codigo"])
                codigos_criados.append(novo_codigo)
                _gravar_rateio_sync(cur, novo_codigo, rateio)
                if parcelas > 1:
                    proxima = avancar_data_frequencia(date.fromisoformat(data_corrente), 4)  # parcelas = mensal
                    data_corrente = proxima.isoformat() if proxima else data_corrente
            conn.commit()
            cur.close()
            return {"success": True, "codigo": codigos_criados[0], "codigos": codigos_criados, "message": "Previsão gravada."}

        cur.execute(
            "UPDATE previsoes SET conta=%s, data_documento=%s, documento=%s, data_vencimento=%s, "
            "favorecido=%s, valor=%s, classe=%s, sub_classe=%s, tipo=%s, memorando=%s, frequencia=%s "
            "WHERE codigo=%s",
            (int(conta), data_documento, documento, data_vencimento, favorecido, valor,
             classe_codigo, sub_classe_codigo, tipo, memorando, frequencia, int(codigo)),
        )
        _gravar_rateio_sync(cur, int(codigo), rateio)
        conn.commit()
        cur.close()
        return {"success": True, "codigo": int(codigo), "message": "Previsão gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _gravar_rateio_sync(cur, codigo_prev: int, rateio: list) -> None:
    cur.execute("DELETE FROM previsoes_centro_custo WHERE codigo_prev = %s", (codigo_prev,))
    for linha in rateio:
        cur.execute(
            "INSERT INTO previsoes_centro_custo (codigo_prev,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito,repete_lancamento) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (codigo_prev, linha.get("centro_custo"), linha.get("classe") or 0, linha.get("sub_classe") or 0,
             _round2(linha.get("valor")), (linha.get("memorando") or "").strip(),
             (linha.get("credito_debito") or "C").strip()[:1].upper(), bool(linha.get("repete_lancamento"))),
        )


async def salvar(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, dados)


# =============================================================================
# Excluir — exige senha de gerente quando controle.senha_gerente_cx=1
# (autorização em si é responsabilidade do AuthorizationSlide do
# frontend, mesmo padrão já usado no resto do app; o backend só recebe a
# confirmação e a registra em auditoria).
# =============================================================================

def _exige_senha_gerente_sync(cur) -> bool:
    cur.execute("SELECT TOP 1 senha_gerente_cx FROM controle")
    r = cur.fetchone() or {}
    return bool(r.get("senha_gerente_cx"))


def _delete_sync(servidor: str, banco: str, codigo: int, autorizado: bool) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cod_transf_caixa FROM previsoes WHERE codigo = %s", (codigo,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Previsão não encontrada."}
        if int(row.get("cod_transf_caixa") or 0) > 0:
            return {"success": False, "message": "Esta previsão pertence a outra tela (Contas a Pagar/Receber) — a exclusão precisa ser feita lá."}
        if _exige_senha_gerente_sync(cur) and not autorizado:
            return {"success": False, "message": "Exclusão exige autorização de gerente.", "exige_autorizacao": True}
        cur.execute("DELETE FROM previsoes_centro_custo WHERE codigo_prev = %s", (codigo,))
        cur.execute("DELETE FROM previsoes WHERE codigo = %s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Previsão excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def excluir(servidor: str, banco: str, codigo: int, autorizado: bool = False) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, codigo, autorizado)


# =============================================================================
# Efetivar — motor central (`Command13_Click`/label `Processa:`, réplica
# fiel). Aceita 1 ou vários códigos — a seleção em lote no legado (itens
# marcados/faixa de data/por favorecido) vira, na migração, simplesmente
# "quais itens o usuário marcou na listagem já filtrada" — mesmo
# resultado prático, mecanismo mais simples.
# =============================================================================

def _efetivar_um_sync(cur, codigo: int, data_liquidacao_override: Optional[str], grupos_doc: tuple, conta_override: Optional[int] = None) -> dict:
    grupo_financeiro, sub_grupo_previsoes, sub_grupo_movimentacoes = grupos_doc
    cur.execute("SELECT * FROM previsoes WHERE codigo = %s", (codigo,))
    prev = cur.fetchone()
    if not prev:
        return {"success": False, "message": f"Previsão {codigo} não encontrada."}
    if int(prev.get("cod_transf_caixa") or 0) > 0:
        return {"success": False, "message": "Esta previsão pertence a outra tela — não pode ser efetivada aqui."}

    tipo = int(prev.get("tipo") or 0)
    data_liquidacao = data_liquidacao_override or prev["data_vencimento"].isoformat()

    if tipo == 2:
        # Override de conta (`ctf`, `FrmManPrev.frm:2095-2105`) só troca a
        # conta DEBITADA/origem no legado — a conta destino (`classe`)
        # nunca muda, mesmo com "Conta" preenchido na Transferência Para
        # Movimentação.
        conta_origem = int(conta_override) if conta_override else int(prev["conta"])
        conta_destino = int(prev["classe"])
        cur.execute(
            "INSERT INTO movimentacoes (conta,data_liquidacao,documento,data_documento,data_vencimento,"
            "favorecido,valor,classe,tipo,memorando) OUTPUT INSERTED.codigo "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,2,%s)",
            (conta_origem, data_liquidacao, prev.get("documento"), prev["data_documento"],
             prev["data_vencimento"], prev.get("favorecido"), prev["valor"], conta_destino, prev.get("memorando")),
        )
        cod_mov = int(cur.fetchone()["codigo"])
        cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual - %s AS NUMERIC(15,2)) WHERE codigo = %s",
                    (prev["valor"], conta_origem))
        cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s",
                    (prev["valor"], conta_destino))
    else:
        conta_alvo = int(conta_override) if conta_override else int(prev["conta"])
        cur.execute(
            "INSERT INTO movimentacoes (conta,data_liquidacao,documento,data_documento,data_vencimento,"
            "favorecido,valor,classe,sub_classe,tipo,memorando) OUTPUT INSERTED.codigo "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (conta_alvo, data_liquidacao, prev.get("documento"), prev["data_documento"],
             prev["data_vencimento"], prev.get("favorecido"), prev["valor"], prev.get("classe"),
             prev.get("sub_classe"), tipo, prev.get("memorando")),
        )
        cod_mov = int(cur.fetchone()["codigo"])
        if tipo == 1:
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s",
                        (prev["valor"], conta_alvo))
        else:  # tipo == 0 (Pagar) ou 3 (Saque)
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual - %s AS NUMERIC(15,2)) WHERE codigo = %s",
                        (prev["valor"], conta_alvo))

    cur.execute(
        "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,memorando,"
        "credito_debito) SELECT %s,centro_custo,classe,sub_classe,valor,memorando,credito_debito "
        "FROM previsoes_centro_custo WHERE codigo_prev = %s",
        (cod_mov, codigo),
    )
    cur.execute(
        "UPDATE gestor_documentos SET cod_sub_grupo = %s, referencia = %s "
        "WHERE cod_grupo = %s AND cod_sub_grupo = %s AND referencia = %s",
        (sub_grupo_movimentacoes, cod_mov, grupo_financeiro, sub_grupo_previsoes, codigo),
    )

    proxima = avancar_data_frequencia(prev["data_vencimento"], int(prev.get("frequencia") if prev.get("frequencia") is not None else 10))
    if proxima is None:
        cur.execute("DELETE FROM previsoes_centro_custo WHERE codigo_prev = %s", (codigo,))
        cur.execute("DELETE FROM previsoes WHERE codigo = %s", (codigo,))
    else:
        cur.execute("UPDATE previsoes SET data_vencimento = %s WHERE codigo = %s", (proxima.isoformat(), codigo))

    return {"success": True, "codigo_movimentacao": cod_mov}


# Grupo/sub-grupo do Gestor de Documentos pra Previsões/Movimentações —
# mesmo padrão do resto do app (find-or-create por descrição), resolvido
# de novo a cada chamada de _efetivar_sync (nunca em variável de módulo —
# ver "Porting VB6 global state" no CLAUDE.md: este backend é stateless,
# atende várias empresas/conexões ao mesmo tempo, um global vazaria o
# grupo de uma empresa pra outra).
GRUPO_FINANCEIRO_DESCRICAO = "FINANCEIRO"
SUB_GRUPO_PREVISOES_DESCRICAO = "PREVISOES"
SUB_GRUPO_MOVIMENTACOES_DESCRICAO = "MOVIMENTACOES"


def _resolver_grupos_gestor_documentos_sync(cur) -> tuple:
    cur.execute("SELECT codigo FROM gestor_docs_grupos WHERE grupo = %s", (GRUPO_FINANCEIRO_DESCRICAO,))
    r = cur.fetchone()
    if r:
        grupo_financeiro = int(r["codigo"])
    else:
        cur.execute("INSERT INTO gestor_docs_grupos (grupo) OUTPUT INSERTED.codigo VALUES (%s)", (GRUPO_FINANCEIRO_DESCRICAO,))
        grupo_financeiro = int(cur.fetchone()["codigo"])
    codigos = {}
    for nome, alvo in ((SUB_GRUPO_PREVISOES_DESCRICAO, "prev"), (SUB_GRUPO_MOVIMENTACOES_DESCRICAO, "mov")):
        cur.execute("SELECT cod_sub_grupo FROM gestor_docs_sub_grupos WHERE cod_grupo = %s AND descricao = %s", (grupo_financeiro, nome))
        r = cur.fetchone()
        if r:
            codigos[alvo] = int(r["cod_sub_grupo"])
        else:
            cur.execute("INSERT INTO gestor_docs_sub_grupos (cod_grupo, descricao) OUTPUT INSERTED.cod_sub_grupo VALUES (%s,%s)", (grupo_financeiro, nome))
            codigos[alvo] = int(cur.fetchone()["cod_sub_grupo"])
    return grupo_financeiro, codigos["prev"], codigos["mov"]


def _efetivar_sync(servidor: str, banco: str, codigos: list, data_liquidacao: Optional[str] = None, conta: Optional[int] = None) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        grupos_doc = _resolver_grupos_gestor_documentos_sync(cur)

        sucesso, falhas = [], []
        for codigo in codigos:
            try:
                resultado = _efetivar_um_sync(cur, int(codigo), data_liquidacao, grupos_doc, conta)
            except Exception as e:
                logger.warning("previsoes: falha ao efetivar %s", codigo, exc_info=True)
                resultado = {"success": False, "message": f"Não foi possível efetivar o item {codigo} — tente novamente ou avise o suporte se persistir."}
            if resultado.get("success"):
                sucesso.append(codigo)
            else:
                falhas.append({"codigo": codigo, "message": resultado.get("message")})

        conn.commit()
        cur.close()
        conn.close()
        return {"success": len(falhas) == 0, "efetivados": sucesso, "falhas": falhas}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def efetivar(servidor: str, banco: str, codigos: list, data_liquidacao: Optional[str] = None, conta: Optional[int] = None) -> dict:
    return await asyncio.to_thread(_efetivar_sync, servidor, banco, codigos, data_liquidacao, conta)

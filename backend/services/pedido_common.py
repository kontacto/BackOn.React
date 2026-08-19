"""Helpers de baixo nível compartilhados pelos serviços de itens e descontos.

Todas as funções recebem um cursor (`cur`) já aberto — não abrem conexão.
Mantidas em módulo próprio para evitar import circular entre itens_service e
descontos_service.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from db.connection import iso
from services.constants import STATUS_CLIENTE_LABEL


def _check_cliente_ativo(cur, cliente_codigo: int) -> tuple[bool, str]:
    """Bloqueia nova movimentação (Pedido/O.S.) para cliente com STATUS_CLIENTE
    diferente de 'A' (Ativo). Cliente sem status definido (NULL/'') é tratado
    como Ativo (dado legado, coluna sem valor). Retorna (permitido, label)."""
    cur.execute("SELECT STATUS_CLIENTE FROM cliente WHERE codigo=%s", (cliente_codigo,))
    row = cur.fetchone()
    status = ((row.get("STATUS_CLIENTE") if row else None) or "").strip().upper()
    if not status or status == "A":
        return True, ""
    return False, STATUS_CLIENTE_LABEL.get(status, status)


def _check_area_atuacao(cur, funcionario_codigo: Optional[int], area_atuacao: Optional[int]) -> tuple[bool, str]:
    """Réplica de `VerificaAreaAtuacao` (`MdiPrincipal`/`Geral\\mdl_proc.bas`)
    — no legado, bloqueia abrir Pedido/O.S. quando o usuário logado não está
    vinculado (`funcionarios_area_atuacao`) à Área de Atuação selecionada.
    Nunca implementado nesta migração até agora — ver PENDENCIAS.md > "MDI
    Principal (VB6)".

    Decisões desta migração (documentadas por não serem cópia literal do
    legado):
    - Sem `funcionario_codigo` resolvido (ex.: usuário master, que não
      depende de linha em `funcionarios` — ver `usuarios_service.py`) ou
      sem `area_atuacao` informado no Pedido/O.S., não há o que checar —
      permitido. O legado tem uma exceção explícita pro usuário KONTACTO;
      como o backend aqui não recebe o login (só o código do funcionário),
      "sem funcionário resolvido" cobre o mesmo caso na prática.
    - Funcionário SEM nenhuma área cadastrada em `funcionarios_area_atuacao`
      é tratado como sem restrição (acesso livre a qualquer área) — evita
      bloquear de surpresa toda uma instalação que nunca configurou esse
      vínculo antes desta feature existir. Só bloqueia quando o
      funcionário TEM área(s) configurada(s) e a solicitada não está entre
      elas.
    """
    if not funcionario_codigo or not area_atuacao:
        return True, ""
    cur.execute("SELECT area FROM funcionarios_area_atuacao WHERE func=%s", (funcionario_codigo,))
    areas = {int(r["area"]) for r in cur.fetchall() if r.get("area") is not None}
    if not areas or int(area_atuacao) in areas:
        return True, ""
    cur.execute("SELECT descricao FROM area_atuacao WHERE area=%s", (area_atuacao,))
    row = cur.fetchone()
    label = (row.get("descricao") if row else "") or str(area_atuacao)
    return False, label


def _chassi_obrigatorio_ok(cur, chassi: Optional[str]) -> bool:
    """`controle.exige_chassi_os` (bit) — avisado pela equipe VB6, 2026-08-17:
    "Se exige ou não na OS oficina o chassi do veículo". Quando ligado, o
    Chassi é obrigatório ao gravar (criar OU editar) uma O.S. — mas só
    quando o segmento Oficina está ativo (`controle_configuracao.Oficina`);
    Oficina e Assistência compartilham a mesma tela de O.S. (ver
    `MODULE_TELAS`/`disabled_telas` em `controle_config_service.py`/
    `permissoes_service.py`), mas só Oficina lida com veículo — Assistência
    nunca exige chassi, independente do flag. Sem o módulo Oficina ligado,
    ou sem o flag `exige_chassi_os` ligado (ou sem registro de `controle`),
    chassi continua opcional — comportamento já existente antes desta
    regra, mesmo princípio de "Regra de Módulo Ativo" já aplicado a outras
    entidades.
    """
    if (chassi or "").strip():
        return True
    cur.execute("SELECT TOP 1 Oficina FROM controle_configuracao")
    row = cur.fetchone()
    if not row or not bool(row.get("Oficina")):
        return True
    cur.execute("SELECT TOP 1 exige_chassi_os FROM controle")
    row2 = cur.fetchone()
    return not (row2 and bool(row2.get("exige_chassi_os")))


def _auto_abrir_dia_se_necessario(cur) -> None:
    """Réplica do lado AUTOMÁTICO de `MudaDataSistema`/`Ger_Abr_Click`
    (`MdiPrincipal`) — quando a empresa NÃO usa a Abertura do Dia manual
    (`controle_configuracao.CONTROLA_ABERTURA_DIA` desligado — o
    comportamento default de toda instalação até hoje, confirmado pela
    equipe VB6 2026-08-16, ninguém nunca ligou o flag), a Data de
    Movimento avança sozinha pra hoje na próxima criação de Pedido/O.S.,
    sem exigir que o operador use a tela "Gerencial > Abertura do Dia"
    (`abertura_dia_service.py`). A reconciliação de estoque que o legado
    fazia junto disso está CONFIRMADA em desuso — não replicada aqui, só
    a Data de Movimento em si.

    Melhor esforço: qualquer falha (coluna/tabela ausente numa instalação
    muito antiga, etc.) é silenciosamente ignorada — nunca deve bloquear
    a criação do Pedido/O.S. por causa disso.
    """
    try:
        cur.execute("SELECT TOP 1 CONTROLA_ABERTURA_DIA FROM controle_configuracao")
        row = cur.fetchone()
        if row and bool(row.get("CONTROLA_ABERTURA_DIA")):
            return  # empresa usa o fluxo manual — não mexe sozinho
        cur.execute("SELECT TOP 1 Data_Movimento FROM controle")
        row = cur.fetchone()
        data_atual = iso((row or {}).get("Data_Movimento"))
        hoje = date.today().isoformat()
        if not data_atual or data_atual < hoje:
            cur.execute("UPDATE controle SET Data_Movimento = %s", (hoje,))
    except Exception:
        pass


def _item_total(qtd, pv) -> float:
    # p_venda já é o preço líquido unitário (= p_normal - desconto + acrescimo)
    return round(float(qtd or 0) * float(pv or 0), 2)


def _recalc_pedido_total(cur, pedido: int) -> float:
    cur.execute(
        "UPDATE pedido_venda SET total = ISNULL(("
        "  SELECT SUM(qtd_pedida * p_venda) "
        "  FROM pedido_venda_prod WHERE pedido=%s AND ISNULL(item_cancelado,0)=0"
        "), 0) WHERE pedido=%s",
        (pedido, pedido),
    )
    cur.execute("SELECT total FROM pedido_venda WHERE pedido=%s", (pedido,))
    r = cur.fetchone()
    return float((r.get("total") if isinstance(r, dict) else (r[0] if r else 0)) or 0)


def _check_pedido_aberto(cur, pedido: int) -> tuple[bool, str]:
    """Retorna (existe, situacao). Não levanta exceção."""
    cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
    row = cur.fetchone()
    if not row:
        return (False, "")
    return (True, (row.get("situacao") or "").strip().upper())


def _ensure_hora_inclusao_item_col(cur) -> None:
    """Migração idempotente: coluna `hora_inclusao_item` em `pedido_venda_prod`
    (hora de inclusão do item, formato HH:MM:SS via CONVERT(...,108) — mesmo
    padrão já usado em `pedido_venda.hora_aberto`). `data_inclusao_item` já
    existe na tabela desde o legado; só a hora é nova.

    Adicionada sob demanda (checa `sys.columns` e só faz ALTER TABLE se
    faltar) porque este backend atende múltiplas empresas — um `servidor`+
    `banco` por conexão — sem um executor de migração central. Mesmo padrão
    já usado em `services/whatsapp/repository.py::ensure_tables`."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='hora_inclusao_item' AND Object_ID=Object_ID('pedido_venda_prod')) "
        "ALTER TABLE pedido_venda_prod ADD hora_inclusao_item NVARCHAR(8) NULL"
    )


def _ensure_qtd_pessoas_col(cur) -> None:
    """Migração idempotente: coluna `qtd_pessoas` em `pedido_venda` — usada
    pelo Painel de Pedidos (Mesa/Comanda/Balcão) pra dividir o valor total da
    conta na impressão. Campo genuinamente novo, sem precedente no legado
    (nunca existiu no VB6) — não é reaproveitamento de coluna existente,
    diferente do caso Cilindro. Mesmo padrão de
    `_ensure_hora_inclusao_item_col` acima. Pedido explícito do usuário,
    2026-07-17."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='qtd_pessoas' AND Object_ID=Object_ID('pedido_venda')) "
        "ALTER TABLE pedido_venda ADD qtd_pessoas INT NULL"
    )


# Tipo EFETIVO de um pedido, pra fins de classificação em coluna (Painel de
# Pedidos, web e KPDV — os dois só leem o campo já resolvido aqui, nenhum
# recalcula por conta própria) e de filtro por tipo. Cai pro tipo do
# CLIENTE (`c.cliente_forn`) só quando o pedido não tem tipo próprio
# (`p.tipo` NULL/0) — MESMA regra desde 2026-07-18 — EXCETO quando esse
# fallback resolveria pra "FIADO": nesse caso específico o fallback é
# recusado (fica `NULL`, fora de toda coluna), nunca classifica o pedido
# como Fiado. Corrigido 2026-08-11, achado ao vivo comparando com o VB6
# (que nunca teve o conceito de "Tipo do Pedido" — é feature só do app
# novo): um pedido antigo sem tipo próprio (ex.: aberto antes de
# 2026-07-18) caía em Fiado só porque o CLIENTE está cadastrado com
# `cliente_forn = Fiado` — categorização administrativa do cliente, não
# prova de que aquele pedido específico é uma venda fiado de verdade
# (mesma ressalva que "Campo 'Tipo' do Pedido Bar" em CLAUDE.md já fazia
# pra Mesa/Comanda: "vários clientes têm cliente_forn apontando pra Mesa/
# Comanda só por serem clientes frequentes categorizados assim
# administrativamente"). Mesa/Comanda/Balcão/Entrega mantêm o fallback
# normal — só Fiado tem essa implicação de crédito/cobrança que torna o
# fallback perigoso o bastante pra desabilitar.
TIPO_EFETIVO_PEDIDO_SQL = (
    "(CASE WHEN NULLIF(p.tipo, 0) IS NOT NULL THEN NULLIF(p.tipo, 0) "
    "WHEN (SELECT wtc.descricao FROM tipo_cliente wtc WHERE wtc.codigo = c.cliente_forn) = 'FIADO' THEN NULL "
    "ELSE c.cliente_forn END)"
)


def _resolve_tipo_pedido(fantasia: Optional[str], cliente_forn, tipo_solicitado: Optional[int]):
    """Resolve o valor final de `pedido_venda.tipo` (combobox "Tipo" do
    pedido — Mesa/Comanda/Balcão/Entrega, FK `tipo_cliente.codigo`),
    separado do tipo do CLIENTE (`cliente.cliente_forn`): um cliente
    Entrega pode virar um pedido lançado como Comanda na lista, sem mudar o
    tipo do cliente. EXCEÇÃO: cliente reservado — nome fantasia contendo
    "MESA"/"COMANDA"/"BALCÃO" (mesa/comanda/balcão físicos do
    estabelecimento) sempre sobrescreve com o próprio tipo do cliente,
    ignorando o que foi pedido/selecionado — não faz sentido uma "MESA 7"
    física virar um pedido de Entrega.

    Compartilhada entre Pedido Bar (`pedidos_service._save_pedido_sync`) e
    Pedido Geral/Completo (`pedido_completo_service._save_pedido_completo_sync`)
    — mesmo combobox, mesma regra, mesma tabela `pedido_venda`. Extraída
    pra cá 2026-07-20 (pedido explícito do usuário: "tente usar as mesmas
    funções para não replicar o mesmo código entre telas") a partir da
    regra original do Pedido Bar, 2026-07-18."""
    fantasia_up = (fantasia or "").strip().upper()
    cliente_reservado = any(k in fantasia_up for k in ("MESA", "COMANDA", "BALCÃO", "BALCAO"))
    return cliente_forn if cliente_reservado else tipo_solicitado


def _modulo_servicos_ativo(cur) -> bool:
    """True se o módulo "Serviço" está ligado em Configurações de Módulo do
    Sistema (controle_configuracao.servicos). Cadastro/consulta/movimentação
    de Serviço só é permitido com o módulo ativo — usado para bloquear a
    inclusão de item do tipo Serviço em Pedido/O.S. quando desligado."""
    cur.execute("SELECT TOP 1 servicos FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("servicos") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _exige_aprovacao_itens_os_ativo(cur) -> bool:
    """True se a empresa exige Autorização de Itens antes de baixar estoque
    na O.S. (`controle_aux.exige_aprovacao_itens_os` — migração de
    `FrmTraOsNew.frm`, aba "Autorização de Itens"). Confirmado pelo usuário,
    2026-08-01: com a flag ligada, o estoque só é reservado quando o item é
    AUTORIZADO, não mais na inclusão do item (default/flag desligada mantém
    o comportamento já existente — reserva na inclusão)."""
    cur.execute("SELECT TOP 1 exige_aprovacao_itens_os FROM controle_aux")
    row = cur.fetchone()
    val = row.get("exige_aprovacao_itens_os") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _exige_expedicao_itens_os_ativo(cur) -> bool:
    """True se a empresa exige Autorização de Expedição ANTES da
    Autorização de Itens em si (`controle_aux.exige_expedicao_itens_os`) —
    confirmado no rastreio de `FrmTraOsNew.frm`: quando ligada, um item só
    pode ser Autorizado depois de já ter sido Expedido. Expedição em si
    nunca movimenta estoque (só Autorização move, ver
    `_exige_aprovacao_itens_os_ativo`) — é um registro de picking/separação
    física do item no estoque, independente da flag de aprovação estar
    ligada ou não."""
    cur.execute("SELECT TOP 1 exige_expedicao_itens_os FROM controle_aux")
    row = cur.fetchone()
    val = row.get("exige_expedicao_itens_os") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _modulo_agenda_ativo(cur) -> bool:
    """True se "Clínica" OU "Assistência" está ligado (controle_configuracao.
    CLINICA / Assistencia) — mesmo princípio de `_modulo_servicos_ativo`.
    Os dois módulos ligam exatamente o mesmo comportamento de Agenda no
    Pedido Geral (mesma tela, mesmo fluxo — "é só chamar a tela", user-
    directed 2026-07-28): desdobramento de item de Serviço em N linhas
    agendáveis e o fluxo de Agendar/Layouts no Pedido Geral, mais a tela
    dedicada Agenda (`app/agenda.tsx`). Clínica é o segmento de Pedido
    (mutuamente exclusivo com Bar/Cilindro/Pedido de Venda/Metro Quadrado,
    ver SEGMENTOS_PEDIDO_EXCLUSIVOS); Assistência é o módulo de O.S. que já
    gateia OS/OS_COMP (par Oficina/Assistência) — independente dos
    segmentos de Pedido, uma empresa pode ter Assistência ligada junto com
    qualquer um deles. Nome anterior desta função: `_modulo_clinica_ativo`.
    Ver PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: Clínica
    (Agendamento)"."""
    cur.execute("SELECT TOP 1 CLINICA, Assistencia FROM controle_configuracao")
    row = cur.fetchone()
    if isinstance(row, dict):
        clinica = row.get("CLINICA")
        assistencia = row.get("Assistencia")
    else:
        clinica = row[0] if row else None
        assistencia = row[1] if row else None
    return bool(clinica) or bool(assistencia)


def _modulo_contratos_ativo(cur) -> bool:
    """True se o módulo "Contratos" está ligado (controle_configuracao.
    contratos) — mesmo princípio de `_modulo_servicos_ativo`. Cadastro/
    consulta/movimentação de todo o módulo Contratos (Tipo de Contrato,
    Tipo de Reajuste, Índices de Reajuste, Produtos Disponíveis, Contrato
    em si) só é permitido com o módulo ativo. Pedido explícito do usuário,
    2026-07-19."""
    cur.execute("SELECT TOP 1 contratos FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("contratos") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _modulo_gestor_projetos_ativo(cur) -> bool:
    """True se o módulo "Gestor de Projetos" está ligado
    (controle_configuracao.gestor_projetos) — mesmo princípio de
    `_modulo_contratos_ativo`. Coluna própria, não reaproveita
    Assistência/Oficina/etc. — ver PENDENCIAS.md > "Gestor de Projetos"."""
    cur.execute("SELECT TOP 1 gestor_projetos FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("gestor_projetos") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _modulo_bar_ativo(cur) -> bool:
    """True se o módulo "Bar" está ligado (controle_configuracao.Bar) —
    mesmo princípio de `_modulo_servicos_ativo`. Gateia o módulo
    Modificadores (Tabelas Auxiliares > Modificadores + o retrofit em
    Produto Completo/Serviços), que hoje só faz sentido pro Pedido Bar
    (único lugar com o seletor de modificador na venda, ver
    modificadores_service.py). Pedido explícito do usuário, 2026-07-23:
    "colocar o modificador ligado ao módulo de Pedido Bar. Só aparecerá
    para esse módulo ativo em configurações"."""
    cur.execute("SELECT TOP 1 Bar FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("Bar") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _modulo_curva_abc_ativo(cur) -> bool:
    """True se o módulo "Curva ABC" está ligado (controle_configuracao.
    Curva_abc) — mesmo princípio de `_modulo_servicos_ativo`. Gateia todo o
    submenu Transações > Compra (Pedido de Compra, Curva ABC e Estoques,
    Gestão de Compras/Ressuprimento, Cotação de Compra) — pedido explícito
    do usuário, 2026-07-19: "o módulo Compras deve ser habilitado em
    Configurações > Módulo Curva ABC" (o flag legado já existente pra essa
    área é literalmente chamado Curva_abc, não existe um flag "Compras"
    separado)."""
    cur.execute("SELECT TOP 1 Curva_abc FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("Curva_abc") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _modulo_metro_quadrado_ativo(cur) -> bool:
    """True se o módulo "Metro Quadrado" está ligado (controle_configuracao.
    metro_quadrado) — mesmo princípio de `_modulo_servicos_ativo`. Diferente
    dos outros módulos acima, este NÃO bloqueia a inclusão do item quando
    desligado — só decide se o item de um produto m²/ml/m³ (`pecas.uni`)
    entra pela precificação especial (`_area_preco`) ou pelo caminho normal
    (preço cheio, sem cálculo de área), réplica fiel do `Else` do legado
    (`AreaPreco`, `mdl_proc.bas`) — mesmo produto, mesmo pedido, o módulo é
    que decide o comportamento, não é uma trava de acesso. Ver
    PENDENCIAS.md > "Transações" > "Pedido Geral — Metro Quadrado"."""
    cur.execute("SELECT TOP 1 metro_quadrado FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("metro_quadrado") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


# Tipos de preço m² (`ListPrecos` do legado, `frmmanpedfor.frm:5881-5886`) —
# índice, rótulo, coluna de `pecas` de onde vem o preço, e a flag booleana
# de `controle_aux` que decide se aquele tipo aplica o piso de área mínima
# compartilhado (`metro_quadrado_minima_metragem`). Ordem = ordem do legado.
TIPOS_PRECO_M2 = [
    (0, "Padrão", "p_venda", "m2_area_minima_padrao"),
    (1, "Modelado Comum", "p_sugestao", "m2_area_minima_modelado"),
    (2, "Engenharia", "p_garantia", "m2_area_minima_engenharia"),
    (3, "Comum (S/Lapidação)", "p_sugerido", "m2_area_minima_comum_sem_lapidacao"),
    (4, "Modelado Engenharia", "preco_base", "m2_area_minima_modelado_engenharia"),
    (5, "Comum (C/Lapidação)", "preco_lista", "m2_area_minima_comum_lapidacao"),
]


def _config_m2(cur) -> dict:
    """Lê de uma vez os campos de `controle_aux` que a precificação m² usa —
    as 6 flags de área mínima por tipo de preço, o piso de área mínima
    compartilhado (`metro_quadrado_minima_metragem`, default 0,25 igual ao
    legado quando a coluna vem 0/NULL — `mdl_proc.bas:7263`), e o flag de
    "controla cabeça de chapa" (arredondamento pra tamanho padrão de chapa
    de vidro). Configuração já existia pronta em Controle do Sistema antes
    desta feature (`controle-sistema.tsx`) — só nunca tinha sido lida por
    nenhuma tela de venda."""
    cur.execute(
        "SELECT m2_area_minima_padrao, m2_area_minima_modelado, m2_area_minima_engenharia, "
        "m2_area_minima_modelado_engenharia, m2_area_minima_comum_lapidacao, "
        "m2_area_minima_comum_sem_lapidacao, metro_quadrado_minima_metragem, "
        "vidro_controla_cabeca_chapa FROM controle_aux"
    )
    row = cur.fetchone() or {}
    minima = float(row.get("metro_quadrado_minima_metragem") or 0)
    return {
        "m2_area_minima_padrao": bool(row.get("m2_area_minima_padrao")),
        "m2_area_minima_modelado": bool(row.get("m2_area_minima_modelado")),
        "m2_area_minima_engenharia": bool(row.get("m2_area_minima_engenharia")),
        "m2_area_minima_modelado_engenharia": bool(row.get("m2_area_minima_modelado_engenharia")),
        "m2_area_minima_comum_lapidacao": bool(row.get("m2_area_minima_comum_lapidacao")),
        "m2_area_minima_comum_sem_lapidacao": bool(row.get("m2_area_minima_comum_sem_lapidacao")),
        "metro_quadrado_minima_metragem": minima if minima > 0 else 0.25,
        "vidro_controla_cabeca_chapa": bool(row.get("vidro_controla_cabeca_chapa")),
    }


def _trunca3(v) -> float:
    """Réplica de `trunca3` (legado) — trunca (não arredonda) em 3 casas
    decimais. Mesmo idioma já usado por `_trunca2` em `inventario_service.py`
    (`Decimal.quantize(..., ROUND_DOWN)`), só com 3 casas em vez de 2."""
    from decimal import ROUND_DOWN, Decimal
    return float(Decimal(str(v)).quantize(Decimal("0.001"), rounding=ROUND_DOWN))


def _arredonda_pbox(num: float, modo_arredondamento) -> float:
    """Réplica de `ArredondaPBox` (`mdl_proc.bas:11969`) — arredonda uma
    dimensão (comprimento ou largura) antes de calcular a área m², usada só
    no modo "controla cabeça de chapa" (`vidro_controla_cabeca_chapa`).

    Modo 10 (usado quando o produto controla número de série — ver
    `_area_preco`): trunca em 1 casa decimal e soma 0,1 se houver qualquer
    resto além dela.
    Outros modos (o Pedido Geral sempre usa modo 5, ver `_area_preco`):
    arredonda pra a centésima ".5" mais próxima por cima quando o resto
    (além da 1ª casa decimal) está entre 0,001 e 0,499; arredonda pra 1
    casa decimal quando o resto está entre 0,501 e 0,999; senão (resto
    exatamente 0 ou 0,500) trunca em 2 casas."""
    num = float(num or 0)
    # Format(num, "###,###,##0.0000") — sempre 4 casas decimais.
    texto = f"{num:.4f}"
    inteiro, decimais = texto.split(".")  # decimais sempre tem 4 dígitos
    # Right(Decimais, 3) — os 3 últimos dos 4 dígitos decimais (tudo além
    # da casa das décimas).
    resto3 = int(decimais[1:])
    tenths = f"{inteiro}.{decimais[0]}"  # Left(temp, Len(temp)-3) — trunca em 1 casa

    if int(modo_arredondamento or 0) == 10:
        base = float(tenths) + 0.1 if resto3 > 0 else float(tenths)
    else:
        if 0 < resto3 < 500:
            base = float(f"{tenths}5")  # concatena "5" na casa das centésimas
        elif 500 < resto3 <= 999:
            base = round(float(texto), 1)  # Format(temp, "0.0") — arredonda p/ 1 casa
        else:  # resto3 == 0 ou == 500 exatos — trunca em 2 casas, já fica em X,X5 nesse caso
            base = float(f"{inteiro}.{decimais[:2]}")
    return round(base, 4)


def _area_preco(
    comprimento: float, largura: float, area_minima_ativa: bool,
    modo_arredondamento, comprimento_chapa: float, largura_chapa: float,
    vidro_controla_cabeca_chapa: bool, metro_quadrado_minima_metragem: float,
) -> float:
    """Réplica de `AreaPreco` (`mdl_proc.bas:12004`) — calcula a área de
    venda (m²/ml/m³) de um item, usada como multiplicador do preço unitário
    escolhido (ver decisão de arquitetura em PENDENCIAS.md > "Transações" >
    "Pedido Geral — Metro Quadrado": aqui só devolvemos a área, quem chama
    dobra ela dentro do preço unitário — o app não replica a multiplicação
    de 3 fatores espalhada pelo legado).

    `comprimento`/`largura` = 0 (produto sem dimensão informada, ex. item
    controlado por número de série) sempre devolve 1 (regra do legado —
    nesse caso a "área" não participa do cálculo).

    Sem "controla cabeça de chapa": trunca(arredonda(comprimento) ×
    arredonda(largura), 3 casas).

    Com "controla cabeça de chapa": se comprimento_chapa/largura_chapa
    divergem de comprimento/largura, usa os valores de chapa em vez dos
    digitados (e pula o arredondamento se a chapa já bate num tamanho
    padrão — 1,8/2,4/3,21m, réplica exata do legado).

    Em ambos os casos, se `area_minima_ativa` (flag do tipo de preço
    escolhido) e a área calculada é menor que o piso compartilhado
    (`metro_quadrado_minima_metragem`), a área sobe pro piso."""
    comprimento = float(comprimento or 0)
    largura = float(largura or 0)
    if comprimento == 0 or largura == 0:
        return 1.0

    if vidro_controla_cabeca_chapa:
        m1, m2 = comprimento, largura
        comprimento_chapa = float(comprimento_chapa or 0)
        largura_chapa = float(largura_chapa or 0)
        usa_chapa = comprimento != comprimento_chapa or largura != largura_chapa
        if usa_chapa:
            m1, m2 = comprimento_chapa, largura_chapa
            cm1 = m1 if m1 in (1.8, 2.4, 3.21) else _arredonda_pbox(m1, modo_arredondamento)
            cm2 = m2 if m2 in (1.8, 2.4, 3.21) else _arredonda_pbox(m2, modo_arredondamento)
        else:
            cm1 = _arredonda_pbox(m1, modo_arredondamento)
            cm2 = _arredonda_pbox(m2, modo_arredondamento)
        area = _trunca3(cm1 * cm2)
    else:
        area = _trunca3(_arredonda_pbox(comprimento, modo_arredondamento) * _arredonda_pbox(largura, modo_arredondamento))

    if area_minima_ativa and area < metro_quadrado_minima_metragem:
        area = metro_quadrado_minima_metragem
    return area


def _area_estoque(comprimento, largura) -> float:
    """Réplica de `AreaEstoque` (`mdl_proc.bas:12103`) — área BRUTA usada
    pra movimentar estoque de um item m² (sem arredondamento de
    `ArredondaPBox` nem piso de área mínima, propositalmente diferente de
    `_area_preco`: o estoque físico consumido é a área real da peça, não a
    área "faturável" com o piso mínimo aplicado). `comprimento`/`largura`
    0 devolve 1 (mesma regra do legado — sem dimensão, não participa do
    cálculo de área)."""
    comprimento = float(comprimento or 0)
    largura = float(largura or 0)
    if comprimento == 0 or largura == 0:
        return 1.0
    return _trunca3(comprimento * largura)


def _resolve_produto(cur, codigo: str) -> Optional[dict]:
    """Procura primeiro em pecas, depois em servicos. Retorna dados padrão do item."""
    cur.execute(
        "SELECT codigo_int AS codigo, descricao, codigo_fab, p_venda AS valor, uni, "
        "       custo_reposicao, tipo_peca FROM pecas WHERE codigo_int=%s",
        (codigo,),
    )
    r = cur.fetchone()
    if r:
        return {
            "tipo": "P",
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo_fab") or "").strip(),
            "valor": float(r.get("valor") or 0),
            "unidade": (r.get("uni") or "").strip()[:2] or "UN",
            "custo": float(r.get("custo_reposicao") or 0),
            # Finalidade (Cozinha/Bebidas/Materiais, etc.) — usada pra decidir
            # impressão automática de item por grupo de produto (ver
            # project_impressao_automatica_finalidade). None se não definida.
            "tipo_peca": int(r["tipo_peca"]) if r.get("tipo_peca") is not None else None,
        }
    cur.execute(
        "SELECT codigo, descricao, valor_hora AS valor FROM servicos WHERE codigo=%s",
        (codigo,),
    )
    r = cur.fetchone()
    if r:
        valor = float(r.get("valor") or 0)
        return {
            "tipo": "S",
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo") or "").strip(),
            "valor": valor,
            "unidade": "HR",
            "custo": valor,  # serviço: custo = valor_hora (regra de negócio)
            "tipo_peca": None,  # Finalidade é coluna só de pecas — serviço nunca tem.
        }
    return None



def _resolve_produto_completo(cur, codigo: str) -> Optional[dict]:
    """Cadeia de resolução mais rica usada pelo Pedido Completo (web),
    espelhando `frmmanpedfor.frm`: Serviço (se prefixo 'S') -> pecas.codigo_fab
    -> pecas.codigo_int -> pecas.codigo_bar -> CODBARRA_AUXILIAR (códigos de
    barra secundários) -> Serviço (sem prefixo, fallback final).

    Deliberadamente uma função NOVA, não uma alteração de `_resolve_produto`
    — aquela é usada pelo fluxo rápido mobile (Pedido/O.S.) já em uso, e essa
    cadeia mais rica não deve mudar o comportamento de telas já em produção.
    Ver PENDENCIAS.md > "Transações" > "Pedido Completo" pro rastreio de onde
    essa cadeia vem (`Campo1_LostFocus`/`Campo_KeyPress` em frmmanpedfor.frm).
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return None

    if codigo.upper().startswith("S"):
        cur.execute("SELECT codigo, descricao, valor_hora AS valor, cod_icms FROM servicos WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        if r:
            valor = float(r.get("valor") or 0)
            return {
                "tipo": "S", "codigo": (r.get("codigo") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "cod_fab": (r.get("codigo") or "").strip(), "valor": valor,
                "unidade": "HR", "custo": valor, "controla_num_serie": False,
                "cod_icms": (r.get("cod_icms") or "").strip(),
                "peso_variado": False,  # serviço nunca é vendido por peso
            }

    for coluna in ("codigo_fab", "codigo_int", "codigo_bar"):
        cur.execute(
            f"SELECT codigo_int AS codigo, descricao, codigo_fab, p_venda AS valor, uni, "
            f"       custo_reposicao, controla_num_serie, aceita_desconto, cod_icms, peso_variado "
            f"FROM pecas WHERE {coluna}=%s",
            (codigo,),
        )
        r = cur.fetchone()
        if r:
            return _linha_peca_completo(r)

    cur.execute(
        "SELECT p.codigo_int AS codigo, p.descricao, p.codigo_fab, p.p_venda AS valor, p.uni, "
        "       p.custo_reposicao, p.controla_num_serie, p.aceita_desconto, p.cod_icms, p.peso_variado "
        "FROM CODBARRA_AUXILIAR cb JOIN pecas p ON p.codigo_int = cb.codigo_int WHERE cb.codigo_bar=%s",
        (codigo,),
    )
    r = cur.fetchone()
    if r:
        return _linha_peca_completo(r)

    cur.execute("SELECT codigo, descricao, valor_hora AS valor, cod_icms FROM servicos WHERE codigo=%s", (codigo,))
    r = cur.fetchone()
    if r:
        valor = float(r.get("valor") or 0)
        return {
            "tipo": "S", "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo") or "").strip(), "valor": valor,
            "unidade": "HR", "custo": valor, "controla_num_serie": False,
            "cod_icms": (r.get("cod_icms") or "").strip(),
        }
    return None


def _linha_peca_completo(r: dict) -> dict:
    return {
        "tipo": "P",
        "codigo": (r.get("codigo") or "").strip(),
        "descricao": (r.get("descricao") or "").strip(),
        "cod_fab": (r.get("codigo_fab") or "").strip(),
        "valor": float(r.get("valor") or 0),
        "unidade": (r.get("uni") or "").strip()[:2] or "UN",
        "custo": float(r.get("custo_reposicao") or 0),
        "controla_num_serie": bool(r.get("controla_num_serie")),
        "aceita_desconto": r.get("aceita_desconto") is None or bool(r.get("aceita_desconto")),
        "cod_icms": (r.get("cod_icms") or "").strip(),
        # "Vendido por peso" — gatilho de leitura ao vivo da Balança Toledo
        # (KPDV) e do código de barras de peso variável (ver
        # decode_codigo_barras_peso_variavel abaixo). Campo já existia no
        # cadastro (Produto Completo, "Peso Variado"), só não era lido em
        # nenhum fluxo de venda até agora.
        "peso_variado": bool(r.get("peso_variado")),
    }


# Prefixo do código de barras de peso variável (posição 1) e posições dos
# campos código do produto / peso em gramas — convenção brasileira mais
# citada pra etiqueta impressa por balança de pré-pesagem (2 + 5 dígitos de
# código + 5 dígitos de peso em gramas + dígito verificador EAN-13 padrão).
# Constantes isoladas de propósito: NÃO validado ainda contra uma etiqueta
# real impressa por balança Toledo (sem hardware/etiqueta física disponível
# nesta sessão) — ver PENDENCIAS.md > "KPDV" > "Balança Toledo + Pré-Pesagem"
# pro resumo da pesquisa e o que falta confirmar. Ajustar aqui, não espalhado
# pelo resto da função, assim que tivermos uma etiqueta real pra comparar.
PESO_VARIAVEL_PREFIXO = "2"
_POS_CODIGO_PRODUTO = slice(1, 6)
_POS_PESO_GRAMAS = slice(6, 11)


def _ean13_checksum_valido(codigo13: str) -> bool:
    """Dígito verificador EAN-13 padrão (mod-10, pesos alternados 1/3) — este
    algoritmo é genérico do padrão EAN/GTIN, não é proprietário Toledo."""
    digitos = [int(c) for c in codigo13]
    soma = sum(d if i % 2 == 0 else d * 3 for i, d in enumerate(digitos[:12]))
    dv = (10 - (soma % 10)) % 10
    return dv == digitos[12]


def decode_codigo_barras_peso_variavel(codigo: str) -> Optional[dict]:
    """Decodifica um código de barras EAN-13 de peso variável — etiqueta
    impressa por uma balança de pré-pesagem (ver `PESO_VARIAVEL_PREFIXO`/
    `_POS_CODIGO_PRODUTO`/`_POS_PESO_GRAMAS` acima pro aviso de confiança).
    Devolve `None` se `codigo` não bater com o formato (tamanho, prefixo ou
    dígito verificador) — nesse caso o chamador trata como um código normal
    (busca direta por `codigo_int`/`codigo_fab`/`codigo_bar`, fluxo de sempre).
    """
    codigo = (codigo or "").strip()
    if len(codigo) != 13 or not codigo.isdigit():
        return None
    if codigo[0] != PESO_VARIAVEL_PREFIXO:
        return None
    if not _ean13_checksum_valido(codigo):
        return None
    peso_gramas = int(codigo[_POS_PESO_GRAMAS])
    return {
        "codigo_produto": codigo[_POS_CODIGO_PRODUTO],
        "peso_kg": round(peso_gramas / 1000, 3),
    }


def _preco_promocional(cur, codigo_int: str, qtd: float) -> Optional[dict]:
    """Resolve o preço promocional aplicável (`pecas_promocao` — "Variações
    de Preços" no Cadastro de Produtos, ver produto_completo_service.py) pro
    produto+quantidade+momento atual, respeitando os critérios opcionais e
    combináveis de dias da semana/período de data/período de hora (todos em
    branco/NULL = sem restrição nesse critério, mesma regra documentada em
    CLAUDE.md > "Produto Completo").

    Usada ao incluir item em qualquer Pedido (Bar/Geral e futuros, via
    `usePedidoItens` no frontend — pedido explícito do usuário, 2026-07-30).
    Sem precedente no legado pra escolher entre várias linhas cujo período
    bate ao mesmo tempo — decisão desta implementação: prefere a de maior
    `qtd` (maior faixa de quantidade atingida), mesmo critério de tier já
    usado em Preço por Quantidade (`pecas_preco_qtd`). Retorna None se
    nenhuma linha bate (produto sem promoção cadastrada, ou fora do
    período/dia/hora de todas as cadastradas)."""
    from services.produto_completo_service import _ensure_promocao_periodo_cols
    _ensure_promocao_periodo_cols(cur)
    cur.execute("SELECT GETDATE() AS agora")
    agora = cur.fetchone()["agora"]
    dow = str((agora.weekday() + 1) % 7)  # 0=domingo..6=sábado, mesmo esquema do frontend (DIAS_SEMANA_LABELS)
    hora_atual = agora.strftime("%H:%M")
    data_atual = agora.date()
    cur.execute(
        "SELECT p_venda, codigo_promocao, descricao_promocao, dias_semana, "
        "data_inicio, data_fim, hora_inicio, hora_fim "
        "FROM pecas_promocao WHERE codigo_int=%s AND qtd<=%s ORDER BY qtd DESC",
        (codigo_int, qtd),
    )
    for r in cur.fetchall():
        dias = (r.get("dias_semana") or "").strip()
        if dias and dow not in [d.strip() for d in dias.split(",") if d.strip()]:
            continue
        di, df = r.get("data_inicio"), r.get("data_fim")
        if di and data_atual < di:
            continue
        if df and data_atual > df:
            continue
        hi = (r.get("hora_inicio") or "").strip()
        hf = (r.get("hora_fim") or "").strip()
        if hi and hora_atual < hi:
            continue
        if hf and hora_atual > hf:
            continue
        return {
            "p_venda": float(r["p_venda"]),
            "codigo_promocao": (r.get("codigo_promocao") or "").strip(),
            "descricao_promocao": (r.get("descricao_promocao") or "").strip(),
        }
    return None


def _kit_componentes(cur, codigo_principal: str) -> list:
    """Componentes de um kit/produto composto (`produtos_compostos.principal`).

    Mesma tabela já usada por Serviços > Previsão de Produtos
    (`produtos_compostos_service.py`, ported de FrmManReceita.frm) — no
    legado essa tabela serve os dois propósitos (previsão de material em
    Serviço, e expansão de kit em Pedido); aqui é o segundo uso, novo nesta
    migração. `produtos_compostos` não tem coluna de custo própria — o custo
    de cada componente vem do próprio cadastro do produto (`pecas.
    custo_reposicao`), resolvido via `_resolve_produto_completo`.
    """
    cur.execute(
        "SELECT vinculado, qtd, valor_no_kit, descricao_no_kit FROM produtos_compostos WHERE principal=%s",
        (codigo_principal,),
    )
    return [dict(r) for r in cur.fetchall()]


def _is_peca(cur, codigo: str) -> bool:
    """True se o código pertence a uma peça (movimenta estoque)."""
    cur.execute("SELECT 1 AS ok FROM pecas WHERE codigo_int=%s", (codigo,))
    return cur.fetchone() is not None


def _mover_estoque(cur, codigo: str, delta_qtd: float, campo_reservado: str) -> None:
    """Movimenta o estoque de uma PEÇA dentro da transação corrente.

    Efeito: pecas.qtd -= delta_qtd ; pecas.<campo_reservado> += delta_qtd.
    `campo_reservado` deve ser 'reservado' (Pedido) ou 'reservado_os' (O.S.).
    Não faz nada para serviços/itens inexistentes. delta_qtd pode ser negativo
    (estorno ao remover/reduzir item).
    """
    if campo_reservado not in ("reservado", "reservado_os"):
        raise ValueError("campo_reservado inválido")
    if not delta_qtd or not _is_peca(cur, codigo):
        return
    cur.execute(
        f"UPDATE pecas SET qtd = ISNULL(qtd,0) - %s, "
        f"{campo_reservado} = ISNULL({campo_reservado},0) + %s "
        f"WHERE codigo_int=%s",
        (delta_qtd, delta_qtd, codigo),
    )


# Forma de Pagamento (FrmForPag.frm + FormaPagamentoDAV.bas) — tela
# genérica no legado, reaproveitada por Pedido, O.S. e Agenda via uma
# struct global só (`Type_FormaPagPedOS` — Tipo/Documento/Situacao/valor/
# Forma_Padrao). Portamos o mesmo desenho: um "tipo de DAV" central
# (DAV_PED/DAV_OS/DAV_AGE) mapeando pra onde os dados vivem — mesmo padrão
# já usado em `gestor_documentos_service.py` (`GRUPO_*`/`_JUNCAO`) pra grupo
# de anexos.
DAV_PED = "PED"
DAV_OS = "OS"
# Agenda (agendamento avulso, sem vir de Pedido/O.S. — Fase B Clínica,
# 2026-07-28) — só usa o caminho automático de 1 forma (nunca a grade
# manual completa), por isso as tabelas próprias (`_ensure_agenda_forma_
# pag_tables` abaixo) têm só as colunas que `_cadastra_forma_automatica`
# de fato usa, não um espelho 1:1 de `pedido_venda_*`.
DAV_AGE = "AGE"

# tipo de DAV -> prefixo das tabelas de forma de pagamento + coluna FK.
DAV_CONFIG: dict[str, dict[str, str]] = {
    DAV_PED: {"prefixo": "pedido_venda_", "fk": "pedido_venda"},
    DAV_OS: {"prefixo": "os_", "fk": "os"},
    DAV_AGE: {"prefixo": "agenda_", "fk": "agenda"},
}

# tipo de forma de pagamento (`forma_pagamento.tipo`) -> sufixo de tabela +
# coluna de valor + coluna de vencimento (None = sem vencimento). Sufixo e
# colunas são idênticos entre pedido_venda_* e os_* (mesmo schema, só o
# prefixo/FK mudam) — confirmado ao vivo em `gibanweb.database.windows.net/
# BDREACTAPP` antes de escrever este código.
FORMA_PAG_SUFIXO_TIPO: dict[str, str] = {
    "DI": "dinheiro", "CH": "cheque", "CC": "cartao", "CD": "debito",
    "DU": "duplicata", "TI": "ticket", "VA": "vale", "FI": "financiado",
}
FORMA_PAG_VALOR_COL: dict[str, str] = {
    "DI": "valor_pago", "CH": "valor", "CC": "valor", "CD": "valor",
    "DU": "valor_pag", "TI": "valor", "VA": "valor", "FI": "valor_pag",
}
FORMA_PAG_VENC_COL: dict[str, Optional[str]] = {
    "DI": None, "CH": "bom_para", "CC": "bom_para", "CD": "bom_para",
    "DU": "data_venc", "TI": None, "VA": "bom_para", "FI": "data_venc",
}


def _ensure_agenda_forma_pag_tables(cur) -> None:
    """Migração idempotente (`IF NOT EXISTS ... CREATE TABLE`, mesmo padrão
    de `_ensure_hora_inclusao_item_col` — este backend atende múltiplas
    empresas sem executor de migração central): cria as 8 tabelas de forma
    de pagamento da Agenda (`agenda_dinheiro`, `agenda_cheque`, ...) usadas
    pelo Faturar avulso (Fase B — Clínica, 2026-07-28). Só com as colunas
    que o caminho automático de 1 forma (`_cadastra_forma_automatica`)
    realmente usa (`sequencia`/`agenda`/`forma_pag`/valor/vencimento) — a
    Agenda nunca expõe a grade manual completa de múltiplas formas que
    Pedido/O.S. têm, então não replica colunas extras só usadas por ela."""
    for tipo_forma, valor_col in FORMA_PAG_VALOR_COL.items():
        tabela = DAV_CONFIG[DAV_AGE]["prefixo"] + FORMA_PAG_SUFIXO_TIPO[tipo_forma]
        venc_col = FORMA_PAG_VENC_COL[tipo_forma]
        colunas_extra = f", {venc_col} DATE" if venc_col else ""
        cur.execute(
            f"IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = '{tabela}') "
            f"CREATE TABLE {tabela} ("
            f"sequencia INT IDENTITY(1,1) PRIMARY KEY, "
            f"agenda INT NOT NULL, "
            f"forma_pag NVARCHAR(10) NOT NULL, "
            f"{valor_col} DECIMAL(18,2) NOT NULL DEFAULT 0"
            f"{colunas_extra})"
        )


def _controla_revisao_os_ativo(cur) -> bool:
    """True se a empresa controla Revisão programada de O.S.
    (`controle_aux.ControlaRevisaoOS`) — migração de `FrmTraOsNew.frm`,
    campo "Doc. Origem". Com a flag ligada, O.S. do tipo Revisão só aceita
    outra O.S. (nunca Pedido) como origem, e exige uma data de revisão
    programada disponível na O.S. de origem (`osrevisao`). Ver
    `_validar_doc_origem` abaixo."""
    cur.execute("SELECT TOP 1 ControlaRevisaoOS FROM controle_aux")
    row = cur.fetchone()
    val = row.get("ControlaRevisaoOS") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _exige_os_original_garantia_ativo(cur) -> bool:
    """True se a empresa exige Doc. Origem (O.S. OU Pedido) em O.S. do tipo
    Garantia — ou Revisão, quando `_controla_revisao_os_ativo` está
    desligada (`controle_aux.EXIGE_OS_ORIGINAL_GARANTIA`). Ver
    `_validar_doc_origem` abaixo."""
    cur.execute("SELECT TOP 1 EXIGE_OS_ORIGINAL_GARANTIA FROM controle_aux")
    row = cur.fetchone()
    val = row.get("EXIGE_OS_ORIGINAL_GARANTIA") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _ensure_os_doc_origem_cols(cur) -> None:
    """Migração idempotente: `os.Tipo_Doc_Original`/`.VALIDOU_GARANTIA`/
    `.QtdRevisoes` — `OS_ORIGINAL` já existe (NOT NULL, sempre gravada,
    default 0 até esta migração). Mesmo padrão de `_ensure_qtd_pessoas_col`.
    Ver "O.S. Completa" > "Doc. Origem / Revisão Programada" em
    PENDENCIAS.md."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='Tipo_Doc_Original' AND Object_ID=Object_ID('os')) "
        "ALTER TABLE os ADD Tipo_Doc_Original NVARCHAR(1) NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='VALIDOU_GARANTIA' AND Object_ID=Object_ID('os')) "
        "ALTER TABLE os ADD VALIDOU_GARANTIA BIT NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='QtdRevisoes' AND Object_ID=Object_ID('os')) "
        "ALTER TABLE os ADD QtdRevisoes INT NULL"
    )


def _ensure_os_forma_pagamento_garantia_col(cur) -> None:
    """Migração idempotente: `os.forma_pagamento_garantia` — forma de
    pagamento usada só pra faturar o bloco de itens Garantia/Interno/
    Contrato (`os_produto.situacao<>0`), separado do bloco Cliente paga
    (`.forma_pagamento`, já existente). Ver "Bifurcação de faturamento
    Garantia×Cliente" em PENDENCIAS.md > "O.S. Completa"."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='forma_pagamento_garantia' AND Object_ID=Object_ID('os')) "
        "ALTER TABLE os ADD forma_pagamento_garantia NVARCHAR(3) NULL"
    )


def _ensure_exige_chassi_os_col(cur) -> None:
    """Migração idempotente: `controle.exige_chassi_os` (bit) — decide se o
    Chassi é obrigatório ao gravar uma O.S. do segmento Oficina. Avisado
    pela equipe VB6, 2026-08-17 — coluna nova no legado, ainda não existe
    em nenhuma instalação até esta data. Ver `_chassi_obrigatorio_ok`
    acima nesse mesmo módulo pra regra de enforcement."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='exige_chassi_os' AND Object_ID=Object_ID('controle')) "
        "ALTER TABLE controle ADD exige_chassi_os BIT NULL"
    )


def _ensure_osrevisao_table(cur) -> None:
    """Migração idempotente: tabela `osrevisao` (datas de revisão
    programada de uma O.S. — `sequencia` PK, `os` = O.S. dona da data,
    `data`, `osrevisao` = 0/NULL enquanto disponível, ou o código da O.S.
    que consumiu essa data ao ser aberta como Revisão dessa origem).
    Confirmada como parte do schema legado real (rastreio de
    `Revenda\\FrmTraOsNew.frm`) — instalações antigas devem já ter essa
    tabela; `IF NOT EXISTS` cobre as que não têm."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'osrevisao') "
        "CREATE TABLE osrevisao (sequencia INT IDENTITY(1,1) PRIMARY KEY, "
        "os INT NOT NULL, data DATE NOT NULL, osrevisao INT NULL)"
    )


def _validar_doc_origem(
    cur, codigo, cliente, tipo_os_desc: str, os_original: int, tipo_doc_original: str, autorizado_por,
):
    """Validação cruzada de OS/Pedido de origem pra O.S. do tipo Garantia/
    Revisão — réplica de `Command2_Click` em `FrmTraOsNew.frm`, linhas
    9737-9982 (rastreio completo em PENDENCIAS.md > "O.S. Completa" >
    "Doc. Origem / Revisão Programada").

    Dois ramos MUTUAMENTE EXCLUSIVOS, decididos pelo texto de
    `tipo_os_desc` (substring, sem acento — mesmo critério do legado, não
    dá pra usar um código fixo porque o cadastro `tipo_os` é livre):
      • Ramo "revisao": tipo contém "REVISÃO"/"REVISAO" E
        `_controla_revisao_os_ativo` — só aceita O.S. como origem (nunca
        Pedido), e exige uma data de revisão programada disponível na O.S.
        de origem (`osrevisao`).
      • Ramo "garantia": tipo contém "GARANTIA" (ou "REVISÃO"/"REVISAO"
        quando o ramo acima não se aplicou) E
        `_exige_os_original_garantia_ativo` — aceita O.S. OU Pedido de
        Venda como origem.
    Se nenhum ramo se aplica, não há nada a validar (retorna ok=True,
    validou_garantia=False, sem tocar o campo).

    Retorna `(ok, validou_garantia, tipo_doc_original_final, mensagem_erro)`.
    `tipo_doc_original_final` é sempre "O" no ramo Revisão (a tela nem
    deixa escolher Pedido nesse caso) — o chamador deve gravar esse valor,
    não o que veio cru na requisição.

    Bypass por "senha superior": se a validação falhar mas
    `autorizado_por` vier preenchido (não-vazio), a gravação é liberada
    mesmo assim — mesmo padrão já usado em `AgendarItemRequest.
    autorizado_por`/`AuthorizationSlide` (o frontend já validou a senha de
    gerente/supervisor/master antes de reenviar; o backend não reverifica,
    só confia no sinal e deixa o CHAMADOR registrar a auditoria)."""
    desc = (tipo_os_desc or "").upper()
    eh_revisao = "REVIS" in desc  # cobre REVISÃO/REVISAO, com ou sem acento
    eh_garantia = "GARANTIA" in desc

    if eh_revisao and _controla_revisao_os_ativo(cur):
        ramo = "revisao"
        tipo_doc_original = "O"
    elif (eh_garantia or eh_revisao) and _exige_os_original_garantia_ativo(cur):
        ramo = "garantia"
    else:
        return True, False, tipo_doc_original, None

    # Já validado antes com os MESMOS valores (reedição sem mudar Doc.
    # Origem) — não repete a validação nem pede senha de novo.
    if codigo:
        cur.execute(
            "SELECT os_original, tipo_doc_original, validou_garantia FROM os WHERE codigo=%s", (codigo,),
        )
        ex = cur.fetchone()
        if ex and ex.get("validou_garantia"):
            os_original_atual = int(ex.get("os_original") or 0)
            tipo_atual = (ex.get("tipo_doc_original") or "").strip().upper()
            if os_original_atual == int(os_original or 0) and tipo_atual == tipo_doc_original:
                return True, True, tipo_doc_original, None

    erro = None
    if ramo == "revisao":
        if not os_original:
            erro = "Para O.S.'s do Tipo Revisão, deve-se obrigatoriamente preencher o Número da O.S. de origem!"
        elif codigo and int(os_original) == int(codigo):
            erro = "O número da O.S. de origem não pode ser o mesmo número da O.S. de revisão!"
        else:
            cur.execute("SELECT cliente, situacao FROM os WHERE codigo=%s", (os_original,))
            origem = cur.fetchone()
            if not origem:
                erro = "O.S. de origem não encontrada!"
            elif int(origem.get("cliente") or 0) != int(cliente or 0):
                erro = "O número da O.S. de origem não é do mesmo cliente da O.S. de revisão!"
            elif (origem.get("situacao") or "").strip().upper() != "PG":
                erro = "A O.S. de origem da revisão não está faturada!"
            else:
                ja_vinculada = False
                if codigo:
                    cur.execute("SELECT TOP 1 1 AS ok FROM osrevisao WHERE osrevisao=%s", (codigo,))
                    ja_vinculada = cur.fetchone() is not None
                if not ja_vinculada:
                    cur.execute(
                        "SELECT TOP 1 1 AS ok FROM osrevisao WHERE os=%s AND ISNULL(osrevisao,0)=0", (os_original,),
                    )
                    if not cur.fetchone():
                        erro = "O.S. de origem não tem datas de revisão disponíveis!"
    else:  # garantia
        if not os_original:
            erro = "Para O.S.'s do Tipo Garantia, deve-se obrigatoriamente preencher o Número do Documento de origem!"
        elif codigo and int(os_original) == int(codigo) and tipo_doc_original == "O":
            erro = "O número da O.S. de origem não pode ser o mesmo número do Documento de garantia!"
        elif tipo_doc_original == "O":
            cur.execute("SELECT cliente, situacao FROM os WHERE codigo=%s", (os_original,))
            origem = cur.fetchone()
            if not origem:
                erro = "O.S. de origem não encontrada!"
            elif int(origem.get("cliente") or 0) != int(cliente or 0):
                erro = "O número da O.S. de origem não é do mesmo cliente da O.S. de garantia!"
            elif (origem.get("situacao") or "").strip().upper() != "PG":
                erro = "A O.S. de origem da garantia não está faturada!"
        else:
            cur.execute("SELECT cliente, situacao FROM pedido_venda WHERE pedido=%s", (os_original,))
            origem = cur.fetchone()
            if not origem:
                erro = "Pedido de Venda não encontrado!"
            elif int(origem.get("cliente") or 0) != int(cliente or 0):
                erro = "O número do Pedido de Venda informado como origem da garantia não é do mesmo cliente da O.S. de garantia!"
            elif (origem.get("situacao") or "").strip().upper() != "PG":
                erro = "O Pedido de Venda informado como origem da garantia não está faturado!"

    if not erro:
        return True, True, tipo_doc_original, None
    if (autorizado_por or "").strip():
        return True, True, tipo_doc_original, None
    return False, False, tipo_doc_original, erro


def _ensure_agenda_os_table(cur) -> None:
    """Migração idempotente: tabela ponte `AGENDA_OS(CODAGENDA, CODOS)` —
    equivalente de `AGENDA_PEDIDO` pro lado da O.S. (`CODOS` guarda o
    `os_produto.cod_os_prod` do ITEM, não o número da O.S. — mesma
    convenção de `AGENDA_PEDIDO.CODPEDIDO` guardar o `codauto` do item, não
    o pedido). Confirmada como parte do schema legado (rastreio de
    `Revenda\\FrmTraOsNew.frm`/`FrmOsProdutoNV2.frm`, ver PENDENCIAS.md >
    "O.S. Completa" > "Agendar item de Serviço") — instalações antigas
    devem já ter essa tabela; `IF NOT EXISTS` cobre as que não têm (mesmo
    padrão de `_ensure_agenda_forma_pag_tables`, sem executor de migração
    central)."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'AGENDA_OS') "
        "CREATE TABLE AGENDA_OS (CODAGENDA INT NOT NULL, CODOS INT NOT NULL)"
    )


def _ensure_os_produto_agenda_cols(cur) -> None:
    """Migração idempotente: `os_produto.data_servico`/`.executor_agenda` —
    espelham as mesmas colunas já usadas em `pedido_venda_prod` pra cachear
    o último agendamento do item (ver `agenda_service.py`). Mesmo raciocínio
    de `_ensure_agenda_os_table` acima — instalações que já têm essas
    colunas no schema legado não sofrem nada (`IF NOT EXISTS`)."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='data_servico' AND Object_ID=Object_ID('os_produto')) "
        "ALTER TABLE os_produto ADD data_servico DATE NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='executor_agenda' AND Object_ID=Object_ID('os_produto')) "
        "ALTER TABLE os_produto ADD executor_agenda INT NULL"
    )


@dataclass
class DavPagamento:
    """Réplica do `Type_FormaPagPedOS` global do legado (`mdl_proc.bas`) —
    contexto genérico de "um documento que tem forma de pagamento". Toda a
    lógica de totalização/validação abaixo recebe esse objeto em vez de
    parâmetros soltos, pra funcionar igual pra Pedido e O.S. sem duplicar
    código por tela."""
    tipo: str          # DAV_PED ou DAV_OS
    documento: int      # pedido_venda.pedido OU os.codigo
    situacao: str
    valor: float         # subtotal/total do documento
    forma_padrao: str    # forma_pagamento.codigo escolhida no combobox simples do cabeçalho (pode ser "")

    def tabela(self, tipo_forma: str) -> str:
        return DAV_CONFIG[self.tipo]["prefixo"] + FORMA_PAG_SUFIXO_TIPO[tipo_forma]

    @property
    def fk(self) -> str:
        return DAV_CONFIG[self.tipo]["fk"]


def _totaliza_dav(cur, dav: DavPagamento) -> float:
    """Soma o valor lançado em TODAS as tabelas de forma de pagamento do
    documento — réplica de `TotalizaDav`/`TotalFPDAV` (FormaPagamentoDAV.bas
    / FrmForPag.frm)."""
    total = 0.0
    for tipo_forma, col in FORMA_PAG_VALOR_COL.items():
        cur.execute(f"SELECT SUM({col}) AS s FROM {dav.tabela(tipo_forma)} WHERE {dav.fk}=%s", (dav.documento,))
        r = cur.fetchone()
        total += float((r.get("s") if r else None) or 0)
    return round(total, 2)


def _qtd_formas(cur, dav: DavPagamento) -> int:
    """Conta quantas linhas de forma de pagamento (somando as 8 tabelas)
    existem pro documento — réplica de `QtdFormas`."""
    qtd = 0
    for tipo_forma in FORMA_PAG_SUFIXO_TIPO:
        cur.execute(f"SELECT COUNT(*) AS c FROM {dav.tabela(tipo_forma)} WHERE {dav.fk}=%s", (dav.documento,))
        r = cur.fetchone()
        qtd += int((r.get("c") if r else None) or 0)
    return qtd


def _unica_forma_existente(cur, dav: DavPagamento) -> Optional[tuple[str, int]]:
    """Retorna (tipo, sequencia) da forma de pagamento se existir EXATAMENTE
    uma linha lançada pro documento (somando as 8 tabelas), ou None caso
    contrário (0 ou 2+ linhas)."""
    encontrados: list[tuple[str, int]] = []
    for tipo_forma in FORMA_PAG_SUFIXO_TIPO:
        cur.execute(f"SELECT sequencia FROM {dav.tabela(tipo_forma)} WHERE {dav.fk}=%s", (dav.documento,))
        for r in cur.fetchall():
            encontrados.append((tipo_forma, int(r.get("sequencia"))))
            if len(encontrados) > 1:
                return None
    return encontrados[0] if len(encontrados) == 1 else None


def _atualiza_valor_forma(cur, dav: DavPagamento, tipo_forma: str, sequencia: int, valor: float) -> None:
    col = FORMA_PAG_VALOR_COL[tipo_forma]
    cur.execute(f"UPDATE {dav.tabela(tipo_forma)} SET {col}=%s WHERE sequencia=%s", (valor, sequencia))


def _insere_duplicata_parcelada(cur, dav: DavPagamento, forma_pag: str, valor: float) -> None:
    """Insere 1+ linhas na tabela de duplicata do documento — se a forma de
    pagamento tem prazos cadastrados em `forma_pag_prazo`, rateia o valor
    por `percentual` (1 linha por prazo, vencimento = hoje + prazo, última
    parcela absorve o arredondamento). Sem prazo cadastrado, insere 1 linha
    só com vencimento hoje (a grade de rateio manual do legado, `FrmFaturado`,
    não foi portada — ver PENDENCIAS.md, o usuário ajusta o vencimento
    editando a linha depois). Réplica do `Case "DU"` em `Command5_Click`/
    `CadastraFPAutomatica` (FrmForPag.frm)."""
    tabela = dav.tabela("DU")
    cur.execute(
        "SELECT prazo, percentual FROM forma_pag_prazo WHERE forma_pag=%s ORDER BY prazo",
        (forma_pag,),
    )
    prazos = cur.fetchall()
    if not prazos:
        cur.execute(
            f"INSERT INTO {tabela} ({dav.fk}, forma_pag, valor_pag, data_venc) "
            f"VALUES (%s, %s, %s, CONVERT(date, GETDATE()))",
            (dav.documento, forma_pag, valor),
        )
        return
    restante = valor
    for i, p in enumerate(prazos):
        pct = float(p.get("percentual") or 0)
        prazo_dias = int(p.get("prazo") or 0)
        parcela = round(restante, 2) if i == len(prazos) - 1 else round(valor * pct / 100, 2)
        restante -= parcela
        cur.execute(
            f"INSERT INTO {tabela} ({dav.fk}, forma_pag, valor_pag, data_venc) "
            f"VALUES (%s, %s, %s, DATEADD(day, %s, CONVERT(date, GETDATE())))",
            (dav.documento, forma_pag, parcela, prazo_dias),
        )


def _cadastra_forma_automatica(cur, dav: DavPagamento, forma_pag: str, valor: float) -> None:
    """Lança automaticamente `valor` na forma de pagamento padrão (combobox
    simples do cabeçalho) quando nenhuma forma ainda foi lançada
    manualmente — réplica de `CadastraDavFormaPagamento`/`CadastraFPAutomatica`."""
    cur.execute("SELECT tipo FROM forma_pagamento WHERE codigo=%s", (forma_pag,))
    row = cur.fetchone()
    tipo_forma = ((row.get("tipo") if row else None) or "").strip().upper()
    if tipo_forma not in FORMA_PAG_SUFIXO_TIPO:
        return
    if tipo_forma == "DU":
        _insere_duplicata_parcelada(cur, dav, forma_pag, valor)
        return
    tabela = dav.tabela(tipo_forma)
    col = FORMA_PAG_VALOR_COL[tipo_forma]
    venc_col = FORMA_PAG_VENC_COL[tipo_forma]
    if venc_col:
        cur.execute(
            f"INSERT INTO {tabela} ({dav.fk}, forma_pag, {col}, {venc_col}) "
            f"VALUES (%s, %s, %s, CONVERT(date, GETDATE()))",
            (dav.documento, forma_pag, valor),
        )
    else:
        cur.execute(
            f"INSERT INTO {tabela} ({dav.fk}, forma_pag, {col}) VALUES (%s, %s, %s)",
            (dav.documento, forma_pag, valor),
        )


def _fecha_fpag_dav(cur, dav: DavPagamento) -> Optional[str]:
    """Réplica de `Fecha_FPAG_Dav` (FormaPagamentoDAV.bas): garante que o
    total lançado nas tabelas de forma de pagamento bate com `dav.valor`
    (subtotal do documento). Se não bate e existe EXATAMENTE 1 forma
    lançada, corrige o valor dela automaticamente (ajuste de arredondamento).
    Se não bate, não há nada lançado ainda e uma forma padrão foi informada
    (combobox simples do cabeçalho), lança automaticamente. Se 2+ formas
    divergem, bloqueia — usuário precisa acertar manualmente pelo modal.
    Retorna None se ok, ou a mensagem de erro (igual ao legado) se bloqueado."""
    total_lancado = _totaliza_dav(cur, dav)
    if abs(total_lancado - dav.valor) < 0.005:
        return None
    unica = _unica_forma_existente(cur, dav)
    if unica:
        _atualiza_valor_forma(cur, dav, unica[0], unica[1], dav.valor)
        return None
    if total_lancado == 0 and (dav.forma_padrao or "").strip():
        _cadastra_forma_automatica(cur, dav, dav.forma_padrao.strip(), dav.valor)
        return None
    if _qtd_formas(cur, dav) == 0:
        # Sem nenhuma forma lançada e sem forma padrão — quem chama decide a
        # mensagem (Command111_Click faz essa checagem separada, com
        # "Defina a Forma de Pagamento", só quando valor > 0).
        return None
    return "Informar a Forma de Pagamento corretamente!"


def _fechar_pedido_itens(cur, pedido: int, subtotal: float = 0.0, forma_padrao: Optional[str] = None) -> Optional[str]:
    """Fecha o Pedido (situação A -> F) dentro da transação corrente: exige
    pelo menos 1 item, valida/ajusta a forma de pagamento (réplica de
    `Fecha_FPAG_Dav` + a checagem `QtdFormas=0` de `Command111_Click`) e move
    o estoque das PEÇAS (qtd -= q ; reservado += q). Retorna uma mensagem de
    erro (str) se bloqueado, ou None se ok — quem chama decide se
    comita/desfaz a transação. Compartilhado entre o Fechar isolado
    (`/pedidos/{pedido}/fechar`) e o Faturar (`/pedidos/{pedido}/faturar`,
    que fecha-e-fatura num clique só quando o pedido ainda está Aberto —
    mesmo comportamento de `Command111_Click` no legado).

    Item m² (`comprimento`/`largura` gravados, ver `_add_item_completo_sync`)
    baixa estoque pela ÁREA REAL da peça (`_area_estoque`, réplica de
    `AreaEstoque` — sem arredondamento nem piso de área mínima, diferente
    do `_area_preco` usado pra precificar), não pela contagem de peças —
    `qtd_pedida × área_estoque`. Item normal continua baixando por
    `qtd_pedida` sozinho, sem mudança."""
    cur.execute(
        "SELECT produto, qtd_pedida, comprimento, largura FROM pedido_venda_prod "
        "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
        (pedido,),
    )
    itens = cur.fetchall()
    if not itens:
        return "Inclua pelo menos um produto ou serviço antes de fechar."
    dav = DavPagamento(tipo=DAV_PED, documento=pedido, situacao="A", valor=subtotal, forma_padrao=forma_padrao or "")
    erro = _fecha_fpag_dav(cur, dav)
    if erro:
        return erro
    if _qtd_formas(cur, dav) == 0 and subtotal > 0:
        return "Defina a Forma de Pagamento do Pedido!"
    for it in itens:
        qtd_pedida = float(it.get("qtd_pedida") or 0)
        comprimento, largura = it.get("comprimento"), it.get("largura")
        qtd_estoque = qtd_pedida * _area_estoque(comprimento, largura) if comprimento and largura else qtd_pedida
        _mover_estoque(cur, (it.get("produto") or "").strip(), qtd_estoque, "reservado")
    cur.execute("UPDATE pedido_venda SET situacao='F' WHERE pedido=%s", (pedido,))
    return None


def _liberar_reservado(cur, codigo: str, delta_qtd: float, campo: str = "reservado") -> None:
    """Libera o estoque RESERVADO de uma PEÇA ao faturar (Comanda) — a baixa
    de `qtd` já aconteceu no Fechar/Inclusão de item (ver `_mover_estoque`),
    aqui só se desfaz a reserva. Efeito: pecas.<campo> -= delta_qtd. Não faz
    nada para serviços/itens inexistentes. `campo` é "reservado" (Pedido) ou
    "reservado_os" (O.S. — mesma coluna já usada por `_mover_estoque` na
    inclusão de item da OS, ver `os_itens_service.py`)."""
    if campo not in ("reservado", "reservado_os"):
        raise ValueError("campo inválido")
    if not delta_qtd or not _is_peca(cur, codigo):
        return
    cur.execute(
        f"UPDATE pecas SET {campo} = ISNULL({campo},0) - %s WHERE codigo_int=%s",
        (delta_qtd, codigo),
    )
"""Testes de `recebimento_service.py` (Recebimento de Mercadoria, Fase 1 —
digitação manual, migração de `Geral\\FrmtraRec.frm`). Ver PENDENCIAS.md >
"Recebimento de Mercadoria" pro racional completo.

Nenhum teste fala com banco real — `FakeCursor` despacha `fetchone`/
`fetchall` por trecho da última query executada (mesmo padrão já usado em
`test_pedido_compra_service.py`), o que evita depender da ORDEM exata de
chamadas num service com vários loops (crítica percorre 13 campos, cada
item recebido dispara sua própria checagem de custo/estoque/baixa de
Pedido de Compra)."""
import xml.etree.ElementTree as ET

import pytest

import services.recebimento_service as svc


class FakeCursor:
    def __init__(self, one_patterns=None, many_patterns=None, one=None, many=None):
        self.one_patterns = one_patterns or {}
        self.many_patterns = many_patterns or {}
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []
        self._last_query = ""

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._last_query = q

    def fetchone(self):
        for pattern, val in self.one_patterns.items():
            if pattern in self._last_query:
                return val
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        for pattern, val in self.many_patterns.items():
            if pattern in self._last_query:
                return val
        return self._many.pop(0) if self._many else []

    def close(self):
        pass

    def updates_matching(self, pattern):
        return [(q, p) for q, p in self.queries if pattern in q and q.strip().upper().startswith("UPDATE")]


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor
        self.committed = False
        self.rolled = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


def _sets_list(update_query: str) -> list:
    """Extrai só os `campo=%s` (com placeholder — descarta literais como
    `alterado=1`) do `SET` de uma query `UPDATE ... SET a=%s, b=1, c=%s
    WHERE ...`, na mesma ordem que os `params` (só entradas com `%s`
    consomem um valor de `params`)."""
    inner = update_query.split("SET ", 1)[1].split(" WHERE")[0]
    return [s.strip() for s in inner.split(",") if "%s" in s]


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


# ---------------------------------------------------------------------------
# Permissão
# ---------------------------------------------------------------------------

def test_novo_rascunho_sem_permissao(monkeypatch):
    cur = FakeCursor()
    _patch(monkeypatch, cur)
    monkeypatch.setattr(svc, "tem_permissao", lambda cur, classe, tela, comando: False)
    r = svc._novo_rascunho_sync("srv", "bd", classe=1, master=False)
    assert r["success"] is False
    assert "permiss" in r["message"].lower()


def test_criticar_sem_permissao(monkeypatch):
    cur = FakeCursor()
    _patch(monkeypatch, cur)
    monkeypatch.setattr(svc, "tem_permissao", lambda cur, classe, tela, comando: False)
    r = svc._criticar_sync("srv", "bd", 1, classe=1, master=False)
    assert r["success"] is False
    assert "permiss" in r["message"].lower()


def test_atualizar_sem_permissao(monkeypatch):
    cur = FakeCursor()
    _patch(monkeypatch, cur)
    monkeypatch.setattr(svc, "tem_permissao", lambda cur, classe, tela, comando: False)
    r = svc._atualizar_sync("srv", "bd", 1, classe=1, master=False)
    assert r["success"] is False
    assert "permiss" in r["message"].lower()


def test_master_bypassa_permissao(monkeypatch):
    cur = FakeCursor(one_patterns={"FROM nf_recebimento WHERE codigo=%s": None})
    _patch(monkeypatch, cur)
    r = svc._criticar_sync("srv", "bd", 1, classe=None, master=True)
    # Sem classe (None) o helper `_sem_permissao` já libera — resultado aqui
    # é "não encontrado" (cab é None), não bloqueio de permissão.
    assert "não encontrado" in r["message"].lower()


# ---------------------------------------------------------------------------
# Crítica de recebimento (achado 1)
# ---------------------------------------------------------------------------

_CAMPOS_ZERO = {c: 0 for c in svc._CAMPOS_CRITICA}


def test_aplica_critica_sem_divergencia():
    cab = {**_CAMPOS_ZERO, "valor_total": 100.0}
    itens = [
        {"codautonum": 1, **_CAMPOS_ZERO, "valor_total": 60.0},
        {"codautonum": 2, **_CAMPOS_ZERO, "valor_total": 40.0},
    ]
    cur = FakeCursor(one=[cab], many_patterns={"FROM nf_recebimento_itens": itens})
    resultado = svc._aplicar_critica_sync(cur, 1, tolerancia=0)
    assert resultado["divergencias"] == []
    assert resultado["ajustes"] == []


def test_aplica_critica_ajusta_item_de_maior_valor_dentro_da_tolerancia():
    cab = {**_CAMPOS_ZERO, "valor_total": 100.0, "valor_icms": 18.5}
    itens = [
        {"codautonum": 1, **_CAMPOS_ZERO, "valor_total": 60.0, "valor_icms": 10.0},
        {"codautonum": 2, **_CAMPOS_ZERO, "valor_total": 40.0, "valor_icms": 8.0},
    ]
    cur = FakeCursor(one=[cab], many_patterns={"FROM nf_recebimento_itens": itens})
    resultado = svc._aplicar_critica_sync(cur, 1, tolerancia=1.0)
    assert resultado["divergencias"] == []
    assert len(resultado["ajustes"]) == 1
    ajuste = resultado["ajustes"][0]
    assert ajuste["campo"] == "valor_icms"
    # Item de MAIOR valor_icms (item 1, 10.0) recebe o ajuste — nunca o cabeçalho.
    assert ajuste["item"] == 1
    assert ajuste["novo_valor"] == 10.5
    updates = cur.updates_matching("nf_recebimento_itens SET valor_icms")
    assert len(updates) == 1
    assert updates[0][1] == (10.5, 1)


def test_aplica_critica_bloqueia_fora_da_tolerancia():
    cab = {**_CAMPOS_ZERO, "valor_total": 100.0, "valor_icms": 50.0}
    itens = [
        {"codautonum": 1, **_CAMPOS_ZERO, "valor_total": 60.0, "valor_icms": 10.0},
        {"codautonum": 2, **_CAMPOS_ZERO, "valor_total": 40.0, "valor_icms": 8.0},
    ]
    cur = FakeCursor(one=[cab], many_patterns={"FROM nf_recebimento_itens": itens})
    resultado = svc._aplicar_critica_sync(cur, 1, tolerancia=1.0)
    assert len(resultado["divergencias"]) == 1
    div = resultado["divergencias"][0]
    assert div["campo"] == "valor_icms"
    assert div["valor_cabecalho"] == 50.0
    assert div["soma_itens"] == 18.0
    # Nenhum ajuste é aplicado quando fora da tolerância.
    assert resultado["ajustes"] == []
    assert cur.updates_matching("nf_recebimento_itens SET valor_icms") == []


def test_criticar_sync_grava_situacao_erro_quando_diverge(monkeypatch):
    cab_load = {"n_fiscal_gerado": None}
    cab_critica = {**_CAMPOS_ZERO, "valor_total": 100.0, "valor_icms": 50.0}
    itens = [{"codautonum": 1, **_CAMPOS_ZERO, "valor_total": 100.0, "valor_icms": 0.0}]
    cur = FakeCursor(
        one_patterns={
            "n_fiscal_gerado FROM nf_recebimento WHERE codigo=%s": cab_load,
            "valor_libera_critica FROM controle": {"valor_libera_critica": 1.0},
        },
        one=[cab_critica],
        many_patterns={"FROM nf_recebimento_itens": itens},
    )
    conn = _patch(monkeypatch, cur)
    r = svc._criticar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is True
    assert r["situacao"] == "E"
    assert conn.committed is True
    situacao_updates = cur.updates_matching("UPDATE nf_recebimento SET situacao=%s WHERE codigo=%s")
    assert situacao_updates[-1][1] == ("E", 1)


def test_criticar_sync_bloqueia_ja_promovido(monkeypatch):
    cur = FakeCursor(one_patterns={"n_fiscal_gerado FROM nf_recebimento WHERE codigo=%s": {"n_fiscal_gerado": 999}})
    _patch(monkeypatch, cur)
    r = svc._criticar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is False
    assert "já foi atualizado" in r["message"]


# ---------------------------------------------------------------------------
# Baixa FIFO de Pedido de Compra (achado 4)
# ---------------------------------------------------------------------------

def test_baixa_pedido_compra_cobre_com_uma_linha():
    linha = {"seq": 1, "codigo": 900, "qtd": 10.0, "qtd_recebida": 0.0, "p_unit": 5.0}
    cur = FakeCursor(
        many_patterns={"pedido_itens pi JOIN pedido p": [linha]},
        one_patterns={"COUNT(*) AS n FROM pedido_itens": {"n": 0}},
    )
    svc._baixar_pedido_compra_sync(cur, recebimento_codigo=1, fornecedor=50, codigo_int="P001", qtd_recebida=10.0)

    inserts = [q for q, p in cur.queries if q.startswith("INSERT INTO nf_recebimento_pedido")]
    assert len(inserts) == 1
    updates_itens = cur.updates_matching("UPDATE pedido_itens SET qtd_recebida=%s WHERE SEQUENCIA_PEDIDO_ITENS=%s")
    assert updates_itens[0][1] == (10.0, 1)
    updates_pedido = cur.updates_matching("UPDATE pedido SET situacao=%s WHERE codigo=%s")
    assert updates_pedido[0][1] == ("R", 900)


def test_baixa_pedido_compra_consome_duas_linhas_em_sequencia():
    linha1 = {"seq": 1, "codigo": 900, "qtd": 6.0, "qtd_recebida": 0.0, "p_unit": 5.0}
    linha2 = {"seq": 2, "codigo": 901, "qtd": 10.0, "qtd_recebida": 0.0, "p_unit": 4.0}
    cur = FakeCursor(
        many_patterns={"pedido_itens pi JOIN pedido p": [linha1, linha2]},
        one_patterns={"COUNT(*) AS n FROM pedido_itens": {"n": 0}},
    )
    svc._baixar_pedido_compra_sync(cur, recebimento_codigo=1, fornecedor=50, codigo_int="P001", qtd_recebida=10.0)

    inserts = [(q, p) for q, p in cur.queries if q.startswith("INSERT INTO nf_recebimento_pedido")]
    assert len(inserts) == 2
    # linha1 (6 unid., pedido 900) totalmente consumida; sobra 4 pra linha2.
    assert inserts[0][1] == (1, 900, "P001", 6.0, 30.0)
    assert inserts[1][1] == (1, 901, "P001", 4.0, 16.0)
    updates_pedido = cur.updates_matching("UPDATE pedido SET situacao=%s WHERE codigo=%s")
    codigos_atualizados = {p[1] for _, p in updates_pedido}
    assert codigos_atualizados == {900, 901}


def test_baixa_pedido_compra_sem_pedido_aberto_nao_falha():
    cur = FakeCursor(many_patterns={"pedido_itens pi JOIN pedido p": []})
    svc._baixar_pedido_compra_sync(cur, recebimento_codigo=1, fornecedor=50, codigo_int="P001", qtd_recebida=10.0)
    assert cur.queries[-1][0].startswith("SELECT")  # só a busca, nada mais executado
    assert not any(q.startswith("INSERT INTO nf_recebimento_pedido") for q, _ in cur.queries)


def test_baixa_pedido_compra_qtd_zero_nao_consulta():
    cur = FakeCursor()
    svc._baixar_pedido_compra_sync(cur, recebimento_codigo=1, fornecedor=50, codigo_int="P001", qtd_recebida=0)
    assert cur.queries == []


# ---------------------------------------------------------------------------
# Atualizar (promoção completa) — custo médio ponderado, preço por margem,
# estoque, vencimentos.
# ---------------------------------------------------------------------------

_CAB_BASE = {c: 0 for c in svc._CAB_CAMPOS}


def _cab_completo(**overrides):
    cab = {"codigo": 1, "n_fiscal_gerado": None, **_CAB_BASE}
    cab.update({
        "fornecedor": 50, "mov": "E01", "num_nf": 123, "serie_nf": "1",
        "data": "2026-08-21", "data_mov": "2026-08-21", "valor_total": 100.0,
    })
    cab.update(overrides)
    return cab


def _item_completo(**overrides):
    item = {c: 0 for c in svc._ITEM_CAMPOS}
    item.update({
        "codautonum": 1, "codigo_int": "P001", "qtd": 10.0, "qtd_un_compra": 1.0, "p_unit": 10.0,
        "valor_total": 100.0,
    })
    item.update(overrides)
    return item


def _build_cursor_atualizar(monkeypatch, cab, itens, *, peca=None, tipo_mov=None, venc_soma=None, duplicado=None, modo_preco=1):
    tipo_mov = tipo_mov or {"atualiza_est": "S", "altera_custo": True, "altera_venda": False}
    venc_soma = cab["valor_total"] if venc_soma is None else venc_soma
    cur = FakeCursor(
        one_patterns={
            "FROM nf_recebimento WHERE codigo=%s": cab,
            "FROM tipo_mov WHERE codigo=%s": tipo_mov,
            "SELECT TOP 1 codigo FROM n_fiscal WHERE num_nf=%s AND serie_nf=%s AND fornecedor=%s": duplicado,
            "SELECT valor_libera_critica FROM controle": {"valor_libera_critica": 0},
            "Altera_preco_venda_tela FROM controle_aux": {"Altera_preco_venda_tela": modo_preco},
            "INSERT INTO n_fiscal (": {"codigo": 555},
            "FROM pecas WHERE codigo_int=%s": peca,
            "SELECT SUM(valor) AS soma FROM nf_recebimento_vencimento": {"soma": venc_soma},
        },
        many_patterns={
            "FROM nf_recebimento_itens WHERE codigo=%s": itens,
            "FROM nf_recebimento_vencimento WHERE codigo=%s": [{"data_venc": "2026-09-21", "valor": cab["valor_total"]}],
            "pedido_itens pi JOIN pedido p": [],
        },
    )
    _patch(monkeypatch, cur)
    return cur


def test_atualizar_bloqueia_ja_promovido(monkeypatch):
    cab = _cab_completo(n_fiscal_gerado=999)
    cur = _build_cursor_atualizar(monkeypatch, cab, [_item_completo()])
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is False
    assert "já foi atualizado" in r["message"]


def test_atualizar_bloqueia_campos_obrigatorios_faltando(monkeypatch):
    cab = _cab_completo(mov=None)
    cur = _build_cursor_atualizar(monkeypatch, cab, [_item_completo()])
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is False
    assert "preencha" in r["message"].lower()


def test_atualizar_bloqueia_nota_duplicada(monkeypatch):
    cab = _cab_completo()
    cur = _build_cursor_atualizar(monkeypatch, cab, [_item_completo()], duplicado={"codigo": 42})
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is False
    assert "já existe" in r["message"].lower()


def test_atualizar_bloqueia_vencimento_nao_bate(monkeypatch):
    cab = _cab_completo()
    cur = _build_cursor_atualizar(monkeypatch, cab, [_item_completo()], venc_soma=50.0)
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is False
    assert "vencimentos somam" in r["message"]


def test_atualizar_bloqueia_divergencia_critica_fora_tolerancia(monkeypatch):
    cab = _cab_completo(valor_icms=999.0)
    item = _item_completo(valor_icms=0.0)
    cur = _build_cursor_atualizar(monkeypatch, cab, [item])
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is False
    assert "divergências" in r["message"].lower()
    assert r["divergencias"]


def test_atualizar_promove_e_calcula_custo_medio_ponderado(monkeypatch):
    # EstoqueAnt=10, CustoAnt(custo_reposicao)=5.0; item recebe 10 unid. a
    # 10.0/un (cr=10.0, sem frete/seguro/ICMS/ST) — achado 2:
    # CustoMedio = (10*10 + 10*5) / (10+10) = 7.5
    cab = _cab_completo()
    item = _item_completo()
    peca = {"qtd": 10.0, "custo_reposicao": 5.0, "p_custo": 5.0, "margem_lucro": 50.0, "margem_tabela": 100.0}
    cur = _build_cursor_atualizar(monkeypatch, cab, [item], peca=peca)
    r = svc._atualizar_sync("srv", "bd", 1, usuario=7, classe=None, master=True)
    assert r["success"] is True
    assert r["n_fiscal"] == 555

    upd = cur.updates_matching("UPDATE pecas SET")
    assert len(upd) == 1
    query, params = upd[0]
    assert "custo_medio=%s" in query
    assert "qtd=%s" in query  # atualiza_est == 'S'
    assert "p_custo=%s" in query and "custo_reposicao=%s" in query  # altera_custo True
    # Ordem dos binds segue a ordem de `sets` montada no service.
    idx_custo_medio = _sets_list(query).index("custo_medio=%s")
    assert round(params[idx_custo_medio], 2) == 7.5

    situacao_updates = cur.updates_matching("UPDATE nf_recebimento SET situacao=%s, n_fiscal_gerado=%s")
    assert situacao_updates[-1][1] == ("P", 555, 1)


def _assert_preco_atualizado(cur):
    upd = cur.updates_matching("UPDATE pecas SET")
    query, params = upd[0]
    assert "p_venda=%s" in query and "preco_lista=%s" in query
    sets = _sets_list(query)
    idx_p_venda = sets.index("p_venda=%s")
    idx_preco_lista = sets.index("preco_lista=%s")
    # custo_base = cr recém-calculado (10.0, já que altera_custo=True) —
    # p_venda = 10 + 10*50/100 = 15.0 ; preco_lista = 10 + 10*100/100 = 20.0
    assert round(params[idx_p_venda], 2) == 15.0
    assert round(params[idx_preco_lista], 2) == 20.0


def _assert_preco_nao_atualizado(cur):
    upd = cur.updates_matching("UPDATE pecas SET")
    query, _ = upd[0]
    assert "p_venda=%s" not in query


# Modo 2 (`controle_aux.Altera_preco_venda_tela=2`) — gating pelo checkbox
# "Atualiza Preço" do item (`nf_recebimento_itens.atualiza_preco`),
# `pecas.politica_preco` é ignorado neste modo.

def test_atualizar_modo2_nao_altera_preco_sem_flag_atualiza_preco(monkeypatch):
    cab = _cab_completo()
    item = _item_completo(atualiza_preco=False)
    peca = {"qtd": 10.0, "custo_reposicao": 5.0, "p_custo": 5.0, "margem_lucro": 50.0, "margem_tabela": 100.0, "politica_preco": "E"}
    tipo_mov = {"atualiza_est": "S", "altera_custo": True, "altera_venda": True}
    cur = _build_cursor_atualizar(monkeypatch, cab, [item], peca=peca, tipo_mov=tipo_mov, modo_preco=2)
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is True
    _assert_preco_nao_atualizado(cur)


def test_atualizar_modo2_altera_preco_por_margem_quando_flag_e_tipo_mov_permitem(monkeypatch):
    cab = _cab_completo()
    item = _item_completo(atualiza_preco=True)
    peca = {"qtd": 10.0, "custo_reposicao": 5.0, "p_custo": 5.0, "margem_lucro": 50.0, "margem_tabela": 100.0, "politica_preco": "C"}
    tipo_mov = {"atualiza_est": "S", "altera_custo": True, "altera_venda": True}
    cur = _build_cursor_atualizar(monkeypatch, cab, [item], peca=peca, tipo_mov=tipo_mov, modo_preco=2)
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is True
    _assert_preco_atualizado(cur)


# Modo 1 (padrão — `Altera_preco_venda_tela<=1`, GERDELL/BARESTELA
# configurada assim) — gating por `pecas.politica_preco='E'` ("Tipo
# Preço"=Entrada no Cadastro de Produtos), o checkbox do item é ignorado.
# Achado tardio 2026-08-21: a Fase 1 original só implementava o Modo 2 —
# corrigido depois de pergunta direta do usuário sobre o campo Tipo Preço.

def test_atualizar_modo1_altera_preco_quando_politica_preco_entrada(monkeypatch):
    cab = _cab_completo()
    item = _item_completo(atualiza_preco=False)  # checkbox do item é ignorado no Modo 1
    peca = {"qtd": 10.0, "custo_reposicao": 5.0, "p_custo": 5.0, "margem_lucro": 50.0, "margem_tabela": 100.0, "politica_preco": "E"}
    tipo_mov = {"atualiza_est": "S", "altera_custo": True, "altera_venda": True}
    cur = _build_cursor_atualizar(monkeypatch, cab, [item], peca=peca, tipo_mov=tipo_mov, modo_preco=1)
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is True
    _assert_preco_atualizado(cur)


def test_atualizar_modo1_nao_altera_preco_quando_politica_preco_controlado(monkeypatch):
    cab = _cab_completo()
    item = _item_completo(atualiza_preco=True)  # checkbox do item é ignorado no Modo 1
    peca = {"qtd": 10.0, "custo_reposicao": 5.0, "p_custo": 5.0, "margem_lucro": 50.0, "margem_tabela": 100.0, "politica_preco": "C"}
    tipo_mov = {"atualiza_est": "S", "altera_custo": True, "altera_venda": True}
    cur = _build_cursor_atualizar(monkeypatch, cab, [item], peca=peca, tipo_mov=tipo_mov, modo_preco=1)
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is True
    _assert_preco_nao_atualizado(cur)


def test_atualizar_modo1_e_o_padrao_quando_config_ausente(monkeypatch):
    # `controle_aux` sem a coluna/linha (instalação nunca configurada) —
    # `int(None or 1) == 1`, mesmo comportamento do Modo 1 (padrão real da
    # fonte, `Altera_preco_venda_tela<=1`).
    cab = _cab_completo()
    item = _item_completo(atualiza_preco=True)
    peca = {"qtd": 10.0, "custo_reposicao": 5.0, "p_custo": 5.0, "margem_lucro": 50.0, "margem_tabela": 100.0, "politica_preco": "C"}
    tipo_mov = {"atualiza_est": "S", "altera_custo": True, "altera_venda": True}
    cur = _build_cursor_atualizar(monkeypatch, cab, [item], peca=peca, tipo_mov=tipo_mov)
    cur.one_patterns.pop("Altera_preco_venda_tela FROM controle_aux")
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is True
    _assert_preco_nao_atualizado(cur)


def test_atualizar_nao_mexe_em_pecas_quando_item_nao_e_peca(monkeypatch):
    cab = _cab_completo()
    item = _item_completo(codigo_int="SERV01")
    cur = _build_cursor_atualizar(monkeypatch, cab, [item], peca=None)
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is True
    assert cur.updates_matching("UPDATE pecas SET") == []


def test_atualizar_nao_soma_estoque_quando_tipo_mov_nao_atualiza(monkeypatch):
    cab = _cab_completo()
    item = _item_completo()
    peca = {"qtd": 10.0, "custo_reposicao": 5.0, "p_custo": 5.0, "margem_lucro": 0, "margem_tabela": 0}
    tipo_mov = {"atualiza_est": "N", "altera_custo": False, "altera_venda": False}
    cur = _build_cursor_atualizar(monkeypatch, cab, [item], peca=peca, tipo_mov=tipo_mov)
    r = svc._atualizar_sync("srv", "bd", 1, classe=None, master=True)
    assert r["success"] is True
    upd = cur.updates_matching("UPDATE pecas SET")
    query, _ = upd[0]
    assert "qtd=%s" not in query
    assert "p_custo=%s" not in query


# ---------------------------------------------------------------------------
# Fase 2 — Importação de XML de NF-e de entrada
# ---------------------------------------------------------------------------

def _det_xml(
    *, cprod="P001", cean="7891234567890", xprod="Produto Um", ncm="12345678", cfop="5102",
    qcom="10.0000", vuncom="5.0000", vprod="50.00", vfrete="2.00", vseg="1.00", vdesc="0.00", voutro="0.00",
    icms='<ICMS00><orig>0</orig><CST>00</CST><vBC>50.00</vBC><pICMS>18.00</pICMS><vICMS>9.00</vICMS></ICMS00>',
    ipi='<IPITrib><CST>50</CST><vBC>50.00</vBC><pIPI>5.00</pIPI><vIPI>2.50</vIPI></IPITrib>',
    pis='<PISAliq><CST>01</CST><vBC>50.00</vBC><pPIS>1.65</pPIS><vPIS>0.82</vPIS></PISAliq>',
    cofins='<COFINSAliq><CST>01</CST><vBC>50.00</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>3.80</vCOFINS></COFINSAliq>',
    pis_st="", cofins_st="",
):
    return (
        f'<det nItem="1"><prod><cProd>{cprod}</cProd><cEAN>{cean}</cEAN><xProd>{xprod}</xProd>'
        f'<NCM>{ncm}</NCM><CFOP>{cfop}</CFOP><uCom>UN</uCom><qCom>{qcom}</qCom><vUnCom>{vuncom}</vUnCom>'
        f'<vProd>{vprod}</vProd><vFrete>{vfrete}</vFrete><vSeg>{vseg}</vSeg><vDesc>{vdesc}</vDesc>'
        f'<vOutro>{voutro}</vOutro></prod><imposto>'
        f"<ICMS>{icms}</ICMS><IPI>{ipi}</IPI><PIS>{pis}</PIS>{pis_st}<COFINS>{cofins}</COFINS>{cofins_st}"
        f"</imposto></det>"
    )


def _xml_nfe(dets, *, num_nf="1234", serie="1", cnpj="12345678000199", venc="", vnf="55.50"):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>'
        f'<infNFe Id="NFe332006{cnpj}550010000012341234567890" versao="4.00">'
        f"<ide><nNF>{num_nf}</nNF><serie>{serie}</serie><dhEmi>2026-08-01T10:00:00-03:00</dhEmi>"
        "<dhSaiEnt>2026-08-02T10:00:00-03:00</dhSaiEnt></ide>"
        f"<emit><CNPJ>{cnpj}</CNPJ><xNome>Fornecedor Teste Ltda</xNome><xFant>Forn Teste</xFant><IE>123456</IE>"
        '<enderEmit><xLgr>Rua Teste</xLgr><nro>100</nro><xBairro>Centro</xBairro><xMun>Rio de Janeiro</xMun>'
        "<UF>RJ</UF><CEP>20000000</CEP><xPais>BRASIL</xPais></enderEmit></emit>"
        + "".join(dets)
        + f"<total><ICMSTot><vBC>50.00</vBC><vICMS>9.00</vICMS><vBCST>0.00</vBCST><vST>0.00</vST>"
        f"<vProd>50.00</vProd><vFrete>2.00</vFrete><vSeg>1.00</vSeg><vDesc>0.00</vDesc><vIPI>2.50</vIPI>"
        f"<vPIS>0.82</vPIS><vCOFINS>3.80</vCOFINS><vOutro>0.00</vOutro><vNF>{vnf}</vNF><vFCP>0.00</vFCP>"
        "<vFCPST>0.00</vFCPST></ICMSTot></total>"
        f"<cobr>{venc}</cobr></infNFe></NFe></nfeProc>"
    )


class TestParseXmlNfe:
    def test_cst_normal_icms_pis_cofins_aliq(self):
        xml = _xml_nfe([_det_xml()], venc="<dup><dVenc>2026-09-01</dVenc><vDup>55.50</vDup></dup>")
        r = svc._parse_xml_nfe(xml)
        assert r["header"]["cnpj_fornecedor"] == "12345678000199"
        assert r["header"]["num_nf"] == "1234"
        assert r["header"]["chave_acesso"]
        item = r["itens"][0]
        assert item["base_icms"] == 50.0 and item["valor_icms"] == 9.0 and item["alqt_icms"] == 18.0
        assert item["tributacao_pis"] == "01" and item["valor_pis"] == 0.82
        assert item["tributacao_cofins"] == "01" and item["valor_cofins"] == 3.80
        # valor_total = vProd(50)+frete(2)+seguro(1)+ipi(2.5)+sub(0)+fcpst(0)-desc(0)
        assert item["valor_total"] == 55.50
        assert r["vencimentos"] == [{"data_venc": "2026-09-01", "valor": 55.50}]

    def test_csosn_simples_nacional(self):
        icms = '<ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102>'
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml(icms=icms)]))
        item = r["itens"][0]
        assert item["base_icms"] == 0.0 and item["valor_icms"] == 0.0

    def test_csosn_101_credito_simples(self):
        icms = '<ICMSSN101><orig>0</orig><CSOSN>101</CSOSN><pCredSN>2.5</pCredSN><vCredICMSSN>1.25</vCredICMSSN></ICMSSN101>'
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml(icms=icms)]))
        item = r["itens"][0]
        assert item["alqt_icms"] == 2.5 and item["valor_icms"] == 1.25

    def test_cst_10_com_substituicao_tributaria(self):
        icms = (
            '<ICMS10><orig>0</orig><CST>10</CST><vBC>50.00</vBC><pICMS>18.00</pICMS><vICMS>9.00</vICMS>'
            '<vBCST>60.00</vBCST><pICMSST>20.00</pICMSST><vICMSST>12.00</vICMSST></ICMS10>'
        )
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml(icms=icms)]))
        item = r["itens"][0]
        assert item["base_sub"] == 60.0 and item["valor_sub"] == 12.0

    def test_pis_qtde_variant(self):
        pis = '<PISQtde><CST>03</CST><qBCProd>10.0000</qBCProd><vAliqProd>0.6500</vAliqProd><vPIS>6.50</vPIS></PISQtde>'
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml(pis=pis)]))
        item = r["itens"][0]
        assert item["tributacao_pis"] == "03" and item["base_pis"] == 10.0 and item["valor_pis"] == 6.50

    def test_pis_nt_variant_zera_valores(self):
        pis = '<PISNT><CST>08</CST></PISNT>'
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml(pis=pis)]))
        item = r["itens"][0]
        assert item["tributacao_pis"] == "08" and item["base_pis"] == 0.0 and item["valor_pis"] == 0.0

    def test_pis_st_soma_no_valor_total_quando_flag_ligada(self):
        pis_st = "<PISST><indSomaPISST>1</indSomaPISST><vBC>50.00</vBC><vPIS>1.00</vPIS></PISST>"
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml(pis_st=pis_st)]))
        item = r["itens"][0]
        assert item["valor_pis_st"] == 1.0
        # 55.50 (base) + 1.00 (PIS-ST somado por causa da flag)
        assert item["valor_total"] == 56.50

    def test_pis_st_nao_soma_sem_a_flag(self):
        pis_st = "<PISST><indSomaPISST>0</indSomaPISST><vBC>50.00</vBC><vPIS>1.00</vPIS></PISST>"
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml(pis_st=pis_st)]))
        item = r["itens"][0]
        assert item["valor_pis_st"] == 1.0
        assert item["valor_total"] == 55.50

    def test_vencimento_diferenca_vai_para_primeira_parcela(self):
        venc = "<dup><dVenc>2026-09-01</dVenc><vDup>20.00</vDup></dup><dup><dVenc>2026-10-01</dVenc><vDup>30.00</vDup></dup>"
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml()], venc=venc, vnf="55.50"))
        # soma real = 50.00, vNF = 55.50 -> diferença (5.50) cai na 1ª parcela
        assert r["vencimentos"][0]["valor"] == 25.50
        assert r["vencimentos"][1]["valor"] == 30.00

    def test_chave_acesso_extraida_do_id_infnfe(self):
        r = svc._parse_xml_nfe(_xml_nfe([_det_xml()]))
        assert len(r["header"]["chave_acesso"]) == 44

    def test_xml_invalido_levanta_parse_error(self):
        with pytest.raises(ET.ParseError):
            svc._parse_xml_nfe("<nfeProc><NFe>")


class TestImportarXmlSync:
    def _fake_cursor_importar(self, monkeypatch, *, forn_existente=None, produto_row=None, ja_existe_nf=None, ja_existe_receb=None, n_fiscal_gerado=None):
        cur = FakeCursor(
            one_patterns={
                "n_fiscal_gerado FROM nf_recebimento WHERE codigo=%s": {"n_fiscal_gerado": n_fiscal_gerado},
                "codigo_int FROM fornecedor WHERE codigo=%s": forn_existente,
                "INSERT INTO fornecedor (": {"codigo_int": 77},
                "TOP 1 codigo FROM n_fiscal WHERE num_nf=%s AND serie_nf=%s AND fornecedor=%s": ja_existe_nf,
                "TOP 1 codigo FROM nf_recebimento WHERE num_nf=%s AND serie_nf=%s AND fornecedor=%s": ja_existe_receb,
                "FROM pecas_xml": produto_row,
                "codigo_fab=%s AND situacao='A'": produto_row,
                "cfop FROM cfop_xml WHERE cfop_xml=%s": None,
                "cod_grupo_pis_cofins FROM pecas WHERE codigo_int=%s": None,
                "codigo_mercosul FROM pecas WHERE codigo_int=%s": None,
                "codigo_bar FROM pecas WHERE codigo_int=%s": None,
                "1 AS ok FROM codbarra_auxiliar WHERE codigo_bar=%s": None,
            },
        )
        conn = _patch(monkeypatch, cur)
        return cur, conn

    def test_sem_permissao(self, monkeypatch):
        cur, _ = self._fake_cursor_importar(monkeypatch)
        monkeypatch.setattr(svc, "tem_permissao", lambda cur, classe, tela, comando: False)
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=1, master=False)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_recebimento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one_patterns={"n_fiscal_gerado FROM nf_recebimento WHERE codigo=%s": None})
        _patch(monkeypatch, cur)
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=None, master=True)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_bloqueia_se_ja_promovido(self, monkeypatch):
        self._fake_cursor_importar(monkeypatch, n_fiscal_gerado=999)
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=None, master=True)
        assert r["success"] is False
        assert "já foi atualizado" in r["message"]

    def test_fornecedor_existente_nao_cria_novo(self, monkeypatch):
        cur, conn = self._fake_cursor_importar(monkeypatch, forn_existente={"codigo_int": 42})
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=None, master=True)
        assert r["success"] is True
        assert r["header"]["fornecedor"] == 42
        assert not any(q.startswith("INSERT INTO fornecedor (") for q, _ in cur.queries)

    def test_fornecedor_novo_e_criado_automaticamente(self, monkeypatch):
        cur, conn = self._fake_cursor_importar(monkeypatch, forn_existente=None)
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=None, master=True)
        assert r["success"] is True
        assert r["header"]["fornecedor"] == 77
        assert any(q.startswith("INSERT INTO fornecedor (") for q, _ in cur.queries)
        assert any(q.startswith("INSERT INTO fornecedor_end (") for q, _ in cur.queries)
        assert conn.committed is True

    def test_produto_vinculado_via_ean(self, monkeypatch):
        produto = {"codigo_int": "P001", "descricao": "Produto Um", "qtd_un_compra": 1}
        cur, _ = self._fake_cursor_importar(monkeypatch, forn_existente={"codigo_int": 42}, produto_row=produto)
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=None, master=True)
        assert r["success"] is True
        item = r["itens"][0]
        assert item["vinculado"] is True
        assert item["codigo_int"] == "P001"
        assert r["itens_sem_vinculo"] == []

    def test_produto_sem_vinculo_fica_marcado(self, monkeypatch):
        cur, _ = self._fake_cursor_importar(monkeypatch, forn_existente={"codigo_int": 42}, produto_row=None)
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=None, master=True)
        assert r["success"] is True
        item = r["itens"][0]
        assert item["vinculado"] is False
        assert item["codigo_int"] is None
        assert len(r["itens_sem_vinculo"]) == 1

    def test_bloqueia_nota_ja_existente_em_n_fiscal(self, monkeypatch):
        self._fake_cursor_importar(monkeypatch, forn_existente={"codigo_int": 42}, ja_existe_nf={"codigo": 5})
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=None, master=True)
        assert r["success"] is False
        assert "já existe" in r["message"].lower()

    def test_bloqueia_xml_ja_importado_em_outro_recebimento(self, monkeypatch):
        self._fake_cursor_importar(monkeypatch, forn_existente={"codigo_int": 42}, ja_existe_receb={"codigo": 9})
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=_xml_nfe([_det_xml()]), classe=None, master=True)
        assert r["success"] is False
        assert "já foi importado" in r["message"].lower()

    def test_xml_sem_itens_bloqueia(self, monkeypatch):
        xml_vazio = _xml_nfe([])
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml=xml_vazio, classe=None, master=True)
        assert r["success"] is False
        assert "nenhum item" in r["message"].lower()

    def test_xml_invalido_retorna_mensagem_amigavel(self, monkeypatch):
        r = svc._importar_xml_sync("srv", "bd", codigo_rascunho=1, conteudo_xml="<not-xml", classe=None, master=True)
        assert r["success"] is False
        assert "xml" in r["message"].lower()

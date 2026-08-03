"""Testes UNITÁRIOS de Inventário de Estoque (Transações > Inventário) —
Fase 1: núcleo manual (Abertura, Digitação, Fechar, Cancelar). Ver
PENDENCIAS.md > "Inventário" pro rastreio de negócio completo."""
from datetime import date

import services.inventario_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []

    def close(self):
        pass


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


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _ctrl(situacao="F", tipo="G", data=None):
    return {"data_balanco": data or date(2026, 7, 22), "situacao_balanco": situacao, "tipo_balanco": tipo}


class TestStatus:
    def test_fechado_nao_conta_itens(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="F")])
        _patch(monkeypatch, cur)
        r = svc._status_sync("srv", "bd")
        assert r["success"] is True
        assert r["aberto"] is False
        assert r["total_itens"] == 0
        assert r["itens_digitados"] == 0

    def test_aberto_conta_itens_total_e_digitados_separado(self, monkeypatch):
        # 2 COUNTs quando aberto: total (todas as linhas) e digitados
        # (contado_em IS NOT NULL) — critério corrigido 2026-07-23: um
        # balanço Contábil recém-aberto tem `estoque_balanco` pré-carregado
        # com o saldo do sistema (não-zero) pra TODO item, então
        # `estoque_balanco<>0` sozinho mostrava "tudo já digitado" mesmo
        # sem ninguém ter digitado nada (achado ao vivo pelo usuário,
        # "Total Digitados: 236 de 236" num balanço Contábil vazio).
        cur = FakeCursor(one=[_ctrl(situacao="A", tipo="C"), {"c": 3186}, {"c": 12}])
        _patch(monkeypatch, cur)
        r = svc._status_sync("srv", "bd")
        assert r["aberto"] is True
        assert r["total_itens"] == 3186
        assert r["itens_digitados"] == 12
        assert r["tipo_balanco_descricao"] == "Contábil"
        query_digitados = cur.queries[-1][0]
        assert "contado_em IS NOT NULL" in query_digitados
        assert "estoque_balanco" not in query_digitados


class TestAbrir:
    def test_bloqueia_se_ja_aberto(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_sync("srv", "bd", "2026-07-22", "G", 10)
        assert r["success"] is False
        assert "em aberto" in r["message"]
        assert conn.committed is False

    def test_tipo_invalido(self, monkeypatch):
        cur = FakeCursor(one=[])
        _patch(monkeypatch, cur)
        r = svc._abrir_sync("srv", "bd", "2026-07-22", "X", 10)
        assert r["success"] is False

    def test_abre_geral_com_sucesso(self, monkeypatch):
        # fetchone order: controle, depois o SELECT 1 do upsert de inventario_controle (None = insere)
        cur = FakeCursor(one=[_ctrl(situacao="F"), None])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_sync("srv", "bd", "2026-07-22", "G", 10)
        assert r["success"] is True
        assert conn.committed is True
        # confere que o snapshot de PECAS e VEICULOS foi inserido, e que o
        # controle foi atualizado pro tipo certo
        insert_queries = [q for q, _ in cur.queries if q.strip().upper().startswith("INSERT INTO INVENTARIO")]
        assert any("FROM pecas" in q for q in insert_queries)
        assert any("FROM veiculos" in q for q in insert_queries)
        update_controle = [p for q, p in cur.queries if "UPDATE controle SET data_balanco" in q][0]
        assert update_controle == ("2026-07-22", "G")

    def test_abre_reaproveitando_linha_de_controle_existente(self, monkeypatch):
        # fetchone order: controle, depois o SELECT 1 acha uma linha -> reabertura (UPDATE, não INSERT)
        cur = FakeCursor(one=[_ctrl(situacao="F"), {"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._abrir_sync("srv", "bd", "2026-07-22", "C", 10)
        assert r["success"] is True
        assert any("UPDATE inventario_controle SET reabertura" in q for q, _ in cur.queries)
        assert not any(q.strip().upper().startswith("INSERT INTO INVENTARIO_CONTROLE") for q, _ in cur.queries)

    def test_abre_parcial_nao_pre_carrega_nada(self, monkeypatch):
        # Pedido explícito do usuário, 2026-07-23 ("o mais importante"):
        # tipo Parcial não pré-carrega estoque nenhum — só o arquivamento
        # do balanço anterior (INSERT...SELECT em inventario_old + DELETE)
        # roda, nenhum INSERT novo em `inventario`.
        cur = FakeCursor(one=[_ctrl(situacao="F"), None])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_sync("srv", "bd", "2026-07-22", "P", 10)
        assert r["success"] is True
        assert "Parcial" in r["message"]
        assert conn.committed is True
        insert_novo = [
            q for q, _ in cur.queries
            if q.strip().upper().startswith("INSERT INTO INVENTARIO ")  # com espaço: exclui "INVENTARIO_OLD"/"INVENTARIO_CONTROLE"
        ]
        assert insert_novo == []
        update_controle = [p for q, p in cur.queries if "UPDATE controle SET data_balanco" in q][0]
        assert update_controle == ("2026-07-22", "P")


class TestBuscarItem:
    def test_bloqueia_sem_balanco_aberto(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="F")])
        _patch(monkeypatch, cur)
        r = svc._buscar_item_sync("srv", "bd", "P001")
        assert r["success"] is False
        assert r["found"] is False

    def test_termo_vazio(self, monkeypatch):
        _patch(monkeypatch, FakeCursor())
        r = svc._buscar_item_sync("srv", "bd", "   ")
        assert r["found"] is False

    def test_encontra_em_pecas_pelo_codigo_int(self, monkeypatch):
        peca = {
            "codigo_int": "P001", "descricao": "Parafuso", "qtd": 10.0, "p_custo": 1.5,
            "p_venda": 3.0, "custo_inventario": 1.5, "custo_reposicao": 1.6,
        }
        # ordem: controle, pecas(codigo_int)=acha, inventario(ja contado)=None
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, None])
        _patch(monkeypatch, cur)
        r = svc._buscar_item_sync("srv", "bd", "P001")
        assert r["found"] is True
        assert r["origem"] == "pecas"
        assert r["ja_contado"] is False
        assert r["estoque_atual"] == 10.0

    def test_cai_para_veiculos_quando_nao_acha_em_pecas(self, monkeypatch):
        veic = {
            "codigo_int": "V001", "chassi": "9BW1234", "descricao": "Carro X",
            "val_custo": 50000.0, "preco_venda": 60000.0, "custo_inventario": 50000.0,
            "custo_reposicao": 50000.0,
        }
        # controle, pecas(codigo_int)=None, pecas(codigo_fab)=None, pecas(codigo_bar)=None,
        # veiculos(chassi)=acha, inventario(ja contado)=None
        cur = FakeCursor(one=[_ctrl(situacao="A"), None, None, None, veic, None])
        _patch(monkeypatch, cur)
        r = svc._buscar_item_sync("srv", "bd", "9BW1234")
        assert r["found"] is True
        assert r["origem"] == "veiculos"
        assert r["estoque_atual"] == 0.0

    def test_linha_existente_com_saldo_zero_nao_e_ja_contado(self, monkeypatch):
        # `inventario.estoque_balanco` tem DEFAULT 0 no banco (achado ao vivo
        # 2026-07-23) — uma Abertura Geral já cria a linha pra todo produto
        # com estoque, com estoque_balanco=0 por padrão do SQL Server, sem
        # ninguém ter digitado nada ainda. Row existir != já contado.
        peca = {
            "codigo_int": "P001", "descricao": "Parafuso", "qtd": 10.0, "p_custo": 1.5,
            "p_venda": 3.0, "custo_inventario": 1.5, "custo_reposicao": 1.6,
        }
        linha_recem_aberta = {
            "preco_custo": 1.5, "preco_venda": 3.0, "custo_inventario": 1.5,
            "custo_reposicao": 1.6, "estoque_balanco": 0.0,
        }
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, linha_recem_aberta])
        _patch(monkeypatch, cur)
        r = svc._buscar_item_sync("srv", "bd", "P001")
        assert r["ja_contado"] is False
        assert r["estoque_balanco_atual"] == 0.0

    def test_ja_contado_traz_valor_atual(self, monkeypatch):
        peca = {
            "codigo_int": "P001", "descricao": "Parafuso", "qtd": 10.0, "p_custo": 1.5,
            "p_venda": 3.0, "custo_inventario": 1.5, "custo_reposicao": 1.6,
        }
        contado = {
            "preco_custo": 1.5, "preco_venda": 3.0, "custo_inventario": 1.5,
            "custo_reposicao": 1.6, "estoque_balanco": 7.0, "contado_em": date(2026, 7, 23),
        }
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, contado])
        _patch(monkeypatch, cur)
        r = svc._buscar_item_sync("srv", "bd", "P001")
        assert r["ja_contado"] is True
        assert r["estoque_balanco_atual"] == 7.0

    def test_abertura_contabil_pre_carrega_saldo_mas_nao_e_ja_contado(self, monkeypatch):
        # Achado ao vivo 2026-07-23: a Abertura tipo Contábil pré-carrega
        # `estoque_balanco` = saldo do sistema (não-zero) pra TODO item, sem
        # ninguém ter digitado nada — `estoque_balanco<>0` sozinho não serve
        # mais de critério (funcionava só pro tipo Geral, onde a linha nasce
        # zerada). Só `contado_em IS NOT NULL` (setado apenas por
        # Incluir/Alterar) decide corretamente pros 2 tipos.
        peca = {
            "codigo_int": "P001", "descricao": "Parafuso", "qtd": 10.0, "p_custo": 1.5,
            "p_venda": 3.0, "custo_inventario": 1.5, "custo_reposicao": 1.6,
        }
        linha_abertura_contabil = {
            "preco_custo": 1.5, "preco_venda": 3.0, "custo_inventario": 1.5,
            "custo_reposicao": 1.6, "estoque_balanco": 10.0, "contado_em": None,
        }
        cur = FakeCursor(one=[_ctrl(situacao="A", tipo="C"), peca, linha_abertura_contabil])
        _patch(monkeypatch, cur)
        r = svc._buscar_item_sync("srv", "bd", "P001")
        assert r["ja_contado"] is False


class TestGravarItem:
    def test_incluir_bloqueia_sem_balanco_aberto(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="F")])
        _patch(monkeypatch, cur)
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "P001", "qtd": 5}, somar=True)
        assert r["success"] is False

    def test_incluir_item_novo_grava_qtd_digitada(self, monkeypatch):
        peca = {"codigo_int": "P001", "descricao": "x", "qtd": 10.0, "p_custo": 1.0, "p_venda": 2.0,
                "custo_inventario": 1.0, "custo_reposicao": 1.0}
        # controle, busca pecas, SELECT estoque_balanco existente = None
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, None])
        conn = _patch(monkeypatch, cur)
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "P001", "qtd": 5}, somar=True)
        assert r["success"] is True
        assert r["estoque_balanco"] == 5
        assert conn.committed is True
        assert any(q.strip().upper().startswith("INSERT INTO INVENTARIO ") for q, _ in cur.queries)

    def test_incluir_item_novo_grava_usuario_digitacao(self, monkeypatch):
        peca = {"codigo_int": "P001", "descricao": "x", "qtd": 10.0, "p_custo": 1.0, "p_venda": 2.0,
                "custo_inventario": 1.0, "custo_reposicao": 1.0}
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, None])
        _patch(monkeypatch, cur)
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "P001", "qtd": 5}, somar=True, usuario=42)
        assert r["success"] is True
        insert = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT INTO INVENTARIO ")][0]
        assert insert[-1] == 42  # usuario_digitacao é o último parâmetro do INSERT

    def test_alterar_item_existente_grava_usuario_digitacao(self, monkeypatch):
        peca = {"codigo_int": "P001", "descricao": "x", "qtd": 10.0, "p_custo": 1.0, "p_venda": 2.0,
                "custo_inventario": 1.0, "custo_reposicao": 1.0}
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, {"estoque_balanco": 3.0}])
        _patch(monkeypatch, cur)
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "P001", "qtd": 5}, somar=False, usuario=7)
        assert r["success"] is True
        update = [p for q, p in cur.queries if q.strip().upper().startswith("UPDATE INVENTARIO SET")][0]
        assert 7 in update

    def test_incluir_item_existente_soma(self, monkeypatch):
        peca = {"codigo_int": "P001", "descricao": "x", "qtd": 10.0, "p_custo": 1.0, "p_venda": 2.0,
                "custo_inventario": 1.0, "custo_reposicao": 1.0}
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, {"estoque_balanco": 3.0}])
        _patch(monkeypatch, cur)
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "P001", "qtd": 5}, somar=True)
        assert r["success"] is True
        assert r["estoque_balanco"] == 8.0

    def test_alterar_item_inexistente_bloqueia(self, monkeypatch):
        peca = {"codigo_int": "P001", "descricao": "x", "qtd": 10.0, "p_custo": 1.0, "p_venda": 2.0,
                "custo_inventario": 1.0, "custo_reposicao": 1.0}
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, None])
        _patch(monkeypatch, cur)
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "P001", "qtd": 5}, somar=False)
        assert r["success"] is False
        assert "não se encontra cadastrado" in r["message"]

    def test_alterar_item_existente_substitui(self, monkeypatch):
        peca = {"codigo_int": "P001", "descricao": "x", "qtd": 10.0, "p_custo": 1.0, "p_venda": 2.0,
                "custo_inventario": 1.0, "custo_reposicao": 1.0}
        cur = FakeCursor(one=[_ctrl(situacao="A"), peca, {"estoque_balanco": 3.0}])
        _patch(monkeypatch, cur)
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "P001", "qtd": 9}, somar=False)
        assert r["success"] is True
        assert r["estoque_balanco"] == 9

    def test_quantidade_invalida(self, monkeypatch):
        _patch(monkeypatch, FakeCursor())
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "P001", "qtd": "abc"}, somar=True)
        assert r["success"] is False

    def test_codigo_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A"), None, None, None, None])
        _patch(monkeypatch, cur)
        r = svc._gravar_item_sync("srv", "bd", {"codigo": "XXX", "qtd": 5}, somar=True)
        assert r["success"] is False
        assert "não está cadastrado" in r["message"]


class TestFechar:
    def test_bloqueia_sem_balanco_aberto(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="F")])
        _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", 10)
        assert r["success"] is False

    def test_tipo_contabil_nao_ajusta_estoque(self, monkeypatch):
        # controle(C) -> pula o bloco de ajuste inteiro -> SELECT fechamento -> None (insere fechamento)
        cur = FakeCursor(one=[_ctrl(situacao="A", tipo="C"), None])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", 10)
        assert r["success"] is True
        assert not any("INSERT INTO movimentacao" in q for q, _ in cur.queries)
        assert not any(q.strip().upper().startswith("UPDATE PECAS") for q, _ in cur.queries)
        assert conn.committed is True

    def test_tipo_parcial_tambem_ajusta_estoque(self, monkeypatch):
        # Parcial (2026-07-23, user-directed) entra no mesmo bloco de ajuste
        # do Geral — o próprio INNER JOIN contra `inventario` já escopa
        # certo sozinho (só os itens digitados têm linha, pro tipo Parcial),
        # sem precisar de nenhum `if` extra além de "!= C".
        cur = FakeCursor(one=[_ctrl(situacao="A", tipo="P"), None])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", 10)
        assert r["success"] is True
        assert any("INSERT INTO movimentacao" in q for q, _ in cur.queries)
        assert any(q.strip().upper().startswith("UPDATE P SET") for q, _ in cur.queries)
        assert conn.committed is True

    def test_tipo_geral_gera_ajuste_set_based(self, monkeypatch):
        # Reescrito 2026-07-23: _fechar_sync não itera itens em Python mais
        # (era o loop que travava a tela contra uma conexão real — ver
        # comentário no topo do bloco em inventario_service.py) — agora são
        # 2 comandos SQL set-based (INSERT...SELECT + UPDATE...FROM), sem
        # fetchall/fetchone por item. controle(G) -> SELECT fechamento -> None.
        cur = FakeCursor(one=[_ctrl(situacao="A", tipo="G"), None])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", 10)
        assert r["success"] is True

        ins_q, ins_p = [(q, p) for q, p in cur.queries if "INSERT INTO movimentacao" in q][0]
        assert "SELECT" in ins_q  # INSERT...SELECT, não INSERT...VALUES por linha
        assert "CASE WHEN" in ins_q and "'E00'" in ins_q and "'S00'" in ins_q
        assert "INNER JOIN pecas p ON p.codigo_int = i.codigo_interno" in ins_q
        assert "ABS(i.estoque_balanco - (i.estoque_atual + i.reservado)) > 0.0001" in ins_q
        assert ins_p == (_ctrl(situacao="A", tipo="G")["data_balanco"],) * 2

        upd_q, upd_p = [(q, p) for q, p in cur.queries if q.strip().upper().startswith("UPDATE P SET")][0]
        assert "FROM pecas p" in upd_q and "INNER JOIN inventario i ON i.codigo_interno = p.codigo_int" in upd_q
        assert upd_p == (_ctrl(situacao="A", tipo="G")["data_balanco"],)
        assert conn.committed is True

    def test_tipo_geral_ajuste_exclui_itens_de_veiculos_via_join(self, monkeypatch):
        # A exclusão de itens de `veiculos` (sem correspondência em `pecas`)
        # agora é feita pelo próprio INNER JOIN pecas no SQL, não por um
        # `try/except KeyError` em Python — este teste confirma que o JOIN
        # certo está na query, já que não há mais como simular isso via mock.
        cur = FakeCursor(one=[_ctrl(situacao="A", tipo="G"), None])
        _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", 10)
        assert r["success"] is True
        ins_q = [q for q, _ in cur.queries if "INSERT INTO movimentacao" in q][0]
        assert "INNER JOIN pecas p ON p.codigo_int = i.codigo_interno" in ins_q


class TestCancelar:
    def test_bloqueia_sem_balanco_aberto(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="F")])
        _patch(monkeypatch, cur)
        r = svc._cancelar_sync("srv", "bd", 10)
        assert r["success"] is False

    def test_cancela_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_sync("srv", "bd", 10)
        assert r["success"] is True
        assert any(q.strip().upper().startswith("DELETE FROM INVENTARIO ") for q, _ in cur.queries)
        assert any("situacao_balanco='C'" in q for q, _ in cur.queries)
        assert conn.committed is True


class TestRelatorioContagem:
    def test_agrupa_por_nivel1_e_ordena(self, monkeypatch):
        linhas = [
            {"codigo_interno": "P002", "descricao": "Zebra", "nivel1": "001"},
            {"codigo_interno": "P001", "descricao": "Abacate", "nivel1": "001"},
            {"codigo_interno": "P003", "descricao": "Sem grupo", "nivel1": ""},
        ]
        descrs = [{"nivel1": "001", "descr": "Bebidas"}]
        cur = FakeCursor(many=[linhas, descrs])
        _patch(monkeypatch, cur)
        r = svc._relatorio_contagem_sync("srv", "bd")
        assert r["success"] is True
        assert len(r["itens"]) == 3
        # dentro do grupo "Bebidas", ordenado por descrição (Abacate antes de Zebra)
        bebidas = [it for it in r["itens"] if it["grupo"] == "Bebidas"]
        assert [it["codigo_interno"] for it in bebidas] == ["P001", "P002"]
        sem_grupo = [it for it in r["itens"] if it["grupo"] == "Sem Nível"]
        assert len(sem_grupo) == 1

    def test_filtra_por_tipo_peca(self, monkeypatch):
        cur = FakeCursor(many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_contagem_sync("srv", "bd", tipos=[1])
        query, params = cur.queries[0]
        assert "tipo_peca IN (%s)" in query
        assert params == (1, 1)

    def test_somente_ativos_adiciona_filtro_situacao(self, monkeypatch):
        cur = FakeCursor(many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_contagem_sync("srv", "bd", somente_ativos=True)
        query, _ = cur.queries[0]
        assert query.count("situacao='A'") == 2  # pecas e veiculos

    def test_filtra_por_nivel_a_escolha_do_usuario(self, monkeypatch):
        # cascata: só as posições preenchidas filtram; posição vazia = "TODOS"
        cur = FakeCursor(many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_contagem_sync("srv", "bd", niveis=["001", "", "003", "", ""])
        query, params = cur.queries[0]
        assert query.count("nivel1=%s") == 2  # pecas e veiculos, cada um com seu WHERE
        assert query.count("nivel2=%s") == 0  # posição vazia não filtra
        assert query.count("nivel3=%s") == 2
        # tipos(3) + nivel1+nivel3 (2) pra pecas, repetido igual pra veiculos
        assert params == (0, 1, 2, "001", "003", 0, 1, 2, "001", "003")

    def test_sem_niveis_nao_filtra_por_nivel(self, monkeypatch):
        cur = FakeCursor(many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_contagem_sync("srv", "bd")
        query, _ = cur.queries[0]
        assert "nivel1=%s" not in query


class TestRelatorioConferencia:
    def test_agrupa_por_tipo_e_nivel(self, monkeypatch):
        linhas_tipo0 = [
            {"codigo_interno": "P001", "descricao": "Cerveja", "estoque_balanco": 10.0, "nivel1": "001"},
        ]
        descrs = [{"nivel1": "001", "descr": "Bebidas"}]
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[linhas_tipo0, descrs])
        _patch(monkeypatch, cur)
        r = svc._relatorio_conferencia_sync("srv", "bd", tipos=[0])
        assert r["success"] is True
        it = r["itens"][0]
        assert it["tipo_peca"] == 0
        assert it["tipo_descricao"] == "Revenda"
        assert it["grupo"] == "Bebidas"
        assert it["estoque_balanco"] == 10.0

    def test_sem_data_balanco_retorna_vazio(self, monkeypatch):
        cur = FakeCursor(one=[{"data_balanco": None, "situacao_balanco": "F", "tipo_balanco": ""}])
        _patch(monkeypatch, cur)
        r = svc._relatorio_conferencia_sync("srv", "bd")
        assert r["success"] is True
        assert r["itens"] == []

    def test_roda_uma_query_por_tipo_nao_uma_unica_com_in(self, monkeypatch):
        # Conferência replica as 3 abas fixas do legado — 3 grupos SEMPRE
        # separados, nunca somados entre si (não um único SELECT com IN).
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_conferencia_sync("srv", "bd", tipos=[0, 1])
        assert len(cur.queries) == 3  # controle + 1 query por tipo
        assert cur.queries[1][1][0] == 0 and cur.queries[1][1][2] == 0
        assert cur.queries[2][1][0] == 1 and cur.queries[2][1][2] == 1

    def test_listar_zerados_false_filtra_estoque_zero(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[], [], []])
        _patch(monkeypatch, cur)
        svc._relatorio_conferencia_sync("srv", "bd", tipos=[0, 1, 2], listar_zerados=False)
        for query, _ in cur.queries[1:]:
            assert "estoque_balanco<>0" in query

    def test_listar_zerados_true_nao_filtra(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[], [], []])
        _patch(monkeypatch, cur)
        svc._relatorio_conferencia_sync("srv", "bd", tipos=[0, 1, 2], listar_zerados=True)
        for query, _ in cur.queries[1:]:
            assert "estoque_balanco<>0" not in query


class TestRelatorioCritica:
    def test_calcula_estoque_sistema_e_agrupa(self, monkeypatch):
        linhas = [{
            "codigo_interno": "P001", "descricao": "Parafuso", "estoque_balanco": 4.0,
            "estoque_sistema": 10.0, "nivel1": "001",
        }]
        descrs = [{"nivel1": "001", "descr": "Ferragens"}]
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[linhas, descrs])
        _patch(monkeypatch, cur)
        r = svc._relatorio_critica_sync("srv", "bd")
        assert r["success"] is True
        it = r["itens"][0]
        assert it["estoque_balanco"] == 4.0
        assert it["estoque_sistema"] == 10.0
        assert it["grupo"] == "Ferragens"

    def test_sem_data_balanco_retorna_vazio(self, monkeypatch):
        cur = FakeCursor(one=[{"data_balanco": None, "situacao_balanco": "F", "tipo_balanco": ""}])
        _patch(monkeypatch, cur)
        r = svc._relatorio_critica_sync("srv", "bd")
        assert r["itens"] == []

    def test_data_diferente_usa_inventario_old(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="F", data=date(2026, 7, 1))], many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_critica_sync("srv", "bd", data="2026-06-15")
        query, params = cur.queries[-1]
        assert "FROM inventario_old i" in query
        # inventario_old não tem contado_em (não existe DDL pra ela) — o
        # filtro precisa ficar de fora quando lendo balanço histórico.
        assert "contado_em" not in query
        assert params[0] == "2026-06-15"

    def test_sem_data_override_usa_inventario_corrente(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A", data=date(2026, 7, 22))], many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_critica_sync("srv", "bd")
        query, _ = cur.queries[-1]
        assert "FROM inventario i" in query
        assert "inventario_old" not in query
        assert "contado_em IS NOT NULL" in query


class TestRelatorioResultado:
    def test_arredonda_unitario_antes_e_trunca_total_depois(self, monkeypatch):
        # Assimetria real do legado (FrmRelInvRes): arredonda o preço
        # unitário primeiro, SÓ DEPOIS multiplica pela quantidade e trunca
        # o total. 1.005 arredonda (half-up) pra 1.01 -> total 100*1.01=
        # 101.00. Se a ordem estivesse errada (truncar o unitário primeiro:
        # 1.00), o total daria 100.00 — valor diferente, prova a ordem certa.
        linhas = [{
            "codigo_interno": "P001", "descricao": "Filtro", "estoque": 100.0,
            "preco_venda": 1.005, "custo_inventario": 2.0, "custo_reposicao": 2.0,
            "nivel1": "001",
        }]
        descrs = [{"nivel1": "001", "descr": "Peças"}]
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[linhas, descrs])
        _patch(monkeypatch, cur)
        r = svc._relatorio_resultado_sync("srv", "bd")
        it = r["itens"][0]
        assert it["preco_unit_venda"] == 1.01
        assert it["total_venda"] == 101.0

    def test_sem_data_balanco_retorna_vazio(self, monkeypatch):
        cur = FakeCursor(one=[{"data_balanco": None, "situacao_balanco": "F", "tipo_balanco": ""}])
        _patch(monkeypatch, cur)
        r = svc._relatorio_resultado_sync("srv", "bd")
        assert r["itens"] == []

    def test_fonte_estoque_default_inventario(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_resultado_sync("srv", "bd")
        query, _ = cur.queries[1]
        assert "(i.estoque_balanco+i.reservado_os+i.estoque_cli-i.estoque_for) AS estoque" in query

    def test_fonte_estoque_fornecedor_troca_formula_so_do_lado_pecas(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_resultado_sync("srv", "bd", fonte_estoque="fornecedor")
        query, _ = cur.queries[1]
        assert "(i.estoque_for) AS estoque" in query
        # lado veículos nunca usa Estoque Fornecedor, mesmo comportamento do legado
        assert "(i.estoque_balanco+i.reservado_os) AS estoque" in query


class TestRelatorioDivergencia:
    def test_calcula_diferenca_e_preco_total_com_sinal(self, monkeypatch):
        linhas = [{
            "codigo_interno": "P001", "descricao": "Correia", "estoque_sistema": 10.0,
            "estoque_balanco": 7.0, "diferenca": -3.0, "preco_unitario": 5.5, "preco_total": -16.5,
            "nivel1": "001",
        }]
        descrs = [{"nivel1": "001", "descr": "Peças"}]
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[linhas, descrs])
        _patch(monkeypatch, cur)
        r = svc._relatorio_divergencia_sync("srv", "bd")
        it = r["itens"][0]
        assert it["diferenca"] == -3.0
        assert it["preco_total"] == -16.5  # trunca2 preserva sinal (não usa abs)

    def test_preco_mapeia_para_coluna_certa(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_divergencia_sync("srv", "bd", preco="custo_reposicao")
        query, _ = cur.queries[-1]
        assert "i.custo_reposicao AS preco_unitario" in query
        assert "contado_em IS NOT NULL" in query

    def test_veiculos_usa_mesma_formula_de_pecas_sem_bug_do_legado(self, monkeypatch):
        # Corrige um bug real do VB6 (`FrmRelInvDiv`): o lado veículos do
        # UNION usava uma variável `um` nunca declarada em lugar nenhum do
        # projeto (SQL malformado). Aqui o lado veículos usa a MESMA
        # fórmula estoque_atual+reservado do lado peças.
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[], []])
        _patch(monkeypatch, cur)
        svc._relatorio_divergencia_sync("srv", "bd")
        query, _ = cur.queries[-1]
        assert query.count("(i.estoque_atual+i.reservado)") >= 4

    def test_ordenacao_por_diferenca(self, monkeypatch):
        linhas = [
            {"codigo_interno": "P001", "descricao": "B", "estoque_sistema": 1, "estoque_balanco": 1,
             "diferenca": 5.0, "preco_unitario": 1.0, "preco_total": 5.0, "nivel1": ""},
            {"codigo_interno": "P002", "descricao": "A", "estoque_sistema": 1, "estoque_balanco": 1,
             "diferenca": -2.0, "preco_unitario": 1.0, "preco_total": -2.0, "nivel1": ""},
        ]
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[linhas])
        _patch(monkeypatch, cur)
        r = svc._relatorio_divergencia_sync("srv", "bd", ordenar="diferenca")
        assert [it["codigo_interno"] for it in r["itens"]] == ["P002", "P001"]


class TestListarItens:
    def test_sem_balanco_aberto_retorna_vazio(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="F")])
        _patch(monkeypatch, cur)
        r = svc._listar_itens_sync("srv", "bd")
        assert r["success"] is True
        assert r["itens"] == []

    def test_lista_itens_contados_com_quem_digitou(self, monkeypatch):
        itens = [
            {"codigo_interno": "P001", "descricao": "Parafuso", "estoque_balanco": 5.0,
             "estoque_atual": 10.0, "usuario_digitacao": 42, "usuario_nome": "JOAO"},
            {"codigo_interno": "P002", "descricao": "Porca", "estoque_balanco": 3.0,
             "estoque_atual": 3.0, "usuario_digitacao": None, "usuario_nome": None},
        ]
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._listar_itens_sync("srv", "bd")
        assert r["success"] is True
        assert len(r["itens"]) == 2
        assert r["itens"][0]["usuario_nome"] == "JOAO"
        # confere que o filtro/ordenação real usados na query fazem sentido
        # com o item de negócio (só itens já contados, contado_em IS NOT
        # NULL — não estoque_balanco<>0, que quebra pro tipo Contábil)
        query = cur.queries[-1][0]
        assert "contado_em IS NOT NULL" in query
        assert "nome_guerra" in query

    def test_filtra_por_usuario_quando_informado(self, monkeypatch):
        # não-Gerente/Supervisor/Master: frontend manda o próprio código, a
        # query já reduz de verdade (não é só esconder na tela).
        itens = [{"codigo_interno": "P001", "descricao": "Parafuso", "estoque_balanco": 5.0,
                   "estoque_atual": 10.0, "usuario_digitacao": 7, "usuario_nome": "MARIA"}]
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._listar_itens_sync("srv", "bd", usuario=7)
        assert r["success"] is True
        query, params = cur.queries[-1]
        assert "usuario_digitacao=%s" in query
        assert params[-1] == 7

    def test_filtra_sem_usuario_usa_is_null(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._listar_itens_sync("srv", "bd", sem_usuario=True)
        assert r["success"] is True
        query, params = cur.queries[-1]
        assert "usuario_digitacao IS NULL" in query
        assert "usuario_digitacao=%s" not in query
        assert len(params) == 1  # só a data, sem parâmetro de usuário


class TestResumoPorUsuario:
    def test_sem_balanco_aberto_retorna_vazio(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="F")])
        _patch(monkeypatch, cur)
        r = svc._resumo_por_usuario_sync("srv", "bd")
        assert r["success"] is True
        assert r["resumo"] == []

    def test_agrupa_e_conta_por_usuario(self, monkeypatch):
        resumo = [
            {"usuario_digitacao": 1, "usuario_nome": "TESTE", "total": 3},
            {"usuario_digitacao": 2, "usuario_nome": "ESTELA", "total": 1},
            {"usuario_digitacao": None, "usuario_nome": None, "total": 2},
        ]
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[resumo])
        _patch(monkeypatch, cur)
        r = svc._resumo_por_usuario_sync("srv", "bd")
        assert r["success"] is True
        assert len(r["resumo"]) == 3
        query = cur.queries[-1][0]
        assert "GROUP BY" in query
        assert "COUNT(*)" in query

    def test_sem_usuario_nao_filtra(self, monkeypatch):
        cur = FakeCursor(one=[_ctrl(situacao="A")], many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_itens_sync("srv", "bd", usuario=None)
        query, _ = cur.queries[-1]
        assert "usuario_digitacao=%s" not in query


class TestInventarioAutomaticoMensal:
    def test_ja_rodou_este_mes_nao_faz_nada(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_automatico_mensal_sync(cur, date(2026, 7, 23))
        assert rodou is False
        assert len(cur.queries) == 1  # só o SELECT de checagem, nada mais

    def test_roda_e_insere_snapshot_de_pecas(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_automatico_mensal_sync(cur, date(2026, 7, 23))
        assert rodou is True
        insert_query = [q for q, _ in cur.queries if "INSERT INTO inventario_old" in q][0]
        assert "FROM pecas" in insert_query
        assert "qtd<1000000" in insert_query
        assert "tipo_peca>=0" in insert_query
        # usa o dia 1 do mês corrente, não o dia informado
        insert_params = [p for q, p in cur.queries if "INSERT INTO inventario_old" in q][0]
        assert insert_params[0] == date(2026, 7, 1)
        assert any("UPDATE inventario_controle SET fechamento" in q for q, _ in cur.queries)


class TestInventarioPostoAutomaticoMensal:
    def test_ja_fechado_nao_faz_nada(self, monkeypatch):
        cur = FakeCursor(one=[{"fechamento": date(2026, 7, 1)}])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_posto_automatico_mensal_sync(cur, date(2026, 7, 23))
        assert rodou is False
        assert len(cur.queries) == 1

    def test_sem_combustiveis_cadastrados_marca_fechado(self, monkeypatch):
        cur = FakeCursor(one=[None], many=[[]])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_posto_automatico_mensal_sync(cur, date(2026, 7, 23))
        assert rodou is True
        assert any("UPDATE inventario_controle SET fechamento" in q for q, _ in cur.queries)

    def test_combustivel_sem_leitura_nao_fecha(self, monkeypatch):
        # 1 combustível cadastrado, mas a junção com tanque_estoque não traz nada
        cur = FakeCursor(one=[None], many=[[{"codigo": 1}], []])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_posto_automatico_mensal_sync(cur, date(2026, 7, 23))
        assert rodou is True
        assert not any("UPDATE inventario_controle SET fechamento" in q for q, _ in cur.queries)

    def test_com_leitura_insere_e_fecha(self, monkeypatch):
        linha = {"codigo_int": "P001", "custo_medio": 5.0, "totvolume": 100.0}
        # one: [controle=None, inventario_old(já existe?)=None]
        cur = FakeCursor(one=[None, None], many=[[{"codigo": 1}], [linha]])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_posto_automatico_mensal_sync(cur, date(2026, 7, 23))
        assert rodou is True
        insert_old = [(q, p) for q, p in cur.queries if q.strip().upper().startswith("INSERT INTO INVENTARIO_OLD")]
        assert len(insert_old) == 1
        assert insert_old[0][1][0] == "P001"
        assert any("UPDATE inventario_controle SET fechamento" in q for q, _ in cur.queries)

    def test_ja_inserido_nao_duplica_mas_conta_como_feito(self, monkeypatch):
        linha = {"codigo_int": "P001", "custo_medio": 5.0, "totvolume": 100.0}
        # one: [controle=None, inventario_old(já existe?)={"ok":1}]
        cur = FakeCursor(one=[None, {"ok": 1}], many=[[{"codigo": 1}], [linha]])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_posto_automatico_mensal_sync(cur, date(2026, 7, 23))
        assert rodou is True
        assert not any(q.strip().upper().startswith("INSERT INTO INVENTARIO_OLD") for q, _ in cur.queries)
        # mesmo sem inserir de novo, já tinha leitura -> conta como combustível concluído -> fecha
        assert any("UPDATE inventario_controle SET fechamento" in q for q, _ in cur.queries)


class TestInventarioContabilDiario:
    def test_ja_rodou_hoje_nao_faz_nada(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_contabil_diario_sync(cur, date(2026, 7, 23))
        assert rodou is False
        assert not any("INSERT INTO inventario_contabil" in q for q, _ in cur.queries)

    def test_roda_e_insere_pecas_e_os(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        rodou = svc._inventario_contabil_diario_sync(cur, date(2026, 7, 23))
        assert rodou is True
        assert any(q.strip().upper().startswith("DELETE FROM INVENTARIO_CONTABIL") for q, _ in cur.queries)
        pecas_q, pecas_p = [(q, p) for q, p in cur.queries if q.strip().upper().startswith("INSERT INTO INVENTARIO_CONTABIL (")][0]
        assert "FROM pecas WHERE situacao='A'" in pecas_q
        assert pecas_p[0] == date(2026, 7, 23)
        os_q, os_p = [(q, p) for q, p in cur.queries if "INSERT INTO inventario_contabil_os" in q][0]
        # nunca replicar a data hardcoded do legado ('2021-04-15') — sempre a data informada
        assert os_p[0] == date(2026, 7, 23)
        assert "2021-04-15" not in os_q


class TestExecutarRotinasAutomaticas:
    def test_posto_ativo_so_roda_mensal_posto(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "modulo_posto_ativo", lambda c: True)
        chamadas = []
        monkeypatch.setattr(svc, "_inventario_posto_automatico_mensal_sync", lambda c, h: chamadas.append("posto") or True)
        monkeypatch.setattr(svc, "_inventario_automatico_mensal_sync", lambda c, h: chamadas.append("geral") or True)
        monkeypatch.setattr(svc, "_inventario_contabil_diario_sync", lambda c, h: chamadas.append("diario") or True)
        r = svc._executar_rotinas_automaticas_sync("srv", "bd")
        assert r["success"] is True
        assert chamadas == ["posto"]
        assert conn.committed is True

    def test_sem_posto_roda_mensal_e_diario(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "modulo_posto_ativo", lambda c: False)
        chamadas = []
        monkeypatch.setattr(svc, "_inventario_posto_automatico_mensal_sync", lambda c, h: chamadas.append("posto") or True)
        monkeypatch.setattr(svc, "_inventario_automatico_mensal_sync", lambda c, h: chamadas.append("geral") or True)
        monkeypatch.setattr(svc, "_inventario_contabil_diario_sync", lambda c, h: chamadas.append("diario") or True)
        r = svc._executar_rotinas_automaticas_sync("srv", "bd")
        assert r["success"] is True
        assert chamadas == ["geral", "diario"]

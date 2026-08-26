"""Testes unitários de os_itens_service — cobertura do campo Situação/
Destino do item (`os_produto.situacao`, réplica de `Destino(2)` do legado
`FrmTraOsNew.frm`: 0=Cliente paga, 1=Garantia, 2=Interno, 3=Contrato),
adicionado pra Fase 1 da O.S. Completa. Antes desta mudança o INSERT
gravava sempre `0` (literal na query, sem parâmetro) e o SELECT de listagem
nem trazia a coluna — a O.S. Mobile continua sempre gravando 0 (default do
schema, sem combobox na tela)."""
import asyncio
from datetime import date

import services.os_itens_service as svc
from models.schemas import OSItemSaveRequest, PontuacaoSaveRequest, AutorizacaoItensRequest, AlterarExecutorRequest


class FakeCursor:
    def __init__(self, one=None, many=None, rowcount=1):
        self._one = list(one or [])
        self._many = list(many or [])
        self.rowcount = rowcount
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
    # Bypass do gate de Checklist de Entrada de Veículo obrigatório
    # (`_checklist_veiculo_pendente_bloqueia`, pedido_common.py,
    # 2026-08-26) — orthogonal à maioria destes testes, que não simulam a
    # query extra que essa checagem faz. Testado à parte em
    # TestChecklistObrigatorioBloqueiaAddItem, sem este bypass.
    monkeypatch.setattr(svc, "_checklist_veiculo_pendente_bloqueia", lambda *a, **k: None)
    return conn


def _item_req(**over):
    base = dict(
        servidor="srv", banco="bd", produto="P100", qtd=1, valor_unitario=50.0,
        complemento="", desconto=0, desconto_pct=0, acrescimo=0,
        vendedor=20, executor=21, situacao=0,
        usuario_codigo=-2, funcao=None, classe=1, plataforma="web",
    )
    base.update(over)
    return OSItemSaveRequest(**base)


PECA = {"tipo": "P", "valor": 50.0, "custo": 30.0}


class TestAddItemSituacao:
    def test_default_grava_situacao_zero(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"cod_os_prod": 900}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        monkeypatch.setattr(svc, "_modulo_servicos_ativo", lambda cur_: True)
        r = svc._add_item_sync(_item_req(situacao=None), 1)
        assert r["success"] is True
        insert_p = next(p for q, p in cur.queries if q.strip().startswith("INSERT INTO os_produto"))
        assert insert_p[-1] == 0  # situacao é o último parâmetro do INSERT

    def test_situacao_garantia_gravada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"cod_os_prod": 901}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        monkeypatch.setattr(svc, "_modulo_servicos_ativo", lambda cur_: True)
        r = svc._add_item_sync(_item_req(situacao=1), 1)
        assert r["success"] is True
        insert_p = next(p for q, p in cur.queries if q.strip().startswith("INSERT INTO os_produto"))
        assert insert_p[-1] == 1


SERVICO = {"tipo": "S", "valor": 80.0, "custo": 0.0}


class TestAddItemAgendaSplit:
    """Item de Serviço com o módulo Agenda (Assistência/Clínica) ativo vira
    N linhas (quant=1 cada) em vez de 1 linha com quant=N — cada linha é 1
    atendimento agendável (ex.: 3 manutenções no mês, datas diferentes,
    mesma O.S.). Réplica do `clinica_split` já usado pelo Pedido Geral
    (`pedido_completo_service._add_item_completo_sync`). Ver PENDENCIAS.md
    > "O.S. Completa" > "Agendar item de Serviço"."""

    def test_servico_com_modulo_ativo_gera_n_linhas(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"CLINICA": 0, "Assistencia": 1},
            {"cod_os_prod": 900}, {"cod_os_prod": 901}, {"cod_os_prod": 902},
            {"valor": 240.0},
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(SERVICO))
        monkeypatch.setattr(svc, "_modulo_servicos_ativo", lambda cur_: True)
        r = svc._add_item_sync(_item_req(produto="S200", qtd=3), 1)
        assert r["success"] is True
        assert r["os_agenda_split"] is True
        assert r["cod_os_prods"] == [900, 901, 902]
        assert r["cod_os_prod"] == 900
        inserts = [(q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os_produto")]
        assert len(inserts) == 3
        for query, _ in inserts:
            assert "%s,%s,1,%s" in query  # quant gravado como literal 1, não parâmetro

    def test_quantidade_fracionaria_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"CLINICA": 0, "Assistencia": 1}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(SERVICO))
        monkeypatch.setattr(svc, "_modulo_servicos_ativo", lambda cur_: True)
        r = svc._add_item_sync(_item_req(produto="S200", qtd=2.5), 1)
        assert r["success"] is False
        assert "inteiro" in r["message"].lower()

    def test_servico_com_modulo_desligado_nao_desdobra(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"CLINICA": 0, "Assistencia": 0}, {"cod_os_prod": 950}, {"valor": 240.0},
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(SERVICO))
        monkeypatch.setattr(svc, "_modulo_servicos_ativo", lambda cur_: True)
        monkeypatch.setattr(svc, "_exige_aprovacao_itens_os_ativo", lambda cur_: False)
        monkeypatch.setattr(svc, "_mover_estoque", lambda *a, **k: None)
        r = svc._add_item_sync(_item_req(produto="S200", qtd=3), 1)
        assert r["success"] is True
        assert r["os_agenda_split"] is False
        assert r["cod_os_prods"] == [950]
        inserts = [(q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os_produto")]
        assert len(inserts) == 1
        assert inserts[0][1][2] == 3.0  # quant = qtd inteira, não desdobrada

    def test_produto_nunca_desdobra_e_nao_consulta_modulo_agenda(self, monkeypatch):
        """Produto (tipo 'P') nunca desdobra — `prod["tipo"] == "S"` no
        `and` faz o Python nem chamar `_modulo_agenda_ativo` (short-circuit),
        então nenhuma query extra é feita pra produto."""
        cur = FakeCursor(one=[{"situacao": "A"}, {"cod_os_prod": 960}, {"valor": 100.0}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        monkeypatch.setattr(svc, "_modulo_servicos_ativo", lambda cur_: True)
        monkeypatch.setattr(svc, "_exige_aprovacao_itens_os_ativo", lambda cur_: False)
        monkeypatch.setattr(svc, "_mover_estoque", lambda *a, **k: None)
        r = svc._add_item_sync(_item_req(qtd=3), 1)
        assert r["success"] is True
        assert r["os_agenda_split"] is False
        assert not any("controle_configuracao" in q for q, _ in cur.queries)


class TestUpdateItemSituacao:
    def test_atualiza_situacao(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"quant": 1.0, "codigo_interno": "P100"}])
        _patch(monkeypatch, cur)
        r = svc._update_item_sync(_item_req(situacao=3), 1, 900)
        assert r["success"] is True
        update_q, update_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os_produto"))
        assert "situacao=%s" in update_q
        assert update_p[8] == 3  # situacao logo antes de cod_os_prod/os no tuple


class TestListItensSituacao:
    def test_lista_traz_situacao_da_linha(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}],
            many=[[{
                "cod_os_prod": 900, "codigo_interno": "P100", "quant": 1.0, "p_venda": 50.0,
                "preco_unitario": 50.0, "desconto": 0, "acrescimo": 0, "vendedor": 20, "executor": 21,
                "descricao_produto_os": "", "situacao": 2,
                "peca_desc": "Produto Teste", "peca_fab": "FAB100", "peca_uni": "UN",
                "serv_desc": None, "vend_nome": "Vendedor", "vend_guerra": "", "exec_nome": "Executor", "exec_guerra": "",
            }]],
        )
        _patch(monkeypatch, cur)
        r = svc._list_itens_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["items"][0]["situacao"] == 2

    def test_lista_situacao_ausente_vira_zero(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}],
            many=[[{
                "cod_os_prod": 901, "codigo_interno": "P100", "quant": 1.0, "p_venda": 50.0,
                "preco_unitario": 50.0, "desconto": 0, "acrescimo": 0, "vendedor": None, "executor": None,
                "descricao_produto_os": "", "situacao": None,
                "peca_desc": "Produto Teste", "peca_fab": "FAB100", "peca_uni": "UN",
                "serv_desc": None, "vend_nome": "", "vend_guerra": "", "exec_nome": "", "exec_guerra": "",
            }]],
        )
        _patch(monkeypatch, cur)
        r = svc._list_itens_sync("srv", "bd", 1)
        assert r["items"][0]["situacao"] == 0

    def test_lista_traz_pontuacao(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}],
            many=[[{
                "cod_os_prod": 902, "codigo_interno": "P100", "quant": 1.0, "p_venda": 50.0,
                "preco_unitario": 50.0, "desconto": 0, "acrescimo": 0, "vendedor": 20, "executor": 21,
                "descricao_produto_os": "", "situacao": 0,
                "Pontuacao_A": 80, "Pontuacao_E": 90, "Pontuacao_V": 70,
                "peca_desc": "Produto Teste", "peca_fab": "FAB100", "peca_uni": "UN",
                "serv_desc": None, "vend_nome": "", "vend_guerra": "", "exec_nome": "", "exec_guerra": "",
            }]],
        )
        _patch(monkeypatch, cur)
        r = svc._list_itens_sync("srv", "bd", 1)
        item = r["items"][0]
        assert item["pontuacao_a"] == 80 and item["pontuacao_e"] == 90 and item["pontuacao_v"] == 70


class TestListItensAgendamento:
    """Enriquecimento com `item.agendamento` (módulo Assistência,
    `AGENDA`/`AGENDA_OS`) — mesmo padrão já usado pro Pedido Geral
    (`AGENDA`/`AGENDA_PEDIDO`), ver `agenda_service.py`."""

    def test_item_com_agendamento_vinculado(self, monkeypatch):
        from datetime import date
        item_row = {
            "cod_os_prod": 900, "codigo_interno": "S100", "quant": 1.0, "p_venda": 80.0,
            "preco_unitario": 80.0, "desconto": 0, "acrescimo": 0, "vendedor": None, "executor": None,
            "descricao_produto_os": "", "situacao": 0,
            "peca_desc": None, "peca_fab": "", "peca_uni": "",
            "serv_desc": "Diagnóstico", "vend_nome": "", "vend_guerra": "", "exec_nome": "", "exec_guerra": "",
        }
        agenda_row = {
            "cod_os_prod": 900, "codagenda": 950, "data": date(2026, 8, 3), "hora_ini": "14:00:00",
            "situacao_atendimento": "Confirmado", "funcionario": 10, "profissional": "MARIA",
        }
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[item_row], [agenda_row]])
        _patch(monkeypatch, cur)
        r = svc._list_itens_sync("srv", "bd", 1)
        assert r["success"] is True
        item = r["items"][0]
        assert item["agendamento"]["codagenda"] == 950
        assert item["agendamento"]["profissional"] == "MARIA"
        assert item["agendamento"]["hora_ini"] == "14:00"

    def test_item_sem_agendamento_fica_sem_chave(self, monkeypatch):
        item_row = {
            "cod_os_prod": 901, "codigo_interno": "S100", "quant": 1.0, "p_venda": 80.0,
            "preco_unitario": 80.0, "desconto": 0, "acrescimo": 0, "vendedor": None, "executor": None,
            "descricao_produto_os": "", "situacao": 0,
            "peca_desc": None, "peca_fab": "", "peca_uni": "",
            "serv_desc": "Diagnóstico", "vend_nome": "", "vend_guerra": "", "exec_nome": "", "exec_guerra": "",
        }
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[item_row], []])
        _patch(monkeypatch, cur)
        r = svc._list_itens_sync("srv", "bd", 1)
        assert "agendamento" not in r["items"][0]


def _pontuacao_req(**over):
    base = dict(servidor="srv", banco="bd", pontuacao_e=90, pontuacao_v=70, pontuacao_a=80,
                usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return PontuacaoSaveRequest(**base)


class TestSavePontuacao:
    def test_item_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_pontuacao_sync(_pontuacao_req(), 1, 900)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_sucesso_grava_os_3_valores(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_pontuacao_sync(_pontuacao_req(), 1, 900)
        assert r["success"] is True
        assert conn.committed is True
        update_q, update_p = cur.queries[-1]
        assert "Pontuacao_E=%s, Pontuacao_V=%s, Pontuacao_A=%s" in update_q
        assert update_p == (90, 70, 80, 900, 1)

    def test_valor_fora_da_faixa_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_pontuacao_sync(_pontuacao_req(pontuacao_e=1000), 1, 900)
        assert r["success"] is False
        assert "0 e 999" in r["message"]
        # bloqueia antes de abrir conexão/consultar o item
        assert cur.queries == []

    def test_valor_negativo_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_pontuacao_sync(_pontuacao_req(pontuacao_a=-1), 1, 900)
        assert r["success"] is False

    def test_permite_gravar_so_um_dos_tres_campos(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._save_pontuacao_sync(_pontuacao_req(pontuacao_e=50, pontuacao_v=None, pontuacao_a=None), 1, 900)
        assert r["success"] is True


# ---------------------------------------------------------------------------
# Autorização/Expedição de Itens (migração de FrmTraOsNew.frm, Revenda) —
# ver pedido_common._exige_aprovacao_itens_os_ativo/_exige_expedicao_itens_os_ativo.
# ---------------------------------------------------------------------------

class TestAddItemEstoqueCondicional:
    def test_reserva_estoque_por_padrao(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"cod_os_prod": 900}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        monkeypatch.setattr(svc, "_modulo_servicos_ativo", lambda cur_: True)
        monkeypatch.setattr(svc, "_exige_aprovacao_itens_os_ativo", lambda cur_: False)
        movs = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda cur_, cod, delta, campo: movs.append((cod, delta, campo)))
        r = svc._add_item_sync(_item_req(), 1)
        assert r["success"] is True
        assert movs == [("P100", 1.0, "reservado_os")]

    def test_nao_reserva_quando_exige_aprovacao(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"cod_os_prod": 901}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        monkeypatch.setattr(svc, "_modulo_servicos_ativo", lambda cur_: True)
        monkeypatch.setattr(svc, "_exige_aprovacao_itens_os_ativo", lambda cur_: True)
        movs = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda cur_, cod, delta, campo: movs.append((cod, delta, campo)))
        r = svc._add_item_sync(_item_req(), 1)
        assert r["success"] is True
        assert movs == []


class TestUpdateItemEstoqueCondicional:
    def test_ajusta_quando_ja_autorizado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"quant": 1.0, "codigo_interno": "P100", "data_autorizacao": date(2026, 7, 1)}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_aprovacao_itens_os_ativo", lambda cur_: True)
        movs = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda cur_, cod, delta, campo: movs.append((cod, delta, campo)))
        r = svc._update_item_sync(_item_req(qtd=3), 1, 900)
        assert r["success"] is True
        assert movs == [("P100", 2.0, "reservado_os")]

    def test_nao_ajusta_quando_exige_aprovacao_e_nao_autorizado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"quant": 1.0, "codigo_interno": "P100", "data_autorizacao": None}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_aprovacao_itens_os_ativo", lambda cur_: True)
        movs = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda cur_, cod, delta, campo: movs.append((cod, delta, campo)))
        r = svc._update_item_sync(_item_req(qtd=3), 1, 900)
        assert r["success"] is True
        assert movs == []


class TestDeleteItemEstoqueCondicional:
    def test_estorna_e_limpa_trilha_quando_ja_autorizado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"quant": 2.0, "codigo_interno": "P100", "data_autorizacao": date(2026, 7, 1)}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_aprovacao_itens_os_ativo", lambda cur_: True)
        movs = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda cur_, cod, delta, campo: movs.append((cod, delta, campo)))
        r = svc._delete_item_sync("srv", "bd", 1, 900)
        assert r["success"] is True
        assert movs == [("P100", -2.0, "reservado_os")]
        del_q, del_p = next((q, p) for q, p in cur.queries if q.strip().startswith("DELETE FROM os_autorizacao_itens"))
        assert del_p == (900,)

    def test_nao_estorna_quando_exige_aprovacao_e_nao_autorizado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"quant": 2.0, "codigo_interno": "P100", "data_autorizacao": None}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_aprovacao_itens_os_ativo", lambda cur_: True)
        movs = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda cur_, cod, delta, campo: movs.append((cod, delta, campo)))
        r = svc._delete_item_sync("srv", "bd", 1, 900)
        assert r["success"] is True
        assert movs == []
        assert not any(q.strip().startswith("DELETE FROM os_autorizacao_itens") for q, p in cur.queries)


def _autorizacao_req(**over):
    base = dict(servidor="srv", banco="bd", cod_os_prod=[900], usuario_alteracao=-2, classe=1, plataforma="web")
    base.update(over)
    return AutorizacaoItensRequest(**base)


class TestAutorizarItens:
    def test_autoriza_e_reserva_estoque(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"quant": 2.0, "codigo_interno": "P100", "data_autorizacao": None, "data_expedicao": None},
            {"cod_os_autorizacao": 500},
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_expedicao_itens_os_ativo", lambda cur_: False)
        movs = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda cur_, cod, delta, campo: movs.append((cod, delta, campo)))
        r = svc._autorizar_itens_sync(_autorizacao_req(), 1)
        assert r["success"] is True
        assert r["autorizados"] == [900]
        assert r["bloqueados"] == []
        assert movs == [("P100", 2.0, "reservado_os")]
        upd_q, upd_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os_produto"))
        assert upd_p == (-2, 900)

    def test_bloqueia_se_ja_autorizado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"quant": 1.0, "codigo_interno": "P100", "data_autorizacao": date(2026, 7, 1), "data_expedicao": None},
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_expedicao_itens_os_ativo", lambda cur_: False)
        r = svc._autorizar_itens_sync(_autorizacao_req(), 1)
        assert r["success"] is True
        assert r["autorizados"] == []
        assert r["bloqueados"] == [900]

    def test_bloqueia_se_exige_expedicao_e_nao_expedido(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"quant": 1.0, "codigo_interno": "P100", "data_autorizacao": None, "data_expedicao": None},
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_expedicao_itens_os_ativo", lambda cur_: True)
        r = svc._autorizar_itens_sync(_autorizacao_req(), 1)
        assert r["bloqueados"] == [900]

    def test_permite_quando_exige_expedicao_e_ja_expedido(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"quant": 1.0, "codigo_interno": "P100", "data_autorizacao": None, "data_expedicao": date(2026, 7, 1)},
            {"cod_os_autorizacao": 501},
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_expedicao_itens_os_ativo", lambda cur_: True)
        monkeypatch.setattr(svc, "_mover_estoque", lambda *a, **k: None)
        r = svc._autorizar_itens_sync(_autorizacao_req(), 1)
        assert r["autorizados"] == [900]

    def test_bloqueia_por_area_de_estoque(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"quant": 1.0, "codigo_interno": "P100", "data_autorizacao": None, "data_expedicao": None},
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_exige_expedicao_itens_os_ativo", lambda cur_: False)
        monkeypatch.setattr(svc, "_tem_area_estoque", lambda cur_, produto, usuario: False)
        r = svc._autorizar_itens_sync(_autorizacao_req(usuario_alteracao=10), 1)
        assert r["bloqueados"] == [900]
        assert r["message"]

    def test_os_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._autorizar_itens_sync(_autorizacao_req(), 1)
        assert r["success"] is False

    def test_sem_itens_selecionados(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._autorizar_itens_sync(_autorizacao_req(cod_os_prod=[]), 1)
        assert r["success"] is False
        assert "nenhum" in r["message"].lower()


class TestRemoverAutorizacao:
    def test_remove_e_estorna_estoque(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"quant": 2.0, "codigo_interno": "P100", "data_autorizacao": date(2026, 7, 1)},
        ])
        _patch(monkeypatch, cur)
        movs = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda cur_, cod, delta, campo: movs.append((cod, delta, campo)))
        r = svc._remover_autorizacao_sync(_autorizacao_req(), 1)
        assert r["success"] is True
        assert r["removidos"] == [900]
        assert movs == [("P100", -2.0, "reservado_os")]
        del_q, del_p = next((q, p) for q, p in cur.queries if q.strip().startswith("DELETE FROM os_autorizacao_itens"))
        assert del_p == (900,)

    def test_ignora_item_nao_autorizado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"quant": 1.0, "codigo_interno": "P100", "data_autorizacao": None},
        ])
        _patch(monkeypatch, cur)
        r = svc._remover_autorizacao_sync(_autorizacao_req(), 1)
        assert r["removidos"] == []

    def test_os_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._remover_autorizacao_sync(_autorizacao_req(), 1)
        assert r["success"] is False


class TestExpedirItens:
    def test_expede_sem_mexer_estoque(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"codigo_interno": "P100", "data_autorizacao": None, "data_expedicao": None},
        ])
        _patch(monkeypatch, cur)
        called = []
        monkeypatch.setattr(svc, "_mover_estoque", lambda *a, **k: called.append(a))
        r = svc._expedir_itens_sync(_autorizacao_req(), 1)
        assert r["success"] is True
        assert r["expedidos"] == [900]
        assert called == []

    def test_bloqueia_se_ja_autorizado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"codigo_interno": "P100", "data_autorizacao": date(2026, 7, 1), "data_expedicao": None},
        ])
        _patch(monkeypatch, cur)
        r = svc._expedir_itens_sync(_autorizacao_req(), 1)
        assert r["bloqueados"] == [900]

    def test_bloqueia_por_area_de_estoque(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"codigo_interno": "P100", "data_autorizacao": None, "data_expedicao": None},
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_tem_area_estoque", lambda cur_, produto, usuario: False)
        r = svc._expedir_itens_sync(_autorizacao_req(usuario_alteracao=10), 1)
        assert r["bloqueados"] == [900]


class TestRemoverExpedicao:
    def test_remove_expedicao(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"data_expedicao": date(2026, 7, 1), "data_autorizacao": None},
        ])
        _patch(monkeypatch, cur)
        r = svc._remover_expedicao_sync(_autorizacao_req(), 1)
        assert r["success"] is True
        assert r["removidos"] == [900]

    def test_ignora_se_ja_autorizado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"data_expedicao": date(2026, 7, 1), "data_autorizacao": date(2026, 7, 2)},
        ])
        _patch(monkeypatch, cur)
        r = svc._remover_expedicao_sync(_autorizacao_req(), 1)
        assert r["removidos"] == []

    def test_ignora_se_nao_expedido(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"data_expedicao": None, "data_autorizacao": None},
        ])
        _patch(monkeypatch, cur)
        r = svc._remover_expedicao_sync(_autorizacao_req(), 1)
        assert r["removidos"] == []


def _alt_exec_req(**over):
    base = dict(
        servidor="srv", banco="bd", vendedor=None, executor=None, propagar_demais=False,
        usuario_alteracao=1, classe=1, plataforma="web",
    )
    base.update(over)
    return AlterarExecutorRequest(**base)


class TestAlterarExecutorPosFechamento:
    """Alteração de Executor/Vendedor pós-fechamento (`CmdAltExec`, branch
    F/PG de `CmDaltera_Click`, Revenda\\FrmTraOsNew.frm) — só permitida com
    a O.S. Fechada ou Faturada."""

    def test_nada_para_alterar_bloqueia_sem_query(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(), 1, 900)
        assert r["success"] is False
        assert "nada para alterar" in r["message"].lower()
        assert cur.queries == []

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(executor=5), 999, 900)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_bloqueia_os_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(executor=5), 1, 900)
        assert r["success"] is False
        assert "fechada ou faturada" in r["message"].lower()

    def test_bloqueia_os_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(executor=5), 1, 900)
        assert r["success"] is False
        assert "fechada ou faturada" in r["message"].lower()

    def test_item_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}, None])
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(executor=5), 1, 900)
        assert r["success"] is False
        assert "item não encontrado" in r["message"].lower()

    def test_permite_com_os_fechada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}, {"vendedor": 20, "executor": 21}])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(executor=99), 1, 900)
        assert r["success"] is True
        assert conn.committed is True
        update_q, update_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os_produto SET executor"))
        assert update_p == (99, 20, 900, 1)  # executor novo, vendedor mantido

    def test_permite_com_os_faturada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}, {"vendedor": 20, "executor": 21}])
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(vendedor=30), 1, 900)
        assert r["success"] is True

    def test_altera_vendedor_e_executor_juntos(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}, {"vendedor": 20, "executor": 21}])
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(vendedor=30, executor=99), 1, 900)
        assert r["success"] is True
        _, update_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os_produto SET executor"))
        assert update_p == (99, 30, 900, 1)

    def test_sem_propagar_nao_afeta_outros_itens(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}, {"vendedor": 20, "executor": 21}])
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(executor=99, propagar_demais=False), 1, 900)
        assert r["success"] is True
        assert r["propagados"] == []
        assert not any("cod_os_prod<>" in q for q, _ in cur.queries)

    def test_propaga_executor_para_outros_itens_com_mesmo_executor_anterior(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "F"}, {"vendedor": 20, "executor": 21}],
            many=[[{"cod_os_prod": 10}, {"cod_os_prod": 11}]],
        )
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(executor=99, propagar_demais=True), 1, 900)
        assert r["success"] is True
        assert r["propagados"] == [10, 11]
        prop_update = next(
            (q, p) for q, p in cur.queries
            if q.strip().startswith("UPDATE os_produto SET executor=%s WHERE os=%s AND executor=%s")
        )
        assert prop_update[1] == (99, 1, 21, 900)

    def test_propaga_vendedor_tambem_quando_ambos_mudam(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "F"}, {"vendedor": 20, "executor": 21}],
            many=[[{"cod_os_prod": 10}], [{"cod_os_prod": 12}]],
        )
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(vendedor=30, executor=99, propagar_demais=True), 1, 900)
        assert r["success"] is True
        assert sorted(r["propagados"]) == [10, 12]
        assert any(q.strip().startswith("UPDATE os_produto SET vendedor=%s WHERE os=%s AND vendedor=%s") for q, _ in cur.queries)

    def test_nao_propaga_quando_valor_anterior_vazio(self, monkeypatch):
        """Item sem executor anterior (None) — propagar aqui pegaria todo
        item sem executor definido, o que não é a intenção; guarda extra
        (não existe no legado) evita esse UPDATE largo demais."""
        cur = FakeCursor(one=[{"situacao": "F"}, {"vendedor": None, "executor": None}])
        _patch(monkeypatch, cur)
        r = svc._alterar_executor_sync(_alt_exec_req(executor=99, propagar_demais=True), 1, 900)
        assert r["success"] is True
        assert r["propagados"] == []
        assert not any("cod_os_prod<>" in q for q, _ in cur.queries)

    def test_alterar_executor_async(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}, {"vendedor": 20, "executor": 21}])
        _patch(monkeypatch, cur)
        r = asyncio.run(svc.alterar_executor(_alt_exec_req(executor=99), 1, 900))
        assert r["success"] is True


class TestChecklistObrigatorioBloqueiaAddItem:
    """Checklist de Entrada de Veículo obrigatório por permissão de grupo
    (`OS_COMP.CHECKLIST_OBRIG`, 2026-08-26 user-directed) — cobre o gate
    REAL (`_checklist_veiculo_pendente_bloqueia`, pedido_common.py), sem
    o bypass que o resto deste arquivo usa via `_patch`. Não mocka
    `_checklist_veiculo_pendente_bloqueia` em si — monta a sequência real
    de queries que `tem_permissao`/a checagem de placa/a checagem de
    `os_checklist` fazem, pra também cobrir a integração entre os dois
    módulos, não só a função isolada (já coberta em
    test_pedido_common.py)."""

    def _patch_sem_bypass(self, monkeypatch, cursor):
        conn = FakeConn(cursor)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
        return conn

    def test_sem_permissao_obrigatoria_prossegue_normalmente(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None, {"cod_os_prod": 900}])
        self._patch_sem_bypass(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        r = svc._add_item_sync(_item_req(classe=1), 1)
        assert r["success"] is True

    def test_permissao_obrigatoria_mas_os_nao_e_oficina_prossegue(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, {"placa": ""}, {"cod_os_prod": 900}])
        self._patch_sem_bypass(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        r = svc._add_item_sync(_item_req(classe=5), 1)
        assert r["success"] is True

    def test_permissao_obrigatoria_oficina_checklist_nao_concluido_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, {"placa": "ABC1234"}, None])
        self._patch_sem_bypass(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        r = svc._add_item_sync(_item_req(classe=5), 1)
        assert r["success"] is False
        assert "Checklist de Entrada" in r["message"]
        assert not any(q.strip().startswith("INSERT INTO os_produto") for q, _ in cur.queries)

    def test_permissao_obrigatoria_oficina_checklist_concluido_prossegue(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, {"placa": "ABC1234"}, {"ok": 1}, {"cod_os_prod": 900}])
        self._patch_sem_bypass(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolve_produto", lambda cur_, cod: dict(PECA))
        r = svc._add_item_sync(_item_req(classe=5), 1)
        assert r["success"] is True
        assert r["success"] is True

"""Testes unitários de projetos_service.py — Gestor de Projetos (Fase 1 —
núcleo, Fase 2 — Ajustar Valores). Ver PENDENCIAS.md > "Gestor de
Projetos"."""
import services.projetos_service as svc
from models.schemas import (
    ProjetosListRequest, ProjetoSaveRequest, ProjetoDocumentoRequest, FecharRequest,
    ProjetoAjustarValoresRequest, ProjetoDocumentoKey,
)


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
    return conn


def _list_req(**over):
    base = dict(servidor="srv", banco="bd", search="", situacao="", responsavel=None, page=1, size=20)
    base.update(over)
    return ProjetosListRequest(**base)


def _save_req(**over):
    base = dict(
        servidor="srv", banco="bd", cliente=10, responsavel=None,
        data_inicio=None, data_prevista=None, detalhes="", master=True,
        usuario_alteracao=1, classe=1, plataforma="web",
    )
    base.update(over)
    return ProjetoSaveRequest(**base)


def _doc_req(**over):
    base = dict(
        servidor="srv", banco="bd", tipo_doc="PED", num_doc=100, master=True,
        usuario_alteracao=1, classe=1, plataforma="web",
    )
    base.update(over)
    return ProjetoDocumentoRequest(**base)


def _fechar_req(**over):
    base = dict(servidor="srv", banco="bd", classe=1, master=True, usuario_alteracao=1, plataforma="web")
    base.update(over)
    return FecharRequest(**base)


def _ajuste_req(**over):
    base = dict(
        servidor="srv", banco="bd", tipo="P", novo_valor=100.0,
        documentos=[ProjetoDocumentoKey(tipo_doc="PED", num_doc=100)],
        master=True, usuario_alteracao=1, classe=1, plataforma="web",
    )
    base.update(over)
    return ProjetoAjustarValoresRequest(**base)


class TestListProjetos:
    def test_lista_com_sucesso(self, monkeypatch):
        rows = [
            {
                "codigo": 1, "cliente": 10, "cliente_nome": "ACME", "responsavel": 5,
                "responsavel_nome": "João", "data_abertura": None, "data_prevista": None,
                "situacao": "A", "valor_produtos": 100.0, "valor_servicos": 50.0, "valor_projeto": 150.0,
            },
        ]
        cur = FakeCursor(one=[{"total": 1}], many=[rows])
        _patch(monkeypatch, cur)
        r = svc._list_projetos_sync(_list_req())
        assert r["success"] is True
        assert r["total"] == 1
        assert r["items"][0]["codigo"] == 1
        assert r["items"][0]["situacao_label"] == "Aberto"

    def test_filtro_situacao_aplica_where(self, monkeypatch):
        cur = FakeCursor(one=[{"total": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_projetos_sync(_list_req(situacao="F"))
        assert any("p.situacao=%s" in q for q, _ in cur.queries)

    def test_busca_por_cliente_nome_e_fantasia(self, monkeypatch):
        cur = FakeCursor(one=[{"total": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_projetos_sync(_list_req(search="acme"))
        assert any("c.nome LIKE" in q and "c.fantasia LIKE" in q for q, _ in cur.queries)

    def test_expoe_ultimo_vinculo_para_projeto_parado(self, monkeypatch):
        import datetime
        rows = [
            {
                "codigo": 1, "cliente": 10, "cliente_nome": "ACME", "responsavel": 5,
                "responsavel_nome": "João", "data_abertura": None, "data_prevista": None,
                "situacao": "A", "valor_produtos": 0.0, "valor_servicos": 0.0, "valor_projeto": 0.0,
                "ultimo_vinculo": datetime.date(2026, 1, 5),
            },
            {
                "codigo": 2, "cliente": 11, "cliente_nome": "BETA", "responsavel": 5,
                "responsavel_nome": "João", "data_abertura": None, "data_prevista": None,
                "situacao": "A", "valor_produtos": 0.0, "valor_servicos": 0.0, "valor_projeto": 0.0,
                "ultimo_vinculo": None,
            },
        ]
        cur = FakeCursor(one=[{"total": 2}], many=[rows])
        _patch(monkeypatch, cur)
        r = svc._list_projetos_sync(_list_req())
        assert r["items"][0]["ultimo_vinculo"] == "2026-01-05"
        assert r["items"][1]["ultimo_vinculo"] is None
        select_q = next(q for q, _ in cur.queries if q.strip().startswith("SELECT p.codigo"))
        assert "MAX(pd.data_inclusao)" in select_q


class TestGetProjeto:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_projeto_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_sucesso_agrega_documentos_itens_e_faturado(self, monkeypatch):
        projeto_row = {
            "codigo": 1, "cliente": 10, "cliente_nome": "ACME", "responsavel": 5,
            "responsavel_nome": "João", "situacao": "A", "detalhes": "Reforma da loja",
            "data_abertura": None, "data_inicio": None, "data_prevista": None, "data_termino": None,
        }
        documentos = [
            {"tipo_doc": "PED", "num_doc": 100, "data_inclusao": None, "situacao": "PG", "total": 200.0},
            {"tipo_doc": "OSS", "num_doc": 200, "data_inclusao": None, "situacao": "A", "total": 80.0},
        ]
        produtos = [{"codigo_fab": "P001", "descricao": "Parafuso", "qtd": 10.0, "preco": 2.0, "custo": 1.0}]
        servicos = [{"codigo_fab": "S001", "descricao": "Instalação", "qtd": 1.0, "preco": 50.0, "custo": 20.0}]
        cur = FakeCursor(one=[projeto_row], many=[documentos, produtos, servicos])
        _patch(monkeypatch, cur)
        r = svc._get_projeto_sync("srv", "bd", 1)
        assert r["success"] is True
        p = r["projeto"]
        assert p["codigo"] == 1
        assert p["situacao_label"] == "Aberto"
        assert len(p["documentos"]) == 2
        assert p["itens"]["total_venda_produtos"] == 20.0  # 10 * 2.0
        assert p["itens"]["total_venda_servicos"] == 50.0  # 1 * 50.0
        assert p["itens"]["total_venda_geral"] == 70.0
        # Faturado = só o documento PG (200.0); saldo = 80.0 (o resto)
        assert p["faturado"] == 200.0
        assert p["saldo_a_faturar"] == 80.0


class TestSaveProjeto:
    def test_criar_modulo_inativo_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"gestor_projetos": False}])
        _patch(monkeypatch, cur)
        r = svc._save_projeto_sync(_save_req(), None)
        assert r["success"] is False
        assert "não está ativo" in r["message"].lower()

    def test_criar_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"gestor_projetos": True}, None])
        _patch(monkeypatch, cur)
        r = svc._save_projeto_sync(_save_req(master=False, classe=2), None)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_criar_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"gestor_projetos": True}, {"codigo": 501}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_projeto_sync(_save_req(cliente=10, responsavel=5), None)
        assert r["success"] is True
        assert r["codigo"] == 501
        assert conn.committed is True
        insert_q = next(q for q, _ in cur.queries if q.strip().startswith("INSERT INTO projetos"))
        assert "'A'" in insert_q  # situação sempre nasce Aberta

    def test_atualizar_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"gestor_projetos": True}, None])
        _patch(monkeypatch, cur)
        r = svc._save_projeto_sync(_save_req(), 555)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_atualizar_situacao_diferente_de_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"gestor_projetos": True}, {"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._save_projeto_sync(_save_req(), 555)
        assert r["success"] is False
        assert "não pode ser alterado" in r["message"].lower()

    def test_atualizar_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"gestor_projetos": True}, {"situacao": "A"}], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._save_projeto_sync(_save_req(cliente=99), 555)
        assert r["success"] is True
        assert r["codigo"] == 555
        assert conn.committed is True
        update_q = next(q for q, _ in cur.queries if q.strip().startswith("UPDATE projetos SET"))
        assert "data_inicio=%s" in update_q


class TestTransicoesSituacao:
    def test_finalizar_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._finalizar_projeto_sync(_fechar_req(), 1)
        assert r["success"] is True
        assert r["situacao"] == "F"
        assert conn.committed is True
        assert any("data_termino=CAST(GETDATE()" in q for q, _ in cur.queries)

    def test_finalizar_bloqueia_se_nao_aberto(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._finalizar_projeto_sync(_fechar_req(), 1)
        assert r["success"] is False
        assert "abertos podem ser finalizados" in r["message"].lower()

    def test_finalizar_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._finalizar_projeto_sync(_fechar_req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_finalizar_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._finalizar_projeto_sync(_fechar_req(master=False, classe=2), 1)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_reabrir_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_projeto_sync(_fechar_req(), 1)
        assert r["success"] is True
        assert r["situacao"] == "A"

    def test_reabrir_bloqueia_se_nao_finalizado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_projeto_sync(_fechar_req(), 1)
        assert r["success"] is False
        assert "finalizados podem ser reabertos" in r["message"].lower()

    def test_cancelar_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_projeto_sync(_fechar_req(), 1)
        assert r["success"] is True
        assert r["situacao"] == "C"

    def test_cancelar_bloqueia_se_nao_aberto(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_projeto_sync(_fechar_req(), 1)
        assert r["success"] is False
        assert "abertos podem ser cancelados" in r["message"].lower()

    def test_cancelar_desvincula_todos_os_documentos(self, monkeypatch):
        """Achado no rastreio de `Command10_Click` (frmgespro.frm):
        cancelar um projeto também apaga todos os vínculos em
        `projetos_documentos`, liberando os documentos pra outro projeto."""
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_projeto_sync(_fechar_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        queries = [q for q, _ in cur.queries]
        delete_idx = next(i for i, q in enumerate(queries) if q.strip().startswith("DELETE FROM projetos_documentos"))
        update_idx = next(i for i, q in enumerate(queries) if "UPDATE projetos SET situacao='C'" in q)
        assert delete_idx < update_idx  # desvincula ANTES de marcar cancelado


class TestAddDocumento:
    def test_tipo_invalido_bloqueia_sem_conexao(self):
        r = svc._add_documento_sync(_doc_req(tipo_doc="XXX"), 1)
        assert r["success"] is False
        assert "inválido" in r["message"].lower()

    def test_projeto_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._add_documento_sync(_doc_req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_projeto_nao_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._add_documento_sync(_doc_req(), 1)
        assert r["success"] is False
        assert "abertos podem receber" in r["message"].lower()

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._add_documento_sync(_doc_req(), 1, classe=2, master=False)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_documento_nao_encontrado_na_tabela_origem(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._add_documento_sync(_doc_req(tipo_doc="PED"), 1, classe=1, master=True)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_documento_ja_vinculado_a_outro_projeto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, {"projeto": 77, "cliente_nome": "OUTRA EMPRESA"}])
        _patch(monkeypatch, cur)
        r = svc._add_documento_sync(_doc_req(), 1, classe=1, master=True)
        assert r["success"] is False
        assert "77" in r["message"] and "OUTRA EMPRESA" in r["message"]

    def test_sucesso_vincula_documento(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._add_documento_sync(_doc_req(tipo_doc="OSS", num_doc=200), 1, classe=1, master=True)
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.strip().startswith("INSERT INTO projetos_documentos") for q, _ in cur.queries)


class TestRemoveDocumento:
    def test_tipo_invalido_bloqueia_sem_conexao(self):
        r = svc._remove_documento_sync(_doc_req(tipo_doc="XXX"), 1)
        assert r["success"] is False
        assert "inválido" in r["message"].lower()

    def test_projeto_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._remove_documento_sync(_doc_req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_projeto_nao_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._remove_documento_sync(_doc_req(), 1)
        assert r["success"] is False
        assert "abertos podem ter documentos removidos" in r["message"].lower()

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._remove_documento_sync(_doc_req(), 1, classe=2, master=False)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_vinculo_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=0)
        _patch(monkeypatch, cur)
        r = svc._remove_documento_sync(_doc_req(), 1, classe=1, master=True)
        assert r["success"] is False
        assert "vínculo não encontrado" in r["message"].lower()

    def test_sucesso_remove_documento(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._remove_documento_sync(_doc_req(), 1, classe=1, master=True)
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.strip().startswith("DELETE FROM projetos_documentos") for q, _ in cur.queries)


class TestAjusteValoresPreview:
    def test_projeto_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._ajuste_valores_preview_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_calcula_estimado_faturado_pendente_e_documentos(self, monkeypatch):
        projeto_row = {"valor_produtos": 1000.0, "valor_servicos": 500.0, "valor_projeto": 1500.0}
        itens = [
            {"categoria": "produto", "tipo_doc": "PED", "num_doc": 100, "situacao_doc": "PG", "item_id": 1, "qtd": 2.0, "preco_bruto": 50.0},
            {"categoria": "servico", "tipo_doc": "PED", "num_doc": 100, "situacao_doc": "PG", "item_id": 2, "qtd": 1.0, "preco_bruto": 80.0},
            {"categoria": "produto", "tipo_doc": "OSS", "num_doc": 200, "situacao_doc": "A", "item_id": 3, "qtd": 1.0, "preco_bruto": 300.0},
            {"categoria": "servico", "tipo_doc": "OSS", "num_doc": 200, "situacao_doc": "A", "item_id": 4, "qtd": 2.0, "preco_bruto": 60.0},
        ]
        cur = FakeCursor(one=[projeto_row], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._ajuste_valores_preview_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["estimado"] == {"produtos": 1000.0, "servicos": 500.0, "geral": 1500.0}
        assert r["faturado"]["produtos"] == 100.0  # PED 100 (PG): 2*50
        assert r["faturado"]["servicos"] == 80.0
        assert r["pendente"]["produtos"] == 300.0  # OSS 200 (A): 1*300
        assert r["pendente"]["servicos"] == 120.0  # 2*60
        assert r["saldo_orcamento"]["produtos"] == 600.0  # 1000 - 100 - 300
        assert r["saldo_orcamento"]["servicos"] == 300.0  # 500 - 80 - 120
        # PED 100 já está PG — não aparece na lista de elegíveis pra reprocessar.
        assert len(r["documentos"]) == 1
        assert r["documentos"][0]["tipo_doc"] == "OSS"
        assert r["documentos"][0]["num_doc"] == 200
        assert r["documentos"][0]["total_produtos"] == 300.0
        assert r["documentos"][0]["total_servicos"] == 120.0
        assert r["documentos"][0]["total"] == 420.0


class TestAjustarValores:
    def test_tipo_invalido_bloqueia_sem_conexao(self):
        r = svc._ajustar_valores_sync(_ajuste_req(tipo="X"), 1)
        assert r["success"] is False
        assert "tipo inválido" in r["message"].lower()

    def test_novo_valor_invalido_bloqueia_sem_conexao(self):
        r = svc._ajustar_valores_sync(_ajuste_req(novo_valor=0), 1)
        assert r["success"] is False
        assert "valor válido" in r["message"].lower()

    def test_documentos_vazio_bloqueia_sem_conexao(self):
        r = svc._ajustar_valores_sync(_ajuste_req(documentos=[]), 1)
        assert r["success"] is False
        assert "selecione ao menos um documento" in r["message"].lower()

    def test_projeto_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_projeto_nao_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(), 1)
        assert r["success"] is False
        assert "abertos podem ter valores reprocessados" in r["message"].lower()

    def test_modulo_inativo_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"gestor_projetos": False}])
        _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(), 1)
        assert r["success"] is False
        assert "não está ativo" in r["message"].lower()

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"gestor_projetos": True}, None])
        _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(master=False, classe=2), 1)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_nenhum_item_elegivel(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"gestor_projetos": True}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(), 1)
        assert r["success"] is False
        assert "nenhum item elegível" in r["message"].lower()

    def test_itens_sem_valor_bloqueia(self, monkeypatch):
        itens = [{"categoria": "produto", "tipo_doc": "PED", "num_doc": 100, "situacao_doc": "A", "item_id": 1, "qtd": 1.0, "preco_bruto": 0.0}]
        cur = FakeCursor(one=[{"situacao": "A"}, {"gestor_projetos": True}], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(), 1)
        assert r["success"] is False
        assert "não têm valor para redistribuir" in r["message"].lower()

    def test_valores_ja_batem_nenhum_ajuste(self, monkeypatch):
        itens = [{"categoria": "produto", "tipo_doc": "PED", "num_doc": 100, "situacao_doc": "A", "item_id": 1, "qtd": 2.0, "preco_bruto": 50.0}]
        cur = FakeCursor(one=[{"situacao": "A"}, {"gestor_projetos": True}], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(novo_valor=100.0), 1)
        assert r["success"] is True
        assert "nenhum ajuste necessário" in r["message"].lower()
        assert r["total_atual"] == 100.0

    def test_ajusta_desconto_pedido_e_recalcula_total(self, monkeypatch):
        itens = [{"categoria": "produto", "tipo_doc": "PED", "num_doc": 100, "situacao_doc": "A", "item_id": 1, "qtd": 2.0, "preco_bruto": 100.0}]
        cur = FakeCursor(one=[{"situacao": "A"}, {"gestor_projetos": True}], many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(novo_valor=150.0, documentos=[ProjetoDocumentoKey(tipo_doc="PED", num_doc=100)]), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert r["total_atual"] == 200.0
        assert r["novo_valor"] == 150.0
        assert r["itens_ajustados"] == 1
        assert r["documentos_afetados"] == 1
        item_update = next(p for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod SET"))
        assert item_update == (75.0, 25.0, 0.0, 1)  # p_venda, desconto, acrescimo, codauto
        assert any(q.strip().startswith("UPDATE pedido_venda SET total") for q, _ in cur.queries)
        assert not any(q.strip().startswith("UPDATE os_produto SET") for q, _ in cur.queries)

    def test_ajusta_acrescimo_os_e_recalcula_total_da_os(self, monkeypatch):
        """Correção deliberada em relação ao legado (`RecalculaDAVS`
        esquece de recalcular o total de `os`) — aqui o total da O.S.
        também é recalculado via `_recalc_os_total`."""
        itens = [{"categoria": "produto", "tipo_doc": "OSS", "num_doc": 200, "situacao_doc": "A", "item_id": 2, "qtd": 1.0, "preco_bruto": 100.0}]
        cur = FakeCursor(one=[{"situacao": "A"}, {"gestor_projetos": True}, {"valor": 150.0}], many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(_ajuste_req(novo_valor=150.0, documentos=[ProjetoDocumentoKey(tipo_doc="OSS", num_doc=200)]), 1)
        assert r["success"] is True
        assert conn.committed is True
        item_update = next(p for q, p in cur.queries if q.strip().startswith("UPDATE os_produto SET"))
        assert item_update == (150.0, 0.0, 50.0, 2)  # p_venda, desconto, acrescimo, cod_os_prod
        assert any(q.strip().startswith("UPDATE os SET valor") for q, _ in cur.queries)

    def test_documento_nao_selecionado_fica_de_fora(self, monkeypatch):
        itens = [
            {"categoria": "produto", "tipo_doc": "PED", "num_doc": 100, "situacao_doc": "A", "item_id": 1, "qtd": 1.0, "preco_bruto": 100.0},
            {"categoria": "produto", "tipo_doc": "OSS", "num_doc": 200, "situacao_doc": "A", "item_id": 2, "qtd": 1.0, "preco_bruto": 50.0},
        ]
        cur = FakeCursor(one=[{"situacao": "A"}, {"gestor_projetos": True}], many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._ajustar_valores_sync(
            _ajuste_req(novo_valor=120.0, documentos=[ProjetoDocumentoKey(tipo_doc="PED", num_doc=100)]), 1,
        )
        assert r["success"] is True
        assert conn.committed is True
        assert r["total_atual"] == 100.0  # só o Pedido selecionado, não os 50 da O.S. não selecionada
        assert r["itens_ajustados"] == 1
        assert r["documentos_afetados"] == 1
        assert not any(q.strip().startswith("UPDATE os_produto SET") for q, _ in cur.queries)


class TestResumoProjetos:
    """Resumo pro card "Projetos" da Tela Principal — Fase 4 (recurso
    extra, confirmado explicitamente pelo usuário)."""

    def test_modulo_inativo_retorna_zerado(self, monkeypatch):
        cur = FakeCursor(one=[{"gestor_projetos": False}])
        _patch(monkeypatch, cur)
        r = svc._resumo_projetos_sync("srv", "bd")
        assert r["success"] is True
        assert r["ativo"] is False
        assert r["total_abertos"] == 0
        assert r["saldo_a_faturar"] == 0.0

    def test_modulo_ativo_agrega_abertos_e_saldo(self, monkeypatch):
        cur = FakeCursor(one=[{"gestor_projetos": True}, {"total": 3}, {"saldo": 1250.5}])
        _patch(monkeypatch, cur)
        r = svc._resumo_projetos_sync("srv", "bd")
        assert r["success"] is True
        assert r["ativo"] is True
        assert r["total_abertos"] == 3
        assert r["saldo_a_faturar"] == 1250.5
        assert any("WHERE situacao='A'" in q for q, _ in cur.queries)
        assert any("doc.projeto = p.codigo" in q for q, _ in cur.queries)


class TestFindVinculo:
    """Busca reversa documento→projeto — Fase 4 (chip "Projeto #N" em
    Pedido/O.S.)."""

    def test_tipo_invalido(self, monkeypatch):
        r = svc._find_vinculo_sync("srv", "bd", "XXX", 1)
        assert r["success"] is False

    def test_sem_vinculo(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._find_vinculo_sync("srv", "bd", "PED", 999)
        assert r["success"] is True
        assert r["projeto"] is None

    def test_com_vinculo(self, monkeypatch):
        cur = FakeCursor(one=[{"projeto": 7, "cliente_nome": "ACME"}])
        _patch(monkeypatch, cur)
        r = svc._find_vinculo_sync("srv", "bd", "ped", 100)
        assert r["success"] is True
        assert r["projeto"] == {"codigo": 7, "cliente_nome": "ACME"}

"""Testes UNITÁRIOS de Equipamentos (_save_sync/_delete_sync/
_disponibilizar_contrato_sync/_alterar_numero_serie_sync).

Mesmo padrão de test_clientes_service.py / test_contatos_service.py:
cursor/conexão falsos (monkeypatch em _open_conn/_get_col_sizes), sem
banco real.
"""
import services.equipamentos_service as svc


class FakeCursor:
    def __init__(self, one=None, rowcount=1):
        self._one = list(one or [])
        self.rowcount = rowcount
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

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
    monkeypatch.setattr(svc, "_get_col_sizes", lambda *a, **k: {})
    return conn


def _args(**over):
    base = dict(
        codigo=None, cliente=10, numero_de_serie="KC0808", numero_de_serie_int=None,
        marca="001", modelo="222", portador="CAIXA", local=None,
        tipo_equipamento="A", detalhe_equipamento=None, situacao_equipamento="A",
        descricao_equipamento="IBM_PC ATHLON XP", valor=0, revisao=None,
    )
    base.update(over)
    return base


class TestValidacoesSemBanco:
    def test_cliente_obrigatorio(self):
        r = svc._save_sync("srv", "bd", **_args(cliente=None))
        assert r["success"] is False and "cliente" in r["message"].lower()

    def test_numero_serie_obrigatorio(self):
        r = svc._save_sync("srv", "bd", **_args(numero_de_serie="  "))
        assert r["success"] is False and "número de série" in r["message"].lower()

    def test_marca_obrigatoria(self):
        r = svc._save_sync("srv", "bd", **_args(marca=""))
        assert r["success"] is False and "marca" in r["message"].lower()

    def test_modelo_obrigatorio(self):
        r = svc._save_sync("srv", "bd", **_args(modelo=""))
        assert r["success"] is False and "modelo" in r["message"].lower()


class TestSaveComMock:
    def test_insere_novo_equipamento(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 501}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", **_args())
        assert r["success"] is True
        assert r["codigo"] == 501
        assert conn.committed is True
        assert any("INSERT INTO equipamentos" in q for q, _ in cur.queries)

    def test_numero_serie_int_default_para_numero_serie(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 501}])
        _patch(monkeypatch, cur)
        svc._save_sync("srv", "bd", **_args(numero_de_serie_int=None))
        insert_q, insert_p = next((q, p) for q, p in cur.queries if "INSERT INTO equipamentos" in q)
        assert "KC0808" in insert_p  # numero_de_serie_int == numero_de_serie

    def test_bloqueia_numero_serie_duplicado_entre_clientes(self, monkeypatch):
        # Equipamento já existe (outro cliente) — bloqueia mesmo sendo um
        # novo cadastro (codigo=None): regra é única GLOBALMENTE.
        cur = FakeCursor(one=[{"codigo": 999}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", **_args(codigo=None))
        assert r["success"] is False
        assert "Número de Série" in r["message"]
        assert conn.committed is False

    def test_edita_existente_via_update_preserva_codigo(self, monkeypatch):
        cur = FakeCursor(one=[None], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", **_args(codigo=999))
        assert r["success"] is True
        assert r["codigo"] == 999
        assert conn.committed is True
        assert any("UPDATE equipamentos" in q for q, _ in cur.queries)

    def test_edita_mesmo_serie_nao_bloqueia_a_si_mesmo(self, monkeypatch):
        # existente encontrado tem o MESMO codigo do que está sendo editado —
        # não deve bloquear (não é duplicidade real).
        cur = FakeCursor(one=[{"codigo": 999}], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", **_args(codigo=999))
        assert r["success"] is True
        assert conn.committed is True


class TestDeleteComMock:
    def test_exclui_e_cascateia_contratos_produtos(self, monkeypatch):
        cur = FakeCursor(one=[{"numero_de_serie": "KC0808"}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("DELETE FROM equipamentos" in q for q, _ in cur.queries)
        assert any("DELETE FROM contratos_produtos_disponiveis" in q for q, _ in cur.queries)
        assert any("DELETE FROM contratos_produtos WHERE" in q for q, _ in cur.queries)

    def test_exclui_equipamento_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False and "não encontrado" in r["message"]
        assert conn.committed is False


class TestDisponibilizarContrato:
    def test_disponibiliza_novo(self, monkeypatch):
        cur = FakeCursor(one=[{"numero_de_serie": "KC0808"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._disponibilizar_contrato_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True

    def test_bloqueia_se_ja_disponivel(self, monkeypatch):
        cur = FakeCursor(one=[{"numero_de_serie": "KC0808"}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._disponibilizar_contrato_sync("srv", "bd", 1)
        assert r["success"] is False and "já está disponível" in r["message"]
        assert conn.committed is False


class TestAlterarNumeroSerie:
    def test_altera_com_sucesso_e_cascateia(self, monkeypatch):
        cur = FakeCursor(one=[{"numero_de_serie": "KC0808", "cliente": 10}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_numero_serie_sync("srv", "bd", 1, "NOVO123", None)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE equipamentos SET numero_de_serie" in q for q, _ in cur.queries)
        assert any("UPDATE retifica" in q for q, _ in cur.queries)
        # os.numero_de_serie é o campo de Assistência Técnica (equivalente
        # moderno do chassi só-Oficina do legado) — nunca os.chassi.
        os_q = next((q for q, _ in cur.queries if q.startswith("UPDATE os ")), None)
        assert os_q is not None
        assert "numero_de_serie" in os_q and "chassi" not in os_q

    def test_bloqueia_se_novo_serie_ja_existe(self, monkeypatch):
        cur = FakeCursor(one=[{"numero_de_serie": "KC0808", "cliente": 10}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_numero_serie_sync("srv", "bd", 1, "JATINHA", None)
        assert r["success"] is False and "Já existe outro" in r["message"]
        assert conn.committed is False

    def test_novo_serie_obrigatorio(self):
        r = svc._alterar_numero_serie_sync("srv", "bd", 1, "   ", None)
        assert r["success"] is False

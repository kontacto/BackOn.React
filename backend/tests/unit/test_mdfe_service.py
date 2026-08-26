"""Testes UNITÁRIOS do MDF-e — Fase A (cadastro, sem emissão SEFAZ),
`mdfe_service.py`. Mesmo padrão de sempre: cursor/conexão falsos
(monkeypatch em `_open_conn`), sem banco real."""
import services.mdfe_service as svc


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


class RaisingCursor(FakeCursor):
    """Como FakeCursor, mas `execute` levanta exceção pra QUALQUER query
    que bata num dos `padroes_falha` (usado pra simular tabela `municipio`
    ausente/incompatível nesta instalação)."""
    def __init__(self, one=None, many=None, padroes_falha=()):
        super().__init__(one=one, many=many)
        self._padroes_falha = padroes_falha

    def execute(self, q, p=None):
        if any(p in q for p in self._padroes_falha):
            raise Exception("Invalid object name 'municipio'.")
        super().execute(q, p)


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


class TestSaveMdfeSync:
    def test_veiculo_obrigatorio(self):
        r = svc._save_mdfe_sync("srv", "bd", None, {"motorista": 5}, "user")
        assert r["success"] is False
        assert "Veículo" in r["message"]

    def test_motorista_obrigatorio(self):
        r = svc._save_mdfe_sync("srv", "bd", None, {"veiculo": 3}, "user")
        assert r["success"] is False
        assert "Motorista" in r["message"]

    def test_uf_default_da_empresa_quando_nao_informada(self, monkeypatch):
        cur = FakeCursor(one=[{"uf": "RJ"}, {"codigo": 1}])
        _patch(monkeypatch, cur)
        r = svc._save_mdfe_sync("srv", "bd", None, {"veiculo": 3, "motorista": 5}, "user")
        assert r["success"] is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO MDFe"))
        assert "RJ" in insert_p

    def test_uf_informada_nao_e_sobrescrita(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1}])
        _patch(monkeypatch, cur)
        r = svc._save_mdfe_sync("srv", "bd", None, {"veiculo": 3, "motorista": 5, "ufini": "SP", "uffim": "MG"}, "user")
        assert r["success"] is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO MDFe"))
        assert "SP" in insert_p and "MG" in insert_p
        # não deve ter consultado controle.uf, já que as duas UFs vieram preenchidas
        assert not any("FROM controle" in q for q, _ in cur.queries)

    def test_update_bloqueado_fora_de_situacao_a_n(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "T"}])
        _patch(monkeypatch, cur)
        r = svc._save_mdfe_sync("srv", "bd", 10, {"veiculo": 3, "motorista": 5, "ufini": "RJ", "uffim": "RJ"}, "user")
        assert r["success"] is False
        assert "edição" in r["message"].lower() or "transmitidos" in r["message"].lower()

    def test_update_permitido_em_situacao_a(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_mdfe_sync("srv", "bd", 10, {"veiculo": 3, "motorista": 5, "ufini": "RJ", "uffim": "RJ"}, "user")
        assert r["success"] is True
        assert r["codigo"] == 10
        assert conn.committed is True

    def test_mdfe_nao_encontrado_no_update(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_mdfe_sync("srv", "bd", 999, {"veiculo": 3, "motorista": 5, "ufini": "RJ", "uffim": "RJ"}, "user")
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()


class TestDeleteMdfeSync:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_mdfe_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_bloqueia_fora_de_situacao_a(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "T"}])
        _patch(monkeypatch, cur)
        r = svc._delete_mdfe_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "edição" in r["message"].lower()

    def test_exclui_em_situacao_a(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_mdfe_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True


class TestResolverMunicipioContraparteSync:
    def test_sem_endereco_cadastrado(self):
        cur = FakeCursor(one=[None])
        r = svc._resolver_municipio_contraparte_sync(cur, "C", 5)
        assert r["cod_municipio"] is None
        assert "endereço" in r["aviso"].lower()

    def test_resolve_via_join_municipio_real(self):
        cur = FakeCursor(one=[{"cidade": "Rio de Janeiro", "uf": "RJ"}, {"codmun": 3304557}])
        r = svc._resolver_municipio_contraparte_sync(cur, "C", 5)
        assert r["cod_municipio"] == 3304557
        assert r["aviso"] is None

    def test_fallback_pro_seed_quando_tabela_municipio_falha(self):
        cur = RaisingCursor(
            one=[{"cidade": "Rio de Janeiro", "uf": "RJ"}],
            padroes_falha=("FROM municipio, UF",),
        )
        r = svc._resolver_municipio_contraparte_sync(cur, "F", 7)
        assert r["cod_municipio"] == 3304557  # seed de nfe_fiscal_common, normalizado pra int
        assert r["aviso"] is None

    def test_normaliza_codigo_float_do_join_real_para_int(self):
        # municipio.codigo é FLOAT no banco real (confirmado ao vivo,
        # ARGEN TESTE) — o valor devolvido pelo JOIN nunca deve vazar cru.
        cur = FakeCursor(one=[{"cidade": "Rio de Janeiro", "uf": "RJ"}, {"codmun": 3304557.0}])
        r = svc._resolver_municipio_contraparte_sync(cur, "C", 5)
        assert r["cod_municipio"] == 3304557
        assert isinstance(r["cod_municipio"], int)

    def test_aviso_quando_nada_resolve(self):
        cur = FakeCursor(one=[{"cidade": "Cidade Desconhecida", "uf": "XX"}, None])
        r = svc._resolver_municipio_contraparte_sync(cur, "C", 5)
        assert r["cod_municipio"] is None
        assert "não pôde ser resolvido" in r["aviso"]

    def test_usa_fornecedor_end_quando_tipo_f(self):
        cur = FakeCursor(one=[{"cidade": "Rio de Janeiro", "uf": "RJ"}, {"codmun": 3304557}])
        svc._resolver_municipio_contraparte_sync(cur, "F", 9)
        assert any("fornecedor_end" in q for q, _ in cur.queries)
        assert any("tipo_endereco" in q for q, _ in cur.queries)


class TestAnexarNotaSync:
    def test_mdfe_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._anexar_nota_sync("srv", "bd", 1, 100)
        assert r["success"] is False
        assert "MDF-e não encontrado" in r["message"]

    def test_bloqueia_fora_de_situacao_a_n(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "T"}])
        _patch(monkeypatch, cur)
        r = svc._anexar_nota_sync("srv", "bd", 1, 100)
        assert r["success"] is False
        assert "edição" in r["message"].lower()

    def test_nota_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._anexar_nota_sync("srv", "bd", 1, 100)
        assert r["success"] is False
        assert "Nota Fiscal não encontrada" in r["message"]

    def test_anexa_com_sucesso_origem_empresa_destino_cliente(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},  # mdfe
            {"fornecedor": 42, "volumes": 3, "peso_bruto": 10.5, "peso_liquido": 9.0, "origem_destino": "C"},  # nf
            {"cidade": "Rio de Janeiro", "uf": "RJ"},  # controle (origem)
            {"codmun": 3304557},  # municipio join (origem)
            {"cidade": "Niteroi", "uf": "RJ"},  # cliente_end (destino)
            {"codmun": 3303302},  # municipio join (destino)
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._anexar_nota_sync("srv", "bd", 1, 100)
        assert r["success"] is True
        assert conn.committed is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO mdfe_notas"))
        assert insert_p == (1, 100, 3304557, 3303302, 3, 10.5, 9.0)

    def test_volumes_nao_numerico_vira_zero(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"},
            {"fornecedor": 42, "volumes": None, "peso_bruto": None, "peso_liquido": None, "origem_destino": "F"},
            {"cidade": "Rio de Janeiro", "uf": "RJ"},
            {"codmun": 3304557},
            {"cidade": None, "uf": None},  # fornecedor_end com linha, mas sem cidade/uf úteis
            None,  # municipio join do destino não acha nada
        ])
        _patch(monkeypatch, cur)
        r = svc._anexar_nota_sync("srv", "bd", 1, 100)
        assert r["success"] is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO mdfe_notas"))
        assert insert_p[4:] == (0, 0, 0)


class TestRemoverNotaSync:
    def test_bloqueia_fora_de_situacao_a_n(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "E"}])
        _patch(monkeypatch, cur)
        r = svc._remover_nota_sync("srv", "bd", 1, 100)
        assert r["success"] is False

    def test_remove_em_situacao_a(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._remover_nota_sync("srv", "bd", 1, 100)
        assert r["success"] is True
        assert conn.committed is True


class TestBuscarNotasElegiveisSync:
    def test_filtro_situacao_a_sempre_presente(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._buscar_notas_elegiveis_sync("srv", "bd", {})
        select_q = cur.queries[0][0]
        assert "nf.situacao='A'" in select_q

    def test_termo_cliente_aplica_origem_destino_c(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._buscar_notas_elegiveis_sync("srv", "bd", {"cliente_fornecedor_termo": "joao", "tipo_pessoa": "C"})
        select_q, select_p = cur.queries[0]
        assert "tm.origem_destino=%s" in select_q
        assert "C" in select_p

    def test_aviso_denegada(self):
        row = {"situacao_nfe": 5, "protocolo_sefaz": "123"}
        assert svc._rotulo_aviso_nota(row) == "NFE DENEGADA"

    def test_aviso_contingencia(self):
        row = {"situacao_nfe": 2, "protocolo_sefaz": "123"}
        assert svc._rotulo_aviso_nota(row) == "NFE EMITIDA EM CONTINGÊNCIA"

    def test_sem_aviso_quando_tudo_ok(self):
        row = {"situacao_nfe": 1, "protocolo_sefaz": "123"}
        assert svc._rotulo_aviso_nota(row) is None

"""Testes UNITÁRIOS de Cadastro de Balanças (Automação Comercial —
pré-pesagem com etiqueta). Mesmo padrão de test_cilindro_service.py — cursor/
conexão falsos, sem banco real.

`_exportar_carga_sync` grava um arquivo de verdade — usa a fixture `tmp_path`
do pytest (pasta temporária isolada, limpa sozinha) em vez de mockar `open`,
mais simples e igualmente seguro (nunca toca pasta real de produção)."""
import services.balanca_service as svc


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


class TestListGet:
    def test_lista_balancas(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo": 1, "descricao": "Balança Loja", "pasta_integracao": r"C:\mgv", "ativo": True}]])
        _patch(monkeypatch, cur)
        r = svc._list_balancas_sync("srv", "bd", "")
        assert r["success"] is True
        assert len(r["items"]) == 1

    def test_get_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_balanca_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]


class TestSave:
    def test_exige_descricao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_balanca_sync("srv", "bd", None, {"pasta_integracao": r"C:\mgv"})
        assert r["success"] is False
        assert "Descrição" in r["message"]

    def test_exige_pasta_integracao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_balanca_sync("srv", "bd", None, {"descricao": "Balança Loja"})
        assert r["success"] is False
        assert "Pasta de Integração" in r["message"]

    def test_rejeita_descricao_duplicada(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 5}])
        _patch(monkeypatch, cur)
        r = svc._save_balanca_sync("srv", "bd", None, {"descricao": "Balança Loja", "pasta_integracao": r"C:\mgv"})
        assert r["success"] is False
        assert "já existe" in r["message"].lower()

    def test_cria_nova_balanca(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 7}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_balanca_sync("srv", "bd", None, {"descricao": "Balança Loja", "pasta_integracao": r"C:\mgv"})
        assert r["success"] is True
        assert r["codigo"] == 7
        assert conn.committed

    def test_atualiza_balanca_existente(self, monkeypatch):
        cur = FakeCursor(one=[None])  # só o dup-check; UPDATE não faz fetchone
        conn = _patch(monkeypatch, cur)
        r = svc._save_balanca_sync("srv", "bd", 3, {"descricao": "Balança Loja", "pasta_integracao": r"C:\mgv2"})
        assert r["success"] is True
        assert r["codigo"] == 3
        assert conn.committed


class TestDelete:
    def test_exclui_balanca_existente(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 3}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_balanca_sync("srv", "bd", 3)
        assert r["success"] is True
        assert conn.committed

    def test_exclui_balanca_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_balanca_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]


class TestExportarCarga:
    def test_gera_arquivo_itensmgv_no_layout_correto(self, monkeypatch, tmp_path):
        pasta = str(tmp_path)
        cur = FakeCursor(
            one=[{"codigo": 1, "descricao": "Balança Loja", "pasta_integracao": pasta, "ativo": True}],
            many=[[
                {"codigo_int": "123", "descricao": "Banana Prata", "p_venda": 6.5},
                {"codigo_int": "4567890", "descricao": "Descrição de produto bem longa que passa de vinte e cinco caracteres", "p_venda": 12.999},
            ]],
        )
        _patch(monkeypatch, cur)

        r = svc._exportar_carga_sync("srv", "bd", 1)

        assert r["success"] is True
        assert r["qtd_produtos"] == 2

        # newline="" preserva o CRLF literal — read_text() padrão traduziria
        # "\r\n" para "\n" (universal newlines), escondendo o terminador real
        # gravado no arquivo (o que estamos testando aqui).
        with open(tmp_path / "ITENSMGV.TXT", encoding="latin-1", newline="") as f:
            conteudo = f.read()
        linhas = conteudo.split("\r\n")
        assert linhas[-1] == ""  # arquivo termina com CRLF
        linha1, linha2 = linhas[0], linhas[1]

        # Layout: departamento(2) tipo(1) código(6) preço(6) validade(3) descricao1(25) descricao2(25)
        assert linha1[:2] == "01"          # departamento padrão
        assert linha1[2] == "0"            # tipo = peso
        assert linha1[3:9] == "000123"     # código zero-padded 6 dígitos
        assert linha1[9:15] == "000650"    # R$ 6,50 -> 650 centavos
        assert linha1[15:18] == "000"      # validade padrão
        assert linha1[18:43].rstrip() == "Banana Prata"
        assert len(linha1) == 68  # 2+1+6+6+3+25+25

        # Código de fábrica com mais de 6 dígitos é truncado pelos ÚLTIMOS 6
        # (mesmo critério de preço, "[-6:]") — comportamento documentado, não
        # validado contra um caso real de código de 7+ dígitos ainda.
        assert linha2[3:9] == "567890"
        assert linha2[18:43].rstrip() == "Descrição de produto bem lon"[:25].rstrip()

    def test_sem_produtos_gera_arquivo_vazio(self, monkeypatch, tmp_path):
        pasta = str(tmp_path)
        cur = FakeCursor(
            one=[{"codigo": 1, "descricao": "Balança Loja", "pasta_integracao": pasta, "ativo": True}],
            many=[[]],
        )
        _patch(monkeypatch, cur)

        r = svc._exportar_carga_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["qtd_produtos"] == 0
        assert (tmp_path / "ITENSMGV.TXT").read_text(encoding="latin-1") == ""

    def test_balanca_inexistente(self, monkeypatch, tmp_path):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._exportar_carga_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

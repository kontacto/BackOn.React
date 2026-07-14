"""Testes UNITÁRIOS do fluxo de gravação de cliente (_save_cliente_sync).

As validações de domínio rodam ANTES de abrir conexão (sem banco). O caminho de
INSERT é testado com conexão/cursor falsos (monkeypatch em _open_conn e
_get_col_sizes), validando o código retornado e as queries emitidas.
"""
import services.clientes_service as cs
from models.schemas import ClienteSaveRequest, EnderecoInput, TelefoneInput, ContatoInput


def _req(**over):
    base = dict(servidor="srv", banco="BDREACTAPP", nome="Cliente Teste",
                cgc_cpf="", e_mail="", inscre="", tipo="", aceita_email=False, vendedor=3)
    base.update(over)
    return ClienteSaveRequest(**base)


# ---- Cursor / conexão falsos ----
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
    monkeypatch.setattr(cs, "_open_conn", lambda *a, **k: conn)
    monkeypatch.setattr(cs, "_get_col_sizes", lambda *a, **k: {})
    return conn


class TestValidacoesSemBanco:
    def test_nome_obrigatorio(self):
        r = cs._save_cliente_sync(_req(nome="   "), [], [], None)
        assert r["success"] is False and "Nome" in r["message"]

    def test_nome_muito_longo(self):
        r = cs._save_cliente_sync(_req(nome="N" * 61), [], [], None)
        assert r["success"] is False and "60" in r["message"]

    def test_cpf_invalido(self):
        r = cs._save_cliente_sync(_req(cgc_cpf="11144477730"), [], [], None)
        assert r["success"] is False and "CPF" in r["message"]

    def test_maximo_3_telefones(self):
        tels = [TelefoneInput(ddd="21", tel=f"9999000{i}") for i in range(4)]
        r = cs._save_cliente_sync(_req(), [], tels, None)
        assert r["success"] is False and "3" in r["message"]


class TestInsertComMock:
    def test_insert_retorna_codigo_e_commita(self, monkeypatch):
        # INSERT cliente ... OUTPUT INSERTED.codigo → fetchone retorna [123]
        cur = FakeCursor(one=[[123]])
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(
            _req(cgc_cpf="11144477735"),
            [EnderecoInput(tipo=0, cep="20000000", endereco="Rua X", numero=10, uf="RJ")],
            [TelefoneInput(ddd="21", tel="999990000", descricao="Cel")],
            None,
        )
        assert r["success"] is True and r["codigo"] == 123
        assert conn.committed is True
        joined = " ".join(q[0].upper() for q in cur.queries)
        assert "INSERT INTO CLIENTE" in joined
        assert "CLIENTE_END" in joined and "CLIENTE_TEL" in joined

    def test_insert_multiplos_enderecos(self, monkeypatch):
        # Cliente pode ter mais de um endereço (residencial, entrega, cobrança...)
        cur = FakeCursor(one=[[124]])
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(
            _req(cgc_cpf="11144477735"),
            [
                EnderecoInput(tipo=0, cep="20000000", endereco="Rua X", numero=10, uf="RJ"),
                EnderecoInput(tipo=2, cep="21000000", endereco="Av Y", numero=20, uf="RJ"),
            ],
            [],
            None,
        )
        assert r["success"] is True
        joined = " ".join(q[0].upper() for q in cur.queries)
        assert joined.count("INSERT INTO CLIENTE_END") == 2

    def test_update_cliente_inexistente(self, monkeypatch):
        # UPDATE com rowcount 0 → cliente não encontrado, faz rollback
        cur = FakeCursor(rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(nome="Novo Nome"), [], [], codigo=999)
        assert r["success"] is False and "não encontrado" in r["message"].lower()
        assert conn.rolled is True

    def test_insert_grava_campos_dados_principais_e_secundarios(self, monkeypatch):
        # Novos campos das abas Dados Principais/Secundários vão para o INSERT de cliente.
        cur = FakeCursor(one=[[125]])
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(
            _req(
                cgc_cpf="11144477735",
                nome_fantasia="Fantasia LTDA",
                sexo="M",
                site="www.teste.com.br",
                historico="Cliente antigo",
                situacao="I",
                limite_credito=1000.0,
                desconto=5.0,
                credita_icms=True,
                consumidor_final=True,
                segmento="2",
                rota=3,
            ),
            [],
            [],
            None,
        )
        assert r["success"] is True
        insert_q = next(q for q, _ in cur.queries if q.upper().startswith("INSERT INTO CLIENTE "))
        assert "fantasia" in insert_q
        assert "situacao" in insert_q
        assert "credita_icms" in insert_q
        assert "segmento" in insert_q

    def test_insert_contatos(self, monkeypatch):
        # Contatos (cliente_contato) são gravados como os telefones/endereços: replace-all.
        cur = FakeCursor(one=[[126]])
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(
            _req(cgc_cpf="11144477735"),
            [],
            [],
            None,
            contatos=[
                ContatoInput(contato="Fulano", setor="Financeiro", cargo="Gerente"),
                ContatoInput(contato="Ciclana", setor="Compras"),
            ],
        )
        assert r["success"] is True
        joined = " ".join(q[0].upper() for q in cur.queries)
        assert joined.count("INSERT INTO CLIENTE_CONTATO") == 2

    def test_contato_sem_nome_e_ignorado(self, monkeypatch):
        cur = FakeCursor(one=[[127]])
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(
            _req(cgc_cpf="11144477735"),
            [],
            [],
            None,
            contatos=[ContatoInput(contato="   ", setor="Financeiro")],
        )
        assert r["success"] is True
        joined = " ".join(q[0].upper() for q in cur.queries)
        assert "INSERT INTO CLIENTE_CONTATO" not in joined

    def test_update_limpa_contatos_existentes(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(nome="Novo Nome"), [], [], codigo=10)
        assert r["success"] is True
        joined = " ".join(q[0].upper() for q in cur.queries)
        assert "DELETE FROM CLIENTE_CONTATO WHERE CODIGO=%S" in joined

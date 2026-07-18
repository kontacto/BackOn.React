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
    def __init__(self, one=None, rowcount=1, many=None):
        self._one = list(one or [])
        self.rowcount = rowcount
        self.queries = []
        self._many = list(many or [])

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


class TestExigeCpfCliente:
    """controle.exige_cpf_cliente — CPF/CNPJ obrigatório no cadastro só
    quando essa flag está ligada; padrão (desligada ou sem registro de
    controle) mantém o documento opcional, como já era antes desta regra."""

    def test_bloqueia_sem_cpf_quando_exige_ligado(self, monkeypatch):
        cur = FakeCursor(one=[[True]])
        _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(cgc_cpf=""), [], [], None)
        assert r["success"] is False and "obrigatório" in r["message"]

    def test_permite_sem_cpf_quando_exige_desligado(self, monkeypatch):
        cur = FakeCursor(one=[[False], [123]])
        _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(cgc_cpf=""), [], [], None)
        assert r["success"] is True

    def test_permite_sem_cpf_quando_sem_registro_de_controle(self, monkeypatch):
        cur = FakeCursor(one=[None, [123]])
        _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(cgc_cpf=""), [], [], None)
        assert r["success"] is True

    def test_nao_consulta_controle_quando_cpf_ja_preenchido(self, monkeypatch):
        cur = FakeCursor(one=[[123]])
        _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(cgc_cpf="11144477735"), [], [], None)
        assert r["success"] is True
        joined = " ".join(q[0].upper() for q in cur.queries)
        assert "EXIGE_CPF_CLIENTE" not in joined


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


class TestClienteMesaOuComandaHelper:
    def test_detecta_mesa_por_nome(self):
        assert cs._cliente_mesa_ou_comanda("M15", None) is True

    def test_detecta_comanda_por_nome(self):
        assert cs._cliente_mesa_ou_comanda("c1", None) is True

    def test_detecta_mesa_por_fantasia(self):
        assert cs._cliente_mesa_ou_comanda("Qualquer Nome", "MESA 15") is True

    def test_nome_parecido_mas_nao_e_mesa(self):
        # "Maria15" não é só letra+dígitos — não deve casar com o padrão.
        assert cs._cliente_mesa_ou_comanda("Maria15", None) is False

    def test_cliente_comum_nao_e_detectado(self):
        assert cs._cliente_mesa_ou_comanda("Cliente Teste", "Fantasia LTDA") is False


class TestClienteMesaComandaBarBloqueiaRenomeio:
    """Cliente Mesa/Comanda (módulo Bar) — nome/fantasia não podem ser
    alterados via UPDATE (CLAUDE.md, seção "Pedido Bar")."""

    # `one[0]` em cada caso abaixo é consumido pela checagem nova de
    # `controle.exige_cpf_cliente` (ver TestExigeCpfCliente) — None = sem
    # registro de controle, documento continua opcional, não interfere
    # nestes testes. `one[1]` é quem essas tests já esperavam (nome/fantasia
    # atuais do cliente, pro bloqueio de renomeio de Mesa/Comanda).
    def test_bloqueia_renomear_mesa_por_nome(self, monkeypatch):
        cur = FakeCursor(one=[None, ["M15", None]], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(nome="Mesa Renomeada"), [], [], codigo=50)
        assert r["success"] is False and "Mesa/Comanda" in r["message"]
        assert conn.rolled is True

    def test_bloqueia_renomear_fantasia_de_mesa(self, monkeypatch):
        cur = FakeCursor(one=[None, ["M15", "MESA 15"]], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(nome="M15", nome_fantasia="Outra Coisa"), [], [], codigo=50)
        assert r["success"] is False and "Mesa/Comanda" in r["message"]

    def test_bloqueia_renomear_comanda(self, monkeypatch):
        cur = FakeCursor(one=[None, ["C1", None]], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(nome="Comanda Nova"), [], [], codigo=51)
        assert r["success"] is False and "Mesa/Comanda" in r["message"]

    def test_permite_gravar_mesa_sem_alterar_nome_fantasia(self, monkeypatch):
        cur = FakeCursor(one=[None, ["M15", None]], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(nome="M15"), [], [], codigo=50)
        assert r["success"] is True

    def test_cliente_normal_pode_ser_renomeado(self, monkeypatch):
        cur = FakeCursor(one=[None, ["Cliente Antigo", None]], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = cs._save_cliente_sync(_req(nome="Cliente Novo Nome"), [], [], codigo=52)
        assert r["success"] is True


class TestBuscaClientePorCodigo:
    """Busca de cliente por código — lista de Pedidos e modal de busca do
    cadastro de Pedido devem achar cliente digitando o código, não só
    nome/CPF/telefone."""

    def test_find_clientes_for_pedido_aceita_codigo(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo": 42, "nome": "Fulano", "cgc_cpf": "", "telefone": ""}]])
        _patch(monkeypatch, cur)
        r = cs._find_clientes_for_pedido_sync("srv", "bd", "42")
        assert r["success"] is True
        select_q, params = cur.queries[-1]
        assert "c.codigo = %s" in select_q
        assert 42 in params
        assert r["items"][0]["codigo"] == 42

    def test_busca_livre_inclui_fantasia(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        cs._find_clientes_for_pedido_sync("srv", "bd", "gama termic")
        select_q, params = cur.queries[-1]
        assert "c.fantasia LIKE %s" in select_q
        assert params.count("%gama termic%") == 5

    def test_busca_nunca_filtra_por_tipo(self, monkeypatch):
        # Filtro por tipo (Painel de Pedidos, "Novo Pedido" por coluna) foi
        # revertido 2026-07-18 — a busca sempre traz todos os tipos (só o
        # JOIN com tipo_cliente continua, pra exibir `tipo_cliente_descricao`
        # em cada resultado).
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        cs._find_clientes_for_pedido_sync("srv", "bd", "fulano")
        select_q, _ = cur.queries[-1]
        assert "c.cliente_forn = %s" not in select_q

    def test_expoe_tipo_cliente_descricao(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "codigo": 42, "nome": "Fulano", "cgc_cpf": "", "telefone": "",
            "tipo_cliente_descricao": "MESA",
        }]])
        _patch(monkeypatch, cur)
        r = cs._find_clientes_for_pedido_sync("srv", "bd", "fulano")
        assert r["items"][0]["tipo_cliente_descricao"] == "MESA"

    def test_list_clientes_aceita_codigo(self, monkeypatch):
        cur = FakeCursor(one=[{"total": 1}], many=[[{
            "codigo": 42, "nome": "Fulano", "cgc_cpf": "", "ddd_cli": "", "telefone_cli": "",
            "e_mail": "", "situacao": "A", "tipo_descricao": "", "lista_negra": 0, "lista_negra_motivo": None,
        }]])
        _patch(monkeypatch, cur)
        from models.schemas import ClientesRequest
        req = ClientesRequest(servidor="srv", banco="bd", search="42", page=1, size=20)
        r = cs._list_clientes_sync(req)
        assert r["success"] is True
        select_q, params = cur.queries[-1]
        assert "CAST(c.codigo AS NVARCHAR(20)) LIKE %s" in select_q
        assert "%42%" in params

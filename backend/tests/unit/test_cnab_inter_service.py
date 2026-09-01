"""Testes UNITÁRIOS do motor CNAB Inter (Fase 2a) — ver
services/cnab_inter_service.py e PENDENCIAS.md > "Bancos (Cadastro de
Cobrança / Boleto / CNAB)" > "Fase 2a". Mesmo padrão de
test_cnab_bradesco_service.py (cursor falso) — sem arquivo real do Inter
disponível pra validar contra dado real (ver docstring do módulo pros
riscos conhecidos, maiores aqui que no Bradesco)."""
from datetime import date

import services.cnab_inter_service as svc


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

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


BANCO_ROW = {
    "cod": 1, "codigo": 77, "agencia": 1234, "dv_agencia": "5",
    "contacorrente": 98765, "dv_contacorrente": "4", "dv_agencia_conta": "3",
    "carteira": 1, "Multa_Atraso_Pag": 2.0, "mora_dia_pag": 0.033,
    "numero_boleto": 0, "remessa": 0, "integracao_api": False,
}

TITULO = {
    "codigo": 10, "duplicata": 555, "desmembramento": 0, "dt_vencimento": date(2026, 8, 3),
    "valor": 250.75, "dt_emissao": date(2026, 7, 24), "num_doc_cliente": 555,
    "cliente": 1990, "conta_cedente": 98765,
}

CLIENTE = {"codigo": 1990, "nome": "CLIENTE TESTE ÁÇÃO", "cgc_cpf": "12345678000199"}
ENDERECO = {"endereco": "RUA TESTE", "numero": "100", "complemento": "AP 1", "bairro": "CENTRO", "cidade": "SAO PAULO", "uf": "SP", "cep": "01000000"}


class TestHelpers:
    def test_n_zero_pad(self):
        assert svc._n(42, 5) == "00042"
        assert svc._n(None, 3) == "000"

    def test_a_pad_e_trunca(self):
        assert svc._a("abc", 5) == "abc  "
        assert svc._a("abcdefgh", 5) == "abcde"

    def test_matricial_remove_acentos_maiuscula(self):
        assert svc._matricial("ção Álvaro") == "CAO ALVARO"

    def test_montar_vendereco_com_numero_e_complemento(self):
        v = svc._montar_vendereco(ENDERECO)
        assert len(v) == 40
        assert "RUA TESTE" in v
        assert "100" in v

    def test_montar_vendereco_sem_endereco(self):
        v = svc._montar_vendereco(None)
        assert len(v) == 40
        assert v.strip() == ""


class TestMontarRegistrosLargura:
    """Cada registro tem que somar EXATAMENTE 400 chars (CNAB400) — soma
    conferida byte a byte durante o rastreio do legado (ver docstring do
    módulo)."""

    def test_header_400(self):
        linha = svc._montar_header_400("EMPRESA TESTE LTDA", 1)
        assert len(linha) == 400
        assert linha[:11] == "01REMESSA01"
        assert "COBRANCA" in linha
        assert "077" in linha
        assert "INTER" in linha
        assert linha[-6:] == "000001"

    def test_detalhe_400(self):
        linha = svc._montar_detalhe_400(BANCO_ROW, TITULO, CLIENTE, ENDERECO, 1, 2)
        assert len(linha) == 400
        assert linha[0] == "1"
        assert linha[20:23] == "112"
        assert linha[23:27] == "0001"

    def test_detalhe_400_sem_endereco(self):
        linha = svc._montar_detalhe_400(BANCO_ROW, TITULO, CLIENTE, None, 1, 2)
        assert len(linha) == 400

    def test_trailer_400(self):
        linha = svc._montar_trailer_400(5, 7)
        assert len(linha) == 400
        assert linha[0] == "9"
        assert linha[1:7] == "000005"
        assert linha[394:400] == "000007"


class TestGerarRemessaValidacoes:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_banco_nao_e_inter(self, monkeypatch):
        cur = FakeCursor(one=[{**BANCO_ROW, "codigo": 237}])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Inter" in r["message"]

    def test_bloqueia_com_integracao_api_ligada(self, monkeypatch):
        cur = FakeCursor(one=[{**BANCO_ROW, "integracao_api": True}])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "API" in r["message"]

    def test_sem_titulos_pendentes(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), {"rz_social": "EMPRESA TESTE"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Nenhum título" in r["message"]

    def test_gera_remessa_com_um_titulo(self, monkeypatch):
        cur = FakeCursor(
            one=[
                dict(BANCO_ROW),                # SELECT * FROM bancos
                {"rz_social": "EMPRESA TESTE"},  # SELECT rz_social FROM controle
                dict(CLIENTE),                   # SELECT cliente
                dict(ENDERECO),                  # SELECT cliente_end tipo 0/1
                {"numero_boleto": 0},            # _gerar_nosso_numero_sync: SELECT bancos.numero_boleto
                None,                             # duplicata_rec_venc já tem numero_boleto? não
                None,                             # loop de colisão: livre na 1ª tentativa
            ],
            many=[[dict(TITULO)]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["qtd_titulos"] == 1
        assert conn.committed is True
        linhas = r["conteudo"].split("\r\n")
        linhas = [l for l in linhas if l]
        assert len(linhas) == 3  # header + 1 detalhe + trailer
        assert all(len(l) == 400 for l in linhas)
        assert r["nome_arquivo"].startswith("CI400_001_")


class TestProcessarRetornoValidacoes:
    CNPJ = "12345678000199"
    IDENT = "1" + "02" + CNPJ

    def _linha_base(self):
        linha = list(" " * 400)
        linha[0] = "1"
        linha[1:3] = list("02")
        linha[3:17] = list(self.CNPJ)
        return linha

    def _conteudo_com_header(self, corpo: str) -> str:
        return "02RETORNO01COBRANCA" + " " * 380 + "\n" + corpo

    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 999, "conteudo qualquer")
        assert r["success"] is False

    def test_cabecalho_invalido(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": self.CNPJ}])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, "conteudo qualquer sem cabecalho")
        assert r["success"] is False
        assert "cabeçalho" in r["message"]

    def test_cnpj_nao_confere(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": "99999999000199"}])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, self._conteudo_com_header(self._linha_base_str()))
        assert r["success"] is False

    def _linha_base_str(self):
        return "".join(self._linha_base())

    def test_ocorrencia_02_confirma_sem_baixar(self, monkeypatch):
        linha = self._linha_base()
        linha[89:91] = list("02")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": self.CNPJ}])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, self._conteudo_com_header("".join(linha)))
        assert r["success"] is True
        assert r["confirmados"] == 1
        assert r["baixados"] == 0

    def test_ocorrencia_06_titulo_nao_encontrado(self, monkeypatch):
        linha = self._linha_base()
        linha[89:91] = list("06")
        linha[70:81] = list("00000000001")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": self.CNPJ}, None])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, self._conteudo_com_header("".join(linha)))
        assert r["success"] is True
        assert r["nao_encontrados"] == ["1"]
        assert r["baixados"] == 0

    def test_ocorrencia_06_baixa_titulo(self, monkeypatch):
        linha = self._linha_base()
        linha[89:91] = list("06")
        linha[70:81] = list("00000000001")
        linha[172:178] = list("240726")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": self.CNPJ}, {"codigo": 10, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, self._conteudo_com_header("".join(linha)))
        assert r["success"] is True
        assert r["baixados"] == 1
        assert conn.committed is True
        assert "UPDATE duplicata_rec_venc SET situacao='PG'" in cur.queries[-1][0]
        # Achado real 2026-08-28: confere que o WHERE realmente usou o
        # número extraído da posição corrigida (70:81), não a antiga
        # (97:107) — é exatamente esse tipo de checagem que faltava nos
        # testes originais e deixou o bug de posição passar despercebido.
        select_params = [p for q, p in cur.queries if q.startswith("SELECT codigo, situacao FROM duplicata_rec_venc")][0]
        assert select_params[0] == 1

    def test_ocorrencia_06_ignora_ocorrencia_nao_mapeada(self, monkeypatch):
        """Ocorrência "07" apareceu num arquivo real do Inter e não tem
        tratamento no legado (nenhum ElseIf cobre esse código) — deve só
        ser ignorada, sem contar como confirmação nem baixa."""
        linha = self._linha_base()
        linha[89:91] = list("07")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": self.CNPJ}])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, self._conteudo_com_header("".join(linha)))
        assert r["success"] is True
        assert r["confirmados"] == 0
        assert r["baixados"] == 0
        assert r["ignorados"] == 1

    def test_arquivo_real_do_inter_2026_07_24(self, monkeypatch):
        """Regressão contra um retorno real do Inter (8 títulos: 4x
        ocorrência 02, 1x 07 não mapeada, 3x 06) colado pelo usuário —
        ver docstring do módulo. Só a leitura/parsing é exercida aqui
        (cursor falso, sem baixa real contra duplicata_rec_venc)."""
        conteudo = (
            "02RETORNO01COBRANCA                 0318631490SOFTHWORD INFORMATICA LTDA    077INTER          240726                                                                                                                                                                                                                                                                                                      000001\n"
            "102521796410001590001120001031863149020501                    000000009074847930300   112022107260000003011907484793032007260000000018000077000101             0000000000000000000   MAX CAR CENTRO AUTOMOTIVO LTDA               53703802000124                                                                                                                                            0903450       000002\n"
            "102521796410001590001120001031863149020488                    000000009074847966700   112022107260000002998907484796672007260000000015000077000101             0000000000000000000   ESTELA GOURMET LTDA                          26171864000160                                                                                                                                            0903450       000003\n"
            "102521796410001590001120001031863149020487                    000000009074847971700   112022107260000002997907484797172007260000000018000077000101             0000000000000000000   ENGENHEIRO PNEUS OFICINA MECANICA LTDA       56185442000104                                                                                                                                            0903450       000004\n"
            "102521796410001590001120001031863149020310                    000000009068652752700   112072107260000002835906865275272005260000000018000077000101             0000000000000000000   MAX CAR CENTRO AUTOMOTIVO LTDA               53703802000124                                                                                                                                            0903450       000005\n"
            "102521796410001590001120001031863149020615                    000000009079022843400   112022407260000003135907902284341408260000000016000077000101             0000000000000000000   TROPIFLORA PLANTAS E FLORES LTDA             27532282000124                                                                                                                                            0903450       000006\n"
            "102521796410001590001120001031863149020506                    000000009074847926100   112062107260000003016907484792612007260000000018000077000101             0000000018390210726   MESQUITA PNEUS OFICINA MECANICA LTDA         57329032000152                                                                                                                                            0903450       000007\n"
            "102521796410001590001120001031863149020502                    000000009074847987300   112062007260000003012907484798732007260000000018000077000101             0000000018000200726   MAX PNEUS OFICINA MECANICA LTDA              58742329000108                                                                                                                                            0903450       000008\n"
            "102521796410001590001120001031863149020465                    000000009074847918800   112062007260000002975907484791882007260000000015000077000101             0000000015000200726   AT2B REPRESENTACAO TECNOLOGIA E SERVICOS     06928026000180                                                                                                                                            0903450       000009\n"
            "9201077          00000008                                00005000000085000            00000                        00003000000051390                                                                                                                                                                                                                                                                      000010\n"
        )
        cur = FakeCursor(
            one=[
                {**BANCO_ROW, "contacorrente": 318631490},
                {"cgc": "52179641000159"},
                {"codigo": 100, "situacao": "A"},  # MESQUITA
                {"codigo": 101, "situacao": "A"},  # MAX PNEUS
                {"codigo": 102, "situacao": "A"},  # AT2B
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, conteudo)
        assert r["success"] is True
        assert r["confirmados"] == 4  # MAX CAR, ESTELA, ENGENHEIRO, TROPIFLORA (ocorrência 02)
        assert r["ignorados"] == 1  # a 2ª MAX CAR (ocorrência 07, não mapeada)
        assert r["baixados"] == 3  # MESQUITA, MAX PNEUS, AT2B (ocorrência 06)
        assert r["nao_encontrados"] == []
        # Achado real 2026-08-28: o teste original nunca conferia QUAL
        # número foi de fato buscado (o FakeCursor "encontra" na ordem
        # chamada, não por conteúdo da query) — por isso o bug de posição
        # do Nosso Número (97:107 em vez de 70:81) passou despercebido por
        # um mês. Reconferido aqui contra os valores reais deste mesmo
        # arquivo: MESQUITA=90748479261, MAX PNEUS=90748479873, AT2B=90748479188.
        selects = [p for q, p in cur.queries if q.startswith("SELECT codigo, situacao FROM duplicata_rec_venc")]
        assert [p[0] for p in selects] == [90748479261, 90748479873, 90748479188]

    def test_arquivo_real_kontacto_real_2026_08_28_confirma_posicao_correta(self, monkeypatch):
        """2º arquivo real, independente do de 2026-07-24 acima — retorno
        genuíno processado contra a instalação real de produção "KONTACTO
        REAL" (`minimachine`/`BD_KONTACTO`), 78 títulos (76 ocorrência 02 +
        2 ocorrência 06). Subconjunto real (header + as 2 linhas de baixa,
        únicas que exercitam a posição do Nosso Número + trailer) — não o
        arquivo completo, mas nenhuma linha foi alterada/inventada. Foi
        exatamente rodando este arquivo contra o banco real que a posição
        antiga (97:107) revelou "não encontrado" pros 2 títulos — motivou
        a correção pra 70:81 documentada no módulo. GUEREN=90820068271,
        MONDRIAN=90825112892 — conferidos ao vivo contra `duplicata_rec_
        venc` real (78/78 títulos do arquivo completo bateram na posição
        nova; 0/78 batiam na antiga)."""
        conteudo = (
            "02RETORNO01COBRANCA                 0318631490SOFTHWORD INFORMATICA LTDA    077INTER          280826                                                                                                                                                                                                                                                                                                      000001\n"
            "102521796410001590001120001031863149020621                    000000009082006827100   112062708260000003139908200682712708260000000012000077000101             0000000012000270826   GUEREN COMERCIO DE GASES LTDA                11769085000193                                                                                                                                            0903450       000002\n"
            "102521796410001590001120001031863149020675                    000000009082511270200   112022408260000003171908251127021009260000000025000077000101             0000000000000000000   GR CENTRO AUTOMOTIVO LTDA                    67192298000150                                                                                                                                            0903450       000003\n"
            "102521796410001590001120001031863149020688                    000000009082511289200   112062808260000003184908251128920509260000000072000077000101             0000000072000280826   MONDRIAN ILUMINACAO LTDA                     45930063000185                                                                                                                                            0903450       000004\n"
            "9201077          00000078                                00076000003490801            00000                        00002000000084000                                                                                                                                                                                                                                                                      000080\n"
        )
        cur = FakeCursor(
            one=[
                {**BANCO_ROW, "contacorrente": 318631490},
                {"cgc": "52179641000159"},
                {"codigo": 200, "situacao": "A"},  # GUEREN
                {"codigo": 201, "situacao": "A"},  # MONDRIAN
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, conteudo)
        assert r["success"] is True
        assert r["confirmados"] == 1  # GR CENTRO AUTOMOTIVO (ocorrência 02)
        assert r["baixados"] == 2  # GUEREN, MONDRIAN (ocorrência 06)
        assert r["nao_encontrados"] == []
        selects = [p for q, p in cur.queries if q.startswith("SELECT codigo, situacao FROM duplicata_rec_venc")]
        assert [p[0] for p in selects] == [90820068271, 90825112892]

    def test_ocorrencia_06_ja_baixado_e_idempotente(self, monkeypatch):
        linha = self._linha_base()
        linha[89:91] = list("06")
        linha[70:81] = list("00000001   ")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": self.CNPJ}, {"codigo": 10, "situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, self._conteudo_com_header("".join(linha)))
        assert r["success"] is True
        assert r["baixados"] == 0

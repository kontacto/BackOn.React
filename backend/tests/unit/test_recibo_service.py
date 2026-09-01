"""Testes unitários do núcleo compartilhado de Recibo numerado
(services/recibo_service.py) — extraído de contratos_service._gerar_
recibo_sync em 2026-08-31 pra também servir Contas a Receber."""
from datetime import date

import services.recibo_service as svc


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None


class TestGravarReciboNumeradoSync:
    def test_numeracao_sequencial_a_partir_do_controle(self):
        cur = FakeCursor(one=[{"rz_social": "EMPRESA X", "seq_recibo": 10, "ano_recibo": 2026}])
        r = svc._gravar_recibo_numerado_sync(cur, recebemos="Fulano", valor=99.9, referente="teste")
        assert r["numero"] == "011/2026"
        assert r["recebemos"] == "Fulano"
        assert r["valor"] == 99.9
        assert r["assinatura"] == "EMPRESA X"
        insert = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT INTO RECIBOS")][0]
        assert insert[0] == 11 and insert[1] == 2026
        update = [p for q, p in cur.queries if q.strip().upper().startswith("UPDATE CONTROLE")][0]
        assert update == (11,)

    def test_sem_linha_de_controle_usa_ano_atual_e_seq_1(self):
        cur = FakeCursor(one=[None])
        r = svc._gravar_recibo_numerado_sync(cur, recebemos="Fulano", valor=1.0, referente="teste")
        assert r["numero"] == f"001/{date.today().year}"

    def test_assinatura_explicita_sobrescreve_rz_social(self):
        cur = FakeCursor(one=[{"rz_social": "EMPRESA X", "seq_recibo": 0, "ano_recibo": 2026}])
        r = svc._gravar_recibo_numerado_sync(cur, recebemos="Fulano", valor=1.0, referente="teste", assinatura="  Ciclano  ")
        assert r["assinatura"] == "Ciclano"

    def test_data_explicita_usada_no_insert(self):
        cur = FakeCursor(one=[{"rz_social": "", "seq_recibo": 0, "ano_recibo": 2026}])
        r = svc._gravar_recibo_numerado_sync(
            cur, recebemos="Fulano", valor=1.0, referente="teste", data_recibo=date(2020, 1, 15),
        )
        assert r["data"] == "2020-01-15"

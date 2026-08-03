"""Testes unitários de `_validar_doc_origem` (pedido_common.py) — validação
cruzada de OS/Pedido de origem pra O.S. do tipo Garantia/Revisão, migração
de `Command2_Click` (`Revenda\\FrmTraOsNew.frm`, linhas 9737-9982). Ver
PENDENCIAS.md > "O.S. Completa" > "Doc. Origem / Revisão Programada"."""
import services.pedido_common as pc


class SqlFakeCursor:
    """Cursor fake que responde por CASAMENTO DE SUBSTRING no SQL da última
    query executada, não por ordem de chamada — mesmo padrão de
    `test_pedido_common_forma_pagamento.py`, necessário aqui porque
    `_validar_doc_origem` dispara queries condicionais/em ordens diferentes
    dependendo do ramo (revisão vs. garantia, OS vs. Pedido)."""

    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []
        self._last_q = ""
        self._one_rules: list[tuple[str, object]] = []

    def when_one(self, substr: str, value) -> "SqlFakeCursor":
        self._one_rules.append((substr, value))
        return self

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._last_q = q

    def fetchone(self):
        for substr, val in self._one_rules:
            if substr in self._last_q:
                return val
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


def _cur_flags(controla_revisao=False, exige_garantia=False, **rules) -> SqlFakeCursor:
    cur = SqlFakeCursor()
    cur.when_one("ControlaRevisaoOS FROM controle_aux", {"ControlaRevisaoOS": 1 if controla_revisao else 0})
    cur.when_one("EXIGE_OS_ORIGINAL_GARANTIA FROM controle_aux", {"EXIGE_OS_ORIGINAL_GARANTIA": 1 if exige_garantia else 0})
    for substr, val in rules.items():
        pass
    return cur


class TestNenhumRamoAplica:
    def test_tipo_sem_revisao_ou_garantia_nao_valida(self):
        cur = _cur_flags(controla_revisao=True, exige_garantia=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "Manutenção Preventiva", 0, "O", None)
        assert ok is True and validou is False and erro is None

    def test_tipo_revisao_mas_flags_desligadas_nao_valida(self):
        cur = _cur_flags(controla_revisao=False, exige_garantia=False)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 0, "O", None)
        assert ok is True and validou is False and erro is None

    def test_tipo_garantia_mas_flag_desligada_nao_valida(self):
        cur = _cur_flags(controla_revisao=False, exige_garantia=False)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "GARANTIA", 0, "O", None)
        assert ok is True and validou is False and erro is None


class TestRamoRevisao:
    def test_sem_os_original_bloqueia(self):
        cur = _cur_flags(controla_revisao=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 0, "O", None)
        assert ok is False and "obrigatoriamente preencher" in erro.lower()

    def test_forca_tipo_doc_original_para_o_mesmo_com_pedido_informado(self):
        """Ramo Revisão nunca aceita Pedido como origem — o tipo é forçado
        pra 'O' mesmo que o request mande 'P' (a tela nem deixa escolher)."""
        cur = _cur_flags(controla_revisao=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 0, "P", None)
        assert tipo == "O"

    def test_origem_igual_a_propria_os_bloqueia(self):
        cur = _cur_flags(controla_revisao=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 100, "O", None)
        assert ok is False and "mesmo número da o.s. de revisão" in erro.lower()

    def test_os_origem_nao_encontrada_bloqueia(self):
        cur = _cur_flags(controla_revisao=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 200, "O", None)
        assert ok is False and "não encontrada" in erro.lower()

    def test_cliente_diferente_bloqueia(self):
        cur = _cur_flags(controla_revisao=True)
        cur.when_one("cliente, situacao FROM os WHERE", {"cliente": 99, "situacao": "PG"})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 200, "O", None)
        assert ok is False and "mesmo cliente" in erro.lower()

    def test_os_origem_nao_faturada_bloqueia(self):
        cur = _cur_flags(controla_revisao=True)
        cur.when_one("cliente, situacao FROM os WHERE", {"cliente": 10, "situacao": "A"})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 200, "O", None)
        assert ok is False and "não está faturada" in erro.lower()

    def test_sem_data_de_revisao_disponivel_bloqueia(self):
        cur = _cur_flags(controla_revisao=True)
        cur.when_one("cliente, situacao FROM os WHERE", {"cliente": 10, "situacao": "PG"})
        # osrevisao WHERE osrevisao=100 (já vinculada?) -> None (não)
        # osrevisao WHERE os=200 AND osrevisao=0 (disponível?) -> None (não)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 200, "O", None)
        assert ok is False and "não tem datas de revisão disponíveis" in erro.lower()

    def test_sucesso_com_data_disponivel(self):
        cur = _cur_flags(controla_revisao=True)
        cur.when_one("cliente, situacao FROM os WHERE", {"cliente": 10, "situacao": "PG"})
        cur.when_one("FROM osrevisao WHERE os=", {"ok": 1})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 200, "O", None)
        assert ok is True and validou is True and erro is None

    def test_ja_vinculada_a_propria_os_dispensa_checagem_de_disponibilidade(self):
        """Se esta O.S. já consumiu uma data da origem (`osrevisao=100` já
        existe), não precisa achar OUTRA disponível — está reeditando a
        mesma revisão já vinculada."""
        cur = _cur_flags(controla_revisao=True)
        cur.when_one("cliente, situacao FROM os WHERE", {"cliente": 10, "situacao": "PG"})
        cur.when_one("FROM osrevisao WHERE osrevisao=", {"ok": 1})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 200, "O", None)
        assert ok is True and validou is True

    def test_bypass_com_autorizado_por(self):
        cur = _cur_flags(controla_revisao=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 0, "O", "GERENTE1")
        assert ok is True and validou is True and erro is None

    def test_ja_validado_com_mesmos_valores_nao_revalida(self):
        cur = _cur_flags(controla_revisao=True)
        cur.when_one(
            "os_original, tipo_doc_original, validou_garantia FROM os WHERE",
            {"os_original": 200, "tipo_doc_original": "O", "validou_garantia": 1},
        )
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 200, "O", None)
        assert ok is True and validou is True and erro is None
        # nenhuma query de validação cruzada disparada além da checagem de já-validado
        assert not any("FROM osrevisao" in q for q, _ in cur.queries)

    def test_ja_validado_mas_os_original_mudou_revalida(self):
        cur = _cur_flags(controla_revisao=True)
        cur.when_one(
            "os_original, tipo_doc_original, validou_garantia FROM os WHERE",
            {"os_original": 999, "tipo_doc_original": "O", "validou_garantia": 1},
        )
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 200, "O", None)
        assert ok is False and "não encontrada" in erro.lower()


class TestRamoGarantia:
    def test_sem_documento_origem_bloqueia(self):
        cur = _cur_flags(exige_garantia=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "GARANTIA", 0, "O", None)
        assert ok is False and "obrigatoriamente preencher" in erro.lower()

    def test_aceita_pedido_como_origem(self):
        cur = _cur_flags(exige_garantia=True)
        cur.when_one("cliente, situacao FROM pedido_venda WHERE", {"cliente": 10, "situacao": "PG"})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "GARANTIA", 300, "P", None)
        assert ok is True and validou is True and tipo == "P"

    def test_pedido_nao_encontrado_bloqueia(self):
        cur = _cur_flags(exige_garantia=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "GARANTIA", 300, "P", None)
        assert ok is False and "pedido de venda não encontrado" in erro.lower()

    def test_pedido_cliente_diferente_bloqueia(self):
        cur = _cur_flags(exige_garantia=True)
        cur.when_one("cliente, situacao FROM pedido_venda WHERE", {"cliente": 99, "situacao": "PG"})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "GARANTIA", 300, "P", None)
        assert ok is False and "mesmo cliente" in erro.lower()

    def test_pedido_nao_faturado_bloqueia(self):
        cur = _cur_flags(exige_garantia=True)
        cur.when_one("cliente, situacao FROM pedido_venda WHERE", {"cliente": 10, "situacao": "A"})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "GARANTIA", 300, "P", None)
        assert ok is False and "não está faturado" in erro.lower()

    def test_aceita_os_como_origem_sem_checar_osrevisao(self):
        """Ramo Garantia não checa `osrevisao` disponível — essa checagem é
        exclusiva do Ramo Revisão."""
        cur = _cur_flags(exige_garantia=True)
        cur.when_one("cliente, situacao FROM os WHERE", {"cliente": 10, "situacao": "PG"})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "GARANTIA", 200, "O", None)
        assert ok is True and validou is True
        assert not any("FROM osrevisao" in q for q, _ in cur.queries)

    def test_revisao_sem_controla_revisao_cai_no_ramo_garantia(self):
        """Tipo Revisão, mas SEM `ControlaRevisaoOS` — se
        `EXIGE_OS_ORIGINAL_GARANTIA` estiver ligado, ainda exige Doc.
        Origem (ramo Garantia, aceita Pedido também)."""
        cur = _cur_flags(controla_revisao=False, exige_garantia=True)
        cur.when_one("cliente, situacao FROM pedido_venda WHERE", {"cliente": 10, "situacao": "PG"})
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "REVISÃO", 300, "P", None)
        assert ok is True and validou is True and tipo == "P"

    def test_bypass_com_autorizado_por(self):
        cur = _cur_flags(exige_garantia=True)
        ok, validou, tipo, erro = pc._validar_doc_origem(cur, 100, 10, "GARANTIA", 0, "O", "SUPERVISOR1")
        assert ok is True and validou is True

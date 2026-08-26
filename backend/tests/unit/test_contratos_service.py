"""Testes focados de `contratos_service.py` — cobre só a extensão de
2026-08-24 (Faturar Contratos ganha campo `tipo_doc` sem emitir nada
automaticamente, mais a ação separada `_emitir_documento_contrato_sync`
e a distribuição por Centro de Custo). O resto do módulo (Fase A completa
+ o restante do motor de Faturar Contratos) foi validado ponta a ponta
contra banco real (ver PENDENCIAS.md > "Contratos") em vez de testes
unitários — não duplicado aqui.

**Achado real, corrigido no mesmo dia**: a 1ª versão desta extensão
emitia NFS-e AUTOMATICAMENTE ao faturar um contrato tipo Nota Fiscal/
Boleto. O Leandro corrigiu direto: "fica a critério do cliente se ele
vai emitir a nota de produtos ou nota de serviços ou ambas ou nenhuma" —
regra que vale pra qualquer comanda com produto+serviço no sistema, não
só Contratos. A emissão agora é SEMPRE uma ação separada e opcional."""
import services.contratos_service as svc


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
        self.committed = 0
        self.rolled = 0

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled += 1

    def close(self):
        pass


CFG = {
    "fatura_os": False, "cfop_peca": "5102", "cfop_servico": "5933",
    "cod_servico_contrato": "S999", "tmov_peca": "S01", "tmov_servico": "S02",
}


def _patch_comum(monkeypatch, cur, *, gerar_comanda_ok=True, transf_erro=None):
    conn = FakeConn(cur)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
    monkeypatch.setattr(svc, "_config_faturamento_sync", lambda cur: CFG)
    if gerar_comanda_ok:
        monkeypatch.setattr(svc, "_gerar_comanda_sync", lambda cur, cfg, cod, valor, ano, mes, func, venc=None: {"success": True, "comanda": 5001, "descreve_os": ""})
    else:
        monkeypatch.setattr(svc, "_gerar_comanda_sync", lambda cur, cfg, cod, valor, ano, mes, func, venc=None: {"success": False, "message": "Contrato não encontrado."})
    monkeypatch.setattr(svc, "_transf_receber_sync", lambda cur, comanda, tipo_mov, cod_servico_contrato="": transf_erro)
    return conn


def _item(codigo=1, tipo_doc=None, valor=100.0):
    return {"codigo": codigo, "valor_total": valor, "vencimento": "2026-09-01", "tipo_doc": tipo_doc}


class TestFaturarContratosSyncNuncaEmiteAutomatico:
    def test_tipo_doc_recibo_so_fatura(self, monkeypatch):
        cur = FakeCursor()
        _patch_comum(monkeypatch, cur)
        r = svc._faturar_contratos_sync("s", "b", 2026, 9, [_item(tipo_doc="R")], 1)
        res = r["resultados"][0]
        assert res["success"] is True
        assert res["tipo_doc"] == "R"
        assert "nf_e" not in res

    def test_tipo_doc_nota_fiscal_nao_dispara_emissao(self, monkeypatch):
        cur = FakeCursor()
        _patch_comum(monkeypatch, cur)
        chamado = {"n": 0}
        monkeypatch.setattr(svc.nfe_agrupada_service, "_emitir_nfse_agrupada_sync", lambda *a, **k: chamado.update(n=chamado["n"] + 1))
        monkeypatch.setattr(svc.nfe_agrupada_service, "_emitir_nfe_agrupada_sync", lambda *a, **k: chamado.update(n=chamado["n"] + 1))

        r = svc._faturar_contratos_sync("s", "b", 2026, 9, [_item(tipo_doc="N")], 1)
        res = r["resultados"][0]
        assert res["success"] is True
        assert res["tipo_doc"] == "N"
        assert "nf_e" not in res
        assert chamado["n"] == 0

    def test_tipo_doc_boleto_nao_dispara_emissao(self, monkeypatch):
        cur = FakeCursor()
        _patch_comum(monkeypatch, cur)
        chamado = {"n": 0}
        monkeypatch.setattr(svc.nfe_agrupada_service, "_emitir_nfse_agrupada_sync", lambda *a, **k: chamado.update(n=chamado["n"] + 1))

        r = svc._faturar_contratos_sync("s", "b", 2026, 9, [_item(tipo_doc="B")], 1)
        assert r["resultados"][0]["tipo_doc"] == "B"
        assert chamado["n"] == 0

    def test_falha_ao_gerar_comanda_nao_grava_tipo_doc(self, monkeypatch):
        cur = FakeCursor()
        _patch_comum(monkeypatch, cur, gerar_comanda_ok=False)
        r = svc._faturar_contratos_sync("s", "b", 2026, 9, [_item(tipo_doc="N")], 1)
        assert r["resultados"][0]["success"] is False
        assert "tipo_doc" not in r["resultados"][0]


class TestEmitirDocumentoContratoSync:
    def test_tipo_invalido_bloqueia(self, monkeypatch):
        r = svc._emitir_documento_contrato_sync("s", "b", tipo="xyz", comanda=1, cod_func=1)
        assert r["success"] is False

    def test_nfse_reaproveita_motor_de_agrupar_comandas(self, monkeypatch):
        capturado = {}

        def _fake_nfse(servidor, banco, *, comandas, usuario, classe, master):
            capturado.update(comandas=comandas, usuario=usuario, classe=classe, master=master)
            return {"success": True, "numero": 42, "chave_acesso": "1" * 50, "nota_fisc": 900}

        monkeypatch.setattr(svc.nfe_agrupada_service, "_emitir_nfse_agrupada_sync", _fake_nfse)

        r = svc._emitir_documento_contrato_sync("s", "b", tipo="nfse", comanda=5001, cod_func=7, classe=3, master=False)
        assert r["success"] is True
        assert r["numero"] == 42
        assert capturado == {"comandas": [5001], "usuario": 7, "classe": 3, "master": False}

    def test_nfe_com_sucesso_roda_distribuicao_centro_de_custo(self, monkeypatch):
        chamado_nfe = {}

        def _fake_nfe(servidor, banco, *, comandas, usuario, classe, master):
            chamado_nfe.update(comandas=comandas)
            return {"success": True, "numero": 10, "chave_acesso": "3" * 44, "nota_fisc": 555}

        monkeypatch.setattr(svc.nfe_agrupada_service, "_emitir_nfe_agrupada_sync", _fake_nfe)
        monkeypatch.setattr(svc, "_config_faturamento_sync", lambda cur: CFG)

        chamado_rateio = {}
        monkeypatch.setattr(
            svc, "_distribuir_centro_custo_sync",
            lambda cur, nota_fiscal, comanda, cod_servico: chamado_rateio.update(nota_fiscal=nota_fiscal, comanda=comanda, cod_servico=cod_servico),
        )
        cur = FakeCursor()
        conn = FakeConn(cur)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)

        r = svc._emitir_documento_contrato_sync("s", "b", tipo="nfe", comanda=5001, cod_func=1)
        assert r["success"] is True
        assert chamado_rateio == {"nota_fiscal": 555, "comanda": 5001, "cod_servico": "S999"}
        assert conn.committed == 1

    def test_nfe_com_falha_nao_tenta_rateio(self, monkeypatch):
        monkeypatch.setattr(
            svc.nfe_agrupada_service, "_emitir_nfe_agrupada_sync",
            lambda *a, **k: {"success": False, "message": "Nenhuma das comandas selecionadas tem item de produto."},
        )
        chamado_rateio = {"n": 0}
        monkeypatch.setattr(svc, "_distribuir_centro_custo_sync", lambda *a, **k: chamado_rateio.update(n=chamado_rateio["n"] + 1))

        r = svc._emitir_documento_contrato_sync("s", "b", tipo="nfe", comanda=5001, cod_func=1)
        assert r["success"] is False
        assert chamado_rateio["n"] == 0

    def test_nfse_nunca_tenta_rateio(self, monkeypatch):
        # NFS-e não tem n_fiscal.codigo (grava em `dps`) -- rateio por
        # Centro de Custo só se aplica ao lado NF-e, ver docstring do
        # módulo. Confirma que o caminho nfse não chama a distribuição.
        monkeypatch.setattr(
            svc.nfe_agrupada_service, "_emitir_nfse_agrupada_sync",
            lambda *a, **k: {"success": True, "numero": 1, "nota_fisc": 900},
        )
        chamado_rateio = {"n": 0}
        monkeypatch.setattr(svc, "_distribuir_centro_custo_sync", lambda *a, **k: chamado_rateio.update(n=chamado_rateio["n"] + 1))

        r = svc._emitir_documento_contrato_sync("s", "b", tipo="nfse", comanda=5001, cod_func=1)
        assert r["success"] is True
        assert chamado_rateio["n"] == 0


class TestDistribuirCentroCustoSync:
    def test_soma_por_centro_custo_sem_5_porcento(self, monkeypatch):
        # Achado real, confirmado com o Leandro (2026-08-24): o "+5%" de
        # ISS do legado (`CentroCustoContrato`) pode ser desconsiderado —
        # só o valor puro entra no rateio.
        cur = FakeCursor(many=[[
            {"centro_custo": 10, "total": 100.0},
            {"centro_custo": 10, "total": 50.0},
            {"centro_custo": 20, "total": 30.0},
        ]])
        svc._distribuir_centro_custo_sync(cur, 555, 5001, "S999")
        inserts = [q for q in cur.queries if q[0].startswith("INSERT INTO n_fiscal_custo")]
        assert len(inserts) == 2
        valores = {p[1]: p[2] for _, p in inserts}
        assert valores[10] == 150.0
        assert valores[20] == 30.0

    def test_delete_anterior_sempre_roda(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        svc._distribuir_centro_custo_sync(cur, 555, 5001, "S999")
        assert any(q[0].startswith("DELETE FROM n_fiscal_custo") for q in cur.queries)

    def test_centro_custo_zerado_nao_insere(self, monkeypatch):
        cur = FakeCursor(many=[[{"centro_custo": 10, "total": 100.0}, {"centro_custo": 10, "total": -100.0}]])
        svc._distribuir_centro_custo_sync(cur, 555, 5001, "S999")
        assert not any(q[0].startswith("INSERT INTO n_fiscal_custo") for q in cur.queries)


class TestDistribuirCentroCustoReceberSync:
    """`_distribuir_centro_custo_receber_sync` -- achado real 2026-08-24
    (`Geral\\FrmFatContrato.frm:2473-2497`, variante irmã de
    `CentroCustoContrato`): fecha o gap de Centro de Custo pra contrato
    100% serviço, gravando em `receber_custo` (chave `Receber.codigo`)
    em vez de `n_fiscal_custo` (chave `n_fiscal.codigo`, só existe quando
    uma NF-e é emitida)."""

    def test_soma_por_centro_custo_grava_em_receber_custo(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"centro_custo": 10, "total": 100.0},
            {"centro_custo": 10, "total": 50.0},
            {"centro_custo": 20, "total": 30.0},
        ]])
        svc._distribuir_centro_custo_receber_sync(cur, 777, 5001, "S999")
        inserts = [q for q in cur.queries if q[0].startswith("INSERT INTO receber_custo")]
        assert len(inserts) == 2
        valores = {p[1]: p[2] for _, p in inserts}
        assert valores[10] == 150.0
        assert valores[20] == 30.0
        assert all(p[0] == 777 for _, p in inserts)  # nota = cod_receber, não n_fiscal

    def test_centro_custo_zerado_nao_insere(self, monkeypatch):
        cur = FakeCursor(many=[[{"centro_custo": 10, "total": 100.0}, {"centro_custo": 10, "total": -100.0}]])
        svc._distribuir_centro_custo_receber_sync(cur, 777, 5001, "S999")
        assert not any(q[0].startswith("INSERT INTO receber_custo") for q in cur.queries)

    def test_nao_faz_delete_previo(self, monkeypatch):
        # Diferente de _distribuir_centro_custo_sync (n_fiscal_custo):
        # esta roda uma vez por faturamento, sobre um cod_receber NOVO —
        # não existe um "anterior" pra limpar (réplica fiel da fonte, que
        # também não tem DELETE aqui).
        cur = FakeCursor(many=[[]])
        svc._distribuir_centro_custo_receber_sync(cur, 777, 5001, "S999")
        assert not any(q[0].startswith("DELETE") for q in cur.queries)


class TestTransfReceberSyncCentroCusto:
    def _cur_faturamento_ok(self):
        return FakeCursor(
            one=[
                {"cliente": 1, "valor_venda": 100.0, "data": "2026-09-01"},  # SELECT comanda
                {"geranumerodup": False, "desmembramento_dup": "", "numero_dup": 0},  # SELECT controle
                {"codigo": 900},  # SELECT TOP 1 codigo FROM Receber
                {"xcod": 950},  # SELECT MAX(codigo) FROM Duplicata_Receber
            ],
            many=[[]],  # nf_vencimento vazio -> ramo Else
        )

    def test_com_cod_servico_contrato_roda_distribuicao(self, monkeypatch):
        cur = self._cur_faturamento_ok()
        chamado = {}
        monkeypatch.setattr(
            svc, "_distribuir_centro_custo_receber_sync",
            lambda cur, cod_receber, comanda, cod_servico: chamado.update(cod_receber=cod_receber, comanda=comanda, cod_servico=cod_servico),
        )
        erro = svc._transf_receber_sync(cur, 5001, "S02", "S999")
        assert erro is None
        assert chamado == {"cod_receber": 900, "comanda": 5001, "cod_servico": "S999"}

    def test_sem_cod_servico_contrato_nao_roda_distribuicao(self, monkeypatch):
        cur = self._cur_faturamento_ok()
        chamado = {"n": 0}
        monkeypatch.setattr(svc, "_distribuir_centro_custo_receber_sync", lambda *a, **k: chamado.update(n=chamado["n"] + 1))
        erro = svc._transf_receber_sync(cur, 5001, "S02")
        assert erro is None
        assert chamado["n"] == 0


class TestListarCobrancasSync:
    """`_listar_cobrancas_sync` -- réplica de Command1_Click (FrmEnvCob.
    frm). Achado real 2026-08-25: as linhas de `cobrancas_enviadas` são
    criadas no faturamento (`_gerar_comanda_sync`), não por esta tela --
    aqui só consulta o que já foi lançado."""

    def test_sem_periodo_nem_mes_ano_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        r = svc._listar_cobrancas_sync("s", "b", ano=None, mes=None, data_ini=None, data_fim=None, status=None)
        assert r["success"] is False
        assert cur.queries == []

    def test_lista_por_ano_mes(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "codigo_cobrancas_enviadas": 1, "contrato": 10, "comanda": 5001,
            "ano_referencia": 2026, "mes_referencia": 9, "vencimento": "2026-09-10",
            "data_envio": None, "hora_envio": "", "e_mail_envio": "", "status_envio": "Não Enviado", "obs_envio": "",
            "contrato_texto": "CT-001", "cliente": 55, "nome": "Cliente Teste", "fantasia": "",
            "email_destino": "cliente@teste.com", "valor_venda": 150.0,
        }]])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        r = svc._listar_cobrancas_sync("s", "b", ano=2026, mes=9, data_ini=None, data_fim=None, status=None)
        assert r["success"] is True
        assert len(r["items"]) == 1
        item = r["items"][0]
        assert item["codigo"] == 1
        assert item["email_destino"] == "cliente@teste.com"
        q, p = cur.queries[0]
        assert "ano_referencia" in q and "mes_referencia" in q
        assert 2026 in p and 9 in p

    def test_lista_por_periodo(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        r = svc._listar_cobrancas_sync("s", "b", ano=None, mes=None, data_ini="2026-09-01", data_fim="2026-09-30", status=None)
        assert r["success"] is True
        q, p = cur.queries[0]
        assert "c.data >= %s AND c.data <= %s" in q
        assert "2026-09-01" in p and "2026-09-30" in p

    def test_status_filtro_aplica_in_clause(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        r = svc._listar_cobrancas_sync("s", "b", ano=2026, mes=9, data_ini=None, data_fim=None, status=["Falha ao Enviar", "Não Enviado"])
        assert r["success"] is True
        q, p = cur.queries[0]
        assert "cb.status_envio IN" in q
        assert "Falha ao Enviar" in p and "Não Enviado" in p


class TestEnviarCobrancasSync:
    """`_enviar_cobrancas_sync` -- réplica simplificada de Command2_Click.
    Fase 1 (2026-08-25) era sem anexo -- nem Recibo nem Boleto tinham PDF
    persistido. 2026-08-26: quando o título já está registrado num banco
    (via "Geração de Boletos", ver boleto_pdf_service.py), o boleto em
    PDF é anexado de verdade -- contrato tipo Recibo, ou Boleto que nunca
    passou por "Geração de Boletos", continua sem anexo."""

    def _row_ok(self, email="cliente@teste.com", tipo_cobranca=2):
        return {
            "codigo_cobrancas_enviadas": 1, "contrato": 10, "comanda": 500, "ano_referencia": 2026, "mes_referencia": 9,
            "tipo_cobranca": tipo_cobranca, "email_destino": email, "nome": "Cliente Teste", "fantasia": "",
        }

    def test_ids_vazio_bloqueia(self, monkeypatch):
        r = svc._enviar_cobrancas_sync("s", "b", [])
        assert r["success"] is False

    def test_cobranca_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        r = svc._enviar_cobrancas_sync("s", "b", [999])
        assert r["success"] is True
        assert r["resultados"][0]["success"] is False
        assert "não encontrada" in r["resultados"][0]["message"].lower()

    def test_sem_email_marca_status_e_nunca_tenta_enviar(self, monkeypatch):
        cur = FakeCursor(one=[self._row_ok(email="")])
        conn = FakeConn(cur)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        chamado = {"n": 0}
        monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", lambda *a, **k: chamado.update(n=chamado["n"] + 1))

        r = svc._enviar_cobrancas_sync("s", "b", [1])
        assert r["resultados"][0]["success"] is False
        assert chamado["n"] == 0
        assert any("Sem Email cadastrado" in q for q, _ in cur.queries if q.startswith("UPDATE cobrancas_enviadas"))
        assert conn.committed >= 1

    def test_com_email_envia_e_atualiza_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[self._row_ok()])
        conn = FakeConn(cur)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        capturado = {}

        def _fake_envio(servidor, banco, destinatario, assunto, corpo, anexos=None):
            capturado.update(destinatario=destinatario, assunto=assunto, anexos=anexos)
            return {"success": True, "message": f"E-mail enviado para {destinatario}."}

        monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", _fake_envio)

        r = svc._enviar_cobrancas_sync("s", "b", [1])
        assert r["resultados"][0]["success"] is True
        assert capturado["destinatario"] == "cliente@teste.com"
        assert "Setembro" in capturado["assunto"] and "2026" in capturado["assunto"]
        assert capturado["anexos"] is None  # nenhum duplicata_rec_venc resolvido -- sem boleto pra anexar
        assert any(q.startswith("UPDATE cobrancas_enviadas") and "Enviado com Sucesso" in q for q, _ in cur.queries)
        assert any(q.startswith("UPDATE contratos") for q, _ in cur.queries)

    def test_com_boleto_ja_registrado_anexa_pdf(self, monkeypatch):
        """2026-08-26: título já registrado num banco (drv.banco_cedente
        preenchido) -- o boleto em PDF vai anexado de verdade."""
        cur = FakeCursor(one=[self._row_ok(), {"codigo": 777}])
        conn = FakeConn(cur)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        monkeypatch.setattr(svc.boleto_pdf_service, "gerar_pdf_um_titulo_sync", lambda cur, drv_codigo: b"%PDF-fake-boleto")
        capturado = {}

        def _fake_envio(servidor, banco, destinatario, assunto, corpo, anexos=None):
            capturado.update(anexos=anexos)
            return {"success": True, "message": "ok"}

        monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", _fake_envio)

        r = svc._enviar_cobrancas_sync("s", "b", [1])
        assert r["resultados"][0]["success"] is True
        assert capturado["anexos"] is not None
        assert capturado["anexos"][0]["conteudo"] == b"%PDF-fake-boleto"
        assert capturado["anexos"][0]["nome_arquivo"] == "boleto_10_2026_09.pdf"

    def test_contrato_recibo_anexa_pdf_identificado_pela_comanda(self, monkeypatch):
        """2026-08-26: contrato tipo Recibo (tipo_cobranca=0) anexa um
        recibo identificado pelo NÚMERO DA COMANDA (resposta de Leandro:
        "o controle já é o número da comanda, não precisa criar
        coluna") -- leitura pura, nunca grava em Recibos/Seq_Recibo."""
        cur = FakeCursor(one=[self._row_ok(tipo_cobranca=0)])
        conn = FakeConn(cur)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        capturado_recibo = {}

        def _fake_montar_recibo(cur, contrato_codigo, comanda, ano_ref, mes_ref, descreve_os):
            capturado_recibo.update(contrato_codigo=contrato_codigo, comanda=comanda, ano_ref=ano_ref, mes_ref=mes_ref)
            return {
                "success": True, "numero": "500", "recebemos": "Cliente Teste", "valor": 500.0,
                "valor_extenso": "quinhentos reais", "referente": "mensalidade", "data": "2026-09-10",
                "assinatura": "EMPRESA TESTE LTDA",
            }

        monkeypatch.setattr(svc, "_montar_recibo_para_anexo_sync", _fake_montar_recibo)
        monkeypatch.setattr(svc.recibo_pdf_service, "gerar_recibo_pdf_bytes", lambda dados: b"%PDF-fake-recibo")
        capturado_email = {}

        def _fake_envio(servidor, banco, destinatario, assunto, corpo, anexos=None):
            capturado_email.update(anexos=anexos)
            return {"success": True, "message": "ok"}

        monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", _fake_envio)

        r = svc._enviar_cobrancas_sync("s", "b", [1])
        assert r["resultados"][0]["success"] is True
        assert capturado_recibo == {"contrato_codigo": 10, "comanda": 500, "ano_ref": 2026, "mes_ref": 9}
        assert capturado_email["anexos"][0]["conteudo"] == b"%PDF-fake-recibo"
        assert capturado_email["anexos"][0]["nome_arquivo"] == "recibo_comanda_500.pdf"

    def test_contrato_recibo_falha_ao_montar_segue_sem_anexo(self, monkeypatch):
        cur = FakeCursor(one=[self._row_ok(tipo_cobranca=0)])
        conn = FakeConn(cur)
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        monkeypatch.setattr(svc, "_montar_recibo_para_anexo_sync", lambda *a, **k: {"success": False, "message": "Contrato ou comanda não encontrados."})
        capturado = {}
        monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", lambda servidor, banco, destinatario, assunto, corpo, anexos=None: capturado.update(anexos=anexos) or {"success": True, "message": "ok"})

        r = svc._enviar_cobrancas_sync("s", "b", [1])
        assert r["resultados"][0]["success"] is True
        assert capturado["anexos"] is None

    def test_falha_no_envio_marca_falha(self, monkeypatch):
        cur = FakeCursor(one=[self._row_ok()])
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        monkeypatch.setattr(svc, "_modulo_contratos_ativo", lambda cur: True)
        monkeypatch.setattr(
            svc.email_cobranca_service, "_enviar_email_sync",
            lambda *a, **k: {"success": False, "message": "Falha de autenticação SMTP"},
        )

        r = svc._enviar_cobrancas_sync("s", "b", [1])
        assert r["resultados"][0]["success"] is False
        assert any(q.startswith("UPDATE cobrancas_enviadas") and "Falha ao Enviar" in q for q, _ in cur.queries)

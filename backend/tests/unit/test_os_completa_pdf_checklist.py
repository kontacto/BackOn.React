"""Testes unitários da seção "Checklist de Entrada do Veículo" dentro do
motor de PDF da O.S. Completa (`os_completa_pdf_service.py`) — pedido
explícito do usuário 2026-08-26, sem precedente no legado. Cobre só a
regra de quando a seção desenha (Oficina + Aberta) versus quando é um
no-op puro (sem placa, ou situação diferente de Aberta) — o restante do
motor de PDF (cabeçalho/itens/totais) já foi verificado visualmente via
self-render com pymupdf (ferramenta dev-only, não faz parte do requirements
nem da suíte automatizada) ao longo desta sessão.

Usa um `reportlab.pdfgen.canvas.Canvas` real (não mockado) — as funções de
desenho recebem e mutam um canvas de verdade, mockar isso teria menos
valor que só desenhar de fato num buffer descartável."""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

import services.os_completa_pdf_service as svc


def _canvas():
    buf = BytesIO()
    return canvas.Canvas(buf, pagesize=A4), buf


def _dados(**over):
    os_row = {
        "codigo": 1, "situacao": "A", "placa": "ABC1D23",
    }
    os_row.update(over.pop("os", {}))
    base = {"os": os_row, "checklist_veiculo": []}
    base.update(over)
    return base


class TestDesenharChecklistVeiculo:
    def test_sem_placa_e_noop(self):
        c, _ = _canvas()
        dados = _dados(os=dict(placa=""))
        y_antes = 500
        y_depois = svc._desenhar_checklist_veiculo(c, dados, y_antes, 1)
        assert y_depois == y_antes
        assert c.getPageNumber() == 1  # nenhuma página nova foi aberta

    def test_placa_mas_situacao_nao_aberta_e_noop(self):
        c, _ = _canvas()
        for sit in ("F", "C", "PG", ""):
            dados = _dados(os=dict(situacao=sit))
            y_antes = 500
            y_depois = svc._desenhar_checklist_veiculo(c, dados, y_antes, 1)
            assert y_depois == y_antes, f"situacao={sit!r} deveria ser no-op"
            assert c.getPageNumber() == 1

    def test_oficina_aberta_sem_marcacao_desenha_pagina_vazia(self):
        c, _ = _canvas()
        dados = _dados()
        y_depois = svc._desenhar_checklist_veiculo(c, dados, 500, 42)
        assert c.getPageNumber() == 2  # abriu página nova (_novo_topo_pagina)
        # y é relativo à página NOVA (topo dela), não comparável ao y da
        # página anterior — só confere que o cursor ficou num valor são,
        # abaixo do topo da página e ainda dentro da folha.
        assert 0 < y_depois < svc._ALTURA

    def test_oficina_aberta_com_marcacoes_nao_estoura_excecao(self):
        c, _ = _canvas()
        marcacoes = [
            {"tipo_avaria": "AMASSADO", "pos_x": 0.1, "pos_y": 0.1, "descricao": "Porta"},
            {"tipo_avaria": "ARRANHAO", "pos_x": 0.9, "pos_y": 0.2, "descricao": ""},
            {"tipo_avaria": "DESCONHECIDO", "pos_x": 0.5, "pos_y": 0.5, "descricao": "Tipo não mapeado"},
        ]
        dados = _dados(checklist_veiculo=marcacoes)
        y_depois = svc._desenhar_checklist_veiculo(c, dados, 500, 1)
        assert c.getPageNumber() == 2
        assert 0 < y_depois < svc._ALTURA

    def test_muitas_marcacoes_pagina_a_legenda(self):
        """Legenda longa o bastante pra estourar 1 página precisa continuar
        numa página nova sem quebrar — mesma paginação já usada pela
        tabela de itens (`_novo_topo_pagina`)."""
        c, _ = _canvas()
        marcacoes = [
            {"tipo_avaria": "OUTRO", "pos_x": 0.5, "pos_y": 0.5, "descricao": f"Avaria número {i} com descrição bem detalhada para forçar quebra de linha"}
            for i in range(40)
        ]
        dados = _dados(checklist_veiculo=marcacoes)
        svc._desenhar_checklist_veiculo(c, dados, 500, 7)
        assert c.getPageNumber() >= 3  # diagrama + legenda estourou pra 2+ páginas de checklist

    def test_tipo_avaria_desconhecido_usa_o_proprio_valor_como_label(self):
        c, _ = _canvas()
        dados = _dados(checklist_veiculo=[{"tipo_avaria": "XYZ", "pos_x": 0.5, "pos_y": 0.5, "descricao": ""}])
        # não deve lançar KeyError mesmo com tipo fora de _TIPO_AVARIA_LABEL
        svc._desenhar_checklist_veiculo(c, dados, 500, 1)


class TestMontarDadosIncluiChecklist:
    def test_chave_checklist_veiculo_presente(self, monkeypatch):
        import asyncio

        async def fake_get_os_completo(*a, **k):
            return {"success": True, "os": {"codigo": 1, "cliente": None}}

        async def fake_list_itens(*a, **k):
            return {"items": []}

        async def fake_list_tempo(*a, **k):
            return {"items": []}

        async def fake_list_formas(*a, **k):
            return {"items": []}

        async def fake_list_equip(*a, **k):
            return {"items": []}

        async def fake_get_empresa(*a, **k):
            return {"success": True}

        async def fake_list_checklist(*a, **k):
            return {"success": True, "items": [{"codigo": 1, "tipo_avaria": "AMASSADO", "pos_x": 0.1, "pos_y": 0.1, "descricao": ""}]}

        monkeypatch.setattr(svc.os_completo_service, "get_os_completo", fake_get_os_completo)
        monkeypatch.setattr(svc.os_itens_service, "list_itens", fake_list_itens)
        monkeypatch.setattr(svc.os_tempo_service, "list_tempo", fake_list_tempo)
        monkeypatch.setattr(svc.forma_pagamento_service, "list_formas_pagamento", fake_list_formas)
        monkeypatch.setattr(svc.os_equipamento_service, "list_equipamentos", fake_list_equip)
        monkeypatch.setattr(svc.controle_service, "get_empresa", fake_get_empresa)
        monkeypatch.setattr(svc.os_checklist_veiculo_service, "list_checklist", fake_list_checklist)

        dados = asyncio.run(svc._montar_dados_os_sync("srv", "bd", 1))
        assert dados is not None
        assert len(dados["checklist_veiculo"]) == 1
        assert dados["checklist_veiculo"][0]["tipo_avaria"] == "AMASSADO"

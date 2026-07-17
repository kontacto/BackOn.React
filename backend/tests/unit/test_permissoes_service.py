"""Testes unitários de `disabled_telas` (filtro de telas por módulo ligado/
desligado, `controle_configuracao`) — função pura, sem banco."""
import services.permissoes_service as ps


def _flags(**over):
    base = {c: False for c, _ in [
        ("Pedido_venda", ""), ("Bar", ""), ("Cilindro", ""), ("Clientes", ""),
        ("servicos", ""), ("Posto", ""), ("Oficina", ""), ("Assistencia", ""),
    ]}
    base.update(over)
    return base


class TestOrdemDeServicoOficinaOuAssistencia:
    def test_os_e_os_comp_ocultas_se_ambos_desligados(self):
        disabled = ps.disabled_telas(_flags())
        assert "OS" in disabled and "OS_COMP" in disabled

    def test_os_e_os_comp_visiveis_se_oficina_ligada(self):
        disabled = ps.disabled_telas(_flags(Oficina=True))
        assert "OS" not in disabled and "OS_COMP" not in disabled

    def test_os_e_os_comp_visiveis_se_assistencia_ligada(self):
        disabled = ps.disabled_telas(_flags(Assistencia=True))
        assert "OS" not in disabled and "OS_COMP" not in disabled

    def test_os_e_os_comp_visiveis_se_ambos_ligados(self):
        disabled = ps.disabled_telas(_flags(Oficina=True, Assistencia=True))
        assert "OS" not in disabled and "OS_COMP" not in disabled


class TestPedidoBarXPedidoCompleto:
    def test_pedido_bar_oculto_se_bar_desligado(self):
        disabled = ps.disabled_telas(_flags())
        assert "PEDIDO" in disabled

    def test_pedido_bar_visivel_se_bar_ligado(self):
        disabled = ps.disabled_telas(_flags(Bar=True))
        assert "PEDIDO" not in disabled

    def test_pedido_completo_oculto_se_pedido_venda_desligado(self):
        disabled = ps.disabled_telas(_flags())
        assert "PEDIDO_COMP" in disabled

    def test_pedido_completo_visivel_se_pedido_venda_ligado(self):
        disabled = ps.disabled_telas(_flags(Pedido_venda=True))
        assert "PEDIDO_COMP" not in disabled


class TestFilterCatalogoRemoveTelasOcultasDaArvore:
    def test_tela_desligada_some_da_arvore_inteira(self):
        # Com tudo desligado, as 4 telas de TRANSACOES (OS/OS_COMP/PEDIDO/
        # PEDIDO_COMP) ficam ocultas — o menu inteiro some (fica sem filhos).
        disabled = ps.disabled_telas(_flags())
        cat = ps.filter_catalogo(disabled)
        assert not any(m["tela"] == "TRANSACOES" for m in cat)

    def test_tela_ligada_aparece_na_arvore(self):
        disabled = ps.disabled_telas(_flags(Bar=True, Oficina=True))
        cat = ps.filter_catalogo(disabled)
        transacoes = next(m for m in cat if m["tela"] == "TRANSACOES")
        telas_visiveis = {t["tela"] for t in transacoes["children"]}
        assert "PEDIDO" in telas_visiveis
        assert "OS" in telas_visiveis

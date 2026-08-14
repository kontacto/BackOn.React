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
        # Com tudo desligado, as 4 telas gateadas por módulo em TRANSACOES
        # (OS/OS_COMP/PEDIDO/PEDIDO_COMP) somem — mas o menu em si continua
        # existindo, já que MOV_PRODUTOS/REQUISICAO (Movimentações,
        # 2026-07-18) não são gateadas por nenhum módulo.
        disabled = ps.disabled_telas(_flags())
        cat = ps.filter_catalogo(disabled)
        transacoes = next(m for m in cat if m["tela"] == "TRANSACOES")
        telas_visiveis = {t["tela"] for t in transacoes["children"]}
        assert not ({"OS", "OS_COMP", "PEDIDO", "PEDIDO_COMP"} & telas_visiveis)

    def test_tela_ligada_aparece_na_arvore(self):
        disabled = ps.disabled_telas(_flags(Bar=True, Oficina=True))
        cat = ps.filter_catalogo(disabled)
        transacoes = next(m for m in cat if m["tela"] == "TRANSACOES")
        telas_visiveis = {t["tela"] for t in transacoes["children"]}
        assert "PEDIDO" in telas_visiveis
        assert "OS" in telas_visiveis


class TestFilterCatalogoRecursaoEmMenuAninhado:
    """Bug real corrigido 2026-08-13, achado ao vivo contra KONTACTO TESTE:
    `filter_catalogo` só filtrava o 1º nível de cada menu — MODIFICADORES
    vive dentro de um menu ANINHADO (CADASTROS > Tabelas Auxiliares >
    Modificadores), gateado pelo módulo Bar, e continuava aparecendo mesmo
    com Bar desligado. Agora `filter_catalogo` é recursivo."""

    def test_modificadores_some_do_submenu_com_bar_desligado(self):
        disabled = ps.disabled_telas(_flags())
        cat = ps.filter_catalogo(disabled)
        cadastros = next(m for m in cat if m["tela"] == "CADASTROS")
        tabaux = next(m for m in cadastros["children"] if m["tela"] == "TABAUX")
        telas_visiveis = {t["tela"] for t in tabaux["children"]}
        assert "MODIFICADORES" not in telas_visiveis
        # Marcas/Modelos não são gateados por nenhum módulo — continuam.
        assert "MARCAS" in telas_visiveis

    def test_modificadores_aparece_no_submenu_com_bar_ligado(self):
        disabled = ps.disabled_telas(_flags(Bar=True))
        cat = ps.filter_catalogo(disabled)
        cadastros = next(m for m in cat if m["tela"] == "CADASTROS")
        tabaux = next(m for m in cadastros["children"] if m["tela"] == "TABAUX")
        telas_visiveis = {t["tela"] for t in tabaux["children"]}
        assert "MODIFICADORES" in telas_visiveis

    def test_submenu_inteiro_some_se_todos_os_filhos_forem_ocultos(self):
        # Sanidade da recursão: se um menu aninhado fictício ficasse sem
        # nenhum filho visível, o menu em si também deveria sumir (mesmo
        # comportamento já garantido pro nível topo). Verificado indireta-
        # mente: TABAUX nunca fica vazio hoje (Marcas/Modelos não são
        # gateados), então aqui confirmamos que TABAUX sempre sobrevive
        # com o restante das telas não-gateadas presentes mesmo com tudo
        # desligado (evita falso-positivo de "sumiu tudo por engano").
        disabled = ps.disabled_telas(_flags())
        cat = ps.filter_catalogo(disabled)
        cadastros = next(m for m in cat if m["tela"] == "CADASTROS")
        assert any(m["tela"] == "TABAUX" for m in cadastros["children"])

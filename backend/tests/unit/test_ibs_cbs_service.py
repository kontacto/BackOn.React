"""Testes unitários do motor IBS/CBS (`ibs_cbs_service.py`) — porte de
`CalculaIBSCBS` (`Geral\\mdl_proc.bas:36433-36985`). Casos por grupo
(normal sem monofásico, cada um dos 4 grupos monofásico isolado,
diferimento, redução com/sem alíquota efetiva > 0), valores batendo com
contas manuais replicando a fórmula do VB6 — ver docstring do módulo."""
from lxml import etree

import services.ibs_cbs_service as svc


class FakeCursor:
    """Cursor mínimo pra testar `resolver_taxa_nfce_para_ibs_cbs_sync` —
    só precisa registrar a query executada e devolver um `fetchone` fixo."""
    def __init__(self, row=None):
        self._row = row
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._row


class TestResolverTaxaNfceParaIbsCbsSync:
    def test_query_filtra_por_cod_icms_destino_e_tipo_mov(self):
        # Achado 2026-08-19 (mdl_proc.bas:36446-36447 + confirmação direta
        # do usuário): a fonte resolve IBS/CBS de PRODUTO e SERVIÇO num
        # join que, no SQL literal do VB6, só filtra por `cod_icms` — mas
        # `taxas_nfce` tem uma chave de 4 campos (destino+cfop+cod_icms+
        # tipo_mov), então isso seria ambíguo em instalações com mais de
        # uma linha por cod_icms. O usuário confirmou que os outros 2
        # campos são CONSTANTES neste contexto (tipo_mov sempre "S01" —
        # NFC-e só existe pra VENDA — e destino sempre a UF da própria
        # empresa, nunca a do cliente) — por isso entram como filtro
        # explícito aqui, não inventados.
        cur = FakeCursor(row={"CST_IBS": "000"})
        r = svc.resolver_taxa_nfce_para_ibs_cbs_sync(cur, cod_icms="00", destino="RJ")
        assert r == {"CST_IBS": "000"}
        query, params = cur.queries[0]
        assert "taxas_nfce" in query
        assert "cod_icms = %s" in query
        assert "destino = %s" in query
        assert "tipo_mov = %s" in query
        assert params == ("00", "RJ", "S01")
        # Nenhum filtro da cascata antiga (protocolo_st/simples_nacional/
        # consumidor_final) — só os 3 campos confirmados como constantes.
        for termo_proibido in ("protocolo_st", "simples_nacional", "consumidor_final"):
            assert termo_proibido not in query.lower()

    def test_tipo_mov_default_e_s01_mas_pode_ser_sobrescrito(self):
        cur = FakeCursor(row=None)
        svc.resolver_taxa_nfce_para_ibs_cbs_sync(cur, cod_icms="00", destino="SP", tipo_mov="S02")
        assert cur.queries[0][1] == ("00", "SP", "S02")

    def test_sem_linha_correspondente_devolve_none(self):
        cur = FakeCursor(row=None)
        assert svc.resolver_taxa_nfce_para_ibs_cbs_sync(cur, cod_icms="99", destino="RJ") is None


def _taxa_base(**overrides) -> dict:
    taxa = {
        "INFORMA_CBS_IBS": 1,
        "CST_IBS": "000", "CCLASSTRIB_IBS": "000001",
        "ALQT_IBS_ESTADO": 8.0, "PERC_DIFERIMENTO_IBS_ESTADO": 0, "PERC_REDUCAO_IBS_ESTADO": 0,
        "ALQT_EFETIVA_REDUCAO_IBS_ESTADO": 0,
        "ALQT_IBS_MUNICIPIO": 2.0, "PERC_DIFERIMENTO_IBS_MUNICIPIO": 0, "PERC_REDUCAO_IBS_MUNICIPIO": 0,
        "ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO": 0,
        "ALQT_CBS_ESTADO": 0.9, "PERC_DIFERIMENTO_CBS_ESTADO": 0, "PERC_REDUCAO_CBS_ESTADO": 0,
        "ALQT_EFETIVA_REDUCAO_CBS_ESTADO": 0,
        "GTRIBREGULAR": 0,
        "gMonoPadrao": 0, "gMonoReten": 0, "gMonoRet": 0, "gMonoDif": 0,
    }
    taxa.update(overrides)
    return taxa


class TestSkipSemibs:
    def test_sem_informa_cbs_ibs_e_cst_comum_pula_item(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base(INFORMA_CBS_IBS=0))
        assert r is None

    def test_sem_informa_cbs_ibs_mas_cst_400_processa(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base(INFORMA_CBS_IBS=0, CST_IBS="400"))
        assert r is not None

    def test_sem_informa_cbs_ibs_mas_cst_410_processa(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base(INFORMA_CBS_IBS=0, CST_IBS="410"))
        assert r is not None

    def test_com_informa_cbs_ibs_processa_qualquer_cst(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base(INFORMA_CBS_IBS=1, CST_IBS="000"))
        assert r is not None


class TestCalculoNormalSemMonofasico:
    def test_valores_base_batem_com_conta_manual(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base())
        assert r["base_ibs_uf"] == 100.0
        assert r["valor_ibs_uf"] == 8.0  # 100 * 8% / 100
        assert r["valor_ibs_municipio"] == 2.0  # 100 * 2% / 100
        assert r["valor_cbs"] == 0.9  # 100 * 0.9% / 100
        assert r["mono"] == {}
        assert r["eh_400_410_ou_mono"] is False
        assert r["contribui_totais"] is True

    def test_qtd_e_p_unit_multiplicam_a_base(self):
        r = svc.calcular_item_ibs_cbs(qtd=3, p_unit=10, codigo_int="P001", taxa=_taxa_base())
        assert r["base_ibs_uf"] == 30.0
        assert r["valor_ibs_uf"] == 2.4  # 30 * 8% / 100

    def test_item_de_servico_nao_contribui_totais_mas_calcula_campos(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="S001", taxa=_taxa_base())
        assert r["contribui_totais"] is False
        assert r["valor_ibs_uf"] == 8.0  # campo calculado mesmo assim (pro DPS ler CST/cClassTrib)
        assert r["xml_item"] == ""  # NFCe não usa — só produto gera fragmento de XML


class TestReducaoComAlicotaEfetiva:
    def test_usa_alicota_efetiva_quando_maior_que_zero(self):
        taxa = _taxa_base(PERC_REDUCAO_IBS_ESTADO=60, ALQT_EFETIVA_REDUCAO_IBS_ESTADO=3.2)
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=taxa)
        assert r["valor_ibs_uf"] == 3.2  # usa a efetiva (3.2), não a cheia (8.0)
        assert r["perc_reducao_ibs_uf"] == 60

    def test_sem_alicota_efetiva_usa_alicota_cheia(self):
        taxa = _taxa_base(PERC_REDUCAO_IBS_ESTADO=60, ALQT_EFETIVA_REDUCAO_IBS_ESTADO=0)
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=taxa)
        assert r["valor_ibs_uf"] == 8.0  # cai pra alíquota cheia


class TestDiferimento:
    def test_valor_diferimento_calculado_a_parte_do_valor_ibs(self):
        taxa = _taxa_base(PERC_DIFERIMENTO_IBS_ESTADO=50)
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=taxa)
        assert r["valor_dif_ibs_uf"] == 50.0  # 100 * 50% / 100
        assert r["valor_ibs_uf"] == 8.0  # não afetado pelo diferimento (campo separado)


class TestGruposMonofasicos:
    def test_gmono_padrao_isolado(self):
        taxa = _taxa_base(gMonoPadrao=1, ALQT_ADREM_PADRAO_IBS=0.05, ALQT_ADREM_PADRAO_CBS=0.03)
        r = svc.calcular_item_ibs_cbs(qtd=10, p_unit=5, codigo_int="P001", taxa=taxa)
        assert set(r["mono"].keys()) == {"padrao"}
        m = r["mono"]["padrao"]
        assert m["base"] == 10.0  # BASE_ADREM_MONO = qtd (não qtd*p_unit)
        assert m["valor_ibs"] == 0.5  # 10 * 0.05
        assert m["valor_cbs"] == 0.3  # 10 * 0.03
        assert r["eh_400_410_ou_mono"] is True

    def test_gmono_reten_isolado(self):
        taxa = _taxa_base(gMonoReten=1, ALQT_ADREM_RETENCAO_IBS=0.02, ALQT_ADREM_RETENCAO_CBS=0.01)
        r = svc.calcular_item_ibs_cbs(qtd=10, p_unit=5, codigo_int="P001", taxa=taxa)
        assert set(r["mono"].keys()) == {"retencao"}
        m = r["mono"]["retencao"]
        assert m["base"] == 10.0
        assert m["valor_ibs"] == 0.2
        assert m["valor_cbs"] == 0.1

    def test_gmono_ret_isolado(self):
        taxa = _taxa_base(gMonoRet=1, ALQT_ADREM_RETIDO_IBS=0.04, ALQT_ADREM_RETIDO_CBS=0.02)
        r = svc.calcular_item_ibs_cbs(qtd=10, p_unit=5, codigo_int="P001", taxa=taxa)
        assert set(r["mono"].keys()) == {"retido"}
        m = r["mono"]["retido"]
        assert m["base"] == 10.0
        assert m["valor_ibs"] == 0.4
        assert m["valor_cbs"] == 0.2

    def test_gmono_dif_isolado_usa_base_qtd_x_p_unit_e_corrige_typo_da_fonte(self):
        # ALQT_ADREM_DIFERIMENTO_IBS (nome correto, não o typo "_UBS" da
        # fonte VB6) — ver docstring do módulo, correção #1.
        taxa = _taxa_base(gMonoDif=1, ALQT_ADREM_DIFERIMENTO_IBS=10, ALQT_ADREM_DIFERIMENTO_CBS=5)
        r = svc.calcular_item_ibs_cbs(qtd=2, p_unit=50, codigo_int="P001", taxa=taxa)
        assert set(r["mono"].keys()) == {"diferimento"}
        m = r["mono"]["diferimento"]
        assert m["base"] == 100.0  # qtd * p_unit (não só qtd, diferente dos outros 3 grupos)
        assert m["valor_ibs"] == 10.0  # 100 * 10% / 100
        assert m["valor_cbs"] == 5.0  # 100 * 5% / 100

    def test_v_tot_ibs_cbs_mono_item_combina_padrao_reten_e_diferimento(self):
        taxa = _taxa_base(
            gMonoPadrao=1, ALQT_ADREM_PADRAO_IBS=1.0, ALQT_ADREM_PADRAO_CBS=0.5,
            gMonoReten=1, ALQT_ADREM_RETENCAO_IBS=0.3, ALQT_ADREM_RETENCAO_CBS=0.2,
            gMonoDif=1, ALQT_ADREM_DIFERIMENTO_IBS=2, ALQT_ADREM_DIFERIMENTO_CBS=1,
        )
        r = svc.calcular_item_ibs_cbs(qtd=10, p_unit=5, codigo_int="P001", taxa=taxa)
        # mono_ibs=10*1.0=10, retencao_ibs=10*0.3=3, diferimento_ibs=50*2%=1 -> 10+3-1=12
        assert r["v_tot_ibs_mono_item"] == 12.0
        # mono_cbs=10*0.5=5, retencao_cbs=10*0.2=2, diferimento_cbs=50*1%=0.5 -> 5+2-0.5=6.5
        assert r["v_tot_cbs_mono_item"] == 6.5


class TestGTribRegular:
    def test_flag_desligado_nao_gera_bloco(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base(GTRIBREGULAR=0))
        assert "<gTribRegular>" not in r["xml_item"]

    def test_flag_ligado_gera_bloco_com_aliquota_efetiva_do_estado_decidindo_ambas(self):
        # ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO propositalmente DIFERENTE de
        # ALQT_IBS_MUNICIPIO (2.0), pra provar que é a condição do ESTADO
        # (>0) que decide usar a efetiva do MUNICÍPIO também — achado
        # não-óbvio confirmado na fonte, replicado tal qual.
        taxa = _taxa_base(
            GTRIBREGULAR=1, PERC_REDUCAO_IBS_ESTADO=50, ALQT_EFETIVA_REDUCAO_IBS_ESTADO=4.0,
            ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO=1.1,
        )
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=taxa)
        xml = r["xml_item"]
        assert "<gTribRegular>" in xml
        assert "<pAliqEfetRegIBSUF>4.0000</pAliqEfetRegIBSUF>" in xml
        # usa a efetiva do MUNICÍPIO (1.1), não a cheia (2.0), porque a
        # condição do ESTADO (>0) já foi satisfeita.
        assert "<pAliqEfetRegIBSMun>1.1000</pAliqEfetRegIBSMun>" in xml


class TestMontarXmlItem:
    def test_xml_bem_formado_e_contem_gibscbs_quando_nao_especial(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base())
        xml = f"<raiz>{r['xml_item']}</raiz>"
        etree.fromstring(xml.encode("utf-8"))  # não lança se bem-formado
        assert "<gIBSCBS>" in r["xml_item"]
        assert "<vIBSUF>8.00</vIBSUF>" in r["xml_item"]

    def test_gibscbs_omitido_quando_cst_400(self):
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base(CST_IBS="400"))
        assert "<gIBSCBS>" not in r["xml_item"]
        assert "<CST>400</CST>" in r["xml_item"]

    def test_tag_pAliqEfet_do_gibsmun_fecha_corretamente_corrigindo_bug_da_fonte(self):
        # mdl_proc.bas:36651 fecha com "/<pAliqEfet>" (malformado) — aqui
        # deve sair sempre bem-formado ("</pAliqEfet>").
        taxa = _taxa_base(PERC_REDUCAO_IBS_MUNICIPIO=30, ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO=1.5)
        r = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=taxa)
        assert "/<pAliqEfet>" not in r["xml_item"]
        etree.fromstring(f"<raiz>{r['xml_item']}</raiz>".encode("utf-8"))

    def test_gibscbsmono_presente_quando_algum_grupo_mono_ligado(self):
        taxa = _taxa_base(gMonoPadrao=1, ALQT_ADREM_PADRAO_IBS=0.1, ALQT_ADREM_PADRAO_CBS=0.05)
        r = svc.calcular_item_ibs_cbs(qtd=10, p_unit=5, codigo_int="P001", taxa=taxa)
        assert "<gIBSCBSMono>" in r["xml_item"]
        assert "<gMonoPadrao>" in r["xml_item"]
        etree.fromstring(f"<raiz>{r['xml_item']}</raiz>".encode("utf-8"))

    def test_gmonodif_sai_vazio_replicando_a_fonte(self):
        taxa = _taxa_base(gMonoDif=1, ALQT_ADREM_DIFERIMENTO_IBS=10, ALQT_ADREM_DIFERIMENTO_CBS=5)
        r = svc.calcular_item_ibs_cbs(qtd=2, p_unit=50, codigo_int="P001", taxa=taxa)
        assert "<gMonoDif></gMonoDif>" in r["xml_item"]


class TestCalcularTotaisIbsCbs:
    def test_lista_vazia_nao_gera_xml(self):
        tot = svc.calcular_totais_ibs_cbs([])
        assert tot["xml_totais"] == ""
        assert tot["tot_ibs_uf"] == 0.0

    def test_itens_none_sao_ignorados_como_skip(self):
        tot = svc.calcular_totais_ibs_cbs([None, None])
        assert tot["xml_totais"] == ""

    def test_soma_apenas_itens_que_contribuem_totais(self):
        produto = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base())
        servico = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="S001", taxa=_taxa_base())
        tot = svc.calcular_totais_ibs_cbs([produto, servico])
        # só o produto contribui — se o serviço também contribuísse, seria 16.0
        assert tot["tot_ibs_uf"] == 8.0
        assert tot["tot_ibs_mun"] == 2.0
        assert tot["tot_cbs"] == 0.9
        assert tot["tot_base_ibs_cbs"] == 100.0
        assert "<IBSCBSTot>" in tot["xml_totais"]
        assert "<vIBSUF>8.00</vIBSUF>" in tot["xml_totais"]

    def test_base_nao_soma_quando_item_e_400_410_ou_mono(self):
        item = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base(CST_IBS="400"))
        tot = svc.calcular_totais_ibs_cbs([item])
        assert tot["tot_base_ibs_cbs"] == 0.0
        # mas ainda gera XML de totais, porque teve_algo (TEVECBS) fica True
        assert tot["xml_totais"] != ""

    def test_gmono_no_xml_totais_so_aparece_com_algum_total_mono_positivo(self):
        item_normal = svc.calcular_item_ibs_cbs(qtd=1, p_unit=100, codigo_int="P001", taxa=_taxa_base())
        tot_sem_mono = svc.calcular_totais_ibs_cbs([item_normal])
        assert "<gMono>" not in tot_sem_mono["xml_totais"]

        item_mono = svc.calcular_item_ibs_cbs(
            qtd=10, p_unit=5, codigo_int="P002",
            taxa=_taxa_base(gMonoPadrao=1, ALQT_ADREM_PADRAO_IBS=0.1, ALQT_ADREM_PADRAO_CBS=0.05),
        )
        tot_com_mono = svc.calcular_totais_ibs_cbs([item_mono])
        assert "<gMono>" in tot_com_mono["xml_totais"]
        assert "<vIBSMono>1.00</vIBSMono>" in tot_com_mono["xml_totais"]

    def test_xml_totais_bem_formado(self):
        item = svc.calcular_item_ibs_cbs(
            qtd=10, p_unit=5, codigo_int="P001",
            taxa=_taxa_base(gMonoPadrao=1, ALQT_ADREM_PADRAO_IBS=0.1, ALQT_ADREM_PADRAO_CBS=0.05),
        )
        tot = svc.calcular_totais_ibs_cbs([item])
        etree.fromstring(f"<raiz>{tot['xml_totais']}</raiz>".encode("utf-8"))

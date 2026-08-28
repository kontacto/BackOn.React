"""Testes unitários do Motor de Regras Fiscais — grupo ICMSUFDest (DIFAL)
+ validações de consistência (ver services/nfe_regras_fiscais.py pro
rastreio completo: NT 2015.003 + XSD oficial, achado 2026-08-28 — a
rejeição 695 real reportada pelo usuário e a descoberta de que o grupo
nunca era construído no motor Python)."""
import services.nfe_regras_fiscais as svc


def _item(**over):
    base = {
        "codigo_int": "P001", "valor_total": 1000.0, "csosn": "102",
        "aliquota_interestadual": 12, "aliquota_interna_destino": 18,
        "percentual_origem": 0, "fundo_pobreza": 0,
    }
    base.update(over)
    return base


class TestGrupoIcmsUfDestAplicavel:
    def test_aplicavel_quando_3_condicoes_batem(self):
        assert svc.grupo_icms_uf_dest_aplicavel("2", "1", "9") is True

    def test_nao_aplicavel_operacao_interna(self):
        assert svc.grupo_icms_uf_dest_aplicavel("1", "1", "9") is False

    def test_nao_aplicavel_nao_consumidor_final(self):
        assert svc.grupo_icms_uf_dest_aplicavel("2", "0", "9") is False

    def test_nao_aplicavel_contribuinte(self):
        """Cenário EXATO do print real (rejeição 695): Consumidor Final
        marcado, mas o destinatário É contribuinte (indIEDest='1', não
        '9') — o grupo tem que ficar ausente, mesmo com a operação sendo
        interestadual e consumidor final."""
        assert svc.grupo_icms_uf_dest_aplicavel("2", "1", "1") is False


class TestMontarGrupoIcmsUfDestItem:
    def test_grupo_vazio_fora_das_3_condicoes(self):
        r = svc.montar_grupo_icms_uf_dest_item("2", "1", "1", _item())
        assert r["xml"] == ""
        assert r["v_icms_uf_dest"] == 0.0
        assert r["v_icms_uf_remet"] == 0.0

    def test_formula_bate_com_partilha_100_destino(self):
        """v_bc=1000, pICMSUFDest=18, pICMSInter=12, percentual_origem=0
        (→ pICMSInterPart=100, partilha atual desde 2019) — cálculo à mão:
        diferenca=6; vICMSUFDest = 1000*0.06*1 = 60.00; vICMSUFRemet = 0
        (partilha 100% destino)."""
        r = svc.montar_grupo_icms_uf_dest_item("2", "1", "9", _item())
        assert r["v_icms_uf_dest"] == 60.0
        assert r["v_icms_uf_remet"] == 0.0
        assert "<ICMSUFDest>" in r["xml"]
        assert "<vBCUFDest>1000.00</vBCUFDest>" in r["xml"]
        assert "<pICMSUFDest>18.00</pICMSUFDest>" in r["xml"]
        assert "<pICMSInter>12.00</pICMSInter>" in r["xml"]
        assert "<pICMSInterPart>100.00</pICMSInterPart>" in r["xml"]
        assert "<vICMSUFDest>60.00</vICMSUFDest>" in r["xml"]
        assert "<vICMSUFRemet>0.00</vICMSUFRemet>" in r["xml"]
        # Ordem confirmada no XSD oficial: vBCUFDest, (FCP opcional),
        # pICMSUFDest, pICMSInter, pICMSInterPart, (vFCPUFDest opcional),
        # vICMSUFDest, vICMSUFRemet — sem FCP aqui (fundo_pobreza=0).
        assert "vBCFCPUFDest" not in r["xml"]
        assert "pFCPUFDest" not in r["xml"]

    def test_formula_com_partilha_parcial_gera_valor_remet(self):
        """percentual_origem=40 (cenário histórico, ex. 2017) →
        pICMSInterPart=60: vICMSUFDest=1000*0.06*0.6=36.00,
        vICMSUFRemet=1000*0.06*0.4=24.00."""
        r = svc.montar_grupo_icms_uf_dest_item("2", "1", "9", _item(percentual_origem=40))
        assert r["v_icms_uf_dest"] == 36.0
        assert r["v_icms_uf_remet"] == 24.0

    def test_diferenca_negativa_zera_os_2_valores(self):
        """pICMSUFDest < pICMSInter (destino com alíquota interna menor
        que a interestadual, caso raro mas previsto na NT: "Se
        (pICMSUFDest - pICMSInter) <= 0: Considerar valor=0")."""
        r = svc.montar_grupo_icms_uf_dest_item("2", "1", "9", _item(aliquota_interna_destino=10, aliquota_interestadual=12))
        assert r["v_icms_uf_dest"] == 0.0
        assert r["v_icms_uf_remet"] == 0.0

    def test_fcp_incluido_quando_fundo_pobreza_maior_que_zero(self):
        r = svc.montar_grupo_icms_uf_dest_item("2", "1", "9", _item(fundo_pobreza=2))
        assert r["v_fcp_uf_dest"] == 20.0  # 1000 * 2/100
        assert "<vBCFCPUFDest>1000.00</vBCFCPUFDest>" in r["xml"]
        assert "<pFCPUFDest>2.00</pFCPUFDest>" in r["xml"]
        assert "<vFCPUFDest>20.00</vFCPUFDest>" in r["xml"]
        # Ordem: vBCUFDest, vBCFCPUFDest, pFCPUFDest, pICMSUFDest, ...
        assert r["xml"].index("vBCFCPUFDest") < r["xml"].index("pICMSUFDest")


class TestMontarTotaisIcmsUfDestXml:
    def test_omite_tudo_quando_zerado(self):
        assert svc.montar_totais_icms_uf_dest_xml(0.0, 0.0, 0.0) == ""

    def test_inclui_totais_quando_ha_difal(self):
        xml = svc.montar_totais_icms_uf_dest_xml(60.0, 0.0, 20.0)
        assert "<vFCPUFDest>20.00</vFCPUFDest>" in xml
        assert "<vICMSUFDest>60.00</vICMSUFDest>" in xml
        assert "<vICMSUFRemet>0.00</vICMSUFRemet>" in xml
        # Ordem confirmada no XSD (TICMSTot): vFCPUFDest antes de vICMSUFDest/vICMSUFRemet.
        assert xml.index("vFCPUFDest") < xml.index("vICMSUFDest")


class TestValidarRegrasFiscais:
    def test_passa_quando_fora_das_3_condicoes(self):
        contexto = svc.montar_contexto_validacao("1", "1", "1", [_item()])
        assert svc.validar_regras_fiscais(contexto) is None

    def test_bloqueia_taxa_sem_aliquota_difal(self):
        contexto = svc.montar_contexto_validacao("2", "1", "9", [_item(aliquota_interna_destino=0)])
        r = svc.validar_regras_fiscais(contexto)
        assert r is not None and r["success"] is False
        assert "Taxa" in r["message"] and "P001" in r["message"]

    def test_passa_quando_taxa_configurada_certo(self):
        contexto = svc.montar_contexto_validacao("2", "1", "9", [_item()])
        assert svc.validar_regras_fiscais(contexto) is None

    def test_bloqueia_csosn_incompativel_com_consumidor_final(self):
        contexto = svc.montar_contexto_validacao("2", "1", "9", [_item(csosn="900")])
        r = svc.validar_regras_fiscais(contexto)
        assert r is not None and r["success"] is False
        assert "CSOSN 900" in r["message"]

    def test_csosn_incompativel_nao_bloqueia_fora_das_3_condicoes(self):
        """Mesmo CSOSN "proibido", mas operação NÃO é interestadual —
        regra N12a-70 só vale nas 3 condições da NT 2015.003."""
        contexto = svc.montar_contexto_validacao("1", "1", "9", [_item(csosn="900")])
        assert svc.validar_regras_fiscais(contexto) is None

    def test_devolve_primeira_falha_nao_a_lista_inteira(self):
        # Item sem alíquota DIFAL E com CSOSN incompatível — a regra 1
        # (Taxa sem alíquota) é checada primeiro na lista registrada.
        contexto = svc.montar_contexto_validacao("2", "1", "9", [_item(aliquota_interna_destino=0, csosn="900")])
        r = svc.validar_regras_fiscais(contexto)
        assert "Taxa" in r["message"]

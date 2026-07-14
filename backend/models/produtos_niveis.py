"""Modelos da tela "Alterações Cadastro de Produtos Níveis" — alteração em
massa de pecas/servicos filtrando por faixa de NCM (pecas.codigo_mercosul /
servicos.codigo_mercosul) ou por nível (grupo mercadológico, tabela `niveis`).
Legado VB6: FrmAltNiv."""
from typing import Literal, Optional

from pydantic import BaseModel


class FiltroBase(BaseModel):
    servidor: str
    banco: str
    modo_filtro: Literal["nivel", "ncm"]
    # modo "nivel"
    nivel_cod_nivel: Optional[int] = None
    nivel_incluir_inferiores: bool = False
    # modo "ncm"
    ncm_de: Optional[str] = None
    ncm_ate: Optional[str] = None
    incluir_pecas: bool = True
    incluir_servicos: bool = True
    classe: Optional[int] = None    # grupo do usuário (para validar permissão)
    master: Optional[bool] = False  # KONTACTO/master ignora checagem de permissão
    usuario_alteracao: Optional[int] = None  # funcionarios.codigo_int — também usado no log de auditoria
    plataforma: Optional[str] = None         # "web"/"android"/"ios" — só para o log de auditoria


class PreviewRequest(FiltroBase):
    pass


class GravarCamposRequest(FiltroBase):
    confirmar: bool = False

    # Tributação
    cst_pis: Optional[str] = None
    perc_valor_pis: Optional[float] = None
    cst_cofins: Optional[str] = None
    perc_valor_cofins: Optional[float] = None
    cod_icms: Optional[str] = None
    perc_mva: Optional[float] = None            # só pecas
    outros_trib_federais: Optional[float] = None  # só pecas

    # Descontos
    desc_g: Optional[float] = None
    desc_s: Optional[float] = None
    desc_v: Optional[float] = None

    # Comissões — Vendedor
    comissao: Optional[float] = None
    valor_comissao: Optional[float] = None
    valor_desc_base_comissao: Optional[float] = None
    # Comissões — Executor
    comissao_e: Optional[float] = None
    valor_comissao_e: Optional[float] = None
    valor_desc_base_comissao_e: Optional[float] = None
    # Comissões — Atendente
    comissao_a: Optional[float] = None
    valor_comissao_a: Optional[float] = None
    valor_desc_base_comissao_a: Optional[float] = None

    paga_comissao: Optional[bool] = None      # invertido na gravação (Sim->0, Não->1)
    aceita_desconto: Optional[bool] = None    # idem

    # Garantia
    tipo_garantia: Optional[int] = None
    prazo_garantia: Optional[int] = None

    # Margem/Preço — só pecas
    margem_lucro: Optional[float] = None
    margem_tabela: Optional[float] = None

    # Estoque/Origem/Finalidade — só pecas
    estoque_minimo: Optional[float] = None
    origem: Optional[str] = None
    tipo_peca: Optional[int] = None
    politica_preco: Optional[str] = None      # grava só a 1ª letra maiúscula
    preco_variado: Optional[bool] = None

    situacao: Optional[str] = None

    uf_protocolo_st: Optional[str] = None     # insert-only em pecas_protocolo_st


class ReajustePrecoRequest(FiltroBase):
    percentual: float
    alterar_preco_tabela: bool = False
    pelo_custo_reposicao: bool = False
    arredondar: bool = False
    confirmar: bool = False


class LeiTransparenciaRequest(FiltroBase):
    percentual: float
    confirmar: bool = False


class DesativarEstoqueRequest(FiltroBase):
    confirmar: bool = False


class ReprocessarItemRequest(BaseModel):
    servidor: str
    banco: str
    busca: str
    classe: Optional[int] = None
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


class ReprocessarReservadosRequest(BaseModel):
    servidor: str
    banco: str
    classe: Optional[int] = None
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None

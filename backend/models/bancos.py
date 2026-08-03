"""Financeiro > Cobranças (cadastro de Bancos) — Fase 1 (cadastro), ver
PENDENCIAS.md > "Bancos (Cadastro de Cobrança / Boleto / CNAB)". Legado:
`FrmManBan.frm` ("Manutenção de Bancos para Cobrança"). Tabela `bancos`
(plural) já existe no banco de dados, usada pelos clientes que ainda rodam
o VB6 — não confundir com `banco` (singular), tabela de outro domínio, em
desuso.

Dois modos de integração coexistem por registro, decididos pelo campo
`integracao_api`: desligado usa o fluxo CNAB tradicional (arquivo de
remessa/retorno); ligado usa credenciais de API (`chave_api_1..4`). Nenhum
motor de emissão (CNAB ou API) foi implementado ainda nesta fase — só o
cadastro."""
from typing import List, Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class BancoSaveRequest(AuditFields):
    servidor: str
    banco: str
    cod: Optional[int] = None  # None = novo registro

    # Identificação bancária
    codigo: int = 0  # Código do banco (padrão Febraban)
    digito_banco: int = 0
    descricao: str = ""
    descr_arquivo: str = ""
    agencia: int = 0
    dv_agencia: str = ""
    conta_corrente: int = 0
    dv_conta_corrente: str = ""
    dv_agencia_conta: str = ""
    situacao: str = "A"  # A=Ativo / I=Inativo

    # Cobrança
    carteira: int = 0
    variacao_carteira: int = 0
    codigo_cedente: str = ""
    cod_transmissao: str = ""
    contrato: float = 0
    especie_doc: int = 0
    aceite: str = "N"

    # Multa / Mora / Protesto / Baixa
    tarifa_cobranca: float = 0
    incidencia_multa: int = 0
    dias_multa: int = 0
    tipo_multa: int = 0
    multa_atraso_pag: float = 0
    mora_dia_pag: float = 0
    dias_protesto: int = 0
    codigo_protesto: int = 0
    dias_baixa: int = 0
    codigo_baixa: int = 0

    # Boleto
    tipo_cobranca: int = 0
    tipo_registro: int = 0
    emissao_boleto: int = 0
    distribui_boleto: int = 0
    numero_boleto: float = 0
    instr_cobranca_1: int = 0
    instr_cobranca_2: int = 0
    titulo_boleto: str = ""
    mensagem_boleto_1: str = ""
    mensagem_boleto_2: str = ""
    mensagem_boleto_3: str = ""

    # CNAB (arquivo) — só usados quando integracao_api = False
    endereco_remessa: str = ""
    endereco_retorno: str = ""

    # Integração por API — só usados quando integracao_api = True
    integracao_api: bool = False
    chave_api_1: str = ""
    chave_api_2: str = ""
    chave_api_3: str = ""
    chave_api_4: str = ""


class BancoDeleteRequest(AuditFields):
    servidor: str
    banco: str
    cod: int


class GerarRemessaRequest(AuditFields):
    servidor: str
    banco: str
    # Subconjunto de `duplicata_rec_venc.codigo` selecionado pelo usuário na
    # grade de "Geração de Boletos" (aba Geração/Envio) — None ou lista
    # vazia mantém o comportamento antigo (TODOS os títulos pendentes do
    # banco entram na remessa).
    titulos: Optional[List[int]] = None


class ProcessarRetornoRequest(AuditFields):
    servidor: str
    banco: str
    conteudo: str  # texto bruto do arquivo de retorno (CNAB400), colado/enviado pelo usuário


class PreviewRetornoRequest(BaseModel):
    servidor: str
    banco: str
    conteudo: str  # texto bruto do arquivo de retorno, só leitura — não grava nada


class AplicarBaixasRequest(AuditFields):
    servidor: str
    banco: str
    itens: List[dict]  # subconjunto de `itens_baixa` devolvido pelo preview, selecionado pelo usuário
    conta: Optional[int] = None  # conta de caixa/banco que recebe o crédito (Baixa_Titulo, FrmImpRetBan.frm)

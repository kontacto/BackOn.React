"""Tabelas de referência fiscal NACIONAIS — códigos fixos, definidos por
legislação/ato normativo federal, os mesmos em qualquer instalação deste
sistema (diferente de `classtrib`, que é uma tabela de BANCO já existente
neste projeto, ou de `Tributacao`, que é uma tabela auxiliar digitada por
cada cliente). Constantes Python puras, sem tabela/migração — mesma
categoria de `IBGE_POR_UF`/`UFS_SVRS` em `nfe_fiscal_common.py`.

Criadas 2026-08-22 pra alimentar o recurso "Sugerir com IA" (Descomplicar
Taxas, Apoio Fiscal/"João") — o enum de saída estruturada da IA é
restringido a estes valores, nunca inventado (CLAUDE.md > "Papel Kelvin",
regra de nunca inventar CST/CFOP/alíquota).

**Fontes pesquisadas nesta sessão, cross-checadas entre 2+ referências
especializadas independentes (Datacaixa, idealsoftwares, CDM
Contabilidade) + confirmação ao vivo de que a página do CONFAZ trata do
Ajuste citado — mas o PDF PRIMÁRIO do Ajuste SINIEF/SPED não foi
carregado direto nesta sessão (erro de redirecionamento no fetch).**
Recomenda-se validar este conteúdo contra o texto primário (CONFAZ/SPED)
antes de liberar o recurso de sugestão por IA pra uso em produção real —
ver PENDENCIAS.md > "Descomplicar Taxas".

- `CST_ICMS`: Ajuste SINIEF 07/2005, Anexo, Tabela B ("Tributação pelo
  ICMS") — regime normal (CRT=3).
- `CSOSN`: Ajuste SINIEF 3/10 (CONFAZ) — Simples Nacional (CRT=1/2).
- `CST_PIS_COFINS`: Tabela 4.3.3 (CST-PIS) / 4.3.4 (CST-COFINS) do leiaute
  do SPED, Receita Federal (sped.rfb.gov.br) — mesmo código serve pra PIS
  e COFINS (as duas tabelas são idênticas na prática, só o nome muda).
"""

CST_ICMS: dict[str, str] = {
    "00": "Tributada integralmente",
    "10": "Tributada com ICMS devido por substituição tributária, relativo às operações e prestações subsequentes",
    "20": "Tributada com redução de base de cálculo",
    "30": "Isenta ou não tributada com ICMS devido por substituição tributária",
    "40": "Isenta",
    "41": "Não tributada",
    "50": "Suspensão",
    "51": "Diferimento",
    "60": "ICMS cobrado anteriormente por substituição tributária ou por antecipação com encerramento",
    "70": "Tributada com redução de base de cálculo e com ICMS devido por substituição tributária",
    "90": "Outras",
}

CSOSN: dict[str, str] = {
    "101": "Tributada pelo Simples Nacional com permissão de crédito",
    "102": "Tributada pelo Simples Nacional sem permissão de crédito",
    "103": "Isenção do ICMS no Simples Nacional para faixa de receita bruta",
    "201": "Tributada pelo Simples Nacional com permissão de crédito e com cobrança do ICMS por substituição tributária",
    "202": "Tributada pelo Simples Nacional sem permissão de crédito e com cobrança do ICMS por substituição tributária",
    "203": "Isenção do ICMS no Simples Nacional para faixa de receita bruta e com cobrança do ICMS por substituição tributária",
    "300": "Imune",
    "400": "Não tributada pelo Simples Nacional",
    "500": "ICMS cobrado anteriormente por substituição tributária (substituído) ou por antecipação",
    "900": "Outros",
}

# Códigos 01-09: operações de SAÍDA. 49-67: operações de AQUISIÇÃO/ENTRADA
# com direito a crédito (real ou presumido). 70-75: aquisição sem/com
# situação especial. 98-99: catch-all. `taxas.tipo_mov` decide se a linha é
# de entrada ou saída — o enum enviado à IA deve ser filtrado por esse
# sentido (só 01-09 pra saída, só 49-75/98 pra entrada), não a tabela
# inteira sempre.
CST_PIS_COFINS: dict[str, str] = {
    "01": "Operação Tributável com Alíquota Básica",
    "02": "Operação Tributável com Alíquota Diferenciada",
    "03": "Operação Tributável com Alíquota por Unidade de Medida de Produto",
    "04": "Operação Tributável Monofásica — Revenda a Alíquota Zero",
    "05": "Operação Tributável por Substituição Tributária",
    "06": "Operação Tributável a Alíquota Zero",
    "07": "Operação Isenta da Contribuição",
    "08": "Operação sem Incidência da Contribuição",
    "09": "Operação com Suspensão da Contribuição",
    "49": "Outras Operações de Saída",
    "50": "Operação com Direito a Crédito — Vinculada Exclusivamente a Receita Tributada no Mercado Interno",
    "51": "Operação com Direito a Crédito — Vinculada Exclusivamente a Receita Não-Tributada no Mercado Interno",
    "52": "Operação com Direito a Crédito — Vinculada Exclusivamente a Receita de Exportação",
    "53": "Operação com Direito a Crédito — Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno",
    "54": "Operação com Direito a Crédito — Vinculada a Receitas Tributadas no Mercado Interno e de Exportação",
    "55": "Operação com Direito a Crédito — Vinculada a Receitas Não Tributadas no Mercado Interno e de Exportação",
    "56": "Operação com Direito a Crédito — Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno e de Exportação",
    "60": "Crédito Presumido — Operação de Aquisição Vinculada Exclusivamente a Receita Tributada no Mercado Interno",
    "61": "Crédito Presumido — Operação de Aquisição Vinculada Exclusivamente a Receita Não-Tributada no Mercado Interno",
    "62": "Crédito Presumido — Operação de Aquisição Vinculada Exclusivamente a Receita de Exportação",
    "63": "Crédito Presumido — Operação de Aquisição Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno",
    "64": "Crédito Presumido — Operação de Aquisição Vinculada a Receitas Tributadas no Mercado Interno e de Exportação",
    "65": "Crédito Presumido — Operação de Aquisição Vinculada a Receitas Não-Tributadas no Mercado Interno e de Exportação",
    "66": "Crédito Presumido — Operação de Aquisição Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno e de Exportação",
    "67": "Crédito Presumido — Outras Operações",
    "70": "Operação de Aquisição sem Direito a Crédito",
    "71": "Operação de Aquisição com Isenção",
    "72": "Operação de Aquisição com Suspensão",
    "73": "Operação de Aquisição a Alíquota Zero",
    "74": "Operação de Aquisição sem Incidência da Contribuição",
    "75": "Operação de Aquisição por Substituição Tributária",
    "98": "Outras Operações de Entrada",
    "99": "Outras Operações",
}

CST_PIS_COFINS_SAIDA = {k: v for k, v in CST_PIS_COFINS.items() if k in {
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "49", "99",
}}
CST_PIS_COFINS_ENTRADA = {k: v for k, v in CST_PIS_COFINS.items() if k not in {
    "01", "02", "03", "04", "05", "06", "07", "08", "09",
}}

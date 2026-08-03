"""Pré-visualização + aplicação seletiva de retorno bancário — motor
compartilhado pela tela `Importação do Arquivo de Retorno`
(`FrmImpRetBan.frm`), reaproveitando o parsing bank-specific já validado em
cada `cnab_*_service.py` (Fase 2a).

**Diferença deliberada em relação ao legado**: o legado monta uma grade de
revisão com DOIS modos (radio "Confirmação de títulos enviados" /
"Processar Baixas") e permite selecionar linhas de QUALQUER um dos dois
tipos pra confirmar/baixar. Aqui, só o fluxo de **baixa** (ocorrência
06/09/17 — a ação com impacto financeiro real, quita o título) vira uma
grade selecionável linha a linha, com cliente/vencimento/valor resolvidos.
**Confirmação (ocorrência 02/03) vira só uma contagem-resumo**, não uma
lista selecionável — nos bancos CNAB400 (Inter/Itaú), o registro de
confirmação não carrega o mesmo identificador (`Nosso Número`) usado pra
achar o título no banco, só um identificador interno (`AutoNumDRV`) que o
parsing atual não extrai pra esse caso (só usa pra CONTAR, replicando o
`_processar_retorno_sync` de cada motor) — extrair isso pros 5 bancos é
trabalho adicional não incluído nesta rodada. Registrado em PENDENCIAS.md.

Dispatch por banco (`MOTORES`, mesmo padrão de `routes/bancos.py`
`_MOTORES_CNAB`). Cada motor expõe `_parse_linhas` com uma destas formas:
- Bradesco/Santander/BB: `_parse_linhas(conteudo) -> list[dict]`
- Inter: `_parse_linhas(conteudo, cnpj_empresa) -> dict` (precisa do CNPJ
  da empresa pra achar os registros, busca o cabeçalho)
- Itaú: `_parse_linhas(conteudo) -> dict` (`{"error"}` ou `{"registros"}`)
`_normalizar_parse` abaixo uniformiza as 3 formas num único formato de
retorno pro resto deste módulo.
"""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn
from services import cnab_bb_service, cnab_bradesco_service, cnab_inter_service, cnab_itau_service, cnab_santander_service

MOTORES = {
    cnab_bradesco_service.BANCO_BRADESCO_CODIGO: cnab_bradesco_service,
    cnab_inter_service.BANCO_INTER_CODIGO: cnab_inter_service,
    cnab_santander_service.BANCO_SANTANDER_CODIGO: cnab_santander_service,
    cnab_bb_service.BANCO_BB_CODIGO: cnab_bb_service,
    cnab_itau_service.BANCO_ITAU_CODIGO: cnab_itau_service,
}

OCORRENCIAS_BAIXA = ("06", "09", "17")
OCORRENCIAS_CONFIRMACAO = ("02", "03")


def _normalizar_parse(motor, banco_febraban: int, conteudo: str, cur) -> dict:
    """Chama o `_parse_linhas` do motor certo, cobrindo as 3 assinaturas
    diferentes (ver docstring do módulo). Retorna `{"error": msg}` ou
    `{"registros": [...]}`."""
    if motor is cnab_inter_service:
        cur.execute("SELECT cgc FROM controle")
        controle = cur.fetchone() or {}
        cnpj = cnab_inter_service._n(str(controle.get("cgc") or "").strip(), 14)
        parsed = motor._parse_linhas(conteudo, cnpj)
        return parsed
    if motor is cnab_itau_service:
        return motor._parse_linhas(conteudo)
    # Bradesco/Santander/BB: retorno já é a lista direto
    return {"registros": motor._parse_linhas(conteudo)}


def _preview_retorno_sync(servidor: str, banco: str, cod_banco: int, conteudo: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM bancos WHERE cod=%s", (cod_banco,))
        banco_row = cur.fetchone()
        if not banco_row:
            return {"success": False, "message": "Banco não encontrado."}
        banco_febraban = int(banco_row.get("codigo") or 0)
        conta_cedente = int(banco_row.get("contacorrente") or 0)
        motor = MOTORES.get(banco_febraban)
        if not motor:
            return {"success": False, "message": "Leitura de retorno implementada só para Bradesco (237), Inter (077), Santander (033), Banco do Brasil (001) e Itaú (341)."}

        parsed = _normalizar_parse(motor, banco_febraban, conteudo, cur)
        if "error" in parsed:
            return {"success": False, "message": parsed["error"]}

        itens_baixa = []
        itens_nao_encontrados = []
        confirmados = 0
        ignorados = 0
        nao_encontrados = []

        for reg in parsed["registros"]:
            if reg.get("ignorado"):
                ignorados += 1
                continue
            ocorrencia = reg["ocorrencia"]
            if ocorrencia in OCORRENCIAS_CONFIRMACAO:
                confirmados += 1
                continue
            if ocorrencia not in OCORRENCIAS_BAIXA:
                ignorados += 1
                continue

            numero_boleto = reg["numero_boleto"]
            cur.execute(
                "SELECT drv.codigo AS drv_codigo, drv.situacao, drv.dt_vencimento, drv.valor AS valor_titulo, "
                "dr.duplicata AS documento, c.nome AS cliente_nome "
                "FROM duplicata_rec_venc drv "
                "JOIN duplicata_receber dr ON dr.codigo = drv.duplicata "
                "JOIN cliente c ON c.codigo = dr.cliente "
                "WHERE drv.numero_boleto = %s AND drv.banco_cedente = %s AND drv.conta_cedente = %s",
                (int(numero_boleto), banco_febraban, conta_cedente),
            )
            row = cur.fetchone()
            if not row:
                nao_encontrados.append(numero_boleto)
                # Sem `drv_codigo` correspondente (nenhum título local casa
                # com esse número) — ainda assim listamos a linha na grade,
                # com os dados que o próprio arquivo trouxe, pra revisão do
                # usuário (não dá pra selecionar/baixar, não existe título
                # local pra atualizar). Pedido explícito do usuário
                # (2026-07-24): "tem que listar os títulos... não só contar".
                itens_nao_encontrados.append({
                    "drv_codigo": None,
                    "numero_boleto": numero_boleto,
                    "ocorrencia": ocorrencia,
                    "cliente_nome": None,
                    "documento": None,
                    "vencimento": None,
                    "valor_titulo": None,
                    "data_pag": reg["data_pag"].isoformat() if reg.get("data_pag") else None,
                    "valor_pago": reg["valor_pago"],
                    "juros": reg["juros"],
                    "desconto": reg["desconto"],
                    "ja_baixado": False,
                    "encontrado": False,
                })
                continue

            itens_baixa.append({
                "drv_codigo": row["drv_codigo"],
                "numero_boleto": numero_boleto,
                "ocorrencia": ocorrencia,
                "cliente_nome": row.get("cliente_nome"),
                "documento": row.get("documento"),
                "vencimento": row["dt_vencimento"].isoformat() if row.get("dt_vencimento") else None,
                "valor_titulo": float(row.get("valor_titulo") or 0),
                "data_pag": reg["data_pag"].isoformat() if reg.get("data_pag") else None,
                "valor_pago": reg["valor_pago"],
                "juros": reg["juros"],
                "desconto": reg["desconto"],
                "ja_baixado": row.get("situacao") == "PG",
                "encontrado": True,
            })

        cur.close()
        return {
            "success": True,
            "itens_baixa": itens_baixa,
            "itens_nao_encontrados": itens_nao_encontrados,
            "confirmados": confirmados,
            "ignorados": ignorados,
            "nao_encontrados": nao_encontrados,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _aplicar_baixas_sync(servidor: str, banco: str, cod_banco: int, itens: list, conta: Optional[int] = None) -> dict:
    """Réplica de `Baixa_Titulo` (`FrmImpRetBan.frm`) — aplica a baixa nos
    títulos selecionados pelo usuário na grade de revisão. `itens` é a
    mesma lista (ou um subconjunto) devolvida por `_preview_retorno_sync`
    em `itens_baixa`. Idempotente (título já 'PG' é pulado, não conta
    erro)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM bancos WHERE cod=%s", (cod_banco,))
        banco_row = cur.fetchone()
        if not banco_row:
            return {"success": False, "message": "Banco não encontrado."}

        baixados = 0
        ja_baixados = 0
        for item in itens:
            drv_codigo = item.get("drv_codigo")
            if not drv_codigo:
                continue
            cur.execute("SELECT situacao FROM duplicata_rec_venc WHERE codigo=%s", (drv_codigo,))
            row = cur.fetchone()
            if not row:
                continue
            if row.get("situacao") == "PG":
                ja_baixados += 1
                continue
            campos_conta = ", conta=%s" if conta else ""
            params = [
                (item.get("data_pag") or date.today().isoformat()),
                item.get("valor_pago") or 0,
                item.get("juros") or 0,
                item.get("desconto") or 0,
                int(item.get("ocorrencia") or 6),
            ]
            if conta:
                params.append(conta)
            params.append(drv_codigo)
            cur.execute(
                f"UPDATE duplicata_rec_venc SET situacao='PG', data_pag=%s, valor_pag=%s, "
                f"juros_pag=%s, desconto_pag=%s, ultima_mov_banco=%s{campos_conta} WHERE codigo=%s",
                tuple(params),
            )
            baixados += 1

        conn.commit()
        cur.close()
        return {"success": True, "baixados": baixados, "ja_baixados": ja_baixados}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def preview_retorno(servidor: str, banco: str, cod_banco: int, conteudo: str) -> dict:
    return await asyncio.to_thread(_preview_retorno_sync, servidor, banco, cod_banco, conteudo)


async def aplicar_baixas(servidor: str, banco: str, cod_banco: int, itens: list, conta: Optional[int] = None) -> dict:
    return await asyncio.to_thread(_aplicar_baixas_sync, servidor, banco, cod_banco, itens, conta)

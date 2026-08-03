"""Fase 2a — Motor CNAB do Banco do Brasil (código Febraban 001).

**Status: só RETORNO implementado nesta rodada** (2026-07-24), pela mesma
razão do Santander (ver `cnab_santander_service.py`) — o cabeçalho de
remessa CNAB240 é montado pela MESMA função compartilhada
(`Gera_Header_240`), com os mesmos campos de largura ambígua
(`RazaoSocial`, `Nome_Banco`, `Cnab_01`) sem `Format()` de largura fixa no
legado. Geração de remessa fica pendente até haver um arquivo real (Santander
ou BB) para confirmar a largura exata. Ver PENDENCIAS.md > "Bancos" >
"Fase 2a — Banco do Brasil (001)".

**Retorno é seguro de implementar já** — `Retorno_Bancodobrasil`
(`Geral/FrmImpRetBan.frm`) é **byte a byte idêntica** a `Retorno_Santander`
(mesmo motor CNAB240 "Segmento T/U", só muda qual `Sub` é chamada pelo
dispatch de banco) — ver docstring de `cnab_santander_service.py` para o
detalhe completo do formato (posições fixas, sem ambiguidade) e da
simplificação deliberada (baixa aplicada direto no `POST /retorno`, sem o
staging de duas etapas do legado).
"""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn

BANCO_BB_CODIGO = 1


def _parse_valor_cnab(raw: str) -> float:
    raw = (raw or "0").strip() or "0"
    try:
        return int(raw) / 100.0
    except ValueError:
        return 0.0


def _parse_data_ddmmyyyy(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    if len(raw) != 8 or raw == "00000000":
        return None
    try:
        return date(2000 + int(raw[6:8]), int(raw[2:4]), int(raw[0:2]))
    except ValueError:
        return None


def _parse_linhas(conteudo: str) -> list:
    """Extrai os registros de detalhe (pares Segmento T+U) do retorno
    CNAB240, sem tocar no banco de dados — mesmo formato de
    `cnab_santander_service._parse_linhas` (funções idênticas no legado,
    ver docstring do módulo). Usado tanto por `_processar_retorno_sync`
    quanto pela pré-visualização compartilhada
    (`cobranca_retorno_service.py`)."""
    linhas = [l for l in conteudo.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]
    registros = []
    titulo_atual = None  # {"nosso_numero": str, "ocorrencia": str}

    for linha in linhas:
        if len(linha) < 62 or linha[7] != "3":
            registros.append({"ignorado": True})
            continue
        cod_segmento = linha[13:14]
        if cod_segmento == "T":
            titulo_atual = {
                "nosso_numero": linha[40:53].strip().lstrip("0") or "0",
                "ocorrencia": linha[15:17].strip(),
            }
        elif cod_segmento == "U" and titulo_atual:
            ocorrencia = titulo_atual["ocorrencia"]
            nosso_numero = titulo_atual["nosso_numero"]
            titulo_atual = None

            if len(linha) < 107:
                registros.append({"ignorado": True})
                continue

            acrescimos = _parse_valor_cnab(linha[17:32])
            descontos = _parse_valor_cnab(linha[32:47]) + _parse_valor_cnab(linha[47:62])
            valor_pago = _parse_valor_cnab(linha[92:107])
            data_pg = _parse_data_ddmmyyyy(linha[137:145] if len(linha) >= 145 else "") or date.today()
            registros.append({
                "ignorado": False, "numero_boleto": nosso_numero, "ocorrencia": ocorrencia,
                "data_pag": data_pg, "valor_pago": valor_pago, "juros": acrescimos, "desconto": descontos,
                "documento": None,
            })
        else:
            registros.append({"ignorado": True})
    return registros


def _processar_retorno_sync(servidor: str, banco: str, cod_banco: int, conteudo: str) -> dict:
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
        conta_cedente = int(banco_row.get("contacorrente") or 0)

        confirmados = 0
        baixados = 0
        nao_encontrados = []
        ignorados = 0

        for reg in _parse_linhas(conteudo):
            if reg["ignorado"]:
                ignorados += 1
                continue
            ocorrencia = reg["ocorrencia"]
            nosso_numero = reg["numero_boleto"]

            if ocorrencia not in ("06", "09", "17"):
                confirmados += 1
                continue

            cur.execute(
                "SELECT codigo, situacao FROM duplicata_rec_venc "
                "WHERE numero_boleto = %s AND banco_cedente = %s AND conta_cedente = %s",
                (int(nosso_numero), BANCO_BB_CODIGO, conta_cedente),
            )
            row = cur.fetchone()
            if not row:
                nao_encontrados.append(nosso_numero)
                continue
            if row.get("situacao") == "PG":
                continue  # já baixado antes — idempotente
            cur.execute(
                "UPDATE duplicata_rec_venc SET situacao='PG', data_pag=%s, valor_pag=%s, "
                "juros_pag=%s, desconto_pag=%s, ultima_mov_banco=%s WHERE codigo=%s",
                (reg["data_pag"].isoformat(), reg["valor_pago"], reg["juros"], reg["desconto"], int(ocorrencia), row["codigo"]),
            )
            baixados += 1

        conn.commit()
        cur.close()
        return {
            "success": True,
            "confirmados": confirmados,
            "baixados": baixados,
            "nao_encontrados": nao_encontrados,
            "ignorados": ignorados,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _gerar_remessa_sync(servidor: str, banco: str, cod_banco: int, titulos: Optional[list] = None) -> dict:
    return {
        "success": False,
        "message": (
            "Geração de remessa para o Banco do Brasil ainda não foi implementada — o layout do "
            "cabeçalho do arquivo (CNAB240) tem campos de largura ambígua no código legado, "
            "sem um arquivo real para confirmar. Ver PENDENCIAS.md."
        ),
    }


async def gerar_remessa(servidor: str, banco: str, cod_banco: int, titulos: Optional[list] = None) -> dict:
    return await asyncio.to_thread(_gerar_remessa_sync, servidor, banco, cod_banco, titulos)


async def processar_retorno(servidor: str, banco: str, cod_banco: int, conteudo: str) -> dict:
    return await asyncio.to_thread(_processar_retorno_sync, servidor, banco, cod_banco, conteudo)

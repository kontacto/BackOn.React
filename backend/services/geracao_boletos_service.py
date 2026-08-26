"""Geração de Boletos (Financeiro > Cobranças) — baseada em `frmrelbol4.frm`
(`Kontacto`). Filtros + grade de títulos + "Gerar Remessa" (reaproveita os
motores CNAB já implementados) + "Gerar Planilha" (exportação Excel, feita
no frontend) + (2026-08-26) "Baixar PDF"/"Enviar por Email" (código de
barras real, ver `boleto_pdf_service.py`). Ver PENDENCIAS.md > "Boleto em
PDF" pro mapeamento completo.

Query de títulos elegíveis replica `Command1_Click` (`frmrelbol4.frm:750`)
— join `duplicata_receber`+`cliente`+`duplicata_rec_venc`, `situacao='A'`.
**Simplificações deliberadas** (ver docstring de cada uma):
- Tarifa bancária/multa/mora aqui são só ESTIMATIVAS informativas pra
  grade (mesma fórmula já usada nos motores CNAB — `bancos.tarifa_cobranca`
  quando `cobra_tarifa_bancaria`, `Multa_Atraso_Pag`/`mora_dia_pag`
  aplicados sobre o valor) — o legado tinha um campo de override manual
  (`Campo(3)`) na tela de impressão, que não existe aqui (não há impressão
  de boleto nesta fase, então não há necessidade de recalcular o valor
  final impresso).
- O filtro "Cliente" segue o padrão global de campo de cliente ([GLOBAL],
  ver CLAUDE.md "Padrão de Campo Cliente") — o frontend resolve o termo
  digitado (Enter) contra `GET /api/clientes/find/search` (que já busca
  pelos principais campos — nome, fantasia, CNPJ/CPF, telefone, código
  exato pra termo numérico) e manda pra cá o `cliente_codigo` já resolvido
  (1 resultado = direto; 0 ou 2+ = abre `ClientSearchModal` pra escolher) —
  o filtro aqui é sempre um único cliente exato, não um LIKE de texto.
- Cruzamento com nota fiscal/comanda (`duplicata_rec_nf`/`n_fiscal`/
  `comanda_nf`) do legado, usado só pra exibir "Comanda" na grade de
  impressão, não foi portado — não é necessário pro fluxo de remessa.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services import boleto_pdf_service, email_cobranca_service


def _listar_titulos_sync(servidor: str, banco: str, cod_banco: int, filtros: dict) -> dict:
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

        where = ["drv.situacao = 'A'"]
        params = []

        if filtros.get("emissao_de") and filtros.get("emissao_ate"):
            where.append("dr.dt_emissao >= %s AND dr.dt_emissao <= %s")
            params += [filtros["emissao_de"], filtros["emissao_ate"]]
        if filtros.get("vencimento_de") and filtros.get("vencimento_ate"):
            where.append("drv.dt_vencimento >= %s AND drv.dt_vencimento <= %s")
            params += [filtros["vencimento_de"], filtros["vencimento_ate"]]
        if filtros.get("duplicata"):
            where.append("dr.duplicata = %s")
            params.append(int(filtros["duplicata"]))
        if filtros.get("numero_boleto"):
            where.append("drv.numero_boleto = %s AND drv.banco_cedente = %s")
            params += [int(filtros["numero_boleto"]), int(banco_row.get("codigo") or 0)]
        if filtros.get("cliente_codigo"):
            where.append("c.codigo = %s")
            params.append(int(filtros["cliente_codigo"]))
        if filtros.get("so_sem_boleto"):
            where.append("(drv.numero_boleto IS NULL OR drv.numero_boleto = 0)")
        if filtros.get("somente_registrados"):
            where.append("drv.registrado = 1")

        sql = (
            "SELECT drv.codigo AS drv_codigo, dr.codigo AS dr_codigo, dr.duplicata, c.codigo AS cliente_codigo, "
            "c.nome AS cliente_nome, dr.dt_emissao, drv.dt_vencimento, drv.valor, drv.OUTROS_acres_pag, "
            "drv.numero_boleto, drv.registrado, drv.banco_cedente, drv.desmembramento, dr.num_parcelas, "
            "c.cobra_tarifa_bancaria "
            "FROM duplicata_receber dr "
            "JOIN cliente c ON c.codigo = dr.cliente "
            "JOIN duplicata_rec_venc drv ON drv.duplicata = dr.codigo "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY c.nome, dr.duplicata, drv.dt_vencimento"
        )
        cur.execute(sql, tuple(params))
        linhas = cur.fetchall()
        cur.close()

        multa_atraso_pag = float(banco_row.get("Multa_Atraso_Pag") or 0)
        mora_dia_pag = float(banco_row.get("mora_dia_pag") or 0)
        tarifa_cobranca = float(banco_row.get("tarifa_cobranca") or 0)

        itens = []
        for l in linhas:
            valor_base = float(l.get("valor") or 0) + float(l.get("OUTROS_acres_pag") or 0)
            taxa_bancaria = tarifa_cobranca if l.get("cobra_tarifa_bancaria") else 0.0
            multa_atraso_est = round(valor_base * multa_atraso_pag / 100, 2)
            multa_dia_est = round(valor_base * mora_dia_pag / 100, 2)
            itens.append({
                "drv_codigo": l["drv_codigo"],
                "cliente_codigo": l["cliente_codigo"],
                "cliente_nome": l.get("cliente_nome"),
                "duplicata": l["duplicata"],
                "dt_emissao": l["dt_emissao"].isoformat() if l.get("dt_emissao") else None,
                "dt_vencimento": l["dt_vencimento"].isoformat() if l.get("dt_vencimento") else None,
                "taxa_bancaria": taxa_bancaria,
                "multa_atraso": multa_atraso_est,
                "multa_dia_atraso": multa_dia_est,
                "valor_total": round(valor_base + taxa_bancaria, 2),
                "numero_boleto": l.get("numero_boleto"),
                "registrado": bool(l.get("registrado")),
                "parcela_info": (
                    f"{l['desmembramento']} de {l['num_parcelas']}"
                    if l.get("num_parcelas") and l.get("num_parcelas") != 1 else ""
                ),
            })
        return {"success": True, "items": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def listar_titulos(servidor: str, banco: str, cod_banco: int, filtros: dict) -> dict:
    return await asyncio.to_thread(_listar_titulos_sync, servidor, banco, cod_banco, filtros)


# ============ PDF / E-mail (2026-08-26) ============
def _baixar_pdf_sync(servidor: str, banco: str, cod_banco: int, titulos: list) -> dict:
    return boleto_pdf_service.gerar_pdf_titulos_sync(servidor, banco, cod_banco, titulos)


async def baixar_pdf(servidor: str, banco: str, cod_banco: int, titulos: list) -> dict:
    return await asyncio.to_thread(_baixar_pdf_sync, servidor, banco, cod_banco, titulos)


def _enviar_email_sync(servidor: str, banco: str, cod_banco: int, titulos: list) -> dict:
    """Por título: registra o título no banco escolhido (mesma gravação
    de `Baixar PDF` — idempotente), resolve o e-mail do cliente (mesma
    cascata já usada em `contratos_service._enviar_cobrancas_sync`),
    gera o PDF de 1 título e chama `email_cobranca_service`. Sem e-mail
    cadastrado nunca tenta enviar. Cada item roda isolado (lote
    best-effort, mesmo padrão de `contratos_service._enviar_cobrancas_
    sync`)."""
    if not titulos:
        return {"success": False, "message": "Selecione ao menos um título."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        resultados = []
        for drv_codigo in titulos:
            try:
                erro = boleto_pdf_service._registrar_banco_no_titulo_sync(cur, drv_codigo, cod_banco)
                if erro:
                    resultados.append({"codigo": drv_codigo, "success": False, "message": erro["message"]})
                    continue
                conn.commit()

                cur.execute(
                    "SELECT ISNULL(NULLIF(c.email_cobranca,''), ISNULL(NULLIF(c.email_NFE,''), c.e_mail)) AS email_destino, "
                    "c.nome, c.fantasia, drv.dt_vencimento, drv.valor "
                    "FROM duplicata_rec_venc drv JOIN duplicata_receber dr ON dr.codigo = drv.duplicata "
                    "JOIN cliente c ON c.codigo = dr.cliente WHERE drv.codigo=%s",
                    (drv_codigo,),
                )
                row = cur.fetchone()
                if not row:
                    resultados.append({"codigo": drv_codigo, "success": False, "message": "Título não encontrado."})
                    continue
                email_destino = (row.get("email_destino") or "").strip()
                if not email_destino:
                    resultados.append({"codigo": drv_codigo, "success": False, "message": "Sem e-mail cadastrado."})
                    continue

                pdf_bytes = boleto_pdf_service.gerar_pdf_um_titulo_sync(cur, drv_codigo)
                if not pdf_bytes:
                    resultados.append({"codigo": drv_codigo, "success": False, "message": "Não foi possível gerar o PDF do boleto."})
                    continue

                nome_cliente = (row.get("fantasia") or row.get("nome") or "").strip()
                vencimento = row["dt_vencimento"].strftime("%d/%m/%Y") if row.get("dt_vencimento") else ""
                assunto = f"Boleto para pagamento — vencimento {vencimento}"
                corpo = (
                    f'<font face="Arial" size="2">Prezado(a) {nome_cliente},<br><br>'
                    f"Segue em anexo o boleto para pagamento, vencimento {vencimento}.<br><br>"
                    "Atenciosamente,<br></font>"
                )
                anexos = [{"conteudo": pdf_bytes, "nome_arquivo": f"boleto_{drv_codigo}.pdf"}]
                envio = email_cobranca_service._enviar_email_sync(servidor, banco, email_destino, assunto, corpo, anexos)
                resultados.append({"codigo": drv_codigo, "success": bool(envio.get("success")), "message": envio.get("message")})
            except Exception as e:
                resultados.append({"codigo": drv_codigo, "success": False, "message": f"Erro: {e}"})
        cur.close()
        return {"success": True, "resultados": resultados}
    finally:
        conn.close()


async def enviar_email(servidor: str, banco: str, cod_banco: int, titulos: list) -> dict:
    return await asyncio.to_thread(_enviar_email_sync, servidor, banco, cod_banco, titulos)

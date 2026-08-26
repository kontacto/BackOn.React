"""Gestor de Comandas / Alterar Comandas — migração de `FrmConCupom.frm`
("Consulta de Vendas") e `FrmAltComNV.frm` ("Alteração de Vendas"). Ver
`C:/Desenv/VB6/SQLSERVER/Geral/FRMCONVENDAS.txt` e `FrmAltComNVNV.txt`
(colados pelo usuário 2026-07-21) e PENDENCIAS.md > "Gestor de Comandas"
pro racional completo/fases.

Toda venda finalizada no sistema (Pré-Venda de O.S., Pedido de Venda,
Faturar Contratos) vira um registro em `comanda` — esta tela é o
"relatório de vendas" sobre essa tabela, e a tela de alteração/cancelamento
que abre a partir dela.

Fase 1 (esta): só a listagem/busca (`_list_comandas_sync`), somente
leitura. Fases 2/3 (Gravar, Alterar Forma de Pagamento, Cancelar) entram
depois — ver PENDENCIAS.md.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.comanda import (
    ComandaAddNumSerieRequest, ComandaAlterarFormaPagamentoRequest, ComandaAlterarVendedorItemRequest,
    ComandaCancelarRequest, ComandaGravarRequest, EmitirNfceRequest, EmitirNfseRequest, ListarComandasRequest,
)
from services import contingencia_nfce_service, fechamento_caixa_service, ibs_cbs_service, nfe_cancelamento_service, nfe_emissao_service, nfe_fiscal_common, nfse_emissao_service
from services.constants import SITUACAO_LABEL
from services.permissoes_service import tem_permissao

# As 8 tabelas de pagamento lançado numa comanda — usadas tanto pro detalhe
# (`_get_comanda_sync`) quanto pra reversão no Cancelar (`_cancelar_comanda_
# sync`). `transf_receber` (bit, confirmado ao vivo contra o schema real —
# não existe `flag_transf_caixa` nessas tabelas) indica se aquele lançamento
# já foi conciliado/transferido pro financeiro (`duplicata_receber` etc.) —
# quando já foi, não há FK de volta da comanda pro financeiro que permita
# reverter com segurança (confirmado: nenhuma das tabelas de
# duplicata/recebimento tem coluna `comanda`), então o cancelamento bloqueia
# nesse caso em vez de arriscar apagar o lançamento errado.
_TABELAS_PAGAMENTO_COMANDA = [
    "comanda_dinheiro", "comanda_cheque", "comanda_cartao", "comanda_debito",
    "comanda_duplicata", "comanda_ticket", "comanda_vale", "comanda_financiado",
]

# Tabelas de forma de pagamento lançadas numa comanda — mesmas 8 modalidades
# já usadas em `forma_pagamento_service.py` (DI/CH/CC/CD/DU/TI/VA/FI), aqui
# pra montar o detalhe da comanda (`_get_comanda_sync`) e localizar o
# lançamento certo em `_alterar_forma_pagamento_sync`. Coluna de valor varia
# por tabela (confirmado ao vivo contra o schema — `valor`, `valor_pago` ou
# `valor_pag` dependendo da tabela).
_TABELAS_FORMA_PAG = {
    "DI": ("comanda_dinheiro", "valor_pago"),
    "CH": ("comanda_cheque", "valor"),
    "CC": ("comanda_cartao", "valor"),
    "CD": ("comanda_debito", "valor"),
    "DU": ("comanda_duplicata", "valor_pag"),
    "TI": ("comanda_ticket", "valor"),
    "VA": ("comanda_vale", "valor"),
    "FI": ("comanda_financiado", "valor_pag"),
}

# Só cartão/débito têm alteração de forma de pagamento no legado
# (`Command12_Click` de `FrmAltComNV.frm`) — mesma modalidade só (cartão↔
# cartão, débito↔débito).
_TABELAS_ALTERAVEIS = {"CC": "comanda_cartao", "CD": "comanda_debito"}


def _iso_ou_str(v) -> Optional[str]:
    """Alguns campos de data/hora do schema (ex.: `comanda_nfce.dhemi`)
    voltam do pymssql como `str` em vez de `datetime` dependendo do tipo
    real da coluna — normaliza os dois casos em vez de assumir sempre
    `datetime` (achado ao vivo contra BD_PAJE, 2026-07-21)."""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _resolver_cliente_termo(cur, termo: str) -> Optional[int]:
    """Resolve um termo de busca de cliente (código, CGC/CPF ou nome) pro
    código — mesma cascata de `Campo_LostFocus(7)` em `FrmConCupom.frm`."""
    termo = (termo or "").strip()
    if not termo:
        return None
    if termo.isdigit():
        cur.execute("SELECT codigo FROM cliente WHERE codigo=%s", (int(termo),))
        row = cur.fetchone()
        if row:
            return int(row["codigo"])
        cur.execute("SELECT codigo FROM cliente WHERE cgc_cpf=%s", (termo,))
        row = cur.fetchone()
        return int(row["codigo"]) if row else None
    cur.execute("SELECT TOP 1 codigo FROM cliente WHERE nome=%s OR fantasia=%s", (termo, termo))
    row = cur.fetchone()
    return int(row["codigo"]) if row else None


def _resolver_produto_termo(cur, termo: str) -> Optional[str]:
    """Resolve um termo de produto/serviço pro `codigo_int` — mesma
    cascata de `Campo_LostFocus(8)` (código de fábrica, descrição, código
    interno, depois o mesmo pra serviços)."""
    termo = (termo or "").strip()
    if not termo:
        return None
    cur.execute("SELECT codigo_int FROM pecas WHERE codigo_fab=%s", (termo,))
    row = cur.fetchone()
    if row:
        return row["codigo_int"]
    cur.execute("SELECT codigo_int FROM pecas WHERE descricao=%s", (termo,))
    row = cur.fetchone()
    if row:
        return row["codigo_int"]
    cur.execute("SELECT codigo_int FROM pecas WHERE codigo_int=%s", (termo,))
    row = cur.fetchone()
    if row:
        return row["codigo_int"]
    cur.execute("SELECT codigo FROM servicos WHERE codigo=%s", (termo,))
    row = cur.fetchone()
    if row:
        return str(row["codigo"])
    cur.execute("SELECT codigo FROM servicos WHERE descricao=%s", (termo,))
    row = cur.fetchone()
    return str(row["codigo"]) if row else None


def _list_comandas_sync(req: ListarComandasRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)

        where: list[str] = ["c.situacao IN ('PG','A')"]
        params: list = []

        if req.data_ini:
            where.append("c.data >= %s")
            params.append(req.data_ini)
        if req.data_fim:
            where.append("c.data <= %s")
            params.append(req.data_fim)
        if req.area_atuacao is not None:
            where.append("(c.area_atuacao = %s OR c.area_atuacao = 0)")
            params.append(req.area_atuacao)
        if req.valor_de is not None:
            where.append("c.valor_venda >= %s")
            params.append(req.valor_de)
        if req.valor_ate is not None:
            where.append("c.valor_venda <= %s")
            params.append(req.valor_ate)
        if req.comanda is not None:
            where.append("c.comanda = %s")
            params.append(req.comanda)
        if req.cliente:
            cod_cliente = _resolver_cliente_termo(cur, req.cliente)
            if cod_cliente is None:
                cur.close()
                conn.close()
                return {"success": True, "items": [], "total": 0, "resumo": _resumo_vazio()}
            where.append("c.cliente = %s")
            params.append(cod_cliente)
        if req.atendente is not None:
            if req.atendente_dav:
                where.append("c.atendente_dav = %s")
            else:
                where.append("c.atendente = %s")
            params.append(req.atendente)
        if req.cupom is not None:
            where.append("%s IN (SELECT cc.num_cupom FROM comanda_cupom cc WHERE cc.comanda = c.comanda)")
            params.append(req.cupom)
        if req.nfce is not None:
            where.append("%s IN (SELECT cn.num_nfce FROM comanda_nfce cn WHERE cn.comanda = c.comanda)")
            params.append(req.nfce)
        if req.nf is not None:
            where.append(
                "%s IN (SELECT nf.num_nf FROM comanda_nf AS cnf, n_fiscal AS nf "
                "WHERE cnf.nota_fisc = nf.codigo AND cnf.comanda = c.comanda)"
            )
            params.append(req.nf)
        if req.pedido is not None:
            where.append("c.comanda IN (SELECT cp.comanda FROM comanda_ped cp WHERE cp.ped = %s)")
            params.append(req.pedido)
        if req.os is not None:
            where.append("c.comanda IN (SELECT co.comanda FROM comanda_os co WHERE co.os = %s)")
            params.append(req.os)
        if req.produto:
            cod_produto = _resolver_produto_termo(cur, req.produto)
            if cod_produto is None:
                cur.close()
                conn.close()
                return {"success": True, "items": [], "total": 0, "resumo": _resumo_vazio()}
            where.append(
                "c.comanda IN (SELECT m.num_nf FROM movimentacao m WHERE m.serie_nf = 'CM' AND m.codigo_int = %s)"
            )
            params.append(cod_produto)
        if req.forma_pagamento:
            cur.execute("SELECT tipo FROM forma_pagamento WHERE codigo=%s", (req.forma_pagamento,))
            fp_row = cur.fetchone()
            tipo = (fp_row.get("tipo") or "").strip().upper() if fp_row else ""
            tabela_por_tipo = {
                "DI": "comanda_dinheiro", "CH": "comanda_cheque", "CC": "comanda_cartao",
                "CD": "comanda_debito", "DU": "comanda_duplicata", "TI": "comanda_ticket",
                "VA": "comanda_vale", "FI": "comanda_financiado",
            }
            tabela = tabela_por_tipo.get(tipo)
            if tabela:
                where.append(f"c.comanda IN (SELECT t.comanda FROM {tabela} t WHERE t.forma_pag = %s)")
                params.append(req.forma_pagamento)
            else:
                cur.close()
                conn.close()
                return {"success": True, "items": [], "total": 0, "resumo": _resumo_vazio()}
        if not req.com_nota and not req.sem_nota:
            # Mesma regra do legado: se os dois estiverem desmarcados, trata
            # como se os dois estivessem marcados (Command6_Click).
            pass
        elif req.com_nota and not req.sem_nota:
            where.append("EXISTS (SELECT 1 FROM comanda_nf cnf WHERE cnf.comanda = c.comanda)")
        elif req.sem_nota and not req.com_nota:
            where.append("NOT EXISTS (SELECT 1 FROM comanda_nf cnf WHERE cnf.comanda = c.comanda)")

        where_sql = " AND ".join(where)
        order_sql = "cli.nome" if req.ordenar_por == "cliente" else "c.comanda DESC"
        # Totais por forma de pagamento — pedido explícito do usuário
        # 2026-07-21 ("totais por forma de pagto") no card "Totais" do
        # Gestor de Comandas. Soma real lançada em cada uma das 8 tabelas
        # (`_TABELAS_FORMA_PAG`), não o valor da comanda — uma comanda sem
        # NENHUMA linha em nenhuma das 8 entra em "sem pagamento lançado",
        # mesmo critério já usado no Fechamento de Caixa
        # (`fechamento_caixa_service._pedidos_faturados_sem_forma_
        # pagamento_sync`).
        forma_pag_cols_sql = ", ".join(
            f"(SELECT ISNULL(SUM({col}), 0) FROM {tabela} WHERE comanda = c.comanda) AS fp_{tipo}"
            for tipo, (tabela, col) in _TABELAS_FORMA_PAG.items()
        )

        cur.execute(
            f"SELECT c.comanda, c.data, c.valor_venda, c.situacao, c.cliente, "
            f"ISNULL(cli.nome, 'CLIENTES DIVERSOS') AS cliente_nome, "
            f"(SELECT TOP 1 cc.num_pdv FROM comanda_cupom cc WHERE cc.comanda = c.comanda) AS num_pdv, "
            f"(SELECT TOP 1 cc.num_cupom FROM comanda_cupom cc WHERE cc.comanda = c.comanda) AS num_cupom, "
            f"(SELECT TOP 1 cn.num_nfce FROM comanda_nfce cn WHERE cn.comanda = c.comanda) AS num_nfce, "
            f"(SELECT TOP 1 nf.num_nf FROM comanda_nf AS cnf, n_fiscal AS nf "
            f" WHERE cnf.nota_fisc = nf.codigo AND cnf.comanda = c.comanda) AS num_nf, "
            f"(SELECT TOP 1 cp.ped FROM comanda_ped cp WHERE cp.comanda = c.comanda) AS ped_vinculado, "
            f"(SELECT TOP 1 co.os FROM comanda_os co WHERE co.comanda = c.comanda) AS os_vinculada, "
            f"(SELECT COALESCE(NULLIF(f.nome_guerra,''), f.nome) FROM funcionarios f "
            f" WHERE f.codigo_int = c.atendente) AS atendente_nome, "
            f"{forma_pag_cols_sql} "
            f"FROM comanda c "
            f"LEFT JOIN cliente cli ON cli.codigo = c.cliente "
            f"WHERE {where_sql} "
            f"ORDER BY {order_sql}",
            tuple(params),
        )
        rows = cur.fetchall()
        items = []
        total_geral = 0.0
        total_ecf = 0.0
        total_nfce = 0.0
        total_nf = 0.0
        total_sem_doc = 0.0
        total_sem_pagamento = 0.0
        totais_forma_pag = {tipo: 0.0 for tipo in _TABELAS_FORMA_PAG}
        for r in rows:
            valor = float(r.get("valor_venda") or 0)
            total_geral += valor
            tem_cupom = r.get("num_cupom") is not None
            tem_nfce = r.get("num_nfce") is not None
            tem_nf = r.get("num_nf") is not None
            if tem_cupom:
                total_ecf += valor
            if tem_nfce:
                total_nfce += valor
            if tem_nf:
                total_nf += valor
            if not tem_cupom and not tem_nfce and not tem_nf:
                total_sem_doc += valor
            valor_pago_total = 0.0
            for tipo in _TABELAS_FORMA_PAG:
                v_tipo = float(r.get(f"fp_{tipo}") or 0)
                totais_forma_pag[tipo] += v_tipo
                valor_pago_total += v_tipo
            if valor_pago_total <= 0.005:
                total_sem_pagamento += valor
            sit = (r.get("situacao") or "").strip()
            items.append({
                "comanda": int(r["comanda"]),
                "data": r["data"].isoformat() if r.get("data") else None,
                "valor": valor,
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "cliente": int(r["cliente"]) if r.get("cliente") else None,
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "num_pdv": r.get("num_pdv"),
                "num_cupom": r.get("num_cupom"),
                "num_nfce": r.get("num_nfce"),
                "num_nf": r.get("num_nf"),
                "pedido_vinculado": r.get("ped_vinculado"),
                "os_vinculada": r.get("os_vinculada"),
                "atendente_nome": (r.get("atendente_nome") or "").strip(),
            })
        cur.close()
        conn.close()
        return {
            "success": True,
            "items": items,
            "total": len(items),
            "resumo": {
                "total_geral": round(total_geral, 2),
                "total_ecf": round(total_ecf, 2),
                "total_nfce": round(total_nfce, 2),
                "total_nf": round(total_nf, 2),
                "total_sem_documento": round(total_sem_doc, 2),
                "total_sem_pagamento": round(total_sem_pagamento, 2),
                "por_forma_pagamento": sorted(
                    (
                        {"tipo": tipo, "label": fechamento_caixa_service.TIPO_LABEL.get(tipo, tipo), "valor": round(v, 2)}
                        for tipo, v in totais_forma_pag.items() if v > 0
                    ),
                    key=lambda x: x["valor"], reverse=True,
                ),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _resumo_vazio() -> dict:
    return {
        "total_geral": 0.0, "total_ecf": 0.0, "total_nfce": 0.0, "total_nf": 0.0, "total_sem_documento": 0.0,
        "total_sem_pagamento": 0.0, "por_forma_pagamento": [],
    }


async def list_comandas(req: ListarComandasRequest) -> dict:
    return await asyncio.to_thread(_list_comandas_sync, req)


def _get_doc_fiscal_sync(servidor: str, banco: str, comanda: int) -> dict:
    """Dados do documento fiscal vinculado a uma comanda, pra reimpressão —
    migração do atalho `[F2] - Reimprimir Não-fiscal ou NFCe` de
    `FrmConCupom.frm`. Como este backend ainda não tem um gerador real de
    DANFE/cupom fiscal (ver `notas_fiscais_service.py`, mesma ressalva),
    isto reproduz os DADOS do documento já armazenados (chave, protocolo,
    valores, XML da NFCe quando existir) — não uma via fac-símile do
    documento oficial."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 num_nfce, situacao, protocolo_sefaz, chave_acesso, dhemi, vnf, xml "
            "FROM comanda_nfce WHERE comanda = %s ORDER BY autonum DESC",
            (comanda,),
        )
        nfce = cur.fetchone()
        if nfce:
            detalhe = nfe_emissao_service.parse_nfce_xml_para_exibicao(nfce.get("xml") or "")
            # Extrato NFC-e ganhou QR Code real (2026-08-20, ver PENDENCIAS.md
            # > "Extrato NFC-e — código de barras e QR reais") — desenha a
            # imagem aqui (servidor) a partir da MESMA URL já embutida no XML
            # transmitido (`qr_code_url`, conteúdo público, nada novo sendo
            # decidido aqui), evita round-trip extra no frontend.
            if detalhe and detalhe.get("qr_code_url"):
                try:
                    detalhe["qr_code_png_base64"] = nfe_fiscal_common.gerar_qrcode_png_base64(detalhe["qr_code_url"])
                except Exception:
                    pass
            cur.close()
            conn.close()
            return {
                "success": True, "tipo": "NFCE",
                "numero": nfce.get("num_nfce"), "situacao": nfce.get("situacao"),
                "protocolo": nfce.get("protocolo_sefaz"), "chave_acesso": nfce.get("chave_acesso"),
                "data_emissao": _iso_ou_str(nfce.get("dhemi")),
                "valor": float(nfce.get("vnf") or 0), "xml": nfce.get("xml"),
                "detalhe": detalhe,
            }
        # `n_fiscal`/`comanda_nf` — tabela central de toda nota fiscal do
        # sistema (correção 2026-07-21, user-directed — ver docstring de
        # `_emitir_nfse_comanda_sync` pro racional completo; reverte uma
        # tentativa anterior, no mesmo dia, de consultar a tabela `dps`).
        cur.execute(
            "SELECT nf.chave_acesso, nf.situacao, nf.data_nf AS data_dps, nf.valor_total, "
            "nf.num_nf AS num_dps, nf.serie_nf AS serie_dps "
            "FROM comanda_nf cnf JOIN n_fiscal nf ON nf.codigo = cnf.nota_fisc "
            "WHERE cnf.comanda = %s AND cnf.tipo = 2",
            (comanda,),
        )
        nfse = cur.fetchone()
        if nfse:
            # Sem round-trip real contra o ADN (nunca testado — ver
            # `nfse_emissao_service.py`), o XML final da NFS-e não é
            # confiavelmente conhecido; emitente/tomador/serviço são
            # RESOLVIDOS DE NOVO aqui (mesmas fontes da emissão: `controle`,
            # `cliente`, `movimentacao`+`servicos`), não lidos de um
            # snapshot gravado — se a empresa/cliente mudou depois da
            # emissão, o fac-símile reflete o dado ATUAL, não o transmitido.
            cur.execute("SELECT cgc, rz_social, fantasia, endereco, numero, bairro, cidade, uf, cep, telefone, inscr_municipal FROM controle")
            controle = cur.fetchone() or {}
            cur.execute("SELECT cliente FROM comanda WHERE comanda = %s", (comanda,))
            cab_cliente = cur.fetchone() or {}
            tomador = None
            if cab_cliente.get("cliente"):
                cur.execute("SELECT cgc_cpf, nome FROM cliente WHERE codigo = %s", (cab_cliente["cliente"],))
                tomador = cur.fetchone()
            cur.execute(
                "SELECT s.descricao, s.cod_lista_servico "
                "FROM movimentacao m JOIN servicos s ON s.codigo = m.codigo_int "
                "WHERE m.serie_nf = 'CM' AND m.num_nf = %s AND ISNULL(m.Estornado, 0) = 0",
                (comanda,),
            )
            servicos_itens = cur.fetchall()
            cur.close()
            conn.close()
            return {
                "success": True, "tipo": "NFSE", "situacao": nfse.get("situacao"),
                "chave_acesso": nfse.get("chave_acesso"), "data_emissao": _iso_ou_str(nfse.get("data_dps")),
                "valor": float(nfse.get("valor_total") or 0),
                "numero_dps": nfse.get("num_dps"), "serie_dps": nfse.get("serie_dps"),
                "detalhe": {
                    "emit_cnpj": controle.get("cgc"), "emit_nome": controle.get("rz_social") or controle.get("fantasia"),
                    "emit_endereco": ", ".join(filter(None, [
                        controle.get("endereco"), str(controle.get("numero") or "").strip() or None, controle.get("bairro"),
                    ])),
                    "emit_cidade": controle.get("cidade"), "emit_uf": controle.get("uf"), "emit_cep": controle.get("cep"),
                    "emit_telefone": controle.get("telefone"), "emit_inscr_municipal": controle.get("inscr_municipal"),
                    "toma_doc": (tomador or {}).get("cgc_cpf"), "toma_nome": (tomador or {}).get("nome"),
                    "servicos": [
                        {"descricao": (s.get("descricao") or "").strip(), "cod_lista_servico": (s.get("cod_lista_servico") or "").strip()}
                        for s in servicos_itens
                    ],
                },
            }
        cur.execute(
            "SELECT nf.num_nf, nf.serie_nf, nf.situacao, nf.protocolo_sefaz, nf.chave_acesso, "
            "nf.xml, nf.dhRecbto "
            "FROM comanda_nf cnf JOIN n_fiscal nf ON nf.codigo = cnf.nota_fisc WHERE cnf.comanda = %s",
            (comanda,),
        )
        nf = cur.fetchone()
        if nf:
            detalhe = nfe_emissao_service.parse_nfe_xml_para_exibicao(nf.get("xml") or "")
            if detalhe:
                detalhe["protocolo_sefaz"] = nf.get("protocolo_sefaz")
                detalhe["chave_acesso"] = nf.get("chave_acesso") or detalhe.get("chave_acesso")
                detalhe["dh_recbto"] = nf.get("dhRecbto")
                detalhe["situacao"] = nf.get("situacao")
            cur.execute("SELECT TOP 1 modelo_danfe FROM controle_aux")
            aux = cur.fetchone()
            cur.close()
            conn.close()
            return {
                "success": True, "tipo": "NF",
                "numero": nf.get("num_nf"), "serie": nf.get("serie_nf"), "situacao": nf.get("situacao"),
                "protocolo": nf.get("protocolo_sefaz"), "chave_acesso": nf.get("chave_acesso"),
                "detalhe": detalhe, "modelo_danfe": (aux or {}).get("modelo_danfe"),
            }
        cur.execute(
            "SELECT num_pdv, num_cupom, coo, situacao FROM comanda_cupom WHERE comanda = %s",
            (comanda,),
        )
        cupom = cur.fetchone()
        if cupom:
            cur.close()
            conn.close()
            return {
                "success": True, "tipo": "CUPOM",
                "num_pdv": cupom.get("num_pdv"), "numero": cupom.get("num_cupom"),
                "coo": cupom.get("coo"), "situacao": cupom.get("situacao"),
            }
        cur.close()
        conn.close()
        return {"success": False, "message": "Nenhum documento fiscal vinculado a esta comanda."}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def get_doc_fiscal(servidor: str, banco: str, comanda: int) -> dict:
    return await asyncio.to_thread(_get_doc_fiscal_sync, servidor, banco, comanda)


def _get_comanda_sync(servidor: str, banco: str, comanda: int) -> dict:
    """Detalhe completo de uma comanda pra tela Alterar Comandas — cabeçalho,
    itens (com vendedor por item), formas de pagamento já lançadas e
    notas/pré-vendas vinculadas. Migração de `FrmAltComNV.frm`."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT c.comanda, c.data, c.valor_venda, c.valor_liquido, c.situacao, c.cliente, "
            "ISNULL(cli.nome, 'CLIENTES DIVERSOS') AS cliente_nome, c.area_atuacao, aa.descricao AS area_atuacao_descricao, "
            "c.paga_comissao, c.atendente, COALESCE(NULLIF(fat.nome_guerra,''), fat.nome) AS atendente_nome, "
            "c.atendente_dav, COALESCE(NULLIF(fad.nome_guerra,''), fad.nome) AS atendente_dav_nome, c.faturar_para "
            "FROM comanda c "
            "LEFT JOIN cliente cli ON cli.codigo = c.cliente "
            "LEFT JOIN area_atuacao aa ON aa.area = c.area_atuacao "
            "LEFT JOIN funcionarios fat ON fat.codigo_int = c.atendente "
            "LEFT JOIN funcionarios fad ON fad.codigo_int = c.atendente_dav "
            "WHERE c.comanda = %s",
            (comanda,),
        )
        cab = cur.fetchone()
        if not cab:
            cur.close()
            conn.close()
            return {"success": False, "message": "Comanda não encontrada."}

        cur.execute(
            "SELECT m.id_mov, m.codigo_int, p.descricao, m.qtd, m.p_unit, m.vendedor, "
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome "
            "FROM movimentacao m "
            "LEFT JOIN pecas p ON p.codigo_int = m.codigo_int "
            "LEFT JOIN funcionarios f ON f.codigo_int = m.vendedor "
            "WHERE m.serie_nf = 'CM' AND m.num_nf = %s AND ISNULL(m.Estornado, 0) = 0",
            (comanda,),
        )
        itens = [
            {
                "id_mov": int(r["id_mov"]), "codigo_int": r.get("codigo_int"), "descricao": r.get("descricao"),
                "qtd": float(r.get("qtd") or 0), "valor_unitario": float(r.get("p_unit") or 0),
                "vendedor": r.get("vendedor"), "vendedor_nome": (r.get("vendedor_nome") or "").strip(),
            }
            for r in cur.fetchall()
        ]

        formas_pag = []
        for tipo, (tabela, col_valor) in _TABELAS_FORMA_PAG.items():
            cur.execute(
                f"SELECT t.sequencia, t.forma_pag, t.{col_valor} AS valor, t.transf_receber, fp.descricao "
                f"FROM {tabela} t LEFT JOIN forma_pagamento fp ON fp.codigo = t.forma_pag "
                f"WHERE t.comanda = %s",
                (comanda,),
            )
            for r in cur.fetchall():
                formas_pag.append({
                    "tipo": tipo, "sequencia": int(r["sequencia"]), "forma_pag": r.get("forma_pag"),
                    "forma_pag_descricao": (r.get("descricao") or "").strip(),
                    "valor": float(r.get("valor") or 0),
                    "conciliado": bool(r.get("transf_receber")),
                    "alteravel": tipo in _TABELAS_ALTERAVEIS and not bool(r.get("transf_receber")),
                })

        cur.execute(
            "SELECT (SELECT TOP 1 ped FROM comanda_ped cp WHERE cp.comanda = c.comanda) AS ped_vinculado, "
            "(SELECT TOP 1 os FROM comanda_os co WHERE co.comanda = c.comanda) AS os_vinculada "
            "FROM comanda c WHERE c.comanda = %s",
            (comanda,),
        )
        vinc = cur.fetchone() or {}
        cur.close()
        conn.close()
        return {
            "success": True,
            "comanda": {
                "comanda": int(cab["comanda"]), "data": cab["data"].isoformat() if cab.get("data") else None,
                "valor_venda": float(cab.get("valor_venda") or 0), "valor_liquido": float(cab.get("valor_liquido") or 0),
                "situacao": (cab.get("situacao") or "").strip(),
                "situacao_label": SITUACAO_LABEL.get((cab.get("situacao") or "").strip(), cab.get("situacao")),
                "cliente": int(cab["cliente"]) if cab.get("cliente") else None,
                "cliente_nome": (cab.get("cliente_nome") or "").strip(),
                "area_atuacao": cab.get("area_atuacao"),
                "area_atuacao_descricao": (cab.get("area_atuacao_descricao") or "").strip(),
                "paga_comissao": bool(cab.get("paga_comissao")),
                "atendente": cab.get("atendente"), "atendente_nome": (cab.get("atendente_nome") or "").strip(),
                "atendente_dav": cab.get("atendente_dav"), "atendente_dav_nome": (cab.get("atendente_dav_nome") or "").strip(),
                "faturar_para": cab.get("faturar_para"),
                "pedido_vinculado": vinc.get("ped_vinculado"), "os_vinculada": vinc.get("os_vinculada"),
            },
            "itens": itens,
            "formas_pagamento": formas_pag,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def get_comanda(servidor: str, banco: str, comanda: int) -> dict:
    return await asyncio.to_thread(_get_comanda_sync, servidor, banco, comanda)


def _save_comanda_sync(req: ComandaGravarRequest, comanda: int) -> dict:
    """Gravar da tela Alterar Comandas — só cabeçalho (atendente/vendedor/
    área/cliente), sem impacto em estoque/fiscal. Migração de
    `CmdGrava_Click` de `FrmAltComNV.frm`."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "ALTERAR_COMANDA", "GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para gravar a comanda."}
        cur.execute("SELECT comanda FROM comanda WHERE comanda = %s", (comanda,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Comanda não encontrada."}
        cur.execute(
            "UPDATE comanda SET area_atuacao = %s, paga_comissao = %s, atendente_dav = %s, "
            "atendente = %s, cliente = %s, faturar_para = %s WHERE comanda = %s",
            (req.area_atuacao, req.paga_comissao, req.atendente_dav, req.atendente, req.cliente, req.faturar_para, comanda),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def save_comanda(req: ComandaGravarRequest, comanda: int) -> dict:
    return await asyncio.to_thread(_save_comanda_sync, req, comanda)


def _alterar_vendedor_item_sync(req: ComandaAlterarVendedorItemRequest, comanda: int) -> dict:
    """Troca o vendedor de UM item (`movimentacao.vendedor`), com opção de
    aplicar aos demais itens da mesma comanda que tinham o vendedor
    anterior — mesma pergunta condicional do legado."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "ALTERAR_COMANDA", "GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para gravar a comanda."}
        cur.execute(
            "SELECT vendedor FROM movimentacao WHERE id_mov = %s AND serie_nf = 'CM' AND num_nf = %s",
            (req.id_mov, comanda),
        )
        item = cur.fetchone()
        if not item:
            conn.close()
            return {"success": False, "message": "Item não encontrado nesta comanda."}
        vendedor_anterior = item.get("vendedor")
        cur.execute("UPDATE movimentacao SET vendedor = %s WHERE id_mov = %s", (req.vendedor, req.id_mov))
        if req.aplicar_aos_demais_itens_do_vendedor_anterior and vendedor_anterior is not None:
            cur.execute(
                "UPDATE movimentacao SET vendedor = %s WHERE serie_nf = 'CM' AND num_nf = %s AND vendedor = %s AND id_mov <> %s",
                (req.vendedor, comanda, vendedor_anterior, req.id_mov),
            )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def alterar_vendedor_item(req: ComandaAlterarVendedorItemRequest, comanda: int) -> dict:
    return await asyncio.to_thread(_alterar_vendedor_item_sync, req, comanda)


def _alterar_forma_pagamento_sync(req: ComandaAlterarFormaPagamentoRequest, comanda: int) -> dict:
    """Troca a forma de pagamento de um lançamento de Cartão/Débito já
    feito — mesma modalidade só (cartão↔cartão, débito↔débito), bloqueado
    se já conciliado no caixa/financeiro (`transf_receber`). Migração de
    `Command12_Click`/`Fpag_LostFocus` de `FrmAltComNV.frm`."""
    tabela = _TABELAS_ALTERAVEIS.get(req.tipo)
    if not tabela:
        return {"success": False, "message": "Só é possível alterar a forma de pagamento de lançamentos de Cartão ou Débito."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "ALTERAR_COMANDA", "FORMA_PAG"):
            conn.close()
            return {"success": False, "message": "Sem permissão para alterar a forma de pagamento."}
        cur.execute(
            f"SELECT sequencia, forma_pag, transf_receber FROM {tabela} WHERE sequencia = %s AND comanda = %s",
            (req.sequencia, comanda),
        )
        lanc = cur.fetchone()
        if not lanc:
            conn.close()
            return {"success": False, "message": "Lançamento não encontrado nesta comanda."}
        if lanc.get("transf_receber"):
            conn.close()
            return {"success": False, "message": "Este lançamento já foi conciliado no caixa/financeiro e não pode mais ser alterado."}
        cur.execute("SELECT tipo FROM forma_pagamento WHERE codigo = %s", (req.forma_pag_nova,))
        fp = cur.fetchone()
        tipo_nova = (fp.get("tipo") or "").strip().upper() if fp else ""
        if tipo_nova != req.tipo:
            conn.close()
            return {"success": False, "message": "A nova forma de pagamento precisa ser da mesma modalidade (Cartão ou Débito)."}
        cur.execute(f"UPDATE {tabela} SET forma_pag = %s WHERE sequencia = %s", (req.forma_pag_nova, req.sequencia))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def alterar_forma_pagamento(req: ComandaAlterarFormaPagamentoRequest, comanda: int) -> dict:
    return await asyncio.to_thread(_alterar_forma_pagamento_sync, req, comanda)


def _list_num_serie_comanda_sync(servidor: str, banco: str, comanda: int) -> dict:
    """Números de série já vinculados a uma comanda (`comanda_num_serie`,
    ligada a `pecas_num_serie` — a mesma tabela auxiliar já gerenciada em
    Tabelas Auxiliares/`FrmManNDS`, aqui só consumida). É uma lista da
    comanda como um todo — o schema não amarra um número de série a um
    item/`movimentacao` específico dentro da comanda."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cns.SEQUENCIA_COMANDA_NUM_SERIE AS sequencia, cns.data, "
            "ns.codigo AS codigo, ns.num_serie, ns.codigo_int, p.descricao "
            "FROM comanda_num_serie cns "
            "JOIN pecas_num_serie ns ON ns.codigo = cns.num_serie "
            "LEFT JOIN pecas p ON p.codigo_int = ns.codigo_int "
            "WHERE cns.comanda = %s ORDER BY cns.data",
            (comanda,),
        )
        items = [
            {
                "sequencia": int(r["sequencia"]), "codigo": int(r["codigo"]),
                "num_serie": (r.get("num_serie") or "").strip(), "codigo_int": r.get("codigo_int"),
                "descricao": (r.get("descricao") or "").strip(),
                "data": r["data"].isoformat() if r.get("data") else None,
            }
            for r in cur.fetchall()
        ]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def list_num_serie_comanda(servidor: str, banco: str, comanda: int) -> dict:
    return await asyncio.to_thread(_list_num_serie_comanda_sync, servidor, banco, comanda)


def _add_num_serie_comanda_sync(req: ComandaAddNumSerieRequest, comanda: int) -> dict:
    """Vincula um número de série já cadastrado (e disponível) a esta
    comanda — mesmo padrão de reserva já usado em Pedido/Pedido de
    Cilindro: só números com `disponivel=1` podem ser escolhidos, e ficam
    marcados `disponivel=0` assim que vinculados."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "ALTERAR_COMANDA", "NUM_SERIE"):
            conn.close()
            return {"success": False, "message": "Sem permissão para gerenciar números de série."}
        cur.execute("SELECT comanda FROM comanda WHERE comanda = %s", (comanda,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Comanda não encontrada."}
        cur.execute("SELECT codigo, disponivel FROM pecas_num_serie WHERE codigo = %s", (req.codigo,))
        ns = cur.fetchone()
        if not ns:
            conn.close()
            return {"success": False, "message": "Número de série não encontrado."}
        if not ns.get("disponivel"):
            conn.close()
            return {"success": False, "message": "Este número de série já está em uso e não está disponível."}
        cur.execute(
            "INSERT INTO comanda_num_serie (comanda, num_serie, data) VALUES (%s, %s, GETDATE())",
            (comanda, req.codigo),
        )
        cur.execute("UPDATE pecas_num_serie SET disponivel = 0 WHERE codigo = %s", (req.codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def add_num_serie_comanda(req: ComandaAddNumSerieRequest, comanda: int) -> dict:
    return await asyncio.to_thread(_add_num_serie_comanda_sync, req, comanda)


def _remove_num_serie_comanda_sync(servidor: str, banco: str, comanda: int, sequencia: int, master: bool, classe: Optional[int]) -> dict:
    """Desvincula um número de série da comanda, liberando-o de volta
    (`disponivel=1`) — o inverso de `_add_num_serie_comanda_sync`."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not master and classe is not None and not tem_permissao(cur, classe, "ALTERAR_COMANDA", "NUM_SERIE"):
            conn.close()
            return {"success": False, "message": "Sem permissão para gerenciar números de série."}
        cur.execute(
            "SELECT num_serie FROM comanda_num_serie WHERE SEQUENCIA_COMANDA_NUM_SERIE = %s AND comanda = %s",
            (sequencia, comanda),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Vínculo não encontrado nesta comanda."}
        cur.execute("DELETE FROM comanda_num_serie WHERE SEQUENCIA_COMANDA_NUM_SERIE = %s", (sequencia,))
        cur.execute("UPDATE pecas_num_serie SET disponivel = 1 WHERE codigo = %s", (row["num_serie"],))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def remove_num_serie_comanda(servidor: str, banco: str, comanda: int, sequencia: int, master: bool, classe: Optional[int]) -> dict:
    return await asyncio.to_thread(_remove_num_serie_comanda_sync, servidor, banco, comanda, sequencia, master, classe)


def _checar_bloqueio_financeiro(cur, comanda: int) -> Optional[str]:
    """Só CHECA (não altera nada) se algum lançamento de pagamento da
    comanda (8 tabelas `comanda_*`) já foi conciliado no caixa/financeiro
    (`transf_receber=1`) — não existe FK de volta da comanda pros
    registros de `duplicata_receber`/`duplicata_rec_venc`/`receber`/
    `previsoes` que teriam sido gerados a partir dali, então apagar essas
    linhas seria adivinhar; nesse caso o ajuste fica manual no financeiro.
    Chamada ANTES de qualquer cancelamento fiscal real (irreversível) ou
    mudança local, pra nunca cancelar no SEFAZ e só depois descobrir que o
    resto do cancelamento está bloqueado."""
    for tabela in _TABELAS_PAGAMENTO_COMANDA:
        cur.execute(f"SELECT TOP 1 1 AS ok FROM {tabela} WHERE comanda = %s AND transf_receber = 1", (comanda,))
        if cur.fetchone():
            return (
                "Esta comanda tem um lançamento de pagamento já conciliado no caixa/financeiro — "
                "não é possível cancelar automaticamente. Ajuste manualmente no financeiro antes de cancelar."
            )
    return None


def _apagar_pagamentos_comanda(cur, comanda: int) -> None:
    """Remove os lançamentos das 8 tabelas `comanda_*` — só chamada depois
    que `_checar_bloqueio_financeiro` já confirmou que nenhum está
    conciliado."""
    for tabela in _TABELAS_PAGAMENTO_COMANDA:
        cur.execute(f"DELETE FROM {tabela} WHERE comanda = %s", (comanda,))


def _ensure_cancelamento_fiscal_cols(cur) -> None:
    """Migração idempotente: colunas de auditoria do cancelamento fiscal
    real (`n_fiscal` — NF-e modelo 55; `comanda_nfce` — NFC-e modelo 65).

    Achado ao vivo 2026-08-23 (1º cancelamento real de NF-e/NFC-e desta
    migração): `_cancelar_comanda_sync` só gravava `situacao='C'` — o
    protocolo de cancelamento e o XML assinado do evento (devolvidos por
    `nfe_cancelamento_service.cancelar_nfe_sync`, ver achado irmão lá)
    eram descartados assim que a função retornava, mesmo o cancelamento
    tendo acontecido de verdade no SEFAZ. Sem essas colunas, não existe
    nenhum jeito de provar/consultar depois QUANDO e com QUE protocolo um
    documento foi cancelado — só um flag binário. Nenhum precedente no
    legado VB6 pra essas colunas (o legado nunca teve cancelamento
    eletrônico real integrado nesta parte do fluxo)."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='protocolo_cancelamento' AND Object_ID=Object_ID('n_fiscal')) "
        "ALTER TABLE n_fiscal ADD protocolo_cancelamento VARCHAR(20) NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='dh_cancelamento' AND Object_ID=Object_ID('n_fiscal')) "
        "ALTER TABLE n_fiscal ADD dh_cancelamento DATETIME NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='motivo_cancelamento' AND Object_ID=Object_ID('n_fiscal')) "
        "ALTER TABLE n_fiscal ADD motivo_cancelamento NVARCHAR(300) NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='xml_cancelamento' AND Object_ID=Object_ID('n_fiscal')) "
        "ALTER TABLE n_fiscal ADD xml_cancelamento NVARCHAR(MAX) NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='protocolo_cancelamento' AND Object_ID=Object_ID('comanda_nfce')) "
        "ALTER TABLE comanda_nfce ADD protocolo_cancelamento VARCHAR(20) NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='dh_cancelamento' AND Object_ID=Object_ID('comanda_nfce')) "
        "ALTER TABLE comanda_nfce ADD dh_cancelamento DATETIME NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='motivo_cancelamento' AND Object_ID=Object_ID('comanda_nfce')) "
        "ALTER TABLE comanda_nfce ADD motivo_cancelamento NVARCHAR(300) NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='xml_cancelamento' AND Object_ID=Object_ID('comanda_nfce')) "
        "ALTER TABLE comanda_nfce ADD xml_cancelamento NVARCHAR(MAX) NULL"
    )


def _cancelar_comanda_sync(req: ComandaCancelarRequest, comanda: int) -> dict:
    """Cancela uma comanda faturada — reversão de estoque, Pedido/O.S.,
    pagamentos e (quando houver protocolo SEFAZ) cancelamento fiscal real,
    via `nfe_cancelamento_service`. Migração de `CmdCancel_Click`
    (`FrmAltComNV.frm`) e `Mod_Pagar.bas` (reversão financeira). Ver
    PENDENCIAS.md > "Gestor de Comandas" > Fase 3 pro escopo exato (o que
    foi e o que não foi portado, e por quê).

    **Nunca chama o SEFAZ de verdade em teste** — `nfe_cancelamento_
    service.cancelar_nfe_sync` já é a peça testada só com certificado
    autoassinado/rede mockada; em produção, esta função chama a peça real
    (que usa o certificado real da empresa, carregado de
    `certificado_digital`) só quando há protocolo SEFAZ preenchido."""
    motivo = (req.motivo or "").strip()
    if len(motivo) < 15:
        return {"success": False, "message": "Informe um motivo com pelo menos 15 caracteres."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "ALTERAR_COMANDA", "CANCELAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar a comanda."}

        cur.execute("SELECT comanda, situacao FROM comanda WHERE comanda = %s", (comanda,))
        cab = cur.fetchone()
        if not cab:
            conn.close()
            return {"success": False, "message": "Comanda não encontrada."}
        sit = (cab.get("situacao") or "").strip().upper()
        if sit == "C":
            conn.close()
            return {"success": False, "message": "Esta comanda já está cancelada."}

        # 1. Bloqueio financeiro checado ANTES de qualquer coisa irreversível
        # (cancelamento fiscal real no SEFAZ) ou mudança local — nunca
        # queremos cancelar no SEFAZ e só depois descobrir que o resto do
        # cancelamento está bloqueado.
        bloqueio = _checar_bloqueio_financeiro(cur, comanda)
        if bloqueio:
            conn.close()
            return {"success": False, "message": bloqueio}

        # 2. Documento fiscal vinculado — cancela de verdade no SEFAZ quando
        # já tem protocolo; sem protocolo (nunca emitido de verdade), só
        # marca cancelado localmente.
        cur.execute(
            "SELECT TOP 1 num_nfce, situacao, protocolo_sefaz, chave_acesso FROM comanda_nfce "
            "WHERE comanda = %s ORDER BY autonum DESC",
            (comanda,),
        )
        nfce = cur.fetchone()
        nf = None
        if not nfce or (nfce.get("situacao") or "").strip().upper() == "C":
            cur.execute(
                "SELECT TOP 1 nf.codigo, nf.situacao, nf.protocolo_sefaz, nf.chave_acesso "
                "FROM comanda_nf cnf JOIN n_fiscal nf ON nf.codigo = cnf.nota_fisc WHERE cnf.comanda = %s",
                (comanda,),
            )
            nf = cur.fetchone()

        doc_ativo = nfce if (nfce and (nfce.get("situacao") or "").strip().upper() != "C") else (
            nf if (nf and (nf.get("situacao") or "").strip().upper() != "C") else None
        )
        if doc_ativo is not None:
            modelo = "65" if doc_ativo is nfce else "55"
            protocolo = (doc_ativo.get("protocolo_sefaz") or "").strip()
            res_fiscal = None
            if protocolo:
                cur.execute("SELECT cgc, uf FROM controle")
                ctrl = cur.fetchone() or {}
                res_fiscal = nfe_cancelamento_service.cancelar_nfe_sync(
                    cur,
                    cnpj=(ctrl.get("cgc") or "").strip(),
                    uf_sigla=(ctrl.get("uf") or "").strip(),
                    modelo=modelo,
                    chave_acesso=(doc_ativo.get("chave_acesso") or "").strip(),
                    protocolo=protocolo,
                    motivo=motivo,
                    tp_amb=nfe_fiscal_common.resolver_tp_amb_sync(cur),
                )
                if not res_fiscal.get("success"):
                    conn.close()
                    return {
                        "success": False,
                        "message": f"Não foi possível cancelar o documento fiscal junto ao SEFAZ: {res_fiscal.get('message')}",
                    }
            # Achado ao vivo 2026-08-23 (1º cancelamento real de NF-e/NFC-e
            # desta migração): antes só `situacao='C'` era gravado — o
            # protocolo/XML/motivo do cancelamento (`res_fiscal`, quando o
            # cancelamento passou pelo SEFAZ de verdade) eram descartados
            # assim que a função retornava, mesmo o cancelamento tendo
            # acontecido de verdade. Ver `_ensure_cancelamento_fiscal_cols`.
            if res_fiscal:
                _ensure_cancelamento_fiscal_cols(cur)
            if modelo == "65":
                if res_fiscal:
                    cur.execute(
                        "UPDATE comanda_nfce SET situacao = 'C', protocolo_cancelamento = %s, "
                        "dh_cancelamento = GETDATE(), motivo_cancelamento = %s, xml_cancelamento = %s "
                        "WHERE comanda = %s",
                        (res_fiscal.get("protocolo_cancelamento"), motivo, res_fiscal.get("xml_evento"), comanda),
                    )
                else:
                    cur.execute("UPDATE comanda_nfce SET situacao = 'C' WHERE comanda = %s", (comanda,))
            else:
                if res_fiscal:
                    cur.execute(
                        "UPDATE n_fiscal SET situacao = 'C', protocolo_cancelamento = %s, "
                        "dh_cancelamento = GETDATE(), motivo_cancelamento = %s, xml_cancelamento = %s "
                        "WHERE codigo = %s",
                        (res_fiscal.get("protocolo_cancelamento"), motivo, res_fiscal.get("xml_evento"), doc_ativo["codigo"]),
                    )
                else:
                    cur.execute("UPDATE n_fiscal SET situacao = 'C' WHERE codigo = %s", (doc_ativo["codigo"],))

        # 3. Reversão financeira — já sabemos que não está bloqueada
        # (checado no passo 1), só apaga os lançamentos agora.
        _apagar_pagamentos_comanda(cur, comanda)

        # 4. Reverter itens — devolve o estoque debitado no Faturar
        # (`pecas.qtd`, nunca `reservado`/`reservado_os` — esses já foram
        # liberados no Faturar, ver `_faturar_pedido_sync`/`_faturar_os_
        # sync`) e marca as linhas de `movimentacao` como estornadas (não
        # DELETE — a coluna `Estornado` já existe pronta pra isso).
        cur.execute(
            "SELECT codigo_int, qtd FROM movimentacao WHERE serie_nf = 'CM' AND num_nf = %s AND ISNULL(Estornado, 0) = 0",
            (comanda,),
        )
        for it in cur.fetchall():
            produto = (it.get("codigo_int") or "").strip()
            qtd = float(it.get("qtd") or 0)
            if produto and qtd:
                cur.execute("UPDATE pecas SET qtd = ISNULL(qtd, 0) + %s WHERE codigo_int = %s", (qtd, produto))
        cur.execute(
            "UPDATE movimentacao SET Estornado = 1 WHERE serie_nf = 'CM' AND num_nf = %s AND ISNULL(Estornado, 0) = 0",
            (comanda,),
        )

        # 5. Reverter Pedido de Venda / COMANDA_PED (volta pra Fechado, não
        # Cancelado — o usuário pode reabrir/corrigir e faturar de novo).
        cur.execute("SELECT ped FROM comanda_ped WHERE comanda = %s", (comanda,))
        ped_row = cur.fetchone()
        if ped_row:
            cur.execute("UPDATE pedido_venda SET situacao = 'F' WHERE pedido = %s", (ped_row["ped"],))
            cur.execute("DELETE FROM comanda_ped WHERE comanda = %s", (comanda,))

        # 6. Reverter O.S. / COMANDA_OS (mesma lógica).
        cur.execute("SELECT os FROM comanda_os WHERE comanda = %s", (comanda,))
        os_row = cur.fetchone()
        if os_row:
            cur.execute("UPDATE os SET situacao = 'F' WHERE codigo = %s", (os_row["os"],))
            cur.execute("DELETE FROM comanda_os WHERE comanda = %s", (comanda,))

        # 7. Números de série — libera de volta (`disponivel=1`).
        cur.execute("SELECT num_serie FROM comanda_num_serie WHERE comanda = %s", (comanda,))
        for r in cur.fetchall():
            cur.execute("UPDATE pecas_num_serie SET disponivel = 1 WHERE codigo = %s", (r["num_serie"],))
        cur.execute("DELETE FROM comanda_num_serie WHERE comanda = %s", (comanda,))

        # 8. Zera a comanda e registra o cancelamento.
        cur.execute("SELECT TOP 1 num_cupom FROM comanda_cupom WHERE comanda = %s", (comanda,))
        cupom_row = cur.fetchone()
        cupom = cupom_row.get("num_cupom") if cupom_row else None
        cur.execute(
            "UPDATE comanda SET situacao = 'C', valor_venda = 0, acrescimo = 0, desconto = 0 WHERE comanda = %s",
            (comanda,),
        )
        cur.execute(
            "INSERT INTO cancelamento (comanda, cupom, usuario, data, hora, motivo) "
            "VALUES (%s, %s, %s, CONVERT(date, GETDATE()), CONVERT(varchar(8), GETDATE(), 108), %s)",
            (comanda, cupom, req.usuario_alteracao or 0, motivo),
        )

        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def cancelar_comanda(req: ComandaCancelarRequest, comanda: int) -> dict:
    return await asyncio.to_thread(_cancelar_comanda_sync, req, comanda)


def _emitir_nfce_comanda_sync(req: EmitirNfceRequest, comanda: int) -> dict:
    """Emite uma NFC-e real (SEFAZ) pra uma comanda já faturada — Fase 1 do
    pacote de emissão fiscal (ver `nfe_emissao_service.py` e o plano de
    implementação). Resolve tributação por item (`_resolver_tributacao_
    sync`, porta de `SitTribut()`), monta/assina/transmite (`emitir_nfce_
    sync`) e grava o resultado em `n_fiscal`/`comanda_nfce`/`comanda_nf`.

    **Nunca chame isto de verdade contra uma conexão com certificado real
    em teste/desenvolvimento** — só com `nfe_emissao_service.emitir_nfce_
    sync`/`nfe_fiscal_common.transmitir` mockados. Ver docstring do módulo
    de emissão."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "ALTERAR_COMANDA", "EMITIR_NF"):
            conn.close()
            return {"success": False, "message": "Sem permissão para emitir nota fiscal."}
        if not nfe_fiscal_common.modulo_nfce_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFCe está desativado — fale com o administrador do sistema."}

        cur.execute("SELECT comanda, situacao, cliente, valor_venda FROM comanda WHERE comanda = %s", (comanda,))
        cab = cur.fetchone()
        if not cab:
            conn.close()
            return {"success": False, "message": "Comanda não encontrada."}
        if (cab.get("situacao") or "").strip().upper() != "PG":
            conn.close()
            return {"success": False, "message": "Só é possível emitir nota fiscal de uma comanda faturada."}

        cur.execute(
            "SELECT TOP 1 1 AS ok FROM comanda_nfce WHERE comanda = %s AND situacao <> 'C'",
            (comanda,),
        )
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Esta comanda já tem uma NFC-e emitida."}

        cliente = None
        if cab.get("cliente"):
            cur.execute(
                "SELECT cgc_cpf, credita_icms, consumidor_final, ISNULL(inscr_est, '') AS inscr_est "
                "FROM cliente WHERE codigo = %s",
                (cab["cliente"],),
            )
            cliente = cur.fetchone()

        cur.execute(
            # JOIN (não LEFT JOIN) — achado ao vivo 2026-07-21: uma comanda
            # pode misturar itens de produto e de serviço (ex.: peça + mão de
            # obra numa auto center); o LEFT JOIN incluiria o item de serviço
            # aqui também, com colunas de tributação de produto vazias,
            # corrompendo a NFC-e. Itens de serviço vão pra NFS-e à parte
            # (ver `_emitir_nfse_comanda_sync`).
            "SELECT m.codigo_int, p.descricao, m.qtd, m.p_unit, p.cod_icms, p.origem, "
            "p.codigo_mercosul AS ncm, p.uni AS unidade "
            "FROM movimentacao m JOIN pecas p ON p.codigo_int = m.codigo_int "
            "WHERE m.serie_nf = 'CM' AND m.num_nf = %s AND ISNULL(m.Estornado, 0) = 0",
            (comanda,),
        )
        itens_mov = cur.fetchall()
        if not itens_mov:
            conn.close()
            return {"success": False, "message": "Comanda sem itens de produto — nada a emitir."}

        cur.execute("SELECT cgc, uf, rz_social FROM controle")
        controle = cur.fetchone() or {}
        cur.execute(
            "SELECT numero_nfce, serie_nfce, csc, csc_hash, SERVICO_FRETE_NFCE, TRANSPORTADOR_FRETE_NFCE FROM controle_aux"
        )
        controle_aux = cur.fetchone() or {}

        # Frete da NFC-e — achado real 2026-08-22 (mesma reauditoria do
        # "Frete por Conta" da NF-e, ver `nfe_emissao_service._resolver_
        # mod_frete`): regra DIFERENTE daquela, não um seletor de tipo —
        # aqui é um item de SERVIÇO na própria comanda (identificado por
        # `controle_aux.SERVICO_FRETE_NFCE`, já exposto em Controle do
        # Sistema mas nunca lido na emissão) cuja soma vira `<vFrete>` e
        # decide `modFrete` (`DAO_NFE.vb:2736-2745`/`5436-5476`, ramo
        # `ModeloNota="65"`). `modFrete=1` só quando esse item tem valor >
        # 0 nesta comanda; senão `9` (sem transporte) — mesmo default de
        # antes, agora resolvido de verdade em vez de hardcoded.
        frete_valor = 0.0
        transportador = None
        servico_frete_cod = (controle_aux.get("SERVICO_FRETE_NFCE") or "").strip()
        if servico_frete_cod:
            cur.execute(
                "SELECT ISNULL(SUM(qtd*p_unit), 0) AS total FROM movimentacao "
                "WHERE num_nf = %s AND serie_nf = 'CM' AND codigo_int = %s AND ISNULL(Estornado, 0) = 0",
                (comanda, servico_frete_cod),
            )
            frete_valor = float((cur.fetchone() or {}).get("total") or 0)
            transportador_codigo_int = int(controle_aux.get("TRANSPORTADOR_FRETE_NFCE") or 0)
            if frete_valor > 0 and transportador_codigo_int > 0:
                cur.execute(
                    "SELECT codigo, nome, inscr_est FROM fornecedor WHERE codigo_int = %s",
                    (transportador_codigo_int,),
                )
                forn = cur.fetchone()
                if forn:
                    cur.execute(
                        "SELECT TOP 1 endereco, numero, complemento, bairro, cidade, uf FROM fornecedor_end WHERE codigo = %s",
                        (transportador_codigo_int,),
                    )
                    end = cur.fetchone() or {}
                    endereco = " ".join(
                        p for p in [
                            (end.get("endereco") or "").strip(),
                            str(end.get("numero")) if end.get("numero") else "",
                            (end.get("complemento") or "").strip(),
                            (end.get("bairro") or "").strip(),
                        ] if p
                    )
                    transportador = {
                        "cgc_cpf": (forn.get("codigo") or "").strip(), "nome": forn.get("nome"),
                        "ie": forn.get("inscr_est"), "endereco": endereco,
                        "cidade": end.get("cidade"), "uf": end.get("uf"),
                    }

        uf_sigla = (controle.get("uf") or "").strip().upper()
        cgc_cpf = (cliente.get("cgc_cpf") or "").strip() if cliente else ""
        nao_contribuinte = bool(cliente) and (len(cgc_cpf) == 11 or not (cliente.get("inscr_est") or "").strip())
        simples_nacional_cliente = bool(cliente and cliente.get("credita_icms"))
        consumidor_final = bool(cliente and cliente.get("consumidor_final")) if cliente else True

        itens_resolvidos = []
        ibs_cbs_calculados = []  # ver ibs_cbs_service.calcular_totais_ibs_cbs abaixo
        for item in itens_mov:
            codigo_int = (item.get("codigo_int") or "").strip()
            cod_icms = (item.get("cod_icms") or "").strip()
            cur.execute("SELECT TOP 1 1 AS ok FROM PECAS_PROTOCOLO_ST WHERE uf = %s AND codigo_int = %s", (uf_sigla, codigo_int))
            protocolo_st = cur.fetchone() is not None
            tributos = nfe_emissao_service._resolver_tributacao_sync(
                cur, cod_icms=cod_icms, cfop_cupom_fiscal="", tipo_mov="S01",
                uf_destino=uf_sigla, uf_controle=uf_sigla, nao_contribuinte=nao_contribuinte,
                simples_nacional_cliente=simples_nacional_cliente, consumidor_final=consumidor_final,
                protocolo_st=protocolo_st,
            )
            if not tributos:
                conn.close()
                return {"success": False, "message": f"Produto '{codigo_int}' sem tributação cadastrada em Taxas (Tabelas Auxiliares)."}
            qtd = float(item.get("qtd") or 0)
            valor_unitario = float(item.get("p_unit") or 0)
            # IBS/CBS usa uma resolução PRÓPRIA, diferente da cascata de
            # `tributos` acima (essa é só pro sistema tributário antigo —
            # ICMS/CSOSN/PIS/COFINS) — ver docstring de
            # `resolver_taxa_nfce_para_ibs_cbs_sync`, achado 2026-08-19.
            taxa_nfce = ibs_cbs_service.resolver_taxa_nfce_para_ibs_cbs_sync(cur, cod_icms=cod_icms, destino=uf_sigla)
            ibs_cbs_item = (
                ibs_cbs_service.calcular_item_ibs_cbs(qtd=qtd, p_unit=valor_unitario, codigo_int=codigo_int, taxa=taxa_nfce)
                if taxa_nfce else None
            )
            ibs_cbs_calculados.append(ibs_cbs_item)
            itens_resolvidos.append({
                "codigo_int": codigo_int, "descricao": (item.get("descricao") or "").strip(),
                "ncm": (item.get("ncm") or "").strip(), "cfop": tributos.get("cfop_livro") or "5102",
                "unidade": (item.get("unidade") or "UN").strip(), "qtd": qtd, "valor_unitario": valor_unitario,
                "valor_total": round(qtd * valor_unitario, 2), "origem": int(item.get("origem") or 0),
                "csosn": "102" if simples_nacional_cliente else "400",
                "cst_pis": "07", "cst_cofins": "07",
                "ibs_cbs_xml": (ibs_cbs_item or {}).get("xml_item") or "",
            })

        ibs_cbs_totais = ibs_cbs_service.calcular_totais_ibs_cbs(ibs_cbs_calculados)
        # `valor_total` = soma SÓ dos itens de PRODUTO (+ frete) — achado
        # ao vivo 2026-08-23 (1ª emissão real de NFC-e com comanda mista
        # produto+serviço): usar `cab.valor_venda` (valor da comanda
        # INTEIRA, incluindo serviço) faz `<vNF>` divergir da soma real
        # dos itens da NFC-e — SEFAZ recusa (rejeição 610, "Total da NF
        # difere do somatorio dos Valores"). Numa comanda só de produto,
        # os dois valores coincidiam por acaso, por isso nunca foi pego
        # antes (nunca testado ao vivo com comanda mista até hoje).
        valor_total_nfce = sum(float(i.get("valor_total") or 0) for i in itens_resolvidos) + frete_valor
        # Contingência (Gestor NFCe, achado 2026-08-19) — se aberta, a
        # emissão segue um caminho alternativo (tpEmis 5/9, sem
        # transmissão) — ver docstring de `emitir_nfce_sync`.
        contingencia = contingencia_nfce_service.contingencia_aberta_sync(cur)
        resultado = nfe_emissao_service.emitir_nfce_sync(
            cur, comanda=comanda, cnpj_emit=(controle.get("cgc") or ""), nome_emit=(controle.get("rz_social") or ""),
            uf_sigla=uf_sigla, uf_controle_sigla=uf_sigla,
            proximo_numero=int(controle_aux.get("numero_nfce") or 0) + 1,
            serie=str(controle_aux.get("serie_nfce") or "1"), cliente=cliente, itens_resolvidos=itens_resolvidos,
            forma_pagamento="01", valor_total=valor_total_nfce,
            tp_amb=nfe_fiscal_common.resolver_tp_amb_sync(cur),
            csc_id=str(controle_aux.get("csc") or ""), csc=(controle_aux.get("csc_hash") or ""),
            ibs_cbs_totais_xml=ibs_cbs_totais["xml_totais"], contingencia=contingencia,
            frete_valor=frete_valor, transportador=transportador,
        )
        if not resultado.get("success"):
            conn.close()
            return resultado

        situacao_n_fiscal = resultado.get("situacao") or "A"
        cstat_n_fiscal = resultado.get("cstat") or "100"
        # `resultado["dh_recbto"]` vem cru do SEFAZ (ISO 8601 com offset,
        # ex. "-03:00") — gravar direto numa coluna DATETIME quebra a
        # conversão e derruba a transação DEPOIS do SEFAZ já ter
        # confirmado sucesso, perdendo o registro local de um documento
        # genuinamente autorizado (achado ao vivo no MDF-e, 2026-08-23 —
        # ver `parse_dh_sefaz`). Corrigido aqui 2026-08-24 (mesmo bug,
        # nunca reproduzido ao vivo pra NFC-e só por sorte de coincidência
        # de formato de coluna).
        cur.execute(
            "INSERT INTO n_fiscal (num_nf, serie_nf, uf, data_nf, data_mov, valor_total, situacao, "
            "chave_acesso, protocolo_sefaz, dhRecbto, cstat, xml) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s, %s, %s, CONVERT(date, GETDATE()), CONVERT(date, GETDATE()), %s, %s, %s, %s, %s, %s, %s)",
            (resultado["numero"], resultado["serie"], uf_sigla, valor_total_nfce, situacao_n_fiscal,
             resultado["chave_acesso"], resultado["protocolo_sefaz"], nfe_fiscal_common.parse_dh_sefaz(resultado.get("dh_recbto")), cstat_n_fiscal, resultado["xml"]),
        )
        codigo_n_fiscal = int(cur.fetchone()["codigo"])
        cur.execute(
            "INSERT INTO comanda_nfce (comanda, num_nfce, situacao, protocolo_sefaz, chave_acesso, dhemi, vnf, xml) "
            "VALUES (%s, %s, %s, %s, %s, GETDATE(), %s, %s)",
            (comanda, resultado["numero"], ("G" if situacao_n_fiscal == "G" else "F"), resultado["protocolo_sefaz"],
             resultado["chave_acesso"], valor_total_nfce, resultado["xml"]),
        )
        cur.execute("INSERT INTO comanda_nf (comanda, nota_fisc, tipo, situacao) VALUES (%s, %s, 1, %s)", (comanda, codigo_n_fiscal, situacao_n_fiscal))
        cur.execute("UPDATE controle_aux SET numero_nfce = %s", (resultado["numero"],))
        conn.commit()
        cur.close()
        conn.close()
        return resultado
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def emitir_nfce_comanda(req: EmitirNfceRequest, comanda: int) -> dict:
    return await asyncio.to_thread(_emitir_nfce_comanda_sync, req, comanda)


def _modulo_sefin_nacional_ativo(cur) -> bool:
    """True se `controle_configuracao.sefin_nacional` está ligado — mesmo
    padrão de `pedido_common._modulo_servicos_ativo` ("Regra de Módulo
    Ativo", CLAUDE.md). Emissão de NFS-e via DPS Nacional só é permitida
    com o módulo ativo."""
    cur.execute("SELECT TOP 1 sefin_nacional FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("sefin_nacional") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


# `_resolver_cod_municipio_ibge` foi movida pra `nfe_fiscal_common.
# resolver_cod_municipio_ibge` 2026-08-19 (virou necessária também pro
# destinatário de NF-e modelo 55 em `nfe_agrupada_service.py`) — mantido
# aqui só o alias pra não precisar tocar em todo call site já existente
# neste arquivo.
_resolver_cod_municipio_ibge = nfe_fiscal_common.resolver_cod_municipio_ibge


def _emitir_nfse_comanda_sync(req: EmitirNfseRequest, comanda: int) -> dict:
    """Emite uma NFS-e real (DPS Nacional/Sefin Nacional) pra uma comanda já
    faturada com itens de serviço — Fase 3 do pacote de emissão fiscal (ver
    `nfse_emissao_service.py` e o plano de implementação). Espelha
    `_emitir_nfce_comanda_sync`, mas resolve itens de SERVIÇO (join com
    `servicos`, não `pecas`) — achado confirmado ao vivo 2026-07-21: uma
    comanda desta empresa pode ter itens de produto E de serviço misturados
    (ex.: peça + mão de obra de alinhamento numa auto center), por isso uma
    mesma comanda pode ter tanto uma NFC-e quanto uma NFS-e vinculadas
    (`comanda_nf.tipo` 1 e 2 respectivamente — confirmado com dados reais já
    existindo com os dois valores).

    **Nunca chame isto de verdade contra uma conexão com certificado real em
    teste/desenvolvimento** — mesma ressalva de `_emitir_nfce_comanda_sync`."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "ALTERAR_COMANDA", "EMITIR_NFSE"):
            conn.close()
            return {"success": False, "message": "Sem permissão para emitir nota fiscal de serviço."}

        if not _modulo_sefin_nacional_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo SEFIN Nacional não está ativo (Módulos e Recursos)."}

        cur.execute("SELECT comanda, situacao, cliente, valor_venda FROM comanda WHERE comanda = %s", (comanda,))
        cab = cur.fetchone()
        if not cab:
            conn.close()
            return {"success": False, "message": "Comanda não encontrada."}
        if (cab.get("situacao") or "").strip().upper() != "PG":
            conn.close()
            return {"success": False, "message": "Só é possível emitir nota fiscal de uma comanda faturada."}

        cur.execute(
            "SELECT TOP 1 1 AS ok FROM comanda_nf WHERE comanda = %s AND tipo = 2 AND situacao <> 'C'",
            (comanda,),
        )
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Esta comanda já tem uma NFS-e emitida."}

        cur.execute(
            "SELECT m.codigo_int, s.descricao, s.cod_lista_servico, s.cod_icms, s.cod_servico_municipio, "
            "m.qtd, m.p_unit "
            "FROM movimentacao m JOIN servicos s ON s.codigo = m.codigo_int "
            "WHERE m.serie_nf = 'CM' AND m.num_nf = %s AND ISNULL(m.Estornado, 0) = 0",
            (comanda,),
        )
        itens_mov = cur.fetchall()
        if not itens_mov:
            conn.close()
            return {"success": False, "message": "Comanda sem itens de serviço — nada a emitir."}

        cur.execute("SELECT cgc, cidade, uf, simples_servico FROM controle")
        controle = cur.fetchone() or {}
        cur.execute(
            "SELECT numero_DPS, serie_DPS, opcao_simples, RegimeEspecialTributacao, codigo_nbs FROM controle_aux"
        )
        controle_aux = cur.fetchone() or {}

        # IBS/CBS do serviço principal — só CST/cClassTrib são enviados no
        # XML da DPS durante a fase de transição (ver docstring de
        # `nfse_emissao_service._montar_xml_dps`); mesma simplificação já
        # existente de "uma DPS = um serviço principal" (só o primeiro item
        # é considerado). Resolução PRÓPRIA de `taxas_nfce` por `cod_icms` +
        # `destino` (UF da própria empresa, nunca a do cliente) +
        # `tipo_mov` fixo `"S01"` — mesma função usada pro lado NFC-e, ver
        # docstring de `resolver_taxa_nfce_para_ibs_cbs_sync` (valores
        # confirmados diretamente pelo usuário 2026-08-19, não inferidos).
        ibs_cbs_cst = ""
        ibs_cbs_classtrib = ""
        cod_icms_serv = (itens_mov[0].get("cod_icms") or "").strip()
        uf_sigla_serv = (controle.get("uf") or "").strip().upper()
        if cod_icms_serv and uf_sigla_serv:
            taxa_nfce_serv = ibs_cbs_service.resolver_taxa_nfce_para_ibs_cbs_sync(
                cur, cod_icms=cod_icms_serv, destino=uf_sigla_serv,
            )
            if taxa_nfce_serv:
                qtd0 = float(itens_mov[0].get("qtd") or 0)
                p_unit0 = float(itens_mov[0].get("p_unit") or 0)
                ibs_cbs_serv = ibs_cbs_service.calcular_item_ibs_cbs(
                    qtd=qtd0, p_unit=p_unit0, codigo_int=(itens_mov[0].get("codigo_int") or ""),
                    taxa=taxa_nfce_serv,
                )
                if ibs_cbs_serv:
                    ibs_cbs_cst = ibs_cbs_serv["cst_ibs_uf"]
                    ibs_cbs_classtrib = ibs_cbs_serv["classtrib_ibs_uf"]

        cod_municipio = _resolver_cod_municipio_ibge(controle.get("cidade"), controle.get("uf"))
        if not cod_municipio:
            conn.close()
            return {
                "success": False,
                "message": (
                    f"Código de município (IBGE) não conhecido para '{controle.get('cidade')}/{controle.get('uf')}' — "
                    "cadastre-o em `_MUNICIPIOS_IBGE_CONHECIDOS` (comanda_service.py) antes de emitir."
                ),
            }

        tomador = None
        if cab.get("cliente"):
            cur.execute("SELECT cgc_cpf, nome FROM cliente WHERE codigo = %s", (cab["cliente"],))
            tomador = cur.fetchone()

        itens = [
            {
                "codigo_int": (item.get("codigo_int") or "").strip(),
                "descricao": (item.get("descricao") or "").strip(),
                "cod_lista_servico": (item.get("cod_lista_servico") or "").strip(),
                "cod_servico_municipio": (item.get("cod_servico_municipio") or "").strip(),
                "valor": round(float(item.get("qtd") or 0) * float(item.get("p_unit") or 0), 2),
            }
            for item in itens_mov
        ]

        resultado = nfse_emissao_service.emitir_nfse_sync(
            cur, comanda=comanda, cnpj_prest=(controle.get("cgc") or ""), cod_municipio=cod_municipio,
            opcao_simples_nacional=bool(controle_aux.get("opcao_simples")),
            regime_especial_tributacao=int(controle_aux.get("RegimeEspecialTributacao") or 0),
            proximo_numero=int(controle_aux.get("numero_DPS") or 0) + 1,
            serie=str(controle_aux.get("serie_DPS") or "1"), tomador=tomador, itens=itens,
            tp_amb=nfe_fiscal_common.resolver_tp_amb_sync(cur),
            ibs_cbs_cst=ibs_cbs_cst, ibs_cbs_classtrib=ibs_cbs_classtrib,
            codigo_nbs=(controle_aux.get("codigo_nbs") or ""),
            simples_servico_pct=float(controle.get("simples_servico") or 0),
        )
        if not resultado.get("success"):
            conn.close()
            return resultado

        valor_total = sum(i["valor"] for i in itens)
        # `dps` e `n_fiscal`/`comanda_nf` são tabelas DISTINTAS, pra
        # FUNÇÕES distintas — confirmado pelo usuário 2026-07-21 com a
        # mesma relação já conhecida deste projeto entre `pedido_venda` e
        # `comanda` (pré-venda/declaração vs. registro definitivo da
        # venda/nota, ver "toda venda finalizada... vira um registro em
        # comanda" no restante deste arquivo). `dps` é o registro próprio
        # da declaração/DPS (usado pela rotina de impressão `Mdl_Imp_XML.
        # bas::DanfeNFSE`, tem sua própria numeração `num_dps`/`serie_dps`
        # em `controle_aux`); `n_fiscal`/`comanda_nf` é o registro
        # definitivo de nota fiscal (qualquer tipo — confirmado central
        # por `GravaNFE`, `Geral\ModNF.bas` linha 7468), o que o resto do
        # sistema (relatórios, Fechamento de Caixa, Gestor de Comandas)
        # já lê pra qualquer documento fiscal. `emitir_nfse_sync` resolve
        # as duas coisas numa única chamada síncrona (constrói a DPS,
        # assina, transmite, recebe a autorização), então os dois
        # registros são gravados juntos, no mesmo commit.
        cur.execute(
            "INSERT INTO dps (comanda, num_dps, serie_dps, data_dps, hora_dps, valor_total, situacao, STATUS, "
            "chave_acesso_dps, chave_acesso_nfse, XML_NFSE) "
            "VALUES (%s, %s, %s, CONVERT(date, GETDATE()), CONVERT(varchar(8), GETDATE(), 108), %s, 'A', 'Transmitida', %s, %s, %s)",
            (comanda, resultado["numero"], resultado["serie"], valor_total,
             resultado.get("id_dps"), resultado.get("chave_acesso"), resultado.get("xml_nfse")),
        )
        cur.execute(
            "INSERT INTO n_fiscal (num_nf, serie_nf, data_nf, data_mov, valor_total, situacao_nfse, chave_acesso, xml) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s, %s, CONVERT(date, GETDATE()), CONVERT(date, GETDATE()), %s, 1, %s, %s)",
            (resultado["numero"], resultado["serie"], valor_total, resultado["chave_acesso"],
             resultado.get("xml_nfse") or resultado["xml_dps"]),
        )
        codigo_n_fiscal = int(cur.fetchone()["codigo"])
        cur.execute(
            "INSERT INTO comanda_nf (comanda, nota_fisc, tipo, situacao) VALUES (%s, %s, 2, 'A')",
            (comanda, codigo_n_fiscal),
        )
        cur.execute("UPDATE controle_aux SET numero_DPS = %s", (resultado["numero"],))
        conn.commit()
        cur.close()
        conn.close()
        return resultado
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def emitir_nfse_comanda(req: EmitirNfseRequest, comanda: int) -> dict:
    return await asyncio.to_thread(_emitir_nfse_comanda_sync, req, comanda)

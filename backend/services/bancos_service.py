"""Financeiro > Cobranças — cadastro de Bancos (Fase 1). Ver
models/bancos.py e PENDENCIAS.md > "Bancos (Cadastro de Cobrança / Boleto /
CNAB)" para o desenho completo e o histórico da decisão de escopo.

Tabela `bancos` já existe no schema (usada pelos clientes que ainda rodam o
VB6) — confirmado ao vivo em GERDELL/BARESTELA 2026-07-23, 53 colunas, PK
`cod` IDENTITY. Este service não roda nenhuma migração/DDL (diferente da
maioria dos módulos novos deste projeto) porque a tabela é pré-existente.

Colunas do schema **deliberadamente fora desta Fase 1** (existem mas não são
lidas/gravadas por este service, por não terem mapeamento confirmado contra
o `.frm` colado pelo usuário — ver "Regras Importantes" no CLAUDE.md, nunca
assumir função de campo sem confirmação):
  • `nome_remessa`, `cod_carteira`, `Tarifa_Boleto` — colunas extras no
    schema sem equivalente visível no formulário legado pasteado.
  • `certificado_digital`/`certificado_digital_auxiliar` (varbinary) — fica
    pra quando a Fase 2b (motor de API) escolher um provedor específico e
    confirmar se aquele provedor exige certificado cliente.
  • `remessa`/`data_remessa` — preenchidos automaticamente pelo motor de
    remessa do legado (nunca pelo formulário manual, `Campo(23)` é
    `Enabled=False` no `.frm`); aqui são só exibidos (somente leitura), não
    fazem parte do save.

Muitos campos numéricos do legado (`tipo_cobranca`, `tipo_multa`,
`incidencia_multa`, `codigo_protesto`, `codigo_baixa`, `tipo_registro`,
`emissao_boleto`, `distribui_boleto`, `especie_doc`) eram preenchidos por
combos (`List1`..`List9`) cujo texto das opções está embutido no recurso
binário `.frx` do form, não no `.frm` texto colado — sem o texto real dessas
opções, os campos ficam como código numérico simples aqui (sem dropdown de
rótulo amigável). Ver PENDENCIAS.md para o registro desse gap.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc

# Único FK real que aponta pra `bancos.cod` (confirmado via sys.foreign_keys
# ao vivo). O legado também bloqueava a exclusão contra `duplicata_rec_venc`,
# mas por uma chave de negócio composta (codigo+contacorrente+carteira, não
# o PK `cod`) — replicado abaixo fielmente (ver docstring da função de
# delete), já que instalações que migraram do VB6 podem ter linhas antigas
# lá referenciando um banco por essa combinação.


def _row_str(row: dict, key: str) -> str:
    v = row.get(key)
    return (v or "").strip() if isinstance(v, str) else str(v or "")


def _to_item(row: dict) -> dict:
    return {
        "cod": row.get("cod"),
        "codigo": int(row.get("codigo") or 0),
        "digito_banco": int(row.get("digito_banco") or 0),
        "descricao": _row_str(row, "descricao"),
        "descr_arquivo": _row_str(row, "descr_arquivo"),
        "agencia": int(row.get("agencia") or 0),
        "dv_agencia": _row_str(row, "dv_agencia"),
        "conta_corrente": int(row.get("contacorrente") or 0),
        "dv_conta_corrente": _row_str(row, "dv_contacorrente"),
        "dv_agencia_conta": _row_str(row, "dv_agencia_conta"),
        "situacao": _row_str(row, "situacao") or "A",
        "carteira": int(row.get("carteira") or 0),
        "variacao_carteira": int(row.get("VARIACAO_CARTEIRA") or 0),
        "codigo_cedente": _row_str(row, "codigocedente"),
        "cod_transmissao": _row_str(row, "Cod_Transmissao"),
        "contrato": float(row.get("contrato") or 0),
        "especie_doc": int(row.get("especie_doc") or 0),
        "aceite": _row_str(row, "aceite") or "N",
        "tarifa_cobranca": float(row.get("tarifa_cobranca") or 0),
        "incidencia_multa": int(row.get("incidencia_multa") or 0),
        "dias_multa": int(row.get("dias_multa") or 0),
        "tipo_multa": int(row.get("tipo_multa") or 0),
        "multa_atraso_pag": float(row.get("Multa_Atraso_Pag") or 0),
        "mora_dia_pag": float(row.get("Mora_Dia_Pag") or 0),
        "dias_protesto": int(row.get("dias_protesto") or 0),
        "codigo_protesto": int(row.get("codigo_protesto") or 0),
        "dias_baixa": int(row.get("dias_baixa") or 0),
        "codigo_baixa": int(row.get("codigo_baixa") or 0),
        "tipo_cobranca": int(row.get("tipo_cobranca") or 0),
        "tipo_registro": int(row.get("tipo_registro") or 0),
        "emissao_boleto": int(row.get("emissao_boleto") or 0),
        "distribui_boleto": int(row.get("distribui_boleto") or 0),
        "numero_boleto": float(row.get("numero_boleto") or 0),
        "instr_cobranca_1": int(row.get("instr_cobranca_1") or 0),
        "instr_cobranca_2": int(row.get("instr_cobranca_2") or 0),
        "titulo_boleto": _row_str(row, "tituloboleto"),
        "mensagem_boleto_1": _row_str(row, "mensagem_boleto_1"),
        "mensagem_boleto_2": _row_str(row, "mensagem_boleto_2"),
        "mensagem_boleto_3": _row_str(row, "mensagem_boleto_3"),
        "endereco_remessa": _row_str(row, "end_remessa"),
        "endereco_retorno": _row_str(row, "end_retorno"),
        "integracao_api": bool(row.get("integracao_api")),
        "chave_api_1": _row_str(row, "chave_api"),
        "chave_api_2": _row_str(row, "chave_api_2"),
        "chave_api_3": _row_str(row, "chave_api_3"),
        "chave_api_4": _row_str(row, "chave_api_4"),
        "numero_ultima_remessa": int(row.get("remessa") or 0),
        "data_ultima_remessa": str(row.get("data_remessa")) if row.get("data_remessa") else None,
    }


_SELECT_COLS = (
    "cod, codigo, digito_banco, descricao, descr_arquivo, agencia, dv_agencia, "
    "contacorrente, dv_contacorrente, dv_agencia_conta, situacao, carteira, "
    "VARIACAO_CARTEIRA, codigocedente, Cod_Transmissao, contrato, especie_doc, "
    "aceite, tarifa_cobranca, incidencia_multa, dias_multa, tipo_multa, "
    "Multa_Atraso_Pag, Mora_Dia_Pag, dias_protesto, codigo_protesto, dias_baixa, "
    "codigo_baixa, tipo_cobranca, tipo_registro, emissao_boleto, distribui_boleto, "
    "numero_boleto, instr_cobranca_1, instr_cobranca_2, tituloboleto, "
    "mensagem_boleto_1, mensagem_boleto_2, mensagem_boleto_3, end_remessa, "
    "end_retorno, integracao_api, chave_api, chave_api_2, chave_api_3, chave_api_4, "
    "remessa, data_remessa"
)


def _list_bancos_sync(servidor: str, banco: str, busca: Optional[str] = None) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if busca and busca.strip():
            where = "WHERE descricao LIKE %s OR CAST(codigo AS NVARCHAR(10)) LIKE %s"
            termo = f"%{busca.strip()}%"
            params = (termo, termo)
        cur.execute(f"SELECT cod, codigo, descricao, agencia, contacorrente, carteira, situacao, integracao_api "
                    f"FROM bancos {where} ORDER BY descricao", params)
        items = [{
            "cod": r.get("cod"),
            "codigo": int(r.get("codigo") or 0),
            "descricao": _row_str(r, "descricao"),
            "agencia": int(r.get("agencia") or 0),
            "conta_corrente": int(r.get("contacorrente") or 0),
            "carteira": int(r.get("carteira") or 0),
            "situacao": _row_str(r, "situacao") or "A",
            "integracao_api": bool(r.get("integracao_api")),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _get_banco_sync(servidor: str, banco: str, cod: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(f"SELECT {_SELECT_COLS} FROM bancos WHERE cod=%s", (cod,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": False, "message": "Banco não encontrado."}
        return {"success": True, **_to_item(row)}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _save_banco_sync(servidor: str, banco: str, dados: dict) -> dict:
    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return {"success": False, "message": "Informe a descrição do banco."}
    if not dados.get("codigo"):
        return {"success": False, "message": "Informe o código do banco (padrão Febraban)."}
    if not dados.get("agencia"):
        return {"success": False, "message": "Informe a agência."}
    if not dados.get("conta_corrente"):
        return {"success": False, "message": "Informe a conta corrente."}
    if not dados.get("carteira"):
        return {"success": False, "message": "Informe a carteira."}
    if not (dados.get("codigo_cedente") or "").strip():
        return {"success": False, "message": "Informe o código cedente."}
    integracao_api = bool(dados.get("integracao_api"))
    if not integracao_api:
        if not (dados.get("endereco_remessa") or "").strip():
            return {"success": False, "message": "Informe o diretório de remessa."}
        if not (dados.get("endereco_retorno") or "").strip():
            return {"success": False, "message": "Informe o diretório de retorno."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        sizes = _get_col_sizes(conn, banco, "bancos")

        situacao = (dados.get("situacao") or "A").strip().upper()[:1] or "A"
        aceite = (dados.get("aceite") or "N").strip().upper()[:1] or "N"

        valores = {
            "codigo": int(dados.get("codigo") or 0),
            "digito_banco": int(dados.get("digito_banco") or 0),
            "descricao": _trunc(descricao, sizes, "descricao"),
            "descr_arquivo": _trunc((dados.get("descr_arquivo") or "").strip(), sizes, "descr_arquivo"),
            "agencia": int(dados.get("agencia") or 0),
            "dv_agencia": _trunc((dados.get("dv_agencia") or "").strip(), sizes, "dv_agencia"),
            "contacorrente": int(dados.get("conta_corrente") or 0),
            "dv_contacorrente": _trunc((dados.get("dv_conta_corrente") or "").strip(), sizes, "dv_contacorrente"),
            "dv_agencia_conta": _trunc((dados.get("dv_agencia_conta") or "").strip(), sizes, "dv_agencia_conta"),
            "situacao": situacao,
            "carteira": int(dados.get("carteira") or 0),
            "VARIACAO_CARTEIRA": int(dados.get("variacao_carteira") or 0),
            "codigocedente": _trunc((dados.get("codigo_cedente") or "").strip(), sizes, "codigocedente"),
            "Cod_Transmissao": _trunc((dados.get("cod_transmissao") or "").strip(), sizes, "Cod_Transmissao"),
            "contrato": float(dados.get("contrato") or 0),
            "especie_doc": int(dados.get("especie_doc") or 0),
            "aceite": aceite,
            "tarifa_cobranca": float(dados.get("tarifa_cobranca") or 0),
            "incidencia_multa": int(dados.get("incidencia_multa") or 0),
            "dias_multa": int(dados.get("dias_multa") or 0),
            "tipo_multa": int(dados.get("tipo_multa") or 0),
            "Multa_Atraso_Pag": float(dados.get("multa_atraso_pag") or 0),
            "Mora_Dia_Pag": float(dados.get("mora_dia_pag") or 0),
            "dias_protesto": int(dados.get("dias_protesto") or 0),
            "codigo_protesto": int(dados.get("codigo_protesto") or 0),
            "dias_baixa": int(dados.get("dias_baixa") or 0),
            "codigo_baixa": int(dados.get("codigo_baixa") or 0),
            "tipo_cobranca": int(dados.get("tipo_cobranca") or 0),
            "tipo_registro": int(dados.get("tipo_registro") or 0),
            "emissao_boleto": int(dados.get("emissao_boleto") or 0),
            "distribui_boleto": int(dados.get("distribui_boleto") or 0),
            "numero_boleto": float(dados.get("numero_boleto") or 0),
            "instr_cobranca_1": int(dados.get("instr_cobranca_1") or 0),
            "instr_cobranca_2": int(dados.get("instr_cobranca_2") or 0),
            "tituloboleto": _trunc((dados.get("titulo_boleto") or "").strip(), sizes, "tituloboleto"),
            "mensagem_boleto_1": _trunc((dados.get("mensagem_boleto_1") or "").strip(), sizes, "mensagem_boleto_1"),
            "mensagem_boleto_2": _trunc((dados.get("mensagem_boleto_2") or "").strip(), sizes, "mensagem_boleto_2"),
            "mensagem_boleto_3": _trunc((dados.get("mensagem_boleto_3") or "").strip(), sizes, "mensagem_boleto_3"),
            "end_remessa": _trunc((dados.get("endereco_remessa") or "").strip(), sizes, "end_remessa"),
            "end_retorno": _trunc((dados.get("endereco_retorno") or "").strip(), sizes, "end_retorno"),
            "integracao_api": integracao_api,
            "chave_api": _trunc((dados.get("chave_api_1") or "").strip(), sizes, "chave_api"),
            "chave_api_2": _trunc((dados.get("chave_api_2") or "").strip(), sizes, "chave_api_2"),
            "chave_api_3": _trunc((dados.get("chave_api_3") or "").strip(), sizes, "chave_api_3"),
            "chave_api_4": _trunc((dados.get("chave_api_4") or "").strip(), sizes, "chave_api_4"),
        }

        cod = dados.get("cod")
        if cod:
            cur.execute("SELECT TOP 1 1 AS ok FROM bancos WHERE cod=%s", (cod,))
            if not cur.fetchone():
                return {"success": False, "message": "Banco não encontrado."}
            set_clause = ", ".join(f"[{k}] = %s" for k in valores)
            cur.execute(f"UPDATE bancos SET {set_clause} WHERE cod=%s", (*valores.values(), cod))
        else:
            cols = ", ".join(f"[{k}]" for k in valores)
            placeholders = ", ".join(["%s"] * len(valores))
            cur.execute(
                f"INSERT INTO bancos ({cols}) OUTPUT INSERTED.cod VALUES ({placeholders})",
                tuple(valores.values()),
            )
            cod = cur.fetchone()["cod"]

        conn.commit()
        cur.close()
        return {"success": True, "cod": cod}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _delete_banco_sync(servidor: str, banco: str, cod: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, contacorrente, carteira FROM bancos WHERE cod=%s", (cod,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Banco não encontrado."}

        cur.execute("SELECT TOP 1 1 AS ok FROM cartoes_configuracoes WHERE cod_banco=%s", (cod,))
        if cur.fetchone():
            return {"success": False, "message": "Não é possível excluir: este banco está em uso em Configurações de Cartões."}

        # Mesma checagem do legado (Command1_Click de CmDexclui), preservada
        # fielmente: `duplicata_rec_venc` referencia o banco pela combinação
        # de negócio (codigo+conta+carteira), não pelo PK `cod` — instalações
        # migradas do VB6 podem ter linhas antigas usando essa chave.
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM duplicata_rec_venc "
            "WHERE banco_cedente=%s AND conta_cedente=%s AND carteira=%s",
            (row.get("codigo"), row.get("contacorrente"), row.get("carteira")),
        )
        if cur.fetchone():
            return {"success": False, "message": "Não é permitida exclusão de bancos com títulos associados."}

        cur.execute("DELETE FROM bancos WHERE cod=%s", (cod,))
        conn.commit()
        cur.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def list_bancos(servidor: str, banco: str, busca: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_list_bancos_sync, servidor, banco, busca)


async def get_banco(servidor: str, banco: str, cod: int) -> dict:
    return await asyncio.to_thread(_get_banco_sync, servidor, banco, cod)


async def save_banco(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_save_banco_sync, servidor, banco, dados)


async def delete_banco(servidor: str, banco: str, cod: int) -> dict:
    return await asyncio.to_thread(_delete_banco_sync, servidor, banco, cod)

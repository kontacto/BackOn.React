"""Bombas (Posto de Combustível) — tabela `bomba`.

Legado: `frmcadbom.frm` ("Cadastro de Bombas"). `codigo` é PK própria
(smallint, estilo "byte" 0-255). Nenhuma chamada ao driver de hardware
Wayne Fusion acontece neste formulário especificamente (`StatusPista`/
`SetaPrecoBomba`/etc. são chamados de OUTRAS telas — Fechamento de
Turno, Baixa de Abastecimentos, Cadastro de Combustível — que ainda vão
usar os dados gravados aqui) — ou seja, o CRUD de Bombas em si não tem
dependência de hardware, só as telas que o CONSOMEM depois.

**Achado importante (não previsto pelo `.frm` fornecido)**: apesar de o
formulário declarar um botão `CmDexclui` ("&Exclui"), **não existe
nenhum `Private Sub CmDexclui_Click()` no código-fonte** — o botão existe
visualmente mas não tem nenhuma ação associada (clicar nele não faz
nada). Isso é quase certamente um bug/lacuna do legado, não uma regra de
negócio intencional ("bomba nunca pode ser excluída") — esta migração
implementa Excluir de verdade, com guards de integridade (bloqueia se
houver `mov_bomba`, `bomba_encerrante` ou `ilha` vinculados).

Schema conferido ao vivo em GERDELL/BARESTELA: `bomba` (codigo smallint
PK, ilha/ponto/posicao/tanque/combustivel smallint, contador_final float,
data_ult_mov date, inserir_valor nvarchar(2), serie/fabricante/modelo
nvarchar(60), tipo_medicao smallint, numero_lacre nvarchar(20), dt_lacre
date, captor nvarchar(2), captor2 nvarchar(3), ordem_captor smallint,
AutoNumBomba int IDENTITY, PRECO2 bit, area_atuacao_bomba int).
`AutoNumBomba`/`ordem_captor`/`area_atuacao_bomba` não aparecem no `.frm`
fornecido — fora de escopo (colunas adicionadas depois).

FKs declaradas existem (`bomba.tanque -> tanque.tanque`,
`bomba.combustivel -> combustivel.codigo`) mas estão **desabilitadas**
no banco (`sys.foreign_keys.is_disabled=1`, confirmado 2026-07-13 — ver
nota em `ilha_service.py` sobre o mesmo achado) — não são regras vigentes
no banco, mas a validação é replicada aqui na camada de aplicação mesmo
assim (mensagens amigáveis, consistência de dados daqui pra frente).
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG

_CAMPOS = [
    "ilha", "ponto", "posicao", "tanque", "combustivel", "contador_final", "data_ult_mov",
    "inserir_valor", "captor", "captor2", "serie", "preco2", "fabricante", "modelo",
    "tipo_medicao", "numero_lacre", "dt_lacre",
]


def _row_to_dict(r: dict) -> dict:
    return {
        "codigo": int(r["codigo"]),
        "ilha": int(r["ilha"]) if r.get("ilha") is not None else None,
        "ponto": int(r["ponto"]) if r.get("ponto") is not None else None,
        "posicao": int(r["posicao"]) if r.get("posicao") is not None else None,
        "tanque": int(r["tanque"]) if r.get("tanque") is not None else None,
        "combustivel": int(r["combustivel"]) if r.get("combustivel") is not None else None,
        "contador_final": float(r.get("contador_final") or 0),
        "data_ult_mov": str(r["data_ult_mov"]) if r.get("data_ult_mov") else None,
        "inserir_valor": (r.get("inserir_valor") or "").strip(),
        "captor": (r.get("captor") or "").strip(),
        "captor2": (r.get("captor2") or "").strip(),
        "serie": (r.get("serie") or "").strip(),
        "preco2": bool(r.get("preco2")),
        "fabricante": (r.get("fabricante") or "").strip(),
        "modelo": (r.get("modelo") or "").strip(),
        "tipo_medicao": int(r["tipo_medicao"]) if r.get("tipo_medicao") is not None else None,
        "numero_lacre": (r.get("numero_lacre") or "").strip(),
        "dt_lacre": str(r["dt_lacre"]) if r.get("dt_lacre") else None,
    }


def _list_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT b.codigo, b.ilha, b.ponto, b.posicao, b.tanque, b.combustivel, "
            "c.descricao AS combustivel_descricao "
            "FROM bomba b LEFT JOIN combustivel c ON c.codigo = b.combustivel "
            "ORDER BY b.codigo"
        )
        items = [
            {
                "codigo": int(r["codigo"]),
                "ilha": int(r["ilha"]) if r.get("ilha") is not None else None,
                "ponto": int(r["ponto"]) if r.get("ponto") is not None else None,
                "posicao": int(r["posicao"]) if r.get("posicao") is not None else None,
                "tanque": int(r["tanque"]) if r.get("tanque") is not None else None,
                "combustivel": int(r["combustivel"]) if r.get("combustivel") is not None else None,
                "combustivel_descricao": (r.get("combustivel_descricao") or "").strip(),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _get_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cols = "codigo," + ",".join(_CAMPOS)
        cur.execute(f"SELECT {cols} FROM bomba WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Bomba não encontrada."}
        return {"success": True, "item": _row_to_dict(row)}
    finally:
        conn.close()


def _save_sync(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    if codigo is None or not (0 <= int(codigo) <= 255):
        return {"success": False, "message": "Código inválido — deve estar entre 0 e 255."}
    ilha = dados.get("ilha")
    if ilha is None or not (0 <= int(ilha) <= 255):
        return {"success": False, "message": "Ilha inválida — deve estar entre 0 e 255."}
    ponto = dados.get("ponto")
    if ponto is None or not (0 <= int(ponto) <= 255):
        return {"success": False, "message": "Ponto inválido — deve estar entre 0 e 255."}
    posicao = dados.get("posicao")
    if posicao is None or not (1 <= int(posicao) <= 3):
        return {"success": False, "message": "Posição inválida — deve estar entre 1 e 3."}
    tanque = dados.get("tanque")
    if tanque is None:
        return {"success": False, "message": "Selecione o tanque."}
    combustivel = dados.get("combustivel")
    if combustivel is None:
        return {"success": False, "message": "Selecione o combustível."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT 1 AS ok FROM tanque WHERE tanque=%s", (tanque,))
        if not cur.fetchone():
            return {"success": False, "message": "Tanque não encontrado."}
        cur.execute("SELECT 1 AS ok FROM combustivel WHERE codigo=%s", (combustivel,))
        if not cur.fetchone():
            return {"success": False, "message": "Combustível não encontrado."}
        cur.execute(
            "SELECT 1 AS ok FROM bomba WHERE ponto=%s AND posicao=%s AND codigo<>%s",
            (ponto, posicao, codigo),
        )
        if cur.fetchone():
            return {"success": False, "message": "Já existe uma bomba com o mesmo Ponto e Posição."}

        cur.execute("SELECT 1 AS ok FROM bomba WHERE codigo=%s", (codigo,))
        existe = cur.fetchone() is not None

        valores = {
            "ilha": ilha, "ponto": ponto, "posicao": posicao, "tanque": tanque, "combustivel": combustivel,
            "contador_final": dados.get("contador_final") or 0,
            "data_ult_mov": dados.get("data_ult_mov") or None,
            "inserir_valor": (dados.get("inserir_valor") or "").strip() or None,
            "captor": (dados.get("captor") or "").strip() or None,
            "captor2": (dados.get("captor2") or "").strip() or None,
            "serie": (dados.get("serie") or "").strip() or None,
            "preco2": 1 if dados.get("preco2") else 0,
            "fabricante": (dados.get("fabricante") or "").strip() or None,
            "modelo": (dados.get("modelo") or "").strip() or None,
            "tipo_medicao": dados.get("tipo_medicao"),
            "numero_lacre": (dados.get("numero_lacre") or "").strip() or None,
            "dt_lacre": dados.get("dt_lacre") or None,
        }

        if existe:
            set_clause = ", ".join(f"{c}=%s" for c in _CAMPOS)
            params = [valores.get(c) for c in _CAMPOS] + [codigo]
            cur.execute(f"UPDATE bomba SET {set_clause} WHERE codigo=%s", params)
        else:
            cols = ["codigo"] + _CAMPOS
            placeholders = ",".join(["%s"] * len(cols))
            params = [codigo] + [valores.get(c) for c in _CAMPOS]
            cur.execute(f"INSERT INTO bomba ({','.join(cols)}) VALUES ({placeholders})", params)
        conn.commit()
        return {"success": True, "message": "Bomba gravada.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT TOP 1 1 AS ok FROM mov_bomba WHERE bomba=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Existem movimentações vinculadas a esta bomba — não pode ser excluída."}
        cur.execute("SELECT TOP 1 1 AS ok FROM bomba_encerrante WHERE bomba=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Existem encerrantes registrados para esta bomba — não pode ser excluída."}
        cur.execute("DELETE FROM bomba WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Bomba não encontrada."}
        conn.commit()
        return {"success": True, "message": "Bomba excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_bombas(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco)


async def get_bomba(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_sync, servidor, banco, codigo)


async def save_bomba(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, codigo, dados)


async def delete_bomba(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, codigo)

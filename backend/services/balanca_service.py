"""Cadastro de Balanças (Automação Comercial — pré-pesagem com etiqueta de
peso variável). Tabela `balancas`, genuinamente NOVA (sem equivalente no
schema legado VB6 — balança nunca existiu no legado, ver CLAUDE.md > "Regras
Globais de Entidade" e PENDENCIAS.md > "KPDV" > "Balança Toledo +
Pré-Pesagem").

Fluxo real (confirmado com o usuário, direto do fabricante Toledo) — só o
PRIMEIRO passo é responsabilidade deste sistema:
1. Este backend gera o arquivo `ITENSMGV.TXT` (layout documentado pela
   Toledo — `help.toledobrasil.com/mgv6/`) com os produtos vendidos por peso
   (`pecas.peso_variado = 1`) e grava na "pasta de integração" configurada.
2. O operador abre o MGV6/MGV7 (software próprio da Toledo, já instalado na
   loja) e faz Importação → tipo "Itens" → Importar.
3. O operador vai na aba "Carga" do MGV, escolhe a(s) balança(s) e clica
   Enviar — só aí a informação chega no equipamento.
Passos 2/3 são manuais, fora do alcance deste sistema (MGV6/MGV7 não tem API
remota documentada).
"""
import asyncio
import os
from typing import Optional

from db.connection import _open_conn

# Layout ITENSMGV.TXT (confirmado no portal oficial help.toledobrasil.com/mgv6):
# departamento(2) + tipo(1, "0"=peso) + código(6) + preço em centavos(6) +
# validade em dias(3) + descrição linha1(25) + descrição linha2(25). Campos
# extras (fornecedor/nutricional/imagem) não fazem parte deste escopo — vão
# em branco/zero. Terminador de linha CR+LF (confirmado).
_DEPARTAMENTO_PADRAO = "01"
_TIPO_PESO = "0"
_VALIDADE_PADRAO_DIAS = "000"


def _row_to_dict(r: dict) -> dict:
    return dict(r)


def _ensure_balancas_table(cur) -> None:
    """Migração idempotente (mesmo padrão de
    `impressao_service._ensure_impressao_fila_table`) — cria a tabela na
    primeira vez que alguma empresa usa o cadastro."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'balancas') "
        "CREATE TABLE balancas ("
        "codigo INT IDENTITY(1,1) PRIMARY KEY, "
        "descricao NVARCHAR(80) NOT NULL, "
        "pasta_integracao NVARCHAR(260) NOT NULL, "
        "ativo BIT NOT NULL DEFAULT 1)"
    )


def _list_balancas_sync(servidor: str, banco: str, search: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_balancas_table(cur)
        conn.commit()
        where = "1=1"
        params: list = []
        term = (search or "").strip()
        if term:
            where += " AND descricao LIKE %s"
            params.append(f"%{term}%")
        cur.execute(
            f"SELECT codigo, descricao, pasta_integracao, ativo FROM balancas "
            f"WHERE {where} ORDER BY descricao",
            tuple(params),
        )
        items = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _get_balanca_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_balancas_table(cur)
        conn.commit()
        cur.execute(
            "SELECT codigo, descricao, pasta_integracao, ativo FROM balancas WHERE codigo=%s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "Balança não encontrada."}
        return {"success": True, "item": _row_to_dict(row)}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_balanca_sync(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return {"success": False, "message": "Informe a Descrição."}
    pasta_integracao = (dados.get("pasta_integracao") or "").strip()
    if not pasta_integracao:
        return {"success": False, "message": "Informe a Pasta de Integração."}
    ativo = bool(dados.get("ativo", True))

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_balancas_table(cur)
        conn.commit()

        cur.execute(
            "SELECT codigo FROM balancas WHERE descricao=%s" + (" AND codigo<>%s" if codigo else ""),
            (descricao, codigo) if codigo else (descricao,),
        )
        dup = cur.fetchone()
        if dup:
            cur.close()
            conn.close()
            return {"success": False, "message": f"Já existe uma balança chamada \"{descricao}\" (código {dup['codigo']})."}

        if codigo:
            cur.execute(
                "UPDATE balancas SET descricao=%s, pasta_integracao=%s, ativo=%s WHERE codigo=%s",
                (descricao, pasta_integracao, ativo, codigo),
            )
        else:
            cur.execute(
                "INSERT INTO balancas (descricao, pasta_integracao, ativo) "
                "OUTPUT INSERTED.codigo VALUES (%s,%s,%s)",
                (descricao, pasta_integracao, ativo),
            )
            codigo = int(cur.fetchone()["codigo"])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Balança gravada.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _delete_balanca_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_balancas_table(cur)
        conn.commit()
        cur.execute("SELECT codigo FROM balancas WHERE codigo=%s", (codigo,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return {"success": False, "message": "Balança não encontrada."}
        cur.execute("DELETE FROM balancas WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Balança excluída."}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}


def _linha_itensmgv(codigo_int: str, descricao: str, preco: float) -> str:
    """Monta uma linha do arquivo `ITENSMGV.TXT` — larguras fixas, sem
    separador entre campos (formato posicional). Ver o layout documentado no
    topo do arquivo."""
    # "[-6:]" em vez de "[:6]" pros dois campos numéricos — mantém os dígitos
    # MENOS significativos quando o valor excede a largura do campo (mesma
    # direção de truncamento pros dois, por consistência; caso de borda raro
    # — código MGV de 7+ dígitos ou preço acima de R$9999,99 — não validado
    # contra um caso real ainda).
    codigo6 = (codigo_int or "").strip()[-6:].rjust(6, "0")
    preco_centavos = round((preco or 0) * 100)
    preco6 = str(preco_centavos)[-6:].rjust(6, "0")
    d1 = (descricao or "").strip()[:25].ljust(25)
    d2 = "".ljust(25)
    return f"{_DEPARTAMENTO_PADRAO}{_TIPO_PESO}{codigo6}{preco6}{_VALIDADE_PADRAO_DIAS}{d1}{d2}"


def _exportar_carga_sync(servidor: str, banco: str, codigo_balanca: int) -> dict:
    """Gera o `ITENSMGV.TXT` com os produtos vendidos por peso e grava na
    pasta de integração configurada. NÃO fala com o MGV nem com a balança —
    ver o docstring do módulo pro fluxo completo (passos 2/3 são manuais)."""
    balanca = _get_balanca_sync(servidor, banco, codigo_balanca)
    if not balanca.get("success"):
        return balanca
    pasta = balanca["item"]["pasta_integracao"]

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo_int, descricao, p_venda FROM pecas WHERE peso_variado = 1"
        )
        produtos = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao consultar produtos: {e}"}

    linhas = [
        _linha_itensmgv(p.get("codigo_int"), p.get("descricao"), float(p.get("p_venda") or 0))
        for p in produtos
    ]
    conteudo = "\r\n".join(linhas) + ("\r\n" if linhas else "")

    try:
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, "ITENSMGV.TXT")
        with open(caminho, "w", encoding="latin-1", newline="") as f:
            f.write(conteudo)
    except Exception as e:
        return {"success": False, "message": f"Erro ao gravar o arquivo na pasta de integração: {e}"}

    return {
        "success": True,
        "message": f"Arquivo exportado com {len(produtos)} produto(s). Agora abra o MGV6/MGV7 e "
                    f"faça Importação → Itens → Importar, depois Carga → Enviar.",
        "qtd_produtos": len(produtos),
    }


async def list_balancas(servidor: str, banco: str, search: str = "") -> dict:
    return await asyncio.to_thread(_list_balancas_sync, servidor, banco, search)


async def get_balanca(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_balanca_sync, servidor, banco, codigo)


async def save_balanca(servidor: str, banco: str, codigo: Optional[int], dados: dict) -> dict:
    return await asyncio.to_thread(_save_balanca_sync, servidor, banco, codigo, dados)


async def delete_balanca(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_balanca_sync, servidor, banco, codigo)


async def exportar_carga(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_exportar_carga_sync, servidor, banco, codigo)

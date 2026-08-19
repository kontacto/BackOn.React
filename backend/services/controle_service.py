"""Controle (tabela única) — limites de desconto por função e dados da empresa."""
import asyncio

from db.connection import _open_conn


def _get_limites_sync(servidor: str, banco: str) -> dict:
    """Lê os limites de desconto por função na tabela controle (registro único)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 desconto_pdv_gerente, desconto_pdv_supervisor, desconto_pdv_vendedor "
            "FROM controle"
        )
        r = cur.fetchone()
        cur.close(); conn.close()
        if not r:
            # sem registro de configuração → sem restrição
            return {"success": True, "gerente": 100.0, "supervisor": 100.0, "vendedor": 100.0, "configurado": False}
        return {
            "success": True,
            "gerente": float(r.get("desconto_pdv_gerente") or 0),
            "supervisor": float(r.get("desconto_pdv_supervisor") or 0),
            "vendedor": float(r.get("desconto_pdv_vendedor") or 0),
            "configurado": True,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _txt(v) -> str:
    """Normaliza um valor de coluna pra texto antes de `.strip()` —
    tolera coluna numérica nesta tabela em algumas instalações (achado
    ao vivo 2026-08-17: `controle.empresa` em Minimachine/KONTACTO-TESTE
    é `int`, não texto, quebrava com `'int' object has no attribute
    'strip'`; mesmo cuidado que `ddd` já tinha, agora generalizado pra
    todo campo de texto desta função)."""
    if v is None:
        return ""
    return str(v).strip()


def _get_empresa_sync(servidor: str, banco: str) -> dict:
    """Dados da empresa (tabela controle, registro único): fantasia/razão
    social + endereço/documento/telefone (cabeçalho de recibo/impressão,
    ver `Cabec`/`Pedido_48_COL` no FrmManPedBar.frm) e `cod_rel` (decide se
    o recibo mostra código interno ou código de fábrica do item)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 empresa, fantasia, rz_social, uf, endereco, numero, complemento, "
            "       bairro, cidade, cep, ddd, telefone, CELULAR, cgc, inscr_est, cod_rel, "
            "       exige_cpf_cliente, aceita_duplicar_cnpj, exige_chassi_os, "
            "       emite_nf_comanda, PERGUNTA_EMITE_NFCE, ESCOLHE_NFE_NFCE, IMPRIME_NFCE_NAO_FISCAL "
            "FROM controle"
        )
        r = cur.fetchone() or {}
        # `emite_nfce`/`emite_nfse` moram em `controle_aux`, não `controle`
        # — mesma separação já usada em `numero_nfce`/`csc`/etc. Réplica de
        # `NFCe_Ws = controle_aux.emite_nfce`/`NFSe_Ws = controle_aux.
        # emite_nfse` (mdl_proc.bas:6866/7369) — decide, junto dos 3 campos
        # acima, a árvore de emissão fiscal da Tela de Vendas/KPDV (ver
        # `ibs_cbs_service`/Parte C do ecossistema fiscal).
        cur.execute("SELECT TOP 1 emite_nfce, emite_nfse FROM controle_aux")
        raux = cur.fetchone() or {}
        cur.close(); conn.close()
        return {
            "success": True,
            "empresa": _txt(r.get("empresa")) or None,
            "fantasia": _txt(r.get("fantasia")) or None,
            "rz_social": _txt(r.get("rz_social")) or None,
            "uf": _txt(r.get("uf")) or None,
            "endereco": _txt(r.get("endereco")),
            "numero": r.get("numero"),
            "complemento": _txt(r.get("complemento")),
            "bairro": _txt(r.get("bairro")),
            "cidade": _txt(r.get("cidade")),
            "cep": _txt(r.get("cep")),
            "ddd": (r.get("ddd") or ""),
            "telefone": _txt(r.get("telefone")),
            "celular": _txt(r.get("CELULAR")),
            "cgc": _txt(r.get("cgc")),
            "inscr_est": _txt(r.get("inscr_est")),
            "cod_rel": _txt(r.get("cod_rel")),
            "exige_cpf_cliente": bool(r.get("exige_cpf_cliente")),
            "aceita_duplicar_cnpj": bool(r.get("aceita_duplicar_cnpj")),
            "exige_chassi_os": bool(r.get("exige_chassi_os")),
            # Árvore de decisão de emissão fiscal da Tela de Vendas/KPDV
            # (réplica de `FrmPafOFF.frm::FinalizaVenda`, ver `CheckoutService.
            # cs`/`VendaViewModel.cs` no KPDV) — `emite_nf_comanda` é o
            # `RegControle.ImprimeNotaFiscal` do legado (master switch: emite
            # nota nenhuma?); `emite_nfce`/`emite_nfse` (controle_aux) são
            # `NFCe_Ws`/`NFSe_Ws` (empresa apta a cada tipo); os 3 últimos já
            # existem em Controle do Sistema (aba Kontacto).
            "emite_nf_comanda": bool(r.get("emite_nf_comanda")),
            "emite_nfce": bool(raux.get("emite_nfce")),
            "emite_nfse": bool(raux.get("emite_nfse")),
            "pergunta_emite_nfce": bool(r.get("PERGUNTA_EMITE_NFCE")),
            "escolhe_nfe_nfce": bool(r.get("ESCOLHE_NFE_NFCE")),
            "imprime_nfce_nao_fiscal": bool(r.get("IMPRIME_NFCE_NAO_FISCAL")),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _get_mensagens_pdv_sync(servidor: str, banco: str) -> dict:
    """Mensagens configuráveis do rodapé do recibo/comanda (tabela
    `mensagenspdv`, até 5 linhas, centralizadas na impressão)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "linhas": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 linha1, linha2, linha3, linha4, linha5 FROM mensagenspdv")
        r = cur.fetchone() or {}
        cur.close(); conn.close()
        linhas = [
            (r.get(f"linha{i}") or "").strip()
            for i in range(1, 6)
        ]
        return {"success": True, "linhas": [l for l in linhas if l]}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "linhas": []}


async def get_limites(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_limites_sync, servidor, banco)


async def get_empresa(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_empresa_sync, servidor, banco)


async def get_mensagens_pdv(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_mensagens_pdv_sync, servidor, banco)

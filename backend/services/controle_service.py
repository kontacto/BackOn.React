"""Controle (tabela única) — limites de desconto por função e dados da empresa."""
import asyncio
import base64

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
            "       exige_cpf_cliente, aceita_duplicar_cnpj, exige_chassi_os, emite_nf_comanda "
            "FROM controle"
        )
        r = cur.fetchone() or {}
        # `emite_nfce`/`emite_nfse`/`PERGUNTA_EMITE_NFCE`/`ESCOLHE_NFE_NFCE`/
        # `IMPRIME_NFCE_NAO_FISCAL` moram em `controle_aux`, não `controle`
        # — mesma separação já usada em `numero_nfce`/`csc`/etc. Réplica de
        # `NFCe_Ws = controle_aux.emite_nfce`/`NFSe_Ws = controle_aux.
        # emite_nfse` (mdl_proc.bas:6866/7369) — decide, junto dos 3 campos
        # acima, a árvore de emissão fiscal da Tela de Vendas/KPDV (ver
        # `ibs_cbs_service`/Parte C do ecossistema fiscal).
        #
        # Bug real corrigido 2026-08-26 (achado ao vivo — recibo do Pedido
        # Bar/O.S. de Oficina saindo sem cabeçalho NENHUM na conexão "Baixo
        # Brisa Remoto", `DESKTOP-TDK482U`/`BD_BAIXOBRISA`): os 3 últimos
        # campos estavam sendo lidos de `FROM controle` (linha acima), mas
        # `CAMPOS_CONTROLE_AUX` (`controle_sistema_service.py`, a lista que
        # define de qual tabela cada campo do Controle do Sistema vem)
        # sempre os classificou como `controle_aux` — confirmado batendo os
        # dois arquivos. Em instalações onde essas 3 colunas só existem em
        # `controle_aux` (não redundantemente em `controle` também — caso
        # de `BD_BAIXOBRISA`, SQL Server 2014 SP1, instalação mais antiga),
        # a query com "Invalid column name" derrubava a função INTEIRA
        # (`success: False`), levando junto fantasia/endereço/telefone —
        # não só esses 3 campos fiscais. Movidos pra query certa abaixo.
        cur.execute(
            "SELECT TOP 1 emite_nfce, emite_nfse, PERGUNTA_EMITE_NFCE, ESCOLHE_NFE_NFCE, "
            "       IMPRIME_NFCE_NAO_FISCAL FROM controle_aux"
        )
        raux = cur.fetchone() or {}
        # Consulta separada pra logo — VARBINARY nunca entra na mesma SELECT
        # dos campos de texto acima (achado real: serialização genérica de
        # `bytes` assume UTF-8 e corromperia o binário da imagem). Leitura
        # manual em base64, mesmo padrão de
        # `gestor_nfse_service._obter_danfe_pdf_base64_sync`/
        # `bancos_service._get_banco_sync`.
        #
        # Bug real corrigido 2026-08-26 (achado ao vivo pelo usuário — O.S.
        # de Oficina e recibo do Pedido Bar saindo sem cabeçalho NENHUM,
        # não só sem logo): `logo_bytes` era lido mas nunca codificado/
        # devolvido no dict de resposta (dead code) — e, pior, essa query
        # ficava dentro do MESMO try/except do restante da função; se ela
        # falhasse (ex.: coluna ainda não migrada num banco específico),
        # a função inteira retornava `success: False`, derrubando também
        # fantasia/endereço/telefone/CNPJ — não só a logo. Isolada num
        # try/except próprio: falha na logo nunca mais derruba o resto do
        # cabeçalho da empresa.
        try:
            cur.execute("SELECT TOP 1 logo_empresa, logo_empresa_mime FROM controle")
            rlogo = cur.fetchone() or {}
        except Exception:
            rlogo = {}
        logo_bytes = rlogo.get("logo_empresa")
        logo_base64 = base64.b64encode(bytes(logo_bytes)).decode("ascii") if logo_bytes else None
        logo_mime = (rlogo.get("logo_empresa_mime") or None) if logo_bytes else None
        cur.close(); conn.close()
        return {
            "logo_base64": logo_base64,
            "logo_mime": logo_mime,
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
            "pergunta_emite_nfce": bool(raux.get("PERGUNTA_EMITE_NFCE")),
            "escolhe_nfe_nfce": bool(raux.get("ESCOLHE_NFE_NFCE")),
            "imprime_nfce_nao_fiscal": bool(raux.get("IMPRIME_NFCE_NAO_FISCAL")),
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

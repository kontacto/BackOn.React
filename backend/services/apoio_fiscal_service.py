"""Apoio Fiscal BackOn — tradução em tempo real de rejeição fiscal (SEFAZ/ADN)
pro lojista, + notificação automática de suporte (e-mail sempre, WhatsApp
quando configurado).

Origem: pedido do usuário 2026-08-28, depois da correção do DIFAL/
ICMSUFDest — "esse aprendizado tem ser propagado para toda nossa carteira
de clientes... o intuito não só ajudar o cliente. é também ajudar nisso
suporte a não precisar perder muito tempo com solução fiscal,
principalmente a Adriana do suporte que não domina o assunto."

A base de conhecimento (`BASE_CONHECIMENTO`) promove pra código os 5
padrões reais confirmados na memória `apoio-fisco-erros-fiscais-reais`
(2026-08-23, sessão de teste ao vivo NF-e/NFC-e/CC-e/NFS-e) + a regra do
DIFAL (rejeição 695) já corrigida no motor de emissão nesta mesma sessão.

**Como adicionar um erro novo à base de conhecimento** (mesmo princípio
de `nfe_regras_fiscais.py` — registro que cresce por achado real
confirmado, nunca por suposição):
1. O padrão precisa ter sido CONFIRMADO por uma rejeição real (SEFAZ/ADN)
   já validada por Kelvin — nunca um texto "provável"/"deve ser assim".
2. Adicionar 1 entrada nova em `BASE_CONHECIMENTO`, chave = código da
   rejeição (`cStat` do SEFAZ, ou um slug estável pra rejeição ADN sem
   código numérico — ver `_slug_rejeicao_adn`).
3. `explicacao_curta` sempre em 1-2 frases, sem jargão técnico (nunca
   nomes de campo XML, nunca código numérico cru) — é o que aparece
   primeiro pro lojista. `explicacao_detalhada` só aparece se ele pedir
   "quero entender melhor". `acao_usuario`: o que ele pode tentar
   sozinho, ou `None` quando a única ação real é acionar o suporte.
4. Nunca mexer no motor de emissão pra adicionar um erro novo — a
   tradução é 100% dirigida por esta tabela.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from db.connection import _open_conn
from services import email_cobranca_service
from services.whatsapp import repository as whatsapp_repository
from services.whatsapp.providers import build_provider as whatsapp_build_provider
from services.whatsapp.service import normalize_phone


@dataclass(frozen=True)
class ErroFiscalConhecido:
    titulo: str
    explicacao_curta: str
    explicacao_detalhada: str
    acao_usuario: Optional[str]


# Chave = código da rejeição SEFAZ (cStat, string) ou slug estável de
# rejeição ADN (NFS-e) — ver `_slug_rejeicao_adn`.
BASE_CONHECIMENTO: dict[str, ErroFiscalConhecido] = {
    "539": ErroFiscalConhecido(
        titulo="Numeração duplicada",
        explicacao_curta=(
            "Isso não é um erro na sua nota — o sistema apontou um número que já foi usado antes "
            "(às vezes pelo sistema antigo, que roda em paralelo). Não precisa corrigir nada na nota em si."
        ),
        explicacao_detalhada=(
            "Este app e o sistema legado compartilham o mesmo banco de dados e podem ficar "
            "temporariamente fora de sincronia sobre qual é o próximo número de nota disponível — "
            "o SEFAZ recusa porque a combinação Série/Número/CNPJ já foi usada. Isso é um ajuste de "
            "numeração feito pelo suporte técnico, não uma falha do lançamento."
        ),
        acao_usuario=None,
    ),
    "897": ErroFiscalConhecido(
        titulo="Erro técnico interno",
        explicacao_curta=(
            "Erro técnico interno na geração do número da nota — não precisa de nada da sua parte, "
            "é ajuste de sistema."
        ),
        explicacao_detalhada=(
            "Um campo puramente interno usado como código anti-fraude da chave de acesso ficou "
            "inconsistente entre duas tentativas de envio. Isso não tem relação com os dados que você "
            "digitou (cliente, produtos, valores) — é resolvido pelo suporte técnico."
        ),
        acao_usuario=None,
    ),
    "695": ErroFiscalConhecido(
        titulo="Grupo de ICMS para a UF de destino (DIFAL)",
        explicacao_curta=(
            "Essa nota é para um cliente de fora do seu estado, consumidor final, que não tem "
            "Inscrição Estadual — esse tipo de venda tem uma regra extra de ICMS (DIFAL) que precisa "
            "ser calculada automaticamente na nota."
        ),
        explicacao_detalhada=(
            "Quando a venda é interestadual (cliente de outro estado), o cliente é consumidor final "
            "(não vai revender) e ele não tem Inscrição Estadual, a nota fiscal é obrigada a informar "
            "o cálculo do ICMS dividido entre o seu estado e o estado do cliente (o chamado DIFAL, da "
            "Reforma Tributária/Convênio ICMS 93/2015). Confira se o cadastro do cliente está com "
            "\"Consumidor Final\" e o Estado corretos — o cálculo em si já é feito automaticamente pelo "
            "sistema a partir dessas 3 informações."
        ),
        acao_usuario=(
            "Confira no cadastro do cliente: Estado correto, e o campo \"Consumidor Final\" marcado "
            "quando for o caso. Se estiver tudo certo e o erro persistir, acione o suporte."
        ),
    ),
    "E0160": ErroFiscalConhecido(
        titulo="Situação no Simples Nacional não confere",
        explicacao_curta=(
            "O sistema informou que sua empresa é optante (ou não optante) do Simples Nacional, mas "
            "isso não bate com o cadastro oficial da Receita Federal pra este mês."
        ),
        explicacao_detalhada=(
            "A Receita Federal valida a situação no Simples Nacional mês a mês. Se sua empresa "
            "realmente mudou de regime recentemente (saiu do Simples, virou MEI, etc.), o cadastro "
            "deste sistema (Controle do Sistema) precisa ser atualizado pra bater com a situação real "
            "— converse com seu contador antes de alterar, é uma mudança de regime tributário real."
        ),
        acao_usuario="Confirme com seu contador se sua empresa mudou de regime tributário recentemente.",
    ),
    "E0166": ErroFiscalConhecido(
        titulo="Regime de apuração do Simples Nacional não informado",
        explicacao_curta=(
            "Sua empresa está cadastrada como optante do Simples Nacional (ME/EPP) — pra esse caso a "
            "nota também precisa informar em qual regime os tributos são apurados."
        ),
        explicacao_detalhada=(
            "Isso é uma configuração de sistema (regime de apuração dos tributos do Simples Nacional, "
            "exigido pela nota técnica da NFS-e nacional), não algo causado por um lançamento errado. "
            "Avise o suporte técnico."
        ),
        acao_usuario=None,
    ),
    "NBS_AUSENTE": ErroFiscalConhecido(
        titulo="Classificação fiscal do serviço não cadastrada",
        explicacao_curta=(
            "Esse tipo de serviço ainda não tem a classificação fiscal configurada no sistema pra "
            "emitir a nota de serviço eletrônica (NFS-e)."
        ),
        explicacao_detalhada=(
            "Toda nota de serviço (NFS-e) precisa de 2 códigos — um nacional (por tipo de serviço, "
            "igual em todo o Brasil) e um municipal (específico da prefeitura da sua cidade). Pra "
            "cadastrar esses códigos é preciso saber a classificação exata do serviço prestado — seu "
            "contador (ou a própria prefeitura) pode confirmar qual é. Encaminhe pro suporte técnico "
            "informando qual serviço está faltando."
        ),
        acao_usuario="Confirme com seu contador (ou a prefeitura) a classificação fiscal exata desse serviço.",
    ),
}

FALLBACK_GENERICO = ErroFiscalConhecido(
    titulo="Apoio Fiscal BackOn",
    explicacao_curta=(
        "Houve uma rejeição no envio da nota pro fisco. Nossa equipe de suporte já foi avisada "
        "automaticamente e vai te ajudar a resolver."
    ),
    explicacao_detalhada=(
        "Este erro específico ainda não está na nossa base de traduções — mas a mensagem original do "
        "fisco já foi enviada junto com o aviso automático pro suporte da Kontacto, que vai analisar e "
        "retornar o quanto antes."
    ),
    acao_usuario=None,
)


def resolver_erro_fiscal(codigo_rejeicao: str) -> ErroFiscalConhecido:
    return BASE_CONHECIMENTO.get((codigo_rejeicao or "").strip(), FALLBACK_GENERICO)


def _buscar_fantasia_sync(servidor: str, banco: str) -> str:
    try:
        conn = _open_conn(servidor, banco)
    except Exception:
        return ""
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 fantasia FROM controle")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return (row.get("fantasia") if row else "") or ""
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return ""


def _montar_corpo_email(
    fantasia: str, tipo_documento: str, codigo_rejeicao: str, mensagem_original: str,
    referencia: Optional[str], erro: ErroFiscalConhecido,
) -> str:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    return (
        f"<h2>Apoio Fiscal BackOn — rejeição {codigo_rejeicao}</h2>"
        f"<p><b>Cliente:</b> {fantasia or '(fantasia não cadastrada)'}</p>"
        f"<p><b>Data/hora:</b> {agora}</p>"
        f"<p><b>Documento:</b> {tipo_documento}" + (f" — {referencia}" if referencia else "") + "</p>"
        f"<p><b>Rejeição original:</b> {mensagem_original or '(sem mensagem)'}</p>"
        f"<p><b>Sugestão de solução (Apoio Fiscal BackOn):</b><br>{erro.explicacao_detalhada}</p>"
    )


def _montar_mensagem_whatsapp(
    fantasia: str, tipo_documento: str, codigo_rejeicao: str, mensagem_original: str, referencia: Optional[str],
) -> str:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas = [
        f"*Apoio Fiscal BackOn — rejeição {codigo_rejeicao}*",
        f"Cliente: {fantasia or '(fantasia não cadastrada)'}",
        f"Data/hora: {agora}",
        f"Documento: {tipo_documento}" + (f" — {referencia}" if referencia else ""),
        f"Rejeição: {mensagem_original or '(sem mensagem)'}",
    ]
    return "\n".join(linhas)


def _enviar_email_suporte_sync(servidor: str, banco: str, assunto: str, corpo_html: str) -> bool:
    """Best-effort, nunca propaga exceção — isolado do canal WhatsApp
    (mesmo princípio de isolamento por sub-query já usado em
    `ensure_all_schema`/`controle_service`)."""
    try:
        resultado = email_cobranca_service._enviar_email_sync(
            servidor, banco, "suporte@kontacto.com.br", assunto, corpo_html,
        )
        return bool(resultado.get("success"))
    except Exception:
        return False


def _enviar_whatsapp_suporte_sync(servidor: str, banco: str, mensagem: str) -> bool:
    """Best-effort, nunca propaga exceção. Só tenta quando o cliente já
    tem WhatsApp habilitado E preencheu "Cel Suporte"."""
    try:
        cfg_wpp = whatsapp_repository.get_config_raw(servidor, banco)
        if not cfg_wpp.get("enabled"):
            return False
        cel_suporte = _buscar_cel_suporte_sync(servidor, banco)
        if not cel_suporte:
            return False
        provider = whatsapp_build_provider(cfg_wpp)
        if provider is None:
            return False
        resultado = provider.send_text(normalize_phone(cel_suporte), mensagem)
        return bool(getattr(resultado, "success", False))
    except Exception:
        return False


def notificar_rejeicao_sync(
    servidor: str, banco: str, *, tipo_documento: str, codigo_rejeicao: str,
    mensagem_original: str, referencia: Optional[str] = None,
) -> dict:
    """Chamada pelos pontos de emissão/cancelamento fiscal (1 documento por
    chamada) quando o fisco (SEFAZ ou ADN) rejeita um documento. Pra
    operações em LOTE (Gestor NFCe), ver `notificar_rejeicoes_lote_sync`
    abaixo — nunca chamar esta função uma vez por item de um lote, spamma
    o suporte."""
    erro = resolver_erro_fiscal(codigo_rejeicao)
    fantasia = _buscar_fantasia_sync(servidor, banco)

    assunto = f"Rejeição {codigo_rejeicao} — {fantasia or servidor + '/' + banco}"
    corpo = _montar_corpo_email(fantasia, tipo_documento, codigo_rejeicao, mensagem_original, referencia, erro)
    notificado_email = _enviar_email_suporte_sync(servidor, banco, assunto, corpo)

    mensagem_wpp = _montar_mensagem_whatsapp(fantasia, tipo_documento, codigo_rejeicao, mensagem_original, referencia)
    notificado_whatsapp = _enviar_whatsapp_suporte_sync(servidor, banco, mensagem_wpp)

    return {
        "titulo": erro.titulo,
        "explicacao_curta": erro.explicacao_curta,
        "explicacao_detalhada": erro.explicacao_detalhada,
        "acao_usuario": erro.acao_usuario,
        "notificado_suporte": {"email": notificado_email, "whatsapp": notificado_whatsapp},
    }


def _montar_corpo_email_lote(fantasia: str, tipo_documento: str, total: int, grupos: list[dict]) -> str:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas_grupos = "".join(
        f"<li><b>{g['codigo_rejeicao']}</b> — {g['titulo']} ({g['quantidade']} item(ns): "
        f"{', '.join(g['referencias'][:20])}"
        f"{'…' if len(g['referencias']) > 20 else ''})<br>{g['explicacao_curta']}</li>"
        for g in grupos
    )
    return (
        f"<h2>Apoio Fiscal BackOn — resumo de lote ({total} item(ns) não processado(s))</h2>"
        f"<p><b>Cliente:</b> {fantasia or '(fantasia não cadastrada)'}</p>"
        f"<p><b>Data/hora:</b> {agora}</p>"
        f"<p><b>Operação:</b> {tipo_documento}</p>"
        f"<p><b>Rejeições agrupadas por código:</b></p>"
        f"<ul>{linhas_grupos}</ul>"
    )


def _montar_mensagem_whatsapp_lote(fantasia: str, tipo_documento: str, total: int, grupos: list[dict]) -> str:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas = [
        f"*Apoio Fiscal BackOn — resumo de lote ({total} item(ns))*",
        f"Cliente: {fantasia or '(fantasia não cadastrada)'}",
        f"Data/hora: {agora}",
        f"Operação: {tipo_documento}",
    ]
    for g in grupos:
        linhas.append(f"- {g['codigo_rejeicao']} ({g['quantidade']}x): {g['titulo']}")
    return "\n".join(linhas)


def notificar_rejeicoes_lote_sync(
    servidor: str, banco: str, *, tipo_documento: str, itens_falhos: list[dict],
) -> Optional[dict]:
    """Resumo agregado — UMA única notificação (e-mail + WhatsApp) cobrindo
    TODOS os itens que falharam numa operação em LOTE do Gestor NFCe
    (Cancelar/Inutilizar/Retransmitir/Validar Contingência), nunca 1
    notificação por item (spammaria a Adriana). Decisão de desenho
    (`AskUserQuestion`, 2026-08-28, escolha "resumo agregado"): agrupa por
    `codigo_rejeicao`, mostra quantos itens de cada código e a lista de
    referências (comanda/número), com a tradução curta de cada código uma
    vez só — não repete a explicação por item.

    `itens_falhos`: lista de dicts `{"referencia": ..., "codigo_rejeicao":
    ..., "mensagem_original": ...}` — um por item que falhou (só os que
    falharam, quem chama já filtra os sucessos antes). Devolve `None`
    quando `itens_falhos` está vazio (nada a notificar)."""
    if not itens_falhos:
        return None

    grupos_map: dict[str, dict] = {}
    for item in itens_falhos:
        codigo = (item.get("codigo_rejeicao") or "?").strip() or "?"
        if codigo not in grupos_map:
            erro = resolver_erro_fiscal(codigo)
            grupos_map[codigo] = {
                "codigo_rejeicao": codigo, "titulo": erro.titulo,
                "explicacao_curta": erro.explicacao_curta,
                "explicacao_detalhada": erro.explicacao_detalhada,
                "acao_usuario": erro.acao_usuario,
                "quantidade": 0, "referencias": [],
            }
        grupos_map[codigo]["quantidade"] += 1
        ref = item.get("referencia")
        if ref is not None:
            grupos_map[codigo]["referencias"].append(str(ref))

    grupos = list(grupos_map.values())
    total = len(itens_falhos)
    fantasia = _buscar_fantasia_sync(servidor, banco)

    assunto = f"Rejeição em lote ({total}) — {tipo_documento} — {fantasia or servidor + '/' + banco}"
    corpo = _montar_corpo_email_lote(fantasia, tipo_documento, total, grupos)
    notificado_email = _enviar_email_suporte_sync(servidor, banco, assunto, corpo)

    mensagem_wpp = _montar_mensagem_whatsapp_lote(fantasia, tipo_documento, total, grupos)
    notificado_whatsapp = _enviar_whatsapp_suporte_sync(servidor, banco, mensagem_wpp)

    return {
        "total": total,
        "grupos": grupos,
        "notificado_suporte": {"email": notificado_email, "whatsapp": notificado_whatsapp},
    }


def _buscar_cel_suporte_sync(servidor: str, banco: str) -> str:
    try:
        conn = _open_conn(servidor, banco)
    except Exception:
        return ""
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 cel_suporte FROM servico_sistema_atualizacao ORDER BY codigo DESC")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return (row.get("cel_suporte") if row else "") or ""
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return ""

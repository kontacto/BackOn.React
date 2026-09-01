"""Recibo numerado — núcleo compartilhado da tabela `Recibos` +
`Controle.Seq_Recibo`/`Ano_Recibo`, extraído de
`contratos_service._gerar_recibo_sync` (2026-08-31) ao generalizar
"Emitir Recibo" pra Contas a Receber.

**Achado real que motivou a generalização**: a tela de Baixa do legado
(`Revenda\\FrmManPar.frm`) já TEM um botão "&Emitir Recibo"
(`Command13`) — mas o `Command13_Click` real está **inteiramente
comentado/morto** no código-fonte atual (nunca chega a abrir
`FrmManRecibo`). O comentário morto já documenta a intenção original:
pré-preencher Recebemos/Valor/Data a partir dos campos da própria Baixa
em andamento. Esta implementação completa essa intenção documentada —
não inventa comportamento sem precedente na fonte, só termina o que
ficou desligado por lá.

**Numeração**: sequencial por "ano" (`Controle.Ano_Recibo`), incrementa
`Controle.Seq_Recibo` a cada emissão — mesma réplica fiel de
`PegaProximo` (`frmmanrecibo.frm`) já usada em
`contratos_service._gerar_recibo_sync`. **Sem verificação de colisão**
de propósito — o legado real (`PegaProximo`) também não verifica, só lê
o próximo valor cru; replicado fielmente, não é uma lacuna desta
migração."""
from datetime import date
from typing import Optional


def _gravar_recibo_numerado_sync(
    cur, *, recebemos: str, valor: float, referente: str, data_recibo: Optional[date] = None,
    assinatura: Optional[str] = None,
) -> dict:
    """Espera um cursor `as_dict=True` já aberto, dentro da transação do
    chamador (não abre/fecha conexão própria — quem chama decide o
    commit). Devolve o dict pronto pra resposta da API (sem
    `valor_extenso` — quem chama decide se/como formatar por extenso,
    ver `contratos_service._valor_por_extenso`)."""
    cur.execute("SELECT rz_social, seq_recibo, ano_recibo FROM controle")
    ctl = cur.fetchone() or {}
    seq = int(ctl.get("seq_recibo") or 0) + 1
    ano_recibo = int(ctl.get("ano_recibo") or date.today().year)
    dt = data_recibo or date.today()
    assin = (assinatura or ctl.get("rz_social") or "").strip()
    cur.execute(
        "INSERT INTO Recibos (seq, ano, recebemos, valor, referente, data, assinatura) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (seq, ano_recibo, recebemos, round(float(valor), 2), referente, dt, assin),
    )
    cur.execute("UPDATE controle SET seq_recibo=%s", (seq,))
    return {
        "numero": f"{seq:03d}/{ano_recibo}",
        "recebemos": recebemos,
        "valor": round(float(valor), 2),
        "referente": referente,
        "data": dt.isoformat() if hasattr(dt, "isoformat") else str(dt),
        "assinatura": assin,
    }

"""Repository do módulo WhatsApp — acesso ao SQL Server (config, logs, documentos).

Cria automaticamente as tabelas `whatsapp_config` e `whatsapp_send_log`
(CREATE TABLE IF NOT EXISTS) na primeira utilização, sem alterar o restante do
schema do cliente.
"""
from typing import Optional

from db.connection import _open_conn
from services.constants import SITUACAO_LABEL

DDL_CONFIG = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'whatsapp_config')
BEGIN
    CREATE TABLE whatsapp_config (
        id INT IDENTITY(1,1) PRIMARY KEY,
        provider NVARCHAR(20) NULL,
        from_number NVARCHAR(30) NULL,
        twilio_sid NVARCHAR(80) NULL,
        twilio_token NVARCHAR(200) NULL,
        meta_phone_id NVARCHAR(60) NULL,
        meta_token NVARCHAR(500) NULL,
        evolution_url NVARCHAR(200) NULL,
        evolution_instance NVARCHAR(80) NULL,
        evolution_apikey NVARCHAR(200) NULL,
        signature NVARCHAR(200) NULL,
        enabled BIT NOT NULL DEFAULT 0,
        updated_at DATETIME NOT NULL DEFAULT GETDATE()
    );
END
"""

DDL_LOG = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'whatsapp_send_log')
BEGIN
    CREATE TABLE whatsapp_send_log (
        id INT IDENTITY(1,1) PRIMARY KEY,
        company_id NVARCHAR(80) NULL,
        document_type NVARCHAR(10) NOT NULL,
        document_id INT NOT NULL,
        customer_id INT NULL,
        phone_number NVARCHAR(30) NULL,
        message NVARCHAR(MAX) NULL,
        sent_at DATETIME NOT NULL DEFAULT GETDATE(),
        status NVARCHAR(20) NOT NULL,
        error_message NVARCHAR(MAX) NULL,
        provider NVARCHAR(20) NULL,
        provider_message_id NVARCHAR(120) NULL,
        duration_ms INT NULL,
        user_id INT NULL
    );
    CREATE INDEX IX_wsl_document ON whatsapp_send_log (document_type, document_id);
    CREATE INDEX IX_wsl_customer ON whatsapp_send_log (customer_id);
    CREATE INDEX IX_wsl_sent_at ON whatsapp_send_log (sent_at);
END
"""

_CONFIG_COLS = [
    "provider", "from_number", "twilio_sid", "twilio_token", "meta_phone_id",
    "meta_token", "evolution_url", "evolution_instance", "evolution_apikey",
    "signature", "enabled",
]


def ensure_tables(cur) -> None:
    cur.execute(DDL_CONFIG)
    cur.execute(DDL_LOG)
    # migração idempotente: coluna de template de mensagem
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='message_template' AND Object_ID=Object_ID('whatsapp_config')) "
        "ALTER TABLE whatsapp_config ADD message_template NVARCHAR(MAX) NULL"
    )


def get_config_raw(servidor: str, banco: str) -> dict:
    """Config completa (com segredos) — uso interno do service."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        ensure_tables(cur)
        conn.commit()
        cur.execute("SELECT TOP 1 * FROM whatsapp_config ORDER BY id")
        row = cur.fetchone() or {}
        cur.close()
        return {
            "provider": (row.get("provider") or "").strip(),
            "from_number": (row.get("from_number") or "").strip(),
            "twilio_sid": (row.get("twilio_sid") or "").strip(),
            "twilio_token": (row.get("twilio_token") or "").strip(),
            "meta_phone_id": (row.get("meta_phone_id") or "").strip(),
            "meta_token": (row.get("meta_token") or "").strip(),
            "evolution_url": (row.get("evolution_url") or "").strip(),
            "evolution_instance": (row.get("evolution_instance") or "").strip(),
            "evolution_apikey": (row.get("evolution_apikey") or "").strip(),
            "signature": (row.get("signature") or "").strip(),
            "message_template": (row.get("message_template") or ""),
            "enabled": bool(row.get("enabled")),
            "configured": bool(row),
        }
    finally:
        conn.close()


def save_config(servidor: str, banco: str, values: dict) -> None:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        ensure_tables(cur)
        cur.execute("SELECT TOP 1 id FROM whatsapp_config ORDER BY id")
        existing = cur.fetchone()
        params = [
            (values.get("provider") or "").strip().lower() or None,
            (values.get("from_number") or "").strip() or None,
            (values.get("twilio_sid") or "").strip() or None,
            (values.get("twilio_token") or "").strip() or None,
            (values.get("meta_phone_id") or "").strip() or None,
            (values.get("meta_token") or "").strip() or None,
            (values.get("evolution_url") or "").strip() or None,
            (values.get("evolution_instance") or "").strip() or None,
            (values.get("evolution_apikey") or "").strip() or None,
            (values.get("signature") or "").strip() or None,
            1 if values.get("enabled") else 0,
            (values.get("message_template") or "").strip() or None,
        ]
        if existing:
            cur.execute(
                "UPDATE whatsapp_config SET provider=%s, from_number=%s, twilio_sid=%s, "
                "twilio_token=%s, meta_phone_id=%s, meta_token=%s, evolution_url=%s, "
                "evolution_instance=%s, evolution_apikey=%s, signature=%s, enabled=%s, "
                "message_template=%s, updated_at=GETDATE() WHERE id=%s",
                (*params, existing["id"]),
            )
        else:
            cur.execute(
                "INSERT INTO whatsapp_config (provider, from_number, twilio_sid, twilio_token, "
                "meta_phone_id, meta_token, evolution_url, evolution_instance, evolution_apikey, "
                "signature, enabled, message_template) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                tuple(params),
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def insert_log(servidor: str, banco: str, log: dict) -> int:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        ensure_tables(cur)
        cur.execute(
            "INSERT INTO whatsapp_send_log (company_id, document_type, document_id, customer_id, "
            "phone_number, message, status, error_message, provider, provider_message_id, duration_ms, user_id) "
            "OUTPUT INSERTED.id "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                log.get("company_id"), log.get("document_type"), log.get("document_id"),
                log.get("customer_id"), log.get("phone_number"), log.get("message"),
                log.get("status"), log.get("error_message"), log.get("provider"),
                log.get("provider_message_id"), log.get("duration_ms"), log.get("user_id"),
            ),
        )
        row = cur.fetchone()
        new_id = int(row["id"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return new_id
    finally:
        conn.close()


def list_logs(servidor: str, banco: str, document_type: str, document_id: int) -> list:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        ensure_tables(cur)
        conn.commit()
        cur.execute(
            "SELECT TOP 100 l.*, f.nome AS user_nome, f.nome_guerra AS user_guerra "
            "FROM whatsapp_send_log l "
            "LEFT JOIN funcionarios f ON f.codigo_int = l.user_id "
            "WHERE l.document_type=%s AND l.document_id=%s ORDER BY l.sent_at DESC",
            (document_type, document_id),
        )
        out = []
        for r in cur.fetchall():
            out.append({
                "id": int(r["id"]),
                "document_type": r.get("document_type"),
                "document_id": int(r.get("document_id") or 0),
                "phone_number": (r.get("phone_number") or "").strip(),
                "status": (r.get("status") or "").strip(),
                "error_message": r.get("error_message") or "",
                "provider": (r.get("provider") or "").strip(),
                "message": r.get("message") or "",
                "sent_at": r["sent_at"].isoformat() if r.get("sent_at") else None,
                "user_nome": (r.get("user_guerra") or r.get("user_nome") or "").strip(),
            })
        cur.close()
        return out
    finally:
        conn.close()


def get_document_items(servidor: str, banco: str, doc_type: str, doc_id: int) -> list:
    """Itens do documento (Pedido ou OS) p/ compor a mensagem.
    Retorna lista de dicts: {descricao, qtd, valor_unitario, desconto, total}.
    `desconto` aqui é o desconto TOTAL do item (unitário * quantidade).
    "CLI" (Cliente/Telemarketing) não tem itens — retorna lista vazia.
    """
    if doc_type == "CLI":
        return []
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if doc_type == "PED":
            cur.execute(
                "SELECT i.produto, i.qtd_pedida AS qtd, i.p_venda, i.desconto, "
                "       i.descricao_produto, pe.descricao AS peca_desc, sv.descricao AS serv_desc "
                "FROM pedido_venda_prod i "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
                "LEFT JOIN servicos sv ON sv.codigo = i.produto "
                "WHERE i.pedido = %s AND ISNULL(i.item_cancelado,0) = 0 "
                "ORDER BY i.codauto",
                (doc_id,),
            )
        else:  # OS
            cur.execute(
                "SELECT i.codigo_interno AS produto, i.quant AS qtd, i.p_venda, i.desconto, "
                "       i.descricao_produto_os AS descricao_produto, "
                "       pe.descricao AS peca_desc, sv.descricao AS serv_desc "
                "FROM os_produto i "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
                "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
                "WHERE i.os = %s AND ISNULL(i.item_cancelado,0) = 0 "
                "ORDER BY i.cod_os_prod",
                (doc_id,),
            )
        out = []
        for r in cur.fetchall():
            base = (r.get("peca_desc") or r.get("serv_desc") or "").strip()
            compl = (r.get("descricao_produto") or "").strip()
            nome = base or compl or (r.get("produto") or "").strip()
            qtd = float(r.get("qtd") or 0)
            pv = float(r.get("p_venda") or 0)
            desc_unit = float(r.get("desconto") or 0)
            out.append({
                "descricao": nome,
                "qtd": qtd,
                "valor_unitario": pv,
                "desconto": round(desc_unit * qtd, 2),
                "total": round(qtd * pv, 2),
            })
        cur.close()
        return out
    finally:
        conn.close()



def get_document_summary(servidor: str, banco: str, doc_type: str, doc_id: int) -> Optional[dict]:
    """Resumo do documento (Pedido, OS ou Cliente/Telemarketing) para montar
    a mensagem. "CLI" não é um documento de verdade (não tem itens/total/
    situação) — `doc_id` é `cliente.codigo`, usado pela tela de
    Telemarketing pra mandar uma mensagem avulsa (não ligada a um Pedido/OS
    específico) e registrar o envio no histórico do cliente."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if doc_type == "CLI":
            cur.execute(
                "SELECT c.codigo AS doc, c.codigo AS cliente, c.nome AS cliente_nome, "
                "LTRIM(RTRIM(ISNULL(CAST(c.ddd_cli AS NVARCHAR(4)),'') + ISNULL(c.telefone_cli,''))) AS telefone "
                "FROM cliente c WHERE c.codigo = %s",
                (doc_id,),
            )
            r = cur.fetchone()
            cur.close()
            if not r:
                return None
            return {
                "doc_type": "CLI", "doc_label": "Cliente",
                "doc": int(r["doc"]),
                "cliente_id": int(r["cliente"]),
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "telefone": (r.get("telefone") or "").strip(),
                "data": None,
                "total": 0.0,
                "situacao_label": "",
                "obs": "",
            }
        if doc_type == "PED":
            cur.execute(
                "SELECT p.pedido AS doc, p.cliente, p.data, p.total, p.situacao, p.obs, "
                "c.nome AS cliente_nome, "
                "LTRIM(RTRIM(ISNULL(CAST(c.ddd_cli AS NVARCHAR(4)),'') + ISNULL(c.telefone_cli,''))) AS telefone "
                "FROM pedido_venda p LEFT JOIN cliente c ON c.codigo = p.cliente "
                "WHERE p.pedido = %s",
                (doc_id,),
            )
            r = cur.fetchone()
            cur.close()
            if not r:
                return None
            sit = (r.get("situacao") or "").strip()
            return {
                "doc_type": "PED", "doc_label": "Pedido de Venda",
                "doc": int(r["doc"]),
                "cliente_id": int(r["cliente"]) if r.get("cliente") else None,
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "telefone": (r.get("telefone") or "").strip(),
                "data": r["data"].isoformat() if r.get("data") else None,
                "total": float(r.get("total") or 0),
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "obs": (r.get("obs") or "").strip(),
            }
        else:  # OS
            cur.execute(
                "SELECT o.codigo AS doc, o.cliente, o.data_entrada, o.valor, o.situacao, o.obs, "
                "o.descricao_cliente, o.resumo, o.placa, o.marca, o.modelo, o.chassi, o.numero_de_serie, "
                "c.nome AS cliente_nome, "
                "LTRIM(RTRIM(ISNULL(CAST(c.ddd_cli AS NVARCHAR(4)),'') + ISNULL(c.telefone_cli,''))) AS telefone "
                "FROM os o LEFT JOIN cliente c ON c.codigo = o.cliente WHERE o.codigo = %s",
                (doc_id,),
            )
            r = cur.fetchone()
            cur.close()
            if not r:
                return None
            sit = (r.get("situacao") or "").strip()
            veic = " ".join([p for p in [(r.get("placa") or "").strip(), (r.get("marca") or "").strip(), (r.get("modelo") or "").strip()] if p])
            serie = (r.get("chassi") or "").strip() or (r.get("numero_de_serie") or "").strip()
            return {
                "doc_type": "OS", "doc_label": "Ordem de Serviço",
                "doc": int(r["doc"]),
                "cliente_id": int(r["cliente"]) if r.get("cliente") else None,
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "telefone": (r.get("telefone") or "").strip(),
                "data": r["data_entrada"].isoformat() if r.get("data_entrada") else None,
                "total": float(r.get("valor") or 0),
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "obs": (r.get("obs") or "").strip(),
                "descricao_cliente": (r.get("descricao_cliente") or "").strip(),
                "resumo": (r.get("resumo") or "").strip(),
                "veiculo": veic,
                "serie": serie,
            }
    finally:
        conn.close()


def registrar_envio_whatsapp_no_historico(
    servidor: str, banco: str, cliente_id: int, telefone: str, usuario_id: Optional[int],
) -> None:
    """Acrescenta uma linha no topo de `cliente.historico` — mesmo mecanismo
    de texto corrido que `FrmManTMa.frm` (Telemarketing) já usa pra registrar
    contatos manuais (Command2_Click) e que a produção real já usa também
    pra logs automáticos de e-mail/boleto (confirmado por print do usuário —
    mesmo formato de frase, "enviado com sucesso por <usuário> em <data> às
    <hora>. Para o destinatário: <contato>."). Usado aqui pro envio de
    WhatsApp "avulso" (document_type=CLI) também virar uma linha no
    histórico do cliente — "versão completa com histórico" pedida pelo
    usuário, sem precisar de tabela nova. Best-effort: falha aqui nunca
    derruba o envio (mesma filosofia do log_auditoria_service)."""
    from datetime import datetime

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        nome_usuario = "Sistema"
        if usuario_id:
            cur.execute("SELECT nome_guerra FROM funcionarios WHERE codigo_int=%s", (usuario_id,))
            row = cur.fetchone()
            if row and row.get("nome_guerra"):
                nome_usuario = row["nome_guerra"].strip()
        agora = datetime.now()
        linha = (
            f"Mensagem de WhatsApp enviada com sucesso por {nome_usuario} em "
            f"{agora.strftime('%d/%m/%Y')} às {agora.strftime('%H:%M')}. "
            f"Para o destinatário: {telefone}."
        )
        cur.execute("SELECT historico FROM cliente WHERE codigo=%s", (cliente_id,))
        row = cur.fetchone()
        antigo = (row.get("historico") if row else None) or ""
        novo = f"{linha}\r\n\r\n{antigo}" if antigo.strip() else linha
        cur.execute("UPDATE cliente SET historico=%s WHERE codigo=%s", (novo, cliente_id))
        conn.commit()
        cur.close()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()

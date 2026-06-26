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


def get_document_summary(servidor: str, banco: str, doc_type: str, doc_id: int) -> Optional[dict]:
    """Resumo do documento (Pedido ou OS) para montar a mensagem."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if doc_type == "PED":
            cur.execute(
                "SELECT p.pedido AS doc, p.cliente, p.data, p.total, p.situacao, p.obs, "
                "c.nome AS cliente_nome, c.telefone_cli AS telefone "
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
                "c.nome AS cliente_nome, c.telefone_cli AS telefone "
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

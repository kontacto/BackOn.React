import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from db.connection import _open_conn
conn = _open_conn("gibanweb.database.windows.net", "BDREACTAPP", timeout=30)
cur = conn.cursor(as_dict=True)
cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='pedido_venda_prod' ORDER BY ORDINAL_POSITION")
print([c['COLUMN_NAME'] for c in cur.fetchall()])
cur.close(); conn.close()

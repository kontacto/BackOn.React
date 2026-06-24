"""MongoDB opcional — usado só pelos endpoints legados /status.

Se o driver motor não estiver instalado OU MONGO_URL/DB_NAME não estiverem no
ambiente, os endpoints ficam desabilitados (não quebra o app). O `.env` deve ter
sido carregado (load_dotenv) ANTES de importar este módulo.
"""
import os

try:
    from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore
    _MOTOR_AVAILABLE = True
except Exception:
    _MOTOR_AVAILABLE = False

mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')

if _MOTOR_AVAILABLE and mongo_url and db_name:
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    _MONGO_ENABLED = True
else:
    client = None
    db = None
    _MONGO_ENABLED = False

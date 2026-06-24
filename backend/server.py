"""Back-On API — bootstrap.

Aplicação FastAPI: carrega o .env, monta o APIRouter com prefixo /api,
inclui os routers de cada domínio, configura CORS e logging.
Toda a lógica de negócio fica em services/ e os endpoints em routes/.
"""
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# IMPORTANTE: carregar o .env ANTES de importar módulos que leem variáveis de
# ambiente em tempo de import (db.mongo, db.connection).
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Garante que os pacotes locais (db/ models/ services/ routes/) sejam importáveis
# INDEPENDENTE de como o uvicorn é iniciado — seja "uvicorn server:app" a partir
# da pasta backend, "uvicorn backend.server:app" a partir da raiz, ou pelo perfil
# de execução do Visual Studio (cujo diretório de trabalho costuma ser a raiz da
# solução). Sem isto, os imports absolutos abaixo (from routes/db/services...)
# quebrariam e o backend não subiria.
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter, FastAPI  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from db import mongo  # noqa: E402
from routes import (  # noqa: E402
    auth, clientes, controle, descontos, lookups, misc, pedidos,
    produtos, relatorios,
)

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Ordem das inclusões: rotas mais específicas de clientes (find/resumo) já são
# tratadas pela ordem interna do router de clientes.
api_router.include_router(misc.router)
api_router.include_router(auth.router)
api_router.include_router(clientes.router)
api_router.include_router(produtos.router)
api_router.include_router(pedidos.router)
api_router.include_router(descontos.router)
api_router.include_router(controle.router)
api_router.include_router(relatorios.router)
api_router.include_router(lookups.router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    if mongo.client is not None:
        mongo.client.close()

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
    afericao_abastecimento, auth, bomba, bordero, cilindro, clientes, combustivel, combustivel_meta, contatos,
    controle, controle_config, controle_sistema, custo_combustivel, descontos, entrada_saida_caixa, equipamentos,
    estoque_combustivel, fechamento_turno, financeiro, fornecedores, funcionarios, gestor_documentos, ilha,
    impressao, log_auditoria, lookups, margem_lucro, misc, mov_encerrante, notas_fiscais, os, pedido_completo, pedidos,
    permissoes, produto_completo, produtos, produtos_compostos, produtos_niveis, reabertura_turno, relatorios,
    servicos, tabelas_aux, tanque, tanque_estoque, tanque_nf, telemarketing, usuarios, veiculos, viagem, whatsapp,
)

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Ordem das inclusões: rotas mais específicas de clientes (find/resumo) já são
# tratadas pela ordem interna do router de clientes.
api_router.include_router(misc.router)
api_router.include_router(auth.router)
api_router.include_router(clientes.router)
api_router.include_router(produtos.router)
api_router.include_router(produto_completo.router)
api_router.include_router(produtos_niveis.router)
api_router.include_router(log_auditoria.router)
api_router.include_router(pedidos.router)
api_router.include_router(pedido_completo.router)
api_router.include_router(os.router)
api_router.include_router(whatsapp.router)
api_router.include_router(descontos.router)
api_router.include_router(controle.router)
api_router.include_router(relatorios.router)
api_router.include_router(margem_lucro.router)
api_router.include_router(lookups.router)
api_router.include_router(permissoes.router)
api_router.include_router(controle_config.router)
api_router.include_router(controle_sistema.router)
api_router.include_router(impressao.router)
api_router.include_router(gestor_documentos.router)
api_router.include_router(tabelas_aux.router)
api_router.include_router(financeiro.router)
api_router.include_router(entrada_saida_caixa.router)
api_router.include_router(contatos.router)
api_router.include_router(equipamentos.router)
api_router.include_router(cilindro.router)
api_router.include_router(viagem.router)
api_router.include_router(bordero.router)
api_router.include_router(telemarketing.router)
api_router.include_router(notas_fiscais.router)
api_router.include_router(usuarios.router)
api_router.include_router(veiculos.router)
api_router.include_router(funcionarios.router)
api_router.include_router(servicos.router)
api_router.include_router(produtos_compostos.router)
api_router.include_router(fornecedores.router)
api_router.include_router(combustivel_meta.router)
api_router.include_router(ilha.router)
api_router.include_router(combustivel.router)
api_router.include_router(tanque.router)
api_router.include_router(estoque_combustivel.router)
api_router.include_router(custo_combustivel.router)
api_router.include_router(bomba.router)
api_router.include_router(tanque_estoque.router)
api_router.include_router(tanque_nf.router)
api_router.include_router(mov_encerrante.router)
api_router.include_router(fechamento_turno.router)
api_router.include_router(reabertura_turno.router)
api_router.include_router(afericao_abastecimento.router)

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

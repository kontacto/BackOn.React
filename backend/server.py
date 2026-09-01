"""Back-On API — bootstrap.

Aplicação FastAPI: carrega o .env, monta o APIRouter com prefixo /api,
inclui os routers de cada domínio, configura CORS e logging.
Toda a lógica de negócio fica em services/ e os endpoints em routes/.
"""
import asyncio
import logging
import os as stdlib_os  # `os` sozinho colide com `routes.os` (rotas de O.S.), importado mais abaixo
import sys
from contextlib import asynccontextmanager
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
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from db import mongo  # noqa: E402
from routes import (  # noqa: E402
    abertura_dia, afericao_abastecimento, agenda, apuracao_fiscal, auth, backup_sistema, balanca, bancos, bomba, bordero, checkout, cilindro, clientes, combustivel, combustivel_meta, comanda, conta_func, contas, contas_pagar, contas_receber, contatos,
    contingencia_nfe, contratos, controle, controle_config, controle_sistema, cotacao_compra, curva_abc, custo_combustivel, descontos, devolucao,
    entrada_saida_caixa, envio_massa, equipamentos, estoque_combustivel, etiqueta_produto, fechamento_turno, financeiro, fornecedores, funcionarios,
    geracao_boletos, gestao_compras, gestor_documentos, gestor_nfce, gestor_nfse, ia_config, ilha, impressao, inutilizacao_nfe, inventario, layout, log_auditoria, lookups, margem_lucro, mdfe, misc, modificadores, movimentacao_produtos,
    manutencao_indices, mov_encerrante, ncm_cest, nfe_agrupada, nfe_avulsa, notas_fiscais, os, os_completo, painel_financeiro, pedido_completo, pedido_compra, pedidos, permissoes, previsoes, produto_completo, produto_imagem, produtos,
    produtos_compostos, produtos_niveis, projetos, reabertura_turno, recebimento, relatorio_clientes, relatorios, requisicao, retifica, servico_sistema, servicos, tabelas_aux, tanque,
    tanque_estoque, tanque_nf, taxas_ia, telemarketing, transferencia_caixa, transferencia_contas, usuarios, veiculos, viagem, whatsapp,
)
from services import backup_sistema_service, manutencao_indices_service, servico_sistema_service  # noqa: E402

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tarefas de fundo deste backend (ver services/servico_sistema_service.py,
    # services/manutencao_indices_service.py e services/backup_sistema_
    # service.py) — rodam dentro do próprio processo, sem depender de SQL
    # Server Agent (Express não suporta) nem de Tarefa Agendada do Windows
    # configurada manualmente por instalação. Todas canceladas no shutdown
    # junto com o fechamento do Mongo — precisa ser um `lifespan` só (não dá
    # pra misturar com o `@app.on_event` antigo no mesmo app).
    task_atualizacao = asyncio.create_task(servico_sistema_service.loop_verificacao_atualizacao())
    task_manutencao_indices = asyncio.create_task(manutencao_indices_service.loop_manutencao_indices())
    task_backup = asyncio.create_task(backup_sistema_service.loop_backup_sistema())
    yield
    task_atualizacao.cancel()
    task_manutencao_indices.cancel()
    task_backup.cancel()
    if mongo.client is not None:
        mongo.client.close()


app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")

# Ordem das inclusões: rotas mais específicas de clientes (find/resumo) já são
# tratadas pela ordem interna do router de clientes.
api_router.include_router(misc.router)
api_router.include_router(auth.router)
api_router.include_router(clientes.router)
api_router.include_router(produtos.router)
api_router.include_router(produto_completo.router)
api_router.include_router(produto_imagem.router)
api_router.include_router(produtos_niveis.router)
api_router.include_router(log_auditoria.router)
api_router.include_router(pedidos.router)
api_router.include_router(pedido_completo.router)
api_router.include_router(agenda.router)
api_router.include_router(layout.router)
api_router.include_router(ia_config.router)
api_router.include_router(os.router)
api_router.include_router(os_completo.router)
api_router.include_router(projetos.router)
api_router.include_router(retifica.router)
api_router.include_router(whatsapp.router)
api_router.include_router(descontos.router)
api_router.include_router(controle.router)
api_router.include_router(relatorios.router)
api_router.include_router(etiqueta_produto.router)
api_router.include_router(relatorio_clientes.router)
api_router.include_router(envio_massa.router)
api_router.include_router(margem_lucro.router)
api_router.include_router(abertura_dia.router)
api_router.include_router(lookups.router)
api_router.include_router(permissoes.router)
api_router.include_router(controle_config.router)
api_router.include_router(controle_sistema.router)
api_router.include_router(servico_sistema.router)
api_router.include_router(manutencao_indices.router)
api_router.include_router(backup_sistema.router)
api_router.include_router(impressao.router)
api_router.include_router(gestor_documentos.router)
api_router.include_router(tabelas_aux.router)
api_router.include_router(ncm_cest.router)
api_router.include_router(apuracao_fiscal.router)
api_router.include_router(taxas_ia.router)
api_router.include_router(mdfe.router)
api_router.include_router(financeiro.router)
api_router.include_router(entrada_saida_caixa.router)
api_router.include_router(contatos.router)
api_router.include_router(equipamentos.router)
api_router.include_router(cilindro.router)
api_router.include_router(balanca.router)
api_router.include_router(comanda.router)
api_router.include_router(gestor_nfce.router)
api_router.include_router(gestor_nfse.router)
api_router.include_router(contingencia_nfe.router)
api_router.include_router(inutilizacao_nfe.router)
api_router.include_router(nfe_agrupada.router)
api_router.include_router(nfe_avulsa.router)
api_router.include_router(recebimento.router)
api_router.include_router(checkout.router)
api_router.include_router(devolucao.router)
api_router.include_router(transferencia_contas.router)
api_router.include_router(transferencia_caixa.router)
api_router.include_router(contas_receber.router)
api_router.include_router(contas_pagar.router)
api_router.include_router(movimentacao_produtos.router)
api_router.include_router(inventario.router)
api_router.include_router(modificadores.router)
api_router.include_router(requisicao.router)
api_router.include_router(gestao_compras.router)
api_router.include_router(curva_abc.router)
api_router.include_router(cotacao_compra.router)
api_router.include_router(pedido_compra.router)
api_router.include_router(contratos.router)
api_router.include_router(viagem.router)
api_router.include_router(bordero.router)
api_router.include_router(bancos.router)
api_router.include_router(contas.router)
api_router.include_router(previsoes.router)
api_router.include_router(painel_financeiro.router)
api_router.include_router(conta_func.router)
api_router.include_router(geracao_boletos.router)
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

# Serve o build web do frontend (`npx expo export -p web`) no MESMO
# processo/porta do backend — decisão do Atualizador automático (ver
# PENDENCIAS.md > "Atualizador automático de instalações de cliente")
# pra não precisar de um segundo processo/porta só pra arquivos
# estáticos numa instalação de cliente. `FRONTEND_DIST_DIR` é setado
# pelo `updater/apply_update.ps1` apontando pra pasta da versão do
# frontend atualmente ativa; sem essa env var (ambiente de
# desenvolvimento local, sem build de produção), cai no default
# `frontend/dist` relativo à raiz do repo — e se nem esse existir, o
# mount simplesmente não acontece (nunca quebra `uvicorn --reload` local,
# que não tem build nenhum). **Precisa ficar DEPOIS de
# `app.include_router(api_router)`** — um mount em "/" registrado antes
# capturaria `/api/*` também, já que Starlette resolve rotas na ordem em
# que foram registradas.
_frontend_dist_dir = stdlib_os.environ.get("FRONTEND_DIST_DIR") or str((ROOT_DIR.parent / "frontend" / "dist").resolve())
if Path(_frontend_dist_dir).is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist_dir, html=True), name="frontend")

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

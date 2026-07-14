import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from services import tabelas_aux_service as svc

SERV = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"

async def main():
    r1 = await svc.save_cor(SERV, BANCO, None, "Prata", "LB9A")
    print("CREATE:", r1)
    cod = r1["codigo"]

    r2 = await svc.list_cores(SERV, BANCO, "Prata")
    print("LIST:", r2)

    r3 = await svc.save_cor(SERV, BANCO, cod, "Prata Metálico", "LB9A")
    print("UPDATE:", r3)

    r4 = await svc.delete_cor(SERV, BANCO, cod)
    print("DELETE:", r4)

    r5 = await svc.list_cores(SERV, BANCO, "Prata")
    print("LIST after delete:", r5)

asyncio.run(main())

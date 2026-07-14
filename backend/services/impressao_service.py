"""Impressão de rede via socket TCP cru.

Esboço da primeira peça da feature de impressão automática de comandas por
Finalidade do produto (módulo Bar, tela Pedido de Venda) — ver memória de
projeto "Impressão automática por Finalidade" para o desenho completo.
Nenhum navegador tem API de impressão silenciosa; a solução é o backend
mandar os bytes direto pro socket da impressora (impressoras térmicas de
rede aceitam conexão TCP crua, sem driver, na porta 9100 por convenção —
protocolo "RAW"/JetDirect).

Escopo deste arquivo: só a primitiva "manda estes bytes pra este IP:porta".
Ainda faltam (fora do escopo deste esboço):
- Montagem do layout ESC/POS do cupom em si (formatação, corte de papel,
  código de barras etc.) — hoje `conteudo` é texto puro.
- Resolver automaticamente IP/porta a partir da Finalidade do item do
  Pedido de Venda (join com `direcionamento_impressora` + Finalidade do
  produto) — hoje quem chama informa IP/porta explicitamente.
- Caminho de impressoras USB locais (precisa de agente local dedicado,
  fora do backend — ver a memória de projeto).
"""
import asyncio
import socket

DEFAULT_PORT = 9100  # porta padrão RAW/JetDirect de impressoras térmicas de rede
CONNECT_TIMEOUT_SECONDS = 5


def _enviar_rede_sync(ip: str, porta: int, conteudo: str) -> dict:
    ip = (ip or "").strip()
    if not ip:
        return {"success": False, "message": "Informe o IP da impressora."}
    if not conteudo:
        return {"success": False, "message": "Conteúdo vazio — nada para imprimir."}

    # cp850 é a codepage mais comum em impressoras térmicas ESC/POS na
    # América Latina (acentuação PT-BR); impressoras que esperam outra
    # codepage vão precisar de configuração por impressora futuramente,
    # não coberto neste esboço.
    try:
        dados = conteudo.encode("cp850", errors="replace")
    except LookupError:
        dados = conteudo.encode("latin-1", errors="replace")

    try:
        with socket.create_connection((ip, porta), timeout=CONNECT_TIMEOUT_SECONDS) as sock:
            sock.sendall(dados)
        return {"success": True, "message": "Impressão enviada."}
    except socket.timeout:
        return {"success": False, "message": f"Tempo esgotado ao conectar em {ip}:{porta}."}
    except (ConnectionRefusedError, OSError) as e:
        return {"success": False, "message": f"Não foi possível conectar na impressora {ip}:{porta}: {e}"}


async def enviar_rede(ip: str, porta: int, conteudo: str) -> dict:
    return await asyncio.to_thread(_enviar_rede_sync, ip, porta or DEFAULT_PORT, conteudo)

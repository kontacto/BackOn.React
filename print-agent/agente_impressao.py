"""Agente local de impressão silenciosa (polling) — ver
backend/services/impressao_service.py para o desenho completo do lado do
backend, e PENDENCIAS.md (seções "Checkout"/"Pedido Bar") para o contexto
de por que essa peça existe (nenhum navegador tem API de impressão sem
diálogo pro usuário confirmar).

Roda numa máquina Windows com uma impressora térmica USB local instalada
normalmente (com driver, como qualquer impressora do Windows). A cada
`intervalo_segundos`, consulta o backend por jobs pendentes pro
`computador` configurado (GET /impressao/fila/pendentes), manda os bytes
crus pro spooler via win32print (modo RAW — sem diálogo, sem abrir nada
na tela do usuário), e confirma o resultado
(POST /impressao/fila/{id}/confirmar).

Uso:
    1. pip install -r requirements.txt
    2. copiar config.exemplo.json para config.json e ajustar os valores
    3. python agente_impressao.py

Processo independente de qualquer navegador/tela do app — pensado pra
futuramente também rodar como serviço Windows/tarefa agendada (fora do
escopo desta primeira versão, que roda em primeiro plano num terminal).
"""
import json
import sys
import time
from pathlib import Path

import requests

try:
    import win32print
except ImportError:
    # Permite importar este módulo fora do Windows (ex.: rodar os testes
    # unitários em CI Linux) — só falha de verdade na hora de imprimir.
    win32print = None

CONFIG_PATH = Path(__file__).parent / "config.json"


def carregar_config(caminho: Path = CONFIG_PATH) -> dict:
    if not caminho.exists():
        print(f"Arquivo de configuração não encontrado: {caminho}")
        print("Copie config.exemplo.json para config.json e ajuste os valores.")
        sys.exit(1)
    with open(caminho, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for campo in ("api_base", "servidor", "banco", "computador"):
        if not cfg.get(campo):
            print(f"config.json: campo obrigatório '{campo}' ausente ou vazio.")
            sys.exit(1)
    return cfg


def buscar_pendentes(cfg: dict) -> list:
    url = f"{cfg['api_base']}/impressao/fila/pendentes"
    params = {"servidor": cfg["servidor"], "banco": cfg["banco"], "computador": cfg["computador"]}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        print(f"Erro ao consultar fila: {data.get('message')}")
        return []
    return data.get("items", [])


def confirmar(cfg: dict, job_id: int, sucesso: bool, mensagem_erro: str = None) -> None:
    url = f"{cfg['api_base']}/impressao/fila/{job_id}/confirmar"
    payload = {
        "servidor": cfg["servidor"], "banco": cfg["banco"],
        "sucesso": sucesso, "mensagem_erro": mensagem_erro,
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except requests.RequestException as e:
        # Job já foi impresso (ou falhou) fisicamente nesse ponto — só a
        # confirmação ao backend que não chegou. O job fica "ENVIADO" e o
        # próprio backend o recoloca como pendente depois de
        # RECUPERACAO_ENVIADO_MINUTOS, então não há necessidade de retry
        # aqui — só logar pra visibilidade.
        print(f"[job {job_id}] falha ao confirmar resultado ao backend: {e}")


def imprimir(cfg: dict, item: dict) -> None:
    nome_impressora = item.get("impressora") or cfg.get("impressora_padrao")
    if not nome_impressora:
        raise RuntimeError(
            "Nenhuma impressora informada no job nem configurada como padrão (impressora_padrao)."
        )
    if win32print is None:
        raise RuntimeError("pywin32 não instalado nesta máquina — rode 'pip install pywin32'.")

    # cp850 é a mesma codepage já usada pelo backend em enviar_rede
    # (impressoras térmicas ESC/POS, acentuação PT-BR) — mantém os dois
    # caminhos de impressão (rede direta e fila local) consistentes.
    try:
        dados = item["conteudo"].encode("cp850", errors="replace")
    except LookupError:
        dados = item["conteudo"].encode("latin-1", errors="replace")

    handle = win32print.OpenPrinter(nome_impressora)
    try:
        win32print.StartDocPrinter(handle, 1, ("Impressao Automatica", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, dados)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


def processar_um_ciclo(cfg: dict) -> int:
    itens = buscar_pendentes(cfg)
    for item in itens:
        job_id = item["id"]
        try:
            imprimir(cfg, item)
            confirmar(cfg, job_id, True)
            print(f"[job {job_id}] impresso com sucesso.")
        except Exception as e:
            confirmar(cfg, job_id, False, str(e))
            print(f"[job {job_id}] falhou: {e}")
    return len(itens)


def main() -> None:
    cfg = carregar_config()
    intervalo = cfg.get("intervalo_segundos", 3)
    print(f"Agente de impressão iniciado — computador='{cfg['computador']}', polling a cada {intervalo}s.")
    print("Pressione Ctrl+C para encerrar.")
    while True:
        try:
            processar_um_ciclo(cfg)
        except requests.RequestException as e:
            print(f"Falha de conexão com o backend: {e}")
        except Exception as e:
            print(f"Erro inesperado no ciclo de polling: {e}")
        time.sleep(intervalo)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAgente encerrado.")

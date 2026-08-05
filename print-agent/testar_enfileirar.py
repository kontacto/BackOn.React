"""Script de teste manual — enfileira um job de impressão de teste pro
computador configurado em config.json, pra validar o ciclo completo
(enfileirar -> agente busca por polling -> imprime -> confirma) sem
precisar de nenhuma tela do app.

Uso:
    python testar_enfileirar.py
    (com o agente rodando em outro terminal: python agente_impressao.py)
"""
from datetime import datetime

import requests

from agente_impressao import carregar_config

CUPOM_TESTE = """\
================================
   TESTE DO AGENTE DE IMPRESSAO
================================
Data/hora: {agora}

Se este cupom saiu na impressora
sem nenhum dialogo aparecer na
tela, o agente esta funcionando.
================================
""".format(agora=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))


def main() -> None:
    cfg = carregar_config()
    url = f"{cfg['api_base']}/impressao/fila"
    payload = {
        "servidor": cfg["servidor"],
        "banco": cfg["banco"],
        "computador": cfg["computador"],
        "impressora": cfg.get("impressora_padrao"),
        "conteudo": CUPOM_TESTE,
        "tipo": "TEXTO",
    }
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("success"):
        print(f"Job {data['id']} enfileirado com sucesso pro computador '{cfg['computador']}'.")
        print("Se o agente estiver rodando, o cupom de teste deve imprimir em até "
              f"{cfg.get('intervalo_segundos', 3)}s.")
    else:
        print(f"Falha ao enfileirar: {data.get('message')}")


if __name__ == "__main__":
    main()

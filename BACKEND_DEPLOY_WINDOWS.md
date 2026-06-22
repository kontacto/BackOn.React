# Back-On — Guia de Instalação do Backend em Windows

> Guia passo a passo testado e validado. Use sempre `requirements-windows.txt`
> (não o `requirements.txt`, que tem libs internas da Emergent).

---

## 🏗 Arquitetura

```
┌──────────────────────────┐
│   📱 App BackOn (APK)    │
│   - Cadastra Conexões    │
│   - Cada conexão tem:    │
│     • Empresa            │
│     • Servidor (SQL)     │
│     • Banco              │
│     • API (URL backend)  │ ◄── DINÂMICO, configurado no app
└────────────┬─────────────┘
             │ HTTPS / HTTP (via campo "API" da conexão)
             ▼
┌──────────────────────────┐
│   💻 PC Windows          │
│   uvicorn server:app     │ ◄── Este guia
│   na porta 8001          │
└────────────┬─────────────┘
             │ TCP 1433 (LAN da empresa)
             ▼
┌──────────────────────────┐
│   🗃 SQL Server          │
│   Credenciais sa/        │
│   Cmslrav@155 (estáticas │
│   no server.py)          │
└──────────────────────────┘
```

**Multi-tenant**: o mesmo APK atende vários clientes. Cada cliente roda sua
própria API neste guia, e o celular guarda uma **conexão por cliente** com
empresa, servidor SQL, banco e a URL da API.

---

## 📋 Pré-requisitos

1. **Windows 10 ou 11**
2. **Python 3.11, 3.12, 3.13 ou 3.14** instalado com "Add Python to PATH" marcado
   - Download: https://www.python.org/downloads/
3. **Git for Windows** instalado
   - Download: https://git-scm.com/download/win
4. **SQL Server alcançável** pela máquina (mesma rede ou local)
5. **(Opcional)** Visual C++ Build Tools — só precisa se `pip install pymssql` reclamar
   - Download: https://aka.ms/vs/17/release/vs_BuildTools.exe

---

## 🚀 Instalação passo a passo

### 1. Criar pasta de desenvolvimento
```powershell
mkdir C:\desenv
cd C:\desenv
```

### 2. Clonar o repositório
```powershell
git clone https://github.com/SEU-USUARIO/BackOn-mobile.git
cd BackOn-mobile
```
> Substitua `SEU-USUARIO` pelo seu usuário do GitHub.

### 3. Entrar na pasta do backend
```powershell
cd backend
```

### 4. Criar o ambiente virtual Python
```powershell
python -m venv .venv
```

### 5. Permitir execução de scripts (uma vez por usuário do Windows)
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Aperte **Y** quando perguntar.

### 6. Ativar o ambiente virtual
```powershell
.\.venv\Scripts\Activate.ps1
```
Depois disso o prompt fica assim:
```
(.venv) PS C:\desenv\BackOn-mobile\backend>
```

### 7. Atualizar o pip
```powershell
pip install --upgrade pip
```

### 8. Instalar as dependências (USE ESTE ARQUIVO)
```powershell
pip install -r requirements-windows.txt
```
> ⚠️ **NÃO USE** `requirements.txt` — ele tem libs internas da Emergent que não existem no PyPI público.

### 9. Criar/editar o arquivo `.env`
```powershell
notepad .env
```
Cole exatamente isto (apenas 2 linhas — as credenciais SQL `sa`/senha são estáticas no código):
```ini
MONGO_URL="mongodb://localhost:27017"
DB_NAME="backon_aux"
```
Salve (`Ctrl+S`) e feche.

> 💡 **Observação importante**: A conta administrativa do SQL Server (`sa` + senha
> `Cmslrav@155`) está **fixa no arquivo `server.py`** e é a mesma para todos os
> clientes Kontacto. Não precisa configurar nada além disso. O app envia a
> **instância** (servidor) e o **nome do banco** no momento do login.

### 10. Liberar a porta no firewall (PowerShell como Administrador)
```powershell
New-NetFirewallRule -DisplayName "Back-On API" -Direction Inbound `
                    -LocalPort 8001 -Protocol TCP -Action Allow
```

### 11. Iniciar a API
```powershell
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Você verá:
```
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### 12. Testar no navegador
Abra: http://localhost:8001/api/
Deve mostrar:
```json
{"message":"Back-On API ativo"}
```

✅ **API funcionando!**

---

## 🌐 Descobrir o IP da máquina (para o celular se conectar)

```powershell
ipconfig | findstr IPv4
```
Exemplo de resposta:
```
   Endereço IPv4. . . . . . . . . . . . . . : 192.168.18.50
```

Use esse IP no celular: `http://192.168.18.50:8001/api/`

Esse IP+porta é o valor que vai no campo **"API"** da tela de Conexões do app.

---

## 📲 Cadastrar a conexão no app

No celular (ou Expo Go), na tela **Conexões → Nova Conexão**, preencha:

| Campo | Exemplo |
|---|---|
| **Empresa** | `BAR ESTELA` |
| **Servidor (instância SQL)** | `GERDELL` ou `192.168.18.10\SQLEXPRESS` |
| **Banco** | `BARESTELA` |
| **API (endereço do backend)** | `http://192.168.18.50:8001` ← este guia |

> 💡 O campo **API** aceita qualquer URL alcançável pelo celular: IP local,
> domínio público com HTTPS, etc. Múltiplos clientes podem coexistir no mesmo
> celular cada um apontando para sua própria API.

---

## 🧪 Testar login real (manualmente)

Em um **segundo PowerShell**, com a API rodando no primeiro:

```powershell
# Teste 1 — Usuário master (sempre funciona, sem precisar de SQL)
$body = @{
    empresa = "Kontacto"
    servidor = "GERDELL"
    banco = "BARESTELA"
    usuario = "KONTACTO"
    senha = "`$KONT2011"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/api/login" `
                  -Method Post -Body $body -ContentType "application/json"

# Teste 2 — Usuário real da tabela usuarios (precisa SQL Authentication ligado)
$body = @{
    empresa = "Bar Estela"
    servidor = "GERDELL"
    banco = "BARESTELA"
    usuario = "ESTELA"
    senha = "minhasenha_real"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/api/login" `
                  -Method Post -Body $body -ContentType "application/json"
```

> ⚠️ **Observe**: este teste manual usa `http://localhost:8001/api/login` porque
> está rodando no mesmo PC. No celular o app vai usar o IP/URL configurado no
> campo **API** da conexão (ex: `http://192.168.18.50:8001/api/login`).

---

## 🔄 Atualizar para versão nova (dia-a-dia)

Quando houver atualização do código no GitHub:

```powershell
# Pare o uvicorn (Ctrl+C)
cd C:\desenv\BackOn-mobile
git pull
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-windows.txt    # atualiza libs se mudou algo
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

---

## 🛠 Rodar como serviço Windows (produção, opcional)

Para a API subir junto com o Windows e reiniciar sozinha:

### 1. Baixar NSSM
https://nssm.cc/download → `nssm-2.24.zip` → extraia em `C:\nssm`

### 2. Instalar serviço (PowerShell como Administrador)
```powershell
cd C:\nssm\win64
.\nssm.exe install BackOnAPI
```

No diálogo gráfico:
- **Path**: `C:\desenv\BackOn-mobile\backend\.venv\Scripts\python.exe`
- **Startup directory**: `C:\desenv\BackOn-mobile\backend`
- **Arguments**: `-m uvicorn server:app --host 0.0.0.0 --port 8001`
- Aba **Details** → Display name: `Back-On API`
- Aba **I/O** → Output: `C:\Logs\backon-stdout.log` / Error: `C:\Logs\backon-stderr.log`
- Clique **Install service**

### 3. Iniciar
```powershell
nssm start BackOnAPI
```

### 4. Comandos úteis do serviço
```powershell
nssm stop BackOnAPI         # parar
nssm start BackOnAPI        # iniciar
nssm restart BackOnAPI      # reiniciar
nssm remove BackOnAPI confirm   # desinstalar
Get-Content C:\Logs\backon-stdout.log -Wait -Tail 50    # ver logs ao vivo
```

---

## 🐛 Troubleshooting

| Sintoma | Solução |
|---|---|
| `Error: Unable to create directory` ao criar venv | Você juntou dois comandos numa linha. Execute `python -m venv .venv` e `.\.venv\Scripts\Activate.ps1` em **linhas separadas** |
| `Could not find a version that satisfies emergentintegrations` | Você usou `requirements.txt` em vez de `requirements-windows.txt`. Use este último. |
| `uvicorn não é reconhecido` | O `pip install` falhou antes de instalar o uvicorn. Reinstale com `pip install -r requirements-windows.txt` |
| `pymssql` falha na compilação | Instale o "Microsoft C++ Build Tools" (link nos pré-requisitos) **OU** use Python 3.12 (`py -3.12 -m venv .venv`) |
| `Login failed for user 'sa'` | Conta `sa` desabilitada **OU** SQL Server em modo só Windows Authentication. Habilite Mixed Mode no SSMS (Server Properties → Security) + habilite a conta `sa` (Logins → sa → Status) + reinicie o serviço SQL no `services.msc` |
| Mobile não chega na API | Firewall do Windows (rode o comando do passo 10) ou celular em rede diferente |
| `Cannot connect to SQL Server` | Habilite TCP/IP no SQL Server Configuration Manager. Reinicie o serviço SQL. |
| `ModuleNotFoundError: pymssql` (ou outra lib) | Você esqueceu de ativar o venv. Rode `.\.venv\Scripts\Activate.ps1` antes |
| Porta 8001 já em uso | Outro processo está usando. Mate com `Get-Process -Id (Get-NetTCPConnection -LocalPort 8001).OwningProcess \| Stop-Process` |
| App mostra "A conexão selecionada não tem URL da API definida" | Edite a conexão e preencha o campo **API** com `http://SEU-IP:8001` |
| App retorna "Falha na conexão" com nome do servidor SQL | A API foi alcançada com sucesso, mas ela mesma não consegue chegar no SQL. Verifique se o nome/IP do servidor SQL informado no app está acessível pelo PC da API |

---

## 📌 Checklist de instalação rápida

Copie e cole esses comandos um por um:

```powershell
# Setup inicial
cd C:\desenv
git clone https://github.com/SEU-USUARIO/BackOn-mobile.git
cd BackOn-mobile\backend
python -m venv .venv
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements-windows.txt
notepad .env        # cole as 4 linhas do passo 9

# Firewall (Administrador)
New-NetFirewallRule -DisplayName "Back-On API" -Direction Inbound -LocalPort 8001 -Protocol TCP -Action Allow

# Iniciar
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

**Pronto!** Em ~5 minutos a API está no ar em qualquer máquina Windows.

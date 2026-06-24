# Back-On — Deploy do BACKEND (FastAPI) no Azure App Service (Linux)

> Guia para publicar **apenas o backend** (a API FastAPI) no Azure App Service
> a partir do GitHub. O repositório é um **monorepo** (`backend/` e `frontend/`
> lado a lado na raiz), e é por isso que o Azure mostrava a tela
> **"Waiting for content"** — ele não encontrava o app Python automaticamente.

---

## 🧩 Por que dava "Waiting for content"?

O builder do Azure (chamado **Oryx**) só reconhece um app Python se encontrar um
arquivo **`requirements.txt` na RAIZ** do repositório. Como o nosso
`requirements.txt` ficava dentro de `backend/`, o Azure não detectava nada e
servia a página padrão "Waiting for content".

✅ **Já resolvido no código:** foi criado um **`requirements.txt` na raiz** com
as dependências mínimas de produção (FastAPI, Uvicorn, Gunicorn, pymssql, etc.).
Esse arquivo NÃO usa as libs internas da Emergent (que não existem no PyPI
público). Basta dar o push (botão **Save**) que ele já vai junto.

Agora falta **1 ajuste manual no portal do Azure**: definir o *Startup Command*.

---

## ⚙️ Passo 1 — Definir o Startup Command no Azure

1. Acesse o **Portal do Azure** → seu **App Service**.
2. No menu lateral, vá em **Settings → Configuration** (ou **Configurações → Configuração**).
3. Abra a aba **General settings** (Configurações gerais).
4. No campo **Startup Command** (Comando de inicialização), cole **exatamente** isto:

```bash
gunicorn --bind=0.0.0.0:8000 --timeout 600 --chdir backend -k uvicorn.workers.UvicornWorker server:app
```

5. Clique em **Save** (Salvar) e confirme. O App Service vai reiniciar.

> 💡 **O que esse comando faz?**
> - `--chdir backend` → entra na pasta `backend/` antes de iniciar (resolve o monorepo).
> - `server:app` → carrega o objeto `app` do arquivo `backend/server.py`.
> - `--bind=0.0.0.0:8000` → o Azure Linux espera a aplicação na porta **8000**.
> - `-k uvicorn.workers.UvicornWorker` → roda FastAPI (ASGI) por baixo do Gunicorn.

---

## ⚙️ Passo 2 — Garantir o build automático

No mesmo **Configuration → Application settings** (Configurações do aplicativo),
confirme/adicione esta variável:

| Nome | Valor |
|---|---|
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |

Isso faz o Azure instalar o `requirements.txt` da raiz a cada deploy.

> (Para deploy via GitHub/Deployment Center esse valor já costuma vir `true`,
> mas confirme.)

---

## ⚙️ Passo 3 — (Opcional) Variáveis de ambiente do banco

O `.env` **não vai para o GitHub** (está no `.gitignore`), então no Azure as
credenciais vêm dos **valores padrão do código** ou de **App Settings**.

- Para bancos **Azure SQL** (host terminando em `.database.windows.net`), o
  backend usa a conta **`suporte`** automaticamente. Se quiser sobrescrever,
  adicione em **Application settings**:

| Nome | Exemplo |
|---|---|
| `SQL_AZURE_USER` | `suporte` |
| `SQL_AZURE_PASSWORD` | `sua_senha` |
| `SQL_TDS_VERSION` | `7.4` |

> O **servidor** e o **banco** continuam sendo enviados pelo app no momento do
> login (campos da tela de Conexões) — não precisa fixar aqui.

---

## ⚙️ Passo 4 — Liberar o firewall do Azure SQL

No recurso do seu **Azure SQL Server** → **Networking / Firewall**, marque a
opção **"Allow Azure services and resources to access this server"**
(Permitir que serviços do Azure acessem este servidor). Sem isso, o App Service
não consegue falar com o banco.

---

## ✅ Passo 5 — Testar

Depois do deploy + reinício, abra no navegador:

```
https://SEU-APP.azurewebsites.net/api/
```

Deve responder:

```json
{"message":"Back-On API ativo"}
```

E o endpoint de login (teste com o usuário master, que não precisa de SQL):

```
POST https://SEU-APP.azurewebsites.net/api/login
Content-Type: application/json

{
  "empresa": "Kontacto",
  "servidor": "SEU-SERVIDOR.database.windows.net",
  "banco": "BDREACTAPP",
  "usuario": "KONTACTO",
  "senha": "$KONT2011"
}
```

Por fim, no **app mobile**, na tela de **Conexões**, preencha o campo **API**
com `https://SEU-APP.azurewebsites.net` (sem `/api` no final — o app já
acrescenta `/api` sozinho).

---

## 🐛 Se ainda der erro

1. **Veja os logs**: Portal → App Service → **Log stream** (Fluxo de logs) ou
   **Monitoring → Log stream**. Procure por `Application startup complete` (sucesso)
   ou pela linha de erro do Python.
2. **`ModuleNotFoundError`** → o `requirements.txt` da raiz não foi instalado;
   confirme o `SCM_DO_BUILD_DURING_DEPLOYMENT=true` e refaça o deploy.
3. **Continua "Waiting for content"** → o Startup Command não foi salvo; refaça
   o Passo 1 e reinicie o App Service (**Overview → Restart**).
4. **`Login failed` / `Cannot connect to SQL`** → firewall do Azure SQL (Passo 4)
   ou credenciais (`SQL_AZURE_PASSWORD`).

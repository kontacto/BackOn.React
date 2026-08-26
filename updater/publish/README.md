# Publicar uma release (só Kontacto)

Esta pasta **não é instalada em nenhum cliente** — roda só na máquina de
quem publica uma versão nova do Back-On.

## Pré-requisitos (uma vez só)

1. PowerShell com o módulo `Az.Storage`:
   ```powershell
   Install-Module -Name Az.Storage -Scope CurrentUser
   ```
2. Um Storage Account do Azure dedicado à distribuição (separado de
   qualquer Storage Account de cliente), com um container **"releases"**.
3. A **connection string completa** (leitura+escrita) desse Storage
   Account — nunca commitar, nunca colocar em `config.json` (esse arquivo
   é o que vai pro cliente, e leva só a SAS de leitura). Configure antes de
   publicar:
   ```powershell
   $env:BACKON_RELEASES_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
   ```
4. Node/npm instalados (pro `npx expo export -p web`).

## Publicar

```powershell
cd updater\publish
.\publish_release.ps1
```

Publica o `HEAD` atual do repositório (usa `git rev-parse --short HEAD`
como identidade da release — este projeto não usa tags/versão semântica,
ver CLAUDE.md). Pra publicar um commit específico:

```powershell
.\publish_release.ps1 -Commit abc1234
```

O script:
1. Empacota `backend/` (sem `.venv`/`__pycache__`/`logs`/`.env`), grava um
   arquivo `VERSION` dentro do zip (`{"commit", "published_at"}` — é o que
   `GET /api/version` lê numa instalação de cliente).
2. Roda `npx expo export -p web` e empacota `frontend/dist/`.
3. Calcula sha256 dos 2 zips.
4. Sobe os 2 zips + `manifest.json` pro container `releases`.

As instalações de cliente pegam a versão nova automaticamente no próximo
ciclo da Tarefa Agendada `BackOn-Updater` (até ~30 min, ver
`updater/README.md`).

## Gerar a SAS de leitura pro cliente

A connection string completa acima **nunca** vai pra máquina de cliente —
só uma SAS (Shared Access Signature) **de leitura**, com validade longa
(ex.: 1 ano), gerada uma vez e reaproveitada em todos os `config.json` dos
clientes:

```powershell
$ctx = New-AzStorageContext -ConnectionString $env:BACKON_RELEASES_CONNECTION_STRING
New-AzStorageContainerSASToken -Container "releases" -Context $ctx `
    -Permission r -ExpiryTime (Get-Date).AddYears(1)
```

Monte a `manifestUrl` final como:
`https://<conta>.blob.core.windows.net/releases/manifest.json<SAS>`

(a SAS gerada já vem com o `?` inicial — cole direto depois de
`manifest.json`). Essa é a URL que vai em `manifestUrl` no `config.json` de
cada cliente (ver `updater/config.exemplo.json`).

## Antes de publicar — checklist

- [ ] O commit foi testado (não existe ambiente de homologação
      automatizado — publicar é um ato manual e deliberado, é isso que
      controla o que vira release).
- [ ] `pytest tests/unit -q` passa sem regressão nova.
- [ ] Não há mudanças não commitadas sendo publicadas por engano (o script
      avisa, mas não bloqueia).

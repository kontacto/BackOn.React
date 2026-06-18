# Back-On — Roadmap das Próximas Implementações

> **IMPORTANTE**: Este documento contém TODO o contexto necessário para
> continuar o desenvolvimento em uma **nova sessão de chat** com contexto fresco.
> Cole este arquivo no início da próxima sessão.

## ✅ O que JÁ ESTÁ FUNCIONANDO

- Backend FastAPI (`/app/backend/server.py`) rodando no Windows do cliente
- Frontend Expo React Native — Splash, Conexões (CRUD), Login, Principal
- Multi-tenant: cada conexão tem `empresa`, `servidor`, `banco`, `api`
- Login real testado: usuário ESTELA / senha 26171 funciona
- Cifra Caesar +3 implementada (`criptografa_frase` no backend)
- JOIN com `classes_usuarios` para exibir nome do grupo
- Usuário master `KONTACTO` / `$KONT2011` bypass do SQL
- Credenciais SQL `sa`/`Cmslrav@155` hardcoded no `server.py`

## 🎯 PENDÊNCIAS — Decidido fazer A + B + C

### C — Logo + Grupo + Layout Boas-vindas (RÁPIDO, fazer primeiro)
1. Adicionar campo `logo` (URL pública string) em `Connection` no `connections.ts`
2. Input de URL no formulário de conexão (`connections.tsx`)
3. Em `principal.tsx`: trocar avatar genérico pela `<Image source={{uri: session.connection.logo}}>`
4. Trocar label "Função" por "Grupo do Sistema" usando `usuario.classe_label` (já vem do JOIN)
5. Mover info de conexão (servidor + banco + api) para o **topo da tela**, próximo ao nome da empresa
6. Renomear tiles: Cadastros → "Clientes", Operações → "Pedidos"
7. **Remover** os cards `Usuário (usuarioObj)` e `Funcionário (funcionarioObj)` da parte de baixo

### B — Dashboard com totais do dia
Preciso da **schema da tabela `pedidos`**. Pedir ao usuário:
```sql
-- Rodar no SSMS e me enviar:
SELECT TOP 1 * FROM pedidos
EXEC sp_help 'pedidos'
```
3 cards no topo do dashboard:
- Total de Pedidos do dia (`COUNT(*)` filtrando data de hoje + vendedor)
- Valor Produtos do dia (`SUM(valor_produtos)`)
- Valor Serviços do dia (`SUM(valor_servicos)`)

Lista abaixo dos cards: pedidos do dia com nome do cliente + valor total.

Endpoint novo: `POST /api/dashboard` com `{empresa, servidor, banco, usuario}` retornando `{total_pedidos, valor_produtos, valor_servicos, lista[]}`.

### A — Cadastro de Clientes (SCHEMA JÁ EXTRAÍDO ✅)

#### Tabelas (do banco BARESTEL)

**`cliente`** (singular, IMPORTANTE):
- PK: `codigo` int IDENTITY
- Campos relevantes:
  - `cgc_cpf` nvarchar(14)
  - `nome` nvarchar(60) NOT NULL
  - `e_mail` nvarchar(max)
  - `inscre` nvarchar(18) — Inscrição Estadual / Identidade (label dinâmico)
  - `tipo` nvarchar(2) DEFAULT 'H' — **FK para `tipo_cliente.codigo`** (atenção: codigo é INT mas tipo é nvarchar(2), provavelmente vira string como '01', '02')
  - `aceita_email` bit
  - `vendedor` int — **FK para `funcionarios.codigo_int`**
  - `usuario_cadastro` int, `usuario_alteracao` int
  - `data`, `data_alteracao` date
  - `situacao` nvarchar(2) DEFAULT 'A'
  - **Atenção**: já tem campos de endereço inline (`end_cli`, `bairro_cli`, `cep_cli`, `ddd_cli`, `telefone_cli`...) — esses são o endereço/telefone PRIMÁRIO. As tabelas `cliente_end` e `cliente_tel` são para endereços/telefones ADICIONAIS.

**`cliente_end`**:
- `codigo` int — FK para `cliente.codigo`
- `tipo` smallint — **0=Comercial, 1=Cobrança, 2=Entrega**
- `endereco` nvarchar(64)
- `numero` int
- `complemento` nvarchar(max)
- `bairro` nvarchar(35)
- `cidade` nvarchar(35)
- `uf` nvarchar(2)
- `cep` nvarchar(8)
- `Pais` nvarchar(60)
- `sequencia` int IDENTITY (PK)

**`cliente_tel`**:
- `codigo` int — FK para `cliente.codigo`
- `ddd` nvarchar(4) DEFAULT '21'
- `tel` nvarchar(10)
- `descricao` nvarchar(max)
- `sequencia` int IDENTITY (PK)

**`tipo_cliente`**:
- `codigo` int IDENTITY (PK)
- `descricao` nvarchar(50) NOT NULL

#### Endpoints a criar
```
GET    /api/clientes                  ?empresa&servidor&banco&search=&page=&size=
GET    /api/clientes/{codigo}         ?empresa&servidor&banco
POST   /api/clientes                  body: ConnectionInfo + cliente + endereco + telefones[]
PUT    /api/clientes/{codigo}         idem
GET    /api/tipo-cliente              ?empresa&servidor&banco
GET    /api/cep/{cep}                 proxy para viacep.com.br (evita CORS no app)
```

#### Tela "Lista de Clientes" (`app/clientes.tsx`)
- FlatList paginada (20/página, scroll infinito)
- TextInput de busca por nome (debounce 500ms)
- Card: nome + telefone primário (`cliente.ddd_cli + telefone_cli`)
- FAB "+" para novo cliente

#### Tela "Formulário de Cliente" (`app/cliente-form.tsx`)
- KeyboardAvoidingView
- Validar CPF (11 dig) ou CNPJ (14 dig com alfanumérico 2026)
- Label dinâmico: 11 dig → "Identidade", 14 dig → "Insc. Estadual"
- Dropdown Tipo Cliente carregado de `/api/tipo-cliente`
- Seção endereço com radio Comercial/Cobrança/Entrega + busca CEP automática
- Lista de telefones (max 3) com botão "+ adicionar"
- Vendedor = `funcionarios.codigo_int` do usuário logado (já vem em `session.funcionario.codigo_int`)
- Botões: Gravar / Fechar

### Bonus — Permissões (Configurações)
Apenas usuários com `funcionarios.cod_funcao = '1'` (administradores) podem acessar.
Esquema:
- Pode usar uma tabela nova `permissoes_classe(classe_codigo INT, tela NVARCHAR(50), liberado BIT)` 
- Ou ler/escrever `classes_usuarios` com colunas booleanas (`acessa_clientes`, `acessa_pedidos`, etc.)
- **Pedir ao usuário** como ele quer modelar isso.

---

## 📨 Mensagem para começar a próxima sessão

> Olá! Continuando o projeto Back-On. Leia o arquivo `/app/ROADMAP_PROXIMAS_FEATURES.md`
> e o `/app/CLIENTES_SPEC.md`. Já temos backend + login funcionando contra SQL Server real.
>
> Implementar nesta ordem:
> 1. **Fase C** (rápida, ~1h): logo da conexão (URL pública) + ajustes da tela Principal.
> 2. **Fase A** (longa, ~3-4h): cadastro de clientes completo (lista + form).
> 3. **Fase B** (~1h após user mandar schema de `pedidos`): dashboard com totais do dia.
>
> Schema das tabelas `cliente`, `cliente_end`, `cliente_tel`, `tipo_cliente` já
> está no ROADMAP. Use a tabela SINGULAR `cliente` (não `clientes`).


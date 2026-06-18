# Back-On — Especificação: Cadastro de Clientes

## Tabelas envolvidas
- `clientes` (principal)
- `cliente_end` (endereço, 1:N mas vamos limitar a 1)
- `cliente_tel` (telefones, 1:N, máx 3)
- `tipo_cliente` (lookup, FK em `clientes.tipo`)
- `funcionarios` (vendedor = usuário logado, via `funcionarios.codigo_int`)

## Tela "Lista de Clientes"
- Lista paginada (20 por página)
- Busca por: nome, CGC/CPF, telefone
- Colunas: **Nome** + **Telefone (primeiro)**
- Tap no cliente → abre formulário em modo edição
- FAB **"+"** → abre formulário em modo novo

## Tela "Formulário de Cliente" (CRUD)

### Seção: Dados Principais
| Campo | Tipo | Validação |
|---|---|---|
| CGC/CPF | string | **Algoritmo CPF (11 dígitos) ou CNPJ (14 dígitos)**. Suporta alfanumérico (novo CNPJ 2026). Máscara dinâmica. |
| Nome | string | Obrigatório, max 60 |
| Email | string | Email válido se preenchido |
| Insc.Est / Identidade | string | **Label dinâmico**: se CPF → "Identidade", se CNPJ → "Insc. Estadual" |
| Tipo Cliente | dropdown | Carrega de `tipo_cliente` (codigo, descricao) |
| Aceita Email | checkbox | bool |
| Vendedor | hidden | = usuario logado (`usuarios.usuario` → busca `funcionarios.codigo_int` onde `nome_guerra = usuario`) |

### Seção: Telefones (até 3)
Lista de até 3 telefones com botão "Adicionar".
| Campo | Tipo |
|---|---|
| DDD | int (2 dígitos) |
| Número | string |
| Descrição | string (ex: "Comercial", "Celular") |

### Seção: Endereço (apenas 1)
| Campo | Notas |
|---|---|
| Tipo | radio: **0=Comercial / 1=Cobrança / 2=Entrega** (default 0) |
| CEP | Input com **busca automática via ViaCEP** ao digitar 8 dígitos: https://viacep.com.br/ws/{cep}/json/ |
| Endereço | preenchido pelo ViaCEP, editável |
| Número | int |
| Complemento | string |
| Bairro | preenchido pelo ViaCEP, editável |
| Cidade | preenchido pelo ViaCEP, editável |
| UF | preenchido pelo ViaCEP, editável (2 chars) |

### Botões
- **Gravar**: valida tudo → INSERT/UPDATE em `clientes`, depois INSERT em `cliente_end` e `cliente_tel`
- **Fechar**: volta para lista, descartando alterações

## Endpoints do backend a criar
```
GET    /api/clientes?empresa&servidor&banco&search=&page=&size=
GET    /api/clientes/{codigo}?empresa&servidor&banco
POST   /api/clientes   (cria)
PUT    /api/clientes/{codigo}   (atualiza)
GET    /api/tipo-cliente?empresa&servidor&banco   (para dropdown)
```

Cada endpoint recebe `empresa`, `servidor`, `banco` (mesma cifra do login) para
reconectar no SQL Server correto.

## Validações CPF/CNPJ
- CPF: 11 dígitos com algoritmo de validação (módulo 11)
- CNPJ: 14 dígitos com algoritmo (módulo 11 com pesos)
- Alfanumérico (CNPJ 2026): aceita A-Z nas primeiras 12 posições, mantém validação no DV.
- Lib sugerida: `validation-br` no React Native, ou validar no backend Python.

## Plano de entrega em fases

### Fase 1 (próxima sessão)
- Schema confirmation: rodar no SSMS e me enviar:
  - `SELECT TOP 1 * FROM clientes`
  - `SELECT TOP 1 * FROM cliente_end`
  - `SELECT TOP 1 * FROM cliente_tel`
  - `SELECT TOP 5 codigo, descricao FROM tipo_cliente`
  - Tipos das colunas e tamanhos (script create dessas 4 tabelas)
- Backend: 4 endpoints (lista, get-by-id, create, update) + JOIN com tipo_cliente
- Frontend: tela de lista com paginação e busca

### Fase 2
- Frontend: formulário completo com todas as seções
- Validações de CPF/CNPJ
- Integração ViaCEP

### Fase 3
- Pedidos (tela Operações)
- Dashboard com totais reais

### Fase 4
- Tela de permissões (apenas funcao=1)
- Logo da conexão

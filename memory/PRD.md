# Back-On — PRD (Continuação)

## Problema Original
Continuar projeto Back-On. Repo: https://github.com/kontacto/BackOn.React (público).
Banco cloud SQL Server: gibanweb.database.windows.net/BDREACTAPP, user `suporte`, senha `Cmslrav@155`.
Faltam APENAS no frontend (Expo React Native):
1. Combobox vendedor (GET /api/funcionarios — disabled se cod_funcao não for 01/02)
2. Combobox area_atuacao (GET /api/area-atuacao)
3. Cliente resumo abaixo do select (GET /api/clientes/{c}/resumo — telefone + endereço)
4. Validade DD/MM/AAAA com calendário customizado modal
5. Filtros data_ini/data_fim na lista pedidos

Backend já tem TODOS os endpoints prontos.

## Arquitetura
- Frontend: Expo Router (React Native + TypeScript), funciona Android/iOS/Web.
- Backend: FastAPI + pymssql conectando ao SQL Server (Azure SQL).
- Multi-tenant: cada `Connection` (empresa, servidor, banco, api) é gravada em AsyncStorage local.

## Status Atual (Jan/2026)
Após análise do código clonado, itens 1, 2, 3 e 5 **já estavam implementados** no repositório:
- 1, 2, 3 → `app/pedido-form.tsx` (SelectField + resumo)
- 5 → `app/pedidos.tsx` (filtro de data com DateField + chips de situação)

Item **4 (calendário customizado modal)** estava usando o picker nativo `@react-native-community/datetimepicker`, que NÃO é "customizado". Foi reescrito:

### Implementado nesta sessão
- **`/app/frontend/src/components/DateField.tsx`** — reescrito do zero
  - Calendário customizado em Modal (estilo Material/Google)
  - Grid 6x7 com dias do mês
  - Navegação ← / → mês a mês
  - Tap no título "Mês AAAA" abre seletor de ano (grid scrollable, respeita min/max)
  - Locale pt-BR (meses e dias da semana)
  - Realce visual: dia selecionado (preenchido), hoje (contornado), dias fora do mês (acinzentados), dias desabilitados por min/max
  - Rodapé com ações: **Limpar**, **Hoje**, **Cancelar**
  - **Funciona Android + iOS + Web** (só usa Modal/Pressable/View/ScrollView do RN — zero dependência de DateTimePicker nativo)
  - API pública preservada: `value`, `onChange`, `label`, `placeholder`, `testID`, `allowClear`, `minimumDate`, `maximumDate`
  - data-testid completos para teste: `{testID}-modal`, `{testID}-prev`, `{testID}-next`, `{testID}-title`, `{testID}-year-{YYYY}`, `{testID}-day-{YYYY-MM-DD}`, `{testID}-today`, `{testID}-clear-action`, `{testID}-cancel`

## Validação
- `npx tsc --noEmit -p tsconfig.json` → 0 erros em `DateField.tsx` (os 2 erros remanescentes em `cliente-form.tsx` são pré-existentes, fora do escopo).
- `npx eslint src/components/DateField.tsx` → 0 issues.
- Não rodado e2e no Expo porque o ambiente preview está em React Web (porta 3000) e Expo bundler usa 8081 (não exposto externamente). Validação visual será feita pelo usuário no app Expo.

## Backlog / Próximos
- Validar visualmente o calendário no Expo Go (Android/iOS/Web) do cliente.
- (Opcional) Corrigir os 2 erros pré-existentes em `app/cliente-form.tsx` linha 358 (`buscarPorCgc` usado antes da declaração).
- Não foi tocado em mais nada do projeto.

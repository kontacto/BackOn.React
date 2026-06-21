#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================
# (mantido em branco — agentes seguem o protocolo padrão de yaml)
#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

user_problem_statement: |
  Continuar projeto Back-On. Já feito: lista /clientes com busca/paginação +
  endpoint POST /api/clientes. Falta: formulário de cliente (criar/editar)
  com endereço (ViaCEP), 3 telefones max, validação CPF/CNPJ
  (incluindo alfanumérico 2026), dropdown tipo_cliente, label dinâmico
  Identidade/Insc.Estadual. Implementar cliente-form.tsx e endpoints
  GET /api/clientes/{codigo}, POST /api/clientes/create,
  PUT /api/clientes/{codigo}, GET /api/tipo-cliente.

backend:
  - task: "GET /api/tipo-cliente — lookup para dropdown"
    implemented: true
    working: "NA"  # depende do SQL Server real do cliente (não testável no preview)
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Endpoint criado, query SELECT codigo, descricao FROM tipo_cliente ORDER BY descricao. Testado contra localhost falha como esperado (sem SQL Server no preview); requer teste contra BARESTEL real."

  - task: "GET /api/clientes/{codigo} — busca cliente + endereço primário + telefones"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "JOIN cliente x tipo_cliente, retorna {cliente, endereco (TOP 1 cliente_end), telefones (TOP 3 cliente_tel ORDER BY sequencia)}."

  - task: "POST /api/clientes/create — INSERT cliente + cliente_end + cliente_tel (transacional)"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "OUTPUT INSERTED.codigo para pegar PK. Telefone primário replicado em cliente.ddd_cli/telefone_cli para compatibilizar lista existente. data=GETDATE(), situacao='A'. Validação CPF/CNPJ no servidor (inclui alfanumérico)."

  - task: "PUT /api/clientes/{codigo} — UPDATE + regrava endereco e telefones"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "UPDATE cliente, depois DELETE cliente_end/cliente_tel do mesmo codigo e INSERT novamente. data_alteracao=GETDATE(). Mesma validação do create."

  - task: "Validação CPF / CNPJ (numérico + alfanumérico 2026)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "_valid_cpf (módulo 11). _valid_cnpj suporta alfanumérico: ord(c)-ord('0') como valor; pesos clássicos; DV permanece numérico. Testes: CPF 11144477735 OK, CPF 00000000000 FAIL, CNPJ 11222333000181 OK, CNPJ 12ABC34501DE35 OK (alfanumérico)."

frontend:
  - task: "Tela /cliente-form — formulário criar/editar com todas as seções"
    implemented: true
    working: true
    file: "frontend/app/cliente-form.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "KeyboardAvoidingView + ScrollView. Seções: Dados Principais, Telefones (até 3 com add/remove), Endereço (radio Comercial/Cobrança/Entrega + CEP+ViaCEP auto). Header com Back e Gravar. Toast para feedback. Modal para dropdown Tipo Cliente. Carrega tipo_cliente via /api/tipo-cliente. Se ?codigo=X, carrega cliente via /api/clientes/X."

  - task: "Máscara dinâmica CGC/CPF"
    implemented: true
    working: true
    file: "frontend/app/cliente-form.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "CPF: 000.000.000-00. CNPJ numérico: 00.000.000/0000-00. CNPJ alfanumérico: 12.ABC.345/01DE-35. Detecção automática: se digito letra → CNPJ; se <=11 dígitos → CPF; >11 → CNPJ."

  - task: "Label dinâmico Identidade / Insc. Estadual"
    implemented: true
    working: true
    file: "frontend/app/cliente-form.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Validado por screenshot: CPF→'Identidade', CNPJ→'Insc. Estadual'."

  - task: "Integração ViaCEP automática (8 dígitos no CEP → fetch)"
    implemented: true
    working: true
    file: "frontend/app/cliente-form.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Validado: CEP 01310100 preencheu Endereço='Avenida Paulista', Bairro='Bela Vista', Cidade='São Paulo', UF='SP'. Botão lupa também dispara busca manual."

  - task: "Dropdown Tipo Cliente (modal de seleção)"
    implemented: true
    working: true
    file: "frontend/app/cliente-form.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Carregado de /api/tipo-cliente. Modal abre, lista descrições, opção (Nenhum), seleção marca com check."

  - task: "Telefones — até 3 com add/remove dinâmico"
    implemented: true
    working: true
    file: "frontend/app/cliente-form.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Botão Adicionar desabilita ao chegar em 3. Remove com lixeira (só visível quando >1)."

  - task: "Lista /clientes — FAB '+' e tap-to-edit"
    implemented: true
    working: true
    file: "frontend/app/clientes.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "FAB azul flutuante no canto inferior direito → /cliente-form. Cards são Pressable → /cliente-form?codigo=X."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 0
  run_ui: false

test_plan:
  current_focus:
    - "POST /api/clientes/create — INSERT cliente + cliente_end + cliente_tel (transacional)"
    - "PUT /api/clientes/{codigo} — UPDATE + regrava endereco e telefones"
    - "GET /api/clientes/{codigo} — busca cliente + endereço primário + telefones"
    - "GET /api/tipo-cliente — lookup para dropdown"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Restaurei o projeto a partir do repositório GitHub https://github.com/kontacto/BackOn-React.git
      (que o usuário tornou público). Implementei tudo que faltava na Fase 2 (cadastro de clientes):

      Backend (/app/backend/server.py):
      - GET /api/tipo-cliente?servidor=&banco=
      - GET /api/clientes/{codigo}?servidor=&banco= (com endereço + telefones)
      - POST /api/clientes/create (corpo: dados + endereco + telefones[])
      - PUT  /api/clientes/{codigo} (mesmo corpo; transacional — delete+insert dos filhos)
      - Validação CPF (módulo 11) e CNPJ (numérico + alfanumérico 2026)

      Frontend (/app/frontend/app/cliente-form.tsx + clientes.tsx):
      - Formulário completo com todas as seções da SPEC
      - Máscara dinâmica e label dinâmico Identidade/Insc.Estadual
      - ViaCEP automático
      - Dropdown Tipo Cliente (modal)
      - 3 telefones max com add/remove
      - FAB "+" na lista e tap-to-edit nos cards

      Os endpoints SQL Server NÃO foram testados contra a base BARESTEL real
      (não acessível no preview Linux). O usuário deve rodar o backend no
      Windows com pymssql e testar contra BARESTEL para validar as queries
      e o fluxo end-to-end.


  - agent: "main"
    message: |
      [2026-06-21] Implementadas as melhorias de UI do módulo Pedidos solicitadas pelo usuário:

      Frontend novos componentes (/app/frontend/src/components/):
      - DateField.tsx — wrapper para @react-native-community/datetimepicker (formato DD/MM/AAAA)
      - SelectField.tsx — combobox/dropdown reutilizável com busca interna em modal bottom-sheet

      Frontend (/app/frontend/app/pedido-form.tsx) — reescrito:
      - Combobox de Vendedor consumindo GET /api/funcionarios
      - Desabilitado se session.funcionario.cod_funcao NÃO está em ["01", "02"]
      - Combobox de Área de Atuação consumindo GET /api/area-atuacao
      - Card de resumo do cliente abaixo da seleção, consumindo GET /api/clientes/{c}/resumo
        (mostra telefone, endereço completo, e-mail)
      - Campo Validade trocado por DateField nativo (DD/MM/AAAA)
      - Envio de area_atuacao no payload de POST /api/pedidos/create e PUT /api/pedidos/{id}

      Frontend (/app/frontend/app/pedidos.tsx) — atualizado:
      - Botão "options" no header para abrir/fechar painel de filtros
      - Painel com filtros DE / ATÉ (DD/MM/AAAA) usando DateField nativo
      - Envio de data_ini e data_fim no body de POST /api/pedidos
      - Indicador visual (dot vermelho) quando filtros de data ativos
      - Botão "Limpar" para resetar os filtros de data
      - Chips de situação agora rolando horizontalmente

      Validação web preview: tela /pedido-form e /pedidos renderizam todos os elementos
      corretamente, sem erros de bundle ou lint.

      Backend NÃO foi modificado — endpoints já existiam:
      - GET /api/area-atuacao (já implementado)
      - GET /api/funcionarios (já implementado)
      - GET /api/clientes/{codigo}/resumo (já implementado)
      - POST /api/pedidos com suporte a data_ini/data_fim (já implementado)
      - POST/PUT /api/pedidos com area_atuacao (já implementado)

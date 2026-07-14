# Claude Code Instructions (APPIAREACT)

These rules are mandatory when creating or updating frontend screens.

## Scope

- Apply this to web layout only.
- Keep mobile behavior unchanged unless explicitly requested.

## Platform Scope (Web vs Mobile vs Windows)

This project now follows explicit platform separation:

- Web: full application scope (all screens/resources), running in the browser.
- Mobile: focused scope for
  - managerial information (dashboard totals and reports)
  - commercial pre-sales flow (Pedidos and O.S.)
- Windows: native desktop app via `react-native-windows`, sharing the same
  React Native codebase as mobile and talking to the same Python HTTP API —
  no backend changes needed to add this platform. Reserved for features that
  need OS-level access the browser sandbox cannot provide (see
  "Windows-only areas" below). Full backend/frontend architecture standard
  for this platform is at "Padrão Geral de Migração de Telas" at the end of
  this file.
  **PAUSED as of 2026-07-10** — the original motivating case (automatic
  printer enumeration for "Cadastro de Impressoras por Grupo de Produtos")
  turned out not to need this platform at all: that screen is plain manual
  text entry today (see "Windows-only areas" below), and the real feature
  behind it (auto-printing comandas by product Finalidade, for the Bar
  module's Pedido de Venda screen) needs server-driven printing (backend
  → TCP socket for network printers) plus a small dedicated local print
  agent for USB-local printers — neither needs a full react-native-windows
  app. Decided with the user to focus on web and build printing that way
  instead of continuing to fight the RNW/VS2026 toolchain (see "Windows
  Build Setup & Known Workarounds" below for how rough that already was).
  The Windows build itself is left in a working state (`npm run windows`)
  if this gets picked back up later — don't delete it, just don't assume
  new work needs to target it without asking first.

### Web-only areas (must not appear on mobile)

- Group/permission administration screens and controls.
- Auxiliary tables (Tabelas Auxiliares, Marcas, Modelos).
- Cadastro completo de cliente (see Cliente Screens Strategy below).

### Windows-only areas (native desktop, must degrade gracefully on web/mobile)

- Any feature that reads local OS state the browser cannot expose — e.g. the
  "Cadastro de Impressoras por Grupo de Produtos" button (Controle do
  Sistema screen, aba Outros) was the original motivating case: reading
  installed printers and the local machine name automatically. **Correction
  (2026-07-10)**: this auto-detection was never actually implemented — as of
  today `ImpressoraModalContent` (`app/controle-sistema.tsx`) is plain manual
  entry, "Nome do Computador" and "Impressora" are free-text `TextInput`
  fields saved via `saveDirecionamentoImpressora`, no native/platform-specific
  code anywhere in it. It already works identically on web/mobile today — do
  not assume this screen needs Windows-only guarding just because of this
  section; verify against the actual code first. If/when real printer
  enumeration is added here, *that* code should follow the guard pattern
  below (web/mobile message instead of a browser-incompatible call) — this
  section documents the intended pattern for that future work, not a
  currently-enforced restriction.

Implementation rules:

1. Hide web-only entries in mobile navigation.
2. Also block direct mobile route access with a web-only guard message.
3. Do not remove existing mobile pre-sales and managerial flows.
4. Guard Windows-only native calls (printers, machine name, filesystem, etc.)
   behind a platform check; show an explicit "Windows app only" message on
   web/mobile instead of failing silently or crashing.

### Windows Build Setup & Known Workarounds

Getting `react-native-windows` to actually compile on this machine took an
extensive debugging session (2026-07-09) because this project's Visual Studio
is version **2026 (v18.7)** — released after RNW 0.81/react-native-windows
0.81.30 shipped, so none of it was tested against this toolset. All fixes are
now baked into `frontend/scripts/run-windows.ps1` — **always build via
`npm run windows` (or `npm run windows:launch` to also open the app)**, never
call `npx react-native run-windows` directly, or every fix below has to be
rediscovered.

- Toolchain: `react-native-windows` must be the **same patch version** as
  `react-native` (RNW compiles react-native's own C++ sources in place from
  `node_modules/react-native`, it doesn't vendor a copy) — currently
  `react-native@0.81.6` + `react-native-windows@0.81.30`. Don't bump one
  without checking the other (`npm view react-native-windows@<rnw-version>
  peerDependencies` and match `react-native` to whatever patch RNW's own
  `package.json` devDependencies pin).
- To (re)scaffold after a version bump: `npx expo prebuild` (only needed once
  for the initial android/ios shell, harmless to rerun), then
  `npx react-native init-windows --overwrite` (NOT the older
  `react-native-windows-init` package — that only supports RNW ≤ 0.75 and
  errors out on newer versions). Re-run `npx @react-native-community/cli
  autolink-windows --sln windows\frontend.sln --proj
  windows\frontend\frontend.vcxproj` after editing `react-native.config.js`.
- **`init-windows --overwrite` re-adds excluded modules straight into
  `windows/frontend.sln`** (as top-level `Project(...)` entries, not just via
  autolinking) — excluding a module in `react-native.config.js` only stops
  *autolinking* from re-adding it; it does **not** remove an existing `.sln`
  entry. After any re-scaffold, check `grep -n "DateTimePicker\|RNScreens\|
  ReactNativeWebView" windows/frontend.sln` and manually delete the stale
  `Project(...)...EndProject` block plus its `ProjectConfigurationPlatforms`
  lines (matched by GUID) if present, or the solution build will try to
  compile modules that autolinking thinks are gone.
- PowerShell 7 (`pwsh.exe`) must be on `PATH`, even though this project only
  otherwise needs Windows PowerShell 5.1 — RNW's CLI helper scripts
  (`@react-native-windows/find-dotnet-tools`) hard-require it, and if it's
  missing the CLI **silently fails to register the `run-windows`/
  `init-windows` commands at all** (no error, they just don't show up in
  `npx @react-native-community/cli config`). Installed to
  `%LocalAppData%\Microsoft\powershell7` via the official install script
  (`-Destination` + `-AddToPath`, no admin needed) since `winget` isn't on
  this machine either.
- Several environment/MSBuild properties are required (all baked into
  `run-windows.ps1`, see the comments at the top of that file for the
  reasoning behind each): `MinimumVisualStudioVersion=18.0` env var (RNW's
  own escape hatch for its `17.11.0`-to-`18.0` hardcoded VS version range,
  which excludes VS 2026 by 0.7), `CL=/D_SILENCE_EXPERIMENTAL_COROUTINE_DEPRECATION_WARNINGS`
  env var (VS2026's MSVC 14.51 hard-errors on RNW's old-style C++ coroutines
  — **must be set via PowerShell, never Bash/Git Bash**, since MSYS rewrites
  `/D...`-looking values as fake Unix paths and silently corrupts them),
  and `--msbuildprops` overrides for `WindowsTargetPlatformVersion` /
  `TargetPlatformVersion` (RNW pins an SDK version we don't have installed),
  `WindowsAppSDKVerifyTransitiveDependencies=false` (an official Microsoft
  escape hatch, see the `.targets` file's own error text),
  `_WindowsAppSDKFoundationPlatform` / `_MrtCoreRuntimeIdentifier` /
  `HermesPlatform=x64` (internal per-package properties that end up empty in
  full-solution builds, breaking `.lib` path construction), and
  `RnwNewArch=true` (this project's `cpp-app` template is WinUI3/Composition,
  which requires New Architecture in the RNW core to avoid a
  `Microsoft.UI.Xaml` vs `Windows.UI.Xaml` type conflict in old "Paper-only"
  code paths).
- **Windows autolinking is excluded for four community modules** in
  `frontend/react-native.config.js` — their Windows native ports only support
  the old Paper/UWP architecture and hard-fail against `RnwNewArch=true`:
  `@react-native-async-storage/async-storage`, `@react-native-community/
  datetimepicker`, `react-native-screens`, `react-native-webview`. Calling
  into any of these on the Windows app throws "NativeModule not found" at
  runtime today — see the comment block at the top of `react-native.config.js`
  for the specific user-facing impact of each and what to do about it
  (`expo-secure-store` already covers credentials so async-storage's gap is
  low-priority; screens/navigation degrades gracefully without
  `react-native-screens`; datetimepicker and webview need a real Windows
  fallback UI eventually). Re-check each one's Windows support status before
  removing its exclusion — don't assume it's fixed just because a newer
  version is available.

### Windows Runtime: `globalThis.expo` Polyfill (getting past "it builds" to "it runs")

A successful build still crashed instantly at boot ("Cannot read property
'EventEmitter' of undefined") because **Expo does not support
react-native-windows at all** — confirmed via
https://github.com/microsoft/react-native-windows/issues/13534. Almost every
`expo-*` package (expo-router, expo-constants, expo-font, expo-image,
expo-secure-store, ...) depends on `expo-modules-core`, which expects a
native `ExpoModulesCore` TurboModule to install a `globalThis.expo` object at
boot; since that module was never ported to Windows, `globalThis.expo` stays
`undefined` and the first `expo-modules-core` file that reads
`globalThis.expo.EventEmitter` (at import time, unconditionally) throws.

The fix is `frontend/windows-polyfills/setUpExpoGlobal.js`, a pure-JS stand-in
for `globalThis.expo` matching the shape in
`expo-modules-core/src/ts-declarations/global.ts` (`EventEmitter`,
`NativeModule`, `SharedObject`, `SharedRef`, `modules`, `uuidv4`/`uuidv5`,
etc.) — see the comments at the top of that file for the exact shape and
reasoning. Key design points, each learned from a real crash:

- **Invoked from a patched `node_modules/expo-modules-core/src/
  ensureNativeModulesAreInstalled.native.ts`**, not from `index.js` or a Metro
  `serializer.getModulesRunBeforeMainModule` preModule — both were tried
  first and failed: static `import` in `index.js` gets hoisted above
  conditional code by Babel (so the polyfill ran too late regardless of
  source order), and Expo's own Metro CLI wrapper doesn't honor a project's
  customized `getModulesRunBeforeMainModule` for the dev server (config
  tested correct in isolation via `node -e "require('./metro.config.js')..."`
  but the served bundle never included the injected preModule).
  `ensureNativeModulesAreInstalled` is the one place every
  `expo-modules-core` entry point already calls, synchronously, immediately
  before touching `globalThis.expo` — patching it sidesteps needing any
  particular bundle ordering at all. **This patch lives only in
  `node_modules` and is wiped by `npm install`** — no sync script exists for
  it yet (unlike the `.windows.js` overrides below); reapply the one-line
  change (`ensureNativeModulesAreInstalled.native.ts` — call
  `setUpExpoGlobalPolyfillForWindows()` when `Platform.OS === 'windows'` and
  `globalThis.expo` is still unset) if it goes missing after a fresh install.
- **`modules` is a `Proxy`, not a plain object.** Packages like expo-asset
  call `requireNativeModule('ExpoAsset')` at their own *module* level (not
  lazily) — an empty `{}` means that throws "Cannot find native module" the
  instant anything importing expo-asset (expo-font, expo-splash-screen, ...)
  is itself imported, crashing the whole app again one module name at a time
  as each is discovered. The Proxy fabricates a stub for whatever name is
  asked, so the *lookup* always succeeds.
- **Stub methods no-op with a `console.warn`, they don't throw.** The first
  version threw a descriptive error on any call — this broke Expo's own
  internal bootstrap: `expo-router`'s splash-screen handling calls
  `ExpoSplashScreen.internalPreventAutoHideAsync()` in an unawaited/uncaught
  promise chain, and a thrown error there stopped
  `AppRegistry.registerComponent` from ever running, failing the whole app
  over one cosmetic splash-screen call.
- **`ExponentConstants` needs a real value, not a stub function** — it's read
  as a plain property (`Constants.expoConfig`), not called as a method; the
  generic function-stub made `expo-linking` throw ("needs access to the
  expo-constants manifest") because it got a function instead of a config
  object. `KNOWN_MODULE_VALUES` in `setUpExpoGlobal.js` special-cases it to
  `{ manifest: require('../app.json').expo, executionEnvironment: 'bare' }`.
- **`requireNativeViewManager` (native *views*, e.g. `expo-image`'s
  `<Image>`) uses a separate, older lookup** —
  `NativeModules.NativeUnimoduleProxy.viewManagersMetadata` — not
  `globalThis.expo.modules` at all (see
  `expo-modules-core/src/NativeViewManagerAdapter.native.tsx`). Patched
  directly in that file to fall back to `{ viewManagersMetadata: {} }`
  instead of crashing — **do not** try to polyfill this by assigning onto
  `NativeModules` from outside (`NativeModules.NativeUnimoduleProxy = {...}`
  throws "Tried to insert a NativeModule into the bridge's NativeModule
  proxy", RN's `NativeModules` object guards against exactly that). The net
  effect is a red "Unimplemented component" placeholder in place of the
  image — a real, currently-unresolved gap, not a crash.
- **`frontend/index.js` needs a real file** (`require("expo-router/entry")`)
  because RNW's native `App.cpp` always requests the bundle named `"index"`,
  ignoring `package.json`'s `"main": "expo-router/entry"` (that field is an
  Expo-tooling convention, not something the native host reads).
- **`windows/frontend/frontend.cpp`'s `ReactViewOptions.ComponentName` must
  be `"main"`, not the project name** (`"frontend"`, what `init-windows`
  scaffolds by default). `expo-router`'s `registerRootComponent()` always
  calls `AppRegistry.registerComponent('main', ...)` — hardcoded, regardless
  of app/project name (`node_modules/expo/src/launch/
  registerRootComponent.tsx`). Mismatched name here means the JS bundle
  loads fine but the app still fails with `"frontend" has not been
  registered` — **this is a native C++ change, requires a rebuild via
  `npm run windows:launch`, not just a Metro/JS reload.**
- **`@react-native-async-storage/async-storage` throws at *import* time**
  (`NativeModule: AsyncStorage is null`) when its native module is missing,
  unlike the graceful expo-modules-core packages above — so the try/catch
  already present around every call site in `src/utils/storage/index.ts` and
  friends never gets a chance to run; the crash happens before any of that
  code executes. Fixed with platform-specific files following the same
  pattern this codebase already used for web
  (`src/utils/storage/index.windows.ts`, `asyncStorageCompat.windows.ts` —
  in-memory only, cleared when the app closes) — `connections.ts`/
  `mlFilters.ts`/`session.ts` import `AsyncStorage` directly (bypassing the
  `storage` wrapper) so each was repointed at `./asyncStorageCompat` instead
  of the raw package.
- **Metro's `blockList` regex for the generated `windows/` folder must have
  a trailing `/`** (`.../windows/.*`, not `.../windows.*`) — without it, the
  pattern also matches any unrelated folder merely *starting* with the
  string "windows", like `windows-polyfills/`, silently excluding it from
  the bundle. This bug was inherited verbatim from `react-native-windows`'
  own generated `metro.config.js` template — it was never applicable before
  because nothing in this project used a `windows*`-prefixed path.
- **Metro's own cache can go stale in ways `--clear` alone doesn't fix.**
  This project's `metro.config.js` sets a custom on-disk `FileStore` at
  `frontend/.metro-cache/` (shared across web/android) — `expo start --clear`
  clears Metro's own default cache but not this custom store, and Metro also
  keeps a separate `metro-file-map-*` cache under `%TEMP%`. When a bundle
  seems to ignore a source change that should affect it, delete both
  `frontend/.metro-cache/` and `%TEMP%\metro-file-map-*` before concluding
  the code itself is wrong.
- **Set env vars for a Node/Metro dev server via PowerShell, not Bash** — the
  MSYS path-mangling gotcha noted above for `CL` isn't C++-specific; it hit
  Node's `metro.config.js` loading too (`ERR_UNSUPPORTED_ESM_URL_SCHEME`,
  unrelated Node.js/Windows/Metro ESM-loader bug — confirmed independent of
  Node version, reproduced on both v24 and v20 LTS via `nvm-windows`
  installed at `%LocalAppData%\nvm`/`%LocalAppData%\nodejs-nvm`; root cause
  was a genuine `metro-config@0.83.3` bug passing a raw Windows path to
  `import()` instead of a `file://` URL — not worth chasing further once
  the dev server itself started fine).

**Known remaining gaps** (app renders, these show as red "Unimplemented
component" placeholders or silent no-ops, not crashes): `expo-image`'s
`<Image>` has no Windows view manager (placeholder instead of the image);
`react-native-screens`' native header/screen container (excluded — see
above). Both are exactly the kind of feature-level, scoped follow-up this
section's "known remaining gaps" style calls out elsewhere in this file, not
build/toolchain mysteries.

## Legacy VB6 Source Reference

When porting a legacy screen, always trace real field-to-column mappings from the
actual VB6/VB.NET source before writing code — never trust on-screen labels alone.
This has repeatedly caught real label/column mismatches (see the Cliente mapping
below, and the Controle do Sistema screen work).

- **VB6 forms** (`.frm`): `C:\Desenv\VB6\Diario Access-SQL\SQLSERVER\`. This tree has
  one subfolder per business-line variant (`Geral`, `Posto`, `Revenda`, `Tesouraria`,
  `ValPorto`, `Cartorio`, `Clauwan`, ...) — the same form (e.g. `FrmGerCon.frm`) is
  often duplicated across most of them, trimmed down per business line. **`Geral`
  holds the canonical/master version** (most complete, all tabs/controls present) —
  prefer it as source of truth; only check a business-line-specific folder when
  investigating a quirk specific to that line.
- **VB.NET business-logic layer** (compiled code the VB6 forms call over COM, e.g.
  `Backon_Controllers.Nfe.AdicionaCertificadoDigital`): source at
  `C:\Desenv\VB6\vb.net\APICamadas\BackOn`. Projects of note: `Backon.Controllers`
  (NFe/NFSe/MDFe emission, `Certificado.vb` — X.509 certificate parsing, TEF/SiTef),
  `Backon.Data` (DAOs), `BackOn.Entity` (EF models). Use this whenever a `.frm`'s
  button/DLL call needs tracing beyond what the VB6 source alone shows — e.g. this is
  how "Certificado Digital" upload (Controle do Sistema screen) was confirmed to be
  local `.pfx` parsing only, no remote signing API, making it portable with Python's
  `cryptography` library.
- Grep pitfall: a plain recursive grep across the VB.NET tree can silently skip real
  `.vb` source (encoding-related false negatives) and match only compiled `.dll`/
  `.pdb` artifacts instead — always add `--include="*.vb"` (or equivalent) when
  searching this tree for source content.
- **VB6 global modules** (`.bas`, not `.frm`): declare app-wide global variables and
  shared functions used across every form (e.g. `Mdl_Proc.bas` — one per business-line
  folder just like `.frm`s, ~40k lines each, covers everything from date/string
  helpers to tax-reform calculations). This is where to look when a `.frm` references
  a bare identifier with no `Dim`/`Set` in that form itself (e.g. `DATESIST`,
  `NomeComputador`, `UsuarioLogado`, `ValorSQL`, `Retorna_Codigo_Func`,
  `AbreBancoADO`/`fechaconexoes`) — these are globals declared in a `.bas` module,
  set once at app startup and read everywhere afterward as an in-memory global for
  the lifetime of that VB6 process.

### Porting VB6 global state (no backend-side globals)

**Added 2026-07-13, user-directed** (arose from `DATESIST` — Posto de Combustível's
"data de movimento" global, ver `services/posto_common.py::data_movimento`). VB6
globals like `DATESIST` work in the legacy app because each installation runs its own
single-user process against a single database — set once at startup, safe to hold in
memory for the rest of the session.

This backend is different: one stateless FastAPI process serves every request, for
every `servidor`+`banco` (empresa), concurrently. **Never port a VB6 global as a
backend-side global/module-level variable** — it would leak one empresa's value into
another's request, or go stale the moment the underlying row changes (e.g. `DATESIST`
advances whenever Fechamento de Turno runs). Instead:

- Re-derive the value with a plain query, scoped to the cursor/connection already open
  for that request (e.g. `data_movimento(cur)` just does
  `SELECT TOP 1 data_movimento FROM controle` — no caching, no module-level state).
  Same pattern already used for `controle.qtd_turnos` in `ilha_service.py`.
- If the frontend wants to show/default to this value, fetch it per-request from the
  backend too (a small dedicated endpoint, or as part of a screen's own data load) —
  don't cache it client-side across the whole session either, since it can change
  mid-session (turno closing) independent of any single screen's own state.
- This isn't unique to `DATESIST` — apply the same rule to any other VB6 global found
  while porting a screen (session globals, "current company" globals, etc.).

### Don't blindly replicate VB6-era hacks as business rules

**Added 2026-07-13, user-directed** ("tem rotina que às vezes acho que nem vale a pena
importar do VB6... muitos truques e bacalhaus que precisam ser feitos por limitação da
linguagem"). Not everything in a `.frm`/`.bas` is a business rule worth porting
literally — plenty of it is a workaround for VB6/Access-era limitations (no real
transactions, no window functions, no refactoring tools, recordsets navigated by hand):
hardcoded one-off data-correction scripts left behind on a hidden button, cross-record
SQL patches to resync a redundant field, malformed SQL that would error if it ever ran,
FIFO-by-hand loops that a modern `SUM()`/window function would replace in one line.

- Before porting a chunk of legacy logic, separate **real business rule** (validation
  order, allowed ranges, what must stay consistent) from **implementation-era
  workaround** (how VB6 happened to achieve that, given its tooling).
- Replicate the rule; re-implement the workaround idiomatically for this stack (real
  transaction, a constraint, a modern SQL aggregate) — don't transliterate the VB6
  code line-by-line just because "that's what the legacy does."
- Still applies: never *assume* a business rule that isn't in the source (section 9,
  "Regras Importantes") — this is the opposite failure mode, don't over-correct into
  assuming everything IS a business rule just because it's present in the code either.
  When genuinely unsure whether something is a rule or a workaround, ask, or register
  it as an open question — don't guess by replicating for safety.

### Field-level separation (not just screen-level)

Platform separation is not only about which screens/routes exist — the same underlying
table can have fields that are web-only even when the record itself (e.g. `cliente`) is
shared with mobile.

1. Do not assume "the table already has a mobile screen" means all of that table's fields
   are safe to add to the mobile screen.
2. When a new column/field is added to a shared table, decide explicitly whether it belongs
   in the mobile quick form or is web-only advanced data — default to web-only unless the
   user asks for it on mobile.
3. This same rule applies going forward to other shared tables, not only `cliente`.

## Cliente Screens Strategy

Use two client registration experiences:

- Cadastro rapido de cliente (`frontend/app/cliente-form.tsx`):
  - available on both web and mobile
  - used in pre-sales contexts (Pedidos/O.S.) and future quick flows the user points to
  - keep this form lean — do not add advanced/complementary fields here

- Cadastro completo de cliente (`frontend/app/cliente-completo.tsx`, web-only):
  - dedicated full CRUD screen for web only, blocked on mobile via web-only guard
  - structured with tabs inspired by the legacy VB6 client registration screen
    (`frmmanclie.frm`, `FrmmanClie` — the ground-truth reference the user provided; source
    of the mapping below)
  - includes fields not shown in mobile quick form
  - designed to accept additional related entities/tables in future iterations
    (beyond the tables already used by cadastro rapido: `cliente`, `cliente_end`, `cliente_tel`)

### Legacy field-to-tab mapping (`frmmanclie.frm`)

Do not re-derive this from scratch in a future session — it was extracted once from the
full VB6 source the user pasted. Extend it here if more of the legacy screen gets built out.

- **Dados Principais** (`Frame9`): codigo, cgc_cpf, nome (razao social), nome_fantasia,
  data (data cadastro, readonly), data_nasc (CPF only) / data abertura (CNPJ only),
  inscr_est (label "Identidade" for CPF / "Insc. Estadual" for CNPJ — already reproduced
  via `labelInscre` in the current quick form), inscr_mun (CNPJ only, separate field —
  **not the same as `inscre`**), sexo (CPF only), situacao (Ativo/Inativo radio) +
  inativo_em (date), site, e_mail, aceita_email, **Telefones grid** (table `cliente_tel`),
  **Enderecos grid — multiple rows, CRUD Incluir/Alterar/Excluir** (table `cliente_end`,
  tipo 0-2 label differs by CPF vs CNPJ, tipo 4 = "Prest. Servico"), historico (free text
  log), and `status` (FK `cliente.STATUS_CLIENTE` → dedicated lookup table
  `STATUS_CLIENTE`, codigo/descricao: A=Ativo, C=Cancelado, D=Desativado, E=Excluido,
  F=Fechado, R=Reservado, S=Suspenso — **not** the generic `situacao` table, which
  happens to hold identical content in this test DB but is a different table; confirmed
  directly by the user 2026-07-01). All of the above are implemented (`useClienteForm.ts`
  + `cliente-completo.tsx`, backend in `clientes_service.py`/`schemas.py`,
  `/api/status-cliente` lookup). **Business rule**: any `STATUS_CLIENTE` other than 'A'
  blocks new Pedido/O.S. creation for that client ("nenhuma movimentação — venda,
  pré-venda — permitida"); enforced server-side in `_check_cliente_ativo`
  (`services/pedido_common.py`), called from both `_save_pedido_sync`
  (`pedidos_service.py`) and `_save_os_sync` (`os_service.py`) on the CREATE path only
  (editing an already-open Pedido/O.S. is unaffected — that's gated separately by the
  Pedido/OS's own `situacao`). A client with `STATUS_CLIENTE` NULL/empty (legacy data
  gap) is treated as Ativo. **Not implemented**: fotografia (webcam/photo, stored on
  filesystem + `cliente_anexos`) — no upload/webcam infra exists yet in this codebase
  (not even for produtos, which only reads a static file by codigo).
- **Dados Secundarios** (`Frame11`): contato (single text field, distinct from the
  Contatos tab), limite_credito, desconto (global client discount), regime_tributario
  (`crt` — hardcoded NFe enum, not a DB lookup), nao_contribuinte (DB column is actually
  `credita_icms` — legacy caption/column mismatch), consumidor_final,
  tributa_iss_fora_municipio, fatura_para (checkbox) + cliente_principal (lookup by
  codigo, resolved via `/clientes/{codigo}/resumo`; DB column `faturar`) + prazo
  (`prazo_faturamento`), indicador_presenca (`indpres` — hardcoded NFe/NFC-e enum, not a
  DB lookup), canal_aquisicao_cliente (lookup table `canal_aquisicao_cliente`),
  **tipo_cliente (lookup table `tipo_cliente`, DB column `cliente_forn`)**, dia_contato /
  dia_entrega (lookup `dia_semana`), forma_pagamento (lookup `forma_pagamento`), segmento
  (lookup `segmentos`), rota (lookup `rotas`), regiao (lookup `regioes`), email_cobranca,
  email_nfe (xml/danfe), centro_custo_cliente (lookup `centro_custo`), conta_transf_caixa
  (lookup `contas`), cobra_tarifa_bancaria + tipo_cobranca_tarifa (Boleto/NFe),
  valor_frete, classe_caixa/sub_classe_caixa (lookup `classes`/`sub_classes`). All of the
  above are implemented. **Not implemented**: vendedor stays auto-assigned from session
  (legacy makes it editable here via `funcionarios` lookup — intentionally not changed);
  conta_transf_contabil (lookup `Plano_<ano_exercicio>`, year-scoped chart of accounts —
  which "ano_exercicio" to use is unresolved); the per-client product price override
  sub-feature ("Tabela de Preco do Cliente": `tabela_cliente` lookup + `tabela_preco_ajuste`
  table keyed by cliente+codigo_int, editable desconto/acrescimo per product) — its own
  future sub-screen.
- **Contatos** (`Frame3`/`Frame10`): a genuinely separate entity — contact **people**,
  not phone numbers. Table `cliente_contato` (codigo, contato, setor, cargo, ddd,
  telefone, ddd_fax, fax, ddd_celular, celular, e_mail, sexo). Do not confuse with the
  Telefones grid on Dados Principais. Implemented as replace-all-on-save (same pattern as
  telefones/enderecos — no per-row update/delete endpoint, the whole list is sent on
  every save).
- Also referenced but hidden/feature-flagged in the legacy form: `cliente_filiacao`
  (pai/mae, only for a "Clinica" mode) — lowest priority, likely out of scope entirely.

Column names above were cross-checked against a live MSSQL instance (instance `GERDELL`,
database `BARESTELA`, 2026-07-01) via `INFORMATION_SCHEMA`/`sys.foreign_keys`, and the
backend code was corrected to match. Real names differ from the VB6-derived guesses in
several places — worth remembering if this area is touched again:
- `cliente.fantasia` (not `nome_fantasia`), `cliente.DATA_ENCERRAMENTO_CLIENTE` (not
  `inativo_em`), `cliente.TRIBUTA_ISS_FORA` (not `..._municipio`), `cliente.forma_pag`
  nvarchar(3) (not `forma_pagamento`/int), `cliente.faturamento_principal` (the "Fatura
  Para" checkbox; `faturar` is the actual `cliente_principal` FK, as already noted above).
- `cliente.segmento` and `cliente.forma_pag` are **string** FKs (`segmentos`/
  `forma_pagamento`.codigo are nvarchar(3)), not ints — API contract for these two is
  `str`, unlike the other Dados Secundarios FKs which are genuinely int.
  `cliente.canal_aquisicao_cliente` is `NOT NULL` (defaults to 0 at the DB level, but only
  when the column is omitted — the app must never send an explicit `NULL`).
  `cliente_contato.ddd`/`ddd_fax` are `smallint`, not text.
- `dia_semana`'s primary key column is `dia`, not `codigo` (the generic
  `_list_codigo_descricao_sync` lookup helper takes a `codigo_col` override for this).
- `cliente.STATUS_CLIENTE` (nvarchar(2)) is the "status" field from the legacy mapping.
  **Correction (2026-07-01, user-confirmed via screenshot)**: it is a soft FK to its own
  dedicated lookup table `STATUS_CLIENTE` (codigo/descricao: A/C/D/E/F/R/S), not the
  generic `situacao` table — they happen to hold identical rows in this test DB, which is
  what led to the initial mixup. Lookup endpoint is `/api/status-cliente`
  (`lookups_service.list_status_cliente`, hook exposes `statusClienteOptions`). See the
  "Business rule" note above this list for the movement-blocking behavior tied to this
  field.
- `cliente.tipo_cobranca_tarifa` is `nvarchar(1)` — stores `'B'`/`'N'`, not the words
  `"Boleto"`/`"NFe"`.
All of the above was validated with a live insert → fetch → update → fetch → delete round
trip against `GERDELL`/`BARESTELA`, plus a smoke test of every new lookup endpoint.

Routing convention:

- `frontend/app/clientes.tsx` (general client list/management screen, reached from the
  Cadastros hub) opens `cliente-completo` on web and `cliente-form` on mobile.
- `pedido-form.tsx` / `os-form.tsx` (pre-sales quick-add) always open `cliente-form`,
  regardless of platform — these stay on the quick form even on web.

Shared logic between the two screens (CPF/CNPJ validation, ViaCEP lookup, telefones
list management, save/load) lives in `frontend/src/hooks/useClienteForm.ts` — extend that
hook rather than duplicating logic when both screens need the same behavior.

## Transações Screens Strategy

**Added 2026-07-13, user-directed `[GLOBAL]`.** Same split pattern as "Cliente
Screens Strategy" above, applied to Pedido and O.S.: a lean version for
mobile pre-sales, and a full version for web-only back-office use.

- **Pedido/O.S. rápidos** (`frontend/app/pedido-form.tsx`, `os-form.tsx`,
  reachable from the mobile "Tela Principal"): unchanged, keep exactly as they
  are today — built for the mobile commercial pre-sales flow (see "Platform
  Scope" above). Their permission entries (`PEDIDO`, `OS`) stay as they are
  too, just re-homed under the renamed permissions branch below — no behavior
  change, no re-grant needed (permission grants key off the leaf `tela`
  values `PEDIDO`/`OS`, not the parent menu wrapper, so renaming the wrapper
  doesn't touch any already-granted permission).
- **Pedido/O.S. completos** (new, web-only): full-featured versions matching
  the scope of the legacy VB6 "Transações" top menu (screenshot reference:
  Produtos, Pré-Vendas, Compra, Contrato, Notas Fiscais, Gestor de Devolução,
  Gestor de Projetos, Vendas, Recibos — a much broader transactional menu
  than today's quick pre-sales forms). **Not migrated yet** — building the
  real "completo" business logic requires tracing the actual legacy
  Pedido/O.S. source form(s) field-by-field first (see "Legacy VB6 Source
  Reference" — do not guess field/behavior scope from the screenshot alone).
  Scaffolding only for now: new top-level tab "Transações"
  (`frontend/app/(tabs)/transacoes.tsx`), **web-only** (`Platform.OS ===
  "web"`, same conditional-`href` pattern as the "Financeiro" tab — no
  module-flag gating like Posto has, this isn't segment-specific). See
  PENDENCIAS.md for the open item.
- **Update 2026-07-13, user-directed**: the **list screens are shared**
  between Mobile and Completo — `frontend/app/pedidos.tsx`/`os.tsx` (already
  built for the mobile pre-sales flow) are also what "Pedido Completo"/"O.S.
  Completa" open to, there's no separate list screen for the Completo
  variant. There is no standalone placeholder screen for this pair anymore
  (`transacao-placeholder.tsx` was deleted) — both `transacoes.tsx`'s
  "Pedido Completo"/"O.S. Completa" cards and `ModuleTiles.tsx`'s Tela
  Principal cards route straight to `/pedidos`/`/os`. What's still missing
  is only the **detail/edit screen**: `pedidos.tsx`/`os.tsx`'s access gate
  was widened to `can("PEDIDO.ABRIR") || can("PEDIDO_COMP.ABRIR")` (same for
  OS) so either variant can open the list, but tapping a row only navigates
  to the mobile quick edit (`pedido-form.tsx`/`os-form.tsx`) when
  `can("PEDIDO.ABRIR")`/`can("OS.ABRIR")` — for a group with only the
  Completo permission, the tap is a deliberate no-op until a real "Pedido
  Completo"/"O.S. Completa" edit screen is built and wired in as the
  alternate destination for that same tap.
- **Permissions catalog**: the `MOVIMENTO` menu was renamed to `TRANSACOES`
  ("Transações") in `backend/services/permissoes_service.py` — same
  `PEDIDO`/`OS` children (mobile quick forms, untouched), plus new
  `PEDIDO_COMP`/`OS_COMP` children for the future complete screens. This
  matches the user's explicit instruction: the quick pre-sales screens stay
  in the **Transações permissions tree**, but must **not** appear as tiles in
  the **Transações navigation menu** (the tab only shows the two "completo"
  tiles) — permissions grouping and navigation menu contents are
  intentionally different here, don't try to make them mirror each other for
  this specific case.
- Master-user bypass and permission-catalog alphabetical-sort rules apply
  here exactly as documented elsewhere in this file — no special case.
- **Mobile x Completo são mutuamente exclusivos `[GLOBAL]`, added 2026-07-13
  user-directed**: in the Permissões screen tree, checking "Pedidos Mobile"
  (`PEDIDO`) auto-unchecks "Pedido Completo" (`PEDIDO_COMP`) and vice versa;
  same pairing for "OS Mobile" (`OS`) / "O.S. Completa" (`OS_COMP`).
  Implemented in `frontend/app/permissoes.tsx` (`EXCLUSIVE_PAIRS` +
  `applyPedidoOsExclusivity`, called from both `toggleNode` — direction-aware,
  clears whichever counterpart matches the clicked node's `tela` — and
  `toggleAll`/bulk toggles, which fall back to keeping the Mobile side and
  clearing Completo when both would otherwise end up checked at once, since
  Completo is still a placeholder). On the Tela Principal
  (`frontend/src/components/principal/ModuleTiles.tsx`), the Pedidos/O.S.
  cards are visible if either the Mobile or the Completo permission is
  granted, and both route to the same shared list (`/pedidos`, `/os` — see
  the update above); the tap-through-to-edit behavior inside that list is
  what actually differs by permission, not the card itself.
- Group labels in the catalog were renamed for clarity: `PEDIDO` displays as
  "Pedidos Mobile" and `OS` as "OS Mobile" (previously "Pedidos"/"Ordem de
  Serviço") — distinguishes them from "Pedido Completo"/"O.S. Completa" in
  the tree UI. Pure label change, no key/behavior change.

## Web Layout Standard

Use the shared web layout tokens from:

- `frontend/src/theme/webLayout.ts`

Required pattern for web screens:

1. Centered content container with consistent max width.
2. Filter and form blocks rendered as visual cards.
3. Scroll content aligned to center on web.
4. Prefer shared base styles/tokens instead of per-screen custom values.

## Compact Size Variant (Web)

When the user asks to reduce card blocks significantly ("50% smaller" look), use the compact variant:

- compact card max width: 560
- compact section/card padding: spacing.md
- compact internal item padding/gap: spacing.sm

Use this compact variant for list-like cards (example: navigation tiles such as Tabelas Auxiliares).
Do not apply compact sizing by default to all report screens unless explicitly requested.

## Field Width Standard (Form Rows)

**Added 2026-07-10, user-directed** ("esses 3 campos cabem na mesma
linha. Código e situação é um campo pequeno" — pointing at the legacy
VB6 form as the sizing reference). Don't default every field in a
`rowFields` row to a 50/50 `flex: 1` split — size each field to what it
actually holds:

- Short codes/enums (situação, UF, CST, ICMS code, a 2-3 digit prazo,
  DDD, CEP) → narrow fixed width. Reference widths already in use:
  `colTiny` (~90px, 1-3 char fields), `colNarrow` (~140px, up to ~8 char
  codes like `Código`) in `app/servicos.tsx`; `enderecoUfCol`/DDD columns
  in `app/cliente-completo.tsx`.
- Free text that can run long (Descrição, nome, endereço) → `flex: 1`
  (`colFlex`) so it absorbs whatever width the narrow siblings don't need.
- Pack as many fields as legitimately fit on one row instead of
  defaulting to two-per-row — check the legacy VB6 form's own layout
  first (see "Legacy VB6 Source Reference" below) rather than guessing;
  the original screens already got this sizing right.

## Required Tokens

Always use these exports when styling web screens:

- `WEB_CONTENT_MAX_WIDTH`
- `WEB_SCROLL_CENTER`
- `WEB_CONTENT_SHELL`
- `WEB_FILTER_CARD`

## Implementation Recipe (New Screen)

1. Import tokens in the screen style file.
2. Keep existing mobile styles as-is.
3. Add `isWeb = Platform.OS === "web"`.
4. Use web-only style composition:

```tsx
<ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
  <View style={isWeb ? styles.webShell : undefined}>
    <View style={[styles.filters, isWeb && styles.filtersWeb]}>
      {/* filters/form */}
    </View>
    {/* content */}
  </View>
</ScrollView>
```

5. Map style keys to shared tokens:

```ts
scrollWeb: WEB_SCROLL_CENTER,
webShell: WEB_CONTENT_SHELL,
filtersWeb: WEB_FILTER_CARD,
```

## Modal/Selector Standard (Web)

For selectors (example: group/class picker), use centered modal card with the same visual language:

- max width based on `WEB_CONTENT_MAX_WIDTH`
- surface background
- border + radius + spacing consistent with filter cards

**Update (2026-07-10, user-directed — "formatação do slide todos tem que
ser da mesma forma... pegue um slide em que tem formatação de redução
forte")**: every slide-up/selector modal must use ONE consistent
formatting, not a mix of bottom-sheets and centered cards. The canonical
reference is `SelectField.tsx`'s `compactWeb` pattern — copy it exactly,
don't invent a new variant per screen:

- Mobile (or non-web): full-width bottom sheet, only top corners rounded
  (`borderTopLeftRadius`/`borderTopRightRadius: radius.lg`), anchored to
  the bottom (`justifyContent: "flex-end"`).
- Web: centered card, `justifyContent: "center"`, `maxWidth: 560`,
  `alignSelf: "center"`, full `radius.lg` on **all four corners**
  (`borderBottomLeftRadius`/`borderBottomRightRadius` added back on top of
  the mobile top-radius), plus a full `borderWidth: 1` border — this is
  the "redução forte" (strong corner rounding) the user is referring to.
- Always wrap in `AppModal` (not a raw RN `Modal`), for consistency with
  every other modal in the app even though the Windows platform itself is
  currently paused (see "Platform Scope" above).
- `NiveisModal.tsx` was fixed to follow this exact pattern (previously a
  raw bottom-sheet-only `Modal`, inconsistent with `SelectField` — fixed
  when it was reused for the read-only Classificação Mercadológica picker
  in Serviços). Use it as the second reference implementation alongside
  `SelectField.tsx`.
- `frontend/src/components/pedido/ClientSearchModal.tsx` (client picker,
  shared by Pedido/O.S./Contatos/Equipamentos) had the same gap — fixed
  2026-07-12 (`modalBgWebCompact`/`modalCardWebCompact` added to the
  shared `pedido/styles.ts`, applied conditionally on `Platform.OS ===
  "web"`). Any other modal still found using a raw bottom-sheet-only
  style on web should get the same treatment — this is a standing
  project-wide requirement, not a one-off fix per screen.

## Padrão de Campo de Data (Web)

**Added 2026-07-13, user-directed** ("os filtros de datas também
desproporcional. tras uma experiência não favorável para um design de
tela moderno e bonito"). Never use a raw `<input type="date">` (or
`type="time"`) styled inline with a screen-local `webDateInputStyle`
object — this pattern was copy-pasted across several screens
(Telemarketing, Contatos, Equipamentos, Entrada/Saída de Caixa, Notas
Fiscais) and had two real problems: (1) `width: "100%"` on a native date
input defaults to `box-sizing: content-box`, so padding+border get added
**on top of** the declared width, making the field visibly wider/
disproportionate next to a sibling `TextInput` (which react-native-web
already renders as `border-box`) — this alone caused the "campo Data
desproporcional ao campo Valor" bug; (2) even once sized correctly, the
native browser chrome (raw placeholder segments, default spinner buttons,
unstyled calendar icon) reads as an unstyled HTML form control dropped
into an otherwise polished, custom-themed UI.

**Always use `frontend/src/components/WebDateField.tsx`** instead:

- Wraps the native `<input type="date">` (or `type="time"` via the
  `type` prop) in a `View` that owns the visual chrome — border, radius,
  background, focus ring (`colors.brandPrimary` border on focus) —
  exactly matching `TextInput`/`SelectField`'s look. The native `<input>`
  itself is stripped to `border: none, background: transparent`, so the
  wrapper is the only thing the user visually sees as "the field".
  `boxSizing: "border-box"` is set explicitly, which is the actual fix
  for the width bug above.
- Injects a small one-time global stylesheet (guarded by a module-level
  flag, safe to call from every instance) that hides the native spinner/
  clear buttons and dims+brightens the calendar picker icon on hover —
  the only way to touch `::-webkit-calendar-picker-indicator` since
  react-native-web only accepts inline style objects, not CSS selectors.
- API: `<WebDateField value={isoStringOrNull} onChange={(v) => ...}
  type="date" | "time" disabled testID min max />` — `value`/`onChange`
  use the same ISO string convention (`yyyy-mm-dd`) the raw `<input
  type="date">` always used, so swapping is a pure find-and-replace at
  call sites, no data-shape changes needed.
- Web-only component (returns `null` off-web) — matches every other
  screen in this file that already guards itself with `Platform.OS ===
  "web"` before rendering, so no double-guarding needed at call sites.
- Retrofitted into all 5 screens that had the raw pattern on 2026-07-13
  (Notas Fiscais, Telemarketing, Contatos, Equipamentos, Entrada/Saída de
  Caixa) — their local `webDateInputStyle` consts were deleted. Any new
  screen needing a date/time input uses `WebDateField` from the start;
  any old screen found still using a raw `<input type="date">` should get
  the same treatment when touched next — same standing project-wide
  requirement precedent as the Modal/Selector Standard above.

## Full CRUD Form Screen Standard (Web)

**Added 2026-07-10, user-directed** ("telas tem que seguir um padrão de
design do cadastro de Cliente com ícones nas abas e etc.", "botão grava na
parte superior direita da tela"). Any web CRUD screen with a multi-tab
form (Cliente, Serviços, and future screens of this shape) must follow the
**same** layout as `app/cliente-completo.tsx` — the reference
implementation — not a modal/dialog popup:

- The form is a **full-page view**, not a centered `AppModal` dialog. If
  the screen doesn't need a separate quick-form route (unlike Cliente,
  which has `cliente-form.tsx` for the mobile/quick path), it's fine to
  swap between "list" and "form" as two render branches of the same
  screen component instead of adding a second route — see
  `app/servicos.tsx` for that pattern. Don't wrap the form in a popup
  card just because that was faster to build; the Gestor de Documentos
  (Anexos) tab in particular needs the full page width to render its
  list+preview panel side by side — a narrow modal visibly cramps it.
- **Header**: back chevron (left) → logo → title (flex, truncates) →
  **"Gravar" button in the top-right corner of the header**, pill-shaped,
  translucent-white on the brand-primary background
  (`saveBtn`/`saveLabel` styles in `cliente-completo.tsx`). This is the
  single save action for the whole form, available from any tab — do not
  also duplicate a "Gravar" button at the bottom of individual tabs.
- **Tabs**: pill buttons directly below the header, each with an
  `Ionicons` icon + label (`tabBtn`/`tabBtnSel` styles) — never
  text-only tabs. Pick icons that describe the tab's content (see
  `cliente-completo.tsx`'s `TABS` array for the icon vocabulary already
  established: `person-outline`, `briefcase-outline`, `people-outline`,
  `attach-outline` for Anexos — reuse `attach-outline` for any future
  Anexos tab, for consistency).
- **Content**: each tab's fields live inside a `WEB_FILTER_CARD`-based
  `card` style, full width under `WEB_CONTENT_SHELL`/`WEB_SCROLL_CENTER` —
  not squeezed into a fixed-width dialog.
- **Anexos tab**: always reuse `GestorDocumentosSection` as-is (same
  component, same props shape) — never fork/duplicate its code per
  screen. If it looks different between two screens, the bug is almost
  always the *container* (a cramped modal vs. a full-width card), not the
  component itself.
- Generic error messages are not acceptable: when a save fails, surface
  the backend's actual `message` (or, for a raw FastAPI 422 payload with
  no `message`/`success` key, join `detail[].msg`) instead of falling
  straight to a hardcoded fallback string.
- **Exception — compact single-view screens**: not every entity needs tabs.
  When the legacy VB6 form itself is compact (everything visible on one
  screen, no tab control — e.g. `FrmmanForn.frm`/Fornecedores, unlike
  `frmmanclie.frm`/Cliente which has explicit tab frames), don't force
  tabs onto the new screen just to match this standard — replicate the
  legacy's density instead (single scroll, sections separated by
  `sectionHeader`+`card` pairs). The header/Gravar-top-right/full-page
  rules above still apply regardless — only the "must have tabs" part is
  conditional on what the legacy form actually looked like. See
  `app/fornecedores.tsx`.
- **Secondary sections that are separate Frames/popups in the legacy
  form** (e.g. `FrmmanForn`'s "Caixa/Contabilidade" and "Contatos"
  buttons, each opening their own floating `Frame`) become a button +
  **slide modal** in the new screen, not an inline card on the main
  page — keeps the main page as compact as the legacy original. Use the
  same `compactWeb` slide pattern as `NiveisModal.tsx`/
  `PrevisaoProdutosModal.tsx` (see "Modal/Selector Standard (Web)" above).
  Don't inline everything into one giant scroll just because it's less
  code — check whether the legacy form itself already separated it out
  before deciding.

## Global Entity Rules

**Added 2026-07-10/11, user-directed ("[GLOBAL]")** — apply these to
*every* entity screen (Cliente, Fornecedor, Serviços, and any future one),
not just the screen being worked on when the rule was stated.

- **CPF/CNPJ fields**: every CPF/CNPJ input in the project must run through
  real check-digit validation, not just a length check — reuse
  `validCPF`/`validCNPJ`/`onlyAlnumUpper`/`maskCgcCpf`/`detectDocType`
  from `frontend/src/hooks/useClienteForm.ts` (already exported, don't
  reimplement). `validCNPJ` already supports the **2026 Receita Federal
  alphanumeric CNPJ format** (first 12 chars alphanumeric, last 2 numeric
  check digits, char value = `charCode - '0'.charCode` per the official
  spec) — this was already built before this rule was written explicitly,
  just wasn't consistently reused. When the document passes validation
  (`onBlur`), query whether an entity with that document already exists
  (`GET /api/clientes/find/by-cgc` for Cliente,
  `GET /api/fornecedores/find/by-codigo` for Fornecedor — same
  `{success, found, codigo/codigo_int}` shape) and, if creating a new
  record, offer/auto-navigate to load the existing one instead of letting
  the user create a duplicate. See `useClienteForm.buscarPorCgc` and
  `app/fornecedores.tsx`'s `buscarPorCodigo` for the two reference
  implementations.
- **Gestor de Documentos (Anexos)**: every entity screen must integrate
  `GestorDocumentosSection` (see "Gestor de Documentos" project memory for
  the architecture) — this is not optional per-screen, it's a standing
  requirement for any entity that has a `cod_grupo` in `gestor_docs_grupos`.
- **CEP fields**: every CEP input must call the ViaCEP lookup
  (`https://viacep.com.br/ws/{cep}/json/`) on blur **and** via a dedicated
  search button (both — don't rely on just one). Audited 2026-07-11 across
  the app; Fornecedores' CEP field had the button wired to `onPress` only,
  no `onBlur` — and the button visually failed to render because the
  `TextInput` inside the `flex:1` row was missing `minWidth: 0` (a classic
  web-flexbox gotcha: without it, a flex child's content-based width can
  overflow its container instead of shrinking, silently pushing sibling
  elements like the search button out of the visible row instead of
  wrapping/shrinking around them). Fixed in `app/fornecedores.tsx` — when
  building any `input + button` row with `flex: 1` on the input, always
  pair it with `minWidth: 0` or the button may render but be invisible.
- **Related/child records need the parent entity saved first**: tables
  that hang off a foreign key to the entity's own PK (telefones,
  endereços, contatos, and — per explicit user direction — any
  secondary/slide section like "Caixa/Contabilidade" even when it's
  technically plain columns on the parent table, not a separate table)
  must not be fillable until the parent record has been saved at least
  once and has a real PK. On a brand-new record, show only the core
  identification fields + Gravar; once saved (PK assigned), unlock the
  related sections. Two reference implementations:
  - `app/fornecedores.tsx` — list+form single-file screen, so unlocking is
    just a local `editingCodigoInt` state update after save (no
    navigation involved).
  - `app/cliente-completo.tsx` — route-param-driven screen (`codigo` comes
    from `useLocalSearchParams`, not local state), so the *first* save of
    a new record can't just flip a boolean — `useClienteForm.handleSave`
    calls `onSaved?.(codigo, wasEditing)` on success (both new and
    already-known args) instead of a bare `onSaved?.()`, and the caller
    decides navigation: `cliente-completo.tsx` does
    `router.replace({pathname: "/cliente-completo", params: {codigo}})`
    when `!wasEditing` (stays on the same route, `editing` flips to
    `true` on re-render, Telefones/Endereços/Contatos/Anexos unlock) vs.
    `router.back()` otherwise. `cliente-form.tsx` (quick form) ignores
    the new args and always does `router.back()` — it has no related
    sections to unlock and returning to the calling Pedido/O.S. flow
    immediately is the correct behavior there, don't "fix" it to match
    cliente-completo's flow.

## Regra de Módulo Ativo — Gating por Entidade (Backend)

**Adicionado 2026-07-13, user-directed.** Toda entidade cujo cadastro só
faz sentido com um módulo ligado (`controle_configuracao.<coluna>`, ver
"Cadastro de Impressoras"/`controle-sistema` e `MODULE_TELAS` em
`backend/services/controle_config_service.py`) deve ter essa regra
**reforçada no backend**, não só escondida no frontend via `moduleOn(...)`.
Caso concreto que originou a regra: entidade Serviço — cadastro, consulta
e movimentação (inserir um item do tipo Serviço em Pedido ou O.S.) só são
permitidos com `controle_configuracao.servicos` ativo. Até então o gating
desse módulo era só frontend (tela inteira escondida) — uma chamada direta
à API passava por cima porque nenhuma rota verificava a flag.

Padrão de implementação (referência: módulo `servicos`, 2026-07-13):

- Helper compartilhado `_modulo_servicos_ativo(cur)` em
  `backend/services/pedido_common.py` — lê a coluna bit direto com o cursor
  já aberto (mesmo padrão de `_check_cliente_ativo`, que já faz o mesmo
  tipo de gating pra "cliente inativo bloqueia nova movimentação"). Para um
  módulo novo, adicionar um helper análogo (não generalizar num único
  helper parametrizado por nome de coluna só por DRY — nome de coluna
  interpolado em SQL é uma superfície de risco desnecessária quando o
  conjunto de módulos é fixo e pequeno).
- **Cadastro/consulta da entidade**: todas as operações do service
  principal da tela (`list`/`get`/`save`/`delete` — ver
  `backend/services/servicos_service.py`) verificam o módulo logo após
  abrir o cursor e bloqueiam com mensagem clara se estiver desligado.
- **Movimentação** (a entidade sendo referenciada/inserida a partir de
  OUTRA tela — ex.: Serviço dentro de Pedido/O.S.): o ponto certo pra
  checar é onde o item é resolvido/incluído (`_resolve_produto` em
  `pedido_common.py`, chamado por `itens_service._add_item_sync` e
  `os_itens_service._add_item_sync`) — bloquear só a **inclusão** de um
  item novo do tipo gateado; editar/excluir um item já existente continua
  permitido (não é uma movimentação nova).
- **Frontend**: sempre auditar TODOS os pontos de busca/seleção dessa
  entidade em outras telas, não só a tela própria — `moduleOn("servicos")`
  já existia em `pedido-form.tsx`/`produtos.tsx`/`produtos-niveis.tsx`, mas
  `os-form.tsx` tinha `tipo: "all"` fixo na busca de item, ignorando o
  flag (corrigido). Ao adicionar um módulo novo, grep por todo consumo
  cross-tela da entidade antes de considerar o frontend coberto — o
  gating do backend acima é defesa em profundidade, não substitui corrigir
  esses pontos.

## Card List Ordering

**Update (2026-07-10, user-directed, supersedes the old exception below)**:
every screen that lays out a collection of cards/tiles — Cadastros,
Configurações, Relatórios, Tabelas Auxiliares, and any future hub screen of
this shape — sorts its cards alphabetically by label. This replaces the
previous rule (kept below struck through for context) that carved out
primary navigation menus as staying in curated/usage-priority order.

- Hub tiles (any screen): sort alphabetically by `label` (`.sort((a, b) => a.label.localeCompare(b.label, "pt-BR"))`).
- Record listings inside Tabelas Auxiliares screens (Área, Área de Atuação,
  Marcas, Modelos, Forma de Pagamento, etc.): sort alphabetically by
  `descricao` at the SQL level (`ORDER BY descricao`), not by `codigo` —
  unchanged from before.

~~Does not apply to primary navigation menus (Cadastros, Configurações,
Relatórios tabs, etc.) — those keep their curated/usage-priority order
unless explicitly asked.~~ — superseded, see above.

## Permissions Tree Ordering

The Permissões screen tree (`GET /api/permissoes/catalogo`, backed by the
declarative `CATALOGO` in `backend/services/permissoes_service.py`) must always
render alphabetically, level by level, preserving parent/child nesting —
implemented via `permissoes_service.sort_catalogo()`, applied in
`routes/permissoes.py` right before the response is returned. `CATALOGO` itself
can stay declared in whatever order is convenient to read/edit; the sort
happens at serve time, so new menu/tela entries don't need to be inserted in
alphabetical position by hand.

- MENU and TELA siblings are alphabetized at each level (accent-insensitive —
  see `_sort_key`, plain `.lower()` sorts accented letters after all ASCII and
  gets it wrong, e.g. "Área" landing after "Forma de Pagamento").
- BOTAO leaves (the action checkboxes inside a TELA — Abrir/Gravar/Excluir/
  Imprimir/Exportar, or the custom Pedido/O.S. action lists) are **not**
  alphabetized — they keep their declared workflow order.
- The frontend (`app/permissoes.tsx`) renders the catalogo tree as received,
  with no re-sorting of its own — the backend is the single source of order.

### Master User Has Full Permission

**Added 2026-07-13, user-directed `[GLOBAL]`.** The master user always has every
permission in the system, overriding group grants. Already implemented at the
single source of truth — `can(key)` in `frontend/src/permissions/index.tsx`
returns `true` unconditionally when `state.isMaster` is set (checked *before*
consulting granted keys). The only thing that overrides master is module
gating (`disabledTelas` — a module switched off in Configurações > Módulos e
Recursos hides/blocks the screen for master too, checked *before* the master
bypass — see "Regra de Módulo Ativo" above).

- Screen code should call plain `can("TELA.ACAO")` — do **not** add a
  redundant `|| isMaster` at each call site; `can()` already covers it. (Some
  screens in this codebase still have the redundant `|| isMaster` from before
  this was written down explicitly — harmless, but don't copy the pattern
  into new screens.)
- This applies to every current and future screen, including the new
  "Transações" area below — no per-screen master carve-out needed.

## Do Not

- Do not hardcode different max widths per new web screen.
- Do not create new ad-hoc web card styles when `WEB_FILTER_CARD` already fits.
- Do not apply compact card sizing globally without explicit request.
- Do not change mobile spacing/behavior while adjusting web layout.
- Do not let card rows in a list shrink-wrap to content width — give the row
  style `alignSelf: "stretch"` (or `width: "100%"`) so every card lines up at
  the same width, even under `WEB_SCROLL_CENTER`'s `alignItems: "center"`.

## Done Checklist (Web Layout)

Before finishing a new screen:

- [ ] Web container is centered and consistent.
- [ ] Filters/forms are in card blocks.
- [ ] Scroll is centered on web.
- [ ] Shared tokens are used.
- [ ] Mobile layout remains preserved.

This checklist gates web *layout* specifically. For the full backend +
frontend migration checklist (business rules, tests, architecture layers),
see "Checklist Final (Migração de Tela — Completa)" in the section below.

---

## Padrão Geral de Migração de Telas (Backend Python API + Frontend React Native Mobile/Windows)

Fonte: prompt mestre original do usuário para a migração completa do ERP
legado VB6. É o padrão de referência para **todo** módulo/tela migrado do
sistema, do início ao fim do projeto — trate como referência permanente,
não como instrução de uma tarefa isolada.

**Nota de adaptação ao estado atual do projeto** (evita conflito com o
restante deste arquivo):

- O frontend já roda em Web (browser) e Mobile, conforme "Platform Scope"
  acima. O alvo "Windows" descrito abaixo (`react-native-windows`) é a
  extensão nova, motivada por telas que precisam de acesso nativo ao SO que
  o navegador não expõe — ver "Windows-only areas" em "Platform Scope"
  acima para o caso concreto que originou essa decisão.
- A estrutura de pastas de backend sugerida na seção 3 (domain/application/
  infrastructure) é o alvo para código novo escrito seguindo este padrão a
  partir de agora; o código já migrado (`backend/models`, `backend/routes`,
  `backend/services`, `backend/schemas.py`) usa uma estrutura mais simples e
  não deve ser reescrito só para se encaixar aqui — avaliar caso a caso, não
  forçar migração de telas já prontas.
- A estrutura de pastas de frontend sugerida na seção 4 é o princípio geral
  de separação de responsabilidades; na prática este repositório usa Expo
  Router (`frontend/app/`) para as telas em vez de uma pasta `screens/`, e
  já tem `frontend/src/hooks/` e `frontend/src/theme/` estabelecidos —
  seguir a convenção já existente do repositório em vez do nome literal das
  pastas abaixo.

### 1. Contexto do projeto

Este projeto é a migração de um sistema ERP comercial de grande porte,
legado em VB6, com centenas de telas, para uma nova arquitetura composta
por:

- **Backend**: API Python, HTTP, independente (não embarcada no app —
  consumida via requisições HTTP).
- **Frontend**: React Native, compartilhado entre app mobile e app desktop
  Windows (via `react-native-windows`), além do app web já existente (ver
  "Platform Scope" acima).

Por ser um projeto de grande escala, consistência é prioridade máxima: toda
tela migrada deve seguir exatamente o mesmo padrão arquitetural, de
nomenclatura e de organização definidos aqui — para garantir reutilização de
código, previsibilidade e facilidade de manutenção entre centenas de
módulos.

### 2. Objetivo geral

Migrar cada tela do VB6 preservando 100% das regras de negócio existentes,
ao mesmo tempo em que se moderniza a arquitetura, aplicando:

- Clean Architecture
- SOLID
- DRY (Don't Repeat Yourself)
- KISS (Keep It Simple, Stupid)
- Clean Code
- Separation of Concerns
- Repository Pattern
- Service Layer
- DTOs
- Injeção de Dependência
- Código altamente testável
- Performance
- Segurança
- Escalabilidade
- Manutenibilidade

### 3. Modelagem — Backend (Python API)

Para cada domínio/tela migrada, definir explicitamente:

- **Entidades**: objetos de domínio puros, sem dependência de
  framework/ORM.
- **DTOs**: um DTO de request e um de response por operação. Espelham
  exatamente o que a tela precisa enviar/receber — nada a mais.
- **Repositories**: interface (contrato) no domínio + implementação
  concreta na infraestrutura. Um repository por agregado/entidade principal
  do módulo.
- **Services**: contêm a regra de negócio migrada do VB6, chamam
  repositories apenas via interface.
- **Controllers**: finos — recebem request, chamam service, devolvem
  response. Zero regra de negócio aqui.
- **Models**: modelos de persistência (ORM) separados das Entidades de
  domínio.
- **Validações**: camada de validação de DTOs antes de chegar ao service
  (ex: Pydantic).
- **Enums**: todo valor fixo/categórico do VB6 (status, tipos, situações)
  vira Enum — nunca strings soltas.
- **Constantes**: valores fixos (limites, timeouts, mensagens padrão)
  centralizados em módulo de constants.
- **Exceptions**: hierarquia própria de exceptions de domínio
  (`EntityNotFoundError`, `BusinessRuleViolationError`, `ValidationError`
  etc.), mapeadas para códigos HTTP corretos.
- **Mapeamentos**: mappers dedicados para Entity → DTO, sem lógica de
  conversão espalhada pelo código.
- **Organização de pastas / estrutura do projeto**:

```
src/
  domain/
    entities/
    enums/
    exceptions/
    repositories/        # interfaces
  application/
    dtos/
    services/
    mappers/
    validators/
  infrastructure/
    repositories/         # implementações concretas
    database/
    config/
    di/
  presentation/
    controllers/
    middlewares/
    error_handlers/
  shared/
    constants/
    utils/
tests/
  unit/
  integration/
```

Injeção de Dependência obrigatória: repositories injetados em services,
services injetados em controllers. Nenhuma classe instancia diretamente
suas dependências.

### 4. Frontend — React Native (Mobile + react-native-windows)

- Interface moderna, responsiva, seguindo Material Design (ex:
  `react-native-paper`).
- Cliente HTTP único e centralizado, apontando para a API Python (URL
  configurável por ambiente).

Separação obrigatória:

- **Screens**: composição de components + hooks, sem chamada direta à API.
- **Components**: reutilizáveis, sem regra de negócio, recebem dados via
  props.
- **Hooks**: estado e efeitos colaterais, chamam a camada de services.
- **Services**: única camada que fala com a API, tipada, espelhando os DTOs
  do backend.
- **Contexts**: estado global (auth, tema, sessão), evitando prop
  drilling.
- **Navigation**: centralizada e tipada.
- **Tipos**: interfaces TypeScript espelhando os DTOs do backend.
- **Validações**: schemas de validação de formulário (ex: `zod`/`yup`),
  migrando as validações que existiam no VB6.
- **Máscaras**: máscaras de input (documento, telefone, moeda, data)
  centralizadas e reutilizáveis entre telas.
- **Estados de carregamento**: loading/skeleton em toda chamada assíncrona.
- **Mensagens de erro**: tratamento padronizado, nunca `alert()` genérico.
- **Feedback visual**: toast/snackbar de sucesso e falha em toda ação.

Estrutura de pastas sugerida:

```
src/
  screens/
  components/
    common/
  hooks/
  services/
  contexts/
  navigation/
  types/
  validations/
  masks/
  constants/
  utils/
  theme/
```

### 5. Refatoração contínua

Durante toda a implementação, em toda tela migrada:

- Eliminar código duplicado.
- Eliminar lógica repetida.
- Criar funções reutilizáveis.
- Criar componentes reutilizáveis.
- Extrair regras de negócio para a camada de Service (nunca deixá-las no
  Controller ou na Screen).
- Centralizar validações.
- Aplicar princípios SOLID em toda nova classe/módulo.
- Aplicar Clean Architecture consistentemente com as telas já migradas
  anteriormente.

### 6. Testes

Para cada módulo/tela migrada, gerar:

- **Testes unitários**: services (regra de negócio) e mappers, com
  repositories mockados.
- **Testes de integração**: fluxo completo do endpoint (controller →
  service → repository → banco de teste).
- **Casos de teste**: cobrindo cenários de sucesso, erro de validação e
  erro de regra de negócio.
- **Fluxos críticos**: identificar e testar os fluxos que não podem falhar
  (ex: cadastro, faturamento, baixa de estoque — conforme o módulo).
- **Validação de regras de negócio**: cada regra migrada do VB6 deve ter
  pelo menos um teste que a comprove.

### 7. Checklist Final (Migração de Tela — Completa)

Complementa o "Done Checklist (Web Layout)" mais acima — aquele cobre só o
layout web; este cobre a tela/módulo como um todo.

- [ ] Todas as regras do VB6 foram migradas.
- [ ] Nenhuma funcionalidade foi perdida.
- [ ] Código limpo.
- [ ] Código desacoplado.
- [ ] Componentes reutilizáveis.
- [ ] Performance adequada.
- [ ] Segurança (validação de entrada, autenticação/autorização, sem
      segredos hardcoded).
- [ ] Tratamento de exceções em todas as camadas.
- [ ] Logs nos pontos relevantes (erros, operações críticas).
- [ ] Código documentado (docstrings/comentários onde a lógica de negócio
      não é óbvia).

### 8. Padrão de Saída Obrigatório (ao migrar uma tela)

Para cada tela/módulo migrado, responder sempre nesta sequência:

1. **Análise da tela** — o que a tela VB6 faz, campos, fluxos, interações.
2. **Regras de negócio encontradas** — listadas explicitamente, uma a uma.
3. **Melhorias propostas** — o que muda/melhora em relação ao VB6.
4. **Arquitetura sugerida** — camadas, entidades e DTOs envolvidos nesta
   tela específica.
5. **Backend Python** — código.
6. **Frontend React Native** — código.
7. **Testes** — unitários e de integração gerados.
8. **Checklist final** — a lista da seção 7 acima, marcada.
9. **Pontos de atenção** — riscos, dúvidas, dívidas técnicas deixadas para
   depois.

### 9. Regras Importantes

- Nunca assumir regras de negócio que não existam no código VB6 original —
  ver "Legacy VB6 Source Reference" acima para os caminhos do código-fonte e
  o processo de rastreio campo-a-campo.
- Quando houver dúvida sobre uma regra, listar explicitamente as dúvidas
  antes de implementar — não implementar em cima de suposição.
- Sempre preferir qualidade à velocidade.
- Sempre justificar decisões arquiteturais.
- Sempre explicar as melhorias realizadas em relação ao VB6.
- Sempre manter compatibilidade funcional com o sistema legado (a tela nova
  deve fazer tudo que a antiga fazia).
- Sempre procurar oportunidades de reutilização de código já migrado em
  outras telas.
- Sempre identificar código legado que pode ser eliminado (sem eliminar sem
  confirmação, se houver dúvida).
- Sempre utilizar nomenclatura consistente com o restante do projeto já
  migrado.
- Sempre produzir código pronto para produção (não código de
  exemplo/rascunho).

### 10. Gestão de Pendências entre Telas

**Adicionado 2026-07-10**, a partir de `promptPendencias.md` (versão mais
completa do prompt mestre original, colada pelo usuário). Em um projeto com
centenas de telas, é normal uma migração ficar bloqueada aguardando
resposta de negócio (analista, cliente, dono do processo). Quando isso
acontecer:

1. **Nunca travar o trabalho esperando a resposta.** Registrar a pendência
   e seguir para a próxima tela/tarefa.
2. Ao identificar uma dúvida bloqueante, criar/atualizar `PENDENCIAS.md` na
   raiz do repositório contendo, por tela/módulo pendente:
   - Nome da tela/módulo e status atual (`bloqueada`, `em andamento`,
     `concluída`).
   - O que já foi analisado e implementado até o momento (regras de
     negócio já levantadas, arquitetura já definida, código já gerado —
     com caminhos de arquivo reais, não resumo vago).
   - As perguntas em aberto, de forma explícita e objetiva, prontas para
     serem respondidas.
   - Data em que a pendência foi registrada.
3. Ao retomar uma tela pendente, ler a entrada correspondente em
   `PENDENCIAS.md` antes de continuar, para recuperar o contexto sem
   precisar reanalisar do zero.
4. Ao receber a resposta da pendência, atualizar o arquivo (marcar a
   pergunta como respondida, registrar a resposta) antes de prosseguir com
   a implementação — isso também vira histórico de decisões de negócio
   para consulta futura em telas semelhantes. Remover a entrada (ou marcar
   `concluída`) quando a tela for finalizada.
5. Nunca implementar uma regra de negócio em cima de suposição só para não
   interromper o fluxo — a pendência existe justamente para evitar isso
   (mesmo princípio já em "Regras Importantes" acima, aqui com o mecanismo
   concreto de registro).

### 11. Escala do Projeto

Este é um sistema ERP comercial de grande porte, com centenas de telas a
migrar. Cada migração deve seguir exatamente este mesmo padrão
arquitetural, para garantir consistência, reutilização de código entre
módulos e facilidade de manutenção em todo o projeto — trate esta seção
como a referência permanente do projeto, não como instrução de uma tarefa
isolada.

### 12. Telas Fiscais — Fonte VB6 em Evolução Contínua

**Adicionado 2026-07-13.** Diferente do restante do sistema legado, os
módulos fiscais (emissão NFe/NFSe/MDFe, certificado digital, TEF/SiTef, e
DLLs do sistema associadas — ver `Backon.Controllers`/`Certificado.vb` em
"Legacy VB6 Source Reference" acima) continuam sob desenvolvimento ativo
diário pela equipe VB6, em paralelo a esta migração. Isso muda o
tratamento dado a essas telas especificamente:

- **Alta probabilidade de retrabalho.** Nunca tratar uma tela fiscal já
  migrada como definitiva — é esperado que volte para nova rodada de
  alteração no futuro, mesmo depois de marcada como concluída no
  `PENDENCIAS.md`.
- **Revalidar a fonte antes de reabrir.** Antes de ajustar uma tela fiscal
  já migrada, comparar o `.frm`/`.vb` atual com a versão usada na migração
  original — o comportamento pode já ter mudado no VB6 desde então. Não
  assumir que a análise anterior ainda é válida; refazer o rastreio
  campo-a-campo (mesmo processo de "Legacy VB6 Source Reference") se o
  arquivo de origem mudou.
- **Isolamento arquitetural reforçado.** Regra de cálculo/validação fiscal
  vive isolada em service/module próprio, nunca misturada com
  controller/UI — reduz o custo de uma futura rodada de mudança (aplica o
  princípio geral da seção 3 com peso extra aqui).
- **Rastreabilidade de DLL.** Ao portar uma tela que chama DLL/COM do
  sistema legado, documentar no código migrado qual DLL/chamada foi usada
  como referência e a data da verificação — facilita comparar quando a DLL
  original mudar.
- **Confirmação obrigatória para mudança de regra fiscal.** Nunca alterar
  regra de cálculo fiscal migrada sem confirmação explícita do usuário,
  mesmo que a mudança pareça pequena (reforça a seção 9, com peso extra
  por ser área fiscal).
- **Registro em PENDENCIAS.md.** Ao concluir uma tela fiscal, registrar
  explicitamente que sua fonte VB6 está sob manutenção ativa e pode
  divergir no futuro (ver seção 10) — isso avisa quem retomar o trabalho
  depois, sem precisar redescobrir esse contexto.

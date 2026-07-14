// Windows-only polyfill for `globalThis.expo`.
//
// expo-modules-core (the foundation almost every expo-* package depends on:
// expo-router, expo-constants, expo-font, expo-image, expo-secure-store,
// expo-local-authentication, etc.) expects a native module called
// "ExpoModulesCore" to install a `globalThis.expo` object at boot
// (see expo-modules-core/src/ensureNativeModulesAreInstalled.native.ts).
// That native module has never been ported to react-native-windows — Expo
// does not support this platform (confirmed via
// https://github.com/microsoft/react-native-windows/issues/13534) — so on
// Windows `globalThis.expo` is simply never set, and the very first
// `expo-modules-core` file that runs (EventEmitter.ts) crashes immediately
// with "Cannot read property 'EventEmitter' of undefined" before the app
// can even render.
//
// This provides a pure-JS stand-in matching the shape documented in
// expo-modules-core/src/ts-declarations/global.ts, just enough for
// expo-modules-core's own import-time code to not crash. It does NOT
// provide real native module functionality — any expo-* package that
// actually calls into its native module (not just imports expo-modules-core)
// will still fail when that specific call happens, since there's no real
// bridge behind `modules`. That failure is scoped to whatever feature uses
// it, instead of taking down the whole app at boot.
class PolyfillEventEmitter {
  constructor() {
    this._listenersByEvent = new Map();
  }

  addListener(eventName, listener) {
    const listeners = this._listenersByEvent.get(eventName) ?? new Set();
    listeners.add(listener);
    this._listenersByEvent.set(eventName, listeners);
    this.startObserving?.(eventName);
    return {
      remove: () => this.removeListener(eventName, listener),
    };
  }

  removeListener(eventName, listener) {
    const listeners = this._listenersByEvent.get(eventName);
    if (!listeners) return;
    listeners.delete(listener);
    if (listeners.size === 0) {
      this._listenersByEvent.delete(eventName);
      this.stopObserving?.(eventName);
    }
  }

  removeAllListeners(eventName) {
    this._listenersByEvent.delete(eventName);
    this.stopObserving?.(eventName);
  }

  emit(eventName, ...args) {
    const listeners = this._listenersByEvent.get(eventName);
    if (!listeners) return;
    for (const listener of Array.from(listeners)) {
      listener(...args);
    }
  }

  listenerCount(eventName) {
    return this._listenersByEvent.get(eventName)?.size ?? 0;
  }
}

class PolyfillNativeModule extends PolyfillEventEmitter {}

class PolyfillSharedObject extends PolyfillEventEmitter {
  release() {
    // no-op: nothing native to release on Windows.
  }
}

class PolyfillSharedRef extends PolyfillSharedObject {
  constructor(nativeRefType = "unknown") {
    super();
    this.nativeRefType = nativeRefType;
  }
}

function uuidv4() {
  // Not cryptographically strong, only used where expo-modules-core wants
  // *a* unique id, not a security-sensitive one.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function uuidv5(name, namespace) {
  // Deterministic-enough stand-in (not a real RFC 4122 v5 hash) — nothing in
  // this app currently relies on interoperating with a specific v5 value
  // computed elsewhere.
  let hash = 0;
  const input = `${namespace}:${name}`;
  for (let i = 0; i < input.length; i++) {
    hash = (hash * 31 + input.charCodeAt(i)) | 0;
  }
  return uuidv4().replace(/^[0-9a-f]{8}/, Math.abs(hash).toString(16).padStart(8, "0").slice(0, 8));
}

// expo-asset, expo-font, and most other expo-* packages call
// requireNativeModule('SomeExpoNativeModule') at their own *module* level
// (not lazily, inside a function) — e.g. expo-asset's ExpoAsset.ts does
// `const AssetModule = requireNativeModule('ExpoAsset')` as its second line.
// Since none of these native modules exist on Windows, an empty `modules: {}`
// object means requireNativeModule() throws "Cannot find native module 'X'"
// the moment ANY package importing expo-asset (expo-font, expo-splash-screen,
// expo-router's local image handling, ...) itself gets imported — crashing
// the whole app at boot again, just like the original globalThis.expo bug,
// one module name at a time as each gets discovered. A Proxy that fabricates
// a stub for whatever module name is asked for turns that into: the *lookup*
// always succeeds, and only an actual *call* to one of that module's methods
// fails — clearly, and only for the specific feature that needed it, instead
// of taking the whole app down before it can even render.
const stubModulesCache = new Map();

// Throwing here (the first version of this stub did) breaks internal Expo
// bootstrap plumbing that calls native methods it expects to be safe no-ops
// on unsupported platforms — e.g. expo-router's splash-screen handling calls
// `ExpoSplashScreen.internalPreventAutoHideAsync()` in an unawaited/uncaught
// promise chain; a thrown error there stops `AppRegistry.registerComponent`
// from ever being called, so the WHOLE APP fails to render over one
// cosmetic splash-screen call. Silently no-op (return undefined) instead,
// logging a warning so the gap is still visible in Metro's logs — a feature
// silently doing nothing on Windows is recoverable; the app never rendering
// at all is not.
const warnedOnce = new Set();

// A handful of modules are read as plain *values* (Constants.expoConfig,
// Constants.manifest, ...), not called as methods — the generic
// "every property is a no-op function" stub below actively breaks these
// (e.g. expo-linking throws "needs access to the expo-constants manifest"
// because it got a function instead of a config object). These provide real
// data instead, sourced from app.json where possible.
const KNOWN_MODULE_VALUES = {
  // Read by expo-constants' Constants.js as `ExponentConstants.manifest`,
  // used to derive `Constants.expoConfig` (which expo-linking, expo-router,
  // and others read for scheme/name/version info).
  ExponentConstants: {
    manifest: require("../app.json").expo,
    executionEnvironment: "bare",
  },
};

function createModuleStub(moduleName) {
  if (stubModulesCache.has(moduleName)) {
    return stubModulesCache.get(moduleName);
  }
  const knownValues = KNOWN_MODULE_VALUES[moduleName] ?? {};
  const stub = new Proxy(
    { ...knownValues },
    {
      get(target, propertyName) {
        if (typeof propertyName !== "string") {
          return undefined;
        }
        if (propertyName in target) {
          return target[propertyName];
        }
        if (propertyName === "then") {
          return undefined; // don't make the stub look like a thenable
        }
        return (...args) => {
          const key = `${moduleName}.${propertyName}`;
          if (!warnedOnce.has(key)) {
            warnedOnce.add(key);
            console.warn(
              `expo-modules-core: '${key}()' is not available on Windows (no native module ` +
                `ported — see windows-polyfills/setUpExpoGlobal.js). Called with no effect.`
            );
          }
          return undefined;
        };
      },
    }
  );
  stubModulesCache.set(moduleName, stub);
  return stub;
}

const modulesProxy = new Proxy(
  {},
  {
    get(target, moduleName) {
      if (typeof moduleName !== "string") {
        return undefined;
      }
      return createModuleStub(moduleName);
    },
  }
);

export function setUpExpoGlobalPolyfillForWindows() {
  if (globalThis.expo) {
    return; // real native module already installed (or already polyfilled)
  }

  globalThis.expo = {
    modules: modulesProxy,
    EventEmitter: PolyfillEventEmitter,
    NativeModule: PolyfillNativeModule,
    SharedObject: PolyfillSharedObject,
    SharedRef: PolyfillSharedRef,
    expoModulesCoreVersion: undefined,
    cacheDir: undefined,
    documentsDir: undefined,
    uuidv4,
    uuidv5,
    getViewConfig: () => null,
    reloadAppAsync: async () => {
      const DevSettings = require("react-native/Libraries/Utilities/DevSettings").default;
      DevSettings?.reload?.();
    },
  };

}

// NOTE: this is invoked directly from
// node_modules/expo-modules-core/src/ensureNativeModulesAreInstalled.native.ts
// (patched — see CLAUDE.md's Windows Build section for why), not imported
// from index.js or injected as a Metro preModule. Both of those were tried
// first and failed: static `import` in index.js gets hoisted above
// conditional code by Babel, and Expo's own Metro CLI wrapper doesn't appear
// to honor a project's customized `serializer.getModulesRunBeforeMainModule`
// for the dev server. `ensureNativeModulesAreInstalled` is the one place
// every expo-modules-core entry point (EventEmitter, NativeModule,
// SharedObject, SharedRef) already calls, synchronously, immediately before
// touching `globalThis.expo` — so patching it in place sidesteps needing any
// particular bundle ordering at all.

// metro.config.js
const { getDefaultConfig } = require("expo/metro-config");
const { mergeConfig } = require("metro-config");
const fs = require("fs");
const path = require("path");
const { FileStore } = require("metro-cache");

const defaultConfig = getDefaultConfig(__dirname);

// Use a stable on-disk store (shared across web/android)
const cacheRoot = process.env.METRO_CACHE_ROOT || path.join(__dirname, ".metro-cache");
defaultConfig.cacheStores = [new FileStore({ root: path.join(cacheRoot, "cache") })];

// Reduce the number of workers to decrease resource usage
defaultConfig.maxWorkers = 2;

// react-native-windows: exclude the generated windows/ project and RNW's own
// build output from the watcher/resolver, otherwise "run-windows" crashes
// Metro with EBUSY on files msbuild has locked (windows\.ProjectImports.zip etc).
const rnwPath = fs.realpathSync(
  path.resolve(require.resolve("react-native-windows/package.json"), ".."),
);

const windowsConfig = {
  resolver: {
    // @react-navigation/stack ships only a compiled ESM build (package.json
    // "main"/"exports" -> lib/module/index.js) whose internal relative
    // imports use explicit ".js" extensions (e.g. "./views/Header/Header.js").
    // Metro's resolver can't resolve that literal path even though the file
    // exists (fails with "None of these files exist:
    // Header.js(.windows.ts|.native.ts|.ts|...)" — it tries appending its own
    // extension candidates onto the already-extensioned name instead of
    // matching it as-is). The package's "exports" map also lists a "source"
    // condition pointing straight at the original .tsx sources, which don't
    // have this problem (plain extensionless imports, resolved normally).
    // Enabling it here makes Metro consume react-navigation's TypeScript
    // source directly instead of its prebuilt output.
    unstable_conditionNames: ["source", "react-native", "require", "default"],
    blockList: [
      // Trailing "/" anchors this to the windows/ folder itself — without it
      // this regex also matches unrelated dirs merely *starting* with
      // "windows", like windows-polyfills/ (a real bug inherited verbatim
      // from react-native-windows' own generated metro.config.js template).
      new RegExp(`${path.resolve(__dirname, "windows").replace(/[/\\]/g, "/")}/.*`),
      new RegExp(`${rnwPath}/build/.*`),
      new RegExp(`${rnwPath}/target/.*`),
      /.*\.ProjectImports\.zip/,
    ],
  },
};

module.exports = mergeConfig(defaultConfig, windowsConfig);

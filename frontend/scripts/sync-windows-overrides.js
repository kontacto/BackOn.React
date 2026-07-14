#!/usr/bin/env node
// react-native-windows ships its own replacements/additions for react-native
// core files (Platform.windows.js, View.windows.js, and supporting files
// with no platform suffix at all like NativePlatformConstantsWin.js) under
// node_modules/react-native-windows/{Libraries,src}/**, mirroring
// react-native's own folder structure exactly. react-native's core files
// import these via plain relative paths (e.g. "./Platform",
// "./NativePlatformConstantsWin"), so Metro only ever looks inside
// node_modules/react-native/** for them — there is no built-in mechanism
// that copies react-native-windows' overrides into place, discovered the
// hard way one missing file at a time (runtime error "Cannot read property
// 'OS' of undefined" from a missing Platform.windows.js, then a missing
// NativePlatformConstantsWin.js that Platform.windows.js itself requires,
// before that a missing ReactDevToolsSettingsManager.windows.js broke
// bundling entirely). Only mirrors Libraries/ and src/ — react-native-windows'
// other top-level folders (Microsoft.ReactNative, Folly, codegen, target,
// etc.) are its own C++/build tooling, not react-native overrides, and must
// not be copied. Runs on postinstall so a plain `npm install` doesn't
// silently wipe these.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const rnwDir = path.join(root, "node_modules", "react-native-windows");
const rnDir = path.join(root, "node_modules", "react-native");
const MIRRORED_DIRS = ["Libraries", "src"];

if (!fs.existsSync(rnwDir) || !fs.existsSync(rnDir)) {
  process.exit(0); // react-native-windows not installed (yet) — nothing to sync
}

function walk(dir, fileList) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, fileList);
    } else {
      fileList.push(full);
    }
  }
  return fileList;
}

let copied = 0;

for (const topDir of MIRRORED_DIRS) {
  const srcRoot = path.join(rnwDir, topDir);
  if (!fs.existsSync(srcRoot)) continue;
  for (const src of walk(srcRoot, [])) {
    const rel = path.relative(rnwDir, src);
    const dest = path.join(rnDir, rel);
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(src, dest);
      copied++;
    }
  }
}

if (copied > 0) {
  console.log(`sync-windows-overrides: copied ${copied} missing file(s) from react-native-windows into node_modules/react-native`);
}

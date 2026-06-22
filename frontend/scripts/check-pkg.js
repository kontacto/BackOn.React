#!/usr/bin/env node
// Wrapper for preinstall hook — delegates to cmd-guard.js --preinstall.
const { runPreinstall } = require("./cmd-guard/modes");
runPreinstall();

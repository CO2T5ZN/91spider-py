// 解包 Dean Edwards packer：eval -> console.log
const fs = require("fs");
const os = require("os");
const path = require("path");

const src = fs.readFileSync(path.join(os.tmpdir(), "91_inline_14.js"), "utf8");
const patched = src.replace("eval(function(p,a,c,k,e,d)", "console.log(function(p,a,c,k,e,d)");
eval(patched);

// esbuild 入口：把 xgplayer 的 CommonJS 构建打成挂 window.xgplayer 的 IIFE，
// 供后端 /watch 页直接 <script> 引用（官方 dist/index.min.js 是 CJS，浏览器直挂会因
// require 未定义报错）。window.xgplayer = Player 构造器，附带 BasePlugin/Events。
const xg = require('xgplayer')
const Player = typeof xg === 'function' ? xg : xg.default
Player.BasePlugin = xg.BasePlugin
Player.Events = xg.Events
Player.SimplePlayer = xg.SimplePlayer
module.exports = Player

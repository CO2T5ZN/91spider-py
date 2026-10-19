// 准备 public/vendor 下的播放器静态资源，vite build 时随 public/ 进入 dist，
// 供后端渲染的 /watch 页直接 <script> 引用：
//   xgplayer.min.js —— esbuild 把 xgplayer(CJS) 打成 IIFE 全局 window.xgplayer
//   xgplayer.min.css / mpegts.js —— 直接复制官方构建（mpegts 本身就是 UMD）
import { build } from 'esbuild'
import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const vendor = join(root, 'public', 'vendor')
mkdirSync(vendor, { recursive: true })

await build({
  entryPoints: [join(root, 'scripts', 'xgplayer-global.entry.cjs')],
  bundle: true,
  format: 'iife',
  globalName: 'xgplayer',
  minify: true,
  legalComments: 'none',
  outfile: join(vendor, 'xgplayer.min.js'),
})
console.log('vendor: xgplayer -> public/vendor/xgplayer.min.js (iife bundle)')

for (const [src, dst] of [
  ['xgplayer/dist/index.min.css', 'xgplayer.min.css'],
  ['mpegts.js/dist/mpegts.js', 'mpegts.js'],
]) {
  copyFileSync(join(root, 'node_modules', src), join(vendor, dst))
  console.log(`vendor: ${src} -> public/vendor/${dst}`)
}

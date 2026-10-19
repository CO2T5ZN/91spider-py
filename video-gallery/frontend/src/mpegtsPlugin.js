/**
 * xgplayer 流协议插件：用 mpegts.js 在线播放裸 .ts 文件（VOD，依赖服务端 HTTP Range）。
 * 接入方式对齐官方 xgplayer-hls.js 插件：
 *   1) 构造时置 player.handleSource = false —— 核心不再给 <video> 赋 src；
 *   2) beforePlayerInit 阶段创建 mpegts 播放器并 attachMediaElement 接管 MSE；
 *   3) afterCreate 后把 player.url 指到 video.src（blob: 地址），destroy 时还原。
 * /watch 移动端页用的是等价的无构建实现：public/vendor/mpegts-plugin.js，改动请两处同步。
 */
import mpegts from 'mpegts.js'
import { BasePlugin, Events } from 'xgplayer'

export default class MpegtsPlugin extends BasePlugin {
  static get pluginName() { return 'MpegtsPlugin' }
  static get defaultConfig() { return {} }
  // 注意：xgplayer 注册插件时会调用 Plugin.isSupported()，这里必须返回函数本身
  //（对齐官方 xgplayer-hls.js 的 get isSupported() { return Hls.isSupported }）
  static get isSupported() { return mpegts.isSupported }

  constructor(args) {
    super(args)
    this.player.handleSource = false
    this._ft = null
  }

  afterCreate() {
    const player = this.player
    try {
      BasePlugin.defineGetterOrSetter(player, {
        url: { get: () => (player.video ? player.video.src : null), configurable: true },
      })
    } catch (e) { /* 已定义过时忽略 */ }
    this.on(Events.URL_CHANGE, url => {
      if (!/^blob:/.test(url)) this._register(url)
    })
  }

  beforePlayerInit() {
    this._register(this.player.config.url)
  }

  _register(url) {
    this._teardown()
    const player = this.player
    // playerConfig.tsDuration：TS 是 VOD 点播，容器无总时长，外部提示 mpegts（毫秒）。
    // 注意 mpegts.js 1.8.2 并不会据此设置 MSE duration（进度条仍要等索引建立），
    // 大范围拖动依赖板上 ts→mp4 转封装，此路径仅作未转封装 ts 的兜底播放
    const source = { type: 'mpegts', isLive: false, url, cors: true }
    if (this.playerConfig.tsDuration > 0) source.duration = Math.round(this.playerConfig.tsDuration * 1000)
    const ft = mpegts.createPlayer(source)
    ft.on(mpegts.Events.ERROR, (errType, errDetail) => {
      player.emit('error', { errType, errDetail })
    })
    ft.attachMediaElement(player.media || player.video)
    ft.load()
    this._ft = ft
  }

  _teardown() {
    if (!this._ft) return
    try { this._ft.destroy() } catch (e) { /* MediaSource 已失效时忽略 */ }
    this._ft = null
  }

  destroy() {
    this._teardown()
    const player = this.player
    try {
      BasePlugin.defineGetterOrSetter(player, {
        url: { get: () => player.__url, configurable: true },
      })
    } catch (e) { /* 忽略 */ }
    super.destroy()
  }
}

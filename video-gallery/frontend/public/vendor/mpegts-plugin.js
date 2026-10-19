/**
 * xgplayer 的 mpegts.js 流协议插件（无构建版本，供后端 /watch 页直接 <script> 引用）。
 * 与 frontend/src/mpegtsPlugin.js 逻辑等价，改动请两处同步。
 */
(function (global) {
  'use strict'
  var mpegts = global.mpegts
  var xgplayer = global.xgplayer
  if (!mpegts || !xgplayer || !xgplayer.BasePlugin) return

  var BasePlugin = xgplayer.BasePlugin
  var URL_CHANGE = xgplayer.Events ? xgplayer.Events.URL_CHANGE : 'urlchange'

  class MpegtsPlugin extends BasePlugin {
    static get pluginName() { return 'MpegtsPlugin' }
    static get defaultConfig() { return {} }
    // 必须返回函数本身（xgplayer 注册时会调用 Plugin.isSupported()），不能返回布尔值
    static get isSupported() { return mpegts.isSupported }

    constructor(args) {
      super(args)
      this.player.handleSource = false
      this._ft = null
    }

    afterCreate() {
      var player = this.player
      try {
        BasePlugin.defineGetterOrSetter(player, {
          url: { get: function () { return player.video ? player.video.src : null }, configurable: true }
        })
      } catch (e) { /* 已定义过时忽略 */ }
      this.on(URL_CHANGE, function (url) {
        if (!/^blob:/.test(url)) this._register(url)
      }.bind(this))
    }

    beforePlayerInit() {
      this._register(this.player.config.url)
    }

    _register(url) {
      this._teardown()
      var player = this.player
      // playerConfig.tsDuration：TS 是 VOD 点播，容器无总时长，外部提示 mpegts（毫秒）。
      // mpegts.js 1.8.2 不会据此设置 MSE duration，此路径仅作未转封装 ts 的兜底播放
      var source = { type: 'mpegts', isLive: false, url: url, cors: true }
      if (this.playerConfig.tsDuration > 0) source.duration = Math.round(this.playerConfig.tsDuration * 1000)
      var ft = mpegts.createPlayer(source)
      ft.on(mpegts.Events.ERROR, function (errType, errDetail) {
        console.error('[MpegtsPlugin]', errType, errDetail)
        player.emit('error', { errType: errType, errDetail: errDetail })
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
      var player = this.player
      try {
        BasePlugin.defineGetterOrSetter(player, {
          url: { get: function () { return player.__url }, configurable: true }
        })
      } catch (e) { /* 忽略 */ }
      super.destroy()
    }
  }

  global.MpegtsPlugin = MpegtsPlugin
})(window)

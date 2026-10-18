// 后台 API 代理：内容脚本不能跨域直连本机服务，统一由 service worker 转发。
// 服务端地址可在扩展「选项」页修改，默认 http://127.0.0.1:8765
const DEFAULT_SERVER = "http://127.0.0.1:8765";

function getServer() {
  // storage 权限缺失等异常时回退到默认地址，保证按钮仍可用
  return new Promise(resolve => {
    try {
      chrome.storage.sync.get({ server: DEFAULT_SERVER }, ({ server }) =>
        resolve(server || DEFAULT_SERVER));
    } catch {
      resolve(DEFAULT_SERVER);
    }
  });
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== "api") return;
  getServer().then(server => {
    const url = server.replace(/\/+$/, "") + msg.path;
    const opts = { method: msg.method || "GET", headers: { "Content-Type": "application/json" } };
    if (msg.body !== undefined) opts.body = JSON.stringify(msg.body);
    fetch(url, opts)
      .then(async r => sendResponse({
        ok: r.ok,
        status: r.status,
        body: await r.json().catch(() => null),
      }))
      .catch(e => sendResponse({ ok: false, status: 0, body: { detail: String(e) } }));
  });
  return true; // 异步响应
});

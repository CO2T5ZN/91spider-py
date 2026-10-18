// 浮标按钮：视频详情页右下角圆形按钮
// 状态机：offline(后端未连) → idle(可提交) → queued(排队) → downloading(进度环) → done(已完成) / failed(可重提)
(() => {
  if (window.__vs_button_installed) return;
  window.__vs_button_installed = true;

  const RING_R = 23;
  const RING_C = 2 * Math.PI * RING_R;

  const state = {
    online: false,
    lastError: "",       // 最近一次通信/请求错误，离线时显示在悬停提示里
    video: null,          // {id,status,title,error,done_segments,total_segments} | null
    downloadingCount: 0,  // 队列中正在下载的数量（角标）
    queueCount: 0,
    active: null,         // 当前正在下载的视频分片进度
    submitting: false,
  };

  const el = document.createElement("div");
  el.id = "vs-float-btn";
  el.innerHTML = `
    <svg viewBox="0 0 52 52">
      <circle class="ring-bg" cx="26" cy="26" r="${RING_R}"></circle>
      <circle class="ring-fg" cx="26" cy="26" r="${RING_R}"></circle>
    </svg>
    <span class="vs-icon">↓</span>
    <span class="vs-badge"></span>
  `;
  document.documentElement.appendChild(el);

  const icon = el.querySelector(".vs-icon");
  const badge = el.querySelector(".vs-badge");
  const ringFg = el.querySelector(".ring-fg");

  function currentStatus() {
    return state.video ? state.video.status : null;
  }

  function render() {
    const st = currentStatus();
    el.classList.remove("st-idle", "st-queued", "st-downloading", "st-done", "st-failed", "st-offline");
    let tip = "";

    if (!state.online) {
      el.classList.add("st-offline");
      icon.textContent = "×";
      tip = "无法连接本地下载服务" + (state.lastError ? `（${state.lastError}）` : "（请确认 video-spider 已启动）");
    } else if (st === "done") {
      el.classList.add("st-done");
      icon.textContent = "✓";
      tip = "已下载完成";
    } else if (st === "downloading") {
      el.classList.add("st-downloading");
      icon.textContent = "↓";
      const p = segPct(state.video);
      setRing(p);
      tip = `下载中 ${state.video.done_segments}/${state.video.total_segments} 分片（${p.toFixed(0)}%）`;
    } else if (st === "pending") {
      el.classList.add("st-queued");
      icon.textContent = "…";
      const p = state.active ? segPct(state.active) : 0;
      setRing(p);
      tip = `排队中（队列 ${state.queueCount + state.downloadingCount} 个，当前下载 ${p.toFixed(0)}%）`;
    } else if (st === "failed") {
      el.classList.add("st-failed");
      icon.textContent = "!";
      tip = "下载失败，点击重试";
    } else {
      el.classList.add("st-idle");
      icon.textContent = "↓";
      setRing(0);
      tip = "提交到本地下载服务";
    }

    if (state.submitting) {
      el.classList.add("st-downloading");
      icon.textContent = "↻";
      tip = "提交中…";
    }

    // 角标：正在下载的数量
    if (state.downloadingCount > 0) {
      badge.style.display = "block";
      badge.textContent = String(state.downloadingCount);
    } else {
      badge.style.display = "none";
    }
    el.title = tip;
  }

  function segPct(v) {
    if (!v || !v.total_segments) return 0;
    return Math.min(100, (v.done_segments / v.total_segments) * 100);
  }

  function setRing(pct) {
    ringFg.style.strokeDashoffset = String(RING_C * (1 - pct / 100));
  }

  function detailUrl() {
    return location.origin + location.pathname + location.search;
  }

  function pageTitle() {
    // 详情页 <title> 形如 "xxx A片 - 91视频|色情视频|成人视频|91porn"
    return (document.title || "").split(/\s+-\s+/)[0].trim() || null;
  }

  async function api(path, opts) {
    return new Promise(resolve => {
      chrome.runtime.sendMessage({ type: "api", path, ...opts }, resp => {
        resolve(resp || { ok: false, status: 0, body: { detail: "no response" } });
      });
    });
  }

  async function refresh() {
    try {
      const r = await api("/api/manual/state?detail_url=" + encodeURIComponent(detailUrl()));
      state.online = !!(r && r.ok);
      if (r && r.ok && r.body) {
        state.video = r.body.video;
        state.downloadingCount = r.body.downloading_count;
        state.queueCount = r.body.queue_count;
        state.active = r.body.active;
        state.lastError = "";
      } else {
        state.lastError = (r && r.body && r.body.detail) ? String(r.body.detail).slice(0, 80) : "无响应";
      }
    } catch (e) {
      state.online = false;
      state.lastError = String(e).slice(0, 80);
    }
    render();
  }

  el.addEventListener("click", async () => {
    const st = currentStatus();
    if (!state.online || st === "done" || st === "pending" || st === "downloading" || state.submitting) {
      return;
    }
    state.submitting = true;
    render();
    await api("/api/manual/submit", {
      method: "POST",
      body: { detail_url: detailUrl(), title: pageTitle() },
    });
    state.submitting = false;
    refresh();
  });

  // 样式
  const style = document.createElement("style");
  style.textContent = `
    #vs-float-btn {
      position: fixed; right: 28px; top: 20vh; width: 52px; height: 52px;
      z-index: 2147483647; border-radius: 50%;
      background: rgba(18, 18, 24, .88); cursor: pointer;
      box-shadow: 0 2px 12px rgba(0, 0, 0, .45);
      user-select: none; -webkit-user-select: none;
      transition: transform .15s ease;
    }
    #vs-float-btn:hover { transform: scale(1.08); }
    #vs-float-btn svg { position: absolute; inset: 0; width: 100%; height: 100%; transform: rotate(-90deg); }
    #vs-float-btn .ring-bg { fill: none; stroke: rgba(255,255,255,.14); stroke-width: 3; }
    #vs-float-btn .ring-fg {
      fill: none; stroke: #4caf50; stroke-width: 3; stroke-linecap: round;
      stroke-dasharray: ${RING_C}; stroke-dashoffset: ${RING_C};
      transition: stroke-dashoffset .4s linear;
    }
    #vs-float-btn .vs-icon {
      position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
      color: #fff; font-size: 20px; font-weight: 700; line-height: 1; font-family: sans-serif;
    }
    #vs-float-btn .vs-badge {
      display: none; position: absolute; top: -4px; right: -4px;
      min-width: 18px; height: 18px; padding: 0 4px; border-radius: 9px;
      background: #e53935; color: #fff; font-size: 11px; font-weight: 700;
      line-height: 18px; text-align: center; font-family: sans-serif;
      box-shadow: 0 1px 4px rgba(0,0,0,.4);
    }
    #vs-float-btn.st-done .ring-fg { stroke: #4caf50; stroke-dashoffset: 0; }
    #vs-float-btn.st-failed .ring-fg { stroke: #e53935; stroke-dashoffset: ${RING_C * 0.25}; }
    #vs-float-btn.st-queued .ring-fg { stroke: #ffb300; }
    #vs-float-btn.st-done .vs-icon { color: #4caf50; }
    #vs-float-btn.st-failed .vs-icon { color: #e53935; }
    #vs-float-btn.st-offline .vs-icon { color: #9e9e9e; }
    #vs-float-btn.st-offline { opacity: .6; }
  `;
  document.documentElement.appendChild(style);

  refresh();
  setInterval(refresh, 2500);
})();

/* ============================================================
   礼品库 · 管理后台逻辑
   ============================================================ */
"use strict";

const $ = (s) => document.querySelector(s);
// 支持 /admin?_t=xxx 直链登录（分享地址时使用）
const _params = new URLSearchParams(location.search);
const _urlTok = _params.get("_t");
if (_urlTok) { localStorage.setItem("gm_token", _urlTok); }
let TOKEN = localStorage.getItem("gm_token") || "";
let curView = "dash";
let editingId = 0;      // 0 = 新增
let editImages = [];     // 编辑中的图片列表，最多 3 张，第一张为封面
let ordersCache = [];

function toast(msg, type = "") {
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = msg;
  $("#toast-wrap").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 2400);
  setTimeout(() => el.remove(), 2800);
}
function money(n) { return "¥" + Number(n).toFixed(2).replace(/\.00$/, ""); }
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

async function api(url, opt = {}) {
  opt.headers = Object.assign({}, opt.headers || {});
  if (TOKEN) opt.headers["Authorization"] = "Bearer " + TOKEN;
  const r = await fetch(url, opt);
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) { showLogin(); throw new Error("登录已过期，请重新登录"); }
  if (!r.ok || d.ok === false) throw new Error(d.msg || ("请求失败 " + r.status));
  return d;
}

/* ---------------- 登录 ---------------- */
function showLogin() {
  $("#loginMask").style.display = "flex";
  localStorage.removeItem("gm_token");
  // 默认把光标放进口令框，新人打开后台直接就能输入，不必先点一下
  focusPwd();
}
function hideLogin() { $("#loginMask").style.display = "none"; }
function focusPwd() {
  const el = $("#pwdInput");
  if (!el || $("#loginMask").style.display === "none") return;
  setTimeout(() => { el.focus(); el.select(); }, 60);
}

async function tryLogin() {
  const pwd = $("#pwdInput").value;
  if (!pwd) return;
  const btn = $("#loginBtn");
  btn.disabled = true; btn.textContent = "登录中…";
  try {
    const r = await fetch("/api/admin/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pwd })
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.msg || "口令不正确");
    TOKEN = d.token;
    localStorage.setItem("gm_token", TOKEN);
    hideLogin();
    loadView();
  } catch (e) {
    $("#loginErr").textContent = e.message;
    focusPwd();   // 口令错了直接全选，方便重输
  } finally {
    btn.disabled = false; btn.textContent = "登 录";
  }
}
$("#loginBtn").onclick = tryLogin;
$("#pwdInput").addEventListener("keydown", e => { if (e.key === "Enter") tryLogin(); });
$("#logoutBtn").onclick = async () => {
  try { await api("/api/admin/logout", { method: "POST" }); } catch {}
  TOKEN = ""; showLogin();
};

/* ---------------- 视图切换 ---------------- */
const VIEWS = ["dash", "products", "orders", "logs"];
function switchView(v) {
  if (!VIEWS.includes(v)) v = "dash";
  curView = v;
  if (location.hash !== "#/" + v) location.hash = "#/" + v;
  document.querySelectorAll(".side-nav a").forEach(x =>
    x.classList.toggle("on", x.dataset.view === v));
  VIEWS.forEach(w => $("#view-" + w).style.display = w === v ? "" : "none");
  loadView();
}
document.querySelectorAll(".side-nav a").forEach(a => {
  a.onclick = (e) => { e.preventDefault(); switchView(a.dataset.view); };
});
window.addEventListener("hashchange", () => {
  const v = location.hash.replace("#/", "") || "dash";
  if (v !== curView) switchView(v);
});

function loadView() {
  if (curView === "dash") loadDash();
  else if (curView === "products") loadProducts();
  else if (curView === "logs") loadLogs();
  else loadOrders();
}

/* ---------------- 操作日志 ---------------- */
const LOG_TAG = {
  "登录成功": ["green", ""], "登录失败": ["red", ""], "修改口令": ["amber", ""],
  "新增礼品": ["green", "＋"], "编辑礼品": ["gray", "✎"], "删除礼品": ["red", "✕"],
  "批量删除": ["red", "✕✕"], "批量上架": ["green", "↑↑"], "批量下架": ["amber", "↓↓"],
  "批量修改": ["gray", "≡≡"], "调整库存": ["gray", "±"], "订单状态": ["gray", "☑"],
  "修改设置": ["amber", "⚙"],
};

async function loadLogs() {
  try {
    const d = await api("/api/admin/logs?limit=300");
    $("#logsBody").innerHTML = d.logs.map(l => {
      const tag = LOG_TAG[l.action] || ["", ""];
      return `<tr>
        <td class="num" style="white-space:nowrap">${esc(l.ts)}</td>
        <td><span class="tag ${tag[0]}">${tag[1]} ${esc(l.action)}</span></td>
        <td style="color:var(--ink-2)">${esc(l.detail) || "—"}</td>
        <td class="num">${esc(l.ip || "—")}</td>
      </tr>`;
    }).join("") || `<tr><td colspan="4" class="empty">还没有操作记录</td></tr>`;
  } catch (e) { if (e.message !== "登录已过期，请重新登录") toast(e.message, "err"); }
}
$("#logsRefresh").onclick = loadLogs;

/* ---------------- 领取规则 / 导出 ---------------- */
async function loadSettings() {
  try {
    const d = await api("/api/admin/settings");
    $("#monthLimit").value = d.settings.month_limit || 0;
    renderSaleToggle(d.settings.sale_ended === "1");
  } catch (e) {}
}

function renderSaleToggle(ended) {
  const state = $("#saleState"), btn = $("#saleToggle");
  if (ended) {
    state.innerHTML = `<b style="color:var(--red,#c0392b)">活动已结束</b>`;
    btn.textContent = "开启新一轮特卖";
    btn.className = "btn sm primary";
  } else {
    state.innerHTML = `<b style="color:var(--green,#2e7d32)">特卖进行中</b>`;
    btn.textContent = "结束本期特卖";
    btn.className = "btn sm danger";
  }
  btn.dataset.ended = ended ? "1" : "";
}

$("#saleToggle").onclick = async () => {
  const toEnd = !$("#saleToggle").dataset.ended;
  if (toEnd && !confirm("确认结束本期特卖？\n\n前台将立即停止展示商品，并无法提交新订单。\n可随时点「开启新一轮特卖」恢复。")) return;
  try {
    await api("/api/admin/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sale_ended: toEnd })
    });
    renderSaleToggle(toEnd);
    toast(toEnd ? "特卖已结束，前台已关闭下单" : "新一轮特卖已开启", "good");
  } catch (e) { toast(e.message, "err"); }
};
$("#saveLimit").onclick = async () => {
  try {
    await api("/api/admin/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ month_limit: $("#monthLimit").value })
    });
    toast("购买规则已保存", "good");
  } catch (e) { toast(e.message, "err"); }
};

$("#backupBtn").onclick = async () => {
  const btn = $("#backupBtn");
  btn.disabled = true;
  try {
    const r = await fetch("/api/admin/backup", {
      headers: { "Authorization": "Bearer " + TOKEN }
    });
    if (r.status === 401) { showLogin(); return; }
    if (!r.ok) throw new Error("备份失败 " + r.status);
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "gift-backup-" + new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "") + ".zip";
    a.click();
    URL.revokeObjectURL(a.href);
    toast("备份已下载（含数据库 + 全部图片）", "good");
  } catch (e) {
    toast(e.message, "err");
  } finally {
    btn.disabled = false;
  }
};

$("#exportBtn").onclick = async () => {
  const btn = $("#exportBtn");
  btn.disabled = true;
  try {
    const r = await fetch("/api/admin/export", {
      headers: { "Authorization": "Bearer " + TOKEN }
    });
    if (r.status === 401) { showLogin(); return; }
    if (!r.ok) throw new Error("导出失败 " + r.status);
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "gift-ledger-" + new Date().toISOString().slice(0, 10) + ".xlsx";
    a.click();
    URL.revokeObjectURL(a.href);
    toast("台账已导出", "good");
  } catch (e) {
    toast(e.message, "err");
  } finally {
    btn.disabled = false;
  }
};

/* ---------------- 概览 ---------------- */
/* ---------------- 概览统计图表 ---------------- */
function localDay(offset) {
  const dt = new Date();
  dt.setDate(dt.getDate() - offset);
  return dt.getFullYear() + "-" +
    String(dt.getMonth() + 1).padStart(2, "0") + "-" + String(dt.getDate()).padStart(2, "0");
}

function renderCharts(chart) {
  renderTrend(chart.trend || []);
  renderBars("#chartTop", chart.top || [], "还没有购买记录");
  renderBars("#chartDepts", chart.depts || [], "还没有部门购买记录", "dept");
}

function renderTrend(trend) {
  const byDay = {};
  trend.forEach(r => { byDay[r.d] = r; });
  const days = [];
  for (let i = 13; i >= 0; i--) days.push(localDay(i));
  const W = 680, H = 190, padL = 34, padB = 30, padT = 14;
  const iw = W - padL - 12, ih = H - padT - padB;
  const maxQty = Math.max(1, ...days.map(d => (byDay[d] || {}).qty || 0));
  const bw = iw / days.length;
  const hasData = trend.length > 0;

  let bars = "";
  days.forEach((d, i) => {
    const r = byDay[d] || {};
    const qty = r.qty || 0;
    const h = qty ? Math.max(3, qty / maxQty * ih) : 0;
    const x = padL + i * bw + bw * 0.18;
    const y = padT + ih - h;
    bars += qty
      ? `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw * 0.64).toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="var(--brand)"><title>${d}：${qty} 件 / ${r.cnt} 单</title></rect>
         <text x="${(x + bw * 0.32).toFixed(1)}" y="${(y - 4).toFixed(1)}" text-anchor="middle" font-size="10" fill="var(--ink-2)">${qty}</text>`
      : `<rect x="${x.toFixed(1)}" y="${(padT + ih - 1).toFixed(1)}" width="${(bw * 0.64).toFixed(1)}" height="1.5" fill="var(--line)"><title>${d}：无发放</title></rect>`;
  });
  // 轴线与日期标签（每 2 天一个）
  const labels = days.map((d, i) => i % 2 === 0
    ? `<text x="${(padL + i * bw + bw * 0.32).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--muted)">${d.slice(5).replace("-", "/")}</text>` : "").join("");
  const grid = [0.5, 1].map(f => {
    const y = padT + ih - ih * f;
    return `<line x1="${padL}" y1="${y}" x2="${W - 12}" y2="${y}" stroke="var(--line)" stroke-dasharray="3 4"/><text x="${padL - 5}" y="${(y + 3).toFixed(1)}" text-anchor="end" font-size="10" fill="var(--muted)">${Math.round(maxQty * f)}</text>`;
  }).join("");

  $("#chartTrend").innerHTML = hasData
    ? `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">
         <line x1="${padL}" y1="${padT + ih}" x2="${W - 12}" y2="${padT + ih}" stroke="var(--line)"/>${grid}${bars}${labels}</svg>`
    : `<div class="chart-empty">近 14 天暂无发放记录，员工下单后这里会出现趋势图</div>`;
}

function renderBars(sel, rows, emptyTip, deptKey) {
  const el = $(sel);
  if (!rows.length) { el.innerHTML = `<div class="chart-empty">${emptyTip}</div>`; return; }
  const max = Math.max(...rows.map(r => r.qty || 0), 1);
  el.innerHTML = rows.map(r => {
    const name = deptKey ? r.dept : r.n;
    const pct = Math.max(4, Math.round((r.qty || 0) / max * 100));
    return `<div class="hbar" title="${esc(name)}：${r.qty} 件 / ${r.cnt} 单">
      <div class="hbar-name">${esc(name || "—")}</div>
      <div class="hbar-track"><div class="hbar-fill" style="width:${pct}%"></div></div>
      <div class="hbar-val">${r.qty} 件</div>
    </div>`;
  }).join("");
}

async function loadDash() {
  loadSettings();
  try {
    const d = await api("/api/admin/stats");
    const s = d.stats;
    $("#statCards").innerHTML = `
      <div class="scard"><div class="v">${s.total}<small>款</small></div><div class="k">礼品总数</div></div>
      <div class="scard"><div class="v">${s.stock}<small>件</small></div><div class="k">库存总量</div></div>
      <div class="scard"><div class="v">¥${Number(s.value).toLocaleString()}</div><div class="k">库存货值</div></div>
      <div class="scard"><div class="v">${s.pending}</div><div class="k">待发放订单</div></div>
      <div class="scard warn"><div class="v">${s.expiring}</div><div class="k">90 天内到期</div></div>
      <div class="scard bad"><div class="v">${s.expired}</div><div class="k">已过期</div></div>`;
    $("#warnBody").innerHTML = s.expiring + s.expired
      ? "" : `<tr><td style="color:var(--green)">✓ 暂无临期或过期礼品</td></tr>`;
    renderCharts(d.chart || {});
  } catch (e) { /* 401 已处理 */ }

  // 预警列表单独拉
  try {
    const d = await api("/api/admin/products");
    const rows = d.products.filter(p =>
      p.expiry_date && (p.days_left == null || p.days_left <= 90));
    $("#warnBody").innerHTML = rows.map(p => {
      const dl = p.days_left;
      const tag = dl < 0 ? `<span class="tag red">已过期 ${-dl} 天</span>`
        : `<span class="tag amber">${dl} 天后到期</span>`;
      return `<tr>
        <td style="width:60px"><img class="thumb" src="${esc(p.image || "/assets/placeholder.svg")}"></td>
        <td class="name-cell">${esc(p.name)}<small>${esc(p.spec || "")}</small></td>
        <td class="num">${money(p.price)}${p.original_price > p.price ? ` <s style="color:var(--muted);font-size:11px">${money(p.original_price)}</s>` : ""}</td>
        <td class="num">${p.stock}</td><td class="num">${esc(p.expiry_date)}</td>
        <td>${tag}</td></tr>`;
    }).join("") || `<tr><td style="color:var(--green)">✓ 暂无临期或过期礼品</td></tr>`;
  } catch (e) {}
}

/* ---------------- 商品管理 ---------------- */
async function loadProducts() {
  try {
    const d = await api("/api/admin/products?q=" + encodeURIComponent($("#aQ").value.trim()));
    $("#pBody").innerHTML = d.products.map(p => `
      <tr data-id="${p.id}">
        <td><input type="checkbox" class="rowChk" data-chk="${p.id}" ${selected.has(p.id) ? "checked" : ""} title="选择"></td>
        <td><img class="thumb" src="${esc(p.image || "/assets/placeholder.svg")}" onerror="this.src='/assets/placeholder.svg'"></td>
        <td class="name-cell">${esc(p.name)}<small>${esc(p.spec || "")}</small></td>
        <td class="num">${money(p.price)}${p.original_price > p.price ? ` <s style="color:var(--muted);font-size:11px">${money(p.original_price)}</s>` : ""}</td>
        <td><span class="mini-stepper">
          <button data-act="dec">−</button><span>${p.stock}</span><button data-act="inc">＋</button></span></td>
        <td class="num">${esc(p.production_date || "—")}</td>
        <td class="num">${esc(p.expiry_date || "长期")}
          ${p.expired ? '<br><span class="tag red">已过期</span>' : (p.expiring ? `<br><span class="tag amber">剩 ${p.days_left} 天</span>` : "")}</td>
        <td><button class="switch ${p.status ? "on" : ""}" data-act="toggle" title="${p.status ? "上架中" : "已下架"}"></button></td>
        <td><div class="row-actions">
          <button class="icon-btn" data-act="edit" title="编辑"><svg viewBox="0 0 24 24"><path d="M3 17.2V21h3.8L17.8 10 14 6.2 3 17.2zM20.7 7.1a1 1 0 0 0 0-1.4l-2.4-2.4a1 1 0 0 0-1.4 0l-1.8 1.9 3.8 3.7 1.8-1.8z"/></svg></button>
          <button class="icon-btn del" data-act="del" title="删除"><svg viewBox="0 0 24 24"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg></button>
        </div></td>
      </tr>`).join("") || `<tr><td colspan="9" class="empty">还没有礼品，点右上角「新增礼品」</td></tr>`;

    // 只保留当前列表中仍存在的选中项
    const alive = new Set(d.products.map(p => p.id));
    for (const id of [...selected]) if (!alive.has(id)) selected.delete(id);

    $("#pBody").querySelectorAll("tr[data-id]").forEach(tr => {
      const id = +tr.dataset.id;
      const p = d.products.find(x => x.id === id);
      tr.querySelectorAll("[data-act]").forEach(el => {
        el.onclick = () => {
          const act = el.dataset.act;
          if (act === "edit") openEdit(p);
          else if (act === "del") delProduct(p);
          else if (act === "toggle") toggleStatus(p);
          else if (act === "inc" || act === "dec") adjustStock(p, act === "inc" ? 1 : -1, el);
        };
      });
      tr.querySelector(".rowChk").onchange = (e) => {
        e.target.checked ? selected.add(id) : selected.delete(id);
        syncBatch();
      };
    });
    syncBatch();
  } catch (e) { if (e.message !== "登录已过期，请重新登录") toast(e.message, "err"); }
}

/* ---------------- 批量选择 ---------------- */
const selected = new Set();

function syncBatch() {
  const boxes = [...document.querySelectorAll("#pBody .rowChk")];
  const shown = boxes.length;
  const checked = boxes.filter(b => b.checked).length;
  $("#batchBar").style.display = selected.size ? "" : "none";
  $("#batchCount").textContent = selected.size;
  const all = $("#chkAll");
  all.checked = shown > 0 && checked === shown;
  all.indeterminate = checked > 0 && checked < shown;
}

$("#chkAll").onchange = (e) => {
  document.querySelectorAll("#pBody .rowChk").forEach(b => {
    b.checked = e.target.checked;
    e.target.checked ? selected.add(+b.dataset.chk) : selected.delete(+b.dataset.chk);
  });
  syncBatch();
};

async function batchAction(action, confirmMsg) {
  if (!selected.size) return;
  if (confirmMsg && !confirm(confirmMsg.replace("{n}", selected.size))) return;
  try {
    const d = await api("/api/admin/products/batch", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, ids: [...selected] })
    });
    const label = { delete: "已删除", on: "已上架", off: "已下架" }[action];
    toast(`${label} ${d.affected} 件礼品`, "good");
    selected.clear();
    loadProducts();
  } catch (e) { toast(e.message, "err"); }
}

$("#batOn").onclick = () => batchAction("on");
$("#batOff").onclick = () => batchAction("off");
$("#batDel").onclick = () => batchAction("delete",
  `确定删除选中的 {n} 件礼品？\n此操作不可恢复（历史订单不受影响）。`);
$("#batCancel").onclick = () => { selected.clear(); loadProducts(); };

/* ---------------- 批量修改弹窗 ---------------- */
function openBatModal() {
  if (!selected.size) return;
  $("#beCount").textContent = selected.size;
  $("#beMode").value = "none";
  $("#bePrice").value = "";
  $("#bePrice").disabled = true;
  $("#beStockMode").value = "none";
  $("#beStock").value = "";
  $("#beStock").disabled = true;
  $("#batMask").classList.add("show");
  $("#batModal").style.display = "";
}
function closeBatModal() {
  $("#batMask").classList.remove("show");
  $("#batModal").style.display = "none";
}
$("#batEdit").onclick = openBatModal;
$("#batEditClose").onclick = closeBatModal;
$("#batEditCancel").onclick = closeBatModal;
$("#batMask").onclick = closeBatModal;
$("#beMode").onchange = (e) => {
  const inp = $("#bePrice");
  inp.disabled = e.target.value === "none";
  inp.placeholder = e.target.value === "percent" ? "如 90 = 9折，80 = 8折" : "统一改为的价格（元）";
};
$("#beStockMode").onchange = (e) => {
  const inp = $("#beStock");
  inp.disabled = e.target.value === "none";
  inp.placeholder = e.target.value === "add" ? "每件增加的数量（件）" : "统一设置为的库存（件）";
};

$("#batEditGo").onclick = async () => {
  const mode = $("#beMode").value;
  const priceRaw = $("#bePrice").value.trim();
  const stockMode = $("#beStockMode").value;
  const stockRaw = $("#beStock").value.trim();
  const payload = {};
  if (mode !== "none") {
    if (priceRaw === "" || isNaN(parseFloat(priceRaw))) {
      toast("请填写价格数值", "err"); return;
    }
    payload.price = parseFloat(priceRaw);
    payload.price_mode = mode;
  }
  if (stockMode !== "none") {
    if (stockRaw === "" || isNaN(parseInt(stockRaw, 10))) {
      toast("请填写库存数量", "err"); return;
    }
    payload.stock = parseInt(stockRaw, 10);
    payload.stock_mode = stockMode;
  }
  const touched = payload.price != null || payload.stock != null;
  if (!touched) {
    toast("价格、库存都没填，没什么可改的", "err"); return;
  }
  if (!confirm(`确定把修改应用到选中的 ${selected.size} 件礼品？`)) return;
  try {
    const d = await api("/api/admin/products/batch", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "edit", ids: [...selected], ...payload })
    });
    toast(`已更新 ${d.affected} 件礼品`, "good");
    closeBatModal();
    selected.clear();
    loadProducts();
  } catch (e) { toast(e.message, "err"); }
};

$("#aQ").addEventListener("input", debounce(loadProducts, 300));
$("#addBtn").onclick = () => openEdit(null);

/* ---------------- Excel 模板下载 / 批量导入 ---------------- */
$("#tplBtn").onclick = async () => {
  try {
    const r = await fetch("/api/admin/import-template", {
      headers: { "Authorization": "Bearer " + TOKEN }
    });
    if (r.status === 401) { showLogin(); return; }
    if (r.status === 404) throw new Error("服务端版本较旧，请双击 gift-mall 目录下的「启动服务-静默.bat」重启后重试");
    if (!r.ok) throw new Error("模板下载失败（HTTP " + r.status + "）");
    const blob = await r.blob();
    const a = document.createElement("a");
    const url = URL.createObjectURL(blob);
    a.href = url; a.download = "礼品导入模板.xlsx";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    toast("模板已下载", "good");
  } catch (e) { toast(e.message, "err"); }
};

$("#impBtn").onclick = () => $("#impFile").click();

$("#impFile").onchange = async (ev) => {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  const box = $("#impBox");
  box.style.display = "block";
  box.innerHTML = `<span style="color:var(--muted)">正在导入 ${esc(file.name)} …</span>`;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/admin/import", {
      method: "POST", headers: { "Authorization": "Bearer " + TOKEN }, body: fd
    });
    const d = await r.json().catch(() => ({}));
    if (r.status === 401) { showLogin(); return; }
    if (r.status === 404) throw new Error("服务端版本较旧，请双击「启动服务-静默.bat」重启后重试");
    if (!d.ok) throw new Error(d.msg || "导入失败");
    const errs = d.errors || [];
    box.innerHTML =
      `<b style="color:${d.added ? "var(--green)" : "var(--amber)"}">✓ 成功导入 ${d.added} 件礼品</b>` +
      (d.error_count ? `<span style="color:var(--amber)">，${d.error_count} 行需要处理</span>` : "") +
      (errs.length ? `<div style="margin-top:6px;color:var(--ink-2)">` +
        errs.map(t => "· " + esc(t)).join("<br>") + `</div>` : "") +
      (d.added ? `<div style="margin-top:6px;color:var(--muted);font-size:12px">` +
        `这些礼品的图片还是空的：在下方列表点「编辑」逐条上传（最多 3 张）。</div>` : "");
    toast(`导入完成：${d.added} 件`, d.added ? "good" : "err");
    await loadProducts();
  } catch (e) {
    box.innerHTML = `<b style="color:var(--red)">导入失败：${esc(e.message)}</b>`;
    toast(e.message, "err");
  } finally {
    ev.target.value = "";
  }
};

function debounce(fn, t) { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), t); }; }

async function adjustStock(p, delta, el) {
  try {
    const d = await api(`/api/admin/products/${p.id}/stock`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delta })
    });
    p.stock = d.stock;  // 同步内存对象，保证「编辑」抽屉打开时显示最新库存
    el.parentElement.querySelector("span").textContent = d.stock;
  } catch (e) { toast(e.message, "err"); }
}

async function toggleStatus(p) {
  try {
    await api(`/api/admin/products/${p.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...p, status: p.status ? 0 : 1 })
    });
    toast(p.status ? "已下架" : "已上架", "good");
    loadProducts();
  } catch (e) { toast(e.message, "err"); }
}

async function delProduct(p) {
  if (!confirm(`确定删除「${p.name}」？\n此操作不可恢复（历史订单不受影响）。`)) return;
  try {
    await api(`/api/admin/products/${p.id}`, { method: "DELETE" });
    toast("已删除", "good");
    loadProducts();
  } catch (e) { toast(e.message, "err"); }
}

/* ---------------- 编辑抽屉 ---------------- */
function openEdit(p) {
  editingId = p ? p.id : 0;
  editImages = (p && Array.isArray(p.images) && p.images.length)
    ? [...p.images] : (p && p.image ? [p.image] : []);
  $("#eTitle").textContent = p ? "编辑礼品" : "新增礼品";
  $("#eName").value = p?.name || "";
  $("#eSpec").value = p?.spec || "";
  $("#ePrice").value = p?.price ?? "";
  $("#eOrig").value = (p?.original_price > 0) ? p.original_price : "";
  $("#eStock").value = p?.stock ?? "";
  $("#eSort").value = p?.sort_no ?? "";
  $("#ePd").value = p?.production_date || "";
  $("#eEd").value = p?.expiry_date || "";
  $("#eDesc").value = p?.description || "";
  $("#eStatus").checked = p ? !!p.status : true;
  renderUploader();
  $("#amask").classList.add("show");
  $("#editDrawer").classList.add("show");
  setTimeout(() => $("#eName").focus(), 250);
}
function closeEdit() {
  $("#amask").classList.remove("show");
  $("#editDrawer").classList.remove("show");
}
$("#editClose").onclick = closeEdit;
$("#amask").onclick = closeEdit;

function renderUploader() {
  const u = $("#uploader");
  const slots = editImages.map((src, i) => `
    <div class="up-slot" data-i="${i}">
      <img src="${esc(src)}" onerror="this.src='/assets/placeholder.svg'">
      <button type="button" class="up-del" data-del="${i}" title="移除这张">×</button>
      ${i === 0 ? '<span class="up-cover">封面</span>' : ""}
    </div>`).join("");
  const add = editImages.length < 3 ? `
    <div class="up-add" id="upAdd">
      <svg viewBox="0 0 24 24"><path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-5H3v5a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-5h-2zM11 6.8 8.4 9.4 7 8l5-5 5 5-1.4 1.4L13 6.8V16h-2V6.8z"/></svg>
      <small>添加第 ${editImages.length + 1} 张 / 共3张</small>
    </div>` : "";
  u.innerHTML = slots + add;
  u.querySelectorAll("[data-del]").forEach(b => b.onclick = (e) => {
    e.stopPropagation();
    editImages.splice(+b.dataset.del, 1);
    renderUploader();
  });
  // 点击空白/添加位由容器级 $("#uploader").onclick 统一打开文件框，不再单独绑定
}

/** 触发系统文件选择框。input 放在 uploader 外部；万一被误删则动态补一个。 */
function pickFile() {
  let inp = document.getElementById("upFile");
  if (!inp) {
    inp = document.createElement("input");
    inp.type = "file";
    inp.id = "upFile";
    inp.accept = "image/png,image/jpeg,image/webp,image/gif,image/bmp";
    inp.style.display = "none";
    document.body.appendChild(inp);
    bindFileInput(inp);
  }
  inp.value = "";          // 允许连续选同一张图
  inp.click();
}

function bindFileInput(inp) {
  inp.onchange = async (e) => {
    const files = [...(e.target.files || [])];
    for (const f of files) {
      if (editImages.length >= 3) { toast("最多 3 张图片", "err"); break; }
      await uploadFile(f);
    }
  };
}

$("#uploader").onclick = pickFile;
bindFileInput(document.getElementById("upFile"));
$("#uploader").addEventListener("dragover", e => { e.preventDefault(); $("#uploader").classList.add("drag"); });
$("#uploader").addEventListener("dragleave", () => $("#uploader").classList.remove("drag"));
$("#uploader").addEventListener("drop", e => {
  e.preventDefault(); $("#uploader").classList.remove("drag");
  const files = [...(e.dataTransfer.files || [])];
  (async () => {
    for (const f of files) {
      if (editImages.length >= 3) { toast("最多 3 张图片", "err"); break; }
      await uploadFile(f);
    }
  })();
});

async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/admin/upload", {
      method: "POST", headers: { "Authorization": "Bearer " + TOKEN }, body: fd
    });
    const d = await r.json();
    if (r.status === 401) { showLogin(); return; }
    if (!d.ok) throw new Error(d.msg || "上传失败");
    if (editImages.length < 3) {
      editImages.push(d.url);
      renderUploader();
      toast("图片已上传", "good");
    }
  } catch (e) {
    toast(e.message, "err");
  }
}

$("#saveBtn").onclick = async () => {
  const payload = {
    name: $("#eName").value.trim(),
    spec: $("#eSpec").value.trim(),
    price: parseFloat($("#ePrice").value) || 0,
    original_price: parseFloat($("#eOrig").value) || 0,
    stock: parseInt($("#eStock").value) || 0,
    sort_no: parseInt($("#eSort").value) || 0,
    production_date: $("#ePd").value,
    expiry_date: $("#eEd").value,
    description: $("#eDesc").value.trim(),
    image: editImages[0] || "",
    images: editImages,
    status: $("#eStatus").checked ? 1 : 0
  };
  if (!payload.name) return toast("请填写礼品名称", "err");
  const btn = $("#saveBtn");
  btn.disabled = true; btn.textContent = "保存中…";
  try {
    if (editingId) {
      await api(`/api/admin/products/${editingId}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } else {
      await api("/api/admin/products", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    }
    toast("已保存", "good");
    closeEdit();
    loadProducts();
  } catch (e) {
    toast(e.message, "err");
  } finally {
    btn.disabled = false; btn.textContent = "保 存";
  }
};

/* ---------------- 订单 ---------------- */
document.querySelectorAll("#oTabs button").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll("#oTabs button").forEach(x => x.classList.toggle("on", x === b));
    renderOrders(b.dataset.st);
  };
});

async function loadOrders() {
  try {
    const d = await api("/api/admin/orders");
    ordersCache = d.orders;
    const on = document.querySelector("#oTabs button.on");
    renderOrders(on ? on.dataset.st : "");
  } catch (e) { if (e.message !== "登录已过期，请重新登录") toast(e.message, "err"); }
}

function renderOrders(st) {
  const rows = !st ? ordersCache
    : st === "picked" ? ordersCache.filter(o => o.picked_at)
    : st === "pending" ? ordersCache.filter(o => o.status === "pending" && !o.picked_at)
    : ordersCache.filter(o => o.status === st);
  const stMap = { pending: ["amber", "待发放"], done: ["green", "已发放"], cancel: ["gray", "已取消"] };
  $("#ordersBody").innerHTML = rows.map(o => {
    const [cls, txt] = stMap[o.status] || ["gray", o.status];
    const items = (o.items || []).map(it => `
      <div class="oi-row">
        <img src="${esc(it.image || "/assets/placeholder.svg")}" onerror="this.src='/assets/placeholder.svg'">
        <span style="flex:1">${esc(it.name)}<small style="color:var(--muted)">　${esc(it.spec || "")}</small></span>
        <span style="color:var(--muted)">× ${it.qty}</span>
        <span class="num" style="width:80px;text-align:right">${money(it.price * it.qty)}</span>
      </div>`).join("");
    return `
    <div class="order-card" data-id="${o.id}">
      <div class="order-hd">
        <span class="order-no">${esc(o.order_no)}</span>
        <span class="tag ${cls}">${txt}</span>
        ${o.picked_at ? `<span class="tag green" data-pick="0" style="cursor:pointer" title="已领时间 ${esc(o.picked_at)}｜流程已结束（误点可点此撤销）">已领实物</span>` : ""}
        <span class="order-meta">${esc(o.buyer_name)}　${esc(o.buyer_dept || "")}　${esc(o.buyer_phone || "")}</span>
        <span class="order-meta" title="下单来源（计算机名 / 局域网 IP）">💻 ${o.client_host || o.client_ip ? `${esc(o.client_host || "未知主机")}${o.client_ip ? ` · ${esc(o.client_ip)}` : ""}` : "—"}</span>
        <span class="order-meta">${esc(o.created_at)}</span>
        ${o.picked_at ? `<span class="order-meta" style="color:var(--green)">📦 ${esc(o.picked_at)} 已领</span>` : ""}
        <span class="order-meta" style="margin-left:auto">${o.qty} 件 · 合计 <b style="color:var(--brand)">${money(o.total)}</b></span>
        ${o.status === "pending" ? `
          <button class="btn sm primary" data-st="done">确认发放</button>` :
          (o.status === "done" && !o.picked_at ? `<button class="btn sm" data-st="pending">撤销发放</button>` : "")}
        ${o.status === "done" && !o.picked_at
          ? `<button class="btn sm danger-solid" data-pick="1" title="确认发放后点击，点完流程即结束">实物已领</button>` : ""}
        ${o.status === "pending" && !o.picked_at ? `<button class="btn sm" data-st="cancel">取消</button>` : ""}
      </div>
      <div class="order-items">${items}${o.note ? `<div style="font-size:12px;color:var(--muted);margin-top:6px">备注：${esc(o.note)}</div>` : ""}</div>
    </div>`;
  }).join("") || `<div class="empty"><div class="icon">📄</div>暂无订单</div>`;

  $("#ordersBody").querySelectorAll(".order-card").forEach(card => {
    const id = +card.dataset.id;
    card.querySelector(".order-hd").addEventListener("click", e => {
      if (e.target.closest("button,[data-pick]")) return;
      card.classList.toggle("open");
    });
    card.querySelectorAll("[data-st]").forEach(b => {
      b.onclick = async () => {
        const st = b.dataset.st;
        if (st === "cancel") {
          const no = card.querySelector(".order-no")?.textContent.trim() || "";
          const who = card.querySelector(".order-meta")?.textContent.trim().split("　")[0] || "";
          if (!confirm(`确定取消订单 ${no}${who ? "（" + who + "）" : ""}？\n\n取消后该单不再计入已售出，状态不可恢复。`)) return;
        }
        if (st === "pending") {
          if (!confirm("确定撤销发放？订单会回到「待发放」状态。")) return;
        }
        try {
          await api(`/api/admin/orders/${id}/status`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: st })
          });
          toast(st === "cancel" ? "订单已取消" : "已更新", "good");
          loadOrders();
        } catch (e) { toast(e.message, "err"); }
      };
    });
    card.querySelectorAll("[data-pick]").forEach(b => {
      b.onclick = async (ev) => {
        ev.stopPropagation();
        const mark = b.dataset.pick === "1";
        if (!mark && !confirm("确定撤销「已领实物」标记？")) return;
        try {
          await api(`/api/admin/orders/${id}/picked`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ picked: mark })
          });
          toast(mark ? "已标记实物已领，流程结束" : "已撤销领取标记", "good");
          loadOrders();
        } catch (e) { toast(e.message, "err"); }
      };
    });
  });
}

/* ---------------- 修改口令 ---------------- */
$("#pwdBtn").onclick = async () => {
  const old = prompt("请输入当前口令：");
  if (old === null) return;
  const nw = prompt("请输入新口令（至少 6 位）：");
  if (nw === null) return;
  try {
    await api("/api/admin/pwd", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old, new: nw })
    });
    toast("口令已更新", "good");
  } catch (e) { toast(e.message, "err"); }
};

/* ---------------- 启动 ---------------- */
// 版本号由服务端返回（gm/__init__.py 单一来源），避免页面里写死过期
(async () => {
  try {
    const r = await fetch("/api/ping");
    const d = await r.json();
    if (d && d.version) {
      const el = document.getElementById("appVer");
      if (el) el.textContent = "v" + d.version;
      document.title = "礼品库后台 v" + d.version;
    }
  } catch (e) { /* 旧服务没有该字段时保持页面默认值 */ }
})();

if (TOKEN) {
  hideLogin();
  switchView(location.hash.replace("#/", "") || "dash");
  // 直达新增：/admin?new=1
  if (_params.get("new") === "1") setTimeout(() => openEdit(null), 120);
  // 直达编辑：/admin?edit=ID
  const editId = parseInt(_params.get("edit"));
  if (editId) {
    switchView("products");
    loadProducts().then(() => {
      const p = productsCache.find(x => x.id === editId);
      if (p) setTimeout(() => openEdit(p), 120);
    }).catch(console.error);
  }
} else {
  showLogin();
}

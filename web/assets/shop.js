/* ============================================================
   礼品库 · 前台逻辑
   ============================================================ */
"use strict";

const $ = (s) => document.querySelector(s);
const state = { q: "", sort: "new", products: [], cart: loadCart(), monthLimit: 0, saleEnded: false };

/* 溢出探针（验收用）：?__probe=1 时把页面横向溢出信息写进标题 */
if (new URLSearchParams(location.search).has("__probe")) {
  addEventListener("load", () => setTimeout(() => {
    const wide = [...document.querySelectorAll("body *")]
      .filter(el => el.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
      .slice(0, 6).map(el => el.className || el.tagName);
    document.title = "PROBE sw=" + document.documentElement.scrollWidth +
      " cw=" + document.documentElement.clientWidth + " wide=" + wide.join("|");
  }, 600));
}
/* 验收探针：?__lb=ID 直达该商品详情并打开灯箱 */
if (new URLSearchParams(location.search).get("__lb")) {
  addEventListener("load", () => setTimeout(() => {
    const p = state.products[0];
    if (p) {
      openDetail(p.id);
      const im = (Array.isArray(p.images) && p.images.length) ? p.images : [p.image];
      if (im[0]) openLightbox(im, 0, null);
    }
  }, 800));
}

/* ---------------- 工具 ---------------- */
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

function loadCart() {
  try { return JSON.parse(localStorage.getItem("gm_cart") || "{}"); } catch { return {}; }
}
function saveCart() { localStorage.setItem("gm_cart", JSON.stringify(state.cart)); }
function cartCount() { return Object.values(state.cart).reduce((a, b) => a + b, 0); }

async function api(url, opt = {}) {
  const r = await fetch(url, opt);
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.ok === false) throw new Error(d.msg || ("请求失败 " + r.status));
  return d;
}

/* ---------------- 数据 ---------------- */
async function loadShop() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  p.set("sort", state.sort);
  const d = await api("/api/shop?" + p.toString());
  state.products = d.products;
  state.saleEnded = !!d.sale_ended;
  $("#sKinds").textContent = d.products.length;
  $("#sStock").textContent = d.products.reduce((s, p) => s + (p.stock || 0), 0);
  $("#sPeriod").textContent = d.stats.period_qty ?? d.stats.period_orders ?? 0;
  document.body.classList.toggle("sale-over", state.saleEnded);
  const ht = $(".hero-title");
  if (ht) ht.innerHTML = state.saleEnded
    ? `礼品物资<span class="hero-dot">·</span><em>本期已结束</em>`
    : `礼品物资<span class="hero-dot">·</span><em>在线特卖</em>`;
  const chip = $("#saleChip");
  if (chip) {
    chip.classList.toggle("off", state.saleEnded);
    chip.querySelector("span").textContent = state.saleEnded ? "本期特卖已结束，敬请期待下一期" : "本期特卖进行中";
  }
  renderGrid();
}

/* ---------------- 商品网格 ---------------- */
function flagTags(p) {
  const t = [];
  if (p.is_new && !p.expired) t.push(`<span class="tag green">新品</span>`);
  if (p.expired) t.push(`<span class="tag red">已过有效期</span>`);
  else if (p.expiring) t.push(`<span class="tag amber">临期 ${p.days_left} 天</span>`);
  if (p.stock <= 0) t.push(`<span class="tag gray">已售完</span>`);
  return t.join("");
}

function renderGrid() {
  const g = $("#grid");
  if (state.saleEnded) {
    g.innerHTML = `<div class="empty sale-over-card" style="grid-column:1/-1">
      <div class="icon">🏁</div>
      <b>本期特卖活动已结束</b>
      <div class="so-sub">感谢大家的热情参与！<br>下一次特卖开启时间，请留意<b>行政部通知</b>。</div>
    </div>`;
    return;
  }
  if (!state.products.length) {
    g.innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="icon">🎁</div>没有找到匹配的礼品</div>`;
    return;
  }
  g.innerHTML = state.products.map(p => {
    const off = p.stock <= 0 || p.expired ? "off" : "";
    const sold = p.stock <= 0 && !p.expired ? `<div class="soldout"><b>已 售 完</b></div>` : "";
    return `
    <article class="pcard ${off}" data-id="${p.id}">
      <div class="ph">
        <img loading="lazy" src="${esc(p.image || "/assets/placeholder.svg")}" alt="${esc(p.name)}"
             onerror="this.src='/assets/placeholder.svg'">
        <div class="flags">${flagTags(p)}</div>
        ${sold}
      </div>
      <div class="bd">
        <div class="name">${esc(p.name)}</div>
        <div class="meta">${esc(p.spec || "")}</div>
        <div class="meta">有效期至 ${esc(p.expiry_date || "长期")}</div>
        <div class="ft">
          <span class="price"><small>¥</small>${Number(p.price).toFixed(2).replace(/\.00$/, "")}</span>
          ${p.original_price > p.price ? `<s class="price-was"><small>¥</small>${Number(p.original_price).toFixed(2).replace(/\.00$/, "")}</s>` : ""}
          <span class="stock-line ${p.stock <= 0 ? "zero" : (p.stock <= 5 ? "low" : "")}">${p.stock <= 0 ? "已售完" : "库存 " + p.stock}</span>
        </div>
      </div>
    </article>`;
  }).join("");
  g.querySelectorAll(".pcard").forEach(c =>
    c.onclick = () => openDetail(+c.dataset.id));
}

/* ---------------- 详情抽屉 ---------------- */
let curP = null, curQty = 1;

/* ---------------- 图片放大灯箱（含缩放） ---------------- */
let lbList = [], lbIdx = 0, lbOnSwitch = null;
let lbScale = 1, lbTx = 0, lbTy = 0;   // 缩放倍数与平移偏移

function openLightbox(imgs, idx, onSwitch) {
  lbList = imgs; lbIdx = idx; lbOnSwitch = onSwitch || null;
  lbResetZoom(false);
  renderLb();
  $("#lightbox").classList.add("show");
  lbShowHint();
}
function lbApply() {
  const img = $("#lb-img");
  img.style.transform = `translate(${lbTx}px, ${lbTy}px) scale(${lbScale})`;
  img.classList.toggle("zoomed", lbScale > 1);
  const z = $(".lb-zoom");
  if (z) {
    z.style.display = lbScale > 1 ? "" : "none";
    z.textContent = Math.round(lbScale * 100) + "%";
  }
}
function lbClampPan() {
  if (lbScale <= 1) { lbTx = 0; lbTy = 0; return; }
  const img = $("#lb-img"), box = $("#lightbox").getBoundingClientRect();
  const mx = Math.max(0, (img.offsetWidth * lbScale - box.width) / 2 + 60);
  const my = Math.max(0, (img.offsetHeight * lbScale - box.height) / 2 + 60);
  lbTx = Math.min(mx, Math.max(-mx, lbTx));
  lbTy = Math.min(my, Math.max(-my, lbTy));
}
function lbZoomAt(cx, cy, factor) {
  const ns = Math.min(4, Math.max(1, lbScale * factor));
  if (Math.abs(ns - lbScale) < 0.01) return;
  const box = $("#lightbox").getBoundingClientRect();
  const px = cx - box.left - box.width / 2, py = cy - box.top - box.height / 2;
  const k = ns / lbScale;
  lbTx = px - (px - lbTx) * k;
  lbTy = py - (py - lbTy) * k;
  lbScale = ns;
  lbClampPan(); lbApply();
}
function lbResetZoom(apply = true) {
  lbScale = 1; lbTx = 0; lbTy = 0;
  if (apply) lbApply();
}
let lbHintTimer = null;
function lbShowHint() {
  const h = $(".lb-hint");
  if (!h) return;
  h.classList.add("show");
  clearTimeout(lbHintTimer);
  lbHintTimer = setTimeout(() => h.classList.remove("show"), 3600);
}
function renderLb() {
  $("#lb-img").src = lbList[lbIdx];
  lbResetZoom(false); lbApply();
  const multi = lbList.length > 1;
  $(".lb-prev").style.display = multi ? "" : "none";
  $(".lb-next").style.display = multi ? "" : "none";
  $(".lb-count").textContent = multi ? `${lbIdx + 1} / ${lbList.length}` : "";
}
function lbStep(d) {
  if (lbList.length < 2) return;
  lbIdx = (lbIdx + d + lbList.length) % lbList.length;
  renderLb();
  if (lbOnSwitch) lbOnSwitch(lbIdx);
}
function closeLightbox() { $("#lightbox").classList.remove("show"); }

function openDetail(id) {
  const p = state.products.find(x => x.id === id);
  if (!p) return;
  curP = p; curQty = 1;
  const dl = p.days_left;
  const pct = p.expired ? 100 : (dl == null ? 100 : Math.max(4, Math.min(100, dl / 730 * 100)));
  const barColor = p.expired ? "var(--red)" : (dl != null && dl <= 90 ? "var(--amber)" : "var(--green)");
  const freshLabel = dl == null ? "长期有效" : (p.expired ? `已过期 ${-dl} 天` : `剩余 ${dl} 天`);

  const imgs = (Array.isArray(p.images) && p.images.length) ? p.images
             : (p.image ? [p.image] : ["/assets/placeholder.svg"]);
  $("#dBody").innerHTML = `
    <img id="d-img" src="${esc(imgs[0])}"
         onerror="this.src='/assets/placeholder.svg'" alt="">
    ${imgs.length > 1 ? `
    <div class="d-thumbs" id="d-thumbs">
      ${imgs.map((s, i) => `<img class="${i === 0 ? "on" : ""}" data-src="${esc(s)}"
           src="${esc(s)}" onerror="this.src='/assets/placeholder.svg'" alt="">`).join("")}
    </div>` : ""}
    <h2 id="d-name">${esc(p.name)}</h2>
    <div id="d-price">${money(p.price)}${p.original_price > p.price ? `<s class="price-was lg">${money(p.original_price)}</s>` : ""}</div>
    <div class="d-row">${flagTags(p)}
      <span class="tag gray">规格 ${esc(p.spec || "—")}</span></div>
    ${p.description ? `<div class="d-desc">${esc(p.description)}</div>` : ""}
    <div style="margin-top:16px">
      <div class="d-kv"><span>生产日期</span><b>${esc(p.production_date || "—")}</b></div>
      <div class="d-kv"><span>有效期至</span><b>${esc(p.expiry_date || "长期")}</b></div>
      <div class="d-kv"><span>当前库存</span><b>${p.stock} 件</b></div>
    </div>
    ${dl != null ? `
    <div class="fresh-bar">
      <div class="lbl"><span>新鲜度</span><span>${freshLabel}</span></div>
      <div class="bar"><i style="width:${pct}%;background:${barColor}"></i></div>
    </div>` : ""}`;

  // 多图切换：点缩略图换主图；点主图/缩略图放大
  const thumbs = $("#d-thumbs");
  let curImg = 0;
  const showImg = (i) => {
    curImg = (i + imgs.length) % imgs.length;
    $("#d-img").src = imgs[curImg];
    if (thumbs) {
      thumbs.querySelectorAll("img").forEach((x, j) => x.classList.toggle("on", j === curImg));
    }
  };
  $("#d-img").onclick = () => openLightbox(imgs, curImg, showImg);
  if (thumbs) {
    thumbs.querySelectorAll("img").forEach((t, i) => t.onclick = () => showImg(i));
  }

  const canBuy = p.stock > 0 && !p.expired;
  $("#dFoot").innerHTML = canBuy ? `
    <div class="qty-row">
      <span style="color:var(--muted);font-size:13px">购买数量</span>
      <div class="stepper">
        <button id="qMinus">−</button><input id="qVal" value="1" inputmode="numeric"><button id="qPlus">＋</button>
      </div>
      <span style="color:var(--muted);font-size:12px">最多 ${p.stock} 件</span>
      <button class="btn primary" style="margin-left:auto" id="addCart">加入清单</button>
    </div>` :
    `<button class="btn block" disabled>${p.expired ? "已过有效期，无法购买" : "已售完"}</button>`;

  if (canBuy) {
    const clamp = v => Math.max(1, Math.min(p.stock, v || 1));
    $("#qMinus").onclick = () => { curQty = clamp(curQty - 1); $("#qVal").value = curQty; };
    $("#qPlus").onclick = () => { curQty = clamp(curQty + 1); $("#qVal").value = curQty; };
    $("#qVal").onchange = e => { curQty = clamp(parseInt(e.target.value)); e.target.value = curQty; };
    $("#addCart").onclick = () => {
      state.cart[p.id] = (state.cart[p.id] || 0) + curQty;
      saveCart(); updateBadge();
      toast(`已加入清单：${p.name} × ${curQty}`, "good");
      closeDrawers();
    };
  }
  openDrawer("dDrawer");
}

/* ---------------- 购物车 ---------------- */
function renderCart() {
  const ids = Object.keys(state.cart).map(Number).filter(id => state.cart[id] > 0);
  const body = $("#cBody"), foot = $("#cFoot");
  if (!ids.length) {
    body.innerHTML = `<div class="empty"><div class="icon">🛒</div>清单还是空的<br>去挑几件心仪的礼品吧</div>`;
    foot.innerHTML = "";
    return;
  }
  let total = 0, qty = 0;
  body.innerHTML = ids.map(id => {
    const p = state.products.find(x => x.id === id);
    if (!p) return "";
    const n = state.cart[id];
    total += p.price * n; qty += n;
    return `
    <div class="cart-item" data-id="${id}">
      <img src="${esc(p.image || "/assets/placeholder.svg")}" onerror="this.src='/assets/placeholder.svg'">
      <div class="ci-bd">
        <div class="ci-name">${esc(p.name)}</div>
        <div class="ci-spec">${esc(p.spec || "")}　单价 ${money(p.price)}</div>
        <div class="ci-ft">
          <div class="stepper">
            <button data-act="dec">−</button><input value="${n}" data-act="set" inputmode="numeric"><button data-act="inc">＋</button>
          </div>
          <span class="ci-price" style="margin-left:auto">${money(p.price * n)}</span>
          <button class="cart-del" data-act="del">移除</button>
        </div>
      </div>
    </div>`;
  }).join("");

  foot.innerHTML = `
    <div class="sum-line"><span>共 ${qty} 件，合计</span><span class="price">${money(total)}</span></div>
    <div class="form-grid">
      <input class="input" id="fName" placeholder="购买人姓名 *" value="${esc(localStorage.getItem("gm_name") || "")}">
      <input class="input" id="fDept" placeholder="部门" value="${esc(localStorage.getItem("gm_dept") || "")}">
      <input class="input full" id="fPhone" placeholder="联系电话" value="${esc(localStorage.getItem("gm_phone") || "")}">
      <textarea class="input full" id="fNote" placeholder="备注（选填）" rows="2"></textarea>
    </div>
    <button class="btn primary lg block" id="submitOrder">提交购买申请</button>`;

  body.querySelectorAll(".cart-item").forEach(row => {
    const id = +row.dataset.id;
    row.querySelectorAll("[data-act]").forEach(el => {
      el.onclick = () => {
        const act = el.dataset.act;
        const max = (state.products.find(x => x.id === id) || {}).stock || 0;
        if (act === "inc") state.cart[id] = Math.min(max, state.cart[id] + 1);
        if (act === "dec") state.cart[id] = state.cart[id] - 1;
        if (act === "del") state.cart[id] = 0;
        if (act === "set") {
          const v = parseInt(el.value) || 0;
          if (v <= 0) state.cart[id] = 0;
          else if (v > max) { state.cart[id] = max; toast(`库存仅剩 ${max} 件`); }
          else state.cart[id] = v;
        }
        if (state.cart[id] <= 0) delete state.cart[id];
        saveCart(); updateBadge(); renderCart();
      };
    });
  });

  $("#submitOrder").onclick = submitOrder;
}

async function submitOrder() {
  if (state.saleEnded) {
    toast("本期特卖活动已结束，无法下单；请留意行政部通知", "err");
    return;
  }
  const name = $("#fName").value.trim();
  const items = Object.entries(state.cart)
    .filter(([, n]) => n > 0).map(([id, n]) => ({ id: +id, qty: n }));
  if (!name) return toast("请填写购买人姓名", "err");
  if (!items.length) return toast("清单为空", "err");
  localStorage.setItem("gm_name", name);
  localStorage.setItem("gm_dept", $("#fDept").value.trim());
  localStorage.setItem("gm_phone", $("#fPhone").value.trim());

  const btn = $("#submitOrder");
  btn.disabled = true; btn.textContent = "提交中…";
  try {
    const d = await api("/api/order", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        buyer_name: name, buyer_dept: $("#fDept").value.trim(),
        buyer_phone: $("#fPhone").value.trim(), note: $("#fNote").value.trim(), items
      })
    });
    state.cart = {}; saveCart(); updateBadge();
    $("#cBody").innerHTML = `
      <div class="order-done">
        <div class="ok-icon">✓</div>
        <h3>购买申请已提交</h3>
        <div class="ord-no">单号 ${d.order_no}　·　${d.qty} 件　·　合计 ${money(d.total)}</div>
        <p style="color:var(--muted);font-size:12px;margin-top:12px">请凭单号到行政部取货，管理员确认后即完成发放。</p>
      </div>`;
    $("#cFoot").innerHTML = `<button class="btn lg block" onclick="closeDrawers();loadShop()">继续挑选</button>`;
    loadShop().catch(console.error);
  } catch (e) {
    toast(e.message, "err");
    btn.disabled = false; btn.textContent = "提交购买申请";
    loadShop().catch(console.error);
    renderCart();
  }
}

function updateBadge() {
  const n = cartCount();
  const b = $("#cartBadge");
  b.style.display = n ? "flex" : "none";
  b.textContent = n;
}

/* ---------------- 抽屉控制 ---------------- */
function openDrawer(id) {
  $("#mask1").classList.add("show");
  $("#" + id).classList.add("show");
}
function closeDrawers() {
  ["dDrawer", "cDrawer", "qDrawer"].forEach(id => $("#" + id).classList.remove("show"));
  $("#mask1").classList.remove("show");
}

/* ---------------- 自助查单 ---------------- */
async function doQuery() {
  const kw = $("#qKeyword").value.trim();
  if (kw.length < 2) return toast("请输入至少 2 个字符", "err");
  $("#qResult").innerHTML = `<div class="empty">查询中…</div>`;
  try {
    const d = await api("/api/order/query", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword: kw })
    });
    if (!d.orders.length) {
      $("#qResult").innerHTML = `<div class="empty"><div class="icon">📭</div>没有找到相关购买记录</div>`;
      return;
    }
    const stMap = { pending: ["amber", "待发放"], done: ["green", "已发放"], cancel: ["gray", "已取消"] };
    $("#qResult").innerHTML = d.orders.map(o => {
      const [cls, txt] = stMap[o.status] || ["gray", o.status];
      const names = (o.items || []).map(it => `${esc(it.name)} × ${it.qty}`).join("、");
      return `<div class="order-card" style="cursor:default">
        <div class="order-hd" style="cursor:default">
          <span class="order-no">${esc(o.order_no)}</span>
          <span class="tag ${cls}">${txt}</span>
          ${o.picked_at ? `<span class="tag green">已领实物</span>` : ""}
          <span class="order-meta" style="margin-left:auto">${o.qty} 件 · ${money(o.total)}</span>
        </div>
        <div style="font-size:13px;margin-top:6px">${names}</div>
        <div class="order-meta" style="margin-top:4px">${esc(o.created_at)}　${esc(o.buyer_dept || "")}</div>
      </div>`;
    }).join("");
  } catch (e) {
    $("#qResult").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}
$("#myOrderBtn").onclick = () => openDrawer("qDrawer");
$("#qGo").onclick = doQuery;
$("#qKeyword").addEventListener("keydown", e => { if (e.key === "Enter") doQuery(); });

/* ---------------- 事件绑定 ---------------- */
let searchTimer = null;
$("#q").addEventListener("input", e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.q = e.target.value.trim(); loadShop().catch(console.error); }, 300);
});
$("#sort").onchange = e => { state.sort = e.target.value; loadShop().catch(console.error); };
$("#cartBtn").onclick = () => { renderCart(); openDrawer("cDrawer"); };
$("#mask1").onclick = closeDrawers;
document.querySelectorAll("[data-close]").forEach(b => b.onclick = closeDrawers);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawers(); });

updateBadge();

/* 灯箱事件绑定（一次） */
$(".lb-x").onclick = closeLightbox;
$(".lb-prev").onclick = (e) => { e.stopPropagation(); lbStep(-1); };
$(".lb-next").onclick = (e) => { e.stopPropagation(); lbStep(1); };
$(".lb-zoom").onclick = (e) => { e.stopPropagation(); lbResetZoom(); };
$("#lightbox").onclick = (e) => { if (e.target === e.currentTarget) closeLightbox(); };
addEventListener("keydown", (e) => {
  if (!$("#lightbox").classList.contains("show")) return;
  if (e.key === "Escape") { lbScale > 1 ? lbResetZoom() : closeLightbox(); }
  else if (e.key === "ArrowLeft") lbStep(-1);
  else if (e.key === "ArrowRight") lbStep(1);
  else if (e.key === "+" || e.key === "=") lbZoomAt(innerWidth / 2, innerHeight / 2, 1.25);
  else if (e.key === "-") lbZoomAt(innerWidth / 2, innerHeight / 2, 0.8);
});

/* 滚轮缩放（以光标为中心，1×~4×） */
$("#lightbox").addEventListener("wheel", (e) => {
  if (!$("#lightbox").classList.contains("show")) return;
  e.preventDefault();
  lbZoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.18 : 1 / 1.18);
}, { passive: false });

/* 鼠标：放大后拖动平移；单击在 1× ↔ 2.5× 间切换 */
let lbDrag = null, lbWasDrag = false;
$("#lb-img").addEventListener("pointerdown", (e) => {
  if (lbScale <= 1) return;
  lbDrag = { x: e.clientX, y: e.clientY, tx: lbTx, ty: lbTy, moved: false };
  $("#lb-img").classList.add("dragging");
  e.preventDefault();
});
addEventListener("pointermove", (e) => {
  if (!lbDrag) return;
  const dx = e.clientX - lbDrag.x, dy = e.clientY - lbDrag.y;
  if (Math.abs(dx) + Math.abs(dy) > 3) lbDrag.moved = true;
  lbTx = lbDrag.tx + dx; lbTy = lbDrag.ty + dy;
  lbClampPan(); lbApply();
});
addEventListener("pointerup", () => {
  lbWasDrag = !!(lbDrag && lbDrag.moved);
  lbDrag = null;
  $("#lb-img").classList.remove("dragging");
});
$("#lb-img").addEventListener("click", (e) => {
  if (lbWasDrag) { lbWasDrag = false; return; }
  if (lbScale > 1) lbResetZoom();
  else lbZoomAt(e.clientX, e.clientY, 2.5);
});

/* 触屏：1× 时左右滑切换；放大后单指拖动、双指捏合缩放 */
let lbTouchX = 0, lbPinch = null, lbTouchPan = null;
$("#lightbox").addEventListener("touchstart", (e) => {
  if (e.touches.length === 2) {
    const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                         e.touches[0].clientY - e.touches[1].clientY);
    lbPinch = { d, s: lbScale };
    lbTouchPan = null;
  } else if (e.touches.length === 1) {
    lbTouchX = e.touches[0].clientX;
    if (lbScale > 1) lbTouchPan = { x: e.touches[0].clientX, y: e.touches[0].clientY, tx: lbTx, ty: lbTy };
  }
}, { passive: true });
$("#lightbox").addEventListener("touchmove", (e) => {
  if (e.touches.length === 2 && lbPinch) {
    e.preventDefault();
    const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                         e.touches[0].clientY - e.touches[1].clientY);
    const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
    const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
    const box = $("#lightbox").getBoundingClientRect();
    const px = midX - box.left - box.width / 2, py = midY - box.top - box.height / 2;
    const ns = Math.min(4, Math.max(1, lbPinch.s * d / lbPinch.d));
    const k = ns / lbScale;
    lbTx = px - (px - lbTx) * k; lbTy = py - (py - lbTy) * k;
    lbScale = ns; lbClampPan(); lbApply();
  } else if (e.touches.length === 1 && lbTouchPan && lbScale > 1) {
    e.preventDefault();
    lbTx = lbTouchPan.tx + (e.touches[0].clientX - lbTouchPan.x);
    lbTy = lbTouchPan.ty + (e.touches[0].clientY - lbTouchPan.y);
    lbClampPan(); lbApply();
  }
}, { passive: false });
$("#lightbox").addEventListener("touchend", (e) => {
  lbPinch = null; lbTouchPan = null;
  if (e.touches.length) return;
  const dx = e.changedTouches[0].clientX - lbTouchX;
  if (lbScale <= 1 && Math.abs(dx) > 50) lbStep(dx < 0 ? 1 : -1);
}, { passive: true });

loadShop().then(() => {
  // 支持 /?p=ID 直达某商品详情（便于分享链接）
  const pid = parseInt(new URLSearchParams(location.search).get("p"));
  if (pid && state.products.some(x => x.id === pid)) openDetail(pid);
}).catch(e => {
  $("#grid").innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="icon">⚠️</div>${esc(e.message)}<br><small>请确认服务已启动</small></div>`;
});

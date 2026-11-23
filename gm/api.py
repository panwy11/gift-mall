# -*- coding: utf-8 -*-
"""业务接口层。"""
import os
import re
import json
import socket
import subprocess
import time
import secrets
import urllib.parse
from datetime import datetime, timedelta

from . import store
from . import xlsx as _xlsx      # 打包时确保被收集（导出/模板生成）
from . import xlsxread as _xlsxread  # 打包时确保被收集（批量导入解析）
from .httpd import route, ok, err, json_resp, need_auth, new_token, revoke, Request

UPLOAD_DIR = os.path.join(store.data_dir(), "uploads")
ALLOW_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_IMAGES = 3          # 每个礼品最多 3 张图


def _norm_images(d):
    """取请求里的 images 数组，清洗为最多 MAX_IMAGES 张的 JSON 字符串；封面取第一张。"""
    imgs = d.get("images")
    if not isinstance(imgs, list):
        imgs = [d.get("image", "")] if d.get("image") else []
    imgs = [str(u).strip() for u in imgs if str(u).strip()][:MAX_IMAGES]
    return json.dumps(imgs, ensure_ascii=False), (imgs[0] if imgs else "")


def _ip(req: Request) -> str:
    try:
        return req.handler.client_address[0]
    except Exception:
        return ""


def _audit(action, detail="", ip=""):
    """写操作日志；任何异常不影响主流程。"""
    store.log_action(action, detail, ip)


_HOST_CACHE = {}          # ip -> (计算机名, 时间戳)；反查较慢，缓存 10 分钟
_HOST_TTL = 600


def _resolve_host(ip: str) -> str:
    """按内网 IP 反查计算机名：先 DNS 反向解析，失败再用 NetBIOS(nbtstat) 兜底。

    域环境下第一步基本都能命中；工作组 / 没配反向解析区时走 nbtstat。
    查不到返回空串，不影响下单。
    """
    if not ip:
        return ""
    if ip in ("127.0.0.1", "::1"):
        return socket.gethostname().upper()
    hit = _HOST_CACHE.get(ip)
    if hit and time.time() - hit[1] < _HOST_TTL:
        return hit[0]
    name = ""
    try:
        name = socket.gethostbyaddr(ip)[0]
    except Exception:
        name = ""
    if not name or name == ip:
        try:
            out = subprocess.run(["nbtstat", "-A", ip], capture_output=True,
                                 timeout=4).stdout.decode("gbk", "replace")
            for line in out.splitlines():
                up = line.upper()
                if "<00>" in up and "UNIQUE" in up:
                    parts = line.split()
                    n = parts[0].strip() if parts else ""
                    if n and not n.upper().startswith("__MSBROWSE"):
                        name = n
                        break
        except Exception:
            pass
    name = (name or "").split(".")[0].strip().upper()
    _HOST_CACHE[ip] = (name, time.time())
    return name


# ================================================================ 前台
@route("GET", r"/api/shop")
def api_shop(req: Request):
    q_ = req.q("q").strip()
    cat = req.q("cat").strip()
    sort = req.q("sort").strip() or "new"
    rows = store.list_products(q_, cat, status=1, sort=sort)
    # 过有效期的商品不展示在前台（后台仍可见，便于处理）
    rows = [r for r in rows if not r["expired"]]
    st = store.stats()
    limit = int(store.get_settings().get("month_limit") or 0)
    ended = (store.get_settings().get("sale_ended") == "1")
    return ok({
        "products": [] if ended else rows,
        "categories": [] if ended else store.categories(exclude_expired=True),
        "stats": st,
        "month_limit": limit,
        "sale_ended": ended,
    })


@route("POST", r"/api/order/query")
def api_order_query(req: Request):
    kw = str(req.json().get("keyword", "")).strip()
    if len(kw) < 2:
        return err("请输入至少 2 个字符的姓名、手机号或单号")
    rows = store.query_orders(kw)
    # 前台自助查询不暴露手机号
    for r in rows:
        r["buyer_phone"] = (r["buyer_phone"][:3] + "****" + r["buyer_phone"][-4:]) \
            if len(r["buyer_phone"]) >= 7 else "***"
    return ok({"orders": rows})


@route("GET", r"/api/product/(?P<pid>\d+)")
def api_product(req: Request):
    if store.get_settings().get("sale_ended") == "1":
        return err("本期特卖活动已结束；请留意行政部通知", 403)
    p = store.get_product(int(req.params["pid"]))
    if not p or not p["status"]:
        return err("商品不存在或已下架", 404)
    return ok({"product": p})


@route("POST", r"/api/order")
def api_order(req: Request):
    d = req.json()
    # 特卖已结束：硬性拒绝下单（防旧页面直接调接口）
    if store.get_settings().get("sale_ended") == "1":
        return err("本期特卖活动已结束，无法下单；请留意行政部通知")
    items = d.get("items") or []
    ip = _ip(req)
    good, payload = store.create_order(
        d.get("buyer_name", ""), d.get("buyer_dept", ""),
        d.get("buyer_phone", ""), d.get("note", ""), items,
        client_ip=ip, client_host=_resolve_host(ip))
    if not good:
        return err(payload)
    return ok(payload)


# ================================================================ 登录
# 登录防爆破：同 IP 15 分钟内错 5 次 -> 锁定 10 分钟（内存态，重启即清零）
_LOGIN_FAILS = {}
_LOGIN_LOCK = {}


@route("POST", r"/api/admin/login")
def api_login(req: Request):
    ip = _ip(req)
    nowt = time.time()
    if nowt < _LOGIN_LOCK.get(ip, 0):
        _audit("登录锁定", "尝试次数过多被临时锁定", ip)
        remain = int((_LOGIN_LOCK[ip] - nowt) / 60) + 1
        return err("尝试次数过多，已临时锁定，请约 %d 分钟后再试" % remain)
    d = req.json()
    if not store.check_pwd(str(d.get("password", ""))):
        fails = [t for t in _LOGIN_FAILS.get(ip, []) if nowt - t < 900]
        fails.append(nowt)
        _LOGIN_FAILS[ip] = fails
        _audit("登录失败", "口令不正确（15 分钟内第 %d 次）" % len(fails), ip)
        if len(fails) >= 5:
            _LOGIN_LOCK[ip] = nowt + 600
            _LOGIN_FAILS[ip] = []
        return err("口令不正确")
    _LOGIN_FAILS.pop(ip, None)
    _LOGIN_LOCK.pop(ip, None)
    _audit("登录成功", "", ip)
    return ok({"token": new_token(), "expire": 8 * 3600})


@route("POST", r"/api/admin/logout")
def api_logout(req: Request):
    revoke(req.token())
    return ok()


@route("POST", r"/api/admin/pwd")
@need_auth
def api_set_pwd(req: Request):
    d = req.json()
    old, new = str(d.get("old", "")), str(d.get("new", ""))
    if not store.check_pwd(old):
        return err("原口令不正确")
    if len(new) < 6:
        return err("新口令至少 6 位")
    store.set_pwd(new)
    _audit("修改口令", "", _ip(req))
    return ok({"msg": "口令已更新"})


# ================================================================ 后台：商品
@route("GET", r"/api/admin/products")
@need_auth
def api_admin_products(req: Request):
    rows = store.list_products(req.q("q").strip(), req.q("cat").strip(), status=None,
                              sort="new")
    return ok({"products": rows, "categories": store.categories()})


@route("POST", r"/api/admin/products")
@need_auth
def api_admin_create(req: Request):
    d = req.json()
    bad = _validate(d)
    if bad:
        return err(bad)
    with store.connect() as conn:
        imgs_json, cover = _norm_images(d)
        cur = conn.execute(
            """INSERT INTO products(name,spec,price,original_price,stock,production_date,
               expiry_date,image,images,description,status,sort_no,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["name"].strip(),
             d.get("spec", "").strip(), float(d.get("price") or 0),
             max(0.0, float(d.get("original_price") or 0)),
             int(d.get("stock") or 0), d.get("production_date", ""),
             d.get("expiry_date", ""), cover, imgs_json,
             d.get("description", "").strip(), int(d.get("status", 1)),
             int(d.get("sort_no") or 0), store.now()))
        conn.commit()
        pid = cur.lastrowid
    _audit("新增礼品", "%s（¥%s × %s）" % (d["name"].strip(), d.get("price"), d.get("stock")), _ip(req))
    return ok({"id": pid})


@route("PUT", r"/api/admin/products/(?P<pid>\d+)")
@need_auth
def api_admin_update(req: Request):
    d = req.json()
    bad = _validate(d)
    if bad:
        return err(bad)
    with store.connect() as conn:
        imgs_json, cover = _norm_images(d)
        old = conn.execute("SELECT image, images FROM products WHERE id=?",
                           (int(req.params["pid"]),)).fetchone()
        conn.execute(
            """UPDATE products SET name=?,spec=?,price=?,original_price=?,stock=?,
               production_date=?,expiry_date=?,image=?,images=?,description=?,status=?,sort_no=?
               WHERE id=?""",
            (d["name"].strip(),
             d.get("spec", "").strip(), float(d.get("price") or 0),
             max(0.0, float(d.get("original_price") or 0)),
             int(d.get("stock") or 0), d.get("production_date", ""),
             d.get("expiry_date", ""), cover, imgs_json,
             d.get("description", "").strip(), int(d.get("status", 1)),
             int(d.get("sort_no") or 0), int(req.params["pid"])))
        conn.commit()
    # 编辑时被移除的旧图，回收磁盘文件（历史订单引用的会自动保留）
    if old:
        gc = store.cleanup_uploads(list(store.product_image_files([old]) -
                                        store._json_image_names(imgs_json) -
                                        ({cover} if cover else set())))
    else:
        gc = 0
    _audit("编辑礼品", "#%s %s%s" % (req.params["pid"], d["name"].strip(),
           "（清理图片 %d 张）" % gc if gc else ""), _ip(req))
    return ok({"removed_images": gc})


@route("POST", r"/api/admin/products/batch")
@need_auth
def api_admin_batch(req: Request):
    d = req.json()
    action = d.get("action", "")
    ids = [int(i) for i in (d.get("ids") or []) if str(i).isdigit()]
    if not ids:
        return err("未选择任何礼品")
    qs = ",".join("?" * len(ids))
    detached = []
    with store.connect() as conn:
        cur = conn.cursor()
        if action == "delete":
            rows = conn.execute(
                "SELECT image, images FROM products WHERE id IN (%s)" % qs, ids).fetchall()
            detached = list(store.product_image_files(rows))
            cur.execute("DELETE FROM products WHERE id IN (%s)" % qs, ids)
        elif action == "edit":
            sets, args = [], []
            price = d.get("price")
            mode = d.get("price_mode", "fixed")
            if price is not None and str(price).strip() != "":
                try:
                    price = float(price)
                except (TypeError, ValueError):
                    return err("价格格式不正确")
                if price < 0:
                    return err("价格不能为负数")
                if mode == "percent":
                    if price <= 0 or price > 500:
                        return err("百分比需在 0-500 之间")
                    sets.append("price=ROUND(price*?,2)")
                    args.append(price / 100.0)
                elif mode == "fixed":
                    sets.append("price=?")
                    args.append(round(price, 2))
                else:
                    return err("未知调价方式")
            stock = d.get("stock")
            stock_mode = d.get("stock_mode", "set")
            if stock is not None and str(stock).strip() != "":
                try:
                    stock = int(float(stock))
                except (TypeError, ValueError):
                    return err("库存格式不正确")
                if stock < 0:
                    return err("库存不能为负数")
                if stock_mode == "add":
                    if stock == 0:
                        return err("增加数量需大于 0")
                    sets.append("stock=stock+?")
                    args.append(stock)
                elif stock_mode == "set":
                    sets.append("stock=?")
                    args.append(stock)
                else:
                    return err("未知库存方式")
            if not sets:
                return err("没有要修改的内容（价格、库存都未填写）")
            args.extend(ids)
            cur.execute("UPDATE products SET %s WHERE id IN (%s)" % (",".join(sets), qs), args)
        elif action in ("on", "off"):
            cur.execute("UPDATE products SET status=? WHERE id IN (%s)" % qs,
                        (1 if action == "on" else 0, *ids))
        else:
            return err("未知操作")
        n = cur.rowcount
        conn.commit()
    _label = {"delete": "批量删除", "on": "批量上架", "off": "批量下架",
              "edit": "批量修改"}[action]
    gc = store.cleanup_uploads(detached) if detached else 0
    _audit(_label, "%d 件（ids: %s）%s" % (len(ids), ",".join(map(str, ids))[:200],
           "（清理图片 %d 张）" % gc if gc else ""), _ip(req))
    return ok({"affected": max(n, 0), "removed_images": gc})


@route("DELETE", r"/api/admin/products/(?P<pid>\d+)")
@need_auth
def api_admin_delete(req: Request):
    pid = int(req.params["pid"])
    with store.connect() as conn:
        rows = conn.execute("SELECT image, images FROM products WHERE id=?", (pid,)).fetchall()
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
    gc = store.cleanup_uploads(list(store.product_image_files(rows)))
    _audit("删除礼品", "#%s%s" % (req.params["pid"], "（清理图片 %d 张）" % gc if gc else ""), _ip(req))
    return ok({"removed_images": gc})


@route("POST", r"/api/admin/products/(?P<pid>\d+)/stock")
@need_auth
def api_admin_stock(req: Request):
    d = req.json()
    delta = int(d.get("delta") or 0)
    with store.connect() as conn:
        conn.execute("UPDATE products SET stock=MAX(0, stock+?) WHERE id=?",
                     (delta, int(req.params["pid"])))
        conn.commit()
        row = conn.execute("SELECT stock FROM products WHERE id=?",
                           (int(req.params["pid"]),)).fetchone()
    _audit("调整库存", "#%s %s%d -> %s" % (req.params["pid"], "+" if delta >= 0 else "", delta,
                                           row["stock"] if row else "?"), _ip(req))
    return ok({"stock": row["stock"] if row else 0})


def _validate(d):
    if not str(d.get("name", "")).strip():
        return "请填写商品名称"
    try:
        if float(d.get("price") or 0) < 0:
            return "价格不能为负"
    except Exception:
        return "价格格式不正确"
    try:
        if int(d.get("stock") or 0) < 0:
            return "库存不能为负"
    except Exception:
        return "库存格式不正确"
    return None


# ================================================================ 后台：图片上传
@route("POST", r"/api/admin/upload")
@need_auth
def api_upload(req: Request):
    fields, files = req.form()
    if not files:
        return err("没有收到文件")
    f = files[0]
    ext = os.path.splitext(f["filename"])[1].lower() or ".png"
    if ext not in ALLOW_EXT:
        return err("仅支持图片格式：png / jpg / webp / gif")
    if len(f["data"]) > 8 * 1024 * 1024:
        return err("图片请不要超过 8MB")
    name = "p_%s_%s%s" % (datetime.now().strftime("%Y%m%d%H%M%S"),
                          secrets.token_hex(3), ext)
    with open(os.path.join(UPLOAD_DIR, name), "wb") as fp:
        fp.write(f["data"])
    return ok({"url": "/uploads/" + name})


# ================================================================ 后台：订单 / 统计
@route("GET", r"/api/admin/orders")
@need_auth
def api_admin_orders(req: Request):
    return ok({"orders": store.list_orders(req.q("status").strip())})


@route("POST", r"/api/admin/orders/(?P<oid>\d+)/status")
@need_auth
def api_admin_order_status(req: Request):
    st = req.json().get("status", "")
    if st not in ("pending", "done", "cancel"):
        return err("状态不合法")
    oid = int(req.params["oid"])
    o = store.get_order(oid)
    if not o:
        return err("订单不存在")
    # 流程：待发放 → 确认发放 → 实物已领（终点）。已领后状态锁定，不允许回退或取消
    if o["picked_at"] and st != "done":
        return err("该订单已标记「实物已领」，流程已结束，不能再撤销发放或取消")
    store.update_order_status(oid, st)
    _audit("订单状态", "#%s -> %s" % (req.params["oid"], st), _ip(req))
    return ok()


@route("POST", r"/api/admin/orders/(?P<oid>\d+)/picked")
@need_auth
def api_admin_order_picked(req: Request):
    """标记「实物已领」＝流程终点；撤销仅作为误点的补救。"""
    oid = int(req.params["oid"])
    picked = bool(req.json().get("picked", True))
    o = store.get_order(oid)
    if not o:
        return err("订单不存在")
    if picked and o["status"] == "cancel":
        return err("该订单已取消，不能标记实物已领")
    store.set_order_picked(oid, picked)
    _audit("实物已领" if picked else "撤销已领", "#%s" % req.params["oid"], _ip(req))
    return ok({"status": "done" if picked else o["status"]})


@route("GET", r"/api/admin/stats")
@need_auth
def api_admin_stats(req: Request):
    return ok({"stats": store.stats(), "chart": store.chart_data()})


# ================================================================ 后台：设置 / 导出
@route("GET", r"/api/admin/logs")
@need_auth
def api_admin_logs(req: Request):
    try:
        limit = min(500, max(1, int(req.q("limit", "200"))))
    except ValueError:
        limit = 200
    return ok({"logs": store.list_logs(limit)})


@route("GET", r"/api/admin/backup")
@need_auth
def api_admin_backup(req: Request):
    data = store.build_backup()
    fname = "gift-backup-%s.zip" % datetime.now().strftime("%Y%m%d-%H%M%S")
    return 200, [
        ("Content-Type", "application/zip"),
        ("Content-Disposition", "attachment; filename=%s" % fname),
    ], data


@route("GET", r"/api/admin/settings")
@need_auth
def api_admin_get_settings(req: Request):
    return ok({"settings": store.get_settings()})


@route("POST", r"/api/admin/settings")
@need_auth
def api_admin_set_settings(req: Request):
    d = req.json()
    kv = {}
    if "month_limit" in d:
        try:
            v = max(0, int(d["month_limit"]))
        except Exception:
            return err("限额必须是数字")
        kv["month_limit"] = v
    if "sale_ended" in d:
        new_val = "1" if str(d["sale_ended"]).lower() in ("1", "true", "yes") else ""
        was_ended = (store.get_settings().get("sale_ended") == "1")
        kv["sale_ended"] = new_val
        # 由「已结束」切回「进行中」= 开启新一期特卖：记录开始时间，本次领取计数从此刻起算
        if was_ended and new_val == "":
            kv["sale_started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not kv:
        return err("没有可更新的设置")
    store.set_settings(kv)
    if "sale_ended" in kv:
        _audit("修改设置", "特卖活动开关 = %s" % ("已结束" if kv["sale_ended"] == "1" else "进行中"), _ip(req))
    if "month_limit" in kv:
        _audit("修改设置", "购买限额 = %s 件/人/月" % kv["month_limit"], _ip(req))
    return ok({"settings": store.get_settings()})


@route("GET", r"/api/admin/export")
@need_auth
def api_admin_export(req: Request):
    from .xlsx import build_xlsx
    st_map = {"pending": "待发放", "done": "已发放", "cancel": "已取消"}

    prods = store.list_products(status=None)
    p_rows = []
    for p in prods:
        dl = p["days_left"]
        p_rows.append([
            p["id"], p["name"], p["spec"],
            (p["price"], "num"), (p["stock"], "num"), (round(p["price"] * p["stock"], 2), "num"),
            p["production_date"] or "—", p["expiry_date"] or "长期",
            ("已过期 %d 天" % -dl) if (dl is not None and dl < 0)
            else (("剩 %d 天" % dl) if (dl is not None and dl <= 90) else "正常"),
            "上架" if p["status"] else "下架",
            p["created_at"],
        ])

    orders = store.list_orders()
    o_rows = []
    for o in orders:
        for it in o["items"]:
            o_rows.append([
                o["order_no"], o["created_at"], o["buyer_name"],
                o["buyer_dept"], o["buyer_phone"],
                it["name"], it["spec"] or "—",
                (it["price"], "num"), (it["qty"], "num"),
                (round(it["price"] * it["qty"], 2), "num"),
                st_map.get(o["status"], o["status"]), o["note"] or "",
                o.get("picked_at") or "未领",
                o["client_host"] or "", o["client_ip"] or "",
            ])

    data = build_xlsx([
        ("库存台账",
         ["ID", "礼品名称", "规格", "单价(元)", "库存", "货值(元)",
          "生产日期", "有效期至", "有效期状态", "上下架", "录入时间"],
         p_rows, [6, 26, 20, 10, 8, 12, 12, 12, 14, 8, 20]),
        ("购买记录",
         ["单号", "提交时间", "购买人", "部门", "联系电话",
          "礼品名称", "规格", "单价(元)", "数量", "小计(元)", "订单状态", "备注",
          "实物领取", "计算机名", "来源IP"],
         o_rows, [22, 20, 10, 12, 14, 26, 18, 10, 8, 12, 10, 20, 20, 18, 16]),
    ])
    fname = "gift-ledger-%s.xlsx" % datetime.now().strftime("%Y%m%d-%H%M%S")
    return 200, [
        ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("Content-Disposition", "attachment; filename=%s" % fname),
    ], data


# ================================================================ 后台：Excel 批量导入
IMPORT_HEADERS = ["礼品名称*", "规格", "单价(元)*", "原价(元)", "库存*",
                  "生产日期(YYYY-MM-DD)", "有效期至(YYYY-MM-DD)", "描述", "上架(是/否)"]

IMPORT_COLS = [
    ("name", ["礼品名称", "商品名称", "名称", "品名"]),
    ("spec", ["规格", "型号"]),
    ("price", ["单价", "特卖价", "价格"]),
    ("original_price", ["原价", "市场价", "参考价"]),
    ("stock", ["库存", "数量"]),
    ("production_date", ["生产日期"]),
    ("expiry_date", ["有效期至", "有效期", "到期"]),
    ("description", ["描述", "说明", "备注"]),
    ("status", ["上架", "是否上架"]),
]


def _norm_header(h):
    return re.sub(r"[\s\*（）()：:／/]", "", str(h or "")).lower()


def _pick_col(headers, aliases):
    for i, h in enumerate(headers):
        hn = _norm_header(h)
        if not hn:
            continue
        for a in aliases:
            if hn.startswith(_norm_header(a)):
                return i
    return -1


def _parse_date(s):
    """把 2026-07-01 / 2026/7/1 / 2026年7月1日 / 20260701 / Excel 序列号 统一成 YYYY-MM-DD。"""
    s = str(s or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        from .xlsxread import excel_serial_to_date
        try:
            return excel_serial_to_date(int(float(s))).strftime("%Y-%m-%d")
        except Exception:
            return ""
    m = re.match(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    if re.fullmatch(r"\d{8}", s):
        try:
            return datetime(int(s[:4]), int(s[4:6]), int(s[6:])).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""


def _num(s, default=0.0):
    """空 → default；有数字 → float；有内容但不是数字 → None（用于提示用户改表）。"""
    s = str(s or "").replace(",", "").replace("¥", "").replace("￥", "").strip()
    if not s:
        return default
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


@route("GET", r"/api/admin/import-template")
@need_auth
def api_import_template(req: Request):
    from .xlsx import build_xlsx
    demo1 = ["保温杯 316不锈钢", "480ml / 商务灰", (69.0, "num"), (99.0, "num"),
             (50, "num"), "2026-07-01", "2028-07-01", "316 食品级内胆，24 小时保温", "是"]
    demo2 = ["抽纸（3层）", "100 抽 × 6 包", (19.9, "num"), (29.9, "num"),
             (120, "num"), "2026-09-01", "2029-09-01", "", "是"]
    tips = [
        ["礼品名称*", "必填。前台卡片上显示的名字"],
        ["规格", "如 480ml / 商务灰，可留空"],
        ["单价(元)*", "必填，本次特卖价，填数字，别带货币符号"],
        ["原价(元)", "选填，前台展示为划线价；填 0 或不填则不显示"],
        ["库存*", "必填，整数"],
        ["生产日期", "选填，支持 2026-07-01、2026/7/1、2026年7月1日"],
        ["有效期至", "选填，同上格式；填了才会参与效期预警与过期自动下架"],
        ["描述", "选填，详情页的介绍文字"],
        ["上架(是/否)", "填「是」或留空=直接上架；填「否」=先不上架"],
        ["商品图片", "模板里没有图片列：导入后在后台「编辑」里逐条添加（最多 3 张）"],
        ["注意事项", "第一行表头请勿删除或改名；一行一个礼品；单次建议不超过 500 行"],
    ]
    data = build_xlsx([
        ("礼品导入模板", IMPORT_HEADERS, [demo1, demo2],
         [24, 20, 10, 10, 8, 22, 22, 36, 12]),
        ("填写说明", ["列名", "填写要求"], tips, [22, 72]),
    ])
    return 200, [
        ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("Content-Disposition", "attachment; filename=gift-import-template.xlsx"),
    ], data


@route("POST", r"/api/admin/import")
@need_auth
def api_import(req: Request):
    from .xlsxread import read_sheet
    fields, files = req.form()
    if not files:
        return err("没有收到文件")
    f = files[0]
    if not f["filename"].lower().endswith((".xlsx", ".xlsm")):
        return err("请上传 .xlsx 格式的文件（.xls 请先另存为 .xlsx）")
    if len(f["data"]) > 8 * 1024 * 1024:
        return err("文件太大（超过 8MB）")
    try:
        rows = read_sheet(f["data"], 0)
    except Exception as e:
        return err("解析失败：%s。请先下载模板，按模板格式填写后再导入" % e)
    if not rows:
        return err("表格是空的")

    # 表头可能不在第一行（用户常在上面加标题），取前 5 行里命中列名最多的一行
    best_hit, head_i = -1, 0
    for i, r in enumerate(rows[:5]):
        hit = sum(1 for _, aliases in IMPORT_COLS if _pick_col(r, aliases) >= 0)
        if hit > best_hit:
            best_hit, head_i = hit, i
    if best_hit < 2:
        return err("没找到表头。请用系统模板，第一行是列名（礼品名称、单价、库存…）")

    headers = rows[head_i]
    idx = {k: _pick_col(headers, a) for k, a in IMPORT_COLS}
    if idx["name"] < 0:
        return err("缺少「礼品名称」列")

    added, errors, total = 0, [], 0
    with store.connect() as conn:
        for n, r in enumerate(rows[head_i + 1:], start=head_i + 2):
            def cell(key):
                i = idx.get(key, -1)
                return r[i].strip() if 0 <= i < len(r) else ""

            name = cell("name")
            if not name:
                if any(cell(k) for k in ("price", "stock", "spec")):
                    errors.append("第 %d 行：缺礼品名称，已跳过" % n)
                continue
            total += 1
            price_v = _num(cell("price"), 0.0)
            op_v = _num(cell("original_price"), 0.0)
            stock_v = _num(cell("stock"), 0.0)
            if price_v is None or op_v is None or stock_v is None:
                bad_cols = [n2 for n2, v in (("单价", price_v), ("原价", op_v), ("库存", stock_v)) if v is None]
                errors.append("第 %d 行：%s 不是数字，已跳过" % (n, "、".join(bad_cols)))
                continue
            price, oprice, stock = price_v, max(0.0, op_v), int(stock_v)
            if price < 0 or stock < 0:
                errors.append("第 %d 行：单价或库存为负数，已跳过" % n)
                continue
            pdate = _parse_date(cell("production_date"))
            edate = _parse_date(cell("expiry_date"))
            if cell("production_date") and not pdate:
                errors.append("第 %d 行：生产日期格式看不懂，已按空处理" % n)
            if cell("expiry_date") and not edate:
                errors.append("第 %d 行：有效期格式看不懂，已按空处理" % n)
            flag = cell("status")
            status = 0 if flag in ("否", "N", "n", "0", "不上架") else 1
            conn.execute(
                """INSERT INTO products(name,spec,price,original_price,stock,
                   production_date,expiry_date,image,images,description,status,sort_no,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, cell("spec"), price, oprice, stock,
                 pdate, edate, "", "[]", cell("description"), status, 0, store.now()))
            added += 1
        conn.commit()

    _audit("批量导入", "新增 %d 件礼品（共 %d 行有名称）" % (added, total), _ip(req))
    return ok({"added": added, "total": total, "errors": errors[:50],
               "error_count": len(errors)})


# ================================================================ 健康检查
@route("GET", r"/api/ping")
def api_ping(req: Request):
    from . import __version__
    return ok({"msg": "pong", "time": store.now(), "version": __version__})

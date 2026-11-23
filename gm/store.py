# -*- coding: utf-8 -*-
"""数据层：SQLite 建表 / 初始化示例数据 / 业务读写。纯标准库实现。"""
import glob
import json
import os
import re
import sys
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta

APP_NAME = "礼品库商城"


# ---------------------------------------------------------------- 路径处理
def base_dir() -> str:
    """程序根目录。打包成 exe 后取 exe 所在目录，否则取项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    d = os.path.join(base_dir(), "data")
    os.makedirs(os.path.join(d, "uploads"), exist_ok=True)
    return d


def web_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "web")
    return os.path.join(base_dir(), "web")


DB_PATH = os.path.join(data_dir(), "gift.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def q(sql, args=(), one=False):
    with connect() as conn:
        cur = conn.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return (rows[0] if rows else None) if one else rows


# ---------------------------------------------------------------- 建表
SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    category        TEXT    NOT NULL DEFAULT '其他',
    spec            TEXT    NOT NULL DEFAULT '',
    price           REAL    NOT NULL DEFAULT 0,
    original_price  REAL    NOT NULL DEFAULT 0,
    stock           INTEGER NOT NULL DEFAULT 0,
    production_date TEXT    NOT NULL DEFAULT '',
    expiry_date     TEXT    NOT NULL DEFAULT '',
    image           TEXT    NOT NULL DEFAULT '',
    images          TEXT    NOT NULL DEFAULT '',
    description     TEXT    NOT NULL DEFAULT '',
    status          INTEGER NOT NULL DEFAULT 1,
    sort_no         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no    TEXT    NOT NULL UNIQUE,
    buyer_name  TEXT    NOT NULL DEFAULT '',
    buyer_dept  TEXT    NOT NULL DEFAULT '',
    buyer_phone TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    total       REAL    NOT NULL DEFAULT 0,
    qty         INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'pending',
    picked_at   TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT '',
    client_ip   TEXT    NOT NULL DEFAULT '',
    client_host TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    name       TEXT    NOT NULL DEFAULT '',
    spec       TEXT    NOT NULL DEFAULT '',
    price      REAL    NOT NULL DEFAULT 0,
    qty        INTEGER NOT NULL DEFAULT 0,
    image      TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL DEFAULT '',
    ip     TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 设置
DEFAULT_SETTINGS = {"month_limit": "0"}   # 每人每月领取件数上限，0 = 不限


def get_settings() -> dict:
    rows = q("SELECT k,v FROM settings")
    d = dict(DEFAULT_SETTINGS)
    d.update({r["k"]: r["v"] for r in rows if not r["k"].startswith("_")})
    return d


def set_settings(kv: dict):
    with connect() as conn:
        for k, v in kv.items():
            conn.execute("INSERT INTO settings(k,v) VALUES(?,?) "
                         "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))
        conn.commit()


def today() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------- 示例图片
PALETTE = [
    ((238, 196, 158), (198, 107, 61)),   # 焦糖
    ((186, 214, 199), (74, 124, 104)),   # 松绿
    ((206, 208, 226), (94, 100, 148)),   # 雾紫
    ((240, 205, 205), (168, 88, 88)),    # 陶红
    ((222, 214, 190), (140, 122, 78)),   # 卡其
    ((199, 219, 232), (68, 116, 150)),   # 湖蓝
]


def make_seed_image(path: str, label: str, idx: int):
    """生成一张柔和的渐变占位图（有 Pillow 就画，没有就退化成 1x1 透明 PNG）。"""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except Exception:
        # 退化成纯色块 GIF 头，保证页面不裂
        with open(path, "wb") as f:
            f.write(bytes.fromhex(
                "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea735d1e300"
                "00000049454e44ae426082"))
        return

    W, H = 720, 540
    c1, c2 = PALETTE[idx % len(PALETTE)]
    img = Image.new("RGB", (W, H), c1)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))

    # 柔光：两个高斯模糊的亮斑叠加，做出高级的雾面质感
    from PIL import ImageChops
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.52, -H * 0.42, W * 1.18, H * 0.62], fill=95)
    gd.ellipse([-W * 0.25, H * 0.48, W * 0.40, H * 1.15], fill=55)
    glow = glow.filter(ImageFilter.GaussianBlur(85))
    img = ImageChops.add(img, Image.merge("RGB", (glow, glow, glow)))
    img = Image.blend(img, Image.new("RGB", (W, H), (255, 255, 255)), 0.05)

    d = ImageDraw.Draw(img)
    # 大字水印
    font = None
    for fp in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
               "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"):
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 210)
                break
            except Exception:
                pass
    ch = label[:1] if label else "礼"
    if font:
        bbox = d.textbbox((0, 0), ch, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((W - tw) / 2 - bbox[0], (H - th) / 2 - bbox[1] - 18), ch,
               font=font, fill=(255, 255, 255))
    d.rectangle([26, 26, W - 26, H - 26], outline=(255, 255, 255), width=2)
    img.save(path, "PNG", optimize=True)


# ---------------------------------------------------------------- 初始数据
SEED = [
    # name, category, spec, price, stock, 生产日期偏移(天前), 有效天数, 描述
    ("经典保温杯 316不锈钢", "生活日用", "480ml / 商务灰", 89.0, 42, 120, 1825,
     "316 食品级不锈钢内胆，24 小时保温，附赠杯刷与礼盒包装。"),
    ("定制商务礼盒套装", "定制礼盒", "笔记本+签字笔+U盘", 168.0, 18, 200, 730,
     "可烫印公司 LOGO，含 A5 皮面笔记本、金属签字笔、32G 优盘。"),
    ("明前龙井茶叶礼盒", "食品茶饮", "250g / 双罐装", 258.0, 26, 95, 540,
     "明前特级龙井，陶瓷双罐配手提礼袋，适合商务往来。"),
    ("便携蓝牙音箱", "数码家电", "5W / 蓝牙5.3", 129.0, 12, 300, 1095,
     "IPX6 防水，续航 12 小时，支持 TWS 双机互联。"),
    ("自动长柄雨伞", "生活日用", "10 骨 / 双层伞面", 69.0, 60, 400, 1825,
     "玻纤伞骨抗风，一键自动开合，可定制伞面印花。"),
    ("A5 皮面笔记本", "办公文具", "160 页 / 道林纸", 38.0, 150, 260, 1095,
     "软皮封面，80g 道林纸不透墨，可丝印企业标识。"),
    ("陶瓷马克杯套装", "生活日用", "350ml × 2 只", 79.0, 8, 420, 900,
     "骨瓷手感，配木质杯盖与勺，礼盒装。"),
    ("坚果零食大礼包", "食品茶饮", "1.5kg / 8 袋装", 119.0, 34, 210, 180,
     "每日坚果混合装，独立小包，年节福利首选。"),
    ("移动电源 20000mAh", "数码家电", "双向快充 / 22.5W", 149.0, 0, 330, 1095,
     "支持 PD+QC 双向快充，数显电量，可上飞机。"),
    ("中秋月饼礼盒", "食品茶饮", "8 枚 / 广式+苏式", 198.0, 6, 400, 90,
     "经典双拼口味，铁盒包装。注意保质期较短，优先发放。"),
    ("纯棉毛巾浴巾套装", "生活日用", "3 件套 / 长绒棉", 59.0, 75, 180, 1095,
     "32 支长绒棉，吸水柔软，独立包装。"),
    ("无线鼠标 静音版", "数码家电", "2.4G / 静音微动", 49.0, 23, 150, 1095,
     "静音按键，人体工学握感，USB 接收器收纳于底部。"),
]


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
        # 老库补列：订单来源（IP / 计算机名）、商品多图，已存在则跳过
        for col in ("client_ip", "client_host", "picked_at"):
            try:
                conn.execute("ALTER TABLE orders ADD COLUMN %s TEXT NOT NULL DEFAULT ''" % col)
            except Exception:
                pass
        try:
            conn.execute("ALTER TABLE products ADD COLUMN images TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE products ADD COLUMN original_price REAL NOT NULL DEFAULT 0")
        except Exception:
            pass
        conn.commit()
        row = conn.execute("SELECT COUNT(*) c FROM products").fetchone()
        if row["c"] == 0:
            _seed_products(conn)
        # 默认管理员口令
        if not conn.execute("SELECT v FROM settings WHERE k='admin_pwd'").fetchone():
            conn.execute("INSERT INTO settings(k,v) VALUES(?,?)",
                         ("admin_pwd", hash_pwd("admin888")))
            conn.commit()


def _seed_products(conn):
    base = today()
    for i, item in enumerate(SEED):
        name, cat, spec, price, stock, pd_days, valid_days, desc = item
        pdate = base - timedelta(days=pd_days)
        edate = pdate + timedelta(days=valid_days)
        fname = "seed_%02d.png" % i
        fpath = os.path.join(data_dir(), "uploads", fname)
        if not os.path.exists(fpath):
            make_seed_image(fpath, name, i)
        conn.execute(
            """INSERT INTO products(name,category,spec,price,stock,production_date,
               expiry_date,image,description,status,sort_no,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,1,?,?)""",
            (name, cat, spec, price, stock, pdate.strftime("%Y-%m-%d"),
             edate.strftime("%Y-%m-%d"), "/uploads/" + fname, desc, i, now()))
    conn.commit()


# ---------------------------------------------------------------- 口令
def hash_pwd(pwd: str, salt: str = "") -> str:
    if not salt:
        salt = secrets.token_hex(8)
    h = hashlib.sha256((salt + pwd).encode("utf-8")).hexdigest()
    return salt + "$" + h


def check_pwd(pwd: str) -> bool:
    row = q("SELECT v FROM settings WHERE k='admin_pwd'", one=True)
    if not row:
        return False
    stored = row["v"]
    if "$" not in stored:
        return False
    salt = stored.split("$", 1)[0]
    return hash_pwd(pwd, salt) == stored


def set_pwd(pwd: str):
    with connect() as conn:
        conn.execute("INSERT INTO settings(k,v) VALUES('admin_pwd',?) "
                     "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (hash_pwd(pwd),))
        conn.commit()


# ---------------------------------------------------------------- 查询
def _fill_images(r):
    """把 images JSON 解析成数组；兼容只有 image 单图的老数据。"""
    try:
        imgs = json.loads(r["images"]) if r["images"] else []
    except Exception:
        imgs = []
    imgs = [u for u in imgs if u]
    if not imgs and r["image"]:
        imgs = [r["image"]]
    if imgs and not r["image"]:
        r["image"] = imgs[0]
    r["images"] = imgs
    return r


def list_products(q_text="", category="", status=None, sort="new"):
    sql = "SELECT * FROM products WHERE 1=1"
    args = []
    if q_text:
        sql += " AND (name LIKE ? OR description LIKE ? OR spec LIKE ?)"
        like = "%" + q_text + "%"
        args += [like, like, like]
    if category:
        sql += " AND category=?"
        args.append(category)
    if status is not None:
        sql += " AND status=?"
        args.append(status)
    if sort == "price_asc":
        sql += " ORDER BY price ASC"
    elif sort == "price_desc":
        sql += " ORDER BY price DESC"
    elif sort == "stock_desc":
        sql += " ORDER BY stock DESC"
    else:
        sql += " ORDER BY sort_no ASC, id DESC"
    rows = q(sql, args)
    for r in rows:
        _fill_images(r)
        r["days_left"] = days_left(r["expiry_date"])
        r["expired"] = r["days_left"] is not None and r["days_left"] < 0
        r["expiring"] = r["days_left"] is not None and 0 <= r["days_left"] <= 90
        # 录入 7 天内视为「新品」
        try:
            age = (datetime.now() - datetime.strptime(r["created_at"][:10], "%Y-%m-%d")).days
        except ValueError:
            age = 9999
        r["is_new"] = 0 <= age <= 7
    return rows


def get_product(pid: int):
    r = q("SELECT * FROM products WHERE id=?", (pid,), one=True)
    if r:
        _fill_images(r)
        r["days_left"] = days_left(r["expiry_date"])
        r["expired"] = r["days_left"] is not None and r["days_left"] < 0
        r["expiring"] = r["days_left"] is not None and 0 <= r["days_left"] <= 90
    return r


def days_left(expiry: str):
    if not expiry:
        return None
    try:
        d = datetime.strptime(expiry, "%Y-%m-%d")
    except Exception:
        return None
    return (d.date() - datetime.now().date()).days


def categories(exclude_expired=False):
    """返回上架商品的分类计数；exclude_expired=True 时排除已过有效期的商品。"""
    rows = q("SELECT * FROM products WHERE status=1")
    if exclude_expired:
        rows = [r for r in rows
                if not (r["expiry_date"] and (days_left(r["expiry_date"]) or 0) < 0)]
    out = {}
    for r in rows:
        out[r["category"]] = out.get(r["category"], 0) + 1
    return [{"category": k, "c": v}
            for k, v in sorted(out.items(), key=lambda kv: -kv[1])]


def stats():
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
        stock = conn.execute("SELECT IFNULL(SUM(stock),0) s FROM products").fetchone()["s"]
        value = conn.execute("SELECT IFNULL(SUM(stock*price),0) v FROM products").fetchone()["v"]
        today_orders = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE substr(created_at,1,10)=?",
            (datetime.now().strftime("%Y-%m-%d"),)).fetchone()["c"]
        month_orders = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE substr(created_at,1,7)=?",
            (datetime.now().strftime("%Y-%m"),)).fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE status='pending' AND picked_at=''").fetchone()["c"]
        picked = conn.execute("SELECT COUNT(*) c FROM orders WHERE picked_at<>''").fetchone()["c"]
    rows = q("SELECT expiry_date FROM products WHERE expiry_date<>''")
    expiring = sum(1 for r in rows if (days_left(r["expiry_date"]) or 0) <= 90)
    expired = sum(1 for r in rows if (days_left(r["expiry_date"]) or 0) < 0)
    # 本次已售出：自本次特卖活动开启以来的累计销售件数（同一单买 2 件算 2 件，排除已取消）
    started_at = get_settings().get("sale_started_at") or ""
    if started_at:
        with connect() as conn:
            period_orders = conn.execute(
                "SELECT COUNT(*) c FROM orders WHERE created_at >= ? AND status<>'cancel'",
                (started_at,)).fetchone()["c"]
            period_qty = conn.execute(
                "SELECT IFNULL(SUM(i.qty),0) q FROM order_items i JOIN orders o ON o.id=i.order_id "
                "WHERE o.created_at >= ? AND o.status<>'cancel'", (started_at,)).fetchone()["q"]
    else:
        # 没有记录活动开始时间（旧数据），回退为本月数据
        period_orders = month_orders
        with connect() as conn:
            period_qty = conn.execute(
                "SELECT IFNULL(SUM(i.qty),0) q FROM order_items i JOIN orders o ON o.id=i.order_id "
                "WHERE substr(o.created_at,1,7)=? AND o.status<>'cancel'",
                (datetime.now().strftime("%Y-%m"),)).fetchone()["q"]
    return {"total": total, "stock": stock, "value": round(value, 2),
            "today_orders": today_orders, "month_orders": month_orders,
            "period_orders": period_orders, "period_qty": int(period_qty or 0),
            "pending": pending, "picked": picked,
            "expiring": expiring, "expired": expired}


# ---------------------------------------------------------------- 下单
def create_order(buyer_name, buyer_dept, buyer_phone, note, items,
                 client_ip="", client_host=""):
    """items: [{id, qty}]。返回 (ok, payload)。库存用条件更新保证不超卖。

    client_ip / client_host：下单来源（局域网 IP 与反查到的计算机名），便于追溯。
    """
    if not items:
        return False, "购物清单为空"
    if not buyer_name.strip():
        return False, "请填写购买人姓名"
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        total, qty_all, lines = 0.0, 0, []
        for it in items:
            pid = int(it.get("id") or 0)
            n = int(it.get("qty") or 0)
            if n <= 0:
                continue
            p = conn.execute("SELECT * FROM products WHERE id=? AND status=1", (pid,)).fetchone()
            if not p:
                conn.rollback()
                return False, "商品已下架"
            dl = days_left(p["expiry_date"])
            if dl is not None and dl < 0:
                conn.rollback()
                return False, "「%s」已过有效期，无法购买" % p["name"]
            cur = conn.execute(
                "UPDATE products SET stock=stock-? WHERE id=? AND stock>=?", (n, pid, n))
            if cur.rowcount == 0:
                conn.rollback()
                return False, "「%s」库存不足，仅剩 %d 件" % (p["name"], p["stock"])
            total += p["price"] * n
            qty_all += n
            lines.append((pid, p["name"], p["spec"], p["price"], n, p["image"]))

        # 每人每月领取限额校验（取消的订单不计入）
        limit = int(get_settings().get("month_limit") or 0)
        if limit > 0 and buyer_name.strip():
            used = conn.execute(
                """SELECT IFNULL(SUM(qty),0) s FROM orders
                   WHERE status<>'cancel' AND buyer_name=?
                     AND substr(created_at,1,7)=?""",
                (buyer_name.strip(), datetime.now().strftime("%Y-%m"))).fetchone()["s"]
            if used + qty_all > limit:
                conn.rollback()
                remain = max(0, limit - used)
                return False, ("超出购买限额：您本月已购 %d 件，限额 %d 件，"
                               "本次最多还可买 %d 件" % (used, limit, remain))

        order_no = "GM" + datetime.now().strftime("%Y%m%d%H%M%S") + str(secrets.randbelow(900) + 100)
        cur = conn.execute(
            """INSERT INTO orders(order_no,buyer_name,buyer_dept,buyer_phone,note,total,qty,status,created_at,client_ip,client_host)
               VALUES(?,?,?,?,?,?,?,'pending',?,?,?)""",
            (order_no, buyer_name.strip(), buyer_dept.strip(), buyer_phone.strip(),
             note.strip(), round(total, 2), qty_all, now(),
             (client_ip or "").strip(), (client_host or "").strip()))
        oid = cur.lastrowid
        conn.executemany(
            "INSERT INTO order_items(order_id,product_id,name,spec,price,qty,image) VALUES(?,?,?,?,?,?,?)",
            [(oid,) + l for l in lines])
        conn.commit()
    return True, {"order_no": order_no, "total": round(total, 2), "qty": qty_all}


# ---------------------------------------------------------------- 操作日志
AUDIT_KEEP = 2000  # 日志最多保留条数


def log_action(action, detail="", ip=""):
    """记录一条后台操作日志，超出 AUDIT_KEEP 自动修剪。失败不影响主流程。"""
    try:
        with connect() as conn:
            conn.execute("INSERT INTO audit_log(ts,ip,action,detail) VALUES(?,?,?,?)",
                         (now(), str(ip or "")[:45], action, str(detail)[:500]))
            conn.execute(
                "DELETE FROM audit_log WHERE id < ("
                "  SELECT IFNULL(MIN(id),0) FROM ("
                "    SELECT id FROM audit_log ORDER BY id DESC LIMIT ?))",
                (AUDIT_KEEP,))
            conn.commit()
    except Exception:
        pass


def list_logs(limit=200):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, ts, ip, action, detail FROM audit_log "
            "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- 备份
BACKUP_KEEP = 7  # 自动备份保留份数


def build_backup() -> bytes:
    """完整备份 zip：gift.db（一致性快照）+ uploads 图片目录。"""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        tmp = DB_PATH + ".bak"
        src = sqlite3.connect(DB_PATH, timeout=15)
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        z.write(tmp, "gift.db")
        os.remove(tmp)
        updir = os.path.join(data_dir(), "uploads")
        if os.path.isdir(updir):
            for fn in sorted(os.listdir(updir)):
                fp = os.path.join(updir, fn)
                if os.path.isfile(fp):
                    z.write(fp, "uploads/" + fn)
    return buf.getvalue()


def write_backup(dest_dir=None):
    """写一份带时间戳的备份到 data/backups/，自动轮换只留最近 BACKUP_KEEP 份。
    当天已有备份则跳过（供每小时兜底调用的自动备份用）。返回备份路径或 None。"""
    dest_dir = dest_dir or os.path.join(data_dir(), "backups")
    os.makedirs(dest_dir, exist_ok=True)
    today = "gift-%s" % datetime.now().strftime("%Y%m%d")
    if any(f.startswith(today) for f in os.listdir(dest_dir)):
        return None
    path = os.path.join(dest_dir, today + "-"
                        + datetime.now().strftime("%H%M") + ".zip")
    with open(path, "wb") as f:
        f.write(build_backup())
    olds = sorted(glob.glob(os.path.join(dest_dir, "gift-*.zip")))
    for old in olds[:-BACKUP_KEEP]:
        try:
            os.remove(old)
        except OSError:
            pass
    return path


def chart_data():
    """概览统计图表数据：近 14 天发放趋势、近 30 天热门礼品与部门分布（不含已取消订单）。"""
    from datetime import timedelta
    d14 = (datetime.now() - timedelta(days=13)).strftime("%Y-%m-%d")
    d30 = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
    with connect() as conn:
        trend = conn.execute(
            "SELECT substr(created_at,1,10) d, COUNT(*) cnt, IFNULL(SUM(qty),0) qty "
            "FROM orders WHERE status<>'cancelled' AND substr(created_at,1,10)>=? "
            "GROUP BY d ORDER BY d", (d14,)).fetchall()
        top = conn.execute(
            "SELECT oi.name n, oi.image img, IFNULL(SUM(oi.qty),0) qty, COUNT(DISTINCT o.id) cnt "
            "FROM order_items oi JOIN orders o ON o.id=oi.order_id "
            "WHERE o.status<>'cancelled' AND substr(o.created_at,1,10)>=? "
            "GROUP BY oi.name ORDER BY qty DESC LIMIT 8", (d30,)).fetchall()
        depts = conn.execute(
            "SELECT buyer_dept dept, COUNT(*) cnt, IFNULL(SUM(qty),0) qty "
            "FROM orders WHERE status<>'cancelled' AND substr(created_at,1,10)>=? "
            "AND buyer_dept<>'' GROUP BY buyer_dept ORDER BY qty DESC LIMIT 8",
            (d30,)).fetchall()
    return {"trend": [dict(r) for r in trend],
            "top": [dict(r) for r in top],
            "depts": [dict(r) for r in depts]}


def list_orders(status=""):
    sql = """SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id=o.id) kinds
             FROM orders o"""
    args = []
    if status:
        sql += " WHERE o.status=?"
        args.append(status)
    sql += " ORDER BY o.id DESC LIMIT 300"
    rows = q(sql, args)
    if rows:
        ids = [r["id"] for r in rows]
        ph = ",".join("?" * len(ids))
        items = q("SELECT * FROM order_items WHERE order_id IN (%s)" % ph, ids)
        by = {}
        for it in items:
            by.setdefault(it["order_id"], []).append(it)
        for r in rows:
            r["items"] = by.get(r["id"], [])
    return rows


def get_order(oid):
    rows = q("SELECT * FROM orders WHERE id=?", (oid,))
    return rows[0] if rows else None


def update_order_status(oid, status):
    with connect() as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))


def set_order_picked(oid, picked=True):
    """标记「实物已领」＝流程终点：同时把订单置为已发放；撤销只清领取时间。"""
    with connect() as conn:
        if picked:
            conn.execute("UPDATE orders SET picked_at=?, status='done' WHERE id=?",
                         (now(), oid))
        else:
            conn.execute("UPDATE orders SET picked_at='' WHERE id=?", (oid,))
        conn.commit()
    return True


def query_orders(keyword: str):
    """员工自助查单：按单号 / 姓名 / 手机号模糊匹配，返回最近的记录。"""
    kw = "%" + keyword.strip() + "%"
    rows = q(
        """SELECT * FROM orders
           WHERE order_no LIKE ? OR buyer_name LIKE ? OR buyer_phone LIKE ?
           ORDER BY id DESC LIMIT 20""", (kw, kw, kw))
    if rows:
        ids = [r["id"] for r in rows]
        ph = ",".join("?" * len(ids))
        items = q("SELECT * FROM order_items WHERE order_id IN (%s)" % ph, ids)
        by = {}
        for it in items:
            by.setdefault(it["order_id"], []).append(it)
        for r in rows:
            r["items"] = by.get(r["id"], [])
    return rows


# ---------------------------------------------------------------- 上传图片回收
_IMG_NAME_RE = re.compile(r"^p_[0-9a-zA-Z_]+\.(jpg|jpeg|png|gif|webp|bmp)$", re.I)


def uploads_dir() -> str:
    return os.path.join(data_dir(), "uploads")


def _json_image_names(images_json) -> set:
    try:
        arr = json.loads(images_json) if images_json else []
    except Exception:
        arr = []
    out = set()
    for v in arr:
        if v:
            out.add(os.path.basename(str(v)))
    return out


def product_image_files(rows) -> set:
    """从 products 行里取出全部图片文件名（封面 + 多图）。"""
    out = set()
    for r in rows:
        if r["image"]:
            out.add(os.path.basename(r["image"]))
        out |= _json_image_names(r["images"])
    return out


def cleanup_uploads(detached):
    """删除不再被任何商品或历史订单引用的上传图片，返回删除数量。

    detached: 刚刚与商品解绑的图片 URL/文件名列表。安全约束：
    1. 只处理符合上传命名规则（p_*.jpg 等）的文件名；
    2. 仍被 order_items.image（历史订单快照）或其他商品引用的一律保留；
    3. 只删 uploads 目录内的文件。
    """
    up = os.path.abspath(uploads_dir())
    names = []
    for u in detached or []:
        if not u:
            continue
        n = os.path.basename(str(u))
        if _IMG_NAME_RE.match(n) and n not in names:
            names.append(n)
    if not names:
        return 0
    keep = set()
    with connect() as conn:
        for (img,) in conn.execute("SELECT image FROM order_items WHERE image<>''"):
            keep.add(os.path.basename(img))
        keep |= product_image_files(conn.execute("SELECT image, images FROM products").fetchall())
    removed = 0
    for n in names:
        if n in keep:
            continue
        fp = os.path.join(up, n)
        if os.path.abspath(fp).startswith(up + os.sep) and os.path.isfile(fp):
            try:
                os.remove(fp)
                removed += 1
            except OSError:
                pass
    return removed

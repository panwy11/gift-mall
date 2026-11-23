# -*- coding: utf-8 -*-
"""
礼品库特卖管理系统 - 测试数据清理工具
用法：双击 清理测试数据.bat（或直接运行本文件）打开界面；
     命令行 `python cleanup-data.py --auto` 为无人值守模式（按默认勾选项执行）。

清理内容（默认全选）：
  1. 订单 + 订单明细（测试下单记录）
  2. 操作日志（audit_log）
  3. 未被任何商品引用的上传图片（孤儿图）
  4. 复位"本期开始时间"（右上角"已售出"从零重新统计）

始终执行：
  - 清理前自动备份到 data/backups/（含数据库 + 在用图片），可在界面看到备份路径
  - 同步清理 gift-mall/data 和 dist/data 两处数据库（exe 读的是 dist/data）

不会动的：商品、分类、管理口令、月度限额等设置。
"""
import os
import re
import sys
import json
import sqlite3
import zipfile
import datetime
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_RE = re.compile(r"^p_[0-9a-zA-Z_]+\.(jpg|jpeg|png|gif|webp|bmp)$", re.I)


def db_paths():
    """两处数据库：项目根 data/（pythonw 方式使用）与 dist/data/（exe 方式使用）。"""
    out = []
    for rel in (os.path.join("data", "gift.db"), os.path.join("dist", "data", "gift.db")):
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            out.append(p)
    return out


def uploads_dir_for(db_path):
    return os.path.join(os.path.dirname(db_path), "uploads")


def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def db_stats(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    s = {"products": 0, "orders": 0, "order_items": 0, "audit": 0, "uploads": 0}
    if table_exists(c, "products"):
        s["products"] = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if table_exists(c, "orders"):
        s["orders"] = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if table_exists(c, "order_items"):
        s["order_items"] = c.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
    if table_exists(c, "audit_log"):
        s["audit"] = c.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    c.close()
    up = uploads_dir_for(db_path)
    if os.path.isdir(up):
        s["uploads"] = len([f for f in os.listdir(up) if IMG_RE.match(f)])
    return s


def check_lock(db_path):
    """数据库被占用返回 False（服务未停止时 SQLite 写入会失败）。"""
    try:
        c = sqlite3.connect(db_path, timeout=2)
        c.execute("BEGIN IMMEDIATE")
        c.rollback()
        c.close()
        return True
    except sqlite3.OperationalError:
        return False


def make_backup(db_path):
    """备份单个库 + 其 uploads 全部图片，返回 zip 路径。"""
    bk_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(bk_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    zp = os.path.join(bk_dir, "gift-before-clean-%s.zip" % stamp)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db_path, "gift.db")
        up = uploads_dir_for(db_path)
        if os.path.isdir(up):
            for f in os.listdir(up):
                fp = os.path.join(up, f)
                if os.path.isfile(fp):
                    z.write(fp, "uploads/" + f)
    return zp


def referenced_images(conn):
    """所有被商品或历史订单引用的图片文件名。"""
    keep = set()
    if table_exists(conn, "order_items"):
        for (img,) in conn.execute("SELECT image FROM order_items WHERE image<>''"):
            keep.add(os.path.basename(img))
    if table_exists(conn, "products"):
        for img, imgs in conn.execute("SELECT image, images FROM products"):
            if img:
                keep.add(os.path.basename(img))
            try:
                for v in (json.loads(imgs) if imgs else []):
                    if v:
                        keep.add(os.path.basename(str(v)))
            except Exception:
                pass
    return keep


def clean_db(db_path, opts, log):
    """按勾选项清理单个库。返回 (删除图片数,)"""
    c = sqlite3.connect(db_path, timeout=5)
    c.row_factory = sqlite3.Row
    if opts.get("orders") and table_exists(c, "order_items"):
        n = c.execute("DELETE FROM order_items").rowcount
        log("  order_items  清空 %d 行" % n)
    if opts.get("orders") and table_exists(c, "orders"):
        n = c.execute("DELETE FROM orders").rowcount
        log("  orders       清空 %d 行" % n)
    if opts.get("audit") and table_exists(c, "audit_log"):
        n = c.execute("DELETE FROM audit_log").rowcount
        log("  audit_log    清空 %d 行" % n)
    if opts.get("period") and table_exists(c, "settings"):
        try:
            c.execute("UPDATE settings SET v='' WHERE k='sale_started_at'")
            log("  settings     已复位本期开始时间")
        except sqlite3.OperationalError:
            log("  settings     表结构不同，跳过")
    c.commit()
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    removed = 0
    if opts.get("orphans"):
        up = uploads_dir_for(db_path)
        if os.path.isdir(up):
            keep = referenced_images(c)
            for f in os.listdir(up):
                if not IMG_RE.match(f) or f in keep:
                    continue
                fp = os.path.join(up, f)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                        removed += 1
                    except OSError:
                        pass
            log("  uploads      清理无引用图片 %d 张" % removed)
    c.execute("VACUUM")
    c.close()
    return removed


def stop_service():
    """停止 exe 与 pythonw 两种形态的服务进程。"""
    for cmd in (["taskkill", "/IM", "gift-mall.exe", "/F"],
                ["taskkill", "/IM", "pythonw.exe", "/F"]):
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
        except Exception:
            pass


# ---------------------------------------------------------------- CLI
def run_auto(log):
    opts = {"orders": True, "audit": True, "orphans": True, "period": True}
    paths = db_paths()
    if not paths:
        log("未找到数据库（data/gift.db 或 dist/data/gift.db），请把本工具放在 gift-mall 根目录。")
        return 1
    for p in paths:
        if not check_lock(p):
            log("数据库被占用（%s），先停止服务…" % p)
            stop_service()
            import time
            time.sleep(1.5)
            if not check_lock(p):
                log("仍被占用：%s\n请手动关闭服务后重试。" % p)
                return 1
    for p in paths:
        log("备份 %s" % p)
        log("  → " + make_backup(p))
    for p in paths:
        log("清理 %s" % p)
        clean_db(p, opts, log)
    log("")
    for p in paths:
        s = db_stats(p)
        log("%s → 商品 %d，订单 %d，日志 %d" % (p, s["products"], s["orders"], s["audit"]))
    log("\n完成。如服务之前被停止，请双击 启动服务-静默.bat 重新启动。")
    return 0


def main_cli():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None
    return run_auto(print)


# ---------------------------------------------------------------- GUI
def main_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox
    root = tk.Tk()
    root.title("礼品库 - 测试数据清理")
    root.geometry("560x520")
    root.minsize(520, 460)

    frm = ttk.Frame(root, padding=14)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="清理前会自动备份到 data/backups/，可放心操作。",
              foreground="#0d9488").grid(row=0, column=0, columnspan=2, sticky="w")

    stats_box = tk.Text(frm, height=6, width=66, font=("Consolas", 10),
                        background="#f2f8f7", relief="flat")
    stats_box.grid(row=1, column=0, columnspan=2, sticky="we", pady=8)

    def refresh_stats():
        stats_box.delete("1.0", "end")
        paths = db_paths()
        if not paths:
            stats_box.insert("end", "未找到数据库！请把本工具放在 gift-mall 根目录运行。")
            return
        for p in paths:
            s = db_stats(p)
            stats_box.insert("end", "%s\n  商品 %d | 订单 %d | 明细 %d | 操作日志 %d | 上传图片 %d\n"
                             % (os.path.relpath(p, ROOT), s["products"], s["orders"],
                                s["order_items"], s["audit"], s["uploads"]))
    refresh_stats()

    vars_ = {
        "orders": tk.BooleanVar(value=True),
        "audit": tk.BooleanVar(value=True),
        "orphans": tk.BooleanVar(value=True),
        "period": tk.BooleanVar(value=True),
    }
    labels = [
        ("orders", "清空测试订单 + 明细（不动商品）"),
        ("audit", "清空操作日志"),
        ("orphans", "清理未被商品引用的上传图片"),
        ("period", "复位“本期开始时间”（已售出统计归零）"),
    ]
    for i, (k, text) in enumerate(labels):
        ttk.Checkbutton(frm, variable=vars_[k], text=text).grid(
            row=2 + i, column=0, columnspan=2, sticky="w", pady=2)

    out = tk.Text(frm, height=12, width=66, font=("Consolas", 9), state="disabled")
    out.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=10)
    frm.columnconfigure(0, weight=1)
    frm.rowconfigure(6, weight=1)

    def log(msg):
        out.configure(state="normal")
        out.insert("end", str(msg) + "\n")
        out.see("end")
        out.configure(state="disabled")
        root.update_idletasks()

    def do_clean():
        opts = {k: v.get() for k, v in vars_.items()}
        if not any(opts.values()):
            messagebox.showwarning("提示", "请至少勾选一项要清理的内容。")
            return
        if not messagebox.askyesno(
                "确认清理",
                "将清理勾选的数据（两处数据库）。\n\n"
                "清理前会自动备份，但建议先停止服务再操作。\n\n确定继续吗？"):
            return
        paths = db_paths()
        locked = [p for p in paths if not check_lock(p)]
        if locked:
            if messagebox.askyesno("服务运行中",
                                   "检测到服务正在占用数据库：\n%s\n\n是否自动停止服务后继续？"
                                   % "\n".join(locked)):
                stop_service()
                root.after(1500, lambda: _do_clean(paths, opts))
                return
            log("已取消（需先停止服务）。")
            return
        _do_clean(paths, opts)

    def _do_clean(paths, opts):
        try:
            for p in paths:
                log("备份 %s → %s" % (os.path.relpath(p, ROOT), make_backup(p)))
            for p in paths:
                log("清理 %s" % os.path.relpath(p, ROOT))
                clean_db(p, opts, log)
            refresh_stats()
            log("\n✅ 完成。如服务被停止，请双击 启动服务-静默.bat 重新启动。")
            messagebox.showinfo("完成", "清理完成，详情见下方日志。")
        except Exception as e:
            log("出错：%s" % e)
            messagebox.showerror("出错", str(e))

    btns = ttk.Frame(frm)
    btns.grid(row=7, column=0, columnspan=2, sticky="e")
    ttk.Button(btns, text="刷新统计", command=refresh_stats).pack(side="left", padx=4)
    ttk.Button(btns, text="开始清理", command=do_clean).pack(side="left", padx=4)
    root.mainloop()


if __name__ == "__main__":
    if "--auto" in sys.argv:
        sys.exit(main_cli())
    else:
        main_gui()

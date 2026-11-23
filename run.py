# -*- coding: utf-8 -*-
"""礼品库商城 —— 启动入口。

直接运行：  python run.py
指定端口：  python run.py 9100          （单个）
            python run.py 9100,8010     （多个，逗号分隔）

默认同时监听两个端口：
  9100 —— 公司防火墙策略里唯一对「任意程序 / 公用网络 / TCP」放行的端口，
          同事从自己电脑访问必须走这个；
  8010 —— 本机习惯端口，方便本机和自己调试。
"""
import os
import sys
import socket
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pythonw / 无控制台环境（VBS 静默启动、PyInstaller --windowed）下 sys.stdout 为 None，
# 直接 print 会抛 AttributeError 让进程静默退出。这里兜底重定向到 devnull。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r", encoding="utf-8", errors="ignore")

from gm import store, httpd  # noqa: E402
from gm import api  # noqa: E402,F401  注册路由

BANNER = r"""
  ____ _  _ ___ _____   __  __   _   _     _
 / ___| |/ |_ _|  ___| |  \/  | / \ | |   | |
| |  _| ' / | || |_    | |\/| |/ _ \| |   | |
| |_| | . \ | ||  _|   | |  | / ___ \ |___| |___
 \____|_|\_\___|_|     |_|  |_/_/   \_\_____|_____|
"""

DEFAULT_PORTS = "9100,8010"


def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def parse_ports():
    raw = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        raw = sys.argv[1]
    elif os.environ.get("GM_PORTS"):
        raw = os.environ["GM_PORTS"]
    elif os.environ.get("GM_PORT"):
        raw = os.environ["GM_PORT"]
    else:
        raw = DEFAULT_PORTS
    ports = []
    for x in raw.replace(" ", "").split(","):
        try:
            p = int(x)
        except ValueError:
            continue
        if 0 < p < 65536 and p not in ports:
            ports.append(p)
    return ports or [8080]


def auto_backup_loop():
    """每天自动备份一次到 data/backups/（保留最近 7 份）。启动时先做一次当天备份。"""
    import time
    while True:
        try:
            p = store.write_backup()
            if p:
                print("  [自动备份] %s" % p)
        except Exception as e:
            print("  [自动备份失败] %s" % e)
        time.sleep(3600)  # 每小时检查一次，当天已备份则跳过


def main():
    store.init_db()
    threading.Thread(target=auto_backup_loop, daemon=True).start()

    want = parse_ports()
    servers = []
    failed = []
    for p in want:
        if not port_free(p):
            failed.append((p, "端口已被占用"))
            continue
        try:
            srv = httpd.serve(p)
            servers.append((p, srv))
        except OSError as e:
            failed.append((p, str(e)))

    if not servers:
        print("\n[启动失败] 以下端口都不可用：")
        for p, why in failed:
            print("  %d -> %s" % (p, why))
        print("\n请关闭占用这些端口的程序，或改用其他端口：python run.py 8888\n")
        try:
            input("按回车退出…")
        except Exception:
            pass
        return

    ip = httpd.get_lan_ip()

    def url(port):
        return "http://%s" % ip if port == 80 else "http://%s:%d" % (ip, port)

    def local(port):
        return "http://127.0.0.1" if port == 80 else "http://127.0.0.1:%d" % port

    print(BANNER)
    print("  礼品库商城已启动  监听端口: %s" % ", ".join(str(p) for p, _ in servers))
    print("  " + "-" * 60)
    print("  ★ 同事访问（发给别人用这个）")
    for p, _ in servers:
        print("      %-26s %s" % (url(p), "" if p != 9100 else "端口已在防火墙放行"))
    print("  ★ 本机访问")
    for p, _ in servers:
        print("      %-26s" % local(p))
    print("  ★ 管理后台")
    for p, _ in servers:
        print("      %-26s 默认口令 admin888" % (url(p) + "/admin"))
    print("  " + "-" * 60)
    print("  数据目录   %s" % store.data_dir())
    print("  按 Ctrl+C 停止服务\n")
    for p, why in failed:
        print("  [跳过] 端口 %d：%s" % (p, why))

    if "--open" in sys.argv or os.environ.get("GM_OPEN") == "1":
        first = servers[0][0]
        threading.Timer(1.2, lambda: webbrowser.open(local(first))).start()

    # 额外的端口放到后台线程里跑
    for p, srv in servers[1:]:
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    try:
        servers[0][1].serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
        for _, srv in servers:
            try:
                srv.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    main()

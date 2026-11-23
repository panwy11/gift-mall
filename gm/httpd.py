# -*- coding: utf-8 -*-
"""极简 Web 框架：路由 + 静态文件 + JSON API + multipart 上传。
只依赖 Python 标准库，方便内网无网络环境运行与打包。"""
import json
import os
import re
import socket
import mimetypes
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROUTES = []          # (method, regex, fn, is_api)
TOKENS = {}          # token -> expire_ts
TOKEN_LOCK = threading.Lock()
TOKEN_TTL = 8 * 3600


# ---------------------------------------------------------------- 请求对象
class Request:
    def __init__(self, handler, method, path, query, body, headers):
        self.handler = handler
        self.method = method
        self.path = path
        self.query = query
        self.body = body
        self.headers = headers
        self.params = {}

    def q(self, key, default=""):
        v = self.query.get(key)
        return v[0] if v else default

    def json(self):
        if not self.body:
            return {}
        try:
            return json.loads(self.body.decode("utf-8"))
        except Exception:
            return {}

    def token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        return self.headers.get("X-Token", "") or self.q("_t")

    def form(self):
        """解析 form-data 或 urlencoded，返回 (fields:dict, files:list)"""
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            txt = self.body.decode("utf-8", "replace")
            fields = {k: v[0] for k, v in urllib.parse.parse_qs(txt).items()}
            return fields, []
        m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', ctype)
        boundary = (m.group(1) or m.group(2)).strip().encode()
        fields, files = {}, []
        chunks = self.body.split(b"--" + boundary)
        for ch in chunks:
            ch = ch.strip(b"\r\n")
            if not ch or ch == b"--":
                continue
            if b"\r\n\r\n" not in ch:
                continue
            raw_head, data = ch.split(b"\r\n\r\n", 1)
            if data.endswith(b"\r\n"):
                data = data[:-2]
            head = raw_head.decode("utf-8", "replace")
            name = re.search(r'name="([^"]*)"', head)
            filename = re.search(r'filename="([^"]*)"', head)
            if filename and filename.group(1):
                files.append({"field": name.group(1) if name else "",
                              "filename": filename.group(1), "data": data})
            elif name:
                fields[name.group(1)] = data.decode("utf-8", "replace")
        return fields, files


# ---------------------------------------------------------------- 响应工具
def json_resp(data, code=200):
    return code, [("Content-Type", "application/json; charset=utf-8")], \
        json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")


def err(msg, code=400):
    return json_resp({"ok": False, "msg": msg}, code)


def ok(data=None, **kw):
    payload = {"ok": True}
    if isinstance(data, dict):
        payload.update(data)
    elif data is not None:
        payload["data"] = data
    payload.update(kw)
    return json_resp(payload)


# ---------------------------------------------------------------- 装饰器
def route(method, pattern, api=True):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, api))
        return fn
    return deco


def need_auth(fn):
    def wrapper(req, *a, **kw):
        t = req.token()
        if not t or not valid_token(t):
            return err("未登录或登录已过期", 401)
        return fn(req, *a, **kw)
    return wrapper


def new_token() -> str:
    t = secrets.token_urlsafe(24)
    with TOKEN_LOCK:
        TOKENS[t] = time.time() + TOKEN_TTL
    return t


def valid_token(t) -> bool:
    with TOKEN_LOCK:
        exp = TOKENS.get(t)
        if not exp:
            return False
        if exp < time.time():
            TOKENS.pop(t, None)
            return False
        return True


def revoke(t):
    with TOKEN_LOCK:
        TOKENS.pop(t, None)


# ---------------------------------------------------------------- 服务器
class Handler(BaseHTTPRequestHandler):
    from . import __version__ as _ver
    server_version = "GiftMall/" + _ver
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # 静默：只打印错误
        pass

    def do_GET(self):
        self.handle_all("GET")

    def do_POST(self):
        self.handle_all("POST")

    def do_PUT(self):
        self.handle_all("PUT")

    def do_DELETE(self):
        self.handle_all("DELETE")

    # --------------------------------------------------
    def handle_all(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        req = Request(self, method, path, query, body, self.headers)

        # 静态资源
        if method == "GET" and (path.startswith("/uploads/") or path.startswith("/assets/")):
            return self.serve_static(path)

        for m, rx, fn, is_api in ROUTES:
            if m != method:
                continue
            mo = rx.match(path)
            if mo:
                req.params = mo.groupdict()
                try:
                    code, headers, data = fn(req)
                except Exception as e:  # 兜底，避免服务崩掉
                    import traceback
                    traceback.print_exc()
                    code, headers, data = err("服务器内部错误：%s" % e, 500)
                return self.send(code, headers, data)

        if method == "GET":
            return self.serve_page(path)
        return self.send(*err("接口不存在", 404))

    def send(self, code, headers, data):
        try:
            keys = [h[0] for h in headers]
            self.send_response(code)
            for k, v in headers:
                self.send_header(k, v)
            if "Cache-Control" not in keys:
                self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_page(self, path):
        from . import store
        pages = {"/": "index.html", "/index.html": "index.html",
                 "/admin": "admin.html", "/admin/": "admin.html",
                 "/admin.html": "admin.html"}
        name = pages.get(path)
        if not name:
            return self.send(404, [("Content-Type", "text/html; charset=utf-8")],
                             "<h1>404</h1>".encode())
        fp = os.path.join(store.web_dir(), name)
        if not os.path.exists(fp):
            return self.send(404, [("Content-Type", "text/plain; charset=utf-8")],
                             b"page missing")
        with open(fp, "rb") as f:
            data = f.read()
        return self.send(200, [("Content-Type", "text/html; charset=utf-8")], data)

    def serve_static(self, path):
        from . import store
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(store.data_dir(), rel)) \
            if rel.startswith("uploads/") else \
            os.path.normpath(os.path.join(store.web_dir(), rel))
        allowed_root = store.data_dir() if rel.startswith("uploads/") else store.web_dir()
        if not full.startswith(os.path.abspath(allowed_root)) or not os.path.exists(full) \
                or os.path.isdir(full):
            return self.send(404, [("Content-Type", "text/plain")], b"not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        # 上传的图片可以长缓存；前端 js/css 每次校验，避免改完不生效
        cache = "public, max-age=86400" if rel.startswith("uploads/") \
            else "no-cache, must-revalidate"
        with open(full, "rb") as f:
            data = f.read()
        return self.send(200, [("Content-Type", ctype),
                               ("Cache-Control", cache)], data)


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def serve(port=8000):
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    return srv

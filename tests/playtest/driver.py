"""playtest 드라이버: 여러 Bash 호출에 걸쳐 같은 브라우저를 유지하며 명령을 받는다.

서버는 `start`가 백그라운드로 띄우고(playwright 필요),
나머지 명령은 표준 라이브러리만으로 HTTP를 보낸다.
사용법은 tests/playtest/README.md.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SETTLE_MS = 400


def call(port: int, cmd: str, args: list[str], timeout: float = 60) -> str:
    body = json.dumps({"cmd": cmd, "args": args}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/", body, {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["out"]


def start(args: argparse.Namespace) -> None:
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        __file__,
        "serve",
        "--url",
        args.url,
        "--out",
        str(out),
        "--port",
        str(args.port),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--name",
        args.name,
    ]
    log = open(out / "server.log", "w")
    proc = subprocess.Popen(
        cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True
    )
    (out / "server.pid").write_text(str(proc.pid))
    for _ in range(100):
        time.sleep(0.3)
        if proc.poll() is not None:
            sys.exit(f"서버가 종료됐다. {out / 'server.log'} 확인")
        try:
            print(call(args.port, "ping", [], timeout=2))
            return
        except OSError:
            continue
    sys.exit("서버 준비 시간 초과")


class Server:
    def __init__(self, args: argparse.Namespace) -> None:
        from playwright.sync_api import sync_playwright

        self.out = Path(args.out)
        self.name = args.name
        self.shots = self.out / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=True)
        size = {"width": args.width, "height": args.height}
        self.ctx = self.browser.new_context(
            viewport=size, record_video_dir=str(self.out / "video"), record_video_size=size
        )
        self.page = self.ctx.new_page()
        self.dialogs: list[str] = []
        self.page.on("dialog", self.on_dialog)
        self.page.goto(args.url)
        self.settle()
        self.done = False

    def on_dialog(self, dialog) -> None:
        self.dialogs.append(f"{dialog.type}: {dialog.message}")
        print(f"[dialog] {dialog.type}: {dialog.message}", flush=True)
        dialog.dismiss()

    def settle(self) -> None:
        self.page.wait_for_timeout(SETTLE_MS)

    def locate(self, target: str, kinds: list[str]):
        """css= 접두사면 CSS, 아니면 kinds 순서로 role/텍스트/라벨을 시도한다."""
        p = self.page
        if target.startswith("css="):
            return p.locator(target[4:]).first
        for kind in kinds:
            if kind == "click":
                cands = [
                    p.get_by_role("button", name=target),
                    p.get_by_role("link", name=target),
                    p.get_by_text(target, exact=True),
                    p.get_by_text(target),
                ]
            else:
                cands = [p.get_by_label(target), p.get_by_placeholder(target)]
            for loc in cands:
                if loc.count() > 0:
                    return loc.first
        return None

    def candidates(self) -> str:
        items = self.page.evaluate(
            """() => [...document.querySelectorAll('button,a,input,textarea,select,[role=button]')]
              .filter(e => e.offsetParent !== null)
              .map(e => (e.innerText || e.placeholder || e.getAttribute('aria-label')
                         || e.value || e.tagName).trim().slice(0, 40))
              .filter(Boolean).slice(0, 5)"""
        )
        return "후보: " + " | ".join(items)

    def handle(self, cmd: str, a: list[str]) -> str:
        p = self.page
        if cmd == "ping":
            return "ready"
        if cmd == "shot":
            name = re.sub(r"[^\w.-]", "_", a[0]) if a else "shot"
            path = self.shots / f"{len(list(self.shots.glob('*.png'))) + 1:02d}-{name}.png"
            p.screenshot(path=str(path), full_page=True)
            return str(path)
        if cmd == "text":
            return p.inner_text("body")[:6000]
        if cmd in ("click", "fill"):
            loc = self.locate(a[0], [cmd])
            if loc is None:
                return f"못 찾음: {a[0]}\n{self.candidates()}"
            loc.click(timeout=5000) if cmd == "click" else loc.fill(a[1], timeout=5000)
            self.settle()
            return "ok" + (f" (대화상자 {len(self.dialogs)}건)" if self.dialogs else "")
        if cmd == "select":
            loc = self.locate(a[0], ["fill"])
            if loc is None:
                return f"못 찾음: {a[0]}\n{self.candidates()}"
            loc.select_option(label=a[1], timeout=5000)
            self.settle()
            return "ok"
        if cmd == "type":
            p.keyboard.type(a[0])
        elif cmd == "press":
            p.keyboard.press(a[0])
        elif cmd == "goto":
            p.goto(a[0])
        elif cmd == "wait":
            p.wait_for_timeout(min(float(a[0]), 10) * 1000)
        elif cmd == "stop":
            return self.stop()
        else:
            return f"알 수 없는 명령: {cmd}"
        self.settle()
        return "ok"

    def stop(self) -> str:
        video = self.page.video
        self.ctx.close()
        webm = Path(video.path())
        self.browser.close()
        self.pw.stop()
        self.done = True
        dest = self.out / f"{self.name}.webm"
        webm.replace(dest)
        return str(dest)


def serve(args: argparse.Namespace) -> None:
    srv = Server(args)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                out = srv.handle(req["cmd"], req["args"])
            except Exception as e:  # 에이전트에게 실패를 돌려줘야 한다
                out = f"오류: {str(e).splitlines()[0][:300]}"
            data = json.dumps({"out": out}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_: object) -> None:
            pass

    httpd = HTTPServer(("127.0.0.1", args.port), Handler)
    while not srv.done:
        httpd.handle_request()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "cmd",
        choices=[
            "start",
            "serve",
            "shot",
            "text",
            "click",
            "fill",
            "select",
            "type",
            "press",
            "goto",
            "wait",
            "stop",
        ],
    )
    ap.add_argument("args", nargs="*")
    ap.add_argument("--url", default="")
    ap.add_argument("--out", default="playtest-out")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PLAYTEST_PORT", 9400)))
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--name", default="playtest")
    args = ap.parse_args()
    if args.cmd == "start":
        start(args)
    elif args.cmd == "serve":
        serve(args)
    else:
        print(call(args.port, args.cmd, args.args, timeout=120))


if __name__ == "__main__":
    main()

"""정답 표시 도구를 띄우는 작은 서버 (2026-11-17).

파일을 그냥 열어도(file://) 점 고치기는 되지만, 아래 두 가지는 이 서버로 열어야 된다.
  - 「바로 세운 각도로 초안 다시 달기」: 그림을 그 각도로 돌려 로컬 AI 서버(AI_URL, 기본 http://127.0.0.1:8001)의
    네 발 분석에 보내고, 돌아온 관절을 원본 좌표로 되돌려 준다.
  - 고친 것을 data/testset/quadruped/labels.json 에 바로 저장하고, 다시 열면 거기서 읽는다.

    python tools/make_labeler.py     (화면 파일 만들기, 그림이 바뀌었을 때만)
    python tools/label_server.py     → http://127.0.0.1:8765/
"""

import json
import math
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from build_testset import analyze  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SET = ROOT / "data/testset/quadruped"
PAGE = ROOT / "data/testset/label_quadruped.html"
LABELS = SET / "labels.json"
PORT = 8765


def redraft(name: str, deg: float) -> dict:
    """그림을 deg 도(시계 방향) 돌려 규칙을 다시 돌리고, 관절을 원본 좌표로 되돌린다"""
    src = SET / Path(name).name
    im = Image.open(src).convert("RGB")
    w, h = im.size
    rot = im.rotate(-deg, expand=True, fillcolor="white", resample=Image.BICUBIC)   # PIL 은 반시계가 양수
    W, H = rot.size
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "upright.png"
        rot.save(tmp)
        r = analyze(tmp)
    if not r:
        return {"ok": False, "message": "AI 서버에 닿지 않습니다 (도커의 AI 서버가 켜져 있는지 확인)"}
    if not r.get("joints"):
        return {"ok": False, "message": r.get("message") or "분석이 관절을 돌려주지 않았습니다"}
    th = math.radians(deg)
    co, si = math.cos(th), math.sin(th)
    joints = {}
    for j in r["joints"]:
        dx, dy = j["x"] - W / 2, j["y"] - H / 2
        x, y = w / 2 + dx * co + dy * si, h / 2 - dx * si + dy * co
        joints[j["name"]] = [round(min(max(x, 0), w)), round(min(max(y, 0), h))]
    return {"ok": True, "found": bool(r.get("success") and r.get("joints_found")), "joints": joints}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:  # noqa: ANN001
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/labels":
            self._json(json.load(open(LABELS, encoding="utf-8")) if LABELS.exists() else {})
        elif path.startswith("/quadruped/") and path.endswith(".png"):
            f = SET / Path(path).name
            if f.exists():
                self._send(200, f.read_bytes(), "image/png")
            else:
                self._send(404, b"", "text/plain")
        else:
            self._send(404, b"", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/redraft":
            try:
                self._json(redraft(body["name"], float(body.get("rotate", 0))))
            except Exception as e:  # noqa: BLE001
                self._json({"ok": False, "message": str(e)[:200]})
        elif self.path == "/labels":
            tmp = LABELS.with_suffix(".tmp")
            json.dump(body, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            tmp.replace(LABELS)
            self._json({"ok": True, "count": len(body)})
        else:
            self._send(404, b"", "text/plain")

    def log_message(self, *a) -> None:  # noqa: ANN002
        pass


if __name__ == "__main__":
    if not PAGE.exists():
        sys.exit("먼저 python tools/make_labeler.py 를 돌린다")
    print(f"정답 표시 도구: http://127.0.0.1:{PORT}/   (끄려면 Ctrl+C)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

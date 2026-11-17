"""정답 표시 도구를 띄우는 작은 서버 (2026-11-17).

파일을 그냥 열어도(file://) 점 고치기는 되지만, 아래 두 가지는 이 서버로 열어야 된다.
  - 「바로 세운 각도로 초안 다시 달기」: 그림을 그 각도로 돌려 로컬 AI 서버(AI_URL, 기본 http://127.0.0.1:8001)의
    네 발 분석에 보내고, 돌아온 관절을 원본 좌표로 되돌려 준다.
  - 고친 것을 data/testset/quadruped/labels.json 에 바로 저장하고, 다시 열면 거기서 읽는다.

    python tools/make_labeler.py     (화면 파일 만들기, 그림이 바뀌었을 때만)
    work/venv/Scripts/python tools/label_server.py     → http://127.0.0.1:8765/   (numpy 가 필요해 work/venv 로 띄운다)
다른 그림 묶음은 `--set qd_pilot` (tools/sets.py, 포트 8766). `/facing` 은 머리 쪽만 빨리 누르는 화면, `/judge` 는 초안이 맞는지만 고르는 화면.
"""

import json
import math
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from body_rule import analyze_upright, body_points  # noqa: E402
from sets import page_path, pick  # noqa: E402

NAME, SET, PORT, _ = pick()
PAGE = page_path(SET)
FACING = page_path(SET, "facing")
LABELS = SET / "labels.json"


def redraft(name: str, deg: float, facing: str | None = None) -> dict:
    """그림을 deg 도(시계 방향) 돌려 규칙을 다시 돌리고, 관절을 원본 좌표로 되돌린다.
    facing 은 바로 세운 화면에서 머리가 있는 쪽(left · right). 주면 규칙이 추측하지 않고 그쪽을 머리로 본다"""
    w, h = Image.open(SET / Path(name).name).size
    r, (W, H) = analyze_upright(SET, name, deg, facing)   # 마스크도 남긴다(몸통 자리 계산용)
    if not r:
        return {"ok": False, "message": "AI 서버에 닿지 않습니다 (도커의 AI 서버가 켜져 있는지 확인)"}
    if not r.get("joints"):
        return {"ok": False, "message": r.get("message") or "분석이 관절을 돌려주지 않았습니다"}
    th = math.radians(deg)
    co, si = math.cos(th), math.sin(th)
    joints = {}
    by = {j["name"]: j for j in r["joints"]}
    guess = ("right" if by["neck"]["x"] > by["hip"]["x"] else "left") if "neck" in by and "hip" in by else ""   # 세운 화면 기준
    for j in r["joints"]:
        dx, dy = j["x"] - W / 2, j["y"] - H / 2
        x, y = w / 2 + dx * co + dy * si, h / 2 - dx * si + dy * co
        joints[j["name"]] = [round(min(max(x, 0), w)), round(min(max(y, 0), h))]
    return {"ok": True, "found": bool(r.get("success") and r.get("joints_found")), "joints": joints, "facing": guess}


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
        elif path in ("/facing", "/judge") and page_path(SET, path[1:]).exists():   # 머리 쪽 누르기 · 초안 고르기
            self._send(200, page_path(SET, path[1:]).read_bytes(), "text/html; charset=utf-8")
        elif path == "/labels":
            self._json(json.load(open(LABELS, encoding="utf-8")) if LABELS.exists() else {})
        elif path.startswith(("/img/", "/quadruped/")) and path.endswith(".png"):
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
                self._json(redraft(body["name"], float(body.get("rotate", 0)), body.get("facing") or None))
            except Exception as e:  # noqa: BLE001
                self._json({"ok": False, "message": str(e)[:200]})
        elif self.path == "/body":   # 몸통 세 점을 다리 자리에서 계산 (tools/body_rule.py)
            try:
                got = body_points(SET, body["name"], float(body.get("rotate", 0)), body.get("joints") or {})
                self._json({"ok": True, "joints": got} if got else {"ok": False, "message": "앞다리와 뒷다리가 하나씩은 있어야 합니다"})
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
        sys.exit(f"먼저 python tools/make_labeler.py --set {NAME} 을 돌린다")
    print(f"정답 표시 도구: http://127.0.0.1:{PORT}/   (끄려면 Ctrl+C)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

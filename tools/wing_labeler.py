"""날개형 정답 표시 도구 (2026-11-20). 네 발 도구(make_labeler.py)는 네 발 전용이라, 날개형은 작게 따로 만들었다.

    python tools/build_wingset.py 로 후보를 모은 뒤
    python tools/wing_labeler.py     → http://127.0.0.1:8770/     (표준 라이브러리만 쓴다)
    정답은 data/testset/winged/labels.json 에 바로 저장된다.

날개형은 날개 하나가 기준이다(사용자 2026-11-20). 사람이 놓는 점은 넷: 몸통, 머리, 날개 뿌리, 날개 끝. 날개 가운데는 뿌리와 끝의 한가운데로 자동(서비스 규칙도 그렇게 놓는다).
초안은 규칙 · 모델이 아니라 그림 크기에 맞춘 고정 자리다. 규칙이나 모델의 초안을 고쳐 만든 정답은 그쪽에 유리해지기 때문이다.

약속 (drawtale-ai winged.py, train/synth_wing.py 와 같다)
  - 몸통 = 몸통 가운데, 머리 = 머리 가운데
  - 날개 뿌리 = 날개가 몸통에 닿는 자리의 가운데, 날개 끝 = 뿌리에서 가장 먼 날개 끝
  - 몸 밖으로 솟은 날개만 날개다. 몸 안에 그린 날개뿐이면 「날개 없음」: 날개 점 셋이 모두 몸통에 겹친다
  - 날개가 둘 보이면 하나만 표시한다: 더 긴 날개, 비슷하면 왼쪽 날개
  - 저장하는 관절은 다섯: body · head · wing_root · wing_mid · wing_tip
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SET = ROOT / "data/testset/winged"
LABELS = SET / "labels.json"
PORT = 8770
ORDER = ["body", "head", "wing_root", "wing_mid", "wing_tip"]

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>날개형 정답 표시</title>
<style>
  body { margin: 0; font: 14px "Malgun Gothic", sans-serif; display: flex; height: 100vh; background: #f4f4f1; }
  #list { width: 210px; overflow: auto; border-right: 1px solid #ccc; background: #fff; }
  #list div { padding: 5px 10px; cursor: pointer; border-bottom: 1px solid #eee; }
  #list div.on { background: #dfe9ff; }
  #list div.done { color: #1a8f3c; }
  #list div.skip { color: #aaa; text-decoration: line-through; }
  #main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  #bar { padding: 8px 12px; background: #fff; border-bottom: 1px solid #ccc; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  #help { padding: 6px 12px; background: #fff; border-bottom: 1px solid #ccc; color: #555; font-size: 12.5px; line-height: 1.5; }
  button { font: inherit; padding: 5px 12px; cursor: pointer; }
  button.sel { background: #25d; color: #fff; border-color: #25d; }
  #stage { flex: 1; overflow: auto; padding: 12px; }
  svg { background: #fff; border: 1px solid #ccc; touch-action: none; }
  text { font-size: 12px; paint-order: stroke; stroke: #fff; stroke-width: 3px; pointer-events: none; }
  circle.p { cursor: grab; stroke: #fff; stroke-width: 2; }
</style></head><body>
<div id="list"></div>
<div id="main">
  <div id="bar">
    <b id="name"></b>
    <span>몸 밖으로 솟은 날개</span>
    <button class="w" data-w="1">있음 (1)</button><button class="w" data-w="0">없음 (0): 몸 안에 그린 날개뿐</button>
    <button id="skip">못 씀 (날개형이 아니거나 알아볼 수 없음)</button>
    <button id="reset">점 처음 자리로</button>
    <button id="next"><b>이 그림 끝 → 다음 (Enter)</b></button>
    <span id="count"></span>
  </div>
  <div id="help">
    점을 끌어 옮깁니다. <b style="color:#1a8f3c">몸통</b> = 몸통 가운데, <b style="color:#e08a00">머리</b> = 머리 가운데,
    <b style="color:#d23">날개 뿌리</b> = 날개가 몸통에 닿는 자리의 가운데, <b style="color:#d23">날개 끝</b> = 뿌리에서 가장 먼 날개 끝. 작은 점(가운데)은 자동입니다.<br>
    <b>날개는 하나만 표시합니다.</b> 둘이 보이면 더 긴 날개, 비슷하면 왼쪽 날개. 나비처럼 한쪽에 위아래 두 장이 붙어 있으면 그 한쪽 전체를 날개 하나로 봅니다.
    몸통 안에 그린 날개뿐이면 「없음」. 키: 1 = 있음, 0 = 없음, X = 못 씀, Enter = 끝, ↑ ↓ = 그림 옮기기.
  </div>
  <div id="stage"><svg id="svg"></svg></div>
</div>
<script>
const AUTO = __AUTO__;
let labels = __LABELS__;
const names = Object.keys(AUTO);
const PTS = [["body", "몸통", "#1a8f3c"], ["head", "머리", "#e08a00"], ["wing1_root", "날개 뿌리", "#d23"], ["wing1_tip", "날개 끝", "#d23"]];
const START = { body: [.5, .58], head: [.7, .42], wing1_root: [.42, .48], wing1_tip: [.28, .2] };
let cur = 0, timer = null, t0 = Date.now();
const $ = id => document.getElementById(id);

function rec(n) {
  if (!labels[n]) {
    const a = AUTO[n], pts = {};
    for (const k in START) pts[k] = [Math.round(START[k][0] * a.width), Math.round(START[k][1] * a.height)];
    labels[n] = { use: true, done: false, wings: 1, pts, ms: 0 };
  }
  if (labels[n].wings > 1) labels[n].wings = 1;      // 날개 둘로 표시하던 때의 기록: 날개 1 만 남긴다
  return labels[n];
}
function joints(r) {            // 저장하는 관절 5개: 날개 하나. 없으면 날개 점 셋이 몸통에 겹친다
  const p = r.pts, root = r.wings ? p.wing1_root : p.body, tip = r.wings ? p.wing1_tip : p.body;
  return { body: p.body, head: p.head, wing_root: root, wing_mid: [(root[0] + tip[0]) / 2, (root[1] + tip[1]) / 2], wing_tip: tip };
}
function save() {
  const r = rec(names[cur]);
  r.joints = joints(r);
  clearTimeout(timer);
  timer = setTimeout(() => fetch("labels", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(labels) })
    .then(x => x.ok || alert("저장 실패")).catch(() => alert("저장 실패: 서버가 꺼졌는지 확인")), 250);
}
function list() {
  $("list").innerHTML = "";
  names.forEach((n, i) => {
    const r = labels[n], d = document.createElement("div");
    d.textContent = n.replace(".png", "") + (AUTO[n].kind ? "  " + AUTO[n].kind : "");
    d.className = (i === cur ? "on " : "") + (r && !r.use ? "skip" : r && r.done ? "done" : "");
    d.onclick = () => go(i);
    $("list").appendChild(d);
    if (i === cur) d.scrollIntoView({ block: "nearest" });
  });
  const done = names.filter(n => labels[n] && labels[n].done && labels[n].use).length, skip = names.filter(n => labels[n] && !labels[n].use).length;
  $("count").textContent = `정답 ${done}장 · 못 씀 ${skip}장 · 모두 ${names.length}장`;
}
function draw() {
  const n = names[cur], a = AUTO[n], r = rec(n), svg = $("svg");
  const s = Math.min(1.6, Math.max(.4, Math.min((window.innerWidth - 260) / a.width, (window.innerHeight - 190) / a.height)));
  svg.setAttribute("width", a.width * s); svg.setAttribute("height", a.height * s); svg.setAttribute("viewBox", `0 0 ${a.width} ${a.height}`);
  $("name").textContent = `${n}  (${a.note})`;
  document.querySelectorAll("button.w").forEach(b => b.classList.toggle("sel", +b.dataset.w === r.wings && r.use));
  $("skip").classList.toggle("sel", !r.use);
  let h = `<image href="img/${n}" width="${a.width}" height="${a.height}" opacity="${r.use ? .8 : .25}"/>`;
  if (r.use) {
    const k = 1 / s, show = PTS.filter(([id]) => id === "body" || id === "head" || r.wings >= 1);
    const line = (p, q, c) => `<line x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" stroke="${c}" stroke-width="${3 * k}"/>`;
    h += line(r.pts.body, r.pts.head, "#1a8f3c");
    for (const [w, c] of [["wing1", "#d23"]]) if (r.wings >= 1) {
      const a1 = r.pts[w + "_root"], b1 = r.pts[w + "_tip"];
      h += line(r.pts.body, a1, c) + line(a1, b1, c) + `<circle cx="${(a1[0] + b1[0]) / 2}" cy="${(a1[1] + b1[1]) / 2}" r="${4 * k}" fill="${c}"/>`;
    }
    for (const [id, label, c] of show) {
      const p = r.pts[id];
      h += `<circle class="p" data-id="${id}" cx="${p[0]}" cy="${p[1]}" r="${8 * k}" fill="${c}"/><text x="${p[0] + 11 * k}" y="${p[1] + 4 * k}" style="font-size:${12 * k}px;stroke-width:${3 * k}px">${label}</text>`;
    }
  }
  svg.innerHTML = h;
}
function go(i) {
  const r = labels[names[cur]];
  if (r) r.ms = (r.ms || 0) + Date.now() - t0;
  cur = (i + names.length) % names.length; t0 = Date.now();
  list(); draw();
}
let drag = null;
$("svg").addEventListener("pointerdown", e => { if (e.target.dataset.id) { drag = e.target.dataset.id; $("svg").setPointerCapture(e.pointerId); } });
$("svg").addEventListener("pointermove", e => {
  if (!drag) return;
  const svg = $("svg"), b = svg.getBoundingClientRect(), a = AUTO[names[cur]];
  const x = Math.max(0, Math.min(a.width, (e.clientX - b.left) * a.width / b.width)), y = Math.max(0, Math.min(a.height, (e.clientY - b.top) * a.height / b.height));
  rec(names[cur]).pts[drag] = [Math.round(x), Math.round(y)];
  draw();
});
$("svg").addEventListener("pointerup", () => { if (drag) { drag = null; save(); } });
function wings(w) { const r = rec(names[cur]); r.use = true; r.wings = w; save(); list(); draw(); }
function skip() { const r = rec(names[cur]); r.use = !r.use; r.done = !r.use || r.done; save(); list(); draw(); }
function next() { const r = rec(names[cur]); r.done = true; save(); go(cur + 1); }
document.querySelectorAll("button.w").forEach(b => b.onclick = () => wings(+b.dataset.w));
$("skip").onclick = skip; $("next").onclick = next;
$("reset").onclick = () => { delete labels[names[cur]]; rec(names[cur]); save(); list(); draw(); };
document.addEventListener("keydown", e => {
  if (e.key === "Enter") next(); else if (e.key === "ArrowDown") go(cur + 1); else if (e.key === "ArrowUp") go(cur - 1);
  else if ("01".includes(e.key)) wings(+e.key); else if (e.key.toLowerCase() === "x") skip(); else return;
  e.preventDefault();
});
window.addEventListener("resize", draw);
const first = names.findIndex(n => !(labels[n] && labels[n].done));
go(first < 0 ? 0 : first);
</script></body></html>
"""


class H(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/":
            auto = json.load(open(SET / "auto.json", encoding="utf-8"))
            labels = json.load(open(LABELS, encoding="utf-8")) if LABELS.exists() else {}
            page = PAGE.replace("__AUTO__", json.dumps(auto, ensure_ascii=False)).replace("__LABELS__", json.dumps(labels, ensure_ascii=False))
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        elif path.startswith("/img/"):
            f = SET / Path(path).name                          # 이름만 쓴다: 폴더 밖 파일은 주지 않는다
            if f.suffix == ".png" and f.exists():
                self._send(200, f.read_bytes(), "image/png")
            else:
                self._send(404, b"", "text/plain")
        else:
            self._send(404, b"", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/labels":
            return self._send(404, b"", "text/plain")
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        tmp = LABELS.with_suffix(".tmp")
        json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        tmp.replace(LABELS)
        self._send(200, b"ok", "text/plain")

    def log_message(self, *a) -> None:  # noqa: ANN002
        pass


if __name__ == "__main__":
    if not (SET / "auto.json").exists():
        raise SystemExit("먼저 work/venv/Scripts/python tools/build_wingset.py 로 그림을 모은다")
    print(f"http://127.0.0.1:{PORT}/   (끄기: Ctrl+C)  정답: {LABELS}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()

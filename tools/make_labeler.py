"""시험 세트 정답 표시 도구 만들기 (2026-11-17).

data/testset/quadruped/auto.json(규칙이 단 초안)을 읽어 한 장짜리 HTML 을 만든다. 브라우저에서 그냥 연다(서버 필요 없음).
  - 점을 끌어 옮긴다. 점을 오른쪽 클릭하면 「안 보임」(그림에 없는 부위, 예: 꼬리 없음)으로 바뀐다.
  - 그림마다 「시험에 씀 / 뺌」(네 발로 선 그림이 아니면 뺌)과 머리 쪽(왼쪽 · 오른쪽)을 고른다.
  - 고친 것은 브라우저에 바로 저장되고, 「내보내기」를 누르면 labels_quadruped.json 을 받는다.
    받은 파일을 data/testset/quadruped/labels.json 으로 옮기면 그것이 정답이다.

    python tools/make_labeler.py   → data/testset/label_quadruped.html
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SET = ROOT / "data/testset/quadruped"

# 관절 이름 · 화면 이름은 drawtale-ai runtime/ai_server/forms/quadruped.json (dev 4c2147f) 그대로.
# 부모는 화면에 선을 긋는 용도라 다리를 몸통 쪽에 이었다(원본은 다리 위 관절의 부모가 root)
JOINTS = [("hip", None, "엉덩이"), ("torso", "hip", "어깨"), ("neck", "torso", "목"),
          ("right_hip_b", "hip", "뒷다리 1 위"), ("right_knee_b", "right_hip_b", "뒷다리 1 무릎"), ("right_foot_b", "right_knee_b", "뒷다리 1 발"),
          ("left_hip_b", "hip", "뒷다리 2 위"), ("left_knee_b", "left_hip_b", "뒷다리 2 무릎"), ("left_foot_b", "left_knee_b", "뒷다리 2 발"),
          ("right_hip_f", "torso", "앞다리 1 위"), ("right_knee_f", "right_hip_f", "앞다리 1 무릎"), ("right_foot_f", "right_knee_f", "앞다리 1 발"),
          ("left_hip_f", "torso", "앞다리 2 위"), ("left_knee_f", "left_hip_f", "앞다리 2 무릎"), ("left_foot_f", "left_knee_f", "앞다리 2 발"),
          ("tail", "hip", "꼬리 뿌리"), ("tail_mid", "tail", "꼬리 가운데"), ("tail_tip", "tail_mid", "꼬리 끝")]

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>네 발 정답 표시</title>
<style>
  body { margin: 0; font: 14px/1.5 system-ui, sans-serif; background: #f4f4f1; color: #222; display: flex; height: 100vh; }
  #list { width: 190px; overflow: auto; border-right: 1px solid #ccc; background: #fff; }
  #list div { padding: 5px 10px; cursor: pointer; border-bottom: 1px solid #eee; }
  #list div.on { background: #dbe9ff; }
  #list div.done::after { content: " ✓"; color: #1a7f37; }
  #list div.skip { color: #999; text-decoration: line-through; }
  #main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  #bar { padding: 8px 12px; background: #fff; border-bottom: 1px solid #ccc; display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
  #stage { flex: 1; overflow: auto; padding: 12px; }
  svg { background: #fff; box-shadow: 0 0 0 1px #ccc; touch-action: none; }
  circle { cursor: grab; stroke: #fff; stroke-width: 1.5; }
  circle.gone { fill: #bbb !important; opacity: .6; }
  text { font-size: 11px; paint-order: stroke; stroke: #fff; stroke-width: 3px; pointer-events: none; }
  button { font: inherit; padding: 4px 10px; }
  #help { color: #555; font-size: 13px; }
</style></head><body>
<div id="list"></div>
<div id="main">
  <div id="bar">
    <b id="name"></b>
    <label><input type="checkbox" id="use"> 시험에 씀(네 발로 선 그림)</label>
    <label>머리 쪽 <select id="facing"><option value="">모름</option><option value="left">왼쪽</option><option value="right">오른쪽</option></select></label>
    <label><input type="checkbox" id="names" checked> 이름 보기</label>
    <button id="reset">초안으로 되돌리기</button>
    <button id="done">이 그림 끝 → 다음</button>
    <button id="export">내보내기</button>
    <span id="count"></span>
  </div>
  <div id="bar"><span id="help">점을 끌어 옮깁니다. 그림에 없는 부위는 점을 오른쪽 클릭해 「안 보임」(회색)으로. 빨강 = 뒷다리, 파랑 = 앞다리, 초록 = 몸통 · 목, 보라 = 꼬리. 고친 것은 바로 저장됩니다.</span></div>
  <div id="stage"><svg id="svg"></svg></div>
</div>
<script>
const DATA = __DATA__, JOINTS = __JOINTS__, KEY = "creature-pose-quadruped-labels-v1";
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const names = Object.keys(DATA).sort();
let cur = 0;
const $ = id => document.getElementById(id), NS = "http://www.w3.org/2000/svg";
const color = n => n.endsWith("_b") ? "#d23" : n.endsWith("_f") ? "#25d" : n.startsWith("tail") ? "#93c" : "#1a8f3c";
function save() { try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {} }
function rec(n) {
  if (!labels[n]) {
    const a = DATA[n], j = {};
    for (const [name] of JOINTS) {
      const p = a.joints[name];
      j[name] = p ? [p[0], p[1], 1] : [a.width / 2, a.height / 2, 1];
    }
    labels[n] = { use: true, facing: "", done: false, joints: j };
  }
  return labels[n];
}
function drawList() {
  $("list").innerHTML = "";
  names.forEach((n, i) => {
    const d = document.createElement("div"), r = labels[n];
    d.textContent = n.replace(".png", "") + (DATA[n].found ? "" : " (초안 없음)");
    d.className = (i === cur ? "on " : "") + (r && r.done ? "done " : "") + (r && !r.use ? "skip" : "");
    d.onclick = () => { cur = i; show(); };
    $("list").appendChild(d);
  });
  const done = names.filter(n => labels[n] && labels[n].done).length;
  $("count").textContent = `끝낸 그림 ${done} / ${names.length}`;
}
function show() {
  const n = names[cur], a = DATA[n], r = rec(n), svg = $("svg");
  const s = Math.min(1, 900 / Math.max(a.width, a.height)) * 1;
  svg.setAttribute("width", a.width * s); svg.setAttribute("height", a.height * s);
  svg.setAttribute("viewBox", `0 0 ${a.width} ${a.height}`);
  svg.innerHTML = "";
  const img = document.createElementNS(NS, "image");
  img.setAttribute("href", "quadruped/" + n); img.setAttribute("width", a.width); img.setAttribute("height", a.height);
  svg.appendChild(img);
  const lines = {}, R = Math.max(a.width, a.height) / 110;
  for (const [name, parent] of JOINTS) if (parent) {
    const l = document.createElementNS(NS, "line");
    l.setAttribute("stroke", color(name)); l.setAttribute("stroke-width", R / 2.2);
    svg.appendChild(l); lines[name] = l;
  }
  function place() {
    for (const [name, parent] of JOINTS) if (parent) {
      const p = r.joints[name], q = r.joints[parent], l = lines[name];
      l.setAttribute("x1", q[0]); l.setAttribute("y1", q[1]); l.setAttribute("x2", p[0]); l.setAttribute("y2", p[1]);
      l.setAttribute("opacity", p[2] && q[2] ? .9 : .15);
    }
  }
  place();
  for (const [name, , label] of JOINTS) {
    const p = r.joints[name], c = document.createElementNS(NS, "circle"), t = document.createElementNS(NS, "text");
    c.setAttribute("r", R); c.setAttribute("fill", color(name));
    const put = () => { c.setAttribute("cx", p[0]); c.setAttribute("cy", p[1]); t.setAttribute("x", p[0] + R * 1.3); t.setAttribute("y", p[1] + 4);
                        c.setAttribute("class", p[2] ? "" : "gone"); };
    t.textContent = label; t.style.display = $("names").checked ? "" : "none"; t.style.fontSize = Math.max(11, R * 1.6) + "px";
    put();
    c.addEventListener("pointerdown", e => {
      if (e.button !== 0) return;
      c.setPointerCapture(e.pointerId);
      const move = ev => {
        const b = svg.getBoundingClientRect();
        p[0] = Math.round(Math.max(0, Math.min(a.width, (ev.clientX - b.left) / b.width * a.width)));
        p[1] = Math.round(Math.max(0, Math.min(a.height, (ev.clientY - b.top) / b.height * a.height)));
        put(); place();
      };
      const up = () => { c.removeEventListener("pointermove", move); c.removeEventListener("pointerup", up); save(); };
      c.addEventListener("pointermove", move); c.addEventListener("pointerup", up);
    });
    c.addEventListener("contextmenu", e => { e.preventDefault(); p[2] = p[2] ? 0 : 1; put(); place(); save(); });
    svg.appendChild(c); svg.appendChild(t);
  }
  $("name").textContent = `${n}  (${a.source}: ${a.note})`;
  $("use").checked = r.use; $("facing").value = r.facing;
  drawList();
}
$("use").onchange = e => { rec(names[cur]).use = e.target.checked; save(); drawList(); };
$("facing").onchange = e => { rec(names[cur]).facing = e.target.value; save(); };
$("names").onchange = show;
$("reset").onclick = () => { delete labels[names[cur]]; save(); show(); };
$("done").onclick = () => { rec(names[cur]).done = true; save(); if (cur < names.length - 1) cur++; show(); };
$("export").onclick = () => {
  const out = {};
  for (const n of names) if (labels[n] && labels[n].done) out[n] = Object.assign({ width: DATA[n].width, height: DATA[n].height, source: DATA[n].source }, labels[n]);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], { type: "application/json" }));
  a.download = "labels_quadruped.json"; a.click();
};
show();
</script></body></html>
"""


def main() -> None:
    auto = json.load(open(SET / "auto.json", encoding="utf-8"))
    page = PAGE.replace("__DATA__", json.dumps(auto, ensure_ascii=False)).replace(
        "__JOINTS__", json.dumps([list(j) for j in JOINTS], ensure_ascii=False))
    out = SET.parent / "label_quadruped.html"
    out.write_text(page, encoding="utf-8")
    print(out, len(auto), "장")


if __name__ == "__main__":
    main()

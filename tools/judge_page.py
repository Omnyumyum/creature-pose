"""「초안 고르기」 화면 (2026-11-17). 점을 고치지 않고, 규칙이 단 초안이 맞는지만 키 하나로 답한다.

고치기가 장당 36초로 너무 힘들어(사용자 11/17) 만든 길. 시험 100장에서 머리 쪽을 알려 준 초안은 다리 + 꼬리가 다 맞은 것이 약 35%,
꼬리만 틀린 것이 약 16% 였다. 맞은 초안만 골라 학습 정답으로 쓴다.
  →  맞음            다리 점이 각 다리 위에 있고 앞(파랑) · 뒤(빨강)가 맞고 꼬리(보라)도 맞음
  ↓  꼬리만 틀림      다리는 맞는데 꼬리가 틀림(꼬리가 없는데 그렸거나, 있는데 엉뚱한 곳). 꼬리 점은 학습에서 빼고 쓴다
  ←  틀림            버림
  ↑ (또는 Backspace)  앞 그림으로
볼 것은 다리와 꼬리뿐: 다리 1 · 2 번호, 무릎 자리, 몸통 세 점(속이 빈 점, 규칙 자리)은 따지지 않는다.
답은 labels.json 의 judge(ok · tail · bad), 걸린 시간은 t_judge(ms). ok · tail 은 done = true 가 된다.
머리 쪽을 누르고 초안이 달린 그림만 나온다. make_labeler.py 가 judge_<묶음>.html 을 만들고 label_server.py 가 /judge 로 보여 준다.
"""

JUDGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>__TITLE__ 초안 고르기</title>
<style>
  body { margin: 0; font: 15px/1.6 system-ui, sans-serif; background: #f4f4f1; color: #222; text-align: center; }
  #top { padding: 10px; background: #fff; border-bottom: 1px solid #ccc; }
  svg { margin: 12px auto 6px; background: #fff; box-shadow: 0 0 0 1px #ccc; display: block; }
  button { font: inherit; padding: 10px 18px; margin: 4px; min-width: 150px; }
  button.on { background: #dbe9ff; border-color: #25d; }
  #help { color: #555; font-size: 13px; max-width: 820px; margin: 6px auto; }
  #state { color: #b35c00; }
</style></head><body>
<div id="top"><b id="name"></b> &nbsp; <span id="count"></span> &nbsp; <span id="state"></span></div>
<svg id="svg"></svg>
<div>
  <button id="bad">← 틀림</button>
  <button id="tail">↓ 꼬리만 틀림</button>
  <button id="ok">맞음 →</button>
</div>
<div><button id="back" style="min-width:0">↑ 앞 그림으로</button> <label><input type="checkbox" id="lines" checked> 뼈대 보기 (스페이스)</label></div>
<div id="help">다리와 꼬리만 봅니다. <b>맞음</b>: 빨강(뒷다리) · 파랑(앞다리) 점이 각 다리 위에 있고 앞뒤가 맞고, 보라(꼬리)도 맞음(꼬리가 없는 그림이면 보라 점이 엉덩이에 모여 있음).
  <b>꼬리만 틀림</b>: 다리는 맞는데 꼬리가 틀림. <b>틀림</b>: 다리가 틀리면 버립니다. 다리 번호, 무릎 자리, 속이 빈 점(몸통)은 따지지 않습니다.</div>
<script>
const DATA = __DATA__, JOINTS = __JOINTS__, $ = id => document.getElementById(id), NS = "http://www.w3.org/2000/svg";
let labels = {}, names = [], cur = 0, shownAt = 0, timer = 0;
const color = n => n.endsWith("_b") ? "#d23" : n.endsWith("_f") ? "#25d" : n.startsWith("tail") ? "#93c" : "#1a8f3c";
function save() {
  clearTimeout(timer);
  timer = setTimeout(() => fetch("labels", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(labels) })
    .catch(() => { $("state").textContent = "파일 저장 실패 (서버가 꺼졌나요)"; }), 300);
}
function show() {
  if (!names.length) { $("name").textContent = "초안이 달린 그림이 없습니다. 먼저 머리 쪽을 누르세요 (/facing)"; return; }
  const n = names[cur], r = labels[n], [w, h] = DATA[n], svg = $("svg"), s = Math.min(1.25, 640 / Math.max(w, h));
  svg.setAttribute("width", w * s); svg.setAttribute("height", h * s); svg.setAttribute("viewBox", `0 0 ${w} ${h}`); svg.innerHTML = "";
  const img = document.createElementNS(NS, "image"); img.setAttribute("href", "img/" + n); img.setAttribute("width", w); img.setAttribute("height", h); svg.appendChild(img);
  if ($("lines").checked) {
    const R = Math.max(w, h) / 90, j = r.joints;
    for (const [name, parent] of JOINTS) if (parent && j[name] && j[parent]) {
      const l = document.createElementNS(NS, "line"), p = j[name], q = j[parent];
      l.setAttribute("x1", q[0]); l.setAttribute("y1", q[1]); l.setAttribute("x2", p[0]); l.setAttribute("y2", p[1]);
      l.setAttribute("stroke", color(name)); l.setAttribute("stroke-width", R / 2); l.setAttribute("opacity", .85); svg.appendChild(l);
    }
    for (const [name] of JOINTS) if (j[name]) {
      const c = document.createElementNS(NS, "circle"), body = ["hip", "torso", "neck"].includes(name), knee = name.includes("knee") || name === "tail_mid";
      c.setAttribute("cx", j[name][0]); c.setAttribute("cy", j[name][1]); c.setAttribute("r", knee ? R * .6 : R);
      c.setAttribute("fill", body ? "#fff" : color(name)); c.setAttribute("stroke", body ? color(name) : "#fff"); c.setAttribute("stroke-width", body ? 3 : 1.5);
      svg.appendChild(c);
    }
  }
  $("name").textContent = `${cur + 1}. ${n.replace(".png", "")}` + (r.found === false ? " (규칙이 다리를 못 찾아 기본 뼈대)" : "");
  for (const k of ["ok", "tail", "bad"]) $(k).className = r.judge === k ? "on" : "";
  const c = { ok: 0, tail: 0, bad: 0 }; names.forEach(x => { if (labels[x].judge) c[labels[x].judge]++; });
  $("count").textContent = `고른 그림 ${c.ok + c.tail + c.bad} / ${names.length} · 맞음 ${c.ok} · 꼬리만 틀림 ${c.tail} · 틀림 ${c.bad}`;
  shownAt = Date.now();
}
function answer(v) {
  if (!names.length) return;
  const r = labels[names[cur]];
  r.t_judge = (r.t_judge || 0) + Math.min(Date.now() - shownAt, 60000);
  r.judge = v; r.done = v !== "bad"; r.tail_unknown = v === "tail";
  save();
  if (cur < names.length - 1) cur++;
  show();
}
$("ok").onclick = () => answer("ok"); $("tail").onclick = () => answer("tail"); $("bad").onclick = () => answer("bad");
$("back").onclick = () => { if (cur > 0) cur--; show(); };
$("lines").onchange = show;
document.addEventListener("click", e => { if (e.target.tagName === "BUTTON" || e.target.tagName === "INPUT") e.target.blur(); });
addEventListener("keydown", e => {
  const k = e.key;
  if (k === "ArrowRight") answer("ok"); else if (k === "ArrowDown") answer("tail"); else if (k === "ArrowLeft") answer("bad");
  else if (k === "ArrowUp" || k === "Backspace") $("back").onclick();
  else if (k === " ") { $("lines").checked = !$("lines").checked; show(); } else return;
  e.preventDefault();
});
fetch("labels").then(r => r.json()).then(got => {
  labels = got || {};
  // 머리 쪽을 누르고 초안이 달렸고, 사람이 손으로 고쳐 끝낸 것이 아닌 그림만
  names = Object.keys(DATA).sort().filter(n => { const r = labels[n]; return r && r.use !== false && r.facing && r.draft && (r.judge || !r.done); });
  const first = names.findIndex(n => !labels[n].judge); cur = first < 0 ? Math.max(0, names.length - 1) : first;
  show();
}).catch(() => { $("state").textContent = "서버에 닿지 않습니다"; });
</script></body></html>
"""

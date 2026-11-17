"""시험 세트 정답 표시 도구 만들기 (2026-11-17).

data/testset/quadruped/auto.json(규칙이 단 초안)을 읽어 한 장짜리 HTML 을 만든다. 브라우저에서 그냥 연다(서버 필요 없음).
  - 점을 끌어 옮긴다. 점을 오른쪽 클릭하면 「안 보임」(그림에 없는 부위, 예: 꼬리 없음)으로 바뀐다.
  - 그림마다 「시험에 씀 / 뺌」(네 발로 선 그림이 아니면 뺌)과 머리 쪽(왼쪽 · 오른쪽)을 고른다.
  - 그림마다 동물 종류를 고른다. 서비스 카드의 네 발 예시(강아지 · 고양이 · 공룡)가 맨 앞. 종류별로 따로 채점하려는 것.
    목록에 없는 동물은 「기타」를 고르고 옆 칸에 이름을 적는다(kind_note).
  - 돌아간 그림은 회전 단추(90도 · 5도)로 바로 세운다. 점은 그림과 함께 돈다.
    정답 좌표는 늘 원본 PNG 기준으로 저장하고, 바로 세우는 각도(rotate, 시계 방향 도)를 따로 적는다.
  - 머리(head) 관절은 서비스 정의에 없는 것을 이 실험에서 더했다(기린처럼 목이 긴 그림). 초안은 어깨 → 목 방향으로 조금 더 간 자리.
  - 꼬리가 없거나 다리가 넷보다 적게 그려진 그림은 「없는 부위」 단추로 그 부위를 통째로 「안 보임」으로 한다.
    다리 약속: 앞 · 뒤 각각 한 개만 그렸으면 「1」에 놓고 「2」를 없음으로. 두 개면 몸 가운데 쪽이 1, 바깥쪽(머리 끝 · 꼬리 끝 쪽)이 2.
  - 고친 것은 브라우저에 바로 저장되고, 「내보내기」를 누르면 labels_quadruped.json 을 받는다.
    받은 파일을 data/testset/quadruped/labels.json 으로 옮기면 그것이 정답이다.

  - 「머리 쪽」을 고르고 초안을 다시 달면 규칙이 그쪽을 머리로 본다(머리 · 앞다리가 그쪽, 꼬리 · 뒷다리가 반대쪽).
    규칙이 머리 쪽을 거꾸로 짐작한 그림을 바로잡는 용도. 「모름」이면 규칙이 짐작하고, 짐작한 쪽을 칸에 채워 준다.
  - 「이 각도로 초안 다시 달기」와 파일 자동 저장은 tools/label_server.py 로 열었을 때만 된다(http://127.0.0.1:8765/).
    파일을 그냥 열면 점 고치기 · 회전 · 내보내기만 된다. 두 방식은 브라우저 저장소가 달라서, 옮길 때는 내보내기 → 가져오기.

  - 그림마다 화면에 떠 있던 시간(t_fix, ms)과 규칙이 단 초안(draft)을 같이 적어 둔다. 고치는 데 드는 시간 · 초안이 그대로 통과한 비율을 재려는 것.
  - 몸통 세 점(엉덩이 · 어깨 · 목)은 끌 수 없다(2026-11-17 규칙 자리로 통일). 다리 뿌리를 옮기면 서버(/body, tools/body_rule.py)가 다시 놓는다.
    새 묶음(quick 표시가 있는 기록)은 무릎 · 꼬리 가운데도 손대기 전에는 양 끝의 한가운데로 따라간다. Enter = 이 그림 끝.
  - 다른 그림 묶음에도 쓴다(tools/sets.py). qd_pilot 은 먼저 「머리 쪽 누르기」 화면(/facing)에서 방향을 누르면 그 방향으로 초안이 달린다.

    python tools/make_labeler.py [--set 이름]   → data/testset/label_quadruped.html (또는 data/label_qd_pilot.html · facing_qd_pilot.html)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from facing_page import FACING  # noqa: E402
from judge_page import JUDGE  # noqa: E402
from sets import page_path, pick  # noqa: E402

# 관절 이름 · 화면 이름은 drawtale-ai runtime/ai_server/forms/quadruped.json (dev 4c2147f) 그대로.
# 부모는 화면에 선을 긋는 용도라 다리를 몸통 쪽에 이었다(원본은 다리 위 관절의 부모가 root).
# head 는 서비스 정의에 없고 이 실험에서 더한 관절이다 (2026-11-17, 목이 긴 동물)
# 동물 종류: 앞 셋은 서비스 형태 카드(4족형)의 예시 동물 (forms/quadruped.json examples)
KINDS = ["강아지", "고양이", "공룡", "말", "소", "돼지", "양", "기린", "코끼리", "호랑이 · 사자", "악어 · 도마뱀", "거북", "쥐 · 토끼", "상상 동물", "기타"]

JOINTS = [("hip", None, "엉덩이"), ("torso", "hip", "어깨"), ("neck", "torso", "목"), ("head", "neck", "머리"),
          ("right_hip_b", "hip", "뒷다리 1 위"), ("right_knee_b", "right_hip_b", "뒷다리 1 무릎"), ("right_foot_b", "right_knee_b", "뒷다리 1 발"),
          ("left_hip_b", "hip", "뒷다리 2 위"), ("left_knee_b", "left_hip_b", "뒷다리 2 무릎"), ("left_foot_b", "left_knee_b", "뒷다리 2 발"),
          ("right_hip_f", "torso", "앞다리 1 위"), ("right_knee_f", "right_hip_f", "앞다리 1 무릎"), ("right_foot_f", "right_knee_f", "앞다리 1 발"),
          ("left_hip_f", "torso", "앞다리 2 위"), ("left_knee_f", "left_hip_f", "앞다리 2 무릎"), ("left_foot_f", "left_knee_f", "앞다리 2 발"),
          ("tail", "hip", "꼬리 뿌리"), ("tail_mid", "tail", "꼬리 가운데"), ("tail_tip", "tail_mid", "꼬리 끝")]

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>__TITLE__ 정답 표시</title>
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
  circle.auto { fill: #fff !important; stroke-width: 3; cursor: default; }
  text { font-size: 11px; paint-order: stroke; stroke: #fff; stroke-width: 3px; pointer-events: none; }
  button { font: inherit; padding: 4px 10px; }
  button.grp.off { background: #bbb; color: #fff; text-decoration: line-through; }
  #help { color: #555; font-size: 13px; }
</style></head><body>
<div id="list"></div>
<div id="main">
  <div id="bar">
    <b id="name"></b>
    <label><input type="checkbox" id="use"> 시험에 씀(네 발로 선 그림)</label>
    <label>머리 쪽 <select id="facing"><option value="">모름</option><option value="left">왼쪽</option><option value="right">오른쪽</option></select></label>
    <label>동물 <select id="kind"><option value="">안 고름</option>__KINDS__</select>
      <input id="kindnote" placeholder="기타: 무슨 동물인지 적기" style="width:170px;display:none"></label>
    <span>회전 <button id="rl90" title="왼쪽으로 90도">↺ 90°</button> <button id="rl5">↺ 5°</button>
      <b id="angle">0°</b> <button id="rr5">↻ 5°</button> <button id="rr90" title="오른쪽으로 90도">↻ 90°</button></span>
    <label><input type="checkbox" id="names" checked> 이름 보기</label>
    <button id="reset">초안으로 되돌리기</button>
    <button id="redraft" title="지금 세운 각도와 고른 머리 쪽으로 규칙을 다시 돌립니다">이 각도 · 머리 쪽으로 초안 다시 달기</button>
    <button id="done">이 그림 끝 → 다음</button>
    <button id="export">내보내기</button>
    <button id="import">가져오기</button><input type="file" id="file" accept=".json" style="display:none">
    <span id="status" style="color:#b35c00"></span>
    <span id="count"></span>
  </div>
  <div id="bar"><span>없는 부위(누르면 통째로 안 보임, 다시 누르면 되살림):</span>
    <button class="grp" data-g="tail">꼬리</button>
    <button class="grp" data-g="_f1">앞다리 1</button><button class="grp" data-g="_f2">앞다리 2</button>
    <button class="grp" data-g="_b1">뒷다리 1</button><button class="grp" data-g="_b2">뒷다리 2</button>
    <button class="grp" data-g="head">머리</button>
    <span id="help2" style="color:#555;font-size:13px">다리를 하나만 그렸으면 「1」에 놓고 「2」를 없음으로. 두 개면 몸 가운데 쪽이 1, 바깥쪽이 2.</span></div>
  <div id="bar"><span id="help">돌아간 그림은 먼저 회전 단추로 바로 세우고, 머리가 반대쪽에 놓였으면 「머리 쪽」을 고른 뒤 「초안 다시 달기」를 누릅니다. 점을 끌어 옮깁니다. <b>속이 빈 점(엉덩이 · 어깨 · 목)은 끌지 않습니다: 다리 뿌리를 맞추면 자동으로 놓입니다.</b> 다리 1 · 2 번호는 바뀌어도 됩니다(한 다리의 점 셋만 같은 다리 위에). Enter = 이 그림 끝. 그림에 없는 부위는 점을 오른쪽 클릭해 「안 보임」(회색)으로. 빨강 = 뒷다리, 파랑 = 앞다리, 초록 = 몸통 · 목 · 머리, 보라 = 꼬리. 고친 것은 바로 저장됩니다.</span></div>
  <div id="stage"><svg id="svg"></svg></div>
</div>
<script>
const DATA = __DATA__, JOINTS = __JOINTS__, KEY = "creature-pose-__SET__-labels-v1";
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const names = Object.keys(DATA).sort();
let cur = Math.max(0, names.indexOf(decodeURIComponent(location.hash.slice(1))));   // 주소 끝에 #그림이름 을 붙이면 그 그림부터
const $ = id => document.getElementById(id), NS = "http://www.w3.org/2000/svg";
const color = n => n.endsWith("_b") ? "#d23" : n.endsWith("_f") ? "#25d" : n.startsWith("tail") ? "#93c" : n === "head" ? "#0a5c2a" : "#1a8f3c";
const SERVED = location.protocol.startsWith("http");   // label_server.py 로 열었나
let timer = 0;
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {}
  if (!SERVED) return;
  clearTimeout(timer);   // 끌 때마다 보내지 않게 조금 모아서 파일에 저장
  timer = setTimeout(() => fetch("labels", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(labels) })
    .then(r => r.json()).then(() => say("파일에 저장됨")).catch(() => say("파일 저장 실패 (서버가 꺼졌나요)")), 500);
}
function say(t) { document.getElementById("status").textContent = t; }
function draft(n, name, j) {
  const a = DATA[n], p = a.joints[name];
  if (p) return [p[0], p[1], 1];
  if (name === "head" && j.neck && j.torso) {   // 어깨 → 목 방향으로 그 길이의 0.8배 더
    const x = j.neck[0] + (j.neck[0] - j.torso[0]) * .8, y = j.neck[1] + (j.neck[1] - j.torso[1]) * .8;
    return [Math.round(Math.max(0, Math.min(a.width, x))), Math.round(Math.max(0, Math.min(a.height, y))), 1];
  }
  return [a.width / 2, a.height / 2, 1];
}
function rec(n) {
  if (!labels[n]) labels[n] = { use: true, facing: "", done: false, rotate: 0, joints: {} };
  if (labels[n].kind === undefined && DATA[n].kind) { labels[n].kind = DATA[n].kind; if (DATA[n].kind_note) labels[n].kind_note = DATA[n].kind_note; }   // 종류를 아는 묶음
  const j = labels[n].joints;
  if (labels[n].kind === "그 밖") labels[n].kind = "기타";   // 예전 이름
  for (const [name] of JOINTS) if (!j[name]) j[name] = draft(n, name, j);   // 예전에 저장한 것에 없는 관절(머리)도 채운다
  return labels[n];
}
const GROUPS = { tail: ["tail", "tail_mid", "tail_tip"], head: ["head"],
  _f1: ["right_hip_f", "right_knee_f", "right_foot_f"], _f2: ["left_hip_f", "left_knee_f", "left_foot_f"],
  _b1: ["right_hip_b", "right_knee_b", "right_foot_b"], _b2: ["left_hip_b", "left_knee_b", "left_foot_b"] };
const BODY = ["hip", "torso", "neck"];   // 몸통 세 점은 사람이 놓지 않는다: 다리 뿌리와 몸 모양에서 규칙 자리로 계산 (tools/body_rule.py)
let refresh = () => {}, bodyTimer = 0;
function follow(r) {   // 줄인 표시: 손대지 않은 무릎 · 꼬리 가운데는 양 끝의 한가운데로 따라간다
  const m = r.manual || {}, half = (k, a, b) => { if (!m[k]) { r.joints[k][0] = Math.round((a[0] + b[0]) / 2); r.joints[k][1] = Math.round((a[1] + b[1]) / 2); } };
  for (const s of ["right", "left"]) for (const e of ["f", "b"]) half(`${s}_knee_${e}`, r.joints[`${s}_hip_${e}`], r.joints[`${s}_foot_${e}`]);
  half("tail_mid", r.joints.tail, r.joints.tail_tip);
}
function askBody(n) {
  if (!SERVED) return;
  clearTimeout(bodyTimer);
  bodyTimer = setTimeout(() => {
    const r = rec(n);
    fetch("body", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: n, rotate: r.rotate || 0, joints: r.joints }) })
      .then(x => x.json()).then(x => {
        if (!x.ok) { say("몸통 자리를 계산하지 못했습니다: " + x.message); return; }
        for (const k of BODY) { r.joints[k][0] = x.joints[k][0]; r.joints[k][1] = x.joints[k][1]; }
        r.body_auto = true; save(); if (names[cur] === n) refresh();
      }).catch(() => {});
  }, 120);
}
function groupButtons() {
  const r = rec(names[cur]);
  document.querySelectorAll("button.grp").forEach(b => b.classList.toggle("off", GROUPS[b.dataset.g].every(k => !r.joints[k][2])));
}
function drawList() {
  $("list").innerHTML = "";
  names.forEach((n, i) => {
    const d = document.createElement("div"), r = labels[n];
    d.textContent = n.replace(".png", "") + (r && r.kind ? " · " + (r.kind === "기타" && r.kind_note ? r.kind_note : r.kind) : "") + ((r && r.found !== undefined ? r.found : DATA[n].found) ? "" : " (초안 없음)");
    d.className = (i === cur ? "on " : "") + (r && r.done ? "done " : "") + (r && !r.use ? "skip" : "");
    d.onclick = () => { cur = i; show(); };
    $("list").appendChild(d);
  });
  const done = names.filter(n => labels[n] && labels[n].done).length;
  $("count").textContent = `끝낸 그림 ${done} / ${names.length}`;
}
let shownAt = 0, shownName = null;
function tick() {   // 그림이 화면에 떠 있던 시간을 더한다 (자리를 비운 것은 한 번에 2분까지만)
  const r = shownName && labels[shownName];
  if (r && !r.done) r.t_fix = (r.t_fix || 0) + Math.min(Date.now() - shownAt, 120000);
  shownAt = Date.now();
}
function show() {
  tick(); shownName = names[cur];
  const n = names[cur], a = DATA[n], r = rec(n), svg = $("svg");
  // 그림을 rotate 도(시계 방향) 돌려 보여 준다. 점은 원본 좌표로 두고 화면 좌표로만 바꿔 그린다
  const deg = r.rotate || 0, th = deg * Math.PI / 180, co = Math.cos(th), si = Math.sin(th);
  const W = Math.abs(a.width * co) + Math.abs(a.height * si), H = Math.abs(a.width * si) + Math.abs(a.height * co);
  const fwd = p => { const dx = p[0] - a.width / 2, dy = p[1] - a.height / 2; return [W / 2 + dx * co - dy * si, H / 2 + dx * si + dy * co]; };
  const inv = (X, Y) => { const dx = X - W / 2, dy = Y - H / 2; return [a.width / 2 + dx * co + dy * si, a.height / 2 - dx * si + dy * co]; };
  const s = Math.min(1.6, 900 / Math.max(W, H));   // 작은 그림(Quick, Draw! 512)은 키워서
  svg.setAttribute("width", W * s); svg.setAttribute("height", H * s);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = "";
  const img = document.createElementNS(NS, "image");
  img.setAttribute("href", "img/" + n); img.setAttribute("width", a.width); img.setAttribute("height", a.height);
  img.setAttribute("transform", `translate(${W / 2} ${H / 2}) rotate(${deg}) translate(${-a.width / 2} ${-a.height / 2})`);
  svg.appendChild(img);
  $("angle").textContent = deg + "°";
  const lines = {}, R = Math.max(W, H) / 110;
  for (const [name, parent] of JOINTS) if (parent) {
    const l = document.createElementNS(NS, "line");
    l.setAttribute("stroke", color(name)); l.setAttribute("stroke-width", R / 2.2);
    svg.appendChild(l); lines[name] = l;
  }
  function place() {
    for (const [name, parent] of JOINTS) if (parent) {
      const p = r.joints[name], q = r.joints[parent], l = lines[name], P = fwd(p), Q = fwd(q);
      l.setAttribute("x1", Q[0]); l.setAttribute("y1", Q[1]); l.setAttribute("x2", P[0]); l.setAttribute("y2", P[1]);
      l.setAttribute("opacity", p[2] && q[2] ? .9 : .15);
    }
  }
  place();
  const puts = [];
  refresh = () => { puts.forEach(f => f()); place(); };
  for (const [name, , label] of JOINTS) {
    const p = r.joints[name], c = document.createElementNS(NS, "circle"), t = document.createElementNS(NS, "text");
    const auto = BODY.includes(name);
    c.setAttribute("r", R); c.setAttribute("fill", color(name)); if (auto) c.style.stroke = color(name);
    const put = () => { const P = fwd(p); c.setAttribute("cx", P[0]); c.setAttribute("cy", P[1]); t.setAttribute("x", P[0] + R * 1.3); t.setAttribute("y", P[1] + 4);
                        c.setAttribute("class", (p[2] ? "" : "gone") + (auto ? " auto" : "")); };
    t.textContent = label; t.style.display = $("names").checked ? "" : "none"; t.style.fontSize = Math.max(11, R * 1.6) + "px";
    put(); puts.push(put);
    c.addEventListener("pointerdown", e => {
      if (e.button !== 0 || auto) return;
      c.setPointerCapture(e.pointerId);
      if (/knee|tail_mid/.test(name)) (r.manual = r.manual || {})[name] = 1;   // 손댄 무릎 · 꼬리 가운데는 더 따라가지 않는다
      const move = ev => {
        const b = svg.getBoundingClientRect();
        const o = inv((ev.clientX - b.left) / b.width * W, (ev.clientY - b.top) / b.height * H);
        p[0] = Math.round(Math.max(0, Math.min(a.width, o[0])));
        p[1] = Math.round(Math.max(0, Math.min(a.height, o[1])));
        if (r.quick) follow(r);
        refresh();
      };
      const up = () => { c.removeEventListener("pointermove", move); c.removeEventListener("pointerup", up); save(); askBody(n); };
      c.addEventListener("pointermove", move); c.addEventListener("pointerup", up);
    });
    c.addEventListener("contextmenu", e => { e.preventDefault(); if (auto) return; p[2] = p[2] ? 0 : 1; put(); place(); save(); groupButtons(); askBody(n); });
    svg.appendChild(c); svg.appendChild(t);
  }
  $("name").textContent = `${n}  (${a.source}: ${a.note})`;
  $("use").checked = r.use; $("facing").value = r.facing; $("kind").value = r.kind || "";
  $("kindnote").style.display = r.kind === "기타" ? "" : "none"; $("kindnote").value = r.kind_note || "";
  groupButtons();
  drawList();
  if (!r.body_auto && r.use !== false) askBody(n);
}
$("use").onchange = e => { rec(names[cur]).use = e.target.checked; save(); drawList(); };
$("facing").onchange = e => { rec(names[cur]).facing = e.target.value; save();
  say(SERVED ? "머리 쪽을 바꿨습니다. 점을 그쪽에 맞춰 다시 놓으려면 「초안 다시 달기」를 누르세요 (손으로 고친 점은 새 초안으로 바뀝니다)" : ""); };
$("kind").onchange = e => { rec(names[cur]).kind = e.target.value; $("kindnote").style.display = e.target.value === "기타" ? "" : "none"; save(); drawList(); };
$("kindnote").oninput = e => { rec(names[cur]).kind_note = e.target.value; save(); drawList(); };
$("names").onchange = show;
document.querySelectorAll("button.grp").forEach(b => b.onclick = () => {
  const r = rec(names[cur]), ks = GROUPS[b.dataset.g], off = ks.every(k => !r.joints[k][2]);
  ks.forEach(k => { r.joints[k][2] = off ? 1 : 0; });
  save(); show(); askBody(names[cur]);
});
const turn = d => { const r = rec(names[cur]); r.rotate = (((r.rotate || 0) + d) % 360 + 360) % 360; save(); show(); askBody(names[cur]); };
$("rl90").onclick = () => turn(-90); $("rr90").onclick = () => turn(90);
$("rl5").onclick = () => turn(-5); $("rr5").onclick = () => turn(5);
$("reset").onclick = () => {
  const r = labels[names[cur]];
  if (r && r.draft) { r.joints = {}; for (const k in r.draft) r.joints[k] = [r.draft[k][0], r.draft[k][1], 1]; r.done = false; }   // 다시 단 초안이 있으면 그것으로
  else delete labels[names[cur]];
  save(); show();
};
$("done").onclick = () => {
  tick(); rec(names[cur]).done = true; save();
  let k = cur + 1;   // 뺀 그림은 건너뛴다
  while (k < names.length && labels[names[k]] && labels[names[k]].use === false) k++;
  if (k < names.length) cur = k;
  show();
};
$("redraft").onclick = () => {
  if (!SERVED) { say("이 단추는 python tools/label_server.py 로 띄운 주소(http://127.0.0.1:8765/)에서만 됩니다"); return; }
  const n = names[cur], r = rec(n);
  say("규칙을 다시 돌리는 중…"); $("redraft").disabled = true;
  fetch("redraft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: n, rotate: r.rotate || 0, facing: r.facing || "" }) })
    .then(x => x.json()).then(x => {
      $("redraft").disabled = false;
      if (!x.ok) { say("초안 못 닮: " + x.message); return; }
      for (const [name] of JOINTS) if (x.joints[name]) r.joints[name] = [x.joints[name][0], x.joints[name][1], 1];
      delete r.joints.head; rec(n);   // 머리는 새 목 · 어깨에서 다시 어림
      r.draft = {}; for (const k in r.joints) r.draft[k] = [r.joints[k][0], r.joints[k][1]];   // 나중에 얼마나 고쳤는지 견줄 초안
      r.found = !!x.found;
      if (!r.facing && x.facing) r.facing = x.facing;   // 규칙이 짐작한 머리 쪽을 칸에 채운다
      r.done = false; save(); show(); askBody(n);
      say(x.found ? "초안을 다시 달았습니다" : "규칙이 다리를 못 찾아 기본 뼈대를 놓았습니다");
    }).catch(() => { $("redraft").disabled = false; say("서버에 닿지 않습니다"); });
};
// Enter = 이 그림 끝 → 다음. 단추를 누른 뒤 Enter 가 그 단추를 다시 누르지 않게 초점을 뗀다
document.addEventListener("click", e => { if (e.target.tagName === "BUTTON") e.target.blur(); });
addEventListener("keydown", e => { if (e.key === "Enter" && !["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName)) { e.preventDefault(); $("done").click(); } });
$("import").onclick = () => $("file").click();
$("file").onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  f.text().then(t => {
    const got = JSON.parse(t); let k = 0;
    for (const n of names) if (got[n] && got[n].joints) { labels[n] = { use: got[n].use !== false, facing: got[n].facing || "", kind: got[n].kind === "그 밖" ? "기타" : (got[n].kind || ""), kind_note: got[n].kind_note || "", done: !!got[n].done, rotate: got[n].rotate || 0, joints: got[n].joints }; k++; }
    save(); show(); say(k + "장 가져옴");
  }).catch(() => say("파일을 읽지 못했습니다"));
  e.target.value = "";
};
$("export").onclick = () => {
  const out = {};
  for (const n of names) if (labels[n] && labels[n].done) out[n] = Object.assign({ width: DATA[n].width, height: DATA[n].height, source: DATA[n].source }, labels[n]);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], { type: "application/json" }));
  a.download = "labels_quadruped.json"; a.click();
};
if (SERVED) {
  // 파일(labels.json)에 저장된 것이 있으면 그것이 기준
  fetch("labels").then(r => r.json()).then(got => { if (Object.keys(got).length) { labels = got; try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {} } show(); })
    .catch(() => show());
} else show();
</script></body></html>
"""


def main() -> None:
    name, SET, _, title = pick()
    auto = json.load(open(SET / "auto.json", encoding="utf-8"))
    fill = lambda t: t.replace("__SET__", name).replace("__TITLE__", title)  # noqa: E731
    page = fill(PAGE).replace("__KINDS__", "".join(f"<option>{k}</option>" for k in KINDS)).replace("__DATA__", json.dumps(auto, ensure_ascii=False)).replace(
        "__JOINTS__", json.dumps([list(j) for j in JOINTS], ensure_ascii=False))
    out = page_path(SET)
    out.write_text(page, encoding="utf-8")
    print(out, len(auto), "장")
    sizes = {n: [a["width"], a["height"]] for n, a in auto.items()}
    out2 = page_path(SET, "facing")
    out2.write_text(fill(FACING).replace("__DATA__", json.dumps(sizes, ensure_ascii=False)), encoding="utf-8")
    print(out2)
    out3 = page_path(SET, "judge")
    out3.write_text(fill(JUDGE).replace("__DATA__", json.dumps(sizes, ensure_ascii=False)).replace(
        "__JOINTS__", json.dumps([list(j) for j in JOINTS if j[0] != "head"], ensure_ascii=False)), encoding="utf-8")
    print(out3)


if __name__ == "__main__":
    main()

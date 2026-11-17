"""「머리 쪽 누르기」 화면 (2026-11-17). make_labeler.py 가 이 틀로 facing_<묶음>.html 을 만들고, label_server.py 가 /facing 으로 보여 준다.

그림을 한 장씩 크게 보여 주고 키 하나로 답한다.
  ←  머리가 왼쪽      →  머리가 오른쪽      ↓ (또는 X)  못 씀      ↑ (또는 Backspace)  앞 그림으로
「못 씀」 = 네 발로 선 몸 전체가 옆에서 보이는 그림이 아님 (얼굴만, 정면, 무엇인지 모름, 다리가 없음).
방향을 누르면 뒤에서 그 방향으로 규칙을 돌려 초안을 달아 둔다(한 번에 한 장씩 차례로). 누르는 데 걸린 시간(t_facing, ms)도 적는다.
다 누르고 초안이 다 달리면 고치기 화면(/)으로 간다. 두 화면을 같이 열어 두고 번갈아 고치지 않는다(서로 덮어쓴다).
"""

FACING = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>__TITLE__ 머리 쪽 누르기</title>
<style>
  body { margin: 0; font: 15px/1.6 system-ui, sans-serif; background: #f4f4f1; color: #222; text-align: center; }
  #top { padding: 10px; background: #fff; border-bottom: 1px solid #ccc; }
  #pic { margin: 14px auto 8px; background: #fff; box-shadow: 0 0 0 1px #ccc; display: block; max-width: 92vw; max-height: 62vh; }
  button { font: inherit; padding: 10px 18px; margin: 4px; min-width: 150px; }
  button.on { background: #dbe9ff; border-color: #25d; }
  #help { color: #555; font-size: 13px; max-width: 760px; margin: 8px auto; }
  #state { color: #b35c00; }
</style></head><body>
<div id="top"><b id="name"></b> &nbsp; <span id="count"></span> &nbsp; <span id="state"></span> &nbsp; <a href="./" id="go">고치기 화면으로</a></div>
<img id="pic" alt="">
<div>
  <button id="left">← 머리가 왼쪽</button>
  <button id="bad">↓ 못 씀</button>
  <button id="right">머리가 오른쪽 →</button>
</div>
<div><button id="back" style="min-width:0">↑ 앞 그림으로</button></div>
<div id="help">키보드 화살표로 누릅니다. 「못 씀」은 네 발로 선 몸 전체가 옆에서 보이는 그림이 아닐 때(얼굴만 있음, 정면, 무엇인지 모르겠음, 다리가 없음).
  방향을 누르면 뒤에서 그 방향으로 규칙이 초안을 달아 둡니다. 다 누른 뒤 「초안 대기 0」이 되면 고치기 화면으로 가세요.</div>
<script>
const DATA = __DATA__, names = Object.keys(DATA).sort(), $ = id => document.getElementById(id);
let labels = {}, cur = 0, shownAt = 0, timer = 0, busy = false;
const queue = [];
function rec(n) { if (!labels[n]) labels[n] = { use: true, facing: "", done: false, rotate: 0, joints: {}, quick: true }; return labels[n]; }   // quick = 줄인 표시 방식
function save() {
  clearTimeout(timer);
  timer = setTimeout(() => fetch("labels", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(labels) })
    .catch(() => { $("state").textContent = "파일 저장 실패 (서버가 꺼졌나요)"; }), 300);
}
function answered(n) { const r = labels[n]; return !!(r && (r.use === false || r.facing)); }
function status() {
  const done = names.filter(answered).length, drafted = names.filter(n => labels[n] && labels[n].draft).length;
  const failed = names.filter(n => labels[n] && labels[n].draft_error).length;
  $("count").textContent = `누른 그림 ${done} / ${names.length} · 초안 달림 ${drafted} · 초안 대기 ${queue.length + (busy ? 1 : 0)}` + (failed ? ` · 초안 실패 ${failed}` : "");
  $("go").style.fontWeight = done === names.length && !queue.length && !busy ? "bold" : "";
}
function show() {
  const n = names[cur], r = labels[n];
  $("pic").src = "img/" + n; $("name").textContent = `${cur + 1}. ${n.replace(".png", "")}`;
  $("left").className = r && r.use !== false && r.facing === "left" ? "on" : "";
  $("right").className = r && r.use !== false && r.facing === "right" ? "on" : "";
  $("bad").className = r && r.use === false ? "on" : "";
  shownAt = Date.now(); status();
}
function work() {   // 초안 달기: 한 번에 한 장
  if (busy || !queue.length) { status(); return; }
  const n = queue.shift(), r = rec(n), facing = r.facing;
  if (r.use === false || !facing || r.done) { work(); return; }
  busy = true; status();
  fetch("redraft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: n, rotate: 0, facing }) })
    .then(x => x.json()).then(x => {
      if (x.ok && r.facing === facing && !r.done) {
        r.joints = {}; r.draft = {};
        for (const k in x.joints) { r.joints[k] = [x.joints[k][0], x.joints[k][1], 1]; r.draft[k] = [x.joints[k][0], x.joints[k][1]]; }
        r.draft_facing = facing; r.found = !!x.found; delete r.draft_error; save();
      } else if (!x.ok) { r.draft_error = x.message || "실패"; save(); }
    }).catch(() => { r.draft_error = "서버에 닿지 않음"; })
    .finally(() => { busy = false; work(); });
}
function answer(v) {
  const n = names[cur], r = rec(n);
  r.t_facing = (r.t_facing || 0) + Math.min(Date.now() - shownAt, 60000);
  if (v === "bad") { r.use = false; r.facing = ""; }
  else {
    r.use = true; r.facing = v;
    if (r.draft_facing !== v && !r.done) { delete r.draft; if (!queue.includes(n)) queue.push(n); work(); }
  }
  save();
  if (cur < names.length - 1) cur++;
  show();
}
$("left").onclick = () => answer("left"); $("right").onclick = () => answer("right"); $("bad").onclick = () => answer("bad");
$("back").onclick = () => { if (cur > 0) cur--; show(); };
addEventListener("keydown", e => {
  const k = e.key;
  if (k === "ArrowLeft") answer("left"); else if (k === "ArrowRight") answer("right");
  else if (k === "ArrowDown" || k === "x" || k === "X") answer("bad");
  else if (k === "ArrowUp" || k === "Backspace") $("back").onclick(); else return;
  e.preventDefault();
});
fetch("labels").then(r => r.json()).then(got => {
  labels = got || {};
  const first = names.findIndex(n => !answered(n)); cur = first < 0 ? names.length - 1 : first;
  for (const n of names) { const r = labels[n]; if (r && r.use !== false && r.facing && !r.draft && !r.done) queue.push(n); }   // 지난번에 못 단 초안
  show(); work();
}).catch(() => { $("state").textContent = "서버에 닿지 않습니다 (python tools/label_server.py --set __SET__)"; show(); });
</script></body></html>
"""

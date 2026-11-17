"""이미 표시한 정답의 몸통 세 점을 규칙 자리로 다시 놓는다 (2026-11-17, 사용자 결정: 규칙 자리로 통일).

사람이 놓았던 엉덩이 · 어깨 · 목을 버리고, 사람이 맞춘 다리 뿌리와 몸 마스크에서 계산한 자리(tools/body_rule.py)로 바꾼다.
다른 관절은 그대로 둔다. 바꾸기 전 파일은 labels.before_body.json 으로 남긴다(처음 한 번만).
마스크가 없는 그림은 로컬 AI 서버로 분석해 만든다(장당 약 3초).

    work/venv/Scripts/python tools/normalize_body.py [--set 이름]
"""

import json
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from body_rule import BODY, body_points  # noqa: E402
from sets import pick  # noqa: E402


def main() -> None:
    _, folder, _, _ = pick()
    path = folder / "labels.json"
    keep = folder / "labels.before_body.json"
    if not keep.exists():
        shutil.copy(path, keep)
    labels = json.load(open(path, encoding="utf-8"))
    moved = []
    for name, r in labels.items():
        if r.get("use") is False or not r.get("done") or not r.get("joints"):
            continue
        got = body_points(folder, name, float(r.get("rotate") or 0), r["joints"])
        if not got:
            print("  못 놓음(앞 · 뒤 다리 없음 또는 마스크 없음):", name)
            continue
        j = r["joints"]
        vis = [v for k, v in j.items() if k != "head" and v[2]]
        size = math.hypot(max(v[0] for v in vis) - min(v[0] for v in vis), max(v[1] for v in vis) - min(v[1] for v in vis)) or 1.0
        for k in BODY:
            moved.append(math.hypot(j[k][0] - got[k][0], j[k][1] - got[k][1]) / size)
            j[k] = [got[k][0], got[k][1], 1]
        r["body_auto"] = True
    tmp = path.with_suffix(".tmp")
    json.dump(labels, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tmp.replace(path)
    if moved:
        moved.sort()
        print(f"{len(moved) // 3}장의 몸통 세 점을 다시 놓음. 옮긴 거리(몸 크기 대비) 가운데 값 {moved[len(moved) // 2]:.3f}, 가장 큰 값 {moved[-1]:.3f}")


if __name__ == "__main__":
    main()

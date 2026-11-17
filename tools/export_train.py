"""학습 정답 모으기 (2026-11-17): 표시 도구의 labels.json 들 → trainset/quad_v1/ (labels.json + masks/).

이 폴더는 저장소에 올린다(집 PC 에서 학습하려고). 들어가는 것은 Quick, Draw! (Google, CC BY 4.0) 낙서에서 만든 마스크와 관절뿐이다.
시험 세트(아이 그림)는 여기 넣지 않는다.

들어가는 것
  qd_pilot   사람이 점을 고쳐 끝낸 그림 (done, 79장 안팎)
  qd_300 …   사람이 초안을 골라 「맞음」(ok) · 「꼬리만 틀림」(tail)이라 한 그림. 관절은 규칙 초안 그대로
관절은 서비스 4족형 18개(tools/score_rule.py GROUPS 순서, 머리는 없음). 서비스 규칙의 약속에 맞춘다.
  - 다리 번호: 뒷다리는 머리에 가까운 쪽이 right(1), 앞다리는 꼬리에 가까운 쪽이 right(1) (= 몸 가운데 쪽이 1). 사람이 번호를 바꿔 놓았어도 여기서 정렬
  - 한쪽에 다리를 하나만 그렸으면 두 칸을 같은 자리에 겹친다 (규칙도 그렇게 놓는다)
  - 꼬리가 없으면 꼬리 점 셋을 엉덩이에 겹친다 (규칙도 그렇게 놓는다)
  - 가중치 0 (학습에서 뺌): 「꼬리만 틀림」의 꼬리 점 셋, 앞이나 뒤 다리가 통째로 없는 쪽의 다리 점
입력은 그림이 아니라 몸 마스크(서비스 cut_out 이 만든 것, <묶음>/masks/이름_r0.png). 실제 아이 그림도 같은 마스크를 거치므로 그림 꼴 차이가 줄어든다.

    work/venv/Scripts/python tools/export_train.py   → trainset/quad_v1/labels.json (마스크 경로 · 관절 · 가중치), trainset/quad_v1/masks/*.png
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from body_rule import get_mask, mask_path  # noqa: E402
from sets import ROOT, SETS  # noqa: E402

ORDER = ["hip", "torso", "neck",
         "right_hip_b", "right_knee_b", "right_foot_b", "left_hip_b", "left_knee_b", "left_foot_b",
         "right_hip_f", "right_knee_f", "right_foot_f", "left_hip_f", "left_knee_f", "left_foot_f",
         "tail", "tail_mid", "tail_tip"]
PARTS = ("hip", "knee", "foot")


def convert(r: dict) -> tuple[dict, dict] | None:
    j = r["joints"]
    toward = 1 if r["facing"] == "right" else -1
    out, w = {}, {}
    for k in ("hip", "torso", "neck"):
        out[k], w[k] = j[k][:2], 1
    for side in "bf":
        legs = [s for s in ("right", "left") if j[f"{s}_hip_{side}"][2]]
        if not legs:                       # 그쪽 다리가 통째로 없음: 자리만 채우고 학습에서 뺀다
            for s in ("right", "left"):
                for p in PARTS:
                    out[f"{s}_{p}_{side}"], w[f"{s}_{p}_{side}"] = j[f"{s}_{p}_{side}"][:2], 0
            continue
        # 몸 가운데 쪽이 1(right): 뒷다리는 머리 쪽, 앞다리는 꼬리 쪽
        legs.sort(key=lambda s: toward * j[f"{s}_hip_{side}"][0], reverse=(side == "b"))
        first, second = legs[0], legs[-1]
        for name, src in (("right", first), ("left", second)):
            for p in PARTS:
                out[f"{name}_{p}_{side}"], w[f"{name}_{p}_{side}"] = j[f"{src}_{p}_{side}"][:2], 1
    has_tail = bool(j["tail"][2])
    for k in ("tail", "tail_mid", "tail_tip"):
        out[k] = j[k][:2] if has_tail else j["hip"][:2]
        w[k] = 0 if r.get("tail_unknown") else 1
    return out, w


def main() -> None:
    items = []
    dst = ROOT / "trainset/quad_v1"
    (dst / "masks").mkdir(parents=True, exist_ok=True)
    for name, (folder, _, _) in SETS.items():
        if not name.startswith("qd_"):
            continue                       # 시험 세트는 학습에 쓰지 않는다
        f = ROOT / folder / "labels.json"
        if not f.exists():
            continue
        labels = json.load(open(f, encoding="utf-8"))
        auto = json.load(open(ROOT / folder / "auto.json", encoding="utf-8"))
        n = 0
        for img, r in sorted(labels.items()):
            if r.get("use") is False or not r.get("done") or not r.get("facing") or r.get("judge") == "bad" or (r.get("rotate") or 0) % 360:
                continue
            if get_mask(ROOT / folder, img, 0) is None:
                print("  마스크 없음:", img)
                continue
            joints, weights = convert(r)
            shutil.copy(mask_path(ROOT / folder, img, 0), dst / "masks" / f"{Path(img).stem}.png")
            items.append({"set": name, "name": img, "cat": auto[img].get("cat"), "facing": r["facing"],
                          "how": r.get("judge") or "fixed", "mask": f"masks/{Path(img).stem}.png", "key": auto[img].get("key"),
                          "joints": [joints[k] for k in ORDER], "weights": [weights[k] for k in ORDER]})
            n += 1
        print(name, n, "장")
    out = dst / "labels.json"
    json.dump({"order": ORDER, "items": items}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("모두", len(items), "장 →", out)


if __name__ == "__main__":
    main()

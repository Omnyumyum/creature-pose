"""형태 여럿을 한 모델로: 등뼈대는 같이 쓰고 출력층만 형태별로 (2026-11-20). quad_model.py 의 다음 단계.

왜: 네 발 · 날개 · 지느러미 … 는 관절 구성이 서로 다르다. 형태마다 모델을 따로 두면 배운 것을 나누지 못하고, 출력까지 하나로 합치면
서로 방해한다. 그래서 그림을 읽는 부분(등뼈대 + 위로 키우는 층)은 하나, 관절을 내는 마지막 층만 형태별로 둔다.
형태는 어른이 골라 주므로(서비스의 형태 고르기) 모델이 맞히지 않는다. 고른 형태의 출력층만 읽는다.

  형태     quad (네 발, 관절 18, 사람 정답 trainset/quad_v1 + 합성 synth_quad)
           wing (날개형, 관절 8, 합성 synth_wing 만. 사람 정답은 아직 없다)
  학습     걸음마다 형태를 번갈아 한 묶음씩. 입력 · 늘리기 · 히트맵은 quad_model.py 와 같다
  저장     models/<형태>_<tag>.pth 를 형태마다 하나씩, quad_model.py 의 Net 과 같은 꼴로 (등뼈대는 같은 값이 들어간다)
           → 네 발은 지금 시험 그대로: python train/quad_model.py test --tag <tag>

    python train/multi_model.py train --forms quad,wing --synth 5000 --tag m1     (같이 쓰기)
    python train/multi_model.py train --forms wing --synth 5000 --tag w1          (날개만 따로: 견줄 것. 네 발만 따로는 quad_model 의 v2)
    python train/multi_model.py train --forms quad,wing --dry                     (몇 장만 넣어 끝까지 도는지 확인, 학습 아님)
    더 줄 수 있는 것: --epochs 60  --rot 25 (돌리기 ±도)  --arch r50 --init ap10k  --workers 0
"""

import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "train"))
import quad_model as Q  # noqa: E402
import synth_quad  # noqa: E402
import synth_wing  # noqa: E402

IN, DEV, arg = Q.IN, Q.DEV, Q.arg


def _wing_fix(pts: np.ndarray, w: np.ndarray) -> None:
    """날개 번호 약속(끝이 왼쪽인 것이 wing1)을 뒤집기 · 돌리기 뒤에도 지킨다"""
    if pts[4, 0] > pts[7, 0]:
        pts[[2, 3, 4, 5, 6, 7]] = pts[[5, 6, 7, 2, 3, 4]]
        w[[2, 3, 4, 5, 6, 7]] = w[[5, 6, 7, 2, 3, 4]]


FORMS = {
    "quad": {"order": synth_quad.ORDER, "gen": synth_quad.generate, "real": ROOT / "trainset/quad_v1", "fix": None},
    "wing": {"order": synth_wing.ORDER, "gen": synth_wing.generate, "real": None, "fix": _wing_fix},
}


def jitter(rng: random.Random, rot: float) -> np.ndarray:
    """quad_model.jitter_matrix 와 같되 돌리기 범위를 받는다"""
    c = IN / 2
    t = math.radians(rng.uniform(-rot, rot))
    s = rng.uniform(0.7, 1.1)
    f = -1.0 if rng.random() < 0.5 else 1.0
    R = np.array([[s * math.cos(t) * f, -s * math.sin(t), 0], [s * math.sin(t) * f, s * math.cos(t), 0], [0, 0, 1]])
    T0 = np.array([[1, 0, -c], [0, 1, -c], [0, 0, 1]], float)
    T1 = np.array([[1, 0, c + rng.uniform(-0.08, 0.08) * IN], [0, 1, c + rng.uniform(-0.08, 0.08) * IN], [0, 0, 1]], float)
    return T1 @ R @ T0


def sample(form: str, mask: np.ndarray, joints: np.ndarray, weights: np.ndarray, rng: random.Random | None, rot: float):  # noqa: ANN201
    M = Q.base_matrix(mask)
    if rng:
        M = jitter(rng, rot) @ M
    m = Q.warp(mask, M)
    if rng:
        m = Q.roughen(m, rng)
    pts = Q.apply(M, joints)
    w = weights.astype(np.float32).copy()
    if FORMS[form]["fix"]:
        FORMS[form]["fix"](pts, w)
    w = w * ((pts >= 0) & (pts < IN)).all(axis=1)
    return (torch.from_numpy(m[None].astype(np.float32)), torch.from_numpy(Q.heatmaps(pts)), torch.from_numpy(w.astype(np.float32)),
            torch.from_numpy(pts.astype(np.float32)))


class Synth(torch.utils.data.Dataset):
    """부를 때마다 새 합성 마스크. seed 를 주면 늘 같은 그림(확인용, 늘리기 없음)"""

    def __init__(self, form: str, n: int, rot: float, seed: int | None = None) -> None:
        self.form, self.n, self.rot, self.seed, self.rng, self.np_rng = form, n, rot, seed, None, None

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, i: int):  # noqa: ANN204
        if self.seed is not None:
            np_rng, rng = np.random.default_rng(self.seed + i), None
        else:
            if self.rng is None:                                   # 일꾼(프로세스)마다 다른 씨앗
                self.np_rng = np.random.default_rng()
                self.rng = random.Random(int(self.np_rng.integers(1 << 30)))
            np_rng, rng = self.np_rng, self.rng
        for _ in range(5):
            mask, pts = FORMS[self.form]["gen"](np_rng)
            if mask.any():
                break
        return sample(self.form, mask, pts, np.ones(len(pts), np.float32), rng, self.rot)


class Real(torch.utils.data.Dataset):
    def __init__(self, form: str, items: list, train: bool, rot: float, repeat: int = 1) -> None:
        import cv2
        folder = FORMS[form]["real"]
        self.form, self.items, self.train, self.rot, self.repeat, self.rng = form, items, train, rot, repeat, None
        self.masks = [np.array(cv2.imread(str(folder / it["mask"]), cv2.IMREAD_GRAYSCALE)) > 127 for it in items]

    def __len__(self) -> int:
        return len(self.items) * self.repeat

    def __getitem__(self, i: int):  # noqa: ANN204
        i %= len(self.items)
        it = self.items[i]
        if self.train and self.rng is None:
            self.rng = random.Random(int(np.random.default_rng().integers(1 << 30)))
        return sample(self.form, self.masks[i], np.array(it["joints"], float), np.array(it["weights"], np.float32), self.rng if self.train else None, self.rot)


class Net(nn.Module):
    """등뼈대 + 위로 키우는 층은 하나, 마지막 층은 형태마다"""

    def __init__(self, forms: list[str], arch: str = "r18", init: str = "imagenet") -> None:
        super().__init__()
        base = Q.Net(1, arch=arch, init=init)
        self.stem, self.up = base.stem, base.up
        self.heads = nn.ModuleDict({f: nn.Conv2d(base.out.in_channels, len(FORMS[f]["order"]), 1) for f in forms})

    def forward(self, x: torch.Tensor, form: str) -> torch.Tensor:
        return self.heads[form](self.up(self.stem(x.repeat(1, 3, 1, 1) * 2 - 1)))

    def single(self, form: str) -> dict:
        """형태 하나를 quad_model.Net 꼴의 가중치로 (stem · up · out)"""
        sd = {k: v for k, v in self.state_dict().items() if not k.startswith("heads.")}
        sd["out.weight"], sd["out.bias"] = self.heads[form].weight.detach(), self.heads[form].bias.detach()
        return sd


def train() -> None:
    dry = "--dry" in sys.argv
    forms = arg("--forms", "quad,wing").split(",")
    for f in forms:
        if f not in FORMS:
            sys.exit(f"모르는 형태: {f} (있는 것: {', '.join(FORMS)})")
    tag, epochs = arg("--tag", "dry" if dry else "m1"), 1 if dry else arg("--epochs", 60)
    synth, rot, lr = (8 if dry else arg("--synth", 5000)), arg("--rot", 25.0), arg("--lr", 1e-3)
    arch, init = arg("--arch", "r18"), arg("--init", "imagenet")
    workers = 0 if dry else arg("--workers", 6 if DEV == "cuda" else 0)
    bs = 4 if dry else 64
    loaders, vals, counts = {}, {}, {}
    for f in forms:
        parts, n_real = [Synth(f, synth, rot)], 0
        if FORMS[f]["real"]:
            items = json.load(open(FORMS[f]["real"] / "labels.json", encoding="utf-8"))["items"]
            random.Random(1117).shuffle(items)                     # quad_model.py 와 같은 나눔: 확인 점수를 v1 · v2 와 견줄 수 있다
            n_val = max(8, round(len(items) * 0.15))
            val, tr = items[:n_val], items[n_val:]
            if dry:
                tr, val = tr[:8], val[:4]
            parts.append(Real(f, tr, True, rot, 1 if dry else max(1, round(960 / len(tr)))))
            vals[f], n_real = torch.utils.data.DataLoader(Real(f, val, False, rot), batch_size=32), len(tr)
        else:
            vals[f] = torch.utils.data.DataLoader(Synth(f, 8 if dry else 300, rot, seed=20261120), batch_size=32)      # 사람 정답이 없어 고정 합성으로 확인
        counts[f] = n_real
        loaders[f] = torch.utils.data.DataLoader(torch.utils.data.ConcatDataset(parts), batch_size=bs, shuffle=True, drop_last=True,
                                                 num_workers=workers, persistent_workers=bool(workers))
        print(f"{f}: 사람 정답 {n_real}장 + 합성 에폭마다 {synth}장 · 확인 {len(vals[f].dataset)}장{'' if FORMS[f]['real'] else '(합성)'}", flush=True)
    print(f"형태 {forms} · 돌리기 ±{rot:g}도 · 장치 {DEV}", flush=True)
    torch.manual_seed(0)
    net = Net(forms, arch, init).to(DEV)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    steps = max(len(d) for d in loaders.values())                  # 에폭 = 형태마다 이만큼씩
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * steps * len(forms), pct_start=0.1)
    (ROOT / "models").mkdir(exist_ok=True)
    log, best = [], -1.0
    for ep in range(epochs):
        net.train()
        t0, tot = time.time(), {f: 0.0 for f in forms}
        its = {f: iter(loaders[f]) for f in forms}
        for _ in range(steps):
            for f in forms:
                try:
                    x, y, w, _p = next(its[f])
                except StopIteration:
                    its[f] = iter(loaders[f])
                    x, y, w, _p = next(its[f])
                x, y, w = x.to(DEV), y.to(DEV), w.to(DEV)
                loss = (((net(x, f) - y) ** 2).mean(dim=(2, 3)) * w).sum() / w.sum().clamp(min=1)
                opt.zero_grad()
                loss.backward()
                opt.step()
                sched.step()
                tot[f] += float(loss.detach())
        net.eval()
        acc = {}
        with torch.no_grad():
            for f in forms:
                ok = n = 0
                for x, _y, w, pts in vals[f]:
                    a, b = Q.pck(Q.decode(net(x.to(DEV), f)), pts.numpy(), w.numpy(), 0.1)
                    ok, n = ok + a, n + b
                acc[f] = ok / max(1, n)
        row = {"epoch": ep + 1, **{f"loss_{f}": round(tot[f] / steps * 1000, 4) for f in forms}, **{f"val_pck10_{f}": round(acc[f], 4) for f in forms}}
        log.append(row)
        print(f"에폭 {ep + 1:>3}  " + "  ".join(f"{f} loss {tot[f] / steps * 1000:.3f} 확인 {acc[f]:.1%}" for f in forms) + f"  {time.time() - t0:.0f}초", flush=True)
        mean = sum(acc.values()) / len(acc)
        if mean >= best:
            best = mean
            for f in forms:
                torch.save(net.single(f), ROOT / f"models/{f}_{tag}.pth")
    res = {"tag": tag, "forms": forms, "arch": arch, "init": init, "rot": rot, "synth_per_epoch": synth, "train_real": counts, "epochs": epochs,
           "best_mean_val_pck10": round(best, 4), "log": log}
    (ROOT / "out").mkdir(exist_ok=True)
    json.dump(res, open(ROOT / f"out/multi_{tag}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("저장: " + ", ".join(f"models/{f}_{tag}.pth" for f in forms) + f", out/multi_{tag}.json")
    if "quad" in forms:
        print(f"네 발 시험(시험 세트가 있는 PC 에서): python train/quad_model.py test --tag {tag}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train()
    else:
        sys.exit(__doc__)

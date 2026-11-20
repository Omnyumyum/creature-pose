"""네 발 관절 모델 첫 학습 · 시험 (2026-11-17). 입력은 몸 마스크(1장), 출력은 관절 18개의 히트맵.

왜 마스크인가: 학습 그림은 Quick, Draw! 낙서, 시험은 실제 아이 그림 사진이라 그림 꼴이 많이 다르다. 둘 다 서비스의 cut_out 이 만든
몸 마스크를 거치면 같은 꼴(흰 덩어리)이 된다. 지금 규칙(quadruped.py find_joints)도 마스크만 보고 관절을 놓으므로 같은 입력으로 견주는 것이기도 하다.
모델은 머리 쪽을 따로 받지 않는다(규칙은 어른이 알려 주거나 굵기로 짐작한다). 머리 쪽까지 스스로 맞혀야 한다.

  모델      ResNet-18(ImageNet 가중치) + 위로 키우는 층 3개 → 64x64 히트맵 18장 (SimpleBaseline 꼴)
  입력      마스크를 감싼 정사각형(긴 변의 1.25배)을 256x256 으로
  늘리기    좌우 뒤집기(관절 이름은 그대로: 이름이 왼 · 오른이 아니라 몸 안쪽 · 바깥쪽이라서), 돌리기 ±25도, 크기 · 자리 흔들기,
            마스크 깎기 · 불리기, 군데군데 지우기(실제 마스크는 끊기고 빠진 곳이 있다)
  시험      data/testset/quadruped (사람 정답 29장), tools/score_rule.py 와 같은 채점. 규칙 점수와 나란히 보여 준다

    python train/quad_model.py train [--epochs 60] [--tag v1] [--limit 장수]   → models/quad_<tag>.pth, out/quad_<tag>.json
    python train/quad_model.py test  [--tag v1]                                 (시험 세트가 있는 PC 에서만: 아이 그림이라 저장소에 없다)
    python train/quad_model.py train --synth 5000 --tag v2                      (에폭마다 합성 마스크 5,000장을 새로 만들어 섞는다. train/synth_quad.py)
    python train/quad_model.py train --synth 5000 --real 0 --tag v2s            (합성만)
    python train/quad_model.py train --arch r50 --init ap10k --tag v3           (AP-10K 동물 사진 가중치에서 시작. 견줄 것: --arch r50 --tag v3i 는 ImageNet 에서)
    python train/quad_model.py train --dry                                      (몇 장만 넣어 끝까지 도는지 확인, 학습 아님)
학습 정답은 trainset/quad_v1/ (tools/export_train.py 가 만든다). 학습은 집 PC(RTX 5080)에서, 시험은 시험 세트가 있는 노트북에서 한다. 설치는 train/INSTALL.md
"""

import json
import math
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torchvision

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "train"))
import synth_quad  # noqa: E402
from score_rule import GROUPS, errors  # noqa: E402

TRAIN = ROOT / "trainset/quad_v1"
MODELS = ROOT / "models"      # *.pth 는 .gitignore 가 막는다. 옮길 때는 git add -f
IN, HM, SIGMA, PAD = 256, 64, 2.0, 1.25
DEV = "cuda" if torch.cuda.is_available() else "cpu"


def arg(name: str, default):  # noqa: ANN001
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


# ── 그림 → 입력 ─────────────────────────────────────────────────────────

def base_matrix(mask: np.ndarray) -> np.ndarray:
    """마스크를 감싼 정사각형을 IN x IN 으로 옮기는 3x3 행렬"""
    ys, xs = np.where(mask)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    side = max(xs.max() - xs.min(), ys.max() - ys.min(), 8) * PAD
    s = IN / side
    return np.array([[s, 0, IN / 2 - s * cx], [0, s, IN / 2 - s * cy], [0, 0, 1]], float)


def jitter_matrix(rng: random.Random) -> np.ndarray:
    """입력 칸 가운데를 중심으로 뒤집기 · 돌리기 · 크기 · 자리 흔들기"""
    c = IN / 2
    t = math.radians(rng.uniform(-25, 25))
    s = rng.uniform(0.7, 1.1)
    f = -1.0 if rng.random() < 0.5 else 1.0
    R = np.array([[s * math.cos(t) * f, -s * math.sin(t), 0], [s * math.sin(t) * f, s * math.cos(t), 0], [0, 0, 1]])
    T0 = np.array([[1, 0, -c], [0, 1, -c], [0, 0, 1]], float)
    T1 = np.array([[1, 0, c + rng.uniform(-0.08, 0.08) * IN], [0, 1, c + rng.uniform(-0.08, 0.08) * IN], [0, 0, 1]], float)
    return T1 @ R @ T0


def warp(mask: np.ndarray, M: np.ndarray) -> np.ndarray:
    return cv2.warpAffine(mask.astype(np.uint8) * 255, M[:2], (IN, IN), flags=cv2.INTER_LINEAR) > 127


def roughen(m: np.ndarray, rng: random.Random) -> np.ndarray:
    """실제 마스크처럼: 깎거나 불리고, 군데군데 지우고, 작은 덩어리를 붙인다"""
    m = m.astype(np.uint8)
    k = rng.choice([0, 0, 1, 2, 3])
    if k:
        el = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
        m = cv2.erode(m, el) if rng.random() < 0.4 else cv2.dilate(m, el)
    if rng.random() < 0.3:
        for _ in range(rng.randint(1, 3)):
            w, h = rng.randint(8, 36), rng.randint(8, 36)
            x, y = rng.randint(0, IN - w), rng.randint(0, IN - h)
            m[y:y + h, x:x + w] = 0
    if rng.random() < 0.2:
        cv2.circle(m, (rng.randint(0, IN - 1), rng.randint(0, IN - 1)), rng.randint(3, 10), 1, -1)
    return m > 0


def heatmaps(pts: np.ndarray) -> np.ndarray:
    g = np.arange(HM, dtype=np.float32)
    out = np.zeros((len(pts), HM, HM), np.float32)
    for i, (x, y) in enumerate(pts * (HM / IN)):
        out[i] = np.exp(-((g[None, :] - x) ** 2 + (g[:, None] - y) ** 2) / (2 * SIGMA ** 2))
    return out


def apply(M: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return np.c_[pts, np.ones(len(pts))] @ M[:2].T


def sample(mask: np.ndarray, joints: np.ndarray, weights: np.ndarray, rng: random.Random | None):  # noqa: ANN201
    """마스크 + 관절 → (입력, 히트맵, 가중치, 입력 칸 좌표). rng 를 주면 늘리기를 한다"""
    M = base_matrix(mask)
    if rng:
        M = jitter_matrix(rng) @ M
    m = warp(mask, M)
    if rng:
        m = roughen(m, rng)
    pts = apply(M, joints)
    w = weights * ((pts >= 0) & (pts < IN)).all(axis=1)      # 칸 밖으로 나간 관절은 뺀다
    return (torch.from_numpy(m[None].astype(np.float32)), torch.from_numpy(heatmaps(pts)), torch.from_numpy(w.astype(np.float32)),
            torch.from_numpy(pts.astype(np.float32)))


class Synth(torch.utils.data.Dataset):
    """부를 때마다 새 합성 마스크 (train/synth_quad.py). 같은 그림이 두 번 나오지 않는다"""

    def __init__(self, n: int) -> None:
        self.n, self.rng, self.np_rng = n, None, None

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, i: int):  # noqa: ANN204
        if self.rng is None:                                   # 일꾼(프로세스)마다 다른 씨앗
            self.np_rng = np.random.default_rng()
            self.rng = random.Random(int(self.np_rng.integers(1 << 30)))
        for _ in range(5):
            mask, pts = synth_quad.generate(self.np_rng)
            if mask.any():
                break
        return sample(mask, pts, np.ones(len(pts), np.float32), self.rng)


class Data(torch.utils.data.Dataset):
    def __init__(self, items: list, train: bool, repeat: int = 1) -> None:
        self.items, self.train, self.repeat = items, train, repeat
        self.masks = [np.array(cv2.imread(str(TRAIN / it["mask"]), cv2.IMREAD_GRAYSCALE)) > 127 for it in items]
        self.rng = None

    def __len__(self) -> int:
        return len(self.items) * self.repeat

    def __getitem__(self, i: int):  # noqa: ANN204
        i %= len(self.items)
        it, mask = self.items[i], self.masks[i]
        if self.train and self.rng is None:
            self.rng = random.Random(int(np.random.default_rng().integers(1 << 30)))
        return sample(mask, np.array(it["joints"], float), np.array(it["weights"], np.float32), self.rng if self.train else None)


# ── 모델 ────────────────────────────────────────────────────────────────

# MMPose 가 나눠 주는 AP-10K(네 발 동물 사진 54종, 17점) 학습 가중치. ResNet-50 SimpleBaseline 256x256.
# 데이터 조건이 상업 이용에 걸리는지 확인이 끝나지 않았다. 지금은 비상업 실험이라 쓰고, 운영에 올리기 전에 다시 확인한다.
AP10K_URL = "https://download.openmmlab.com/mmpose/animal/resnet/res50_ap10k_256x256-35760eb8_20211029.pth"


def ap10k_weights() -> dict:
    """AP-10K 가중치를 우리 층 이름으로. 등뼈대(backbone)와 위로 키우는 층 3개를 물려받고, 마지막 층(17점)은 관절 정의가 달라 버린다"""
    ck = torch.hub.load_state_dict_from_url(AP10K_URL, model_dir=str(ROOT / "work/pretrained"), map_location="cpu", check_hash=True, weights_only=True)
    sd = ck.get("state_dict", ck)
    back = {k[len("backbone."):]: v for k, v in sd.items() if k.startswith("backbone.")}
    up = {k[len("keypoint_head.deconv_layers."):]: v for k, v in sd.items() if k.startswith("keypoint_head.deconv_layers.")}
    return {"backbone": back, "up": up}


class Net(nn.Module):
    """arch r18: ResNet-18 + 128칸 층(처음 것). r50: ResNet-50 + 256칸 층(AP-10K 가중치와 같은 꼴). init: imagenet · ap10k · none"""

    def __init__(self, joints: int = 18, pretrained: bool = True, arch: str = "r18", init: str = "imagenet") -> None:
        super().__init__()
        make, wts, c, width = ((torchvision.models.resnet50, torchvision.models.ResNet50_Weights.DEFAULT, 2048, 256) if arch == "r50"
                               else (torchvision.models.resnet18, torchvision.models.ResNet18_Weights.DEFAULT, 512, 128))
        if not pretrained:
            init = "none"
        if init == "ap10k" and arch != "r50":
            raise SystemExit("--init ap10k 는 --arch r50 과 함께 쓴다 (가중치가 ResNet-50 것)")
        try:
            r = make(weights=wts if init == "imagenet" else None)
        except Exception as e:  # noqa: BLE001
            print("ImageNet 가중치를 못 받아 처음부터 학습:", str(e)[:80])
            r = make(weights=None)
        ap = ap10k_weights() if init == "ap10k" else None
        if ap:
            miss = r.load_state_dict(ap["backbone"], strict=False)
            left = [k for k in miss.missing_keys if not k.startswith("fc.")]
            if left or miss.unexpected_keys:
                raise SystemExit(f"AP-10K 등뼈대 층 이름이 안 맞음: 빠짐 {left[:3]} 남음 {miss.unexpected_keys[:3]}")
        self.stem = nn.Sequential(r.conv1, r.bn1, r.relu, r.maxpool, r.layer1, r.layer2, r.layer3, r.layer4)
        up = []
        for _ in range(3):
            up += [nn.ConvTranspose2d(c, width, 4, 2, 1, bias=False), nn.BatchNorm2d(width), nn.ReLU(inplace=True)]
            c = width
        self.up = nn.Sequential(*up)
        if ap:
            self.up.load_state_dict(ap["up"])           # 층 번호(0 · 1 · 3 · 4 · 6 · 7)가 MMPose 와 같다
            print("AP-10K 가중치로 시작 (등뼈대 + 위로 키우는 층)", flush=True)
        self.out = nn.Conv2d(width, joints, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.out(self.up(self.stem(x.repeat(1, 3, 1, 1) * 2 - 1)))


def decode(hm: torch.Tensor) -> np.ndarray:
    """히트맵 (N, J, HM, HM) → 입력 칸 좌표 (N, J, 2). 가장 높은 칸에서 옆 칸 쪽으로 1/4 칸"""
    n, j = hm.shape[:2]
    idx = hm.reshape(n, j, -1).argmax(-1).cpu().numpy()
    ys, xs = idx // HM, idx % HM
    h = hm.cpu().numpy()
    out = np.zeros((n, j, 2), np.float32)
    for a in range(n):
        for b in range(j):
            x, y = int(xs[a, b]), int(ys[a, b])
            dx = np.sign(h[a, b, y, min(x + 1, HM - 1)] - h[a, b, y, max(x - 1, 0)]) * 0.25
            dy = np.sign(h[a, b, min(y + 1, HM - 1), x] - h[a, b, max(y - 1, 0), x]) * 0.25
            out[a, b] = ((x + dx + 0.5) * IN / HM - 0.5, (y + dy + 0.5) * IN / HM - 0.5)
    return out


def predict(net: Net, mask: np.ndarray) -> np.ndarray:
    """마스크(원래 크기) → 관절 18개 (마스크 좌표)"""
    M = base_matrix(mask)
    x = torch.from_numpy(warp(mask, M)[None, None].astype(np.float32)).to(DEV)
    with torch.no_grad():
        pts = decode(net(x))[0]
    return apply(np.linalg.inv(M), pts.astype(float))


# ── 학습 ────────────────────────────────────────────────────────────────

def pck(pred: np.ndarray, gt: np.ndarray, w: np.ndarray, t: float) -> tuple[int, int]:
    ok = n = 0
    for p, g, ww in zip(pred, gt, w):
        keep = ww > 0
        if not keep.any():
            continue
        size = math.hypot(*(g[keep].max(0) - g[keep].min(0))) or 1.0
        d = np.hypot(*(p[keep] - g[keep]).T) / size
        ok += int((d <= t).sum())
        n += int(keep.sum())
    return ok, n


def train() -> None:
    dry = "--dry" in sys.argv
    tag, epochs, limit = arg("--tag", "dry" if dry else "v1"), 1 if dry else arg("--epochs", 60), arg("--limit", 0)
    synth, real = arg("--synth", 0), arg("--real", 1)      # 에폭마다 합성 장 수, 사람 정답을 쓸지(0 이면 합성만)
    workers = arg("--workers", 6 if DEV == "cuda" else 0)
    data = json.load(open(TRAIN / "labels.json", encoding="utf-8"))
    items = data["items"]
    random.Random(1117).shuffle(items)
    n_val = max(8, round(len(items) * 0.15))
    val, tr = items[:n_val], items[n_val:]
    if dry:
        tr, val = tr[:8], val[:4]
    if limit:
        tr = tr[:limit]                    # 양을 줄여 학습해 보기(정답이 늘면 얼마나 오르나)
    if dry and synth:
        synth = 8
    print(f"학습 {len(tr) if real else 0}장 + 합성 에폭마다 {synth}장 · 확인 {len(val)}장 · 장치 {DEV}", flush=True)
    torch.manual_seed(0)
    arch, init, lr = arg("--arch", "r18"), arg("--init", "imagenet"), arg("--lr", 1e-3)
    net = Net(len(data["order"]), arch=arch, init=init).to(DEV)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    repeat = 1 if dry else max(1, round(960 / len(tr)))
    parts = ([Data(tr, True, repeat)] if real else []) + ([Synth(synth)] if synth else [])
    dl = torch.utils.data.DataLoader(torch.utils.data.ConcatDataset(parts), batch_size=4 if dry else 64 if synth else 32, shuffle=True, drop_last=True,
                                     num_workers=0 if dry else workers, persistent_workers=bool(workers) and not dry)
    dv = torch.utils.data.DataLoader(Data(val, False), batch_size=32)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * len(dl), pct_start=0.1)
    log, best = [], -1.0
    out = MODELS
    out.mkdir(parents=True, exist_ok=True)
    for ep in range(epochs):
        net.train()
        t0, tot = time.time(), 0.0
        for x, y, w, _ in dl:
            x, y, w = x.to(DEV), y.to(DEV), w.to(DEV)
            loss = (((net(x) - y) ** 2).mean(dim=(2, 3)) * w).sum() / w.sum().clamp(min=1)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += float(loss.detach())
        net.eval()
        ok = n = 0
        with torch.no_grad():
            for x, _, w, pts in dv:
                a, b = pck(decode(net(x.to(DEV))), pts.numpy(), w.numpy(), 0.1)
                ok, n = ok + a, n + b
        acc = ok / max(1, n)
        log.append({"epoch": ep + 1, "loss": round(tot / len(dl) * 1000, 4), "val_pck10": round(acc, 4)})
        print(f"에폭 {ep + 1:>3}  loss x1000 {tot / len(dl) * 1000:.3f}  확인 PCK@0.1 {acc:.1%}  {time.time() - t0:.0f}초", flush=True)
        if acc >= best:
            best = acc
            torch.save(net.state_dict(), out / f"quad_{tag}.pth")
    res = {"tag": tag, "arch": arch, "init": init, "lr": lr, "train": len(tr) if real else 0, "synth_per_epoch": synth, "val": len(val), "epochs": epochs, "best_val_pck10": round(best, 4), "log": log}
    if (ROOT / "data/testset/quadruped/labels.json").exists():
        res["test"] = test(tag)
    else:
        print(f"시험 세트가 이 PC 에 없어 시험은 건너뜀. models/quad_{tag}.pth 를 시험 세트가 있는 PC 로 옮겨 `python train/quad_model.py test --tag {tag}`")
    (ROOT / "out").mkdir(exist_ok=True)
    json.dump(res, open(ROOT / f"out/quad_{tag}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ── 시험 세트 ───────────────────────────────────────────────────────────

def test(tag: str) -> dict:
    from body_rule import get_mask
    folder = ROOT / "data/testset/quadruped"
    labels = json.load(open(folder / "labels.json", encoding="utf-8"))
    order = json.load(open(TRAIN / "labels.json", encoding="utf-8"))["order"]
    sd = torch.load(MODELS / f"quad_{tag}.pth", map_location=DEV, weights_only=True)
    net = Net(len(order), pretrained=False, arch="r50" if sd["up.0.weight"].shape[0] == 2048 else "r18").to(DEV)   # 꼴은 가중치에서 읽는다
    net.load_state_dict(sd)
    net.eval()
    used = {n: r for n, r in labels.items() if r.get("use")}
    from PIL import Image
    result = {}
    for cond, rule_file in (("그대로", "auto.json"), ("세워서", "auto_upright.json")):
        pred = {}
        for name, r in used.items():
            deg = float(r.get("rotate") or 0) if cond == "세워서" else 0.0
            mask = get_mask(folder, name, deg)
            if mask is None or not mask.any():
                continue
            w, h = Image.open(folder / name).size
            H, W = mask.shape
            co, si = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            pts = predict(net, mask)
            pred[name] = {k: [w / 2 + (x - W / 2) * co + (y - H / 2) * si, h / 2 - (x - W / 2) * si + (y - H / 2) * co] for k, (x, y) in zip(order, pts)}
        json.dump({n: {"found": True, "joints": j} for n, j in pred.items()}, open(folder / f"pred_{tag}_{'upright' if cond == '세워서' else 'asis'}.json", "w"), indent=1)
        rule = json.load(open(folder / rule_file, encoding="utf-8")) if (folder / rule_file).exists() else {}
        rows = {"모델": {n: errors(r["joints"], pred.get(n, {})) for n, r in used.items()},
                "규칙": {n: errors(r["joints"], rule.get(n, {}).get("joints", {})) for n, r in used.items()}}
        sets = {"전체": list(used), "실제 그림": [n for n in used if not n.startswith("synth_")], "아이 그림": [n for n in used if n.startswith("kids_")],
                "공개 낙서": [n for n in used if n.startswith("qr_")], "합성": [n for n in used if n.startswith("synth_")]}
        print(f"\n[시험 세트 · {cond}]  PCK@0.1 / @0.2   (규칙의 「세워서」는 머리 쪽도 알려 준 것, 모델은 알려 주지 않음)")
        result[cond] = {}

        def line(title: str, names: list, keys: list | None) -> None:
            cell = {}
            for who in ("규칙", "모델"):
                es = [e for n in names for k, e in rows[who][n].items() if keys is None or k in keys]
                cell[who] = [round(sum(e <= t for e in es) / max(1, len(es)), 4) for t in (0.1, 0.2)]
            print(f"  {title:<10} 규칙 {cell['규칙'][0]:5.1%} / {cell['규칙'][1]:5.1%}    모델 {cell['모델'][0]:5.1%} / {cell['모델'][1]:5.1%}")
            result[cond][title] = cell
        for title, names in sets.items():
            line(title, names, None)
        for g, keys in GROUPS.items():
            line(g, list(used), keys)
        result[cond]["그림별 모델 PCK@0.2"] = {n: round(sum(e <= 0.2 for e in rows["모델"][n].values()) / len(rows["모델"][n]), 3) for n in used}
    return result


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train()
    else:
        test(arg("--tag", "v1"))

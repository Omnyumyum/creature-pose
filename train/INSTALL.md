# 집 PC(RTX 5080)에서 네 발 모델 학습하기

학습은 집 PC 에서, 시험은 시험 세트가 있는 노트북에서 한다. 시험 세트에는 아이 그림이 있어 저장소에 올리지 않기 때문이다.
학습 정답(`trainset/quad_v1/`)은 저장소에 들어 있다. Quick, Draw! (Google, CC BY 4.0) 낙서에서 만든 몸 마스크 190장과 관절 좌표다.

## 1. 받기와 설치 (처음 한 번)

```powershell
git clone https://github.com/Omnyumyum/creature-pose
cd creature-pose
py -3.12 -m venv venv
venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
venv\Scripts\python -m pip install opencv-python-headless numpy pillow
venv\Scripts\python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

- 마지막 줄이 `True` 와 `RTX 5080` 을 찍어야 한다. `False` 면 CPU 판이 깔린 것이니 torch 를 지우고 위 주소(`cu128`)로 다시 깐다.
- RTX 50 시리즈는 CUDA 12.8 로 만든 PyTorch(2.7 이상)가 필요한 것으로 알고 있다. 위 확인 줄에서 경고가 나오면 그 글을 그대로 알려 준다.
- 파이썬은 3.10 ~ 3.13 이면 된다. `py -3.12` 가 없으면 `py -0` 으로 깔린 판을 보고 고른다.

## 2. 끝까지 도는지 확인 (몇 초, 학습 아님)

```powershell
venv\Scripts\python train/quad_model.py train --dry
```

`장치 cuda` 가 찍히고 「시험 세트가 이 PC 에 없어 시험은 건너뜀」으로 끝나면 된다.

## 3. 학습

```powershell
venv\Scripts\python train/quad_model.py train
venv\Scripts\python train/quad_model.py train --limit 40 --tag v1_040
venv\Scripts\python train/quad_model.py train --limit 80 --tag v1_080
venv\Scripts\python train/quad_model.py train --synth 5000 --tag v2
venv\Scripts\python train/quad_model.py train --synth 5000 --real 0 --tag v2s
```

- 첫 줄이 전체(학습 161장 · 확인 29장, 60 에폭). 나머지 두 줄은 정답을 40장 · 80장만 썼을 때다. 정답이 늘면 점수가 얼마나 오르는지 보려는 것이다.
- `v2` 는 에폭마다 합성 마스크 5,000장을 새로 만들어 사람 정답과 섞는다(60 에폭이면 합성 30만 장, 같은 그림이 두 번 나오지 않음). `v2s` 는 합성만으로 학습한다. 합성기는 `train/synth_quad.py`, 생김새는 `venv\Scripts\python train/synth_quad.py 24` → `work/synth_look.jpg`.
- `v3` · `v3i` (2026-11-20 더함): 동물 사진으로 학습된 가중치에서 시작하면 나아지는지 본다.

  ```powershell
  venv\Scripts\python train/quad_model.py train --arch r50 --init ap10k --tag v3
  venv\Scripts\python train/quad_model.py train --arch r50 --tag v3i
  venv\Scripts\python train/quad_model.py train --arch r50 --init ap10k --synth 5000 --tag v3s
  ```

  `v3` 은 MMPose 의 AP-10K(네 발 동물 사진 54종) ResNet-50 가중치에서, `v3i` 는 같은 ResNet-50 을 ImageNet 가중치에서 시작한다. 둘을 견줘야 오른 점수가 동물 가중치 덕인지 모델이 커진 덕인지 가려진다. `v3s` 는 `v3` 에 합성 마스크를 섞은 것. 가중치(136MB)는 처음 돌릴 때 `work/pretrained/` 로 받는다. MMPose 설치는 필요 없다. AP-10K 데이터의 상업 이용 조건은 확인이 끝나지 않았다. 지금은 비상업 실험이라 쓰고, 운영에 올리기 전에 다시 확인한다.
- 합성 학습은 그림을 만드는 일꾼 6개를 띄운다. 느리거나 오류가 나면 `--workers 0` 을 붙인다.
- 에폭마다 `확인 PCK@0.1` 이 찍힌다. 따로 떼어 둔 Quick, Draw! 29장에서 잰 값이라 실제 아이 그림 점수는 아니다.
- 결과: `models/quad_<이름>.pth` (약 60MB), `out/quad_<이름>.json` (에폭별 기록).

## 3-2. 형태 여럿을 한 모델로 (2026-11-20 더함)

등뼈대는 같이 쓰고 출력층만 형태별로 두는 방식이다. 지금 형태는 네 발(`quad`)과 날개형(`wing`: 날개 하나 기준 관절 5개, 합성 마스크만으로 학습).

```powershell
venv\Scripts\python train/multi_model.py train --forms quad,wing --dry
venv\Scripts\python train/multi_model.py train --forms quad,wing --synth 5000 --tag m1
venv\Scripts\python train/multi_model.py train --forms wing --synth 5000 --tag w1
venv\Scripts\python train/multi_model.py train --forms quad,wing --synth 5000 --rot 180 --tag m1r
```

- 첫 줄은 몇 장으로 끝까지 도는지 보는 확인이다(학습 아님).
- `m1` 이 같이 쓰기, `w1` 은 날개만 따로 학습한 것이다. 네 발만 따로는 이미 있는 `v2` 다. 같이 쓴 것이 따로 한 것보다 나은지 이 셋으로 견준다.
- `m1r` 은 돌리기를 ±180도로 넓힌 것이다. `v2` 가 누운 사진에 약했다(아이 그림 53% → 세우면 89%).
- 결과: 형태마다 `models/quad_<이름>.pth` · `models/wing_<이름>.pth`, 기록은 `out/multi_<이름>.json`. 4절에서 올릴 때 `models/wing_*.pth out/multi_*.json` 도 함께 더한다.
- 날개형 확인 점수는 합성 그림으로 잰 것이라 실제 그림 점수가 아니다. 날개형 시험 세트는 아직 없다.

## 4. 결과를 노트북으로 보내기

`*.pth` 와 `out/` 은 `.gitignore` 가 막고 있어 `-f` 로 더한다.

```powershell
git checkout -b train/quad-v1
git add -f models/*.pth out/quad_*.json out/multi_*.json
git commit -m "네 발 모델 v1 학습 결과"
git push -u origin train/quad-v1
```

노트북에서는 그 브랜치의 `models/` 를 받아 `python train/quad_model.py test --tag v1` 로 시험 세트 점수를 낸다.
견줄 기준(지금 규칙, 몸 크기의 20% 안): 받은 그대로 45.8%, 각도 · 머리 쪽을 알려 주면 72.8%.

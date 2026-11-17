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
- 합성 학습은 그림을 만드는 일꾼 6개를 띄운다. 느리거나 오류가 나면 `--workers 0` 을 붙인다.
- 에폭마다 `확인 PCK@0.1` 이 찍힌다. 따로 떼어 둔 Quick, Draw! 29장에서 잰 값이라 실제 아이 그림 점수는 아니다.
- 결과: `models/quad_<이름>.pth` (약 60MB), `out/quad_<이름>.json` (에폭별 기록).

## 4. 결과를 노트북으로 보내기

`*.pth` 와 `out/` 은 `.gitignore` 가 막고 있어 `-f` 로 더한다.

```powershell
git checkout -b train/quad-v1
git add -f models/quad_v1.pth models/quad_v1_040.pth models/quad_v1_080.pth models/quad_v2.pth models/quad_v2s.pth out/quad_v*.json
git commit -m "네 발 모델 v1 학습 결과"
git push -u origin train/quad-v1
```

노트북에서는 그 브랜치의 `models/` 를 받아 `python train/quad_model.py test --tag v1` 로 시험 세트 점수를 낸다.
견줄 기준(지금 규칙, 몸 크기의 20% 안): 받은 그대로 45.8%, 각도 · 머리 쪽을 알려 주면 72.8%.

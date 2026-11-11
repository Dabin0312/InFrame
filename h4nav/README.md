# Castle · 목표 조건 H4

[경계 우회 전후의 주행 경로와 첫 STOP](compare.html?study=escape&scene=chair2&case=0) · [기존 2번의 충돌과 인계 시점 RGB](escape-diagnosis.png)

[같은 출발점에서 목표 바꿔보기](https://dabin0312.github.io/InFrame/demo/search.html) · [개선 전후 경로와 사진](compare.html) · [의자 탐색 비교](compare.html?study=chair&scene=panel7&case=0) · [벽면 구역에서 쓰레기통 찾기](compare.html?study=panel&scene=bin21&case=1) · [쓰레기통 유무 비교](compare.html?study=bin&scene=blind7&case=4) · [소화기 검증 기록](peripheral-report.json) · [이전 35쌍](compare.html?study=recovery) · [초기 H4 실험](report.json) · [학습 기록](fit.json)

같은 시뮬레이터, 출발 좌표, 카메라 방향에서 목표 이름만 바꾼다. `worker.mjs`는 시작 시 이름을 받고 매 스텝 전방 RGB를 받는다. MobileCLIP이 이름을 임베딩하고 YOLOE가 같은 RGB에서 해당 이름의 후보를 찾는다. H4는 RGB 네 장과 후보 네 개, 텍스트 임베딩으로 전진·좌회전·우회전·STOP 중 최대 점수 행동을 실행한다. NavMesh, 자세, 물체 좌표, ID 마스크는 환경·교사·채점에서만 사용한다.

## 재실행

저장소 루트에서 `python3 -m http.server 8000` 실행 후 `http://localhost:8000/demo/search.html`을 연다. 출발 장면을 고른 뒤 목표를 입력하고 **H4 실행**을 누른다. 사진 카드를 누르면 기록에 저장한 같은 출발점의 경로와 마지막 RGB를 확인한다. 각 기록에는 첫 RGB의 SHA-256, 출발 자세, 스텝별 자세·행동·로짓, 종료 사유가 들어 있다.

- 전진 0.22 m, 회전 15°, 최대 120스텝. 제한에 도달한 경우 사진은 마지막 관측이다.
- 물체별 채점은 첫 STOP에 수평거리 ≤1.35 m, 가려짐을 적용한 인스턴스 마스크 ≥80 px, 마스크 바운딩 박스의 가로 중심이 화면 중앙 절반 안에 있어야 통과한다. 기본 배치에서는 기존의 등록 관측점까지 NavMesh 거리 ≤0.8 m 조건도 기록한다. 재배치 후에는 기존 관측점이 유효하지 않다.
- 세 목표가 모두 있는 장면에 전자레인지를 입력하고, 같은 장면에서 쓰레기통 하나만 제거한 다음 쓰레기통을 입력한다. 두 실험 모두 120스텝 동안 첫 STOP이 발생했는지 검사한다. 미발견은 공간 전체를 탐색했다는 판정과 구별한다.

## 학습

기존 소화기 H4 체크포인트에서 CNN·GRU를 초기화했다. 무작위로 물체를 배치한 Castle에서 4프레임 시범 4,100개를 생성하고 시퀀스 단위로 3,690개 학습, 410개 검증으로 분리했다. 같은 영상에 세 양성 이름과 부재 이름을 대응시켰다. 위치를 아는 교사가 물체가 보일 때 접근·정지, 안 보일 때 순찰하도록 레이블을 만든다. 시각·언어 검출기를 고정하고 H4의 시각 특징, 순환층, 목표별 주목 영역, 탐색·행동 헤드를 학습했다. 목표 근거의 세기에 따라 탐색과 접근 출력을 결합하는 게이트에는 고정된 신뢰도 사전값과 학습 가능한 항이 함께 있다. 배포 모델은 ONNX이고, 런타임에는 별도의 목표별 조종기나 규칙 STOP을 두지 않는다.

1. 위 로컬 서버를 켜고 `npm install --no-save playwright-core`로 수집기를 준비한다. Chrome을 설치한 환경에서 다음을 실행한다.

   ```sh
   node h4nav/collect.cjs broad /tmp/castle-broad
   node h4nav/collect.cjs near /tmp/castle-near
   ```

2. PyTorch, OpenCV, Ultralytics, OpenAI CLIP 및 ONNX가 설치된 환경에서 YOLOE-11s-seg와 MobileCLIP BLT 가중치를 지정해 시각 후보와 텍스트 특징을 준비한다.

   ```sh
   python h4nav/prepare.py /tmp/castle-broad /path/to/yoloe-11s-seg.pt /path/to/mobileclip_blt.ts
   python h4nav/prepare.py /tmp/castle-near /path/to/yoloe-11s-seg.pt /path/to/mobileclip_blt.ts
   python h4nav/train.py /tmp/castle-broad/train.npz /path/to/student-4.pt /tmp/h4-fit --extra /tmp/castle-near/train.npz --epochs 36
   ```

   `student-4.pt`는 [단계별 릴리스](https://github.com/Dabin0312/InFrame/releases/tag/v0.7.0)의 5단계 체크포인트다. 기본 장치는 Apple MPS다. CPU·CUDA는 각 Python 명령에 `--device cpu` 또는 `--device cuda`를 지정한다.

3. 기본 모델과 같은 실험은 `node h4nav/evaluate.cjs /tmp/h4-runs`로 실행한다. 시뮬레이터는 모델을 한 번에 하나만 실행하고, 출발 자세를 매번 초기화한다. 실행 기본값은 아래의 회복 시범까지 학습한 체크포인트다. 초기 정책만 실험하려면 실행 명령 끝에 `baseline`을 붙인다. 새로 학습한 체크포인트를 시험하려면 로컬 복사본의 `h4nav/student.onnx`에 내보낸 ONNX를 넣는다.

의자·쓰레기통·소화기는 양성 학습 범주다. 영문 이름을 자유 입력할 수 있으며, 미학습 물체에 대한 일반화 또는 실제 Go2 주행 성공은 이 실험의 검증 범위 밖이다. [장면·모델 출처](../spatial/NOTICES.md)

## 경계와 제자리 회전에서의 회복

기존 H4를 고정한 뒤, 별도 시드의 Castle 배치 640개에서 각 58스텝의 움직임을 수집했다. 카메라가 전진 후에도 같은 자리에 머무르는 경우와 좌우로 반복되는 경우를 포함한다. 학습용 교사는 전진 실패 시 옆으로 돌아 이동한 뒤 원래 방향을 회복하는 시범을 제공한다. 같은 방향 회전이 길어질 때의 전진 시범도 포함한다. 학습 560개와 검증 80개는 시퀀스 단위로 분리한다.

새 GRU는 직전 행동과 최신 RGB를 앞선 세 장과 비교한 밝기·색 변화량을 입력받는다. 숨은 상태는 경로 시작마다 초기화한다. 학습한 잔차는 ONNX 안에서 전진·좌회전·우회전 점수에 더해지며, 네 행동 중 최대 점수를 실행한다. STOP 점수는 기존 H4에서 온다. 외부에서 경로·충돌 신호·목표 좌표를 정책에 전달하지 않는다.

```sh
node h4nav/collect.cjs recovery /tmp/h4-recovery
python h4nav/train-recovery.py /tmp/h4-recovery/sequences.json h4nav/base-h4.pt /tmp/h4-fit-recovery --epochs 104
node h4nav/evaluate.cjs /tmp/h4-before baseline
node h4nav/evaluate.cjs /tmp/h4-after current
python h4nav/compare-runs.py /tmp/h4-before /tmp/h4-after /tmp/comparison.json
```

새 출발 자세·배치 네 개를 학습 전에 [고정](holdout.json)했다. 이전 검증에 쓰인 중앙 통로·재배치 장면의 두 실패는 개발에 사용했다. 같은 건물과 같은 3D 물체를 쓰며, 새 배치는 출발 자세와 물체의 배치를 바꾼다. 모델을 고정한 뒤 배치마다 세 종류의 목표, 없는 전자레인지, 등록 쓰레기통을 제거한 조건을 120스텝씩 비교한다. 모든 케이스에서 첫 RGB 해시·자세·장면·목표와 평가 규칙이 두 정책 사이에 일치하는지 검사한다. [회복층 학습 기록](recovery-fit.json)

## 화면 가장자리에서의 목표 획득

[같은 출발 자세의 지도·RGB](compare.html?study=peripheral&scene=unseen2&case=2) · [미사용 배치에서 직접 실행](../demo/search.html?study=peripheral&scene=blind1&case=2) · [오프라인 비교 화면](peripheral-viewer.zip)

기준 모델은 경계 회복을 학습한 `student.onnx`다. `peripheral.onnx`는 이를 포함하고, 목표 이름의 임베딩이 소화기와 가까울 때 원래 해상도(160×120)의 시각 특징을 함께 사용한다. 시각 헤드는 작은 물체의 마스크와 접근·정지 행동을 배운다. 방향 헤드는 훈련 중 교사가 계산한 통행 가능한 경로의 국소 방향과 탐색 방향을 RGB에서 예측한다. 실행 중에는 좌표, 경로, 가시성 정답을 전달하지 않는다. 의자와 쓰레기통은 기존 목표 조건 H4로 주행한다.

소화기 분기는 기존 4프레임 H4의 행동 점수를 제한된 범위에서 반영한다. 전진 명령 뒤 영상 변화가 없으면 내부 상태가 회전과 측면 이동을 유지한다. 네 프레임에서 두 시점이 반복되면 학습한 회전 인식기가 기존 H4 회복 출력을 12스텝 동안 사용하게 한다. 이 전환 시간과 우회 동작의 순서는 고정값이다.

```sh
node h4nav/collect.cjs peripheral /tmp/h4-edge-rgb
node h4nav/collect.cjs recovery /tmp/h4-recovery-sequences
python h4nav/train-peripheral.py /tmp/h4-edge-rgb h4nav/base-h4.pt h4nav/motion.pt /tmp/h4-peripheral --recovery-sequences /tmp/h4-recovery-sequences/sequences.json
node h4nav/evaluate.cjs /tmp/h4-old current peripheral
node h4nav/evaluate.cjs /tmp/h4-new peripheral peripheral
python h4nav/build-peripheral-report.py /tmp/h4-old /tmp/h4-new /tmp/h4-report
```

재학습에는 PyTorch, NumPy, OpenCV, Pillow, SciPy, ONNX가 필요하다. 실행기는 저장소의 두 고정 체크포인트를 비교한다. 새 가중치를 실험하려면 로컬 복사본의 `h4nav/peripheral.onnx`와 `peripheral-fit.json`에 학습 출력을 넣는다.

무작위 카메라 7,200개를 6,300개 학습·900개 검증으로 나눴다. 교대 회전은 별도의 회복 시퀀스 560개에서 학습하고 80개에서 검증했다. 기존 문제 배치와 1차 여섯 배치는 개발 기록으로 남겼다. 최종 여덟 배치는 별도 시드로 고정했다. 배치마다 세 목표, 전자레인지 부재, 쓰레기통 제거, 소화기 제거를 각각 120스텝 한도로 실행한다. [배치 정의](confirmation.json) · [시각·방향·회전 학습 기록](peripheral-fit.json) · [기존 정책 행동 분해](peripheral-diagnosis.json)

## 쓰레기통 유무에 따른 첫 STOP

같은 카메라와 장면에서 등록 쓰레기통만 넣고 뺀 3,400쌍의 RGB로 H4의 STOP 출력을 학습했다. 카메라 쌍 2,975개는 학습에, 425개는 체크포인트 선택에 사용했다. 소형 CNN이 쓰레기통의 위치와 근접·가시성을 학습하고, 시각 근거 점수가 기존 STOP과 이동 행동의 점수 차이를 조정한다. 이 연산과 목표 임베딩을 기존 H4와 하나의 ONNX 그래프로 묶었다. 실행 입력은 기존 모델과 같다.

새 출발 자세와 배치 24개는 실내 전역, 주행 경계, 벽면 패널 구역에서 8개씩 표집했다. 모든 위치에서 쓰레기통 찾기를 두 번 실행하며, 두 번째 실행에서 등록 쓰레기통을 제거한다. 의자와 소화기도 같은 출발 자세에서 실행한다. 이 실험의 검증 범위는 같은 Castle과 같은 등록 물체의 재배치다.

```sh
node h4nav/collect.cjs bin /tmp/h4-bin-pairs
python h4nav/train-bin-stop.py /tmp/h4-bin-pairs h4nav/peripheral.onnx h4nav/base-h4.pt /tmp/h4-bin-fit
node h4nav/evaluate.cjs /tmp/h4-bin-before peripheral bin
node h4nav/evaluate.cjs /tmp/h4-bin-after bin bin
python h4nav/build-bin-report.py /tmp/h4-bin-before /tmp/h4-bin-after /tmp/h4-bin-report
```

평가는 저장소의 고정 체크포인트를 사용한다. 학습을 다시 한 경우 로컬 복사본에서 `h4nav/bin-h4.onnx`와 `bin-fit.json`을 새 출력으로 교체해 비교할 수 있다. [배치·시드](bin-holdout.json) · [학습 기록](bin-fit.json) · [빈 벽 진단 기록](bin-diagnosis.json) · [전체 주행 기록](bin-report.json)


## 벽면에서 시작하는 탐색

기존 H4가 쓰레기통을 놓친 다섯 주행을 같은 카메라 자세에서 다시 렌더링했다. 17번과 21번은 제자리 회전, 19번과 24번은 시야 가장자리의 목표 상실, 23번은 접근 도중 스텝 한도에 도달한 사례다. [프레임별 가시 픽셀·경계 상자](panel-diagnosis.json) · [다섯 원본 장면](panel-diagnosis.png)

새 CNN은 별도 시드의 Castle RGB 5,425장으로 가려짐을 반영한 쓰레기통 마스크, 가시성, 열린 통로와 목표 쪽의 이동 방향을 학습했다. 775장은 체크포인트 선택에 사용했다. 교사는 학습용 NavMesh에서 방향을 계산한다. 실행 시 H4는 전방 RGB, 이름에서 얻은 임베딩, 이 RGB에서 산출한 시각 후보, 자기 행동 이력을 사용한다. ONNX 내부에서 카메라를 돌며 유망한 통로 방향을 기억하고, 관측한 쓰레기통의 방향을 잠시 유지한다. 회전·전진 시간과 우회 동작은 정해진 값이다. 기존 H4의 STOP 점수에 새 마스크의 크기·중심·가시성 조건을 적용했다. 이 분기는 쓰레기통 텍스트와 가까운 목표에 적용된다.

새 배치 24곳에는 벽면 패널 구역 16곳과 실내 전역·경계 각 4곳이 들어 있다. 같은 출발 자세와 배치에서 의자, 쓰레기통, 소화기와 쓰레기통 제거 조건을 각각 120스텝 한도로 돌린다. 판정에는 정책이 내린 첫 STOP을 쓴다. 평가 후의 구역 이탈은 출발 구역의 사각 범위를 벗어난 위치가 경로에 있는지로 표시한다. [실행 화면](../demo/search.html?study=panel&scene=bin21&case=1) · [검증 배치](panel-holdout.json) · [모델·배치 해시](panel-fit.json)

저장소 루트에서 HTTP 서버를 실행하고 기존 주행 환경에서 다음 명령으로 재현한다. 학습 단계를 생략하면 공개된 ONNX 두 개를 바로 비교할 수 있다.

```sh
node h4nav/collect.cjs panel /tmp/panel-train
python h4nav/train-panel.py /tmp/panel-train /tmp/panel-fit
python h4nav/export-panel.py /tmp/panel-fit/search-vision.pt h4nav/bin-h4.onnx h4nav/base-h4.pt /tmp/panel-fit/panel-h4.onnx
node h4nav/evaluate.cjs /tmp/panel-before bin panel
node h4nav/evaluate.cjs /tmp/panel-after panel panel
python h4nav/build-panel-report.py /tmp/panel-before /tmp/panel-after /tmp/panel-report
```

## 의자가 보이는 방향으로 접근하고 정지하기

[7번과 22번의 실패 프레임](chair-diagnosis.png) · [같은 출발점의 경로·정지 사진](compare.html?study=chair&scene=panel7&case=0) · [새 배치 24곳의 주행 기록](chair-report.json) · [오프라인 비교 화면](chair-viewer.zip)

기존 H4는 7번에서 전진이 막힌 뒤 화면 중앙에 보이던 의자를 놓쳤다. 22번에서는 목표가 보이지 않는 첫 화면에서 STOP을 냈다. 새 분기는 RGB에서 의자의 마스크·가시성·도착 여부와 이동 방향을 학습한다. H4 내부에서 직전에 본 의자의 방향을 기억하고 네 프레임의 행동 점수를 조향·정지 판단에 반영한다. 탐색 회전과 우회 동작의 길이는 고정값이다. 목표 좌표와 가시성 정답은 학습·채점에만 쓴다. 이 분기는 의자에 가까운 이름 임베딩에서 동작한다.

별도 시드로 카메라 자세 6,200개를 생성했다. 같은 자세에서 의자를 제거한 사진은 원본과 같은 분할에 넣었다. RGB 6,615장으로 학습하고 963장으로 체크포인트를 골랐다. 최종 검증은 Castle의 통로·경계·벽면 구역에서 새 출발점과 물체 배치를 각각 8개씩 고정했다. 각 배치에서 두 정책에 같은 시작 자세로 의자, 의자 제거, 쓰레기통, 소화기 네 조건을 실행한다. 개발에 사용한 7번·22번은 따로 표시한다. [검증 배치](chair-holdout.json) · [체크포인트 기록](chair-fit.json)

저장소 루트에서 HTTP 서버를 실행한 뒤 아래 명령으로 재현한다. 공개된 체크포인트를 사용하면 두 개의 평가 명령부터 실행할 수 있다.

```sh
node h4nav/collect.cjs chair /tmp/chair-train
python h4nav/train-panel.py /tmp/chair-train /tmp/chair-fit --target chair
python h4nav/export-panel.py /tmp/chair-fit/search-vision.pt h4nav/panel-h4.onnx h4nav/base-h4.pt /tmp/chair-fit/chair-h4.onnx --target chair
node h4nav/evaluate.cjs /tmp/chair-before panel chair
node h4nav/evaluate.cjs /tmp/chair-after chair chair
python h4nav/build-panel-report.py /tmp/chair-before /tmp/chair-after /tmp/chair-report --study chair
```

## 막힌 경계를 돌아 목표 다시 찾기

`escape-h4.onnx`는 이전 H4와 세 목표에 공통으로 쓰는 시각 모델·우회 모델을 하나의 정책으로 실행한다. 시각 모델은 RGB에서 등록 물체의 마스크·가시성·거리와 Castle 안의 카메라 자세를 추정한다. 회전하거나 목표가 가려지면 직전 행동과 프레임 변화로 마지막 관측의 상대 방향·거리를 갱신한다. 우회 모델은 이 관측에서 다음 이동 방향을 예측한다. 지도·센서 자세·충돌 플래그·목표 좌표를 실행 입력으로 전달하지 않는다. 기존 H4의 행동 점수와 정지 판단을 사용하며, 탐색 회전과 충돌 후 회복 시간은 모델 안의 고정 규칙이다. 의자 접근 중 전진이 막히면 직전에 실제로 이동한 쪽과 시각 모델의 우회 방향을 참고한다. 선택한 쪽으로 이동한 거리를 기억하면서 모서리를 돈다. 이 검증은 같은 건물과 같은 3D 물체에서 출발점과 배치를 바꾼 결과다.

두 모델을 먼저 고정하고 새 배치 24개에서 평가했다. 각 배치의 의자·쓰레기통·소화기와 의자 제거 조건에서 첫 RGB, 출발 자세, 장면 배치, 성공 기준, 120스텝 한도를 맞췄다. 기존 2번의 별도 실험은 같은 카메라와 행동을 각각 49·79스텝까지 재현한 후 남은 행동을 새 H4에 맡긴다. 인계 시 그전까지 실제로 실행한 행동과 RGB 이력을 사용한다. [배치와 시드](escape-holdout.json) · [학습 및 모델 해시](escape-fit.json) · [인계 실험 원본](escape-handoff.json)

```sh
node h4nav/evaluate.cjs /tmp/escape-before chair escape
node h4nav/evaluate.cjs /tmp/escape-after escape escape
python h4nav/build-panel-report.py /tmp/escape-before /tmp/escape-after /tmp/escape-report --study escape
node h4nav/replay-escape.cjs /tmp/handoff.json
```

학습을 재현하려면 앞에서 설명한 `chair`, `panel`, `peripheral` 수집기로 카메라 영상을 준비한다. 같은 위치에서 의자를 뺀 영상과 원본은 같은 분할에 둔다. 우회 방향 시범은 학습용 바닥에서 표집한 점 쌍으로 만든다. [새 배치 경로·사진](escape-routes.png) · [오프라인 비교 화면](escape-viewer.zip)

```sh
python h4nav/train-escape-vision.py /tmp/chair-train /tmp/panel-train /tmp/h4-edge-rgb /tmp/escape-fit
python h4nav/train-escape-route.py /tmp/escape-fit
python h4nav/export-escape.py h4nav/chair-h4.onnx /tmp/escape-fit h4nav/base-h4.pt /tmp/escape-fit/escape-h4.onnx
```

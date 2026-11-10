# Castle · 목표 조건 H4

[같은 출발점에서 목표 바꿔보기](https://dabin0312.github.io/InFrame/demo/search.html) · [실험 기록](report.json) · [학습 기록](fit.json)

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

3. 기본 모델과 같은 실험은 `node h4nav/evaluate.cjs /tmp/h4-runs`로 실행한다. 시뮬레이터는 모델을 한 번에 하나만 실행하고, 출발 자세를 매번 초기화한다. 새로 학습한 체크포인트를 시험하려면 로컬 복사본의 `h4nav/student.onnx`에 내보낸 ONNX를 넣는다.

의자·쓰레기통·소화기는 양성 학습 범주다. 영문 이름을 자유 입력할 수 있으며, 미학습 물체에 대한 일반화 또는 실제 Go2 주행 성공은 이 실험의 검증 범위 밖이다. [장면·모델 출처](../spatial/NOTICES.md)

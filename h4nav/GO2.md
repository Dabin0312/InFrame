# Multi-goal H4 on the Go2 mock camera

[주행 지도·정지 사진·스텝별 행동](https://dabin0312.github.io/InFrame/h4nav/go2-parity.html) · [검증 로그와 모델 SHA-256](go2-parity.json)

Castle의 브라우저 시뮬레이터와 Python 모의 어댑터는 같은 MobileCLIP, YOLOE, transfer-h4.onnx를 실행한다. 목표 이름과 시간순 RGB를 각각 독립 처리한다. 모의 카메라는 시뮬레이터의 각 프레임을 PNG로 다시 읽고 시뮬레이터의 행동·목표 좌표·포즈를 받지 않는다. 정책은 160×120 카메라, 80×60 RGB 네 장, 검출 후보와 노출 보정 후의 프레임 차이를 사용한다. 속도 제한은 정책이 행동을 선택한 뒤 적용된다.

저장소 루트에서 Python 3.10+, Node 및 Chrome을 사용한다. 재생 시뮬레이터만 Playwright가 필요하다.

```sh
python -m pip install numpy pillow opencv-python onnxruntime
npm install --no-save playwright-core
python -m http.server 8000 --bind 127.0.0.1
```

두 번째 터미널에서 실행한다. 첫 명령은 배치 escape13에서 세 목표의 RGB·행동·정지 사진을 생성한다. 다음 명령은 Go2 모의 카메라로 4 Hz 주행을 실행하고 첫 STOP과 매 스텝을 대조한다.

```sh
node h4nav/capture-parity.cjs http://127.0.0.1:8000 /tmp/inframe-castle escape13
python outputs/InFrame_7단계/src/check_multigoal.py /tmp/inframe-castle
python outputs/InFrame_7단계/src/check_exposure.py /tmp/inframe-castle
node spatial/check-footprint.cjs http://127.0.0.1:8000 /tmp/inframe-castle/feet.json
```

개별 모의 주행은 아래처럼 실행한다. 속도 요청과 실제로 보낸 명령은 JSON 로그에서 확인할 수 있다.

```sh
python outputs/InFrame_7단계/src/runtime.py --backend mock --goal '의자' \
  --recording /tmp/inframe-castle/chair/camera.npz --log /tmp/inframe-chair.json
```

기존 escape-h4의 가중치를 그대로 사용하고 밝기 변화에 민감했던 여섯 프레임 차이 연산을 교체했다. 그래프를 다시 생성하려면 `pip install onnx` 후 `python h4nav/export-transfer.py`를 실행한다. 과거 비교 기록은 당시 체크포인트를 사용한다. 실제 Go2의 카메라 지연, 보행 중 흔들림, 명령 추종 및 제동거리는 기체 검증 대상으로 남아 있다.

# H4의 첫 STOP

같은 영상에 기존 H4와 개선 H4를 4 Hz로 실행하고 첫 정지 행동을 기록합니다. [9편 비교](https://dabin0312.github.io/InFrame/h4/) · [내 영상으로 실행](https://dabin0312.github.io/InFrame/demo/) · [프레임별 행동·지도·정지 사진](replays.zip)

## 왜 멈추지 않았나

문제가 된 접근 영상의 10.00초에서 기존 H4는 남은 거리를 7.72 m로 추정했고 정지 로짓은 −13.62였습니다. 기본 정지는 추정 거리가 0.65 m 이하이고 정지 로짓이 0 이상일 때 작동합니다. 보조 정지 경로의 근접·준비 로짓도 각각 −6.44, −7.32로 기준 1.0, 0.9에 미달했습니다. 수치는 브라우저에 배포한 모델의 추정값입니다. 이 영상에는 실제 거리 정답이 없습니다. [동일 입력과 원본 출력](../spatial/approach-report.json)

기존 80×60 RGB의 이동·복구 제어를 보존하고, 동일한 4:3 중앙 시야를 320×240 RGB로도 읽는 정지 헤드를 학습했습니다. 동결한 YOLOE의 소화기 후보 점수·위치·크기로 여덟 특징을 만들고 현재 특징과 최근 네 관측 평균으로 로지스틱 행동 헤드를 학습합니다. 세 모듈을 한 ONNX 그래프로 결합했습니다. 학습한 정지 로짓이 0 이상이거나 기존 정지 경로가 활성화되면 정책이 전진 0, 회전 0, STOP 1을 반환합니다. 지도와 삼각측량은 정책 입력에서 독립적입니다. [학습](train.py) · [그래프 구성](build.py) · [실제 행동 출력](worker.mjs)

## 처음 쓰는 촬영본에서의 검증

원본 촬영 ID가 겹치지 않게 학습 9편, 개발 3편, 최종 평가 9편을 분리했습니다. 개발 3편에서 운용점을 고른 뒤 모델을 동결했습니다. 중앙 RGB를 이미지로 확인해 붙인 단일 판독 라벨을 사용했습니다. 독립 평가자 간 합의는 측정하지 않았습니다. 정책 출력 전에 소화기 본체나 손잡이를 알아볼 수 있고 대략 화면 높이의 10% 이상을 차지하는 구간을 표시했습니다. 닫힌 함과 안내 표지만 보이는 구간은 제외했습니다. 평가 단위는 촬영본별 최초 STOP 한 번입니다. [촬영본·출처](split.json) · [모델 해시와 개발 결과](frozen.json) · [판독 구간](holdout-labels.json)

| 최초 STOP 판정 | 기존 H4 | 개선 H4 |
| --- | ---: | ---: |
| 소화기가 보이는 5편에서 유효 정지 | 0/5 | 4/5 |
| 판독 가능한 소화기가 없는 4편에서 오정지 | 0/4 | 0/4 |

평가 영상은 실내 8편과 야외 교통 콘 대조 1편입니다. 청소 도구를 찾는 실내 영상에도 소화기가 보여 양성으로 집계했습니다. STOP 4건 중 3건에서 정지 프레임의 카메라 자세를 복원했습니다. 쇼핑몰 안내대 영상은 소화기를 지도에 등록했지만 판독 구간 내 최고 정지 로짓이 −0.00289였습니다. 문턱과 모델을 그대로 유지한 결과입니다. 학습에 사용한 문제 영상의 개선 후 STOP은 10.75초이며 위 표에서 제외했습니다.

녹화 경로 재생은 시각적 정지 의사결정을 검증합니다. 실제 거리, 자율 접근 성공률과 실기 제동은 별도 평가 대상입니다. Castle 기준 RGB 재생에서는 두 모델 모두 17.25초에 정지했고, 웹 기구학 시뮬레이터의 개선 모델은 FRESH-015에서 17.00초, FRESH-004에서 19.00초에 정지했으며 두 번 모두 소화기 C의 렌더 마스크가 보였습니다. 기존 릴리스의 51/60 및 Go2 모의 어댑터 검증은 해당 릴리스의 정책으로 측정했습니다.

## 재현

저장소 루트에서 실행합니다. 배포 모델은 [policy.onnx](policy.onnx)이며 SHA-256은 [frozen.json](frozen.json)에 있습니다. 학습 재현에 사용한 버전은 Python용 PyTorch 2.8.0, NumPy 2.2.6, ONNX 1.17.0입니다. 패키지에는 12편의 학습·개발 관측 특징만 포함합니다.

```sh
python -m pip install torch==2.8.0 numpy==2.2.6 onnx==1.17.0
unzip h4/training-features.zip -d work/features
python h4/train.py work/features work/fit
python h4/build.py . work/fit
```

평가 재실행에는 FFmpeg, 데스크톱 Chrome, Node.js가 필요합니다. 원본에서 16 Hz, 최대 너비 640인 무음 H.264로 변환했습니다. 사용한 FFmpeg는 6.1.1이며 검사한 파일별 해시는 [결과](results.json)의 media_sha256에 있습니다. 서버를 첫 터미널에서 열고 다음 명령을 두 번째 터미널에서 실행합니다.

```sh
python -m http.server 8000
```

```sh
python h4/get_holdout.py work/media
npm install --prefix work/browser playwright-core@1.65.0
NODE_PATH="$PWD/work/browser/node_modules" node h4/evaluate.cjs work/media work/runs
python -m pip install opencv-python==4.11.0.86
mkdir -p work/report
python h4/make_results.py work/media work/runs work/report
```

평가 결과의 JSON에는 프레임별 시간, 지도 구간, 카메라 자세, 소화기 관측, 두 정책의 활성 구간 행동과 점수가 있습니다. stop과 before에는 첫 STOP에서 정책에 넣은 RGB를 PNG로 보관합니다. 끝까지 STOP이 없으면 null입니다.

## 출처

촬영본과 파생 사진·장면 자료는 OpenDriveLab SparseVideoNav의 CC BY-NC-SA 4.0 조건을 따릅니다. 재배포 자료는 리사이즈, 중앙 크롭, 시간대 판독 및 지도화를 거쳤습니다. 평가 자료는 InFrame 학습·튜닝에서 격리한 촬영본입니다. [데이터셋](https://huggingface.co/datasets/OpenDriveLab/SparseVideoNav) · [라이선스](https://creativecommons.org/licenses/by-nc-sa/4.0/)

결합 ONNX는 소화기 프롬프트로 내보낸 YOLOE-11s의 AGPL-3.0 가중치를 포함합니다. 변환 코드와 기반 모델의 소스·라이선스를 함께 제공합니다. [모델·라이선스](../spatial/NOTICES.md) · [기반 H4](../demo/)

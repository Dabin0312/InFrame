# 처음 실행하는 순서

**영상만 보려면** [교사 주행](https://github.com/Dabin0312/InFrame/raw/refs/heads/main/evidence/teacher-run.mp4), [학생 비교](https://github.com/Dabin0312/InFrame/raw/refs/heads/main/evidence/student-comparison.mp4), [개선 후 남은 실패](https://github.com/Dabin0312/InFrame/raw/refs/heads/main/evidence/remaining-failure.mp4), [정상 정지와 입력 단절](https://github.com/Dabin0312/InFrame/raw/refs/heads/main/evidence/go2-stop.mp4)을 연다. MP4가 다운로드되면 로컬 플레이어로 재생한다. [검증 기록](evidence/)에는 각 숫자의 JSON·CSV 원본이 있다.

## 1. 데이터를 받는다

[릴리스 v0.7.0](https://github.com/Dabin0312/InFrame/releases/tag/v0.7.0)의 **inframe-stages-0-7.zip**에 단계별 코드, Fire 입력 일부, 장면, 교사 시범 297개, 학생 가중치, 주행 프레임과 비교 화면이 들어 있다. GitHub가 자동으로 만드는 Source code (zip)은 코드 열람용이다. 아래는 macOS/Linux 터미널 기준이다.

~~~sh
mkdir inframe-run && cd inframe-run
release=https://github.com/Dabin0312/InFrame/releases/download/v0.7.0
curl -fL "$release/inframe-stages-0-7.zip" -o inframe-stages-0-7.zip
curl -fL "$release/SHA256SUMS.txt" -o SHA256SUMS.txt
grep ' inframe-stages-0-7.zip$' SHA256SUMS.txt | shasum -a 256 -c -
unzip -q inframe-stages-0-7.zip
cd InFrame
~~~

### 설치 없이 같은 출발점에서 비교

압축을 푼 뒤 아래 HTML을 브라우저로 연다. 프레임·사진이 옆 폴더에 있으므로 압축은 전체를 푼다.

| 파일 | 볼 수 있는 것 |
|---|---|
| `outputs/InFrame_4단계/주행재생.html` | 교사의 경로와 카메라. 같은 출발에서 너무 일찍 멈춘 경우와 반대 방향을 보고 멈춘 경우 |
| `outputs/InFrame_6단계/주행비교.html` | 60개 출발점의 교사·두 학생을 같은 지도, 시점, 정지 사진으로 비교. 두 학생이 모두 실패한 10곳의 위치와 진단 |
| `outputs/InFrame_6단계_정책개선/개선전후_주행비교.html` | 별도 60개 출발점의 개선 전후. 제자리 회전·경계 충돌·남은 실패 |
| `outputs/InFrame_7단계/media/` | 정상 주행과 카메라 단절을 나란히 편집한 영상, 자동 정지 시점 사진 |

## 2. 시뮬레이터와 모델 환경을 설치한다

검증 기기는 Apple Silicon Mac이다. 시뮬레이터는 Habitat-Sim 0.3.3 / Python 3.9, 정책은 PyTorch 2.8 / Python 3.10에서 돌렸다. Conda와 Python 3.10이 필요하다. Habitat가 장면을 렌더링할 수 있는 그래픽 환경에서 실행한다. 학습 가중치를 제공하므로 평가에는 재학습이나 학습용 GPU가 필요하지 않다.

~~~sh
mkdir -p .venvs
conda env create --prefix "$PWD/.venvs/sim" -f environment-sim.yml
python3.10 -m venv .venvs/model
.venvs/model/bin/python -m pip install -r requirements-model.txt
export SIM_PY="$PWD/.venvs/sim/bin/python"
export MODEL_PY="$PWD/.venvs/model/bin/python"
"$SIM_PY" -c 'import habitat_sim, quaternion, trimesh'
"$MODEL_PY" -c 'import cv2, torch, scipy'
~~~

터미널을 새로 열면 압축을 푼 InFrame 폴더에서 위의 export 두 줄을 다시 실행한다.

## 3. 단계별로 실행한다

전체 순서는 `python3 reproduce.py all`이다. 한 단계씩 실행하려면 아래 표를 위에서부터 따라간다. 각 실행 결과는 화면에 표시되는 `work/runs/번호-임의문자/`에 생긴다.

| 단계 | 명령 | 실제 다시 수행하는 작업 / 대조할 결과 |
|---|---|---|
| 0 | `python3 reproduce.py 0` | STOP, 0.8 m 접근, 동일 ID 가시성, 누적 충돌 3회·150초 제한을 읽는다. |
| 1 | `python3 reproduce.py 1` | 작은 방에서 Habitat 주행을 다시 돌리고 저장된 TUM 추적 CSV에서 보고서를 재계산한다. 원시 영상으로 ORB-SLAM3를 빌드·실행하는 방법은 [시각 SLAM 가이드](stages/02-visual-slam/README.md)에 있다. [Fire의 두 궤적](evidence/fire-slam.json)은 기존 실측 기록이다. |
| 2 | `python3 reproduce.py 2` | 포함한 Fire RGB-D, SLAM 궤적, 검출 마스크로 의미 지도를 새로 만들고 사진 연결을 평가한다. 개선 모델의 저장 예측도 다시 채점해 77/82, 18/20을 대조한다. 원본 다운로드·분할 모델부터 다시 실행하는 명령은 패키지의 `outputs/InFrame_Fire_2단계{,_개선}/README.md`에 있다. |
| 3 | `python3 reproduce.py 3` | Fire 충돌 장면에서 이동·차단을 다시 시험하고 로봇 폭을 고려한 궤적 여유 공간을 검산한다. [구간별 대조](evidence/fire-traversability.json) |
| 4 | `python3 reproduce.py 4` | 교사 기록 386회를 읽고 분할·행동·종료점·최종 RGB를 독립 검증한다. 새 교사 시범 생성은 아래에 있다. [교사 기록](evidence/teacher.json) |
| 5 | `python3 reproduce.py 5` | 두 체크포인트를 각각 같은 60곳에서 폐루프 주행시킨다. 저장 영상 재생과 달리 정책이 낸 행동이 다음 RGB를 결정한다. 단일 프레임 46회, 4스텝 50회 성공. |
| 6 | `python3 reproduce.py 6` | 예약 구역 60곳에서 기존·개선 정책을 각각 주행시킨다. 38→51회 성공. 5단계 검증 집합과 출발점이 다르다. |
| 7 | `python3 reproduce.py 7` | 기록 RGB로 모의 SDK 실행 → 실제 시계로 단절 시험 → Habitat 정상 60회·저속 1회·단절 1회 → 명령·최종 RGB 독립 재검산. 정상 51/60, 전진 상한 0.40 m/s, 회전 상한 ±1.00 rad/s. |

**예측·학습부터 다시 하는 경우**　기본 명령은 배포한 가중치를 평가한다. 교사 시범과 학생을 직접 다시 만들려면 별도로 압축을 푼 작업 사본에서 아래 명령을 실행한다. 단계별 원본 스크립트 중 일부는 해당 사본의 체크포인트와 기존 기록을 갱신한다.

~~~sh
"$SIM_PY" outputs/InFrame_4단계/src/teacher.py
"$SIM_PY" outputs/InFrame_4단계/src/verify.py
mkdir -p work/student5
"$MODEL_PY" outputs/InFrame_5단계/src/prepare_data.py work/student5/train.npz
"$SIM_PY" outputs/InFrame_5단계/src/augment.py work/student5/views
"$MODEL_PY" outputs/InFrame_5단계/src/train.py work/student5/train.npz --views work/student5/views
python3 reproduce.py 5
~~~

6단계의 실패 재현, 교정 데이터 생성, 학습·봉인 순서와 코드 이름은 패키지의 `outputs/InFrame_6단계_정책개선/README.md`에 있다. 그 문서들의 역사적 경로 `work/sitepilot/env/bin/python`은 여기의 `"$SIM_PY"`, `work/fire-models/env/bin/python`은 `"$MODEL_PY"`에 해당한다. 재학습한 결과는 새 실험으로 보존한다. 7단계는 배포 시 봉인한 모델 해시를 검사한다.

## Go2 모의 시험만 빠르게 실행

[작은 패키지](https://github.com/Dabin0312/InFrame/releases/download/v0.7.0/inframe-go2-mock.zip)를 별도 폴더에 푼다. 이 경로에는 로봇·Habitat·Unitree SDK가 필요하지 않다.

~~~sh
cd go2-mock
python3.10 -m venv .venv
.venv/bin/python -m pip install 'torch==2.8.0' 'opencv-python==4.11.0.86' 'numpy==2.2.6' 'pillow==11.3.0'
.venv/bin/python src/runtime.py --backend mock --log my-session.json
.venv/bin/python src/safety_check.py --out my-safety.json
~~~

정상 예시에서는 FRESH-015의 RGB 70장을 읽어 시작 정지 1회, 이동 명령 69회, 목표 정지 1회를 기록한다. 감시 시험에서는 카메라 무응답 10회와 추론 정체·손상 프레임을 주입한다. 밀리초 값과 폐루프 세부 궤적은 실행마다 조금씩 달라질 수 있다.

## 실기 전 검증 경계

이 릴리스에서 확인한 마지막 지점은 **호스트에서 Go2 형식의 Move 또는 StopMove 호출이 발생하는 순간**이다. 모의 시험에서 단절 감지까지 약 0.20 m 이동했고, 정지 명령 후 시뮬레이터의 1초 변위는 0 m였다. 물리적 제동거리와 네트워크 단절 시 기체 측 동작은 측정하지 않았다. 현장 검증 항목과 복도·최종 사진 판독 기준은 [과제 명세](stages/00-task/README.md)에 있다. 실기에서는 카메라 화각·지연과 제동거리를 측정하고, 복도 통과 3곳·차단 3곳을 실측한 뒤 정지 사진의 소화기를 독립 판독자 2명이 식별한다.

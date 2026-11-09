# 1단계 · 로컬 시뮬레이터 검증

직접 만든 샘플 방을 Habitat-Sim에서 불러와 로봇 카메라로 렌더링하고, 장애물을 피해 목적지까지 연결되는 길과 벽 충돌 처리를 확인했다.

## 실행

검증 환경은 Apple Silicon macOS, Python 3.9, Habitat-Sim 0.3.3이다. Miniforge 설치 후 저장소 루트에서 실행한다.

~~~sh
conda env create -f stages/01-simulator/environment.yml
conda run -n inframe-simulator python stages/01-simulator/run.py --out work/simulator
~~~

스크립트가 장면, NavMesh, 시작·도착 시점 PNG, 평면 경로도와 결과 JSON을 출력한다. 마지막에 시작점·목표점의 접근 가능 여부, 경로 탐색 성공과 벽 차단을 검사한다.

| 기존 실행에서 확인한 항목 | 기록 |
| --- | --- |
| 장면과 NavMesh 생성 | 성공. 가상 로봇 반경 0.22 m, 높이 0.65 m |
| 샘플 방의 최단 경로 | 8.188 m |
| 벽 너머로 이동 요청 | x = 5.00 m 요청, x = 3.65 m에서 차단 |
| 로봇 시점 | [출발 화면](reference/start_rgb.png) · [도착 화면](reference/goal_rgb.png) |

**1단계 완료.** [결과 JSON](reference/result.json) · [경로와 충돌 지점](reference/topdown_path.png) · [샘플 장면과 NavMesh](reference/)

이 방은 시뮬레이터 기능 검사용이다. [작업실 통합 시연](../../#연결-과정)의 7.223 m는 별도로 RGB-D 스캔한 작업실에서 관측 지도로 계산한 경로다.

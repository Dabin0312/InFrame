# Try your own data

[브라우저에서 실행](https://dabin0312.github.io/InFrame/demo/) · [프로젝트](https://dabin0312.github.io/InFrame/)

실내 MP4를 선택하면 브라우저에서 AlvaAR로 카메라 자세를 추정하고 특징점과 YOLOE 소화기 관측을 삼각측량합니다. 지도는 각 추적 구간의 상대 척도입니다. 영상·지도·정지 사진은 같은 타임라인을 사용합니다.

- **기존 H4 / 개선 H4**는 같은 중앙 RGB에서 두 정책이 처음 STOP을 낸 시점과 입력 사진을 각각 표시합니다. 개선 정책은 최근 네 관측의 소화기 특징으로 정지 행동을 학습합니다. [정책과 실영상 평가](../h4/)
- **공개 영상**에서 SparseVideoNav 접근 구간과 전체 동선을 각각 다시 분석할 수 있습니다. Castle 기준 주행에서는 기록된 RGB와 시뮬레이터 기준 좌표를 사용합니다. [저장된 공개 검증 결과](https://dabin0312.github.io/InFrame/demo/?example=approach) · [데이터와 모델](../spatial/NOTICES.md)

## 모델

v0.7.0의 동결된 4스텝 체크포인트에서 신경망 세 개를 ONNX로 내보내고, 같은 정지·회전·진행 제어를 자바스크립트에 옮겼습니다. 샘플의 원본 RGB에서 기준 정책과 비교한 70개 행동은 전진·회전 오차 0.0001 이내로 일치했고 STOP은 17.25초였습니다. 변환하려면 릴리스의 작은 패키지를 풀고 모델 환경에서 실행합니다.

```sh
python -m pip install onnx==1.17.0
python demo/export_policy.py /path/to/go2-mock demo
```

브라우저는 번들에 포함한 ONNX Runtime Web 1.21.0의 단일 스레드 WASM 백엔드를 사용합니다. 로컬에서 보려면 저장소 루트에서 `python3 -m http.server 8000`을 실행하고 `http://localhost:8000/demo/`를 엽니다. [라이선스](vendor/LICENSE) · [서드파티 고지](vendor/ThirdPartyNotices.txt) · [데이터 출처](../DATA-NOTICES.md)

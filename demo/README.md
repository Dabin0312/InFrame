# Try your own data

[브라우저에서 실행](https://dabin0312.github.io/InFrame/demo/) · [프로젝트](https://dabin0312.github.io/InFrame/)

실내 RGB 영상을 고르면 브라우저가 4 Hz로 프레임을 읽습니다. 네 장의 영상 이력, 학습된 조향·정지 출력층과 시각적 이동량을 사용해 전진 속도(m/s), 회전 속도(rad/s), STOP을 계산합니다. JSON의 시각은 원본 영상 기준 초입니다. 지원 코덱은 브라우저에 따라 달라지며 H.264 MP4를 권장합니다.

**샘플**은 FRESH-015의 기록 RGB 70장을 무손실로 읽고 같은 타임라인의 MP4로 보여줍니다. 새 파일에는 브라우저가 디코딩한 영상이 들어갑니다. 손실 압축, 촬영 화각, 새로운 장소에 따라 명령이 달라질 수 있습니다. 목표 종류는 소화기입니다.

## 모델

v0.7.0의 동결된 4스텝 체크포인트에서 신경망 세 개를 ONNX로 내보내고, 같은 정지·회전·진행 제어를 자바스크립트에 옮겼습니다. 샘플의 원본 RGB에서 기준 정책과 비교한 70개 행동은 전진·회전 오차 0.0001 이내로 일치했고 STOP은 17.25초였습니다. 변환하려면 릴리스의 작은 패키지를 풀고 모델 환경에서 실행합니다.

```sh
python -m pip install onnx==1.17.0
python demo/export_policy.py /path/to/go2-mock demo
```

브라우저는 번들에 포함한 ONNX Runtime Web 1.21.0의 단일 스레드 WASM 백엔드를 사용합니다. 로컬에서 보려면 저장소 루트에서 `python3 -m http.server 8000`을 실행하고 `http://localhost:8000/demo/`를 엽니다. [라이선스](vendor/LICENSE) · [서드파티 고지](vendor/ThirdPartyNotices.txt) · [데이터 출처](../DATA-NOTICES.md)

# InFrame

**실내 의미 지도와 전방 RGB에 기반한 목표 객체 탐색 및 정지(ObjectNav).**

InFrame은 지정된 종류의 물체가 보이는 자리까지 이동하고, 첫 STOP 사진을 지도 위의 개체와 연결합니다. 소화기는 첫 검증 범주입니다. 현재 공개 모델의 검출·정지 가중치는 소화기에 맞춰져 있으며, 의자·쓰레기통에 대한 주행 평가는 후속 과제입니다.

[Project page](https://dabin0312.github.io/InFrame/) · [Try your own data](https://dabin0312.github.io/InFrame/demo/) · [주행 영상](https://dabin0312.github.io/InFrame/#run) · [Data & models](https://github.com/Dabin0312/InFrame/releases/tag/v0.7.0)

[![InFrame 시스템 프레임워크. 지도 구성, 교사 학습, RGB 정책, 모의 Go2와 실기 검증 계획](project/framework.png)](https://dabin0312.github.io/InFrame/#method)

[편집용 Figma 원본](https://www.figma.com/design/51O4U6yauUxvwLy8aRX9rI/InFrame?node-id=2-2) · [영상과 같은 공간의 지도 보기](https://dabin0312.github.io/InFrame/#run)

## Try your own data

[새 공개 영상 9편의 정책 비교](https://dabin0312.github.io/InFrame/h4/) · [공개 실내 영상의 결과 열기](https://dabin0312.github.io/InFrame/demo/?example=approach) · [내 영상으로 실행](https://dabin0312.github.io/InFrame/demo/) · [Go2 주행 직접 실행](https://dabin0312.github.io/InFrame/#live)

촬영한 MP4를 선택하면 카메라 영상, 그 영상에서 복원한 단안 SLAM 지도, 정지 장면을 함께 볼 수 있습니다. 지도에서 소화기를 선택하면 관측한 프레임으로 이동합니다. 기존 H4와 실영상으로 정지 행동을 학습한 H4의 첫 STOP을 비교할 수 있습니다. 영상은 브라우저에서 처리하며 관측과 지도는 JSON으로 저장할 수 있습니다.

## Method

1. **Semantic SLAM.** 7-Scenes Fire의 RGB-D 궤적과 분할 마스크를 결합해 실물 소화기 A·B를 지도에 등록하고 서로 다른 시점의 사진을 연결합니다.
2. **ObjectNav.** Skokloster Castle 스캔에 소화기 C를 배치하고 지도 기반 교사의 성공 시범 297개로 학생 정책을 학습합니다. 개선한 4스텝 정책은 같은 건물의 예약 출발점 60곳 중 51곳에서 소화기가 보이는 위치에 정지했습니다.
3. **Go2 interface.** 같은 정책을 모의 어댑터에 연결해 RGB 입력, 속도 제한, 정지 명령을 검증했습니다. 실제 기체 주행은 후속 평가입니다.

## Run locally

[릴리스](https://github.com/Dabin0312/InFrame/releases/tag/v0.7.0)에서 전체 재현용 `inframe-stages-0-7.zip` 또는 모의 어댑터용 `inframe-go2-mock.zip`을 받으세요. 전체 묶음은 압축을 풀고 [환경 설정](RUNBOOK.md)을 마친 뒤 아래 명령으로 실행합니다.

```sh
python3 reproduce.py all
```

[단계별 실행 방법](RUNBOOK.md) · [검증 기록](evidence/) · [데이터 출처 및 라이선스](DATA-NOTICES.md)

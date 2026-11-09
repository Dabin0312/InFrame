# In Frame

[프로젝트 페이지](https://dabin0312.github.io/InFrame/) · 실내 영상 SLAM과 목표 객체 탐색(ObjectNav)

실내 영상을 3D 지도로 만드는 과정과 로봇이 목표 앞에서 멈추는 과정을 재생한다. 단계 이름이나 재생 막대를 누르면 해당 시점으로 이동한다. 동작 줄이기 설정에서는 재생 버튼으로 시작한다.

## 실내 영상과 지도

TUM fr1/xyz의 RGB 798프레임을 ORB-SLAM3 단안 모드로 처리해 794프레임의 자세와 최종 희소 지도점 3,381개를 얻었다. 영상·지도는 이 실행에서 같은 시각을 가리킨다.

- **실내 영상**은 추적된 구간에서 RGB 192장을 시간순으로 선택해 12초로 압축한 것이다. 영상의 시각은 원본 시퀀스 시작 후 경과 시간이다.
- **공간 표면**은 그중 매 네 번째 RGB 프레임에 대해 25 ms 이내의 정렬된 깊이 영상을 대응시켜 만든다. TUM 기준 궤적과 단안 궤적의 유사변환에서 구한 단일 척도를 적용하고, 각 프레임의 ORB-SLAM3 자세로 색상과 3D 좌표를 변환한다. 1.9 cm 복셀에 처음 들어온 표본을 촬영 순서로 쌓는다.
- **SLAM 지도점**을 누르면 같은 ORB-SLAM3 실행에서 저장한 최종 희소 지도를 본다. 카메라 위치와 방향은 선택한 프레임을 따른다. 지도를 드래그하면 관점을 바꿀 수 있다.

원본 데이터는 J. Sturm, N. Engelhard, F. Endres, W. Burgard, D. Cremers, *A Benchmark for the Evaluation of RGB-D SLAM Systems*, IROS 2012. 페이지용 파일은 프레임 선택·축소·재인코딩과 깊이 역투영을 거쳤다. [TUM RGB-D Benchmark](https://cvg.cit.tum.de/data/datasets/rgbd-dataset) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) · [ORB-SLAM3](https://github.com/UZ-SLAMLab/ORB_SLAM3).

## ObjectNav 주행

두 번째 실험은 독립된 실내 시뮬레이션이다. Habitat-Sim에서 구한 8.188 m 참조 경로를 따라 소화기의 지정 관측 지점에 접근한다. 페이지에서는 경로와 현재 로봇 자세를 재생하고 카메라 시야각과 장애물 가림으로 목표의 가시 여부를 계산한다. STOP에서는 관측 지점 도착과 목표 가시 여부를 확인한다. 같은 위치에서 ‘뒤돌아보기’를 누르면 정지 방향에 따른 판정 차이가 보인다. 이 시연은 지도 기반 교사 경로이며, 실제 복도 주행과 학습 정책 평가는 후속 단계다. [Habitat-Sim](https://github.com/facebookresearch/habitat-sim).

‘직접 주행’에서 WASD나 바닥 클릭으로 이동하고 화살표로 회전한다. 모바일에서는 조이스틱과 회전 버튼을 사용한다. ‘시연으로 돌아가기’로 마지막 재생 위치에 돌아간다.

## 평가 계획

추론 입력은 전방 영상, 목표 종류, 행동 이력이다. STOP 시 지정 관측 지점까지 경로 거리가 0.8 m 이내이고 같은 목표가 정지 화면에 보일 때 성공으로 센다. 미학습 출발 자세 20개 × 목표 3종에서 60회 중 42회 이상 성공을 목표로 한다. 현장 촬영 뒤 실제 복도의 통과 구간 3곳과 차단 구간 3곳을 재구성한 장면과 대조한다.

## 로컬 실행

이 디렉터리에서 `python3 -m http.server 8000`을 실행하고 `http://localhost:8000`을 연다. 로봇 장면은 Three.js 또는 Canvas 2D로 표시한다. 배포본에 Three.js의 MIT와 Geist 및 Pretendard의 SIL Open Font License가 포함되어 있다.

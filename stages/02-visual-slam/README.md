# 2단계 · 실제 영상 SLAM

휴대폰 영상에서 프레임을 추출해 ORB-SLAM3으로 카메라 궤적과 희소 지도점을 계산한다. 실측 거리가 있으면 결과를 미터 단위로 환산한다. **공개 영상에서 입력부터 결과 저장까지 실행했고, 실제 복도 검증은 촬영 자료를 기다리고 있다.** [현장 촬영 순서와 인쇄용 보정판](CAPTURE.md)

## 공개 영상 검증

TUM RGB-D 벤치마크의 freiburg1_xyz 시퀀스에서 RGB만 입력한 단안 실행이다. 제공된 카메라 보정값을 사용했다. 아래 수치는 보관한 실행 1회의 결과다. [TUM RGB-D 데이터셋과 인용 정보](https://cvg.cit.tum.de/data/datasets/rgbd-dataset)

| 기록 | 검증값 |
| --- | --- |
| 전체 프레임 / 추적 상태 OK | 798 / 794 (99.5%) |
| 키프레임 / 희소 지도점 | 56 / 3,381 |
| 추적 상실 후 복구 이벤트 / 큰 지도 변경 이벤트 | 각각 0건 |
| 단안 척도 | 이 실행에는 현장 실측 기준이 없어 SLAM 자체 단위로 저장 |

[프레임별 상태 CSV](reference/TrackingStatus.csv) · [집계 JSON](reference/tracking_report.json) · [카메라 궤적](reference/poses.json) · [지도점](reference/map_points.json) · [궤적 그림](reference/trajectory_xz.png)

저장소 구조로 옮긴 뒤 같은 영상과 기존 로컬 엔진으로 다시 실행했다. 두 번째 실행에서는 **792/798프레임**, 키프레임 55개, 지도점 3,205개를 얻었다. 처음 실행의 프레임별 CSV를 다시 집계한 값은 원본 보고서와 일치했다. [재실행 추적 보고서](reference/repeat_tracking_report.json)

## 1. 환경과 엔진 준비

다음 명령은 저장소 루트에서 실행한다. Apple Silicon macOS에서 Xcode Command Line Tools와 Miniforge의 conda가 필요하다. 빌드 스크립트가 전용 환경과 ORB-SLAM3 체크아웃을 work 아래에 만든다. macOS 빌드 수정과 결과 내보내기 코드는 고정된 원본 커밋에 패치로 적용한다. [ORB-SLAM3 원본](https://github.com/UZ-SLAMLab/ORB_SLAM3/tree/4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4) · [패치](orb_slam3_macos.patch) · [원본 GPLv3 라이선스](ORB-SLAM3-LICENSE.txt)

~~~sh
bash stages/02-visual-slam/build_local.sh
slam_py=work/envs/slam/bin/python
stage=stages/02-visual-slam
orb=work/vendor/ORB_SLAM3
~~~

## 2. 공개 샘플 실행과 기록 대조

위 TUM 페이지에서 freiburg1_xyz 전체 시퀀스를 받아 work/data 아래에 푼다. 아래 첫 명령이 생성하는 새 결과와 저장된 reference를 비교한다. 병렬로 동작하는 SLAM의 추적 수와 지도점 수는 재실행마다 달라질 수 있다. 두 번째 명령은 같은 CSV에서 기존 보고서를 다시 계산한다.

~~~sh
"$slam_py" "$stage/run_slam.py" work/data/rgbd_dataset_freiburg1_xyz "$orb/Examples/Monocular/TUM1.yaml" work/tum-run
"$slam_py" "$stage/slam_io.py" report "$stage/reference/TrackingStatus.csv" work/recount.json
cmp work/recount.json "$stage/reference/tracking_report.json"
"$slam_py" "$stage/render_trajectory.py" work/tum-run/poses.json work/tum-run/map_points.json work/tum-run/trajectory_xz.png
~~~

## 3. 휴대폰 자료 처리

아래는 촬영 파일을 work/site_01 아래에 둔 예시다. 보정판도 동영상 모드로 찍으면 복도 영상과 렌즈·화각을 맞추기 쉽다. 보정판을 한 자세에 약 2초씩 멈춰 찍은 뒤, 추출된 보정 프레임 중 흔들리거나 같은 자세가 반복된 것은 제외한다. 아래 18 mm, 8초, 17초, 2 m는 **명령 예시**이며 실제 측정값으로 교체한다.

~~~sh
site=work/site_01
"$slam_py" "$stage/slam_io.py" prepare "$site/board.mov" "$site/board-frames" --fps 1 --max-width 960
"$slam_py" "$stage/slam_io.py" calibrate "$site/board-frames/rgb" "$site/camera.json" --glob '*.png' --columns 9 --rows 6 --square-m 0.018
"$slam_py" "$stage/slam_io.py" prepare "$site/main.mov" "$site/main" --fps 15 --max-width 960
"$slam_py" "$stage/slam_io.py" make-config "$site/camera.json" "$site/main/frames.json" "$site/camera.yaml"
"$slam_py" "$stage/run_slam.py" "$site/main" "$site/camera.yaml" "$site/main-run" --anchor-a 8 --anchor-b 17 --distance-m 2.00
"$slam_py" "$stage/render_trajectory.py" "$site/main-run/poses.json" "$site/main-run/map_points.json" "$site/main-run/trajectory_xz.png"
~~~

같은 설정·화각으로 찍은 보정 사진이 있으면 사진 폴더로 calibrate를 바로 실행한다. 동일한 카메라 설정의 내부 파라미터 JSON이 있으면 make-config부터 사용할 수 있다. A·B 거리 없이 run_slam.py를 실행할 수도 있다. 이 경우 SLAM 단위 위치만 채우고 미터 척도는 보류한다.

## 4. 재방문과 현장 판정

~~~sh
"$slam_py" "$stage/slam_io.py" prepare "$site/revisit.mov" "$site/revisit" --fps 15 --max-width 960
"$slam_py" "$stage/slam_io.py" combine "$site/main" "$site/revisit" "$site/both"
"$slam_py" "$stage/run_slam.py" "$site/both" "$site/camera.yaml" "$site/revisit-run"
~~~

두 구간은 같은 해상도·카메라 설정을 사용한다. 결합본은 원본 프레임을 참조하므로 검사할 때까지 두 입력 폴더를 보관한다. 첫 영상의 출발·귀환 위치 및 방향을 현장 사진과 대조하고, 두 번째 영상에서 같은 문·코너가 첫 지도상의 같은 위치와 대응하는지 확인한다. 상태 로그만으로 루프 클로저나 정확한 재위치를 확정할 수 없어 대응 프레임과 궤적을 함께 남긴다. 최종 복도 통과·차단과 정지 시야는 [0단계 판정 기준](../00-task/)으로 별도 평가한다.

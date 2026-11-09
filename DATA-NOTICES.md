# 데이터 출처와 배포 조건

| 자료 | 배포본에 포함한 부분과 변경 사항 (2026-11-09~10) | 제작자·원본·조건 |
|---|---|---|
| 7-Scenes Fire | 재현에 필요한 일부 등록 RGB·깊이·자세, 카메라 파라미터, 파생 마스크·사진 연결·충돌 지도·근접 주행. 원본 프레임 이름을 유지했다. | Microsoft Research, *Scene Coordinate Regression Forests for Camera Relocalization in RGB-D Images*, Shotton et al., CVPR 2013. [원본 및 MSR 라이선스](https://www.microsoft.com/en-us/research/project/rgb-d-dataset-7-scenes/) · [등록 RGB-D 배포처](https://3dmatch.cs.princeton.edu/) · [동봉된 라이선스 원문](DATA-LICENSE-7SCENES.rtf) |
| The King’s Hall, Skokloster Castle | Habitat 스캔 좌표를 변환하고 실험용 소화기 C, 관측점과 NavMesh를 추가했다. 주행 사진·영상은 이 수정 장면에서 렌더링했다. | Skoklosters slott. [원본 스캔](https://sketchfab.com/3d-models/the-king-s-hall-d18155613363445b9b68c0c67196d98d) · [Habitat 배포본](https://huggingface.co/datasets/ai-habitat/habitat_test_scenes) · [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) |
| Korean Fire Extinguisher 01 | 크기·방향·위치를 장면에 맞춰 배치하고 렌더링했다. | UM JOORIN / Poly Haven. [원본·CC0](https://polyhaven.com/a/korean_fire_extinguisher_01) |

MSR 7-Scenes 데이터에는 동봉한 비상업 연구 이용 조건이 적용된다. 외부 모델·라이브러리에는 각 배포자의 조건이 적용된다. [ORB-SLAM3](https://github.com/UZ-SLAMLab/ORB_SLAM3) · [Grounding DINO](https://github.com/IDEA-Research/GroundingDINO) · [SAM 2](https://github.com/facebookresearch/sam2) · [Habitat-Sim](https://github.com/facebookresearch/habitat-sim) · [Unitree SDK2 Python](https://github.com/unitreerobotics/unitree_sdk2_python)

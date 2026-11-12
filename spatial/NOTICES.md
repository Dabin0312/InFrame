# Spatial demo

## Public indoor validation

OpenDriveLab, *SparseVideoNav*, BVN episode `d39b9a4ef7409c87`. This recording diagnoses the original H4 and belongs to training for the updated STOP head. It is excluded from the new nine-recording holdout. Both clips are silent, resized to 640×480, and encoded at 16 Hz. The shorter clip begins 16 seconds into the source. Times shown in the viewer are relative to the selected file. The two MP4s, extracted photo, and sample-specific analysis are made available under CC BY-NC-SA 4.0. [Dataset](https://huggingface.co/datasets/OpenDriveLab/SparseVideoNav) · [Source recording](https://huggingface.co/datasets/OpenDriveLab/SparseVideoNav/blob/main/raw_videos/bvn/d39b9a4ef7409c87.mp4) · [License](https://creativecommons.org/licenses/by-nc-sa/4.0/)

The downloadable report was produced by selecting the short MP4 through the same file input used for personal videos. At 640×480 the final triangulated point reprojects inside its associated detector box in 17 of 17 observations. The median distance to the box centre is 7.3 pixels. This checks image-to-map consistency. Physical coordinate error requires independent 3D ground truth. The darker glass and the overlapping extinguishers can produce multiple observation tracks. A track ID identifies evidence linked over time.

[Recorded browser output](approach-report.json) · [Source clip used for the file upload](approach.mp4) · [Policy comparison on independent recordings](../h4/)

## Project teaser and framework

The real-video project teaser uses seconds 37.00–43.00 of SparseVideoNav BVN recording `fe75cd3028c834ef`, trimmed and re-encoded for playback. Its overlaid observations, reconstructed camera path and 43.00 s STOP are from the [same held-out run](../h4/). [Source recording](https://huggingface.co/datasets/OpenDriveLab/SparseVideoNav/blob/main/raw_videos/bvn/fe75cd3028c834ef.mp4) · [License](https://creativecommons.org/licenses/by-nc-sa/4.0/)

## Browser mapper and detector

- AlvaAR by Alan Ross, GPL-3.0, revision 7796af500ee92001ac2a9888363ff64d7a3bee75. The release module embeds its WASM runtime. The desk clip is the upstream video example. [Corresponding source and build instructions](https://github.com/alanross/AlvaAR/tree/7796af500ee92001ac2a9888363ff64d7a3bee75) · [License](LICENSE-AlvaAR.txt)
- jsfeat 0.0.8 by Eugene Zatepyakin, MIT. FAST keypoints and pyramidal Lucas–Kanade tracks support sparse multi-view triangulation. [Source](https://github.com/inspirit/jsfeat) · [License](LICENSE-jsfeat.txt)
- YOLOE-11s-seg, Ultralytics 8.3.200, AGPL-3.0. The checkpoint is re-parameterized for the single prompt “fire extinguisher” using MobileCLIP. The 320×320 ONNX graph exports boxes and scores. Convolution weights use per-channel int8 storage with float dequantization. [YOLOE](https://github.com/THU-MIG/yoloe) · [Ultralytics release source](https://github.com/ultralytics/ultralytics/tree/v8.3.200) · [Conversion script](export-detector.py) · [License](LICENSE-YOLOE.txt)
- The navigation policy and ONNX Runtime Web 1.21.0 come from the existing InFrame deployment. [Model and reference replay](../demo/README.md) · [ONNX Runtime license](../demo/vendor/LICENSE)

## Live simulation

The camera sees the textured castle scan and the registered Poly Haven target. The exterior view uses the same traversable floor triangles and coordinate system. The supervised H4 policy reads 192×144 camera RGB. A body-velocity integrator advances the camera on the NavMesh at 0.25-second policy intervals. Camera orbit and playback speed are viewer controls. At STOP a second, depth-tested render counts visible target pixels. Joint movement is animated for display. Physical Go2 testing remains a separate stage.

- Skokloster Castle and extinguisher C. Web assets use compressed geometry and resized textures. [Source and original licenses](../DATA-NOTICES.md)
- Unitree Robotics Go2 visual meshes from MuJoCo Menagerie, BSD-3-Clause. OBJ parts and XML hierarchy converted to glTF. [Corresponding model](https://github.com/google-deepmind/mujoco_menagerie/tree/98a70c569c4c1b6da467a20012f766ee1f8dc521/unitree_go2) · [License](LICENSE-go2.txt)
- Three.js 0.187.0, MIT, and meshoptimizer, MIT. [Three.js](https://github.com/mrdoob/three.js) · [License](LICENSE-three.txt) · [meshoptimizer](https://github.com/zeux/meshoptimizer) · [License](LICENSE-meshopt.txt)

## Multi-goal extension

The chair and bin are placed once in the Castle scene. Both RGB and the overview render their geometry. Models are scaled, repositioned, texture-resized and meshopt-compressed for the browser. [Plastic Monobloc Chair](https://polyhaven.com/a/plastic_monobloc_chair_01) · [Metal Trash Can](https://polyhaven.com/a/metal_trash_can) · [Poly Haven CC0 license](https://polyhaven.com/license)

The two additional video examples are OpenDriveLab SparseVideoNav recordings `3120aeb0b735e436` (gallery chair) and `067e8e394345e3cb` (elevator bins). Resized recordings and derived frames are distributed under CC BY-NC-SA 4.0. [Dataset revision](https://huggingface.co/datasets/OpenDriveLab/SparseVideoNav/tree/c986feef0f63cd688d8b0835320516dd9aa76280) · [License](https://creativecommons.org/licenses/by-nc-sa/4.0/)

The two-channel indoor detector uses the same YOLOE-11s weights, text encoder and AGPL-3.0 terms listed above. Rebuild with `python export-detector.py --indoor --output indoor.onnx`. Channel 0 is chair and channel 1 is trash can.

The approach examples on the project page pair the gallery recording `3120aeb0b735e436` (frames at 12.00 and 28.00 s, a map derived with AlvaAR, and the associated chair detection; CC BY-NC-SA 4.0 as above) with the FRESH-015 Castle bin run (NavMesh, commanded velocities and robot-camera frame at 16.75 s). The Castle scan is credited in [project sources](../DATA-NOTICES.md) and the bin asset above. The gallery and Castle are separate scenes.

The system figure pairs the registered Fire RGB frame (seq-01, 000000) with a projection of its RGB-D cloud, camera path and object anchors. The Castle teacher path and frames 0, 44 and 88 come from C-train-000. The inference panels reproduce the last four RGB frames and final action logits of [Castle layout 13, chair, updated H4](../h4nav/escape-trial-escape13.json). Camera images are simulation observations of the credited Castle scan and object assets. The Go2 command diagram describes the three-goal ONNX mock parity and camera timeout test. [Dataset and asset credits](../DATA-NOTICES.md).

## Runtime text prompts

The 416 px YOLOE-11s segmentation graph accepts an image and a 512-dimensional MobileCLIP-B(LT) embedding. The text encoder is stored in four chunks and evaluated locally once per run. Predefined goals retain their original exports. The free-prompt path uses instance masks, camera poses and a later-view reprojection check. The short reverse pass initializes the monocular mapper from the recording itself. [Model export](export-open.py) · [Ultralytics 8.3.200](https://github.com/ultralytics/ultralytics/tree/v8.3.200) · [MobileCLIP model terms](LICENSE-MobileCLIP.txt) · [MobileCLIP](https://github.com/apple/ml-mobileclip) · [CLIP tokenizer](https://github.com/openai/CLIP)

The sign clip contains the first 80 RGB frames of Microsoft Research 7-Scenes Fire sequence 01, played at 16 fps. Its browser example uses only RGB. The separate metric validation uses registered depth, calibrated intrinsics and ORB-SLAM3 poses. [7-Scenes](https://www.microsoft.com/en-us/research/project/rgb-d-dataset-7-scenes/) · [Dataset terms](../DATA-LICENSE-7SCENES.rtf) · [Verification script](../evidence/verify-sign.py)

The two-room simulation uses original procedural geometry. The other search scene uses the project’s Skokloster Castle scan and its NavMesh, with a 4.5 × 5 m search region. Both environments render the cone at scene time; its coordinates are withheld from the controller. The search controller receives the robot pose, detections and contact feedback. Only the renderer and evaluator know which prop was placed where. [Policy](search-policy.mjs) · [Simulator](search-bench.mjs)

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONDA_BIN="${CONDA_EXE:-conda}"
ENV_DIR="$PROJECT_DIR/work/envs/slam"
ORB_DIR="$PROJECT_DIR/work/vendor/ORB_SLAM3"
ORB_COMMIT="4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4"

if ! command -v "$CONDA_BIN" >/dev/null 2>&1; then
  echo "Install Miniforge for macOS arm64 and make conda available." >&2
  exit 1
fi
if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  mkdir -p "$(dirname "$ENV_DIR")"
  "$CONDA_BIN" env create -f "$SCRIPT_DIR/environment.yml" -p "$ENV_DIR"
fi
mkdir -p "$(dirname "$ORB_DIR")"
if [[ ! -d "$ORB_DIR/.git" ]]; then
  git clone --depth 1 https://github.com/UZ-SLAMLab/ORB_SLAM3.git "$ORB_DIR"
fi
if [[ "$(git -C "$ORB_DIR" rev-parse HEAD)" != "$ORB_COMMIT" ]]; then
  git -C "$ORB_DIR" fetch --depth 1 origin "$ORB_COMMIT"
  git -C "$ORB_DIR" checkout --detach "$ORB_COMMIT"
fi
if git -C "$ORB_DIR" apply --check "$SCRIPT_DIR/orb_slam3_macos.patch" 2>/dev/null; then
  git -C "$ORB_DIR" apply "$SCRIPT_DIR/orb_slam3_macos.patch"
elif ! git -C "$ORB_DIR" apply --reverse --check "$SCRIPT_DIR/orb_slam3_macos.patch" 2>/dev/null; then
  echo "ORB-SLAM3 checkout differs from the pinned InFrame patch." >&2
  exit 1
fi
if [[ ! -f "$ORB_DIR/Vocabulary/ORBvoc.txt" ]]; then
  tar -xzf "$ORB_DIR/Vocabulary/ORBvoc.txt.tar.gz" -C "$ORB_DIR/Vocabulary"
fi
for component in DBoW2 g2o; do
  "$ENV_DIR/bin/cmake" -S "$ORB_DIR/Thirdparty/$component" -B "$ORB_DIR/Thirdparty/$component/build" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$ENV_DIR" -DCMAKE_CXX_FLAGS="-I$ENV_DIR/include"
  "$ENV_DIR/bin/cmake" --build "$ORB_DIR/Thirdparty/$component/build" -j 4
done
"$ENV_DIR/bin/cmake" -S "$ORB_DIR" -B "$ORB_DIR/build" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$ENV_DIR" \
  -DCMAKE_CXX_FLAGS="-I$ENV_DIR/include" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$ENV_DIR/lib" \
  -DCMAKE_SHARED_LINKER_FLAGS="-L$ENV_DIR/lib"
"$ENV_DIR/bin/cmake" --build "$ORB_DIR/build" --target mono_tum -j 4
echo "Built $ORB_DIR/Examples/Monocular/mono_tum"

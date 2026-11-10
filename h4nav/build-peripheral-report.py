"""Check paired, closed-loop runs and publish one independently loadable bundle per layout."""

import argparse
import hashlib
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
validate_run = runpy.run_path(str(ROOT / "compare-runs.py"))["validate_run"]


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(pairs, field):
    return dict(
        total=len(pairs), **{key: sum(p[key][field] for p in pairs) for key in ("before", "after")}
    )


def main():
    p = argparse.ArgumentParser()
    for key in ["before", "after", "out"]:
        p.add_argument(key, type=Path)
    args = p.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    development = load(ROOT / "edge-holdout.json")
    held = load(ROOT / "confirmation.json")
    assert (
        digest(ROOT / "confirmation.json")
        == "47eb52710f08a55356ba4cda9ac49c09c6e90b12996f3d80a8e8a1cffa22822f"
    )
    prior = load(ROOT / "holdout.json")
    new_hash = digest(ROOT / "peripheral.onnx")
    old_hash = digest(ROOT / "student.onnx")
    assert new_hash == load(ROOT / "peripheral-fit.json")["model_sha256"]
    assert old_hash == load(ROOT / "recovery-fit.json")["onnx_sha256"]
    assert (
        digest(ROOT / "edge-holdout.json")
        == "ac9beecbc2c3d08b60bf203281161c394a2f0ae1113a5d00f4b960bd86f71664"
    )
    layouts = {"unseen2": "이전 배치 2 · 원인 재현"}
    layouts.update({k: "최종 미사용 배치 " + k[5:] for k in held["layouts"]})
    layouts.update({k: "1차 검증 배치 " + k[4:] for k in development["layouts"]})
    layouts.update(gallery="기존 중앙 통로", fresh="기존 FRESH-015", transfer="기존 재배치")
    layouts.update({k: "이전 배치 " + k[6:] for k in prior["layouts"] if k not in layouts})
    traces = {}
    blind = []
    archived = {(p["layout"], p["case"]): p["after"] for p in load(ROOT / "comparison.json")["pairs"]}
    for layout in layouts:
        group = []
        for case in range(6):
            name = f"{layout}-{case}.json"
            before, after = [load(d / name) for d in (args.before, args.after)]
            assert before["layout"] == layout and (before["policy"], after["policy"]) == (
                "current",
                "peripheral",
            )
            for r in (before, after):
                validate_run(r, case, held["stepLimit"])
                scene = {**prior["layouts"], **development["layouts"], **held["layouts"]}.get(layout)
                if scene:
                    assert r["start"] == scene["start"] and r["anchors"] == scene["anchors"]
            for key in (
                "layout",
                "start",
                "anchors",
                "removed",
                "prompt",
                "scoreKey",
                "firstFrameSHA256",
            ):
                assert before[key] == after[key], (name, key)
            if (layout, case) in archived:
                ref = archived[(layout, case)]
                assert before["trace"] == ref["trace"] and before["photo"] == ref["photo"], name
            group.append(dict(layout=layout, case=case, before=before, after=after))
        assert len({p["before"]["firstFrameSHA256"] for p in group[:4]}) == 1
        traces[layout] = "peripheral-" + layout + ".json"
        save(args.out / traces[layout], group)
        if layout in held["layouts"]:
            blind.extend(group)
    metrics = dict(
        holdoutPositive=measure([p for p in blind if p["case"] < 3], "success"),
        holdoutAbsent=measure([p for p in blind if p["case"] >= 3], "firstStop"),
        byCase=[
            measure([p for p in blind if p["case"] == i], "success" if i < 3 else "firstStop")
            for i in range(6)
        ],
    )
    d = load(ROOT / "peripheral-diagnosis.json")
    frame = d["frames"][105]
    assert frame["step"] == 106 and frame["truth"]["box"] == [139, 31, 151, 54]
    old_trial = load(args.before / "unseen2-2.json")
    executed = [f for f in d["frames"] if f["wasAction"]]
    assert len(executed) == old_trial["steps"] == 120
    for f, t in zip(executed, old_trial["trace"]):
        assert f["action"] == t["a"] and not any(f["proposal"])
        for a, b, c in zip(t["logits"], f["base"], f["residual"]):
            assert abs(a - b - c) < 0.00011
    assert (
        d["newVisualHeadOnSameFrame"]["visual_logits"].index(
            max(d["newVisualHeadOnSameFrame"]["visual_logits"])
        )
        == 3
    )
    report = dict(
        study="peripheral",
        scene="Skokloster Castle",
        holdoutCount=len(held["layouts"]),
        holdoutSHA256=digest(ROOT / "confirmation.json"),
        oldModelSHA256=old_hash,
        newModelSHA256=new_hash,
        layouts=layouts,
        traces=traces,
        metrics=metrics,
        diagnosis=dict(
            caption="106번째 입력에서 소화기가 오른쪽 139–151열에 172픽셀 보였습니다. 기존 H4의 기본층은 우회전을 골랐지만, 직전 전진이 막힌 뒤 회복층이 좌회전에 47.39점을 더해 좌회전이 실행됐습니다. YOLOE는 120스텝 동안 목표 후보를 반환하지 않았습니다. 같은 사진에서 새 시각 헤드는 우회전에 가장 높은 점수를 줬습니다.",
            photo=d["photo"],
        ),
        description="Castle의 동일한 3D 물체를 새 위치에 배치하고 출발 자세를 바꿨습니다. 개선 H4는 소화기 목표일 때 원해상도 전방 RGB에서 작은 물체의 방향과 접근 행동을 학습하고, 네 프레임에 같은 두 시점이 번갈아 나타나는지 추정합니다. 1차 검증 여섯 배치에서 발견한 좌우 회전을 보완한 뒤 모델을 고정했습니다. 요약 수치는 별도로 고정한 최종 여덟 배치에서 계산했습니다. 정책 입력은 목표 이름과 전방 RGB이며 직전 행동을 내부에 기억합니다. 거리·마스크·NavMesh는 환경과 채점에만 사용합니다.",
    )
    save(args.out / "peripheral-report.json", report)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

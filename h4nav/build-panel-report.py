"""Check matched starts, endpoints, action traces and reference outcomes for the panel study."""

import argparse
import base64
import json
import hashlib
import math
import runpy
from pathlib import Path

ROOT = Path(__file__).parent
validate = runpy.run_path(str(ROOT / "compare-runs.py"))["validate_run"]


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(pairs, field):
    return dict(
        total=len(pairs),
        **{s: sum(p[s][field] for p in pairs) for s in ("before", "after")},
    )


def summarize(pairs):
    return {
        name: measure([p for p in pairs if p["case"] == k], field)
        for k, name, field in [
            (0, "chair", "success"),
            (1, "present", "success"),
            (2, "extinguisher", "success"),
            (4, "removed", "firstStop"),
        ]
    }


def outside_panel(p):
    return not (5.15 <= p["x"] <= 6.53 and 7.5 <= p["z"] <= 10.85)


def main():
    p = argparse.ArgumentParser()
    for n in ("before", "after", "out"):
        p.add_argument(n, type=Path)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    suite = load(ROOT / "panel-holdout.json")
    fit = load(ROOT / "panel-fit.json")
    assert sha(ROOT / "panel-holdout.json") == fit["holdout_sha256"]
    assert (
        sha(ROOT / "panel-h4.onnx") == fit["model_sha256"]
        and sha(ROOT / "bin-h4.onnx") == fit["parent_sha256"]
    )
    old = {
        k: v
        for data in [
            "bin-holdout.json",
            "confirmation.json",
            "edge-holdout.json",
            "holdout.json",
        ]
        for k, v in load(ROOT / data)["layouts"].items()
    }
    new = suite["layouts"]
    dev = ["bin17", "bin19", "bin21", "bin23", "bin24"]
    labels = {
        "gallery": "실내 전역",
        "perimeter": "주행 경계 근처",
        "panel": "벽면 패널 구역",
    }
    layouts = {k: "이전 배치 " + k[3:] + " · 원인 재현" for k in dev}
    layouts.update(
        {k: "새 배치 " + k[5:] + " · " + labels[v["group"]] for k, v in new.items()}
    )
    traces = {}
    independent = []
    diagnoses = []
    cases = [0, 1, 2, 4]
    for k in layouts:
        scene = (new if k in new else old)[k]
        if k in new:
            assert all(
                scene["start"] != v["start"] and scene["anchors"] != v["anchors"]
                for v in old.values()
            )
        rows = []
        for c in cases:
            name = f"{k}-{c}.json"
            before = load(a.before / name)
            after = load(a.after / name)
            for r, id in [(before, "bin"), (after, "panel")]:
                assert (
                    r["policy"] == id
                    and r["layout"] == k
                    and r["start"] == scene["start"]
                    and r["anchors"] == scene["anchors"]
                )
                validate(r, c, 120)
            for f in (
                "firstFrameSHA256",
                "removed",
                "prompt",
                "scoreKey",
                "start",
                "anchors",
            ):
                assert before[f] == after[f], (name, f)
            if k in dev:
                archived = next(
                    t["after"]
                    for t in load(ROOT / f"bin-trial-{k}.json")
                    if t["case"] == c
                )
                assert (
                    before["trace"] == archived["trace"]
                    and before["photo"] == archived["photo"]
                )
            rows.append(dict(layout=k, case=c, before=before, after=after))
        for side in ("before", "after"):
            assert len({r[side]["firstFrameSHA256"] for r in rows[:3]}) == 1
            assert (
                rows[1][side]["prompt"] == rows[3][side]["prompt"]
                and rows[3][side]["removed"] == 1
            )
        (independent if k in new else diagnoses).extend(rows)
        traces[k] = f"panel-trial-{k}.json"
        save(a.out / traces[k], rows)
    stats = summarize(independent)
    panels = [
        p
        for p in independent
        if new[p["layout"]]["group"] == "panel" and p["case"] == 1
    ]
    escape = {
        side: sum(
            any(outside_panel(v) for v in [*p[side]["trace"], p[side]["endpoint"]])
            for p in panels
        )
        for side in ("before", "after")
    }
    metrics = dict(
        holdoutPositive=measure([p for p in independent if p["case"] < 3], "success"),
        holdoutAbsent=stats["removed"],
        byCase=[stats[k] for k in ["chair", "present", "extinguisher", "removed"]],
        strata={
            z: summarize([p for p in independent if new[p["layout"]]["group"] == z])
            for z in labels
        },
        panelExit=dict(total=len(panels), **escape),
        diagnostic=summarize(diagnoses),
    )
    diagnosis = load(ROOT / "panel-diagnosis.json")
    report = dict(
        study="panel",
        scene="Skokloster Castle",
        holdoutCount=len(new),
        holdoutSHA256=fit["holdout_sha256"],
        oldModelSHA256=fit["parent_sha256"],
        newModelSHA256=fit["model_sha256"],
        layouts=layouts,
        cases=cases,
        traces=traces,
        metrics=metrics,
        description="같은 Castle에서 벽면 패널 구역 16곳, 실내 전역과 주행 경계 각 4곳을 모델 선택 전에 고정했습니다. 각 출발 자세에서 쓰레기통만 제거한 조건까지 두 정책을 각각 120스텝 한도로 실행했습니다. 기존 다섯 배치는 별도의 원인 재현용입니다.",
        diagnosis=dict(
            caption=diagnosis["caption"],
            photo="data:image/png;base64,"
            + base64.b64encode((ROOT / "panel-diagnosis.png").read_bytes()).decode(),
        ),
    )
    save(a.out / "panel-report.json", report)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

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


def summarize(pairs, absence=4):
    return {
        name: measure([p for p in pairs if p["case"] == k], field)
        for k, name, field in [
            (0, "chair", "success"),
            (1, "bin" if absence == 6 else "present", "success"),
            (2, "extinguisher", "success"),
            (absence, "removed", "firstStop"),
        ]
    }


def outside_panel(p):
    return not (5.15 <= p["x"] <= 6.53 and 7.5 <= p["z"] <= 10.85)


def main():
    p = argparse.ArgumentParser()
    for n in ("before", "after", "out"):
        p.add_argument(n, type=Path)
    p.add_argument("--study", choices=["panel", "chair", "escape"], default="panel")
    a = p.parse_args()
    escape = a.study == "escape"
    chair = a.study in ("chair", "escape")
    prefix = a.study
    prev = "chair" if escape else ("panel" if chair else "bin")
    absence = 6 if chair else 4
    sought = 0 if chair else 1
    a.out.mkdir(parents=True, exist_ok=True)
    suite = load(ROOT / f"{prefix}-holdout.json")
    fit = load(ROOT / f"{prefix}-fit.json")
    assert sha(ROOT / f"{prefix}-holdout.json") == fit["holdout_sha256"]
    assert (
        sha(ROOT / f"{prefix}-h4.onnx") == fit["model_sha256"]
        and sha(ROOT / f"{prev}-h4.onnx") == fit["parent_sha256"]
    )
    old = {
        k: v
        for data in (["chair-holdout.json"] if escape else [])
        + (["panel-holdout.json"] if chair else [])
        + [
            "bin-holdout.json",
            "confirmation.json",
            "edge-holdout.json",
            "holdout.json",
        ]
        for k, v in load(ROOT / data)["layouts"].items()
    }
    new = suite["layouts"]
    dev = (
        ["chair2"]
        if escape
        else (
            ["panel7", "panel22"]
            if chair
            else ["bin17", "bin19", "bin21", "bin23", "bin24"]
        )
    )
    labels = {
        "gallery": "실내 전역",
        "perimeter": "주행 경계 근처",
        "panel": "벽면 패널 구역",
    }
    layouts = {k: "이전 배치 " + k.removeprefix(prev) + " · 원인 재현" for k in dev}
    layouts.update(
        {
            k: "새 배치 " + k.removeprefix(prefix) + " · " + labels[v["group"]]
            for k, v in new.items()
        }
    )
    traces = {}
    independent = []
    diagnoses = []
    cases = [0, 1, 2, absence]
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
            for r, id in [(before, prev), (after, prefix)]:
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
            if k in dev and (escape or not chair or c < 3):
                archived = next(
                    t["after"]
                    for t in load(ROOT / f"{prev}-trial-{k}.json")
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
                rows[sought][side]["prompt"] == rows[3][side]["prompt"]
                and rows[3][side]["removed"] == sought
            )
        (independent if k in new else diagnoses).extend(rows)
        traces[k] = f"{prefix}-trial-{k}.json"
        save(a.out / traces[k], rows)
    stats = summarize(independent, absence)
    panels = [
        p
        for p in independent
        if new[p["layout"]]["group"] == "panel" and p["case"] == sought
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
        byCase=[
            stats[k]
            for k in ["chair", "bin" if chair else "present", "extinguisher", "removed"]
        ],
        strata={
            z: summarize(
                [p for p in independent if new[p["layout"]]["group"] == z], absence
            )
            for z in labels
        },
        panelExit=dict(total=len(panels), **escape),
        diagnostic=summarize(diagnoses, absence),
    )
    if escape:
        metrics["blockedForward"] = {
            str(case): measure([p for p in independent if p["case"] == case], "bumped")
            for case in cases
        }
    diagnosis = load(ROOT / f"{prefix}-diagnosis.json")
    report = dict(
        study=prefix,
        scene="Skokloster Castle",
        holdoutCount=len(new),
        holdoutSHA256=fit["holdout_sha256"],
        oldModelSHA256=fit["parent_sha256"],
        newModelSHA256=fit["model_sha256"],
        layouts=layouts,
        cases=cases,
        traces=traces,
        metrics=metrics,
        description=(
            "같은 Castle의 새 출발점·배치 24곳에서 두 정책에 같은 첫 화면과 목표 이름을 주었습니다. 실내 전역·경계·벽면 구역은 각각 8곳입니다. 기존 2번은 별도 원인 재현용입니다. 의자 제거 조건은 같은 배치에서 등록 의자만 뺐습니다."
            if escape
            else (
                "같은 Castle의 실내 전역·주행 경계·벽면 구역에서 새 배치를 8개씩 고정했습니다. 같은 카메라와 가구 배치에서 등록 의자만 제거해 두 정책을 120스텝씩 비교했습니다. 기존 7·22번은 개발 사례로 별도 표시합니다."
                if chair
                else "같은 Castle에서 벽면 패널 구역 16곳, 실내 전역과 주행 경계 각 4곳을 모델 선택 전에 고정했습니다. 각 출발 자세에서 쓰레기통만 제거한 조건까지 두 정책을 각각 120스텝 한도로 실행했습니다. 기존 다섯 배치는 별도의 원인 재현용입니다."
            )
        ),
        diagnosis=dict(
            caption=diagnosis["caption"],
            photo="data:image/png;base64,"
            + base64.b64encode(
                (ROOT / f"{prefix}-diagnosis.png").read_bytes()
            ).decode(),
        ),
    )
    save(a.out / f"{prefix}-report.json", report)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

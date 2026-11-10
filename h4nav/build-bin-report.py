"""Verify paired positive/removal episodes against the pre-registered bin study."""

import argparse, base64, hashlib, json, runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
v = runpy.run_path(str(ROOT / "compare-runs.py"))


def load(p):
    return json.loads(p.read_text())


def save(p, item):
    p.write_text(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def measure(rows, field):
    return {
        "total": len(rows),
        **{side: sum(x[side][field] for x in rows) for side in ("before", "after")},
    }


def main():
    p = argparse.ArgumentParser()
    for k in ["before", "after", "out"]:
        p.add_argument(k, type=Path)
    a = p.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    suite = load(ROOT / "bin-holdout.json")
    fit = load(ROOT / "bin-fit.json")
    assert (
        digest(ROOT / "bin-holdout.json")
        == "98fc56a34eccb743c22ebd8c12e605be6451c38da198bb7a927d3608266e99c5"
    )
    assert (
        digest(ROOT / "peripheral.onnx") == fit["parent_sha256"]
        and digest(ROOT / "bin-h4.onnx") == fit["model_sha256"]
    )
    groups = {"gallery": "실내 전역", "perimeter": "주행 경계 근처", "panel": "벽면 패널 구역"}
    layouts = {"blind7": "기존 배치 7 · 벽면 오정지"}
    layouts.update(
        {k: "새 배치 " + k[3:] + " · " + groups[s["group"]] for k, s in suite["layouts"].items()}
    )
    layouts["unseen2"] = "이전 소화기 회귀 검증"
    independent = []
    traces = {}
    cases = [0, 1, 2, 4]
    for layout in layouts:
        rows = []
        for case in cases:
            file = f"{layout}-{case}.json"
            before, after = [load(folder / file) for folder in (a.before, a.after)]
            assert before["policy"] == "peripheral" and after["policy"] == "bin"
            for key in (
                "layout",
                "anchors",
                "start",
                "prompt",
                "removed",
                "scoreKey",
                "firstFrameSHA256",
            ):
                assert before[key] == after[key], (file, key)
            assert before["layout"] == layout
            for run in (before, after):
                v["validate_run"](run, case, suite["stepLimit"])
            scene = suite["layouts"].get(layout)
            if scene:
                assert scene["anchors"] == before["anchors"] and scene["start"] == before["start"]
            else:
                archived = next(
                    x["after"] for x in load(ROOT / f"peripheral-{layout}.json") if x["case"] == case
                )
                assert archived["trace"] == before["trace"] and archived["photo"] == before["photo"]
            rows.append(dict(layout=layout, case=case, before=before, after=after))
        for side in ("before", "after"):
            assert len({r[side]["firstFrameSHA256"] for r in rows[:3]}) == 1
            binpos, binneg = rows[1][side], rows[3][side]
            assert (
                binpos["prompt"] == binneg["prompt"]
                and binpos["start"] == binneg["start"]
                and binpos["anchors"] == binneg["anchors"]
            )
            assert binpos["removed"] == -1 and binneg["removed"] == 1
        if layout in suite["layouts"]:
            independent += rows
        traces[layout] = f"bin-trial-{layout}.json"
        save(a.out / traces[layout], rows)
    metrics = {
        "holdoutPositive": measure([p for p in independent if p["case"] < 3], "success"),
        "holdoutAbsent": measure([p for p in independent if p["case"] == 4], "firstStop"),
    }
    metrics["byCase"] = [
        measure([p for p in independent if p["case"] == i], "success" if i < 3 else "firstStop")
        for i in cases
    ]
    metrics["strata"] = {}
    for id, label in groups.items():
        part = [p for p in independent if suite["layouts"][p["layout"]]["group"] == id]
        metrics["strata"][label] = {
            "present": measure([p for p in part if p["case"] == 1], "success"),
            "removed": measure([p for p in part if p["case"] == 4], "firstStop"),
        }
    d = load(ROOT / "bin-diagnosis.json")
    r = load(a.before / "blind7-4.json")
    assert d["photo"] == r["photo"] and all(f["yolo"] == 0 for f in d["frames"])
    for frame, step in zip(d["frames"], r["trace"]):
        assert max(abs(v - w) for v, w in zip(frame["combined"], step["logits"])) < 0.00014
    report = dict(
        study="bin",
        scene="Skokloster Castle",
        holdoutCount=len(suite["layouts"]),
        holdoutSHA256=digest(ROOT / "bin-holdout.json"),
        oldModelSHA256=fit["parent_sha256"],
        newModelSHA256=fit["model_sha256"],
        layouts=layouts,
        cases=cases,
        traces=traces,
        metrics=metrics,
        description="Castle의 새 배치 24곳에서 목표 이름과 전방 RGB만 정책에 전달했습니다. 실내 전역, 주행 경계, 기존 오정지가 나타난 벽면 패널 구역에서 8곳씩 표집했습니다. 각 배치에서 카메라 출발 자세와 다른 물체는 고정하고 쓰레기통만 넣고 뺐습니다. 기존 배치 7과 이전 소화기 사례는 최종 집계에서 제외했습니다.",
        diagnosis={
            "caption": "12번째 화면에서 YOLOE 검출은 0건이었지만, 기존 H4의 자체 시각 특징은 쓰레기통 근거 점수 0.69를 냈습니다. 최종 STOP 점수는 1.127, 좌회전은 1.034였습니다. 같은 네 프레임에서 내부 공간 특징만 제거한 진단 실행에서는 좌회전이 선택됐습니다.",
            "photo": "data:image/png;base64,"
            + base64.b64encode((ROOT / "bin-attention.png").read_bytes()).decode(),
        },
    )
    save(a.out / "bin-report.json", report)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

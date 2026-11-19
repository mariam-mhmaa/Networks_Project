"""Export recorded application timings; this is not a protocol benchmark.

Usage: python tools/export_batch_measurements.py batch-8.json --output DIR
Requires matplotlib for the PNG. Input reports are read-only.
"""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean


def export(reports, output):
    rows, seen = [], set()
    for path in reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        batch = report["batch"]
        if batch["id"] in seen:
            raise ValueError("Duplicate input batch: " + batch["display_id"])
        seen.add(batch["id"])
        for op in report["operations"]:
            request = op["request"]
            if request["type"] not in {"PRODUCE", "INSPECT"}:
                continue
            result, evidence = op.get("result") or {}, op["evidence"]
            frozen = result.get("settings", {})
            rows.append({
                "source_report": path.name, "batch": batch["display_id"], "batch_id": batch["id"],
                "part_id": request["part_id"], "station": op["station"], "action": request["type"],
                "operation_id": op["id"], "outcome": op["phase"], "verdict": result.get("verdict", ""),
                "production_setting_ms": frozen.get("production_time_ms", ""),
                "inspection_setting_ms": frozen.get("inspection_time_ms", ""),
                "N": frozen.get("N", ""), "K": frozen.get("K", ""),
                "device_elapsed_ms": result.get("elapsed_ms", ""),
                **{stage + "_observed_gateway_monotonic_s": evidence.get(stage + "_observed_at")
                   for stage in ("received", "accepted", "completed")},
                "request_attempts": evidence["request_attempts"], "query_attempts": evidence["query_attempts"],
            })
    if not rows:
        raise ValueError("No production/inspection measurements in input")
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "measurements.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    batches = list(dict.fromkeys(row["batch_id"] for row in rows))
    labels = [next(row["batch"] for row in rows if row["batch_id"] == batch) for batch in batches]
    fig, ax = plt.subplots(figsize=(8, 4.8), layout="constrained")
    for station, offset, color, caption in (("A", -.19, "#e4ae38", "A: production"),
                                            ("B", .19, "#69a6c0", "B: inspection")):
        xs, ys, ns = [], [], []
        for i, batch in enumerate(batches):
            samples = [row["device_elapsed_ms"] for row in rows
                       if row["batch_id"] == batch and row["station"] == station
                       and row["outcome"] == "COMPLETED" and type(row["device_elapsed_ms"]) is int]
            if samples:
                xs.append(i + offset); ys.append(mean(samples)); ns.append(len(samples))
        bars = ax.bar(xs, ys, width=.36, color=color, label=caption)
        ax.bar_label(bars, labels=[f"{y:g} ms\n(n={n})" for y, n in zip(ys, ns)], padding=4)
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylabel("Mean device-reported execution time (ms)")
    ax.set_title("Recorded production and inspection execution times")
    ax.set_ylim(0, max(row["device_elapsed_ms"] for row in rows
                       if type(row["device_elapsed_ms"]) is int) * 1.35)
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=.25)
    ax.legend(loc="upper right")
    fig.supxlabel("Completed jobs only; excludes queue wait and communication delay.\nApplication timing evidence, not formal protocol benchmarking.", fontsize=9)
    image_path = output / "timing-comparison.png"
    fig.savefig(image_path, dpi=180)
    plt.close(fig)
    return csv_path, image_path, len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for artifact in export(args.reports, args.output)[:2]:
        print(artifact)

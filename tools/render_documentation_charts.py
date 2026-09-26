"""Render the public evidence figures from reviewed aggregate data.

From the repository root:
    uv run --no-project --with matplotlib==3.10.8 python tools/render_documentation_charts.py

Optional --preview-dir writes PNGs outside the tracked documentation for visual QA.
This script reads only docs/data/step-evidence.json; no keys or raw runs are needed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
BLUE = "#245EAD"
NEUTRAL = "#ABB7C8"
INK = "#17253B"
MUTED = "#536176"


def style_axis(axis: plt.Axes) -> None:
    axis.set_axisbelow(True)
    axis.grid(axis="x", color="#E5EAF0", linewidth=0.8)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.spines["bottom"].set_color("#A9B4C2")
    axis.tick_params(axis="y", length=0, pad=12)
    axis.tick_params(axis="x", colors=MUTED)


def save(figure: plt.Figure, name: str, preview_dir: Path | None) -> None:
    output = ROOT / "docs" / "assets"
    output.mkdir(parents=True, exist_ok=True)
    svg_path = output / f"{name}.svg"
    figure.savefig(svg_path, metadata={"Date": None}, facecolor="white")
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text().splitlines()) + "\n")
    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
        figure.savefig(preview_dir / f"{name}.png", dpi=150, facecolor="white")
    plt.close(figure)


def render_kernel(data: dict, preview_dir: Path | None) -> None:
    rows = data["official_kernel"]["rows"]
    figure, axis = plt.subplots(figsize=(10.8, 6.3))
    figure.subplots_adjust(left=0.25, right=0.94, top=0.70, bottom=0.28)
    figure.text(0.045, 0.94, "StepFun's reported GPU kernel results", fontsize=21, weight="bold")
    figure.text(0.045, 0.875, "Best of 4 runs per model | 24-hour budget per run", fontsize=13)
    figure.text(0.045, 0.827, "Fixed MLA workload on one NVIDIA H100", fontsize=12, color=MUTED)
    labels = [f"{row['model']}\n{row['effort']} effort" for row in rows]
    scores = [row["tflops"] for row in rows]
    axis.barh(labels, scores, height=0.58, color=[BLUE, NEUTRAL, NEUTRAL, NEUTRAL])
    axis.invert_yaxis()
    axis.set_xlim(0, 580)
    axis.set_xticks([0, 100, 200, 300, 400, 500])
    axis.set_xlabel("Forward + backward achieved TFLOPS (higher is better)", labelpad=12)
    for index, score in enumerate(scores):
        axis.text(score + 9, index, str(score), va="center", weight="bold", fontsize=13)
    style_axis(axis)
    figure.text(0.045, 0.15, "Vendor-reported best runs; not average performance or an equal-cost comparison.",
                fontsize=11, color=MUTED)
    figure.text(0.045, 0.11, "Shape: head dimension 512 | batch 1 | 64 heads | 8,192 tokens.",
                fontsize=11, color=MUTED)
    figure.text(0.045, 0.055, "Source: stepfun.com/step-5-preview | Checked 2026-09-26",
                fontsize=10, color=MUTED)
    save(figure, "step-kernel-results", preview_dir)


def render_local(data: dict, preview_dir: Path | None) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(10.8, 8.6))
    figure.subplots_adjust(left=0.16, right=0.80, top=0.74, bottom=0.23, hspace=1.15)
    figure.text(0.045, 0.95, "Our local sprite-composition case", fontsize=21, weight="bold")
    figure.text(0.045, 0.898, "Same RGBA output | Lower elapsed time is better", fontsize=13)
    figure.text(0.045, 0.852, "One workload; 3 live attempts, including 2 that produced no patch",
                fontsize=12, color=MUTED)
    for axis, row in zip(axes, data["local_case"]["rows"], strict=True):
        values = [row["baseline"], row["accepted"]]
        reduction = 100 * (1 - values[1] / values[0])
        axis.barh(["Baseline", "Accepted"], values, height=0.52, color=[NEUTRAL, BLUE])
        axis.invert_yaxis()
        axis.set_xlim(0, values[0] * 1.08)
        axis.set_xlabel(f"Elapsed time ({row['unit']})", labelpad=6)
        axis.set_title(row["name"], loc="left", pad=14, fontsize=13, weight="bold")
        for index, value in enumerate(values):
            axis.text(value + values[0] * 0.02, index, f"{value:.6f} {row['unit']}",
                      va="center", fontsize=11)
        axis.text(1.02, 0.96, f"{reduction:.2f}% less time", transform=axis.transAxes,
                  ha="left", va="bottom", color=BLUE, fontsize=12, weight="bold")
        style_axis(axis)
    figure.text(0.045, 0.13, "Separate units and timing scopes; do not combine the reductions. Not animation FPS.",
                fontsize=11, color=MUTED)
    figure.text(0.045, 0.095, "Private fixtures omitted; no confidence intervals or other-model comparison.",
                fontsize=11, color=MUTED)
    figure.text(0.045, 0.045, "Source: docs/case-study.md | Measured 2026-09-26", fontsize=10, color=MUTED)
    save(figure, "local-case-results", preview_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path)
    args = parser.parse_args()
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica", "sans-serif"],
        "font.size": 12,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.labelsize": 10,
        "ytick.labelsize": 12,
        "svg.fonttype": "none",
        "svg.hashsalt": "step-engineer-evidence-v1",
    })
    data = json.loads((ROOT / "docs/data/step-evidence.json").read_text())
    render_kernel(data, args.preview_dir)
    render_local(data, args.preview_dir)
    print("Rendered two evidence figures from docs/data/step-evidence.json")


if __name__ == "__main__":
    main()

"""Acceptance boundaries, independent of provider calls or benchmark timing noise."""

from __future__ import annotations

import math
from decimal import Decimal, localcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from step_engineer.harness import Harness
from step_engineer.models import JobSpec, MetricConstraint


def threshold_harness(tmp_path: Path, baseline: float, direction: str, threshold: float):
    spec = JobSpec(
        source_dir=str(tmp_path),
        files=["implementation.py"],
        editable_files=["implementation.py"],
        objective="Improve the measured score without changing the behavior contract.",
        checks=[{"name": "correctness", "argv": ["{python}", "check.py"]}],
        benchmark={"name": "benchmark", "argv": ["{python}", "benchmark.py"]},
        direction=direction,
        minimum_relative_improvement=threshold,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    harness = Harness(spec, run_dir, client=None)
    harness.baseline = {"score": baseline}
    harness.workspace = SimpleNamespace(
        best=tmp_path, validation_workspace=lambda _: tmp_path,
    )
    return harness


async def verify_scores(harness: Harness, development_score: float, final_score: float):
    harness.best = {"score": development_score}

    async def measure(_root):
        return {"feasible": True, "score": final_score}

    harness.measure = measure
    return await harness.verify_final()


@pytest.mark.parametrize("direction", ["minimize", "maximize"])
def test_baseline_contract_normalization_and_exact_constraints(tmp_path, direction):
    """Pre-existing invariants must pass before and after the threshold fix."""
    harness = threshold_harness(tmp_path, 1e-14, direction, 0.1)
    sign = -1 if direction == "minimize" else 1
    candidate = 1e-14 + sign * 1e-13
    assert harness.improvement(candidate) == pytest.approx(0.1)
    assert harness.better(candidate, 1e-14)
    assert not harness.better(1e-14, 1e-14)
    harness.spec.constraints = [MetricConstraint(metric="recall", op=">=", value=0.95)]
    assert harness.constraints_hold({"recall": 0.95})
    assert not harness.constraints_hold({"recall": math.nextafter(0.95, -math.inf)})


@pytest.mark.parametrize(
    ("baseline", "boundary", "direction"),
    [
        (0.3, 0.27, "minimize"),
        (0.3, 0.33, "maximize"),
        (-0.3, -0.33, "minimize"),
        (-0.3, -0.27, "maximize"),
        (0.0, -1e-13, "minimize"),
        (0.0, 1e-13, "maximize"),
        (1e-14, -9e-14, "minimize"),
        (1e-14, 1.1e-13, "maximize"),
        (-1e-14, -1.1e-13, "minimize"),
        (-1e-14, 9e-14, "maximize"),
    ],
)
@pytest.mark.parametrize("position", ["equal", "below", "above"])
async def test_threshold_boundary_accepts_equal_and_rejects_real_shortfall(
    tmp_path, baseline, boundary, direction, position
):
    harness = threshold_harness(tmp_path, baseline, direction, 0.1)
    # Sixteen input-scale ULPs are materially beyond arithmetic roundoff here;
    # fixed epsilons such as 1e-12 must not admit this genuinely smaller gain.
    offset = 16 * math.ulp(max(abs(baseline), 1e-12))
    improvement_sign = -1 if direction == "minimize" else 1
    candidate = boundary
    if position == "below":
        candidate -= improvement_sign * offset
    elif position == "above":
        candidate += improvement_sign * offset
    assert await verify_scores(harness, candidate, candidate) is (position != "below")


@pytest.mark.parametrize("direction", ["minimize", "maximize"])
@pytest.mark.parametrize("baseline", [-0.3, 0.0, 0.3])
@pytest.mark.parametrize("position", ["equal", "worse", "better"])
async def test_zero_threshold_still_requires_strict_improvement(
    tmp_path, baseline, direction, position
):
    harness = threshold_harness(tmp_path, baseline, direction, 0)
    better_toward = -math.inf if direction == "minimize" else math.inf
    candidate = baseline
    if position != "equal":
        candidate = math.nextafter(
            baseline, better_toward if position == "better" else -better_toward
        )
    assert await verify_scores(harness, candidate, candidate) is (position == "better")


@pytest.mark.parametrize("stage", ["development", "final"])
@pytest.mark.parametrize("position", ["equal", "below"])
async def test_each_acceptance_stage_uses_the_same_boundary(tmp_path, stage, position):
    harness = threshold_harness(tmp_path, 0.3, "minimize", 0.1)
    boundary = 0.27 if position == "equal" else 0.27 + 16 * math.ulp(0.3)
    scores = (boundary, 0.25) if stage == "development" else (0.25, boundary)
    assert await verify_scores(harness, *scores) is (position == "equal")


@pytest.mark.parametrize("baseline", [1e-300, 1e-12, -3.7, 1e12, 1e300])
@pytest.mark.parametrize("threshold", [1e-8, 0.25, 0.99])
@pytest.mark.parametrize("direction", ["minimize", "maximize"])
@pytest.mark.parametrize("position", ["equal", "below"])
async def test_precision_reference_across_thresholds_and_score_scales(
    tmp_path, baseline, threshold, direction, position
):
    harness = threshold_harness(tmp_path, baseline, direction, threshold)
    sign = -1 if direction == "minimize" else 1
    scale = max(abs(baseline), 1e-12)
    # Compute the real-valued boundary of the supplied binary floats at high
    # precision, then round once to the representable candidate score. This
    # reference does not reuse the implementation's subtraction or tolerance.
    with localcontext() as context:
        context.prec = 400
        required = Decimal.from_float(threshold) * Decimal.from_float(scale)
        boundary = Decimal.from_float(baseline) + sign * required
        candidate = float(boundary)
    if position == "below":
        candidate -= sign * 16 * math.ulp(scale)
    assert await verify_scores(harness, candidate, candidate) is (position == "equal")

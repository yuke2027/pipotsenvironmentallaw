"""Property 8: a failed pipeline step stops the pass and the next pass starts over."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.scheduler.jobs import STEP_NAMES, failure, success
from app.scheduler.pipeline import Pipeline

_OUTCOME = st.sampled_from(("success", "noop", "fail"))


@given(first=st.tuples(_OUTCOME, _OUTCOME, _OUTCOME, _OUTCOME, _OUTCOME, _OUTCOME))
@pytest.mark.property
def test_property_08_pipeline_stops_at_the_first_failure(
    first: tuple[str, str, str, str, str, str],
) -> None:
    """Executed steps are the prefix through the first failure, and the next run starts at collect.

    **Feature: environmental-supervision-platform, Property 8: 流水线故障隔离**
    **Property 8：流水线故障隔离**
    **Validates: Requirements 2.11, 2.12**
    """

    def build(outcomes: tuple[str, ...]) -> Pipeline:
        steps = {}
        for name, outcome in zip(STEP_NAMES, outcomes):
            def step(outcome: str = outcome, name: str = name) -> object:
                del name
                if outcome == "fail":
                    return failure("step failed")
                return success(no_op=outcome == "noop")

            steps[name] = step
        return Pipeline(steps)  # type: ignore[arg-type]

    initial = build(first).run_once()
    expected: list[str] = []
    for name, outcome in zip(STEP_NAMES, first):
        expected.append(name)
        if outcome == "fail":
            break
    assert list(initial.executed) == expected
    assert (initial.failed_step is None) is ("fail" not in first)
    again = build(first).run_once()
    assert again.run_id != initial.run_id
    assert again.executed[0] == "collect"
    assert list(again.executed) == expected

# Copyright (C) 2024, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory
# of this source tree.

from collections import OrderedDict

import numpy as np
import pytest

from infinigen.core.constraints.example_solver import propose_discrete


class DummyFactory:
    pass


class DummyState:
    def __init__(self, names):
        self.objs = OrderedDict((name, object()) for name in names)


def test_sample_unique_name_retries_until_unused(monkeypatch):
    state = DummyState(["1234_DummyFactory"])
    samples = iter([1234, 5678])

    monkeypatch.setattr(np.random, "randint", lambda _: next(samples))

    assert (
        propose_discrete.sample_unique_name(state, DummyFactory, max_attempts=2)
        == "5678_DummyFactory"
    )


def test_sample_unique_name_raises_after_exhausting_attempts(monkeypatch):
    state = DummyState(["1234_DummyFactory"])
    monkeypatch.setattr(np.random, "randint", lambda _: 1234)

    with pytest.raises(RuntimeError, match="Failed to sample a unique name"):
        propose_discrete.sample_unique_name(state, DummyFactory, max_attempts=2)

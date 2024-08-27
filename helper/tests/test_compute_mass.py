import json
from pathlib import Path

import pytest

from ..mass_calculation_compute import compute_mass


@pytest.fixture()
def test_txs():
    with open(Path(__file__).parent.joinpath(r"test_txs.json"), "r") as f:
        return json.load(f)


def test_compute_mass(test_txs):
    for tx in test_txs:
        print(int(tx["verboseData"]["mass"]))
        assert compute_mass(tx) == int(tx["verboseData"]["mass"])

import json
from pathlib import Path

import pytest

from ..mass_calculation_compute import calc_compute_mass


@pytest.fixture()
def txs():
    with open(Path(__file__).parent.joinpath(r"test_txs.json"), "r") as f:
        return json.load(f)


def test_compute_mass(txs):
    for tx in txs:
        print(int(tx["verboseData"]["mass"]))
        assert calc_compute_mass(tx) == int(tx["verboseData"]["mass"])

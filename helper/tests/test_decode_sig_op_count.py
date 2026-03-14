import pytest

from ..mass_calculation_compute import decode_sig_op_count


@pytest.mark.parametrize(
    "tx_version,encoded,expected",
    [
        # version 0: always passthrough regardless of encoded value
        (0, 0, 0),
        (0, 50, 50),
        (0, 100, 100),
        (0, 101, 101),
        (0, 200, 200),
        (0, 255, 255),
        # version > 0, encoded 0-100: direct mapping
        (1, 0, 0),
        (1, 1, 1),
        (1, 100, 100),
        # version > 0, encoded 101-255: compressed
        (1, 101, 110),
        (1, 104, 140),
        (1, 164, 740),
        (1, 255, 1650),
        # version > 0 (other versions behave the same)
        (2, 104, 140),
        (2, 255, 1650),
    ],
)
def test_decode_sig_op_count(tx_version, encoded, expected):
    assert decode_sig_op_count(tx_version, encoded) == expected

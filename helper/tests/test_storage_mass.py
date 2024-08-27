from ..mass_calculation_storage import calc_storage_mass


def test_storage_mass():
    assert calc_storage_mass([1_0000_0000, 1_0000_0000], [9000_0000]) == 0
    assert calc_storage_mass([1_0000_0000, 1_0000_0000], [9000_0000, 1000]) == 999991111
    assert calc_storage_mass([1_1000_0000], [9000_0000, 1000, 1000, 1000]) == 3000002021
    assert calc_storage_mass([1_0000_0000], [7900_0000, 2000_0000]) == 52658

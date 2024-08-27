# encoding: utf-8

# Storage mass constant
C = 10**12


def _negative_mass(inputs, outputs_num):
    """
    Calculates the negative component of the storage mass formula. Note that there is no dependency on output
    values but only on their count. The code is designed to maximize precision and to avoid intermediate overflows.
    """
    inputs_num = len(inputs)
    if outputs_num == 1 or inputs_num == 1 or (outputs_num == 2 and inputs_num == 2):
        return sum(C // v for v in inputs)
    return inputs_num * (C // (sum(inputs) // inputs_num))


def calc_storage_mass(inputs, outputs):
    """
    Calculates the storage mass for the provided input/output collections
    """
    N = _negative_mass(inputs, outputs_num=len(outputs))
    P = sum(C // o for o in outputs)
    return max(P - N, 0)

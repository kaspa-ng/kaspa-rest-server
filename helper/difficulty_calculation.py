def from_compact_target_bits(bits):
    # Translation of https://github.com/kaspanet/rusty-kaspa/blob/master/math/src/lib.rs
    unshifted_expt = bits >> 24
    if unshifted_expt <= 3:
        mant = (bits & 0xFFFFFF) >> (8 * (3 - unshifted_expt))
        expt = 0
    else:
        mant = bits & 0xFFFFFF
        expt = 8 * (unshifted_expt - 3)
    if mant > 0x7FFFFF:
        return 0
    else:
        return mant << expt


def bits_to_difficulty(bits):
    # https://github.com/kaspanet/rusty-kaspa/blob/master/consensus/core/src/config/constants.rs:
    max_target = 2**255 - 1
    # https://github.com/kaspanet/rusty-kaspa/blob/master/rpc/service/src/converter/consensus.rs:
    target = from_compact_target_bits(bits)
    return max_target / target if target != 0 else float("inf")

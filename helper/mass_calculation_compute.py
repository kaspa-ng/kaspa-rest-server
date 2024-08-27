# encoding: utf-8

MASS_PER_TX_BYTE = 1
MASS_PER_SCRIPT_PUB_KEY_BYTE = 10
MASS_PER_SIG_OP = 1000

MAXIMUM_STANDARD_TRANSACTION_MASS = 100_000


def outpoint_size(tx_input_outpoint):
    """
    size for outpoint
    """
    size = 0
    size += 32  # one HASH_SIZE constant
    size += 4  # Index
    return size


def tx_output_serialized(tx_output):
    """
    size for each output
    """
    size = 0
    size += 8  # value
    size += 2  # scriptpubkey version
    size += 8  # length of script pub key
    size += len(tx_output["scriptPublicKey"]["scriptPublicKey"]) / 2
    return size


def tx_input_serialized(tx_input):
    """
    size for each input
    """
    size = 0
    size += outpoint_size(tx_input)  # previous outpoint size
    size += 8  # length of signature script
    size += len(tx_input["signatureScript"]) / 2
    size += 8  # sequence
    return size


def tx_serialized_size(tx):
    size = 0
    size += 2  # 2 bytes for tx version
    size += 8  # count of inputs
    size += sum([tx_input_serialized(x) for x in tx["inputs"]])
    size += 8  # count of outputs
    size += sum([tx_output_serialized(x) for x in tx["outputs"]])
    size += 8  # lock time
    size += 20  # subnetwork id size
    size += 8  # gas
    size += 32  # hash size payload hash
    size += 8  # length of the payload
    size += len(tx.get("payload", "")) / 2  # length of payload

    return size


def calc_compute_mass(tx):
    """
    Calculate mass for a TX-OBJECT
    :param tx:
    :return:
    """
    if tx["subnetworkId"] == "0100000000000000000000000000000000000000":
        return 0

    # get the size of serialized tx
    size = tx_serialized_size(tx)

    # calc mass for serialized tx
    mass = size * MASS_PER_TX_BYTE

    # count ALL outputs (script public key version + script public key)
    total_script_public_key_sum = sum([2 + (len(x["scriptPublicKey"]["scriptPublicKey"]) / 2) for x in tx["outputs"]])

    # calc sum
    total_script_public_key_mass = MASS_PER_SCRIPT_PUB_KEY_BYTE * total_script_public_key_sum

    # calc mass for all inputs with sigOpCount
    total_sigops_mass = MASS_PER_SIG_OP * sum([x["sigOpCount"] for x in tx["inputs"]])
    return int(mass + total_script_public_key_mass + total_sigops_mass)

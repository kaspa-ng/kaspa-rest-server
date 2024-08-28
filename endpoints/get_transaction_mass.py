from fastapi import HTTPException
from pydantic import BaseModel

from endpoints.get_transactions import search_for_transactions, TxSearch
from endpoints.kaspad_requests.submit_transaction_request import SubmitTxModel
from helper.mass_calculation_compute import calc_compute_mass
from helper.mass_calculation_storage import calc_storage_mass
from server import app


class TxMass(BaseModel):
    mass: int
    storage_mass: int
    compute_mass: int


def _get_amount_from_tx_output_index(txs, tx_id, output_index: int):
    for tx in txs:
        if tx["transaction_id"] == tx_id:
            for output in tx["outputs"]:
                if output.index == output_index:
                    return output.amount


@app.post(
    "/transactions/mass",
    response_model=TxMass,
    tags=["Kaspa transactions"],
    response_model_exclude_unset=True,
)
async def calculate_transaction_mass(tx: SubmitTxModel):
    """
    This function calculates and returns the mass of a transaction, which is essential for determining the minimum fee. The mass calculation takes into account the storage mass as defined in KIP-0009.

    Note: Be aware that if the transaction has a very low output amount or a high number of outputs, the mass can become significantly large.
    """
    previous_outpoints = [input.previousOutpoint for input in tx.inputs]

    txs = list(
        await search_for_transactions(
            TxSearch(transactionIds=list([x.transactionId for x in previous_outpoints])), "", False
        )
    )

    if len(txs) != len(previous_outpoints):
        raise HTTPException(status_code=404, detail="Previous outpoint(s) not found in database.")

    tx_input_amounts = [
        _get_amount_from_tx_output_index(
            txs,
            previous_outpoint.transactionId,
            previous_outpoint.index,
        )
        for previous_outpoint in previous_outpoints
    ]

    tx_output_amounts = [output.amount for output in tx.outputs]

    storage_mass = calc_storage_mass(tx_input_amounts, tx_output_amounts)
    compute_mass = calc_compute_mass(tx.dict())

    return TxMass(mass=max(storage_mass, compute_mass), storage_mass=storage_mass, compute_mass=compute_mass)

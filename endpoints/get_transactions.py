# encoding: utf-8

from enum import Enum
from typing import List

from fastapi import Path, HTTPException, Query, Response
from pydantic import BaseModel, parse_obj_as
from sqlalchemy.future import select

from dbsession import async_session
from endpoints import filter_fields, sql_db_only
from models.Block import Block
from models.BlockTransaction import BlockTransaction
from models.Subnetwork import Subnetwork
from models.Transaction import Transaction, TransactionOutput, TransactionInput
from models.TransactionAcceptance import TransactionAcceptance
from server import app

DESC_RESOLVE_PARAM = (
    "Use this parameter to fetch details of the TransactionInput's previous outpoint."
    " 'Light' mode fetches only the address and amount, while 'Full' mode fetches the entire TransactionOutput"
    " and adds it to each TxInput."
)


class TxOutput(BaseModel):
    transaction_id: str
    index: int
    amount: int
    script_public_key: str
    script_public_key_address: str
    script_public_key_type: str
    accepting_block_hash: str | None

    class Config:
        orm_mode = True


class TxInput(BaseModel):
    transaction_id: str
    index: int
    previous_outpoint_hash: str
    previous_outpoint_index: str
    previous_outpoint_resolved: TxOutput | None
    previous_outpoint_address: str | None
    previous_outpoint_amount: int | None
    signature_script: str
    sig_op_count: str

    class Config:
        orm_mode = True


class TxModel(BaseModel):
    subnetwork_id: str | None
    transaction_id: str | None
    hash: str | None
    mass: str | None
    payload: str | None
    block_hash: List[str] | None
    block_time: int | None
    is_accepted: bool | None
    accepting_block_hash: str | None
    accepting_block_blue_score: int | None
    inputs: List[TxInput] | None
    outputs: List[TxOutput] | None

    class Config:
        orm_mode = True


class TxSearch(BaseModel):
    transactionIds: List[str]


class PreviousOutpointLookupMode(str, Enum):
    no = "no"
    light = "light"
    full = "full"


@app.get(
    "/transactions/{transactionId}",
    response_model=TxModel,
    tags=["Kaspa transactions"],
    response_model_exclude_unset=True,
)
@sql_db_only
async def get_transaction(
    response: Response,
    transactionId: str = Path(regex="[a-f0-9]{64}"),
    inputs: bool = True,
    outputs: bool = True,
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(
        default=PreviousOutpointLookupMode.no, description=DESC_RESOLVE_PARAM
    ),
):
    """
    Retrieves transaction details for a given transaction ID from the database.
    Optionally includes `inputs` and `outputs`. Use `resolve_previous_outpoints` to
    enrich each input with data from the referenced previous outpoint. Modes:
    - `no`: No outpoint resolution.
    - `light`: Includes only address and amount.
    - `full`: Full outpoint data.
    """
    async with async_session() as s:
        tx = await s.execute(
            select(
                Transaction,
                Subnetwork,
                TransactionAcceptance.transaction_id.label("accepted_transaction_id"),
                TransactionAcceptance.block_hash.label("accepting_block_hash"),
                Block.blue_score,
            )
            .join(Subnetwork, Transaction.subnetwork_id == Subnetwork.id)
            .join(
                TransactionAcceptance, Transaction.transaction_id == TransactionAcceptance.transaction_id, isouter=True
            )
            .join(Block, TransactionAcceptance.block_hash == Block.hash, isouter=True)
            .filter(Transaction.transaction_id == transactionId)
        )

        tx = tx.first()

        tx_outputs = None
        tx_inputs = None

        block_hashes = (
            (
                await s.execute(
                    select(BlockTransaction.block_hash).filter(BlockTransaction.transaction_id == transactionId)
                )
            )
            .scalars()
            .all()
        )

        if outputs:
            tx_outputs = await s.execute(
                select(TransactionOutput).filter(TransactionOutput.transaction_id == transactionId)
            )

            tx_outputs = tx_outputs.scalars().all()

        if inputs:
            if resolve_previous_outpoints in ["light", "full"]:
                tx_inputs = await s.execute(
                    select(TransactionInput, TransactionOutput)
                    .outerjoin(
                        TransactionOutput,
                        (TransactionOutput.transaction_id == TransactionInput.previous_outpoint_hash)
                        & (TransactionOutput.index == TransactionInput.previous_outpoint_index),
                    )
                    .filter(TransactionInput.transaction_id == transactionId)
                )

                tx_inputs = tx_inputs.all()

                if resolve_previous_outpoints in ["light", "full"]:
                    for tx_in, tx_prev_outputs in tx_inputs:
                        # it is possible, that the old tx is not in database. Leave fields empty
                        if not tx_prev_outputs:
                            tx_in.previous_outpoint_amount = None
                            tx_in.previous_outpoint_address = None
                            if resolve_previous_outpoints == "full":
                                tx_in.previous_outpoint_resolved = None
                            continue

                        tx_in.previous_outpoint_amount = tx_prev_outputs.amount
                        tx_in.previous_outpoint_address = tx_prev_outputs.script_public_key_address
                        if resolve_previous_outpoints == "full":
                            tx_in.previous_outpoint_resolved = tx_prev_outputs

                # remove unneeded list
                tx_inputs = [x[0] for x in tx_inputs]

            else:
                tx_inputs = await s.execute(
                    select(TransactionInput).filter(TransactionInput.transaction_id == transactionId)
                )
                tx_inputs = tx_inputs.scalars().all()

    if tx:
        return {
            "subnetwork_id": tx.Subnetwork.subnetwork_id,
            "transaction_id": tx.Transaction.transaction_id,
            "hash": tx.Transaction.hash,
            "mass": tx.Transaction.mass,
            "payload": tx.Transaction.payload,
            "block_hash": block_hashes,
            "block_time": tx.Transaction.block_time,
            "is_accepted": True if tx.accepted_transaction_id else False,
            "accepting_block_hash": tx.accepting_block_hash,
            "accepting_block_blue_score": tx.blue_score,
            "outputs": parse_obj_as(List[TxOutput], sorted(tx_outputs, key=lambda x: x.index)) if tx_outputs else None,
            "inputs": parse_obj_as(List[TxInput], sorted(tx_inputs, key=lambda x: x.index)) if tx_inputs else None,
        }
    else:
        raise HTTPException(
            status_code=404, detail="Transaction not found", headers={"Cache-Control": "public, max-age=3"}
        )


@app.post(
    "/transactions/search", response_model=List[TxModel], tags=["Kaspa transactions"], response_model_exclude_unset=True
)
@sql_db_only
async def search_for_transactions(
    txSearch: TxSearch,
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(
        default=PreviousOutpointLookupMode.no, description=DESC_RESOLVE_PARAM
    ),
):
    """
    Searches for transactions by a list of transaction IDs with optional field filtering.
    Limits the ID list size to 1000; reduced to 50 for light/full previous outpoint resolution.
    Use the `fields` parameter to filter returned fields and optimize query load.
    Modes for `resolve_previous_outpoints`:
    - `no`: No outpoint data.
    - `light`: Adds address and amount from referenced outpoints.
    - `full`: Includes full outpoint data.
    """
    if len(txSearch.transactionIds) > 1000:
        raise HTTPException(422, "Too many transaction ids")

    if resolve_previous_outpoints in ["light", "full"] and len(txSearch.transactionIds) > 50:
        raise HTTPException(422, "Temporary issue: Transaction ids count is limited to 50 for light and full searches.")

    fields = fields.split(",") if fields else []

    async with async_session() as s:
        tx_list = await s.execute(
            select(
                Transaction,
                Subnetwork,
                TransactionAcceptance.transaction_id.label("accepted_transaction_id"),
                TransactionAcceptance.block_hash.label("accepting_block_hash"),
                Block.blue_score,
            )
            .join(Subnetwork, Transaction.subnetwork_id == Subnetwork.id)
            .join(
                TransactionAcceptance, Transaction.transaction_id == TransactionAcceptance.transaction_id, isouter=True
            )
            .join(Block, TransactionAcceptance.block_hash == Block.hash, isouter=True)
            .filter(Transaction.transaction_id.in_(txSearch.transactionIds))
            .order_by(Transaction.block_time.desc())
        )

        tx_list = tx_list.all()

        tx_blocks = await s.execute(
            select(BlockTransaction).filter(BlockTransaction.transaction_id.in_(txSearch.transactionIds))
        )
        tx_blocks = tx_blocks.scalars().all()

        if not fields or "inputs" in fields:
            # join TxOutputs if needed
            if resolve_previous_outpoints in ["light", "full"]:
                tx_inputs = await s.execute(
                    select(TransactionInput, TransactionOutput)
                    .outerjoin(
                        TransactionOutput,
                        (TransactionOutput.transaction_id == TransactionInput.previous_outpoint_hash)
                        & (TransactionOutput.index == TransactionInput.previous_outpoint_index),
                    )
                    .filter(TransactionInput.transaction_id.in_(txSearch.transactionIds))
                )

            # without joining previous_tx_outputs
            else:
                tx_inputs = await s.execute(
                    select(TransactionInput).filter(TransactionInput.transaction_id.in_(txSearch.transactionIds))
                )
            tx_inputs = tx_inputs.all()

            if resolve_previous_outpoints in ["light", "full"]:
                for tx_in, tx_prev_outputs in tx_inputs:
                    # it is possible, that the old tx is not in database. Leave fields empty
                    if not tx_prev_outputs:
                        tx_in.previous_outpoint_amount = None
                        tx_in.previous_outpoint_address = None
                        if resolve_previous_outpoints == "full":
                            tx_in.previous_outpoint_resolved = None
                        continue

                    tx_in.previous_outpoint_amount = tx_prev_outputs.amount
                    tx_in.previous_outpoint_address = tx_prev_outputs.script_public_key_address
                    if resolve_previous_outpoints == "full":
                        tx_in.previous_outpoint_resolved = tx_prev_outputs

            # remove unneeded list
            tx_inputs = [x[0] for x in tx_inputs]

        else:
            tx_inputs = None

        if not fields or "outputs" in fields:
            tx_outputs = await s.execute(
                select(TransactionOutput).filter(TransactionOutput.transaction_id.in_(txSearch.transactionIds))
            )
            tx_outputs = tx_outputs.scalars().all()
        else:
            tx_outputs = None

    return (
        filter_fields(
            {
                "subnetwork_id": tx.Subnetwork.subnetwork_id,
                "transaction_id": tx.Transaction.transaction_id,
                "hash": tx.Transaction.hash,
                "mass": tx.Transaction.mass,
                "payload": tx.Transaction.payload,
                "block_hash": [x.block_hash for x in tx_blocks if x.transaction_id == tx.Transaction.transaction_id],
                "block_time": tx.Transaction.block_time,
                "is_accepted": True if tx.accepted_transaction_id else False,
                "accepting_block_hash": tx.accepting_block_hash,
                "accepting_block_blue_score": tx.blue_score,
                "outputs": parse_obj_as(
                    List[TxOutput],
                    sorted(
                        [x for x in tx_outputs if x.transaction_id == tx.Transaction.transaction_id],
                        key=lambda x: x.index,
                    ),
                )
                if tx_outputs
                else None,  # parse only if needed
                "inputs": parse_obj_as(
                    List[TxInput],
                    sorted(
                        [x for x in tx_inputs if x.transaction_id == tx.Transaction.transaction_id],
                        key=lambda x: x.index,
                    ),
                )
                if tx_inputs
                else None,  # parse only if needed
            },
            fields,
        )
        for tx in tx_list
    )

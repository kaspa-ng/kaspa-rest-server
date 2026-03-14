# encoding: utf-8
import logging
from collections import defaultdict
from enum import Enum
from typing import List, Optional

from fastapi import Path, HTTPException, Query
from kaspa_script_address import to_address
from pydantic import BaseModel, Field
from sqlalchemy import exists, text
from sqlalchemy.future import select
from starlette.responses import Response

from constants import TX_SEARCH_ID_LIMIT, TX_SEARCH_BS_LIMIT, PREV_OUT_RESOLVED, ADDRESS_PREFIX
from dbsession import async_session, async_session_blocks
from endpoints import filter_fields, sql_db_only
from endpoints.get_blocks import get_block_from_kaspad
from helper.PublicKeyType import get_public_key_type
from helper.utils import add_cache_control
from models.Block import Block
from models.BlockTransaction import BlockTransaction
from models.Transaction import Transaction
from models.TransactionAcceptance import TransactionAcceptance
from models.TransactionTypes import bytea_to_hex
from server import app

_logger = logging.getLogger(__name__)

DESC_RESOLVE_PARAM = (
    "Use this parameter if you want to fetch the TransactionInput previous outpoint details."
    " Light fetches only the address and amount. Full fetches the whole TransactionOutput and "
    "adds it into each TxInput."
)


class TxOutput(BaseModel):
    transaction_id: str
    index: int
    amount: int
    script_public_key: str | None
    script_public_key_address: str | None
    script_public_key_type: str | None
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
    signature_script: str | None
    sig_op_count: str | None

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
    version: int | None
    is_accepted: bool | None
    accepting_block_hash: str | None
    accepting_block_blue_score: int | None
    accepting_block_time: int | None
    inputs: List[TxInput] | None
    outputs: List[TxOutput] | None

    class Config:
        orm_mode = True


class TxSearchAcceptingBlueScores(BaseModel):
    gte: int
    lt: int


class TxSearch(BaseModel):
    transactionIds: List[str] | None
    acceptingBlueScores: TxSearchAcceptingBlueScores | None


class TxAcceptanceRequest(BaseModel):
    transactionIds: list[str] = Field(
        example=[
            "b9382bdee4aa364acf73eda93914eaae61d0e78334d1b8a637ab89ef5e224e41",
            "1e098b3830c994beb28768f7924a38286cec16e85e9757e0dc3574b85f624c34",
            "000ad5138a603aadc25cfcca6b6605d5ff47d8c7be594c9cdd199afa6dc76ac6",
        ]
    )


class TxAcceptanceResponse(BaseModel):
    transactionId: str = "b9382bdee4aa364acf73eda93914eaae61d0e78334d1b8a637ab89ef5e224e41"
    accepted: bool
    acceptingBlockHash: str | None
    acceptingBlueScore: int | None
    acceptingTimestamp: int | None


class PreviousOutpointLookupMode(str, Enum):
    no = "no"
    light = "light"
    full = "full"


class AcceptanceMode(str, Enum):
    accepted = "accepted"
    rejected = "rejected"


@app.get(
    "/transactions/{transaction_id}",
    response_model=TxModel,
    tags=["Kaspa transactions"],
    response_model_exclude_unset=True,
)
@sql_db_only
async def get_transaction(
    response: Response,
    transaction_id: str = Path(regex="[a-f0-9]{64}"),
    blockHash: str = Query(None, description="Specify a containing block (if known) for faster lookup"),
    inputs: bool = True,
    outputs: bool = True,
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(
        default=PreviousOutpointLookupMode.no, description=DESC_RESOLVE_PARAM
    ),
):
    """
    Get details for a given transaction id
    """
    async with async_session_blocks() as session_blocks:
        async with async_session() as session:
            transaction = None
            if blockHash:
                block_hashes = [blockHash]
            else:
                block_hashes = await session_blocks.execute(
                    select(BlockTransaction.block_hash).filter(BlockTransaction.transaction_id == transaction_id)
                )
                block_hashes = block_hashes.scalars().all()

            if block_hashes:
                transaction = await get_transaction_from_kaspad(block_hashes, transaction_id, inputs, outputs)
                if transaction and transaction["inputs"] and inputs:
                    transaction["inputs"] = (
                        await resolve_inputs_from_db(transaction["inputs"], resolve_previous_outpoints, False)
                    ).get(transaction_id)

            if not transaction:
                tx = await session.execute(select(Transaction).filter(Transaction.transaction_id == transaction_id))
                tx = tx.first()

                if tx:
                    logging.debug(f"Found transaction {transaction_id} in database")
                    transaction = {
                        "subnetwork_id": tx.Transaction.subnetwork_id,
                        "transaction_id": tx.Transaction.transaction_id,
                        "hash": tx.Transaction.hash,
                        "mass": tx.Transaction.mass,
                        "payload": tx.Transaction.payload,
                        "block_hash": block_hashes,
                        "block_time": tx.Transaction.block_time,
                        "version": tx.Transaction.version or 0,
                        "inputs": [vars(i) for i in tx.Transaction.inputs]
                        if tx.Transaction.inputs and inputs
                        else None,
                        "outputs": [vars(o) for o in tx.Transaction.outputs]
                        if tx.Transaction.outputs and outputs
                        else None,
                    }
                    if transaction["inputs"]:
                        transaction["inputs"] = (
                            await resolve_inputs_from_db(transaction["inputs"], resolve_previous_outpoints)
                        ).get(transaction_id)

            if transaction:
                accepted_transaction_id, accepting_block_hash = (
                    await session.execute(
                        select(
                            TransactionAcceptance.transaction_id,
                            TransactionAcceptance.block_hash,
                        ).filter(TransactionAcceptance.transaction_id == transaction_id)
                    )
                ).one_or_none() or (None, None)
                transaction["is_accepted"] = accepted_transaction_id is not None

                if accepting_block_hash:
                    accepting_block_blue_score, accepting_block_time = (
                        await session_blocks.execute(
                            select(
                                Block.blue_score,
                                Block.timestamp,
                            ).filter(Block.hash == accepting_block_hash)
                        )
                    ).one_or_none() or (None, None)
                    transaction["accepting_block_hash"] = accepting_block_hash
                    transaction["accepting_block_blue_score"] = accepting_block_blue_score
                    transaction["accepting_block_time"] = accepting_block_time
                    if not accepting_block_blue_score:
                        accepting_block = await get_block_from_kaspad(accepting_block_hash, False, False)
                        accepting_block_header = accepting_block.get("header") if accepting_block else None
                        if accepting_block_header:
                            transaction["accepting_block_blue_score"] = accepting_block_header.get("blueScore")
                            transaction["accepting_block_time"] = accepting_block_header.get("timestamp")

    if transaction:
        add_cache_control(transaction.get("accepting_block_blue_score"), transaction.get("block_time"), response)
        return transaction
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
    fields: str = Query(default=""),
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(
        default=PreviousOutpointLookupMode.no, description=DESC_RESOLVE_PARAM
    ),
    acceptance: Optional[AcceptanceMode] = Query(
        default=None, description="Only used when searching using transactionIds"
    ),
):
    """
    Search for transactions by transaction_ids or blue_score
    """
    if not txSearch.transactionIds and not txSearch.acceptingBlueScores:
        return []

    if txSearch.transactionIds and len(txSearch.transactionIds) > TX_SEARCH_ID_LIMIT:
        raise HTTPException(422, f"Too many transaction ids. Max {TX_SEARCH_ID_LIMIT}")

    if txSearch.transactionIds and txSearch.acceptingBlueScores:
        raise HTTPException(422, "Only one of transactionIds and acceptingBlueScores must be non-null")

    if (
        txSearch.acceptingBlueScores
        and txSearch.acceptingBlueScores.lt - txSearch.acceptingBlueScores.gte > TX_SEARCH_BS_LIMIT
    ):
        raise HTTPException(400, f"Diff between acceptingBlueScores.gte and lt must be <= {TX_SEARCH_BS_LIMIT}")

    transaction_ids = set(txSearch.transactionIds or [])
    accepting_blue_score_gte = txSearch.acceptingBlueScores.gte if txSearch.acceptingBlueScores else None
    accepting_blue_score_lt = txSearch.acceptingBlueScores.lt if txSearch.acceptingBlueScores else None

    fields = fields.split(",") if fields else []

    async with async_session() as session:
        async with async_session_blocks() as session_blocks:
            tx_query = (
                select(
                    Transaction,
                    TransactionAcceptance.transaction_id.label("accepted_transaction_id"),
                    TransactionAcceptance.block_hash.label("accepting_block_hash"),
                )
                .outerjoin(TransactionAcceptance, Transaction.transaction_id == TransactionAcceptance.transaction_id)
                .order_by(Transaction.block_time.desc())
            )

            if accepting_blue_score_gte:
                tx_acceptances = await session_blocks.execute(
                    select(
                        Block.hash.label("accepting_block_hash"),
                        Block.blue_score.label("accepting_block_blue_score"),
                        Block.timestamp.label("accepting_block_time"),
                    )
                    .filter(exists().where(TransactionAcceptance.block_hash == Block.hash))  # Only chain blocks
                    .filter(Block.blue_score >= accepting_blue_score_gte)
                    .filter(Block.blue_score < accepting_blue_score_lt)
                )
                tx_acceptances = {row.accepting_block_hash: row for row in tx_acceptances.all()}
                if not tx_acceptances:
                    return []
                tx_query = tx_query.filter(TransactionAcceptance.block_hash.in_(tx_acceptances.keys()))
                tx_list = (await session.execute(tx_query)).all()
                transaction_ids = [row.Transaction.transaction_id for row in tx_list]
            else:
                tx_query = tx_query.filter(Transaction.transaction_id.in_(transaction_ids))
                if acceptance == AcceptanceMode.accepted:
                    tx_query = tx_query.filter(TransactionAcceptance.transaction_id.is_not(None))
                elif acceptance == AcceptanceMode.rejected:
                    tx_query = tx_query.filter(TransactionAcceptance.transaction_id.is_(None))
                tx_list = (await session.execute(tx_query)).all()
                if not tx_list:
                    return []
                accepting_block_hashes = [
                    row.accepting_block_hash for row in tx_list if row.accepting_block_hash is not None
                ]
                tx_acceptances = await session_blocks.execute(
                    select(
                        Block.hash.label("accepting_block_hash"),
                        Block.blue_score.label("accepting_block_blue_score"),
                        Block.timestamp.label("accepting_block_time"),
                    ).filter(Block.hash.in_(accepting_block_hashes))
                )
                tx_acceptances = {row.accepting_block_hash: row for row in tx_acceptances.all()}

    if not fields or "inputs" in fields:
        tx_inputs = await resolve_inputs_from_db(
            [vars(i) for tx in tx_list for i in (tx.Transaction.inputs or []) if i], resolve_previous_outpoints
        )
    else:
        tx_inputs = {}
    tx_blocks = await get_tx_blocks_from_db(fields, transaction_ids)

    block_cache = {}
    results = []
    for tx in tx_list:
        accepting_block_blue_score = None
        accepting_block_time = None
        accepting_block = tx_acceptances.get(tx.accepting_block_hash)
        if accepting_block:
            accepting_block_blue_score = accepting_block.accepting_block_blue_score
            accepting_block_time = accepting_block.accepting_block_time
        else:
            if tx.accepting_block_hash:
                if tx.accepting_block_hash not in block_cache:
                    block_cache[tx.accepting_block_hash] = await get_block_from_kaspad(
                        tx.accepting_block_hash, False, False
                    )
                accepting_block = block_cache[tx.accepting_block_hash]
                if accepting_block and accepting_block["header"]:
                    accepting_block_blue_score = accepting_block["header"]["blueScore"]
                    accepting_block_time = accepting_block["header"]["timestamp"]

        result = filter_fields(
            {
                "subnetwork_id": tx.Transaction.subnetwork_id,
                "transaction_id": tx.Transaction.transaction_id,
                "hash": tx.Transaction.hash,
                "mass": tx.Transaction.mass,
                "payload": tx.Transaction.payload,
                "block_hash": tx_blocks.get(tx.Transaction.transaction_id),
                "block_time": tx.Transaction.block_time,
                "version": tx.Transaction.version or 0,
                "is_accepted": True if tx.accepted_transaction_id else False,
                "accepting_block_hash": tx.accepting_block_hash,
                "accepting_block_blue_score": accepting_block_blue_score,
                "accepting_block_time": accepting_block_time,
                "inputs": tx_inputs.get(tx.Transaction.transaction_id) if not fields or "inputs" in fields else None,
                "outputs": [vars(o) for o in tx.Transaction.outputs]
                if tx.Transaction.outputs and not fields or "outputs" in fields
                else None,
            },
            fields,
        )
        results.append(result)
    return results


@app.post(
    "/transactions/acceptance",
    response_model=List[TxAcceptanceResponse],
    response_model_exclude_unset=True,
    tags=["Kaspa transactions"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_transaction_acceptance(tx_acceptance_request: TxAcceptanceRequest):
    """
    Given a list of transaction_ids, return whether each one is accepted and the accepting blue score and timestamp.
    """
    transaction_ids = tx_acceptance_request.transactionIds
    if len(transaction_ids) > TX_SEARCH_ID_LIMIT:
        raise HTTPException(422, f"Too many transaction ids. Max {TX_SEARCH_ID_LIMIT}")

    async with async_session() as s:
        result = await s.execute(
            select(TransactionAcceptance.transaction_id, TransactionAcceptance.block_hash).where(
                TransactionAcceptance.transaction_id.in_(set(transaction_ids))
            )
        )
        transaction_id_to_block_hash = {tx_id: block_hash for tx_id, block_hash in result}

    async with async_session_blocks() as s:
        result = await s.execute(
            select(Block.hash, Block.blue_score, Block.timestamp).where(
                Block.hash.in_(set(transaction_id_to_block_hash.values()))
            )
        )
        block_hash_to_info = {block_hash: (blue_score, timestamp) for block_hash, blue_score, timestamp in result}

    responses = []
    for tx_id in transaction_ids:
        block_hash = transaction_id_to_block_hash.get(tx_id)
        blue_score, timestamp = block_hash_to_info.get(block_hash, (None, None))
        responses.append(
            TxAcceptanceResponse(
                transactionId=tx_id,
                accepted=block_hash is not None,
                acceptingBlockHash=block_hash,
                acceptingBlueScore=blue_score,
                acceptingTimestamp=timestamp,
            )
        )
    return responses


async def get_tx_blocks_from_db(fields, transaction_ids):
    tx_blocks_dict = defaultdict(list)
    if fields and "block_hash" not in fields:
        return tx_blocks_dict

    async with async_session_blocks() as session_blocks:
        tx_blocks = await session_blocks.execute(
            select(BlockTransaction).filter(BlockTransaction.transaction_id.in_(transaction_ids))
        )
        for row in tx_blocks.scalars().all():
            tx_blocks_dict[row.transaction_id].append(row.block_hash)
        return tx_blocks_dict


async def resolve_inputs_from_db(inputs, resolve_previous_outpoints, prev_out_resolved=PREV_OUT_RESOLVED):
    if inputs and (
        resolve_previous_outpoints == PreviousOutpointLookupMode.light
        and not prev_out_resolved
        or resolve_previous_outpoints == PreviousOutpointLookupMode.full
    ):
        tx_ids, tx_indices, prev_hashes, prev_indices = zip(
            *[
                (
                    bytes.fromhex(i["transaction_id"]),
                    i["index"],
                    bytes.fromhex(i["previous_outpoint_hash"]),
                    i["previous_outpoint_index"],
                )
                for i in inputs
            ]
        )

        query = text("""
            WITH inputs AS (
                SELECT
                    unnest(:tx_ids) AS transaction_id,
                    unnest(:tx_indices) AS index,
                    unnest(:prev_hashes) AS previous_outpoint_hash,
                    unnest(:prev_indices) AS previous_outpoint_index
            )
            SELECT
                i.transaction_id,
                i.index,
                o.amount AS previous_outpoint_amount,
                o.script_public_key AS previous_outpoint_script,
                o.script_public_key_address AS previous_outpoint_address
            FROM inputs i
            JOIN transactions t ON t.transaction_id = i.previous_outpoint_hash
            CROSS JOIN LATERAL unnest(t.outputs) AS o
            WHERE o.index = i.previous_outpoint_index
            """)

        async with async_session() as session:
            result = await session.execute(
                query,
                {
                    "tx_ids": list(tx_ids),
                    "tx_indices": list(tx_indices),
                    "prev_hashes": list(prev_hashes),
                    "prev_indices": list(prev_indices),
                },
            )
            rows = result.fetchall()

            resolved_inputs_dict = {(bytea_to_hex(r.transaction_id), r.index): r for r in rows}
            for i in inputs:
                resolved_input = resolved_inputs_dict.get((i["transaction_id"], i["index"]))
                if resolved_input:
                    previous_outpoint_script = bytea_to_hex(resolved_input.previous_outpoint_script)
                    previous_outpoint_address = resolved_input.previous_outpoint_address
                    if not previous_outpoint_address and previous_outpoint_script:
                        previous_outpoint_address = to_address(ADDRESS_PREFIX, previous_outpoint_script)
                    i["previous_outpoint_amount"] = resolved_input.previous_outpoint_amount
                    i["previous_outpoint_address"] = previous_outpoint_address
                    if resolve_previous_outpoints == PreviousOutpointLookupMode.full:
                        i["previous_outpoint_resolved"] = {
                            "transaction_id": i["previous_outpoint_hash"],
                            "index": i["previous_outpoint_index"],
                            "amount": resolved_input.previous_outpoint_amount,
                            "script_public_key": previous_outpoint_script,
                            "script_public_key_address": previous_outpoint_address,
                            "script_public_key_type": get_public_key_type(previous_outpoint_script),
                        }
    elif resolve_previous_outpoints == PreviousOutpointLookupMode.no:
        for i in inputs:  # Clear any pre-resolved for consistency
            i["previous_outpoint_amount"] = None
            i["previous_outpoint_script"] = None
            i["previous_outpoint_address"] = None

    inputs_by_txid = {}
    for i in inputs:
        inputs_by_txid.setdefault(i["transaction_id"], []).append(i)
    return inputs_by_txid


async def get_transaction_from_kaspad(block_hashes, transaction_id, include_inputs, include_outputs):
    block = await get_block_from_kaspad(block_hashes[0], True, False)
    return map_transaction_from_kaspad(block, transaction_id, block_hashes, include_inputs, include_outputs)


def map_transaction_from_kaspad(block, transaction_id, block_hashes, include_inputs, include_outputs):
    if block and "transactions" in block:
        for tx in block["transactions"]:
            if tx["verboseData"]["transactionId"] == transaction_id:
                return {
                    "subnetwork_id": tx["subnetworkId"],
                    "transaction_id": tx["verboseData"]["transactionId"],
                    "hash": tx["verboseData"]["hash"],
                    "mass": tx["verboseData"]["computeMass"]
                    if tx["verboseData"].get("computeMass", "0") not in ("0", 0)
                    else None,
                    "payload": tx["payload"] if tx["payload"] else None,
                    "block_hash": block_hashes,
                    "block_time": tx["verboseData"]["blockTime"],
                    "version": tx["version"],
                    "inputs": [
                        {
                            "transaction_id": tx["verboseData"]["transactionId"],
                            "index": tx_in_idx,
                            "previous_outpoint_hash": tx_in["previousOutpoint"]["transactionId"],
                            "previous_outpoint_index": tx_in["previousOutpoint"]["index"],
                            "signature_script": tx_in["signatureScript"],
                            "sig_op_count": tx_in["sigOpCount"],
                        }
                        for tx_in_idx, tx_in in enumerate(tx["inputs"])
                    ]
                    if include_inputs and tx["inputs"]
                    else None,
                    "outputs": [
                        {
                            "transaction_id": tx["verboseData"]["transactionId"],
                            "index": tx_out_idx,
                            "amount": tx_out["amount"],
                            "script_public_key": tx_out["scriptPublicKey"]["scriptPublicKey"],
                            "script_public_key_address": tx_out["verboseData"]["scriptPublicKeyAddress"],
                            "script_public_key_type": tx_out["verboseData"]["scriptPublicKeyType"],
                        }
                        for tx_out_idx, tx_out in enumerate(tx["outputs"])
                    ]
                    if include_outputs and tx["outputs"]
                    else None,
                }

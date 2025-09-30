# encoding: utf-8
import asyncio
import logging
from collections import defaultdict
from enum import Enum
from typing import List, Optional

from fastapi import Path, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists
from sqlalchemy.future import select
from starlette.responses import Response

from constants import TX_SEARCH_ID_LIMIT, TX_SEARCH_BS_LIMIT, PREV_OUT_RESOLVED
from dbsession import async_session, async_session_blocks
from endpoints import filter_fields, sql_db_only
from endpoints.get_blocks import get_block_from_kaspad
from helper.utils import add_cache_control
from models.Block import Block
from models.BlockTransaction import BlockTransaction
from models.Subnetwork import Subnetwork
from models.Transaction import Transaction, TransactionOutput, TransactionInput
from models.TransactionAcceptance import TransactionAcceptance
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
    acceptingBlueScore: int | None


class PreviousOutpointLookupMode(str, Enum):
    no = "no"
    light = "light"
    full = "full"


class AcceptanceMode(str, Enum):
    accepted = "accepted"
    rejected = "rejected"


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
    res_outpoints = resolve_previous_outpoints

    # --- Шаг 1: Получить все данные из БД и сразу закрыть сессии ---
    block_hashes = None
    db_transaction = None
    accepted_transaction_id = None
    accepting_block_hash = None
    accepting_block_blue_score = None
    accepting_block_time = None

    async with async_session_blocks() as session_blocks:
        if blockHash:
            block_hashes = [blockHash]
        else:
            result = await session_blocks.execute(
                select(BlockTransaction.block_hash).filter(BlockTransaction.transaction_id == transactionId)
            )
            block_hashes = result.scalars().all()

        # Попытка найти принятие транзакции и accepting block
        if block_hashes:
            acceptance_result = await session_blocks.execute(
                select(TransactionAcceptance.transaction_id, TransactionAcceptance.block_hash)
                .filter(TransactionAcceptance.transaction_id == transactionId)
            )
            acceptance_row = acceptance_result.one_or_none()
            if acceptance_row:
                accepted_transaction_id, accepting_block_hash = acceptance_row
            else:
                accepted_transaction_id, accepting_block_hash = None, None

            # Если есть accepting_block_hash — попробуем получить его данные из БД
            if accepting_block_hash:
                block_result = await session_blocks.execute(
                    select(Block.blue_score, Block.timestamp)
                    .filter(Block.hash == accepting_block_hash)
                )
                block_row = block_result.one_or_none()
                if block_row:
                    accepting_block_blue_score, accepting_block_time = block_row

    # --- Шаг 2: Выполняем внешние HTTP-вызовы (без открытых сессий!) ---
    transaction = None

    # Сначала пробуем получить транзакцию из kaspad, если есть block_hashes
    if block_hashes:
        transaction = await get_transaction_from_kaspad(block_hashes, transactionId, inputs, outputs)

    # Если не получили из kaspad — используем данные из БД
    if not transaction and db_transaction:
        transaction = db_transaction
        transaction["block_hash"] = block_hashes  # может быть None или []

        # Загружаем inputs/outputs из БД при необходимости
        if inputs and (res_outpoints != "light" or PREV_OUT_RESOLVED) and res_outpoints != "full":
            tx_inputs = await get_tx_inputs_from_db(None, res_outpoints, [transactionId])
            transaction["inputs"] = tx_inputs.get(transactionId)

        if outputs:
            tx_outputs = await get_tx_outputs_from_db(None, [transactionId])
            transaction["outputs"] = tx_outputs.get(transactionId)

    # Получаем транзакцию из основной БД только если Kaspad не дал результат
    if not transaction:
        async with async_session() as session:
            tx = await session.execute(
                select(Transaction, Subnetwork)
                .join(Subnetwork, Transaction.subnetwork_id == Subnetwork.id)
                .filter(Transaction.transaction_id == transactionId)
            )
            tx = tx.first()
            if tx:
                transaction = {
                    "subnetwork_id": tx.Subnetwork.subnetwork_id,
                    "transaction_id": tx.Transaction.transaction_id,
                    "hash": tx.Transaction.hash,
                    "mass": tx.Transaction.mass,
                    "payload": tx.Transaction.payload,
                    "block_time": tx.Transaction.block_time,
                    "block_hash": block_hashes,  # важно!
                }

                # Загружаем inputs/outputs из БД при необходимости
                if inputs and (res_outpoints != "light" or PREV_OUT_RESOLVED) and res_outpoints != "full":
                    tx_inputs = await get_tx_inputs_from_db(None, res_outpoints, [transactionId])
                    transaction["inputs"] = tx_inputs.get(transactionId)

                if outputs:
                    tx_outputs = await get_tx_outputs_from_db(None, [transactionId])
                    transaction["outputs"] = tx_outputs.get(transactionId)

    # Дополнительная обработка inputs при light/full resolve
    if transaction and inputs and (res_outpoints == "light" and not PREV_OUT_RESOLVED or res_outpoints == "full"):
        tx_inputs = await get_tx_inputs_from_db(None, res_outpoints, [transactionId])
        if transactionId in tx_inputs:
            transaction["inputs"] = tx_inputs[transactionId]

    # Устанавливаем флаг принятия
    if transaction is not None:
        transaction["is_accepted"] = accepted_transaction_id is not None
        if accepting_block_hash:
            transaction["accepting_block_hash"] = accepting_block_hash
            transaction["accepting_block_blue_score"] = accepting_block_blue_score
            transaction["accepting_block_time"] = accepting_block_time

            # Если данных о блоке нет — запрашиваем из kaspad
            if accepting_block_blue_score is None:
                accepting_block = await get_block_from_kaspad(accepting_block_hash, False, False)
                if accepting_block and accepting_block.get("header"):
                    header = accepting_block["header"]
                    transaction["accepting_block_blue_score"] = header.get("blueScore")
                    transaction["accepting_block_time"] = header.get("timestamp")

    # --- Шаг 3: Финальная проверка и ответ ---
    if transaction is not None:
        # Убедимся, что block_hash установлен (может быть None из kaspad)
        if "block_hash" not in transaction:
            transaction["block_hash"] = block_hashes

        add_cache_control(
            transaction.get("accepting_block_blue_score"),
            transaction.get("block_time"),
            response
        )
        return transaction
    else:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found",
            headers={"Cache-Control": "public, max-age=3"}
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
                    Subnetwork,
                    TransactionAcceptance.transaction_id.label("accepted_transaction_id"),
                    TransactionAcceptance.block_hash.label("accepting_block_hash"),
                )
                .join(Subnetwork, Transaction.subnetwork_id == Subnetwork.id)
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

    async_tasks = [
        get_tx_blocks_from_db(fields, transaction_ids),
        get_tx_inputs_from_db(fields, resolve_previous_outpoints, transaction_ids),
        get_tx_outputs_from_db(fields, transaction_ids),
    ]
    tx_blocks, tx_inputs, tx_outputs = await asyncio.gather(*async_tasks)

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
                "subnetwork_id": tx.Subnetwork.subnetwork_id,
                "transaction_id": tx.Transaction.transaction_id,
                "hash": tx.Transaction.hash,
                "mass": tx.Transaction.mass,
                "payload": tx.Transaction.payload,
                "block_hash": tx_blocks.get(tx.Transaction.transaction_id),
                "block_time": tx.Transaction.block_time,
                "is_accepted": True if tx.accepted_transaction_id else False,
                "accepting_block_hash": tx.accepting_block_hash,
                "accepting_block_blue_score": accepting_block_blue_score,
                "accepting_block_time": accepting_block_time,
                "outputs": tx_outputs.get(tx.Transaction.transaction_id),
                "inputs": tx_inputs.get(tx.Transaction.transaction_id),
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
    Given a list of transaction_ids, return whether each one is accepted and the accepting blue score.
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
            select(Block.hash, Block.blue_score).where(Block.hash.in_(set(transaction_id_to_block_hash.values())))
        )
        block_hash_to_blue_score = {block_hash: blue_score for block_hash, blue_score in result}

    return [
        TxAcceptanceResponse(
            transactionId=transaction_id,
            accepted=(transaction_id in transaction_id_to_block_hash),
            acceptingBlueScore=block_hash_to_blue_score.get(transaction_id_to_block_hash.get(transaction_id)),
        )
        for transaction_id in transaction_ids
    ]


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


async def get_tx_inputs_from_db(fields, resolve_previous_outpoints, transaction_ids):
    tx_inputs_dict = defaultdict(list)
    if fields and "inputs" not in fields:
        return tx_inputs_dict

    async with async_session() as session:
        if resolve_previous_outpoints == "light" and not PREV_OUT_RESOLVED or resolve_previous_outpoints == "full":
            tx_inputs = await session.execute(
                select(TransactionInput, TransactionOutput)
                .outerjoin(
                    TransactionOutput,
                    (TransactionOutput.transaction_id == TransactionInput.previous_outpoint_hash)
                    & (TransactionOutput.index == TransactionInput.previous_outpoint_index),
                )
                .filter(TransactionInput.transaction_id.in_(transaction_ids))
                .order_by(TransactionInput.transaction_id, TransactionInput.index)
            )
            for tx_input, tx_prev_output in tx_inputs.all():
                if tx_prev_output:
                    tx_input.previous_outpoint_script = tx_prev_output.script_public_key
                    tx_input.previous_outpoint_amount = tx_prev_output.amount
                    if resolve_previous_outpoints == "full":
                        tx_input.previous_outpoint_resolved = tx_prev_output
                else:
                    tx_input.previous_outpoint_script = None
                    tx_input.previous_outpoint_amount = None
                    if resolve_previous_outpoints == "full":
                        tx_input.previous_outpoint_resolved = None
                tx_inputs_dict[tx_input.transaction_id].append(tx_input)
        else:
            tx_inputs = await session.execute(
                select(TransactionInput)
                .filter(TransactionInput.transaction_id.in_(transaction_ids))
                .order_by(TransactionInput.transaction_id, TransactionInput.index)
            )
            for tx_input in tx_inputs.scalars().all():
                if resolve_previous_outpoints == "no" and PREV_OUT_RESOLVED:
                    tx_input.previous_outpoint_script = None
                    tx_input.previous_outpoint_amount = None
                tx_inputs_dict[tx_input.transaction_id].append(tx_input)
        return tx_inputs_dict


async def get_tx_outputs_from_db(fields, transaction_ids):
    tx_outputs_dict = defaultdict(list)
    if fields and "outputs" not in fields:
        return tx_outputs_dict

    async with async_session() as session:
        tx_outputs = await session.execute(
            select(TransactionOutput)
            .filter(TransactionOutput.transaction_id.in_(transaction_ids))
            .order_by(TransactionOutput.transaction_id, TransactionOutput.index)
        )
        for tx_output in tx_outputs.scalars().all():
            tx_outputs_dict[tx_output.transaction_id].append(tx_output)
        return tx_outputs_dict


async def get_transaction_from_kaspad(block_hashes: list[str], transaction_id: str, include_inputs: bool, include_outputs: bool):
    """
    Fetch transaction details directly from Kaspad using the first block hash.
    Does NOT interact with the database.
    Returns a dict with the same structure as the DB-based transaction.
    """
    if not block_hashes:
        return None

    # Запрашиваем блок у Kaspad
    block = await get_block_from_kaspad(block_hashes[0], True, True)
    if not block or "transactions" not in block:
        return None

    # Ищем нужную транзакцию в блоке
    for tx in block["transactions"]:
        verbose_data = tx.get("verboseData", {})
        if verbose_data.get("transactionId") == transaction_id:
            return map_transaction_from_kaspad(
                block=block,
                transaction_id=transaction_id,
                block_hashes=block_hashes,
                include_inputs=include_inputs,
                include_outputs=include_outputs,
            )

    return None


def map_transaction_from_kaspad(block, transaction_id, block_hashes, include_inputs, include_outputs):
    """
    Maps raw Kaspad transaction data into the expected response structure.
    Pure function — no I/O, no DB calls.
    """
    for tx in block.get("transactions", []):
        verbose = tx.get("verboseData", {})
        if verbose.get("transactionId") == transaction_id:
            return {
                "subnetwork_id": tx.get("subnetworkId"),
                "transaction_id": verbose.get("transactionId"),
                "hash": verbose.get("hash"),
                "mass": verbose.get("computeMass") if verbose.get("computeMass") not in ("0", 0) else None,
                "payload": tx.get("payload") or None,
                "block_hash": block_hashes,
                "block_time": verbose.get("blockTime"),
                "inputs": [
                    {
                        "transaction_id": verbose.get("transactionId"),
                        "index": idx,
                        "previous_outpoint_hash": inp["previousOutpoint"]["transactionId"],
                        "previous_outpoint_index": inp["previousOutpoint"]["index"],
                        "signature_script": inp.get("signatureScript"),
                        "sig_op_count": inp.get("sigOpCount"),
                        "previous_outpoint_resolved": None,          # будет заполнено позже, если нужно
                        "previous_outpoint_address": None,           # будет заполнено позже
                        "previous_outpoint_amount": None,            # будет заполнено позже
                    }
                    for idx, inp in enumerate(tx.get("inputs", []))
                ] if include_inputs and tx.get("inputs") else None,
                "outputs": [
                    {
                        "transaction_id": verbose.get("transactionId"),
                        "index": idx,
                        "amount": out.get("amount"),
                        "script_public_key": out.get("scriptPublicKey", {}).get("scriptPublicKey"),
                        "script_public_key_address": out.get("verboseData", {}).get("scriptPublicKeyAddress"),
                        "script_public_key_type": out.get("verboseData", {}).get("scriptPublicKeyType"),
                        "accepting_block_hash": None,  # неизвестно на этом этапе
                    }
                    for idx, out in enumerate(tx.get("outputs", []))
                ] if include_outputs and tx.get("outputs") else None,
            }
    return None

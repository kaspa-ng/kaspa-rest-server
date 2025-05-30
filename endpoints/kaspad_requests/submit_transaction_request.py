# encoding: utf-8
import logging
from asyncio import wait_for
from typing import List

from fastapi import Query, HTTPException
from kaspa import (
    Transaction,
    TransactionInput,
    TransactionOutpoint,
    TransactionOutput,
    ScriptPublicKey,
    Hash,
)
from pydantic import BaseModel
from starlette.responses import JSONResponse

from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client

_logger = logging.getLogger(__name__)


class SubmitTxOutpoint(BaseModel):
    transactionId: str
    index: int


class SubmitTxInput(BaseModel):
    previousOutpoint: SubmitTxOutpoint
    signatureScript: str
    sequence: int
    sigOpCount: int


class SubmitTxScriptPublicKey(BaseModel):
    version: int
    scriptPublicKey: str


class SubmitTxOutput(BaseModel):
    amount: int
    scriptPublicKey: SubmitTxScriptPublicKey


class SubmitTxModel(BaseModel):
    version: int
    inputs: List[SubmitTxInput]
    outputs: List[SubmitTxOutput]
    lockTime: int | None = 0
    subnetworkId: str | None


class SubmitTransactionRequest(BaseModel):
    transaction: SubmitTxModel
    allowOrphan: bool = False


class SubmitTransactionResponse(BaseModel):
    transactionId: str | None
    error: str | None


@app.post(
    "/transactions",
    tags=["Kaspa transactions"],
    response_model_exclude_unset=True,
    responses={200: {"model": SubmitTransactionResponse}, 400: {"model": SubmitTransactionResponse}},
)
async def submit_a_new_transaction(
    body: SubmitTransactionRequest,
    replaceByFee: bool = Query(description="Replace an existing transaction in the mempool", default=False),
):
    rpc_client = await kaspad_rpc_client()
    if replaceByFee:
        if rpc_client:
            tx = convert_from_legacy_tx(body.transaction)
            try:
                tx_resp = await wait_for(rpc_client.submit_transaction_replacement({"transaction": tx}), 10)
            except Exception as e:
                logging.warning(f"Failed submitting transaction, error (w1r): {str(e)}")
                return JSONResponse(status_code=400, content={"error": str(e)})
        else:
            resp = await kaspad_client.request(
                "submitTransactionReplacementRequest", {"transaction": body.transaction.dict()}
            )
            if resp.get("error"):
                logging.warning(f"Failed submitting transaction, error (g1r): {resp['error']}")
                raise HTTPException(500, resp["error"])
            tx_resp = resp["submitTransactionReplacementResponse"]
    else:
        if rpc_client:
            tx = convert_from_legacy_tx(body.transaction)
            try:
                tx_resp = await wait_for(
                    rpc_client.submit_transaction({"allow_orphan": body.allowOrphan, "transaction": tx}), 10
                )
            except Exception as e:
                logging.warning(f"Failed submitting transaction, error (w1): {str(e)}")
                return JSONResponse(status_code=400, content={"error": str(e)})
        else:
            resp = await kaspad_client.request("submitTransactionRequest", body.dict())
            if resp.get("error"):
                logging.warning(f"Failed submitting transaction, error (g1): {resp['error']}")
                raise HTTPException(500, resp["error"])
            tx_resp = resp["submitTransactionResponse"]

    if "error" in tx_resp:
        logging.warning(f"Failed submitting transaction, error (2): {tx_resp['error'].get('message', '')}")
        return JSONResponse(status_code=400, content={"error": tx_resp["error"].get("message", "")})
    elif "transactionId" in tx_resp:
        logging.info(f"Successfully submitted transaction: {tx_resp['transactionId']}")
        return {"transactionId": tx_resp["transactionId"]}
    else:
        logging.warning(f"Failed submitting transaction, error (3): {str(tx_resp)}")
        return JSONResponse(status_code=500, content={"error": str(tx_resp)})


def convert_from_legacy_tx(transaction: SubmitTxModel) -> Transaction | None:
    if not transaction:
        return
    return Transaction(
        transaction.version,
        [
            TransactionInput(
                TransactionOutpoint(Hash(i.previousOutpoint.transactionId), i.previousOutpoint.index),
                i.signatureScript,
                i.sequence,
                i.sigOpCount,
            )
            for i in transaction.inputs
        ],
        [
            TransactionOutput(o.amount, ScriptPublicKey(o.scriptPublicKey.version, o.scriptPublicKey.scriptPublicKey))
            for o in transaction.outputs
        ],
        transaction.lockTime or 0,
        transaction.subnetworkId or "0000000000000000000000000000000000000000",
        0,
        "",
        0,
    )


"""
{
  "transaction": {
    "version": 0,
    "inputs": [
      {
        "previousOutpoint": {
          "transactionId": "fa99f98b8e9b0758100d181eccb35a4c053b8265eccb5a89aadd794e087d9820",
          "index": 1
        },
        "signatureScript": "4187173244180496d67a94dc78f3d3651bc645139b636a9c79a4f1d36fdcc718e88e9880eeb0eb208d0c110f31a306556457bc37e1044aeb3fdd303bd1a8c1b84601",
        "sequence": 0,
        "sigOpCount": 1
      }
    ],
    "outputs": [
      {
        "amount": 100000,
        "scriptPublicKey": {
          "scriptPublicKey": "20167f5647a0e88ed3ac7834b5de4a5f0e56a438bcb6c97186a2c935303290ef6fac",
          "version": 0
        }
      },
      {
        "amount": 183448,
        "scriptPublicKey": {
          "scriptPublicKey": "2010352c822bf3c67637c84ea09ff90edc11fa509475ae1884cf5b971e53afd472ac",
          "version": 0
        }
      }
    ],
    "lockTime": 0,
    "subnetworkId": "0000000000000000000000000000000000000000"
  }
}
"""

# encoding: utf-8
import asyncio

from kaspad.KaspadClient import KaspadClient

# poetry run python -m grpc_tools.protoc -I./protos --python_out=. --grpc_python_out=. ./protos/rpc.proto ./protos/messages.proto
from kaspad.KaspadThread import KaspadCommunicationError


class KaspadMultiClient(object):
    def __init__(self, hosts: list[str]):
        self.kaspads = [KaspadClient(*h.split(":")) for h in hosts]

    def __get_kaspad(self):
        for k in self.kaspads:
            if k.is_utxo_indexed and k.is_synced:
                return k
        return None

    async def initialize_all(self):
        tasks = [asyncio.create_task(k.ping()) for k in self.kaspads]

        for t in tasks:
            await t

    async def request(self, command, params=None, timeout=5):
        client = self.__get_kaspad()
        if client is None:
            await self.initialize_all()
            client = self.__get_kaspad()
            if client is None:
                raise KaspadCommunicationError("no synced kaspad available")
        try:
            return await client.request(command, params, timeout=timeout)
        except KaspadCommunicationError:
            await self.initialize_all()
            client = self.__get_kaspad()
            if client is None:
                raise KaspadCommunicationError("no synced kaspad available after re-init")
            return await client.request(command, params, timeout=timeout)

    async def notify(self, command, params, callback):
        client = self.__get_kaspad()
        if client is None:
            raise KaspadCommunicationError("no synced kaspad available")
        return await client.notify(command, params, callback)

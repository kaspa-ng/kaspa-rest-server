from helper.mining_address import get_miner_payload_from_block, retrieve_miner_info_from_payload


def test_get_miner_payload_from_block():
    data = {
        "header": {
            "version": 1,
            "hashMerkleRoot": "a4f42ff8a8e240eb3f1b35cf7bd56044f3d4fe6db7b5cdbe56d858690c278778",
            "acceptedIdMerkleRoot": "3ef3fbf49340062398be32fa20c4bfb0786b0b147f0021821283eedce64ce01e",
            "utxoCommitment": "4ad51d9d625573e680f4c4211c9657c1026be501d38048a3f92cfca7b0ef181e",
            "timestamp": "1724081279941",
            "bits": 420908524,
            "nonce": "9519250016613520",
            "daaScore": "87768050",
            "blueWork": "56217f0bcee1a55ea0424",
            "parents": [
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {"parentHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"]},
                {
                    "parentHashes": [
                        "46bccc16780c4494380bda9b19a2027ea882f417ed077d05a84b2405c50c87bc",
                        "516f3ada5f6879ee10bd3ced654e5f0527c501179cff827d29e3a9034b9f1751",
                    ]
                },
                {"parentHashes": ["309e08307992aafc26fcc2a43deb62db0eb2da362bde602489a47d1843b26ac1"]},
                {"parentHashes": ["d3ef05369b407a36f577e68b240d4830d6bbcf387a2ccba7a14df692edabde83"]},
                {"parentHashes": ["d3ef05369b407a36f577e68b240d4830d6bbcf387a2ccba7a14df692edabde83"]},
                {"parentHashes": ["9bfeb17963c903e61e83a1d0d2ab749ff851f7780835eef2bea1307a4203bd33"]},
                {"parentHashes": ["9bfeb17963c903e61e83a1d0d2ab749ff851f7780835eef2bea1307a4203bd33"]},
                {"parentHashes": ["9bfeb17963c903e61e83a1d0d2ab749ff851f7780835eef2bea1307a4203bd33"]},
                {"parentHashes": ["5a7dc00ae69d152101381e8443a99b569a7a3372113833fe3dfc48cf1d8dfe9e"]},
                {"parentHashes": ["316f6dc2ed29853fcada555c9ee790e3f8247802984387c08eabb638588b89a9"]},
                {"parentHashes": ["316f6dc2ed29853fcada555c9ee790e3f8247802984387c08eabb638588b89a9"]},
                {"parentHashes": ["316f6dc2ed29853fcada555c9ee790e3f8247802984387c08eabb638588b89a9"]},
                {"parentHashes": ["25464ccd884133b3de6afe208ee22efc5b1d1445242a4495b8409f7ec37d8bce"]},
                {"parentHashes": ["25464ccd884133b3de6afe208ee22efc5b1d1445242a4495b8409f7ec37d8bce"]},
                {"parentHashes": ["2b9f6ef6d7944fce82d1c605ffbd3ef0ecc86bc09c898041680af69bd41a56dd"]},
                {"parentHashes": ["2b9f6ef6d7944fce82d1c605ffbd3ef0ecc86bc09c898041680af69bd41a56dd"]},
                {"parentHashes": ["9f3b4c43fd4c6f48fe5294029145222a4d6f9c4e3dd8bd2a81597047c1874347"]},
                {"parentHashes": ["9c7c5b2e0cb234c81cf3983fe866ef45d3425b68d577bc5cadb8f33b96d8c7df"]},
                {"parentHashes": ["9c7c5b2e0cb234c81cf3983fe866ef45d3425b68d577bc5cadb8f33b96d8c7df"]},
                {"parentHashes": ["9c7c5b2e0cb234c81cf3983fe866ef45d3425b68d577bc5cadb8f33b96d8c7df"]},
                {"parentHashes": ["9c7c5b2e0cb234c81cf3983fe866ef45d3425b68d577bc5cadb8f33b96d8c7df"]},
                {"parentHashes": ["9c7c5b2e0cb234c81cf3983fe866ef45d3425b68d577bc5cadb8f33b96d8c7df"]},
                {"parentHashes": ["9c7c5b2e0cb234c81cf3983fe866ef45d3425b68d577bc5cadb8f33b96d8c7df"]},
                {"parentHashes": ["9c7c5b2e0cb234c81cf3983fe866ef45d3425b68d577bc5cadb8f33b96d8c7df"]},
                {"parentHashes": ["9c7c5b2e0cb234c81cf3983fe866ef45d3425b68d577bc5cadb8f33b96d8c7df"]},
            ],
            "blueScore": "86160825",
            "pruningPoint": "ef3ae1d5568d2dda83833fa67cebd075b9a5198f14da6109baf770b29955ed6e",
        },
        "transactions": [
            {
                "outputs": [
                    {
                        "amount": "9249860567",
                        "scriptPublicKey": {
                            "scriptPublicKey": "20cdcb53d7708f03ffa58c989ad41ecd1b91e3f30a34bbd91f593aacdb5e0b2fd8ac",
                            "version": 0,
                        },
                        "verboseData": {
                            "scriptPublicKeyType": "pubkey",
                            "scriptPublicKeyAddress": "kaspa:qrxuk57hwz8s8la93jvf44q7e5derclnpg6thkgltya2ek67pvhasz43zf6ys",
                        },
                    }
                ],
                "subnetworkId": "0100000000000000000000000000000000000000",
                "payload": "b9b5220500000000d7ab55270200000000002220cdcb53d7708f03ffa58c989ad41ecd1b91e3f30a34bbd91f593aacdb5e0b2fd8ac302e31342e312f322f302f637878782f",
                "verboseData": {
                    "transactionId": "fb6e3181309b235d2a241b12374f9dca7d8d6cbddd2cf8cf218326fd6f5eef51",
                    "hash": "a4f42ff8a8e240eb3f1b35cf7bd56044f3d4fe6db7b5cdbe56d858690c278778",
                    "blockHash": "be95d8f3b51064e6bae0ce2659b2dbb9944fd47cc8e2510ecad73149f605e54c",
                    "blockTime": "1724081279941",
                    "mass": "0",
                },
                "version": 0,
                "inputs": [],
                "lockTime": "0",
                "gas": "0",
            }
        ],
        "verboseData": {
            "hash": "be95d8f3b51064e6bae0ce2659b2dbb9944fd47cc8e2510ecad73149f605e54c",
            "difficulty": 4.0893924312663526e17,
            "selectedParentHash": "911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9",
            "transactionIds": ["fb6e3181309b235d2a241b12374f9dca7d8d6cbddd2cf8cf218326fd6f5eef51"],
            "blueScore": "86160825",
            "childrenHashes": ["aeb31f138efa2c47b5b32638faf7cf313aa0f9706e236a41730855344bd7d184"],
            "mergeSetBluesHashes": ["911b8d97121c9972718913564732734e98545c280f4d9cc1101da747c1cdd6f9"],
            "isChainBlock": True,
            "isHeaderOnly": False,
            "mergeSetRedsHashes": [],
        },
    }

    assert (
        get_miner_payload_from_block(data)
        == "b9b5220500000000d7ab55270200000000002220cdcb53d7708f03ffa58c989ad41ecd1b91e3f30a34bbd91f593aacdb5e0b2fd8ac302e31342e312f322f302f637878782f"
    )


def test_retrieve_mining_info_from_payload():
    payload = "b9b5220500000000d7ab55270200000000002220cdcb53d7708f03ffa58c989ad41ecd1b91e3f30a34bbd91f593aacdb5e0b2fd8ac302e31342e312f322f302f637878782f"
    miner_info, mining_address = retrieve_miner_info_from_payload(payload)
    assert mining_address == "kaspa:qrxuk57hwz8s8la93jvf44q7e5derclnpg6thkgltya2ek67pvhasz43zf6ys"
    assert miner_info == "0.14.1/2/0/cxxx/"


def test_retrieve_mining_info_from_payload_ecdsa():
    payload = "7b23e204000000005f2bda6a0200000000002321036441a8148e58123d99bf62777c35a4c7eab682fda9764e7b8047a94c0de014d5ab302e31322e31342f6f6b6d696e6572"
    miner_info, mining_address = retrieve_miner_info_from_payload(payload)
    assert mining_address == "kaspa:qypkgsdgzj89sy3anxlkyamuxkjv064kst76jajw0wqy022vphspf4gxj4qr5m5"
    assert miner_info == "0.12.14/okminer"

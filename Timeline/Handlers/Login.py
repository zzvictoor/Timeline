"""Login handlers for Timeline AS2/AS3 clients."""

import logging
import os
from pathlib import Path

from twisted.internet.defer import inlineCallbacks, returnValue

from Timeline import Nickname, Password, Username
from Timeline.Database.DB import Friend, Penguin
from Timeline.Server.Constants import (
    AS2_PROTOCOL,
    AS3_PROTOCOL,
    CROSS_PROTOCOL,
    LOGIN_SERVER,
    TIMELINE_LOGGER,
    WORLD_SERVER,
)
from Timeline.Utils.Events import PacketEventHandler

logger = logging.getLogger(TIMELINE_LOGGER)

firebase_admin = None
auth = None
credentials = None
FIREBASE_INIT = False
FIREBASE_APP = None

try:
    import firebase_admin
    from firebase_admin import auth, credentials
except ImportError:
    logger.info("Firebase login disabled (firebase-admin not installed)")
else:
    try:
        try:
            FIREBASE_APP = firebase_admin.get_app()
            FIREBASE_INIT = True
        except ValueError:
            credential_path = os.getenv("FIREBASE_CREDENTIAL_PATH", "").strip()
            if credential_path and Path(credential_path).is_file():
                cred = credentials.Certificate(credential_path)
                FIREBASE_APP = firebase_admin.initialize_app(cred)
                FIREBASE_INIT = True

        if FIREBASE_INIT:
            logger.info("Firebase login enabled")
        else:
            logger.info("Firebase login disabled (no credential configured)")
    except Exception as exc:
        logger.warning("Firebase login disabled: %s", exc)


@PacketEventHandler.onXML("verChk", LOGIN_SERVER)
@PacketEventHandler.onXML("verChk", WORLD_SERVER)
@PacketEventHandler.onXML("verChk", WORLD_SERVER, server_protocol=CROSS_PROTOCOL)
@PacketEventHandler.onXML("verChk", LOGIN_SERVER, server_protocol=CROSS_PROTOCOL)
@PacketEventHandler.onXML_AS2("verChk", LOGIN_SERVER)
@PacketEventHandler.onXML_AS2("verChk", WORLD_SERVER)
def APIVersionCheck(client, version):
    if version != 153:
        client.send(
            client.PacketHandler.buildXML(
                {"msg": {"t": "sys", "body": {"action": "apiKO", "r": "0"}}}
            )
        )
        return client.disconnect()

    client.send(
        client.PacketHandler.buildXML(
            {"msg": {"t": "sys", "body": {"action": "apiOK", "r": "0"}}}
        )
    )
    if client.handshakeStage < 1:
        client.handshakeStage = 1


@PacketEventHandler.onXML("rndK", LOGIN_SERVER, p_r=False)
@PacketEventHandler.onXML("rndK", WORLD_SERVER, p_r=False)
@PacketEventHandler.onXML("rndK", WORLD_SERVER, server_protocol=CROSS_PROTOCOL, p_r=False)
@PacketEventHandler.onXML("rndK", LOGIN_SERVER, server_protocol=CROSS_PROTOCOL, p_r=False)
@PacketEventHandler.onXML_AS2("rndK", LOGIN_SERVER, p_r=False)
@PacketEventHandler.onXML_AS2("rndK", WORLD_SERVER, p_r=False)
def GetPenguinRandomKey(client, body):
    client.send(
        client.PacketHandler.buildXML(
            {
                "msg": {
                    "t": "sys",
                    "body": {
                        "action": "rndK",
                        "r": "-1",
                        "k": [client.CryptoHandler.randomKey],
                    },
                }
            }
        )
    )


@PacketEventHandler.onXML("login", LOGIN_SERVER, server_protocol=CROSS_PROTOCOL)
@inlineCallbacks
def HandleCrossLoginServer(client, user, passd):
    exists = yield client.db_penguinExists("username", user)

    if user == "$fire":
        client.Protocol = AS3_PROTOCOL
        client.CryptoHandler.salt = "a1ebe00441f5aecb185d0ec178ca2305Y(02.>'H}t\":E1_root"
        result = yield HandlePrimaryPenguinLogin(client, user, passd)
        returnValue(result)

    if not exists:
        client.send("e", 101)
        returnValue(client.disconnect())

    client.penguin.username = user
    yield client.db_init()
    client.penguin.password = client.dbpenguin.password.upper()

    client.Protocol = AS2_PROTOCOL
    client.CryptoHandler.salt = "Y(02.>'H}t\":E1"

    if not client.checkPassword(passd):
        client.Protocol = AS3_PROTOCOL
        client.CryptoHandler.salt = "a1ebe00441f5aecb185d0ec178ca2305Y(02.>'H}t\":E1_root"

    result = yield HandlePrimaryPenguinLogin(client, user, passd)
    returnValue(result)


@PacketEventHandler.onXML("login", WORLD_SERVER, server_protocol=CROSS_PROTOCOL)
def HandleCrossWorldLogin(client, isAS3, *args, **kwargs):
    client.Protocol = AS3_PROTOCOL if isAS3 else AS2_PROTOCOL
    handler = HandleWorldPenguinLogin if isAS3 else HandleWorldPenguinLoginAS2
    return handler(client, *args, **kwargs)


@PacketEventHandler.onXML("login", LOGIN_SERVER)
@PacketEventHandler.onXML_AS2("login", LOGIN_SERVER)
@inlineCallbacks
def HandlePrimaryPenguinLogin(client, user, passd):
    user_data = None

    if user == "$fire" and FIREBASE_INIT:
        try:
            token_data = auth.verify_id_token(passd, check_revoked=True)
            user_data = auth.get_user(token_data["uid"])
            client.penguin.firebase_user = user_data
            exists = True
        except Exception as exc:
            logger.warning("Firebase token rejected: %s", exc)
            client.send("e", 101)
            returnValue(client.disconnect())
    else:
        exists = yield client.db_penguinExists("username", user)

    if not exists:
        client.send("e", 101)
        returnValue(client.disconnect())

    if user == "$fire" and FIREBASE_INIT:
        claims = user_data.custom_claims or {}
        client.penguin.swid = claims.get("swid")
        if not client.penguin.swid:
            client.send("e", 101)
            returnValue(client.disconnect())
    else:
        client.penguin.username = user

    yield client.db_init()
    client.penguin.username = Username(client.dbpenguin.username, client)
    client.penguin.password = Password(client.dbpenguin.password, client)

    firebase_account = client["password"] == "firebase"
    if (firebase_account and user != "$fire") or (
        not client.checkPassword(passd) and (user != "$fire" or not FIREBASE_INIT)
    ):
        client.send("e", 101)
        returnValue(client.disconnect())

    client.penguin.id = client.dbpenguin.id
    if (yield client.banned()):
        returnValue(0)

    client.penguin.swid = client.dbpenguin.swid
    key = client.CryptoHandler.confirmHash()
    confh = client.CryptoHandler.bcrypt(key)
    fkey = client.CryptoHandler.md5(key)

    yield client.engine.redis.server.set(
        "conf:{}".format(client.dbpenguin.id), key, 15 * 60
    )

    worlds = []
    world_data, world_users = yield client.engine.redis.getWorldServers()
    for world_id, details in world_data.items():
        maximum = max(int(details["max"]), 1)
        bars = int(int(details["population"]) * 5 / maximum)
        worlds.append("{},{}".format(world_id, bars))
    world_string = "|".join(worlds)

    if client.Protocol == AS3_PROTOCOL:
        avatar = yield client.dbpenguin.avatar.get()
        language = avatar.language if avatar is not None else 45
        player_data = "{}|{}|{}|{}|NULL|{}|2".format(
            client.dbpenguin.id,
            client.dbpenguin.swid,
            client.dbpenguin.nickname,
            client.CryptoHandler.bcrypt(key),
            language,
        )

        email = str(client.dbpenguin.email or "")
        if "@" in email:
            local, domain = email.split("@", 1)
            masked_email = (local[:1] or "*") + "***@" + domain
        else:
            masked_email = "***"

        login_data = [player_data, confh, fkey, world_string, masked_email]
        preactivate_data = client.activationStatus()
        if preactivate_data is not None:
            login_data.append(preactivate_data)
        client.send("l", *login_data)

    elif client.Protocol == AS2_PROTOCOL:
        friends_db = yield Friend.find(where=["penguin_id = ?", client.dbpenguin.swid])
        friends = set(friend.friend for friend in friends_db)
        worlds_with_friends = [
            str(world_id)
            for world_id, users in world_users.items()
            if len(users) != len(users - friends)
        ]
        client.send(
            "l",
            client.dbpenguin.id,
            confh,
            "|".join(worlds_with_friends),
            world_string,
        )

    returnValue(client.disconnect())


@PacketEventHandler.onXML_AS2("login", WORLD_SERVER)
@inlineCallbacks
def HandleWorldPenguinLoginAS2(client, user, confirmHash, loginkey):
    exists = yield client.db_penguinExists("username", user)
    if not exists:
        client.send("e", 101)
        returnValue(client.disconnect())

    penguin = yield client.db_getPenguin("username = ?", user)
    yield HandleWorldPenguinLogin(
        client,
        penguin.nickname,
        penguin.id,
        penguin.swid,
        confirmHash,
        confirmHash,
        loginkey + confirmHash,
    )


@PacketEventHandler.onXML("login", WORLD_SERVER)
@inlineCallbacks
def HandleWorldPenguinLogin(client, nickname, _id, swid, password, confirmHash, loginkey):
    exists = yield client.db_penguinExists(value=_id)
    if not exists:
        client.send("e", 101)
        returnValue(client.disconnect())

    client.penguin.nickname = Nickname(nickname, client)
    client.penguin.password = password
    client.penguin.id = _id
    client.penguin.swid = swid

    yield client.db_init()
    client.penguin.username = Username(client.dbpenguin.username, client)
    if client.dbpenguin.swid != swid or client.dbpenguin.nickname != nickname:
        client.send("e", 101)
        returnValue(client.disconnect())

    if (yield client.banned()):
        returnValue(0)

    logger.debug("Redis ping: %s", (yield client.engine.redis.server.ping()))

    if (yield client.engine.redis.isPenguinLoggedIn(client.penguin.id)):
        client.send("e", 3)
        returnValue(client.disconnect())

    details = yield client.engine.redis.server.get(
        "conf:{}".format(client.dbpenguin.id)
    )
    if not details:
        client.send("e", 101)
        returnValue(client.disconnect())

    if (
        not client.CryptoHandler.bcheck(details, loginkey[32:])
        or not client.CryptoHandler.bcheck(details, confirmHash)
        or not client.CryptoHandler.bcheck(details, password)
    ):
        client.send("e", 101)
        returnValue(client.disconnect())

    yield client.engine.redis.server.delete("conf:{}".format(client.penguin.id))
    yield client.engine.redis.server.hmset(
        "online:{}".format(client.penguin.id),
        {
            "server": client.engine.id,
            "place": 0,
            "playing": 0,
            "waddling": 0,
            "joined": 0,
        },
    )

    client.ReceivePacketEnabled = True
    client.send("l", "timeline")


def init():
    logger.debug("Login Server::Login initiated!")
    logger.debug("World Server::Login initiated!")

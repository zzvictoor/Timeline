"""Timeline AS2/AS3 client protocol implementation."""

from math import ceil
import datetime as dt
import logging
import time
import weakref

from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.protocols.basic import LineReceiver
from twisted.protocols.policies import TimeoutMixin

from Timeline import Age, Cache, EPFAgent, Nickname
from Timeline.Database.DB import Coin, Inventory, PenguinDB
from Timeline.Server.Constants import (
    AS2_PROTOCOL,
    AS3_PROTOCOL,
    PACKET_DELIMITER,
    PACKET_TYPE,
    TIMELINE_LOGGER,
    WORLD_SERVER,
)
from Timeline.Server.Packets import PacketHandler
from Timeline.Utils.Cryptography import Crypto
from Timeline.Utils.Currency import CurrencyHandler
from Timeline.Utils.Events import GeneralEvent
from Timeline.Utils.Ninja import NinjaHandler
from Timeline.Utils.Plugins.Abstract import ExtensibleObject
from Timeline.Utils.Refresh import PenguinObject
from Timeline.Utils.Refresh.Refresh import Refresh


class LR(LineReceiver, TimeoutMixin):
    def makeConnection(self, transport):
        pass

    def connectionLost(self, reason):
        pass

    def lineReceived(self, line):
        pass

    def send(*args):
        pass


class Penguin(PenguinDB, ExtensibleObject, LR):
    """AS2 + AS3 protocol implementation."""

    delimiter = b"\x00"
    TIMEOUT = 70

    def __init__(self, engine):
        super(Penguin, self).__init__()
        self.Protocol = engine.server_protocol
        self.factory = self.engine = engine
        self.logger = logging.getLogger(TIMELINE_LOGGER)
        self.cleanConnectionLost = Deferred()
        self.errored = None
        self.buildPenguin()

    def __del__(self):
        try:
            self.logger.debug(
                "Discarding Penguin<%s> Object: %s : %s",
                self.engine.server_protocol,
                str(self.client),
                self.getPortableName(),
            )
        except Exception:
            pass

    def buildPenguin(self):
        self.handshakeStage = -1
        self.canRecvPacket = False
        self.ReceivePacketEnabled = True
        self.ignorableXTPackets = [
            ("s", "j#js", 1),
            ("s", "p#getdigcooldown", 0),
            ("s", "u#h", 0),
            ("s", "f#epfgf", 0),
            ("l", "login", 1),
        ]

        self.penguin = PenguinObject()
        self.penguin.name = None
        self.penguin.id = None
        self.penguin.room = None
        self.penguin.prevRooms = []
        self.ref = weakref.proxy(self)

        self.PacketHandler = PacketHandler(self.ref)
        self.CryptoHandler = Crypto(self.ref)

    def initialize(self):
        self.penguin.nickname = Nickname(self.dbpenguin.nickname, self.ref)
        self.penguin.swid = self.dbpenguin.swid
        self.penguin.epf = EPFAgent(
            self.dbpenguin.agent, str(self.dbpenguin.epf), self.ref
        )
        self.penguin.RefreshHandler = Refresh(self.ref)
        self.penguin.moderator = int(self.dbpenguin.moderator)
        self.penguin.stealth_mode = self["moderator"] == 2
        self.penguin.mascot_mode = self["moderator"] == 3
        self.penguin.x = self.penguin.y = self.penguin.frame = 0
        self.penguin.age = Age(self.dbpenguin.create, self.ref)
        self.penguin.muted = False
        self.penguin.cache = Cache(self.ref)
        self.penguin.ninjaHandler = NinjaHandler(self.ref)
        self.penguin.currencyHandler = CurrencyHandler(self.ref)
        self.engine.musicHandler.init(self.ref)
        GeneralEvent("onBuildClient", self.ref)

    def checkPassword(self, password):
        return self.CryptoHandler.loginHash() == password

    def activationStatus(self):
        activation_data = self.dbpenguin.hash or ""
        activation_pending = ";" in activation_data
        if not activation_pending:
            return None

        expires = self.dbpenguin.create + dt.timedelta(days=7)
        expired = dt.datetime.now() > expires
        hours_left = ceil(((expires - dt.datetime.now()).total_seconds()) / 3600)

        if expired:
            self.send("loginMustActivate", 0, None, None, self.dbpenguin.email)
            self.disconnect()

        return "{}|7|{}".format(hours_left, hours_left)

    @inlineCallbacks
    def banned(self):
        bans = yield self.dbpenguin.bans.get(
            where=["expire > CURRENT_TIMESTAMP"], limit=1
        )
        if bans is None:
            returnValue(False)

        now = int(time.time())
        expire = int(time.mktime(bans.expire.timetuple()))
        hours = (expire - now) / (60 * 60.0)

        if 0 < hours < 1:
            self.send("e", 602, int(hours * 60))
            returnValue(True)
        if hours <= 0:
            returnValue(False)

        self.send("e", 601, int(hours))
        self.disconnect()
        returnValue(True)

    def handleCrossDomainPolicy(self):
        self.send(
            "<cross-domain-policy><allow-access-from domain='*' to-ports='{}' />"
            "</cross-domain-policy>".format(self.engine.port)
        )

    def getPortableName(self):
        if self["username"] is None and self["id"] is None:
            return "{}, {}".format(repr(self.client), self.Protocol)
        if self["username"] is not None:
            return "{}, {}".format(self["username"], self.Protocol)
        if self["id"] is not None:
            return "{}, {}".format(self["id"], self.Protocol)
        return "{}, {}".format(self["username"], self.Protocol)

    @inlineCallbacks
    def addItem(self, item, comment="Added via catalog"):
        if isinstance(item, int):
            item = self.engine.itemCrumbs[item]
        elif isinstance(item, str):
            try:
                item = self.engine.itemCrumbs[int(item)]
            except (TypeError, ValueError, KeyError):
                item = None

        if item is None:
            returnValue(False)

        cost = item.cost
        if int(self.penguin.coins) < cost:
            self.send("e", 401)
            returnValue(False)
        if self["RefreshHandler"].inInventory(item):
            returnValue(False)

        yield Inventory(
            penguin_id=self["id"], item=int(item), comments=comment
        ).save()
        yield Coin(
            penguin_id=self["id"],
            transaction=-cost,
            comment="Money spent on adding item ({}). Item: {}".format(
                comment, int(item)
            ),
        ).save()
        self.penguin.coins -= cost
        returnValue(True)

    def __str__(self):
        walking_id = walking_item = walking_type = walking_subtype = ""
        walking_state = 0

        if self["walkingPuffle"] is not None:
            puffle = self["walkingPuffle"]
            walking_id = int(puffle.id)
            walking_item = int(puffle.hat)
            walking_type = int(puffle.type)
            walking_subtype = int(puffle.subtype)
            walking_state = int(puffle.state)

        data = [
            self["id"],
            self["nickname"],
            self["language"],
            self["data"].avatar.color,
            self["data"].avatar.head,
            self["data"].avatar.face,
            self["data"].avatar.neck,
            self["data"].avatar.body,
            self["data"].avatar.hand,
            self["data"].avatar.feet,
            self["data"].avatar.pin,
            self["data"].avatar.photo,
            self["x"],
            self["y"],
            self["frame"],
            self["member"].enum,
            int(self["member"]),
            self["data"].avatar.avatar,
            None,
            None,
            walking_id,
            walking_type,
            walking_subtype,
            walking_item,
            walking_state,
        ][:-8 if self.Protocol == AS2_PROTOCOL else None]
        return "|".join(map(str, data))

    def __getitem__(self, prop):
        return getattr(self.penguin, prop)

    def __setitem__(self, prop, val):
        setattr(self.penguin, prop, val)

    def checkForExceptions(self, err):
        self.errored = err
        self.engine.log("error", self.getPortableName(), err.getErrorMessage())

    def lineReceived(self, line):
        self.resetTimeout()
        try:
            super(Penguin, self).lineReceived(line)
        except NotImplementedError:
            return

        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")

        received = self.PacketHandler.handlePacketReceived(line)
        received.addErrback(self.checkForExceptions)

    @staticmethod
    def _wire(value):
        if isinstance(value, bytes):
            return value
        return str(value).encode("utf-8")

    def send(self, *args):
        super(Penguin, self).send(*args)
        buffers = list(args)
        if not buffers:
            return None

        if len(buffers) == 1:
            self.engine.log("debug", "[SEND]", self.getPortableName(), buffers[0])
            return self.sendLine(self._wire(buffers[0]))

        server_internal_id = "-1"
        if self.penguin.room is not None:
            server_internal_id = int(self.penguin.room)

        buffering = ["", PACKET_TYPE, buffers[0], server_internal_id]
        buffering += buffers[1:]
        buffering.append("")
        packet = PACKET_DELIMITER.join(map(str, buffering))
        self.engine.log("debug", "[SEND]", self.getPortableName(), packet)
        return self.sendLine(self._wire(packet))

    def log(self, level, *args):
        self.engine.log(level, self.getPortableName(), *args)

    def disconnect(self):
        self.transport.loseConnection()

    @inlineCallbacks
    def connectionLost(self, reason):
        super(Penguin, self).connectionLost(reason)
        self.penguin.connectionLost = True

        if self.engine.type == WORLD_SERVER and self.penguin.id is not None:
            if self["RefreshHandler"] is not None:
                loop = self["RefreshHandler"].RefreshManagerLoop
                if loop.running:
                    loop.stop()
                yield self.engine.redis.server.srem(
                    "users:{}".format(self.engine.id), self["swid"]
                )

            yield GeneralEvent("onClientDisconnect", self.ref)
            if self["RefreshHandler"] is not None:
                del self.penguin.RefreshHandler

        if self.engine.redis.server is not None:
            yield self.engine.redis.server.delete("online:{}".format(self["id"]))
        yield self.engine.disconnect(self)

        if not self.cleanConnectionLost.called:
            self.cleanConnectionLost.callback(True)

    def makeConnection(self, transport):
        self.transport = transport
        self.client = transport
        self.connectionMade = True
        self.send(
            "<cross-domain-policy><allow-access-from domain='*' to-ports='{}' />"
            "</cross-domain-policy>".format(self.engine.port)
        )
        self.setTimeout(self.TIMEOUT)

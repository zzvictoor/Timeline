"""Timeline Twisted server engine."""

from collections import deque
import logging
import weakref

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.protocol import Factory, Protocol

from Timeline.Server.Constants import AS3_PROTOCOL, TIMELINE_LOGGER, WORLD_SERVER
from Timeline.Server.Music import MusicTrackEngine
from Timeline.Server.Redis import Redis
from Timeline.Server.Room import RoomHandler
from Timeline.Utils.Crumbs import Avatars, Cards, Igloo, Items, Postcards, Puffle, Stamps
from Timeline.Utils.Events import GeneralEvent
from Timeline.Utils.Plugins.Abstract import ExtensibleObject


class AClient(Protocol):
    def makeConnection(self, transport):
        # Twisted transports require bytes on Python 3.
        transport.write(b"%xt%e%-1%211%\x00")
        transport.pauseProducing()
        transport.loseConnection()


class Engine(Factory, ExtensibleObject):
    """Main Timeline TCP factory."""

    def __init__(
        self,
        protocol,
        _type,
        _id,
        name="World Server 1",
        _max=300,
        server_protocol=AS3_PROTOCOL,
    ):
        self.protocol = protocol
        self.server_protocol = server_protocol
        self.type = _type
        self.id = _id
        self.logger = logging.getLogger(TIMELINE_LOGGER)
        self.name = name
        self.users = deque()
        self.dbDetails = {}
        self.maximum = _max - 1
        self._listening = False
        self._portListener = None
        self.proxyReference = weakref.proxy(self)

        self.redis = Redis(self)

        self.log("info", "Timeline Factory Started!")
        self.log("info", "Running:", self.name)
        self.log("info", "Maximum users:", self.maximum)

        if self.type == WORLD_SERVER:
            self.initializeWorld()

        self.redis.redisConnectionDefer.addCallback(
            lambda *_args: GeneralEvent("onEngine", self)
        )

    def initializeWorld(self):
        self.itemCrumbs = Items.PaperItems(self)
        self.roomHandler = RoomHandler(self)
        self.postcardHandler = Postcards.PostcardHandler(self)
        self.iglooCrumbs = Igloo.IglooHandler(self)
        self.puffleCrumbs = Puffle.PuffleCrumbHandler(self)
        self.stampCrumbs = Stamps.StampHandler(self)
        self.cardCrumbs = Cards.CardsHandler(self)
        self.musicHandler = MusicTrackEngine(self)
        self.avatarHandler = Avatars.AvatarHandler(self)

    def __repr__(self):
        return "{}<{}:{}#{}>".format(
            self.name, self.server_protocol, self.id, len(self.users)
        )

    def getPenguinById(self, _id):
        _id = int(_id)
        for peng in list(self.users):
            if peng["id"] == _id:
                return peng.ref
        return None

    def run(self, ip, port):
        if self._listening:
            raise RuntimeError("{} is already listening".format(self))

        self.ip, self.port = ip, int(port)
        self._portListener = reactor.listenTCP(self.port, self, interface=ip)
        self.log("info", self.name, "listening on", "{}:{}".format(ip, port))
        self._listening = True

    @inlineCallbacks
    def disconnect(self, client):
        GeneralEvent("onClientRemove", client.ref)

        if client in self.users:
            self.users.remove(client)
            if self.redis.server is not None:
                yield self.redis.server.hmset(
                    "server:{}".format(self.id), {"population": len(self.users)}
                )
            return True
        return False

    def buildProtocol(self, address):
        if len(self.users) > self.maximum:
            protocol = AClient()
            protocol.factory = self
            self.log("warning", "Client count overload, disposing it!")
            return protocol

        user = self.protocol(self)
        self.log("info", "Built new protocol for user#{}".format(len(self.users)))
        self.users.append(user)

        if self.redis.server is not None:
            self.redis.server.hmset(
                "server:{}".format(self.id), {"population": len(self.users)}
            )
        return user

    def log(self, level, *args):
        message = " ".join(str(arg) for arg in args)
        message = "[{}:{}] {}".format(self.type, self.name, message)

        if level == "info":
            self.logger.info(message)
        elif level in ("warn", "warning"):
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        else:
            self.logger.debug(message)

    @inlineCallbacks
    def connectionLost(self, reason):
        self.log("warning", "Server exiting! reason:", reason)

        for user in list(self.users):
            self.users.remove(user)
            user.canRecvPacket = user.ReceivePacketEnabled = False
            user.disconnect()
            yield user.cleanConnectionLost

        if self.redis.server is not None:
            yield self.redis.server.hmset(
                "server:{}".format(self.id), {"population": 0}
            )
        return True

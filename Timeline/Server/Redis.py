"""Timeline Redis-backed runtime state."""

import json
import os

import txredisapi as redis
from twisted.internet.defer import inlineCallbacks, returnValue

from Timeline.Server.Constants import LOGIN_SERVER, WORLD_SERVER


class Redis(object):
    def __init__(self, engine):
        self.engine = engine
        self.server = None

        host = os.getenv("REDIS_HOST", "127.0.0.1")
        port = int(os.getenv("REDIS_PORT", "6379"))
        dbid = int(os.getenv("REDIS_DB", "0"))

        self.redisConnectionDefer = redis.ConnectionPool(
            host=host,
            port=port,
            dbid=dbid,
            reconnect=True,
            charset="utf-8",
        )
        self.redisConnectionDefer.addCallback(self.initPenguins)

    @inlineCallbacks
    def initPenguins(self, pool):
        self.server = pool
        self.log("info", "Setting Redis data...")

        if self.engine.type == WORLD_SERVER:
            name = "server:{0}".format(self.engine.id)
            yield self.server.hmset(
                name,
                {
                    "name": self.engine.name,
                    "max": self.engine.maximum,
                    "population": 0,
                },
            )
            yield self.server.sadd("servers", self.engine.id)

        self.log("info", "Redis runtime state ready")
        returnValue(pool)

    @inlineCallbacks
    def getWorldServers(self):
        servers = yield self.server.smembers("servers")
        data = {}
        users = {}

        for sid in servers:
            data[sid] = yield self.server.hgetall("server:{0}".format(sid))
            users[sid] = set(
                (yield self.server.smembers("users:{}".format(sid)))
            )

        returnValue([data, users])

    @inlineCallbacks
    def isPenguinLoggedIn(self, peng_id):
        exists = yield self.server.exists("online:{0}".format(peng_id))
        returnValue(bool(exists))

    @inlineCallbacks
    def isPenguinOnlineOnServer(self, peng, server):
        logged_in = yield self.isPenguinLoggedIn(peng)
        if not logged_in:
            returnValue(False)

        online = yield self.server.hgetall("online:{}".format(peng))
        returnValue(str(online["server"]) == str(server))

    @inlineCallbacks
    def getPlayerKey(self, pid):
        key = yield self.server.get("conf:{}".format(pid))
        returnValue(key)

    def log(self, level, *args):
        self.engine.log(level, "(Redis)", *args)

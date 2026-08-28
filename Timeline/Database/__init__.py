"""Timeline database registry and validation helpers."""

from collections import deque
import logging

from twistar.registry import Registry
from twistar.dbconfig.mysql import ReconnectingMySQLConnectionPool

from Timeline.Database.DB import (
    Asset,
    Avatar,
    Ban,
    CareItem,
    Coin,
    Currency,
    Friend,
    Igloo,
    IglooFurniture,
    IglooLike,
    Ignore,
    Inventory,
    Mail,
    Membership,
    MusicTrack,
    Ninja,
    Penguin,
    Puffle,
    Request,
    Stamp,
    StampCover,
)
from Timeline.Server.Constants import TIMELINE_LOGGER


class DBManagement(object):
    def __init__(self, user, passd, db, host="127.0.0.1", port=3306):
        self.db_data = (user, db)
        self.host = host
        self.port = int(port)
        self.logger = logging.getLogger(TIMELINE_LOGGER)
        self.conn = False

        if self.setupRegistry(passd):
            self.logger.info(
                "MySQL database pool setup successfully @ %s:%s/%s",
                self.host,
                self.port,
                db,
            )
        else:
            self.logger.error("Unable to setup MySQL pool")

    def setupRegistry(self, passd):
        user, db = self.db_data
        self.logger.info("Starting MySQL DB pool @ %s:%s/%s", self.host, self.port, db)
        try:
            Registry.register(
                Penguin,
                Igloo,
                Avatar,
                Currency,
                Ninja,
                Asset,
                Ban,
                CareItem,
                Friend,
                Request,
                Ignore,
                Inventory,
                Mail,
                Membership,
                MusicTrack,
                Puffle,
                Stamp,
                StampCover,
                Coin,
            )
            Registry.register(Igloo, IglooFurniture, IglooLike)

            Registry.DBPOOL = ReconnectingMySQLConnectionPool(
                "MySQLdb",
                host=self.host,
                port=self.port,
                user=user,
                passwd=passd,
                db=db,
                charset="utf8mb4",
                use_unicode=True,
                cp_reconnect=True,
            )
            self.conn = True
        except Exception as exc:
            self.logger.exception("Unable to start MySQL pool: %s", exc)
            self.conn = False

        return self.conn


def validateNickname(peng):
    peng.nickname = peng.nickname.strip()
    nickname = peng.nickname
    compact = nickname.replace(" ", "")

    if len(nickname) > 20:
        peng.errors.add("nickname", "Nickname should be less than 21 characters")

    if not compact.isalnum():
        peng.errors.add("nickname", "Nickname should be alpha numeric")


def validateInventory(peng):
    peng.inventory = peng.inventory.strip("%")


Penguin.addValidator(validateNickname)

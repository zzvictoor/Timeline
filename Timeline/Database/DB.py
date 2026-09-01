"""Timeline database models backed by Twistar."""

import json
import logging
import time

from twisted.internet.defer import inlineCallbacks, returnValue
from twistar.dbobject import DBObject
from twistar.registry import Registry

from Timeline.Server.Constants import TIMELINE_LOGGER


class Penguin(DBObject):
    HASONE = ["avatar", "currency", "ninja"]
    HASMANY = [
        "assets",
        "bans",
        "careItems",
        "coins",
        "friends",
        "ignores",
        "requests",
        "inventories",
        "mails",
        "memberships",
        "musicTracks",
        "puffles",
        "stamps",
        "stampCovers",
        "igloos",
    ]


class Coin(DBObject):
    pass


class Igloo(DBObject):
    HASMANY = ["iglooFurnitures", "iglooLikes"]

    @inlineCallbacks
    def get_likes_count(self):
        likes = yield Registry.getConfig().execute(
            "SELECT COALESCE(SUM(likes), 0) FROM igloo_likes WHERE igloo_id = %s"
            % self.id
        )
        returnValue(likes[0][0])

    @inlineCallbacks
    def get_furnitures(self):
        furnitures = yield self.iglooFurnitures.get()
        returnValue(furnitures)

    @inlineCallbacks
    def get_furnitures_string(self):
        furnitures = yield self.get_furnitures()
        data = []
        for item in furnitures:
            values = [item.furn_id, item.x, item.y, item.rotate, item.frame]
            data.append("|".join(map(str, map(int, values))))
        returnValue(",".join(data))

    @inlineCallbacks
    def updateFurnitures(self, furnitures):
        yield self.refresh()
        yield IglooFurniture.deleteAll(where=["igloo_id = ?", self.id])

        objects = [
            IglooFurniture(
                igloo_id=self.id,
                furn_id=value[0],
                x=value[1],
                y=value[2],
                rotate=value[3],
                frame=value[4],
            )
            for value in furnitures
        ]
        for furniture in objects:
            yield furniture.save()
        yield self.iglooFurnitures.set(objects)


class IglooFurniture(DBObject):
    pass


class IglooLike(DBObject):
    def get_time(self):
        return int(time.mktime(self.time.timetuple()))


class Avatar(DBObject):
    pass


class Currency(DBObject):
    pass


class Ninja(DBObject):
    pass


class Asset(DBObject):
    def getPurchasedTimestamp(self):
        return int(time.mktime(self.purchased.timetuple()))


class Ban(DBObject):
    def banned(self):
        return self.hours() > 0

    def hours(self):
        expire = int(time.mktime(self.expire.timetuple()))
        return (expire - time.time()) / (60 * 60.0) if expire > time.time() else 0


class CareItem(DBObject):
    pass


class Friend(DBObject):
    friend_id = -1


class Ignore(DBObject):
    pass


class Request(DBObject):
    pass


class Inventory(DBObject):
    pass


class Mail(DBObject):
    def get_sent_on(self):
        return int(time.mktime(self.sent_on.timetuple()))


class Membership(DBObject):
    pass


class MusicTrack(DBObject):
    shared = False

    def __len__(self):
        return self.length

    def __str__(self, withNotes=False):
        if not withNotes:
            return "|".join(map(str, [self.id, self.name, int(self.shared), self.likes]))
        return "%".join(
            map(str, [self.id, self.name, int(self.shared), self.notes, self.hash, self.likes])
        )

    def __int__(self):
        return self.id


class Puffle(DBObject):
    state = x = y = 0

    def __str__(self):
        return "|".join(
            map(
                str,
                [
                    int(self.id),
                    int(self.type),
                    self.subtype if int(self.subtype) != 0 else "",
                    self.name,
                    self.adopt(),
                    int(self.food),
                    int(self.play),
                    int(self.rest),
                    int(self.clean),
                    int(self.hat),
                    int(self.x),
                    int(self.y),
                    int(self.walking),
                ],
            )
        )

    def adopt(self):
        return int(time.mktime(self.adopted.timetuple()))

    def updatePuffleStats(self, engine):
        care_history = json.loads(self.lastcare) if self.lastcare else {}
        if not isinstance(care_history, dict):
            care_history = {}

        now = time.time()
        if len(care_history) < 1 or bool(int(self.backyard)) or self.walking:
            care_history["food"] = care_history["play"] = care_history["bath"] = now
            self.lastcare = json.dumps(care_history)
            self.save()
            return

        last_fed = care_history["food"]
        last_played = care_history["play"]
        last_bathed = care_history["bath"]
        food, play, clean = int(self.food), int(self.play), int(self.clean)

        self.rest = 100
        self.save()

        fed_percent = food - 5 * ((now - last_fed) / 86400)
        play_percent = play - 5 * ((now - last_played) / 86400)
        clean_percent = clean - 10 * ((now - last_bathed) / 86400)
        total_percent = (fed_percent + play_percent + clean_percent) / 3.0

        if fed_percent < 3 or total_percent < 6:
            self.backyard = 1
            self.food = self.play = self.clean = 100
            self.save()
            return

        if fed_percent < 10:
            penguin_id = self.penguin_id
            puffle_name = self.name

            def send_mail(mail):
                if mail is not None:
                    sent = mail.get_sent_on()
                    if (time.time() - sent) / 3600 / 12 < 1:
                        return
                Mail(
                    penguin_id=penguin_id,
                    from_user=0,
                    type=110,
                    description=str(puffle_name),
                ).save()

            Mail.find(
                where=[
                    "penguin_id = ? AND type = 110 AND description = ?",
                    self.penguin_id,
                    self.name,
                ],
                orderby="sent_on DESC",
                limit=1,
            ).addCallback(send_mail)

        self.food = fed_percent
        self.play = play_percent
        self.clean = clean_percent
        care_history["food"] = care_history["play"] = care_history["bath"] = now
        self.lastcare = json.dumps(care_history)
        self.save()


class Stamp(DBObject):
    def __int__(self):
        return int(self.stamp)


class StampCover(DBObject):
    pass


class EPFCom(DBObject):
    TABLENAME = "epfcoms"

    def getTime(self):
        return int(time.mktime(self.time.timetuple()))

    def __str__(self):
        return "|".join(map(str, [self.message, self.getTime(), self.mascot]))


class PenguinDB(object):
    def __init__(self):
        self.logger = logging.getLogger(TIMELINE_LOGGER)
        self.dbpenguin = None

    @inlineCallbacks
    def db_init(self):
        if self.dbpenguin is None:
            column, value = "username", self.penguin.username
            if self.penguin.id is not None:
                column, value = "ID", self.penguin.id
            elif self.penguin.swid is not None:
                column, value = "swid", self.penguin.swid

            self.dbpenguin = yield Penguin.find(
                where=["{} = ?".format(column), value], limit=1
            )
            if self.dbpenguin is None:
                raise LookupError(
                    "[TE201] Penguin not found with {} - {}".format(column, value)
                )
        returnValue(True)

    @inlineCallbacks
    def db_nicknameUpdate(self, nick):
        previous = self.dbpenguin.nickname
        self.dbpenguin.nickname = nick
        saved = yield self.dbpenguin.save()

        errors = getattr(saved, "errors", None)
        if errors is not None and not errors.isEmpty():
            self.dbpenguin.nickname = previous
            self.log("error", "[TE200] MySQL nickname update failed")
            returnValue(False)
        returnValue(True)

    @inlineCallbacks
    def db_penguinExists(self, criteria="ID", value=None):
        exists = yield Penguin.exists(["`{}` = ?".format(criteria), value])
        returnValue(exists)

    @inlineCallbacks
    def db_getPenguin(self, criteria, *values):
        penguin = yield Penguin.find(where=[criteria] + list(values), limit=1)
        returnValue(penguin)

    @inlineCallbacks
    def db_refresh(self):
        yield self.dbpenguin.refresh()

"""Refresh diff handlers."""

import logging

from twisted.internet.defer import inlineCallbacks

from Timeline.Database.DB import IglooFurniture, Penguin
from Timeline.Handlers.AS2.Puffle import getAS2PuffleString
from Timeline.Server.Constants import AS3_PROTOCOL, TIMELINE_LOGGER
from Timeline.Utils.Refresh import PenguinObject


class RefreshHandler(object):
    def __init__(self):
        self.logger = logging.getLogger(TIMELINE_LOGGER)
        super(RefreshHandler, self).__init__()

    def handleInventory(self, itemAdded, itemRemoved, itemsOriginal):
        for item in itemAdded:
            self.penguin.send("ai", int(item.item), self.penguin["coins"])
        self.cache.inventories = list(itemsOriginal.union(itemAdded) - itemRemoved)

    @inlineCallbacks
    def handleAssets(self, assetAdded, assetRemoved, originalAssets):
        asset_type = {"i": "au", "f": "af", "l": "aloc", "fl": "ag"}
        for asset in assetAdded:
            self.penguin.send(
                asset_type[asset.type], int(asset.item), self.penguin["coins"]
            )

        self.cache.assets = list(originalAssets.union(assetAdded) - assetRemoved)
        for asset in self.cache.assets:
            if asset.type != "f":
                continue
            yield asset.refresh()
            furniture = self.penguin.engine.iglooCrumbs.getFurnitureById(asset.item)
            if furniture is not None and asset.quantity > furniture.max:
                asset.quantity = furniture.max
                yield asset.save()

    @inlineCallbacks
    def handleFriends(self, newFriends, friendRemoved, originalFriends):
        self.cache.friends = list(originalFriends.union(newFriends) - friendRemoved)

        for friend in newFriends:
            friend_obj = yield Penguin.find(
                where=["swid = ?", friend.friend], limit=1
            )
            if friend_obj is None:
                friend.delete()
                continue

            friend.friend_id = friend_obj.id
            presence = yield self.penguin.engine.redis.server.hmget(
                "online:{}".format(int(friend_obj.id)), ["place_name"]
            )
            friend_online = presence[0] if presence and presence[0] is not None else "N/A"
            if not self.penguin["moderator"] and friend_obj.moderator == 2:
                friend_online = "N/A"

            data = [
                int(friend_obj.id),
                friend_obj.nickname,
                friend_obj.swid,
                friend.bff,
                int(friend_online != "N/A"),
                friend_online,
            ]
            self.penguin.send("fb", "|".join(map(str, data)))

        for friend in friendRemoved:
            self.penguin.send("frf", friend.friend)

        for friend in self.cache.friends:
            friend_obj = yield Penguin.find(
                where=["swid = ?", friend.friend], limit=1
            )
            if friend_obj is None:
                friend.delete()
                continue

            presence = yield self.penguin.engine.redis.server.hmget(
                "online:{}".format(int(friend_obj.id)),
                ["place_name", "place", "world"],
            )
            friend_online, room_id, world_id = presence if presence else (None, None, None)
            if not self.penguin["moderator"] and friend_obj.moderator == 2:
                friend_online = None

            friend_online = friend_online if friend_online is not None else "N/A"
            friend.onlinePresence = {
                "online_status": friend_online != "N/A",
                "roomId": room_id,
                "worldId": world_id,
            }
            self.penguin.send(
                "fo",
                "|".join(
                    map(
                        str,
                        [
                            friend.friend,
                            room_id or 0,
                            friend_online,
                            friend_obj.id,
                            world_id or -1,
                        ],
                    )
                ),
            )

    @inlineCallbacks
    def handleRequests(self, newRequests, removedRequests, originalRequests):
        self.cache.requests = list(
            originalRequests.union(newRequests) - removedRequests
        )
        for request in newRequests:
            penguin = yield Penguin.find(
                where=["swid = ?", request.requested_by], limit=1
            )
            if penguin is not None:
                self.penguin.send("fn", penguin.nickname, penguin.swid)

    def handleIgnores(self, newIgnores, removedIgnores, originalIgnores):
        pass

    def handleStamps(self, stampAdded, stampRemoved, originalStamps):
        recent = self.penguin["recentStamps"] or []
        self.penguin.penguin.recentStamps = recent + list(stampAdded)
        for stamp in stampAdded:
            self.penguin.send("aabs", int(stamp.stamp))
        self.cache.stamps = list(originalStamps.union(stampAdded) - stampRemoved)

    def handleCareItems(self, itemAdded, itemRemoved, originalItems):
        for item in itemAdded:
            self.penguin.send(
                "papi", self.penguin["coins"], int(item.item), int(item.quantity)
            )
        self.cache.careItems = list(originalItems.union(itemAdded) - itemRemoved)

    @inlineCallbacks
    def handleMails(self, mailArrived, mailBurnt, originalMails):
        for mail in mailArrived:
            nickname = "Timeline Team"
            penguin = yield Penguin.find(mail.from_user)
            if penguin is not None:
                nickname = penguin.nickname
            self.penguin.send(
                "mr",
                nickname,
                int(mail.from_user),
                int(mail.type),
                mail.description,
                mail.get_sent_on(),
                int(mail.id),
                int(mail.opened),
            )

        self.cache.mails = list(originalMails.union(mailArrived) - mailBurnt)

        # Python 3 forbids yield inside comprehensions.
        refreshed = []
        for mail in self.cache.mails:
            yield mail.refresh()
            refreshed.append(mail)
        self.cache.mails = [mail for mail in refreshed if not mail.junk]

        if not self.cache.mails and originalMails:
            self.penguin.send("mdp", 0)

    def handleBans(self, newBans, unBans, bans):
        for ban in newBans:
            if ban.banned():
                self.penguin.send("e", ban.type, ban.hours())
                return self.penguin.disconnect()

    def handlePuffles(self, adoptedPuffles, puffleToWoods, puffleHostaged):
        for puffle in adoptedPuffles:
            serialized = (
                puffle
                if self.penguin.Protocol == AS3_PROTOCOL
                else getAS2PuffleString(self.penguin, [puffle])
            )
            self.penguin.send("pn", self.penguin["coins"], serialized)

        for puffle in puffleToWoods:
            self.penguin["igloo"].send("prp", int(puffle.id))
            self.penguin["igloo"].backyard.send("prp", int(puffle.id))

        self.cache.puffles = list(
            puffleHostaged.union(adoptedPuffles) - puffleToWoods
        )
        for puffle in self.cache.puffles:
            puffle.updatePuffleStats(self.penguin.engine)

    def handleStampCovers(self, coverAdded, coverRemoved, coverPresent):
        self.cache.stampCovers = list(
            coverPresent.union(coverAdded) - coverRemoved
        )
        for cover in self.cache.stampCovers[6:]:
            cover.delete()
        self.cache.stampCovers = self.cache.stampCovers[:6]

    @inlineCallbacks
    def handleIgloos(self):
        igloos = yield self.penguin.dbpenguin.igloos.get()
        igloo_config = {item.igloo.id: item for item in self.cache.igloos}

        for igloo in igloos:
            if igloo.id not in igloo_config:
                igloo_cache = PenguinObject()
                igloo_cache.igloo = igloo
                self.cache.igloos.append(igloo_cache)
            else:
                igloo_cache = igloo_config[igloo.id]

            igloo_cache.iglooFurnitures = yield igloo.iglooFurnitures.get()
            igloo_cache.iglooLikes = yield igloo.iglooLikes.get()

            remove_furns = tuple(
                item.id for item in igloo_cache.iglooFurnitures[99:]
            )
            if remove_furns:
                yield IglooFurniture.deleteAll(
                    where=["igloo_id = ? AND id in ?", igloo.id, remove_furns]
                )

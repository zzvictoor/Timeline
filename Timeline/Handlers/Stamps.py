"""Stamp book and stamp award handlers."""

from twisted.internet.defer import inlineCallbacks, returnValue

from Timeline.Database.DB import Coin, Penguin, Stamp, StampCover
from Timeline.Server.Constants import SERVER_ONLY_STAMP_GROUP, WORLD_SERVER
from Timeline.Utils.Events import GeneralEvent, PacketEventHandler


@PacketEventHandler.onXT("s", "st#gsbcd", WORLD_SERVER)
@PacketEventHandler.onXT_AS2("s", "st#gsbcd", WORLD_SERVER)
@inlineCallbacks
def handleGetSBCoverDetails(client, penguin_id):
    penguin = client.dbpenguin if penguin_id == client["id"] else (yield Penguin.find(penguin_id))
    if penguin is None:
        returnValue(client.send("gsbcd", "", "", "", "", "", ""))

    cover_items = yield penguin.stampCovers.get()
    serialized = [
        "{i.type}|{i.stamp}|{i.x}|{i.y}|{i.rotation}|{i.depth}".format(i=item)
        for item in cover_items
    ]
    client.send(
        "gsbcd",
        penguin.cover_color,
        penguin.cover_highlight,
        penguin.cover_pattern,
        penguin.cover_icon,
        *serialized
    )


@PacketEventHandler.onXT("s", "st#gps", WORLD_SERVER)
@PacketEventHandler.onXT_AS2("s", "st#gps", WORLD_SERVER)
@inlineCallbacks
def handleGetPlayerStamps(client, penguin_id):
    if penguin_id == client["id"]:
        penguin_stamps = client["data"].stamps
    else:
        penguin = yield Penguin.find(penguin_id)
        if penguin is None:
            penguin_stamps = []
        else:
            penguin_stamps = yield penguin.stamps.get()

    client.send("gps", penguin_id, "|".join(str(stamp.stamp) for stamp in penguin_stamps))


@PacketEventHandler.onXT("s", "st#gmres", WORLD_SERVER, p_r=False)
@PacketEventHandler.onXT_AS2("s", "st#gmres", WORLD_SERVER, p_r=False)
def handleGetRecentStamps(client, data):
    client.send("gmres", "|".join(map(str, client["recentStamps"])))
    client.penguin.recentStamps = []


@PacketEventHandler.onXT("s", "st#ssbcd", WORLD_SERVER)
@PacketEventHandler.onXT_AS2("s", "st#ssbcd", WORLD_SERVER)
@inlineCallbacks
def handleSBCoverUpdate(client, color, highlight, pattern, icon, stamps):
    cover_crumb = client.engine.stampCrumbs.cover

    if not client["member"]:
        returnValue(client.send("e", 999))

    if (
        color not in cover_crumb["colors"]
        or highlight not in cover_crumb["highlights"]
        or pattern not in cover_crumb["patterns"]
        or icon not in cover_crumb["icons"]
    ):
        returnValue(None)

    stamps_used = []
    stamps_earned = [item.stamp for item in client["data"].stamps]

    for stamp_config in stamps:
        item_type, item_id, x, y, rotation, depth = stamp_config
        stamp = client.engine.stampCrumbs[item_id]

        if stamp is None:
            item = client.engine.itemCrumbs[item_id]
            if item is None:
                returnValue(None)
            if not (item.type == 8 and client["RefreshHandler"].inInventory(int(item))):
                returnValue(None)
            stamp = item
        elif int(stamp) not in stamps_earned:
            returnValue(None)

        if item_id in stamps_used:
            returnValue(None)
        stamps_used.append(item_id)

    yield StampCover.deleteAll(where=["penguin_id=?", client["id"]])
    client.dbpenguin.cover_color = color
    client.dbpenguin.cover_highlight = highlight
    client.dbpenguin.cover_pattern = pattern
    client.dbpenguin.cover_icon = icon
    yield client.dbpenguin.save()

    stamp_covers = [
        StampCover(
            penguin_id=client["id"],
            type=value[0],
            stamp=value[1],
            x=value[2],
            y=value[3],
            rotation=value[4],
            depth=value[5],
        )
        for value in stamps
    ]
    for stamp_cover in stamp_covers:
        yield stamp_cover.save()

    client.send("ssbcd", "success")


@PacketEventHandler.onXT("s", "st#sse", WORLD_SERVER)
@PacketEventHandler.onXT_AS2("s", "st#sse", WORLD_SERVER)
@inlineCallbacks
def handleStampEarned(client, stamp_id, fromServer=False):
    stamp = client.engine.stampCrumbs[stamp_id]
    if stamp is None:
        return

    if stamp.group in SERVER_ONLY_STAMP_GROUP and not fromServer:
        client.engine.log("warning", client["username"], "trying to manipulate Stamp System.")
        return

    if int(stamp) in [item.stamp for item in client["data"].stamps]:
        return

    client["coins"] += 1
    yield Coin(
        penguin_id=client["id"],
        transaction=1,
        comment="Earned money by earning stamp. Stamp: {}".format(stamp),
    ).save()
    yield Stamp(penguin_id=client["id"], stamp=int(stamp)).save()
    client["recentStamps"].append(stamp)


@GeneralEvent.on("mascot-joined-room")
def handleAwardMascotStamp(room, mascot_name, penguins):
    available = room.roomHandler.engine.stampCrumbs.getStampsByGroup(6)
    mascot_stamps = {str(stamp.name).strip(): stamp.id for stamp in available}
    mascot = str(mascot_name).strip()

    if mascot in mascot_stamps:
        stamp_id = mascot_stamps[mascot]
        for client in penguins:
            handleStampEarned(client, stamp_id, True)

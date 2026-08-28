"""Card Jitsu Fire handlers."""

import logging
from random import choice

from twisted.internet.defer import inlineCallbacks

from Timeline.Handlers.Games.CardJitsu.CardJitsu import getSensei
from Timeline.Handlers.Games.CardJitsuFire import CJ_MATS, CJMat
from Timeline.Handlers.Games.CardJitsuFire.Sensei import CardJitsuFireSenseiGame
from Timeline.Server.Constants import FIRE_STARTER_DECK, TIMELINE_LOGGER, WORLD_SERVER
from Timeline.Utils.Events import GeneralEvent, PacketEventHandler

logger = logging.getLogger(TIMELINE_LOGGER)


@GeneralEvent.on("Room-handler")
def setCJMats(room_handler):
    for mat_id in CJ_MATS:
        room_handler.ROOM_CONFIG.WADDLES[mat_id] = CJMat(
            room_handler,
            mat_id,
            "FireJitsuMat",
            "Card Jitsu Fire Mat",
            CJ_MATS[mat_id],
            False,
            False,
            None,
        )
        room_handler.ROOM_CONFIG.WADDLES[mat_id].waddle = mat_id
        room_handler.ROOM_CONFIG.WADDLES[mat_id].waddles = CJ_MATS[mat_id]

    logger.debug("Card Jitsu Fire Initiated")


@PacketEventHandler.onXT("z", "jsen", WORLD_SERVER, p_r=False)
def handleJoinSenseiCJ(client, data):
    room_handler = client.engine.roomHandler
    if client["room"].ext_id != 953:
        return

    if 997 not in CJ_MATS:
        CJ_MATS[997] = 2

    game_mat = CJMat(
        room_handler, 997, "JitsuMat", "Card Jitsu Mat", 3, False, False, None
    )
    game_mat.waddle = 997
    game_mat.game = CardJitsuFireSenseiGame
    sensei_room = client["room"]

    sensei = getSensei(client.engine)
    game_mat.append(sensei)
    game_mat.append(client)

    game = client["game"]
    game.send("scard", game.ext_id, 997, 2)

    sensei.penguin.game_index = 0
    game.joinGame(sensei)
    list.remove(sensei_room, client)


@GeneralEvent.on("add-item:8006")
@inlineCallbacks
def AddFireStarterDeck(client):
    # Python 3 forbids yield inside comprehensions.
    for item_id in (821, 3032):
        yield client.addItem(item_id)

    yield client["RefreshHandler"].forceRefresh()

    bonus_card = choice([250, 250, 250, 250, 352])
    cards_to_add = [
        client.engine.cardCrumbs[card_id]
        for card_id in FIRE_STARTER_DECK + [bonus_card]
    ]

    for card in cards_to_add:
        if card is None:
            continue
        if card.id not in client["ninjaHandler"].cards:
            client["ninjaHandler"].cards[card.id] = [card, 0]
        client["ninjaHandler"].cards[card.id][1] += 1

    client["ninjaHandler"].ninja.cards = "|".join(
        "{},{}".format(card_id, client["ninjaHandler"].cards[card_id][1])
        for card_id in client["ninjaHandler"].cards
    )
    yield client["ninjaHandler"].ninja.save()

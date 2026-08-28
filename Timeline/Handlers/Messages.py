"""Chat and optional Perspective API moderation handlers."""

import logging
import os

from Timeline.Database.DB import Penguin
from Timeline.Server.Constants import LOGIN_SERVER, TIMELINE_LOGGER, WORLD_SERVER
from Timeline.Utils.Events import GeneralEvent, PacketEventHandler

logger = logging.getLogger(TIMELINE_LOGGER)


@PacketEventHandler.XTPacketRule("s", "u#sma", WORLD_SERVER)
@PacketEventHandler.XTPacketRule_AS2("s", "u#sma", WORLD_SERVER)
def SendMascotMessageRule(data):
    return [[int(data[2][0])], {}]


@PacketEventHandler.onXT("s", "u#sma", WORLD_SERVER)
@PacketEventHandler.onXT_AS2("s", "u#sma", WORLD_SERVER)
def handleSendMascotMessage(client, message_id):
    if client["mascot_mode"]:
        client["room"].send("sma", client["id"], message_id)


@PacketEventHandler.XTPacketRule("s", "m#sm", WORLD_SERVER)
@PacketEventHandler.XTPacketRule_AS2("s", "m#sm", WORLD_SERVER)
def SendMessageRule(data):
    return [[int(data[2][0]), str(data[2][1])], {}]


@PacketEventHandler.onXT("s", "m#sm", WORLD_SERVER)
@PacketEventHandler.onXT_AS2("s", "m#sm", WORLD_SERVER)
def handleSendMessage(client, penguin_id, message):
    if client["id"] != penguin_id:
        return

    message = message.strip().replace("|", "\\|")
    GeneralEvent.call("before-message", client, message)

    if client["muted"]:
        GeneralEvent.call("after-message-muted", client, message)
        return
    if client["stealth_mode"] or client["mascot_mode"]:
        return

    toxic = Toxicity(message)
    if toxic > 60:
        if toxic > 90:
            GeneralEvent(
                "ban-player",
                client,
                0,
                "Rude. Toxicity [{}] message: {}".format(toxic, message),
                type=3,
                ban_type=610,
            )
        elif toxic > 80:
            GeneralEvent(
                "kick-player",
                client,
                "Rude. Toxicity [{}] message: {}".format(toxic, message),
            )
        else:
            GeneralEvent(
                "mute-player",
                client,
                "Rude. Toxicity [{}] message: {}".format(toxic, message),
            )
        return

    client["room"].send("sm", penguin_id, message)
    GeneralEvent.call("after-message", client, message)


PERSPECTIVE_API_KEY = os.getenv("PERSPECTIVE_API_KEY", "").strip()
TOXIC_FILTER = os.getenv("PERSPECTIVE_ATTRIBUTE", "SEVERE_TOXICITY")
API_ACTIVE = False
service = None

if PERSPECTIVE_API_KEY:
    try:
        from googleapiclient import discovery

        service = discovery.build(
            "commentanalyzer",
            "v1alpha1",
            developerKey=PERSPECTIVE_API_KEY,
            cache_discovery=False,
        )
        API_ACTIVE = True
        logger.info("Perspective API moderation enabled")
    except Exception as exc:
        logger.warning("Perspective API disabled: %s", exc)
else:
    logger.info("Perspective API moderation disabled (no PERSPECTIVE_API_KEY)")


def Toxicity(text):
    if not API_ACTIVE or service is None:
        return 0

    try:
        request = {
            "comment": {"text": text},
            "requestedAttributes": {TOXIC_FILTER: {}},
        }
        response = service.comments().analyze(body=request).execute()
        toxicity = round(
            100
            * float(
                response["attributeScores"][TOXIC_FILTER]["summaryScore"]["value"]
            )
        )
        logger.debug("Perspective toxicity [%s]", toxicity)
        return toxicity
    except Exception as exc:
        logger.warning("Perspective API request failed: %s", exc)
        return 0

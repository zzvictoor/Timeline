"""Timeline packet parsing and dispatch."""

from lxml import etree as XML
from lxml.etree import fromstring as parseXML
from twisted.internet import defer

from Timeline.Server.Constants import (
    AVAILABLE_XML_PACKET_TYPES,
    PACKET_DELIMITER,
    PACKET_TYPE,
)
from Timeline.Utils.Events import PacketEventHandler


class PacketHandler(object):
    def __init__(self, penguin):
        self.penguin = penguin

    @staticmethod
    def _text(data):
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data)

    def tryParseXML(self, xml_data):
        try:
            if not self.penguin.ReceivePacketEnabled:
                return True

            text = self._text(xml_data)
            xml_root = parseXML(text.encode("utf-8"))
            packet_type = xml_root.get("t")
            if packet_type not in AVAILABLE_XML_PACKET_TYPES:
                return None

            body = xml_root.xpath("//body")
            for node in body:
                node.get("action")
            return [packet_type, body]
        except Exception:
            return None

    def tryParseXT(self, xt_data):
        try:
            xt_data = self._text(xt_data)
            if (
                not xt_data.startswith(PACKET_DELIMITER)
                or not self.penguin.ReceivePacketEnabled
            ):
                return None

            data = xt_data.split(PACKET_DELIMITER)
            if len(data) < 6:
                return None
            if data[1] != PACKET_TYPE:
                return None

            category = data[2]
            handler = data[3]
            client_data = data[5:-1]

            if not self.penguin.canRecvPacket:
                ignores = [(item[0], item[1]) for item in self.penguin.ignorableXTPackets]
                packet = (category, handler)
                if packet in ignores:
                    entry = self.penguin.ignorableXTPackets[ignores.index(packet)]
                    if entry[2] == 0:
                        return True
                else:
                    return None

            return [category, handler, client_data]
        except Exception as exc:
            self.penguin.log("error", "Unable to parse XT packet:", exc)
            return None

    def parsePacket(self, data):
        data = self._text(data)
        parsed = self.tryParseXML(data)
        if not parsed and data.startswith("<"):
            self.penguin.disconnect()
            raise ValueError("[TE001] Malformed XML String")
        if parsed:
            return self.executePacket(parsed, 1)

        parsed = self.tryParseXT(data)
        if not parsed and data.startswith(PACKET_DELIMITER):
            self.penguin.disconnect()
            raise ValueError("[TE002] Malformed XT String")
        if parsed:
            return self.executePacket(parsed, 2)

        raise ValueError("[TE003] Unhandled Packet Type")

    def executePacket(self, data, packet_kind):
        if packet_kind == 1:
            if data is True:
                return False

            for body in data[1]:
                action = body.get("action")
                event = "{2}:{3}-></{0}-{1}>".format(
                    data[0], action, self.penguin.engine.type, self.penguin.Protocol
                )
                rule = PacketEventHandler.FetchRule(
                    "xml",
                    action,
                    data[0],
                    self.penguin.engine.type,
                    self.penguin.Protocol,
                )
                if rule is not None:
                    args, kwargs = rule(body)
                else:
                    args, kwargs = [], {}

                args = [self.penguin] + args
                PacketEventHandler.call(
                    event,
                    args=(self.penguin, body),
                    rules_a=args,
                    rules_kwarg=kwargs,
                )

        elif packet_kind == 2:
            if data is True:
                return False

            event = "{2}:{3}->%{0}%{1}%".format(
                data[0], data[1], self.penguin.engine.type, self.penguin.Protocol
            )
            rule = PacketEventHandler.FetchRule(
                "xt",
                data[0],
                data[1],
                self.penguin.engine.type,
                self.penguin.Protocol,
            )
            if rule is not None:
                args, kwargs = rule(data)
            else:
                args, kwargs = [], {}

            args = [self.penguin] + args
            PacketEventHandler.call(
                event,
                args=[self.penguin, data],
                rules_a=args,
                rules_kwarg=kwargs,
            )
        elif packet_kind == 3:
            return False

        return True

    def handlePacketReceived(self, line):
        line = self._text(line)
        if line == "<policy-file-request/>":
            return defer.maybeDeferred(self.penguin.handleCrossDomainPolicy)
        return defer.maybeDeferred(self.parsePacket, line)

    def buildXML(self, node):
        root_name = next(iter(node))
        root = XML.Element(str(root_name))
        self.buildXMLNodes(root, node[root_name])
        return XML.tostring(root, encoding="unicode")

    def buildXMLNodes(self, element, node):
        if node is None or isinstance(node, (str, int, float, bool)):
            element.text = XML.CDATA("" if node is None else str(node))
            return

        if isinstance(node, dict):
            for key, value in node.items():
                key = str(key)
                if isinstance(value, dict):
                    child = XML.Element(key)
                    self.buildXMLNodes(child, value)
                    element.append(child)
                elif isinstance(value, list):
                    child_name = key[:-1] if key.endswith("s") else key
                    for item in value:
                        child = XML.Element(child_name)
                        self.buildXMLNodes(child, item)
                        element.append(child)
                else:
                    element.set(key, "" if value is None else str(value))
            return

        if isinstance(node, (list, tuple)):
            for item in node:
                child = XML.Element("item")
                self.buildXMLNodes(child, item)
                element.append(child)
            return

        element.text = XML.CDATA(str(node))

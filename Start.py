# -*- coding: utf-8 -*-
"""Timeline server bootstrap.

Modernized for Python 3 while preserving the original AS2/AS3 protocol and
handler/plugin architecture.
"""

import gc
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import signal
import sys

from dotenv import load_dotenv
from twisted.internet import reactor
from twisted.python import log

import Timeline
from Timeline import Handlers, PacketHandler, Plugins
from Timeline.Database import DBManagement as DBM
from Timeline.Server import Constants
from Timeline.Server.Engine import Engine
from Timeline.Server.Penguin import Penguin
from Timeline.Utils.Events import GeneralEvent
from Timeline.Utils.Modules import ModuleHandler
from Timeline.Utils.Plugins import (
    PLUGINS_LOADED,
    getPlugins,
    loadPluginObjects,
    loadPlugins,
)

load_dotenv()

Constants.TIMELINE_LOGGER = "Timeline"


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def initiate_color_logger(name="Timeline"):
    from colorlog import ColoredFormatter

    Constants.TIMELINE_LOGGER = name
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers when hot-reloading/importing Start.py.
    if logger.handlers:
        return logger

    stream = logging.StreamHandler()
    fmt = "  %(reset)s%(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s"
    stream.setFormatter(
        ColoredFormatter(
            fmt,
            log_colors={
                "DEBUG": "white",
                "INFO": "cyan",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "black,bg_red",
            },
        )
    )
    logger.addHandler(stream)

    os.makedirs("./logs", exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        "./logs/TimelineLogs.log", when="d", interval=1, encoding="utf-8"
    )
    logger.addHandler(file_handler)
    logger.debug("Timeline Logger::Initiated")
    return logger


def initiate_logger(name="Timeline"):
    Constants.TIMELINE_LOGGER = name
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger

    stream = logging.StreamHandler()
    stream.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s]\t : %(message)s", "%H:%M")
    )
    logger.addHandler(stream)

    os.makedirs("./logs", exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        "./logs/TimelineLogs.log", when="d", interval=1, encoding="utf-8"
    )
    logger.addHandler(file_handler)
    logger.debug("Timeline Logger::Initiated")
    return logger


def hot_load_module(module):
    return ModuleHandler(module).startLoadingModules()


def load_plugins(module):
    loadPlugins(module)
    loaded = list(PLUGINS_LOADED)
    TimelineLogger.info(
        "Loaded %s Plugin(s) : %s",
        len(loaded),
        ", ".join(plugin.name for plugin in getPlugins()),
    )
    loadPluginObjects()


print(
    r"""
     _______
    |__   __|
       | |  #   _ _     __  ||  #  __     __  py3
       | | | | | | |  / //| || || |  |  / //|
       | | | | | | | |_||/  || || |  | |_||/
       |_| |_| | | |  \___  || || |  |  \__
    ----------------------------------------------
    > AS3 + AS2 CPPS Emulator
    > Timeline 7.7 compatibility port for Python 3
"""
)

TimelineLogger = initiate_color_logger()

DBMS = DBM(
    user=os.getenv("MYSQL_USER", "timeline"),
    passd=os.getenv("MYSQL_PASSWORD", "timeline"),
    db=os.getenv("MYSQL_DATABASE", "timeline"),
    host=os.getenv("MYSQL_HOST", "127.0.0.1"),
    port=env_int("MYSQL_PORT", 3306),
)

if not DBMS.conn:
    sys.exit(1)

if not DBMS.db_data[1].endswith("line"):
    TimelineLogger.critical(
        "Unsupported data structure: Timeline >= v7 requires the database name "
        "to end with 'line' (for example: timeline)."
    )
    TimelineLogger.info("Exiting Timeline.")
    sys.exit(1)

# Route unhandled Twisted Deferred errors through Timeline's logger.
TEObserver = log.PythonLoggingObserver(loggerName=Constants.TIMELINE_LOGGER)
TEObserver.start()

SERVERS = []


def safeDestroyClients():
    TimelineLogger.warning("Timeline is shutting down safely...")
    deferreds = []
    for engine in SERVERS:
        deferreds.append(engine.connectionLost("Server shutdown"))
    return deferreds


def onExitSignal(*_args):
    TimelineLogger.info("Closing Timeline...")
    if not reactor.running:
        return
    reactor.callFromThread(reactor.stop)


for sig_name in ("SIGABRT", "SIGINT", "SIGTERM"):
    sig = getattr(signal, sig_name, None)
    if sig is not None:
        try:
            signal.signal(sig, onExitSignal)
        except (OSError, ValueError):
            pass


def main():
    global SERVERS

    bind_host = os.getenv("TIMELINE_BIND_HOST", "0.0.0.0")
    login_port = env_int("TIMELINE_LOGIN_PORT", 6112)
    world_port = env_int("TIMELINE_WORLD_PORT", 9875)
    world_id = env_int("TIMELINE_WORLD_ID", 100)
    world_max = env_int("TIMELINE_WORLD_MAX", 300)
    world_name = os.getenv("TIMELINE_WORLD_NAME", "Gravity")

    login_server = Engine(
        Penguin,
        Constants.LOGIN_SERVER,
        1,
        "Login",
        server_protocol=Constants.CROSS_PROTOCOL,
    )
    world_server = Engine(
        Penguin,
        Constants.WORLD_SERVER,
        world_id,
        world_name,
        _max=world_max,
        server_protocol=Constants.CROSS_PROTOCOL,
    )

    login_server.run(bind_host, login_port)
    world_server.run(bind_host, world_port)
    SERVERS = [login_server, world_server]


load_plugins(Plugins)
hot_load_module(Handlers).addCallback(
    lambda _x: hot_load_module(PacketHandler).addCallback(lambda _y: main())
)
reactor.addSystemEventTrigger("before", "shutdown", safeDestroyClients)
reactor.run()
gc.collect()

"""Dynamic handler/module loader with hot-reload support."""

from collections import deque
import importlib
import logging
import os
import pkgutil

from twisted.internet import defer
from twisted.python.rebuild import rebuild
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer as ModuleObserver

from Timeline.Server.Constants import TIMELINE_LOGGER
from Timeline.Utils.Events import Event, GeneralEvent, PacketEventHandler


class ModulesEventHandler(FileSystemEventHandler):
    def __init__(self):
        super(ModulesEventHandler, self).__init__()

    def stripModule(self, path, length=None):
        relative_path = path[len(self.module_package):length]
        relative_path = relative_path.rstrip("/\\").lstrip("/\\")
        relative_path = relative_path.replace("\\", ".").replace("/", ".")
        module_name = "{}.{}".format(self.parent_module_name, relative_path)
        module_parent_path = "/".join(path.replace("\\", "/").split("/")[:-1])
        module_parent_scope = ".".join(module_name.split(".")[:-1])
        return module_parent_path, module_parent_scope, module_name

    def on_created(self, event):
        path = event.src_path
        if event.is_directory:
            parent_path, parent_scope, module_name = self.stripModule(path)
            self.loadModules(parent_scope, [parent_path])
            self.logger.info("on_created_directory: %s", module_name)
            return
        if not path.startswith(self.module_package) or not path.endswith(".py"):
            return
        parent_path, parent_scope, module_name = self.stripModule(path, -3)
        self.loadModules(parent_scope, [parent_path])
        self.logger.info("on_created: %s", module_name)

    def on_moved(self, event):
        path = event.src_path
        path2 = event.dest_path
        _, _, module_name = self.stripModule(path, -3)
        parent_path, parent_scope, module_name2 = self.stripModule(path2, -3)

        if event.is_directory:
            _, _, module_name = self.stripModule(path)
            parent_path, parent_scope, module_name2 = self.stripModule(path2)
            self.clearModules(module_name, True)
            self.loadModules(parent_scope, [parent_path])
            self.logger.info("on_moved_directory: from %s to %s", module_name, module_name2)
            return
        if not path.endswith(".py") or not path2.endswith(".py"):
            return
        self.clearModules(module_name)
        self.loadModules(parent_scope, [parent_path])
        self.logger.info("on_moved: from %s to %s", module_name, module_name2)

    def on_deleted(self, event):
        path = event.src_path
        _, _, module_name = self.stripModule(path, -3)
        if event.is_directory:
            _, _, module_name = self.stripModule(path)
            self.clearModules(module_name, True)
            self.logger.info("on_deleted_directory: %s", module_name)
            return
        if not path.endswith(".py"):
            return
        self.clearModules(module_name)
        self.logger.info("on_deleted: %s", module_name)

    def on_modified(self, event):
        path = event.src_path
        if event.is_directory or not path.endswith(".py"):
            return
        _, _, module_name = self.stripModule(path, -3)
        self.clearModules(module_name, only_unset=True)
        self.reloadModules(module_name)
        self.logger.info("on_modified: %s", module_name)


class ModuleHandler(ModulesEventHandler):
    def __init__(self, module):
        super(ModuleHandler, self).__init__()
        self.module_parent = module
        self.parent_module_name = module.__name__
        self.module_package = module.__path__[-1]
        self.modules = deque()
        self.logger = logging.getLogger(TIMELINE_LOGGER)
        self.observer = None

    def unsetEventsInModulesAndSubModules(self, name):
        Event.unsetEventsInModulesAndSubModules(name)
        PacketEventHandler.unsetEventsInModulesAndSubModules(name)
        GeneralEvent.unsetEventsInModulesAndSubModules(name)

    def unsetEventInModule(self, name):
        Event.unsetEventInModule(name)
        PacketEventHandler.unsetEventInModule(name)
        GeneralEvent.unsetEventInModule(name)

    def clearModules(self, name=None, submodules=False, only_unset=False):
        for module in list(self.modules):
            matches = name is None or module.__name__ == name
            if submodules and name is not None:
                matches = module.__name__ == name or module.__name__.startswith(name + ".")
            if not matches:
                continue
            if submodules:
                self.unsetEventsInModulesAndSubModules(module.__name__)
            else:
                self.unsetEventInModule(module.__name__)
            if not only_unset:
                self.modules.remove(module)

    def reloadModules(self, name=None):
        for index, module in enumerate(list(self.modules)):
            if name is not None and module.__name__ != name:
                continue
            try:
                self.modules[index] = rebuild(module)
            except Exception as exc:
                self.logger.exception("[TE030] Error rebuilding %s: %s", module.__name__, exc)
        return self.modules

    def loadModules(self, scope=None, _path=None):
        module_paths = self.module_parent.__path__ if _path is None else _path
        module_name = self.module_parent.__name__ if scope is None else scope.strip(".")
        for _finder, name, is_package in pkgutil.iter_modules(module_paths):
            import_name = "{}.{}".format(module_name, name)
            loaded = importlib.import_module(import_name)
            if is_package:
                self.loadModules(loaded.__name__, loaded.__path__)
            else:
                self.modules.append(loaded)

    def modulesLoaded(self, _result):
        for module in self.modules:
            if hasattr(module, "init"):
                module.init()
        self.logger.info("Loaded %s module(s) in %s", len(self.modules), self.module_parent.__name__)

    def autoReloadModules(self, _result):
        if os.getenv("TIMELINE_HOT_RELOAD", "1").lower() in ("0", "false", "no"):
            return
        self.observer = ModuleObserver()
        self.observer.schedule(self, path=self.module_parent.__path__[0], recursive=True)
        self.observer.daemon = True
        self.observer.start()

    def loadingException(self, err):
        self.logger.error(err.getTraceback())
        self.logger.error("[Error loading module] : %s", err.getErrorMessage())
        return err

    def startLoadingModules(self):
        self.modules.clear()
        result = defer.maybeDeferred(self.loadModules)
        result.addCallback(self.modulesLoaded)
        result.addCallback(self.autoReloadModules)
        result.addErrback(self.loadingException)
        self.logger.info("Loading modules in: %s", self.module_parent.__name__)
        return result

"""Temporary compatibility loader for Timeline's remaining Python 2 modules.

The server core is being ported directly to Python 3. Until every historical
handler/plugin is converted in-source, this importer runs lib2to3 on those
legacy modules in memory. It never rewrites files on disk and can be removed
once the port is complete.

Python 3.11 is intentionally targeted because lib2to3 is still available there.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import threading
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from lib2to3 import refactor


_MODERNIZED_MODULES = {
    "Timeline.compat",
    "Timeline.Database",
    "Timeline.Database.DB",
    "Timeline.Handlers.Login",
    "Timeline.Handlers.Messages",
    "Timeline.Server.Constants",
    "Timeline.Server.Engine",
    "Timeline.Server.Packets",
    "Timeline.Server.Penguin",
    "Timeline.Server.Redis",
    "Timeline.Utils.Cryptography",
    "Timeline.Utils.Modules",
}

_TOOL = None
_TOOL_LOCK = threading.Lock()
_INSTALLED = False


def _tool():
    global _TOOL
    if _TOOL is None:
        with _TOOL_LOCK:
            if _TOOL is None:
                fixers = refactor.get_fixers_from_package("lib2to3.fixes")
                _TOOL = refactor.RefactoringTool(fixers)
    return _TOOL


class LegacyTimelineLoader(importlib.machinery.SourceFileLoader):
    def source_to_code(self, data, path, *, _optimize=-1):
        source = importlib.util.decode_source(data)
        if source and not source.endswith("\n"):
            source += "\n"
        try:
            converted = str(_tool().refactor_string(source, path))
        except Exception as exc:
            raise ImportError(
                "Unable to convert legacy Timeline module {}: {}".format(path, exc)
            ) from exc
        return compile(converted, path, "exec", dont_inherit=True, optimize=_optimize)


class LegacyTimelineFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith("Timeline.") or fullname in _MODERNIZED_MODULES:
            return None

        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or not isinstance(
            spec.loader, importlib.machinery.SourceFileLoader
        ):
            return None

        spec.loader = LegacyTimelineLoader(fullname, spec.loader.path)
        return spec


def install_legacy_importer():
    global _INSTALLED
    if _INSTALLED:
        return
    if os.getenv("TIMELINE_LEGACY_IMPORT_COMPAT", "1").lower() in (
        "0",
        "false",
        "no",
    ):
        return
    sys.meta_path.insert(0, LegacyTimelineFinder())
    _INSTALLED = True

import os
from os.path import basename, dirname, isfile

from Emilia import LOGGER


def getListOfFiles(dirName):
    listOfFile = os.listdir(dirName)
    allFiles = list()
    for entry in listOfFile:
        fullPath = os.path.join(dirName, entry)
        if "__pycache__" not in fullPath:
            if os.path.isdir(fullPath):
                allFiles = allFiles + getListOfFiles(fullPath)
            else:
                allFiles.append(fullPath)

    return allFiles


# Derive the commands/ dir from this file, not os.getcwd(): launching from any
# directory other than the repo root previously loaded zero command modules.
commands_dir = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "modules", "commands"
)
mod_paths = getListOfFiles(dirName=dirname(__file__)) + getListOfFiles(
    dirName=commands_dir
)

all_modules = [
    f[:-3]
    for f in mod_paths
    if isfile(f) and f.endswith(".py") and not f.endswith("__init__.py")
]

module_names = [
    basename(f)[:-3]
    for f in mod_paths
    if isfile(f) and f.endswith(".py") and not f.endswith("__init__.py")
]

LOGGER.debug(f"{', '.join(module_names)} - MODULES LOADED")
ALL_MODULES = sorted(all_modules)
LOGGER.info(f"{len(ALL_MODULES)} modules discovered.")
__all__ = ALL_MODULES + ["ALL_MODULES"]

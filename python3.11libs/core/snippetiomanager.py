import hou
import json
import os
import uuid
import shutil
from collections import namedtuple

from core.settings import Settings

# Removed 'desc' and 'author' from the Snippet definition
Snippet = namedtuple('Snippet', ['id', 'name', 'runover', 'expression', 'kind'])


class SnippetIOManager:
    """
    Handles saving and loading snippets to/from a single JSON database file.
    Uses Settings to handle application preferences and includes a rolling backup system.
    """

    SNIPPETS_DB_VERSION = 1.2  # Incremented version for the new data structure
    EMPTY_SNIPPETS_DATA = {
        "version": SNIPPETS_DB_VERSION,
        "snippets": []
    }
    MAX_BACKUPS = 5

    def __init__(self):
        self.settings = Settings()

    def snippetToDict(self, obj):
        """
        Recursively convert a namedtuple (Snippet) or other objects to a
        JSON-serializable dictionary.
        """
        if isinstance(obj, uuid.UUID):
            return str(obj)

        if isinstance(obj, tuple) and hasattr(obj, "_asdict"):
            return {k: self.snippetToDict(v) for k, v in obj._asdict().items()}
        elif isinstance(obj, list):
            return [self.snippetToDict(v) for v in obj]
        else:
            return obj

    def getSnippetsDatabasePath(self):
        """
        Reads the last used database file path from the settings.
        """
        databasePath = self.settings.loadValue("snippets_database/path")
        if databasePath and os.path.exists(databasePath):
            return databasePath

        databasePath = os.path.join(self.settings.getUserHome(), f"{self.settings.SETTING_DIRECTORY}/snippets.json")
        self.setSnippetsDatabasePath(databasePath)
        return databasePath

    def setSnippetsDatabasePath(self, dbPath):
        """
        Saves the given database file path to the settings.
        """
        if not os.path.exists(dbPath):
            with open(dbPath, "w") as f:
                json.dump(self.EMPTY_SNIPPETS_DATA, f, indent=4)

        self.settings.saveValue("snippets_database", "path", dbPath)

    def loadSnippetsFromDatabase(self):
        """
        Loads and parses the JSON snippet database from the given path.
        """
        dbPath = self.getSnippetsDatabasePath()
        if not dbPath or not os.path.exists(dbPath):
            return {}

        try:
            outSnippets = {}
            with open(dbPath, "r") as f:
                data = json.load(f)
                snippets = data.get('snippets', [])

                for snippetData in snippets:
                    # Load only the fields that still exist, ignoring old ones
                    s = Snippet(
                        snippetData['id'],
                        snippetData.get('name', 'Untitled'),
                        snippetData.get('runover', 'N/A'),
                        snippetData.get('expression', ''),
                        snippetData.get('kind', 'attribwrangle')
                    )
                    outSnippets[s.id] = s

                return outSnippets

        except (json.JSONDecodeError, IOError) as e:
            hou.ui.displayMessage(f"Error loading snippet database '{dbPath}': {e}", severity=hou.severityType.Error)
            return {}

    def _manageBackups(self, dbPath):
        """
        Manages rolling backups, storing them in a 'snippet_backups' subdirectory.
        """
        dbDir = os.path.dirname(dbPath)
        dbFilename, dbExt = os.path.splitext(os.path.basename(dbPath))
        backupDir = os.path.join(dbDir, "snippet_backups")

        try:
            os.makedirs(backupDir, exist_ok=True)
        except OSError as e:
            hou.ui.displayMessage(f"Could not create backup directory: {e}", severity=hou.severityType.Warning)
            return

        backupBase = os.path.join(backupDir, dbFilename)

        for i in range(self.MAX_BACKUPS, 1, -1):
            prevBackupPath = f"{backupBase}.bak{i - 1}{dbExt}"
            nextBackupPath = f"{backupBase}.bak{i}{dbExt}"
            if os.path.exists(prevBackupPath):
                if os.path.exists(nextBackupPath):
                    os.remove(nextBackupPath)
                os.rename(prevBackupPath, nextBackupPath)

        if os.path.exists(dbPath):
            newBackupPath = f"{backupBase}.bak1{dbExt}"
            shutil.copy2(dbPath, newBackupPath)

    def saveSnippetsToDatabase(self, snippetData):
        """
        Saves the provided snippet data, creating a backup of the old file first.
        """
        dbPath = self.getSnippetsDatabasePath()
        if not dbPath:
            hou.ui.displayMessage("Snippet database path not set.", severity=hou.severityType.Error)
            return False

        try:
            self._manageBackups(dbPath)
        except Exception as e:
            hou.ui.displayMessage(f"Failed to create database backup: {e}", severity=hou.severityType.Warning)

        outSnippetData = self.EMPTY_SNIPPETS_DATA
        outSnippetData['snippets'] = [self.snippetToDict(s) for s in snippetData.values()]

        try:
            tempPath = dbPath + ".tmp"
            with open(tempPath, "w") as f:
                json.dump(outSnippetData, f, indent=4)

            shutil.move(tempPath, dbPath)
            return True
        except (IOError, TypeError) as e:
            hou.ui.displayMessage(f"Error saving snippet database to '{dbPath}': {e}", severity=hou.severityType.Error)
            return False


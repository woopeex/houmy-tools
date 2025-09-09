import os
from hutil.Qt.QtCore import QSettings

class Settings:
    """
    A generic wrapper for QSettings to handle saving and loading
    application preferences for various Houdini tools.
    """

    SETTING_DIRECTORY = ".houmy_tools"

    def __init__(self):
        settingsFile = os.path.join(self.getUserHome(), f'{self.SETTING_DIRECTORY}/settings.ini')
        self.settings = QSettings(settingsFile, QSettings.IniFormat)

    def getUserHome(self):
        return os.path.expanduser('~')

    def saveValue(self, group, key, value):
        """
        Saves a value to the settings for a given key.

        Args:
            key (str): The key to store the value under.
            value: The value to store. Can be various types supported by QSettings.
        """
        self.settings.beginGroup(group)
        self.settings.setValue(key, value)
        self.settings.endGroup()

    def loadValue(self, key, defaultValue=None):
        """
        Loads a value from the settings for a given key.

        Args:
            key (str): The key of the value to retrieve.
            defaultValue: The value to return if the key is not found. Defaults to None.

        Returns:
            The retrieved value, or the defaultValue if not found.
        """
        return self.settings.value(key, defaultValue)

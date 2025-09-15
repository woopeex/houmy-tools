import hou

def sceneEventCallback(event_type):
    pass
    # if event_type == hou.hipFileEventType.BeforeClear:
    #     # Called before the current hipfile is cleared
    # elif event_type == hou.hipFileEventType.AfterClear:
    #     # Called after the current hipfile is cleared
    # elif event_type == hou.hipFileEventType.BeforeLoad:
    #     # Called immediatly before a hipfile is loaded
    # elif event_type == hou.hipFileEventType.AfterLoad:
    #     # Called immediatly after a hipfile is loaded
    # elif event_type == hou.hipFileEventType.BeforeMerge:
    #     # Called immediatly before a hipfile is merged
    # elif event_type == hou.hipFileEventType.AfterMerge:
    #     # Called immediatly after a hipfile is merged
    # elif event_type == hou.hipFileEventType.BeforeSave:
    #     # Called immediatly before a hipfile is saved
    # elif event_type == hou.hipFileEventType.AfterSave:
    #     # Called immediatly after a hipfile is saved


# hou.hipFile.addEventCallback(scene_event_callback)
from hutil.Qt import QtCore, QtGui, QtWidgets

class HouMyToolsFilter(QtCore.QObject):

    def eventFilter(self, obj, event):

        if event.type() == QtCore.QEvent.DragMove:
            mimeData = event.mimeData()
            data = mimeData.data(hou.qt.mimeType.parmPath)
            if not data.isEmpty():
                parmPath = str(data).split("\t")
                # print("Dropped parameter path:", parmPath)

        if event.type() == QtCore.QEvent.Drop:
            mimeData = event.mimeData()

            print("MimeData:", mimeData.formats())
            print("Dropped text:", mimeData.text())

            data = mimeData.data(hou.qt.mimeType.nodePath)
            if not data.isEmpty():
                nodePath = str(data).split("\t")
                print("Dropped node path:", nodePath)

            data = mimeData.data(hou.qt.mimeType.parmPath)
            if not data.isEmpty():
                parmPath = str(data, 'utf-8').split("\t")[0]
                parm = hou.parm(parmPath)
                print("Dropped parameter path:", parm)

                if parm:
                    from core.nodemanager import NodeManager
                    NodeManager.createControlAttribute(parm)

        return super(HouMyToolsFilter, self).eventFilter(obj, event)


global houmyToolsFilter
houmyToolsFilter = HouMyToolsFilter()

theApp = QtWidgets.QApplication.instance()
theApp.installEventFilter(houmyToolsFilter)

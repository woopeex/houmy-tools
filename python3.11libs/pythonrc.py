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
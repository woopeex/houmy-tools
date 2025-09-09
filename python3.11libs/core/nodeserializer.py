"""
Houdini Node Serialization Script

This script contains functions to serialize a list of Houdini nodes into a
string and deserialize them back, allowing for saving and loading.

The core idea is to convert a complex node network into a single, portable
text string. This string can then be saved to a file, copied to the clipboard,
or sent over a network. The script can then take that string and faithfully
recreate the nodes in another Houdini session or a different part of the scene.

This code has been extracted and simplified from the 'hpaste' tool.

Key Functions:
- serializeNodesToString(nodes, transferAssets=True):
    Takes a list of hou.Node objects and returns a serialized string.
- deserializeStringToNodes(s, parentNode, **kwargs):
    Takes a serialized string and recreates the nodes under a parent node.
- saveNodesToFile(nodes, filepath, transferAssets=True):
    A convenience wrapper to serialize nodes and save them directly to a file.
- loadNodesFromStringInteractive(serializedData, targetParent=None):
    An interactive wrapper to load nodes from a string, handling context checks.
"""

# =============================================================================
# NOTE: This script is based on the original 'hpaste.py' tool.
# The core serialization and deserialization logic has been adapted and
# simplified from that codebase for easier integration into other tools.
#
# Original HPaste repository: https://github.com/pedohorse/hpaste.git
# =============================================================================

import os
import hou
import json
import re
import hashlib
import base64
import bz2
import tempfile

# The version of the data format this script produces. This is embedded in the
# serialized string to handle compatibility checks when loading.
CURRENT_FORMAT_VERSION = (2, 2)

class InvalidContextError(RuntimeError):
    """Custom exception raised when trying to load nodes into an incorrect context."""
    def __init__(self, parentNode, expectedContext):
        # Determine the context of the node we are trying to paste into.
        self.currentContext = getChildContext(parentNode, hou.applicationVersion())
        self.expectedContext = expectedContext
        # Create a user-friendly error message.
        message = (f"This snippet requires a '{self.expectedContext}' context, "
                   f"but the current context is '{self.currentContext}'.")
        super().__init__(message)


def getChildContext(node, houver):
    """
    Determines the network context (e.g., 'Sop', 'Object') of a parent node.
    The method to get this information changed between Houdini versions.

    Args:
        node (hou.Node): The parent node to check.
        houver (tuple): The Houdini application version tuple (e.g., (19, 5, 432)).

    Returns:
        str: The name of the child type category.
    """
    if houver[0] >= 16:
        # Modern Houdini versions use this path to get the category name.
        return node.type().childTypeCategory().name()
    elif 10 <= houver[0] <= 15:
        # Older versions had the method directly on the node.
        return node.childTypeCategory().name()
    else:
        raise RuntimeError("Unsupported Houdini version!")

def orderNodes(nodes):
    """
    Sorts a list of nodes based on their input/output connections.
    This is crucial for the legacy `asCode` serialization method to ensure that
    when the code is executed, nodes are created before other nodes try to
    connect to them.

    Args:
        nodes (list of hou.Node): The list of nodes to sort.

    Returns:
        list of hou.Node: A sorted list of the nodes.
    """
    if not nodes:
        return []

    parent = nodes[0].parent()
    for node in nodes:
        if node.parent() != parent:
            raise RuntimeError("Selected nodes must have the same parent!")

    # Start with nodes that have no inputs from within the selected group.
    # These are the "root" nodes of the selection.
    sortedNodes = [n for n in nodes if not any(inp in nodes for inp in n.inputs())]

    # Walk the dependency graph, adding nodes only after their inputs are in the list.
    for node in sortedNodes:
        for output in (out for out in node.outputs() if out in nodes):
            if output not in sortedNodes:
                sortedNodes.append(output)

    return sortedNodes

def serializeNodesToString(nodes, transferAssets=True):
    """
    Serializes a list of Houdini nodes into a single, portable string.
    This is the core saving function. It packages node data, HDAs, and metadata
    into a compressed, encoded format.

    Args:
        nodes (list): A list of `hou.Node` or `hou.NetworkMovableItem` objects.
        transferAssets (bool): If True, scans for and includes custom HDA
                                definitions used by the nodes.

    Returns:
        str: A single string containing all the serialized node data.
    """
    if not nodes:
        raise ValueError("The 'nodes' list cannot be empty.")

    parent = nodes[0].parent()
    for item in nodes:
        if item.parent() != parent:
            raise RuntimeError("All selected items must have the same parent!")

    # --- Determine Serialization Method ---
    # The method depends on the Houdini version. Modern versions use a more
    # reliable native binary format (`algType` 1 or 2).
    houver = hou.applicationVersion()
    algType = 0
    if 10 <= houver[0] <= 15:
        algType = 1 # Native format for H10-15
    elif houver[0] >= 16:
        algType = 2 # Native format for H16+
    else:
        # SECUIRTY FIX: Raise an error on very old Houdini versions that would
        # have used the insecure 'asCode' method.
        raise RuntimeError("Sorry, this Houdini version is too old and not supported.")

    nodeCode = ''
    hdaList = []

    # --- Modern Serialization (Native Binary) ---
    # --- Package Custom Digital Assets (HDAs) ---
    if transferAssets:
        hfs = os.environ['HFS'] # Path to Houdini installation ($HFS)
        itemsToScan = [item for item in nodes if isinstance(item, hou.Node)]
        for item in itemsToScan:
            # Include the node itself and any nodes inside it (if it's a subnet)
            allSubNodes = [item] + list(item.allSubChildren())
            for subNode in allSubNodes:
                definition = subNode.type().definition()
                if not definition:
                    continue

                # Check if the HDA is part of the standard Houdini install.
                # If not, we need to package its definition.
                libPath = definition.libraryFilePath()
                if not libPath.startswith(hfs):
                    fd, tempPath = tempfile.mkstemp()
                    try:
                        # Save the HDA definition to a temporary file.
                        definition.copyToHDAFile(tempPath)
                        with open(tempPath, 'rb') as f:
                            hdaCode = f.read()
                        # Encode the binary HDA data for JSON compatibility.
                        encodedHda = base64.b64encode(hdaCode).decode('utf-8')
                        hdaList.append({
                            'type': subNode.type().name(),
                            'category': subNode.type().category().name(),
                            'code': encodedHda
                        })
                    finally:
                        os.close(fd)
                        os.remove(tempPath)

    # --- Serialize Node Network ---
    # We save the nodes to a temporary file and then read the raw binary
    # data from that file. This is the most reliable way to copy nodes.
    fd, tempPath = tempfile.mkstemp()
    try:
        if algType == 1: # H10-15
            nodeItems = [n for n in nodes if isinstance(n, hou.Node)]
            parent.saveChildrenToFile(nodeItems, (), tempPath)
        elif algType == 2: # H16+
            parent.saveItemsToFile(nodes, tempPath, False)

        with open(tempPath, "rb") as f:
            nodeCode = f.read()
    finally:
        os.close(fd)
        os.remove(tempPath)

    # --- Final Data Assembly and Encoding ---
    # Encode the primary node data into a base64 string.
    encodedCode = base64.b64encode(nodeCode).decode('utf-8')

    # Assemble the final data dictionary (payload).
    data = {
        'algtype': algType,
        'version': CURRENT_FORMAT_VERSION[0],
        'version.minor': CURRENT_FORMAT_VERSION[1],
        'houver': houver,
        'context': getChildContext(parent, houver),
        'code': encodedCode,
        'hdaList': hdaList,
        'chsum': hashlib.sha1(encodedCode.encode('utf-8')).hexdigest()
    }

    # Convert the dictionary to a JSON string.
    jsonString = json.dumps(data)
    # Compress the JSON string to make it smaller.
    compressedData = bz2.compress(jsonString.encode('utf-8'))
    # Encode the compressed data into a URL-safe string.
    finalString = base64.urlsafe_b64encode(compressedData).decode('utf-8')

    return finalString

def deserializeStringToNodes(s, parentNode, ignoreHdasIfAlreadyDefined=True, forcePreferHdas=False):
    """
    Deserializes a string and recreates the nodes within the given parentNode.
    This is the core loading function. It unpacks the data, installs HDAs,
    and creates the nodes.

    Args:
        s (str): The serialized node string.
        parentNode (hou.Node): The node under which to create the new nodes.
        ignoreHdasIfAlreadyDefined (bool): If True, skips installing an HDA
            from the string if an HDA with the same name is already installed.
        forcePreferHdas (bool): If True, sets newly installed embedded
            HDAs as the preferred definition.

    Returns:
        list: A list of the newly created `hou.NetworkMovableItem` objects.
    """
    try:
        # Reverse the encoding process: base64 decode -> decompress -> JSON parse.
        sBytes = s.encode('utf-8')
        data = json.loads(bz2.decompress(base64.urlsafe_b64decode(sBytes)))
    except Exception as e:
        raise RuntimeError(f"Input data is corrupted or not a valid node string: {e}")

    # --- SECURITY FIX: Block the insecure legacy algorithm type ---
    algType = data['algtype']
    if algType == 0:
        raise RuntimeError(
            "This node snippet uses an insecure legacy format ('algtype 0') "
            "that is no longer supported due to security vulnerabilities. "
            "Please re-save the snippet from a modern version of Houdini."
        )

    houverCurrent = hou.applicationVersion()

    # --- Validation Checks ---
    # Check if the data is from a future version of the script.
    if data['version'] > CURRENT_FORMAT_VERSION[0]:
        raise RuntimeError("Data format is from a newer version of the script. Please update.")

    # Check if the network context matches (e.g., can't paste SOPs in OBJ level).
    context = getChildContext(parentNode, houverCurrent)
    if context != data['context']:
        raise InvalidContextError(parentNode, data['context'])

    # Verify the checksum to ensure the data hasn't been corrupted.
    if hashlib.sha1(data['code'].encode('utf-8')).hexdigest() != data['chsum']:
        raise RuntimeError("Checksum failed! Data may be corrupt.")

    # --- HDA Installation ---
    for hdaItem in data.get('hdaList', []):
        ntype = hdaItem['type']
        ncategory = hdaItem['category']
        # Optionally skip installing if a node type with this name already exists.
        if ignoreHdasIfAlreadyDefined:
            if hou.nodeType(hou.nodeTypeCategories()[ncategory], ntype):
                continue

        # Decode the HDA data and write it to a temporary file to be installed.
        hdaCode = base64.b64decode(hdaItem['code'])
        fd, tempPath = tempfile.mkstemp()
        try:
            with open(tempPath, 'wb') as f: f.write(hdaCode)
            # Install the HDA file into the current session.
            hou.hda.installFile(tempPath, force_use_assets=True)
            if forcePreferHdas:
                definitions = hou.hda.definitionsInFile(tempPath)
                for definition in definitions:
                    if definition.nodeType().name() == ntype:
                        definition.setIsPreferred(True)
        finally:
            os.close(fd)
            os.remove(tempPath)

    # --- Node Creation ---
    # Get a set of all items before we create new ones, to identify what's new later.
    oldItems = set(parentNode.allItems())
    nodeCode = base64.b64decode(data['code'])

    # Modern method: load from a temporary file containing the node data.
    fd, tempPath = tempfile.mkstemp()
    try:
        with open(tempPath, "wb") as f: f.write(nodeCode)
        if algType == 1:
            parentNode.loadChildrenFromFile(tempPath)
        elif algType == 2:
            parentNode.loadItemsFromFile(tempPath)
    except hou.LoadWarning as e:
        # Report warnings but don't stop the process.
        print(f"Houdini Load Warning: {e}")
    finally:
        os.close(fd)
        os.remove(tempPath)

    # Compare the current items with the old set to find the newly created ones.
    newItems = [item for item in parentNode.allItems() if item not in oldItems]
    return newItems

def saveNodesToFile(nodes, filepath, transferAssets=True):
    """
    Convenience wrapper function to serialize a list of nodes and save the
    resulting string to a file.

    Args:
        nodes (list): The list of `hou.Node` or `hou.NetworkMovableItem` to save.
        filepath (str): The full path to the file to save.
        transferAssets (bool): Whether to include custom HDA definitions.
    """
    print(f"Serializing {len(nodes)} nodes...")
    serializedData = serializeNodesToString(nodes, transferAssets)
    with open(filepath, "w") as f:
        f.write(serializedData)
    print(f"Successfully saved nodes to: {filepath}")

def loadNodesFromStringInteractive(serializedData, targetParent=None):
    """
    Provides a user-friendly, interactive workflow for loading nodes from a string.
    It handles context checking and automatic creation of parent nodes if needed.

    Args:
        serializedData (str): The node data string from serializeNodesToString().
        targetParent (hou.Node, optional): A specific parent node to load into.
            If None, it uses the current network editor's location.
    """
    if not serializedData:
        print("Error: No serialized data provided.")
        return

    # Mapping of required node contexts to the type of container node to create.
    CONTEXT_TO_NODE_TYPE = {
        'Sop': 'geo',
        'Object': None, # Cannot create /obj, handled as a special case.
        'Driver': 'ropnet',
        'ChopNet': 'chopnet',
        'Vop': 'vopnet'
    }

    # 1. Read metadata from the string to determine the required context.
    try:
        sBytes = serializedData.encode('utf-8')
        data = json.loads(bz2.decompress(base64.urlsafe_b64decode(sBytes)))
        requiredContext = data['context']
    except Exception as e:
        hou.ui.displayMessage(f"Failed to parse node data: {e}", severity=hou.severityType.Error)
        return

    # 2. Determine the target parent node and check its context.
    if targetParent and isinstance(targetParent, hou.Node):
        parentNode = targetParent
    else:
        # Default to the current location in the active network editor.
        try:
            pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
            parentNode = pane.pwd()
        except AttributeError: # No network editor open
            parentNode = hou.node('/obj') # Fallback to a sensible default

    currentContext = getChildContext(parentNode, hou.applicationVersion())

    # 3. If context doesn't match, ask user to create a new parent.
    if currentContext != requiredContext:
        nodeTypeName = CONTEXT_TO_NODE_TYPE.get(requiredContext)
        if not nodeTypeName:
            msg = f"Nodes require a '{requiredContext}' context, but you are in '{currentContext}'.\nCannot automatically create a suitable parent."
            hou.ui.displayMessage(msg, severity=hou.severityType.Error)
            return

        message = (f"These nodes require a '{requiredContext}' context, but your current location "
                   f"is a '{currentContext}' network.\n\nWould you like to create a new '{nodeTypeName}' "
                   "container here and load the nodes into it?")

        choice = hou.ui.displayMessage(message, buttons=("Create and Load", "Cancel"))

        if choice == 0: # Create and Load
            try:
                # Create the new container node inside the current directory.
                newParent = parentNode.createNode(nodeTypeName, "loaded_nodes")
                parentNode = newParent # The new node is now our target parent.
            except hou.OperationFailed as e:
                hou.ui.displayMessage(f"Failed to create new node: {e}", severity=hou.severityType.Error)
                return
        else: # Cancel
            print("Load cancelled due to context mismatch.")
            return

    # 4. Proceed with loading the nodes into the determined parent.
    try:
        print(f"Loading nodes into: {parentNode.path()}")
        newlyCreatedNodes = deserializeStringToNodes(serializedData, parentNode)
        if newlyCreatedNodes:
            # As a final step, arrange the new nodes for visibility.
            parentNode.layoutChildren(items=newlyCreatedNodes)
            print(f"Successfully loaded and arranged {len(newlyCreatedNodes)} items.")
    except Exception as e:
        hou.ui.displayMessage(f"An error occurred during load: {e}", severity=hou.severityType.Error)

# --- Example Usage ---
#
# To use this script, you can run the following code in Houdini's
# Python Source Editor or save it as a shelf tool.
#
# --- SAVE EXAMPLE ---
# 1. Select some nodes in a Houdini network editor.
# 2. Run this code to save the selection to a temporary file.
#
# try:
#     selectedNodes = hou.selectedNodes()
#     if selectedNodes:
#         # Use a temporary file for the example. In a real workflow, you would
#         # specify a permanent path or pass the string directly.
#         temp_dir = hou.homeHoudiniDirectory() + "/temp"
#         if not os.path.exists(temp_dir):
#             os.makedirs(temp_dir)
#         filepath = temp_dir + "/my_nodes.snippet"
#
#         saveNodesToFile(selectedNodes, filepath)
#     else:
#         hou.ui.displayMessage("Please select at least one node to save.",
#                               severity=hou.severityType.Warning)
# except Exception as e:
#     hou.ui.displayMessage(f"An error occurred during save: {e}",
#                           severity=hou.severityType.Error)
#
#
# --- LOAD EXAMPLE ---
# 1. This example reads the string from the file saved above.
# 2. It then calls the interactive load function with the string data.
#
# try:
#     # Path to the file saved in the previous step.
#     filepath = hou.homeHoudiniDirectory() + "/temp/my_nodes.snippet"
#     if os.path.exists(filepath):
#         with open(filepath, "r") as f:
#             serialized_data_from_file = f.read()
#
#         # Call the interactive loader with the data read from the file.
#         # You can optionally specify a parent node, e.g., hou.node('/obj').
#         loadNodesFromStringInteractive(serialized_data_from_file)
#     else:
#         hou.ui.displayMessage(f"Snippet file not found: {filepath}",
#                               severity=hou.severityType.Warning)
# except Exception as e:
#     hou.ui.displayMessage(f"An error occurred during load: {e}",
#                           severity=hou.severityType.Error)
#



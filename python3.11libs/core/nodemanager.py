import hou
from core.utils import linkParameters


class NodeManager:
    """
    Handles all direct interactions with Houdini nodes, keeping the UI
    class clean and decoupled from Houdini-specific operations.
    """

    SUPPORTED_NODE_TYPES = ["attribwrangle", "volumewrangle", "deformationwrangle", "opencl", "python"]
    # Defines which node kinds have a 'class' (Run Over) parameter for sub-categorization
    KINDS_WITH_RUNOVER = ["attribwrangle"]

    @staticmethod
    def nodesUnderCursor(eps=0.5):
        pane = hou.ui.paneTabUnderCursor()
        if pane and pane.type() == hou.paneTabType.NetworkEditor:
            networkPos = pane.cursorPosition()
            screenPos = pane.posToScreen(networkPos)

            topLeft = hou.Vector2(screenPos[0] - eps, screenPos[1] + eps)
            botRight = hou.Vector2(screenPos[0] + eps, screenPos[1] - eps)

            netItems = pane.networkItemsInBox(topLeft, botRight, for_drop=True, for_select=False)

            # Filters the output of hou.NetworkEditor.networkItemsInBox to return only nodes.
            return tuple(item[0] for item in netItems if isinstance(item, tuple) and len(item) > 1 and item[1] == 'node')

        return None

    @staticmethod
    def createControlParm(sourceParm=None):

        pane = hou.ui.paneTabUnderCursor()
        if not pane or pane.type() != hou.paneTabType.NetworkEditor:
            # hou.ui.displayMessage("A Network Editor pane must be under the cursor.",
            #                       severity=hou.severityType.Error)
            return

        if sourceParm is None:
            return

        nodes = NodeManager.nodesUnderCursor()
        if not nodes or len(nodes) > 1:
            return

        node = nodes[0]

        sourceParmTemplate = sourceParm.parmTemplate()
        name = sourceParmTemplate.name()
        # get existing list of parameters for the specified node
        g = node.parmTemplateGroup()
        if g.find(name):
            return

        clonedParmTemplate = sourceParmTemplate.clone()
        # append the new parameter to the list
        g.append(clonedParmTemplate)
        # apply changes
        node.setParmTemplateGroup(g)
        cparm = node.parm(clonedParmTemplate.name())
        linkParameters(cparm, sourceParm, True)

    @staticmethod
    def getCodeParmName(nodeType):
        """Returns the correct code parameter name for a given node type."""
        if nodeType == "python":
            return "python"
        if nodeType == "opencl":
            return "kernelcode"
        # Default for all VEX-based wrangles
        return "snippet"

    def findTargetNode(self):
        """
        Finds a suitable node to interact with based on user selection or display flag.

        Returns:
            hou.Node: The target Houdini node, or None if no suitable node is found.
        """
        nodeToCheck = None
        selectedNodes = hou.selectedNodes()

        if len(selectedNodes) > 1:
            hou.ui.displayMessage("Please select only one node.", severity=hou.severityType.Error)
            return None

        if len(selectedNodes) == 1 and selectedNodes[0].type().name() in self.SUPPORTED_NODE_TYPES:
            nodeToCheck = selectedNodes[0]
        else:
            try:
                pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
                if pane:
                    displayNode = pane.pwd().displayNode()
                    if displayNode and displayNode.type().name() in self.SUPPORTED_NODE_TYPES:
                        nodeToCheck = displayNode
            except hou.Error:
                pass  # Ignore if no network editor is open

        if not nodeToCheck:
            hou.ui.displayMessage("Could not find a supported node.", severity=hou.severityType.Error)
            return None

        return nodeToCheck

    def grabDataFromNode(self, node):
        """
        Extracts relevant data from a given Houdini node.

        Args:
            node (hou.Node): The node to extract data from.

        Returns:
            dict: A dictionary containing the node's data (kind, name, code, runOver).
        """
        if not node:
            return None

        nodeType = node.type().name()
        hasRunover = nodeType in self.KINDS_WITH_RUNOVER
        code = ""

        # Special handling for OpenCL node
        if nodeType == "opencl":
            if node.parm("usecode") and node.parm("usecode").eval() == 1:
                codeParm = node.parm("kernelcode")
                if codeParm:
                    code = codeParm.eval()
        else:
            # Standard handling for other node types
            codeParmName = self.getCodeParmName(nodeType)
            codeParm = node.parm(codeParmName)
            if codeParm:
                code = codeParm.eval()

        data = {
            "kind": nodeType,
            "name": node.name(),
            "code": code,
            "runOver": node.parm("class").eval() if hasRunover and node.parm("class") else -1
        }
        return data

    def createNodeFromSnippet(self, snippet, screenPosTuple=None):
        """
        Creates a new Houdini node from a snippet object.

        Args:
            snippet (Snippet): The snippet to create the node from.
            screenPosTuple (tuple, optional): A (x, y) tuple of the global mouse position. Defaults to None.
        """
        try:
            pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
            parentNode = pane.pwd() if pane else hou.node('/obj') or hou.root()
            newNode = parentNode.createNode(snippet.kind, node_name=snippet.name.replace(" ", "_").lower())

            self.applyDataToNode(newNode, snippet.expression, snippet)

            if pane and screenPosTuple:
                # Position the new node under the cursor
                screenVec = hou.Vector2(screenPosTuple)
                networkPos = pane.posFromScreen(screenVec)
                newNode.setPosition(networkPos)
                newNode.move(-newNode.size() / 2.0)

        except Exception as e:
            hou.ui.displayMessage(f"An error occurred while creating node: {e}", severity=hou.severityType.Error)

    def applyDataToNode(self, node, code, snippet):
        """
        Sets the parameters on a target node based on snippet data.

        Args:
            node (hou.Node): The node to modify.
            code (str): The code to apply to the node.
            snippet (Snippet): The source snippet containing metadata.
        """
        nodeType = node.type().name()
        codeParmName = self.getCodeParmName(nodeType)

        if node.parm(codeParmName):
            node.parm(codeParmName).set(code)

        # Special handling for OpenCL to ensure the code is active
        if nodeType == "opencl" and node.parm("usecode"):
            node.parm("usecode").set(1)

        if node.parm("class") and snippet.runover != "N/A":
            DEFAULT_NODE_TYPES = ["Detail", "Primitives", "Points", "Vertices", "Numbers"]
            if snippet.runover in DEFAULT_NODE_TYPES:
                runOverIndex = DEFAULT_NODE_TYPES.index(snippet.runover)
                node.parm("class").set(runOverIndex)


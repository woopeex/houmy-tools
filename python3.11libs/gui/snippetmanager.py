# HouMy Tools - Snippet Manager

import hou
import json
import os
import uuid
import re
import sys

from hutil.Qt import QtWidgets, QtGui, QtCore

from core.settings import Settings
from core.snippetiomanager import Snippet, SnippetIOManager
from core.nodemanager import NodeManager
from gui.syntaxhighlighter import SyntaxHighlighter
from gui.codeeditor import CodeEditor


class NamingValidator(QtGui.QValidator):
    """
    Validator that only accepts:
      - letters (a-z, A-Z)
      - digits (0-9)
      - whitespace
      - underscore (_)
      - hyphen (-)
    """

    _pattern = re.compile(r'^[A-Za-z0-9_\-\s]*$')

    def validate(self, s: str, pos: int):
        if self._pattern.fullmatch(s) or s == "":
            return (QtGui.QValidator.Acceptable, s, pos)
        return (QtGui.QValidator.Invalid, s, pos)

    def fixup(self, s: str) -> str:
        """Remove all disallowed characters."""
        return "".join(ch for ch in s if self._pattern.fullmatch(ch))


class RecursiveFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Keeps a row visible if the row itself matches OR *any* of its descendants match.
    Uses substring (case-insensitive) matching against column 0 text.
    """

    def filterAcceptsRow(self, sourceRow, sourceParent):
        model = self.sourceModel()
        keyCol = self.filterKeyColumn()
        idx = model.index(sourceRow, keyCol, sourceParent)
        if not idx.isValid():
            return False

        needle = self.filterRegularExpression().pattern()
        if not needle:
            return True

        text = str(model.data(idx, QtCore.Qt.DisplayRole) or "")
        if needle.casefold() in text.casefold():
            return True

        childCount = model.rowCount(idx)
        for i in range(childCount):
            if self.filterAcceptsRow(i, idx):
                return True

        return False


class SnippetManager(QtWidgets.QWidget):
    DEFAULT_NODE_TYPES = [
        "Detail",
        "Primitives",
        "Points",
        "Vertices",
        "Numbers",
    ]

    KIND_DISPLAY_NAMES = {
        "Attribute Wrangle": "attribwrangle",
        "Volume Wrangle": "volumewrangle",
        "Deformation Wrangle": "deformationwrangle",
        "Python": "python",
        "OpenCL": "opencl"
    }

    def __init__(self, parent=None):
        """Initializes the Snippet Manager UI."""
        super(SnippetManager, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)

        self.setGeometry(500, 300, 550, 850)
        self.setWindowTitle('Snippet Manager')

        self.splitter = None
        self.snippetEdit = None
        self.typeCombo = None
        self.kindCombo = None
        self.runOverLabel = None
        self.nameEdit = None
        self.proxyModel = None
        self.snippetPreview = None
        self.treeView = None
        self.databasePath = None

        self.snippetDatabase = None
        self.previewHighlighter = None
        self.snippetEditHighlighter = None

        self.model = QtGui.QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Name"])

        self.nodeManager = NodeManager()

        mainLayout = QtWidgets.QVBoxLayout(self)
        mainLayout.setContentsMargins(1, 1, 1, 1)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        mainLayout.addWidget(separator)

        self.tabs = QtWidgets.QTabWidget()
        mainLayout.addWidget(self.tabs)

        self.createSavedSnippetsTab()
        self.createNewSnippetTab()

        self.treeView.expandAll()

        self.settings = Settings()
        self.ioManager = SnippetIOManager()

        self.onKindChanged()

    def createSavedSnippetsTab(self):
        """Creates the tab containing the search, tree, and snippet preview."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        searchInput = QtWidgets.QLineEdit()
        searchInput.setPlaceholderText("Search in tree...")
        layout.addWidget(searchInput)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        self.treeView = QtWidgets.QTreeView()
        self.treeView.setHeaderHidden(True)
        self.treeView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.treeView.customContextMenuRequested.connect(self.onTreeViewContextMenu)

        detailsGroup = QtWidgets.QGroupBox("Snippet Details")
        detailsLayout = QtWidgets.QVBoxLayout(detailsGroup)
        detailsLayout.setContentsMargins(3, 3, 3, 3)
        detailsLayout.setSpacing(5)

        self.snippetPreview = CodeEditor()
        self.snippetPreview.setReadOnly(True)
        self.previewHighlighter = SyntaxHighlighter(self.snippetPreview.document())

        applyBtn = QtWidgets.QPushButton("Apply to Selected Node")
        applyBtn.clicked.connect(self.onApplyButtonPressed)

        detailsLayout.addWidget(self.snippetPreview)
        detailsLayout.addWidget(applyBtn)

        self.splitter.addWidget(self.treeView)
        self.splitter.addWidget(detailsGroup)
        self.splitter.setSizes([400, 400])

        self.treeView.clicked.connect(self.onTreeViewClick)
        self.treeView.doubleClicked.connect(self.onTreeViewDoubleClick)

        layout.addWidget(self.splitter)
        self.setupFilterProxy()
        searchInput.textChanged.connect(self.onSearchChanged)
        self.tabs.addTab(tab, "Saved Snippets")

    def createNewSnippetTab(self):
        """Creates the tab for adding a new snippet."""
        w = QtWidgets.QWidget()
        validator = NamingValidator()

        self.nameEdit = QtWidgets.QLineEdit(w)
        self.nameEdit.setValidator(validator)

        self.kindCombo = QtWidgets.QComboBox(w)
        self.kindCombo.addItems(self.KIND_DISPLAY_NAMES.keys())
        self.kindCombo.currentIndexChanged.connect(self.onKindChanged)

        self.typeCombo = QtWidgets.QComboBox(w)
        self.typeCombo.addItems(list(SnippetManager.DEFAULT_NODE_TYPES))
        self.typeCombo.setCurrentIndex(self.typeCombo.findText("Points"))

        self.runOverLabel = QtWidgets.QLabel("Run Over")

        form = QtWidgets.QFormLayout()
        form.addRow("Name", self.nameEdit)
        form.addRow("Kind", self.kindCombo)
        form.addRow(self.runOverLabel, self.typeCombo)

        self.snippetEdit = CodeEditor()
        self.snippetEditHighlighter = SyntaxHighlighter(self.snippetEdit.document())

        snippetGroup = QtWidgets.QGroupBox("Snippet", w)
        vSnip = QtWidgets.QVBoxLayout(snippetGroup)
        vSnip.addWidget(self.snippetEdit)

        grabBtn = QtWidgets.QPushButton("Grab Snippet from Node", w)
        saveBtn = QtWidgets.QPushButton("Save Snippet", w)
        grabBtn.clicked.connect(self.onGrabButtonPressed)
        saveBtn.clicked.connect(self.onSaveButtonPressed)

        root = QtWidgets.QVBoxLayout(w)
        root.addLayout(form)
        root.addWidget(snippetGroup, 1)
        root.addWidget(grabBtn)
        root.addWidget(saveBtn)
        w.setLayout(root)
        self.tabs.addTab(w, "New Snippet")

    def setupFilterProxy(self):
        """Wrap the source model with a recursive filter proxy and set it on the view."""
        self.proxyModel = RecursiveFilterProxyModel(self)
        self.proxyModel.setFilterKeyColumn(0)
        self.proxyModel.setFilterRegularExpression(QtCore.QRegularExpression(""))
        self.proxyModel.setSourceModel(self.model)
        self.treeView.setModel(self.proxyModel)
        self.treeView.expandAll()

    def loadSnippets(self, existing=False):
        """Loads snippets from the database and populates the tree view with a node-kind-based hierarchy."""
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Name"])

        if not existing:
            self.snippetDatabase = self.ioManager.loadSnippetsFromDatabase()

        for snippet in self.snippetDatabase.values():
            path = ""
            invertedKindMap = {v: k for k, v in self.KIND_DISPLAY_NAMES.items()}
            rootCategory = invertedKindMap.get(snippet.kind, snippet.kind.capitalize())

            if snippet.kind in self.nodeManager.KINDS_WITH_RUNOVER:
                path = "/".join([rootCategory, snippet.runover, snippet.name])
            else:
                path = "/".join([rootCategory, snippet.name])

            if path:
                self.addPath(path, snippet.id)

        self.treeView.expandAll()

    def onKindChanged(self):
        """Updates the UI when the user changes the snippet kind in the 'New Snippet' tab."""
        if not self.kindCombo: return

        selectedDisplayText = self.kindCombo.currentText()
        selectedKind = self.KIND_DISPLAY_NAMES.get(selectedDisplayText)

        self.snippetEditHighlighter.setLanguage(selectedKind)

        isVisible = selectedKind in self.nodeManager.KINDS_WITH_RUNOVER

        self.runOverLabel.setVisible(isVisible)
        self.typeCombo.setVisible(isVisible)

        if not isVisible:
            self.typeCombo.setCurrentIndex(-1)
        else:
            pointsIndex = self.typeCombo.findText("Points")
            if pointsIndex != -1:
                self.typeCombo.setCurrentIndex(pointsIndex)

    def onSearchChanged(self, text):
        """Update the recursive filter."""
        regex = QtCore.QRegularExpression(QtCore.QRegularExpression.escape(text))
        self.proxyModel.setFilterRegularExpression(regex)
        self.treeView.expandAll() if text.strip() else self.treeView.collapseAll()

    def onTreeViewContextMenu(self, point):
        """Creates and shows the right-click context menu for the tree view."""
        index = self.treeView.indexAt(point)
        if not index.isValid(): return
        sourceIndex = self.proxyModel.mapToSource(index)
        itemId = sourceIndex.data(role=QtCore.Qt.UserRole + 1)
        if itemId is None: return

        menu = QtWidgets.QMenu()
        deleteAction = menu.addAction("Delete")
        deleteAction.triggered.connect(lambda: self.onDeleteSnippet(itemId))
        menu.exec_(self.treeView.viewport().mapToGlobal(point))

    def onDeleteSnippet(self, itemId):
        """Deletes a snippet after user confirmation."""
        snippet = self.snippetDatabase.get(itemId)
        if not snippet: return

        reply = QtWidgets.QMessageBox.question(self, 'Delete Snippet',
                                               f"Are you sure you want to delete '{snippet.name}'?",
                                               QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                               QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            del self.snippetDatabase[itemId]
            self.ioManager.saveSnippetsToDatabase(self.snippetDatabase)
            self.loadSnippets(existing=True)
            self.clearPreviewFields()
            hou.ui.displayMessage(f"Snippet '{snippet.name}' deleted.", severity=hou.severityType.Message)

    def clearPreviewFields(self):
        """Clears all fields in the 'Saved Snippets' preview area."""
        self.snippetPreview.clear()

    def onTreeViewClick(self, index):
        """Handles single-click events on the tree view to preview a snippet."""
        if not index.isValid():
            self.clearPreviewFields()
            return
        sourceIndex = self.proxyModel.mapToSource(index)
        itemId = sourceIndex.data(role=QtCore.Qt.UserRole + 1)
        if itemId is None:
            self.clearPreviewFields()
            return
        snippet = self.snippetDatabase.get(itemId)
        if snippet:
            self.snippetPreview.setPlainText(snippet.expression)
            self.previewHighlighter.setLanguage(snippet.kind)

    def onTreeViewDoubleClick(self, index):
        """Handles double-click events to create a new node, with confirmation."""
        if not index.isValid(): return
        sourceIndex = self.proxyModel.mapToSource(index)
        itemId = sourceIndex.data(role=QtCore.Qt.UserRole + 1)
        if itemId is None: return
        snippet = self.snippetDatabase.get(itemId)
        if not snippet: return

        reply = QtWidgets.QMessageBox.question(self, 'Confirm Action',
                                               f"Create a new '{snippet.kind}' node with the '{snippet.name}' snippet?",
                                               QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                               QtWidgets.QMessageBox.StandardButton.Yes)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            cursorPos = QtGui.QCursor.pos()
            posTuple = (cursorPos.x(), cursorPos.y())
            self.nodeManager.createNodeFromSnippet(snippet, screenPosTuple=posTuple)

    def onApplyButtonPressed(self):
        """Applies the currently previewed snippet to the selected node."""
        currentIndex = self.treeView.currentIndex()
        if not currentIndex.isValid():
            hou.ui.displayMessage("Please select a snippet to apply.", severity=hou.severityType.Warning)
            return
        sourceIndex = self.proxyModel.mapToSource(currentIndex)
        itemId = sourceIndex.data(role=QtCore.Qt.UserRole + 1)
        if itemId is None:
            hou.ui.displayMessage("Please select a valid snippet, not a category folder.",
                                  severity=hou.severityType.Warning)
            return
        snippet = self.snippetDatabase.get(itemId)
        if not snippet: return

        targetNode = self.nodeManager.findTargetNode()
        if not targetNode: return

        if targetNode.type().name() != snippet.kind:
            reply = QtWidgets.QMessageBox.question(self, 'Confirm Mismatch',
                                                   f"The selected node ('{targetNode.type().name()}') does not match the snippet kind ('{snippet.kind}').\n\nApply anyway?",
                                                   QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                                   QtWidgets.QMessageBox.StandardButton.No)
            if reply == QtWidgets.QMessageBox.StandardButton.No: return

        codeParmName = self.nodeManager.getCodeParmName(targetNode.type().name())
        if not targetNode.parm(codeParmName):
            hou.ui.displayMessage(f"Selected node '{targetNode.name()}' has no suitable code parameter.",
                                  severity=hou.severityType.Error)
            return

        currentCode = targetNode.parm(codeParmName).eval().strip()
        finalCode = snippet.expression
        actionMessage = "Applied"
        if currentCode:
            msgBox = QtWidgets.QMessageBox(self)
            msgBox.setWindowTitle("Confirm Action")
            msgBox.setText(f"The node '{targetNode.name()}' already contains code.")
            msgBox.setInformativeText("How would you like to apply the new snippet?")
            replaceButton = msgBox.addButton("Replace", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            appendButton = msgBox.addButton("Append", QtWidgets.QMessageBox.ButtonRole.ActionRole)
            cancelButton = msgBox.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)
            msgBox.exec_()
            clickedButton = msgBox.clickedButton()
            if clickedButton == replaceButton:
                actionMessage = "Replaced code on"
            elif clickedButton == appendButton:
                commentChar = "#" if targetNode.type().name() == "python" else "//"
                finalCode = f"{currentCode}\n\n{commentChar} --- Appended: {snippet.name} ---\n{snippet.expression}"
                actionMessage = "Appended snippet to"
            else:
                return

        self.nodeManager.applyDataToNode(targetNode, finalCode, snippet)
        hou.ui.displayMessage(f"{actionMessage} '{targetNode.name()}'.", severity=hou.severityType.Message)

    def onGrabButtonPressed(self):
        """Grabs code from a selected or display-flagged node."""
        nodeToCheck = self.nodeManager.findTargetNode()
        if not nodeToCheck: return

        data = self.nodeManager.grabDataFromNode(nodeToCheck)
        if not data: return

        self.nameEdit.setText(data["name"])
        self.snippetEdit.setPlainText(data["code"])

        invertedKindMap = {v: k for k, v in self.KIND_DISPLAY_NAMES.items()}
        displayKindName = invertedKindMap.get(data["kind"], "")

        kindIndex = self.kindCombo.findText(displayKindName)
        if kindIndex != -1:
            self.kindCombo.setCurrentIndex(kindIndex)

        if data["kind"] in self.nodeManager.KINDS_WITH_RUNOVER:
            self.typeCombo.setCurrentIndex(data["runOver"])

    def onSaveButtonPressed(self):
        """Saves the current snippet in the form to the database."""
        name = self.nameEdit.text()
        expression = self.snippetEdit.toPlainText()
        selectedDisplayText = self.kindCombo.currentText()
        snippetKind = self.KIND_DISPLAY_NAMES.get(selectedDisplayText)
        snippetType = self.typeCombo.currentText() if self.typeCombo.isVisible() else "N/A"

        s = Snippet(
            str(uuid.uuid4()),
            name,
            snippetType,
            expression,
            snippetKind
        )
        self.snippetDatabase[s.id] = s
        if self.ioManager.saveSnippetsToDatabase(self.snippetDatabase):
            self.loadSnippets(True)
            hou.ui.displayMessage("Successfully saved!", severity=hou.severityType.Message)

    def addPath(self, path, itemId=None, sep="/"):
        """Create (or reuse) items along a 'folder-like' path."""
        if not path: return None
        parts = [p.strip() for p in path.split(sep) if p.strip()]
        parent = self.model.invisibleRootItem()
        for name in parts:
            found = None
            for r in range(parent.rowCount()):
                candidate = parent.child(r, 0)
                if candidate and candidate.text().casefold() == name.casefold():
                    found = candidate
                    break
            if found is None:
                found = QtGui.QStandardItem(name)
                found.setFlags(found.flags() & ~QtCore.Qt.ItemIsEditable)
                parent.appendRow([found])
            parent = found
        if parts and itemId:
            parent.setData(itemId, role=QtCore.Qt.UserRole + 1)
        return parent

    def addPathsFromText(self, textBlock, itemId=None, sep="/"):
        """Convenience: add multiple paths separated by newlines."""
        for line in (textBlock or "").splitlines():
            line = line.strip()
            if line: self.addPath(line, itemId, sep)

    def showEvent(self, event):
        """Loads settings and data when the window is shown."""
        super(SnippetManager, self).showEvent(event)
        value = self.settings.loadValue("snippet_manager/window_geometry")
        if value: self.restoreGeometry(bytes.fromhex(value))
        splitterValue = self.settings.loadValue("snippet_manager/splitter_state")
        if splitterValue and self.splitter: self.splitter.restoreState(bytes.fromhex(splitterValue))
        self.loadSnippets()

    def closeEvent(self, event):
        """Saves settings when the window is closed."""
        super(SnippetManager, self).closeEvent(event)
        self.settings.saveValue("snippet_manager", "window_geometry",
                                bytes(self.saveGeometry().toHex()).decode('ascii'))
        if self.splitter:
            splitterState = bytes(self.splitter.saveState().toHex()).decode('ascii')
            self.settings.saveValue("snippet_manager", "splitter_state", splitterState)

    def eventFilter(self, source, event):
        """Generic event filter."""
        super(SnippetManager, self).eventFilter(source, event)
        return QtWidgets.QWidget.eventFilter(self, source, event)


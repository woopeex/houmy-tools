from hutil.Qt import QtWidgets, QtGui, QtCore


class LineNumberArea(QtWidgets.QWidget):
    """This widget displays the line numbers for the CodeEditor."""

    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        """Returns the preferred size of the line number area."""
        return QtCore.QSize(self.codeEditor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        """Paints the line numbers."""
        self.codeEditor.lineNumberAreaPaintEvent(event)


class CodeEditor(QtWidgets.QPlainTextEdit):
    """
    A custom QPlainTextEdit that includes a line number area and current line highlighting.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)

        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

        font = QtGui.QFont()
        """
        Not sure about the default font, need to investigate!
        """
        font.setFamily("Courier New")
        font.setPointSize(12)
        self.setFont(font)

        metrics = QtGui.QFontMetrics(self.font())
        self.setTabStopDistance(metrics.horizontalAdvance(' ') * 4)

    def keyPressEvent(self, event):
        """Overrides the default key press event to handle auto-pairing, indentation, and custom tab behavior."""
        cursor = self.textCursor()
        text = event.text()

        # Handle Enter key for auto-indentation
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            current_block = cursor.block()
            line_text = current_block.text()

            leading_whitespace = ""
            for char in line_text:
                if char.isspace():
                    leading_whitespace += char
                else:
                    break

            # Insert a newline and the indentation of the current line
            cursor.insertText("\n" + leading_whitespace)

            # If the previous line ended with an opening brace, add an extra indent
            if line_text.strip().endswith('{'):
                cursor.insertText("    ")

            if line_text.strip().endswith(':'):
                cursor.insertText("    ")

            self.setTextCursor(cursor)
            return

        # Handle Tab key for indentation
        if event.key() == QtCore.Qt.Key_Tab:
            cursor.insertText("    ")
            return

        # Auto-complete curly braces
        if text == '{':
            # Get indentation of the current line to apply to the new lines
            current_block = cursor.block()
            line_text = current_block.text()

            leading_whitespace = ""
            for char in line_text:
                if char.isspace():
                    leading_whitespace += char
                else:
                    break

            cursor.beginEditBlock()
            cursor.insertText("{\n")
            cursor.insertText(leading_whitespace + "    ")
            cursor_pos_to_keep = cursor.position()
            cursor.insertBlock()
            cursor.insertText(leading_whitespace + "}")
            cursor.setPosition(cursor_pos_to_keep)
            cursor.endEditBlock()

            self.setTextCursor(cursor)
            return

            # Auto-complete quotes
        if text == '"' or text == "'":
            cursor.beginEditBlock()
            cursor.insertText(text + text)
            cursor.movePosition(QtGui.QTextCursor.PreviousCharacter)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return

        # For all other key presses, fall back to the default behavior
        super().keyPressEvent(event)

    def lineNumberAreaWidth(self):
        """Calculates the width required for the line number area."""
        digits = 1
        count = max(1, self.blockCount())
        while count >= 10:
            count //= 10
            digits += 1
        space = 8 + self.fontMetrics().horizontalAdvance('10') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        """Sets the left margin of the editor to make space for the line numbers."""
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        """Updates the line number area when the editor is scrolled."""
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        """Handles the resize event to adjust the line number area's geometry."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QtCore.QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def highlightCurrentLine(self):
        """Highlights the line where the cursor is currently located."""
        extraSelections = []
        if not self.isReadOnly():
            selection = QtWidgets.QTextEdit.ExtraSelection()
            lineColor = QtGui.QColor(QtCore.Qt.black).lighter(160)
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)

    def lineNumberAreaPaintEvent(self, event):
        """The actual painting logic for the line numbers."""
        painter = QtGui.QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QtGui.QColor("#000000"))  # A light grey background

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(QtCore.Qt.gray)
                painter.drawText(0, int(top), self.lineNumberArea.width() - 4, self.fontMetrics().height(),
                                 QtCore.Qt.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            blockNumber += 1


from hutil.Qt import QtGui, QtCore


class SyntaxHighlighter(QtGui.QSyntaxHighlighter):
    """A dynamic syntax highlighter for VEX and Python languages."""

    def __init__(self, parent=None):
        super(SyntaxHighlighter, self).__init__(parent)

        self.highlightingRules = []
        self.language = "vex"

        # --- VEX Formats (Original Colors Preserved) ---
        self.vexFormats = {
            'keyword': self.createTextFormat("#6697be", bold=True),
            'dataType': self.createTextFormat("#87c3d8", bold=True),
            'function': self.createTextFormat("#7c7cb0", bold=True),
            'userFunction': self.createTextFormat("#7c7cb0", bold=True),
            'attribute': self.createTextFormat("#c1be90", bold=True),
            'string': self.createTextFormat("#6a9955", bold=True),
            'preprocessor': self.createTextFormat("#b5cea8"),
            'comment': self.createTextFormat("#a8aa9f"),
        }

        # --- Python Formats ---
        self.pythonFormats = {
            'keyword': self.createTextFormat("#C586C0", bold=True),
            'built_in': self.createTextFormat("#499CD6"),
            'self': self.createTextFormat("#499CD6", bold=True),
            'string': self.createTextFormat("#CE9178"),
            'numbers': self.createTextFormat("#B5CEA8"),
            'function': self.createTextFormat("#DCDCAA"),
            'comment': self.createTextFormat("#6A9955", italic=True),
        }

        # --- Multi-line Comment/String Formats ---
        self.vexMultiLineFormat = self.createTextFormat("#a8aa9f")
        self.pythonMultiLineFormat = self.createTextFormat("#CE9178")

        # --- VEX Keywords & Functions ---
        self.vexKeywords = ["if", "else", "for", "while", "do", "break", "continue", "return", "foreach", "in",
                            "struct", "const", "export", "import", "function"]
        self.vexDataTypes = ["int", "float", "vector", "vector2", "vector4", "matrix", "matrix3", "string", "void",
                             "pvector", "nvector", "cvector", "hvector", "dict", "array"]
        self.vexFunctions = ["abs", "addpoint", "addprim", "append", "array", "cos", "degrees", "dot", "exp", "fit",
                             "floor", "getattrib", "getbbox_center", "haspointattrib", "length", "lerp", "log", "match",
                             "max", "min", "noise", "normalize", "point", "pow", "prim", "printf", "radians", "rand",
                             "removepoint", "setpointattrib", "sin", "sqrt", "tan", "vtransform", "xnoise"]

        # --- Python Keywords & Built-ins ---
        self.pythonKeywords = ['and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else',
                               'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda',
                               'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield', 'None', 'True',
                               'False']
        self.pythonBuiltins = ['abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'filter', 'float', 'int', 'len',
                               'list', 'map', 'max', 'min', 'range', 'str', 'sum', 'tuple', 'type', 'zip']

        # --- Multi-line Expressions ---
        self.vexCommentStart = QtCore.QRegularExpression("/\\*")
        self.vexCommentEnd = QtCore.QRegularExpression("\\*/")
        self.pyStringStart_single = QtCore.QRegularExpression("'''")
        self.pyStringEnd_single = QtCore.QRegularExpression("'''")
        self.pyStringStart_double = QtCore.QRegularExpression('"""')
        self.pyStringEnd_double = QtCore.QRegularExpression('"""')

        self.setLanguage("vex")

    def createTextFormat(self, color, bold=False, italic=False):
        """Helper function to create a QTextCharFormat."""
        textFormat = QtGui.QTextCharFormat()
        textFormat.setForeground(QtGui.QColor(color))
        if bold:
            textFormat.setFontWeight(QtGui.QFont.Bold)
        if italic:
            textFormat.setFontItalic(True)
        return textFormat

    def setLanguage(self, language):
        """Sets the syntax language, rebuilds the rules, and forces a re-highlight."""
        self.language = "python" if language == "python" else "vex"
        self.buildRules()
        self.rehighlight()

    def buildRules(self):
        """Constructs the list of highlighting rules based on the current language."""
        self.highlightingRules = []

        if self.language == "python":
            # Rule for functions, allowing optional whitespace before the parenthesis
            self.highlightingRules.append(
                (QtCore.QRegularExpression("\\b[A-Za-z0-9_]+(?=\\s*\\()"), self.pythonFormats['function']))

            # Specific rules (applied second to overwrite the general rule where needed)
            self.highlightingRules.extend(
                [(QtCore.QRegularExpression(f"\\b{word}\\b"), self.pythonFormats['keyword']) for word in
                 self.pythonKeywords])
            self.highlightingRules.extend(
                [(QtCore.QRegularExpression(f"\\b{word}\\b"), self.pythonFormats['built_in']) for word in
                 self.pythonBuiltins])
            self.highlightingRules.append((QtCore.QRegularExpression("\\bself\\b"), self.pythonFormats['self']))

            # Remaining rules
            self.highlightingRules.append((QtCore.QRegularExpression("\".*\""), self.pythonFormats['string']))
            self.highlightingRules.append((QtCore.QRegularExpression("'.*'"), self.pythonFormats['string']))
            self.highlightingRules.append(
                (QtCore.QRegularExpression("\\b[0-9]+\\.?[0-9]*\\b"), self.pythonFormats['numbers']))
            self.highlightingRules.append((QtCore.QRegularExpression("#[^\n]*"), self.pythonFormats['comment']))
        else:  # VEX
            # Keywords and Data Types
            self.highlightingRules.extend(
                [(QtCore.QRegularExpression(f"\\b{word}\\b"), self.vexFormats['keyword']) for word in self.vexKeywords])
            self.highlightingRules.extend(
                [(QtCore.QRegularExpression(f"\\b{word}\\b"), self.vexFormats['dataType']) for word in
                 self.vexDataTypes])

            # Built-in Functions
            self.highlightingRules.extend(
                [(QtCore.QRegularExpression(f"\\b{word}\\b"), self.vexFormats['function']) for word in
                 self.vexFunctions])

            # User-defined Functions (excluding reserved words), allowing optional whitespace
            all_reserved = self.vexKeywords + self.vexDataTypes + self.vexFunctions
            negative_lookahead = f"\\b(?!({'|'.join(all_reserved)})\\b)[A-Za-z0-9_]+(?=\\s*\\()"
            self.highlightingRules.append(
                (QtCore.QRegularExpression(negative_lookahead), self.vexFormats['userFunction']))

            # Attributes, Strings, Preprocessor, Comments
            self.highlightingRules.append((QtCore.QRegularExpression("@[A-Za-z0-9_]+"), self.vexFormats['attribute']))
            self.highlightingRules.append((QtCore.QRegularExpression("\".*\""), self.vexFormats['string']))
            self.highlightingRules.append((QtCore.QRegularExpression("'.*'"), self.vexFormats['string']))
            self.highlightingRules.append((QtCore.QRegularExpression("#[^\n]*"), self.vexFormats['preprocessor']))
            self.highlightingRules.append((QtCore.QRegularExpression("//[^\n]*"), self.vexFormats['comment']))

    def highlightBlock(self, text):
        """Highlights a block of text based on the current language."""
        for pattern, format in self.highlightingRules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

        # Handle multi-line logic
        if self.language == "python":
            self.setCurrentBlockState(0)
            self.applyMultiLineRule(text, self.pyStringStart_single, self.pyStringEnd_single, 1,
                                    self.pythonMultiLineFormat)
            if self.currentBlockState() != 1:
                self.applyMultiLineRule(text, self.pyStringStart_double, self.pyStringEnd_double, 2,
                                        self.pythonMultiLineFormat)
        else:  # VEX
            self.applyMultiLineRule(text, self.vexCommentStart, self.vexCommentEnd, 3, self.vexMultiLineFormat)

    def applyMultiLineRule(self, text, startExpression, endExpression, state, format):
        """Generic logic to apply multi-line formatting."""
        startIndex = 0

        if self.previousBlockState() == state:
            startIndex = 0
        else:
            match = startExpression.match(text)
            startIndex = match.capturedStart()

        while startIndex >= 0:
            match = endExpression.match(text, startIndex)
            endIndex = match.capturedStart()

            if endIndex == -1:
                self.setCurrentBlockState(state)
                commentLength = len(text) - startIndex
            else:
                self.setCurrentBlockState(0)
                commentLength = endIndex - startIndex + match.capturedLength()

            self.setFormat(startIndex, commentLength, format)
            startIndex = startExpression.match(text, startIndex + commentLength).capturedStart()


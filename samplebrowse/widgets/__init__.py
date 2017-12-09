import re
from .advsplitter import *
from .delegates import *
from PyQt5 import QtCore, QtWidgets


class ColorLineEdit(QtWidgets.QLineEdit):
    editBtnClicked = QtCore.pyqtSignal()
    def __init__(self, *args, **kwargs):
        QtWidgets.QLineEdit.__init__(self, *args, **kwargs)
        self.editBtn = QtWidgets.QPushButton('...', self)
        self.editBtn.setCursor(QtCore.Qt.ArrowCursor)
        self.editBtn.clicked.connect(self.editBtnClicked.emit)

    def resizeEvent(self, event):
        size = self.height() - 8
        self.editBtn.resize(size, size)
        self.editBtn.move(self.width() - size - 4, (self.height() - size) / 2)


class DropTimer(QtCore.QTimer):
    expandIndex = QtCore.pyqtSignal(object)
    def __init__(self):
        QtCore.QTimer.__init__(self)
        self.setInterval(500)
        self.setSingleShot(True)
        self.currentIndex = None
        self.timeout.connect(self.expandEmit)

    def expandEmit(self):
        if self.currentIndex:
            self.expandIndex.emit(self.currentIndex)
            self.currentIndex = None
#        self.expandIndex.emit(self.currentIndex) if self.currentIndex else None

    def start(self, index):
        if not index:
            self.stop()
            return
        if index == self.currentIndex:
            return
        self.currentIndex = index
        QtCore.QTimer.start(self)

class TreeViewWithLines(QtWidgets.QTreeView):
    def drawRow(self, painter, option, index):
        QtWidgets.QTreeView.drawRow(self, painter, option, index)
        painter.setPen(QtCore.Qt.lightGray)
        y = option.rect.y()
        painter.save()
        for sectionId in range(self.header().count()):
#            x = self.header().sectionSize(sectionId)
            painter.drawLine(0, y, 0, y + option.rect.height())
            painter.translate(self.header().sectionSize(sectionId), 0)
        painter.restore()
#        painter.drawLine(0, y + option.rect.height(), option.rect.width(), y + option.rect.height())


class DbTreeView(TreeViewWithLines):
    samplesAddedToTag = QtCore.pyqtSignal(object, str)
    samplesImported = QtCore.pyqtSignal(object, object)
    def __init__(self, main, *args, **kwargs):
        QtWidgets.QTreeView.__init__(self, *args, **kwargs)
        self.main = main
        self.setAcceptDrops(True)
        #something is wrong with setAutoExpandDelay, we use a custom QTimer
        self.dropTimer = QtCore.QTimer()
        self.dropTimer.setInterval(500)
        self.dropTimer.setSingleShot(True)
        self.dropTimer.timeout.connect(self.expandDrag)
        self.currentTagIndex = None

    def expandDrag(self):
        if not (self.currentTagIndex and self.currentTagIndex.isValid()):
            return
        if not self.isExpanded(self.currentTagIndex):
            self.expand(self.currentTagIndex)
        else:
            self.collapse(self.currentTagIndex)

    def dragEnterEvent(self, event):
        formats = event.mimeData().formats()
        if 'application/x-qabstractitemmodeldatalist' in formats:
            event.accept()
            currentTagIndex = self.indexAt(event.pos())
            if currentTagIndex.isValid() and currentTagIndex not in (self.model().index(0, 0), self.model().index(0, 1)):
                self.currentTagIndex = currentTagIndex
                self.dropTimer.start()
        elif 'text/uri-list' in formats:
            event.accept()

    def dragMoveEvent(self, event):
        currentTagIndex = self.indexAt(event.pos())
        if self.currentTagIndex:
            self.update(self.currentTagIndex)
        if not currentTagIndex.isValid() or currentTagIndex in (self.model().index(0, 0), self.model().index(0, 1)):
            self.currentTagIndex = None
            self.dropTimer.stop()
            if 'text/uri-list' in event.mimeData().formats():
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
            if currentTagIndex != self.currentTagIndex:
                self.currentTagIndex = currentTagIndex
                self.dropTimer.start()
            #to enable item highlight at least for dbmodel drag we need this,
            #otherwise it will not show the right cursor icon when dragging from external sources
            if 'application/x-qabstractitemmodeldatalist' in event.mimeData().formats():
                QtWidgets.QTreeView.dragMoveEvent(self, event)

    def dragLeaveEvent(self, event):
        self.currentTagIndex = None
        self.dropTimer.stop()
        event.accept()

    def dropEvent(self, event):
        self.dropTimer.stop()
        currentTagIndex = self.indexAt(event.pos())
        formats = event.mimeData().formats()
        if not 'text/uri-list' in formats and (
            'application/x-qabstractitemmodeldatalist' in formats and (
                not currentTagIndex.isValid() or currentTagIndex in (self.model().index(0, 0), self.model().index(0, 1)))):
            event.ignore()
            return
        event.accept()

        if 'application/x-qabstractitemmodeldatalist' in formats:
            itemsDict = {}
            data = event.mimeData().data('application/x-qabstractitemmodeldatalist')
            stream = QtCore.QDataStream(data)
            while not stream.atEnd():
                row = stream.readInt32()
                if not row in itemsDict:
                    itemsDict[row] = {}
                #column is ignored
                stream.readInt32()
                items = stream.readInt32()
                for i in range(items):
                    key = stream.readInt32()
                    value = stream.readQVariant()
                    itemsDict[row][key] = value
            sampleList = [row[FilePathRole] for row in itemsDict.values()]
            #TODO: use indexFromPath?
            currentTag = currentTagIndex.data()
            parentIndex = currentTagIndex.parent()
            while parentIndex != self.model().index(0, 0):
                currentTag = '{}/{}'.format(parentIndex.data(), currentTag)
                parentIndex = parentIndex.parent()
            self.samplesAddedToTag.emit(sampleList, currentTag)
        elif 'text/uri-list' in formats:
            tag = self.model().sourceModel().pathFromIndex(self.model().mapToSource(currentTagIndex))
            urlList = str(event.mimeData().data('text/uri-list'), encoding='ascii').split()
            fileList = []
            dirList = []
            for encodedUrl in urlList:
                fileInfo = QtCore.QFileInfo(QtCore.QUrl(encodedUrl).toLocalFile())
                if fileInfo.isDir():
                    dirList.append(fileInfo.absoluteFilePath())
                else:
                    fileList.append(fileInfo.absoluteFilePath())
            if dirList:
                scanDialog = SampleScanDialog(self)
                if not scanDialog.exec_():
                    return
                scanMode = scanDialog.scanModeCombo.currentIndex()
                formats = scanDialog.getFormats()
                sampleRates = scanDialog.getSampleRates()
                channels = scanDialog.channelsCombo.currentIndex()
            else:
                scanMode = 0
                formats = True
                sampleRates = True
                channels = 0
            res = ImportDialogScanDnD(self.main, dirList, fileList, scanMode, formats, sampleRates, channels, tag).exec_()
            if not res:
                return
            self.samplesImported.emit([(filePath, fileName, info, tags) for (filePath, fileName, info, tags) in res], currentTagIndex)


class TagsEditorTextEdit(QtWidgets.QTextEdit):
    tagsApplied = QtCore.pyqtSignal(object)
    def __init__(self, *args, **kwargs):
        QtWidgets.QTextEdit.__init__(self, *args, **kwargs)
        self.document().setDefaultStyleSheet('''
            span {
                background-color: rgba(200,200,200,150);
            }
            span.sep {
                color: transparent;
                background-color: transparent;
                }
            ''')
        self.textChanged.connect(self.checkText)
        self.applyBtn = QtWidgets.QPushButton('Apply', self)
        self.applyBtn.setMaximumSize(self.applyBtn.fontMetrics().width('Apply') + 4, self.applyBtn.fontMetrics().height() + 2)
        self.applyBtn.setVisible(False)
        self.applyBtn.clicked.connect(self.applyTags)
        self.applyMode = False
        self._tagList = ''
        self.viewport().setCursor(QtCore.Qt.IBeamCursor)

    def keyPressEvent(self, event):
        if not self.applyMode:
            if event.key() == QtCore.Qt.Key_Tab:
                event.ignore()
                return
            return QtWidgets.QTextEdit.keyPressEvent(self, event)
        else:
            if event.key() == QtCore.Qt.Key_Escape:
                self.textChanged.disconnect(self.checkText)
                self._setTags(self._tagList)
                cursor = self.textCursor()
                cursor.movePosition(cursor.End)
                self.setTextCursor(cursor)
                self.textChanged.connect(self.checkText)
            elif event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
                self.clearFocus()
                self.applyTags()
            else:
                return QtWidgets.QTextEdit.keyPressEvent(self, event)

    def applyTags(self):
        self.checkText()
        self._tagList = self.toPlainText()
        self.tagsApplied.emit(self.tags())

    def checkText(self):
        pos = self.textCursor().position()
        self.textChanged.disconnect(self.checkText)
        if pos == 1 and self.toPlainText().startswith(','):
            pos = 0
        self._setTags(re.sub(r'\/,', ',', re.sub(r'[\n\t]+', ',', self.toPlainText())))
        self.textChanged.connect(self.checkText)
        cursor = self.textCursor()
        if len(self.toPlainText()) < pos:
            pos = len(self.toPlainText())
        cursor.setPosition(pos)
        self.setTextCursor(cursor)

    def _setTags(self, tagList):
        tagList = re.sub(r'\,\,+', ',', tagList.lstrip(','))
        tags = []
        for tag in tagList.split(','):
            tags.append(tag.lstrip().lstrip('/').strip('\n'))
        QtWidgets.QTextEdit.setHtml(self, '<span>{}</span>'.format('</span><span class="sep">,</span><span>'.join(tags)))

    def setTags(self, tagList):
        self._tagList = [tag for tag in tagList if tag is not None]
        self._setTags(','.join(self._tagList))
        cursor = self.textCursor()
        cursor.movePosition(cursor.End)
        self.setTextCursor(cursor)

    def tags(self):
        tags = re.sub(r'\,\,+', ',', self.toPlainText()).replace('\n', ',').strip(',').split(',')
        tags = set(tag.strip('/') for tag in tags if tag)
        return sorted(tags) if tags else []

    def enterEvent(self, event):
        if not self.applyMode:
            return
        self.applyBtn.setVisible(True)
        self.moveApplyBtn()

    def moveApplyBtn(self):
        self.applyBtn.move(self.width() - self.applyBtn.width() - 2, self.height() - self.applyBtn.height() - 2)

    def leaveEvent(self, event):
        self.applyBtn.setVisible(False)

    def resizeEvent(self, event):
        QtWidgets.QTextEdit.resizeEvent(self, event)
        self.moveApplyBtn()


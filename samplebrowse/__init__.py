#!/usr/bin/env python3
# *-* coding: utf-8 *-*

import sys
import os
import sqlite3
#from math import log
from PyQt5 import QtCore, QtGui, QtMultimedia, QtWidgets, uic
import soundfile
import numpy as np

from samplebrowse.widgets import *
from samplebrowse.constants import *
from samplebrowse.dialogs import *
from samplebrowse.classes import *

class EllipsisLabel(QtWidgets.QLabel):
    def __init__(self, *args, **kwargs):
        QtWidgets.QLabel.__init__(self, *args, **kwargs)
        self._text = self.text()

    def minimumSizeHint(self):
        default = QtWidgets.QLabel.minimumSizeHint(self)
        return QtCore.QSize(10, default.height())

    def setText(self, text):
        self._text = text
        QtWidgets.QLabel.setText(self, text)

    def resizeEvent(self, event):
        QtWidgets.QLabel.setText(self, self.fontMetrics().elidedText(self._text, QtCore.Qt.ElideMiddle, self.width()))


class TagTreeDelegate(QtWidgets.QStyledItemDelegate):
    tagColorsChanged = QtCore.pyqtSignal(object, object, object)
    startEditTag = QtCore.pyqtSignal(object)
    def editorEvent(self, event, model, _option, index):
        if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.RightButton:
            if index != model.index(0, 0):
                menu = QtWidgets.QMenu()
                editTagAction = QtWidgets.QAction('Rename tag...', menu)
                editColorAction = QtWidgets.QAction('Edit tag color...', menu)
                menu.addActions([editTagAction, editColorAction])
                res = menu.exec_(_option.widget.viewport().mapToGlobal(event.pos()))
                if res == editColorAction:
                    colorDialog = TagColorDialog(_option.widget.window(), index)
                    if colorDialog.exec_():
                        model.setData(index, colorDialog.foregroundColor, QtCore.Qt.ForegroundRole)
                        model.setData(index, colorDialog.backgroundColor, QtCore.Qt.BackgroundRole)
                        self.tagColorsChanged.emit(index, colorDialog.foregroundColor, colorDialog.backgroundColor)
                elif res == editTagAction:
                    self.startEditTag.emit(index)
                return True
            return True
        return QtWidgets.QStyledItemDelegate.editorEvent(self, event, model, _option, index)

    def createEditor(self, parent, option, index):
        widget = QtWidgets.QStyledItemDelegate.createEditor(self, parent, option, index)
        widget.setValidator(QtGui.QRegExpValidator(QtCore.QRegExp(r'[^\/,]+')))
        return widget

    def setModelData(self, widget, model, index):
        if not widget.text():
            return
        QtWidgets.QStyledItemDelegate.setModelData(self, widget, model, index)


class WaveScene(QtWidgets.QGraphicsScene):
    _orange = QtGui.QColor()
    _orange.setNamedColor('orangered')
    waveGrad = QtGui.QLinearGradient(0, -1, 0, 1)
    waveGrad.setSpread(waveGrad.RepeatSpread)
#    waveGrad.setCoordinateMode(waveGrad.ObjectBoundingMode)
    waveGrad.setColorAt(0.0, QtCore.Qt.red)
    waveGrad.setColorAt(.1, _orange)
    waveGrad.setColorAt(.5, QtCore.Qt.darkGreen)
    waveGrad.setColorAt(.9, _orange)
    waveGrad.setColorAt(1, QtCore.Qt.red)
    waveBrush = QtGui.QBrush(waveGrad)

    def __init__(self, *args, **kwargs):
        QtWidgets.QGraphicsScene.__init__(self, *args, **kwargs)
        self.waveRect = QtCore.QRectF()
        self.wavePen = QtGui.QPen(QtCore.Qt.NoPen)
        self.zeroPen = QtGui.QPen(QtCore.Qt.lightGray)

    def showPlayhead(self):
        self.playhead.show()

    def hidePlayhead(self):
        self.playhead.hide()

    def movePlayhead(self, pos):
        self.playhead.setX(pos)

    def drawWave(self, data, dtype=None):
        left, right = data
        self.clear()
        self.playhead = self.addLine(-10, -100, -10, 100)
        self.playhead.setFlags(self.playhead.flags() ^ self.playhead.ItemIgnoresTransformations)
        path = QtGui.QPainterPath()
        pos = 0
        path.moveTo(0, 0)
        for value in left[0]:
            path.lineTo(pos, value)
            pos += 10
        path.lineTo(pos, 0)
        path.moveTo(0, 0)
        pos = 0
        for value in left[1]:
            path.lineTo(pos, value)
            pos += 10
        path.lineTo(pos, 0)
        path.closeSubpath()
        leftPath = self.addPath(path, self.wavePen, self.waveBrush)
        leftLine = self.addLine(0, 0, leftPath.boundingRect().width(), 0, self.zeroPen)
        leftLine.setFlags(leftLine.flags() ^ leftLine.ItemIgnoresTransformations)
        if not right:
            self.waveRect = QtCore.QRectF(0, -1, leftPath.boundingRect().width(), 2)
            return

        path = QtGui.QPainterPath()
        pos = 0
        path.moveTo(0, 0)
        for value in right[0]:
            path.lineTo(pos, value)
            pos += 10
        path.lineTo(pos, 0)
        path.moveTo(0, 0)
        pos = 0
        for value in right[1]:
            path.lineTo(pos, value)
            pos += 10
        path.lineTo(pos, 0)
        path.closeSubpath()
        path.translate(0, 2)
        rightPath = self.addPath(path, self.wavePen, self.waveBrush)
        rightLine = self.addLine(0, 50, rightPath.boundingRect().width(), 50, self.zeroPen)
        rightLine.setFlags(rightLine.flags() ^ rightLine.ItemIgnoresTransformations)
        leftText = self.addText('L')
        leftText.setY(-1)
        leftText.setFlag(leftText.ItemIgnoresTransformations, True)
        rightText = self.addText('R')
        rightText.setY(1)
        rightText.setFlag(leftText.ItemIgnoresTransformations, True)
        self.waveRect = QtCore.QRectF(0, -1, leftPath.boundingRect().width(), 4)


class UpArrowIcon(QtGui.QIcon):
    def __init__(self):
        pm = QtGui.QPixmap(12, 12)
        pm.fill(QtCore.Qt.transparent)
        qp = QtGui.QPainter(pm)
        qp.setRenderHints(QtGui.QPainter.Antialiasing)
        path = QtGui.QPainterPath()
        path.moveTo(2, 8)
        path.lineTo(6, 2)
        path.lineTo(10, 8)
        qp.drawPath(path)
        del qp
        QtGui.QIcon.__init__(self, pm)


class DownArrowIcon(QtGui.QIcon):
    def __init__(self):
        pm = QtGui.QPixmap(12, 12)
        pm.fill(QtCore.Qt.transparent)
        qp = QtGui.QPainter(pm)
        qp.setRenderHints(QtGui.QPainter.Antialiasing)
        path = QtGui.QPainterPath()
        path.moveTo(2, 4)
        path.lineTo(6, 10)
        path.lineTo(10, 4)
        qp.drawPath(path)
        del qp
        QtGui.QIcon.__init__(self, pm)


class VerticalDownToggleBtn(QtWidgets.QToolButton):
    def __init__(self, *args, **kwargs):
        QtWidgets.QToolButton.__init__(self, *args, **kwargs)
        self.upIcon = UpArrowIcon()
        self.downIcon = DownArrowIcon()
        self.setMaximumSize(16, 16)
        self.setIcon(self.downIcon)

    def toggle(self, value):
        if value:
            self.setDown()
        else:
            self.setUp()

    def setDown(self):
        self.setIcon(self.downIcon)

    def setUp(self):
        self.setIcon(self.upIcon)


class Player(QtCore.QObject):
    stateChanged = QtCore.pyqtSignal(object)
    notify = QtCore.pyqtSignal()
    started = QtCore.pyqtSignal()
    stopped = QtCore.pyqtSignal()
    paused = QtCore.pyqtSignal()

    def __init__(self, main, audioDeviceName=None):
        QtCore.QObject.__init__(self)
        self.main = main
        self.audioBufferArray = QtCore.QBuffer(self)
        self.output = None
        self.audioDevice = None
        self.setAudioDeviceByName(audioDeviceName)
        self.setAudioDevice()

    def setAudioDeviceByName(self, audioDeviceName):
        defaultDevice = QtMultimedia.QAudioDeviceInfo.defaultOutputDevice()
        if not audioDeviceName:
            self.audioDevice = defaultDevice
        elif audioDeviceName == defaultDevice:
            self.audioDevice = defaultDevice
        else:
            for sysDevice in QtMultimedia.QAudioDeviceInfo.availableDevices(QtMultimedia.QAudio.AudioOutput):
                if sysDevice.deviceName() == audioDeviceName:
                    break
            else:
                sysDevice = defaultDevice
            self.audioDevice = sysDevice
#        self.audioDeviceName = audioDeviceName if audioDeviceName else QtMultimedia.QaudioDeviceInfo.defaultOutputDevice()

    def setAudioDevice(self, audioDevice=None):
        if audioDevice:
            self.audioDevice = audioDevice
        sampleSize = 32 if 32 in self.audioDevice.supportedSampleSizes() else 16
        sampleRate = 48000 if 48000 in self.audioDevice.supportedSampleRates() else 44100

        format = QtMultimedia.QAudioFormat()
        format.setSampleRate(sampleRate)
        format.setChannelCount(2)
        format.setSampleSize(sampleSize)
        format.setCodec('audio/pcm')
        format.setByteOrder(QtMultimedia.QAudioFormat.LittleEndian)
        format.setSampleType(QtMultimedia.QAudioFormat.Float if sampleSize >= 32 else QtMultimedia.QAudioFormat.SignedInt)

        if not self.audioDevice.isFormatSupported(format):
            format = self.audioDevice.nearestFormat(format)
            #do something else with self.audioDevice.nearestFormat(format)?
        self.sampleSize = format.sampleSize()
        self.sampleRate = format.sampleRate()
        self.output = QtMultimedia.QAudioOutput(self.audioDevice, format)
        self.output.setNotifyInterval(50)
        self.output.stateChanged.connect(self.stateChanged)
        self.output.notify.connect(self.notify)

    def isPlaying(self):
        return True if self.output.state() == QtMultimedia.QAudio.ActiveState else False

    def stateChanged(self, state):
        if state in (QtMultimedia.QAudio.StoppedState, QtMultimedia.QAudio.IdleState):
            self.stopped.emit()
        elif state == QtMultimedia.QAudio.ActiveState:
            self.started.emit()
        else:
            self.paused.emit()

#    def run(self):
#        while True:
#            res = self.audioQueue.get()
#            if res == -1:
#                break
#            self.output.stop()
#            self.audioBufferArray.close()
#            self.audioBufferArray.setData(res)
#            self.audioBufferArray.open(QtCore.QIODevice.ReadOnly)
#            self.audioBufferArray.seek(0)
#            self.output.start(self.audioBufferArray)
#        self.output.stop()

    def stop(self):
        self.output.stop()

    def play(self, waveData, info):
        if info.channels == 1:
            waveData = waveData.repeat(2, axis=1)/2
        elif info.channels == 2:
            pass
        elif info.channels == 3:
            front = waveData[:, [0, 1]]/1.5
            center = waveData[:, [2]].repeat(2, axis=1)/2
            waveData = front + center
        elif info.channels == 4:
            front = waveData[:, [0, 1]]/2
            rear = waveData[:, [2, 3]]/2
            waveData = front + rear
        elif info.channels == 5:
            front = waveData[:, [0, 1]]/2.5
            rear = waveData[:, [2, 3]]/2.5
            center = waveData[:, [4]].repeat(2, axis=1)/2
            waveData = front + rear + center
        elif info.channels == 6:
            front = waveData[:, [0, 1]]/3
            rear = waveData[:, [2, 3]]/3
            center = waveData[:, [4]].repeat(2, axis=1)/2
            sub = waveData[:, [5]].repeate(2, axis=1)/2
            waveData = front + rear + center + sub
        if self.sampleSize == 16:
            waveData = (waveData * 32767).astype('int16')
        self.audioBufferArray.close()
        self.audioBufferArray.setData(waveData.tostring())
        self.audioBufferArray.open(QtCore.QIODevice.ReadOnly)
        self.audioBufferArray.seek(0)
        self.output.start(self.audioBufferArray)

    def setVolume(self, volume):
#        try:
#            volume = QtMultimedia.QAudio.convertVolume(volume / 100, QtMultimedia.QAudio.LogarithmicVolumeScale, QtMultimedia.QAudio.LinearVolumeScale)
#        except:
#            if volume >= 100:
#                volume = 1
#            else:
#                volume = -log(1 - volume/100) / 4.60517018599
        self.output.setVolume(volume/100)


class SampleView(QtWidgets.QTableView):
    def viewportEvent(self, event):
        if event.type() == QtCore.QEvent.ToolTip:
            index = self.indexAt(event.pos())
            if index.isValid():
                fileIndex = index.sibling(index.row(), 0)
                fileName = fileIndex.data()
                filePath = fileIndex.data(FilePathRole)
                dirIndex = index.sibling(index.row(), dirColumn)
                dir = dirIndex.data() if dirIndex.data() else '?'
                info = fileIndex.data(InfoRole)
                tags = index.sibling(index.row(), tagsColumn).data(TagsRole)
                if tags:
                    tagsText = '<br/><h4>Tags:</h4><ul><li>{}</li></ul>'.format('</li><li>'.join(tags))
                else:
                    tagsText = ''
                if not info:
                    info = soundfile.info(filePath)
                self.setToolTip('''
                    <h3>{fileName}</h3>
                    <table>
                        <tr>
                            <td>Path:</td>
                            <td>{dir}</td>
                        </tr>
                        <tr>
                            <td>Length:</td>
                            <td>{length:.03f}</td>
                        </tr>
                        <tr>
                            <td>Format:</td>
                            <td>{format} ({subtype})</td>
                        </tr>
                        <tr>
                            <td>Sample rate:</td>
                            <td>{sampleRate}</td>
                        </tr>
                        <tr>
                            <td>Channels:</td>
                            <td>{channels}</td>
                        </tr>
                    </table>
                    {tags}
                    '''.format(
                        fileName=fileName, 
                        dir=dir, 
                        length=float(info.frames) / info.samplerate, 
                        format=info.format, 
                        sampleRate=info.samplerate, 
                        channels=info.channels, 
                        subtype=subtypesDict.get(info.subtype, info.subtype), 
                        tags=tagsText, 
                        )
                    )
            else:
                self.setToolTip('')
                QtWidgets.QToolTip.showText(event.pos(), '')
        return QtWidgets.QTableView.viewportEvent(self, event)


class SampleBrowse(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        uic.loadUi('{}/main.ui'.format(os.path.dirname(constants.__file__)), self)
        self.audioSettingsDialog = AudioSettingsDialog(self)
        self.settings = QtCore.QSettings()
        self.player = Player(self, self.settings.value('AudioDevice'))
        self.player.stopped.connect(self.stopped)
        self.player.output.notify.connect(self.movePlayhead)
        self.sampleSize = self.player.sampleSize
        self.sampleRate = self.player.sampleRate

        self.browseSelectGroup.setId(self.browseSystemBtn, 0)
        self.browseSelectGroup.setId(self.browseDbBtn, 1)
        self.volumeSlider.mousePressEvent = self.volumeSliderMousePressEvent
        self.volumeSlider.valueChanged.connect(self.player.setVolume)

        self.browserStackedWidget = QtWidgets.QWidget()
        self.browserStackedLayout = QtWidgets.QStackedLayout()
        self.browserStackedWidget.setLayout(self.browserStackedLayout)
        self.mainSplitter.insertWidget(0, self.browserStackedWidget)

        self.fsSplitter = AdvancedSplitter(QtCore.Qt.Vertical)
        self.browserStackedLayout.addWidget(self.fsSplitter)
        self.fsView = QtWidgets.QTreeView()
        self.fsSplitter.addWidget(self.fsView, collapsible=False)
        self.fsView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.fsView.setHeaderHidden(True)
        self.favouritesTable = QtWidgets.QTableView()
        self.fsSplitter.addWidget(self.favouritesTable, label='Favourites')
        self.favouritesTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.favouritesTable.setSelectionBehavior(self.favouritesTable.SelectRows)
        self.favouritesTable.setSortingEnabled(True)
        self.favouritesTable.horizontalHeader().setMaximumHeight(self.favouritesTable.fontMetrics().height() + 4)
        self.favouritesTable.horizontalHeader().setHighlightSections(False)
        self.favouritesTable.verticalHeader().setVisible(False)
        
        self.fsModel = QtWidgets.QFileSystemModel()
        self.fsModel.setFilter(QtCore.QDir.AllDirs|QtCore.QDir.NoDot | QtCore.QDir.NoDotDot)
        self.fsProxyModel = QtCore.QSortFilterProxyModel()
        self.fsProxyModel.setSourceModel(self.fsModel)
        self.fsView.setModel(self.fsProxyModel)
        for c in range(1, self.fsModel.columnCount()):
            self.fsView.hideColumn(c)
        self.fsModel.setRootPath(QtCore.QDir.currentPath())
        self.fsModel.directoryLoaded.connect(self.cleanFolders)
        self.fsView.sortByColumn(0, QtCore.Qt.AscendingOrder)
#        self.fsView.setRootIndex(self.fsModel.index(QtCore.QDir.currentPath()))
        self.fsView.setCurrentIndex(self.fsProxyModel.mapFromSource(self.fsModel.index(QtCore.QDir.currentPath())))
        self.fsView.doubleClicked.connect(self.dirChanged)
        self.fsView.customContextMenuRequested.connect(self.fsViewContextMenu)

        self.favouritesModel = QtGui.QStandardItemModel()
        self.favouritesModel.setHorizontalHeaderLabels(['Name', 'Path'])
        self.favouritesTable.setModel(self.favouritesModel)
        self.favouritesTable.mousePressEvent = self.favouritesTableMousePressEvent
        self.favouritesTable.horizontalHeader().setStretchLastSection(True)
        self.loadFavourites()
        self.favouritesModel.dataChanged.connect(self.favouritesDataChanged)

        self.fsSplitter.setStretchFactor(0, 50)
        self.fsSplitter.setStretchFactor(1, 1)

        self.loadDb()

        self.dbSplitter = AdvancedSplitter(QtCore.Qt.Vertical)
        self.browserStackedLayout.addWidget(self.dbSplitter)
        self.dbTreeView = DbTreeView(self)
        self.dbTreeView.samplesAddedToTag.connect(self.addSamplesToTag)
        self.dbTreeView.samplesImported.connect(self.importSamplesWithTags)
        self.tagTreeDelegate = TagTreeDelegate()
        self.tagTreeDelegate.tagColorsChanged.connect(self.saveTagColors)
        self.tagTreeDelegate.startEditTag.connect(self.renameTag)
        self.dbTreeView.setItemDelegateForColumn(0, self.tagTreeDelegate)
        self.dbTreeView.setEditTriggers(self.dbTreeView.NoEditTriggers)
        self.dbTreeView.header().setStretchLastSection(False)
        self.dbTreeView.setHeaderHidden(True)
        self.dbTreeModel = TagsModel(self.sampleDb)
        self.dbTreeModel.tagRenamed.connect(self.tagRenamed)
        self.dbTreeProxyModel = QtCore.QSortFilterProxyModel()
        self.dbTreeProxyModel.setSourceModel(self.dbTreeModel)
        self.dbTreeView.setModel(self.dbTreeProxyModel)
        self.dbTreeView.doubleClicked.connect(self.dbTreeViewDoubleClicked)
        self.dbSplitter.addWidget(self.dbTreeView, collapsible=False)

        self.dbDirView = TreeViewWithLines()
        self.dbDirView.setEditTriggers(self.dbDirView.NoEditTriggers)
        self.dbDirView.doubleClicked.connect(self.dbDirViewSelect)
        self.dbSplitter.addWidget(self.dbDirView, label='Directories')
        self.dbDirModel = DbDirModel(self.sampleDb)
        self.dbDirView.setModel(self.dbDirModel)
        self.dbDirView.setHeaderHidden(True)
        self.dbDirView.header().setStretchLastSection(False)
        self.dbDirView.resizeColumnToContents(1)
        #TODO: wtf?!
#        self.dbDirView.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
#        self.dbDirView.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

        self.dbSplitter.setStretchFactor(0, 50)
        self.dbSplitter.setStretchFactor(1, 1)


        self.browseSelectGroup.buttonClicked[int].connect(self.toggleBrowser)
        self.browseModel = QtGui.QStandardItemModel()
        self.dbModel = QtGui.QStandardItemModel()
        self.dbProxyModel = SampleSortFilterProxyModel()
        self.dbProxyModel.setSourceModel(self.dbModel)
        self.sampleView.setModel(self.browseModel)
        self.alignCenterDelegate = AlignItemDelegate(QtCore.Qt.AlignCenter)
        self.alignLeftElideMidDelegate = AlignItemDelegate(QtCore.Qt.AlignLeft, QtCore.Qt.ElideMiddle)
        self.sampleView.setItemDelegateForColumn(1, self.alignLeftElideMidDelegate)
        for c in range(2, subtypeColumn + 1):
            self.sampleView.setItemDelegateForColumn(c, self.alignCenterDelegate)
        self.subtypeDelegate = SubtypeDelegate()
        self.sampleView.setItemDelegateForColumn(subtypeColumn, self.subtypeDelegate)
        self.tagListDelegate = TagListDelegate(self.tagColorsDict)
        self.sampleView.setItemDelegateForColumn(tagsColumn, self.tagListDelegate)
        self.tagListDelegate.tagSelected.connect(self.selectTagOnTree)
        self.sampleView.setMouseTracking(True)
        self.sampleControlDelegate = SampleControlDelegate()
        self.sampleControlDelegate.controlClicked.connect(self.playToggle)
        self.sampleControlDelegate.doubleClicked.connect(self.play)
#        self.sampleControlDelegate.contextMenuRequested.connect(self.sampleContextMenu)
        self.sampleView.clicked.connect(self.setCurrentWave)
        self.sampleView.doubleClicked.connect(self.editTags)
        self.sampleView.setItemDelegateForColumn(0, self.sampleControlDelegate)
        self.sampleView.keyPressEvent = self.sampleViewKeyPressEvent
        self.sampleView.customContextMenuRequested.connect(self.sampleContextMenu)

        self.waveScene = WaveScene()
        self.waveView.setScene(self.waveScene)
        self.player.stopped.connect(self.waveScene.hidePlayhead)
        self.player.started.connect(self.waveScene.showPlayhead)

        self.filterStackedLayout = QtWidgets.QStackedLayout()
        self.filterStackedWidget.setLayout(self.filterStackedLayout)
        self.browsePathLbl = EllipsisLabel()
        self.filterStackedLayout.addWidget(self.browsePathLbl)
        self.filterWidget = QtWidgets.QWidget()
        self.filterWidget.setContentsMargins(0, 0, 0, 0)
        self.filterStackedLayout.addWidget(self.filterWidget)
        filterLayout = QtWidgets.QHBoxLayout()
        filterLayout.setContentsMargins(0, 0, 0, 0)
        self.filterWidget.setLayout(filterLayout)
        filterLayout.addWidget(QtWidgets.QLabel('Search'))
        self.searchEdit = QtWidgets.QLineEdit()
        self.searchEdit.textChanged.connect(self.searchDb)
        filterLayout.addWidget(self.searchEdit)

        self.tagsEdit.applyMode = True
        self.tagsEdit.tagsApplied.connect(self.tagsApplied)

        self.currentSampleIndex = None
        self.currentShownSampleIndex = None
        self.currentBrowseDir = None
        self.currentDbQuery = None
        self.sampleDbUpdated = False

        self.browse()
        for column, visible in browseColumns.items():
            self.sampleView.horizontalHeader().setSectionHidden(column, not visible)
        self.mainSplitter.setStretchFactor(0, 8)
        self.mainSplitter.setStretchFactor(1, 16)

        self.infoTabWidget.setTabEnabled(1, False)
        self.shown = False

        self.reloadTags()
        self.dbTreeView.expandToDepth(0)

        self.doMenu()

    def doMenu(self):
        quitAction = QtWidgets.QAction(QtGui.QIcon.fromTheme('application-exit'), 'Quit', self)
        quitAction.setMenuRole(QtWidgets.QAction.QuitRole)
        quitAction.triggered.connect(self.quit)
        self.fileMenu.addActions([quitAction])

        rightMenuBar = QtWidgets.QMenuBar(self.menubar)
        helpMenu = QtWidgets.QMenu('&?', self.menubar)
        rightMenuBar.addMenu(helpMenu)
        self.menubar.setCornerWidget(rightMenuBar)

        settingsAction = QtWidgets.QAction(QtGui.QIcon.fromTheme('preferences-desktop-multimedia'), 'Audio settings...', self)
        settingsAction.setMenuRole(QtWidgets.QAction.PreferencesRole)
        settingsAction.triggered.connect(self.showAudioSettings)
        aboutAction = QtWidgets.QAction(QtGui.QIcon.fromTheme('help-about'), 'About...', self)
        aboutAction.setMenuRole(QtWidgets.QAction.AboutRole)
        aboutAction.triggered.connect(AboutDialog(self).exec_)
        helpMenu.addActions([settingsAction, utils.menuSeparator(self), aboutAction])

    def showAudioSettings(self):
        res = self.audioSettingsDialog.exec_()
        if not res:
            return
        self.player.setAudioDevice(res)

    def quit(self):
        self.dbConn.commit()
        self.dbConn.close()
        QtWidgets.QApplication.quit()

    def loadDb(self):
        dataDir = QtCore.QDir(QtCore.QStandardPaths.standardLocations(QtCore.QStandardPaths.AppDataLocation)[0])
        dbFile = QtCore.QFile(dataDir.filePath('sample.sqlite'))
        if not dbFile.exists():
            if not dataDir.exists():
                dataDir.mkpath(dataDir.absolutePath())
        self.dbConn = sqlite3.connect(dbFile.fileName())
        self.sampleDb = self.dbConn.cursor()
        try:
            self.sampleDb.execute('CREATE table samples(filePath varchar primary key, fileName varchar, length float, format varchar, sampleRate int, channels int, tags varchar, preview blob)')
        except Exception as e:
            print(e)
            #migrate
            self.sampleDb.execute('PRAGMA table_info(samples)')
            if len(self.sampleDb.fetchall()) != len(allColumns):
                self.sampleDb.execute('ALTER TABLE samples RENAME TO oldsamples')
                self.sampleDb.execute('CREATE table samples(filePath varchar primary key, fileName varchar, length float, format varchar, sampleRate int, channels int, subtype varchar, tags varchar, preview blob)')
                self.sampleDb.execute('INSERT INTO samples (filePath, fileName, length, format, sampleRate, channels, tags, preview) SELECT filePath, fileName, length, format, sampleRate, channels, tags, preview FROM oldsamples')
                self.sampleDb.execute('DROP TABLE oldsamples')
        try:
            self.sampleDb.execute('CREATE table tagColors(tag varchar primary key, foreground varchar, background varchar)')
        except Exception as e:
            print(e)
        self.dbConn.commit()
        self.tagColorsDict = {}
        self.sampleDb.execute('SELECT tag,foreground,background FROM tagColors')
        for res in self.sampleDb.fetchall():
            tag, foreground, background = res
            self.tagColorsDict[tag] = QtGui.QColor(foreground), QtGui.QColor(background)

    def showEvent(self, event):
        if not self.shown:
            QtCore.QTimer.singleShot(
                1000, 
                lambda: self.fsView.scrollTo(
                    self.fsProxyModel.mapFromSource(self.fsModel.index(QtCore.QDir.currentPath())), self.fsView.PositionAtTop
                    )
                )
            self.resize(640, 480)
            self.shown = True

    def sampleViewKeyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Space:
            if not self.player.isPlaying():
                if self.sampleView.currentIndex().isValid():
                    self.play(self.sampleView.currentIndex())
                    self.sampleView.setCurrentIndex(self.sampleView.currentIndex())
            else:
                if self.sampleView.model().rowCount() <= 1:
                    self.player.stop()
                else:
                    if event.modifiers() == QtCore.Qt.ShiftModifier:
                        if self.currentSampleIndex.row() == 0:
                            next = self.currentSampleIndex.sibling(self.sampleView.model().rowCount() -1, 0)
                        else:
                            next = self.currentSampleIndex.sibling(self.currentSampleIndex.row() - 1, 0)
                    else:
                        if self.currentSampleIndex.row() == self.sampleView.model().rowCount() - 1:
                            next = self.currentSampleIndex.sibling(0, 0)
                        else:
                            next = self.currentSampleIndex.sibling(self.currentSampleIndex.row() + 1, 0)
                    self.sampleView.setCurrentIndex(next)
                    self.play(next)
        elif event.key() in (QtCore.Qt.Key_Period, QtCore.Qt.Key_Escape):
            self.player.stop()
        else:
            QtWidgets.QTableView.keyPressEvent(self.sampleView, event)

    def cleanFolders(self, path):
        index = self.fsModel.index(path)
        for row in range(self.fsModel.rowCount(index)):
            self.fsModel.fetchMore(index.sibling(row, 0))
        self.fsModel.fetchMore(self.fsModel.index(path))

    def fsViewContextMenu(self, pos):
        dirIndex = self.fsView.indexAt(pos)
        dirName = dirIndex.data()
        dirPath = self.fsModel.filePath(self.fsProxyModel.mapToSource(dirIndex))

        menu = QtWidgets.QMenu()
        addDirAction = QtWidgets.QAction(QtGui.QIcon.fromTheme('emblem-favorite'), 'Add "{}" to favourites'.format(dirName), menu)
        for row in range(self.favouritesModel.rowCount()):
            dirPathItem = self.favouritesModel.item(row, 1)
            if dirPathItem.text() == dirPath:
                addDirAction.setEnabled(False)
                break
        scanAction = QtWidgets.QAction(QtGui.QIcon.fromTheme('edit-find'), 'Scan "{}" for samples'.format(dirName), menu)

        menu.addActions([addDirAction, utils.menuSeparator(menu), scanAction])
        res = menu.exec_(self.fsView.mapToGlobal(pos))
        if res == addDirAction:
            dirLabelItem = QtGui.QStandardItem(dirIndex.data())
            dirPathItem = QtGui.QStandardItem(dirPath)
            dirPathItem.setFlags(dirPathItem.flags() ^ QtCore.Qt.ItemIsEditable)
            self.favouritesModel.dataChanged.disconnect(self.favouritesDataChanged)
            self.favouritesModel.appendRow([dirLabelItem, dirPathItem])
            self.favouritesModel.dataChanged.connect(self.favouritesDataChanged)
            self.settings.beginGroup('Favourites')
            self.settings.setValue(dirIndex.data(), dirPath)
            self.settings.endGroup()
        elif res == scanAction:
            self.sampleScan(dirPath)

    def sampleScan(self, dirPath=QtCore.QDir('.').absolutePath()):
        scanDialog = SampleScanDialog(self, dirPath)
        if not scanDialog.exec_():
            return
        dirPath = scanDialog.dirPathEdit.text()
        scanMode = scanDialog.scanModeCombo.currentIndex()
        formats = scanDialog.getFormats()
        sampleRates = scanDialog.getSampleRates()
        channels = scanDialog.channelsCombo.currentIndex()
        res = ImportDialogScan(self, dirPath, scanMode, formats, sampleRates, channels).exec_()
        if not res:
            return
        for filePath, fileName, info, tags in res:
            self._addSampleToDb(filePath, fileName, info, ','.join(tags))
        self.dbConn.commit()
        self.reloadTags()
        #TODO reload database table?

    def favouritesDataChanged(self, index, _):
        dirPathIndex = index.sibling(index.row(), 1)
        dirLabel = index.sibling(index.row(), 0).data()
        dirPath = dirPathIndex.data()
        self.settings.beginGroup('Favourites')
        for fav in self.settings.childKeys():
            if self.settings.value(fav) == dirPath:
                self.settings.remove(fav)
                self.settings.setValue(dirLabel, dirPath)
                break
        else:
            self.settings.setValue(dirLabel, dirPath)
        self.settings.endGroup()

    def loadFavourites(self):
        self.settings.beginGroup('Favourites')
        for fav in self.settings.childKeys():
            dirLabelItem = QtGui.QStandardItem(fav)
            dirPathItem = QtGui.QStandardItem(self.settings.value(fav))
            dirPathItem.setFlags(dirPathItem.flags() ^ QtCore.Qt.ItemIsEditable)
            self.favouritesModel.appendRow([dirLabelItem, dirPathItem])
        self.settings.endGroup()

    def browseFromFavourites(self, index):
        if not index.isValid():
            return
        dirPathIndex = index.sibling(index.row(), 1)
        self.browse(dirPathIndex.data())

    def favouritesTableMousePressEvent(self, event):
        index = self.favouritesTable.indexAt(event.pos())
        if event.button() != QtCore.Qt.RightButton:
            self.browseFromFavourites(index)
            return QtWidgets.QTableView.mousePressEvent(self.favouritesTable, event)
        if not index.isValid():
            return
        QtWidgets.QTableView.mousePressEvent(self.favouritesTable, event)
        dirPathIndex = index.sibling(index.row(), 1)
        dirPath = dirPathIndex.data()
        menu = QtWidgets.QMenu()
        scrollToAction = QtWidgets.QAction(QtGui.QIcon.fromTheme('folder'), 'Show directory in tree', menu)
        removeAction = QtWidgets.QAction(QtGui.QIcon.fromTheme('edit-delete'), 'Remove from favourites', menu)
        menu.addActions([scrollToAction, utils.menuSeparator(menu), removeAction])
        res = menu.exec_(self.favouritesTable.viewport().mapToGlobal(event.pos()))
        if res == scrollToAction:
            self.fsView.setCurrentIndex(self.fsProxyModel.mapFromSource(self.fsModel.index(dirPath)))
            self.fsView.scrollTo(
                self.fsProxyModel.mapFromSource(self.fsModel.index(dirPath)), self.fsView.PositionAtTop
                )
        elif res == removeAction:
            self.settings.beginGroup('Favourites')
            for fav in self.settings.childKeys():
                if self.settings.value(fav) == dirPath:
                    self.settings.remove(fav)
                    break
            self.favouritesModel.takeRow(index.row())
            self.settings.endGroup()

#    def favouritesToggle(self, *args):
#        visible = not self.favouritesTable.isVisible()
#        self.favouritesTable.setVisible(visible)
#        self.favouritesToggleBtn.toggle(visible)
#        self.favouriteWidget.setMaximumHeight(self.favouriteWidget.layout().sizeHint().height())
#
#    def dbDirToggle(self, *args):
#        visible = not self.dbDirView.isVisible()
#        self.dbDirView.setVisible(visible)
#        self.dbDirToggleBtn.toggle(visible)
#        self.dbDirWidget.setMaximumHeight(self.dbDirWidget.layout().sizeHint().height())

    def dirChanged(self, index):
        self.browse(self.fsModel.filePath(self.fsProxyModel.mapToSource(index)))

    
    def browse(self, path=None):
        if path is None:
            if self.currentBrowseDir:
                if self.currentShownSampleIndex and self.currentShownSampleIndex.model() == self.browseModel:
                    self.sampleView.setCurrentIndex(self.currentShownSampleIndex)
                return
            else:
                path = QtCore.QDir('.')
        else:
            path = QtCore.QDir(path)
        self.currentBrowseDir = path
        self.browseModel.clear()
        self.browseModel.setHorizontalHeaderLabels(['Name', None, 'Length', 'Format', 'Rate', 'Ch.', 'Bits', None, None])
        for column, visible in browseColumns.items():
            self.sampleView.horizontalHeader().setSectionHidden(column, not visible)
        for fileInfo in path.entryInfoList(availableExtensions, QtCore.QDir.Files):
            filePath = fileInfo.absoluteFilePath()
            fileName = fileInfo.fileName()
#            if fileName.lower().endswith(availableFormats):
            fileItem = QtGui.QStandardItem(fileName)
            fileItem.setData(filePath, FilePathRole)
            fileItem.setIcon(QtGui.QIcon.fromTheme('media-playback-start'))
            try:
                info = soundfile.info(filePath)
                fileItem.setData(info, InfoRole)
            except Exception as e:
#                print e
                continue
            dirItem = QtGui.QStandardItem(fileInfo.absolutePath())
            lengthItem = QtGui.QStandardItem('{:.3f}'.format(float(info.frames) / info.samplerate))
            formatItem = QtGui.QStandardItem(info.format)
            rateItem = QtGui.QStandardItem(str(info.samplerate))
            channelsItem = QtGui.QStandardItem(str(info.channels))
            subtypeItem = QtGui.QStandardItem(info.subtype)
            self.browseModel.appendRow([fileItem, dirItem, lengthItem, formatItem, rateItem, channelsItem, subtypeItem])
        self.sampleView.resizeColumnsToContents()
        self.sampleView.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for c in range(1, subtypeColumn + 1):
            self.sampleView.horizontalHeader().setSectionResizeMode(c, QtWidgets.QHeaderView.Fixed)
        self.sampleView.resizeRowsToContents()
        self.browsePathLbl.setText(path.absolutePath())

    def volumeSliderMousePressEvent(self, event):
        if event.button() == QtCore.Qt.MidButton:
            self.volumeSpin.setValue(100)
        else:
            QtWidgets.QSlider.mousePressEvent(self.volumeSlider, event)

    def sampleContextMenu(self, pos):
        selIndex = self.sampleView.indexAt(pos)
        if not selIndex.isValid():
            return
        if len(self.sampleView.selectionModel().selectedRows()) == 1:
            self.singleSampleContextMenu(selIndex.sibling(selIndex.row(), 0), pos)
        else:
            self.multiSampleContextMenu(pos)

    def singleSampleContextMenu(self, fileIndex, pos):
        fileName = fileIndex.data()
        filePath = fileIndex.data(FilePathRole)
        menu = QtWidgets.QMenu()
        addToDatabaseAction = QtWidgets.QAction('Add "{}" to database'.format(fileName), menu)
        editTagsAction = QtWidgets.QAction('Edit "{}" tags...'.format(fileName), menu)
        delFromDatabaseAction = QtWidgets.QAction('Remove "{}" from database'.format(fileName), menu)
        self.sampleDb.execute('SELECT * FROM samples WHERE filePath=?', (filePath, ))
        if self.sampleView.model() == self.browseModel and not self.sampleDb.fetchone():
            menu.addAction(addToDatabaseAction)
        else:
            if self.sampleView.model() == self.dbProxyModel:
                menu.addAction(editTagsAction)
            menu.addAction(delFromDatabaseAction)
        res = menu.exec_(self.sampleView.viewport().mapToGlobal(pos))
        if res == addToDatabaseAction:
            info = fileIndex.data(InfoRole)
            self.addSampleToDb(filePath, fileName, info, '', None)
        elif res == delFromDatabaseAction:
            filePath = fileIndex.data(FilePathRole)
            self.sampleDb.execute(
                'DELETE FROM samples WHERE filePath=?', 
                (filePath, )
                )
            self.dbConn.commit()
            self.reloadTags()
            if self.sampleView.model() == self.dbProxyModel:
                self.dbModel.takeRow(fileIndex.row())
            else:
                self.sampleDbUpdated = True
        elif res == editTagsAction:
            self.editTags(fileIndex.sibling(fileIndex.row(), tagsColumn))

    def multiSampleContextMenu(self, pos):
        new = []
        exist = []
        for fileIndex in self.sampleView.selectionModel().selectedRows():
            filePath = fileIndex.data(FilePathRole)
            self.sampleDb.execute('SELECT * FROM samples WHERE filePath=?', (filePath, ))
            if not self.sampleDb.fetchone():
                new.append(fileIndex)
            else:
                exist.append(fileIndex)
        menu = QtWidgets.QMenu()
        if self.sampleView.model() == self.browseModel:
            removeAllAction = QtWidgets.QAction('Remove {} existing samples from database'.format(len(exist)), menu)
        else:
            removeAllAction = QtWidgets.QAction('Remove selected samples from database', menu)
        addAllAction = QtWidgets.QAction('Add selected samples to database', menu)
        addAllActionWithTags = QtWidgets.QAction('Add selected samples to database with tags...', menu)
        if new:
            menu.addActions([addAllAction, addAllActionWithTags])
        if exist:
            if new:
                menu.addAction(utils.menuSeparator(menu))
            menu.addAction(removeAllAction)
        res = menu.exec_(self.sampleView.viewport().mapToGlobal(pos))
        if res == addAllAction:
            self.addSampleGroupToDb(new)
        elif res == addAllActionWithTags:
            tags = AddSamplesWithTagDialog(self, new).exec_()
            if isinstance(tags, str):
                self.addSampleGroupToDb(new, tags)
        elif res == removeAllAction:
            if RemoveSamplesDialog(self, exist).exec_():
                fileNames = [i.data(FilePathRole) for i in exist]
                if len(fileNames) < 999:
                    self.sampleDb.execute(
                        'DELETE FROM samples WHERE filePath IN ({})'.format(','.join(['?' for i in fileNames])), 
                        fileNames
                        )
                else:
                    for items in [fileNames[i:i+999] for i in range(0, len(fileNames), 999)]:
                        self.sampleDb.execute(
                            'DELETE FROM samples WHERE filePath IN ({})'.format(','.join(['?' for i in items])), 
                            items
                            )
                self.dbConn.commit()
                if self.sampleView.model() == self.dbProxyModel:
                    for index in sorted(exist, key=lambda index: index.row(), reverse=True):
                        self.dbModel.takeRow(index.row())
                else:
                    self.sampleDbUpdated = True
                self.reloadTags()
                self.dbDirModel.updateTree()

    def addSampleGroupToDb(self, fileIndexes, tags=''):
        for fileIndex in fileIndexes:
            filePath = fileIndex.data(FilePathRole)
            fileName = fileIndex.data()
            info = fileIndex.data(InfoRole)
            self._addSampleToDb(filePath, fileName, info, tags)
        self.dbConn.commit()
        self.reloadTags()
#        if self.sampleView.model() == self.browseModel:
#            self.sampleDbUpdated = True
#        else:
#            reload query

    def addSampleToDb(self, filePath, fileName=None, info=None, tags='', preview=None):
        self._addSampleToDb(filePath, fileName, info, tags, preview)
        self.dbConn.commit()
        self.reloadTags()
        if self.sampleView.model() == self.browseModel:
            self.sampleDbUpdated = True
#        else:
#            reload query

    def _addSampleToDb(self, filePath, fileName=None, info=None, tags='', preview=None):
        if not fileName:
            fileName = QtCore.QFile(filePath).fileName()
        if not info:
            soundfile.info(filePath)
        self.sampleDb.execute(
            'INSERT OR REPLACE INTO samples values (?,?,?,?,?,?,?,?,?)', 
            (filePath, fileName, float(info.frames) / info.samplerate, info.format, info.samplerate, info.channels, info.subtype, tags, preview), 
            )

    def browseDb(self, query=None, force=True):
        if query is None:
            if not force and (self.currentDbQuery and not self.sampleDbUpdated):
                if self.currentShownSampleIndex and self.currentShownSampleIndex.model() == self.dbModel:
                    self.sampleView.setCurrentIndex(self.currentShownSampleIndex)
                return
            elif not self.currentDbQuery:
                query = 'SELECT * FROM samples', tuple()
            else:
                query = self.currentDbQuery
        self.currentDbQuery = query
        self.sampleDbUpdated = False
        self.dbModel.clear()
        self.dbModel.setHorizontalHeaderLabels(['Name', 'Path', 'Length', 'Format', 'Rate', 'Ch.', 'Bits', 'Tags', 'Preview'])
        for column, visible in dbColumns.items():
            self.sampleView.horizontalHeader().setSectionHidden(column, not visible)
        for row in self.sampleDb.execute(*query):
            filePath, fileName, length, format, sampleRate, channels, subtype, tags, data = row
            fileItem = QtGui.QStandardItem(fileName)
            fileItem.setData(filePath, FilePathRole)
            dirItem = QtGui.QStandardItem(QtCore.QFileInfo(filePath).absolutePath())
            fileItem.setIcon(QtGui.QIcon.fromTheme('media-playback-start'))
            lengthItem = QtGui.QStandardItem('{:.3f}'.format(length))
            formatItem = QtGui.QStandardItem(format)
            rateItem = QtGui.QStandardItem(str(sampleRate))
            channelsItem = QtGui.QStandardItem(str(channels))
            subtypeItem = QtGui.QStandardItem(subtype)
            tagsItem = QtGui.QStandardItem()
            tagsItem.setData(list(filter(None, tags.split(','))), TagsRole)
#            self.dbModel.appendRow([fileItem, lengthItem, formatItem, rateItem, channelsItem, tagsItem])
            self.dbModel.appendRow([fileItem, dirItem, lengthItem, formatItem, rateItem, channelsItem, subtypeItem, tagsItem])
        self.sampleView.resizeColumnsToContents()
        self.sampleView.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.sampleView.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        for c in range(2, subtypeColumn + 1):
            self.sampleView.horizontalHeader().setSectionResizeMode(c, QtWidgets.QHeaderView.Fixed)
        self.sampleView.resizeRowsToContents()

    def searchDb(self, text):
        self.dbProxyModel.setFilterRegExp(text)

    def editTags(self, index):
        if self.sampleView.model() != self.dbProxyModel or index.column() != tagsColumn:
            return
        fileIndex = index.sibling(index.row(), 0)
        filePath = fileIndex.data(FilePathRole)
        self.sampleDb.execute('SELECT tags FROM samples WHERE filePath=?', (filePath, ))
        tags = list(filter(None, self.sampleDb.fetchone()[0].split(',')))
        res = TagsEditorDialog(self, tags, fileIndex.data()).exec_()
        if not isinstance(res, list):
            return
        self.sampleView.model().setData(index, res, TagsRole)
        self.sampleDb.execute('UPDATE samples SET tags=? WHERE filePath=?', (','.join(res), filePath))
        self.dbConn.commit()
        self.reloadTags()
        self.sampleView.resizeColumnToContents(tagsColumn)

    def saveTagColors(self, index, foregroundColor, backgroundColor):
        root = self.dbTreeProxyModel.index(0, 0)
        tag = index.data()
        parent = index.parent()
        while parent != root:
            tag = '{parent}/{current}'.format(parent=parent.data(), current=tag)
            parent = parent.parent()
        if not foregroundColor and not backgroundColor:
            self.sampleDb.execute(
                'DELETE FROM tagColors WHERE tag=?', 
                (tag, )
                )
            try:
                self.tagColorsDict.pop(tag)
            except:
                pass
        else:
            self.sampleDb.execute(
                'INSERT OR REPLACE INTO tagColors(tag,foreground,background) VALUES (?,?,?)', 
                (tag, foregroundColor.name(), backgroundColor.name())
                )
            self.tagColorsDict[tag] = foregroundColor, backgroundColor
        self.dbConn.commit()
        self.sampleView.viewport().update()

    def tagRenamed(self, newTag, oldTag):
        newTagTree = newTag.split('/')
        oldTagTree = oldTag.split('/')
        for depth, (new, old) in enumerate(zip(newTagTree, oldTagTree), 1):
            if new != old:
                break
        else:
            return
        newTag = '/'.join(newTagTree[:depth])
        oldTag = '/'.join(oldTagTree[:depth])
        self.sampleDb.execute('SELECT filePath,tags FROM samples WHERE tags LIKE ?', ('%{}%'.format(oldTag), ))
        for filePath, tags in self.sampleDb.fetchall():
            tags = tags.split(',')
            newTags = set()
            for tag in tags:
                if tag == oldTag:
                    newTags.add(newTag)
                elif tag.startswith('{}/'.format(oldTag)):
                    newTags.add('{}/{}'.format(newTag, tag[len(oldTag):]))
                else:
                    newTags.add(tag)
            self.sampleDb.execute('UPDATE samples SET tags=? WHERE filePath=?', (','.join(sorted(newTags)), filePath))
            sampleMatch = self.dbModel.match(self.dbModel.index(0, 0), FilePathRole, filePath, flags=QtCore.Qt.MatchExactly)
            if not sampleMatch:
                continue
            fileIndex = sampleMatch[0]
            tagsIndex = fileIndex.sibling(fileIndex.row(), tagsColumn)
            self.dbModel.setData(tagsIndex, sorted(newTags), TagsRole)

    def renameTag(self, index):
        changing = self.dbTreeView.edit(index, self.dbTreeView.AllEditTriggers, QtCore.QEvent(QtCore.QEvent.None_))
        self.dbTreeModel.blockSignals(True)
        if not changing:
            self.dbTreeProxyModel.setData(index, None, TagsRole)
        else:
            self.dbTreeProxyModel.setData(index, index.data(), TagsRole)
        self.dbTreeModel.blockSignals(False)

    def reloadTags(self):
        self.sampleDb.execute('SELECT tags FROM samples')
        tags = set()
        for tagList in self.sampleDb.fetchall():
            tagList = tagList[0].strip(',').split(',')
            [tags.add(tag.strip().strip('\n')) for tag in tagList]
        self.dbTreeModel.setTags(tags)
        self.dbTreeView.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.dbTreeView.resizeColumnToContents(1)
        self.dbTreeView.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.dbTreeView.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)

    
    def dbTreeViewDoubleClicked(self, index):
        if self.dbTreeProxyModel.mapToSource(index) == self.dbTreeModel.index(0, 0):
            self.browseDb()
            return
        #TODO this has to be implemented along with browseDb
        self.dbModel.clear()
        self.dbModel.setHorizontalHeaderLabels(['Name', 'Path', 'Length', 'Format', 'Rate', 'Ch.', 'Bits', 'Tags', 'Preview'])
        for column, visible in dbColumns.items():
            self.sampleView.horizontalHeader().setSectionHidden(column, not visible)

        currentTag = index.data()
        current = index
        #TODO: use indexFromPath?
        while True:
            parent = current.parent()
            if not parent.isValid() or parent == self.dbTreeProxyModel.index(0, 0):
                break
            currentTag = '{parent}/{current}'.format(parent=parent.data(), current=currentTag)
            current = parent
        hasChildren = self.dbTreeProxyModel.hasChildren(index)
        self.sampleDb.execute('SELECT * FROM samples WHERE tags LIKE ?', ('%{}%'.format(currentTag), ))
        for row in self.sampleDb.fetchall():
            filePath, fileName, length, format, sampleRate, channels, subtype, tags, data = row
            if hasChildren:
                for tag in tags.split(','):
                    if tag.startswith(currentTag):
                        break
                else:
                    continue
            elif not currentTag in tags:
                continue
            fileItem = QtGui.QStandardItem(fileName)
            fileItem.setData(filePath, FilePathRole)
            fileItem.setIcon(QtGui.QIcon.fromTheme('media-playback-start'))
            dirItem = QtGui.QStandardItem(QtCore.QFileInfo(filePath).absolutePath())
            lengthItem = QtGui.QStandardItem('{:.3f}'.format(length))
            formatItem = QtGui.QStandardItem(format)
            rateItem = QtGui.QStandardItem(str(sampleRate))
            channelsItem = QtGui.QStandardItem(str(channels))
            subtypeItem = QtGui.QStandardItem(subtype)
            tagsItem = QtGui.QStandardItem()
            tagsItem.setData(list(filter(None, tags.split(','))), TagsRole)
            self.dbModel.appendRow([fileItem, dirItem, lengthItem, formatItem, rateItem, channelsItem, subtypeItem, tagsItem])
        self.sampleView.resizeColumnsToContents()
        self.sampleView.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.sampleView.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        for c in range(2, subtypeColumn + 1):
            self.sampleView.horizontalHeader().setSectionResizeMode(c, QtWidgets.QHeaderView.Fixed)
        self.sampleView.resizeRowsToContents()

    def dbDirViewSelect(self, index):
        self.browseDb(('SELECT * from samples WHERE filePath LIKE ?', ('{}%'.format(index.data(FilePathRole)), )))

    def addSamplesToTag(self, sampleList, newTag):
        for filePath in sampleList:
            self.sampleDb.execute('SELECT tags FROM samples WHERE filePath=?', (filePath, ))
            tags = set(filter(None, self.sampleDb.fetchone()[0].split(',')))
            tags.add(newTag)
            self.sampleDb.execute('UPDATE samples SET tags=? WHERE filePath=?', (','.join(tags), filePath))
            sampleMatch = self.dbModel.match(self.dbModel.index(0, 0), FilePathRole, filePath, flags=QtCore.Qt.MatchExactly)
            if sampleMatch:
                fileIndex = sampleMatch[0]
                tagsIndex = fileIndex.sibling(fileIndex.row(), tagsColumn)
                self.dbModel.setData(tagsIndex, tags, TagsRole)
        self.sampleView.viewport().update()
        self.dbConn.commit()
        self.reloadTags()

    def importSamplesWithTags(self, sampleList, tagIndex):
        for filePath, fileName, info, tags in sampleList:
            self._addSampleToDb(filePath, fileName, info, ','.join(tags))
        self.dbConn.commit()
        self.reloadTags()
        if tagIndex.isValid():
            self.dbTreeViewDoubleClicked(tagIndex)
        self.dbDirModel.updateTree()


    def toggleBrowser(self, index):
        self.browserStackedLayout.setCurrentIndex(index)
        self.filterStackedLayout.setCurrentIndex(index)
        if index == 0:
            self.sampleView.setModel(self.browseModel)
            self.browse()
        else:
            self.sampleView.setModel(self.dbProxyModel)
            self.browseDb()
        for column, visible in sampleViewColumns[index].items():
            self.sampleView.horizontalHeader().setSectionHidden(column, not visible)

    def playToggle(self, index):
        if not index.isValid():
            self.player.stop()
            return
        fileIndex = index.sibling(index.row(), 0)
        if self.currentSampleIndex and self.currentSampleIndex == fileIndex and self.player.isPlaying():
            self.player.stop()
        else:
            self.play(index)

    def play(self, index):
        if not index.isValid():
            self.player.stop()
            return
        self.player.stop()
        fileIndex = index.sibling(index.row(), 0)
        self.currentSampleIndex = fileIndex
        #setCurrentWave also loads waveData
        #might want to launch it in a separated thread or something else whenever a database will be added?
        self.setCurrentWave(fileIndex)
        fileItem = self.sampleView.model().itemFromIndex(fileIndex)
        info = fileIndex.data(InfoRole)
        waveData = fileItem.data(WaveRole)
#        waveData = waveData * self.volumeSpin.value()/100.
        self.waveScene.movePlayhead(0)
        self.player.play(waveData, info)
        fileItem.setIcon(QtGui.QIcon.fromTheme('media-playback-stop'))

    def movePlayhead(self):
#        bytesInBuffer = self.output.bufferSize() - self.output.bytesFree()
#        usInBuffer = 1000000. * bytesInBuffer / (2 * self.sampleSize / 8) / self.sampleRate
#        self.waveScene.movePlayhead((self.output.processedUSecs() - usInBuffer) / 200)
        self.waveScene.movePlayhead(self.waveScene.playhead.x() + self.player.sampleRate / 200.)

    def stopped(self):
        if self.currentSampleIndex:
            model = self.currentSampleIndex.model()
            model.itemFromIndex(self.currentSampleIndex).setData(QtGui.QIcon.fromTheme('media-playback-start'), QtCore.Qt.DecorationRole)
            self.currentSampleIndex = None
#            self.waveScene.movePlayhead(-50)

    def getWaveData(self, filePath):
        with soundfile.SoundFile(filePath) as sf:
            waveData = sf.read(always_2d=True, dtype='float32')
        return waveData

    def selectTagOnTree(self, tag):
        index = self.dbTreeModel.indexFromPath(tag)
        if index:
            mapIndex = self.dbTreeProxyModel.mapFromSource(index)
            self.dbTreeView.setCurrentIndex(mapIndex)
            self.dbTreeView.scrollTo(index, self.dbTreeView.EnsureVisible)
            self.dbTreeViewDoubleClicked(mapIndex)

    def tagsApplied(self, tagList):
        filePath = self.currentShownSampleIndex.data(FilePathRole)
        self.sampleDb.execute('SELECT * FROM samples WHERE filePath=?', (filePath, ))
        if not self.sampleDb.fetchone():
            return
        self.sampleDb.execute('UPDATE samples SET tags=? WHERE filePath=?', (','.join(tagList), filePath))
        self.dbConn.commit()
        self.reloadTags()
        sampleMatch = self.dbModel.match(self.dbModel.index(0, 0), FilePathRole, filePath, flags=QtCore.Qt.MatchExactly)
        if sampleMatch:
            fileIndex = sampleMatch[0]
            tagsIndex = fileIndex.sibling(fileIndex.row(), tagsColumn)
            self.dbModel.itemFromIndex(tagsIndex).setData(tagList, TagsRole)

    def setCurrentWave(self, index=None):
        self.infoTab.setEnabled(True)
        self.infoTabWidget.setTabEnabled(1, True if self.sampleView.model() == self.dbProxyModel else False)
        if index is None:
            self.waveScene.clear()
        if self.currentShownSampleIndex and self.currentShownSampleIndex == index:
            return
        fileIndex = index.sibling(index.row(), 0)
        if self.player.isPlaying():
            self.play(fileIndex)
        info = fileIndex.data(InfoRole)
        if not info:
            fileItem = self.sampleView.model().itemFromIndex(fileIndex)
            info = soundfile.info(fileItem.data(FilePathRole))
            fileItem.setData(info, InfoRole)
        self.infoFileNameLbl.setText(fileIndex.data())
        self.infoLengthLbl.setText('{:.3f}'.format(float(info.frames) / info.samplerate))
        self.infoFormatLbl.setText(info.format)
        self.infoSampleRateLbl.setText(str(info.samplerate))
        self.infoChannelsLbl.setText(str(info.channels))

        if self.sampleView.model() == self.dbProxyModel:
            tagsIndex = index.sibling(index.row(), tagsColumn)
            if tagsIndex.isValid():
                self.tagsEdit.setTags(tagsIndex.data(TagsRole))

        previewData = fileIndex.data(PreviewRole)
        if not previewData:
            waveData = fileIndex.data(WaveRole)
            if waveData is None:
                fileItem = self.sampleView.model().itemFromIndex(fileIndex)
                waveData = self.getWaveData(fileItem.data(FilePathRole))
                fileItem.setData(waveData, WaveRole)
            ratio = 100
            if info.channels > 1:
                left = waveData[:, 0]
                leftMin = np.amin(np.pad(left, (0, ratio - left.size % ratio), mode='constant', constant_values=0).reshape(-1, ratio), axis=1)
                leftMax = np.amax(np.pad(left, (0, ratio - left.size % ratio), mode='constant', constant_values=0).reshape(-1, ratio), axis=1)
                right = waveData[:, 1]
                rightMin = np.amin(np.pad(right, (0, ratio - right.size % ratio), mode='constant', constant_values=0).reshape(-1, ratio), axis=1)
                rightMax = np.amax(np.pad(right, (0, ratio - right.size % ratio), mode='constant', constant_values=0).reshape(-1, ratio), axis=1)
                rightData = rightMax, rightMin
            else:
                leftMin = np.amin(np.pad(waveData, (0, ratio - waveData.size % ratio), mode='constant', constant_values=0).reshape(-1, ratio), axis=1)
                leftMax = np.amax(np.pad(waveData, (0, ratio - waveData.size % ratio), mode='constant', constant_values=0).reshape(-1, ratio), axis=1)
                rightData = None
            leftData = leftMax, leftMin
            previewData = leftData, rightData
            fileItem.setData(previewData, PreviewRole)
        self.waveScene.drawWave(previewData)
        self.waveView.fitInView(self.waveScene.waveRect)
        self.currentShownSampleIndex = fileIndex

    def resizeEvent(self, event):
        self.waveView.fitInView(self.waveScene.waveRect)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName('jidesk')
    app.setApplicationName('SampleBrowse')

    player = SampleBrowse()
    player.show()
    sys.exit(app.exec_())

#if __name__ == '__main__':
#    main()
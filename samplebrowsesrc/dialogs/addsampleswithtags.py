from PyQt5 import QtCore, QtGui, QtWidgets
from samplebrowsesrc.widgets import TagsEditorTextEdit
from samplebrowsesrc.constants import *

class AddSamplesWithTagDialog(QtWidgets.QDialog):
    def __init__(self, parent, fileList):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowTitle('Add samples to database')
        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)
        layout.addWidget(QtWidgets.QLabel('The following samples are about to be added to the database'))
        sampleModel = QtGui.QStandardItemModel()
        sampleView = QtWidgets.QTableView()
        sampleView.setHorizontalScrollMode(sampleView.ScrollPerPixel)
        sampleView.setVerticalScrollMode(sampleView.ScrollPerPixel)
        sampleView.setMaximumHeight(100)
        layout.addWidget(sampleView)
        sampleView.setModel(sampleModel)
        sampleView.setEditTriggers(sampleView.NoEditTriggers)
        sampleView.horizontalHeader().setVisible(False)
        sampleView.verticalHeader().setVisible(False)
        if isinstance(fileList[0], str):
            for filePath in fileList:
                fileItem = QtGui.QStandardItem(QtCore.QFile(filePath).fileName())
                filePathItem = QtGui.QStandardItem(filePath)
                sampleModel.appendRow([fileItem, filePathItem])
        else:
            for index in fileList:
                fileItem = QtGui.QStandardItem(index.data())
                filePathItem = QtGui.QStandardItem(index.data(FilePathRole))
                sampleModel.appendRow([fileItem, filePathItem])
        sampleView.resizeColumnsToContents()
        sampleView.resizeRowsToContents()
#        sampleView.setStretchLastSection(True)
        layout.addWidget(QtWidgets.QLabel('Tags that will be applied to all of them (separate tags with commas):'))
        self.tagsEditor = TagsEditorTextEdit()
        self.tagsEditor.setMaximumHeight(100)
#        self.tagsEditor.setReadOnly(False)
        layout.addWidget(self.tagsEditor)
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok|QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.button(self.buttonBox.Ok).clicked.connect(self.accept)
        self.buttonBox.button(self.buttonBox.Cancel).clicked.connect(self.reject)
        layout.addWidget(self.buttonBox)

    def exec_(self):
        res = QtWidgets.QDialog.exec_(self)
        if res:
            return self.tagsEditor.tags()
        else:
            return res


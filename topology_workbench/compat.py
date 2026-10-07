"""Scoped enums work with both the Qt5 and Qt6 bindings supplied by QGIS."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView

USER_ROLE = Qt.ItemDataRole.UserRole
CHECKED = Qt.CheckState.Checked
UNCHECKED = Qt.CheckState.Unchecked
CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable
ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft
CASE_INSENSITIVE = Qt.CaseSensitivity.CaseInsensitive
MATCH_CONTAINS = Qt.MatchFlag.MatchContains
DOCK_RIGHT = Qt.DockWidgetArea.RightDockWidgetArea
SELECT_ROWS = QAbstractItemView.SelectionBehavior.SelectRows
EXTENDED_SELECTION = QAbstractItemView.SelectionMode.ExtendedSelection
NO_EDIT = QAbstractItemView.EditTrigger.NoEditTriggers
STRETCH = QHeaderView.ResizeMode.Stretch
RESIZE_CONTENTS = QHeaderView.ResizeMode.ResizeToContents
ACCEPTED = QDialog.DialogCode.Accepted
OK_CANCEL = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel


def exec_dialog(dialog):
    return dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()

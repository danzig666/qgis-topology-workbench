from .i18n import qgis_locale, tr
from qgis.PyQt.QtCore import QAbstractTableModel, QLocale, QModelIndex, QSortFilterProxyModel, Qt
from .compat import USER_ROLE
from .models import RULES


class IssueModel(QAbstractTableModel):
    HEADERS = ("#", 'Rule', 'Layer', 'Feature ID', 'Other layer / feature', 'Issue description', 'Area (m²)')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.issues = []
        self.locale = QLocale(qgis_locale())

    def replace(self, issues):
        self.beginResetModel()
        self.issues = list(issues)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.issues)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        issue = self.issues[index.row()]
        if role == USER_ROLE:
            return issue
        if index.column() == 6:
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
                return "—" if issue.area_m2 is None else self.locale.toString(issue.area_m2, "g", 10)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if index.column() != 6 and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            other = issue.reference_name
            if issue.reference_feature_id is not None:
                other += f" / {issue.reference_feature_id}"
            return (index.row() + 1, RULES[issue.kind].title, issue.layer_name,
                    "—" if issue.feature_id is None else issue.feature_id, other, issue.message)[index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return tr(self.HEADERS[section])
        return None


class IssueFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""
        self.kind = ""

    def lessThan(self, left, right):
        if left.column() == 6:
            issues = self.sourceModel().issues
            a, b = issues[left.row()].area_m2, issues[right.row()].area_m2
            return (-1 if a is None else a) < (-1 if b is None else b)
        return super().lessThan(left, right)

    def set_query(self, query):
        self.query = query.casefold().strip()
        self.invalidateFilter()

    def set_kind(self, kind):
        self.kind = kind or ""
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        issue = self.sourceModel().issues[row]
        if self.kind and issue.kind != self.kind:
            return False
        haystack = " ".join(str(value) for value in (
            RULES[issue.kind].title, issue.layer_name, issue.feature_id, issue.reference_name,
            issue.reference_feature_id, issue.message)).casefold()
        return all(word in haystack for word in self.query.split())

    def visible_issues(self):
        return [self.index(row, 0).data(USER_ROLE) for row in range(self.rowCount())]

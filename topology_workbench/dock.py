from .i18n import tr
import json
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDockWidget, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QTableView, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)
from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer,
)
from qgis.gui import QgsHighlight

from .compat import (
    ACCEPTED, CHECKABLE, CHECKED, EXTENDED_SELECTION, NO_EDIT, RESIZE_CONTENTS,
    SELECT_ROWS, STRETCH, UNCHECKED, USER_ROLE, exec_dialog,
)
from .engine import LayerSnapshot, Scope
from .exporter import export_csv, export_geopackage, issue_layers
from .models import DEFINITIONS, RULES, Rule, deserialize_rules, serialize_rules
from .results import IssueFilter, IssueModel
from .rule_dialog import RuleDialog
from .tasks import CheckTask


class WorkbenchDock(QDockWidget):
    def __init__(self, iface):
        super().__init__("Topology Workbench", iface.mainWindow())
        self.setObjectName("TopologyWorkbenchDock")
        self.setMinimumWidth(490)
        self.iface = iface
        self.project = QgsProject.instance()
        self.rules = []
        self.report = None
        self.task = None
        self.highlights = []
        self.layer_connections = []
        self.rebuilding = False
        root = QWidget()
        self.setWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel("TOPOLOGY WORKBENCH")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #23866e; padding: 4px 0;")
        layout.addWidget(title)
        subtitle = QLabel(tr('Check • locate • export'))
        layout.addWidget(subtitle)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.build_rules_tab()
        self.build_results_tab()
        controls = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItem(tr('Entire layer'), "all")
        self.scope.addItem(tr('Selected features'), "selected")
        self.scope.addItem(tr('Current map extent'), "extent")
        self.scope.setToolTip(tr('Filters the source features to check; surrounding and reference features are still considered.'))
        self.run_button = QPushButton(tr('Run checks'))
        self.run_button.setStyleSheet("QPushButton { padding: 8px 14px; font-weight: 600; }")
        self.run_button.clicked.connect(self.start_check)
        self.cancel_button = QPushButton(tr('Cancel'))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_check)
        controls.addWidget(self.scope)
        controls.addWidget(self.run_button)
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status = QLabel(tr('Add a rule or add basic checks for the active layer.'))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.warnings = QPlainTextEdit()
        self.warnings.setReadOnly(True)
        self.warnings.setMaximumHeight(120)
        self.warnings.setVisible(False)
        layout.addWidget(self.warnings)
        self.project.readProject.connect(self.project_loaded)
        self.project.cleared.connect(self.project_cleared)
        self.project.layersWillBeRemoved.connect(self.layers_removed)
        self.project.layersAdded.connect(self.layers_added)
        self.watch_layers(list(self.project.mapLayers().values()))
        self.load_rules()

    def build_rules_tab(self):
        self.rules_tab = QWidget()
        layout = QVBoxLayout(self.rules_tab)
        hint = QLabel(tr('Save rules for your project layers. Double-click a rule to edit it.'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        self.add_button = QPushButton(tr('+ Add rule'))
        self.add_button.clicked.connect(self.add_rule)
        self.quick_button = QPushButton(tr('Basic checks'))
        self.quick_button.setToolTip(tr('Validity, empty geometry, duplicates and polygon overlaps for the active layer.'))
        self.quick_button.clicked.connect(self.quick_rules)
        self.edit_button = QPushButton(tr('Edit'))
        self.edit_button.clicked.connect(self.edit_rule)
        self.delete_button = QPushButton(tr('Delete'))
        self.delete_button.clicked.connect(self.delete_rules)
        for button in (self.add_button, self.quick_button, self.edit_button, self.delete_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.rule_table = QTableWidget(0, 4)
        self.rule_table.setHorizontalHeaderLabels([tr('Enabled'), tr('Rule'), tr('Source layer'), tr('Reference')])
        self.rule_table.setSelectionBehavior(SELECT_ROWS)
        self.rule_table.setSelectionMode(EXTENDED_SELECTION)
        self.rule_table.setEditTriggers(NO_EDIT)
        self.rule_table.verticalHeader().hide()
        self.rule_table.horizontalHeader().setSectionResizeMode(0, RESIZE_CONTENTS)
        for column in (1, 2, 3):
            self.rule_table.horizontalHeader().setSectionResizeMode(column, STRETCH)
        self.rule_table.cellDoubleClicked.connect(lambda row, column: self.edit_rule())
        self.rule_table.itemChanged.connect(self.rule_toggled)
        layout.addWidget(self.rule_table, 1)
        files = QHBoxLayout()
        self.import_button = QPushButton(tr('Load rules…'))
        self.import_button.clicked.connect(self.import_rules)
        self.save_button = QPushButton(tr('Save rules…'))
        self.save_button.clicked.connect(self.save_rules_file)
        files.addWidget(self.import_button)
        files.addWidget(self.save_button)
        layout.addLayout(files)
        limits = QHBoxLayout()
        limits.addWidget(QLabel(tr('Maximum issues:')))
        self.max_errors = QSpinBox()
        self.max_errors.setRange(1, 100000)
        self.max_errors.setValue(10000)
        self.max_errors.setToolTip(tr('Reaching the limit makes the check incomplete. Up to 250,000 features can be read per layer.'))
        limits.addWidget(self.max_errors)
        limits.addStretch()
        layout.addLayout(limits)
        self.tabs.addTab(self.rules_tab, tr('Rules'))

    def build_results_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.summary = QLabel(tr('No check results yet.'))
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(tr('Search by layer, feature ID or issue…'))
        self.filter_kind = QComboBox()
        self.filter_kind.addItem(tr('All rules'), "")
        for definition in DEFINITIONS:
            self.filter_kind.addItem(definition.title, definition.key)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.filter_kind)
        layout.addLayout(filters)
        self.model = IssueModel(self)
        self.proxy = IssueFilter(self)
        self.proxy.setSourceModel(self.model)
        self.search.textChanged.connect(self.proxy.set_query)
        self.filter_kind.currentIndexChanged.connect(lambda: self.proxy.set_kind(self.filter_kind.currentData()))
        self.proxy.rowsInserted.connect(self.update_result_count)
        self.proxy.rowsRemoved.connect(self.update_result_count)
        self.proxy.modelReset.connect(self.update_result_count)
        self.proxy.layoutChanged.connect(self.update_result_count)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setSelectionMode(EXTENDED_SELECTION)
        self.table.setEditTriggers(NO_EDIT)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(5, STRETCH)
        self.table.setColumnWidth(0, 38)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 180)
        self.table.setColumnWidth(6, 120)
        self.table.doubleClicked.connect(lambda index: self.zoom_issue())
        self.table.selectionModel().selectionChanged.connect(self.highlight_selected)
        layout.addWidget(self.table, 1)
        navigation = QHBoxLayout()
        previous = QPushButton(tr('← Previous'))
        previous.clicked.connect(lambda: self.navigate(-1))
        next_button = QPushButton(tr('Next →'))
        next_button.clicked.connect(lambda: self.navigate(1))
        zoom = QPushButton(tr('Zoom to issue'))
        zoom.clicked.connect(self.zoom_issue)
        select = QPushButton(tr('Select source features'))
        select.clicked.connect(self.select_sources)
        for button in (previous, next_button, zoom, select):
            navigation.addWidget(button)
        layout.addLayout(navigation)
        export_row = QHBoxLayout()
        self.export_button = QPushButton(tr('Export…'))
        self.export_button.clicked.connect(self.export_results)
        self.export_button.setEnabled(False)
        self.add_layer_button = QPushButton(tr('Add issue layers'))
        self.add_layer_button.clicked.connect(self.add_result_layers)
        self.add_layer_button.setEnabled(False)
        self.filtered_export = QCheckBox(tr('Filtered results only'))
        self.filtered_export.setChecked(True)
        export_row.addWidget(self.export_button)
        export_row.addWidget(self.add_layer_button)
        export_row.addWidget(self.filtered_export)
        layout.addLayout(export_row)
        note = QLabel(tr('Double-click to zoom to an issue. Results reflect the checked snapshot; run again after fixing features.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs.addTab(tab, tr('Issues'))

    def selected_rule_rows(self):
        return sorted({index.row() for index in self.rule_table.selectionModel().selectedRows()})

    def add_rule(self):
        dialog = RuleDialog(self.project, self)
        active = self.iface.activeLayer()
        if isinstance(active, QgsVectorLayer):
            dialog.source.setLayer(active)
        if exec_dialog(dialog) == ACCEPTED:
            self.rules.append(dialog.result_rule)
            self.rules_changed()

    def edit_rule(self):
        rows = self.selected_rule_rows()
        if not rows:
            return
        row = rows[0]
        dialog = RuleDialog(self.project, self, self.rules[row])
        if exec_dialog(dialog) == ACCEPTED:
            self.rules[row] = dialog.result_rule
            self.rules_changed()

    def delete_rules(self):
        for row in reversed(self.selected_rule_rows()):
            del self.rules[row]
        self.rules_changed()

    def quick_rules(self):
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer) or int(layer.geometryType()) not in (0, 1, 2):
            QMessageBox.information(self, tr('Choose a layer'), tr('Select a vector layer in the Layers panel to add basic checks.'))
            return
        kinds = ["valid", "empty", "duplicates"]
        if int(layer.geometryType()) == 2:
            kinds.append("overlap")
        existing = {(rule.kind, rule.layer_id) for rule in self.rules}
        for kind in kinds:
            if (kind, layer.id()) not in existing:
                self.rules.append(Rule(kind, layer.id(), layer_name=layer.name()))
        self.rules_changed()

    def rule_toggled(self, item):
        if self.rebuilding or item.column() != 0:
            return
        self.rules[item.row()].enabled = item.checkState() == CHECKED
        self.save_project_rules()
        self.mark_stale()

    def rules_changed(self):
        self.refresh_rule_table()
        self.save_project_rules()
        self.mark_stale()

    def refresh_rule_table(self):
        self.rebuilding = True
        self.rule_table.setRowCount(len(self.rules))
        for row, rule in enumerate(self.rules):
            enabled = QTableWidgetItem()
            enabled.setFlags(enabled.flags() | CHECKABLE)
            enabled.setCheckState(CHECKED if rule.enabled else UNCHECKED)
            self.rule_table.setItem(row, 0, enabled)
            self.rule_table.setItem(row, 1, QTableWidgetItem(RULES[rule.kind].title))
            for column, layer_id, saved_name in ((2, rule.layer_id, rule.layer_name), (3, rule.reference_id, rule.reference_name)):
                layer = self.project.mapLayer(layer_id)
                text = layer.name() if layer else (tr('⚠ {0} (missing)', saved_name or layer_id) if layer_id else "—")
                item = QTableWidgetItem(text)
                item.setToolTip(layer_id if layer_id else tr('This rule does not use a reference layer.'))
                if layer_id and not layer:
                    item.setForeground(QColor("#d06e29"))
                self.rule_table.setItem(row, column, item)
        self.rebuilding = False
        self.tabs.setTabText(0, tr('Rules ({0})', len(self.rules)))

    def save_project_rules(self):
        for rule in self.rules:
            layer = self.project.mapLayer(rule.layer_id)
            reference = self.project.mapLayer(rule.reference_id)
            if layer:
                rule.layer_name = layer.name()
            if reference:
                rule.reference_name = reference.name()
        self.project.writeEntry("TopologyWorkbench", "rules", json.dumps(serialize_rules(self.rules), ensure_ascii=False))

    def rebind_rules(self, rules):
        for rule in rules:
            for attr, name_attr in (("layer_id", "layer_name"), ("reference_id", "reference_name")):
                layer_id = getattr(rule, attr)
                if layer_id and not self.project.mapLayer(layer_id):
                    matches = self.project.mapLayersByName(getattr(rule, name_attr))
                    if len(matches) == 1 and isinstance(matches[0], QgsVectorLayer):
                        setattr(rule, attr, matches[0].id())
        return rules

    def load_rules(self):
        value, found = self.project.readEntry("TopologyWorkbench", "rules", "")
        try:
            self.rules = self.rebind_rules(deserialize_rules(json.loads(value))) if found and value else []
        except (ValueError, TypeError) as error:
            self.rules = []
            self.status.setText(tr('Could not read the saved rules: {0}', error))
        self.refresh_rule_table()

    def save_rules_file(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Save rule set'), "topology-rules.json", "JSON (*.json)")
        if not path:
            return
        try:
            self.save_project_rules()
            Path(path).write_text(json.dumps(serialize_rules(self.rules), ensure_ascii=False, indent=2), encoding="utf-8")
            self.status.setText(tr('Rule set saved.'))
        except OSError as error:
            QMessageBox.warning(self, tr('Save failed'), str(error))

    def import_rules(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Load rule set'), "", "JSON (*.json)")
        if not path:
            return
        try:
            imported = deserialize_rules(json.loads(Path(path).read_text(encoding="utf-8-sig")))
            self.rules = self.rebind_rules(imported)
            self.rules_changed()
            self.status.setText(tr('Rule set loaded. Use Edit to assign any missing layers.'))
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, tr('Load failed'), str(error))

    def start_check(self):
        if self.task:
            return
        active = [rule for rule in self.rules if rule.enabled]
        if not active:
            QMessageBox.information(self, tr('No enabled rules'), tr('Add at least one enabled check rule.'))
            return
        snapshots, layers = {}, []
        mode = self.scope.currentData()
        try:
            for layer_id in {layer_id for rule in active for layer_id in (rule.layer_id, rule.reference_id) if layer_id}:
                layer = self.project.mapLayer(layer_id)
                if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
                    raise ValueError(tr('A rule layer is missing. Edit the rule marked with a warning.'))
                snapshots[layer_id] = LayerSnapshot.capture(layer)
                layers.append(layer)
            if mode == "selected":
                missing = {snapshots[rule.layer_id].name for rule in active if not snapshots[rule.layer_id].selected_ids}
                if missing:
                    raise ValueError(tr('No source features selected: ') + ", ".join(sorted(missing)))
            canvas = self.iface.mapCanvas()
            scope = Scope(mode, QgsRectangle(canvas.extent()), QgsCoordinateReferenceSystem(canvas.mapSettings().destinationCrs()))
        except Exception as error:
            QMessageBox.warning(self, tr('Cannot start checks'), str(error))
            return
        self.report = None
        self.model.replace([])
        self.clear_highlights()
        self.set_running(True)
        self.status.setText(tr('Checks are running… Click Cancel to stop.'))
        self.warnings.setVisible(False)
        self.task = CheckTask(list(active), snapshots, self.project.transformContext(), scope,
                              self.max_errors.value(), self.check_finished)
        self.task.setDependentLayers(layers)
        self.task.progressChanged.connect(lambda value: self.progress.setValue(int(value)))
        QgsApplication.taskManager().addTask(self.task)

    def set_running(self, running):
        self.rules_tab.setEnabled(not running)
        self.scope.setEnabled(not running)
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.progress.setVisible(running)
        if running:
            self.progress.setValue(0)
            self.export_button.setEnabled(False)
            self.add_layer_button.setEnabled(False)

    def cancel_check(self):
        if self.task:
            self.task.cancel()
            self.status.setText(tr('Cancellation requested… Waiting for the current geometry operation to finish.'))

    def check_finished(self, report):
        self.task = None
        self.report = report
        self.set_running(False)
        self.model.replace(report.issues)
        self.update_result_count()
        count = len(report.issues)
        state = tr('CANCELED') if report.canceled else (tr('DONE') if report.complete else tr('INCOMPLETE RESULTS'))
        self.status.setText(tr('{0} • {1:,} issues • {2:.1f} s • {3:,} feature checks', state, count, report.elapsed_seconds, report.checked_features))
        self.summary.setText(tr('No issues found for the enabled rules.') if not count and report.complete else
                             (tr('{0:,} topology issues. Select a result to highlight it on the map.', count) if report.complete else
                              tr('The check is incomplete. The issue list is partial; read the warnings below.')))
        self.warnings.setPlainText("\n".join(report.warnings))
        self.warnings.setVisible(bool(report.warnings))
        self.export_button.setEnabled(count > 0)
        self.add_layer_button.setEnabled(count > 0)
        self.tabs.setCurrentIndex(1)

    def update_result_count(self, *_):
        if hasattr(self, "proxy"):
            self.tabs.setTabText(1, tr('Issues ({0} / {1})', self.proxy.rowCount(), len(self.model.issues)))

    def selected_issues(self):
        return [index.data(USER_ROLE) for index in self.table.selectionModel().selectedRows()]

    def clear_highlights(self):
        for highlight in self.highlights:
            highlight.hide()
            self.iface.mapCanvas().scene().removeItem(highlight)
        self.highlights = []

    def highlight_selected(self, *_):
        self.clear_highlights()
        canvas = self.iface.mapCanvas()
        for issue in self.selected_issues()[:100]:
            if issue.geometry.isNull() or issue.geometry.isEmpty():
                continue
            try:
                geometry = self.map_geometry(issue)
                highlight = QgsHighlight(canvas, geometry, None)
                highlight.setColor(QColor("#ef704d"))
                highlight.setFillColor(QColor(239, 112, 77, 65))
                highlight.setWidth(3)
                highlight.setMinWidth(2)
                highlight.show()
                self.highlights.append(highlight)
            except Exception as error:
                self.status.setText(tr('Could not highlight the issue: {0}', error))

    def map_geometry(self, issue):
        geometry = QgsGeometry(issue.geometry)
        geometry.transform(QgsCoordinateTransform(issue.crs, self.iface.mapCanvas().mapSettings().destinationCrs(),
                                                  self.project.transformContext()))
        return geometry

    def zoom_issue(self):
        selected = self.selected_issues()
        if not selected:
            return
        canvas = self.iface.mapCanvas()
        bounds = None
        try:
            for issue in selected[:100]:
                if issue.geometry.isNull() or issue.geometry.isEmpty():
                    continue
                extent = self.map_geometry(issue).boundingBox()
                if bounds is None:
                    bounds = QgsRectangle(extent)
                else:
                    bounds.combineExtentWith(extent)
            if bounds is None:
                self.status.setText(tr('An issue with empty geometry cannot be zoomed to. Select the source feature by its ID.'))
                return
            minimum = max(canvas.extent().width(), canvas.extent().height()) * 0.02
            if minimum <= 0:
                minimum = 0.001 if canvas.mapSettings().destinationCrs().isGeographic() else 1.0
            bounds.grow(max(minimum, max(bounds.width(), bounds.height()) * 0.1))
            canvas.setExtent(bounds)
            canvas.refresh()
            self.highlight_selected()
        except Exception as error:
            self.status.setText(tr('Could not zoom to the issue: {0}', error))

    def navigate(self, step):
        count = self.proxy.rowCount()
        if not count:
            return
        row = self.table.currentIndex().row()
        row = ((row + step) % count) if row >= 0 else (0 if step > 0 else count - 1)
        self.table.selectRow(row)
        self.table.scrollTo(self.proxy.index(row, 0))
        self.zoom_issue()

    def select_sources(self):
        groups = {}
        for issue in self.selected_issues():
            if issue.feature_id is not None:
                groups.setdefault(issue.layer_id, set()).add(issue.feature_id)
            if issue.reference_id and issue.reference_feature_id is not None:
                groups.setdefault(issue.reference_id, set()).add(issue.reference_feature_id)
        for layer_id, ids in groups.items():
            layer = self.project.mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer):
                layer.selectByIds(list(ids))
        if not groups:
            self.status.setText(tr('This issue has no source feature ID (for example, an enclosed gap).'))

    def export_issues(self):
        return self.proxy.visible_issues() if self.filtered_export.isChecked() else list(self.model.issues)

    def export_results(self):
        issues = self.export_issues()
        if not issues or not self.report:
            self.status.setText(tr('There are no issues to export with the current filters.'))
            return
        path, selected_filter = QFileDialog.getSaveFileName(self, tr('Export issues'), "topology-errors.gpkg",
                                                           "GeoPackage (*.gpkg);;CSV – Excel (*.csv)")
        if not path:
            return
        try:
            if path.lower().endswith(".csv") or (not Path(path).suffix and selected_filter.startswith("CSV")):
                path = str(Path(path).with_suffix(".csv"))
                export_csv(path, issues, self.report)
            else:
                path = str(Path(path).with_suffix(".gpkg"))
                export_geopackage(path, issues, self.report, self.iface.mapCanvas().mapSettings().destinationCrs(),
                                  self.project.transformContext())
            self.status.setText(tr('{0:,} issues exported: {1}', len(issues), path))
        except Exception as error:
            QMessageBox.warning(self, tr('Export failed'), str(error))

    def add_result_layers(self):
        issues = self.export_issues()
        if not issues or not self.report:
            return
        try:
            layers = issue_layers(issues, self.report, self.iface.mapCanvas().mapSettings().destinationCrs(), self.project.transformContext())
            for layer in layers:
                layer.setName(tr('Topology issues – ') + layer.name().removeprefix("topology_"))
                layer.setCustomProperty("TopologyWorkbench/results", True)
                renderer = layer.renderer()
                if renderer:
                    renderer.symbol().setColor(QColor("#ef704d"))
            self.project.addMapLayers(layers)
            self.status.setText(tr('Added {0} temporary issue layers. Export to GeoPackage for permanent storage.', len(layers)))
        except Exception as error:
            QMessageBox.warning(self, tr('Could not create layers'), str(error))

    def mark_stale(self, *_):
        if self.report and not self.report.stale:
            self.report.stale = True
            self.summary.setText(tr('⚠ Rules or layer geometries have changed. These results reflect an earlier snapshot; run the checks again.'))

    def watch_layers(self, layers):
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and not layer.customProperty("TopologyWorkbench/results", False):
                for signal_name in ("geometryChanged", "featureAdded", "featureDeleted", "dataChanged"):
                    signal = getattr(layer, signal_name, None)
                    if signal:
                        signal.connect(self.layer_changed)
                        self.layer_connections.append((layer, signal_name))

    def layer_changed(self, *_):
        layer = self.sender()
        relevant = {layer_id for rule in self.rules for layer_id in (rule.layer_id, rule.reference_id)}
        if layer and layer.id() in relevant:
            if self.task:
                self.cancel_check()
            self.mark_stale()

    def layers_added(self, layers):
        self.watch_layers(layers)
        self.refresh_rule_table()

    def layers_removed(self, layer_ids):
        if any(rule.layer_id in layer_ids or rule.reference_id in layer_ids for rule in self.rules):
            self.mark_stale()
            self.clear_highlights()
        # layersWillBeRemoved is emitted before the actual removal; defer labels.
        from qgis.PyQt.QtCore import QTimer
        QTimer.singleShot(0, self.refresh_rule_table)

    def detach_task(self):
        if self.task:
            self.task.on_finished = None
            try:
                self.task.progressChanged.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.task.cancel()
            self.task = None

    def clear_report(self):
        self.detach_task()
        self.clear_highlights()
        self.report = None
        self.model.replace([])
        self.set_running(False)
        self.export_button.setEnabled(False)
        self.add_layer_button.setEnabled(False)
        self.summary.setText(tr('No check results yet.'))
        self.status.setText(tr('Add a check rule.'))
        self.warnings.setVisible(False)

    def project_loaded(self, *_):
        self.clear_report()
        self.load_rules()

    def project_cleared(self):
        self.clear_report()
        self.rules = []
        self.refresh_rule_table()

    def cleanup(self):
        self.detach_task()
        self.clear_highlights()
        for signal, slot in ((self.project.readProject, self.project_loaded),
                             (self.project.cleared, self.project_cleared),
                             (self.project.layersWillBeRemoved, self.layers_removed),
                             (self.project.layersAdded, self.layers_added)):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        for layer, signal_name in self.layer_connections:
            try:
                getattr(layer, signal_name).disconnect(self.layer_changed)
            except (TypeError, RuntimeError):
                pass
        self.layer_connections = []

    def closeEvent(self, event):
        self.clear_highlights()
        super().closeEvent(event)

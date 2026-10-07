from .i18n import tr
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox, QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QLabel, QMessageBox, QVBoxLayout,
)
from qgis.core import Qgis, QgsUnitTypes, QgsVectorLayer
from qgis.gui import QgsMapLayerComboBox
from .compat import CASE_INSENSITIVE, MATCH_CONTAINS, OK_CANCEL
from .models import DEFINITIONS, RULES, Rule


def searchable_layers(parent, polygon=False):
    combo = QgsMapLayerComboBox(parent)
    filters = Qgis.LayerFilter.PolygonLayer if polygon else Qgis.LayerFilter.VectorLayer
    combo.setFilters(filters)
    combo.setAllowEmptyLayer(True)
    combo.setShowCrs(True)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    completer = QCompleter(combo.model(), combo)
    completer.setCompletionColumn(0)
    completer.setCaseSensitivity(CASE_INSENSITIVE)
    completer.setFilterMode(MATCH_CONTAINS)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    combo.setCompleter(completer)
    combo.lineEdit().setPlaceholderText(tr('Type any part of the layer name…'))
    combo.setMinimumWidth(360)
    return combo


class RuleDialog(QDialog):
    def __init__(self, project, parent=None, rule=None):
        super().__init__(parent)
        self.project = project
        self.original = rule
        self.result_rule = None
        self.setWindowTitle(tr('Edit rule') if rule else tr('New check rule'))
        self.resize(550, 340)
        layout = QVBoxLayout(self)
        self.description = QLabel()
        self.description.setWordWrap(True)
        form = QFormLayout()
        self.kind = QComboBox()
        for definition in DEFINITIONS:
            self.kind.addItem(definition.title, definition.key)
        self.source = searchable_layers(self)
        self.reference = searchable_layers(self, polygon=True)
        self.reference.setLayer(None)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0, 1000000)
        self.tolerance.setDecimals(8)
        self.tolerance.setSingleStep(0.01)
        self.unit = QLabel()
        self.unit.setWordWrap(True)
        form.addRow(tr('Check'), self.kind)
        form.addRow(tr('Source layer'), self.source)
        form.addRow(tr('Reference layer'), self.reference)
        form.addRow(tr('Connection tolerance'), self.tolerance)
        form.addRow(tr('Units'), self.unit)
        layout.addLayout(form)
        layout.addWidget(self.description)
        self.buttons = QDialogButtonBox(OK_CANCEL)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('Save') if rule else tr('Add'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Cancel'))
        self.buttons.accepted.connect(self.validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.kind.currentIndexChanged.connect(self.update_definition)
        self.source.layerChanged.connect(self.update_source)
        if rule:
            self.kind.setCurrentIndex(self.kind.findData(rule.kind))
            self.source.setLayer(project.mapLayer(rule.layer_id))
            self.reference.setLayer(project.mapLayer(rule.reference_id))
            self.tolerance.setValue(rule.tolerance)
        else:
            self.source.setLayer(None)
        self.update_definition()

    def update_definition(self, *_):
        definition = RULES[self.kind.currentData()]
        filters = { (2,): Qgis.LayerFilter.PolygonLayer, (1,): Qgis.LayerFilter.LineLayer }
        self.source.setFilters(filters.get(definition.geometry_types, Qgis.LayerFilter.VectorLayer))
        self.description.setText(definition.description)
        self.reference.setEnabled(definition.reference)
        self.tolerance.setEnabled(definition.tolerance)
        self.update_source()

    def update_source(self, *_):
        definition = RULES[self.kind.currentData()]
        layer = self.source.currentLayer()
        if definition.tolerance and layer:
            unit = tr('degrees') if layer.crs().isGeographic() else QgsUnitTypes.toString(layer.crs().mapUnits())
            self.unit.setText(tr('{0} ({1}). Tolerance applies only to connection checks.', unit, layer.crs().authid()))
        else:
            self.unit.setText("—")

    def validate(self):
        definition = RULES[self.kind.currentData()]
        source, reference = self.source.currentLayer(), self.reference.currentLayer()
        message = ""
        if not isinstance(source, QgsVectorLayer) or not source.isValid():
            message = tr('Choose a valid source layer from the results list.')
        elif int(source.geometryType()) not in definition.geometry_types:
            message = tr('This rule does not support the selected geometry type.')
        elif not source.crs().isValid():
            message = tr('The source layer has no coordinate reference system.')
        elif definition.reference:
            if not isinstance(reference, QgsVectorLayer) or not reference.isValid() or int(reference.geometryType()) != 2:
                message = tr('Choose a valid polygon reference layer.')
            elif not reference.crs().isValid():
                message = tr('The reference layer has no coordinate reference system.')
            elif reference.id() == source.id():
                message = tr('The source and reference must be different layers.')
        # Editable lookup text must resolve to the actual selected layer. Do not
        # silently run a previous choice when a user has only typed a search.
        for combo in (self.source, self.reference) if definition.reference else (self.source,):
            if combo.currentLayer() and combo.lineEdit().text() != combo.itemText(combo.currentIndex()):
                message = tr('After typing your search, choose a layer from the results list.')
        if message:
            QMessageBox.warning(self, tr('Cannot add the rule yet'), message)
            return
        self.result_rule = Rule(definition.key, source.id(),
                                reference.id() if definition.reference else "",
                                self.tolerance.value() if definition.tolerance else 0,
                                self.original.enabled if self.original else True,
                                layer_name=source.name(),
                                reference_name=reference.name() if definition.reference else "")
        if self.original:
            self.result_rule.id = self.original.id
        self.accept()

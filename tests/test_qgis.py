"""Integration tests against the actual PyQGIS / Qt runtime, without mocks for GEOS."""
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from string import Formatter
import ast
from osgeo import ogr
ogr.UseExceptions()

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.PyQt.QtCore import QEventLoop, QTimer
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QMainWindow, QMessageBox
from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry,
    QgsProject, QgsRectangle, QgsVectorLayer, Qgis,
)
from qgis.gui import QgsMapCanvas
from topology_workbench import classFactory
from topology_workbench.compat import USER_ROLE
from topology_workbench.engine import LayerSnapshot, Scope, TopologyEngine
from topology_workbench.exporter import COLUMNS, export_csv, export_geopackage, issue_layers
from topology_workbench.models import Issue, Report, Rule, deserialize_rules, serialize_rules
from topology_workbench.rule_dialog import RuleDialog
from topology_workbench.i18n import (
    CONTEXT, PluginTranslation, hungarian_catalog, language_for_locale, qgis_locale, tr,
)
from topology_workbench.models import DEFINITIONS, RULES
from topology_workbench.results import IssueModel

APP = QgsApplication([], True)
APP.initQgis()
TEST_LOCALE = os.environ.get("TOPOLOGY_TEST_LANGUAGE", "en_US")
APP.setTranslation(TEST_LOCALE)


class FakeIface:
    def __init__(self):
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas(self.window)
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.canvas.setExtent(QgsRectangle(-2, -2, 12, 12))
        self.window.setCentralWidget(self.canvas)
        self.active = None

    def mainWindow(self):
        return self.window

    def activeLayer(self):
        return self.active

    def mapCanvas(self):
        return self.canvas

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)

    def addPluginToVectorMenu(self, *args):
        pass

    def removePluginVectorMenu(self, *args):
        pass

    def addToolBarIcon(self, *args):
        pass

    def removeToolBarIcon(self, *args):
        pass


def rectangle(x1, y1, x2, y2):
    return f"POLYGON(({x1} {y1},{x2} {y1},{x2} {y2},{x1} {y2},{x1} {y1}))"


class QgisTests(unittest.TestCase):
    def setUp(self):
        self.project = QgsProject.instance()
        self.project.clear()
        self.iface = None
        self.plugin = None
        self.translation = PluginTranslation()
        self.translation.install()

    def tearDown(self):
        if self.plugin:
            self.plugin.unload()
        if self.iface:
            self.iface.window.close()
            self.iface.window.deleteLater()
        self.project.clear()
        self.translation.remove()
        APP.processEvents()

    def layer(self, kind, wkts, name="Minta", crs="EPSG:3857"):
        layer = QgsVectorLayer(f"{kind}?crs={crs}", name, "memory")
        self.assertTrue(layer.isValid())
        features = []
        for wkt in wkts:
            feature = QgsFeature()
            if wkt:
                feature.setGeometry(QgsGeometry.fromWkt(wkt))
            features.append(feature)
        self.assertTrue(layer.dataProvider().addFeatures(features)[0])
        layer.updateExtents()
        self.project.addMapLayer(layer)
        return layer

    def run_rule(self, kind, layer, reference=None, tolerance=0, scope=None, **kwargs):
        snapshots = {layer.id(): LayerSnapshot.capture(layer)}
        if reference:
            snapshots[reference.id()] = LayerSnapshot.capture(reference)
        rule = Rule(kind, layer.id(), reference.id() if reference else "", tolerance)
        engine = TopologyEngine([rule], snapshots, self.project.transformContext(), scope, **kwargs)
        return engine.run()

    def assert_count(self, report, count, complete=True):
        self.assertEqual(len(report.issues), count, report.warnings)
        self.assertEqual(report.complete, complete, report.warnings)

    def test_valid_geometry_and_bowtie(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 1, 1), "POLYGON((0 0,2 2,0 2,2 0,0 0))"])
        report = self.run_rule("valid", layer)
        self.assertGreater(len(report.issues), 0)
        self.assertTrue(report.complete, report.warnings)
        self.assertEqual({issue.feature_id for issue in report.issues}, {2})

    def test_null_and_empty(self):
        layer = self.layer("Point", [None, "POINT EMPTY", "POINT(1 1)"])
        self.assert_count(self.run_rule("empty", layer), 2)

    def test_multipart(self):
        layer = self.layer("MultiPoint", ["MULTIPOINT((0 0),(1 1))", "MULTIPOINT((3 3))"])
        self.assert_count(self.run_rule("singlepart", layer), 1)

    def test_duplicate_points(self):
        layer = self.layer("Point", ["POINT(0 0)", "POINT(0 0)", "POINT(2 2)"])
        self.assert_count(self.run_rule("duplicates", layer), 1)

    def test_duplicate_reversed_polygon(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 2, 2), "POLYGON((2 2,2 0,0 0,0 2,2 2))"])
        self.assert_count(self.run_rule("duplicates", layer), 1)

    def test_containment_is_overlap_but_shared_border_is_not(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 4, 4), rectangle(1, 1, 2, 2), rectangle(4, 0, 5, 4)])
        report = self.run_rule("overlap", layer)
        self.assert_count(report, 1)
        self.assertAlmostEqual(report.issues[0].geometry.area(), 1)

    def test_identical_polygons_are_overlap(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 2, 2)] * 2)
        self.assert_count(self.run_rule("overlap", layer), 1)

    def test_invalid_geometry_cannot_produce_false_clean(self):
        layer = self.layer("Polygon", ["POLYGON((0 0,2 2,0 2,2 0,0 0))"])
        self.assert_count(self.run_rule("overlap", layer), 0, complete=False)

    def frame(self):
        return self.layer("Polygon", [rectangle(0, 0, 4, 1), rectangle(0, 3, 4, 4),
                                      rectangle(0, 1, 1, 3), rectangle(3, 1, 4, 3)])

    def test_enclosed_gap(self):
        report = self.run_rule("gaps", self.frame())
        self.assert_count(report, 1)
        self.assertAlmostEqual(report.issues[0].geometry.area(), 4)
        self.assertIsNone(report.issues[0].feature_id)

    def test_open_gap_not_enclosed(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 4, 1), rectangle(0, 3, 4, 4), rectangle(0, 1, 1, 3)])
        self.assert_count(self.run_rule("gaps", layer), 0)

    def test_selected_gap_uses_full_union(self):
        layer = self.frame()
        layer.selectByIds([1])
        self.assert_count(self.run_rule("gaps", layer, scope=Scope("selected")), 1)

    def test_gap_outside_view_excluded(self):
        layer = self.frame()
        scope = Scope("extent", QgsRectangle(10, 10, 11, 11), layer.crs())
        self.assert_count(self.run_rule("gaps", layer, scope=scope), 0)

    def test_dangles_chain_and_closed_ring(self):
        layer = self.layer("LineString", ["LINESTRING(0 0,1 0)", "LINESTRING(1 0,2 0)",
                                          "LINESTRING(4 4,5 4,5 5,4 4)"])
        self.assert_count(self.run_rule("dangles", layer), 2)

    def test_t_junction_connects_to_line_interior(self):
        layer = self.layer("LineString", ["LINESTRING(0 0,2 0)", "LINESTRING(1 0,1 1)"])
        layer.selectByIds([2])
        self.assert_count(self.run_rule("dangles", layer, scope=Scope("selected")), 1)

    def test_dangle_tolerance(self):
        layer = self.layer("LineString", ["LINESTRING(0 0,1 0)", "LINESTRING(1.05 0,2 0)"])
        self.assert_count(self.run_rule("dangles", layer), 4)
        self.assert_count(self.run_rule("dangles", layer, tolerance=0.1), 2)

    def test_multipart_internal_connection(self):
        layer = self.layer("MultiLineString", ["MULTILINESTRING((0 0,1 0),(1 0,2 0))"])
        self.assert_count(self.run_rule("dangles", layer), 2)

    def test_selected_overlap_checks_unselected_context_once(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 2, 2), rectangle(1, 1, 3, 3)])
        layer.selectByIds([2])
        self.assert_count(self.run_rule("overlap", layer, scope=Scope("selected")), 1)
        layer.selectByIds([1, 2])
        self.assert_count(self.run_rule("overlap", layer, scope=Scope("selected")), 1)

    def test_extent_scope_keeps_external_comparison(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 2, 2), rectangle(1, 1, 3, 3)])
        scope = Scope("extent", QgsRectangle(0.1, 0.1, 0.2, 0.2), layer.crs())
        self.assert_count(self.run_rule("overlap", layer, scope=scope), 1)

    def test_coverage_includes_boundary(self):
        source = self.layer("Point", ["POINT(0 1)", "POINT(1 1)", "POINT(4 4)"])
        target = self.layer("Polygon", [rectangle(0, 0, 2, 2)])
        report = self.run_rule("covered", source, target)
        self.assert_count(report, 1)
        self.assertEqual(report.issues[0].feature_id, 3)

    def test_coverage_union_of_multiple_reference_polygons(self):
        source = self.layer("LineString", ["LINESTRING(0.5 1,3.5 1)"])
        target = self.layer("Polygon", [rectangle(0, 0, 2, 2), rectangle(2, 0, 4, 2)])
        self.assert_count(self.run_rule("covered", source, target), 0)

    def test_empty_reference_reports_uncovered(self):
        source = self.layer("Point", ["POINT(1 1)"])
        target = self.layer("Polygon", [])
        self.assert_count(self.run_rule("covered", source, target), 1)

    def test_different_crs_cross_overlap(self):
        source = self.layer("Polygon", [rectangle(0, 0, 200000, 200000)])
        target = self.layer("Polygon", [rectangle(0.5, 0.5, 1, 1)], crs="EPSG:4326")
        self.assert_count(self.run_rule("cross_overlap", source, target), 1)

    def test_invalid_reference_marks_incomplete(self):
        source = self.layer("Point", ["POINT(1 1)"])
        target = self.layer("Polygon", [None])
        self.assert_count(self.run_rule("covered", source, target), 1, complete=False)

    def test_empty_selection_is_not_false_clean(self):
        layer = self.layer("Point", ["POINT(1 1)"])
        self.assert_count(self.run_rule("empty", layer, scope=Scope("selected")), 0, complete=False)

    def test_error_limit(self):
        layer = self.layer("Point", [None] * 3)
        self.assert_count(self.run_rule("empty", layer, max_errors=2), 2, complete=False)

    def test_feature_limit(self):
        layer = self.layer("Point", ["POINT(1 1)"] * 3)
        self.assert_count(self.run_rule("duplicates", layer, max_features=2), 0, complete=False)

    def test_cancel(self):
        layer = self.layer("Point", ["POINT(1 1)"])
        report = self.run_rule("empty", layer, canceled=lambda: True)
        self.assertFalse(report.complete)
        self.assertTrue(report.canceled)

    def test_loading_progress_and_cancellation(self):
        layer = self.layer("Point", [f"POINT({x} 0)" for x in range(600)])
        progress = []
        report = self.run_rule("duplicates", layer, progress=progress.append,
                               canceled=lambda: any(value > 0 for value in progress))
        self.assertTrue(report.canceled)
        self.assertFalse(report.complete)
        self.assertTrue(any(0 < value < 100 for value in progress))

    def test_multiple_rule_progress_never_moves_backwards(self):
        layer = self.layer("Point", [f"POINT({x} 0)" for x in range(600)])
        rules = [Rule(kind, layer.id()) for kind in ("empty", "duplicates")]
        progress = []
        report = TopologyEngine(rules, {layer.id(): LayerSnapshot.capture(layer)},
                                self.project.transformContext(), progress=progress.append).run()
        self.assertTrue(report.complete, report.warnings)
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 100)

    def test_rule_roundtrip_and_corrupt_file(self):
        rules = [Rule("covered", "a", "b", layer_name="Ékezetes réteg")]
        self.assertEqual(deserialize_rules(json.loads(json.dumps(serialize_rules(rules)))), rules)
        for document in ({}, {"format": "topology-workbench", "version": 2},
                         {"format": "topology-workbench", "version": 1, "rules": [{"kind": "evil"}]}):
            with self.assertRaises(ValueError):
                deserialize_rules(document)
        for tolerance in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Rule.from_dict({"kind": "dangles", "layer_id": "x", "tolerance": tolerance})

    def mixed_report(self):
        crs = QgsCoordinateReferenceSystem("EPSG:3857")
        geometries = ["POINT(111319.490793 111325.142866)", "LINESTRING(0 0,1 1)", rectangle(0, 0, 1, 1), None]
        issues = [Issue("rule1", "valid", "layer1", "Árvíztűrő; réteg", -7, "Hiba; idézet \"a\"",
                        QgsGeometry.fromWkt(wkt) if wkt else QgsGeometry(), crs) for wkt in geometries]
        return Report(issues=issues, complete=False, warnings=["Részleges"], stale=True)

    def test_csv_roundtrip(self):
        report = self.mixed_report()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "errors.csv"
            export_csv(path, report.issues, report)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter=";"))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["layer"], "Árvíztűrő; réteg")
            self.assertEqual(rows[0]["feature_id"], "-7")
            self.assertEqual(rows[0]["run_complete"], "false")
            self.assertEqual(rows[0]["run_stale"], "true")

    def test_geopackage_all_geometry_types_roundtrip_and_transform(self):
        report = self.mixed_report()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "errors.gpkg"
            names = export_geopackage(path, report.issues, report, QgsCoordinateReferenceSystem("EPSG:4326"), self.project.transformContext())
            self.assertEqual(len(names), 4)
            datasource = ogr.Open(str(path))
            self.assertIsNotNone(datasource)
            for name in names:
                layer = datasource.GetLayerByName(name)
                self.assertIsNotNone(layer, name)
                self.assertEqual(layer.GetFeatureCount(), 1)
                feature = layer.GetNextFeature()
                self.assertEqual(feature.GetField("feature_id"), "-7")
                self.assertEqual(feature.GetField("run_complete"), "false")
                if name == "topology_multipoint":
                    point = feature.GetGeometryRef().GetGeometryRef(0)
                    self.assertAlmostEqual(point.GetX(), 1, places=5)
                    self.assertAlmostEqual(point.GetY(), 1, places=5)
                    point = None
                feature = None
                layer = None
            datasource = None
            # Existing destination is replaced only after all tables are written.
            export_geopackage(path, report.issues[:1], report, QgsCoordinateReferenceSystem("EPSG:3857"), self.project.transformContext())

    def open_dock(self, layer):
        self.iface = FakeIface()
        self.iface.active = layer
        self.iface.canvas.setLayers([layer])
        self.plugin = classFactory(self.iface)
        self.plugin.initGui()
        self.plugin.show_dock()
        return self.plugin.dock

    def test_lookup_dialog_validates_selection(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 1, 1)], name="Hosszú nevű poligonréteg")
        dialog = RuleDialog(self.project)
        self.assertTrue(dialog.source.isEditable())
        dialog.source.setLayer(layer)
        dialog.validate()
        self.assertIsNotNone(dialog.result_rule)
        self.assertEqual(dialog.result_rule.layer_id, layer.id())
        dialog.deleteLater()

    def test_lookup_typing_substring_and_accepting_completion(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 1, 1)], name="Hosszú nevű poligonréteg")
        self.layer("Point", ["POINT(0 0)"], name="Másik pont")
        dialog = RuleDialog(self.project)
        dialog.show()
        edit = dialog.source.lineEdit()
        edit.setFocus()
        edit.selectAll()
        QTest.keyClicks(edit, "poligon")
        APP.processEvents()
        completer = dialog.source.completer()
        self.assertEqual(completer.completionCount(), 1)
        completion = completer.completionModel().index(0, 0)
        completer.popup().setCurrentIndex(completion)
        QTest.keyClick(completer.popup(), Qt.Key.Key_Return)
        APP.processEvents()
        self.assertEqual(dialog.source.currentLayer(), layer)
        self.assertEqual(dialog.source.currentText(), dialog.source.itemText(dialog.source.currentIndex()))
        dialog.close()
        dialog.deleteLater()

    def test_ui_filter_navigation_highlight_and_stale(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 2, 2), rectangle(1, 1, 3, 3)], name="Telek")
        dock = self.open_dock(layer)
        dock.quick_rules()
        self.assertEqual(len(dock.rules), 4)
        dock.quick_rules()
        self.assertEqual(len(dock.rules), 4)
        report = self.run_rule("overlap", layer)
        dock.check_finished(report)
        self.assertEqual(dock.proxy.rowCount(), 1)
        dock.search.setText("nemlétező")
        self.assertEqual(dock.proxy.rowCount(), 0)
        dock.search.setText("telek")
        self.assertEqual(dock.proxy.rowCount(), 1)
        dock.navigate(1)
        self.assertEqual(len(dock.highlights), 1)
        dock.select_sources()
        self.assertEqual(set(layer.selectedFeatureIds()), {1, 2})
        layer.startEditing()
        layer.changeGeometry(1, QgsGeometry.fromWkt(rectangle(0, 0, 1, 1)))
        self.assertTrue(dock.report.stale)
        layer.rollBack()

    def test_background_task_completes_and_plugin_can_unload(self):
        layer = self.layer("Polygon", [rectangle(0, 0, 2, 2), rectangle(1, 1, 3, 3)])
        dock = self.open_dock(layer)
        dock.quick_rules()
        dock.start_check()
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if dock.task is None else None)
        poll.start(20)
        QTimer.singleShot(15000, loop.quit)
        loop.exec() if hasattr(loop, "exec") else loop.exec_()
        poll.stop()
        self.assertIsNone(dock.task, "Background task timed out")
        self.assertIsNotNone(dock.report)
        self.assert_count(dock.report, 1)

    def test_rule_persistence_and_ambiguous_name_rebinding(self):
        layer = self.layer("Point", ["POINT(0 0)"], name="Azonos név")
        self.layer("Point", [], name="Azonos név")
        dock = self.open_dock(layer)
        missing = Rule("empty", "missing", layer_name="Azonos név")
        self.assertEqual(dock.rebind_rules([missing])[0].layer_id, "missing")
        dock.rules = [Rule("empty", layer.id(), layer_name=layer.name())]
        dock.rules_changed()
        dock.rules = []
        dock.load_rules()
        self.assertEqual(len(dock.rules), 1)
        self.assertEqual(dock.rules[0].layer_id, layer.id())

    def test_project_clear_resets_results_and_rules(self):
        layer = self.layer("Point", [None])
        dock = self.open_dock(layer)
        dock.quick_rules()
        dock.check_finished(self.run_rule("empty", layer))
        self.project.clear()
        self.assertEqual(dock.rules, [])
        self.assertIsNone(dock.report)
        self.assertEqual(dock.model.rowCount(), 0)

    def test_qgis_interface_language_is_detected(self):
        self.assertEqual(PluginTranslation().language, language_for_locale(TEST_LOCALE))
        # The active UI language takes precedence over numeric/OS locale.
        with patch("topology_workbench.i18n.QgsApplication.locale", return_value="hu_HU"):
            self.assertEqual(language_for_locale(qgis_locale()), language_for_locale(TEST_LOCALE))

    def test_locale_variants_and_english_fallback(self):
        for locale in ("hu", "hu_HU", "hu-HU", "HU_hu"):
            self.assertEqual(language_for_locale(locale), "hu")
        for locale in ("en", "en_US", "en-GB", "de_DE", "", None):
            self.assertEqual(language_for_locale(locale), "en")

    def test_hungarian_catalog_and_unload_fallback(self):
        self.translation.remove()
        self.assertEqual(tr("Run checks"), "Run checks")
        translation = PluginTranslation("hu_HU")
        translation.install()
        try:
            self.assertEqual(tr("Run checks"), "Ellenőrzés indítása")
            self.assertEqual(RULES["valid"].title, "Érvényes geometria")
            self.assertIn("Önmetszés", RULES["valid"].description)
            self.assertEqual(tr("Rules ({0})", 3), "Szabályok (3)")
            self.assertEqual(tr("{0}: no features are selected.", "My layer"), "My layer: nincs kijelölt elem.")
            self.assertEqual(tr("Unknown future text"), "Unknown future text")
            from qgis.PyQt.QtCore import QCoreApplication
            self.assertEqual(QCoreApplication.translate("AnotherPlugin", "Run checks"), "Run checks")
        finally:
            translation.remove()
        self.assertEqual(tr("Run checks"), "Run checks")
        self.assertEqual(RULES["valid"].title, "Valid geometry")

    def test_ui_rules_errors_and_exports_follow_language(self):
        hungarian = language_for_locale(TEST_LOCALE) == "hu"
        layer = self.layer("Point", [None], name="User supplied name")
        dock = self.open_dock(layer)
        self.assertEqual(dock.run_button.text(), "Ellenőrzés indítása" if hungarian else "Run checks")
        self.assertEqual(dock.scope.itemText(0), "Teljes réteg" if hungarian else "Entire layer")
        self.assertEqual(dock.rule_table.horizontalHeaderItem(1).text(), "Szabály" if hungarian else "Rule")
        self.assertEqual(dock.model.headerData(2, Qt.Orientation.Horizontal), "Réteg" if hungarian else "Layer")
        dialog = RuleDialog(self.project, dock)
        self.assertEqual(dialog.windowTitle(), "Új ellenőrzési szabály" if hungarian else "New check rule")
        self.assertIn("Gépelj" if hungarian else "Type", dialog.source.lineEdit().placeholderText())
        dialog.deleteLater()
        report = self.run_rule("empty", layer)
        expected_message = "Hiányzó vagy üres geometria." if hungarian else "Missing or empty geometry."
        self.assertEqual(report.issues[0].message, expected_message)
        dock.check_finished(report)
        self.assertTrue(dock.status.text().startswith("KÉSZ" if hungarian else "DONE"))
        # IDs, keys and user-supplied layer names are never translated.
        self.assertEqual(report.issues[0].layer_name, "User supplied name")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "localized.csv"
            export_csv(path, report.issues, report)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                row = next(csv.DictReader(stream, delimiter=";"))
            self.assertEqual(row["message"], expected_message)
            self.assertEqual(row["rule"], RULES["empty"].title)
            self.assertEqual(row["layer"], "User supplied name")
        with self.assertRaises(ValueError) as error:
            Rule.from_dict({"kind": "empty", "layer_id": ""})
        self.assertEqual(str(error.exception), "Hiányzó forrásréteg." if hungarian else "Missing source layer.")

    def test_translation_catalog_covers_messages_and_preserves_placeholders(self):
        catalog = hungarian_catalog()
        texts = {value for definition in DEFINITIONS for value in (definition.title_source, definition.description_source)}
        texts.update(value for value in IssueModel.HEADERS if value != "#")
        root = Path(__file__).resolve().parents[1] / "topology_workbench"
        for source in root.glob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                    if node.args and isinstance(node.args[0], ast.Constant):
                        texts.add(node.args[0].value)
        self.assertFalse(texts.difference(catalog), "Missing Hungarian translations")
        for source, translated in catalog.items():
            self.assertTrue(translated)
            fields = lambda text: sorted((field, spec, conversion) for _, field, spec, conversion in Formatter().parse(text) if field is not None)
            self.assertEqual(fields(source), fields(translated), source)


if __name__ == "__main__":
    print(f"Runtime: QGIS {Qgis.QGIS_VERSION}; language: {TEST_LOCALE}", flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QgisTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    QgsProject.instance().clear()
    APP.processEvents()
    APP.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)

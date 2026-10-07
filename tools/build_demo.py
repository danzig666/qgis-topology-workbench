"""Build portable QGIS sample data and capture the actual Qt widgets for QA."""
import json
from io import BytesIO
import os
from pathlib import Path
import re
import runpy
import sys
import zipfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
test_module = runpy.run_path(str(ROOT / "tests" / "test_qgis.py"))
APP = test_module["APP"]
FakeIface = test_module["FakeIface"]
rectangle = test_module["rectangle"]
from qgis.PyQt.QtGui import QColor, QFont, QFontDatabase
from qgis.PyQt.QtCore import QEventLoop, QTimer
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProject,
    QgsRectangle, QgsVectorFileWriter, QgsVectorLayer, Qgis,
)
from topology_workbench import classFactory
from topology_workbench.engine import LayerSnapshot, TopologyEngine
from topology_workbench.models import Rule, serialize_rules
from topology_workbench.rule_dialog import RuleDialog

project = QgsProject.instance()
if os.name == "nt":
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
APP.setFont(QFont("Segoe UI", 10))
project.clear()
folder = ROOT / "examples"
folder.mkdir(exist_ok=True)
output = ROOT / "test-output"
output.mkdir(exist_ok=True)
data_path = folder / "topology-demo.gpkg"
definitions = [
    ("parcels", "Parcels", "Polygon", [rectangle(0, 0, 400, 100),
      rectangle(0, 300, 400, 400), rectangle(0, 100, 100, 300), rectangle(300, 100, 400, 300),
      rectangle(350, 350, 450, 450), rectangle(500, 0, 650, 150), rectangle(500, 0, 650, 150)]),
    ("roads", "Roads", "LineString", ["LINESTRING(0 500,200 500)",
      "LINESTRING(200 500,400 500)", "LINESTRING(200 500,200 600)"]),
    ("points", "Points", "Point", ["POINT(50 50)", "POINT(200 200)", "POINT(800 200)"]),
    ("invalid", "Invalid / empty", "Polygon", ["POLYGON((550 300,700 450,550 450,700 300,550 300))", None]),
]
layers = []
for position, (table, name, kind, wkts) in enumerate(definitions):
    memory = QgsVectorLayer(f"{kind}?crs=EPSG:3857", name, "memory")
    features = []
    for wkt in wkts:
        feature = QgsFeature()
        if wkt:
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = table
    options.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile if position == 0
                                   else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer)
    result = QgsVectorFileWriter.writeAsVectorFormatV3(memory, str(data_path), project.transformContext(), options)
    if result[0] != QgsVectorFileWriter.WriterError.NoError:
        raise RuntimeError(result)
    layer = QgsVectorLayer(f"{data_path}|layername={table}", name, "ogr")
    assert layer.isValid()
    layer.renderer().symbol().setColor(QColor(("#71bdae", "#4b719b", "#dd9c39", "#dc7c7c")[position]))
    project.addMapLayer(layer)
    layers.append(layer)
parcels, roads, points, invalid = layers
rules = [Rule(kind, parcels.id(), layer_name=parcels.name()) for kind in ("valid", "duplicates", "overlap", "gaps")]
rules += [Rule("dangles", roads.id(), layer_name=roads.name()),
          Rule("covered", points.id(), parcels.id(), layer_name=points.name(), reference_name=parcels.name()),
          Rule("valid", invalid.id(), layer_name=invalid.name()), Rule("empty", invalid.id(), layer_name=invalid.name())]
project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
metadata = project.metadata()
metadata.setAuthor("Topology Workbench contributors")
project.setMetadata(metadata)
project.viewSettings().setDefaultViewExtent(__import__("qgis.core", fromlist=["QgsReferencedRectangle"]).QgsReferencedRectangle(
    QgsRectangle(-70, -70, 900, 680), project.crs()))
project.writeEntry("TopologyWorkbench", "rules", json.dumps(serialize_rules(rules), ensure_ascii=False))
project.setFileName(str(folder / "topology-demo.qgz"))
assert project.write()
# QGIS adds the local Windows login/full name to project-save attributes.
# Keep the publicly distributed synthetic example independent of its builder.
sanitized = BytesIO()
with zipfile.ZipFile(project.fileName()) as original, zipfile.ZipFile(sanitized, "w") as cleaned:
    for item in original.infolist():
        payload = original.read(item.filename)
        if item.filename.endswith(".qgs"):
            xml = payload.decode("utf-8")
            xml = re.sub(r' saveUser(?:Full)?="[^"]*"', "", xml)
            payload = xml.encode("utf-8")
        cleaned.writestr(item, payload)
Path(project.fileName()).write_bytes(sanitized.getvalue())
(folder / "topology-demo-rules.json").write_text(json.dumps(serialize_rules(rules), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

iface = FakeIface()
iface.active = parcels
iface.canvas.setLayers(layers)
iface.canvas.setExtent(QgsRectangle(-70, -70, 900, 680))
iface.window.resize(1820, 940)
iface.window.setWindowTitle(f"Topology Workbench • QGIS {Qgis.QGIS_VERSION}")
plugin = classFactory(iface)
plugin.initGui()
plugin.show_dock()
dock = plugin.dock
iface.window.resizeDocks([dock], [1040], __import__("qgis.PyQt.QtCore", fromlist=["Qt"]).Qt.Orientation.Horizontal)
iface.window.show()
APP.processEvents()
iface.window.grab().save(str(output / "workbench-rules.png"))
snapshots = {layer.id(): LayerSnapshot.capture(layer) for layer in layers}
report = TopologyEngine(rules, snapshots, project.transformContext()).run()
assert report.complete, report.warnings
dock.check_finished(report)
dock.table.selectRow(next(index for index, issue in enumerate(report.issues) if issue.kind == "gaps"))
iface.canvas.refresh()
loop = QEventLoop()
QTimer.singleShot(350, loop.quit)
loop.exec() if hasattr(loop, "exec") else loop.exec_()
iface.window.grab().save(str(output / "workbench-results.png"))
dialog = RuleDialog(project, iface.window)
dialog.source.setLayer(parcels)
dialog.show()
APP.processEvents()
dialog.grab().save(str(output / "workbench-lookup.png"))
dialog.close()
plugin.unload()
iface.window.close()
project.clear()
APP.processEvents()
print(f"Demo saved: {folder}; {len(report.issues)} issues; runtime {Qgis.QGIS_VERSION}")
APP.exitQgis()

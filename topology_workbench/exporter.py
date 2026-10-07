"""Export original issue geometries and reproducible run metadata."""
from .i18n import tr
import csv
import os
from pathlib import Path
import re
import tempfile

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateTransform, QgsFeature, QgsField, QgsGeometry, QgsProject,
    QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes, QgsProviderRegistry,
)
from .models import RULES

COLUMNS = ("error_id", "rule_id", "rule", "layer_id", "layer", "feature_id",
           "reference_layer_id", "reference_layer", "reference_feature_id", "message",
           "source_crs", "source_wkt", "run_complete", "run_stale", "run_scope", "run_started_utc", "run_warnings", "area_m2")


def record(issue, number, report):
    return (number, issue.rule_id, RULES[issue.kind].title, issue.layer_id, issue.layer_name,
            "" if issue.feature_id is None else str(issue.feature_id), issue.reference_id,
            issue.reference_name, "" if issue.reference_feature_id is None else str(issue.reference_feature_id),
            issue.message, issue.crs.authid() or issue.crs.toWkt(), issue.geometry.asWkt(),
            "true" if report.complete else "false", "true" if report.stale else "false", report.scope, report.started_at,
            " | ".join(report.warnings), issue.area_m2)


def export_csv(path, issues, report):
    """UTF-8 BOM for Excel; csv quoting preserves WKT and Hungarian characters."""
    destination = Path(path)
    handle, temporary = tempfile.mkstemp(prefix=".topology-", suffix=".csv", dir=destination.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(COLUMNS)
            for number, issue in enumerate(issues, 1):
                values = record(issue, number, report)
                # Spreadsheet formula injection protection for external layer names
                # and error text. Numeric IDs are serialized as ordinary numbers.
                values = ["'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r", "\n")
                          and not re.fullmatch(r"-?\d+", v)
                          else v for v in values]
                writer.writerow(values)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def geometry_parts(geometry):
    if geometry.isNull() or geometry.isEmpty():
        yield "None", QgsGeometry()
        return
    kind = int(QgsWkbTypes.geometryType(geometry.wkbType()))
    if kind not in (0, 1, 2):
        for part in geometry.asGeometryCollection():
            yield from geometry_parts(part)
        return
    copy = QgsGeometry(geometry)
    copy.convertToStraightSegment()
    copy.get().dropZValue()
    copy.get().dropMValue()
    copy.convertToMultiType()
    yield ("MultiPoint", "MultiLineString", "MultiPolygon")[kind], copy


def issue_layers(issues, report, destination_crs, context):
    """GeoPackage uses separate tables for point, line, polygon and nonspatial issues."""
    groups = {}
    transforms = {}
    for number, issue in enumerate(issues, 1):
        geometry = QgsGeometry(issue.geometry)
        if not geometry.isNull() and not geometry.isEmpty() and issue.crs != destination_crs:
            key = issue.crs.toWkt()
            if key not in transforms:
                transforms[key] = QgsCoordinateTransform(issue.crs, destination_crs, context)
                transforms[key].setBallparkTransformsAreAppropriate(False)
            geometry.transform(transforms[key])
        for kind, part in geometry_parts(geometry):
            if kind not in groups:
                layer = QgsVectorLayer(kind, f"topology_{kind.lower()}", "memory")
                layer.setCrs(destination_crs)
                types = {"error_id": QVariant.Int, "area_m2": QVariant.Double}
                fields = [QgsField(name, types.get(name, QVariant.String)) for name in COLUMNS]
                if not layer.dataProvider().addAttributes(fields):
                    raise RuntimeError(tr('Could not create the export fields.'))
                layer.updateFields()
                groups[kind] = layer
            layer = groups[kind]
            feature = QgsFeature(layer.fields())
            feature.setAttributes(list(record(issue, number, report)))
            if kind != "None":
                feature.setGeometry(part)
            if not layer.dataProvider().addFeatures([feature])[0]:
                raise RuntimeError(tr('Could not add an issue to the export.'))
    for layer in groups.values():
        layer.updateExtents()
    return list(groups.values())


def export_geopackage(path, issues, report, destination_crs, context):
    if not issues:
        raise ValueError(tr('There are no issues to export.'))
    if not destination_crs.isValid():
        raise ValueError(tr('The export coordinate reference system is invalid.'))
    destination = Path(path)
    for layer in QgsProject.instance().mapLayers().values():
        uri = QgsProviderRegistry.instance().decodeUri(layer.providerType(), layer.source())
        source_path = uri.get("path")
        if source_path and Path(source_path).resolve() == destination.resolve():
            raise ValueError(tr('This file is already open as a project layer. Export to a different filename or remove the layer from the project.'))
    layers = issue_layers(issues, report, destination_crs, context)
    handle, temporary = tempfile.mkstemp(prefix=".topology-", suffix=".gpkg", dir=destination.parent)
    os.close(handle)
    os.unlink(temporary)
    try:
        for index, layer in enumerate(layers):
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.fileEncoding = "UTF-8"
            options.layerName = layer.name()
            options.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
                                           if index == 0 else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer)
            result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, temporary, context, options)
            if result[0] != QgsVectorFileWriter.WriterError.NoError:
                raise RuntimeError(result[1] or tr('Could not write the GeoPackage.'))
        try:
            os.replace(temporary, destination)
        except PermissionError as error:
            raise ValueError(tr('The destination file is locked or not writable. Choose a different filename. The original file has been preserved.')) from error
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return [layer.name() for layer in layers]

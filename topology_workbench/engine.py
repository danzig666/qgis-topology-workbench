"""Topology checks on owned feature sources; no project or GUI access in workers."""
from .i18n import tr
from dataclasses import dataclass
import time

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCoordinateTransformContext,
    QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsRectangle,
    QgsSpatialIndex, QgsVectorLayerFeatureSource, QgsWkbTypes,
)

from .models import Issue, Report, RULES
from .measurements import gap_area_m2


@dataclass
class LayerSnapshot:
    id: str
    name: str
    crs: object
    geometry_type: int
    source: object
    selected_ids: frozenset
    feature_count: int = -1

    @classmethod
    def capture(cls, layer):
        return cls(layer.id(), layer.name(), QgsCoordinateReferenceSystem(layer.crs()),
                   int(layer.geometryType()), QgsVectorLayerFeatureSource(layer),
                   frozenset(layer.selectedFeatureIds()), layer.featureCount())


@dataclass
class Scope:
    mode: str = "all"
    extent: object = None
    crs: object = None


class Canceled(Exception):
    pass


class LimitReached(Exception):
    pass


class TopologyEngine:
    def __init__(self, rules, snapshots, transform_context, scope=None,
                 max_errors=10000, max_features=250000, canceled=None, progress=None):
        self.rules = [rule for rule in rules if rule.enabled]
        self.snapshots = snapshots
        self.context = QgsCoordinateTransformContext(transform_context)
        self.scope = scope or Scope()
        self.max_errors = max_errors
        self.max_features = max_features
        self.canceled = canceled or (lambda: False)
        self.progress = progress or (lambda value: None)
        self.report = Report(scope=self.scope.mode)
        self.cache = {}
        self.rule_position = 0
        self.rule_progress = 0

    def update_rule_progress(self, value):
        self.rule_progress = max(self.rule_progress, value)
        self.progress(100 * (self.rule_position + self.rule_progress / 100) / max(1, len(self.rules)))

    def iter_primary(self, ids):
        ordered = sorted(ids)
        for position, fid in enumerate(ordered):
            self.checkpoint()
            if position % 128 == 0:
                self.update_rule_progress(40 + 59 * position / max(1, len(ordered)))
            yield fid

    def checkpoint(self):
        if self.canceled():
            raise Canceled()

    def warning(self, text):
        self.report.complete = False
        if text not in self.report.warnings:
            self.report.warnings.append(text)

    def load(self, layer_id, destination_crs=None):
        snapshot = self.snapshots[layer_id]
        destination_crs = destination_crs or snapshot.crs
        key = (layer_id, destination_crs.toWkt())
        if key in self.cache:
            return self.cache[key]
        if not snapshot.crs.isValid() or not destination_crs.isValid():
            raise ValueError(tr('{0}: invalid or missing coordinate reference system.', snapshot.name))
        transform = None
        if snapshot.crs != destination_crs:
            transform = QgsCoordinateTransform(snapshot.crs, destination_crs, self.context)
            transform.setBallparkTransformsAreAppropriate(False)
        geometries, valid, index = {}, {}, QgsSpatialIndex()
        # Full comparison context avoids artificial dangles, gaps and missing pairs
        # when only the selected features or current viewport are being checked.
        request = QgsFeatureRequest().setNoAttributes()
        count = max(1, snapshot.feature_count)
        for feature in snapshot.source.getFeatures(request):
            self.checkpoint()
            if len(geometries) >= self.max_features:
                raise ValueError(tr('{0}: the safety limit of {1:,} features was exceeded. The check is incomplete.', snapshot.name, self.max_features))
            geometry = QgsGeometry(feature.geometry())
            if transform and not geometry.isNull() and not geometry.isEmpty():
                geometry.transform(transform)
            geometries[feature.id()] = geometry
            if not geometry.isNull() and not geometry.isEmpty() and geometry.isGeosValid():
                linear = QgsGeometry(geometry)
                linear.convertToStraightSegment()
                valid[feature.id()] = linear
                indexed = QgsFeature()
                indexed.setId(feature.id())
                indexed.setGeometry(linear)
                index.addFeature(indexed)
            if len(geometries) % 256 == 0:
                self.update_rule_progress(35 * min(1, len(geometries) / count))
        self.cache[key] = (geometries, valid, index)
        return self.cache[key]

    def primary_ids(self, snapshot, geometries):
        if self.scope.mode == "selected":
            return set(geometries).intersection(snapshot.selected_ids)
        if self.scope.mode == "extent":
            transform = QgsCoordinateTransform(self.scope.crs, snapshot.crs, self.context)
            window = QgsGeometry.fromRect(self.scope.extent)
            window.transform(transform)
            return {fid for fid, geometry in geometries.items()
                    if not geometry.isNull() and geometry.intersects(window)}
        return set(geometries)

    def issue(self, rule, fid, message, geometry, other_fid=None, other_layer=None):
        self.checkpoint()
        if len(self.report.issues) >= self.max_errors:
            raise LimitReached()
        snapshot = self.snapshots[rule.layer_id]
        other = self.snapshots[other_layer] if other_layer else None
        self.report.issues.append(Issue(
            rule.id, rule.kind, snapshot.id, snapshot.name, fid, message,
            QgsGeometry(geometry), QgsCoordinateReferenceSystem(snapshot.crs),
            other.id if other else "", other.name if other else "", other_fid,
            gap_area_m2(geometry, snapshot.crs, self.context) if rule.kind == "gaps" else None,
        ))

    def run(self):
        started = time.monotonic()
        try:
            if self.scope.mode not in ("all", "selected", "extent"):
                raise ValueError(tr('Unknown check scope.'))
            for position, rule in enumerate(self.rules):
                self.checkpoint()
                self.rule_position, self.rule_progress = position, 0
                self.progress(100 * position / max(1, len(self.rules)))
                try:
                    self.check_rule(rule)
                except (Canceled, LimitReached):
                    raise
                except Exception as error:
                    self.warning(f"{RULES[rule.kind].title}: {error}")
                self.update_rule_progress(100)
            self.checkpoint()
            self.progress(100)
        except Canceled:
            self.report.complete = False
            self.report.canceled = True
            self.report.warnings.append(tr('The check was canceled; the issue list is incomplete.'))
        except LimitReached:
            self.warning(tr('The safety limit of {0:,} issues was reached; the check is incomplete.', self.max_errors))
        except Exception as error:
            self.warning(str(error))
        self.report.elapsed_seconds = time.monotonic() - started
        return self.report

    def check_rule(self, rule):
        if rule.layer_id not in self.snapshots:
            raise ValueError(tr('The source layer was not found.'))
        snapshot = self.snapshots[rule.layer_id]
        definition = RULES[rule.kind]
        if snapshot.geometry_type not in definition.geometry_types:
            raise ValueError(tr('The layer geometry type is not supported by this rule.'))
        if definition.reference:
            if rule.reference_id not in self.snapshots:
                raise ValueError(tr('The reference layer was not found.'))
            if rule.reference_id == rule.layer_id:
                raise ValueError(tr('The source and reference must be different layers.'))
            if self.snapshots[rule.reference_id].geometry_type != 2:
                raise ValueError(tr('The reference layer must be a polygon layer.'))
        geometries, valid, index = self.load(rule.layer_id)
        primary = self.primary_ids(snapshot, geometries)
        self.report.checked_features += len(primary)
        if self.scope.mode == "selected" and not primary:
            raise ValueError(tr('{0}: no features are selected.', snapshot.name))
        if rule.kind not in ("valid", "empty", "singlepart"):
            invalid_count = sum(not geom.isNull() and not geom.isEmpty() and fid not in valid
                                for fid, geom in geometries.items())
            if invalid_count:
                self.warning(tr('{0}: {1} invalid geometries were skipped in spatial comparisons. Run the Valid geometry rule.', snapshot.name, invalid_count))
        if rule.kind in ("valid", "empty", "singlepart"):
            for fid in self.iter_primary(primary):
                self.checkpoint()
                geometry = geometries[fid]
                if rule.kind == "empty" and (geometry.isNull() or geometry.isEmpty()):
                    self.issue(rule, fid, tr('Missing or empty geometry.'), geometry)
                elif rule.kind == "singlepart" and geometry.isMultipart() and geometry.constGet().numGeometries() > 1:
                    self.issue(rule, fid, tr('The feature has more than one geometry part.'), geometry)
                elif rule.kind == "valid" and not geometry.isNull() and not geometry.isEmpty() and fid not in valid:
                    errors = geometry.validateGeometry()
                    if not errors:
                        self.issue(rule, fid, tr('Invalid GEOS geometry.'), geometry)
                    for error in errors:
                        location = QgsGeometry.fromPointXY(error.where()) if error.hasWhere() else geometry
                        self.issue(rule, fid, error.what(), location)
            return
        if rule.kind in ("duplicates", "overlap", "cross_overlap"):
            cross = rule.kind == "cross_overlap"
            if cross:
                target_raw, target, target_index = self.load(rule.reference_id, snapshot.crs)
                self.check_reference_validity(rule, target_raw, target)
            else:
                target, target_index = valid, index
            for fid in self.iter_primary(primary.intersection(valid)):
                self.checkpoint()
                geometry = valid[fid]
                for other_fid in sorted(target_index.intersects(geometry.boundingBox())):
                    self.checkpoint()
                    if not cross and (other_fid == fid or (other_fid in primary and other_fid < fid)):
                        continue
                    other = target[other_fid]
                    if rule.kind == "duplicates":
                        if geometry.isGeosEqual(other):
                            self.issue(rule, fid, tr('Identical geometry to another feature.'), geometry, other_fid, rule.layer_id)
                    elif geometry.intersects(other):
                        intersection = self.operation(geometry.intersection(other))
                        if intersection.area() > 0:
                            self.issue(rule, fid, tr('The polygon areas overlap.'), intersection,
                                       other_fid, rule.reference_id if cross else rule.layer_id)
            return
        if rule.kind == "gaps":
            self.update_rule_progress(40)
            merged = self.union(list(valid.values()))
            for polygon in self.polygons(merged):
                for ring in polygon[1:]:
                    self.checkpoint()
                    hole = QgsGeometry.fromPolygonXY([ring])
                    if self.scope.mode == "extent":
                        window = QgsGeometry.fromRect(self.scope.extent)
                        window.transform(QgsCoordinateTransform(self.scope.crs, snapshot.crs, self.context))
                        if not hole.intersects(window):
                            continue
                    elif self.scope.mode == "selected":
                        if not any(fid in primary and hole.intersects(valid[fid])
                                   for fid in index.intersects(hole.boundingBox())):
                            continue
                    self.issue(rule, None, tr('Enclosed gap between polygons.'), hole)
            return
        if rule.kind == "covered":
            target_raw, target, target_index = self.load(rule.reference_id, snapshot.crs)
            self.check_reference_validity(rule, target_raw, target)
            for fid in self.iter_primary(primary.intersection(valid)):
                self.checkpoint()
                geometry = valid[fid]
                candidates = [target[other_fid] for other_fid in target_index.intersects(geometry.boundingBox())]
                coverage = self.union(candidates)
                remainder = self.operation(geometry.difference(coverage)) if candidates else geometry
                if not remainder.isEmpty() and not remainder.isNull():
                    self.issue(rule, fid, tr('The reference polygons do not fully cover the feature.'),
                               remainder, other_layer=rule.reference_id)
            return
        if rule.kind == "dangles":
            if rule.tolerance < 0:
                raise ValueError(tr('Tolerance cannot be negative.'))
            for fid in self.iter_primary(primary.intersection(valid)):
                self.checkpoint()
                geometry = valid[fid]
                parts = geometry.asMultiPolyline() if geometry.isMultipart() else [geometry.asPolyline()]
                for part_position, part in enumerate(parts):
                    if len(part) < 2 or part[0].distance(part[-1]) <= rule.tolerance:
                        continue
                    for endpoint in (part[0], part[-1]):
                        point = QgsGeometry.fromPointXY(QgsPointXY(endpoint))
                        bounds = QgsRectangle(point.boundingBox())
                        bounds.grow(rule.tolerance)
                        connected = False
                        for other_fid in index.intersects(bounds):
                            self.checkpoint()
                            if other_fid != fid and point.distance(valid[other_fid]) <= rule.tolerance:
                                connected = True
                                break
                        if not connected:
                            connected = any(point.distance(QgsGeometry.fromPolylineXY(other_part)) <= rule.tolerance
                                            for i, other_part in enumerate(parts) if i != part_position)
                        if not connected:
                            self.issue(rule, fid, tr('Line end does not connect to another line.'), point)

    def check_reference_validity(self, rule, raw, valid):
        omitted = len(raw) - len(valid)
        if omitted:
            self.warning(tr('{0}: {1} empty or invalid reference geometries were skipped.', self.snapshots[rule.reference_id].name, omitted))

    def operation(self, geometry):
        if geometry.lastError():
            raise ValueError(tr('Geometry operation failed: {0}', geometry.lastError()))
        return geometry

    def union(self, geometries):
        self.checkpoint()
        if not geometries:
            return QgsGeometry()
        return self.operation(QgsGeometry.unaryUnion(geometries))

    @staticmethod
    def polygons(geometry):
        if geometry.isNull() or geometry.isEmpty():
            return []
        if QgsWkbTypes.geometryType(geometry.wkbType()) != 2:
            return []
        return geometry.asMultiPolygon() if geometry.isMultipart() else [geometry.asPolygon()]

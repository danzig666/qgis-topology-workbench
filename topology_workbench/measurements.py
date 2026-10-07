"""Gap areas in square metres, independent of the map/export CRS."""
import math

from qgis.core import Qgis, QgsDistanceArea, QgsUnitTypes
from .i18n import tr


def gap_area_m2(geometry, crs, context):
    if crs.isGeographic():
        measure = QgsDistanceArea()
        measure.setSourceCrs(crs, context)
        if not measure.setEllipsoid(crs.ellipsoidAcronym() or "WGS84") or not measure.willUseEllipsoid():
            raise ValueError(tr('Could not measure the gap area in square metres.'))
        area = measure.convertAreaMeasurement(measure.measureArea(geometry), Qgis.AreaUnit.SquareMeters)
    else:
        units = crs.mapUnits()
        if units in (Qgis.DistanceUnit.Unknown, Qgis.DistanceUnit.Degrees):
            raise ValueError(tr('Could not measure the gap area in square metres.'))
        factor = QgsUnitTypes.fromUnitToUnitFactor(units, Qgis.DistanceUnit.Meters)
        area = geometry.area() * factor * factor
    if not math.isfinite(area) or area <= 0:
        raise ValueError(tr('Could not measure the gap area in square metres.'))
    return area

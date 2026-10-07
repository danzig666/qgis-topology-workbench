"""Plain Python rule configuration, shared by the UI and engine."""
from .i18n import tr
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
import uuid


@dataclass(frozen=True)
class RuleDefinition:
    key: str
    title_source: str
    description_source: str
    geometry_types: tuple = (0, 1, 2)
    reference: bool = False
    tolerance: bool = False

    @property
    def title(self):
        return tr(self.title_source)

    @property
    def description(self):
        return tr(self.description_source)


DEFINITIONS = (
    RuleDefinition("valid", 'Valid geometry', 'Self-intersections, invalid rings and other GEOS geometry errors.'),
    RuleDefinition("empty", 'Must not have empty geometry', 'Find missing or empty geometries.'),
    RuleDefinition("singlepart", 'Single-part features only', 'Flag features with more than one geometry part.'),
    RuleDefinition("duplicates", 'Must not have duplicate geometry', 'Spatially identical geometries; attributes may differ.'),
    RuleDefinition("overlap", 'Polygons must not overlap', 'Overlaps with positive area, including containment and duplicate polygons.', (2,)),
    RuleDefinition("gaps", 'Must not have enclosed gaps', 'Enclosed holes in the union of the polygons. Gaps open to the outer boundary are not flagged.', (2,)),
    RuleDefinition("dangles", 'Must not have dangling line ends', 'Line ends must connect to another line or another part of the same feature. Closed lines are allowed.', (1,), tolerance=True),
    RuleDefinition("covered", 'Must be covered by reference polygons', 'The entire source geometry must be covered by the union of the reference polygons; boundaries are allowed.', reference=True),
    RuleDefinition("cross_overlap", 'Must not overlap the reference layer', 'Find overlaps with positive area between two polygon layers.', (2,), reference=True),
)
RULES = {definition.key: definition for definition in DEFINITIONS}


@dataclass
class Rule:
    kind: str
    layer_id: str
    reference_id: str = ""
    tolerance: float = 0.0
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    layer_name: str = ""
    reference_name: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or value.get("kind") not in RULES:
            raise ValueError(tr('Unknown or invalid rule.'))
        rule = cls(**{k: v for k, v in value.items() if k in cls.__dataclass_fields__})
        if not isinstance(rule.layer_id, str) or not rule.layer_id:
            raise ValueError(tr('Missing source layer.'))
        if not isinstance(rule.reference_id, str) or (RULES[rule.kind].reference and not rule.reference_id):
            raise ValueError(tr('Missing reference layer.'))
        if not isinstance(rule.enabled, bool):
            raise ValueError(tr('The enabled value must be a boolean.'))
        if not isinstance(rule.id, str) or not rule.id:
            raise ValueError(tr('Missing rule ID.'))
        if not isinstance(rule.layer_name, str) or not isinstance(rule.reference_name, str):
            raise ValueError(tr('Layer names must be strings.'))
        rule.tolerance = float(rule.tolerance)
        if not math.isfinite(rule.tolerance) or rule.tolerance < 0:
            raise ValueError(tr('Tolerance must be a finite, nonnegative number.'))
        return rule


def serialize_rules(rules):
    return {"format": "topology-workbench", "version": 1, "rules": [rule.to_dict() for rule in rules]}


def deserialize_rules(document):
    if not isinstance(document, dict) or document.get("format") != "topology-workbench" or document.get("version") != 1:
        raise ValueError(tr('Unsupported rule set.'))
    if not isinstance(document.get("rules"), list):
        raise ValueError(tr('Missing rule list.'))
    rules = [Rule.from_dict(value) for value in document["rules"]]
    if len({rule.id for rule in rules}) != len(rules):
        raise ValueError(tr('Rule IDs must be unique.'))
    return rules


@dataclass
class Issue:
    rule_id: str
    kind: str
    layer_id: str
    layer_name: str
    feature_id: object
    message: str
    geometry: object
    crs: object
    reference_id: str = ""
    reference_name: str = ""
    reference_feature_id: object = None
    area_m2: object = None


@dataclass
class Report:
    issues: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    complete: bool = True
    canceled: bool = False
    checked_features: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    elapsed_seconds: float = 0.0
    scope: str = "all"
    stale: bool = False

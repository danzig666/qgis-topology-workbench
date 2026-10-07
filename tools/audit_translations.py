"""Audit translation completeness and formatting without requiring PyQGIS."""
import ast
import configparser
import json
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "topology_workbench"
catalog = json.loads((PLUGIN / "i18n" / "hu.json").read_text(encoding="utf-8"))
sources = set()
for path in PLUGIN.glob("*.py"):
    text = path.read_text(encoding="utf-8")
    compile(text, str(path), "exec")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "tr" and node.args and isinstance(node.args[0], ast.Constant):
                sources.add(node.args[0].value)
            elif node.func.id == "RuleDefinition":
                sources.update(arg.value for arg in node.args[1:3])
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "HEADERS" for target in node.targets):
            sources.update(item.value for item in node.value.elts if item.value != "#")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(character in node.value for character in "áéíóöőúüűÁÉÍÓÖŐÚÜŰ"):
                raise AssertionError(f"Untranslated Hungarian literal in {path.name}:{node.lineno}")
missing = sources.difference(catalog)
assert not missing, f"Missing Hungarian translations: {missing}"
for source, translated in catalog.items():
    assert isinstance(translated, str) and translated, source
    fields = lambda text: sorted((name, spec, conversion) for _, name, spec, conversion in Formatter().parse(text) if name is not None)
    assert fields(source) == fields(translated), f"Mismatched placeholders: {source}"
metadata = configparser.ConfigParser()
metadata.read(PLUGIN / "metadata.txt", encoding="utf-8")
for key in ("description", "about"):
    assert metadata["general"][key]
    assert metadata["general"][f"{key}[hu]"]
print(f"Source syntax, {len(sources)} English messages, {len(catalog)} Hungarian translations, placeholders and localized metadata: OK")

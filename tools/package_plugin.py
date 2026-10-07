"""Create a deterministic, dependency-free ZIP accepted by QGIS Install from ZIP."""
from pathlib import Path
import configparser
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "topology_workbench"
metadata = configparser.ConfigParser()
metadata.read(PLUGIN / "metadata.txt", encoding="utf-8")
version = metadata["general"]["version"]
output = ROOT / "dist"
output.mkdir(exist_ok=True)
destination = output / f"topology_workbench-{version}.zip"
with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for source in sorted(PLUGIN.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        item = zipfile.ZipInfo(source.relative_to(ROOT).as_posix(), date_time=(2026, 10, 7, 0, 0, 0))
        item.compress_type = zipfile.ZIP_DEFLATED
        item.create_system = 3
        item.external_attr = 0o100644 << 16
        archive.writestr(item, source.read_bytes())
    for filename in ("README.md", "LICENSE", "CHANGELOG.md", "docs/README.hu.md",
                     "docs/images/workbench-en.png", "docs/images/layer-lookup-en.png"):
        source = ROOT / filename
        item = zipfile.ZipInfo(f"topology_workbench/{filename}", date_time=(2026, 10, 7, 0, 0, 0))
        item.compress_type = zipfile.ZIP_DEFLATED
        item.create_system = 3
        item.external_attr = 0o100644 << 16
        archive.writestr(item, source.read_bytes())
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert "topology_workbench/__init__.py" in archive.namelist()
    assert "topology_workbench/metadata.txt" in archive.namelist()
digest = hashlib.sha256(destination.read_bytes()).hexdigest()
destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
print(f"{destination} ({destination.stat().st_size:,} bytes)\nSHA256 {digest}")

demo = output / f"topology_workbench-demo-{version}.zip"
with zipfile.ZipFile(demo, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for source in sorted((ROOT / "examples").glob("topology-demo*")):
        if source.suffix not in (".qgz", ".gpkg", ".json"):
            continue
        item = zipfile.ZipInfo(source.name, date_time=(2026, 10, 7, 0, 0, 0))
        item.compress_type = zipfile.ZIP_DEFLATED
        item.create_system = 3
        item.external_attr = 0o100644 << 16
        archive.writestr(item, source.read_bytes())
demo_digest = hashlib.sha256(demo.read_bytes()).hexdigest()
demo.with_suffix(".zip.sha256").write_text(f"{demo_digest}  {demo.name}\n", encoding="ascii")
print(f"{demo} ({demo.stat().st_size:,} bytes)")

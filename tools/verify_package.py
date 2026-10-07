"""Load the packaged ZIP through QGIS's real plugin loader in an isolated path."""
import configparser
import os
from pathlib import Path
import runpy
import sys
import tempfile
import zipfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
source_metadata = configparser.ConfigParser()
source_metadata.read(ROOT / "topology_workbench" / "metadata.txt", encoding="utf-8")
version = source_metadata["general"]["version"]
from qgis.core import Qgis, QgsProject
from qgis import utils
from pyplugin_installer.version_compare import isCompatible
with tempfile.TemporaryDirectory(prefix="topology-package-") as folder:
    with zipfile.ZipFile(ROOT / "dist" / f"topology_workbench-{version}.zip") as archive:
        archive.extractall(folder)
    metadata = configparser.ConfigParser()
    metadata.read(Path(folder) / "topology_workbench" / "metadata.txt", encoding="utf-8")
    assert isCompatible(Qgis.QGIS_VERSION.split("-")[0], metadata["general"]["qgisMinimumVersion"],
                        metadata["general"]["qgisMaximumVersion"])
    sys.path.insert(0, folder)
    __import__("topology_workbench")
    # Bootstrap QApplication and the fake interface, without writing a QGIS profile.
    bootstrap = runpy.run_path(str(ROOT / "tests" / "test_qgis.py"))
    APP = bootstrap["APP"]
    iface = bootstrap["FakeIface"]()
    utils.iface = iface
    utils.plugin_paths = [folder]
    utils.updateAvailablePlugins()
    assert "topology_workbench" in utils.available_plugins
    assert utils.loadPlugin("topology_workbench")
    assert Path(sys.modules["topology_workbench"].__file__).resolve().is_relative_to(Path(folder).resolve())
    assert utils.startPlugin("topology_workbench")
    plugin = utils.plugins["topology_workbench"]
    plugin.show_dock()
    assert plugin.dock is not None
    from topology_workbench.i18n import language_for_locale
    expected = "Ellenőrzés indítása" if language_for_locale(bootstrap["TEST_LOCALE"]) == "hu" else "Run checks"
    assert plugin.dock.run_button.text() == expected
    from qgis.PyQt.QtCore import Qt
    expected_area = "Terület (m²)" if language_for_locale(bootstrap["TEST_LOCALE"]) == "hu" else "Area (m²)"
    assert plugin.dock.model.headerData(6, Qt.Orientation.Horizontal) == expected_area
    APP.processEvents()
    assert utils.unloadPlugin("topology_workbench")
    iface.window.close()
    QgsProject.instance().clear()
    APP.processEvents()
    APP.exitQgis()
    print(f"Packaged ZIP {version}: metadata, discovery, load, initGui, localized dock, unload OK on QGIS {Qgis.QGIS_VERSION}; {bootstrap['TEST_LOCALE']}")

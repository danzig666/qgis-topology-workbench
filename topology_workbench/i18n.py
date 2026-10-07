"""Qt translations selected from QGIS's interface language, not its number locale.

The UTF-8 catalog is shipped with the plugin, so installing the ZIP requires no
Qt Linguist compiler and the same catalog works with the Qt5 and Qt6 bindings.
"""
from functools import lru_cache
import json
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator
from qgis.core import QgsApplication

CONTEXT = "TopologyWorkbench"


def qgis_locale():
    app = QgsApplication.instance()
    # translation() is the active interface translation. locale() can also
    # reflect a different locale chosen for number formatting in QGIS.
    active = app.translation() if app is not None else ""
    return active or QgsApplication.locale() or QLocale.system().name()


def language_for_locale(locale):
    language = str(locale or "").strip().replace("-", "_").split("_")[0].lower()
    return "hu" if language == "hu" else "en"


@lru_cache(maxsize=1)
def hungarian_catalog():
    path = Path(__file__).with_name("i18n") / "hu.json"
    return json.loads(path.read_text(encoding="utf-8"))


class CatalogTranslator(QTranslator):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = hungarian_catalog()

    def isEmpty(self):
        return not self.catalog

    def translate(self, context, source_text, disambiguation=None, n=-1):
        if context == CONTEXT:
            return self.catalog.get(source_text)
        # A null QString allows other translators (QGIS, Qt and other plugins)
        # to handle their own contexts without this plugin intercepting them.
        return None


class PluginTranslation:
    def __init__(self, locale=None):
        self.language = language_for_locale(qgis_locale() if locale is None else locale)
        self.translator = None

    def install(self):
        if self.language == "hu" and self.translator is None:
            translator = CatalogTranslator(QCoreApplication.instance())
            if not QCoreApplication.installTranslator(translator):
                raise RuntimeError("Could not install the Hungarian translation catalog.")
            self.translator = translator

    def remove(self):
        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None


def tr(source_text, *values):
    """Translate before inserting dynamic values, preserving names and IDs."""
    translated = QCoreApplication.translate(CONTEXT, source_text)
    return translated.format(*values) if values else translated

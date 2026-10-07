from .i18n import tr
from pathlib import Path
from qgis.PyQt.QtGui import QIcon
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction
from .compat import DOCK_RIGHT
from .dock import WorkbenchDock
from .i18n import PluginTranslation


class TopologyWorkbenchPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None
        self.translation = None

    def initGui(self):
        self.translation = PluginTranslation()
        self.translation.install()
        self.action = QAction(QIcon(str(Path(__file__).with_name("icon.svg"))), "Topology Workbench", self.iface.mainWindow())
        self.action.setToolTip(tr('Topology checks with searchable layer selection and export'))
        self.action.triggered.connect(self.show_dock)
        self.iface.addPluginToVectorMenu("Topology Workbench", self.action)
        self.iface.addToolBarIcon(self.action)

    def show_dock(self):
        if self.dock is None:
            self.dock = WorkbenchDock(self.iface)
            self.iface.addDockWidget(DOCK_RIGHT, self.dock)
        self.dock.show()
        self.dock.raise_()

    def unload(self):
        if self.action:
            self.iface.removePluginVectorMenu("Topology Workbench", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
        if self.dock:
            self.dock.cleanup()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.translation:
            self.translation.remove()
            self.translation = None

"""QGIS plugin entry point; imports are delayed until QGIS loads the plugin."""


def classFactory(iface):
    from .plugin import TopologyWorkbenchPlugin
    return TopologyWorkbenchPlugin(iface)

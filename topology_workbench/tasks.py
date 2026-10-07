from .i18n import tr
from qgis.core import QgsTask
from .engine import TopologyEngine
from .models import Report


class CheckTask(QgsTask):
    def __init__(self, rules, snapshots, context, scope, max_errors, on_finished):
        super().__init__(tr('Topology Workbench – check'), QgsTask.Flag.CanCancel)
        self.engine = TopologyEngine(rules, snapshots, context, scope, max_errors,
                                     canceled=self.isCanceled, progress=self.setProgress)
        self.on_finished = on_finished
        self.report = None

    def run(self):
        try:
            self.report = self.engine.run()
            return not self.report.canceled
        except Exception as error:
            self.report = Report(complete=False, warnings=[str(error)])
            return False

    def finished(self, result):
        if not result and self.report and self.report.complete:
            self.report.complete = False
            self.report.canceled = True
            self.report.warnings.append(tr('The check was canceled; the issue list is incomplete.'))
        if self.on_finished:
            self.on_finished(self.report or Report(complete=False, canceled=True,
                                                   warnings=[tr('The check did not start.')]))

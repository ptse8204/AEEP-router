"""First-party glue for pytest's public collection and runtest-report hooks.

No subject imports, stdout parsing, identity rewriting or successful collection
grades. A PASS requires all three native runtest phases to have passed.
"""


class NativeCapture:
    def __init__(self, collect_only=False):
        self.collect_only = collect_only
        self.native_ids = []
        self.selected_ids = []
        self.phases = {}
        self.problems = set()

    def _identity(self, value):
        if not isinstance(value, str) or not value or not value.isprintable() or len(value.encode('utf-8')) > 8192:
            self.problems.add('invalid_identity')
            return False
        return True

    def pytest_itemcollected(self, item):
        if self.collect_only and self._identity(item.nodeid):
            if len(self.native_ids) >= 10000:
                self.problems.add('collection_limit')
            else:
                self.native_ids.append(item.nodeid)

    def pytest_collection_finish(self, session):
        for item in session.items:
            if self._identity(item.nodeid):
                if len(self.selected_ids) >= 10000:
                    self.problems.add('selected_limit')
                    break
                self.selected_ids.append(item.nodeid)

    def pytest_runtest_logreport(self, report):
        if not self._identity(report.nodeid):
            return
        if report.when not in ('setup', 'call', 'teardown') or report.outcome not in ('passed', 'failed', 'skipped'):
            self.problems.add('invalid_phase_or_outcome')
            return
        if report.nodeid not in self.phases and len(self.phases) >= 10000:
            self.problems.add('report_limit')
            return
        phases = self.phases.setdefault(report.nodeid, {})
        if report.when in phases:
            self.problems.add('duplicate_phase')
            return
        phases[report.when] = (report.outcome, hasattr(report, 'wasxfail'))

    def export(self):
        if len(set(self.selected_ids)) != len(self.selected_ids):
            self.problems.add('duplicate_selected_identity')
        if self.collect_only:
            if len(set(self.native_ids)) != len(self.native_ids):
                self.problems.add('duplicate_collected_identity')
            if not set(self.selected_ids) <= set(self.native_ids) or self.phases:
                self.problems.add('collection_scope_mismatch')
            if self.problems:
                raise ValueError('native_collection_protocol:' + ','.join(sorted(self.problems)))
            return {'native_ids': self.native_ids, 'selected_ids': self.selected_ids}
        if not set(self.phases) <= set(self.selected_ids):
            self.problems.add('unselected_report_identity')
        statuses = {}
        for node, phases in self.phases.items():
            if any(outcome == 'failed' for when, (outcome, _) in phases.items() if when != 'call'):
                statuses[node] = 'ERROR'
            elif any(outcome == 'skipped' for outcome, _ in phases.values()):
                statuses[node] = 'XFAIL' if any(xfail for _, xfail in phases.values()) else 'SKIPPED'
            elif 'call' in phases:
                outcome, xfail = phases['call']
                if xfail:
                    statuses[node] = 'XFAIL'  # Unexpected passes never satisfy a required PASS.
                elif outcome == 'failed':
                    statuses[node] = 'FAILED'
                elif set(phases) == {'setup', 'call', 'teardown'} and all(v == ('passed', False) for v in phases.values()):
                    statuses[node] = 'PASSED'
                else:
                    self.problems.add('incomplete_pass_phases')
        if self.problems:
            raise ValueError('native_report_protocol:' + ','.join(sorted(self.problems)))
        # Missing reports stay absent; the protected coordinator rejects missing IDs.
        return {'statuses': statuses}

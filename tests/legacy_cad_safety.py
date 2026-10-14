"""Opt-in safety envelope for the bounded legacy part pilot, not v2 acceptance."""
import json
import time
from pathlib import Path


def close_owned_part(session, owned, identity):
    """Synchronous test calls have returned; never close by current document alone."""
    current = session._open_documents()
    if not current:
        session._model = None
        return 'already_closed'
    if len(current) != 1 or identity(current[0]) != identity(owned):
        raise RuntimeError('Unknown document roster; retained without closing.')
    model = current[0]
    if int(model.GetBlockingState()) != 0:
        raise RuntimeError('Owned document is blocked; retained without closing.')
    revision = int(model.GetUpdateStamp())
    title, path = model.GetTitle(), model.GetPathName()
    if identity(model) != identity(owned) or int(model.GetUpdateStamp()) != revision:
        raise RuntimeError('Owned document changed before cleanup; retained.')
    session._sw.CloseDoc(title)
    if session._open_documents():
        raise RuntimeError('CloseDoc did not restore the empty roster.')
    session._model = None
    return dict(closed=True, title=title, path=path, revision=revision)


class LegacyPilotAudit:
    def __init__(self, session, report_path):
        # Lazy imports keep ordinary pure collection entirely outside COM.
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        import pythoncom
        from verify_export_operations import application_preferences
        self.session = session
        self.identity = lambda model: model._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
        self.preferences = application_preferences
        self.path = Path(report_path).resolve()
        private = Path(__file__).resolve().parents[1] / 'work'
        if not self.path.is_relative_to(private) or self.path.exists():
            raise RuntimeError('Use a fresh private legacy pilot report under work/.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.before = self.preferences(session._sw)
        self.visible = bool(session._sw.Visible)
        self.started = time.perf_counter()
        self.report = dict(scope='legacy_source_part_pilot_safety_v1', accepted=False,
                           solidworks_revision=str(session._sw.RevisionNumber()),
                           baseline_empty=True, baseline_guard=False, owned=[],
                           cleanup_seconds=0., preferences_before=self.before)
        self.persist()

    def persist(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding='utf8')

    def own(self, model, nodeid):
        current = self.session._open_documents()
        if len(current) != 1 or self.identity(current[0]) != self.identity(model):
            raise RuntimeError('Pilot did not create exactly one owned part.')
        self.report['owned'].append(dict(nodeid=nodeid, title=model.GetTitle(),
                                         path=model.GetPathName(), closed=False))
        self.persist()

    def close(self, model):
        started = time.perf_counter()
        try:
            if self.session._sw.CommandInProgress is not True:
                raise RuntimeError('Pilot lost its owned command guard.')
            result = close_owned_part(self.session, model, self.identity)
            self.report['owned'][-1].update(closed=True, cleanup=result)
        except BaseException as exc:
            self.report.update(cleanup_unknown=True, error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            self.report['cleanup_seconds'] += time.perf_counter() - started
            self.persist()

    def finish(self):
        try:
            after = self.preferences(self.session._sw)
            changed = [key for key in self.before if self.before[key] != after[key]]
            # Geometry-dependent STL settings are explicitly outside this pilot.
            scoped = [key for key in changed if not key.startswith('stl_')]
            self.report.update(preferences_after=after, changed_preferences=changed,
                               non_stl_changed=scoped, stl_verified=False,
                               final_roster_empty=not self.session._open_documents(),
                               final_guard=bool(self.session._sw.CommandInProgress),
                               visibility_restored=bool(self.session._sw.Visible) == self.visible,
                               elapsed_seconds=time.perf_counter() - self.started)
            if (scoped or not self.report['final_roster_empty'] or self.report['final_guard']
                    or not self.report['visibility_restored'] or self.report.get('cleanup_unknown')
                    or not all(row['closed'] for row in self.report['owned'])):
                raise RuntimeError('Legacy pilot final safety postconditions failed.')
            self.report['accepted'] = True
        finally:
            self.persist()

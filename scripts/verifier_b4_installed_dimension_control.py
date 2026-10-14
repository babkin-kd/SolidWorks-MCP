"""Original child-owned dimension return/finish receipts; no native Q authority.

Install before server factories run. Arm uses only the prepared Python catalog
and coherent terminal journal; no preparation, COM/getters or target dispatch.
Release is explicit original-finish control, never crash/restart/reconciliation.
"""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import re
from threading import RLock

from solidworks_mcp import __version__
from solidworks_mcp.dimensions import DimensionCatalog, SCOPE
from solidworks_mcp.jobs import _json
from solidworks_mcp.runtime_v2 import Runtime


def sibling(filename, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


owned = sibling('verifier_b4_owned_child_process.py', '_b4_control_owned')
finished = sibling('verifier_b4_installed_finish.py', '_b4_control_finish')
returned = sibling('verifier_b4_dimension_return.py', '_b4_control_return')


class DimensionControlError(RuntimeError):
    def __init__(self, message, *, retained_owner=None):
        super().__init__(message)
        self.retained_owner = retained_owner


def require(condition, message):
    if not condition:
        raise DimensionControlError(message)


def private_root():
    return Path(__file__).resolve().parents[1] / 'work'


def authority():
    return dict(accepted=False, native_q='not_run', native_admission='not_run', independent_postconditions='not_run',
                process_stop_authorized=False, restart_authorized=False, cad_cleanup_authorized=False)


class InstalledDimensionControl:
    def __init__(self, server_module, *, state_root, lineage):
        keys = {'package_version', 'git_sha', 'wheel_sha256', 'source_digest', 'nonce', 'owner_pid', 'state_root'}
        require(type(lineage) is dict and set(lineage) == keys, 'Exact child version/nonce/root lineage required.')
        self.root = Path(state_root).resolve()
        require(self.root.is_dir() and self.root.is_relative_to(private_root().resolve())
                and lineage['state_root'] == str(self.root) and lineage['owner_pid'] == os.getpid()
                and type(lineage['owner_pid']) is int and lineage['package_version'] == __version__,
                'Original current child/version/private root required.')
        require(all(type(lineage[key]) is str and re.fullmatch('[0-9a-f]{' + str(size) + '}', lineage[key])
                    for key, size in (('git_sha', 40), ('wheel_sha256', 64), ('source_digest', 64), ('nonce', 64))),
                'Exact clean build/wheel/source/nonce identities required.')
        manifest = owned._read(self.root / 'launch-spec.json')
        wheel = manifest['candidate']['wheel']
        require(manifest['state_dir'] == str(self.root) and manifest['nonce'] == lineage['nonce']
                and all(wheel[key] == lineage[key] for key in ('package_version', 'git_sha', 'wheel_sha256', 'source_digest')),
                'Original own-root launch manifest lineage differs.')
        require(not any((self.root / name).exists() for name in
                ('callback-return.json', 'finish-barrier.json', 'dimension-control-closed.json')),
                'Fresh control receipt paths required; no receipt adoption.')
        self.lineage = deepcopy(lineage)
        self._launch_manifest = deepcopy(manifest)
        self.seam = finished.InstalledFinishSeam(server_module, journal_path=self.root / 'server' / 'jobs.sqlite',
                                               persist=self._persist_finish)
        self.observer = self.target = self._original_barrier = None
        self._phase, self._fault = 'new', None
        self._arm_attempted = self._release_attempted = self._shutdown_prepared = self._close_attempted = False
        self._persist_attempted = {'callback': False, 'finish': False}
        self._receipts = {'callback': None, 'finish': None}
        self._lock = RLock()

    @property
    def runtime(self):
        return self.seam.runtime

    @property
    def proxy(self):
        return self.seam.proxy

    def _fail(self, exc):
        with self._lock:
            self._phase = 'failed'
            if self._fault is None:
                self._fault = type(exc).__name__ + ': ' + str(exc)
        raise DimensionControlError(self._fault, retained_owner=self) from exc

    def _lineage(self, runtime, lineage):
        require(os.getpid() == self.lineage['owner_pid'] and _json(lineage) == _json(self.lineage),
                'Original live child/root/version/nonce required.')
        require(_json(owned._read(self.root / 'launch-spec.json')) == _json(self._launch_manifest),
                'Original launch manifest changed; no owner/root identity adoption.')
        self.seam.assert_wired(runtime)

    def install(self):
        try:
            require(self._phase == 'new', 'Original controller installation is one-shot.')
            self.seam.install()
            self._phase = 'unarmed'
            return self
        except Exception as exc:
            self._fail(exc)

    def _prepared_history(self, rows, payload):
        context = payload['context']
        require(all(row['status'] == 'succeeded' and row['error'] is None and row['payload']['mutates'] is False
                    and row['mutation'] is None and row['operation'] in ('document.list', 'dimension.list', 'dimension.get')
                    for row in rows), 'Only original terminal successful discovery/dimension reads may precede arm.')
        discovery = [row for row in rows if row['operation'] == 'document.list']
        require(discovery and any(item['document_id'] == context['document_id'] for item in discovery[-1]['result']['documents']),
                'Original successful discovery must contain this exact prepared document.')
        reads = [row for row in rows if row['operation'] in ('dimension.list', 'dimension.get')]
        require(reads and all(row['payload']['arguments']['document_id'] == context['document_id']
                and row['payload']['arguments']['configuration'] == context['configuration'] for row in reads),
                'Prepared dimension reads must belong only to this original target/configuration.')
        last = reads[-1]['result']
        items = last['items'] if 'items' in last else [last['dimension']]
        require(last['document_id'] == context['document_id'] and last['configuration'] == context['configuration']
                and last['revision'] == context['expected_revision'] and last['revision_scope'] == SCOPE
                and any(item['object_id'] == context['object_id'] for item in items),
                'Exact latest terminal prepared dimension/revision evidence required.')

    def arm(self, *, runtime, lineage, request_id, operation, payload):
        try:
            with self._lock, self.proxy._lock:
                require(not self._arm_attempted and self._phase == 'unarmed', 'Original target arm is one-shot; no retry.')
                self._arm_attempted = True
                self._lineage(runtime, lineage)
                require(operation == 'dimension.set_value' and type(runtime) is Runtime
                        and type(runtime._dimensions) is DimensionCatalog and runtime._runner is not None,
                        'Original runtime must already own its prepared dimension catalog/worker.')
                require(type(request_id) is str and bool(request_id.strip()) and type(payload) is dict
                        and set(payload) == {'arguments', 'context', 'mutates'} and payload['mutates'] is True,
                        'Exact new request/operation/durable payload required.')
                rows = finished._barrier._read_journal(self.proxy.path)
                require(not any(row['request_id'] == request_id for row in rows), 'Original target must not exist before arm.')
                self._prepared_history(rows, payload)
                dimensions = runtime._dimensions
                entries = [entry for entry in runtime._catalog._entries if entry.document_id == payload['context']['document_id']]
                require(len(entries) == 1 and payload['context']['object_id'] in
                        entries[0].features.get('dimensions', {}).get('references', {}),
                        'Original cached prepared dimension namespace required; no getter or reference discovery.')
                reference = entries[0].features['dimensions']['references'][payload['context']['object_id']]
                require(reference.object_id == payload['context']['object_id']
                        and reference.configuration == payload['context']['configuration'],
                        'Original cached dimension/configuration identity differs.')
                self.target = dict(request_id=request_id, operation=operation, payload=deepcopy(payload))
                self.observer = returned.DimensionReturnObserver(runtime, request_id=request_id, payload=payload,
                                                                 persist=self._persist_return).install()
                result = self.proxy.arm(runtime=runtime, request_id=request_id, operation=operation, payload=payload)
                self._original_barrier = self.proxy.barrier
                self._phase = 'armed'
                return dict(scope='b4_installed_dimension_control_arm_v1', lineage=deepcopy(self.lineage),
                            target=deepcopy(self.target), finish_arm=result, **authority())
        except Exception as exc:
            self._fail(exc)

    def _persist(self, kind, original):
        try:
            with self._lock:
                require(self._phase == 'armed' and not self._persist_attempted[kind], 'Original receipt persistence is one-shot.')
                self._persist_attempted[kind] = True
                self._lineage(self.runtime, self.lineage)
                rows = finished._barrier._read_journal(self.proxy.path)
                matches = [row for row in rows if row['operation_id'] == original['operation_id']]
                require(len(matches) == 1 and matches[0]['request_id'] == self.target['request_id']
                        and matches[0]['operation'] == self.target['operation']
                        and _json(matches[0]['payload']) == _json(self.target['payload']), 'Original receipt target journal differs.')
                if kind == 'callback':
                    observed = self.observer.observation()
                    require(observed['persist_attempted'] is True and _json(observed['receipt']) == _json(original),
                            'Only original return observer may persist its actual receipt.')
                    dto = dict(matches[0])
                    dto.pop('digest')
                    require(_json(dto) == _json(original['journal_row_before_finish']), 'Full actual callback row differs.')
                else:
                    require(self.proxy.barrier is self._original_barrier and self._receipts['callback'] is not None
                            and _json(original['journal']) == _json(rows)
                            and _json(original['return_result']) == _json(self._receipts['callback']['original_receipt']['return_result']),
                            'Original finish barrier must follow the durable actual return receipt.')
                receipt = dict(scope='b4_installed_dimension_control_' + kind + '_v1', lineage=deepcopy(self.lineage),
                    target=deepcopy(self.target), original_receipt=deepcopy(original), journal=rows, **authority())
                name = 'callback-return.json' if kind == 'callback' else 'finish-barrier.json'
                owned._write(self.root / name, receipt)
                self._receipts[kind] = receipt
        except Exception as exc:
            self._fail(exc)

    def _persist_return(self, original):
        self._persist('callback', original)

    def _persist_finish(self, original):
        self._persist('finish', original)

    def release(self, *, runtime, lineage):
        try:
            with self._lock:
                require(not self._release_attempted and self._fault is None, 'Original finish release is one-shot; no retry.')
                self._release_attempted = True
                self._lineage(runtime, lineage)
                require(self.proxy.barrier is self._original_barrier and self._original_barrier is not None
                        and self._receipts['finish'] is not None, 'Original durable waiting finish required.')
                self.proxy.release(runtime=runtime)
                self._phase = 'released'
                return authority()
        except Exception as exc:
            self._fail(exc)

    def prepare_normal_shutdown(self):
        try:
            require(self._fault is None and not self._shutdown_prepared, 'Original normal shutdown preparation is one-shot.')
            if self.observer is not None:
                require(self._phase == 'released' and self._original_barrier.state == 'finished'
                        and self.observer.observation()['callback_live'] is False, 'Original released finish/callback must complete first.')
                self.observer.uninstall()
            self._shutdown_prepared = True
            self._phase = 'ready_for_normal_shutdown'
            return authority()
        except Exception as exc:
            self._fail(exc)

    def complete_normal(self):
        try:
            require(self._fault is None and not self._close_attempted, 'Original normal completion is one-shot.')
            self._close_attempted = True
            if self.observer is not None:
                require(self._shutdown_prepared, 'Unwire original observer before Runtime shutdown, never adopt released catalogs.')
            self._lineage(self.runtime, self.lineage)
            require(self.runtime._closed is True and self.proxy._closed is True and self.proxy._store._db is None,
                    'Original Runtime/store must already close normally after server return.')
            rows = finished._barrier._read_journal(self.proxy.path)
            require(all(row['status'] not in ('queued', 'running', 'unknown') and
                    (row['mutation'] is None or row['mutation']['phase'] not in ('prepared', 'unresolved')) for row in rows),
                    'Normal control completion cannot close unresolved or live history.')
            self.seam.uninstall()
            receipt = dict(scope='b4_installed_dimension_control_closed_v1', lineage=deepcopy(self.lineage),
                target=deepcopy(self.target), journal=rows, original_factories_restored=True, **authority())
            owned._write(self.root / 'dimension-control-closed.json', receipt)
            self._phase = 'closed'
            return receipt
        except Exception as exc:
            self._fail(exc)

    def inspect_state(self):
        with self._lock:
            state = dict(scope='b4_installed_dimension_control_state_v1', phase=self._phase, fault=self._fault,
                lineage=deepcopy(self.lineage), target=deepcopy(self.target), persist_attempted=deepcopy(self._persist_attempted),
                receipts=deepcopy(self._receipts), **authority())
        # Do not hold controller lock while acquiring observer's callback lock.
        state['return_observation'] = None if self.observer is None else self.observer.observation()
        state['barrier_state'] = None if self._original_barrier is None else self._original_barrier.state
        return state

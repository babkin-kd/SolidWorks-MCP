"""Guarded standalone construction executor and exact returned feature IDs.

Only fully observed effects may authorize an owned inverse. Missing receipts,
pending calls, storage failures and foreign deltas retain application holds.
"""
from copy import deepcopy

from .documents import rejected
from .jobs import ExecutionFailure, _json
from .mutations import MutationCoordinator, PreparedMutation
from .rectangle_construction import RectangleSketch, BlindRectangleExtrusion
from .rectangle_postconditions import verified_rectangle_sketch
from .rectangle_extrusion_postconditions import verified_rectangle_extrusion


class RectangleConstructionExecutionMixin:
    def create_sketch(self, operation_id, document_id, configuration, expected_revision, **parameters):
        definition = RectangleSketch.validate(**parameters)
        return self._execute_rectangle(operation_id, document_id, configuration, expected_revision,
            definition, self.prepare_sketch, verified_rectangle_sketch, 'sketch')

    def create_extrusion(self, operation_id, document_id, configuration, expected_revision, **parameters):
        definition = BlindRectangleExtrusion.validate(**parameters)
        return self._execute_rectangle(operation_id, document_id, configuration, expected_revision,
            definition, self.prepare_extrusion, verified_rectangle_extrusion, 'extrusion')

    def _execute_rectangle(self, operation_id, document_id, configuration, expected_revision,
                           definition, prepare_public, admission, kind):
        context = dict(entries=(), receipt=None, guarded_ids=(), manager=None,
            guard_released=False, release_attempted=False, pending_release=False,
            journal_failed=False, reference_binding_unconfirmed=False,
            guards=[], created_native_id=None, verified_mode=None)

        def record(label, phase, evidence):
            context['journal_failed'] = True
            self.store.record_mutation_step(operation_id, name='rectangle_' + label,
                phase=phase, evidence=evidence)
            context['journal_failed'] = False

        def receipt_evidence():
            receipt = context['receipt']
            if receipt is None: return None
            return {key: getattr(receipt, key) for key in ('attempted', 'native_call_returned',
                'pending_creation', 'pending_sketch_close', 'sketch_closed', 'selection_uncertain',
                'restore_attempted', 'restored', 'pending_native_step', 'native_step_journal_failed')}

        def pending():
            r = receipt_evidence()
            return (context['journal_failed'] or context['pending_release']
                or context['reference_binding_unconfirmed'] or (r is not None and
                (r['pending_creation'] or r['pending_sketch_close'] or r['selection_uncertain']
                 or r['pending_native_step'] is not None or r['native_step_journal_failed'])))

        def prepare():
            if len(self.receipts) >= 1000:
                raise rejected('rectangle_receipt_budget', 'Reconcile retained native receipts before further construction.')
            public = prepare_public(document_id, configuration, **vars(definition))
            entry, _ = self.documents.resolve(document_id, configuration)
            entries, semantic, snapshots = self._capture(document_id)
            state = dict(semantic=semantic, snapshots=snapshots)
            target = next((e for e in entries if e.document_id == document_id), None)
            if state != public['baseline'] or target is None or target.identity != entry.identity:
                raise rejected('rectangle_snapshot_changed', 'Complete preparation changed before the checkpoint.')
            cfg = self.adapter.configuration_identity(entry.model, configuration)
            objects = self.adapter.features(entry.model)
            object_id = definition.plane_object_id if kind == 'sketch' else definition.sketch_object_id
            feature, reference = self.features._resolve(entry, configuration, cfg, objects, object_id)
            if reference.persistent_id.hex() != public['reference_persistent_id_hex']:
                raise rejected('rectangle_snapshot_changed', 'The exact reference changed before checkpointing.')
            receipt = self.adapter.new_rectangle_stage_receipt(entry.model, objects,
                snapshots[document_id]['clone_state']['creation_controls'],
                sketch=feature if kind == 'extrusion' else None, recorder=record)
            context.update(entry=entry, entries=entries, reference=feature, receipt=receipt,
                guarded_ids=tuple(e.document_id for e in entries))
            self.receipts[operation_id] = context
            return PreparedMutation(public['revision'], dict(scope=public['scope'], baseline=state,
                definition=vars(definition), reference_persistent_id_hex=reference.persistent_id.hex(),
                reference_native_id=self.adapter.feature_summary(feature)['native_id'],
                plane_transform=public['plane_transform']), effect_scope='application')

        def validate(prepared):
            profile = prepared.before['baseline']['snapshots'][document_id]['clone_state']['profile']
            scope = prepared.before['scope']
            object_id = definition.plane_object_id if kind == 'sketch' else definition.sketch_object_id
            current = self._prepare(document_id, configuration, definition, profile, scope,
                object_id, 'RefPlane' if kind == 'sketch' else 'ProfileFeature',
                guarded_ids=context['guarded_ids'])
            entry, _ = self.documents.resolve(document_id, configuration)
            return current['revision'] == prepared.revision and entry.identity == context['entry'].identity

        def enter_guard(label):
            record(label, 'pending', dict(document_ids=[e.document_id for e in context['entries']]))
            manager = self.adapter.native_open_guard(tuple(e.model for e in context['entries']),
                tuple(e.document_id for e in context['entries']))
            context.update(manager=manager, guarded_ids=tuple(e.document_id for e in context['entries']),
                           release_attempted=False, guard_released=False)
            context['guards'].append(manager)
            manager.__enter__()
            record(label, 'returned', deepcopy(manager.evidence))

        def release_guard(*args, journal=True):
            if context['release_attempted']:
                raise ExecutionFailure('rectangle_guard_release_repeated', 'Owned guard release is one-shot.', uncertain=True)
            label = 'guard_release_' + str(len(context['guards']))
            if journal: record(label, 'pending', dict(document_ids=list(context['guarded_ids'])))
            context['release_attempted'], context['pending_release'] = True, True
            result = context['manager'].__exit__(*(args or (None, None, None)))
            context.update(guard_released=True, pending_release=False, guarded_ids=())
            if journal: record(label, 'returned', deepcopy(context['manager'].evidence))
            return result

        def inspect(prepared):
            entries, semantic, snapshots = self._capture(document_id, context['guarded_ids'])
            if [e.identity for e in entries] != [e.identity for e in context['entries']]:
                raise rejected('rectangle_session_changed', 'The exact model incarnations changed during execution.')
            return dict(state=dict(semantic=semantic, snapshots=snapshots), receipt=receipt_evidence(),
                original_files=self.sessions.census._disk_files(prepared.before['baseline']['semantic']),
                pending=pending(), guard_released=context['guard_released'])

        def effect(before, observed):
            r = observed['receipt']
            if kind=='sketch':
                snapshot=observed['state']['snapshots'][document_id]
                sketch=snapshot['clone_state'].get('sketch')
                if not isinstance(sketch,dict):return False
                plane=sketch['reference_plane']
                role=plane['pid_hex']['reference_role']
                anchors=[ref['token'] for ref in snapshot['references'] if ref['kind']=='feature' and ref['role']==role]
                if (plane['native_id']!=before['reference_native_id']
                        or anchors!=[before['reference_persistent_id_hex']]
                        or plane['transform']!=[float(v).hex() for v in before['plane_transform']]):return False
            return (observed['pending'] is False and r is not None and r['attempted'] is True
                and r['native_call_returned'] is True and r['restored'] is False
                and (kind != 'sketch' or r['sketch_closed'] is True)
                and observed['original_files'] == before['baseline']['semantic']['files']
                and admission(before['baseline'], observed['state'], document_id,
                              definition, context['created_native_id']))

        def apply(prepared):
            receipt, model = context['receipt'], context['entry'].model
            if kind == 'sketch':
                self.adapter.create_rectangle_sketch(model, context['reference'], definition, receipt)
            else:
                self.adapter.extrude_rectangle_sketch(model, definition, receipt)
            created = receipt.sketch if kind == 'sketch' else receipt.extrusion
            owned_identity = receipt.sketch_identity if kind == 'sketch' else receipt.extrusion_identity
            if created is None or self.adapter.identity(created) != owned_identity:
                raise ExecutionFailure('rectangle_created_handle_unconfirmed', 'No exact owned returned handle.', uncertain=True)
            context['created_native_id'] = self.adapter.feature_summary(created)['native_id']
            # Release precedes the coordinator's independent final observation.
            release_guard()
            return dict(document_id=document_id, configuration=configuration,
                        created_native_id=context['created_native_id'], kind=kind)

        def verify(before, after, value):
            good = after['guard_released'] is True and effect(before, after)
            if good:
                context['reference_binding_unconfirmed'] = True
                entry, _ = self.documents.resolve(document_id, configuration)
                receipt = context['receipt']
                created = receipt.sketch if kind == 'sketch' else receipt.extrusion
                owned_identity = receipt.sketch_identity if kind == 'sketch' else receipt.extrusion_identity
                if entry.identity != context['entry'].identity or self.adapter.identity(created) != owned_identity:
                    raise ExecutionFailure('rectangle_created_reference_changed', 'Only the exact retained feature may receive a result ID.', uncertain=True)
                cfg = self.adapter.configuration_identity(entry.model, configuration)
                reference = self.features._register(entry, configuration, cfg, created)
                current, _ = self.features._resolve(entry, configuration, cfg,
                    self.adapter.features(entry.model), reference.object_id)
                rows = after['state']['snapshots'][document_id]['clone_state']['features']
                matches = [i for i, row in enumerate(rows) if row['native_id'] == context['created_native_id']]
                if len(matches) != 1:
                    raise ExecutionFailure('rectangle_created_reference_changed', 'The created native ID has no exact observed role.', uncertain=True)
                role = 'feature:' + str(matches[0])
                anchors = after['state']['snapshots'][document_id]['references']
                tokens = [r['token'] for r in anchors if r['kind'] == 'feature' and r['role'] == role]
                if tokens != [reference.persistent_id.hex()] or self.adapter.identity(current) != owned_identity:
                    raise ExecutionFailure('rectangle_created_reference_changed', 'Returned ID must bind the independently observed exact persistent anchor.', uncertain=True)
                context['reference_binding_unconfirmed'] = False
                # Registration/getters cannot adopt a changed model or neighbor.
                closing = inspect(PreparedMutation('', before))
                good = closing['guard_released'] is True and effect(before, closing)
                if good:
                    after.update(closing)
                    value['object_id'] = reference.object_id
                    value['sketch_object_id' if kind == 'sketch' else 'feature_object_id'] = reference.object_id
            record('released_check', 'pending', dict(document_id=document_id))
            record('released_check', 'returned', dict(verified=good, observed=after))
            if good: context['verified_mode'] = 'effect'
            return good

        def restore(before, prepared):
            if pending():
                raise ExecutionFailure('rectangle_restore_unconfirmed', 'Pending native/storage effects prohibit an inverse.', uncertain=True)
            observed = inspect(prepared)
            if observed['state'] == before['baseline'] and observed['original_files'] == before['baseline']['semantic']['files']:
                if not context['release_attempted']: release_guard()
                return
            if not effect(before, observed):
                raise ExecutionFailure('rectangle_restore_unconfirmed', 'Only a complete independently proved own effect can be deleted.', uncertain=True)
            if context['guard_released']:
                enter_guard('restoration_guard')
                if not effect(before, inspect(prepared)):
                    raise ExecutionFailure('rectangle_restore_changed', 'The proved own effect changed before its inverse.', uncertain=True)
            method = self.adapter.restore_rectangle_sketch if kind == 'sketch' else self.adapter.restore_rectangle_extrusion
            method(context['entry'].model, context['receipt'])
            release_guard()

        def restored(before, after):
            # Restoration permits only documented native observation counters.
            # The dirty state and every baseline datum/anchor must return exactly.
            a, b = deepcopy(before['baseline']), deepcopy(after['state'])
            original_target = next(row for row in a['semantic']['documents'] if row['document_id'] == document_id)
            restored_target = next(row for row in b['semantic']['documents'] if row['document_id'] == document_id)
            if set(original_target) != set(restored_target): return False
            for row in (original_target, restored_target):
                if (type(row.get('update_stamp')) is not int
                        or type(row.get('observation_sequence')) is not int
                        or type(row.get('observation_revision')) is not str
                        or not row['observation_revision']): return False
            original_dimensions = a['snapshots'][document_id]['clone_state']['dimensions']
            restored_dimensions = b['snapshots'][document_id]['clone_state']['dimensions']
            if (len(original_dimensions) != len(restored_dimensions)
                    or any(set(x) != set(y) for x, y in zip(original_dimensions, restored_dimensions))): return False
            for state in (a, b):
                for row in state['semantic']['documents']:
                    if row['document_id'] == document_id:
                        for key in ('update_stamp', 'observation_sequence', 'observation_revision'): row.pop(key, None)
                for row in state['snapshots'][document_id]['clone_state']['dimensions']:
                    if 'owner_update_stamp' in row:
                        if type(row['owner_update_stamp']) is not int: return False
                        row.pop('owner_update_stamp')
            good = (not after['pending'] and after['guard_released'] is True and _json(a) == _json(b)
                    and after['original_files'] == before['baseline']['semantic']['files'])
            if good:
                record('restored_release_check', 'pending', dict(document_id=document_id))
                record('restored_release_check', 'returned', dict(verified=True, observed=after))
                context['verified_mode'] = 'restored'
            return good

        class Guard:
            def __enter__(self):
                enter_guard('execution_guard')
                return self
            def __exit__(self, *args):
                if not context['release_attempted'] and context['manager'] is not None:
                    return release_guard(*args, journal=False)
                return False
            @property
            def evidence(self):
                return dict(scope='rectangle_construction_guard_v1',
                    native_guards=[deepcopy(g.evidence) for g in context['guards']],
                    guard_released=context['guard_released'], pending_release=context['pending_release'],
                    journal_failed=context['journal_failed'],
                    reference_binding_unconfirmed=context['reference_binding_unconfirmed'],
                    full_release_check=context['verified_mode'])

        try:
            result = MutationCoordinator(self.store, self.connection_epoch).execute(operation_id,
                document_id=document_id, configuration=configuration, expected_revision=expected_revision,
                prepare=prepare, validate=validate, apply=apply, inspect=inspect, verify=verify,
                restore=restore, verify_restored=restored, guard=lambda _: Guard())
        except ExecutionFailure as error:
            if not error.uncertain: self.receipts.pop(operation_id, None)
            raise
        self.receipts.pop(operation_id, None)
        return result

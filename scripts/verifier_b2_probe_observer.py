"""Concrete read-only phase producer for the owned B2 PID experiment.

No CLI, fixture adoption/creation, selection, suppression, rebuild or cleanup.
Root invokes this on its owning STA only after releasing its action guard.
Input ownership comes from retained creation bindings, never a roster delta.
The preferences callback must be the root's direct passive native preference
reader. This module does not import a native verifier or initialize COM.
"""
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from solidworks_mcp.jobs import _json


_spec = importlib.util.spec_from_file_location('_b2_probe_observer_receipts',
    Path(__file__).with_name('verifier_b2_suppression_probe.py'))
_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gate)


class CanonicalOrdinalPool:
    """Retain unhashable native IUnknown objects; ordinals use equality only.

    Pass adapter.identity(dispatch) or configuration_identity's already-native
    identity. There is no name, Python id/hash, GetID, or pointer-string path.
    Keep this same pool and every root-owned binding alive for all three phases.
    """
    def __init__(self):
        self._identities = []

    def ordinal(self, identity):
        if identity is None:
            raise ValueError('A retained canonical identity is required.')
        matches = [i for i, old in enumerate(self._identities) if old == identity]
        if len(matches) > 1:
            raise ValueError('Ambiguous canonical identity equivalence.')
        if matches:
            return matches[0] + 1
        self._identities.append(identity)
        return len(self._identities)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _detach(value):
    return json.loads(_json(value))


class OwnedSuppressionProbeObserver:
    """Observe one phase from exact retained native root-owned bindings.

    owned_fixtures maps exactly two current document IDs to (model, canonical
    IUnknown) pairs created by root. owner is the gate's complete owner record;
    its ordinals must already bind this identity_pool's retained doc/config/
    feature identities. sessions is NativeDocumentOpenCatalog using the same
    DocumentCatalog and adapter. This observer never acquires an action guard.
    Failures propagate; no partial receipt or fallback is returned.
    """
    def __init__(self, documents, sessions, *, owner, model, feature,
                 document_identity, feature_identity, configuration_identity,
                 owned_fixtures, identity_pool, read_preferences):
        self.documents, self.sessions = documents, sessions
        self.adapter = documents.adapter
        _require(sessions.documents is documents and sessions.adapter is self.adapter,
                 'One exact DocumentCatalog/adapter/session owner required.')
        self.owner = _detach(owner)
        self.model, self.feature = model, feature
        self.document_identity = document_identity
        self.feature_identity = feature_identity
        self.configuration_identity = configuration_identity
        self.fixtures = dict(owned_fixtures)
        self.pool, self.read_preferences = identity_pool, read_preferences
        _require(type(identity_pool) is CanonicalOrdinalPool and callable(read_preferences),
                 'Retained canonical pool and passive preferences reader required.')
        _require(set(self.fixtures) == set(owner['owned_document_ids'])
                 and len(self.fixtures) == 2 and owner['document_id'] in self.fixtures
                 and all(type(pair) is tuple and len(pair) == 2 for pair in self.fixtures.values()),
                 'Exactly two explicit retained owned fixture bindings required.')
        bound_model, bound_identity = self.fixtures[owner['document_id']]
        _require(self.adapter.identity(bound_model) == document_identity
                 and bound_identity == document_identity
                 and self.adapter.identity(model) == document_identity
                 and self.adapter.identity(feature) == feature_identity,
                 'Retained root-owned model/feature bindings differ.')
        for token, identity in ((owner['document_identity_token'], document_identity),
            (owner['configuration_identity_token'], configuration_identity),
            (owner['feature_identity_token'], feature_identity)):
            _require(type(token) is int and token == self.pool.ordinal(identity),
                     'Owner ordinals must bind the existing retained canonical pool.')
        self.pid = bytes.fromhex(owner['feature_pid_hex'])
        _require(bool(self.pid) and self.pid.hex() == owner['feature_pid_hex'],
                 'Exact original feature persistent bytes required.')

    def _command(self):
        raw = self.adapter._sw.CommandInProgress
        _require(type(raw) is bool and raw is False,
                 'Phase capture requires raw CommandInProgress=False outside the action guard.')
        return raw

    def _entry_bindings(self, entries, semantic):
        _require(len(entries) == 2 and {entry.document_id for entry in entries} == set(self.fixtures),
                 'No foreign or missing document may enter the owned probe.')
        for entry in entries:
            model, retained = self.fixtures[entry.document_id]
            _require(entry.identity == retained
                     and self.adapter.identity(entry.model) == retained
                     and self.adapter.identity(model) == retained,
                     'Current census replaced a retained canonical model.')
        entry, observed = self.documents.resolve(self.owner['document_id'], self.owner['configuration'])
        _require(entry.identity == self.document_identity
                 and self.adapter.identity(entry.model) == self.document_identity
                 and observed['active_configuration'] == self.owner['configuration']
                 and observed['configurations'] == [self.owner['configuration']]
                 and self.adapter.configuration_identity(self.model, self.owner['configuration'])
                     == self.configuration_identity,
                 'Explicit active document/configuration canonical binding changed.')
        _require(semantic['active_document_id'] == self.owner['document_id'],
                 'Probe target must remain the explicit active document.')

    def _census(self):
        features = list(self.adapter.features(self.model))
        _require(6 <= len(features) <= 64, 'A complete bounded native feature census required.')
        identities = [self.adapter.identity(feature) for feature in features]
        tokens = [self.pool.ordinal(identity) for identity in identities]
        _require(len(set(tokens)) == len(tokens), 'Duplicate native canonical feature membership.')
        rows = _detach([self.adapter.feature_summary(feature) for feature in features])
        _gate._features(rows)
        matches = [i for i, identity in enumerate(identities) if identity == self.feature_identity]
        _require(len(matches) == 1, 'Exact retained feature missing or ambiguous in native traversal.')
        position = matches[0]
        _require(rows[position]['native_id'] == self.owner['feature_native_id']
                 and rows[position]['feature_type'] in ('Extrusion', 'Boss')
                 and self.adapter.persistent_id(self.model, features[position]) == self.pid,
                 'GetID census hint must agree with the original exact PID member.')
        return features, identities, tokens, rows, position

    def observe_phase(self, phase):
        _require(phase in _gate.PHASES, 'Only before/suppressed/restored observations supported.')
        self._command()
        with ExitStack() as stack:
            watches = []
            for model, identity in self.fixtures.values():
                _require(self.adapter.identity(model) == identity, 'Owned model identity replaced.')
                watch = self.adapter.watch_part(model)
                stack.callback(watch.close)
                watches.append((watch, watch.poll()))
            opening_entries, opening = self.sessions._capture_session()
            self._entry_bindings(opening_entries, opening)
            preferences = _detach(self.read_preferences(self.adapter._sw))
            _require(type(preferences) is dict and bool(preferences), 'Complete actual native preferences required.')
            features, identities, tokens, rows, position = self._census()
            raw, state = self.adapter._extension(self.model).GetObjectByPersistReference3(
                self.adapter._persistent_variant(self.pid))
            _require(type(state) is int and state == 0 and raw is not None,
                     'Ordinary native feature PID resolver must return state zero and a native object.')
            _require(self.adapter.identity(raw) == self.feature_identity,
                     'Raw PID resolution returned another canonical object.')
            resolved = self.adapter.resolve_persistent_id(self.model, self.pid, 'feature')
            _require(resolved is not None, 'Normal native resolver returned no feature.')
            resolved_identity = self.adapter.identity(resolved)
            resolved_token = self.pool.ordinal(resolved_identity)
            roundtrip = self.adapter.persistent_id(self.model, resolved)
            native_id = resolved.GetID()
            _require(resolved_identity == self.feature_identity
                     and self.adapter.identity(self.feature) == self.feature_identity
                     and roundtrip == self.pid and type(native_id) is int
                     and native_id == self.owner['feature_native_id'],
                     'Normal adapter resolver must bind the same native feature/PID/incarnation.')
            suppressed = resolved.IsSuppressed2(1, None)
            _require(type(suppressed) in (list, tuple) and len(suppressed) == 1
                     and type(suppressed[0]) is bool and suppressed[0] == rows[position]['suppressed'],
                     'Actual IsSuppressed2 singleton and traversal census disagree.')
            _require(suppressed[0] is (phase == 'suppressed'),
                     'Observed suppression state does not match the requested phase.')
            snapshot = None
            if phase == 'suppressed':
                geometry = _detach(self.adapter.dimension_geometry_snapshot(self.model))
                _require(geometry == {'representation': 'planar_polyhedral_brep_v1', 'bodies': []},
                         'Suppressed own base must have an actually empty body census.')
            else:
                snapshot = _gate._snapshot(self.adapter.rectangle_construction_snapshot(self.model),
                                            self.owner['configuration'])
                _require(snapshot['clone_state']['features'] == rows,
                         'Full native oracle and exact census disagree.')
                geometry = deepcopy(snapshot['clone_state']['geometry'])
            neighbors = {}
            for entry in opening_entries:
                if entry.document_id == self.owner['document_id']:
                    continue
                row = next(row for row in opening['documents'] if row['document_id'] == entry.document_id)
                neighbors[entry.document_id] = _gate._snapshot(
                    self.adapter.rectangle_construction_snapshot(entry.model), row['active_configuration'])
            _, final_identities, final_tokens, final_rows, final_position = self._census()
            _require(identities == final_identities and tokens == final_tokens
                     and _json(rows) == _json(final_rows) and position == final_position,
                     'Complete feature census changed while reading the phase.')
            final_entries, final = self.sessions._capture_session()
            self._entry_bindings(final_entries, final)
            _require(_json(opening) == _json(final)
                     and [entry.identity for entry in opening_entries] == [entry.identity for entry in final_entries]
                     and _json(preferences) == _json(self.read_preferences(self.adapter._sw))
                     and all(watch.poll() == sequence for watch, sequence in watches),
                     'Native session/preferences/events changed during the complete phase capture.')
            command = self._command()
            session = dict(semantic=deepcopy(final), neighbor_snapshots=neighbors,
                           application_preferences=preferences)
            session['semantic']['application']['command_in_progress'] = command
            _gate._session(session, self.owner['document_id'], self.owner['configuration'],
                           self.owner['owned_document_ids'])
            observation = dict(phase=phase, **{key: self.owner[key] for key in (
                'document_id', 'configuration', 'document_identity_token', 'configuration_identity_token')},
                feature_summaries=rows, feature_identity_tokens=tokens,
                resolver=dict(input_pid_hex=self.pid.hex(), state=state, object_returned=True,
                    roundtrip_pid_hex=roundtrip.hex(),
                    canonical_identity_token=resolved_token,
                    native_id=native_id, membership_index=position),
                is_suppressed2=list(suppressed), geometry=geometry, session=session)
            if snapshot is not None:
                observation['full_snapshot'] = snapshot
            return {'observation': _detach(observation), 'receipt_produced': True,
                    'accepted': False, 'native_b2_accepted': False, 'can_dispatch_native': False,
                    'cad_cleanup_authorized': False, 'process_stop_authorized': False}

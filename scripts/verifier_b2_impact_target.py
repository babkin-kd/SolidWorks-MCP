"""Passive retained target collector for the three finite N5 fixtures.

Construct before fixture preparation on its original owning STA. The owner still
must bracket two captures with the complete session/neighbor/file census. This
module neither dispatches deletion nor authorizes cleanup or acceptance.
"""
import json
import math
import threading

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_snapshot import BASE, validated_rectangle_snapshot
from verifier_b2_impact_fixture import require
from verifier_b2_body_binding import bind_current_body


SCOPE = 'b2_impact_current_target_v1'


class B2ImpactTarget:
    def __init__(self, fixture, parent_snapshot, *, ancillary=None, extrusion=None, topology=None, body_bridge=None):
        self.fixture = fixture
        self.binding = fixture.binding
        self.adapter = fixture.adapter
        self._thread = threading.get_ident()
        self.ancillary = ancillary
        self.extrusion = extrusion
        self.topology = topology
        self.body_bridge = body_bridge
        require(fixture.used is False, 'Retain the original census before fixture preparation.')
        self.parent = validated_rectangle_snapshot(parent_snapshot)
        require(self.parent['clone_state']['profile'] == BASE, 'Original complete BASE required.')
        self._owner()
        a, b = self.adapter, self.binding
        self.features = tuple(a.features(b.model))
        self.feature_identities = tuple(a.identity(f) for f in self.features)
        self.rows = [a.feature_summary(f) for f in self.features]
        require(_json(self.rows) == _json(self.parent['clone_state']['features']),
                'Actual original complete feature census differs from the parent.')
        self.dimensions = tuple(a.dimensions(b.model, self.features))
        require(len(self.dimensions) == 3, 'Three original native driving dimensions required.')
        self.dimension_identities = tuple(a.identity(a.dimension_object(d)) for d in self.dimensions)
        self.anchors = tuple(a.dimension_persistent_id(b.model, d) for d in self.dimensions)
        roles = {row['full_name']: row['role'].removeprefix('dimension:')
                 for row in self.parent['native_observations']['qualified_dimensions']}
        require(set(roles.values()) == {'width', 'height', 'depth'}, 'Exact original dimension roles required.')
        self.roles = roles
        self.plane_dimension = None
        for record, anchor in zip(self.dimensions, self.anchors):
            summary = a.dimension_summary(record, [b.configuration])
            matches = [row for row in self.parent['references'] if row['kind'] == 'dimension'
                       and row['role'] == 'dimension:' + roles.get(summary['full_name'], '')]
            require(type(anchor) is dict and len(matches) == 1 and _json(anchor) == matches[0]['token'],
                    'Current dimension must retain its actual original primary anchor.')
            self._dimension(record, anchor)
        bodies = a.bodies(b.model, 'all')
        require(type(bodies) in (list, tuple) and len(bodies) == 1, 'Exact original solid census required.')
        self.body = bodies[0]
        self.body_identity = a.identity(self.body)
        self.body_pid = a.persistent_id(b.model, self.body)
        matches = [row for row in self.parent['references'] if row['kind'] == 'body' and row['role'] == 'body:0']
        require(type(self.body_pid) is bytes and bool(self.body_pid) and len(matches) == 1
                and self.body_pid.hex() == matches[0]['token'], 'Original current body PID required.')

    def _owner(self):
        require(threading.get_ident() == self._thread, 'Retained collector belongs to the original STA.')
        self.fixture._owner()
        a, b = self.adapter, self.binding
        observed = a.snapshot(b.model)
        require(observed['document_type'] == 'part' and observed['path'] == ''
                and observed['configurations'] == [b.configuration]
                and observed['active_configuration'] == b.configuration
                and a.configuration_identity(b.model, b.configuration) == b.configuration_identity,
                'Only the original unsaved single active configuration is supported.')
        return observed

    def _dimension(self, record, anchor):
        a, b = self.adapter, self.binding
        require(a.dimension_reference_is_current(b.model, record, anchor) is True
                and a.identity(a.resolve_dimension_id(b.model, anchor)) == a.identity(a.dimension_object(record)),
                'Original dimension/owner/PID membership changed.')

    def _current_body(self):
        f,a,b=self.fixture,self.adapter,self.binding
        if self.body_bridge is None:
            bodies=a.bodies(b.model,'all')
            require(type(bodies) in (tuple,list) and len(bodies)==1
                and a.identity(bodies[0])==self.body_identity
                and f._pid(bodies[0],'body')==self.body_pid,'Original single body incarnation changed.')
            return bodies[0]
        return bind_current_body(original_body=self.body,original_canonical=self.body_identity,
            original_pid=self.body_pid,owner_feature=f._owner(),owner_canonical=b.feature_identity,
            identity=a.identity,persistent_id=lambda body:f._pid(body,'body'),
            resolve_body=lambda pid:a.resolve_persistent_id(b.model,pid,'body'),
            census=lambda:a.bodies(b.model,'all'),bridge=self.body_bridge)

    def capture(self):
        f, a, b = self.fixture, self.adapter, self.binding
        require(f.used is True and f.case in ('child_plane', 'unused_equation', 'linked_equation')
                and f.pending_native_step is None and f.journal_failed is False,
                'Normally acknowledged finite fixture required; pending forbids capture.')
        opening = self._owner()
        watch = a.watch_part(b.model)
        try:
            sequence = watch.poll()
            features = tuple(a.features(b.model))
            identities = tuple(a.identity(obj) for obj in features)
            expected = self.feature_identities + ((f.created_plane_identity,) if f.case == 'child_plane' else ())
            require(len(identities) == len(expected) and all(sum(token == old for token in identities) == 1 for old in expected),
                    'Only every original member and the exact acknowledged child plane are allowed.')
            rows = [a.feature_summary(obj) for obj in features]
            require(all(row['suppressed'] is False and row['error_code'] == 0 for row in rows),
                    'Current fixture feature states must remain clean and unsuppressed.')
            references = []
            from solidworks_mcp.cad_native_first_save_snapshot import FOLDERS, DISPLAY_FEATURES
            for feature in features:
                row = a.feature_summary(feature)
                if row['feature_type'] not in FOLDERS | DISPLAY_FEATURES:
                    pid = f._pid(feature, 'feature')
                    references.append(dict(kind='feature', role='native_feature:' + pid.hex(), token=pid.hex()))
            current_body=self._current_body()
            current_body_identity=a.identity(current_body)
            geometry = a.dimension_geometry_snapshot(b.model)
            require(_json(geometry) == _json(self.parent['clone_state']['geometry']),
                    'Fixture or refused preview changed original complete BREP.')
            references.append(dict(kind='body', role='body:0', token=self.body_pid.hex()))
            topology = self.topology
            if topology is None:
                from solidworks_mcp.cad_native_first_save_snapshot import _topology
                topology = _topology
            topology(a, b.model, current_body, geometry['bodies'][0], references)
            boundary = geometry['bodies'][0]
            require(len([row for row in references if row['kind'] == 'face']) == len(boundary['faces'])
                    and len([row for row in references if row['kind'] == 'edge']) == len(boundary['edges']),
                    'Every current geometric face/edge requires its actual PID binding.')
            records = tuple(a.dimensions(b.model, features))
            require(len(records) in ((3, 4) if f.case == 'child_plane' else (3,))
                    and all(sum(a.identity(a.dimension_object(d)) == old for d in records) == 1
                    for old in self.dimension_identities),
                    'Only three original dimensions and at most one exact own plane dimension are supported.')
            current_roles = dict(self.roles)
            summaries = []
            for record in records:
                identity = a.identity(a.dimension_object(record))
                indexes = [i for i, token in enumerate(self.dimension_identities) if identity == token]
                if indexes:
                    anchor = self.anchors[indexes[0]]
                else:
                    require(f.case == 'child_plane' and record.owner is not None
                            and a.identity(record.owner) == record.owner_tree_identity == f.created_plane_identity
                            and f._pid(record.owner, 'feature') == f.created_plane_pid,
                            'Extra dimension must belong to the exact normally acknowledged plane.')
                    anchor = a.dimension_persistent_id(b.model, record)
                    require(type(anchor) is dict and bool(anchor), 'Own plane dimension needs a real primary anchor.')
                    if self.plane_dimension is None:
                        self.plane_dimension = (record, identity, json.loads(_json(anchor)))
                    require(identity == self.plane_dimension[1] and _json(anchor) == _json(self.plane_dimension[2]),
                            'Retained own plane dimension incarnation or anchor was replaced.')
                require(_json(a.dimension_persistent_id(b.model, record)) == _json(anchor), 'Current primary anchor changed.')
                self._dimension(record, anchor)
                summary = a.dimension_summary(record, [b.configuration])
                if not indexes:
                    name = summary['full_name']
                    require(type(name) is str and bool(name) and name not in current_roles,
                            'Own plane dimension requires a unique current presentation name.')
                    current_roles[name] = 'plane_offset'
                summaries.append(summary)
                references.append(dict(kind='dimension', role='dimension:' + current_roles[summary['full_name']],
                                       token=_json(anchor)))
            require(self.plane_dimension is None or len(records) == 4,
                    'Retained own plane dimension disappeared from the complete current census.')
            context = f._context()
            sketch, _ = a.sketch_snapshot(b.model, b.receipt.borrowed_sketch)
            planes = [dict(native_id=row['native_id'], transform=list(a.reference_plane_transform(obj)))
                      for obj, row in zip(features, rows) if row['feature_type'] == 'RefPlane']
            require(len(planes) == (4 if f.case == 'child_plane' else 3), 'Complete current plane census required.')
            require(all(len(row['transform']) == 16 and all(type(value) in (int, float) and math.isfinite(value)
                        for value in row['transform']) for row in planes), 'Complete finite native plane transforms required.')
            if self.extrusion is None:
                from solidworks_mcp.cad_native_first_save_snapshot import _extrusion
                extrusion = _extrusion(a, b.feature)
            else:
                extrusion = self.extrusion(a, b.feature)
            collector = self.ancillary
            if collector is None:
                from verifier_b2_impact_ancillary import collect_impact_ancillary
                collector = collect_impact_ancillary
            ancillary = collector(a, b.model, configuration=b.configuration, features=features,
                                  summaries=rows, dimensions=records, dimension_roles=current_roles,
                                  references=references, body=current_body)
            controls = a.dimension_context(b.model)
            require(all(type(value) is dict and bool(value) for value in (sketch, extrusion, ancillary, controls)),
                    'Every current target inventory must be available; no replacement values.')
            for record, anchor in zip(self.dimensions, self.anchors):
                self._dimension(record, anchor)
            if self.plane_dimension is not None:
                self._dimension(self.plane_dimension[0], self.plane_dimension[2])
            closing_body=self._current_body()
            require(a.identity(closing_body)==current_body_identity,
                    'Body incarnation changed during ancillary collection.')
            closing_features = tuple(a.features(b.model))
            require(tuple(a.identity(obj) for obj in closing_features) == identities
                    and _json([a.feature_summary(obj) for obj in closing_features]) == _json(rows)
                    and _json(self._owner()) == _json(opening) and watch.poll() == sequence,
                    'Native metadata/incarnations/events changed during current target capture.')
            result = dict(scope=SCOPE, document_id=b.document_id, configuration=b.configuration,
                          metadata=opening, features=rows, dimensions=summaries, geometry=geometry,
                          deletion_context=context, controls=controls,
                          sketch=sketch, planes=planes, extrusion=extrusion, ancillary=ancillary,
                          accepted=False, native_b2_accepted=False, cleanup_authorized=False,
                          full_refusal_context_available=False,
                          open_gates=['complete_session_neighbor_file_capture', 'before_after_refusal_equality',
                                      'own_fixture_cleanup_and_original_baseline'])
            return json.loads(_json(result))
        finally:
            watch.close()

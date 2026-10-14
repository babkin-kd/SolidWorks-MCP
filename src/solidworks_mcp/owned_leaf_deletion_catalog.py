"""Full preparation and durable execution of exact own leaf extrusion deletion."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib

from .documents import rejected
from .feature_suppression_catalog import FeatureSuppressionCatalog
from .jobs import _json
from .owned_leaf_deletion_postconditions import MAX_LEAF_DOCUMENTS, validated_leaf_target
from .rectangle_construction import BlindRectangleExtrusion
from .rectangle_extrusion_postconditions import verified_rectangle_extrusion
from .rectangle_inventory import feature_relations, empty_feature_external_inventory
from .feature_deletion_context import context_semantics
from .retained_feature_resolution import resolve_retained_feature_pid
from .rectangle_snapshot import BASE, SKETCH, validated_rectangle_snapshot
from .owned_leaf_deletion_execution import OwnLeafDeletionExecutionMixin


SCOPE = 'owned_rectangular_leaf_extrusion_deletion_v1'


class OwnLeafDeletionCatalog(OwnLeafDeletionExecutionMixin):
    """Reuse the original current-epoch construction registry, never recreate it.

Preparation holds no native mutation authority. The original creation receipt
and its annotation/sketch/view evidence are not changed. Execution uses a
separate one-shot receipt and independently persists/verifies its outcome.
"""
    def __init__(self, documents, store, connection_epoch, ownership):
        self.observations = FeatureSuppressionCatalog(documents,store,connection_epoch,ownership)
        self.documents,self.adapter,self.store = documents,documents.adapter,store
        self.connection_epoch,self.ownership = connection_epoch,ownership
        self.receipts={}

    def _capture_current(self,binding,guarded_ids=()):
        """Capture after deletion without touching the deleted native feature."""
        entries,semantic=self.observations.sessions._capture_session(guarded_ids)
        self._require(0<len(entries)<=MAX_LEAF_DOCUMENTS,'Complete bounded current native roster required.')
        snapshots={}
        for entry in entries:
            row=next(row for row in semantic['documents'] if row['document_id']==entry.document_id)
            self._require(row['document_type']=='part','Full current part oracles required.')
            if entry.document_id==binding.document_id:
                self._require(entry.identity==binding.model_identity,'Original target model incarnation required.')
            first=validated_rectangle_snapshot(self.adapter.rectangle_construction_snapshot(entry.model))
            second=validated_rectangle_snapshot(self.adapter.rectangle_construction_snapshot(entry.model))
            self._require(_json(first)==_json(second) and second['configuration']==row['active_configuration']
                and second['configurations']==row['configurations'],'Current full native snapshot changed.')
            self._require(second['clone_state']['profile'] in ((BASE,SKETCH) if entry.document_id==binding.document_id else (BASE,)),
                'Only target BASE/SKETCH and complete BASE neighbors are supported.')
            snapshots[entry.document_id]=second
        closing_entries,closing=self.observations.sessions._capture_session(guarded_ids)
        self._require(_json(semantic)==_json(closing)
            and [entry.identity for entry in entries]==[entry.identity for entry in closing_entries]
            and binding.document_id in snapshots,'Full session or original model changed during capture.')
        return closing_entries,dict(semantic=semantic,snapshots=snapshots)

    @staticmethod
    def _require(condition, field):
        if not condition: raise rejected('leaf_deletion_unsupported',field)

    def _owned(self, document_id, configuration, object_id):
        binding,feature = self.ownership.resolve(document_id,configuration,object_id,
            connection_epoch=self.connection_epoch)
        self._require(binding.kind=='extrusion','Only the original standalone owned extrusion is supported.')
        suppressed = list(feature.IsSuppressed2(1,None))
        self._require(len(suppressed)==1 and suppressed[0] is False,'Current unsuppressed native BASE required.')
        children = feature.GetChildren()
        # Same normally-returned empty-array contract as restore_rectangle_extrusion.
        # Full independently captured BASE links below must agree; None alone
        # never proves this is a leaf or supplies a count we did not measure.
        self._require(children is None or type(children) in (list,tuple),'Complete native GetChildren return required.')
        self._require(not children,'Native dependent children forbid leaf deletion.')
        return binding,feature

    def _state(self, binding, entries, state):
        self._require(any(entry.document_id==binding.document_id
            and entry.identity==binding.model_identity for entry in entries),'Current target canonical entry required.')
        try:
            checked = validated_leaf_target(state,document_id=binding.document_id,
                configuration=binding.configuration,object_id=binding.object_id,
                feature_native_id=binding.native_id,feature_pid_hex=binding.persistent_id.hex())
            snapshot = checked['snapshots'][binding.document_id]
            data = snapshot['clone_state']
            links = feature_relations(data)
            empty_feature_external_inventory(data)
            self._require(not links['parent_links_without_child_confirmation']
                and not links['child_links_without_parent_confirmation'],'All current dependency links must be confirmed.')
            self._require(not any(parent==binding.native_id for parent,child in links['child_links']),
                          'Full native dependency census forbids downstream children.')
            inventories = context_semantics(data['equation_reference_inventory'])
            eq= inventories['equations']
            self._require(eq['enumerated_count']==0 and eq['disabled_count']==0
                and eq['disabled_definitions_captured'] is True
                and eq['properties']['linked_to_file'] is False and eq['properties']['file_path']==''
                and inventories['external_references']['count']==0
                and inventories['auxiliary_references']['count']==0,
                'Equations/external/auxiliary references require another profile.')
            self._require(data['auxiliary_data']==dict(attachments=0,comments=0,named_selection_sets=0),
                          'Attachments/comments/selection sets require another profile.')
            args = binding.creation_result['before']['definition']
            feature_row = next(row for row in data['features'] if row['native_id']==binding.native_id)
            definition = BlindRectangleExtrusion.validate(sketch_object_id=args['sketch_object_id'],
                depth_mm=data['parameters']['depth_m']*1000.,feature_name=feature_row['name'],body_name=data['body']['name'])
            sketch = binding.receipt.borrowed_sketch
            identity = binding.receipt.borrowed_sketch_identity
            self._require(sketch is not None and identity is not None and self.adapter.identity(sketch)==identity,
                          'Original retained borrowed sketch canonical binding required.')
            native_features = self.adapter.features(binding.model)
            self._require(sum(self.adapter.identity(feature)==identity for feature in native_features)==1,
                          'Original sketch must remain in the complete current native feature census.')
            sketch_id = data['sketch']['feature_native_id']
            native_sketch = next(feature for feature in native_features if self.adapter.identity(feature)==identity)
            self._require(self.adapter.feature_summary(native_sketch)['native_id']==sketch_id,
                          'Observed sketch role must be the original canonical retained sketch.')
            original = binding.baseline_target_snapshot
            original_rows = original['clone_state']['features']
            original_index = next(index for index,row in enumerate(original_rows) if row['native_id']==sketch_id)
            pid = bytes.fromhex(next(row['token'] for row in original['references']
                if row['kind']=='feature' and row['role']=='feature:'+str(original_index)))
            resolve_retained_feature_pid(self.adapter,binding.model,pid,identity)
            candidate = deepcopy(checked)
            candidate['snapshots'][binding.document_id] = original
            self._require(verified_rectangle_extrusion(candidate,checked,binding.document_id,definition,binding.native_id),
                'Current BASE must be the full finite extrusion delta of the unchanged original borrowed sketch/profile.')
        except (KeyError,StopIteration,ValueError,TypeError) as error:
            raise rejected('leaf_deletion_snapshot_unconfirmed','Unavailable/unsupported complete current leaf data: '+str(error)) from error
        return checked,definition

    def prepare(self, document_id, configuration, object_id):
        return self._prepare(document_id,configuration,object_id)

    def _prepare(self, document_id, configuration, object_id, guarded_ids=()):
        self._require(all(type(value) is str and value.strip() for value in (document_id,configuration,object_id)),
                      'Explicit current document/configuration/owned object required.')
        if not guarded_ids:self._require(not self.adapter.application_busy(),'An existing native command cannot be borrowed.')
        watches = []
        with ExitStack() as cleanup:
            models = self.adapter.documents()
            self._require(0 < len(models) <= MAX_LEAF_DOCUMENTS,'Complete bounded native document roster required.')
            for model in models:
                self._require(self.adapter.snapshot(model)['document_type']=='part','All current neighbors require the supported part oracle.')
                watch = self.adapter.watch_part(model)
                cleanup.callback(watch.close)
                watches.append((watch,watch.poll()))
            binding,feature = self._owned(document_id,configuration,object_id)
            entries,first = self.observations._capture(binding,None,guarded_ids)
            first,definition = self._state(binding,entries,first)
            closing_binding,closing_feature = self._owned(document_id,configuration,object_id)
            self._require(closing_binding is binding and self.adapter.identity(closing_feature)==binding.feature_identity,
                          'Original owned feature must survive the read-only preparation.')
            closing_entries,last = self.observations._capture(binding,None,guarded_ids)
            last,closing_definition = self._state(binding,closing_entries,last)
            self._require(_json(first)==_json(last) and definition==closing_definition
                and [entry.identity for entry in entries]==[entry.identity for entry in closing_entries],
                'Complete current session/feature changed during preparation.')
            self._require(all(watch.poll()==sequence for watch,sequence in watches),'Native model event raced preparation.')
            if not guarded_ids:self._require(not self.adapter.application_busy(),'A native command started during read-only preparation.')
            payload = dict(scope=SCOPE,connection_epoch=self.connection_epoch,document_id=document_id,
                configuration=configuration,object_id=object_id,creation_operation_id=binding.creation_operation_id,
                feature_native_id=binding.native_id,feature_pid_hex=binding.persistent_id.hex(),
                current_definition=vars(definition),baseline=first,
                expected_after_profile='closed_rectangular_sketch_v1',expected_solid_body_count=0,
                application_command_in_progress=False,
                preview=dict(deleted_feature_object_ids=[object_id],
                    preserved_sketch_object_id=definition.sketch_object_id,
                    remaining_dimension_roles=['dimension:width','dimension:height'],
                    expected_solid_body_count=0,geometry_references_require_refresh=True))
            return dict(**payload,revision='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest(),
                revision_scope=SCOPE,delete_authorized=False,native_execution_available=True)

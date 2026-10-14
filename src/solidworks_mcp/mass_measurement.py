"""Public passive mass calculation with a durable guard for temporary UI state.

The revision covers the measurement target and UI roster, not arbitrary model
editing. Restoration never re-runs a calculation or a native Resume operation.
"""
from dataclasses import dataclass
import hashlib

from .documents import rejected
from .geometry import GeometryCatalog
from .jobs import _json, ExecutionFailure
from .mutations import MutationCoordinator, PreparedMutation

SCOPE='part_mass_selection_measurement_v1'


@dataclass(frozen=True)
class MassPrepared(PreparedMutation):
    native:tuple=()


class MassMeasurementCatalog:
    def __init__(self,documents,store,connection_epoch):
        self.geometry=GeometryCatalog(documents);self.documents=documents
        self.adapter=documents.adapter;self.coordinator=MutationCoordinator(store,connection_epoch)

    def _capture(self,document_id,configuration,expected_observation_revision,body_id=None):
        entry,observed,identity=self.geometry._context(document_id,configuration,expected_observation_revision)
        all_bodies=tuple(self.adapter.bodies(entry.model,'solid'))
        if not all_bodies:raise rejected('no_solid_bodies','No solid bodies in the explicit active configuration.')
        if len(all_bodies)>500:raise rejected('mass_scope_budget_exceeded','Mass scope supports at most 500 solid bodies.')
        selected=None
        if body_id is not None:
            selected,reference=self.geometry._resolve(entry,body_id,configuration,identity,'body')
            if self.adapter.geometry_summary(selected,reference.kind)['body_type']!='solid':
                raise rejected('unsupported_body_type','Mass requires solid bodies.')
        rows=[];strong=[]
        for body in all_bodies:
            ref=self.geometry._register(entry,body,'body',configuration,identity)
            pid=ref.persistent_id
            if self.adapter.identity(self.adapter.resolve_persistent_id(entry.model,pid,'body'))!=self.adapter.identity(body):
                raise rejected('mass_body_reference_changed','Solid body reference changed.')
            rows.append(dict(persistent_id=pid.hex(),geometric_moments=self.adapter.mass_body_signature(body)))
            strong.append((pid,self.adapter.identity(body)))
        order=sorted(range(len(rows)),key=lambda i:rows[i]['persistent_id'])
        rows=[rows[i] for i in order];strong=tuple(strong[i] for i in order)
        if selected is not None and not any(self.adapter.identity(selected)==token for _,token in strong):
            raise rejected('object_not_in_active_configuration','Selected solid is not a member of the current body scope.')
        selection,selection_tokens=self.adapter.mass_selection_capture(entry.model)
        self.geometry._confirm(entry,observed,configuration,identity)
        if getattr(self.adapter,'_mass_selection_reconciliation_required',False):
            raise ExecutionFailure('mass_selection_reconciliation_required','Reconcile previous selection uncertainty first.',uncertain=True)
        before=dict(document_id=document_id,configuration=configuration,observation_revision=expected_observation_revision,
            body_id=body_id,solid_bodies=rows,selection=selection,revision_scope=SCOPE)
        revision='rev_'+hashlib.sha256(_json(before).encode('utf8')).hexdigest()
        return MassPrepared(revision,before,'application',(entry,identity,strong,selection_tokens))

    @staticmethod
    def _same(left,right):
        return left.revision==right.revision and left.native==right.native

    def prepare(self,document_id,configuration,expected_observation_revision,body_id=None):
        prepared=self._capture(document_id,configuration,expected_observation_revision,body_id)
        return dict(document_id=document_id,configuration=configuration,body_id=body_id,
            revision=prepared.revision,revision_scope=SCOPE,body_count=1 if body_id else len(prepared.before['solid_bodies']),
            coordinate_frame='model',includes_hidden_bodies=True,model_geometry_modified=False,
            ui_effect='temporary_selection_with_durable_application_guard')

    def measure(self,operation_id,document_id,configuration,expected_observation_revision,expected_revision,body_id=None):
        args=dict(document_id=document_id,configuration=configuration,
            expected_observation_revision=expected_observation_revision,body_id=body_id)
        def capture():return self._capture(**args)
        def inspect(prepared):
            current=capture()
            if current.native!=prepared.native:
                raise rejected('mass_native_members_changed','Strong document/body/selection members changed.')
            return current.before
        def unchanged(before,after):
            return {k:v for k,v in before.items() if k!='_mutation_effect_scope'}==after
        def restore(before,prepared):
            # Native calculation owns cleanup. Only prove its already-restored
            # UI state; never retry ResumeSelectionList after an uncertain call.
            if getattr(self.adapter,'_mass_selection_reconciliation_required',False):
                raise ExecutionFailure('mass_selection_restore_unconfirmed','Selection ownership is unconfirmed.',uncertain=True)
            if not unchanged(before,inspect(prepared)):
                raise ExecutionFailure('mass_read_restore_unconfirmed','Read-only baseline changed.',uncertain=True)
        result=self.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=capture,
            validate=lambda prepared:self._same(prepared,capture()),
            apply=lambda prepared:self.geometry.measure_mass(**args),inspect=inspect,
            verify=lambda before,after,value:unchanged(before,after) and value['body_count']>0,
            restore=restore,verify_restored=unchanged,
            guard=lambda prepared:self.adapter.mass_read_guard(prepared.native[0].model))
        return {**result['value'],'verified':True,'revision_scope':SCOPE,
            'measurement_revision':expected_revision,'model_geometry_modified':False,
            'execution_guard':result['execution_guard']}

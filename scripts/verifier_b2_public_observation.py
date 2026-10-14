"""Independent B2 public observations; called only by the live native owner.

Original journal jobs remain immutable. Separate comparison operands may use
independently observed view namespaces after a complete B1 comparison, never
as persisted jobs, ownership receipts or mutation authorization.
"""
from copy import deepcopy
import re

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_snapshot import BASE, SKETCH, validated_rectangle_snapshot
from verifier_rectangle_stages import verified_rectangle_job


def feature_role(job):
    """Get the exact created structural PID role from the original B1 job."""
    if not verified_rectangle_job(job):
        raise ValueError('A complete original committed B1 creation job is required.')
    value=job['result']['value']
    kind=value['kind']
    operation={'sketch':'sketch.create_rectangle','extrusion':'part.extrude_rectangle'}
    if kind not in operation or job['operation']!=operation[kind]:
        raise ValueError('Exact B1 sketch/extrusion creation lineage required.')
    object_id=value['sketch_object_id' if kind=='sketch' else 'feature_object_id']
    if (object_id!=value['object_id'] or re.fullmatch(r'feat_[0-9a-f]{32}',object_id) is None
            or type(value['created_native_id']) is not int):
        raise ValueError('Exact original created feature ID is required.')
    snapshot=validated_rectangle_snapshot(job['result']['after']['state']['snapshots'][value['document_id']])
    matches=[(index,row) for index,row in enumerate(snapshot['clone_state']['features'])
             if row['native_id']==value['created_native_id']]
    if len(matches)!=1:raise ValueError('One current created structural role is required.')
    role='feature:'+str(matches[0][0])
    anchors=[row['token'] for row in snapshot['references'] if row['kind']=='feature' and row['role']==role]
    if len(anchors)!=1 or not bytes.fromhex(anchors[0]) or bytes.fromhex(anchors[0]).hex()!=anchors[0]:
        raise ValueError('One canonical original persistent anchor is required.')
    return dict(document_id=value['document_id'],configuration=value['configuration'],object_id=object_id,
        kind=kind,creation_operation_id=job['operation_id'],native_id=value['created_native_id'],
        feature_role=role,persistent_id_hex=anchors[0])


def independent_creation_operand(extrusion_job,independent_sketch,independent_base):
    """A detached scalar oracle operand, explicitly not a durable job DTO."""
    from verify_rectangle_stages_public import compare_stage_snapshot
    feature_role(extrusion_job)
    if extrusion_job['operation']!='part.extrude_rectangle':
        raise ValueError('Original extrusion is required.')
    target=extrusion_job['result']['value']['document_id']
    original=extrusion_job['result']
    compare_stage_snapshot(independent_sketch,original['before']['baseline']['snapshots'][target])
    compare_stage_snapshot(independent_base,original['after']['state']['snapshots'][target],
                           previous=independent_sketch)
    before=deepcopy(original['before']['baseline'])
    after=deepcopy(original['after']['state'])
    before['snapshots'][target]=deepcopy(independent_sketch)
    after['snapshots'][target]=deepcopy(independent_base)
    return dict(scope='b2_independent_creation_comparison_operand_v1',
        accepted=False,native_acceptance=False,cleanup_authorized=False,mutation_authorized=False,
        operation=extrusion_job['operation'],status=extrusion_job['status'],error=deepcopy(extrusion_job['error']),
        mutation=dict(phase='committed'),result=dict(verified=True,value=deepcopy(original['value']),
            before=dict(scope=original['before']['scope'],baseline=before,definition=deepcopy(original['before']['definition'])),
            after=dict(state=after)))


async def after_base(**owner):
    """Use the existing B1 canonical owner and supervised client, no connection."""
    from solidworks_mcp.documents import DocumentCatalog
    from solidworks_mcp.native_document_open import NativeDocumentOpenCatalog
    from solidworks_mcp.native_first_save import validated_part_snapshot
    from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
    from solidworks_mcp.cad_owned_suppression_snapshot import PROFILE as SUPPRESSED
    from verifier_b2_native_observer import AttestationOnly
    from verifier_b2_session_mapping import HeldDocumentBridge, compare_mapped_session
    from verifier_b2_scalar_rename import verified_b2_depth_change,verified_b2_feature_rename
    from verifier_b2_public_route import run_b2_positive,compare_b2_observed_state
    from verify_dimension_mcp import require_native_cleanup

    client,gate=owner['client'],owner['gate']
    adapter,target,neighbor=owner['adapter'],owner['target'],owner['neighbor']
    report,persist=owner['report'],owner['persist']
    target_id=owner['context']['document_id']
    original=owner['extrusion_job']
    original_state=original['result']['after']['state']
    target_identity,neighbor_identity=owner['target_identity'],owner['neighbor_identity']
    # This scope is exactly the two original unsaved controls. A foreign/hidden
    # model or multiple window cannot be silently adopted by a later census.
    ids={row['document_id'] for row in original_state['semantic']['documents']}
    if len(ids)!=2 or target_id not in ids:
        raise ValueError('Only the original public two-control B2 session is supported.')
    neighbor_id=next(iter(ids-{target_id}))
    windows=[row for row in original_state['semantic']['windows'] if row['document_id']==neighbor_id]
    actual_windows=[info for model,info in adapter.native_close_windows()
                    if adapter.identity(model)==neighbor_identity]
    if (len(windows)!=1 or len(actual_windows)!=1
            or _json(actual_windows[0])!=_json({key:windows[0][key] for key in ('hwnd','title')})
            or adapter.identity(target)!=target_identity or adapter.identity(neighbor)!=neighbor_identity
            or validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))!=owner['neighbor_before']):
        raise ValueError('Original held canonical neighbor/current HWND must match its original complete B1 evidence.')
    bridges=(HeldDocumentBridge(target_id,target_identity,owner['bridge']['hwnd'],deepcopy(owner['bridge'])),
        HeldDocumentBridge(neighbor_id,neighbor_identity,windows[0]['hwnd'],
            dict(scope='original_owned_public_neighbor_v1',document_id=neighbor_id,
                 hwnd=windows[0]['hwnd'],original_snapshot=deepcopy(owner['neighbor_before']))))
    # Only _capture_session is used. This observer never dispatches mutations,
    # writes a journal, registers feature ownership or invokes open/close.
    sessions=NativeDocumentOpenCatalog(DocumentCatalog(adapter),None,'attestation-only-public-b2')
    ext_role,sketch_role=feature_role(original),feature_role(owner['sketch_job'])
    comparison=independent_creation_operand(original,owner['independent_sketch'],owner['independent_base'])
    definition=BlindRectangleExtrusion.validate(**original['result']['before']['definition'])
    resized=BlindRectangleExtrusion.validate(**{**vars(definition),'depth_mm':12.})
    renamed=BlindRectangleExtrusion.validate(**{**vars(resized),'feature_name':'Основание пластины'})
    retained=None
    previous=None

    def observe(stage,expected):
        nonlocal retained,previous
        if adapter._sw.CommandInProgress is not False:
            raise ValueError('Public native observation must begin quiescent.')
        report.update(phase='b2-independent-'+stage,native_calls_live=True);persist()
        adapter._sw.CommandInProgress=True
        if adapter._sw.CommandInProgress is not True:raise ValueError('Owned observation flag acquisition failed.')
        entries,semantic=sessions._capture_session()
        if (len(entries)!=2 or sum(entry.identity==target_identity for entry in entries)!=1
                or sum(entry.identity==neighbor_identity for entry in entries)!=1
                or target_identity==neighbor_identity):
            raise ValueError('Complete original canonical two-control census required.')
        if retained is None or stage=='renamed':
            current=validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(target))
            retained=AttestationOnly(adapter,target,current,bridge=owner['bridge'],
                model_identity=target_identity,extrusion_role=ext_role,sketch_role=sketch_role)
        profile=(SUPPRESSED if stage in ('suppress','suppress-replay','return-preview') else
                 SKETCH if stage in ('deleted','retired-id-refused') else BASE)
        target_observation=retained.capture(profile)
        first=validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(neighbor))
        second=validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(neighbor))
        closing_entries,closing=sessions._capture_session()
        if (_json(semantic)!=_json(closing) or first!=second
                or [entry.identity for entry in entries]!=[entry.identity for entry in closing_entries]
                or validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))!=owner['neighbor_before']):
            raise ValueError('Independent full session/neighbor changed during native observation.')
        raw=dict(semantic=semantic,snapshots={entry.document_id:
            target_observation['snapshot'] if entry.identity==target_identity else second for entry in entries})
        # Scalar/rename callbacks receive their actual independent session, not
        # scalar result DTOs posing as full native state. Mapping is verified
        # against the last complete server state only when one is available.
        reference=expected if type(expected) is dict and set(expected)=={'semantic','snapshots'} else None
        proof=compare_mapped_session(raw,reference,native_entries=entries,bridges=bridges,previous=previous)
        previous=proof
        mapped=proof['mapped_state']
        report.setdefault('b2_independent_observations',[]).append(dict(stage=stage,
            raw_state=raw,mapping=proof,target_observation=target_observation))
        adapter._sw.CommandInProgress=False
        if adapter._sw.CommandInProgress is not False:raise ValueError('Owned observation flag release failed.')
        report['native_calls_live']=False;persist()
        return mapped

    common=dict(document_id=target_id,configuration=owner['context']['configuration'],
        object_id=ext_role['object_id'],feature_native_id=ext_role['native_id'],feature_pid_hex=ext_role['persistent_id_hex'])
    def depth(before,after,*_):
        return verified_b2_depth_change(before,after,comparison,**common,
                                       old_definition=definition,new_definition=resized)
    def rename(before,after,*_):
        return verified_b2_feature_rename(before,after,comparison,**common,
                                         old_definition=resized,new_definition=renamed)
    await require_native_cleanup(client,gate)
    try:
        return await run_b2_positive(client=client,gate=gate,journal_path=owner['journal_path'],
            context=owner['context'],extrusion_job=original,observe=observe,
            verify_depth=depth,verify_rename=rename,report=report,persist=persist,
            compare_state=compare_b2_observed_state)
    except BaseException:
        client.retain('Independent public B2 scope/handles/mapping not completely proved.')
        raise

"""Bounded public B2 route primitives, with no connection or fixture lifecycle.

The native owner supplies the live supervised client and full independent
observer. No result here accepts B2 or authorizes native cleanup by itself.
"""
from copy import deepcopy

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_snapshot import SKETCH, validated_rectangle_snapshot
from verifier_b2_public_contract import verified_b2_job


def compare_b2_state(actual, expected):
    """Compare the entire observed session in an explicitly mapped namespace.

    The driver must map document IDs using its held canonical/HWND bridge.
    This helper never infers identity from names or fills missing observations.
    Session metadata is exact; only adapter-local annotation view namespaces
    receive the full row/axis comparison of the independent observer.
    """
    from verifier_b2_native_observer import compare_b2_snapshot
    keys={'semantic','snapshots'}
    if (type(actual) is not dict or type(expected) is not dict
            or set(actual)!=keys or set(expected)!=keys
            or type(actual['semantic']) is not dict
            or set(actual['semantic'])!={'documents','windows','files','application',
                                        'active_document_id','reference_graph'}
            or _json(actual['semantic'])!=_json(expected['semantic'])
            or type(actual['snapshots']) is not dict
            or type(expected['snapshots']) is not dict
            or not actual['snapshots']
            or set(actual['snapshots'])!=set(expected['snapshots'])):
        raise ValueError('Complete independently mapped B2 session/neighbor evidence differs.')
    for document_id in expected['snapshots']:
        compare_b2_snapshot(actual['snapshots'][document_id],expected['snapshots'][document_id])
    return True


def preserved_journal(before,after,operation_id):
    """A dispatch may add its own row; prior creation/results stay immutable."""
    def indexed(rows):
        if type(rows) is not list or any(type(row) is not dict
                or type(row.get('operation_id')) is not str or not row['operation_id'] for row in rows):
            raise ValueError('Complete coherent journal rows are required.')
        found={row['operation_id']:row for row in rows}
        if len(found)!=len(rows):raise ValueError('Duplicate durable operation ID.')
        return found
    first,last=indexed(before),indexed(after)
    if (operation_id not in last or not set(first)<=set(last)
            or set(last)-set(first) not in (set(),{operation_id})
            or any(_json(row)!=_json(last[key]) for key,row in first.items())):
        raise ValueError('Public dispatch/replay changed prior durable evidence or added unrelated jobs.')
    return True


async def run_b2_positive(*, client, gate, journal_path, context, extrusion_job,
        observe, verify_depth, verify_rename, report, persist):
    """Execute N1–N4 on the original live public B1 feature.

    ``observe(stage, expected_state)`` is an independent full native-scope
    callback owned by the driver. Scalar/name callbacks raise on any incomplete
    or foreign delta. They do not replace the remote domain/SQL verification.
    The caller retains its COM apartment, fixture ownership and supervisor.
    """
    from verify_rectangle_stages_public import public_invoke
    from verifier_b2_public_contract import durable_b2_job
    from verifier_lifecycle import read_journal
    from verifier_first_save_public_contract import fixture_depth_dimension

    target=context['document_id']
    feature=extrusion_job['result']['value']['feature_object_id']
    cfg=context['configuration']
    result=dict(scope='b2_public_positive_extension_v1',accepted=False,
        native_b2_accepted=False,positive_case_passed=False,jobs=[],cases=[])

    async def persisted_response(response,before):
        raw=await client.call_tool('job_get',{'operation_id':response['operation_id']})
        if raw.isError or raw.structuredContent['status']!='succeeded':
            raise ValueError('Full public B2 job DTO is unavailable.')
        dto=raw.structuredContent['data']
        current_rows=read_journal(journal_path)
        preserved_journal(before,current_rows,response['operation_id'])
        rows=[row for row in current_rows if row['operation_id']==response['operation_id']]
        if len(rows)!=1:raise ValueError('One coherent durable B2 row is required.')
        job=durable_b2_job(dto,rows[0])
        if job['status']!=response['status']:
            raise ValueError('Public response status differs from its durable job.')
        result['jobs'].append(job);report['b2_extension']=result;persist()
        return job

    async def invoke(tool,request,**arguments):
        before=read_journal(journal_path)
        response=await public_invoke(client,gate,report,persist,tool,request_id=request,**arguments)
        if response['status']!='succeeded':
            raise ValueError('Public B2 step did not succeed: '+tool)
        job=await persisted_response(response,before)
        return response['data'],job,response

    async def observed(stage,expected):
        from inspect import isawaitable
        from verify_dimension_mcp import require_native_cleanup
        await require_native_cleanup(client,gate)
        value=observe(stage,expected)
        if isawaitable(value):value=await value
        if (type(value) is not dict or set(value)!={'semantic','snapshots'}
                or target not in value['snapshots']):
            raise ValueError('A complete independently observed native B2 session is required.')
        return value

    try:
        initial=await observed('initial',extrusion_job['result']['after']['state'])
        compare_b2_state(initial,extrusion_job['result']['after']['state'])
        listed,_,_=await invoke('dimension_list','b2-depth-list',**context)
        depth=fixture_depth_dimension(listed,cfg,10.)
        current,_,_=await invoke('dimension_get','b2-depth-get',**context,object_id=depth['object_id'])
        size_args=dict(**context,object_id=depth['object_id'],value=12.,unit='mm',expected_revision=current['revision'])
        _,size_job,_=await invoke('dimension_set_value','b2-depth-set',**size_args)
        if size_job['mutation']['phase']!='committed' or size_job['result']['verified'] is not True:
            raise ValueError('Committed scalar mutation is required.')
        changed=await observed('depth12',size_job['result'])
        if verify_depth(initial,changed,extrusion_job,size_job) is not True:
            raise ValueError('Independent complete scalar delta was not proved.')
        _,replay,_=await invoke('dimension_set_value','b2-depth-set',**size_args)
        if _json(replay)!=_json(size_job):raise ValueError('Scalar replay changed its durable job.')
        result['cases'].append(dict(label='B2-public-depth12-full9600',passed=True));persist()

        current,_,_=await invoke('feature_get','b2-feature-before-rename',**context,object_id=feature)
        rename_args=dict(**context,object_id=feature,expected_revision=current['revision'],name='Основание пластины')
        _,rename_job,_=await invoke('feature_rename','b2-feature-rename',**rename_args)
        if rename_job['mutation']['phase']!='committed' or rename_job['result']['verified'] is not True:
            raise ValueError('Committed Russian rename is required.')
        renamed=await observed('renamed',rename_job['result'])
        if verify_rename(changed,renamed,extrusion_job,rename_job) is not True:
            raise ValueError('Independent complete rename delta was not proved.')
        _,replay,_=await invoke('feature_rename','b2-feature-rename',**rename_args)
        if _json(replay)!=_json(rename_job):raise ValueError('Rename replay changed its durable job.')
        result['cases'].append(dict(label='B2-public-Russian-name-same-reference',passed=True));persist()

        original_suppression=None
        previous_state=renamed
        for requested in (True,False):
            label='suppress' if requested else 'return'
            args=dict(**context,object_id=feature,suppressed=requested)
            prepared,preparation,_=await invoke('feature_prepare_suppression','b2-'+label+'-prepare',**args)
            if not verified_b2_job(preparation):
                raise ValueError('Exact read-only suppression preparation must be proved.')
            prepared_state=await observed(label+'-preview',prepared['baseline'])
            compare_b2_state(prepared_state,prepared['baseline'])
            compare_b2_state(prepared_state,previous_state)
            args['expected_revision']=prepared['revision']
            _,job,_=await invoke('feature_set_suppressed','b2-'+label,**args)
            if not verified_b2_job(job,preparation_job=preparation,
                    original_suppression_job=original_suppression):
                raise ValueError('Full committed suppression/return lineage was not proved.')
            state=await observed(label,job['result']['after']['state'])
            compare_b2_state(state,job['result']['after']['state'])
            _,replay,_=await invoke('feature_set_suppressed','b2-'+label,**args)
            if _json(replay)!=_json(job):raise ValueError('Suppression replay changed its durable job.')
            previous_state=await observed(label+'-replay',job['result']['after']['state'])
            compare_b2_state(previous_state,state)
            if requested:original_suppression=job
            result['cases'].append(dict(label='B2-public-'+label+'-full-state',passed=True));persist()

        args=dict(**context,object_id=feature)
        before_preview=await observed('before-leaf-preview',job['result']['after']['state'])
        compare_b2_state(before_preview,job['result']['after']['state'])
        prepared,preparation,_=await invoke('feature_prepare_leaf_deletion','b2-leaf-prepare',**args)
        if not verified_b2_job(preparation):
            raise ValueError('Exact read-only leaf preparation must be proved.')
        prepared_state=await observed('leaf-preview',prepared['baseline'])
        compare_b2_state(prepared_state,prepared['baseline'])
        compare_b2_state(prepared_state,before_preview)
        args['expected_revision']=prepared['revision']
        _,job,_=await invoke('feature_delete_leaf','b2-leaf-delete',**args)
        if not verified_b2_job(job,preparation_job=preparation):
            raise ValueError('Exact committed leaf deletion was not proved.')
        final=await observed('deleted',job['result']['after']['state'])
        compare_b2_state(final,job['result']['after']['state'])
        _,replay,_=await invoke('feature_delete_leaf','b2-leaf-delete',**args)
        if _json(replay)!=_json(job):raise ValueError('Deletion replay changed its durable job.')
        # The deleted feature ID is tested through read-only access. No new
        # deletion request is dispatched after its committed retirement.
        before=read_journal(journal_path)
        refused=await public_invoke(client,gate,report,persist,'feature_get',
            request_id='b2-deleted-feature-get',**context,object_id=feature)
        if (refused['status']!='failed' or refused.get('error',{}).get('code')!='object_reference_not_found'):
            raise ValueError('The exact retired feature ID must be refused on read.')
        refused_job=await persisted_response(refused,before)
        if (refused_job['operation']!='feature.get'
                or refused_job['payload']['arguments']!=dict(**context,object_id=feature)
                or refused_job['payload']['mutates'] is not False
                or refused_job.get('mutation') is not None
                or refused_job['error']['code']!='object_reference_not_found'):
            raise ValueError('Retired-ID refusal must be a durable read-only exact-object job.')
        after_refusal=await observed('retired-id-refused',job['result']['after']['state'])
        compare_b2_state(after_refusal,final)
        result.update(final_job=job,final_preparation_job=preparation,
            independent_final_state=after_refusal,deleted_id_refused=refused_job)
        result['cases'].append(dict(label='B2-public-leaf-preview-delete-replay-retired-ID',passed=True))
        result['positive_case_passed']=True
        extension_final_state(result,extrusion_job)
        report['b2_extension']=result;persist()
        return result
    except BaseException:
        client.retain('Public B2 mutation, durable/native observation or lineage unconfirmed.')
        raise


def extension_final_state(extension, original_extrusion_job):
    """Bind bootstrap cleanup metadata to an actual final committed leaf job."""
    if (type(extension) is not dict or extension.get('scope') != 'b2_public_positive_extension_v1'
            or extension.get('accepted') is not False or extension.get('native_b2_accepted') is not False
            or extension.get('positive_case_passed') is not True):
        raise ValueError('A completed bounded B2 extension is required.')
    job, preparation = extension['final_job'], extension['final_preparation_job']
    if not verified_b2_job(job, preparation_job=preparation):
        raise ValueError('Exact durable final leaf job/preparation must be proved.')
    original = original_extrusion_job['payload']['arguments']
    args = job['payload']['arguments']
    created = original_extrusion_job['result']['value']
    if (job['operation'] != 'feature.delete_leaf'
            or args['document_id'] != original['document_id']
            or args['configuration'] != original['configuration']
            or args['object_id'] != created['feature_object_id']
            or preparation['result']['creation_operation_id'] != original_extrusion_job['operation_id']
            or job['result']['value']['preserved_sketch_object_id'] != original['sketch_object_id']):
        raise ValueError('The exact original B1 target/sketch lineage must survive the extension.')
    state = job['result']['after']['state']
    snapshot = validated_rectangle_snapshot(state['snapshots'][args['document_id']])
    actual=validated_rectangle_snapshot(extension['independent_final_state']['snapshots'][args['document_id']])
    if (snapshot['clone_state']['profile'] != SKETCH or snapshot['solid_body_count'] != 0
            or actual['clone_state']['profile'] != SKETCH or actual['solid_body_count'] != 0):
        raise ValueError('Full independent final SKETCH evidence is required.')
    compare_b2_state(extension['independent_final_state'],state)
    return deepcopy(state)

"""One-owner installed B1 positive/replay native probe; not whole B1 acceptance.

Only exact normal fixture returns establish ownership. Pending/unknown effects
retain the process and native receipts; no cancellation, retry or roster adoption.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import traceback
import uuid

import pythoncom
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner,JobStore
from solidworks_mcp.native_first_save import validated_part_snapshot
from solidworks_mcp.part_creation import BaseRectangle,validated_plane_transform
from solidworks_mcp.rectangle_construction_catalog import RectangleConstructionCatalog
from solidworks_mcp.rectangle_snapshot import validated_rectangle_snapshot,EMPTY,SKETCH,BASE
from solidworks_mcp.session import SolidWorksSession
from probe_native_first_save_domain import package_evidence
from verify_bounds_measurements import InlineSta
from verify_export_operations import activate_owned,application_preferences
from verify_native_document_open import retire_owned,snapshot
from verify_native_first_save_rejections import owned_document_rows
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verifier_rectangle_stages import verified_rectangle_job


HELPERS=('verify_rectangle_stages_positive.py','verifier_rectangle_stages.py','probe_native_first_save_domain.py',
    'verify_installed_metadata.py','verify_wheel_artifact.py','verify_bounds_measurements.py',
    'verify_export_operations.py','verify_native_document_open.py','verify_native_first_save_rejections.py',
    'verifier_dimension_diagnostics.py')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks',action='store_true')
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--expected-version',required=True)
    parser.add_argument('--expected-git-sha',required=True)
    args=parser.parse_args();assert args.run_solidworks
    state=args.state_dir.resolve();assert state.is_relative_to(Path.cwd()/'work') and not state.exists()
    state.mkdir();args.state_dir=state
    started=time.perf_counter()
    report=dict(scope='installed_rectangle_stages_positive_only',accepted=False,positive_case_passed=False,
        phase='preflight',native_calls_live=False,owned_documents=[],cases=[],captures=[],
        verifier_hashes={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in HELPERS})
    def persist():
        report['elapsed_seconds']=time.perf_counter()-started
        (state/'report.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    def record(models):report['owned_documents']=owned_document_rows(models);persist()
    try:report.update(package_evidence(args,installed=True))
    except BaseException as error:
        report.update(phase='preflight_failed',error=str(error));persist();raise

    class Observed(SolidWorksDocuments):
        creates=extrusions=0
        def _stage(self,kind,method,*args):
            receipt=args[-1]
            report['native_calls_live']=True;persist()
            if kind=='sketch':self.creates+=1
            else:self.extrusions+=1
            try:return method(*args)
            finally:
                if (receipt.native_call_returned is True and receipt.pending_native_step is None
                        and not receipt.pending_creation and not receipt.pending_sketch_close
                        and not receipt.native_step_journal_failed and not receipt.selection_uncertain):
                    report['native_calls_live']=False;persist()
        def create_rectangle_sketch(self,*args):return self._stage('sketch',super().create_rectangle_sketch,*args)
        def extrude_rectangle_sketch(self,*args):return self._stage('extrusion',super().extrude_rectangle_sketch,*args)
        def rectangle_construction_snapshot(self,model):
            row=dict(title=model.GetTitle(),status='running',started_s=time.perf_counter()-started)
            report['captures'].append(row);persist()
            try:
                result=super().rectangle_construction_snapshot(model)
                row.update(status='returned',elapsed_s=time.perf_counter()-started-row['started_s']);return result
            except BaseException as error:row.update(status='failed',error=str(error));raise
            finally:persist()

    owned=[];store=domain=None
    pythoncom.CoInitialize()
    try:
        sw=binding.connect(show=False);module=binding.module();adapter=Observed()
        assert not sw.GetDocuments() and sw.ActiveDoc is None and sw.CommandInProgress is False and sw.UserControl is True
        original=snapshot(sw,module);app=adapter.native_close_application_context();prefs=application_preferences(sw)
        report.update(original_baseline=original,original_application=app,original_preferences=prefs,phase='fixture_creation')
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is False
        sw.CommandInProgress=True;assert sw.CommandInProgress is True
        session=SolidWorksSession();session._sw,session._mod=sw,module
        for name in ('Контрольная деталь отдельных стадий','Рабочий сосед отдельных стадий'):
            report['native_calls_live']=True;persist()
            returned=session.new_part();model=session._model;owned.append(model)
            assert type(returned) is dict and returned['ok'] is True
            report.setdefault('normal_creation_returns',[]).append(returned)
            report['native_calls_live']=False;record(owned)
            assert model.SetTitle2(name) and model.GetTitle()==name
            cfg=binding.wrap(model.GetActiveConfiguration(),module.IConfiguration);cfg.Name='Основная'
            assert tuple(model.GetConfigurationNames())==('Основная',)
            assert model.ForceRebuild3(False);model.ClearSelection2(True)
        target,neighbor=owned
        frame=validated_plane_transform((1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.))
        features=adapter.features(neighbor)
        planes=[f for f in features if f.GetTypeName2()=='RefPlane' and validated_plane_transform(adapter.reference_plane_transform(f))==frame]
        assert len(planes)==1
        base=BaseRectangle.validate(plane_object_id='feat_'+uuid.uuid4().hex,width_mm=5.,height_mm=6.,depth_mm=7.)
        receipt=adapter.new_base_receipt(neighbor,features,adapter.part_creation_controls(neighbor))
        report['native_calls_live']=True;persist();adapter.create_base_rectangle(neighbor,planes[0],base,receipt)
        report['native_calls_live']=False;record(owned)
        assert neighbor.ForceRebuild3(False) and neighbor.GetSaveFlag() is True
        activate_owned(sw,target,target.GetTitle())
        initial=validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(target));assert initial['clone_state']['profile']==EMPTY
        neighbor_before=validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))
        report.update(independent_empty=initial,independent_neighbor=neighbor_before)
        sw.CommandInProgress=False;assert sw.CommandInProgress is False
        documents=DocumentCatalog(adapter);documents.list()
        target_id=next(e.document_id for e in documents._entries if e.identity==adapter.identity(target))
        store=JobStore(state/'jobs.sqlite');domain=RectangleConstructionCatalog(documents,store,'rectangle_'+uuid.uuid4().hex)
        runner=JobRunner(store,InlineSta())
        planes=domain.features.list(target_id,'Основная')['items']
        matches=[]
        for row in planes:
            if row['feature_type']!='RefPlane' or not row['object_id']:continue
            entry,_=documents.resolve(target_id,'Основная')
            current,_=domain.features._resolve(entry,'Основная',adapter.configuration_identity(target,'Основная'),adapter.features(target),row['object_id'])
            if validated_plane_transform(adapter.reference_plane_transform(current))==frame:matches.append(row['object_id'])
        assert len(matches)==1
        def read(label,operation,arguments,function):
            report['phase']=label;persist()
            job=runner.submit(label,operation,arguments,lambda:function(**arguments),context=arguments)
            report[label]=job;persist();assert job['status']=='succeeded',job['error'];return job['result']
        def mutate(label,operation,arguments,function):
            report['phase']=label;persist()
            job=runner.submit(label,operation,arguments,lambda op:function(op,**arguments),context=arguments,
                mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
            report[label]=job;persist();assert verified_rectangle_job(job),job.get('error')
            replay=runner.submit(label,operation,arguments,lambda op:(_ for _ in ()).throw(AssertionError('Native replay')),
                context=arguments,mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
            assert replay==job;return job
        args_sketch=dict(document_id=target_id,configuration='Основная',plane_object_id=matches[0],width_mm=40.,height_mm=20.)
        p=read('sketch_prepare','sketch.prepare_rectangle',args_sketch,domain.prepare_sketch)
        args_sketch['sketch_name']='Эскиз основания';args_sketch['expected_revision']=p['revision']
        job=mutate('sketch_job','sketch.create_rectangle',args_sketch,domain.create_sketch)
        assert adapter.creates==1 and adapter.extrusions==0 and not domain.receipts
        report['cases'].append(dict(label='B1-N1-separate-sketch-and-replay',passed=True))
        sw.CommandInProgress=True;assert sw.CommandInProgress is True
        separate=validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(target))
        assert separate['clone_state']['profile']==SKETCH and separate['solid_body_count']==0
        assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))==neighbor_before
        report['independent_sketch']=separate;sw.CommandInProgress=False;assert sw.CommandInProgress is False
        args_extrude=dict(document_id=target_id,configuration='Основная',sketch_object_id=job['result']['value']['sketch_object_id'],depth_mm=10.)
        p=read('extrusion_prepare','part.prepare_rectangle_extrusion',args_extrude,domain.prepare_extrusion)
        args_extrude.update(feature_name='Основание',body_name='Тело основания',expected_revision=p['revision'])
        job=mutate('extrusion_job','part.extrude_rectangle',args_extrude,domain.create_extrusion)
        assert adapter.creates==adapter.extrusions==1 and not domain.receipts
        report['cases'].append(dict(label='B1-N1-separate-extrusion-and-replay',passed=True))
        sw.CommandInProgress=True;assert sw.CommandInProgress is True
        final=validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(target));assert final['clone_state']['profile']==BASE
        bodies=adapter.bodies(target,'all');assert len(bodies)==1
        volume=float(bodies[0].GetMassProperties(1.)[3])*1e9;assert math.isclose(volume,8000.,rel_tol=1e-8,abs_tol=1e-6)
        assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))==neighbor_before and neighbor.GetSaveFlag() is True
        report.update(independent_base=final,independent_volume_mm3=volume,independent_native_readback_verified=True)
        report['cases'].append(dict(label='B1-N2-N3-exact-native-base-and-neighbor',passed=True))
        assert report['native_calls_live'] is False and all(x['status']=='returned' for x in report['captures'])
        report['phase']='owned_cleanup';persist()
        retire_owned(sw,module,target,[target],owned,record)
        assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))==neighbor_before
        retire_owned(sw,module,neighbor,[neighbor],owned,record)
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        sw.CommandInProgress=False;assert sw.CommandInProgress is False
        restored=snapshot(sw,module);assert restored==original and adapter.native_close_application_context()==app
        report['restored_application']=adapter.native_close_application_context()
        assert_non_stl_preferences(lambda:application_preferences(sw),prefs,report,'restored_preferences')
        report.update(phase='terminal',positive_case_passed=True,baseline_restored=True,own_cleanup_verified=True,
            restored_baseline=restored,native_calls_live=False)
        report['cases'].append(dict(label='B1-owned-cleanup-baseline',passed=True));persist();store.close()
    except BaseException as error:
        report.update(phase='failed',error=str(error),traceback=traceback.format_exc());persist()
        if owned or report['native_calls_live'] is not False:
            report['retained_process']=True;persist()
            while True:time.sleep(.5)
        raise
    finally:persist();pythoncom.CoUninitialize()
    print(json.dumps(dict(scope=report['scope'],positive_case_passed=True,elapsed_seconds=report['elapsed_seconds'])),flush=True)


if __name__=='__main__':main()

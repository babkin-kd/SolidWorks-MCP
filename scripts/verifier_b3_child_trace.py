"""Consume actual private child records only after coherent terminal SDK/SQL.

No CAD, ownership adoption, cancellation or cleanup. Native PID/HWND/oracle
proofs still belong to the original fixture owner, not this trace binding.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from solidworks_mcp.jobs import _json


def require(condition,message):
    if not condition:raise ValueError(message)


class ChildTrace:
    def __init__(self,directory):
        self.directory=Path(directory).resolve(strict=True)
        private=Path(__file__).resolve().parents[1]/'work'
        require(self.directory.is_dir() and self.directory.is_relative_to(private)
                and self.directory!=private,'Existing private child trace directory required.')
        self.sequence=0;self.epoch=None;self.bound={}

    def bind(self,job):
        require(type(job) is dict and job.get('status') in ('succeeded','failed'),
                'Previously coherent terminal SDK/SQLite job required.')
        operation_id=job['operation_id']
        if operation_id in self.bound:
            saved=self.bound[operation_id]
            require(_json(job)==_json(saved['job']),'Replay changed the exact durable job.')
            raw=saved['path'].read_bytes()
            require(hashlib.sha256(raw).hexdigest()==saved['sha256'],'Original replay trace bytes changed.')
            return deepcopy(saved['evidence'])
        require(self.sequence<256,'Finite child trace sequence required.')
        path=self.directory/f'{self.sequence+1:04d}.json'
        raw=path.read_bytes()
        require(len(raw)<=1024*1024,'Complete bounded child trace required.')
        record=json.loads(raw)
        require(record.get('scope')=='private_b3_child_registration_trace_v1'
                and type(record.get('sequence')) is int and record['sequence']==self.sequence+1
                and record.get('operation_id')==operation_id and record.get('request_id')==job['request_id']
                and record.get('operation')==job['operation']
                and _json(record.get('arguments'))==_json(job['payload']['arguments'])
                and record.get('journal_status_at_capture')=='running'
                and record.get('journal_payload_sha256')==hashlib.sha256(_json(job['payload']).encode('utf8')).hexdigest(),
                'Actual callback trace differs from coherent operation/request/payload.')
        epoch=record.get('connection_epoch')
        require(type(epoch) is str and re.fullmatch('connection_[0-9a-f]{32}',epoch) is not None
                and (self.epoch is None or self.epoch==epoch),'Original child connection epoch changed or missing.')
        require(all(record.get(key) is False for key in ('accepted','native_acceptance',
                'cleanup_authorized','current_membership_verified','whole_session_native_envelope_verified',
                'original_birth_ownership_verified')),'Private trace cannot claim native ownership/acceptance.')
        if job['status']=='succeeded':
            require(record.get('status')=='returned' and record.get('error') is None
                    and record.get('result_sha256')==hashlib.sha256(_json(job['result']).encode('utf8')).hexdigest(),
                    'Normally returned trace differs from terminal result.')
            windows=record.get('document_window_bindings');exports=record.get('registered_references')
            require(type(windows) is list and 0<len(windows)<=32 and type(exports) is list
                    and len(exports)==len(windows),'Actual complete window-mode namespace required, not registration-only mode.')
            ids=[item['document_id'] for item in windows];hwnds=[item['hwnd'] for item in windows]
            require(all(type(item) is str and re.fullmatch('doc_[0-9a-f]{32}',item) for item in ids)
                    and len(set(ids))==len(ids) and all(type(hwnd) is int and 0<hwnd<2**63 for hwnd in hwnds)
                    and len(set(hwnds))==len(hwnds) and [item['document_id'] for item in exports]==ids,
                    'Distinct complete actual document/HWND/export associations required.')
        else:
            require(record.get('status')=='exception_returned' and record.get('result_sha256') is None
                    and type(record.get('error')) is dict and type(job.get('error')) is dict
                    and record['error']['code']==job['error']['code']
                    and job['error'].get('requires_reconciliation') is False
                    and record.get('registered_references')==[] and record.get('document_window_bindings') is None,
                    'Only a coherent known exception refusal may bind without current namespace.')
        evidence=dict(scope='b3_actual_child_trace_job_binding_v1',trace=record,
            sha256=hashlib.sha256(raw).hexdigest(),accepted=False,native_acceptance=False,
            cleanup_authorized=False,current_membership_verified=False)
        self.bound[operation_id]=dict(job=deepcopy(job),path=path,sha256=evidence['sha256'],evidence=deepcopy(evidence))
        self.sequence+=1;self.epoch=epoch
        return evidence

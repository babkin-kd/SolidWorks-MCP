"""Future N4/N5 driver refuses a live/foreign positive report before COM."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


def test_driver_rejects_running_positive_report_without_native_connection(tmp_path,monkeypatch):
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec=importlib.util.spec_from_file_location('rectangle_faults_preflight_driver',scripts/'verify_rectangle_stages_faults.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    monkeypatch.chdir(tmp_path)
    (tmp_path/'work').mkdir()
    positive=tmp_path/'positive.json'
    positive.write_text(json.dumps(dict(scope='installed_rectangle_stages_positive_only',
        phase='sketch_job',accepted=False,positive_case_passed=False)),encoding='utf8')
    monkeypatch.setattr(helper,'package_evidence',lambda *args,**kwargs:dict(wheel={}))
    monkeypatch.setattr(helper.binding,'connect',lambda **kwargs:pytest.fail('Preflight dispatched a native connection'))
    monkeypatch.setattr(helper.pythoncom,'CoInitialize',lambda:pytest.fail('Preflight initialized the CAD STA'))
    monkeypatch.setattr(sys,'argv',['verify_rectangle_stages_faults.py','--run-solidworks',
        '--state-dir',str(tmp_path/'work'/'refused'), '--wheel','unused.whl',
        '--expected-version','2.0.0.dev91','--expected-git-sha','a'*40,
        '--positive-report',str(positive)])
    with pytest.raises(ValueError):helper.main()
    report=json.loads((tmp_path/'work'/'refused'/'report.json').read_text(encoding='utf8'))
    assert report['phase']=='preflight_failed' and report['accepted'] is False
    assert report['native_calls_live'] is False and report['owned_documents']==[]

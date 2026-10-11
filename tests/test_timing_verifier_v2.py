"""Metadata-only harness must close a plain SDK session without CAD dispatch."""
from contextlib import asynccontextmanager
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('enabled',[False,True])
def test_metadata_only_uses_no_native_supervisor_or_durable_dispatch(tmp_path,monkeypatch,enabled):
    root=Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'scripts'))
    spec=importlib.util.spec_from_file_location('timing_verifier_under_test',root/'scripts/verify_timings_v2.py')
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    wheel=dict(package_version='2.0.0.dev69',git_sha='a'*40,source_digest='b'*64)
    called=[];closed=[]
    @asynccontextmanager
    async def transport(params):
        assert ('--enable-timings' in params.args)==enabled
        yield None,None
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):closed.append(True)
        async def initialize(self):pass
        async def list_tools(self):return SimpleNamespace(tools=[])
        async def call_tool(self,name,args):
            assert name in {'system_get_info','job_get','diagnostics_get_timings'}
            called.append(name)
            content=dict(status='succeeded',data={})
            if name=='job_get':content['status']='failed'
            if name=='diagnostics_get_timings':
                if args['period_s']<0:content.update(status='failed',error=dict(code='invalid_timing_filter'))
                else:
                    groups=[dict(build=wheel,operation='system_get_info',sample_count=21,kind='mcp_call',outcome='succeeded'),
                        dict(build=wheel,operation='job_get',sample_count=1,kind='poll',outcome='failed')] if enabled else []
                    content['data']=dict(enabled=enabled,available=enabled,sample_count=22 if enabled else 0,groups=groups)
            return SimpleNamespace(isError=False,structuredContent=content)
    monkeypatch.setattr(verifier,'stdio_client',transport)
    monkeypatch.setattr(verifier,'ClientSession',lambda *args:Client())
    monkeypatch.setattr(verifier,'verify_metadata',lambda *args:None)
    monkeypatch.setattr(verifier,'open_supervised_session',lambda *a,**k:pytest.fail('Empty native tracker cannot authorize metadata-only exit'))
    report=asyncio.run(verifier.exercise(tmp_path/'entry',tmp_path,wheel,enabled,False))
    assert report['metadata_only_sdk_closed'] is True and report['supervisor_cleanup_verified'] is None
    assert report['native_read_transport'] is None and closed==[True]
    assert called.count('system_get_info')==21
    assert not (tmp_path/'jobs.sqlite').exists()

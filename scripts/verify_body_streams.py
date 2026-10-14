"""Diagnose opaque native serialization; never normalize bytes or accept export.

Run sequentially against the installed wheel. Only temporary body copies from
owned disposable fixtures are serialized. No source CAD file is saved.
"""

import argparse
import hashlib
import json
from pathlib import Path
import time

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures


def serialized(body):
    assert body.IsTemporaryBody()
    stream = pythoncom.CreateStreamOnHGlobal()
    body.Save(stream)
    size = int(stream.Seek(0, 2))
    assert 0 < size < 64 * 1024 * 1024
    stream.Seek(0, 0)
    value = stream.Read(size)
    assert len(value) == size
    return value


def facts(value):
    return {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}


def compare(first, second):
    offsets = [index for index, (a, b) in enumerate(zip(first, second)) if a != b]
    return {'equal': first == second, 'first': facts(first), 'second': facts(second),
            'different_byte_count': len(offsets) + abs(len(first) - len(second)),
            'first_difference_offsets': offsets[:32]}


def check():
    assert 'site-packages' in solidworks_mcp.__file__
    original = native_snapshot()
    report = {'package_version': solidworks_mcp.__version__, 'checks': {}}
    with fixtures() as (_, owned, _):
        module = binding.module()
        model = owned[1]
        source = binding.wrap(binding.wrap(model, module.IPartDoc).GetBodies2(-1, False)[0], module.IBody2)
        metadata = native_snapshot()
        original_body_stamp = int(source.GetUpdateStamp())

        def clone(method):
            raw = source.Copy() if method == 'Copy' else source.Copy2(True)
            body = binding.wrap(raw, module.IBody2)
            assert body.IsTemporaryBody()
            assert body._oleobj_.QueryInterface(pythoncom.IID_IUnknown) != source._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
            return body

        for method in ('Copy', 'Copy2_preserve_face_ids'):
            body = clone(method)
            first = serialized(body)
            immediate = serialized(body)
            time.sleep(1.2)
            delayed_same = serialized(body)
            delayed_new = serialized(clone(method))
            value = {'same_clone_immediate': compare(first, immediate),
                     'same_clone_delayed': compare(first, delayed_same),
                     'new_clone_delayed': compare(delayed_same, delayed_new),
                     'source_body_stamp_before': original_body_stamp,
                     'source_body_stamp_after': int(source.GetUpdateStamp()),
                     'temporary_body_stamp': int(body.GetUpdateStamp())}
            report['checks'][method] = value
            print(json.dumps({'phase': method, **value}), flush=True)
        assert native_snapshot() == metadata
    assert native_snapshot() == original
    report['original_document_baseline_restored'] = True
    report['export_or_dimension_acceptance'] = False
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    assert not args.report.exists()
    pythoncom.CoInitialize()
    try:
        result = check()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
        print(json.dumps(result, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()

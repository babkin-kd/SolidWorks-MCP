"""Installed analytic boundary-snapshot acceptance on owned planar fixtures.

No source model is changed. A translation is applied only to an independent
temporary copy. This is a box/translation gate, not arbitrary BREP acceptance.
"""

import argparse
import hashlib
import json
from pathlib import Path
import time

import pythoncom
import win32com.client
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.cad_planar_brep import planar_body_snapshot
from solidworks_mcp.jobs import _json
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures


def check():
    assert 'site-packages' in solidworks_mcp.__file__
    original = native_snapshot()
    with fixtures() as (session, owned, _):
        sw, module = session._sw, binding.module()
        model = owned[1]
        native = binding.wrap(model, module.IPartDoc).GetBodies2(-1, False)
        assert len(native) == 1
        body = binding.wrap(native[0], module.IBody2)
        setup = native_snapshot()

        def identity(obj):
            return obj._oleobj_.QueryInterface(pythoncom.IID_IUnknown)

        def wrap(obj, interface):
            return binding.wrap(obj, getattr(module, interface))

        def snapshot(obj):
            return planar_body_snapshot(obj, identity=identity, wrap=wrap)

        first = snapshot(body)
        time.sleep(1.2)
        assert snapshot(body) == first, 'Source snapshot changed with elapsed time.'
        for method in ('Copy', 'Copy2'):
            raw = body.Copy() if method == 'Copy' else body.Copy2(True)
            clone = wrap(raw, 'IBody2')
            assert clone.IsTemporaryBody() and identity(clone) != identity(body)
            assert snapshot(clone) == first, f'{method} does not preserve the declared boundary scope.'
        clone = wrap(body.Copy(), 'IBody2')
        math_utility = wrap(sw.GetMathUtility(), 'IMathUtility')
        matrix = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
            [1., 0., 0., 0., 1., 0., 0., 0., 1., .001, 0., 0., 1., 0., 0., 0.])
        transform = wrap(math_utility.CreateTransform(matrix), 'IMathTransform')
        assert transform is not None and clone.ApplyTransform(transform)
        assert snapshot(clone) != first, 'A translated temporary body was accepted as unchanged.'
        assert snapshot(body) == first
        assert native_snapshot() == setup
        result = {'package_version': solidworks_mcp.__version__, 'box_face_count': int(body.GetFaceCount()),
            'box_edge_count': int(body.GetEdgeCount()), 'box_vertex_count': int(body.GetVertexCount()),
            'source_snapshot_sha256': hashlib.sha256(_json(first).encode('utf8')).hexdigest(),
            'same_source_after_delay_verified': True, 'copy_and_copy2_same_boundary_verified': True,
            'temporary_translation_detected': True, 'source_model_unchanged': True,
            'arbitrary_brep_acceptance': False, 'internal_cavity_native_acceptance': False,
            'native_topology_split_acceptance': False, 'curved_geometry_acceptance': False}
    assert native_snapshot() == original
    result['original_document_baseline_restored'] = True
    return result


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

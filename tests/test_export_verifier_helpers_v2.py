"""Truthful export-verifier reporting regressions, with no native imports.

Only selected function definitions are extracted from the verifier sources.
Their module-level imports, main routines and CAD setup never execute. The
failure-path tests supply explicitly artificial readers and owned fixtures.
"""

import ast
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def extracted_functions(filename, names, namespace=None):
    namespace = {} if namespace is None else namespace
    path = SCRIPTS / filename
    tree = ast.parse(path.read_text(encoding='utf8'), filename=str(path))
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in selected} == set(names)
    # A future helper change must not silently turn these pure tests native.
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom))
                   for function in selected for node in ast.walk(function))
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def setup_baseline(before, after):
    function = extracted_functions('verify_export_operations.py',
                                   {'fixture_preferences_baseline'})['fixture_preferences_baseline']
    return function(before, after)


def cleanup_flags(readers):
    function = extracted_functions('verify_internal_exports.py',
                                   {'cleanup_baseline_flags'})['cleanup_baseline_flags']
    return function(readers)


def test_fixture_deviation_recalculation_preserves_exact_before_after_evidence():
    before = {'stl_deviation': 9.151909669896612e-7, 'stl_angle': 0.1, 'stl_quality': 2}
    after = {**before, 'stl_deviation': 9.15190966989661e-7}
    facts = setup_baseline(before, after)
    assert facts['fixture_setup_stl_deviation'] == {
        'before': before['stl_deviation'], 'after': after['stl_deviation']}
    assert facts['export_preferences_baseline_captured_after_fixture_setup'] is True
    assert facts['fixture_setup_other_preferences_exactly_unchanged'] is True
    # Setup reporting must not round/mutate the snapshots into exact equality.
    assert before != after


def test_fixture_other_preference_change_is_rejected_even_with_deviation_change():
    before = {'stl_deviation': 1., 'stl_angle': 0.1}
    after = {'stl_deviation': 2., 'stl_angle': 0.10000000000000002}
    with pytest.raises(AssertionError, match='Fixture setup changed other preferences'):
        setup_baseline(before, after)


def test_fixture_changed_keyset_or_missing_deviation_cannot_claim_baseline():
    pairs = [({'stl_deviation': 1.}, {'stl_deviation': 1., 'stl_quality': 2}),
             ({'stl_deviation': 1., 'stl_quality': 2}, {'stl_deviation': 1.}),
             ({'stl_quality': 2}, {'stl_quality': 2})]
    for before, after in pairs:
        with pytest.raises((AssertionError, KeyError)):
            setup_baseline(before, after)


def test_fixture_unchanged_setup_is_accepted_and_not_mutated():
    before = {'stl_deviation': 1., 'stl_quality': 2}
    after = dict(before)
    facts = setup_baseline(before, after)
    assert facts['fixture_setup_other_preferences_exactly_unchanged'] is True
    assert facts['fixture_setup_stl_deviation'] == {'before': 1., 'after': 1.}
    assert before == after == {'stl_deviation': 1., 'stl_quality': 2}


def test_cleanup_flags_distinguish_match_from_exact_float_mismatch():
    result = cleanup_flags({'docs': (lambda: ['baseline'], ['baseline']),
                            'prefs': (lambda: 0.10000000000000002, 0.1)})
    assert result['docs'] is True
    assert result['prefs'] is False
    assert result['cleanup_baseline_read_errors'] == {}


def test_cleanup_failed_reader_is_unknown_and_other_readers_still_execute():
    calls = []

    def broken():
        calls.append('docs')
        raise RuntimeError('Read unavailable')

    def later():
        calls.append('ui')
        return 0

    result = cleanup_flags({'docs': (broken, []), 'ui': (later, 0)})
    assert result['docs'] is None
    assert result['ui'] is True
    assert calls == ['docs', 'ui']
    assert result['cleanup_baseline_read_errors'] == {
        'docs': {'error_type': 'RuntimeError', 'message': 'Read unavailable'}}


def test_cleanup_comparison_error_is_unknown_instead_of_false_or_true():
    class Uncomparable:
        def __eq__(self, other):
            raise ValueError('Equality unavailable')

    result = cleanup_flags({'ui': (lambda: Uncomparable(), 0)})
    assert result['ui'] is None
    assert result['cleanup_baseline_read_errors']['ui'] == {
        'error_type': 'ValueError', 'message': 'Equality unavailable'}


def failed_owned_setup(provenance):
    """Exercise real verifier cleanup/report control flow with only fakes."""
    original_error = RuntimeError('Owned adapter setup failure')
    calls = []

    @contextmanager
    def fixtures():
        try:
            yield None, [], None
        finally:
            calls.append('fixture_cleanup')

    def snapshot():
        calls.append('snapshot')
        if calls.count('snapshot') > 1:
            assert 'fixture_cleanup' in calls
        return ('exact',)

    def fail_adapter():
        raise original_error

    def read_provenance():
        calls.append('provenance')
        return dict(provenance)

    namespace = {'ExitStack': ExitStack, '_provenance': read_provenance,
                 'native_snapshot': snapshot,
                 'binding': SimpleNamespace(connect=lambda **kwargs: object(),
                                            module=lambda: object()),
                 'application_preferences': lambda sw: {'stl_deviation': 1.},
                 'ui_snapshot': lambda sw, module: [('ui', 0)],
                 'user_file_metadata': lambda original: {},
                 'fixtures': fixtures, 'SolidWorksDocuments': fail_adapter}
    check = extracted_functions('verify_internal_exports.py',
                                {'check', 'cleanup_baseline_flags'}, namespace)['check']
    report = {}
    with pytest.raises(RuntimeError) as captured:
        check(None, None, failure_report=report)
    assert captured.value is original_error
    return report, calls


def test_verifier_failure_preserves_exception_and_reads_baselines_after_cleanup():
    report, calls = failed_owned_setup({})
    assert calls == ['provenance', 'snapshot', 'fixture_cleanup', 'snapshot']
    for key in ('original_user_document_baseline_restored', 'original_preferences_restored',
                'original_ui_blocking_and_selection_restored', 'original_user_file_metadata_unchanged'):
        assert report[key] is True
    assert report['cleanup_baseline_read_errors'] == {}
    assert report['actual_native_export_count'] == 0
    assert report['native_export_adapter_call_count'] == 0
    assert report['actual_native_export_count_basis'] == 'no_native_export_adapter_entry'
    assert report['independently_confirmed_export_count'] == 0
    assert report['original_user_file_byte_hashes_checked'] is False


def test_verifier_failure_retains_installed_wheel_provenance_without_rereading():
    provenance = {'package_version': '2.0.0.dev13', 'git_sha': 'owned-build',
                  'source_dirty': False, 'installed_source_digest': 'strictdigest',
                  'installed_build_matches_package': True}
    report, calls = failed_owned_setup(provenance)
    assert {key: report[key] for key in provenance} == provenance
    assert calls.count('provenance') == 1
    assert calls.index('fixture_cleanup') < len(calls) - 1

"""Same-STA private ID/PID export with actual native document-window bindings.

No connection, registration, activation, setters, ownership adoption or cleanup.
The parent still proves each HWND belongs to its original retained model and
resolves used PIDs to original canonical objects; this capture cannot certify it.
"""
from verifier_b3_registered_references import export_registered_references, require


def capture_native_namespace(documents, *, expected_window_hwnds, watch_poll, assert_safe):
    """One original model window per document, complete finite unchanged census.

expected_window_hwnds are the driver's acknowledged original fixture windows,
not titles/path matches or a later roster difference. watch_poll combines the
already-owned watchers for all these models. Both callbacks run on this STA.
Only existing document/catalog tables are read; no refresh or ID adoption.
"""
    require(type(expected_window_hwnds) is tuple and 0 < len(expected_window_hwnds) <= 32
            and all(type(hwnd) is int and 0 < hwnd < 2**63 for hwnd in expected_window_hwnds)
            and len(set(expected_window_hwnds)) == len(expected_window_hwnds)
            and callable(watch_poll) and callable(assert_safe), 'Original bounded unique HWND roster and owner callbacks required.')
    assert_safe()

    def events():
        result = watch_poll()
        require(type(result) in (tuple, list) and len(result) == len(expected_window_hwnds)
                and all(type(value) is int and value >= 0 for value in result),
                'Complete typed native watcher sequence roster required.')
        return tuple(result)

    before_events = events()
    entries = tuple(documents._entries)
    require(len(entries) == len(expected_window_hwnds)
            and len({entry.document_id for entry in entries}) == len(entries),
            'Complete existing unique document registry required.')
    adapter = documents.adapter
    identities = tuple(entry.identity for entry in entries)
    require(all(sum(token == other for other in identities) == 1 for token in identities),
            'Distinct original catalog native identities required.')

    def capture_windows():
        current = tuple(adapter.documents())
        tokens = tuple(adapter.identity(model) for model in current)
        require(len(tokens) == len(identities)
                and all(sum(token == original for token in tokens) == 1 for original in identities),
                'Complete current model census differs; no foreign/new document adoption.')
        windows = tuple(adapter.native_close_windows())
        require(len(windows) == len(entries), 'One current original native window per document required.')
        mapping = []
        for entry in entries:
            require(adapter.identity(entry.model) == entry.identity, 'Original catalog model incarnation changed.')
            matched = [(model, info) for model, info in windows if adapter.identity(model) == entry.identity]
            require(len(matched) == 1, 'Exactly one current native window must belong to each retained catalog model.')
            hwnd = matched[0][1]['hwnd']
            require(type(hwnd) is int and hwnd in expected_window_hwnds,
                    'Current actual HWND must belong to the original acknowledged allowlist.')
            mapping.append(dict(document_id=entry.document_id, hwnd=hwnd))
        require(len({row['hwnd'] for row in mapping}) == len(mapping)
                and {row['hwnd'] for row in mapping} == set(expected_window_hwnds),
                'Whole original window roster differs or aliases models.')
        return mapping

    before = capture_windows()
    exports = [export_registered_references(entry, assert_safe=assert_safe) for entry in entries]
    after = capture_windows()
    current_entries = tuple(documents._entries)
    require(before == after and len(current_entries) == len(entries)
            and all(current is original for current, original in zip(current_entries, entries)),
            'Document registry or current window association changed during namespace export.')
    require(exports == [export_registered_references(entry, assert_safe=assert_safe) for entry in entries],
            'Actual private reference registration changed during window observation.')
    # All canonical comparisons and owner admission precede the final poll.
    assert_safe()
    require(events() == before_events, 'Whole document watcher envelope changed, including ABA.')
    return dict(scope='private_b3_current_native_window_namespace_v1',
                document_bindings=before, registered_references=exports,
                event_sequences=list(before_events), accepted=False, native_acceptance=False,
                cleanup_authorized=False, original_birth_ownership_verified=False,
                current_object_membership_verified=False,
                open_gates=['parent_original_model_canonical_HWND_association',
                            'used_PID_original_canonical_and_owner_roundtrip',
                            'whole_session_fixture_and_exact_installed_driver'])

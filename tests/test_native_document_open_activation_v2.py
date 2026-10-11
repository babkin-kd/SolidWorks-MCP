"""Ambiguous native title must not activate or discard the wrong model."""

from test_native_document_open_v2 import setup


def test_duplicate_title_prohibits_activation_and_ambiguous_cleanup(setup):
    x = setup
    original = x.a.open_native_document

    def duplicate(receipt):
        original(receipt)
        receipt.model.state['title'] = x.neighbor.state['title']

    x.a.open_native_document = duplicate
    result = x.run()
    assert result['status'] == 'unknown', result
    assert result['mutation']['phase'] == 'unresolved'
    assert x.a.open_calls == 1 and x.a.calls == 0 and x.a.activations == []
    assert result['operation_id'] in x.c.receipts
    assert x.neighbor.state['needs_save'] is True and not x.a.busy
    assert x.run() == result and x.a.open_calls == 1

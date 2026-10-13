"""Finite document-metadata subroute of B3-I01; no CAD ownership or cleanup.

Feature/dimension/sketch I01 reads stay separate. Current native observers must
read independently from the two original retained models/configuration anchors.
"""
from copy import deepcopy
import uuid

from verifier_b3_part_geometry import _call, _canonical, _proof


SCOPE = 'bounded_b3_i01_document_metadata_evidence_v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


async def document_metadata_case(reader, *, owned_document_ids, configurations,
                                 capture_full, capture_document):
    """Read exactly two owned parts and their explicit existing configurations.

capture_document(document_id, configuration) returns independent metadata
(excluding opaque document_id/observation revision/sequence), native_identity
and configuration_identity positive canonical equality ordinals, native_receipt.
It must reject replaced/foreign anchors and observe actual inactive metadata
without activation. capture_full observes both full parts and whole session.
No boolean complete flag substitutes for either trusted native producer.
"""
    require(type(owned_document_ids) is list and len(owned_document_ids) == 2
            and all(type(x) is str and x for x in owned_document_ids)
            and len(set(owned_document_ids)) == 2, 'Two original held document IDs required.')
    require(type(configurations) is dict and set(configurations) == set(owned_document_ids),
            'Original explicit configuration rosters required.')
    for names in configurations.values():
        require(type(names) is list and 1 <= len(names) <= 2
                and all(type(x) is str and x for x in names) and len(set(names)) == len(names),
                'Finite one/two existing configurations per owned part required.')
    require(callable(capture_full) and callable(capture_document), 'Independent native producers required.')
    owned_document_ids, configurations = deepcopy(owned_document_ids), deepcopy(configurations)
    before = _proof(await _call(capture_full))
    rows, receipts = [], []

    async def read(tool, **args):
        args = dict(request_id='b3-i01-'+uuid.uuid4().hex, **args)
        row = await reader.read(tool, args)
        require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal metadata read required.')
        rows.append(dict(tool=tool, arguments=args, journal=deepcopy(row)))
        return row['result']

    listed = await read('document_list')
    require(listed['revision_scope'] == 'update_stamp_and_document_metadata'
            and type(listed['documents']) is list and len(listed['documents']) == 2
            and {x['document_id'] for x in listed['documents']} == set(owned_document_ids),
            'Exact original two-document census required; no roster adoption.')
    by_id = {item['document_id']: item for item in listed['documents']}
    native_models = set()
    for document_id in owned_document_ids:
        original = by_id[document_id]
        require(original['document_type'] == 'part' and original['configurations'] == configurations[document_id]
                and original['active_configuration'] in configurations[document_id]
                and type(original['observation_revision']) is str and original['observation_revision'],
                'Original supported part/configuration roster differs.')
        model_identity, config_identities = None, set()
        for configuration in configurations[document_id]:
            value = await read('document_get', document_id=document_id, configuration=configuration)
            expected = dict(original, configuration=configuration,
                configuration_is_active=configuration == original['active_configuration'],
                revision_scope='update_stamp_and_document_metadata')
            require(_canonical(value) == _canonical(expected), 'Metadata list/get revision or configuration differs.')
            proof = _proof(await _call(capture_document, document_id, configuration))
            require(_canonical(proof['metadata']) == _canonical({k: v for k, v in value.items()
                if k not in ('document_id', 'observation_revision', 'observation_sequence')}),
                'Independent current native metadata differs.')
            for key in ('native_identity', 'configuration_identity'):
                require(type(proof[key]) is int and proof[key] > 0, 'Retained canonical equality ordinal required.')
            if model_identity is None:
                model_identity = proof['native_identity']
            require(proof['native_identity'] == model_identity
                    and proof['configuration_identity'] not in config_identities,
                    'Current retained model/configuration incarnation differs.')
            config_identities.add(proof['configuration_identity'])
            _proof(proof['native_receipt'])
            receipts.append(dict(document_id=document_id, configuration=configuration, proof=proof))
        require(model_identity not in native_models, 'Distinct original native parts required.')
        native_models.add(model_identity)
    after = _proof(await _call(capture_full))
    require(_canonical(before) == _canonical(after), 'Full parts/session changed during metadata reads.')
    return dict(scope=SCOPE, rows=rows, native_receipts=receipts, before=before, after=after,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['I01_feature_dimension_sketch', 'actual_native_producers',
                            'exact_installed_B3_driver', 'terminal_owned_cleanup'])

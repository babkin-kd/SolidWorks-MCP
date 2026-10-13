"""Direct retained-model I01 metadata observer; no connection or activation.

Original opaque-ID and birth ownership admission comes from the owning driver.
Whole-session observation remains separate from this local raw getter receipt.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RetainedConfiguration:
    name: str
    handle: object
    canonical: object


@dataclass(frozen=True)
class RetainedDocument:
    document_id: str
    model: object
    canonical: object
    configurations: tuple


def require(condition, message):
    if not condition:
        raise ValueError(message)


def capture_native_document_metadata(*, document_id, configuration, binding,
        wrap, identity, ordinal, watch, assert_safe):
    """Observe an existing active OR inactive configuration without switching.

All callbacks run on the original owner STA. assert_safe admits the actual
private document-ID binding before canonical comparisons/native getters.
Configuration handles were retained at fixture creation, never inferred from
names returned by the public result. Ordinals describe canonical equality only.
"""
    require(isinstance(binding, RetainedDocument)
            and type(document_id) is str and document_id
            and document_id == binding.document_id
            and type(configuration) is str and configuration,
            'Exact original document/configuration request required.')
    anchors = binding.configurations
    require(type(anchors) is tuple and 1 <= len(anchors) <= 2
            and all(isinstance(x, RetainedConfiguration) and type(x.name) is str and x.name for x in anchors)
            and len({x.name for x in anchors}) == len(anchors)
            and configuration in [x.name for x in anchors], 'Original finite configuration anchors required.')
    context = dict(document_id=document_id, configuration=configuration)
    assert_safe(context)
    event = watch.poll()
    require(type(event) is int and event >= 0, 'Typed original event sequence required.')
    model = binding.model
    names = [x.name for x in anchors]

    def observe():
        require(identity(model) == binding.canonical, 'Retained model incarnation changed.')
        require(all(sum(x.canonical == y.canonical for y in anchors) == 1 for x in anchors),
                'Original configuration canonical anchors must be distinct.')
        stamp = model.GetUpdateStamp()
        roster = model.GetConfigurationNames()
        require(type(stamp) is int and type(roster) in (list, tuple) and list(roster) == names,
                'Complete original configuration roster and typed update stamp required.')
        for anchor in anchors:
            current = wrap(model.GetConfigurationByName(anchor.name), 'IConfiguration')
            require(current is not None and current.Name == anchor.name
                    and identity(current) == anchor.canonical
                    and identity(anchor.handle) == anchor.canonical,
                    'Current named configuration must be its original retained incarnation.')
        active = wrap(model.GetActiveConfiguration(), 'IConfiguration')
        require(active is not None and type(active.Name) is str and active.Name in names,
                'Original active configuration required.')
        active_anchor = next(x for x in anchors if x.name == active.Name)
        require(identity(active) == active_anchor.canonical, 'Active configuration incarnation changed.')
        title, path, kind, dirty = model.GetTitle(), model.GetPathName(), model.GetType(), model.GetSaveFlag()
        require(type(title) is str and title and type(path) is str
                and type(kind) is int and kind == 1 and type(dirty) is bool,
                'Typed native part metadata required.')
        closing_stamp = model.GetUpdateStamp()
        require(type(closing_stamp) is int and closing_stamp == stamp,
                'Model changed inside raw metadata observation.')
        return dict(title=title, path=path, document_type='part', needs_save=dirty,
                    configurations=names[:], active_configuration=active.Name, update_stamp=stamp)

    before = observe()
    selected = next(x for x in anchors if x.name == configuration)
    native_id, config_id = ordinal(binding.canonical), ordinal(selected.canonical)
    require(all(type(x) is int and x > 0 for x in (native_id, config_id)), 'Positive canonical equality ordinals required.')
    after = observe()
    require(before == after, 'Native document metadata changed during observation.')
    # The closing admission may itself compare native handles: keep it watched.
    assert_safe(context)
    closing = watch.poll()
    require(type(closing) is int and closing == event, 'Native events changed during observation, including ABA.')
    metadata = dict(after, configuration=configuration,
                    configuration_is_active=configuration == after['active_configuration'],
                    revision_scope='update_stamp_and_document_metadata')
    return dict(metadata=metadata, native_identity=native_id, configuration_identity=config_id,
                native_receipt=dict(scope='raw_retained_document_metadata_v1', before=before, after=after,
                    event_sequence=event, original_configuration_count=len(anchors),
                    accepted=False, native_acceptance=False, cleanup_authorized=False))

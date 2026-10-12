"""Exact retained annotation-view inverse for the bounded rectangle stages.

Internal bridge: the caller owns the model guard, durable checkpoint and private
selection scope. This does not authorize an inverse without the executor's full
effect proof, and does not replace its independent restored-baseline gate.
"""
from dataclasses import dataclass, field

from . import binding
from .cad_native_first_save_snapshot import _array, _number, _typed
from .jobs import ExecutionFailure


def _fail(message):
    raise ExecutionFailure('rectangle_view_restore_unconfirmed', message, uncertain=True)


@dataclass
class NativeView:
    view: object
    token: object
    data: dict


@dataclass
class RectangleViewReceipt:
    model_token: object
    baseline: tuple
    owned: list = field(default_factory=list)
    binding_attempted: bool = False
    bound: bool = False
    retirement_attempted: bool = False
    retired: bool = False


def _inventory(adapter, model):
    extension = adapter._extension(model)
    raw = _array(extension.AnnotationViews, 16)
    count = extension.AnnotationViewCount
    if type(count) is not int or count != len(raw) or not raw:
        _fail('A complete nonempty native view inventory is required.')
    rows = []
    for item in raw:
        view = binding.wrap(item, adapter._module.IAnnotationView)
        token = adapter.identity(view)
        if any(token == row.token for row in rows):
            _fail('Native view identities must be unique.')
        rotation = _array(view.GetViewRotation(), 9)
        if len(rotation) != 9:
            _fail('A full view rotation is required.')
        data = dict(always_2d=_typed(view.Always2D, bool),
            flat_pattern=_typed(view.FlatPatternView, bool),
            unassigned=_typed(view.UnassignedView, bool),
            shown=_typed(view.IsShown(), bool),
            angle=_number(view.AngleMadeWithViewHorizontal),
            rotation=[_number(v) for v in rotation],
            annotation_count=_typed(view.AnnotationCount, int))
        if data['annotation_count'] != 0 or _array(view.GetAnnotations2(False, False), 128):
            _fail('Only completely observed empty annotation views are supported.')
        rows.append(NativeView(view, token, data))
    closing = _array(extension.AnnotationViews, 16)
    if (type(extension.AnnotationViewCount) is not int
            or extension.AnnotationViewCount != count or len(closing) != count
            or any(adapter.identity(v) != row.token for v, row in zip(closing, rows))):
        _fail('View inventory changed during observation.')
    return tuple(rows)


def capture_rectangle_views(adapter, model):
    """Retain the complete baseline before construction, without selection."""
    return RectangleViewReceipt(adapter.identity(model), _inventory(adapter, model))


def _same(rows, expected):
    return (len(rows) == len(expected)
        and all(a.token == b.token and a.data == b.data for a, b in zip(rows, expected)))


def _current_owned(adapter, model, receipt):
    if adapter.identity(model) != receipt.model_token:
        _fail('The exact retained document is required.')
    current = _inventory(adapter, model)
    baseline = [row for row in current if any(row.token == old.token for old in receipt.baseline)]
    if not _same(baseline, receipt.baseline):
        _fail('Baseline view incarnations or data changed.')
    created = [row for row in current if not any(row.token == old.token for old in receipt.baseline)]
    return current, created


def _selected_view(adapter, model):
    selection = binding.wrap(model.SelectionManager, adapter._module.ISelectionMgr)
    count = selection.GetSelectedObjectCount2(-1)
    kind = selection.GetSelectedObjectType3(1, -1) if count == 1 else None
    if type(count) is not int or count != 1 or type(kind) is not int or kind != 139:
        _fail('Exactly one native annotation view must be selected.')
    raw = selection.GetSelectedObject6(1, -1)
    if raw is None:
        _fail('Selected annotation view has no exact handle.')
    return adapter.identity(raw)


def retain_rectangle_view(adapter, model, receipt, owned_feature, *, step, dimension_count):
    """Bind one new view through exact owned dimensions and native selection.

    `owned_feature` must be the normal-return handle already proved by the
    construction receipt/full executor observation. No name, native ID or tree
    roster difference can establish view ownership.
    """
    if (receipt.binding_attempted or receipt.retirement_attempted
            or type(dimension_count) is not int or dimension_count not in (1, 2)):
        _fail('Annotation view binding is one-shot for one rectangle stage.')
    receipt.binding_attempted = True
    current, created = _current_owned(adapter, model, receipt)
    if len(created) != 1:
        _fail('One independently bound new view is required.')
    target = created[0]
    if (target.data['always_2d'] or target.data['flat_pattern'] or target.data['unassigned']
            or target.data['shown'] or target.data['angle'] != 0.0.hex()):
        _fail('New view is outside the bounded rectangle display effect.')
    feature_token = adapter.identity(owned_feature)
    if not any(adapter.identity(f) == feature_token for f in adapter.features(model)):
        _fail('Owned feature must still belong to the exact document.')
    dimensions = adapter.dimensions(model, [owned_feature])
    if len(dimensions) != dimension_count:
        _fail('Complete owned feature dimensions are required.')
    for dimension in dimensions:
        if (dimension.owner_tree_identity != feature_token or dimension.owner is None
                or adapter.identity(dimension.owner) != feature_token or not dimension.displays):
            _fail('Every dimension must belong to the retained owned feature.')
        for display in dimension.displays:
            annotation = binding.wrap(display.GetAnnotation(), adapter._module.IAnnotation)
            owner = binding.wrap(annotation.AnnotationView, adapter._module.IAnnotationView) if annotation else None
            if owner is None or adapter.identity(owner) != target.token:
                _fail('All owned driving dimensions must bind this exact new view.')
    manager = binding.wrap(model.FeatureManager, adapter._module.IFeatureManager)
    root = binding.wrap(manager.GetFeatureTreeRootItem2(0), adapter._module.ITreeControlItem)
    if root is None:
        _fail('Complete annotation-view feature tree is unavailable.')
    queue, seen, matches, candidates = [root], [], [], 0
    while queue:
        node = queue.pop()
        node_token = adapter.identity(node)
        if any(node_token == old for old in seen) or len(seen) >= 500:
            _fail('Annotation feature tree is cyclic or exceeds its budget.')
        seen.append(node_token)
        kind = node.ObjectType
        if type(kind) is not int or kind not in (0, 1):
            _fail('Native tree object type is malformed.')
        if kind == 1:
            feature = binding.wrap(node.Object, adapter._module.IFeature)
            if feature is None:
                _fail('Native tree feature has no exact handle.')
            if feature.GetTypeName2() == 'AnnotationViewFeat':
                if candidates >= 16:
                    _fail('Annotation-view feature inventory exceeds its budget.')
                label = 'bind_annotation_view_feature_' + str(candidates)
                candidates += 1
                if step(label, feature.Select2, False, 0) is not True:
                    _fail('Native annotation-view feature selection is unconfirmed.')
                if _selected_view(adapter, model) == target.token:
                    matches.append(feature)
        child = binding.wrap(node.GetFirstChild(), adapter._module.ITreeControlItem)
        while child is not None:
            if len(queue) >= 500 or any(adapter.identity(child) == adapter.identity(v) for v in queue):
                _fail('Native sibling inventory is cyclic or exceeds its budget.')
            queue.append(child)
            child = binding.wrap(child.GetNext(), adapter._module.ITreeControlItem)
    if len(matches) != 1 or not _same(_inventory(adapter, model), current):
        _fail('No unique exact annotation-view feature binding survived observation.')
    receipt.owned.append((target, matches[0]))
    receipt.bound = True


def retire_rectangle_view(adapter, model, receipt, *, step):
    """Delete only the bound, now unused view, once, preserving all baseline views."""
    if not receipt.bound or receipt.retirement_attempted or len(receipt.owned) != 1:
        _fail('Only a fully bound, unused one-shot receipt authorizes retirement.')
    receipt.retirement_attempted = True
    current, created = _current_owned(adapter, model, receipt)
    owned, feature = receipt.owned[0]
    if not _same(created, (owned,)):
        _fail('An unrelated or changed view prevents retirement.')
    for dimension in adapter.dimensions(model, adapter.features(model)):
        for display in dimension.displays:
            annotation = binding.wrap(display.GetAnnotation(), adapter._module.IAnnotation)
            if annotation is None or annotation.AnnotationView is None:
                _fail('Remaining dimension view membership is incomplete.')
            if adapter.identity(annotation.AnnotationView) == owned.token:
                _fail('A remaining dimension still uses the owned view.')
    if feature.GetTypeName2() != 'AnnotationViewFeat':
        _fail('The retained feature changed type.')
    if step('restore_select_annotation_view', feature.Select2, False, 0) is not True:
        _fail('Exact owned view selection is unconfirmed.')
    if _selected_view(adapter, model) != owned.token:
        _fail('The retained feature selected another annotation view.')
    if not _same(_inventory(adapter, model), current):
        _fail('View data changed before the owned delete.')
    if step('restore_delete_annotation_view', adapter._extension(model).DeleteSelection2, 0) is not True:
        _fail('Annotation-view deletion acknowledgement is unconfirmed; no retry.')
    # Enumerate only current handles. Never call a getter on a retired proxy.
    if not _same(_inventory(adapter, model), receipt.baseline):
        _fail('Full baseline view inventory was not restored.')
    receipt.retired = True

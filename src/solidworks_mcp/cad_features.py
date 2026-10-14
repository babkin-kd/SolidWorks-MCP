"""Part feature metadata and revision notifications, called only on a pumping STA."""

import threading

import pythoncom

from . import binding
from .documents import rejected


class PartRevisionWatch:
    # Selection/view/highlight events do not invalidate a model revision. All
    # handlers ignore their arguments (which may be COM proxies) and return 0:
    # do not veto a native action, call COM, or retain callback arguments.
    EVENTS = frozenset({
        'OnAddItemNotify', 'OnRenameItemNotify', 'OnDeleteItemNotify', 'OnModifyNotify',
        'OnActiveConfigChangePostNotify', 'OnConfigurationChangeNotify',
        'OnSuppressionStateChangeNotify', 'OnDimensionChangeNotify', 'OnSketchSolveNotify',
        'OnAddCustomPropertyNotify', 'OnChangeCustomPropertyNotify', 'OnDeleteCustomPropertyNotify',
        'OnBodyVisibleChangeNotify', 'OnFeatureManagerTreeRebuildNotify',
        'OnRegenPostNotify', 'OnRegenPostNotify2', 'OnUndoPostNotify', 'OnRedoPostNotify',
        'OnFileSavePostNotify', 'OnFileReloadNotify', 'OnFileReloadPostNotify',
        'OnEquationEditorPostNotify', 'OnCloseDesignTableNotify', 'OnUnitsChangeNotify',
        'OnActiveDisplayStateChangePostNotify', 'OnVisualPropertiesChangeNotify',
        'OnWeldmentCutListUpdatePostNotify', 'OnDestroyNotify', 'OnDestroyNotify2',
    })

    def __init__(self, model, module):
        self.sequence = 0
        self.alive = True
        self.thread = threading.get_ident()
        self._sink = None
        base = module.DPartDocEvents
        registered = set(base._dispid_to_func_.values()) & self.EVENTS
        if not {'OnRenameItemNotify', 'OnDimensionChangeNotify', 'OnConfigurationChangeNotify'} <= registered:
            raise rejected('revision_monitor_unavailable', 'Registered CAD library lacks required part notifications.')
        self.events = sorted(registered)
        def handler(name):
            def notify(sink, *args):
                self.sequence += 1
                if name in ('OnDestroyNotify', 'OnDestroyNotify2'):
                    self.alive = False
                return 0
            return notify
        cls = type('PartRevisionSink', (base,), {name: handler(name) for name in registered})
        try:
            self._sink = cls(model)
        except Exception as exc:
            raise rejected('revision_monitor_unavailable', f'Could not attach native part notifications: {exc}') from exc

    def poll(self):
        if threading.get_ident() != self.thread:
            raise rejected('wrong_apartment', 'Revision notifications belong to the document STA.')
        if pythoncom.PumpWaitingMessages():
            self.alive = False
            raise rejected('revision_monitor_stopped', 'The document apartment received WM_QUIT.')
        if not self.alive or self._sink is None:
            raise rejected('revision_monitor_stopped', 'The native document revision monitor is no longer live.')
        return self.sequence

    def close(self):
        if threading.get_ident() != self.thread:
            raise rejected('wrong_apartment', 'Revision notifications must be released on their owning STA.')
        if self._sink is not None:
            sink, self._sink = self._sink, None
            try:
                sink.close()
            except pythoncom.com_error:
                # The source may already have been closed/disconnected; the
                # local proxy is still released here, on the owning apartment.
                pass
            finally:
                self.alive = False


class CadFeaturesMixin:
    def watch_part(self, model):
        return PartRevisionWatch(model, self._module)

    def features(self, model):
        """Complete bounded native feature traversal, including absorbed subfeatures.

        Native GetID is used ONLY for traversal duplicate detection. Client
        object IDs resolve through persistent references and native identity.
        """
        cls = self._module.IFeature
        queue = [(binding.wrap(model.FirstFeature(), cls), False)]
        seen, links, result = {}, set(), []
        while queue:
            feature, sub = queue.pop()
            if feature is None:
                continue
            native_id = int(feature.GetID())
            prior = seen.get(native_id)
            if prior is not None and self.identity(prior) != self.identity(feature):
                raise rejected('feature_identity_collision', 'Native feature IDs are not unique in this traversal.')
            link = (native_id, sub)
            if link in links:
                continue
            links.add(link)
            next_raw = feature.GetNextSubFeature() if sub else feature.GetNextFeature()
            queue.append((binding.wrap(next_raw, cls), sub))
            if prior is not None:
                continue
            if len(result) >= 5000:
                raise rejected('feature_budget_exceeded', 'Feature-tree revision budget is 5000; no partial revision is issued.')
            seen[native_id] = feature
            result.append(feature)
            queue.append((binding.wrap(feature.GetFirstSubFeature(), cls), True))
        return result

    def feature_summary(self, feature):
        error, warning = feature.GetErrorCode2()
        suppressed = feature.IsSuppressed2(1, None)
        if suppressed is None or len(suppressed) != 1:
            raise rejected('feature_read_failed', 'Native current-configuration suppression was not returned.')
        owner = binding.wrap(feature.GetOwnerFeature(), self._module.IFeature)
        return {'native_id': int(feature.GetID()), 'name': str(feature.Name),
                'feature_type': str(feature.GetTypeName2()), 'suppressed': bool(suppressed[0]),
                'owner_native_id': int(owner.GetID()) if owner is not None else None,
                'error_code': int(error), 'is_warning': bool(warning) if error else False}

    def feature_dependencies(self, features):
        """Capture native-reported links within an already collected feature tree.

        Called on the owning STA. Indexes identify rows in this one capture;
        public targets still require persistent references and a closing revision
        check. Parent/child disagreement is reported explicitly. This capture
        alone does not authorize deletion or claim a complete deletion impact.
        """
        if type(features) not in (list, tuple) or len(features) > 5000:
            raise rejected('feature_budget_exceeded', 'Dependency capture supports at most 5000 feature rows.')
        by_native_id = {}
        for index, feature in enumerate(features):
            identifier = feature.GetID()
            if type(identifier) is not int or identifier in by_native_id:
                raise rejected('feature_identity_collision', 'Dependency feature rows require unique native ID hints.')
            by_native_id[identifier] = index
        relations_read = 0

        def member_index(raw):
            nonlocal relations_read
            relations_read += 1
            if relations_read > 100000:
                raise rejected('feature_dependency_budget_exceeded', 'Dependency relation budget is 100000.')
            member = binding.wrap(raw, self._module.IFeature)
            if member is None:
                raise rejected('feature_dependency_read_failed', 'Native relation contains a null feature.')
            identifier = member.GetID()
            index = by_native_id.get(identifier) if type(identifier) is int else None
            if index is None:
                raise rejected('feature_dependency_outside_tree', 'Native dependency is outside the captured feature tree.')
            # Native GetID is a candidate hint. Every link must prove canonical
            # membership; matching names or integer IDs never suffice.
            if self.identity(member) != self.identity(features[index]):
                raise rejected('feature_identity_collision', 'Native dependency ID belongs to a different feature identity.')
            return index

        def collection(value):
            if value is None:
                return ()
            if type(value) not in (list, tuple) or len(value) > 5000:
                raise rejected('feature_dependency_read_failed', 'Expected a bounded native feature relation array.')
            return value

        parents, children, absorbed = set(), set(), set()
        for index, feature in enumerate(features):
            for raw in collection(feature.GetParents()):
                parents.add((member_index(raw), index))
            for raw in collection(feature.GetChildren()):
                children.add((index, member_index(raw)))
            owner = feature.GetOwnerFeature()
            if owner is not None:
                absorbed.add((member_index(owner), index))
        return {'scope': 'native_feature_relation_capture_v1', 'feature_count': len(features),
                'parent_links': [list(edge) for edge in sorted(parents)],
                'child_links': [list(edge) for edge in sorted(children)],
                'absorbed_links': [list(edge) for edge in sorted(absorbed)],
                'parent_links_without_child_confirmation': [list(edge) for edge in sorted(parents - children)],
                'child_links_without_parent_confirmation': [list(edge) for edge in sorted(children - parents)],
                'relations_read': relations_read}

    def rename_feature(self, feature, name):
        feature.Name = name
        return str(feature.Name)

"""Cleanup for a serialized neutral-file import, without title-only ownership.

The caller must hold CommandInProgress throughout its import. A snapshot delta
is used only within that exclusive automation interval, never as a background
sweeper. An ambiguous identity, changed document or failed close stops cleanup;
no close call is retried. This does not expose a public v2 import operation.
"""


class ImportDocumentCleanup:
    def __init__(self, application, documents, identity, owned_interval, child_documents=None):
        self.application = application
        self.documents = documents
        self.identity = identity
        self.owned_interval = owned_interval
        self.child_documents = child_documents or (lambda document: ())
        self.guarded = bool(application.CommandInProgress) and bool(owned_interval())
        self.before = self.snapshot()

    def snapshot(self):
        result = []
        for document in self.documents():
            token = self.identity(document)  # Retain canonical IUnknown; no pointer reuse.
            stamp = int(document.GetUpdateStamp())
            facts = {'title': str(document.GetTitle()), 'path': str(document.GetPathName()),
                     'type': int(document.GetType()), 'stamp': stamp,
                     'modified': bool(document.GetSaveFlag())}
            if int(document.GetUpdateStamp()) != stamp:
                raise RuntimeError('Import document changed during cleanup inventory.')
            if any(token == item[0] for item in result):
                raise RuntimeError('Ambiguous native document identity.')
            result.append((token, facts))
        return result

    @staticmethod
    def find(items, token):
        return next((facts for other, facts in items if token == other), None)

    def unchanged_originals(self, items):
        if any(self.find(items, token) != facts for token, facts in self.before):
            raise RuntimeError('A pre-existing document changed; import cleanup retained documents.')

    def parents_first(self, created):
        # Close outer assemblies before referenced subassemblies, not merely
        # all assemblies before parts. Canonical identities coalesce instances.
        children = [set() for _ in created]
        incoming = [0 for _ in created]
        for document in self.documents():
            token = self.identity(document)
            parent = next((i for i, (other, _) in enumerate(created) if token == other), None)
            if parent is None:
                continue
            for child in self.child_documents(document):
                child_token = self.identity(child)
                index = next((i for i, (other, _) in enumerate(created) if child_token == other), None)
                if index is None:
                    if self.find(self.before, child_token) is None:
                        raise RuntimeError('Import dependency is outside the captured document inventory.')
                    continue  # A reused pre-existing library component is never closed.
                if index not in children[parent]:
                    children[parent].add(index)
                    incoming[index] += 1
        ordered = []
        ready = [i for i, count in enumerate(incoming) if count == 0]
        while ready:
            ready.sort(key=lambda i: (created[i][1]['type'] != 2, i))
            parent = ready.pop(0)
            ordered.append(created[parent])
            for child in sorted(children[parent]):
                incoming[child] -= 1
                if incoming[child] == 0:
                    ready.append(child)
        if len(ordered) != len(created):
            raise RuntimeError('Cyclic import document dependencies; documents were retained.')
        return ordered

    def cleanup(self):
        if not self.guarded or not self.owned_interval() or not bool(self.application.CommandInProgress):
            raise RuntimeError('Import cleanup requires the original exclusive automation interval; '
                               'documents were retained for state reconciliation.')
        current = self.snapshot()
        self.unchanged_originals(current)
        created = [(token, facts) for token, facts in current if self.find(self.before, token) is None]
        created = self.parents_first(created)
        for token, facts in created:
            current = self.snapshot()
            self.unchanged_originals(current)
            actual = self.find(current, token)
            if actual is None:  # Closing its owning assembly may already have released this part.
                continue
            if actual != facts:
                raise RuntimeError('Imported document changed before close; documents were retained.')
            title = facts['title']
            if not title or sum(other['title'] == title for _, other in current) != 1:
                raise RuntimeError('Ambiguous document title; nothing with that title was closed.')
            if not self.owned_interval() or not bool(self.application.CommandInProgress):
                raise RuntimeError('Import automation interval ended before close; documents were retained.')
            self.application.CloseDoc(title)  # Native void; never save, never retry after an exception.
            after = self.snapshot()
            self.unchanged_originals(after)
            if self.find(after, token) is not None:
                raise RuntimeError('Import document close was not confirmed; reconcile state before retrying.')
        final = self.snapshot()
        self.unchanged_originals(final)
        if any(self.find(self.before, token) is None for token, _ in final):
            raise RuntimeError('Untracked new documents remain; reconcile state before another import.')

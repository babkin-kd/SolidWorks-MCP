"""Private native read counters; no CAD arguments/results or file paths recorded.

Counts explicit Python -> COM dispatches, not native internal RPC or C-slot
canonical comparisons. The full-tree counter measures adapter enumerations.
"""
import sys
import time

from solidworks_mcp.cad_documents import SolidWorksDocuments


class CountingDocuments(SolidWorksDocuments):
    def __init__(self):
        super().__init__()
        self.full_tree_enumerations = self.feature_metadata_reads = 0
    def features(self, model):
        self.full_tree_enumerations += 1
        return super().features(model)
    def feature_summary(self, feature):
        self.feature_metadata_reads += 1
        return super().feature_summary(feature)


class NativeReadMetrics:
    def __init__(self, adapter):
        self.adapter = adapter
        self.dispatches = self.interface_queries = 0
        self.data = None
    def _profile(self, frame, event, argument):
        if event != 'c_call':
            return
        owner = getattr(argument, '__self__', None)
        if type(owner).__name__ not in ('PyIDispatch', 'PyIUnknown'):
            return
        name = getattr(argument, '__name__', '')
        if name in ('InvokeTypes', 'Invoke'):
            self.dispatches += 1
        elif name == 'QueryInterface':
            self.interface_queries += 1
    def __enter__(self):
        if sys.getprofile() is not None:
            raise RuntimeError('Native read metrics require an unused thread profiling hook.')
        self.before = (self.adapter.full_tree_enumerations, self.adapter.feature_metadata_reads)
        self.started = time.perf_counter()
        sys.setprofile(self._profile)
        return self
    def __exit__(self, kind, error, traceback):
        try:
            sys.setprofile(None)
        except BaseException as cleanup_error:
            if error is None:
                raise
            error.add_note('Native metric profile restoration failed: ' + type(cleanup_error).__name__)
            return False
        self.data = {'full_tree_enumerations': self.adapter.full_tree_enumerations - self.before[0],
                     'feature_metadata_reads': self.adapter.feature_metadata_reads - self.before[1],
                     'python_com_api_dispatches': self.dispatches,
                     'explicit_query_interface_calls': self.interface_queries,
                     'native_internal_calls_measured': False,
                     'elapsed_seconds': time.perf_counter() - self.started,
                     'scope': 'single_catalog_read_excludes_fixture_setup_and_independent_oracles'}
        return False


def measure_read(adapter, operation, expected_tree_reads=2):
    with NativeReadMetrics(adapter) as measured:
        result = operation()
    assert measured.data['full_tree_enumerations'] == expected_tree_reads
    assert measured.data['python_com_api_dispatches'] > 0, 'Native dispatch profiling did not observe COM calls.'
    return result, measured.data

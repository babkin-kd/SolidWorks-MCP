"""Runtime routes durable sketch edits on its existing owning worker/catalog."""
import asyncio
from solidworks_mcp.runtime_v2 import Runtime
from test_sketch_dimensions_v2 import setup as sketch_setup


def test_runtime_routes_preparation_mutation_repeats_and_releases_catalog(sketch_setup):
    adapter,catalog,store,runner,doc,obj,ids=sketch_setup
    runtime=Runtime(store)
    runtime._runner=runner
    runtime._catalog=catalog.documents
    runtime._dimensions=catalog.dimensions
    runtime._connection_epoch='sketch-test'
    async def exercise():
        args=dict(document_id=doc,configuration='Основная',object_id=obj,dimension_id=ids[0],value_mm=45.)
        prepared=await runtime.read('prepare','sketch.prepare_dimension_change',args)
        assert prepared['status']=='succeeded',prepared
        args['expected_revision']=prepared['result']['revision']
        edited=await runtime.mutate('edit','sketch.set_dimension',args)
        assert edited['status']=='succeeded',edited
        assert edited['payload']['context']['dimension_id']==ids[0]
        assert await runtime.mutate('edit','sketch.set_dimension',args)==edited
        assert len(adapter.dimension_writes)==1
        fetched=await runtime.read('get','sketch.get',dict(document_id=doc,configuration='Основная',object_id=obj))
        assert fetched['status']=='succeeded'
    asyncio.run(exercise())
    runtime._release_catalog()
    assert runtime._sketches is None and runtime._dimensions is None

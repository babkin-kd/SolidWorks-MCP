"""Strict complete native feature relation/external inventories, without CAD."""


def feature_relations(data):
    value=data['dependencies']
    keys={'scope','feature_count','parent_links','child_links','absorbed_links',
          'parent_links_without_child_confirmation','child_links_without_parent_confirmation','relations_read'}
    rows=data['features']
    if (type(value) is not dict or set(value)!=keys or value['scope']!='native_feature_relation_capture_v1'
            or type(value['feature_count']) is not int or value['feature_count']!=len(rows)):
        raise ValueError('Incomplete dependency inventory')
    links={}
    for key in keys-{'scope','feature_count','relations_read'}:
        if type(value[key]) is not list:raise ValueError('Incomplete relation array')
        edges=[]
        for pair in value[key]:
            if (type(pair) is not list or len(pair)!=2
                    or any(type(i) is not int or not 0<=i<len(rows) for i in pair)):
                raise ValueError('Invalid relation membership')
            edges.append(tuple(rows[i]['native_id'] for i in pair))
        if len(edges)!=len(set(edges)):raise ValueError('Duplicate relations')
        links[key]=set(edges)
    if (links['parent_links_without_child_confirmation']!=links['parent_links']-links['child_links']
            or links['child_links_without_parent_confirmation']!=links['child_links']-links['parent_links']
            or type(value['relations_read']) is not int
            or value['relations_read']!=sum(len(links[k]) for k in ('parent_links','child_links','absorbed_links'))):
        raise ValueError('Unconfirmed native relation inventory')
    return links


def empty_feature_external_inventory(data):
    value=data['feature_external_reference_inventory']
    if (type(value) is not dict or set(value)!={'scope','feature_count','total_reference_rows','features'}
            or value['scope']!='native_feature_external_references_v1'
            or type(value['feature_count']) is not int or value['feature_count']!=len(data['features'])
            or type(value['total_reference_rows']) is not int or value['total_reference_rows']!=0
            or type(value['features']) is not list or len(value['features'])!=len(data['features'])):
        raise ValueError('Incomplete native external reference inventory')
    for row,feature in zip(value['features'],data['features']):
        if (type(row) is not dict or set(row)!={'native_id','count','rows'}
                or type(row['native_id']) is not int or row['native_id']!=feature['native_id']
                or type(row['count']) is not int or row['count']!=0
                or type(row['rows']) is not list or row['rows']!=[]):
            raise ValueError('Every current feature requires its complete empty external inventory')
    return value

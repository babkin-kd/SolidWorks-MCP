"""Finite display delta admission; requires independently captured native bindings.

No CAD getters or write permission. A matching scalar view row alone cannot
establish that a new annotation view belongs to the created sketch dimensions.
"""
import math
import re


def validated_view_bindings(display,evidence,expected_axes):
    fields={'always_2d','angle','annotation_count','flat_pattern','rotation','shown','unassigned'}
    if (type(display) is not dict or set(display)!= {'lights','annotation_views'}
            or type(display['lights']) is not list or type(display['annotation_views']) is not list
            or not 1<=len(display['annotation_views'])<=16 or type(evidence) is not dict
            or set(evidence)!= {'scope','view_ids','dimension_views'}
            or evidence['scope']!='native_rectangle_annotation_view_bindings_v1'
            or type(evidence['view_ids']) is not list or len(evidence['view_ids'])!=len(display['annotation_views'])
            or any(type(v) is not str or re.fullmatch(r'av_[0-9a-f]{32}',v) is None for v in evidence['view_ids'])
            or len(set(evidence['view_ids']))!=len(evidence['view_ids'])
            or type(evidence['dimension_views']) is not dict or set(evidence['dimension_views'])!=expected_axes
            or any(type(v) is not str or v not in evidence['view_ids'] for v in evidence['dimension_views'].values())):
        raise ValueError('Complete independently captured annotation-view bindings required.')
    for row in display['annotation_views']:
        if (type(row) is not dict or set(row)!=fields
                or any(type(row[k]) is not bool for k in ('always_2d','flat_pattern','shown','unassigned'))
                or type(row['annotation_count']) is not int or row['annotation_count']!=0
                or type(row['angle']) is not str or not math.isfinite(float.fromhex(row['angle']))
                or type(row['rotation']) is not list or len(row['rotation'])!=9
                or any(type(v) is not str or not math.isfinite(float.fromhex(v)) for v in row['rotation'])):
            raise ValueError('A complete empty native annotation view is required.')
    return evidence


def verified_new_sketch_view(before,after,before_evidence,after_evidence):
    return verified_new_dimension_view(before,after,before_evidence,after_evidence,created_axes={'width','height'})


def verified_new_dimension_view(before,after,before_evidence,after_evidence,*,created_axes):
    try:
        if (type(before) is not dict or type(after) is not dict
                or set(before)!= {'lights','annotation_views'} or set(after)!=set(before)
                or before['lights']!=after['lights']):return False
        fields={'always_2d','angle','annotation_count','flat_pattern','rotation','shown','unassigned'}
        def read(data,evidence):
            rows=data['annotation_views']
            if (type(rows) is not list or not 1<=len(rows)<=16
                    or type(evidence) is not dict or set(evidence)!= {'scope','view_ids','dimension_views'}
                    or evidence['scope']!='native_rectangle_annotation_view_bindings_v1'
                    or type(evidence['view_ids']) is not list or len(evidence['view_ids'])!=len(rows)
                    or any(type(v) is not str or not v.startswith('av_') or len(v)!=35 for v in evidence['view_ids'])
                    or len(set(evidence['view_ids']))!=len(rows)
                    or type(evidence['dimension_views']) is not dict):raise ValueError('Incomplete native bindings')
            for row in rows:
                if (type(row) is not dict or set(row)!=fields
                        or any(type(row[k]) is not bool for k in ('always_2d','flat_pattern','shown','unassigned'))
                        or type(row['annotation_count']) is not int or row['annotation_count']!=0
                        or type(row['angle']) is not str or not math.isfinite(float.fromhex(row['angle']))
                        or type(row['rotation']) is not list or len(row['rotation'])!=9
                        or any(type(x) is not str or not math.isfinite(float.fromhex(x)) for x in row['rotation'])):
                    raise ValueError('Complete supported native view required')
            return dict(zip(evidence['view_ids'],rows))
        old,new=read(before,before_evidence),read(after,after_evidence)
        original_axes=set(before_evidence['dimension_views'])
        validated_view_bindings(before,before_evidence,original_axes)
        validated_view_bindings(after,after_evidence,original_axes|created_axes)
        if (created_axes not in ({'width','height'},{'depth'})
                or original_axes!=(set() if created_axes=={'width','height'} else {'width','height'})
                or set(after_evidence['dimension_views'])!=original_axes|created_axes
                or len(new)!=len(old)+1 or not set(old)<set(new)
                or any(new[key]!=row for key,row in old.items())
                or any(after_evidence['dimension_views'][axis]!=before_evidence['dimension_views'][axis] for axis in original_axes)):return False
        created=(set(new)-set(old)).pop()
        if {after_evidence['dimension_views'][axis] for axis in created_axes}!={created}:return False
        row=new[created]
        return (row['always_2d'] is False and row['flat_pattern'] is False and row['unassigned'] is False
                and row['shown'] is False and float.fromhex(row['angle'])==0.)
    except Exception:return False

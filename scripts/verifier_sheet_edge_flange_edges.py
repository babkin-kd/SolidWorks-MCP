"""Read-only candidate filtering; domain still proves actual edge ownership."""

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.sheet_edge_flange_definition import l_flange_edge_points


def flange_edge_candidate(row,source,frame):
    if row['curve_type']!='line':return False
    points=tuple(tuple(v/1000. for v in row[k]) for k in ('start_mm','end_mm'))
    try:l_flange_edge_points(points,source,frame)
    except ExecutionFailure as exc:
        if exc.code=='sheet_flange_edge_unsupported':return False
        raise
    return True

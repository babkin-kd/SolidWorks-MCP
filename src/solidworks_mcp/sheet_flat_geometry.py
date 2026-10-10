"""Intended L-sheet flat material boundary; no CAD call or state change.

The fixed leg must come from independent native FlatPattern fixed-face proof.
Trying both boxes after a write is not a substitute for that proof. This helper
is not a published flatten operation or evidence of native/wheel acceptance.
"""

import math

from .cad_planar_brep import PLANAR_BREP_SCOPE
from .documents import rejected
from .part_creation import validated_plane_transform


TOLERANCE_M=1e-12


def fixed_l_leg_from_face(face,definition,plane_transform,*,flattened=False):
    """Identify the independently bound native fixed face, before changing state.

    Native adapter must round-trip the PID and bind this exact face to the
    explicit current body. Four corners, plane position and outward normal must
    match one entire straight folded face or one entire merged flat face.
    """
    try:
        frame=validated_plane_transform(plane_transform)
        if (type(flattened) is not bool or face['is_plane'] is not True
                or face['owner_body_is_current'] is not True or not face['pid_hex']
                or type(face['normal_opposes_surface']) is not bool):raise ValueError()
        points=face['vertices'];p=face['plane_parameters']
        if len(points)!=4 or len(p)!=6 or any(len(v)!=3 for v in points):raise ValueError()
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (*p,*(v for point in points for v in point))):raise ValueError()
        close=lambda a,b:len(a)==len(b) and all(abs(x-y)<=TOLERANCE_M for x,y in zip(a,b))
        normal=tuple(-v if face['normal_opposes_surface'] else v for v in p[:3])
        w,h,t,r,length=(v/1000. for v in (definition.leg_x_mm,definition.leg_y_mm,definition.thickness_mm,definition.bend_radius_mm,definition.length_mm))
        developed=definition.developed_length_mm/1000.;candidates=[]
        for leg in ('x','y'):
            varying=0 if leg=='x' else 1;constant=1-varying
            low=(w-developed if leg=='x' else h-developed) if flattened else r+t
            high=w if leg=='x' else h
            for side in (0,1):
                wanted=[]
                for end in (low,high):
                    for z in (0.,length):
                        local=[0.,0.,z];local[varying]=end;local[constant]=side*t
                        wanted.append(tuple(math.fsum(local[j]*frame[3*j+i] for j in range(3)) for i in range(3)))
                outward=tuple((1. if side else -1.)*v for v in frame[3*constant:3*constant+3])
                offset=math.fsum(p[3+i]*frame[3*constant+i] for i in range(3))
                remaining=list(points)
                for point in wanted:
                    match=next((i for i,v in enumerate(remaining) if close(point,v)),None)
                    if match is None:break
                    remaining.pop(match)
                if not remaining and close(normal,outward) and abs(offset-side*t)<=TOLERANCE_M:candidates.append(leg)
        if len(candidates)!=1:raise ValueError()
        return candidates[0]
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):
        raise rejected('sheet_fixed_face_unsupported','The complete native fixed face does not bind one exact supported L-sheet leg.') from None


def expected_flat_l_geometry(definition,plane_transform,fixed_leg):
    frame=validated_plane_transform(plane_transform)
    if fixed_leg not in ('x','y'):
        raise rejected('sheet_fixed_face_unsupported','The native fixed face must bind the exact straight X or Y leg.')
    d,t,length=(v/1000. for v in (definition.developed_length_mm,definition.thickness_mm,definition.length_mm))
    w,h=definition.leg_x_mm/1000.,definition.leg_y_mm/1000.
    bounds=((w-d,w),(0.,t),(0.,length)) if fixed_leg=='x' else ((0.,t),(h-d,h),(0.,length))
    points=[tuple(math.fsum((x*frame[i],y*frame[3+i],z*frame[6+i])) for i in range(3))
        for x in bounds[0] for y in bounds[1] for z in bounds[2]]
    pairs=sorted({tuple(sorted((i,i^bit))) for i in range(8) for bit in (1,2,4)})
    faces=[]
    for axis in range(3):
        bit=(4,2,1)[axis]
        for end in (0,1):
            faces.append(dict(vertices=[i for i in range(8) if bool(i&bit)==bool(end)],
                normal=[(1. if end else -1.)*v for v in frame[3*axis:3*axis+3]],
                axis=axis,offset_m=bounds[axis][end]))
    return dict(fixed_leg=fixed_leg,plane_transform=list(frame),bounds_m=[list(p) for p in bounds],
        vertices_si=[[float(v).hex() for v in p] for p in points],edge_pairs=[list(p) for p in pairs],faces=faces,
        developed_length_mm=definition.developed_length_mm,
        volume_mm3=d*t*length*1e9,surface_area_mm2=2.*math.fsum((d*t,d*length,t*length))*1e6)


def flat_l_body_matches(geometry,expected):
    """Match all native vertices, edges and oriented face cycles of the flat box.

Input must be the complete planar reader output, which independently verifies
finite trims, incidence, partner coedges, manifold links and native close stamps.
"""
    try:
        if len(geometry['bodies'])!=1:return False
        body=geometry['bodies'][0]
        if body['scope']!=PLANAR_BREP_SCOPE or tuple(len(body[k]) for k in ('vertices','edges','faces'))!=(8,12,6):return False
        decode=lambda raw:tuple(float.fromhex(v) for v in raw)
        close=lambda a,b:len(a)==len(b) and all(math.isfinite(x) and abs(x-y)<=TOLERANCE_M for x,y in zip(a,b))
        dot=lambda a,b:math.fsum(x*y for x,y in zip(a,b))
        wanted=[decode(p) for p in expected['vertices_si']];mapping={}
        for index,raw in enumerate(body['vertices']):
            matches=[i for i,p in enumerate(wanted) if close(decode(raw),p)]
            if len(matches)!=1 or matches[0] in mapping.values():return False
            mapping[index]=matches[0]
        pairs=[frozenset((mapping[e['start']],mapping[e['end']])) for e in body['edges']]
        if len(set(pairs))!=12 or set(pairs)!={frozenset(p) for p in expected['edge_pairs']}:return False
        remaining={frozenset(f['vertices']):f for f in expected['faces']}
        frame=validated_plane_transform(expected['plane_transform'])
        for face in body['faces']:
            if face.get('surface_type','plane')!='plane' or len(face['loops'])!=1:return False
            loop=face['loops'][0]
            if loop['outer'] is not True or len(loop['coedges'])!=4:return False
            uses=loop['coedges'];found=remaining.pop(frozenset(mapping[u['start']] for u in uses),None)
            if found is None:return False
            if any(pairs[u['edge']]!=frozenset((mapping[u['start']],mapping[u['end']])) for u in uses):return False
            if any(u['end']!=uses[(i+1)%4]['start'] for i,u in enumerate(uses)):return False
            p=decode(face['plane_parameters']);normal=tuple(-v if face['normal_opposes_surface'] else v for v in p[:3])
            axis=frame[3*found['axis']:3*found['axis']+3]
            if not close(normal,found['normal']) or abs(dot(p[3:6],axis)-found['offset_m'])>TOLERANCE_M:return False
        return not remaining
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):return False

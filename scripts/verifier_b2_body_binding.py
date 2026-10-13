"""Current body binding after acknowledged setup; no mutation or acceptance.

Explicit native equality path: same original PID, strict IsSame=1, current
PID/canonical roundtrip and all six faces of the original owning extrusion.
Shape/name never creates ownership. Failure has no fallback or retry.
"""
from dataclasses import dataclass
from verifier_b2_impact_fixture import require


@dataclass(frozen=True)
class NativeBodyBridge:
    query:object
    is_same:object


def bind_current_body(*,original_body,original_canonical,original_pid,owner_feature,
                      owner_canonical,identity,persistent_id,resolve_body,census,bridge):
    require(type(bridge) is NativeBodyBridge and callable(bridge.query) and callable(bridge.is_same)
        and all(callable(value) for value in (identity,persistent_id,resolve_body,census)),
        'Explicit native body equality callbacks required.')
    require(type(original_pid) is bytes and bool(original_pid) and original_body is not None
        and owner_feature is not None,'Original retained body/PID/feature required.')
    require(identity(original_body)==original_canonical and identity(owner_feature)==owner_canonical,
        'Original retained handles changed before native body binding.')
    current=None;canonical=None
    for boundary in range(2):
        bodies=census()
        require(type(bodies) in (list,tuple) and len(bodies)==1 and bodies[0] is not None,
            'Exactly one current body required.')
        body=bodies[0];token=identity(body)
        if boundary==0:current,canonical=body,token
        require(token==canonical,'Current body canonical changed inside binding.')
        queried=bridge.query(body,'IBody2')
        require(queried is not None and identity(queried)==canonical,
            'Current IBody2 query changed its own canonical.')
        pid=persistent_id(body)
        require(type(pid) is bytes and bool(pid) and pid==original_pid,
            'Current body must retain exact original nonempty bytes PID.')
        resolved=resolve_body(pid)
        require(resolved is not None and identity(resolved)==canonical,
            'Original PID must resolve to the exact current body.')
        same=bridge.is_same(original_body,body)
        require(type(same) is int and same==1,'Native body equality requires exact int1.')
        require(identity(owner_feature)==owner_canonical,'Original owning feature changed.')
        faces=owner_feature.GetFaces()
        require(type(faces) in (list,tuple) and len(faces)==6,'All six original extrusion faces required.')
        face_tokens=[]
        for raw in faces:
            raw_token=identity(raw)
            face=bridge.query(raw,'IFace2')
            require(face is not None,'Current original feature face query required.')
            face_token=identity(face)
            require(face_token==raw_token,'Face query changed the original returned canonical.')
            require(not any(face_token==previous for previous in face_tokens),'Duplicate owner face not allowed.')
            face_tokens.append(face_token)
            raw_owned=face.GetBody()
            require(raw_owned is not None,'Original feature face returned no body.')
            raw_owned_token=identity(raw_owned)
            owned=bridge.query(raw_owned,'IBody2')
            require(owned is not None and identity(owned)==raw_owned_token==canonical,
                'Every original feature face must belong to the exact current body.')
        # Recheck after every native callback, including the last face GetBody.
        require(identity(original_body)==original_canonical and identity(owner_feature)==owner_canonical,
            'Original body/feature handles changed inside native binding.')
        closing=census()
        require(type(closing) in (list,tuple) and len(closing)==1 and identity(closing[0])==canonical,
            'Current body census changed during owner verification.')
        ending=persistent_id(closing[0])
        require(type(ending) is bytes and ending==original_pid and identity(resolve_body(ending))==canonical,
            'Current body PID/canonical changed after owner verification.')
    # Cover effects inside the final resolver callback. The caller additionally
    # brackets this whole producer with its native metadata/event envelope.
    require(identity(original_body)==original_canonical and identity(owner_feature)==owner_canonical,
        'Original handles changed inside final PID resolution.')
    final=census()
    require(type(final) in (list,tuple) and len(final)==1 and identity(final[0])==canonical,
        'Body census changed inside final PID resolution.')
    final_pid=persistent_id(final[0])
    require(type(final_pid) is bytes and final_pid==original_pid,
        'Body PID changed inside final resolution.')
    return current

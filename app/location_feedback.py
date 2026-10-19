"""Geometry readiness for setup and recommendation UI; no combat rules."""
import math

def location_ready(packet, minimum_revision):
    """Geometry readiness only; this never certifies combat values or a template ID."""
    if type(packet) is not dict or packet.get('kind')!='facts':return False
    revision=packet.get('revision')
    if type(revision) is not int or revision<minimum_revision:return False
    geometry=packet.get('geometry',{})
    if type(geometry) is not dict or geometry.get('Variant')!='D_VISIBLE':return False
    values=[geometry.get(k) for k in ('Scale','Left','Top')]
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):return False
    # Cached geometry alone cannot certify a frame whose layout markers failed.
    facts=packet.get('facts',())
    if type(facts) not in (list,tuple):return False
    for fact in facts:
        if type(fact) is not dict:return False
        reason=str(fact.get('reason',''))
        if 'MARKER_MISMATCH' in reason or 'COLUMN_DIVIDER_MISMATCH' in reason:return False
    scale,left,top=values
    return 1.3<=scale<=1.46 and left>=0 and top>=0


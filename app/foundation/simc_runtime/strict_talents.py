"""隔离研究工具。从固定 SimC 数据重建节点；不改游戏、旧解码器或主线。"""
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
COMMIT = '3dcabb94dd32f786786c67541dfd10db9f39e43b'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def nodes_from_source():
    rows = []
    source = ROOT / 'sources/trait_data.inc'
    for lineno, line in enumerate(source.read_text(encoding='utf-8').splitlines(), 1):
        m = re.match(r'\s*\{\s*([^"{}]+),\s*"([^"]+)",\s*\{([^}]+)\},\s*\{([^}]+)\},\s*(\d+),\s*(\d+)\s*\},', line)
        if not m:
            continue
        nums = [int(x.strip()) for x in m[1].split(',')]
        if len(nums) != 13:
            raise ValueError('source format changed')
        tree, cls, entry, node, ranks, points, definition, spell, replace, override, row, col, selection = nums
        if cls != 5:
            continue
        rows.append(dict(tree=tree, entry=entry, node=node, ranks=ranks, spell=spell,
                         selection=selection, name=m[2], specs=[int(x) for x in m[3].split(',')],
                         grants=[int(x) for x in m[4].split(',')], sub=int(m[5]), type=int(m[6]), line=lineno))
    nodes = {}
    for row in rows:  # generated data already ordered by selection index, per trait_data.cpp
        nodes.setdefault(row['node'], []).append(row)
    nodes = dict(sorted(nodes.items()))
    for entries in nodes.values():
        assert [e['selection'] for e in entries] == sorted(e['selection'] for e in entries)
    return nodes

class Reader:
    def __init__(self, text):
        if not text or any(c not in B64 for c in text):
            raise ValueError('empty or invalid alphabet')
        self.bits = [(B64.index(c) >> i) & 1 for c in text for i in range(6)]
        self.pos = 0
    def get(self, count):
        if self.pos + count > len(self.bits):
            raise ValueError('truncated input')
        val = sum(self.bits[self.pos+i] << i for i in range(count))
        self.pos += count
        return val

def decode(text, nodes, expected_hash=None):
    r = Reader(text)
    version, spec = r.get(8), r.get(16)
    tree_hash = bytes(r.get(8) for _ in range(16)).hex()
    if version != 2 or spec != 258:
        raise ValueError('version or specialization mismatch')
    if expected_hash is not None and tree_hash != expected_hash:
        raise ValueError('profile tree hash changed; requires new source validation')
    picked, spans = [], {}
    for node, entries in nodes.items():
        if not r.get(1):
            continue
        e = entries[0]
        ntype = e['type']
        maximum = sum(x['ranks'] for x in entries) if ntype == 1 else e['ranks']
        purchased = r.get(1)
        rank, choice = (maximum if purchased else 1), None
        if purchased:
            if r.get(1):
                span = r.pos
                rank = r.get(6)
                spans[(node,'rank')] = (span,6)
                if not 0 < rank < maximum:
                    raise ValueError('invalid partial rank')
            span = r.pos
            choice_flag = r.get(1)
            spans[(node,'choice_flag')] = (span,1)
            if choice_flag:
                if ntype not in (2,3):
                    raise ValueError('choice bits on non-choice node')
                span = r.pos
                choice = r.get(2)
                spans[(node,'choice')] = (span,2)
                if choice >= len(entries):
                    raise ValueError('choice index out of bounds')
                e = entries[choice]
            elif ntype in (2,3):
                raise ValueError('missing choice bits')
        if any(e['specs']) and spec not in e['specs']:
            raise ValueError('node unavailable to specialization')
        if not purchased and spec not in e['grants']:
            raise ValueError('unearned granted node')
        allocations = []
        if ntype == 1:
            remaining = rank
            for tier in entries:
                allocated = min(remaining,tier['ranks'])
                if allocated:
                    allocations.append(dict(entry=tier['entry'],spell=tier['spell'],rank=allocated))
                remaining -= allocated
            if remaining:
                raise ValueError('tier allocation overflow')
        else:
            allocations.append(dict(entry=e['entry'],spell=e['spell'],rank=rank))
        picked.append(dict(e, rank=rank, rank_definition='total node rank',
                           allocations=allocations,purchased=bool(purchased),choice=choice))
    if len(r.bits) - r.pos > 5 or any(r.bits[r.pos:]):
        raise ValueError('extra data or nonzero padding')
    active = {p['sub'] for p in picked if p['tree'] == 4}
    if len(active) != 1:
        raise ValueError('ambiguous hero selection')
    for p in picked:
        p['effective_in_profile'] = p['tree'] != 3 or p['sub'] in active
        if p['tree'] == 3 and p['purchased'] and not p['effective_in_profile']:
            raise ValueError('purchased talents from another hero tree')
    return dict(version=version, spec=spec, tree_hash=tree_hash, bits_used=r.pos,
                bits_total=len(r.bits), purchased_points=sum(p['rank'] for p in picked if p['purchased']),
                purchased_rank_sum_definition='Includes hero selector node; not a game talent budget proof',
                purchased_rank_by_tree={str(t):sum(p['rank'] for p in picked if p['purchased'] and p['tree']==t) for t in range(1,5)},
                hero_subtree=next(iter(active))), picked, spans


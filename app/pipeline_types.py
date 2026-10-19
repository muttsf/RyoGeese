"""Immutable messages shared by capture, decision, logging and presentation."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Stamp:
    session: str
    clock: str
    revision: int
    generation: int
    sequence: int
    ordinal: int
    received_ns: int
    native_ns: int
    recognized_ns: int
    admitted_ns: int
    round_started_ns: int = 0

@dataclass(frozen=True)
class Work:
    stamp: Stamp
    profile_identity: str
    profile_version: int
    control_version: int
    fence: int
    job: int
    mode: str
    observation_json: str

@dataclass(frozen=True)
class Outcome:
    work: Work
    skill: object
    reason: str
    applied_mode: str
    details_json: str = '{}'

@dataclass(frozen=True)
class View:
    skill: object
    skill_name: object
    key: object
    reason: str
    requested_mode: str
    applied_mode: object
    pending_control: bool
    stopped: bool
    details_json: object = None

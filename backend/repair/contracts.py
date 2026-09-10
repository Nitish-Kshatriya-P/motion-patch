from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

class RepairStatus(str, Enum):
    PASSED = "PASSED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"

@dataclass(frozen=True)
class TokenReplacement:
    frame_index: int
    channel_index: int
    original_start: int
    original_end: int
    output_start: int
    output_end: int
    original_token: bytes
    output_token: bytes

@dataclass
class WriteSetDeclaration:
    operator_id: str
    target_frames: List[int]
    joint_name: str
    channel_name: str
    channel_index: int
    max_permitted_change: float
    blend_frames: int
    derivation_reason: str

@dataclass
class CandidateParameters:
    candidate_id: str
    priority_index: int
    filter_strength: float = 1.0
    blend_frames: int = 3
    hermite_tangent_scale: float = 1.0
    smoothing_window: int = 5
    cutoff_freq: float = 10.0
    method: str = "slerp"

@dataclass
class CandidateScoreBreakdown:
    target_error_reduction: float
    weighted_channel_displacement: float
    boundary_jerk_penalty: float
    foot_contact_penalty: float
    root_path_penalty: float
    total_score: float

@dataclass
class RepairResult:
    status: RepairStatus
    reason_code: Optional[str] = None
    staging_path: Optional[str] = None
    original_asset_id: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    applied_operator_ids: List[str] = field(default_factory=list)
    declared_write_sets: List[WriteSetDeclaration] = field(default_factory=list)

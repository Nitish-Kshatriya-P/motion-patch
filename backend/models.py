import json
import hashlib
from enum import Enum
from typing import Optional, List, Dict, Any, Union, Tuple
from pydantic import BaseModel, Field


class LifecycleState(str, Enum):
    UPLOADING = "UPLOADING"
    ANALYZING = "ANALYZING"
    REVIEWING_FINDINGS = "REVIEWING_FINDINGS"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REPAIRING = "REPAIRING"
    VALIDATING = "VALIDATING"
    PREVIEWING = "PREVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class UpAxis(str, Enum):
    Y = "Y"
    Z = "Z"
    UNKNOWN = "UNKNOWN"


class AnalysisStatus(str, Enum):
    CLEAN = "CLEAN"
    FINDINGS = "FINDINGS"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED = "FAILED"


class AssessmentVerdict(str, Enum):
    LIKELY_VISIBLE_DEFECT = "Likely visible defect"
    REVIEW = "Review"
    NUMERICAL_ONLY = "Numerical-only"
    INCONCLUSIVE = "Inconclusive"


class AnomalyType(str, Enum):
    PLANTED_FOOT_SLIDING = "PLANTED_FOOT_SLIDING"
    ROTATION_JITTER = "ROTATION_JITTER"
    TRANSLATION_JITTER = "TRANSLATION_JITTER"
    ROOT_DISCONTINUITY = "ROOT_DISCONTINUITY"
    OPTICAL_OCCLUSION_FLATLINE = "OPTICAL_OCCLUSION_FLATLINE"
    OPTICAL_MARKER_SWAP = "OPTICAL_MARKER_SWAP"
    EULER_GIMBAL_LOCK_FLIP = "EULER_GIMBAL_LOCK_FLIP"
    ROM_HYPEREXTENSION = "ROM_HYPEREXTENSION"
    JOINT_DISLOCATION = "JOINT_DISLOCATION"
    BONE_LENGTH_VIOLATION = "BONE_LENGTH_VIOLATION"
    GROUND_PENETRATION = "GROUND_PENETRATION"
    GROUND_HOVERING = "GROUND_HOVERING"
    LIMB_SELF_COLLISION = "LIMB_SELF_COLLISION"
    DYNAMIC_ZMP_VIOLATION = "DYNAMIC_ZMP_VIOLATION"
    BALLISTIC_GRAVITY_VIOLATION = "BALLISTIC_GRAVITY_VIOLATION"
    LONG_TERM_DRIFT = "LONG_TERM_DRIFT"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BodyPart(str, Enum):
    PELVIS = "pelvis"
    SPINE = "spine"
    TORSO = "torso"
    ARM = "arm"
    LEG = "leg"
    FOOT = "foot"
    HEAD = "head"
    GENERAL = "general"
    UNKNOWN = "unknown"


class Status(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    GENERATING_SCRIPT = "GENERATING_SCRIPT"
    RUNNING_JOB = "RUNNING_JOB"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InstructionPayload(BaseModel):
    prompt: Optional[str] = ""
    audio_data: Optional[bytes] = None
    audio_mime: Optional[str] = None


class BatchFile(BaseModel):
    id: str
    original_name: str
    path: str
    status: Status = Status.PENDING
    output_path: Optional[str] = None

    def transition_to(self, new_status: Status, output_path: Optional[str] = None):
        self.status = new_status
        if output_path:
            self.output_path = output_path


class BatchJob(BaseModel):
    batch_id: str
    status: Status = Status.PROCESSING
    files: List[BatchFile] = []


class ExecutionParams(BaseModel):
    input_bvh_path: str
    script_code: str
    upload_dir: str
    temp_output_id: str


class BVHMetadata(BaseModel):
    parser_version: str = "1.0.0"
    skeleton_signature: str
    root_name: str
    joints: List[str]
    channel_order: Dict[str, List[str]]
    total_channels: int
    frame_count: int
    frame_time: float
    duration_seconds: float
    skeleton_scale: float


class Evidence(BaseModel):
    """
    Structured mathematical and kinematic evidence supporting a finding.

    Frame Conventions:
    - peak_frame: 0-indexed internal frame index of metric peak excursion.
    - display_peak_frame: 1-indexed display frame index of metric peak (= peak_frame + 1).
    - playback_frame_start / end: 0-indexed internal playback context window with lead-in and lead-out padding.
    - display_playback_frame_start / end: 1-indexed display playback context window.
    """
    model_config = {"extra": "allow"}

    metric_name: str = Field(default="defect_metric", description="Name of the quantified kinematic metric")
    measured_value: Optional[float] = Field(default=None, description="Quantified peak or excursion value")
    threshold: Optional[float] = Field(default=None, description="Numerical detection threshold")
    unit: Optional[str] = Field(default=None, description="Physical or mathematical unit of measurement")
    peak_frame: Optional[int] = Field(default=None, description="0-indexed internal frame index where the metric peaked")
    display_peak_frame: Optional[int] = Field(default=None, description="1-indexed display frame index where the metric peaked")
    context_padding_frames: int = Field(default=15, description="Playback context padding frames")
    playback_frame_start: Optional[int] = Field(default=None, description="0-indexed internal playback start frame")
    playback_frame_end: Optional[int] = Field(default=None, description="0-indexed internal playback end frame")
    display_playback_frame_start: Optional[int] = Field(default=None, description="1-indexed display playback start frame")
    display_playback_frame_end: Optional[int] = Field(default=None, description="1-indexed display playback end frame")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional detector-specific metric details")

    def model_post_init(self, __context: Any) -> None:
        if self.peak_frame is not None and self.display_peak_frame is None:
            self.display_peak_frame = self.peak_frame + 1
        if self.peak_frame is not None:
            if self.playback_frame_start is None:
                self.playback_frame_start = max(0, self.peak_frame - self.context_padding_frames)
            if self.playback_frame_end is None:
                self.playback_frame_end = self.peak_frame + self.context_padding_frames
            if self.display_playback_frame_start is None:
                self.display_playback_frame_start = self.playback_frame_start + 1
            if self.display_playback_frame_end is None:
                self.display_playback_frame_end = self.playback_frame_end + 1

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            val = getattr(self, key)
            if val is not None:
                return val
        if self.__pydantic_extra__ and key in self.__pydantic_extra__:
            return self.__pydantic_extra__[key]
        if key in self.details:
            return self.details[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self.__class__.model_fields:
            setattr(self, key, value)
        else:
            if self.__pydantic_extra__ is None:
                self.__pydantic_extra__ = {}
            self.__pydantic_extra__[key] = value

    def __contains__(self, key: str) -> bool:
        if hasattr(self, key) and getattr(self, key) is not None:
            return True
        if self.__pydantic_extra__ and key in self.__pydantic_extra__:
            return True
        if key in self.details:
            return True
        return False

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> List[str]:
        k = [field for field in self.__class__.model_fields.keys() if getattr(self, field) is not None]
        if self.__pydantic_extra__:
            for ek in self.__pydantic_extra__.keys():
                if ek not in k:
                    k.append(ek)
        for dk in self.details.keys():
            if dk not in k:
                k.append(dk)
        return k

    def values(self) -> List[Any]:
        return [self[k] for k in self.keys()]

    def items(self) -> List[Tuple[str, Any]]:
        return [(k, self[k]) for k in self.keys()]

    def to_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        if self.__pydantic_extra__:
            data.update(self.__pydantic_extra__)
        return data


class CoverageStatus(str, Enum):
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    NOT_COVERED = "NOT_COVERED"
    SKIPPED = "SKIPPED"
    UNSUPPORTED = "UNSUPPORTED"


class CoveragePrerequisites(BaseModel):
    """
    Prerequisites required to achieve analysis coverage on a motion check.

    Decouples whether a check can be evaluated from whether findings were discovered.
    Prerequisites:
    - scale: Positive, finite skeleton rest-pose height or scale is available.
    - up_axis: Spatial coordinate orientation (Y or Z) is unambiguously resolved.
    - joint_presence: Required kinematic joints exist in hierarchy (e.g. feet for footskate).
    - frame_count: Sufficient motion frame count is available for numerical differentiation.
    - channels: Required positional or rotational Euler channels exist on the target joints.
    """
    scale: bool = Field(default=True, description="Whether skeleton scale prerequisite was satisfied")
    up_axis: bool = Field(default=True, description="Whether up-axis prerequisite was satisfied")
    joint_presence: bool = Field(default=True, description="Whether requisite joint presence was satisfied")
    frame_count: bool = Field(default=True, description="Whether frame count prerequisite was satisfied")
    channels: bool = Field(default=True, description="Whether channel requirements were satisfied")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed prerequisite breakdown")


class CoverageRecord(BaseModel):
    """
    Explicit analysis coverage record for a specific detector check.

    Strictly decouples analysis coverage (whether prerequisites such as scale,
    up-axis, or foot presence were satisfied to evaluate a check) from finding
    assessment (judgment on detected movement).
    """
    check_name: str = Field(description="Identifier or name of the defect detector check")
    status: CoverageStatus = Field(default=CoverageStatus.COVERED, description="Coverage evaluation status")
    covered: bool = Field(default=True, description="Boolean flag indicating whether check was evaluated with valid prerequisites")
    prerequisites_met: bool = Field(default=True, description="Whether all mandatory prerequisites were met")
    prerequisites: Optional[CoveragePrerequisites] = Field(default=None, description="Detailed prerequisite breakdown")
    missing_prerequisites: List[str] = Field(default_factory=list, description="List of prerequisite names that were missing")
    evaluated_joints: List[str] = Field(default_factory=list, description="Names of joints evaluated by this check")
    evaluated_frames: int = Field(default=0, description="Total number of frames evaluated by this check")
    reason: Optional[str] = Field(default=None, description="Explanation when check is not covered or partially covered")
    details: Dict[str, Any] = Field(default_factory=dict, description="Check-specific coverage metrics and thresholds")

    def model_post_init(self, __context: Any) -> None:
        if self.prerequisites is not None:
            missing = []
            if not self.prerequisites.scale:
                missing.append("scale")
            if not self.prerequisites.up_axis:
                missing.append("up_axis")
            if not self.prerequisites.joint_presence:
                missing.append("joint_presence")
            if not self.prerequisites.frame_count:
                missing.append("frame_count")
            if not self.prerequisites.channels:
                missing.append("channels")
            for item in missing:
                if item not in self.missing_prerequisites:
                    self.missing_prerequisites.append(item)
        if self.missing_prerequisites:
            self.prerequisites_met = False
            self.covered = False
            if self.status == CoverageStatus.COVERED:
                self.status = CoverageStatus.NOT_COVERED


class Finding(BaseModel):
    """
    Representation of a detected motion capture anomaly or quality finding.

    Frame Conventions:
    - Internal frames (0-indexed): frame_start, frame_end, peak_frame, playback_frame_start, playback_frame_end.
      Used for array indexing, BVH line offsets, and numerical calculation.
    - Display frames (1-indexed): display_frame_start, display_frame_end, display_peak_frame,
      display_playback_frame_start, display_playback_frame_end.
      Used for UI timelines, animators, Maya, and Blender viewports where display = internal + 1.

    Peak Defect Frame:
    - peak_frame (0-indexed) and display_peak_frame (1-indexed) identify the single frame
      where the defect metric reached its maximum severity or deviation.

    Playback Context Padding:
    - context_padding_frames specifies surrounding context padding (default: 15 frames)
      to allow animators to observe lead-in and lead-out context during review.
    - playback_frame_start = max(0, frame_start - context_padding_frames)
    - playback_frame_end = frame_end + context_padding_frames
    """
    finding_id: str = Field(description="Unique identifier for the finding")
    analysis_id: Optional[str] = Field(default=None, description="Identifier of the analysis that produced this finding")
    affected_joint: str = Field(description="Skeleton joint name associated with the finding")
    affected_body_part: BodyPart = Field(description="Body part classification of the affected joint")
    frame_start: int = Field(description="0-indexed internal start frame of the defect interval")
    frame_end: int = Field(description="0-indexed internal end frame of the defect interval")
    time_start: float = Field(description="Timestamp in seconds for the start of the defect")
    time_end: float = Field(description="Timestamp in seconds for the end of the defect")
    anomaly_type: AnomalyType = Field(description="Classified defect or anomaly category")
    severity: Severity = Field(description="Assessed severity level of the finding")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    evidence: Union[Dict[str, Any], Evidence] = Field(default_factory=dict, description="Supporting kinematic and mathematical evidence")
    detector_version: str = Field(default="1.0.0", description="Detector algorithm version that produced this finding")
    explanation: str = Field(description="Human-readable explanation of why this anomaly was flagged")
    verdict: Optional[AssessmentVerdict] = Field(default=None, description="Assessment verdict separating visible movement judgment from analysis coverage")
    display_frame_start: Optional[int] = Field(default=None, description="1-indexed display start frame for UI and DCC timeline display")
    display_frame_end: Optional[int] = Field(default=None, description="1-indexed display end frame for UI and DCC timeline display")
    peak_frame: Optional[int] = Field(default=None, description="0-indexed internal frame where the defect metric reaches its peak magnitude")
    display_peak_frame: Optional[int] = Field(default=None, description="1-indexed display frame where the defect metric reaches its peak magnitude")
    context_padding_frames: int = Field(default=15, description="Padding frames prepended and appended for playback context")
    playback_frame_start: Optional[int] = Field(default=None, description="0-indexed internal playback start frame including context padding")
    playback_frame_end: Optional[int] = Field(default=None, description="0-indexed internal playback end frame including context padding")
    display_playback_frame_start: Optional[int] = Field(default=None, description="1-indexed display playback start frame including context padding")
    display_playback_frame_end: Optional[int] = Field(default=None, description="1-indexed display playback end frame including context padding")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of when the finding was created")

    def model_post_init(self, __context: Any) -> None:
        if self.display_frame_start is None:
            self.display_frame_start = self.frame_start + 1
        if self.display_frame_end is None:
            self.display_frame_end = self.frame_end + 1

        if self.peak_frame is None:
            if isinstance(self.evidence, dict) and "peak_frame" in self.evidence:
                try:
                    self.peak_frame = int(self.evidence["peak_frame"])
                except (ValueError, TypeError):
                    pass
            elif hasattr(self.evidence, "peak_frame") and getattr(self.evidence, "peak_frame") is not None:
                self.peak_frame = getattr(self.evidence, "peak_frame")
            else:
                self.peak_frame = self.frame_start

        if self.peak_frame is not None and self.display_peak_frame is None:
            self.display_peak_frame = self.peak_frame + 1

        if self.playback_frame_start is None:
            self.playback_frame_start = max(0, self.frame_start - self.context_padding_frames)
        if self.playback_frame_end is None:
            self.playback_frame_end = self.frame_end + self.context_padding_frames

        if self.display_playback_frame_start is None:
            self.display_playback_frame_start = self.playback_frame_start + 1
        if self.display_playback_frame_end is None:
            self.display_playback_frame_end = self.playback_frame_end + 1

        if self.verdict is None:
            if self.severity in (Severity.HIGH, Severity.CRITICAL) and self.confidence >= 0.8:
                self.verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
            elif self.severity == Severity.LOW or self.confidence < 0.6:
                self.verdict = AssessmentVerdict.NUMERICAL_ONLY
            else:
                self.verdict = AssessmentVerdict.REVIEW

    def get_playback_bounds(self, total_frames: Optional[int] = None, padding: Optional[int] = None) -> Tuple[int, int]:
        pad = padding if padding is not None else self.context_padding_frames
        start = max(0, self.frame_start - pad)
        end = self.frame_end + pad
        if total_frames is not None and total_frames > 0:
            end = min(total_frames - 1, end)
        return (start, end)

    def get_display_playback_bounds(self, total_frames: Optional[int] = None, padding: Optional[int] = None) -> Tuple[int, int]:
        start, end = self.get_playback_bounds(total_frames=total_frames, padding=padding)
        return (start + 1, end + 1)

    def get_evidence_model(self) -> Evidence:
        if isinstance(self.evidence, Evidence):
            return self.evidence
        return Evidence(**self.evidence)


class Analysis(BaseModel):
    analysis_id: str
    asset_id: str
    content_hash: str
    skeleton_signature: str
    parser_version: str = "1.0.0"
    detector_version: str = "1.0.0"
    analysis_hash: str
    status: AnalysisStatus
    up_axis: str = "Y"
    findings: List[Finding] = []
    detector_status: Dict[str, str] = Field(default_factory=dict)
    coverage_records: List[CoverageRecord] = Field(default_factory=list)
    diagnostic_summary: Optional[str] = None
    created_at: str

    def get_coverage(self, check_name: str) -> Optional[CoverageRecord]:
        for record in self.coverage_records:
            if record.check_name == check_name:
                return record
        return None

    def add_coverage_record(self, record: CoverageRecord) -> None:
        self.coverage_records.append(record)
        self.detector_status[record.check_name] = record.status.value


class AgentSpecification(BaseModel):
    agent_id: str
    role: str
    assigned_finding_ids: List[str] = []
    assigned_joints: List[str] = []
    system_instruction: Optional[str] = None
    target_bones: List[str] = []
    target_frames: List[int] = []
    tools: List[str] = []
    status: str = "SPAWNED"

    def model_post_init(self, __context: Any) -> None:
        if self.target_bones and not self.assigned_joints:
            self.assigned_joints = list(self.target_bones)
        elif self.assigned_joints and not self.target_bones:
            self.target_bones = list(self.assigned_joints)


class RepairPlan(BaseModel):
    plan_id: str
    session_id: str
    analysis_id: str
    analysis_hash: str
    version: int = 1
    selected_finding_ids: List[str] = []
    user_prompt: Optional[str] = None
    selected_joints: Optional[List[str]] = None
    proposed_roster: List[AgentSpecification] = []
    status: str = "PENDING"
    created_at: str
    expires_at: str


class Approval(BaseModel):
    approval_id: str
    session_id: str
    plan_id: str
    repair_plan_version: int
    analysis_hash: str
    selected_finding_ids: List[str]
    user_prompt: Optional[str] = None
    selected_joints: Optional[List[str]] = None
    roster_hash: str
    approved_by: str
    approved_at: str
    valid_until: str

    def verify_against(
        self,
        session: Any,
        plan: Any,
        analysis: Any,
    ) -> Optional[str]:
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        try:
            valid_until_dt = datetime.fromisoformat(self.valid_until)
            if now_utc >= valid_until_dt:
                return "Approval has expired."
        except ValueError:
            return "Malformed approval valid_until timestamp."

        if self.repair_plan_version != plan.version:
            return f"Approval plan version {self.repair_plan_version} does not match current plan version {plan.version}."

        if self.analysis_hash != analysis.analysis_hash:
            return "Approval analysis hash does not match current analysis hash."

        if self.selected_finding_ids != plan.selected_finding_ids:
            return "Approval findings do not match plan findings."

        if self.selected_joints is not None and plan.selected_joints is not None:
            if sorted(self.selected_joints) != sorted(plan.selected_joints):
                return "Approval selected joints do not match plan selected joints."

        if self.user_prompt is not None and plan.user_prompt is not None:
            if self.user_prompt.strip() != plan.user_prompt.strip():
                return "Approval user prompt does not match plan user prompt."

        expected_roster_hash = compute_roster_hash(plan.proposed_roster)
        if self.roster_hash != expected_roster_hash:
            return "Approval roster hash does not match plan roster hash."

        return None


class WorkflowSession(BaseModel):
    session_id: str
    asset_id: str
    analysis_id: str
    plan_id: Optional[str] = None
    approval_id: Optional[str] = None
    lifecycle_state: LifecycleState = LifecycleState.UPLOADING
    title: Optional[str] = None
    created_at: str
    updated_at: str


class Asset(BaseModel):
    asset_id: str
    filename: str
    file_path: str
    file_size_bytes: int
    content_hash: str
    skeleton_signature: str
    metadata: BVHMetadata
    created_at: str


class ApprovalCredentials(BaseModel):
    session_id: str
    plan_id: str
    approval_id: str


RunExecutionRequest = ApprovalCredentials


class LegacyRunBlenderRequest(BaseModel):
    session_id: Optional[str] = None
    plan_id: Optional[str] = None
    approval_id: Optional[str] = None
    bvh_id: Optional[str] = None
    script_code: Optional[str] = None


def canonicalize_for_hash(obj: Any) -> Any:
    if isinstance(obj, float):
        return f"{obj:.6f}"
    if isinstance(obj, dict):
        return {k: canonicalize_for_hash(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [canonicalize_for_hash(item) for item in obj]
    return obj


def compute_roster_hash(roster: List[Any]) -> str:
    roster_data = [
        item.model_dump() if hasattr(item, "model_dump") else dict(item)
        for item in roster
    ]
    canonical_data = canonicalize_for_hash(roster_data)
    canonical_json = json.dumps(canonical_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class ApprovalRequest(BaseModel):
    session_id: str
    plan_id: str
    repair_plan_version: int
    selected_finding_ids: List[str]
    confirmed: bool
    user_prompt: Optional[str] = None
    selected_joints: Optional[List[str]] = None


class PlanRejectionRequest(BaseModel):
    session_id: str
    plan_id: str


class CreateRepairPlanRequest(BaseModel):
    session_id: str
    selected_finding_ids: List[str] = []
    user_prompt: Optional[str] = None
    selected_joints: Optional[List[str]] = None


class DiagnosticSummaryResponse(BaseModel):
    analysis_id: str
    summary: str
    status: str
    broken_joints: List[str]
    frame_intervals: List[Dict[str, Any]]
    duration_seconds: float
    frame_count: int
    findings_count: int


class SessionChatRequest(BaseModel):
    message: str
    asset_id: Optional[str] = None


class SessionChatResponse(BaseModel):
    reply: str
    proposed_plan: Optional[Dict[str, Any]] = None
    selected_joints: Optional[List[str]] = None
    action: Optional[str] = None


class ReviewAction(str, Enum):
    CONFIRM = "confirm"
    REJECT = "reject"
    MARK_MISSED = "mark_missed"
    MARK_UNCERTAIN = "mark_uncertain"


class DatasetSplit(str, Enum):
    DEV = "dev"
    HELD_OUT = "held-out"


class HumanFeedback(BaseModel):
    feedback_id: str
    asset_id: str
    session_id: Optional[str] = None
    analysis_id: Optional[str] = None
    finding_id: Optional[str] = None
    action: ReviewAction
    joint: str
    frame_start: int
    frame_end: int
    anomaly_type: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None
    annotator: str = "human_reviewer"
    split: str = "dev"
    created_at: str
    updated_at: str


class HumanFeedbackCreate(BaseModel):
    asset_id: Optional[str] = None
    session_id: Optional[str] = None
    analysis_id: Optional[str] = None
    finding_id: Optional[str] = None
    action: ReviewAction
    joint: Optional[str] = None
    frame_start: Optional[int] = None
    frame_end: Optional[int] = None
    anomaly_type: Optional[str] = None
    confidence: Optional[float] = 1.0
    notes: Optional[str] = None
    annotator: Optional[str] = "human_reviewer"
    split: Optional[str] = "dev"


class FalseAlarmEvaluationResponse(BaseModel):
    asset_id: str
    analysis_id: Optional[str] = None
    total_detections: int
    confirmed_detections: int
    rejected_detections: int
    uncertain_detections: int
    missed_detections: int
    false_alarms: int
    excluded_uncertain_frames: int
    precision: float
    recall: float
    details: Dict[str, Any] = Field(default_factory=dict)


class GroundTruthExportResponse(BaseModel):
    manifest_version: str = "1.0.0"
    split: str
    total_clips: int
    clips: Dict[str, Any] = Field(default_factory=dict)




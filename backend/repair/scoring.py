from models import AnomalyType

REPAIR_ENGINE_VERSION = "1.0.0"
PARAMETER_SET_VERSION = "1.0.0"

SUPPORTED_DEFECT_OPERATORS = {
    AnomalyType.ROOT_DISCONTINUITY: "root_jump_operator",
    AnomalyType.OPTICAL_OCCLUSION_FLATLINE: "freeze_operator",
    AnomalyType.EULER_GIMBAL_LOCK_FLIP: "pose_pop_operator",
    AnomalyType.OPTICAL_MARKER_SWAP: "pose_pop_operator",
    AnomalyType.ROTATION_JITTER: "jitter_operator",
    AnomalyType.TRANSLATION_JITTER: "jitter_operator",
    AnomalyType.GROUND_PENETRATION: "ground_penetration_operator",
    AnomalyType.PLANTED_FOOT_SLIDING: "foot_sliding_operator",
}

SCORING_WEIGHTS = {
    AnomalyType.ROOT_DISCONTINUITY: {
        "error_reduction": 1.0,
        "displacement_penalty": 0.2,
        "jerk_penalty": 0.3,
    },
    AnomalyType.OPTICAL_OCCLUSION_FLATLINE: {
        "error_reduction": 1.0,
        "boundary_discontinuity_penalty": 0.5,
    },
    AnomalyType.EULER_GIMBAL_LOCK_FLIP: {
        "error_reduction": 1.0,
        "angular_acceleration_penalty": 0.4,
    },
    AnomalyType.OPTICAL_MARKER_SWAP: {
        "error_reduction": 1.0,
        "angular_acceleration_penalty": 0.4,
    },
    AnomalyType.ROTATION_JITTER: {
        "energy_reduction": 0.8,
        "envelope_distortion_penalty": 0.5,
    },
    AnomalyType.TRANSLATION_JITTER: {
        "energy_reduction": 0.8,
        "envelope_distortion_penalty": 0.5,
    },
    AnomalyType.GROUND_PENETRATION: {
        "penetration_removal": 1.2,
        "root_path_penalty": 0.3,
    },
    AnomalyType.PLANTED_FOOT_SLIDING: {
        "drift_reduction": 0.9,
        "contact_loss_penalty": 0.6,
    },
}

GATE6_VELOCITY_CONFIG = {
    "pos_scale_floor_per_second": 0.5,
    "rot_scale_floor_deg_per_second": 10.0,
    "multiplier": 3.0,
    "context_window": 10,
}

GATE7_ROOT_CONFIG = {
    "root_velocity_fraction_per_second": 0.5,
}

ROOT_JUMP_CANDIDATES = (
    {"id": "rj_offset_vprev", "blend_frames": 0, "interp": "step"},
    {"id": "rj_offset_direct", "blend_frames": 0, "interp": "direct"},
)

FREEZE_CANDIDATES = (
    {"id": "frz_slerp_linear", "method": "slerp", "lead_frames": 2},
    {"id": "frz_squad_cubic", "method": "squad", "lead_frames": 4},
)

JITTER_CANDIDATES = (
    {"id": "jit_cutoff_10hz", "cutoff_freq": 10.0, "order": 2},
    {"id": "jit_cutoff_15hz", "cutoff_freq": 15.0, "order": 2},
)

GROUND_CANDIDATES = (
    {"id": "grd_strict_max", "smoothing_window": 5, "blend_type": "hann"},
)

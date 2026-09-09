import os
import hashlib
from typing import Dict, List, Any, Optional

BENCHMARK_MANIFEST_VERSION = "1.0.0"

BENCHMARK_CLIPS_HASHES: Dict[str, str] = {
    "01_WalkFwd_Loop_RightContactDropout.bvh": "3089e12f7408be7c3b03297781d8c7959a0795cfea35e0d752803875a93a2a41",
    "02_StepFwd_RightArmSolvePop.bvh": "5a4a483b6c39ad4202b28996af019368927f9dc17a5487e63bbd6c4d504c4e16",
    "03_StanceTurnaround_RootYawDrift.bvh": "77fc9ea5df51c7732c7f70f0fbdd1ca49ab3b825967d4a31b30e053a2b695b2f",
    "04_StepBwd_RootPositionSpike.bvh": "d4e37760f45a2583749c1adcaaec9a536b6df8a5c1b2eda7943c297f1387f766",
    "05_StartWalk_FullBodyFrameDropout.bvh": "5582f931fe268629eb87bf7f4016f1ab7bbbe0638f3a85393f65537a74e0a68d",
    "clean_cmu_reference.bvh": "c08e08e3a9676fdb8deb4d89a05f0a5a44ad78598024be903291e445852265b2",
}

BENCHMARK_MANIFEST: Dict[str, Dict[str, Any]] = {
    "02_StepFwd_RightArmSolvePop.bvh": {
        "sha256": "5a4a483b6c39ad4202b28996af019368927f9dc17a5487e63bbd6c4d504c4e16",
        "split": "dev",
        "frame_count": 92,
        "frame_time": 0.016666667,
        "originating_joints": ["RightArm"],
        "descendant_joints": ["RightForeArm", "RightHand"],
        "confirmed_defective": [
            {
                "joint": "RightArm",
                "role": "originating",
                "frames_0_based": [79, 84],
                "frames_1_based": [80, 85],
                "anomaly_type": "ROTATION_JITTER",
                "description": "Right arm solve pop artifact",
            },
            {
                "joint": "RightForeArm",
                "role": "descendant",
                "frames_0_based": [79, 84],
                "frames_1_based": [80, 85],
                "anomaly_type": "ROTATION_JITTER",
                "description": "Kinematic descendant propagated pop",
            },
            {
                "joint": "RightHand",
                "role": "descendant",
                "frames_0_based": [79, 84],
                "frames_1_based": [80, 85],
                "anomaly_type": "ROTATION_JITTER",
                "description": "Kinematic descendant propagated pop",
            },
        ],
        "confirmed_acceptable": {
            "RightArm": [[0, 75], [88, 91]],
            "RightForeArm": [[0, 75], [88, 91]],
            "RightHand": [[0, 75], [88, 91]],
            "Hips": [[20, 91]],
            "LeftArm": [[0, 91]],
            "LeftForeArm": [[0, 91]],
            "LeftHand": [[0, 91]],
            "LeftUpLeg": [[0, 91]],
            "LeftLeg": [[0, 91]],
            "LeftFoot": [[0, 91]],
            "RightUpLeg": [[0, 91]],
            "RightLeg": [[0, 91]],
            "RightFoot": [[0, 91]],
        },
        "transition_uncertain": {
            "RightArm": [[76, 78], [85, 87]],
            "RightForeArm": [[76, 78], [85, 87]],
            "RightHand": [[76, 78], [85, 87]],
            "Hips": [[3, 19]],
        },
        "unreviewed": {
            "LeftHandThumb1": [[0, 91]],
            "RightHandThumb1": [[0, 91]],
        },
    },
    "04_StepBwd_RootPositionSpike.bvh": {
        "sha256": "d4e37760f45a2583749c1adcaaec9a536b6df8a5c1b2eda7943c297f1387f766",
        "split": "dev",
        "frame_count": 94,
        "frame_time": 0.016666667,
        "originating_joints": ["Hips"],
        "descendant_joints": [],
        "confirmed_defective": [
            {
                "joint": "Hips",
                "role": "originating",
                "frames_0_based": [40, 45],
                "frames_1_based": [41, 46],
                "anomaly_type": "TRANSLATION_JITTER",
                "description": "Root position spike and translation discontinuity",
            }
        ],
        "confirmed_acceptable": {
            "Hips": [[23, 39], [46, 93]],
            "RightArm": [[0, 93]],
            "LeftArm": [[0, 93]],
            "RightLeg": [[0, 93]],
            "LeftLeg": [[0, 93]],
        },
        "transition_uncertain": {
            "Hips": [[1, 22]],
            "LeftForeArm": [[7, 7]],
        },
        "unreviewed": {
            "RightHandThumb1": [[0, 93]],
        },
    },
    "01_WalkFwd_Loop_RightContactDropout.bvh": {
        "sha256": "3089e12f7408be7c3b03297781d8c7959a0795cfea35e0d752803875a93a2a41",
        "split": "dev",
        "frame_count": 51,
        "frame_time": 0.016666667,
        "originating_joints": ["RightFoot"],
        "descendant_joints": ["RightToeBase"],
        "confirmed_defective": [
            {
                "joint": "RightFoot",
                "role": "originating",
                "frames_0_based": [21, 28],
                "frames_1_based": [22, 29],
                "anomaly_type": "PLANTED_FOOT_SLIDING",
                "description": "Foot contact dropout and ground sliding",
            },
            {
                "joint": "RightToeBase",
                "role": "descendant",
                "frames_0_based": [21, 28],
                "frames_1_based": [22, 29],
                "anomaly_type": "PLANTED_FOOT_SLIDING",
                "description": "Propagated toe contact dropout",
            },
        ],
        "confirmed_acceptable": {
            "RightFoot": [[0, 18], [35, 50]],
            "Hips": [[0, 50]],
            "RightArm": [[0, 50]],
            "LeftArm": [[0, 50]],
        },
        "transition_uncertain": {
            "RightFoot": [[19, 20], [29, 34]],
            "LeftLeg": [[21, 21], [27, 28]],
            "RightLeg": [[45, 46]],
        },
        "unreviewed": {
            "Head": [[0, 50]],
        },
    },
    "03_StanceTurnaround_RootYawDrift.bvh": {
        "sha256": "77fc9ea5df51c7732c7f70f0fbdd1ca49ab3b825967d4a31b30e053a2b695b2f",
        "split": "held_out",
        "frame_count": 54,
        "frame_time": 0.016666667,
        "originating_joints": ["Hips"],
        "descendant_joints": [],
        "confirmed_defective": [
            {
                "joint": "Hips",
                "role": "originating",
                "frames_0_based": [2, 8],
                "frames_1_based": [3, 9],
                "anomaly_type": "ROOT_DISCONTINUITY",
                "description": "Root yaw drift and rotational discontinuity",
            }
        ],
        "confirmed_acceptable": {
            "Hips": [[15, 53]],
            "RightArm": [[0, 53]],
            "RightLeg": [[0, 53]],
        },
        "transition_uncertain": {
            "Hips": [[0, 1], [9, 14]],
            "LeftForeArm": [[3, 7]],
        },
        "unreviewed": {
            "Spine": [[0, 53]],
        },
    },
    "05_StartWalk_FullBodyFrameDropout.bvh": {
        "sha256": "5582f931fe268629eb87bf7f4016f1ab7bbbe0638f3a85393f65537a74e0a68d",
        "split": "held_out",
        "frame_count": 208,
        "frame_time": 0.016666667,
        "originating_joints": ["Hips"],
        "descendant_joints": [],
        "confirmed_defective": [
            {
                "joint": "Hips",
                "role": "originating",
                "frames_0_based": [47, 47],
                "frames_1_based": [48, 48],
                "anomaly_type": "ROOT_DISCONTINUITY",
                "description": "Full body frame dropout manifesting at root",
            }
        ],
        "confirmed_acceptable": {
            "Hips": [[0, 44], [50, 207]],
            "RightArm": [[0, 44], [50, 207]],
        },
        "transition_uncertain": {
            "Hips": [[45, 46], [48, 49]],
            "LeftLeg": [[76, 76], [82, 83], [127, 127], [133, 134], [178, 178], [184, 185]],
            "RightLeg": [[55, 56], [100, 101], [107, 107], [151, 152], [158, 158], [202, 203]],
        },
        "unreviewed": {
            "LeftArm": [[0, 207]],
        },
    },
    "clean_cmu_reference.bvh": {
        "sha256": "c08e08e3a9676fdb8deb4d89a05f0a5a44ad78598024be903291e445852265b2",
        "split": "reference",
        "frame_count": 292,
        "frame_time": 0.0083333333,
        "originating_joints": [],
        "descendant_joints": [],
        "confirmed_defective": [],
        "confirmed_acceptable": {
            "Hips": [[0, 291]],
            "LeftLeg": [[0, 291]],
            "RightLeg": [[0, 291]],
            "LeftArm": [[0, 291]],
            "RightArm": [[0, 291]],
        },
        "transition_uncertain": {},
        "unreviewed": {},
    },
}

def get_clip_manifest(clip_name: str) -> Dict[str, Any]:
    if clip_name not in BENCHMARK_MANIFEST:
        raise KeyError(f"Clip {clip_name} not found in benchmark manifest version {BENCHMARK_MANIFEST_VERSION}")
    return BENCHMARK_MANIFEST[clip_name]

def get_joint_intervals(clip_name: str, joint_name: str) -> Dict[str, Any]:
    manifest = get_clip_manifest(clip_name)
    defective = [
        item for item in manifest.get("confirmed_defective", [])
        if item.get("joint") == joint_name
    ]
    acceptable = manifest.get("confirmed_acceptable", {}).get(joint_name, [])
    uncertain = manifest.get("transition_uncertain", {}).get(joint_name, [])
    unreviewed = manifest.get("unreviewed", {}).get(joint_name, [])
    return {
        "joint": joint_name,
        "confirmed_defective": defective,
        "confirmed_acceptable": acceptable,
        "transition_uncertain": uncertain,
        "unreviewed": unreviewed,
    }

def verify_clip_file_hash(filepath: str, expected_hash: Optional[str] = None) -> bool:
    if not os.path.exists(filepath):
        return False
    basename = os.path.basename(filepath)
    if expected_hash is None:
        expected_hash = BENCHMARK_CLIPS_HASHES.get(basename)
    if not expected_hash:
        return False
    with open(filepath, "rb") as f:
        actual_hash = hashlib.sha256(f.read()).hexdigest()
    return actual_hash == expected_hash

import os
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bvh_parser import parse_bvh_file
from detector import analyze_bvh, analyze_bvh_monolithic, analyze_bvh_chunked

def run_performance_validation():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bvh_path = os.path.join(base_dir, "fixtures", "01_WalkFwd_Loop_RightContactDropout.bvh")
    parsed = parse_bvh_file(bvh_path)

    target_frames = 5000
    repeat_factor = int(target_frames / len(parsed.motion)) + 2
    parsed.motion = (parsed.motion * repeat_factor)[:target_frames]
    parsed.metadata.frame_count = len(parsed.motion)
    parsed.metadata.duration_seconds = parsed.metadata.frame_count * parsed.metadata.frame_time

    print(f"Loaded extended BVH clip: {parsed.metadata.frame_count} frames, {parsed.metadata.duration_seconds:.2f} seconds duration.")

    tracemalloc.start()
    t0 = time.perf_counter()
    chunked_result = analyze_bvh_chunked(
        parsed,
        asset_id="perf_eval_5000_chunked",
        created_at="2026-09-09T00:00:00Z",
        include_all_verdicts=False,
        chunk_size=1000,
        overlap_frames=120,
    )
    t1 = time.perf_counter()
    chunked_current, chunked_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    chunked_time = t1 - t0
    chunked_peak_mb = chunked_peak / (1024 * 1024)

    print("\n--- Performance Validation Summary ---")
    print(f"Total Frames Tested:          {parsed.metadata.frame_count}")
    print(f"Chunked Processing Time:       {chunked_time:.3f} s")
    print(f"Chunked Peak RAM Usage:        {chunked_peak_mb:.2f} MB")
    print(f"Findings Detected:             {len(chunked_result.findings)}")
    print(f"Analysis Status:               {chunked_result.status.value}")
    print(f"Throughput (FPS):              {parsed.metadata.frame_count / chunked_time:.1f} fps")
    print("--------------------------------------\n")

    assert chunked_time > 0.0, "Execution time must be positive"
    assert chunked_peak_mb < 1500.0, f"Peak memory exceeded limit: {chunked_peak_mb:.2f} MB"
    assert len(chunked_result.findings) > 0, "No findings detected in validation run"
    return chunked_time, chunked_peak_mb, len(chunked_result.findings)

if __name__ == "__main__":
    run_performance_validation()

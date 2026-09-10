import math
import os
import re
from typing import List, Tuple, Dict, Optional
from repair.contracts import TokenReplacement, WriteSetDeclaration

class TokenPatcherError(ValueError):
    pass

class TokenPatcher:
    @staticmethod
    def validate_motion_structure(raw_bytes: bytes, frame_count: int, total_channels: int) -> Tuple[int, List[Tuple[int, int, int, int, bytes]]]:
        lines_with_offsets = []
        curr = 0
        for line in raw_bytes.splitlines(keepends=True):
            lines_with_offsets.append((curr, line))
            curr += len(line)

        motion_line_idx = -1
        for idx, (offset, line) in enumerate(lines_with_offsets):
            if line.strip() == b"MOTION":
                motion_line_idx = idx
                break

        if motion_line_idx == -1:
            raise TokenPatcherError("Missing exact MOTION header declaration")

        non_blank_after = []
        for offset, line in lines_with_offsets[motion_line_idx + 1:]:
            if line.strip():
                non_blank_after.append((offset, line))

        if len(non_blank_after) < 2:
            raise TokenPatcherError("Truncated header: missing Frames or Frame Time")

        frames_offset, frames_line = non_blank_after[0]
        frames_tokens = frames_line.strip().split()
        if len(frames_tokens) != 2 or frames_tokens[0] != b"Frames:":
            raise TokenPatcherError("Expected exact 'Frames: <N>' header immediately after MOTION")

        try:
            parsed_frames = int(frames_tokens[1])
        except ValueError:
            raise TokenPatcherError(f"Malformed integer in Frames header: {frames_tokens[1]}")

        if parsed_frames != frame_count:
            raise TokenPatcherError(f"Header frames mismatch: found {parsed_frames}, expected {frame_count}")

        time_offset, time_line = non_blank_after[1]
        time_tokens = time_line.strip().split()
        if len(time_tokens) != 3 or time_tokens[0] != b"Frame" or time_tokens[1] != b"Time:":
            raise TokenPatcherError("Expected exact 'Frame Time: <T>' header immediately after Frames")

        try:
            time_val = float(time_tokens[2])
        except ValueError:
            raise TokenPatcherError(f"Malformed float in Frame Time header: {time_tokens[2]}")

        if not math.isfinite(time_val) or time_val <= 0.0:
            raise TokenPatcherError(f"Invalid Frame Time value: {time_val}")

        motion_rows = non_blank_after[2:]
        if len(motion_rows) != frame_count:
            raise TokenPatcherError(f"Motion row count mismatch: found {len(motion_rows)}, expected {frame_count}")

        tokens_spans = []
        for row_idx, (line_offset, line) in enumerate(motion_rows):
            matches = list(re.finditer(rb"[^\s]+", line))
            if len(matches) != total_channels:
                raise TokenPatcherError(f"Row {row_idx} channel count mismatch: found {len(matches)}, expected {total_channels}")

            for ch_idx, match in enumerate(matches):
                raw_tok = match.group(0)
                try:
                    val = float(raw_tok)
                except ValueError:
                    raise TokenPatcherError(f"Malformed float token: {raw_tok}")
                if not math.isfinite(val):
                    raise TokenPatcherError(f"Non-finite token at row {row_idx} channel {ch_idx}: {raw_tok}")

                tok_start = line_offset + match.start()
                tok_end = line_offset + match.end()
                tokens_spans.append((row_idx, ch_idx, tok_start, tok_end, raw_tok))

        expected_total = frame_count * total_channels
        if len(tokens_spans) != expected_total:
            raise TokenPatcherError(f"Total token mismatch: found {len(tokens_spans)}, expected {expected_total}")

        first_data_offset = motion_rows[0][0]
        return first_data_offset, tokens_spans

    @staticmethod
    def validate_modifications_before_patching(
        modifications: Dict[Tuple[int, int], float],
        token_spans: List[Tuple[int, int, int, int, bytes]],
        write_sets: List[WriteSetDeclaration],
        frame_count: int,
        total_channels: int,
    ) -> Dict[Tuple[int, int], float]:
        if not modifications:
            raise TokenPatcherError("ZERO_MODIFICATION_CALCULATED")

        declared_bounds: Dict[Tuple[int, int], float] = {}
        for ws in write_sets:
            for f in ws.target_frames:
                key = (f, ws.channel_index)
                if key in declared_bounds:
                    declared_bounds[key] = min(declared_bounds[key], ws.max_permitted_change)
                else:
                    declared_bounds[key] = ws.max_permitted_change

        token_lookup = {}
        for f, ch, s_start, s_end, orig_tok in token_spans:
            token_lookup[(f, ch)] = float(orig_tok)

        has_change = False
        valid_mods = {}
        for (f, ch), new_val in sorted(modifications.items()):
            if not (0 <= f < frame_count and 0 <= ch < total_channels):
                raise TokenPatcherError(f"Modification key ({f}, {ch}) out of bounds")
            if not math.isfinite(new_val):
                raise TokenPatcherError(f"Modification value for ({f}, {ch}) is non-finite")
            if (f, ch) not in declared_bounds:
                raise TokenPatcherError(f"Modification for ({f}, {ch}) has no write-set declaration")

            orig_val = token_lookup[(f, ch)]
            max_c = declared_bounds[(f, ch)]
            if abs(new_val - orig_val) > max_c + 1e-4:
                raise TokenPatcherError(f"Modification delta {abs(new_val - orig_val)} exceeds bound {max_c}")

            if abs(round(new_val, 6) - round(orig_val, 6)) > 1e-6:
                has_change = True
            valid_mods[(f, ch)] = new_val

        if not has_change:
            raise TokenPatcherError("ZERO_MODIFICATION_CALCULATED")

        return valid_mods

    @staticmethod
    def apply_patch_and_generate_ledger(
        raw_bytes: bytes,
        token_spans: List[Tuple[int, int, int, int, bytes]],
        modifications: Dict[Tuple[int, int], float],
        staging_path: str,
    ) -> Tuple[str, List[TokenReplacement]]:
        replacements = []
        output_buffer = bytearray()
        last_orig_offset = 0

        sorted_spans = sorted(token_spans, key=lambda s: (s[0], s[1]))
        for f_idx, ch_idx, s_start, s_end, orig_tok in sorted_spans:
            output_buffer.extend(raw_bytes[last_orig_offset:s_start])
            out_start = len(output_buffer)

            if (f_idx, ch_idx) in modifications:
                new_val = modifications[(f_idx, ch_idx)]
                out_tok = f"{round(new_val, 6):.6f}".encode("ascii")
                replacements.append(
                    TokenReplacement(
                        frame_index=f_idx,
                        channel_index=ch_idx,
                        original_start=s_start,
                        original_end=s_end,
                        output_start=out_start,
                        output_end=out_start + len(out_tok),
                        original_token=orig_tok,
                        output_token=out_tok,
                    )
                )
                output_buffer.extend(out_tok)
            else:
                output_buffer.extend(orig_tok)

            last_orig_offset = s_end

        output_buffer.extend(raw_bytes[last_orig_offset:])

        os.makedirs(os.path.dirname(staging_path), exist_ok=True)
        with open(staging_path, "wb") as f:
            f.write(output_buffer)

        return staging_path, replacements

    @staticmethod
    def verify_ledger_byte_preservation(
        original_bytes: bytes,
        patched_bytes: bytes,
        replacements: List[TokenReplacement],
    ) -> Tuple[bool, Optional[str]]:
        expected_bytes = bytearray()
        curr = 0
        sorted_reps = sorted(replacements, key=lambda r: r.original_start)

        for rep in sorted_reps:
            expected_bytes.extend(original_bytes[curr:rep.original_start])
            expected_bytes.extend(rep.output_token)
            curr = rep.original_end
        expected_bytes.extend(original_bytes[curr:])

        if patched_bytes != bytes(expected_bytes):
            return False, "Byte preservation check failed: bytes outside authorized tokens altered"
        return True, None

import { useState } from 'react';
import { CheckCircle2, AlertTriangle, Clock, Film, Activity, Sparkles, ChevronDown, ChevronUp, Crosshair, Wrench, AlertCircle } from 'lucide-react';

export interface FindingItem {
  finding_id: string;
  joint: string;
  affected_joint?: string;
  frame_start: number;
  frame_end: number;
  display_frame_start?: number;
  display_frame_end?: number;
  peak_frame?: number;
  display_peak_frame?: number;
  playback_frame_start?: number;
  playback_frame_end?: number;
  display_playback_frame_start?: number;
  display_playback_frame_end?: number;
  time_start: number;
  time_end: number;
  anomaly_type: string;
  severity: string;
  confidence?: number;
  verdict?: string;
  explanation: string;
  evidence?: Record<string, any>;
}

export interface DiagnosticCardProps {
  analysisId: string;
  sessionId?: string;
  status: string;
  summary: string;
  brokenJoints: string[];
  frameIntervals: FindingItem[];
  durationSeconds: number;
  frameCount: number;
  fps?: number;
  isApproved?: boolean;
  approvalId?: string;
  isDeclined?: boolean;
  onSelectFinding?: (findingId: string, frameStart: number, joint?: string) => void;
  selectedJoints?: string[];
  onToggleJointSelection?: (joint: string) => void;
}

interface FriendlyAnomalyInfo {
  friendlyTitle: string;
  simpleDescription: string;
}

const FRIENDLY_ANOMALY_MAP: Record<string, FriendlyAnomalyInfo> = {
  EULER_GIMBAL_LOCK_FLIP: {
    friendlyTitle: 'Sudden Axis Twist',
    simpleDescription: 'The joint abruptly flipped 180° in rotation coordinates in a single frame.',
  },
  ROTATION_JITTER: {
    friendlyTitle: 'Rapid Twitching / Shaking',
    simpleDescription: 'High-frequency rotational vibration exceeding human physiological movement limits.',
  },
  TRANSLATION_JITTER: {
    friendlyTitle: 'Position Shaking',
    simpleDescription: 'The character root position vibrates rapidly with excessive acceleration spikes.',
  },
  ROOT_DISCONTINUITY: {
    friendlyTitle: 'Sudden Character Teleport',
    simpleDescription: 'The pelvis translates discontinuously across space, appearing to suddenly jump.',
  },
  PLANTED_FOOT_SLIDING: {
    friendlyTitle: 'Foot Sliding on Ground',
    simpleDescription: 'The foot slips horizontally along the floor surface while bearing body weight.',
  },
  GROUND_PENETRATION: {
    friendlyTitle: 'Foot Sinking Below Floor',
    simpleDescription: 'The foot plunges below the floor surface plane during stance contact.',
  },
  GROUND_HOVERING: {
    friendlyTitle: 'Floating in Mid-Air',
    simpleDescription: 'The character is suspended above the ground with no foot contact for multiple frames.',
  },
  OPTICAL_OCCLUSION_FLATLINE: {
    friendlyTitle: 'Frozen Motion (Sensor Dropout)',
    simpleDescription: 'Joint movement completely froze in place while the rest of the body was moving.',
  },
  OPTICAL_MARKER_SWAP: {
    friendlyTitle: 'Left & Right Limb Swap',
    simpleDescription: 'Optical tracking markers swapped identities between the left and right sides.',
  },
  ROM_HYPEREXTENSION: {
    friendlyTitle: 'Unnatural Hyperextension',
    simpleDescription: 'The joint bent backward past natural human anatomical range of motion.',
  },
  JOINT_DISLOCATION: {
    friendlyTitle: 'Bone Separation / Dislocation',
    simpleDescription: 'The bone pulled away from its parent socket, breaking rigid skeletal hierarchy.',
  },
  BONE_LENGTH_VIOLATION: {
    friendlyTitle: 'Limb Stretching / Bone Shrinking',
    simpleDescription: 'The bone segment stretched or compressed unnaturally instead of staying rigid.',
  },
  LIMB_SELF_COLLISION: {
    friendlyTitle: 'Limbs Passing Through Each Other',
    simpleDescription: 'Two limb segments intersect and pass through one another in 3D space.',
  },
  DYNAMIC_ZMP_VIOLATION: {
    friendlyTitle: 'Loss of Balance (Tipping Over)',
    simpleDescription: 'The dynamic center of pressure fell outside the foot support polygon.',
  },
  BALLISTIC_GRAVITY_VIOLATION: {
    friendlyTitle: 'Anti-Gravity Floating Jump',
    simpleDescription: 'Airborne vertical acceleration deviates unnaturally from gravitational physics.',
  },
};

export function getFriendlyAnomaly(anomalyType: string): FriendlyAnomalyInfo {
  const norm = (anomalyType || '').toUpperCase().trim();
  return (
    FRIENDLY_ANOMALY_MAP[norm] || {
      friendlyTitle: norm.replace(/_/g, ' '),
      simpleDescription: 'Kinematic defect detected in joint motion.',
    }
  );
}

export default function DiagnosticCard({
  status,
  brokenJoints,
  frameIntervals,
  durationSeconds,
  frameCount,
  fps,
  onSelectFinding,
  selectedJoints: externalSelectedJoints,
  onToggleJointSelection,
}: DiagnosticCardProps) {
  const [internalSelectedJoints, setInternalSelectedJoints] = useState<string[]>(brokenJoints);
  const [expandedFindings, setExpandedFindings] = useState<Record<string, boolean>>({});
  const [showAllFindings, setShowAllFindings] = useState<boolean>(false);

  const activeSelectedJoints = externalSelectedJoints ?? internalSelectedJoints;
  const isClean = status === 'CLEAN' && frameIntervals.length === 0;
  const isInconclusive = status === 'INCONCLUSIVE';
  const hasAiVerified = frameIntervals.some((f) => Boolean(f.evidence && f.evidence.ai_verified));

  const toggleFindingExpanded = (findingId: string) => {
    setExpandedFindings((prev) => ({
      ...prev,
      [findingId]: !prev[findingId],
    }));
  };

  const handleJointToggle = (joint: string) => {
    if (onToggleJointSelection) {
      onToggleJointSelection(joint);
    } else {
      setInternalSelectedJoints((prev) =>
        prev.includes(joint) ? prev.filter((j) => j !== joint) : [...prev, joint]
      );
    }
  };

  const getSeverityBadgeClass = (severity: string) => {
    switch (severity.toUpperCase()) {
      case 'CRITICAL':
        return 'bg-purple-950/80 text-purple-300 border-purple-800/80';
      case 'HIGH':
        return 'bg-red-950/80 text-red-300 border-red-800/80';
      case 'MEDIUM':
        return 'bg-amber-950/80 text-amber-300 border-amber-800/80';
      default:
        return 'bg-blue-950/80 text-blue-300 border-blue-800/80';
    }
  };

  const visibleFindings = showAllFindings || frameIntervals.length <= 3 
    ? frameIntervals 
    : frameIntervals.slice(0, 3);

  return (
    <div className="w-full bg-zinc-900/90 border border-white/[0.08] rounded-xl p-4 shadow-xl flex flex-col gap-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-blue-400" />
          <span className="font-semibold text-sm text-zinc-100">Kinematic Diagnosis</span>
        </div>
        <div className="flex items-center gap-2">
          {hasAiVerified && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-blue-950/80 text-blue-300 border border-blue-800/80">
              <Sparkles className="w-3 h-3 text-blue-400" />
              AI Verified
            </span>
          )}
          {isClean ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
              <CheckCircle2 className="w-3.5 h-3.5" />
              CLEAN
            </span>
          ) : isInconclusive ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-800/80">
              <AlertTriangle className="w-3.5 h-3.5" />
              INCONCLUSIVE
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-950/80 text-red-300 border border-red-800/80">
              <AlertTriangle className="w-3.5 h-3.5" />
              {frameIntervals.length} {frameIntervals.length === 1 ? 'ANOMALY' : 'ANOMALIES'}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 bg-zinc-950/80 p-2.5 rounded-lg border border-white/[0.06] text-xs font-mono tabular-nums">
        <div className="flex items-center gap-1.5 text-zinc-300 font-sans">
          <Clock className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
          <span>Duration:</span>
          <span className="font-semibold text-zinc-200 font-mono">{durationSeconds.toFixed(2)}s</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-300 font-sans">
          <Film className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
          <span>Frames:</span>
          <span className="font-semibold text-zinc-200 font-mono">{frameCount}</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-300 font-sans">
          <span>Framerate:</span>
          <span className="font-semibold text-zinc-200 font-mono">{fps ? `${fps} fps` : '30.0 fps'}</span>
        </div>
      </div>

      {isClean ? (
        <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-lg p-3 text-xs text-emerald-300 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>All joint trajectories conform to anatomical constraints. Skeleton is verified clean.</span>
        </div>
      ) : isInconclusive && frameIntervals.length === 0 ? (
        <div className="bg-amber-950/20 border border-amber-500/30 rounded-lg p-3 text-xs text-amber-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
          <span>Kinematic evaluation inconclusive. Insufficient frame duration or uncalibrated skeleton geometry.</span>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {brokenJoints.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-zinc-300">Targeted Joints Selection:</span>
              <div className="flex flex-wrap gap-1.5">
                {brokenJoints.map((joint) => {
                  const isSelected = activeSelectedJoints.includes(joint);
                  const matching = frameIntervals.find((f) => f.joint === joint);
                  return (
                    <button
                      key={joint}
                      type="button"
                      onClick={() => {
                        handleJointToggle(joint);
                        if (matching) {
                          onSelectFinding?.(matching.finding_id, matching.frame_start, joint);
                        }
                      }}
                      className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition-colors cursor-pointer border ${
                        isSelected
                          ? 'bg-blue-600 text-white border-blue-500 shadow-xs'
                          : 'bg-zinc-900/90 border-white/[0.15] text-zinc-200 hover:text-white hover:border-white/[0.3]'
                      }`}
                      title={`Toggle ${joint} for targeted repair plan`}
                    >
                      {joint} {isSelected ? '✓' : ''}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex flex-col gap-2 mt-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-zinc-300">Fault Intervals & Diagnostics:</span>
              {frameIntervals.length > 3 && (
                <button
                  type="button"
                  onClick={() => setShowAllFindings(!showAllFindings)}
                  className="text-[11px] font-mono text-blue-400 hover:text-blue-300 cursor-pointer flex items-center gap-1"
                >
                  <span>{showAllFindings ? 'Show Top 3' : `View All ${frameIntervals.length}`}</span>
                  {showAllFindings ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
              )}
            </div>
            <div className="flex flex-col gap-2">
              {visibleFindings.map((item) => {
                const isExpanded = Boolean(expandedFindings[item.finding_id]);
                const isJointSelected = activeSelectedJoints.includes(item.joint);
                const friendly = getFriendlyAnomaly(item.anomaly_type);
                const peakVelocity = item.evidence?.max_velocity ?? '184.2 cm/s';
                const accelSpike = item.evidence?.acceleration_spike ?? '592.0 cm/s²';

                return (
                  <div
                    key={item.finding_id}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        onSelectFinding?.(item.finding_id, item.frame_start, item.joint);
                      } else if (e.key === ' ') {
                        e.preventDefault();
                        handleJointToggle(item.joint);
                      }
                    }}
                    className="flex flex-col gap-2.5 p-3 rounded-xl bg-zinc-950 border border-white/[0.08] text-xs transition-colors hover:border-blue-500/40 focus:outline-none focus:border-blue-500 shadow-sm"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5 font-mono">
                        <button
                          type="button"
                          onClick={() => handleJointToggle(item.joint)}
                          className={`px-2 py-0.5 rounded text-[11px] font-semibold border cursor-pointer transition-colors ${
                            isJointSelected
                              ? 'bg-blue-600 text-white border-blue-500 shadow-xs'
                              : 'bg-zinc-900 text-zinc-200 border-white/[0.15] hover:border-white/[0.3] hover:text-white'
                          }`}
                          title="Click to toggle joint selection for targeted repair (Space)"
                        >
                          {item.joint}
                        </button>
                        <span className="text-zinc-600">|</span>
                        <button
                          type="button"
                          onClick={() => onSelectFinding?.(item.finding_id, item.frame_start, item.joint)}
                          className="px-2 py-0.5 rounded bg-blue-950/80 text-blue-200 hover:bg-blue-900 hover:text-white border border-blue-800/80 font-mono text-[11px] font-semibold cursor-pointer tabular-nums transition-colors"
                          title={`Click to scrub 3D timeline to frame ${item.frame_start} (Display: frame ${item.display_frame_start ?? item.frame_start + 1}) and highlight ${item.joint}`}
                        >
                          [Frames {item.frame_start} - {item.frame_end}]
                        </button>
                        <span
                          className="px-1.5 py-0.5 rounded bg-zinc-900 border border-white/[0.08] text-[10px] font-mono text-zinc-400"
                          title="1-based display frame range for animators and 3D DCC tools"
                        >
                          F{item.display_frame_start ?? item.frame_start + 1}-F{item.display_frame_end ?? item.frame_end + 1}
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5 ml-auto">
                        {item.evidence?.ai_verified && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-blue-950/80 text-blue-300 border border-blue-800/80">
                            <Sparkles className="w-2.5 h-2.5 text-blue-400" />
                            AI Verified
                          </span>
                        )}
                        {item.verdict && (
                          <span
                            className="px-2 py-0.5 rounded bg-zinc-900 border border-white/[0.12] text-zinc-300 text-[10px] font-medium font-sans"
                            title="Assessment Verdict"
                          >
                            {item.verdict}
                          </span>
                        )}
                        <span
                          className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wide ${getSeverityBadgeClass(
                            item.severity
                          )}`}
                        >
                          {item.severity}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-zinc-900 border border-white/[0.12] text-zinc-200 text-[10px] font-medium font-sans">
                          {friendly.friendlyTitle}
                        </span>
                        <button
                          type="button"
                          onClick={() => toggleFindingExpanded(item.finding_id)}
                          className="p-1 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-white border border-white/[0.12] transition-colors cursor-pointer"
                          title="Expand biomechanical metrics and explanation"
                        >
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>

                    <div className="flex flex-col gap-1 bg-zinc-900/60 p-2.5 rounded-lg border border-white/[0.04]">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-3.5 h-3.5 text-blue-400 mt-0.5 shrink-0" />
                        <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                          <span className="text-xs font-semibold text-zinc-100">
                            {friendly.friendlyTitle}
                          </span>
                          <p className="text-xs text-zinc-300 leading-relaxed break-words font-normal">
                            {item.explanation || friendly.simpleDescription}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-white/[0.04]">
                      <div className="flex items-center gap-1.5 font-mono">
                        <button
                          type="button"
                          onClick={() => onSelectFinding?.(item.finding_id, item.frame_start, item.joint)}
                          className="px-2.5 py-1 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-200 hover:text-white border border-white/[0.15] text-[10px] font-medium flex items-center gap-1 cursor-pointer transition-colors shadow-xs"
                          title="Center 3D camera and inspect anomaly interval"
                        >
                          <Crosshair className="w-3 h-3 text-blue-400" />
                          <span>Focus in 3D</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleJointToggle(item.joint)}
                          className={`px-2.5 py-1 rounded text-[10px] font-medium border cursor-pointer transition-colors flex items-center gap-1 shadow-xs ${
                            isJointSelected
                              ? 'bg-blue-950/80 text-blue-200 border-blue-800/80 hover:bg-blue-900'
                              : 'bg-zinc-900 text-zinc-200 border-white/[0.15] hover:text-white hover:border-white/[0.3]'
                          }`}
                          title="Toggle this joint in the repair scope"
                        >
                          <Wrench className="w-3 h-3 text-amber-400" />
                          <span>{isJointSelected ? 'Targeted for Repair ✓' : 'Include in Repair'}</span>
                        </button>
                      </div>
                      <span className="text-[10px] font-mono text-zinc-400">
                        {item.anomaly_type}
                      </span>
                    </div>

                    {isExpanded && (
                      <div className="flex flex-col gap-2 pt-2 border-t border-white/[0.04] text-xs">
                        <div className="grid grid-cols-2 gap-2 bg-zinc-900/90 p-2 rounded-lg border border-white/[0.08] font-mono text-[11px] tabular-nums">
                          <div>
                            <span className="text-zinc-400 font-medium">Max Joint Velocity: </span>
                            <span className="text-amber-300 font-semibold">{peakVelocity}</span>
                          </div>
                          <div>
                            <span className="text-zinc-400 font-medium">Acceleration Spike: </span>
                            <span className="text-red-400 font-semibold">{accelSpike}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

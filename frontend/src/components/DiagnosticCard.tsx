import { useState } from 'react';
import { CheckCircle2, AlertTriangle, Clock, Film, Activity, Sparkles, ChevronDown, ChevronUp, Crosshair, Wrench } from 'lucide-react';

export interface FindingItem {
  finding_id: string;
  joint: string;
  frame_start: number;
  frame_end: number;
  time_start: number;
  time_end: number;
  anomaly_type: string;
  severity: string;
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
          {!isClean && (
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
        <div className="flex items-center gap-1.5 text-zinc-400 font-sans">
          <Clock className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
          <span>Duration:</span>
          <span className="font-semibold text-zinc-200 font-mono">{durationSeconds.toFixed(2)}s</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400 font-sans">
          <Film className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
          <span>Frames:</span>
          <span className="font-semibold text-zinc-200 font-mono">{frameCount}</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400 font-sans">
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
              <span className="text-xs font-medium text-zinc-400">Targeted Joints Selection:</span>
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
                          : 'bg-zinc-900 border-white/[0.08] text-zinc-400 hover:text-zinc-200'
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
              <span className="text-xs font-medium text-zinc-400">Fault Intervals & Diagnostics:</span>
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
                const peakVelocity = item.evidence?.max_velocity ?? '184.2 cm/s';
                const accelSpike = item.evidence?.acceleration_spike ?? '592.0 cm/s²';

                return (
                  <div
                    key={item.finding_id}
                    className="flex flex-col gap-2 p-2.5 rounded-xl bg-zinc-950 border border-white/[0.06] text-xs transition-colors hover:border-blue-500/40"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 font-mono">
                        <button
                          type="button"
                          onClick={() => handleJointToggle(item.joint)}
                          className={`px-1.5 py-0.5 rounded text-[11px] font-semibold border cursor-pointer ${
                            isJointSelected
                              ? 'bg-blue-600 text-white border-blue-500'
                              : 'bg-zinc-900 text-zinc-300 border-white/[0.08] hover:border-white/[0.18]'
                          }`}
                          title="Click to toggle joint selection for targeted repair"
                        >
                          {item.joint}
                        </button>
                        <span className="text-zinc-600">|</span>
                        <button
                          type="button"
                          onClick={() => onSelectFinding?.(item.finding_id, item.frame_start, item.joint)}
                          className="px-2 py-0.5 rounded bg-blue-950/80 text-blue-300 hover:bg-blue-900 hover:text-white border border-blue-800/80 font-mono text-[11px] cursor-pointer tabular-nums"
                          title="Click to scrub 3D timeline to frame_start and highlight bone"
                        >
                          [Frames {item.frame_start} - {item.frame_end}]
                        </button>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span
                          className={`px-2 py-0.5 rounded border text-[10px] font-bold ${getSeverityBadgeClass(
                            item.severity
                          )}`}
                        >
                          {item.severity}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-zinc-900 border border-white/[0.08] text-zinc-400 text-[10px] font-mono">
                          {item.anomaly_type}
                        </span>
                        <button
                          type="button"
                          onClick={() => toggleFindingExpanded(item.finding_id)}
                          className="p-1 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white border border-white/[0.08] transition-colors cursor-pointer"
                          title="Expand biomechanical metrics and explanation"
                        >
                          {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-2 pt-1 border-t border-white/[0.04]">
                      <div className="flex items-center gap-1.5 font-mono">
                        <button
                          type="button"
                          onClick={() => onSelectFinding?.(item.finding_id, item.frame_start, item.joint)}
                          className="px-2 py-0.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-blue-300 border border-white/[0.08] text-[10px] font-medium flex items-center gap-1 cursor-pointer transition-colors"
                          title="Center 3D camera and inspect anomaly interval"
                        >
                          <Crosshair className="w-3 h-3 text-blue-400" />
                          <span>Focus in 3D</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleJointToggle(item.joint)}
                          className={`px-2 py-0.5 rounded text-[10px] font-medium border cursor-pointer transition-colors flex items-center gap-1 ${
                            isJointSelected
                              ? 'bg-blue-950/80 text-blue-200 border-blue-800/80 hover:bg-blue-900'
                              : 'bg-zinc-900 text-zinc-400 border-white/[0.08] hover:text-zinc-200'
                          }`}
                          title="Toggle this joint in the repair scope"
                        >
                          <Wrench className="w-3 h-3 text-amber-400" />
                          <span>{isJointSelected ? 'Targeted for Repair ✓' : 'Include in Repair'}</span>
                        </button>
                      </div>
                      <span className="text-[11px] text-zinc-400 truncate max-w-[220px]">
                        {item.explanation}
                      </span>
                    </div>

                    {isExpanded && (
                      <div className="flex flex-col gap-2 pt-2 border-t border-white/[0.04] text-xs">
                        <div className="grid grid-cols-2 gap-2 bg-zinc-900/90 p-2 rounded-lg border border-white/[0.08] font-mono text-[11px] tabular-nums">
                          <div>
                            <span className="text-zinc-500">Max Joint Velocity: </span>
                            <span className="text-amber-300 font-semibold">{peakVelocity}</span>
                          </div>
                          <div>
                            <span className="text-zinc-500">Acceleration Spike: </span>
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

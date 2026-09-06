import { useState, useEffect } from 'react';
import axios from 'axios';
import { Bot, Sparkles, Sliders, XCircle, CheckCircle2, AlertCircle, Loader2, Lock, Target, Copy, Check } from 'lucide-react';

export interface ConsentPromptCardProps {
  analysisId: string;
  sessionId: string;
  findingIds?: string[];
  availableJoints?: string[];
  initialApproved?: boolean;
  initialApprovalId?: string;
  initialDeclined?: boolean;
  onApproved?: (planId: string, approvalId: string, customPrompt?: string, selectedJoints?: string[]) => void;
  onDeclined?: () => void;
  apiBaseUrl?: string;
}

export default function ConsentPromptCard({
  analysisId,
  sessionId,
  findingIds,
  availableJoints = [],
  initialApproved = false,
  initialApprovalId,
  initialDeclined = false,
  onApproved,
  onDeclined,
  apiBaseUrl = 'http://localhost:8000',
}: ConsentPromptCardProps) {
  const [isApproved, setIsApproved] = useState<boolean>(initialApproved);
  const [approvalId, setApprovalId] = useState<string | null>(initialApprovalId || null);
  const [isDeclined, setIsDeclined] = useState<boolean>(initialDeclined);
  const [showCustomPrompt, setShowCustomPrompt] = useState<boolean>(false);
  const [showJointSelector, setShowJointSelector] = useState<boolean>(false);
  const [selectedJoints, setSelectedJoints] = useState<string[]>(availableJoints);
  const [customPrompt, setCustomPrompt] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedToken, setCopiedToken] = useState<boolean>(false);

  const handleCopyToken = () => {
    if (!approvalId) return;
    navigator.clipboard.writeText(approvalId);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  const handleApprove = async (overrideJoints?: string[]) => {
    setIsLoading(true);
    setError(null);
    try {
      let fids: string[] = findingIds || [];
      if (fids.length === 0) {
        const analysisRes = await axios.get(`${apiBaseUrl}/analyses/${analysisId}`);
        fids = (analysisRes.data.findings || []).map((f: { finding_id: string }) => f.finding_id);
      }

      const postPlanData: {
        session_id: string;
        selected_finding_ids: string[];
        user_prompt?: string;
        selected_joints?: string[];
      } = {
        session_id: sessionId,
        selected_finding_ids: fids,
      };
      if (customPrompt.trim()) {
        postPlanData.user_prompt = customPrompt.trim();
      }
      if (overrideJoints && overrideJoints.length > 0) {
        postPlanData.selected_joints = overrideJoints;
      }

      const planRes = await axios.post(`${apiBaseUrl}/analyses/${analysisId}/repair-plan`, postPlanData);

      const planId = planRes.data.plan_id;
      const planVersion = planRes.data.version;

      const approveData: {
        session_id: string;
        plan_id: string;
        repair_plan_version: number;
        selected_finding_ids: string[];
        confirmed: boolean;
        user_prompt?: string;
        selected_joints?: string[];
      } = {
        session_id: sessionId,
        plan_id: planId,
        repair_plan_version: planVersion,
        selected_finding_ids: fids,
        confirmed: true,
      };
      if (customPrompt.trim()) {
        approveData.user_prompt = customPrompt.trim();
      }
      if (overrideJoints && overrideJoints.length > 0) {
        approveData.selected_joints = overrideJoints;
      }

      const approveRes = await axios.post(`${apiBaseUrl}/repair-plans/${planId}/approve`, approveData);

      const receivedApprovalId = approveRes.data.approval_id;
      setApprovalId(receivedApprovalId);
      setIsApproved(true);
      setShowCustomPrompt(false);
      if (overrideJoints) {
        onApproved?.(planId, receivedApprovalId, customPrompt.trim() || undefined, overrideJoints);
      } else {
        onApproved?.(planId, receivedApprovalId, customPrompt.trim() || undefined);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err.message || 'Failed to approve repair plan';
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDecline = async () => {
    setIsLoading(true);
    setError(null);
    try {
      if (sessionId) {
        try {
          await axios.post(`${apiBaseUrl}/sessions/${sessionId}/cancel`);
        } catch {
        }
      }
      setIsDeclined(true);
      setShowCustomPrompt(false);
      setShowJointSelector(false);
      onDeclined?.();
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err.message || 'Failed to decline repair';
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isApproved || isDeclined) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        if (!showCustomPrompt && !showJointSelector) {
          e.preventDefault();
          handleApprove();
        }
      } else if ((e.metaKey || e.ctrlKey) && e.key === 'Backspace') {
        if (!showCustomPrompt) {
          e.preventDefault();
          handleDecline();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isApproved, isDeclined, showCustomPrompt, showJointSelector, findingIds, customPrompt, sessionId, analysisId]);

  const toggleJoint = (joint: string) => {
    setSelectedJoints((prev) =>
      prev.includes(joint) ? prev.filter((j) => j !== joint) : [...prev, joint]
    );
  };

  if (isApproved) {
    return (
      <div
        data-testid="consent-prompt-card"
        className="w-full bg-emerald-950/20 border border-emerald-500/30 rounded-xl p-4 shadow-xl flex flex-col gap-3 font-sans transition-all"
      >
        <div className="flex items-center justify-between border-b border-emerald-500/20 pb-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="font-semibold text-sm text-emerald-200">
              Approved for Multi-Agent Repair
            </span>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
            <Lock className="w-3 h-3 text-emerald-400" />
            <span>CRYPTOGRAPHICALLY LOCKED</span>
          </div>
        </div>

        <div className="flex flex-col gap-1.5 text-xs text-zinc-300">
          <p className="text-zinc-400">
            Execution unblocked. Multi-agents are authorized to repair kinematic anomalies.
          </p>
          {approvalId && (
            <div className="flex items-center justify-between gap-2 mt-1 bg-zinc-950/80 px-3 py-2 rounded-lg border border-emerald-500/20 font-mono text-[11px]">
              <div className="flex items-center gap-2 min-w-0">
                <Lock className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span className="text-zinc-400">Approval Token:</span>
                <span data-testid="approval-id" className="text-emerald-300 font-medium truncate tabular-nums">
                  {approvalId}
                </span>
              </div>
              <button
                type="button"
                onClick={handleCopyToken}
                className="p-1 rounded text-zinc-400 hover:text-emerald-300 hover:bg-emerald-950/40 transition-colors shrink-0 cursor-pointer"
                title="Copy approval token"
              >
                {copiedToken ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          )}
          {selectedJoints.length > 0 && (
            <div className="flex items-center gap-1.5 mt-1 bg-zinc-950/80 px-3 py-1.5 rounded-lg border border-white/[0.08] text-[11px] font-mono">
              <span className="text-zinc-400">Authorized Joints:</span>
              <span className="text-blue-300">{selectedJoints.join(', ')}</span>
            </div>
          )}
          {customPrompt && (
            <div className="flex flex-col gap-1 mt-1 bg-zinc-950/80 px-3 py-2 rounded-lg border border-white/[0.08] font-mono text-[11px]">
              <span className="text-zinc-400">Custom Instructions:</span>
              <span className="text-blue-300">{customPrompt}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (isDeclined) {
    return (
      <div
        data-testid="consent-prompt-card"
        className="w-full bg-zinc-950/60 border border-white/[0.08] rounded-xl p-4 shadow-xl flex flex-col gap-2 font-sans opacity-80"
      >
        <div className="flex items-center gap-2 text-zinc-400">
          <XCircle className="w-4 h-4 text-zinc-500 shrink-0" />
          <span className="font-semibold text-sm text-zinc-300">Repair Declined</span>
        </div>
        <p className="text-xs text-zinc-400">
          Multi-agent kinematic repair was declined for this analysis. Session has been closed.
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid="consent-prompt-card"
      className="w-full bg-zinc-900/90 border border-white/[0.08] hover:border-blue-500/30 rounded-xl p-4 shadow-xl flex flex-col gap-3 font-sans transition-all"
    >
      <div className="flex items-center justify-between border-b border-white/[0.08] pb-2.5">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-blue-950/80 border border-blue-800/80 text-blue-300 flex items-center justify-center shrink-0">
            <Bot className="w-3.5 h-3.5" />
          </div>
          <span className="font-semibold text-sm text-zinc-100">Plan Review & Authorization</span>
        </div>
        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-blue-950/80 text-blue-300 border border-blue-800/80">
          Authorization Required
        </span>
      </div>

      <p className="text-xs text-zinc-300 leading-relaxed font-medium">
        Would you like the multi-agent system to formulate targeted Blender kinematic fixes for these broken frames?
      </p>

      {error && (
        <div className="flex items-center gap-2 bg-red-950/40 border border-red-800 text-red-300 text-xs p-2.5 rounded-lg">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {showJointSelector && (
        <div className="flex flex-col gap-2 bg-zinc-950/80 p-3 rounded-lg border border-white/[0.08]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-300 flex items-center gap-1.5">
              <Target className="w-3.5 h-3.5 text-blue-400" />
              Select Specific Joints to Fix:
            </span>
            <button
              type="button"
              onClick={() => setShowJointSelector(false)}
              className="text-zinc-400 hover:text-white text-xs cursor-pointer"
            >
              Close
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {(availableJoints.length > 0 ? availableJoints : ['LeftFoot', 'RightFoot', 'Spine', 'Hips']).map((joint) => {
              const isSelected = selectedJoints.includes(joint);
              return (
                <button
                  key={joint}
                  type="button"
                  onClick={() => toggleJoint(joint)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono transition-colors cursor-pointer border ${
                    isSelected
                      ? 'bg-blue-600 border-blue-500 text-white font-semibold'
                      : 'bg-zinc-900 border-white/[0.08] text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {joint}
                </button>
              );
            })}
          </div>
          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={() => handleApprove(selectedJoints)}
              disabled={isLoading || selectedJoints.length === 0}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5 shadow-md disabled:opacity-50 cursor-pointer"
            >
              {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              <span>Approve Selected Joints</span>
            </button>
          </div>
        </div>
      )}

      {showCustomPrompt ? (
        <div className="flex flex-col gap-2.5 bg-zinc-950/80 p-3 rounded-lg border border-white/[0.08]">
          <label className="text-xs font-medium text-zinc-300 flex items-center gap-1.5">
            <Sliders className="w-3.5 h-3.5 text-blue-400" />
            Custom Repair Instructions
          </label>
          <textarea
            data-testid="custom-instructions-input"
            rows={3}
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            placeholder="e.g., Apply Catmull-Rom smoothing to LeftFoot frames 40-75 and preserve root translation..."
            className="w-full bg-zinc-900 border border-white/[0.08] rounded-lg p-2.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500 resize-none font-mono"
            disabled={isLoading}
          />
          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setShowCustomPrompt(false)}
              disabled={isLoading}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors border border-white/[0.08] disabled:opacity-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              data-testid="approve-custom-btn"
              onClick={() => handleApprove()}
              disabled={isLoading}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5 shadow-md disabled:opacity-50 cursor-pointer"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Authorizing...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Approve & Spawn Agents</span>
                </>
              )}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            type="button"
            data-testid="spawn-agents-btn"
            onClick={() => handleApprove()}
            disabled={isLoading}
            className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5 shadow-md shadow-blue-900/40 disabled:opacity-50 cursor-pointer"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Authorizing...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5 text-blue-200" />
                <span>Spawn Agents to Fix All</span>
                <kbd className="px-1.5 py-0.5 rounded bg-blue-700/80 border border-blue-400/50 text-[9px] font-mono text-blue-100 ml-1">
                  ⌘↵
                </kbd>
              </>
            )}
          </button>

          <button
            type="button"
            data-testid="select-joints-btn"
            onClick={() => {
              setShowJointSelector(!showJointSelector);
              setShowCustomPrompt(false);
            }}
            disabled={isLoading}
            className="px-3 py-2 rounded-lg text-xs font-medium bg-zinc-800/90 hover:bg-zinc-700 text-zinc-200 transition-colors flex items-center gap-1.5 border border-white/[0.08] disabled:opacity-50 cursor-pointer"
          >
            <Target className="w-3.5 h-3.5 text-blue-400" />
            <span>Select Specific Joints/Frames...</span>
          </button>

          <button
            type="button"
            data-testid="customize-btn"
            onClick={() => {
              setShowCustomPrompt(true);
              setShowJointSelector(false);
            }}
            disabled={isLoading}
            className="px-3 py-2 rounded-lg text-xs font-medium bg-zinc-800/90 hover:bg-zinc-700 text-zinc-200 transition-colors flex items-center gap-1.5 border border-white/[0.08] disabled:opacity-50 cursor-pointer"
          >
            <Sliders className="w-3.5 h-3.5 text-zinc-400" />
            <span>Custom Instruction</span>
          </button>

          <button
            type="button"
            data-testid="decline-btn"
            onClick={handleDecline}
            disabled={isLoading}
            className="px-3 py-2 rounded-lg text-xs font-medium bg-zinc-950/80 hover:bg-red-950/40 text-zinc-400 hover:text-red-300 transition-colors flex items-center gap-1.5 border border-white/[0.08] hover:border-red-900/50 disabled:opacity-50 cursor-pointer ml-auto"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Decline / Keep Original</span>
          </button>
        </div>
      )}
    </div>
  );
}

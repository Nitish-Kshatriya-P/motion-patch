import { useEffect, useRef } from 'react';
import type { DragEvent } from 'react';
import { Bot, Sparkles, UploadCloud } from 'lucide-react';
import DiagnosticCard, { type DiagnosticCardProps } from './DiagnosticCard';
import ConsentPromptCard from './ConsentPromptCard';
import DynamicAgentRosterCard, { type DynamicAgent } from './DynamicAgentRosterCard';
import RepairCompleteCard, { type RepairCompleteCardProps } from './RepairCompleteCard';

export interface ProposedPlanData {
  session_id?: string;
  selected_joints?: string[];
  user_prompt?: string;
  description?: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  timestamp: string;
  text?: string;
  diagnosticData?: DiagnosticCardProps;
  sessionId?: string;
  isApproved?: boolean;
  approvalId?: string;
  isDeclined?: boolean;
  agentRoster?: DynamicAgent[];
  repairData?: RepairCompleteCardProps;
  proposedPlan?: ProposedPlanData;
}

interface ChatStreamProps {
  messages: ChatMessage[];
  activeSessionId?: string | null;
  onSelectFinding?: (findingId: string, frameStart: number, joint?: string) => void;
  onDropFile?: (file: File) => void;
  isUploading?: boolean;
  isGenerating?: boolean;
  onApproveRepair?: (messageId: string, planId: string, approvalId: string, customPrompt?: string, selectedJoints?: string[]) => void;
  onDeclineRepair?: (messageId: string) => void;
  onInspectCode?: (scriptCode: string) => void;
  onAuthorizeProposedPlan?: (messageId: string, plan: ProposedPlanData) => void;
}

export default function ChatStream({
  messages,
  activeSessionId,
  onSelectFinding,
  onDropFile,
  isUploading,
  isGenerating,
  onApproveRepair,
  onDeclineRepair,
  onInspectCode,
  onAuthorizeProposedPlan,
}: ChatStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const dropZoneRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === 'function') {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isUploading, isGenerating]);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files?.[0];
    if (file && onDropFile) {
      onDropFile(file);
    }
  };

  const renderMessageText = (text: string) => {
    const regex = /(LeftFoot|RightFoot|LeftToeBase|RightToeBase|Spine|Hips|Neck|Head|frames?\s+\d+(?:-\d+)?)/gi;
    const parts = text.split(regex);
    return parts.map((part, i) => {
      const lower = part.toLowerCase();
      if (['leftfoot', 'rightfoot', 'lefttoebase', 'righttoebase', 'spine', 'hips', 'neck', 'head'].includes(lower)) {
        return (
          <button
            key={i}
            type="button"
            onClick={() => onSelectFinding?.('', 0, part)}
            className="inline-block px-1.5 py-0.5 mx-0.5 rounded bg-blue-950/80 text-blue-300 hover:bg-blue-900 hover:text-white border border-blue-800 text-[11px] font-mono cursor-pointer transition-colors"
            title={`Focus 3D Viewport on ${part}`}
          >
            {part}
          </button>
        );
      }
      const frameMatch = lower.match(/frames?\s+(\d+)(?:-(\d+))?/);
      if (frameMatch) {
        const frameNum = parseInt(frameMatch[1], 10);
        return (
          <button
            key={i}
            type="button"
            onClick={() => onSelectFinding?.('', frameNum)}
            className="inline-block px-1.5 py-0.5 mx-0.5 rounded bg-amber-950/80 text-amber-300 hover:bg-amber-900 hover:text-white border border-amber-800 text-[11px] font-mono cursor-pointer transition-colors"
            title={`Scrub timeline to frame ${frameNum}`}
          >
            {part}
          </button>
        );
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#0a0d14]">
      <div className="px-4 py-2.5 border-b border-white/[0.08] bg-[#0c101a]/90 backdrop-blur-md flex items-center justify-between shrink-0 select-none">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-blue-400" />
          <span className="font-semibold text-xs text-zinc-200 tracking-wide font-mono uppercase">Agent Inspector</span>
        </div>
        <div className="flex items-center gap-2">
          {activeSessionId && (
            <span className="text-[10px] font-mono text-zinc-400 font-medium truncate max-w-[90px] tabular-nums" title={activeSessionId}>
              #{activeSessionId.slice(0, 8)}
            </span>
          )}
        </div>
      </div>
      <div
        ref={dropZoneRef}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className="flex-1 overflow-y-auto px-3.5 py-4 flex flex-col gap-3 text-sm"
      >
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 gap-4 border border-dashed border-white/[0.08] rounded-2xl bg-[#0d1017]/60 my-auto select-none">
            <div className="w-12 h-12 rounded-2xl bg-blue-950/60 border border-blue-800/60 flex items-center justify-center text-blue-400 shadow-inner">
              <Sparkles className="w-6 h-6" />
            </div>
            <div className="flex flex-col gap-1 max-w-sm">
              <h3 className="font-semibold text-sm text-zinc-100 font-sans">Codex Kinematic Inspector</h3>
              <p className="text-xs text-zinc-400 leading-relaxed">
                Drop a <span className="text-blue-400 font-mono">.bvh</span> mocap clip or enter a prompt below to launch multi-agent diagnostic analysis.
              </p>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-zinc-400 font-mono mt-1 bg-zinc-900/80 px-3 py-1.5 rounded-lg border border-white/[0.08]">
              <UploadCloud className="w-3.5 h-3.5 text-blue-400" />
              <span>Drop BVH file or type instruction</span>
            </div>
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.sender === 'user';
            const formattedTime = msg.timestamp
              ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              : '';

            return (
              <div
                key={msg.id}
                data-testid={`chat-turn-${msg.id}`}
                className="w-full flex flex-col gap-1.5"
              >
                {formattedTime && (
                  <div className={`flex items-center text-[10px] font-mono text-zinc-500 select-none px-1 ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <span className="tabular-nums">{formattedTime}</span>
                  </div>
                )}

                <div className="w-full flex flex-col gap-2">
                  {msg.text && (
                    isUser ? (
                      <div
                        data-testid={`user-message-${msg.id}`}
                        className="w-full rounded-xl px-3.5 py-2.5 text-xs leading-relaxed bg-zinc-800/80 border border-white/[0.1] text-zinc-100 shadow-sm"
                      >
                        <div className="whitespace-pre-wrap">{renderMessageText(msg.text)}</div>
                      </div>
                    ) : (
                      <div
                        data-testid={`assistant-message-${msg.id}`}
                        className="w-full px-1 py-1 text-xs leading-relaxed text-zinc-200"
                      >
                        <div className="whitespace-pre-wrap">{renderMessageText(msg.text)}</div>
                      </div>
                    )
                  )}

                  {msg.proposedPlan && !msg.isApproved && (
                    <div className="w-full bg-blue-950/30 border border-blue-800/70 rounded-xl p-3 flex flex-col gap-2 shadow-lg">
                      <div className="flex items-center justify-between border-b border-blue-900/50 pb-2">
                        <div className="flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                          <span className="font-semibold text-xs text-blue-200">Proposed Targeted Repair Plan</span>
                        </div>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-blue-900/60 text-blue-300 border border-blue-700">
                          ACTIONABLE
                        </span>
                      </div>
                      <p className="text-xs text-zinc-300 leading-normal">{msg.proposedPlan.description}</p>
                      {msg.proposedPlan.selected_joints && msg.proposedPlan.selected_joints.length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-[10px] text-zinc-300 font-medium font-mono">Target Joints:</span>
                          {msg.proposedPlan.selected_joints.map((j) => (
                            <span key={j} className="px-2 py-0.5 rounded bg-zinc-900/90 border border-blue-800/60 text-blue-200 font-mono text-[10px] font-semibold">
                              {j}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="flex justify-end pt-1">
                        <button
                          type="button"
                          onClick={() => onAuthorizeProposedPlan?.(msg.id, msg.proposedPlan!)}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5 shadow-md cursor-pointer"
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Authorize Agents</span>
                        </button>
                      </div>
                    </div>
                  )}

                  {msg.diagnosticData && (
                    <div className="w-full flex flex-col gap-3">
                      <DiagnosticCard
                        {...msg.diagnosticData}
                        onSelectFinding={onSelectFinding}
                      />
                      {msg.diagnosticData.frameIntervals && msg.diagnosticData.frameIntervals.length > 0 && (
                        <ConsentPromptCard
                          analysisId={msg.diagnosticData.analysisId}
                          sessionId={msg.sessionId || msg.diagnosticData.sessionId || activeSessionId || ''}
                          findingIds={msg.diagnosticData.frameIntervals.map((f) => f.finding_id)}
                          availableJoints={msg.diagnosticData.brokenJoints}
                          initialApproved={msg.isApproved ?? msg.diagnosticData.isApproved}
                          initialApprovalId={msg.approvalId ?? msg.diagnosticData.approvalId}
                          initialDeclined={msg.isDeclined ?? msg.diagnosticData.isDeclined}
                          onApproved={(planId, approvalId, customPrompt, selectedJoints) => {
                            onApproveRepair?.(msg.id, planId, approvalId, customPrompt, selectedJoints);
                          }}
                          onDeclined={() => {
                            onDeclineRepair?.(msg.id);
                          }}
                        />
                      )}
                    </div>
                  )}

                  {msg.agentRoster && msg.agentRoster.length > 0 && (
                    <DynamicAgentRosterCard
                      agents={msg.agentRoster}
                      sessionId={msg.sessionId || activeSessionId || undefined}
                    />
                  )}

                  {msg.repairData && (
                    <RepairCompleteCard
                      {...msg.repairData}
                      onInspectCode={onInspectCode}
                    />
                  )}
                </div>
              </div>
            );
          })
        )}

        {isUploading && (
          <div className="flex items-center gap-2.5 bg-zinc-900 border border-blue-900/60 text-blue-300 px-3.5 py-2.5 rounded-xl shadow-lg w-fit text-xs">
            <div className="w-3.5 h-3.5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            <span className="font-medium">Analyzing BVH kinematics and inspecting joints...</span>
          </div>
        )}

        {isGenerating && (
          <div
            data-testid="generating-indicator"
            className="w-full flex flex-col gap-1.5"
          >
            <div className="flex items-center text-[11px] font-mono text-zinc-400 select-none px-1">
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-blue-400 bg-blue-950/60 border border-blue-800/50 px-2 py-0.5 rounded-full animate-pulse">
                <Sparkles className="w-2.5 h-2.5 animate-spin" />
                <span>Thinking...</span>
              </span>
            </div>

            <div className="w-full px-1 py-1 flex items-center justify-between gap-3 text-zinc-300">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1" aria-label="generating dots">
                  <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" />
                </div>
                <span className="text-xs text-zinc-300 font-medium">
                  Generating answer...
                </span>
              </div>
              <span className="text-[10px] font-mono text-zinc-500">
                Analyzing kinematics
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}

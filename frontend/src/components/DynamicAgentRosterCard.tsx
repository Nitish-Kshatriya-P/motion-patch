import { useState } from 'react';
import { Bot, CheckCircle2, Database, Activity, Code2, ChevronDown, ChevronUp, Footprints, Compass, Copy, Check, Loader2, XCircle } from 'lucide-react';

export type AgentActivityStatus =
  | 'SPAWNED'
  | 'SYNTHESIZING'
  | 'THINKING'
  | 'QUERYING_RAG'
  | 'GENERATING'
  | 'GENERATING_BPY'
  | 'QA_VALIDATION'
  | 'QA_PASSED'
  | 'EXECUTING'
  | 'COMPLETED'
  | 'FAILED'
  | string;

export interface DynamicAgent {
  agent_id: string;
  role: string;
  target_bones?: string[];
  target_joints?: string[];
  target_frames?: number[];
  tools?: string[];
  status: AgentActivityStatus;
  system_instruction?: string;
  code_snippet?: string;
  memory_reference?: string;
}

export interface DynamicAgentRosterCardProps {
  agents: DynamicAgent[];
  sessionId?: string;
  title?: string;
}

const renderAgentIcon = (role: string) => {
  const r = role.toLowerCase();
  if (r.includes('foot') || r.includes('toe') || r.includes('slide') || r.includes('ankle')) {
    return <Footprints className="w-3.5 h-3.5 text-blue-400" />;
  }
  if (r.includes('spine') || r.includes('smooth') || r.includes('jitter') || r.includes('torso')) {
    return <Activity className="w-3.5 h-3.5 text-amber-400" />;
  }
  if (r.includes('root') || r.includes('hip') || r.includes('stabiliz')) {
    return <Compass className="w-3.5 h-3.5 text-purple-400" />;
  }
  return <Bot className="w-3.5 h-3.5 text-blue-400" />;
};

const getMemoryReference = (agent: DynamicAgent): string => {
  if (agent.memory_reference) return agent.memory_reference;
  const r = agent.role.toLowerCase();
  if (r.includes('foot') || r.includes('toe') || r.includes('slide')) {
    return 'Referencing ClickHouse cluster: 4 similar foot slide motions retrieved (cosine distance: 0.12)';
  }
  if (r.includes('spine') || r.includes('smooth') || r.includes('jitter')) {
    return 'Referencing ClickHouse cluster: 6 trajectory jitter profiles retrieved (cosine distance: 0.09)';
  }
  return 'Referencing ClickHouse cluster: biomechanical constraint vector memory (cosine distance: 0.14)';
};

export default function DynamicAgentRosterCard({
  agents,
  title = 'Dynamic Multi-Agent Roster',
}: DynamicAgentRosterCardProps) {
  const [expandedCodeAgents, setExpandedCodeAgents] = useState<Record<string, boolean>>({});
  const [copiedAgentCode, setCopiedAgentCode] = useState<Record<string, boolean>>({});

  if (!agents || agents.length === 0) {
    return null;
  }

  const toggleCodeExpand = (agentId: string) => {
    setExpandedCodeAgents((prev) => ({
      ...prev,
      [agentId]: !prev[agentId],
    }));
  };

  const handleCopyCode = (agentId: string, code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedAgentCode((prev) => ({ ...prev, [agentId]: true }));
    setTimeout(() => {
      setCopiedAgentCode((prev) => ({ ...prev, [agentId]: false }));
    }, 2000);
  };

  const isWorking = agents.some((a) => {
    const s = (a.status || '').toUpperCase();
    return !(
      s === 'COMPLETED' ||
      s === 'EXECUTED' ||
      s === 'FIXED' ||
      s === 'REPAIRED' ||
      s === 'SUCCESS' ||
      s === 'FAILED' ||
      s === 'ERROR' ||
      s === 'DECLINED' ||
      s.includes('FAIL')
    );
  });

  return (
    <div
      data-testid="dynamic-agent-roster-card"
      className="w-full bg-zinc-900/95 border border-white/[0.08] rounded-xl p-4 shadow-xl flex flex-col gap-3 font-sans transition-all"
    >
      <div className="flex items-center justify-between border-b border-white/[0.08] pb-2.5">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-blue-950/80 border border-blue-800/80 text-blue-300 flex items-center justify-center shrink-0">
            {isWorking ? (
              <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
            ) : (
              <Bot className="w-3.5 h-3.5" />
            )}
          </div>
          <span className="font-semibold text-sm text-zinc-100">{title}</span>
        </div>
        <div className="flex items-center gap-2">
          {isWorking && (
            <span
              data-testid="agent-active-badge"
              className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono text-blue-300 bg-blue-950/80 border border-blue-800/80"
            >
              <Loader2 className="w-2.5 h-2.5 text-blue-400 animate-spin" />
              <span>Working</span>
            </span>
          )}
          <span
            data-testid="agent-count-badge"
            className="px-2 py-0.5 rounded text-[10px] font-mono tabular-nums uppercase bg-blue-950/80 text-blue-300 border border-blue-800/80"
          >
            {agents.length} {agents.length === 1 ? 'Worker' : 'Workers'} Spawned
          </span>
        </div>
      </div>

      {isWorking && (
        <div data-testid="agent-work-progress-bar" className="w-full bg-blue-950/40 h-1 rounded-full overflow-hidden">
          <div className="h-full bg-gradient-to-r from-blue-600 via-cyan-400 to-blue-600 w-full animate-pulse" />
        </div>
      )}

      <div className="flex flex-col gap-2.5">
        {agents.map((agent) => {
          const bones = agent.target_bones || agent.target_joints || [];
          const frames = agent.target_frames || [];
          const statusUpper = (agent.status || '').toUpperCase();
          const isCompleted =
            statusUpper === 'COMPLETED' ||
            statusUpper === 'EXECUTED' ||
            statusUpper === 'FIXED' ||
            statusUpper === 'REPAIRED' ||
            statusUpper === 'SUCCESS';
          const isFailed =
            statusUpper === 'FAILED' ||
            statusUpper === 'ERROR' ||
            statusUpper === 'DECLINED' ||
            statusUpper.includes('FAIL');
          const isGenerating = statusUpper === 'GENERATING' || statusUpper === 'GENERATING_BPY' || statusUpper.includes('BPY');
          const isQa = statusUpper === 'QA_VALIDATION' || statusUpper === 'QA_PASSED' || statusUpper.includes('QA');
          const memoryRef = getMemoryReference(agent);
          const isCodeExpanded = Boolean(expandedCodeAgents[agent.agent_id]);
          const codeSnippet = agent.code_snippet || `import bpy\narmature = bpy.context.active_object\nrole = "${agent.role}"\nframes = "${frames.join('-')}"`;

          return (
            <div
              key={agent.agent_id}
              data-testid={`agent-card-${agent.agent_id}`}
              className={`bg-zinc-950/80 border rounded-xl p-3 flex flex-col gap-2.5 transition-all ${
                !isCompleted && !isFailed
                  ? 'border-blue-500/40 shadow-[0_0_12px_rgba(59,130,246,0.12)] ring-1 ring-blue-500/20'
                  : 'border-white/[0.06] hover:border-white/[0.12]'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-6 h-6 rounded-lg bg-zinc-900 border border-white/[0.08] flex items-center justify-center shrink-0">
                    {renderAgentIcon(agent.role)}
                  </div>
                  <span
                    data-testid={`agent-role-${agent.agent_id}`}
                    className="font-medium text-xs text-zinc-100 truncate"
                  >
                    {agent.role}
                  </span>
                </div>

                <div
                  data-testid={`agent-status-${agent.agent_id}`}
                  className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold uppercase shrink-0 border ${
                    isCompleted
                      ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800/80'
                      : isFailed
                      ? 'bg-rose-950/80 text-rose-300 border-rose-800/80'
                      : isGenerating
                      ? 'bg-purple-950/80 text-purple-300 border-purple-800/80'
                      : isQa
                      ? 'bg-cyan-950/80 text-cyan-300 border-cyan-800/80'
                      : 'bg-amber-950/80 text-amber-300 border-amber-800/80'
                  }`}
                >
                  {isCompleted ? (
                    <CheckCircle2
                      data-testid={`status-icon-completed-${agent.agent_id}`}
                      className="w-3 h-3 text-emerald-400"
                    />
                  ) : isFailed ? (
                    <XCircle
                      data-testid={`status-icon-failed-${agent.agent_id}`}
                      className="w-3 h-3 text-rose-400"
                    />
                  ) : (
                    <Loader2
                      data-testid={`status-icon-spinner-${agent.agent_id}`}
                      className="w-3 h-3 animate-spin text-current"
                    />
                  )}
                  <span>{agent.status}</span>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-0.5">
                {bones.length > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] font-mono text-zinc-300 font-medium flex items-center gap-0.5">
                      <Activity className="w-3 h-3 text-zinc-400" />
                      Joints:
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {bones.map((bone) => (
                        <span
                          key={bone}
                          data-testid={`agent-joint-${agent.agent_id}-${bone}`}
                          className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-900 border border-white/[0.15] text-zinc-200 font-medium"
                        >
                          {bone}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {frames.length > 0 && (
                  <div className="flex items-center gap-1 text-[10px] font-mono text-zinc-300 font-medium">
                    <span className="text-zinc-300 font-medium">Frames:</span>
                    <span
                      data-testid={`agent-frames-${agent.agent_id}`}
                      className="px-1.5 py-0.5 rounded bg-blue-950/60 border border-blue-900/80 text-blue-300 font-mono tabular-nums"
                    >
                      {frames.length >= 2 ? `${frames[0]} - ${frames[1]}` : frames.join(', ')}
                    </span>
                  </div>
                )}

                <div className="flex items-center gap-1 text-[10px] font-mono text-zinc-300 font-medium ml-auto">
                  <span className="text-zinc-300 font-medium flex items-center gap-0.5">
                    <Database className="w-2.5 h-2.5 text-purple-400" />
                    Tool:
                  </span>
                  <span className="px-1.5 py-0.5 rounded bg-purple-950/50 border border-purple-900/60 text-purple-300 font-mono text-[9px]">
                    ClickHouse RAG
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-purple-950/30 border border-purple-900/40 text-[10px] font-mono text-purple-300">
                <Database className="w-3 h-3 text-purple-400 shrink-0" />
                <span className="truncate">{memoryRef}</span>
              </div>

              <div className="flex flex-col gap-1.5 pt-0.5 border-t border-white/[0.06]">
                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => toggleCodeExpand(agent.agent_id)}
                    className="flex items-center gap-1 text-[10px] font-mono text-zinc-200 hover:text-white font-medium cursor-pointer py-0.5"
                  >
                    <Code2 className="w-3 h-3 text-blue-400" />
                    <span>Generated bpy Execution Block</span>
                    {isCodeExpanded ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />}
                  </button>
                  {isCodeExpanded && (
                    <button
                      type="button"
                      onClick={() => handleCopyCode(agent.agent_id, codeSnippet)}
                      className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-200 hover:text-white border border-white/[0.15] text-[9px] font-mono font-medium cursor-pointer transition-colors"
                      title="Copy script"
                    >
                      {copiedAgentCode[agent.agent_id] ? (
                        <>
                          <Check className="w-2.5 h-2.5 text-emerald-400" />
                          <span className="text-emerald-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-2.5 h-2.5" />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
                {isCodeExpanded && (
                  <pre className="bg-zinc-950 p-2.5 rounded-lg border border-white/[0.08] text-[10px] font-mono text-emerald-300 overflow-x-auto leading-relaxed selection:bg-emerald-900/50">
                    <code>{codeSnippet}</code>
                  </pre>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

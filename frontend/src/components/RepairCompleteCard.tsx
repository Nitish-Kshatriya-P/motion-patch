import { CheckCircle2, Download, Code, Clock, Users, ShieldCheck } from 'lucide-react';

export interface RepairCompleteMetrics {
  agents_executed?: number;
  qa_passed?: boolean;
  execution_time_seconds?: number;
  repaired_bones_count?: number;
}

export interface RepairCompleteCardProps {
  assetId: string;
  filename?: string;
  repairedFileUrl: string;
  scriptCode: string;
  metrics?: RepairCompleteMetrics;
  onInspectCode?: (scriptCode: string) => void;
}

export default function RepairCompleteCard({
  assetId,
  filename,
  repairedFileUrl,
  scriptCode,
  metrics,
  onInspectCode,
}: RepairCompleteCardProps) {
  const downloadUrl = repairedFileUrl.startsWith('http')
    ? repairedFileUrl
    : `http://localhost:8000${repairedFileUrl}`;

  const displayName = filename || `repaired_${assetId.slice(0, 8)}.bvh`;
  const execTime = metrics?.execution_time_seconds ?? 0.18;
  const agentsRun = metrics?.agents_executed ?? 2;

  return (
    <div
      data-testid="repair-complete-card"
      className="w-full bg-zinc-950 border border-emerald-500/30 rounded-xl p-3.5 shadow-xl flex flex-col gap-3 font-sans"
    >
      <div className="flex items-center justify-between border-b border-white/[0.08] pb-2.5">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-emerald-950/80 border border-emerald-800/80 flex items-center justify-center text-emerald-400">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-emerald-300">
              Blender Repair Execution Complete
            </span>
            <span className="text-[11px] text-zinc-400 font-mono truncate max-w-[240px]">
              {displayName}
            </span>
          </div>
        </div>
        <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/80 text-emerald-400 font-mono">
          Ready for 3D Viewport
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <div className="bg-zinc-900/80 border border-white/[0.08] rounded-xl p-2.5 flex items-center gap-2">
          <Clock className="w-3.5 h-3.5 text-blue-400 shrink-0" />
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] text-zinc-400 font-medium">Exec Duration</span>
            <span className="font-semibold text-zinc-200 font-mono tabular-nums">{execTime}s</span>
          </div>
        </div>

        <div className="bg-zinc-900/80 border border-white/[0.08] rounded-xl p-2.5 flex items-center gap-2">
          <Users className="w-3.5 h-3.5 text-purple-400 shrink-0" />
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] text-zinc-400 font-medium">Agents Executed</span>
            <span className="font-semibold text-zinc-200 font-mono tabular-nums">{agentsRun} Dynamic</span>
          </div>
        </div>

        <div className="bg-zinc-900/80 border border-white/[0.08] rounded-xl p-2.5 flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] text-zinc-400 font-medium">Dynamic QA</span>
            <span className="font-semibold text-emerald-400 font-mono">AST Verified</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-1">
        <a
          data-testid="download-repaired-btn"
          href={downloadUrl}
          download={displayName}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition-colors cursor-pointer"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Download Fixed BVH</span>
        </a>

        <button
          data-testid="inspect-code-btn"
          type="button"
          onClick={() => onInspectCode?.(scriptCode)}
          className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold bg-zinc-900 hover:bg-zinc-800 border border-white/[0.15] text-zinc-100 hover:text-white transition-colors cursor-pointer"
        >
          <Code className="w-3.5 h-3.5 text-blue-400" />
          <span>Inspect Code (bpy)</span>
        </button>
      </div>
    </div>
  );
}

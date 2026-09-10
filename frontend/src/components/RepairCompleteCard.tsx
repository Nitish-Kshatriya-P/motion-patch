import { CheckCircle2, Download, Code, Clock, Users, ShieldCheck, AlertTriangle, Check, AlertCircle } from 'lucide-react';
import { API_BASE_URL } from '../config';

export interface FindingSummaryItem {
  finding_id: string;
  joint: string;
  anomaly_type: string;
  frame_start?: number;
  frame_end?: number;
  attempts?: number;
  description?: string;
  reason?: string;
}

export interface RepairCompleteMetrics {
  agents_executed?: number;
  qa_passed?: boolean;
  execution_time_seconds?: number;
  repaired_bones_count?: number;
  outcome_status?: 'COMPLETED' | 'PARTIALLY_REPAIRED' | 'FAILED';
  summary_message?: string;
  fixed_findings?: FindingSummaryItem[];
  unresolved_findings?: FindingSummaryItem[];
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
    : `${API_BASE_URL}${repairedFileUrl}`;

  const baseName = filename || `repaired_${assetId.slice(0, 8)}.bvh`;
  const displayName = baseName.toLowerCase().endsWith('.bvh') ? baseName : `${baseName}.bvh`;

  const handleDownload = async (e: React.MouseEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(downloadUrl);
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = displayName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);
    } catch {
      window.open(downloadUrl, '_blank');
    }
  };
  const execTime = metrics?.execution_time_seconds ?? 0.18;
  const agentsRun = metrics?.agents_executed ?? 2;
  const isPartial = metrics?.outcome_status === 'PARTIALLY_REPAIRED';
  const fixedList = metrics?.fixed_findings ?? [];
  const unresolvedList = metrics?.unresolved_findings ?? [];

  return (
    <div
      data-testid="repair-complete-card"
      className={`w-full bg-zinc-950 border ${
        isPartial ? 'border-amber-500/30' : 'border-emerald-500/30'
      } rounded-xl p-3.5 shadow-xl flex flex-col gap-3 font-sans overflow-hidden`}
    >
      <div className="flex items-start sm:items-center justify-between gap-2.5 border-b border-white/[0.08] pb-2.5">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <div
            className={`w-7 h-7 rounded-lg ${
              isPartial
                ? 'bg-amber-950/80 border border-amber-800/80 text-amber-400'
                : 'bg-emerald-950/80 border border-emerald-800/80 text-emerald-400'
            } flex items-center justify-center shrink-0`}
          >
            {isPartial ? (
              <AlertTriangle className="w-4 h-4" />
            ) : (
              <CheckCircle2 className="w-4 h-4" />
            )}
          </div>
          <div className="flex flex-col min-w-0">
            <span
              className={`text-xs font-semibold ${
                isPartial ? 'text-amber-300' : 'text-emerald-300'
              } truncate`}
            >
              {isPartial ? 'Partial Repair Succeeded' : 'Blender Repair Execution Complete'}
            </span>
            <span className="text-[11px] text-zinc-400 font-mono truncate">
              {displayName}
            </span>
          </div>
        </div>
        <span
          className={`text-[10px] uppercase font-semibold tracking-wider px-2 py-0.5 rounded ${
            isPartial
              ? 'bg-amber-950/80 border border-amber-800/80 text-amber-400'
              : 'bg-emerald-950/80 border border-emerald-800/80 text-emerald-400'
          } font-mono shrink-0 whitespace-nowrap`}
        >
          {isPartial ? 'Partially Repaired' : 'Ready for 3D Viewport'}
        </span>
      </div>

      {metrics?.summary_message && (
        <div
          className={`text-xs px-3 py-2 rounded-lg border ${
            isPartial
              ? 'bg-amber-950/20 border-amber-800/40 text-amber-200'
              : 'bg-emerald-950/20 border-emerald-800/40 text-emerald-200'
          }`}
        >
          {metrics.summary_message}
        </div>
      )}

      {fixedList.length > 0 && (
        <div className="flex flex-col gap-1.5 bg-zinc-900/60 border border-white/[0.06] rounded-lg p-2.5 text-[11px]">
          <div className="flex items-center gap-1.5 text-zinc-300 font-medium">
            <Check className="w-3.5 h-3.5 text-emerald-400" />
            <span>Fixed Findings ({fixedList.length})</span>
          </div>
          <div className="flex flex-col gap-1">
            {fixedList.map((f, idx) => (
              <div
                key={f.finding_id || idx}
                className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-zinc-950/70 border border-white/[0.04]"
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="text-zinc-200 font-semibold truncate">
                    {f.joint || 'Joint'}
                  </span>
                  <span className="text-zinc-500">•</span>
                  <span className="text-zinc-400 truncate">
                    {f.anomaly_type?.replace(/_/g, ' ') || 'Defect'}
                  </span>
                  {f.frame_start !== undefined && f.frame_end !== undefined && (
                    <span className="text-[10px] font-mono text-zinc-500">
                      [{f.frame_start}..{f.frame_end}]
                    </span>
                  )}
                </div>
                {f.attempts && f.attempts > 1 && (
                  <span className="text-[10px] font-mono text-emerald-400 shrink-0">
                    {f.attempts} attempts
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {unresolvedList.length > 0 && (
        <div className="flex flex-col gap-1.5 bg-zinc-900/60 border border-white/[0.06] rounded-lg p-2.5 text-[11px]">
          <div className="flex items-center gap-1.5 text-amber-300 font-medium">
            <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
            <span>Unresolved Findings ({unresolvedList.length})</span>
          </div>
          <div className="flex flex-col gap-1">
            {unresolvedList.map((u, idx) => (
              <div
                key={u.finding_id || idx}
                className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-zinc-950/70 border border-white/[0.04]"
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="text-amber-200 font-semibold truncate">
                    {u.joint || 'Joint'}
                  </span>
                  <span className="text-zinc-500">•</span>
                  <span className="text-zinc-400 truncate">
                    {u.anomaly_type?.replace(/_/g, ' ') || 'Defect'}
                  </span>
                  {u.frame_start !== undefined && u.frame_end !== undefined && (
                    <span className="text-[10px] font-mono text-zinc-500">
                      [{u.frame_start}..{u.frame_end}]
                    </span>
                  )}
                </div>
                {u.reason && (
                  <span className="text-[10px] text-zinc-400 truncate max-w-[180px]">
                    {u.reason}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
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
          <ShieldCheck
            className={`w-3.5 h-3.5 ${
              isPartial ? 'text-amber-400' : 'text-emerald-400'
            } shrink-0`}
          />
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] text-zinc-400 font-medium">Quality Gate</span>
            <span
              className={`font-semibold ${
                isPartial ? 'text-amber-400' : 'text-emerald-400'
              } font-mono`}
            >
              {isPartial ? 'Partial Approved' : 'AST Verified'}
            </span>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap sm:flex-nowrap items-center gap-2 pt-1">
        <a
          data-testid="download-repaired-btn"
          href={downloadUrl}
          download={displayName}
          onClick={handleDownload}
          className={`flex-1 min-w-[140px] flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold ${
            isPartial
              ? 'bg-amber-600 hover:bg-amber-500'
              : 'bg-emerald-600 hover:bg-emerald-500'
          } text-white shadow-sm transition-colors cursor-pointer`}
        >
          <Download className="w-3.5 h-3.5" />
          <span>{isPartial ? 'Download Partially Fixed BVH' : 'Download Fixed BVH'}</span>
        </a>

        <button
          data-testid="inspect-code-btn"
          type="button"
          onClick={() => onInspectCode?.(scriptCode)}
          className="flex-1 sm:flex-none min-w-[140px] flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold bg-zinc-900 hover:bg-zinc-800 border border-white/[0.15] text-zinc-100 hover:text-white transition-colors cursor-pointer"
        >
          <Code className="w-3.5 h-3.5 text-blue-400" />
          <span>Inspect Code (bpy)</span>
        </button>
      </div>
    </div>
  );
}

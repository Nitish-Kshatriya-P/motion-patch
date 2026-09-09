import { useState } from 'react';
import {
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Search,
} from 'lucide-react';

export interface SessionSummary {
  session_id: string;
  asset_id: string;
  original_asset_id?: string | null;
  repaired_asset_id?: string | null;
  analysis_id: string;
  plan_id?: string | null;
  approval_id?: string | null;
  lifecycle_state: string;
  created_at: string;
  updated_at: string;
  filename: string;
  title?: string | null;
  duration_seconds: number;
  frame_count: number;
  findings_count: number;
  status: string;
  diagnostic_summary?: string | null;
}

export function isUuidLike(value?: string | null): boolean {
  if (!value) return false;
  const s = value.replace(/\.[^/.]+$/, '').trim();
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s)) {
    return true;
  }
  if (/^[0-9a-f]{16,}$/i.test(s)) {
    return true;
  }
  return false;
}

export function formatSessionTitle(session: SessionSummary): string {
  if (session.title && session.title.trim() && !isUuidLike(session.title)) {
    return session.title.trim();
  }

  if (session.filename && !isUuidLike(session.filename)) {
    return session.filename;
  }

  if (session.diagnostic_summary) {
    const match = session.diagnostic_summary.match(/-\s*([A-Za-z0-9_]+):\s*frames\s*[\d-]+\s*\(([^,)]+)/);
    if (match) {
      const joint = match[1];
      const anomaly = match[2].replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      return `${joint} ${anomaly}`;
    }
  }

  if (session.findings_count > 0) {
    return `${session.findings_count} Kinematic ${session.findings_count === 1 ? 'Fault' : 'Faults'}`;
  }

  if (session.status === 'CLEAN' || (!session.status && session.findings_count === 0)) {
    if (session.frame_count > 0) {
      return `Clean Take (${session.frame_count}f)`;
    }
    return 'Clean Motion Take';
  }

  if (session.status === 'INCONCLUSIVE') {
    if (session.frame_count > 0) {
      return `Inconclusive Scan (${session.frame_count}f)`;
    }
    return 'Inconclusive Take';
  }

  return 'Motion Capture Take';
}

interface SessionSidebarProps {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelectSession: (session: SessionSummary) => void;
  onNewSession: () => void;
  isOpen: boolean;
  onToggleOpen: () => void;
  isLoading?: boolean;
}

export default function SessionSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  isOpen,
  onToggleOpen,
  isLoading,
}: SessionSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  const filteredSessions = sessions.filter((s) => {
    const title = formatSessionTitle(s);
    const query = searchQuery.toLowerCase();
    return (
      title.toLowerCase().includes(query) ||
      s.filename.toLowerCase().includes(query)
    );
  });

  if (!isOpen) {
    return (
      <div className="w-13 shrink-0 bg-[#0a0d14] border-r border-white/[0.08] flex flex-col items-center py-3 gap-3 select-none z-20">
        <button
          type="button"
          onClick={onToggleOpen}
          className="p-2 text-zinc-400 hover:text-white hover:bg-white/[0.06] rounded-xl transition-all cursor-pointer"
          title="Expand sidebar (Cmd+B)"
        >
          <PanelLeftOpen className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={onNewSession}
          className="p-2 text-blue-400 hover:text-white hover:bg-blue-600 rounded-xl transition-all cursor-pointer shadow-xs"
          title="New thread (Cmd+N)"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <aside className="w-72 shrink-0 bg-[#090c13] border-r border-white/[0.08] flex flex-col h-full select-none z-20">
      <div className="flex items-center justify-between px-3.5 py-3 border-b border-white/[0.08]">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-xs tracking-wider uppercase text-zinc-400 font-mono">Threads</span>
          <span className="px-1.5 py-0.2 rounded-full bg-white/[0.06] text-zinc-400 text-[10px] font-mono tabular-nums">
            {sessions.length}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onNewSession}
            className="flex items-center gap-1 bg-blue-600 hover:bg-blue-500 text-white px-2.5 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer shadow-[0_0_12px_rgba(37,99,235,0.3)]"
            title="Start new thread (Cmd+N)"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New</span>
          </button>
          <button
            type="button"
            onClick={onToggleOpen}
            className="p-1.5 text-zinc-400 hover:text-white hover:bg-white/[0.06] rounded-lg transition-colors cursor-pointer"
            title="Collapse sidebar (Cmd+B)"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="p-2.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 bg-zinc-950/80 border border-white/[0.08] px-2.5 py-1.5 rounded-xl text-xs focus-within:border-blue-500/80 transition-colors">
          <Search className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search threads..."
            className="w-full bg-transparent text-xs text-zinc-200 placeholder-zinc-500 outline-none"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5">
        {isLoading && sessions.length === 0 ? (
          <div className="text-center text-xs text-zinc-500 py-8 font-mono">Loading threads...</div>
        ) : filteredSessions.length === 0 ? (
          <div className="text-center text-xs text-zinc-500 py-8 px-4 leading-relaxed">
            {searchQuery ? 'No matching threads found.' : 'No previous sessions. Drop a BVH file to begin.'}
          </div>
        ) : (
          filteredSessions.map((session) => {
            const isActive = session.session_id === activeSessionId;
            const isClean = session.status === 'CLEAN' || session.findings_count === 0;
            const displayTitle = formatSessionTitle(session);

            return (
              <button
                key={session.session_id}
                type="button"
                onClick={() => onSelectSession(session)}
                className={`w-full text-left p-2.5 rounded-xl border transition-all flex flex-col gap-1.5 cursor-pointer relative ${
                  isActive
                    ? 'bg-zinc-900/90 border-blue-500/80 text-white shadow-lg shadow-black/40'
                    : 'bg-zinc-900/30 border-white/[0.05] text-zinc-300 hover:bg-zinc-800/40 hover:border-white/[0.12]'
                }`}
              >
                {isActive && (
                  <span className="absolute left-0 top-2 bottom-2 w-1 bg-blue-500 rounded-r" />
                )}
                <div className="flex items-center justify-between gap-1 w-full pl-1">
                  <span className="font-medium text-xs truncate text-zinc-100" title={displayTitle}>
                    {displayTitle}
                  </span>
                  {isClean ? (
                    <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-medium shrink-0 bg-emerald-950/60 border border-emerald-800/60 px-1.5 py-0.2 rounded-full">
                      <CheckCircle2 className="w-3 h-3" />
                      Clean
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[10px] text-red-400 font-medium shrink-0 bg-red-950/60 border border-red-800/60 px-1.5 py-0.2 rounded-full">
                      <AlertTriangle className="w-3 h-3" />
                      {session.findings_count}
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono tabular-nums pl-1">
                  <div className="flex items-center gap-1">
                    <Clock className="w-3 h-3 text-zinc-500" />
                    <span>{formatTime(session.created_at)}</span>
                  </div>
                  <span>
                    {session.duration_seconds > 0 ? `${session.duration_seconds.toFixed(1)}s` : ''}
                    {session.frame_count > 0 ? ` · ${session.frame_count}f` : ''}
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}

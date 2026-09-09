import { useState, useMemo } from 'react';
import {
  Clock,
  CheckCircle2,
  AlertTriangle,
  Search,
  ArrowRight,
  Sparkles,
  ChevronDown,
  ChevronUp,
  X,
} from 'lucide-react';
import { formatSessionTitle, type SessionSummary } from './SessionSidebar';

interface HomepageThreadHistoryProps {
  sessions: SessionSummary[];
  onSelectSession: (session: SessionSummary) => void;
  isLoading?: boolean;
}

export default function HomepageThreadHistory({
  sessions,
  onSelectSession,
  isLoading,
}: HomepageThreadHistoryProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'faults' | 'clean'>('all');
  const [isExpanded, setIsExpanded] = useState(false);

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

  const filteredSessions = useMemo(() => {
    return sessions.filter((s) => {
      const isClean = s.status === 'CLEAN' || s.findings_count === 0;
      if (statusFilter === 'clean' && !isClean) return false;
      if (statusFilter === 'faults' && isClean) return false;

      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      const title = formatSessionTitle(s).toLowerCase();
      const filename = (s.filename || '').toLowerCase();
      return title.includes(q) || filename.includes(q);
    });
  }, [sessions, searchQuery, statusFilter]);

  const faultCount = useMemo(
    () => sessions.filter((s) => s.status !== 'CLEAN' && s.findings_count > 0).length,
    [sessions]
  );
  const cleanCount = useMemo(
    () => sessions.filter((s) => s.status === 'CLEAN' || s.findings_count === 0).length,
    [sessions]
  );

  const displayedSessions = isExpanded
    ? filteredSessions
    : filteredSessions.slice(0, 6);

  if (isLoading && sessions.length === 0) {
    return (
      <div className="w-full text-center py-6 text-xs text-zinc-500 font-mono">
        Loading previous threads...
      </div>
    );
  }

  if (sessions.length === 0) {
    return null;
  }

  return (
    <div className="w-full bg-[#0c1018]/90 border border-white/[0.08] rounded-2xl p-4 flex flex-col gap-3.5 backdrop-blur-md shadow-xl text-left">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div className="flex items-center gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 font-mono">
              Recent Motion Threads
            </h2>
            <span className="px-1.5 py-0.2 rounded-full bg-white/[0.06] text-zinc-400 text-[10px] font-mono tabular-nums">
              {sessions.length}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center bg-zinc-950/80 border border-white/[0.08] px-2.5 py-1 rounded-lg text-xs focus-within:border-blue-500/80 transition-colors w-full sm:w-48">
            <Search className="w-3 h-3 text-zinc-500 shrink-0 mr-1.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search history..."
              className="w-full bg-transparent text-xs text-zinc-200 placeholder-zinc-500 outline-none"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="text-zinc-500 hover:text-zinc-300 ml-1 cursor-pointer"
                title="Clear search"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setStatusFilter('all')}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all cursor-pointer ${
              statusFilter === 'all'
                ? 'bg-blue-600 text-white shadow-xs'
                : 'bg-white/[0.04] text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.08]'
            }`}
          >
            All ({sessions.length})
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter('faults')}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all cursor-pointer flex items-center gap-1 ${
              statusFilter === 'faults'
                ? 'bg-red-600/90 text-white shadow-xs'
                : 'bg-white/[0.04] text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.08]'
            }`}
          >
            <AlertTriangle className="w-3 h-3 text-red-400" />
            <span>Faults ({faultCount})</span>
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter('clean')}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all cursor-pointer flex items-center gap-1 ${
              statusFilter === 'clean'
                ? 'bg-emerald-600/90 text-white shadow-xs'
                : 'bg-white/[0.04] text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.08]'
            }`}
          >
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span>Clean ({cleanCount})</span>
          </button>
        </div>

        {filteredSessions.length > 6 && (
          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300 font-medium transition-colors cursor-pointer"
          >
            <span>{isExpanded ? 'Show fewer' : `Show all (${filteredSessions.length})`}</span>
            {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>

      {filteredSessions.length === 0 ? (
        <div className="text-center py-8 text-xs text-zinc-500">
          No threads match your current filter or search criteria.
        </div>
      ) : (
        <div
          className={`grid grid-cols-1 sm:grid-cols-2 gap-2.5 ${
            isExpanded ? 'max-h-96 overflow-y-auto pr-1' : ''
          }`}
        >
          {displayedSessions.map((session) => {
            const title = formatSessionTitle(session);
            const isClean = session.status === 'CLEAN' || session.findings_count === 0;

            return (
              <button
                key={session.session_id}
                type="button"
                onClick={() => onSelectSession(session)}
                className="w-full text-left p-3 rounded-xl bg-zinc-900/40 hover:bg-zinc-800/60 border border-white/[0.06] hover:border-blue-500/50 transition-all duration-150 flex flex-col gap-2 cursor-pointer group relative overflow-hidden"
              >
                <div className="flex items-center justify-between gap-1.5 w-full">
                  <span
                    className="font-medium text-xs text-zinc-100 group-hover:text-white truncate"
                    title={title}
                  >
                    {title}
                  </span>
                  <div className="shrink-0">
                    {isClean ? (
                      <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-medium bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded-full">
                        <CheckCircle2 className="w-3 h-3" />
                        Clean
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] text-red-400 font-medium bg-red-950/60 border border-red-800/60 px-2 py-0.5 rounded-full">
                        <AlertTriangle className="w-3 h-3" />
                        {session.findings_count} {session.findings_count === 1 ? 'Fault' : 'Faults'}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono tabular-nums">
                  <div className="flex items-center gap-1">
                    <Clock className="w-3 h-3 text-zinc-500" />
                    <span>{formatTime(session.created_at)}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span>
                      {session.duration_seconds > 0 ? `${session.duration_seconds.toFixed(1)}s` : ''}
                      {session.frame_count > 0 ? ` · ${session.frame_count}f` : ''}
                    </span>
                    <ArrowRight className="w-3 h-3 text-zinc-500 group-hover:text-blue-400 group-hover:translate-x-0.5 transition-all opacity-0 group-hover:opacity-100" />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

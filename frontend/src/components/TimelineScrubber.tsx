import { Play, Pause, SkipBack, SkipForward, Repeat } from 'lucide-react';
import type { FindingItem } from './DiagnosticCard';

export interface TimelineScrubberProps {
  currentFrame: number;
  totalFrames: number;
  fps?: number;
  isPlaying: boolean;
  isLooping: boolean;
  playbackRate: number;
  brokenIntervals?: FindingItem[];
  onSeek: (frame: number) => void;
  onTogglePlay: () => void;
  onStepForward: () => void;
  onStepBackward: () => void;
  onToggleLoop: () => void;
  onChangePlaybackRate: (rate: number) => void;
  onSelectInterval?: (intervalId: string, frameStart: number) => void;
}

export default function TimelineScrubber({
  currentFrame,
  totalFrames,
  fps = 30,
  isPlaying,
  isLooping,
  playbackRate,
  brokenIntervals = [],
  onSeek,
  onTogglePlay,
  onStepForward,
  onStepBackward,
  onToggleLoop,
  onChangePlaybackRate,
  onSelectInterval,
}: TimelineScrubberProps) {
  const safeTotalFrames = Math.max(1, totalFrames);
  const clampedFrame = Math.max(0, Math.min(currentFrame, safeTotalFrames - 1));
  const progressPercent = safeTotalFrames > 1 ? (clampedFrame / (safeTotalFrames - 1)) * 100 : 0;
  const currentTimeSec = (clampedFrame / fps).toFixed(2);
  const totalTimeSec = ((safeTotalFrames - 1) / fps).toFixed(2);

  const getMarkerColorClass = (severity: string) => {
    switch (severity.toUpperCase()) {
      case 'CRITICAL':
      case 'HIGH':
        return 'bg-red-500/90 hover:bg-red-400 border-red-400/80';
      case 'MEDIUM':
        return 'bg-amber-500/90 hover:bg-amber-400 border-amber-400/80';
      default:
        return 'bg-blue-500/90 hover:bg-blue-400 border-blue-400/80';
    }
  };

  const handleMarkerClick = (e: React.MouseEvent, interval: FindingItem) => {
    e.stopPropagation();
    onSeek(interval.frame_start);
    onSelectInterval?.(interval.finding_id, interval.frame_start);
  };

  const speedOptions = [0.5, 1.0, 2.0];

  return (
    <div
      data-testid="timeline-scrubber"
      className="w-full bg-zinc-950/80 backdrop-blur-xl border-t border-white/[0.08] px-4 py-2.5 flex flex-col gap-2 select-none z-20 font-sans"
    >
      <div className="relative w-full h-7 flex items-center">
        <div
          data-testid="scrubber-track"
          className="relative w-full h-2.5 bg-zinc-900/90 border border-white/[0.06] rounded-full overflow-hidden flex items-center cursor-pointer shadow-inner"
        >
          {brokenIntervals.map((interval) => {
            const leftPct = safeTotalFrames > 1 ? (interval.frame_start / (safeTotalFrames - 1)) * 100 : 0;
            const spanFrames = Math.max(1, interval.frame_end - interval.frame_start + 1);
            const widthPct = Math.max(1.5, safeTotalFrames > 1 ? (spanFrames / (safeTotalFrames - 1)) * 100 : 2);
            return (
              <div
                key={interval.finding_id}
                data-testid="marker-band"
                data-severity={interval.severity.toLowerCase()}
                onClick={(e) => handleMarkerClick(e, interval)}
                title={`${interval.joint} (${interval.severity}): frames ${interval.frame_start}-${interval.frame_end}`}
                style={{
                  left: `${Math.min(98.5, leftPct)}%`,
                  width: `${Math.min(100 - leftPct, widthPct)}%`,
                }}
                className={`absolute top-0 bottom-0 z-10 border-x cursor-pointer transition-opacity opacity-85 hover:opacity-100 ${getMarkerColorClass(
                  interval.severity
                )}`}
              />
            );
          })}

          <div
            style={{ width: `${progressPercent}%` }}
            className="h-full bg-blue-500/50 pointer-events-none rounded-full"
          />
        </div>

        <input
          data-testid="scrubber-slider"
          type="range"
          min={0}
          max={safeTotalFrames - 1}
          value={clampedFrame}
          onInput={(e) => onSeek(Number((e.target as HTMLInputElement).value))}
          onChange={(e) => onSeek(Number(e.target.value))}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
          aria-label="Timeline Scrubber"
        />

        <div
          style={{ left: `${progressPercent}%` }}
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3.5 h-3.5 bg-white border border-blue-500/50 rounded-full shadow-[0_0_10px_rgba(59,130,246,0.5)] pointer-events-none z-15"
        />
      </div>

      <div className="flex items-center justify-between text-xs text-zinc-300">
        <div className="flex items-center gap-1.5">
          <button
            data-testid="play-pause-btn"
            onClick={onTogglePlay}
            className="p-1.5 rounded-lg bg-zinc-900/80 border border-white/[0.08] text-zinc-200 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
          </button>

          <button
            data-testid="step-back-btn"
            onClick={onStepBackward}
            className="p-1.5 rounded-lg bg-zinc-900/80 border border-white/[0.08] text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Step back 1 frame"
          >
            <SkipBack className="w-3.5 h-3.5" />
          </button>

          <button
            data-testid="step-forward-btn"
            onClick={onStepForward}
            className="p-1.5 rounded-lg bg-zinc-900/80 border border-white/[0.08] text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Step forward 1 frame"
          >
            <SkipForward className="w-3.5 h-3.5" />
          </button>

          <button
            data-testid="loop-toggle-btn"
            onClick={onToggleLoop}
            className={`p-1.5 rounded-lg border transition-colors cursor-pointer ${
              isLooping
                ? 'bg-blue-950/80 text-blue-400 border-blue-800/80'
                : 'bg-zinc-900/80 text-zinc-500 border-white/[0.08] hover:text-zinc-300 hover:bg-zinc-800'
            }`}
            title={isLooping ? 'Loop enabled' : 'Loop disabled'}
          >
            <Repeat className="w-3.5 h-3.5" />
          </button>

          <div
            data-testid="frame-counter"
            className="ml-2 font-mono tabular-nums text-[11px] text-zinc-300 bg-zinc-900/80 backdrop-blur-md px-2.5 py-1 rounded-lg border border-white/[0.08] flex items-center gap-1.5 shadow-xs"
          >
            <span className="text-zinc-500 font-sans">Frame</span>
            <span className="font-semibold text-blue-400">{clampedFrame}</span>
            <span className="text-zinc-600">/</span>
            <span className="text-zinc-400">{safeTotalFrames - 1}</span>
            <span className="text-zinc-700">|</span>
            <span className="text-zinc-400 font-mono text-[10px]">
              {currentTimeSec}s / {totalTimeSec}s
            </span>
          </div>
        </div>

        <div className="flex items-center gap-0.5 bg-zinc-900/80 p-0.5 rounded-lg border border-white/[0.08] shadow-xs">
          {speedOptions.map((speed) => (
            <button
              key={speed}
              data-testid={`speed-${speed}x`}
              onClick={() => onChangePlaybackRate(speed)}
              className={`px-2 py-0.5 rounded text-[11px] font-mono tabular-nums transition-colors cursor-pointer ${
                playbackRate === speed
                  ? 'bg-blue-600 text-white font-semibold shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {speed}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

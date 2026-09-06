import { useEffect } from 'react';
import { Layers, CheckCircle2, Ghost, Lock } from 'lucide-react';
import * as THREE from 'three';

export type ComparisonMode = 'original' | 'repaired' | 'ghost';

export interface ComparisonControlsProps {
  mode: ComparisonMode;
  onModeChange: (mode: ComparisonMode) => void;
  originalBvhId?: string | null;
  repairedBvhId?: string | null;
  fps?: number;
  currentFrame?: number;
}

export function syncMixerTime(
  mixer: THREE.AnimationMixer | null,
  action: THREE.AnimationAction | null,
  frame: number,
  fps: number,
  duration: number
): number {
  const safeFps = fps > 0 ? fps : 30;
  const safeDuration = duration > 0 ? duration : 0;
  const targetTime = Math.min(Math.max(0, frame / safeFps), safeDuration);
  if (action) {
    const wasPaused = action.paused;
    action.paused = false;
    action.time = targetTime;
    if (mixer) {
      mixer.setTime(targetTime);
      mixer.update(0.00001);
    }
    action.paused = wasPaused;
    action.time = targetTime;
  } else if (mixer) {
    mixer.setTime(targetTime);
    mixer.update(0.00001);
  }
  return targetTime;
}

export default function ComparisonControls({
  mode,
  onModeChange,
  originalBvhId,
  repairedBvhId,
  fps = 30,
  currentFrame = 0,
}: ComparisonControlsProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || '').toLowerCase();
      if (activeTag === 'input' || activeTag === 'textarea' || (document.activeElement as HTMLElement)?.isContentEditable) {
        return;
      }
      if (e.key === 'a' || e.key === 'A' || e.key === '1') {
        onModeChange('original');
      } else if (e.key === 'b' || e.key === 'B' || e.key === '2') {
        onModeChange('repaired');
      } else if (e.key === 'g' || e.key === 'G' || e.key === '3') {
        onModeChange('ghost');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onModeChange]);

  if (!repairedBvhId) {
    return null;
  }

  return (
    <div
      data-testid="comparison-controls"
      data-original-id={originalBvhId || undefined}
      data-current-frame={currentFrame}
      className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex flex-col items-center gap-1.5"
    >
      <div className="flex items-center bg-zinc-950/80 backdrop-blur-2xl p-1 rounded-2xl border border-white/[0.08] shadow-2xl gap-1 select-none">
        <button
          data-testid="mode-original-btn"
          type="button"
          onClick={() => onModeChange('original')}
          className={`px-3 py-1.5 text-xs font-medium rounded-xl transition-all flex items-center gap-1.5 cursor-pointer ${
            mode === 'original'
              ? 'bg-blue-600 text-white shadow-[0_0_12px_rgba(37,99,235,0.4)]'
              : 'text-zinc-300 hover:text-white hover:bg-white/[0.08]'
          }`}
          title="Switch to original motion clip (Key: A or 1)"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Original (A)</span>
        </button>

        <button
          data-testid="mode-repaired-btn"
          type="button"
          onClick={() => onModeChange('repaired')}
          className={`px-3 py-1.5 text-xs font-medium rounded-xl transition-all flex items-center gap-1.5 cursor-pointer ${
            mode === 'repaired'
              ? 'bg-emerald-600 text-white shadow-[0_0_12px_rgba(16,185,129,0.4)]'
              : 'text-zinc-300 hover:text-white hover:bg-white/[0.08]'
          }`}
          title="Switch to repaired motion clip (Key: B or 2)"
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Repaired (B)</span>
        </button>

        <button
          data-testid="mode-ghost-btn"
          type="button"
          onClick={() => onModeChange('ghost')}
          className={`px-3 py-1.5 text-xs font-medium rounded-xl transition-all flex items-center gap-1.5 cursor-pointer ${
            mode === 'ghost'
              ? 'bg-purple-600 text-white shadow-[0_0_12px_rgba(168,85,247,0.4)] ring-1 ring-purple-400/40'
              : 'text-zinc-300 hover:text-white hover:bg-white/[0.08]'
          }`}
          title="Compare original ghost overlay with repaired primary skeleton (Key: G or 3)"
        >
          <Ghost className="w-3.5 h-3.5" />
          <span>Ghost Compare (A/B)</span>
        </button>
      </div>

      {mode === 'ghost' && (
        <div
          data-testid="ghost-legend"
          className="flex items-center gap-3 px-3 py-1 bg-zinc-950/80 backdrop-blur-xl rounded-full border border-white/[0.08] text-[10px] font-mono shadow-lg text-zinc-300 animate-in fade-in duration-200"
        >
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400/90 shadow-[0_0_6px_rgba(251,191,36,0.6)]" />
            <span className="text-amber-300">Original Ghost (45%)</span>
          </div>
          <span className="text-zinc-700">|</span>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]" />
            <span className="text-emerald-300">Repaired Solid</span>
          </div>
          <span className="text-zinc-700">|</span>
          <div className="flex items-center gap-1 text-zinc-300 font-medium">
            <Lock className="w-3.5 h-3.5 text-purple-400" />
            <span>Lockstep Sync ({fps} FPS)</span>
          </div>
        </div>
      )}
    </div>
  );
}

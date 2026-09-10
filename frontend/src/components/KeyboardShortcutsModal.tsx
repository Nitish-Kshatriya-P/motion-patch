import React, { useEffect } from 'react';
import { X, Keyboard, Play, Target, Sparkles, Layers } from 'lucide-react';

interface KeyboardShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ShortcutItem {
  keys: string[];
  description: string;
}

interface ShortcutCategory {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  items: ShortcutItem[];
}

const SHORTCUT_CATEGORIES: ShortcutCategory[] = [
  {
    title: 'Playback & 3D Viewport',
    icon: Play,
    items: [
      { keys: ['Space'], description: 'Play or pause 3D skeletal playback' },
      { keys: ['←', '→'], description: 'Step backward or forward by 1 frame' },
      { keys: ['Shift', '← / →'], description: 'Jump backward or forward by 10 frames' },
      { keys: ['Home', 'End'], description: 'Jump to the first or last frame' },
      { keys: ['L'], description: 'Toggle animation playback looping' },
      { keys: ['R'], description: 'Reset 3D camera orbit position' },
      { keys: ['[', ']'], description: 'Decrease or increase playback speed (0.25x - 4x)' },
      { keys: ['A', 'B', 'G'], description: 'Switch mode: Original (A), Repaired (B), Ghost (G)' },
    ],
  },
  {
    title: 'Plan Review & Authorization Card',
    icon: Sparkles,
    items: [
      { keys: ['⌘', '↵'], description: 'Approve repair plan and spawn agents (all views)' },
      { keys: ['1'], description: 'Spawn agents to fix all detected faults' },
      { keys: ['2'], description: 'Open specific joints and frames selector' },
      { keys: ['3'], description: 'Open custom repair instructions editor' },
      { keys: ['4', 'Esc'], description: 'Decline repair and keep original BVH' },
    ],
  },
  {
    title: 'Kinematic Diagnosis Findings',
    icon: Target,
    items: [
      { keys: ['Enter'], description: 'Focus 3D camera on fault interval and highlight bone' },
      { keys: ['Space'], description: 'Toggle joint inclusion in targeted repair plan' },
    ],
  },
  {
    title: 'Global Navigation & Studio',
    icon: Layers,
    items: [
      { keys: ['⌘ / Ctrl', 'B'], description: 'Toggle session sidebar' },
      { keys: ['⌘ / Ctrl', 'N'], description: 'New session and clear workspace' },
      { keys: ['⌘ / Ctrl', 'I'], description: 'Inspect generated Python script drawer' },
      { keys: ['?'], description: 'Toggle this keyboard shortcuts guide' },
      { keys: ['Esc'], description: 'Close any active modal or drawer' },
    ],
  },
];

export default function KeyboardShortcutsModal({ isOpen, onClose }: KeyboardShortcutsModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      data-testid="keyboard-shortcuts-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-150"
    >
      <div className="bg-[#0c1017] border border-white/[0.1] rounded-2xl max-w-2xl w-full p-6 shadow-2xl flex flex-col gap-5 text-white max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
              <Keyboard className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold font-display tracking-tight text-white">
                Keyboard Controls
              </h2>
              <p className="text-xs text-zinc-400">
                Workstation hotkeys for high-speed motion analysis and multi-agent repair.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-white/[0.08] transition-colors cursor-pointer"
            title="Close (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {SHORTCUT_CATEGORIES.map((category) => {
            const Icon = category.icon;
            return (
              <div
                key={category.title}
                className="flex flex-col gap-2.5 bg-zinc-950/70 border border-white/[0.06] rounded-xl p-3.5"
              >
                <div className="flex items-center gap-2 text-xs font-semibold text-zinc-200">
                  <Icon className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                  <span>{category.title}</span>
                </div>
                <div className="flex flex-col gap-2">
                  {category.items.map((item, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between gap-2 text-[11px]"
                    >
                      <span className="text-zinc-400 leading-tight flex-1">
                        {item.description}
                      </span>
                      <div className="flex items-center gap-1 shrink-0">
                        {item.keys.map((k, kIdx) => (
                          <kbd
                            key={kIdx}
                            className="px-1.5 py-0.5 rounded bg-zinc-900 border border-white/[0.12] font-mono text-[10px] text-zinc-200 shadow-xs"
                          >
                            {k}
                          </kbd>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-between border-t border-white/[0.08] pt-3 text-xs text-zinc-500">
          <span>Press <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-white/[0.12] font-mono text-[10px] text-zinc-300">?</kbd> at any time to toggle this guide</span>
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 hover:text-white transition-colors text-xs font-medium cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

import React from 'react';
import MotionPatchLogo, { type LogoVariant } from './MotionPatchLogo';

interface BrandStudioModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeVariant: LogoVariant;
  onSelectVariant: (variant: LogoVariant) => void;
}

const VARIANTS: Array<{
  id: LogoVariant;
  name: string;
  tag: string;
  desc: string;
}> = [
  {
    id: 'hexacore',
    name: 'HexaCore',
    tag: '3D Spatial Joint',
    desc: 'Isometric coordinate frame with 1.2px optical gutters and central kinematic node.',
  },
  {
    id: 'apex',
    name: 'Apex Delta',
    tag: 'High Velocity',
    desc: 'Precision aerodynamic chevron with forward kinetic vector and suture stabilizer.',
  },
  {
    id: 'tangent',
    name: 'Harmonic Tangent',
    tag: 'Continuous Orbit',
    desc: 'Dual hyperbolic velocity curves meeting in tangency for smooth trajectory flow.',
  },
  {
    id: 'ribbon',
    name: 'Kinematic Ribbon',
    tag: 'M-P Monogram',
    desc: 'Unbroken planar ribbon that forms both the letter M and P in a single path.',
  },
  {
    id: 'suture',
    name: 'Euler Suture',
    tag: 'Continuity Loop',
    desc: 'Topological loop with cross-frame bridge eliminating angular discontinuities.',
  },
];

export const BrandStudioModal: React.FC<BrandStudioModalProps> = ({
  isOpen,
  onClose,
  activeVariant,
  onSelectVariant,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-150">
      <div className="bg-[#0c1017] border border-white/[0.1] rounded-2xl max-w-2xl w-full p-6 shadow-2xl flex flex-col gap-5 text-white">
        <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-[0_0_14px_rgba(37,99,235,0.4)]">
              <MotionPatchLogo variant={activeVariant} size={18} className="text-white" />
            </div>
            <div>
              <h2 className="font-display font-bold text-base tracking-tight text-white">Brand Symbol Studio</h2>
              <p className="text-xs text-zinc-400">Select a minimal, modern mark for MotionPatch</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors text-xs font-mono"
            aria-label="Close brand modal"
          >
            Esc &times;
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {VARIANTS.map((item) => {
            const isSelected = activeVariant === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  onSelectVariant(item.id);
                  try {
                    localStorage.setItem('motionpatch_logo_variant', item.id);
                  } catch {
                    // ignore
                  }
                }}
                className={`flex items-start gap-3.5 p-3.5 rounded-xl text-left border transition-all duration-150 ${
                  isSelected
                    ? 'bg-blue-950/40 border-blue-500/50 shadow-[0_0_16px_rgba(37,99,235,0.2)]'
                    : 'bg-zinc-900/50 border-white/[0.06] hover:bg-zinc-900 hover:border-white/[0.12]'
                }`}
              >
                <div
                  className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 transition-colors ${
                    isSelected ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40' : 'bg-white/[0.04] text-zinc-300'
                  }`}
                >
                  <MotionPatchLogo variant={item.id} size={22} />
                </div>
                <div className="flex flex-col gap-0.5 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-xs tracking-tight text-white">{item.name}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-white/[0.08] text-zinc-300 font-mono font-medium">
                      {item.tag}
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-300 leading-snug line-clamp-2 mt-0.5 font-medium">{item.desc}</p>
                </div>
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-white/[0.08] text-xs">
          <a
            href="/logo-showcase.html"
            target="_blank"
            rel="noreferrer"
            className="text-blue-400 hover:text-blue-300 font-medium inline-flex items-center gap-1 transition-colors"
          >
            Launch Full Brand Showcase &rarr;
          </a>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white font-medium text-xs border border-white/[0.15] transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export default BrandStudioModal;

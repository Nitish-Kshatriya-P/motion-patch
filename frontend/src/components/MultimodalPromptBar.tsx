import { useState, useRef, useEffect } from 'react';
import type { KeyboardEvent, ChangeEvent, DragEvent, MouseEvent, WheelEvent } from 'react';
import { ArrowUp, Paperclip, X, Footprints, Activity, Compass, FileSearch, Sparkles, ShieldCheck, Download, Gauge } from 'lucide-react';
import HoldToSpeakButton from './HoldToSpeakButton';

interface MultimodalPromptBarProps {
  onSendMessage: (text: string, audio?: Blob | null) => void;
  onFileUpload: (file: File, userPrompt?: string) => void;
  disabled?: boolean;
  isGenerating?: boolean;
  externalStagedFile?: File | null;
  onClearExternalStagedFile?: () => void;
  diagnosticStatus?: string | null;
  hasAnomalies?: boolean;
  anomalyTypes?: string[];
}

export default function MultimodalPromptBar({
  onSendMessage,
  onFileUpload,
  disabled,
  isGenerating,
  externalStagedFile,
  onClearExternalStagedFile,
  diagnosticStatus,
  hasAnomalies,
}: MultimodalPromptBarProps) {
  const [prompt, setPrompt] = useState('');
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [internalStagedFile, setInternalStagedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const stagedFile = externalStagedFile ?? internalStagedFile;

  const clearStaged = () => {
    setInternalStagedFile(null);
    onClearExternalStagedFile?.();
  };

  const [isDraggingChips, setIsDraggingChips] = useState(false);
  const [startX, setStartX] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [dragDistance, setDragDistance] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chipsContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      const targetHeight = Math.min(Math.max(scrollHeight, 40), 180);
      textareaRef.current.style.height = `${targetHeight}px`;
    }
  }, [prompt]);

  const handleSend = () => {
    if ((!prompt.trim() && !audioBlob && !stagedFile) || disabled) return;
    const currentPrompt = prompt.trim();
    if (stagedFile) {
      onFileUpload(stagedFile, currentPrompt);
      clearStaged();
      setPrompt('');
      setAudioBlob(null);
      return;
    }
    if (currentPrompt || audioBlob) {
      onSendMessage(currentPrompt, audioBlob);
      setPrompt('');
      setAudioBlob(null);
    }
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSend();
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.name.toLowerCase().endsWith('.bvh')) {
      setInternalStagedFile(file);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.name.toLowerCase().endsWith('.bvh')) {
      setInternalStagedFile(file);
    }
  };

  const handleChipsWheel = (e: WheelEvent<HTMLDivElement>) => {
    if (chipsContainerRef.current && e.deltaY !== 0) {
      chipsContainerRef.current.scrollLeft += e.deltaY;
    }
  };

  const handleMouseDown = (e: MouseEvent<HTMLDivElement>) => {
    if (!chipsContainerRef.current) return;
    setIsDraggingChips(true);
    setStartX(e.pageX - chipsContainerRef.current.offsetLeft);
    setScrollLeft(chipsContainerRef.current.scrollLeft);
    setDragDistance(0);
  };

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!isDraggingChips || !chipsContainerRef.current) return;
    e.preventDefault();
    const x = e.pageX - chipsContainerRef.current.offsetLeft;
    const walk = (x - startX) * 1.5;
    chipsContainerRef.current.scrollLeft = scrollLeft - walk;
    setDragDistance(Math.abs(x - startX));
  };

  const handleMouseUpOrLeave = () => {
    setIsDraggingChips(false);
  };

  const handleChipClick = (actionText: string) => {
    if (dragDistance < 5 && !disabled) {
      onSendMessage(actionText, null);
    }
  };

  const canSubmit = Boolean(prompt.trim() || audioBlob || stagedFile) && !disabled && !isGenerating;

  const quickActions = hasAnomalies
    ? [
        { label: 'Fix Foot Sliding Only', text: 'Fix foot sliding only', Icon: Footprints },
        { label: 'Smooth Spine Jitter', text: 'Smooth spine jitter', Icon: Activity },
        { label: 'Stabilize Root Motion', text: 'Stabilize root motion', Icon: Compass },
        { label: 'Explain Anomaly Causes', text: 'Explain kinematic anomaly causes', Icon: FileSearch },
      ]
    : diagnosticStatus === 'CLEAN'
    ? [
        { label: 'Explain Kinematic Baseline', text: 'Explain kinematic baseline constraints and verification', Icon: ShieldCheck },
        { label: 'Stress-Test Velocity Limits', text: 'Stress-test acceleration limits and joint velocity thresholds', Icon: Gauge },
        { label: 'Export Verified BVH', text: 'Export verified clean BVH clip', Icon: Download },
        { label: 'Explain Anomaly Causes', text: 'Explain kinematic anomaly detection parameters', Icon: FileSearch },
      ]
    : [
        { label: 'Fix Foot Sliding Only', text: 'Fix foot sliding only', Icon: Footprints },
        { label: 'Smooth Spine Jitter', text: 'Smooth spine jitter', Icon: Activity },
        { label: 'Stabilize Root Motion', text: 'Stabilize root motion', Icon: Compass },
        { label: 'Explain Anomaly Causes', text: 'Explain kinematic anomaly causes', Icon: FileSearch },
      ];

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`p-3 bg-[#080b11] border-t border-white/[0.08] transition-all flex flex-col gap-2 select-none ${
        isDragOver ? 'bg-blue-950/20 border-blue-500/80' : ''
      }`}
    >
      <div
        ref={chipsContainerRef}
        onWheel={handleChipsWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUpOrLeave}
        onMouseLeave={handleMouseUpOrLeave}
        className="flex items-center gap-1.5 overflow-x-auto pb-0.5 cursor-grab active:cursor-grabbing no-scrollbar"
      >
        {quickActions.map((action) => {
          const Icon = action.Icon;
          return (
            <button
              key={action.text}
              type="button"
              disabled={disabled}
              onClick={() => handleChipClick(action.text)}
              className="whitespace-nowrap px-2.5 py-1 rounded-full text-[11px] font-medium bg-zinc-900/80 hover:bg-zinc-800 text-zinc-300 hover:text-white border border-white/[0.06] hover:border-blue-500/40 transition-all shrink-0 disabled:opacity-50 cursor-pointer flex items-center gap-1.5 shadow-xs"
            >
              <Icon className="w-3 h-3 text-blue-400 shrink-0" />
              <span>{action.label}</span>
            </button>
          );
        })}
      </div>

      {stagedFile && (
        <div className="flex items-center justify-between gap-2 px-3 py-1.5 rounded-xl bg-blue-950/50 border border-blue-800/80 text-blue-200 text-xs font-mono">
          <div className="flex items-center gap-2 min-w-0">
            <Paperclip className="w-3.5 h-3.5 text-blue-400 shrink-0" />
            <span className="font-medium truncate">{stagedFile.name}</span>
            <span className="text-[10px] text-zinc-400 shrink-0 tabular-nums">
              ({(stagedFile.size / 1024).toFixed(1)} KB)
            </span>
          </div>
          <button
            type="button"
            onClick={clearStaged}
            className="p-1 rounded-md text-zinc-400 hover:text-white hover:bg-white/[0.08] transition-colors cursor-pointer"
            title="Remove staged file"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {audioError && (
        <div className="px-3 py-1.5 rounded-xl bg-red-950/80 border border-red-800 text-red-300 text-xs flex justify-between items-center">
          <span>{audioError}</span>
          <button onClick={() => setAudioError(null)} className="text-red-400 hover:text-white cursor-pointer">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {audioBlob && (
        <div className="px-3 py-1.5 rounded-xl bg-emerald-950/70 border border-emerald-800/80 text-emerald-300 text-xs flex justify-between items-center">
          <span>Audio recording captured and staged for transmission</span>
          <button
            onClick={() => setAudioBlob(null)}
            className="text-emerald-400 hover:text-white p-0.5 rounded cursor-pointer"
            title="Discard audio"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <div className="flex flex-col bg-zinc-900/90 border border-white/[0.08] rounded-2xl p-2.5 focus-within:border-white/[0.2] focus-within:ring-1 focus-within:ring-white/[0.1] transition-all shadow-xl select-text">
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          accept=".bvh"
          className="hidden"
        />

        <textarea
          ref={textareaRef}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || isGenerating}
          placeholder={
            stagedFile
              ? "Press Enter to inspect staged BVH or add repair prompt..."
              : "Ask MotionPatch AI or describe kinematic adjustments..."
          }
          className="w-full min-h-[40px] max-h-[180px] bg-transparent text-zinc-100 placeholder-zinc-500 text-xs outline-none resize-none px-1 py-0.5 leading-relaxed font-sans"
        />

        <div className="flex items-center justify-between pt-2 border-t border-white/[0.04] mt-1 select-none">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled || isGenerating}
              className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.06] rounded-lg transition-colors shrink-0 disabled:opacity-50 cursor-pointer flex items-center gap-1 text-[11px]"
              title="Attach .bvh file"
            >
              <Paperclip className="w-3.5 h-3.5" />
              <span className="text-zinc-500 text-[10px] font-mono">BVH</span>
            </button>

            <HoldToSpeakButton
              onRecordingComplete={(blob) => setAudioBlob(blob)}
              onError={(msg) => setAudioError(msg)}
              disabled={disabled || isGenerating || false}
            />

            {isGenerating && (
              <span
                data-testid="prompt-generating-badge"
                className="inline-flex items-center gap-1.5 text-[10px] font-mono text-blue-400 ml-1 bg-blue-950/60 border border-blue-800/50 px-2 py-0.5 rounded-full animate-pulse"
              >
                <Sparkles className="w-2.5 h-2.5 animate-spin" />
                <span>Generating answer...</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-[10px] font-mono text-zinc-400">
              <span className="text-[9px]">⌘</span>↵
            </kbd>
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSubmit}
              className="w-7 h-7 bg-white text-zinc-950 hover:bg-zinc-200 disabled:bg-zinc-800 disabled:text-zinc-600 rounded-full flex items-center justify-center transition-all cursor-pointer shadow-md disabled:cursor-not-allowed"
              title={
                isGenerating
                  ? "Generating answer..."
                  : stagedFile
                  ? "Upload and analyze staged file"
                  : "Send message"
              }
            >
              {isGenerating ? (
                <div
                  data-testid="prompt-generating-spinner"
                  className="w-3.5 h-3.5 border-2 border-zinc-600 border-t-zinc-200 rounded-full animate-spin"
                />
              ) : (
                <ArrowUp className="w-3.5 h-3.5 stroke-[2]" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

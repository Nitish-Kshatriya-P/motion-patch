import { useState, useEffect, lazy, Suspense } from 'react';
import { Terminal, Play, Copy, Check, RotateCcw, X, Loader2 } from 'lucide-react';

const Editor = lazy(() => import('@monaco-editor/react'));

export interface WhiteBoxCodeDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  initialScript: string;
  onExecuteScript?: (script: string) => Promise<void> | void;
  isExecuting?: boolean;
  title?: string;
}

export default function WhiteBoxCodeDrawer({
  isOpen,
  onClose,
  initialScript,
  onExecuteScript,
  isExecuting = false,
  title = 'White-Box Blender Inspector (bpy)',
}: WhiteBoxCodeDrawerProps) {
  const [code, setCode] = useState<string>(initialScript || '');
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    setCode(initialScript || '');
  }, [initialScript]);

  if (!isOpen) {
    return null;
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const handleReset = () => {
    setCode(initialScript || '');
  };

  const handleRun = () => {
    if (!isExecuting && onExecuteScript) {
      onExecuteScript(code);
    }
  };

  return (
    <div
      data-testid="white-box-code-drawer"
      className="fixed inset-y-0 right-0 z-50 w-full sm:w-[640px] md:w-[720px] bg-zinc-950 border-l border-white/[0.08] shadow-2xl flex flex-col transition-all duration-300 animate-in slide-in-from-right"
    >
      <div className="h-13 border-b border-white/[0.08] px-4 bg-zinc-950/90 backdrop-blur-xl flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-blue-950/80 border border-blue-800/80 flex items-center justify-center text-blue-400">
            <Terminal className="w-4 h-4" />
          </div>
          <div className="flex flex-col">
            <h3 className="text-xs font-semibold text-zinc-100 leading-none">{title}</h3>
            <span className="text-[10px] text-zinc-500 font-mono mt-1">Python 3.x / bpy Sandboxed Engine</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            data-testid="reset-script-btn"
            type="button"
            onClick={handleReset}
            title="Reset code to generated state"
            className="p-1.5 rounded-lg bg-zinc-900 border border-white/[0.15] text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <button
            data-testid="copy-script-btn"
            type="button"
            onClick={handleCopy}
            title="Copy script to clipboard"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-zinc-900 border border-white/[0.15] text-zinc-200 hover:text-white hover:bg-zinc-800 text-xs font-medium transition-colors cursor-pointer"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-[11px] text-emerald-400 font-medium">Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5 text-zinc-300" />
                <span className="text-[11px]">Copy</span>
              </>
            )}
          </button>

          <button
            data-testid="run-script-btn"
            type="button"
            onClick={handleRun}
            disabled={isExecuting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-blue-950 disabled:text-zinc-500 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer disabled:cursor-not-allowed"
          >
            {isExecuting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Running...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Run Script (bpy)</span>
              </>
            )}
          </button>

          <div className="w-px h-5 bg-white/[0.08] mx-1" />

          <button
            data-testid="close-drawer-btn"
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-300 hover:text-white hover:bg-zinc-900 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 w-full bg-zinc-950 overflow-hidden relative">
        <Suspense
          fallback={
            <div className="flex items-center justify-center h-full text-xs text-zinc-500 font-mono gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
              <span>Loading Monaco Editor...</span>
            </div>
          }
        >
          <Editor
            height="100%"
            defaultLanguage="python"
            language="python"
            theme="vs-dark"
            value={code}
            onChange={(val) => setCode(val || '')}
            options={{
              minimap: { enabled: false },
              fontSize: 12,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 4,
              insertSpaces: true,
              fontFamily: 'JetBrains Mono, Menlo, Monaco, Consolas, monospace',
            }}
          />
        </Suspense>
      </div>

      <div className="h-9 border-t border-white/[0.08] px-4 bg-zinc-950 flex items-center justify-between text-[11px] text-zinc-500 font-mono shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <span>Interactive White-Box Mode</span>
        </div>
        <span>Docker Container Sandboxed</span>
      </div>
    </div>
  );
}

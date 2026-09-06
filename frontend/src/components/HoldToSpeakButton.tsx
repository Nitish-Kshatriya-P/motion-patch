import { useState, useRef, useEffect } from 'react';
import { Mic, Square } from 'lucide-react';

export default function HoldToSpeakButton({
  onRecordingComplete,
  onError,
  disabled,
}: {
  onRecordingComplete: (blob: Blob) => void;
  onError: (msg: string) => void;
  disabled: boolean;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const holdStartTime = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (isRecording) {
      timerRef.current = window.setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
    };
  }, [isRecording]);

  const stopStream = (stream: MediaStream) => {
    stream.getTracks().forEach((track) => track.stop());
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorder.current = recorder;
      audioChunks.current = [];
      setDuration(0);

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunks.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(audioChunks.current, { type: mimeType });
        stopStream(stream);
        if (blob.size > 0) onRecordingComplete(blob);
      };

      recorder.start();
      setIsRecording(true);
      holdStartTime.current = Date.now();
    } catch (err) {
      console.error(err);
      onError('Microphone access denied or not available');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder.current && mediaRecorder.current.state === 'recording') {
      mediaRecorder.current.stop();
      setIsRecording(false);
      holdStartTime.current = null;
    }
  };

  const handleToggleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        onClick={handleToggleClick}
        disabled={disabled}
        className={`p-1.5 rounded-lg transition-all cursor-pointer select-none shrink-0 flex items-center gap-1.5 text-[11px] ${
          isRecording
            ? 'bg-red-500/20 text-red-400 border border-red-500/40 animate-pulse'
            : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.06]'
        } disabled:opacity-50`}
        title={isRecording ? 'Click to stop recording' : 'Click to record voice instruction'}
      >
        {isRecording ? (
          <>
            <Square className="w-3 h-3 fill-red-400 text-red-400" />
            <span className="font-mono text-[10px] text-red-400 tabular-nums font-semibold">
              {duration}s
            </span>
          </>
        ) : (
          <Mic className="w-3.5 h-3.5" />
        )}
      </button>
    </div>
  );
}

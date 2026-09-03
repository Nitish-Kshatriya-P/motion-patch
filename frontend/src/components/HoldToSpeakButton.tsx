import React, { useState, useRef } from 'react';
import { Mic } from 'lucide-react';

export default function HoldToSpeakButton({ 
  onRecordingComplete, 
  onError, 
  disabled 
}: { 
  onRecordingComplete: (blob: Blob) => void, 
  onError: (msg: string) => void, 
  disabled: boolean 
}) {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const isUserHolding = useRef(false);

  const stopStream = (stream: MediaStream) => {
    stream.getTracks().forEach(track => track.stop());
  };

  const startRecording = async () => {
    isUserHolding.current = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!isUserHolding.current) {
        stopStream(stream);
        onError("Hold the button longer to record audio.");
        return;
      }
      let mimeType = 'audio/webm';
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported('audio/mp4')) {
        mimeType = 'audio/mp4';
      }
      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorder.current = recorder;
      audioChunks.current = [];
      
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };
      
      recorder.onstop = () => {
        const blob = new Blob(audioChunks.current, { type: mimeType });
        stopStream(stream);
        if (blob.size > 0) onRecordingComplete(blob);
      };
      
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Error accessing microphone", err);
      onError("Microphone access denied or not available");
    }
  };

  const stopRecording = () => {
    isUserHolding.current = false;
    if (mediaRecorder.current && mediaRecorder.current.state === "recording") {
      mediaRecorder.current.stop();
      setIsRecording(false);
    }
  };

  return (
    <button
      className={`${isRecording ? 'bg-red-600 animate-pulse' : 'bg-gray-600 hover:bg-gray-700'} disabled:bg-gray-500 text-white p-2 rounded-lg transition-colors ml-2 select-none touch-none shrink-0`}
      onMouseDown={startRecording}
      onMouseUp={stopRecording}
      onMouseLeave={stopRecording}
      onTouchStart={startRecording}
      onTouchEnd={stopRecording}
      disabled={disabled}
      title="Hold to Speak"
    >
      <Mic className="w-5 h-5" />
    </button>
  );
}

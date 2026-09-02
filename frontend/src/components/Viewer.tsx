import React, { useEffect, useRef, useMemo, useState } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls, Grid, Html } from '@react-three/drei';
import * as THREE from 'three';
import { BVHLoader } from 'three/examples/jsm/loaders/BVHLoader.js';
import axios from 'axios';
import { Loader2, Send, Play, Mic } from 'lucide-react';
import Editor from '@monaco-editor/react';
import { extractError } from '../utils';

function BvhModel({ url }: { url: string }) {
  const bvh = useLoader(BVHLoader as any, url);
  const mixer = useRef<THREE.AnimationMixer>(null);

  const helper = useMemo(() => {
    if (!bvh) return null;
    return new THREE.SkeletonHelper(bvh.skeleton.bones[0]);
  }, [bvh]);

  useEffect(() => {
    if (bvh && helper) {
      const m = new THREE.AnimationMixer(bvh.skeleton.bones[0]);
      mixer.current = m;
      
      const action = m.clipAction(bvh.clip);
      action.play();
    }
    return () => {
      if (mixer.current) mixer.current.stopAllAction();
    };
  }, [bvh, helper]);

  useFrame((_, delta) => {
    if (mixer.current) {
      mixer.current.update(delta);
    }
  });

  if (!bvh) return null;

  return (
    <group>
      <primitive object={bvh.skeleton.bones[0]} />
      {helper && <primitive object={helper} />}
    </group>
  );
}

function Loader() {
  return (
    <Html center>
      <div className="text-white text-lg font-medium animate-pulse whitespace-nowrap">
        Loading 3D Model...
      </div>
    </Html>
  );
}

function HoldToSpeakButton({ onRecordingComplete, disabled }: { onRecordingComplete: (blob: Blob) => void, disabled: boolean }) {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const isIntentRecording = useRef(false);

  const startRecording = async () => {
    isIntentRecording.current = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!isIntentRecording.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      const recorder = new MediaRecorder(stream);
      mediaRecorder.current = recorder;
      audioChunks.current = [];
      
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };
      
      recorder.onstop = () => {
        const blob = new Blob(audioChunks.current, { type: 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        if (blob.size > 0) onRecordingComplete(blob);
      };
      
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Error accessing microphone", err);
    }
  };

  const stopRecording = () => {
    isIntentRecording.current = false;
    if (mediaRecorder.current && isRecording) {
      mediaRecorder.current.stop();
      setIsRecording(false);
    }
  };

  return (
    <button
      className={`${isRecording ? 'bg-red-600 animate-pulse' : 'bg-gray-600 hover:bg-gray-700'} disabled:bg-gray-500 text-white p-2 rounded-lg transition-colors ml-2 select-none touch-none`}
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

export default function Viewer({ bvhId, onBvhUpdate }: { bvhId: string, onBvhUpdate?: (id: string) => void }) {
  const [timestamp, setTimestamp] = useState(() => Date.now());
  const url = `http://localhost:8000/bvh/${bvhId}?t=${timestamp}`;

  const [prompt, setPrompt] = useState("");
  const [processingState, setProcessingState] = useState<'idle' | 'generating_code' | 'editing_code' | 'processing_blender'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [scriptCode, setScriptCode] = useState<string>("");

  const submitGeneration = async (audioBlob?: Blob) => {
    setError(null);
    setProcessingState('generating_code');

    try {
      const formData = new FormData();
      formData.append('bvh_id', bvhId);
      formData.append('prompt', prompt);
      
      let endpoint = 'http://localhost:8000/generate_code';
      let payload: any = { prompt, bvh_id: bvhId };
      let config = {};
      
      if (audioBlob) {
        endpoint = 'http://localhost:8000/generate_code_audio';
        formData.append('audio', audioBlob, 'recording.webm');
        payload = formData;
      }

      const genRes = await axios.post(endpoint, payload, config);
      setScriptCode(genRes.data.code);
      setProcessingState('editing_code');
    } catch (err: any) {
      console.error(err);
      setError(extractError(err));
      setProcessingState('idle');
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    await submitGeneration();
  };

  const handleExecute = async () => {
    setError(null);
    setProcessingState('processing_blender');

    try {
      const runRes = await axios.post('http://localhost:8000/run_blender', { bvh_id: bvhId, script_code: scriptCode });
      
      const newBvhId = runRes.data.id;
      
      if (onBvhUpdate) {
        onBvhUpdate(newBvhId);
      } else {
        setTimestamp(Date.now());
      }
      setPrompt("");
      setProcessingState('idle');
    } catch (err: any) {
      console.error(err);
      setError(extractError(err));
      setProcessingState('editing_code');
    }
  };

  const isEditing = processingState === 'editing_code';
  const isProcessing = processingState === 'generating_code' || processingState === 'processing_blender';

  return (
    <div className="w-full h-full flex flex-row relative">
      {error && !isEditing && (
        <div className="absolute top-6 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4 z-50">
          <div className="bg-red-500/90 text-white text-sm px-4 py-2 rounded-lg shadow-lg">
            {error}
          </div>
        </div>
      )}

      <div className={`relative ${isEditing ? 'w-1/2 border-r border-gray-700' : 'w-full'} h-full transition-all duration-300`}>
        <Canvas camera={{ position: [0, 100, 400], fov: 50 }}>
          <color attach="background" args={['#111']} />
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 10]} intensity={1} />
          
          <OrbitControls />
          <Grid infiniteGrid fadeDistance={1000} sectionColor="#444" cellColor="#222" />
          
          <React.Suspense fallback={<Loader />}>
            <BvhModel url={url} />
          </React.Suspense>
        </Canvas>

        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4 flex flex-col gap-2 z-10">
          {isProcessing && (
            <div className="flex items-center justify-center gap-3 bg-blue-600/90 text-white px-6 py-3 rounded-xl shadow-lg mx-auto w-fit">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="font-medium">
                {processingState === 'generating_code' ? 'Agent Generating Code...' : 'Blender Processing File...'}
              </span>
            </div>
          )}

          {!isEditing && (
            <div className="flex items-center bg-white/10 backdrop-blur-md rounded-xl p-2 border border-white/20 shadow-2xl">
              <input 
                type="text"
                className="flex-1 bg-transparent text-white placeholder-gray-300 px-4 py-2 outline-none"
                placeholder="e.g. Scale the root bone motion by 2x on the Y axis"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                disabled={processingState !== 'idle'}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleGenerate();
                }}
              />
              <button
                className={`${isRecording ? 'bg-red-600 animate-pulse' : 'bg-gray-600 hover:bg-gray-700'} disabled:bg-gray-500 text-white p-2 rounded-lg transition-colors ml-2 select-none touch-none`}
                onMouseDown={startRecording}
                onMouseUp={stopRecording}
                onMouseLeave={stopRecording}
                onTouchStart={startRecording}
                onTouchEnd={stopRecording}
                disabled={processingState !== 'idle'}
                title="Hold to Speak"
              >
                <Mic className="w-5 h-5" />
              </button>
              <button 
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-500 text-white p-2 rounded-lg transition-colors ml-2"
                onClick={handleGenerate}
                disabled={!prompt.trim() || processingState !== 'idle'}
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {isEditing && (
        <div className="w-1/2 h-full flex flex-col bg-[#1e1e1e] relative">
          {error && (
            <div className="absolute top-16 left-1/2 -translate-x-1/2 w-full max-w-lg px-4 z-50">
              <div className="bg-red-500/90 text-white text-sm px-4 py-2 rounded-lg shadow-lg">
                {error}
              </div>
            </div>
          )}
          <div className="flex justify-between items-center px-4 py-3 bg-gray-800 border-b border-gray-700">
            <h3 className="text-white font-medium text-sm">Review & Edit Code (bpy)</h3>
            <div className="flex gap-2">
              <button 
                className="bg-gray-600 hover:bg-gray-500 text-white px-4 py-1.5 rounded text-sm transition-colors"
                onClick={() => setProcessingState('idle')}
              >
                Cancel
              </button>
              <button 
                className="bg-green-600 hover:bg-green-500 text-white px-4 py-1.5 rounded text-sm transition-colors flex items-center gap-1"
                onClick={handleExecute}
              >
                <Play className="w-4 h-4" /> Execute
              </button>
            </div>
          </div>
          <div className="flex-1">
            <Editor
              height="100%"
              defaultLanguage="python"
              theme="vs-dark"
              value={scriptCode}
              onChange={(value) => setScriptCode(value || '')}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                wordWrap: 'on',
                scrollBeyondLastLine: false,
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

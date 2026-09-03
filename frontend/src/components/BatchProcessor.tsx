import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Upload, AlertCircle, Loader2, Send, FileCode, CheckCircle, Download, Clock, PlayCircle } from 'lucide-react';
import { extractError } from '../utils';
import HoldToSpeakButton from './HoldToSpeakButton';

interface BatchFileStatus {
  id: string;
  original_name: string;
  status: string;
}

export default function BatchProcessor() {
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchStatus, setBatchStatus] = useState<string | null>(null);
  const [fileStatuses, setFileStatuses] = useState<BatchFileStatus[]>([]);
  
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (batchId && batchStatus === "PROCESSING") {
      interval = setInterval(async () => {
        try {
          const res = await axios.get(`http://localhost:8000/batch_process/${batchId}`);
          setBatchStatus(res.data.status);
          setFileStatuses(res.data.files);
        } catch (err) {
          console.error(err);
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [batchId, batchStatus]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0) return;
    const bvhFiles = selectedFiles.filter(f => f.name.toLowerCase().endsWith('.bvh'));
    if (bvhFiles.length !== selectedFiles.length) {
      setError('Only .bvh files are allowed.');
      return;
    }
    if (bvhFiles.length > 5) {
      setError('You can only select up to 5 files for batch processing.');
      return;
    }
    setError(null);
    setFiles(bvhFiles);
    setBatchId(null);
  };

  const handleSubmit = async () => {
    if (files.length === 0) return setError("Please select at least one BVH file.");
    if (!prompt.trim() && !audioBlob) return setError("Please provide a text prompt or record an audio note.");
    
    setError(null);
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    formData.append('prompt', prompt);
    if (audioBlob) {
      const ext = audioBlob.type.includes('mp4') ? 'mp4' : 'webm';
      formData.append('audio', audioBlob, `batch_recording.${ext}`);
    }

    try {
      const res = await axios.post('http://localhost:8000/batch_process', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setBatchId(res.data.batch_id);
      setBatchStatus("PROCESSING");
      setFileStatuses(res.data.files);
    } catch (err: any) {
      setError(extractError(err));
    }
  };

  const getStatusIcon = (status: string) => {
    if (status === 'PENDING') return <Clock className="w-4 h-4 text-gray-400" />;
    if (status === 'GENERATING_SCRIPT') return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
    if (status === 'RUNNING_JOB') return <PlayCircle className="w-4 h-4 text-purple-500 animate-pulse" />;
    if (status === 'COMPLETED') return <CheckCircle className="w-4 h-4 text-green-500" />;
    return <AlertCircle className="w-4 h-4 text-red-500" />;
  };

  const isProcessing = batchStatus === "PROCESSING";

  return (
    <div className="w-full max-w-2xl bg-white p-8 rounded-xl shadow-md">
      {!batchId ? (
        <>
          <h2 className="text-xl font-bold mb-4 text-gray-800">Enterprise Batch Processing</h2>
          <p className="text-sm text-gray-600 mb-6">Upload up to 5 .bvh files and provide instructions to fix them all concurrently.</p>
          
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">Select BVH Files (Max 5)</label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 bg-gray-50 text-center relative hover:bg-gray-100 transition-colors">
              <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
              <label className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg cursor-pointer transition-colors font-medium text-sm inline-block">
                Browse Files
                <input type="file" className="hidden" accept=".bvh" multiple onChange={handleFileChange} />
              </label>
              {files.length > 0 && (
                <div className="mt-4 text-left border-t border-gray-200 pt-4">
                  <p className="text-xs font-semibold text-gray-500 mb-2 uppercase">Selected Files ({files.length}/5):</p>
                  <ul className="space-y-1">
                    {files.map((f, i) => (
                      <li key={i} className="text-sm text-gray-700 flex items-center gap-2">
                        <FileCode className="w-4 h-4 text-blue-500" />
                        {f.name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">Instructions</label>
            <div className="flex items-center bg-gray-50 rounded-xl p-2 border border-gray-200 shadow-sm focus-within:border-blue-400 focus-within:ring-1 focus-within:ring-blue-400 transition-all">
              <input 
                type="text"
                className="flex-1 bg-transparent text-gray-800 placeholder-gray-400 px-4 py-2 outline-none"
                placeholder="e.g. Fix the foot sliding issue on all models"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              />
              <HoldToSpeakButton onRecordingComplete={setAudioBlob} onError={setError} disabled={false} />
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-50 rounded-lg flex items-start text-red-600">
              <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" />
              <p className="text-sm">{error}</p>
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={files.length === 0 || (!prompt.trim() && !audioBlob)}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-3 rounded-lg shadow-sm transition-colors flex justify-center items-center gap-2"
          >
            <Send className="w-5 h-5" /> Run Batch Processing
          </button>
        </>
      ) : (
        <div className="py-4">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-gray-800">Batch Status</h2>
            {batchStatus === 'COMPLETED' && (
              <span className="bg-green-100 text-green-800 text-xs font-bold px-3 py-1 rounded-full flex items-center gap-1">
                <CheckCircle className="w-4 h-4" /> DONE
              </span>
            )}
            {batchStatus === 'FAILED' && (
              <span className="bg-red-100 text-red-800 text-xs font-bold px-3 py-1 rounded-full">FAILED</span>
            )}
            {isProcessing && (
              <span className="bg-blue-100 text-blue-800 text-xs font-bold px-3 py-1 rounded-full flex items-center gap-2">
                <Loader2 className="w-3 h-3 animate-spin" /> PROCESSING
              </span>
            )}
          </div>
          
          <div className="space-y-3 mb-8">
            {fileStatuses.map((fs) => (
              <div key={fs.id} className="flex items-center justify-between p-4 bg-gray-50 border border-gray-100 rounded-lg">
                <div className="flex items-center gap-3">
                  <FileCode className="w-5 h-5 text-gray-400" />
                  <span className="font-medium text-gray-700">{fs.original_name}</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  {getStatusIcon(fs.status)}
                  <span className="capitalize">{fs.status.replace('_', ' ')}</span>
                </div>
              </div>
            ))}
          </div>
          
          {batchStatus === 'COMPLETED' && (
            <div className="text-center">
              <a
                href={`http://localhost:8000/batch_process/${batchId}/download`}
                download="batch_results.zip"
                className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-medium px-6 py-3 rounded-lg shadow-sm transition-colors"
              >
                <Download className="w-5 h-5" /> Download ZIP
              </a>
              <br/>
              <button onClick={() => { setBatchId(null); setFiles([]); setFileStatuses([]); setPrompt(""); setAudioBlob(null); }} className="mt-6 text-blue-600 hover:underline text-sm font-medium">
                Process another batch
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

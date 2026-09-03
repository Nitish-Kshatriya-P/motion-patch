import React, { useState } from 'react';
import axios from 'axios';
import { Upload, AlertCircle, Loader2, Send, FileCode, CheckCircle, Download } from 'lucide-react';
import { extractError } from '../utils';
import HoldToSpeakButton from './HoldToSpeakButton';

export default function BatchProcessor() {
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

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
    setDownloadUrl(null);
  };

  const handleAudioComplete = (blob: Blob) => {
    setAudioBlob(blob);
    setError(null);
  };

  const handleSubmit = async () => {
    if (files.length === 0) {
      setError("Please select at least one BVH file.");
      return;
    }
    if (!prompt.trim() && !audioBlob) {
      setError("Please provide a text prompt or record an audio note.");
      return;
    }
    
    setError(null);
    setIsProcessing(true);
    setDownloadUrl(null);

    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });
    formData.append('prompt', prompt);
    if (audioBlob) {
      const ext = audioBlob.type.includes('mp4') ? 'mp4' : 'webm';
      formData.append('audio', audioBlob, `batch_recording.${ext}`);
    }

    try {
      const response = await axios.post('http://localhost:8000/batch_process', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      setDownloadUrl(url);
    } catch (err: any) {
      console.error(err);
      if (err.response && err.response.data instanceof Blob) {
          const text = await err.response.data.text();
          try {
              const json = JSON.parse(text);
              setError(json.detail || 'An error occurred.');
          } catch {
              setError('Failed to process batch.');
          }
      } else {
        setError(extractError(err));
      }
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="w-full max-w-2xl bg-white p-8 rounded-xl shadow-md">
      {!downloadUrl ? (
        <>
          <h2 className="text-xl font-bold mb-4 text-gray-800">Enterprise Batch Processing</h2>
          <p className="text-sm text-gray-600 mb-6">Upload up to 5 .bvh files and provide instructions to fix them all concurrently.</p>
          
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">Select BVH Files (Max 5)</label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 bg-gray-50 text-center relative hover:bg-gray-100 transition-colors">
              <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
              <label className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg cursor-pointer transition-colors font-medium text-sm inline-block">
                Browse Files
                <input 
                  type="file" 
                  className="hidden" 
                  accept=".bvh"
                  multiple
                  onChange={handleFileChange}
                  disabled={isProcessing}
                />
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
                disabled={isProcessing}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleSubmit();
                }}
              />
              <HoldToSpeakButton onRecordingComplete={handleAudioComplete} onError={setError} disabled={isProcessing} />
            </div>
            {audioBlob && (
              <p className="mt-2 text-sm text-green-600 flex items-center gap-1">
                <CheckCircle className="w-4 h-4" /> Audio instructions recorded
              </p>
            )}
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-50 rounded-lg flex items-start text-red-600">
              <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" />
              <p className="text-sm">{error}</p>
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={isProcessing || files.length === 0 || (!prompt.trim() && !audioBlob)}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-3 rounded-lg shadow-sm transition-colors flex justify-center items-center gap-2"
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Processing {files.length} files concurrently (Cloud Run Jobs)...
              </>
            ) : (
              <>
                <Send className="w-5 h-5" />
                Run Batch Processing
              </>
            )}
          </button>
        </>
      ) : (
        <div className="text-center py-8">
          <div className="bg-green-100 text-green-600 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
            <CheckCircle className="w-8 h-8" />
          </div>
          <h2 className="text-2xl font-bold text-gray-800 mb-2">Batch Complete!</h2>
          <p className="text-gray-600 mb-8">All files were successfully processed.</p>
          
          <a
            href={downloadUrl}
            download="batch_results.zip"
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-medium px-6 py-3 rounded-lg shadow-sm transition-colors"
          >
            <Download className="w-5 h-5" />
            Download ZIP
          </a>
          <br/>
          <button
            onClick={() => {
              setDownloadUrl(null);
              setFiles([]);
              setPrompt("");
              setAudioBlob(null);
            }}
            className="mt-6 text-blue-600 hover:underline text-sm font-medium"
          >
            Process another batch
          </button>
        </div>
      )}
    </div>
  );
}

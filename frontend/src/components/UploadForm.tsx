import { useState } from 'react';
import axios from 'axios';
import { Upload, AlertCircle, Loader2 } from 'lucide-react';

interface UploadFormProps {
  onUploadSuccess: (id: string) => void;
}

export default function UploadForm({ onUploadSuccess }: UploadFormProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.bvh')) {
      setError('Please select a valid .bvh file');
      return;
    }

    setError(null);
    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('http://localhost:8000/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      onUploadSuccess(response.data.id);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to upload file. Please verify it is a valid BVH format and the server is running.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white p-8 rounded-xl shadow-md">
      <div className="flex flex-col items-center justify-center border-2 border-dashed border-gray-300 rounded-lg p-12 bg-gray-50 hover:bg-gray-100 transition-colors relative">
        {isUploading ? (
          <div className="flex flex-col items-center text-blue-500">
            <Loader2 className="w-12 h-12 animate-spin mb-4" />
            <p className="text-sm font-medium">Uploading and verifying...</p>
          </div>
        ) : (
          <>
            <Upload className="w-12 h-12 text-gray-400 mb-4" />
            <p className="text-sm text-gray-600 mb-2">Drag and drop your .bvh file here</p>
            <p className="text-xs text-gray-400 mb-6">or</p>
            <label className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg cursor-pointer transition-colors font-medium">
              Browse Files
              <input 
                type="file" 
                className="hidden" 
                accept=".bvh"
                onChange={handleFileChange}
              />
            </label>
          </>
        )}
      </div>

      {error && (
        <div className="mt-4 p-4 bg-red-50 rounded-lg flex items-start text-red-600">
          <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" />
          <p className="text-sm">{error}</p>
        </div>
      )}
    </div>
  );
}

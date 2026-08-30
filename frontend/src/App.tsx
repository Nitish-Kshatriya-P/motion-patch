import { useState } from 'react';
import UploadForm from './components/UploadForm';
import Viewer from './components/Viewer';

function App() {
  const [bvhId, setBvhId] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col items-center p-8">
      <h1 className="text-3xl font-bold mb-8 text-gray-800">Hello World Mocap Viewer</h1>
      
      {!bvhId ? (
        <UploadForm onUploadSuccess={setBvhId} />
      ) : (
        <div className="w-full max-w-4xl h-[600px] bg-black rounded-lg overflow-hidden relative shadow-xl">
          <Viewer bvhId={bvhId} />
          <button 
            className="absolute top-4 left-4 bg-white hover:bg-gray-200 text-black px-4 py-2 rounded shadow-md z-10 font-medium transition-colors"
            onClick={() => setBvhId(null)}
          >
            Upload Another
          </button>
        </div>
      )}
    </div>
  );
}

export default App;

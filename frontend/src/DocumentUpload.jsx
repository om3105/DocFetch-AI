import { useState, useRef } from 'react';
import './DocumentUpload.css';

export default function DocumentUpload({ onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [description, setDescription] = useState('');
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  function handleDrag(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && isValidFile(droppedFile)) {
      setFile(droppedFile);
      setStatus(null);
    } else {
      setStatus({ type: 'error', message: 'Only PDF and TXT files are supported.' });
    }
  }

  function isValidFile(f) {
    return f.type === 'application/pdf' || f.type === 'text/plain' || f.name.endsWith('.txt');
  }

  function handleFileChange(e) {
    const selected = e.target.files[0];
    if (selected && isValidFile(selected)) {
      setFile(selected);
      setStatus(null);
    } else if (selected) {
      setStatus({ type: 'error', message: 'Only PDF and TXT files are supported.' });
    }
  }

  async function handleUpload() {
    if (!file || !description.trim()) return;

    setUploading(true);
    setStatus(null);

    try {
      const { uploadDocument } = await import('./api.js');
      await uploadDocument(file, description.trim());
      setStatus({ type: 'success', message: `Uploaded: ${file.name}` });
      onUploadSuccess?.(file.name);
      setFile(null);
      setDescription('');
      if (inputRef.current) inputRef.current.value = '';
    } catch {
      setStatus({ type: 'error', message: `Upload failed for ${file.name}` });
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="upload-panel">
      <div className="section-label">
        <span className="material-symbols-outlined">cloud_upload</span>
        Knowledge Base
      </div>

      <div
        className={`drop-zone ${dragActive ? 'drag-active' : ''} ${file ? 'has-file' : ''}`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt"
          onChange={handleFileChange}
          style={{ display: 'none' }}
        />
        {file ? (
          <div className="file-preview">
            <span className="file-icon">{file.name.endsWith('.pdf') ? '📕' : '📄'}</span>
            <span className="file-name">{file.name}</span>
            <span className="file-size">({(file.size / 1024).toFixed(1)} KB)</span>
          </div>
        ) : (
          <div className="drop-prompt">
            <span className="material-symbols-outlined">upload_file</span>
            <p>Drag & Drop Documents</p>
            <span className="drop-hint">PDF, TXT</span>
          </div>
        )}
      </div>

      {file && (
        <div className="description-section">
          <input
            type="text"
            className="description-input"
            placeholder="Add a description..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={300}
          />
          <button
            className="upload-btn"
            onClick={handleUpload}
            disabled={uploading || !description.trim()}
          >
            {uploading ? (
              <span className="btn-loading">
                <span className="spinner" />
                Processing...
              </span>
            ) : (
              <>
                <span className="material-symbols-outlined">add_circle</span>
                Process Document
              </>
            )}
          </button>
        </div>
      )}

      {status && (
        <div className={`upload-status ${status.type}`}>
          {status.type === 'success' ? '✅' : '❌'} {status.message}
        </div>
      )}
    </div>
  );
}

import { useRef, useState } from 'react';

export default function FileDropzone({ label, accept, file, onChange, hint }) {
  const inputRef = useRef();
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) onChange(f);
  };

  return (
    <div>
      <label className="label">{label}</label>
      <div
        onClick={() => inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className="relative rounded-xl cursor-pointer transition-all duration-200 p-6 text-center"
        style={{
          border: `2px dashed ${dragging ? 'var(--accent)' : file ? 'var(--accent-border)' : 'var(--border)'}`,
          background: dragging ? 'var(--accent-dim)' : file ? 'rgba(34,197,94,0.04)' : 'rgba(255,255,255,0.02)',
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => e.target.files[0] && onChange(e.target.files[0])}
        />

        {file ? (
          <div className="flex items-center justify-center gap-3">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'var(--accent-dim)', border: '1px solid var(--accent-border)' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </div>
            <div className="text-left overflow-hidden">
              <p className="text-sm font-medium truncate" style={{ color: 'var(--accent)' }}>{file.name}</p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{(file.size / 1024).toFixed(1)} KB — click to replace</p>
            </div>
          </div>
        ) : (
          <div>
            <div className="w-10 h-10 rounded-xl mx-auto mb-3 flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <p className="text-sm font-medium" style={{ color: 'var(--text-subtle)' }}>Drop file here or <span style={{ color: 'var(--accent)' }}>browse</span></p>
            {hint && <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{hint}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
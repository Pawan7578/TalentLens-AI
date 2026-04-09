import { useEffect } from 'react';

const Toast = ({ message, type, onClose }) => {
  useEffect(() => {
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [onClose]);

  const isSuccess = type === 'success';
  const bgColor = isSuccess
    ? 'rgba(34,197,94,0.95)'
    : 'rgba(239,68,68,0.95)';
  const textColor = isSuccess ? '#00ff00' : '#ffffff';
  const icon = isSuccess ? '✅' : '❌';

  return (
    <div
      className="fixed bottom-4 right-4 z-50 animate-slide-up"
      style={{
        background: bgColor,
        color: textColor,
        padding: '1rem 1.5rem',
        borderRadius: '0.75rem',
        boxShadow: '0 10px 30px rgba(0,0,0,0.3)',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255,255,255,0.1)',
        maxWidth: '380px',
        minWidth: '300px',
      }}
    >
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <p className="text-sm font-medium flex-1">{message}</p>
        <button
          onClick={onClose}
          className="ml-4 hover:opacity-70 transition-opacity flex-shrink-0"
          style={{ color: textColor }}
        >
          ✕
        </button>
      </div>
    </div>
  );
};

export default Toast;

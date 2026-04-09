import { useState } from 'react';

const DateFilter = ({ onFilterChange, currentFilter }) => {
  const [showCustom, setShowCustom] = useState(false);
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');

  const dateFilters = [
    { label: 'All Time', value: 'all', days: null },
    { label: 'Last 24 Hours', value: 'last24h', days: 1 },
    { label: 'Last 7 Days', value: 'last7d', days: 7 },
    { label: 'Last 30 Days', value: 'last30d', days: 30 },
    { label: 'Custom Range', value: 'custom', days: null },
  ];

  const handleDateChange = (value) => {
    const filter = dateFilters.find(f => f.value === value);
    if (value === 'custom') {
      setShowCustom(true);
    } else {
      setShowCustom(false);
      onFilterChange(filter);
    }
  };

  const handleCustomRangeSubmit = () => {
    if (customStart && customEnd) {
      onFilterChange({
        label: 'Custom Range',
        value: 'custom',
        days: null,
        start: customStart,
        end: customEnd,
      });
      setShowCustom(false);
    }
  };

  return (
    <div className="flex gap-3 items-center">
      <label className="text-xs font-medium whitespace-nowrap" style={{ color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        Date Submitted:
      </label>
      <select
        value={currentFilter?.value || 'all'}
        onChange={(e) => handleDateChange(e.target.value)}
        className="input-field text-xs py-2 px-3 max-w-fit"
        style={{
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid var(--border)',
        }}
      >
        {dateFilters.map((filter) => (
          <option key={filter.value} value={filter.value}>
            {filter.label}
          </option>
        ))}
      </select>

      {/* Custom Date Range Picker */}
      {showCustom && (
        <div className="flex gap-2 items-center">
          <input
            type="date"
            value={customStart}
            onChange={(e) => setCustomStart(e.target.value)}
            className="input-field text-xs py-2 px-3"
            style={{
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--border)',
            }}
          />
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>to</span>
          <input
            type="date"
            value={customEnd}
            onChange={(e) => setCustomEnd(e.target.value)}
            className="input-field text-xs py-2 px-3"
            style={{
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--border)',
            }}
          />
          <button
            onClick={handleCustomRangeSubmit}
            disabled={!customStart || !customEnd}
            className="btn-primary text-xs px-3 py-2"
            style={{
              opacity: customStart && customEnd ? 1 : 0.5,
              cursor: customStart && customEnd ? 'pointer' : 'not-allowed',
            }}
          >
            Apply
          </button>
          <button
            onClick={() => setShowCustom(false)}
            className="btn-ghost text-xs px-3 py-2"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
};

export default DateFilter;

import React from 'react';

const ATSFilter = ({ onFilterChange, currentFilter }) => {
  const filters = [
    { label: 'All', value: 'all', min: 0, max: 100 },
    { label: 'Critical (80+)', value: 'critical', min: 80, max: 100 },
    { label: 'Promising (70-79)', value: 'promising', min: 70, max: 79 },
    { label: 'Average (60-69)', value: 'average', min: 60, max: 69 },
    { label: 'Poor (<60)', value: 'poor', min: 0, max: 59 },
  ];

  return (
    <div className="flex gap-3 items-center">
      <label className="text-xs font-medium whitespace-nowrap" style={{ color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        ATS Score:
      </label>
      <select
        value={currentFilter?.value || 'all'}
        onChange={(e) => {
          const selected = filters.find(f => f.value === e.target.value);
          onFilterChange(selected);
        }}
        className="input-field text-xs py-2 px-3 max-w-fit"
        style={{
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid var(--border)',
        }}
      >
        {filters.map((filter) => (
          <option key={filter.value} value={filter.value}>
            {filter.label}
          </option>
        ))}
      </select>
    </div>
  );
};

export default ATSFilter;

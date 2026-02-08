export default function PromptPresets({ presets, selectedPresetId, onSelect }) {
  return (
    <div className="preset-wrap">
      <p className="preset-title">Trasformazioni comuni</p>
      <div className="preset-grid">
        {presets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={`preset-button ${selectedPresetId === preset.id ? "active" : ""}`}
            title={preset.description}
            onClick={() => onSelect(preset)}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  );
}

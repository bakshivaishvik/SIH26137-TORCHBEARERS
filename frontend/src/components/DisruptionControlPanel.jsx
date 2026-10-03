import React from 'react';

export const DisruptionControlPanel = ({ onHazard, onPlay, onPause, running }) => {
    return (
        <div style={{ padding: '10px', border: '1px solid #ccc', marginTop: '10px' }}>
            <h3>Control Panel</h3>
            <div style={{ marginBottom: '10px' }}>
                <button onClick={running ? onPause : onPlay}>
                    {running ? "Pause" : "Play"}
                </button>
            </div>
            <div>
                <h4>Inject Hazard (Chaos Mode)</h4>
                <button onClick={() => onHazard({ lat: 17.442, lon: 78.375, type: 'roadblock' })}>
                    Inject Roadblock near Inorbit
                </button>
                <button onClick={() => onHazard({ lat: 17.435, lon: 78.382, type: 'accident' })} style={{ marginLeft: '10px' }}>
                    Inject Accident near IKEA
                </button>
            </div>
        </div>
    );
};


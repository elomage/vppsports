import React, { useState, useEffect, useRef } from 'react'
import './App.css'
import Dashboard from './Dashboard'
import RunControl from './Runcontrol'
import UploadSensorData from './UploadSensorData'

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboards, setDashboards] = useState([{ id: 1, flexGrow: 1 }]);
  const [dashboardRuns, setDashboardRuns] = useState({}); // Track selectedRun per dashboard
  const MAX_DASHBOARDS = 4; // Limit to 4 for readability
  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'upload', label: 'Upload Sensor Data' },
  ];

  const addDashboard = () => {
    if (dashboards.length < MAX_DASHBOARDS) {
      const newId = dashboards.length ? dashboards[dashboards.length - 1].id + 1 : 1;
      setDashboards(prev => [...prev, { id: newId, flexGrow: 1 }]);
    }
  };

  const removeDashboard = (id) => {
    setDashboards(prev => prev.filter(d => d.id !== id));
    // Clean up the run data for removed dashboard
    setDashboardRuns(prev => {
      const newRuns = { ...prev };
      delete newRuns[id];
      return newRuns;
    });
  };

  const updateFlexGrow = (id, newFlexGrow) => {
    setDashboards(prevDashboards =>
      prevDashboards.map(dash =>
        dash.id === id ? { ...dash, flexGrow: Math.max(0.1, newFlexGrow) } : dash
      )
    );
  };

  const setSelectedRunForDashboard = (dashboardId, run) => {
    setDashboardRuns(prev => ({
      ...prev,
      [dashboardId]: run
    }));
  };

  return (
    <>
      <div className="top-bar">
        <div className="top-bar__tabs" role="tablist" aria-label="Main views">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`top-bar__tab ${activeTab === tab.id ? 'is-active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {activeTab === 'dashboard' && (
          <div className="top-bar__actions">
            <button 
              className="btn btn-primary" 
              onClick={addDashboard}
              disabled={dashboards.length >= MAX_DASHBOARDS}
            >
              Add Run {dashboards.length >= MAX_DASHBOARDS && '(Max reached)'}
            </button>
          </div>
        )}
      </div>

      <div id="main-wrapper" className={activeTab === 'dashboard' ? 'dashboard-grid' : 'upload-grid'}>
        {activeTab === 'dashboard' && dashboards.map((dashboard, index) => {
          const isLastDashboard = index === dashboards.length - 1;
          
          return (
            <React.Fragment key={dashboard.id}>
              <div 
                className="dashboard-card"
                style={{
                  flex: `${dashboard.flexGrow} 1 0`,
                  minWidth: '300px',
                  minHeight: '200px'
                }}
              >
                <div className="dashboard-card__toolbar">
                  <RunControl 
                    setSelectedRun={(run) => setSelectedRunForDashboard(dashboard.id, run)} 
                  />
                  <button className="btn btn-outline-danger btn-sm" onClick={() => removeDashboard(dashboard.id)}>
                    Remove
                  </button>
                </div>
                <div className="dashboard-card__content">
                  <Dashboard 
                    selectedRun={dashboardRuns[dashboard.id] || null}
                  />
                </div>
              </div>
              {!isLastDashboard && (
                <DashboardResizeHandle
                  topDashboard={dashboard}
                  bottomDashboard={dashboards[index + 1]}
                  onResize={(topGrow, bottomGrow) => {
                    updateFlexGrow(dashboard.id, topGrow);
                    updateFlexGrow(dashboards[index + 1].id, bottomGrow);
                  }}
                />
              )}
            </React.Fragment>
          );
        })}
        {activeTab === 'upload' && <UploadSensorData />}
      </div>
    </>
  )
}

function DashboardResizeHandle({ topDashboard, bottomDashboard, onResize }) {
  const [isDragging, setIsDragging] = useState(false);
  const startPosRef = useRef({ y: 0, topGrow: 0, bottomGrow: 0, totalGrow: 0 });
  const handleRef = useRef(null);

  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsDragging(true);
    
    const totalGrow = topDashboard.flexGrow + bottomDashboard.flexGrow;
    startPosRef.current = {
      y: e.clientY,
      topGrow: topDashboard.flexGrow,
      bottomGrow: bottomDashboard.flexGrow,
      totalGrow: totalGrow
    };
  };

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e) => {
      const deltaY = e.clientY - startPosRef.current.y;
      const container = handleRef.current?.parentElement;
      if (!container) return;

      const containerHeight = container.offsetHeight;
      const deltaRatio = deltaY / containerHeight;
      const totalGrow = startPosRef.current.totalGrow;

      // Calculate new flex-grow values based on drag distance
      let newTopGrow = startPosRef.current.topGrow + (deltaRatio * totalGrow * 2);
      let newBottomGrow = startPosRef.current.bottomGrow - (deltaRatio * totalGrow * 2);

      // Ensure minimum sizes
      newTopGrow = Math.max(0.2, newTopGrow);
      newBottomGrow = Math.max(0.2, newBottomGrow);

      // Normalize to maintain total
      const sum = newTopGrow + newBottomGrow;
      newTopGrow = (newTopGrow / sum) * totalGrow;
      newBottomGrow = (newBottomGrow / sum) * totalGrow;

      onResize(newTopGrow, newBottomGrow);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, onResize]);

  return (
    <div
      ref={handleRef}
      onMouseDown={handleMouseDown}
      style={{
        height: '12px',
        width: '100%',
        cursor: 'ns-resize',
        backgroundColor: isDragging ? '#007bff' : '#e0e0e0',
        flexShrink: 0,
        position: 'relative',
        transition: isDragging ? 'none' : 'background-color 0.2s',
        zIndex: 10,
        margin: '4px 0'
      }}
      onMouseEnter={(e) => {
        if (!isDragging) {
          e.currentTarget.style.backgroundColor = '#007bff';
        }
      }}
      onMouseLeave={(e) => {
        if (!isDragging) {
          e.currentTarget.style.backgroundColor = '#e0e0e0';
        }
      }}
    >
      {/* Visual indicator */}
      <div style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '60px',
        height: '4px',
        backgroundColor: isDragging ? '#fff' : '#999',
        borderRadius: '2px',
        pointerEvents: 'none'
      }} />
    </div>
  );
}

export default App

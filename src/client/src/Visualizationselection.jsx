import React, { useState, useEffect, useRef } from 'react';
import './Visualizationselection.css';

const componentsMap = {
    info: React.lazy(() => import('./Infovisualizer')),
    graph: React.lazy(() => import('./PlotlyGraphvisualizer2')),
    video: React.lazy(() => import('./VideoVisualizer')),
    model: React.lazy(() => import('./Modelvisualizer')),
};

export default function ComponentSelector({ selectedRun, sliderValue, setSliderValue }) {
    const [selectedComponent, setSelectedComponent] = useState([
        // { id: 1, type: 'info', flexGrow: 1 },
        { id: 1, type: 'graph', flexGrow: 1 },
        { id: 2, type: 'video', flexGrow: 1 },
        { id: 3, type: 'model', flexGrow: 1 },
    ]);
    const [containerSize, setContainerSize] = useState({ width: window.innerWidth, height: window.innerHeight });

    const addComponent = (value) => {
        const newComponents = [...selectedComponent, { id: Date.now(), type: value, flexGrow: 1 }];
        setSelectedComponent(newComponents);
    };

    const removeComponent = (id) => {
        setSelectedComponent(selectedComponent.filter((component) => component.id !== id));
    };

    const updateFlexGrow = (id, newFlexGrow) => {
        setSelectedComponent(prevComponents =>
            prevComponents.map(comp =>
                comp.id === id ? { ...comp, flexGrow: Math.max(0.1, newFlexGrow) } : comp
            )
        );
    };

    const graphCount = selectedComponent.filter(component => component.type === 'graph').length || 1;

    useEffect(() => {
        const handleResize = () => {
            const sidebarWidth = document.getElementById('sidebar') ? document.getElementById('sidebar').offsetWidth : 0;
            setContainerSize({ width: window.innerWidth - sidebarWidth - 100, height: window.innerHeight });
        };

        window.addEventListener('resize', handleResize);
        handleResize();

        return () => {
            window.removeEventListener('resize', handleResize);
        };
    }, []);

    useEffect(() => {
        const handleWidthChange = () => {
            setContainerSize((prevSize) => ({ ...prevSize, width: window.innerWidth }));
        };

        window.addEventListener('resize', handleWidthChange);

        return () => {
            window.removeEventListener('resize', handleWidthChange);
        };
    }, []);

    return (
        <>
            {/* <h1 className='text-2xl font-bold mb-4'>Visualization</h1> */}
            <div className='flex gap-4'>
                {/* <button className='btn btn-primary' onClick={() => addComponent('info')} style={{margin: '5px'}}>Add Info</button> */}
                <button className='btn btn-primary' onClick={() => addComponent('graph')} style={{margin: '5px'}}>Add Graph</button>
                <button className='btn btn-primary' onClick={() => addComponent('video')} style={{margin: '5px'}}>Add Video</button>
                <button className='btn btn-primary' onClick={() => addComponent('model')} style={{margin: '5px'}}>Add Model</button>
            </div>
            <div className='flex flex-col items-center p-6' id='visualization-component-wrapper' style={{ '--graph-count': graphCount }}>
                <div className='flex flex-wrap' style={{ flex: 1, width: '100%' }}>
                    {selectedComponent.map((component, index) => {
                        const Component = componentsMap[component.type];
                        const wrapperClass = component.type === 'graph' ? 'graph-wrapper' : component.type === 'model' ? 'model-wrapper' : component.type === 'video' ? 'video-wrapper' : 'component-wrapper';
                        const isLastComponent = index === selectedComponent.length - 1;
                        
                        return (
                            <React.Fragment key={component.id}>
                                <div 
                                    className={wrapperClass} 
                                    style={{ 
                                        flex: `${component.flexGrow} 1 0`,
                                        minWidth: '200px',
                                        minHeight: '200px',
                                        position: 'relative',
                                        display: 'flex',
                                        flexDirection: 'column'
                                    }}
                                >
                                    <React.Suspense fallback={<div>Loading...</div>}>
                                        <Component 
                                            selectedRun={selectedRun} 
                                            sliderValue={sliderValue} 
                                            removeFunction={() => removeComponent(component.id)} 
                                            style={{width: '100%', height: '100%', flex: 1 }} 
                                            setSliderValue={setSliderValue}
                                        />
                                    </React.Suspense>
                                    <button 
                                        className='btn btn-danger' 
                                        style={{margin: 0}} 
                                        onClick={() => removeComponent(component.id)}
                                    >
                                        Remove
                                    </button>
                                </div>
                                {!isLastComponent && (
                                    <ResizeHandle
                                        leftComponent={component}
                                        rightComponent={selectedComponent[index + 1]}
                                        onResize={(leftGrow, rightGrow) => {
                                            updateFlexGrow(component.id, leftGrow);
                                            updateFlexGrow(selectedComponent[index + 1].id, rightGrow);
                                        }}
                                    />
                                )}
                            </React.Fragment>
                        );
                    })}
                </div>
            </div>
        </>
    );
}

function ResizeHandle({ leftComponent, rightComponent, onResize }) {
    const [isDragging, setIsDragging] = useState(false);
    const startPosRef = useRef({ x: 0, leftGrow: 0, rightGrow: 0, totalGrow: 0 });
    const handleRef = useRef(null);

    const handleMouseDown = (e) => {
        e.preventDefault();
        setIsDragging(true);
        
        const totalGrow = leftComponent.flexGrow + rightComponent.flexGrow;
        startPosRef.current = {
            x: e.clientX,
            leftGrow: leftComponent.flexGrow,
            rightGrow: rightComponent.flexGrow,
            totalGrow: totalGrow
        };
    };

    useEffect(() => {
        if (!isDragging) return;

        const handleMouseMove = (e) => {
            const deltaX = e.clientX - startPosRef.current.x;
            const container = handleRef.current?.parentElement;
            if (!container) return;

            const containerWidth = container.offsetWidth;
            const deltaRatio = deltaX / containerWidth;
            const totalGrow = startPosRef.current.totalGrow;

            // Calculate new flex-grow values based on drag distance
            let newLeftGrow = startPosRef.current.leftGrow + (deltaRatio * totalGrow);
            let newRightGrow = startPosRef.current.rightGrow - (deltaRatio * totalGrow);

            // Ensure minimum sizes
            newLeftGrow = Math.max(0.1, newLeftGrow);
            newRightGrow = Math.max(0.1, newRightGrow);

            // Normalize to maintain total
            const sum = newLeftGrow + newRightGrow;
            newLeftGrow = (newLeftGrow / sum) * totalGrow;
            newRightGrow = (newRightGrow / sum) * totalGrow;

            onResize(newLeftGrow, newRightGrow);
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
                width: '8px',
                cursor: 'ew-resize',
                backgroundColor: isDragging ? '#007bff' : '#e0e0e0',
                flexShrink: 0,
                position: 'relative',
                transition: isDragging ? 'none' : 'background-color 0.2s',
                zIndex: 10
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
                width: '4px',
                height: '40px',
                backgroundColor: isDragging ? '#fff' : '#999',
                borderRadius: '2px',
                pointerEvents: 'none'
            }} />
        </div>
    );
}
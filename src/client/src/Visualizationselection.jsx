import React, { useState, useEffect, useRef } from 'react';
import './Visualizationselection.css';
import { checkRunVideoExists, fetchPluginAssignments } from './api';

const componentsMap = {
    info: React.lazy(() => import('./Infovisualizer')),
    echart: React.lazy(() => import('./EChartGraph')),
    video: React.lazy(() => import('./VideoVisualizer')),
    model: React.lazy(() => import('./Modelvisualizer')),
};

export default function ComponentSelector({ selectedRun, effectiveTimestamps, sliderValue, setSliderValue, onEffectiveTimestampsChange }) {
    const [selectedComponent, setSelectedComponent] = useState([
        { id: 1, type: 'echart', flexGrow: 1 },
        { id: 2, type: 'video', flexGrow: 1 },
    ]);
    const [hasVideoForRun, setHasVideoForRun] = useState(true);
    const [containerSize, setContainerSize] = useState({ width: window.innerWidth, height: window.innerHeight });

    // Plugin assignment state.
    // vizPlugins: array of { id, enabled, order } or null when no config (all enabled).
    // enabledFilterIds: array of enabled filter IDs or null (all enabled).
    const [vizPlugins, setVizPlugins] = useState(null);
    const [enabledFilterIds, setEnabledFilterIds] = useState(null);

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

    useEffect(() => {
        let isCancelled = false;

        const updateVideoAvailability = async () => {
            if (!selectedRun?._id) {
                if (!isCancelled) {
                    setHasVideoForRun(false);
                    setSelectedComponent((prev) => prev.filter((component) => component.type !== 'video'));
                }
                return;
            }

            try {
                const hasVideo = await checkRunVideoExists(selectedRun._id);
                if (isCancelled) return;

                setHasVideoForRun(hasVideo);
                if (!hasVideo) {
                    setSelectedComponent((prev) => prev.filter((component) => component.type !== 'video'));
                } else {
                    setSelectedComponent((prev) => {
                        const hasVideoComponent = prev.some((component) => component.type === 'video');
                        if (hasVideoComponent) return prev;
                        return [...prev, { id: Date.now(), type: 'video', flexGrow: 1 }];
                    });
                }
            } catch (error) {
                if (isCancelled) return;

                // Fail closed: hide video component if availability check fails.
                setHasVideoForRun(false);
                setSelectedComponent((prev) => prev.filter((component) => component.type !== 'video'));
            }
        };

        updateVideoAvailability();

        return () => {
            isCancelled = true;
        };
    }, [selectedRun?._id]);

    // Fetch plugin assignments whenever the run's context changes.
    useEffect(() => {
        const contextId = selectedRun?.contextId
            ? String(selectedRun.contextId)
            : null;

        if (!contextId) {
            setVizPlugins(null);
            setEnabledFilterIds(null);
            return;
        }

        let isCancelled = false;

        fetchPluginAssignments(contextId, 'visualization')
            .then((data) => {
                if (isCancelled) return;
                const plugins = Array.isArray(data?.plugins) ? data.plugins : null;
                setVizPlugins(plugins);

                if (plugins) {
                    const disabledTypes = new Set(
                        plugins.filter((p) => !p.enabled).map((p) => p.id)
                    );
                    if (disabledTypes.size > 0) {
                        setSelectedComponent((prev) =>
                            prev.filter((c) => !disabledTypes.has(c.type))
                        );
                    }
                }
            })
            .catch(() => {
                if (!isCancelled) setVizPlugins(null);
            });

        fetchPluginAssignments(contextId, 'filter')
            .then((data) => {
                if (isCancelled) return;
                const plugins = Array.isArray(data?.plugins) ? data.plugins : null;
                const ids = plugins
                    ? plugins.filter((p) => p.enabled).map((p) => p.id)
                    : null;
                setEnabledFilterIds(ids);
            })
            .catch(() => {
                if (!isCancelled) setEnabledFilterIds(null);
            });

        return () => {
            isCancelled = true;
        };
    }, [selectedRun?.contextId]);

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

    // Set of viz plugin IDs that are enabled for the current context.
    // null vizPlugins = no config loaded yet, default to all enabled.
    const enabledVizTypes = vizPlugins
        ? new Set(vizPlugins.filter((p) => p.enabled).map((p) => p.id))
        : new Set(Object.keys(componentsMap));

    return (
        <>
            <div className='flex gap-4'>
                {enabledVizTypes.has('echart') && (
                    <button className='btn btn-primary' onClick={() => addComponent('echart')} style={{margin: '5px'}}>Add Graph</button>
                )}
                {hasVideoForRun && enabledVizTypes.has('video') && (
                    <button className='btn btn-primary' onClick={() => addComponent('video')} style={{margin: '5px'}}>Add Video</button>
                )}
                {enabledVizTypes.has('info') && (
                    <button className='btn btn-primary' onClick={() => addComponent('info')} style={{margin: '5px'}}>Add Info</button>
                )}
                {enabledVizTypes.has('model') && (
                    <button className='btn btn-primary' onClick={() => addComponent('model')} style={{margin: '5px'}}>Add Model</button>
                )}
            </div>
            <div className='flex flex-col items-center p-6' id='visualization-component-wrapper'>
                <div className='flex flex-wrap' style={{ flex: 1, width: '100%' }}>
                    {(() => {
                        let echartCounter = 0;
                        return selectedComponent.filter((component) => component.type !== 'video' || hasVideoForRun).map((component, index, visibleComponents) => {
                        const chartIndex = component.type === 'echart' ? echartCounter++ : undefined;
                        const Component = componentsMap[component.type];
                        const wrapperClass = component.type === 'echart'
                            ? 'graph-wrapper'
                            : component.type === 'model'
                                ? 'model-wrapper'
                                : component.type === 'video'
                                    ? 'video-wrapper'
                                    : 'component-wrapper';
                        const isLastComponent = index === visibleComponents.length - 1;

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
                                            style={{width: '100%', height: '100%', flex: 1}}
                                            setSliderValue={setSliderValue}
                                            onEffectiveTimestampsChange={component.type === 'echart' ? onEffectiveTimestampsChange : undefined}
                                            enabledFilterIds={component.type === 'echart' ? enabledFilterIds : undefined}
                                            effectiveTimestamps={component.type === 'video' ? effectiveTimestamps : undefined}
                                            chartIndex={chartIndex}
                                        />
                                    </React.Suspense>
                                </div>
                                {!isLastComponent && (
                                        <ResizeHandle
                                            leftComponent={component}
                                            rightComponent={visibleComponents[index + 1]}
                                            onResize={(leftGrow, rightGrow) => {
                                                updateFlexGrow(component.id, leftGrow);
                                            updateFlexGrow(visibleComponents[index + 1].id, rightGrow);
                                            }}
                                        />
                                )}
                            </React.Fragment>
                        );
                    });
                    })()}
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

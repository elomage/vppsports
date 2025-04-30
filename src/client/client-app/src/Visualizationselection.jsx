import React, { useState, useEffect } from 'react';
import './Visualizationselection.css';

const componentsMap = {
    info: React.lazy(() => import('./Infovisualizer')),
    graph: React.lazy(() => import('./PlotlyGraphvisualizer')),
    video: React.lazy(() => import('./VideoVisualizer'))
    // model: React.lazy(() => import('./Modelvisualizer')),
};

export default function ComponentSelector({ selectedRun, sliderValue, setSliderValue }) {
    const [selectedComponent, setSelectedComponent] = useState([
        // { id: 1, type: 'info' },
        { id: 1, type: 'graph' },
        // { id: 3, type: 'model' },
        { id: 2, type: 'video' },
    ]);
    const [containerSize, setContainerSize] = useState({ width: window.innerWidth, height: window.innerHeight });

    const addComponent = (value) => {
        const newComponents = [...selectedComponent, { id: Date.now(), type: value }];
        setSelectedComponent(newComponents);
    };

    const removeComponent = (id) => {
        setSelectedComponent(selectedComponent.filter((component) => component.id !== id));
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
                    <h1 className='text-2xl font-bold mb-4'>Visualization</h1>
            <div className='flex gap-4'>
                {/* <button className='btn btn-primary' onClick={() => addComponent('info')} style={{margin: '5px'}}>Add Info</button> */}
                <button className='btn btn-primary' onClick={() => addComponent('graph')} style={{margin: '5px'}}>Add Graph</button>
                <button className='btn btn-primary' onClick={() => addComponent('video')} style={{margin: '5px'}}>Add Video</button>
                {/* <button className='btn btn-primary' onClick={() => addComponent('model')} style={{margin: '5px'}}>Add Model</button> */}
            </div>
        {/* <div className='flex flex-col items-center p-6' id='visualization-component-wrapper' style={{ width: containerSize.width, height: containerSize.height }}> */}
        <div className='flex flex-col items-center p-6' id='visualization-component-wrapper' style={{ '--graph-count': graphCount }}>

            <div className='flex flex-wrap gap-4 mt-4' style={{ flex: 1 }}>
                {selectedComponent.map((component) => {
                    const Component = componentsMap[component.type];
                    const wrapperClass = component.type === 'graph' ? 'graph-wrapper' : component.type === 'model' ? 'model-wrapper' : component.type === 'video' ? 'video-wrapper' : 'component-wrapper';
                    return (
                        <div key={component.id} className={wrapperClass} style={{ flex: '1 1 auto', width: containerSize.width, height: containerSize.height }}>
                            <React.Suspense fallback={<div>Loading...</div>}>
                                <Component selectedRun={selectedRun} sliderValue={sliderValue} removeFunction={() => removeComponent(component.id)} style={{width: containerSize.width, height: containerSize.height }} setSliderValue={setSliderValue}/>
                            </React.Suspense>
                            <button className='btn btn-danger' onClick={() => removeComponent(component.id)}>Remove</button>
                        </div>
                    );
                })}
            </div>
        </div>
        </>
    );
}
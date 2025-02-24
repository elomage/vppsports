import React, { useState, useEffect } from 'react';
import './Visualizationselection.css';

const componentsMap = {
    info: React.lazy(() => import('./Infovisualizer')),
    graph: React.lazy(() => import('./Graphvisualizer')),
};

export default function ComponentSelector({ selectedRun, sliderValue }) {
    const [selectedComponent, setSelectedComponent] = useState([
        { id: 1, type: 'info' },
        { id: 2, type: 'graph' },
    ]);

    const addComponent = (value) => {
        const newComponents = [...selectedComponent, { id: Date.now(), type: value }];
        setSelectedComponent(newComponents);
    };

    const removeComponent = (id) => {
        setSelectedComponent(selectedComponent.filter((component) => component.id !== id));
    };

    return (
        <div className='flex flex-col items-center p-6' id='visualization-component-wrapper'>
            <h1 className='text-2xl font-bold mb-4'>Visualization Selection</h1>
            <div className='flex gap-4'>
                <button className='btn btn-primary' onClick={() => addComponent('info')}>Add Info</button>
                <button className='btn btn-primary' onClick={() => addComponent('graph')}>Add Graph</button>
            </div>
            <div className='flex flex-col gap-4 mt-4'>
                {selectedComponent.map((component) => {
                    const Component = componentsMap[component.type];
                    return (
                        <div key={component.id} className='flex flex-col gap-4'>
                            <React.Suspense fallback={<div>Loading...</div>}>
                                <Component selectedRun={selectedRun} sliderValue={sliderValue} />
                            </React.Suspense>
                            <button className='btn btn-danger' onClick={() => removeComponent(component.id)}>Remove</button>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
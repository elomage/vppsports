// import React, { useState, useEffect } from 'react';
// import './Visualizationselection.css';

// const componentsMap = {
//     info: React.lazy(() => import('./Infovisualizer')),
//     graph: React.lazy(() => import('./Graphvisualizer')),
//     model: React.lazy(() => import('./Modelvisualizer')),
// };

// export default function ComponentSelector({ selectedRun, sliderValue }) {
//     const [selectedComponent, setSelectedComponent] = useState([
//         { id: 1, type: 'info' },
//         { id: 2, type: 'graph' },
//         { id: 3, type: 'model' },
//     ]);
//     const [containerSize, setContainerSize] = useState({ width: window.innerWidth, height: window.innerHeight });

//     const addComponent = (value) => {
//         const newComponents = [...selectedComponent, { id: Date.now(), type: value }];
//         setSelectedComponent(newComponents);
//     };

//     const removeComponent = (id) => {
//         setSelectedComponent(selectedComponent.filter((component) => component.id !== id));
//     };

//     useEffect(() => {
//         const handleResize = () => {
//             const sidebarWidth = document.getElementById('sidebar').offsetWidth;
//             setContainerSize({ width: window.innerWidth - sidebarWidth - 100, height: window.innerHeight});
//         };

//         window.addEventListener('resize', handleResize);
//         handleResize();

//         return () => {
//             window.removeEventListener('resize', handleResize);
//         };
//     }, []);

//     return (
//         <div className='flex flex-col items-center p-6' id='visualization-component-wrapper' style={{ width: containerSize.width, height: containerSize.height}}>
//             {/* <h1 className='text-2xl font-bold mb-4'>Visualization Selection</h1> */}
//             <div className='flex gap-4'>
//                 <button className='btn btn-primary' onClick={() => addComponent('info')}>Add Info</button>
//                 <button className='btn btn-primary' onClick={() => addComponent('graph')}>Add Graph</button>
//                 <button className='btn btn-primary' onClick={() => addComponent('model')}>Add Model</button>
//             </div>
//             <div className='flex flex-row gap-4 mt-4'>
//                 {selectedComponent.map((component) => {
//                     const Component = componentsMap[component.type];
//                     return (
//                         <div key={component.id} className='flex flex-col gap-4'>
//                             <React.Suspense fallback={<div>Loading...</div>}>
//                                 <Component selectedRun={selectedRun} sliderValue={sliderValue} />
//                             </React.Suspense>
//                             <button className='btn btn-danger' onClick={() => removeComponent(component.id)}>Remove</button>
//                         </div>
//                     );
//                 })}
//             </div>
//             <div style={{ height: '100px' }}>
//             </div>

//         </div>
//     );
// }



// import React, { useState, useEffect } from 'react';
// import './Visualizationselection.css';

// const componentsMap = {
//     info: React.lazy(() => import('./Infovisualizer')),
//     graph: React.lazy(() => import('./Graphvisualizer')),
//     model: React.lazy(() => import('./Modelvisualizer')),
// };

// export default function ComponentSelector({ selectedRun, sliderValue }) {
//     const [selectedComponent, setSelectedComponent] = useState([
//         { id: 1, type: 'info' },
//         { id: 3, type: 'graph' },
//         { id: 2, type: 'model' },
//     ]);
//     const [containerSize, setContainerSize] = useState({ width: window.innerWidth, height: window.innerHeight });

//     const addComponent = (value) => {
//         const newComponents = [...selectedComponent, { id: Date.now(), type: value }];
//         setSelectedComponent(newComponents);
//     };

//     const removeComponent = (id) => {
//         setSelectedComponent(selectedComponent.filter((component) => component.id !== id));
//     };

//     useEffect(() => {
//         const handleResize = () => {
//             const sidebarWidth = document.getElementById('sidebar').offsetWidth;
//             setContainerSize({ width: window.innerWidth - sidebarWidth - 100, height: window.innerHeight });
//         };

//         window.addEventListener('resize', handleResize);
//         handleResize();

//         return () => {
//             window.removeEventListener('resize', handleResize);
//         };
//     }, []);

//     return (
//         <>
//         <div className='flex flex-col items-center p-6' id='visualization-component-wrapper' style={{ width: containerSize.width, height: containerSize.height }}>
//             <div className='flex gap-4'>
//                 <button className='btn btn-primary' onClick={() => addComponent('info')}>Add Info</button>
//                 <button className='btn btn-primary' onClick={() => addComponent('graph')}>Add Graph</button>
//                 <button className='btn btn-primary' onClick={() => addComponent('model')}>Add Model</button>
//             </div>
//             <div className='flex flex-wrap gap-4 mt-4'>
//                 {selectedComponent.map((component) => {
//                     const Component = componentsMap[component.type];
//                     const wrapperClass = component.type === 'graph' ? 'graph-wrapper' : 'component-wrapper';
//                     return (
//                         <div key={component.id} className={wrapperClass}>
//                             <React.Suspense fallback={<div>Loading...</div>}>
//                                 <Component selectedRun={selectedRun} sliderValue={sliderValue} />
//                             </React.Suspense>
//                             <button className='btn btn-danger' onClick={() => removeComponent(component.id)}>Remove</button>
//                         </div>
//                     );
//                 })}
//             </div>
//             {/* <h1>a</h1> */}
//             <div style={{height: '100px'}}></div>
//             <div className='playback-slider-space'></div>
//         </div>
//         </>
//     );
// }


import React, { useState, useEffect } from 'react';
import './Visualizationselection.css';

const componentsMap = {
    info: React.lazy(() => import('./Infovisualizer')),
    graph: React.lazy(() => import('./Graphvisualizer')),
    model: React.lazy(() => import('./Modelvisualizer')),
};

export default function ComponentSelector({ selectedRun, sliderValue }) {
    const [selectedComponent, setSelectedComponent] = useState([
        { id: 1, type: 'info' },
        { id: 2, type: 'graph' },
        { id: 3, type: 'model' },
    ]);
    const [containerSize, setContainerSize] = useState({ width: window.innerWidth, height: window.innerHeight });

    const addComponent = (value) => {
        const newComponents = [...selectedComponent, { id: Date.now(), type: value }];
        setSelectedComponent(newComponents);
    };

    const removeComponent = (id) => {
        setSelectedComponent(selectedComponent.filter((component) => component.id !== id));
    };

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
                    <h1 className='text-2xl font-bold mb-4'>Visualization Selection</h1>
            <div className='flex gap-4'>
                <button className='btn btn-primary' onClick={() => addComponent('info')} style={{margin: '5px'}}>Add Info</button>
                <button className='btn btn-primary' onClick={() => addComponent('graph')} style={{margin: '5px'}}>Add Graph</button>
                <button className='btn btn-primary' onClick={() => addComponent('model')} style={{margin: '5px'}}>Add Model</button>
            </div>
        <div className='flex flex-col items-center p-6' id='visualization-component-wrapper' style={{ width: containerSize.width, height: containerSize.height }}>

            <div className='flex flex-wrap gap-4 mt-4' style={{ flex: 1 }}>
                {selectedComponent.map((component) => {
                    const Component = componentsMap[component.type];
                    const wrapperClass = component.type === 'graph' ? 'graph-wrapper' : component.type === 'model' ? 'model-wrapper' : 'component-wrapper';
                    return (
                        <div key={component.id} className={wrapperClass} style={{ flex: '1 1 auto' }}>
                            <React.Suspense fallback={<div>Loading...</div>}>
                                <Component selectedRun={selectedRun} sliderValue={sliderValue} />
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
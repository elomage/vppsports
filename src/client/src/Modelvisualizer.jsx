import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader';

const SERVER_URL = import.meta.env.VITE_SERVER_URL;
const ACCESS_TOKEN_STORAGE_KEY = "vppsports_access_token";

const getAuthHeaders = () => {
    const token = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
    return token ? { Authorization: `Bearer ${token}` } : {};
};

const fetchRunSensorOrientation = async (runid, accelerometerid, gyroscopeid, magnetometerid) => {
    try {
        const response = await fetch(`${SERVER_URL}/run/${runid}/sensor/orientation?accelerometerid=${accelerometerid}&gyroscopeid=${gyroscopeid}&magnetometerid=${magnetometerid}`, {
            headers: getAuthHeaders(),
            credentials: 'include',
        });
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching data:', error);
    }
};

const binarySearchNearest = (readings, ts) => {
    let lo = 0, hi = readings.length - 1;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (readings[mid].timestamp < ts) lo = mid + 1;
        else hi = mid;
    }
    if (lo > 0 && Math.abs(readings[lo - 1].timestamp - ts) < Math.abs(readings[lo].timestamp - ts)) {
        return readings[lo - 1];
    }
    return readings[lo];
};

const ModelVisualizer = ({ selectedRun, sliderValue, data, removeFunction }) => {
    const controlsRef = useRef(null);
    const objectRef = useRef(null);
    const containerRef = useRef(null);
    const [sensitivity, setSensitivity] = useState(1);

    const rotationReadings = useMemo(() => {
        if (!Array.isArray(selectedRun?.data)) return [];
        return selectedRun.data
            .filter(d => d.sensorType === 'gyroscope' && Array.isArray(d.data) && d.data.length >= 3)
            .sort((a, b) => a.timestamp - b.timestamp);
    }, [selectedRun]);

    const resetIMUZoom = () => {
        if (controlsRef.current) {
            controlsRef.current.reset();
        }
    };

    useEffect(() => {
        const canvas = document.querySelector('#bg');
        const container = containerRef.current;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(90, container.clientWidth / container.clientHeight, 0.1, 1000);

        const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.setSize(container.clientWidth, container.clientHeight);

        camera.position.setZ(0.75);
        camera.position.setY(0.75);
        camera.position.setX(0.75);


        //LOAD BOX OBJECT
        const geometry = new THREE.BoxGeometry(10, 3, 16, 100);
        const material = new THREE.MeshStandardMaterial({ color: 0xFF6347 });
        const torus = new THREE.Mesh(geometry, material);
        torus.scale.set(0.05, 0.05, 0.05); 
        const faceColors = [0xff0000, 0x00ff00, 0x0000ff, 0xffff00, 0xff00ff, 0x00ffff];
        const materials = faceColors.map(color => new THREE.MeshStandardMaterial({ color }));
        torus.material = materials;
        // torus.rotation.z = Math.PI;


        //LOAD BOX MODEL

        scene.add(torus);
        objectRef.current = torus;


        //LOAD MODEL OBJECT
        
        // const objLoader = new OBJLoader();
        // objLoader.load(
        //     './model.obj',
        //     function (object) {
        //         object.rotation.x = -(Math.PI / 2);
        //         object.scale.set(0.025, 0.025, 0.025);
        //         scene.add(object);
        //         objectRef.current = object;
        //     },
        //     function (xhr) {
        //         
        //     },
        //     function (error) {
        //         console.error('An error happened', error);
        //     }
        // );

        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5); // soft white light
        scene.add(ambientLight);

        const gridHelper = new THREE.GridHelper(10, 1);
        const axesHelper = new THREE.AxesHelper(0);
        // axesHelper.material.linewidth = 5;
        // axesHelper.setColors(
        //     new THREE.Color(0x75ecef),
        //     new THREE.Color(0x00ff00),
        //     new THREE.Color(0xf2ba55)
        // );
        scene.add(gridHelper, axesHelper);

        const controls = new OrbitControls(camera, renderer.domElement);
        controlsRef.current = controls;

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }

        animate();

        const handleResize = () => {
            const container = containerRef.current;
            if (container) {
                camera.aspect = container.clientWidth / container.clientHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(container.clientWidth, container.clientHeight);
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            renderer.dispose();
            controls.dispose();
        };
    }, []);

    useEffect(() => {
        if (!objectRef.current || !selectedRun) return;

        // Path 1: direct gyroscope sensor readings (primary)
        if (rotationReadings.length > 0) {
            const currentTs = selectedRun.totalTimestamps?.[sliderValue];
            if (currentTs == null) return;
            const reading = binarySearchNearest(rotationReadings, currentTs);
            if (reading) {
                objectRef.current.rotation.x = reading.data[0] * sensitivity;
                objectRef.current.rotation.y = reading.data[1] * sensitivity;
                objectRef.current.rotation.z = reading.data[2] * sensitivity;
            }
            return;
        }

        // Path 2: pre-computed orientationData (legacy fallback)
        if (selectedRun.orientationData?.length > 0) {
            const currentTs = selectedRun.totalTimestamps?.[sliderValue];
            if (currentTs == null) return;
            const orientation = selectedRun.orientationData.reduce((prev, curr) =>
                Math.abs(curr.timestamp - currentTs) < Math.abs(prev.timestamp - currentTs) ? curr : prev,
                selectedRun.orientationData[0]
            );
            if (orientation) {
                objectRef.current.rotation.x = -orientation.pitch;
                objectRef.current.rotation.y = orientation.yaw;
                objectRef.current.rotation.z = orientation.roll;
            }
        }
    }, [sliderValue, selectedRun, rotationReadings, sensitivity]);

    useEffect(() => {
        let arrowHelper;
        const scaleFactor = 2; // Scale factor to make the vector bigger

        if (objectRef.current && selectedRun && selectedRun.data) {
            // const accelerometer = selectedRun.filteredRunData?.data?.find(d => d._id === "accelerometer") || selectedRun.data.find(d => d._id === "accelerometer");

            const accelerometer = selectedRun.data.filter(d => d.sensorId === 1);

            // if (accelerometer && accelerometer.readings) {
            if (accelerometer && accelerometer.length > 0) {
                const updateVector = () => {
                    // const reading = accelerometer.readings[sliderValue];
                    const reading = accelerometer[sliderValue];
                    if (reading) {
                        const gravity = 1; // Earth's gravity in m/s^2
                        const [rawX, rawY, rawZ] = reading.data;
                        // const [rawX, rawY, rawZ] = reading;
                        const x = rawX;
                        const y = rawY;
                        const z = -rawZ; // Remove gravity from the Z-axis

                        

                        const forceVector = new THREE.Vector3(x, z, y).multiplyScalar(scaleFactor); // Scale the vector

                        const length = forceVector.length();

                        if (!arrowHelper) {
                            arrowHelper = new THREE.ArrowHelper(
                                forceVector.clone().normalize(), // Direction
                                objectRef.current.position,      // Origin
                                length,                          // Length
                                0xff0000,                        // Color
                                undefined,                       // Head length (default)
                                0.1                              // Head width (increased thickness)
                            );
                            objectRef.current.parent.add(arrowHelper);
                        } else {
                            arrowHelper.setDirection(forceVector.clone().normalize());
                            arrowHelper.setLength(length);
                        }
                    }
                };

                updateVector();
            }
        }

        return () => {
            if (arrowHelper) {
                objectRef.current.parent.remove(arrowHelper);
                arrowHelper = null;
            }
        };
    }, [sliderValue, selectedRun]);

    useEffect(() => {
        const axesLength = 15; // Length of the axes

        if (objectRef.current) {
            // Create X-axis
            const xAxis = new THREE.ArrowHelper(
                new THREE.Vector3(1, 0, 0), // Direction
                new THREE.Vector3(0, 0, 0), // Origin
                axesLength,                 // Length
                0xff0000                    // Color (red for X-axis)
            );
            objectRef.current.add(xAxis);

            // Create Y-axis
            const yAxis = new THREE.ArrowHelper(
                new THREE.Vector3(0, 1, 0), // Direction
                new THREE.Vector3(0, 0, 0), // Origin
                axesLength,                 // Length
                0x00ff00                    // Color (green for Y-axis)
            );
            objectRef.current.add(yAxis);

            // Create Z-axis
            const zAxis = new THREE.ArrowHelper(
                new THREE.Vector3(0, 0, 1), // Direction
                new THREE.Vector3(0, 0, 0), // Origin
                axesLength,                 // Length
                0x0000ff                    // Color (blue for Z-axis)
            );
            objectRef.current.add(zAxis);
        }
    }, [selectedRun]);

    return (
        <>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 10px', borderBottom: '1px solid #dee2e6', flexShrink: 0, gap: '12px' }}>
            <button id="reset-imu-zoom-button" onClick={resetIMUZoom} className="btn btn-sm btn-outline-primary">
                Reset Zoom
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1 }}>
                <label style={{ fontSize: '13px', whiteSpace: 'nowrap', margin: 0 }}>Sensitivity: {sensitivity.toFixed(2)}x</label>
                <input
                    type="range"
                    min="0.01"
                    max="2"
                    step="0.01"
                    value={sensitivity}
                    onChange={e => setSensitivity(Number(e.target.value))}
                    style={{ flex: 1 }}
                />
            </div>
            <button type="button" className="btn btn-sm btn-outline-danger" onClick={removeFunction}>
                Remove
            </button>
        </div>
        <div id="rotation-visualizer" ref={containerRef} style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center', 
            flex: 1,
            minHeight: 0,
            height: '100%'
        }}>
            <canvas id="bg" style={{ width: '100%', height: '100%' }}></canvas>
        </div>
        </>
    );
};

export default ModelVisualizer;

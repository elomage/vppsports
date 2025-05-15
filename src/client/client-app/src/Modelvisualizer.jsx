import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader';

const ModelVisualizer = ({ selectedRun, sliderValue }) => {
    const controlsRef = useRef(null);
    const objectRef = useRef(null);
    const containerRef = useRef(null);

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

        camera.position.setZ(1);
        camera.position.setY(2);
        camera.position.setX(2);


        //LOAD BOX OBJECT
        const geometry = new THREE.BoxGeometry(10, 3, 16, 100);
        const material = new THREE.MeshStandardMaterial({ color: 0xFF6347 });
        const torus = new THREE.Mesh(geometry, material);
        torus.scale.set(0.05, 0.05, 0.05); 
        torus.rotation.y = Math.PI / 2;
        scene.add(torus);
        objectRef.current = torus;


        ////LOAD MODEL OBJECT
        //
        // const objLoader = new OBJLoader();
        // objLoader.load(
        //     './public/model.obj',
        //     function (object) {
        //         object.rotation.x = -(Math.PI / 2);
        //         object.scale.set(0.25, 0.25, 0.25);
        //         scene.add(object);
        //         objectRef.current = object;
        //     },
        //     function (xhr) {
        //         console.log((xhr.loaded / xhr.total * 100) + '% loaded');
        //     },
        //     function (error) {
        //         console.error('An error happened', error);
        //     }
        // );

        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5); // soft white light
        scene.add(ambientLight);

        const gridHelper = new THREE.GridHelper(10, 1);
        const axesHelper = new THREE.AxesHelper(2);
        // axesHelper.material.linewidth = 5;
        axesHelper.setColors(
            new THREE.Color(0x75ecef),
            new THREE.Color(0x00ff00),
            new THREE.Color(0xf2ba55)
        );
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
            camera.aspect = container.clientWidth / container.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(container.clientWidth, container.clientHeight);
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            renderer.dispose();
            controls.dispose();
        };
    }, []);

    useEffect(() => {
        if (objectRef.current && selectedRun && selectedRun.orientationData) {
            const orientation = selectedRun.orientationData[sliderValue];
            if (orientation) {
                const [time, roll, yaw, pitch] = orientation;
                objectRef.current.rotation.x = pitch - Math.PI / 2;
                objectRef.current.rotation.y = yaw;
                objectRef.current.rotation.z = roll;
            }
        }
    }, [sliderValue, selectedRun]);

    useEffect(() => {
        let arrowHelper;
        const scaleFactor = 2; // Scale factor to make the vector bigger

        if (objectRef.current && selectedRun && selectedRun.data) {
            const accelerometer = selectedRun.filteredRunData.data.find(d => d._id === "accelerometer");
            if (accelerometer && accelerometer.readings) {
                const updateVector = () => {
                    const reading = accelerometer.readings[sliderValue];
                    if (reading) {
                        const gravity = 1; // Earth's gravity in m/s^2
                        const [rawX, rawY, rawZ] = reading.data;
                        const x = rawX;
                        const y = rawY;
                        const z = rawZ - gravity; // Remove gravity from the Z-axis

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

    return (
        <>
        <button id="reset-imu-zoom-button" onClick={resetIMUZoom} className="btn-reset-zoom">
            Reset Zoom
        </button>
        <div id="rotation-visualizer" ref={containerRef} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', maxHeight: '60vh'}}>
            <div style={{ width: '100%', height: '50%' }}>
                <canvas id="bg" style={{ width: '100%', height: '100%', maxHeight: '300px' }}></canvas>
            </div>
        </div>
        </>
    );
};

export default ModelVisualizer;
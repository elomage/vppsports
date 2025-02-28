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

        camera.position.setZ(20);
        camera.position.setY(10);
        camera.position.setX(10);

        const geometry = new THREE.BoxGeometry(10, 3, 16, 100);
        const material = new THREE.MeshStandardMaterial({ color: 0xFF6347 });
        const torus = new THREE.Mesh(geometry, material);

        // scene.add(torus);

        const objLoader = new OBJLoader();
        objLoader.load(
            './public/model.obj',
            function (object) {
                object.rotation.x = -(Math.PI / 2);
                object.scale.set(0.25, 0.25, 0.25);
                scene.add(object);
                objectRef.current = object;
            },
            function (xhr) {
                console.log((xhr.loaded / xhr.total * 100) + '% loaded');
            },
            function (error) {
                console.error('An error happened', error);
            }
        );

        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5); // soft white light
        scene.add(ambientLight);

        const gridHelper = new THREE.GridHelper(200, 50);
        const axesHelper = new THREE.AxesHelper(5);
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

        // Cleanup on component unmount
        return () => {
            window.removeEventListener('resize', handleResize);
            renderer.dispose();
            controls.dispose();
        };
    }, []);

    useEffect(() => {
        if (objectRef.current && selectedRun) {
            const orientation = selectedRun.orientationData[sliderValue];
            if (orientation) {
                const [time, roll, yaw, pitch] = orientation;
                objectRef.current.rotation.x = pitch - Math.PI / 2;
                objectRef.current.rotation.y = yaw;
                objectRef.current.rotation.z = roll;
            }
        }
    }, [sliderValue, selectedRun]);

    return (
        <>
        <h1>Model Visualizer</h1>
        <div id="rotation-visualizer" ref={containerRef} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', maxHeight: '60vh'}}>
            <div style={{ width: '100%', height: '50%' }}>
                <canvas id="bg" style={{ width: '100%', height: '100%' }}></canvas>
            </div>
            <button id="reset-imu-zoom-button" onClick={resetIMUZoom}>
                Reset IMU Zoom
            </button>
        </div>
        </>
    );
};

export default ModelVisualizer;
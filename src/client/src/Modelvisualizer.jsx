import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const SERVER_URL = import.meta.env.VITE_SERVER_URL;
const ACCESS_TOKEN_STORAGE_KEY = "vppsports_access_token";

const getAuthHeaders = () => {
    const token = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
    return token ? { Authorization: `Bearer ${token}` } : {};
};

const fetchJson = async (url) => {
    const response = await fetch(url, { headers: getAuthHeaders(), credentials: 'include' });
    if (!response.ok) throw new Error('Network response was not ok');
    return response.json();
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

const ModelVisualizer = ({ selectedRun, sliderValue, effectiveTimestamps, removeFunction }) => {
    const controlsRef = useRef(null);
    const objectRef = useRef(null);
    const containerRef = useRef(null);
    const [gyroReadings, setGyroReadings] = useState([]);
    const [loadError, setLoadError] = useState(null);
    const [sensitivity, setSensitivity] = useState(0.05);

    useEffect(() => {
        const runId = selectedRun?._id;
        if (!runId) {
            setGyroReadings([]);
            return;
        }

        let cancelled = false;
        setLoadError(null);

        const load = async () => {
            try {
                const sensors = await fetchJson(`${SERVER_URL}/run/${runId}/sensor`);
                if (cancelled) return;

                const gyroSensor = Array.isArray(sensors)
                    ? sensors.find(s => s.sensorType === 'gyroscope')
                    : null;

                if (!gyroSensor) {
                    setGyroReadings([]);
                    return;
                }

                const filters = encodeURIComponent(JSON.stringify([{ type: 'movingaverage', params: { windowSize: 50 } }]));
                const data = await fetchJson(`${SERVER_URL}/run/${runId}/sensor/${gyroSensor.sensorId}/data?filters=${filters}`);
                if (cancelled) return;

                const readings = Array.isArray(data) ? data : (Array.isArray(data?.readings) ? data.readings : []);
                setGyroReadings(readings.sort((a, b) => a.timestamp - b.timestamp));
            } catch (err) {
                if (!cancelled) setLoadError(err.message);
            }
        };

        load();
        return () => { cancelled = true; };
    }, [selectedRun?._id]);

    // Set up Three.js scene once.
    useEffect(() => {
        const container = containerRef.current;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(90, container.clientWidth / container.clientHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.setSize(container.clientWidth, container.clientHeight);
        container.appendChild(renderer.domElement);

        camera.position.set(0.75, 0.75, 0.75);

        const geometry = new THREE.BoxGeometry(10, 3, 16, 100);
        const faceColors = [0xff0000, 0x00ff00, 0x0000ff, 0xffff00, 0xff00ff, 0x00ffff];
        const mesh = new THREE.Mesh(geometry, faceColors.map(c => new THREE.MeshStandardMaterial({ color: c })));
        mesh.scale.set(0.05, 0.05, 0.05);
        scene.add(mesh);
        objectRef.current = mesh;

        // Axis arrows attached to the mesh.
        const axesLength = 15;
        [
            [new THREE.Vector3(1, 0, 0), 0xff0000],
            [new THREE.Vector3(0, 1, 0), 0x00ff00],
            [new THREE.Vector3(0, 0, 1), 0x0000ff],
        ].forEach(([dir, color]) => mesh.add(new THREE.ArrowHelper(dir, new THREE.Vector3(0, 0, 0), axesLength, color)));

        scene.add(new THREE.AmbientLight(0xffffff, 0.5));
        scene.add(new THREE.GridHelper(10, 1));

        const controls = new OrbitControls(camera, renderer.domElement);
        controlsRef.current = controls;

        const FRAME_INTERVAL = 1000 / 60;
        let lastFrameTime = 0;
        const animate = (now) => {
            requestAnimationFrame(animate);
            if (now - lastFrameTime < FRAME_INTERVAL) return;
            lastFrameTime = now;
            controls.update();
            renderer.render(scene, camera);
        };
        animate(0);

        const handleResize = () => {
            if (!containerRef.current) return;
            camera.aspect = containerRef.current.clientWidth / containerRef.current.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
        };
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            renderer.dispose();
            controls.dispose();
            container.removeChild(renderer.domElement);
        };
    }, []);

    useEffect(() => {
        if (!objectRef.current || gyroReadings.length === 0) return;

        const timestamps = effectiveTimestamps ?? selectedRun?.totalTimestamps;
        const currentTs = timestamps?.[sliderValue];
        if (currentTs == null) return;

        const reading = binarySearchNearest(gyroReadings, currentTs);
        if (reading?.data?.length >= 3) {
            objectRef.current.rotation.x = reading.data[0] * sensitivity;
            objectRef.current.rotation.y = reading.data[1] * sensitivity;
            objectRef.current.rotation.z = reading.data[2] * sensitivity;
        }
    }, [sliderValue, gyroReadings, effectiveTimestamps, selectedRun?.totalTimestamps, sensitivity]);

    const resetZoom = () => controlsRef.current?.reset();

    return (
        <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 10px', borderBottom: '1px solid #dee2e6', flexShrink: 0, gap: '12px' }}>
                <button onClick={resetZoom} className="btn btn-sm btn-outline-primary">Reset Zoom</button>
                {loadError && <span style={{ fontSize: '12px', color: '#dc3545' }}>Failed to load gyroscope data</span>}
                {!loadError && gyroReadings.length === 0 && selectedRun && (
                    <span style={{ fontSize: '12px', color: '#6c757d' }}>No gyroscope sensor found</span>
                )}
                <button type="button" className="btn btn-sm btn-outline-danger" onClick={removeFunction}>Remove</button>
            </div>
            <div
                ref={containerRef}
                id="rotation-visualizer"
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, minHeight: 0, height: '100%' }}
            />
        </>
    );
};

export default ModelVisualizer;

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import 'bootstrap/dist/js/bootstrap.bundle.min';
import 'bootstrap/dist/css/bootstrap.min.css';
import '@fortawesome/fontawesome-free/css/all.min.css';

import Chart from 'chart.js/auto';
import Hammer from 'hammerjs';
import zoomPlugin from 'chartjs-plugin-zoom';
import moment from 'moment';
import annotationPlugin from 'chartjs-plugin-annotation';
import 'chartjs-adapter-moment';
// import Popper from '@popperjs/core';

Chart.register(zoomPlugin, annotationPlugin);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

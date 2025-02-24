import React from 'react';

const InfoVisualizer = ({ selectedRun }) => (
  <>
    <h1>Info Visualizer</h1>
    <figure id="run-info">
      <b>
        <figcaption id="run-info-title">Selected run: {selectedRun._id}</figcaption>
      </b>
      <ul id="run-info-items">
        <li>Date: {selectedRun.date}</li>
        <li>Description: {selectedRun.description}</li>
        <li>Weather: {selectedRun.weather}</li>
      </ul>
      {selectedRun.Track && (
        <>
          <b>
            <figcaption id="run-info-track-title">Selected Track: {selectedRun.Track._id}</figcaption>
          </b>
          <ul id="run-info-track">
            <li>Track Name: {selectedRun.Track.name}</li>
          </ul>
        </>
      )}
      {selectedRun.Driver && (
        <>
          <b>
            <figcaption id="run-info-driver-title">Selected Driver: {selectedRun.Driver._id}</figcaption>
          </b>
          <ul id="run-info-driver">
            <li>Driver Name: {selectedRun.Driver.name}</li>
            <li>Driver Surname: {selectedRun.Driver.surname}</li>
          </ul>
        </>
      )}
    </figure>
  </>
);

export default InfoVisualizer;
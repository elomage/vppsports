import React from 'react';
import './Sidebar.css';

const Sidebar = () => (
    <nav className="sidebar bg-light navbar-expand-lg navbar-light" id="sidebar">
        <button className="btn btn-primary d-md-none navbar-toggler" type="button" data-toggle="collapse" data-target="#sidebarContent" aria-expanded="false" aria-controls="sidebarContent">
          <span className="navbar-toggler-icon"></span>
        </button>
        <div className="collapse d-md-block" id="sidebarContent">
            <ul>
              <li><a href="/">Dashboard</a></li>
              <li><a href="/config">Configuration</a></li>
            </ul>
        </div>
    </nav>
);

export default Sidebar;
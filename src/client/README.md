# Setup

## Install dependencies
```
npm install
```

## .ENV file structure
Create .env file in current directory and add line

```bash
VITE_SERVER_URL=... (where backend server is hosted, example, http://localhost:8080)
```

To run the frontend server in dev
```
npm run dev
```
connect to the local server `http://localhost:5173`
# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

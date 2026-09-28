import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import { Cabinet } from "./Cabinet.jsx";
import "./styles.css";
import "./cabinet.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {window.location.pathname.startsWith('/cabinet') ? <Cabinet /> : <App />}
  </React.StrictMode>,
);

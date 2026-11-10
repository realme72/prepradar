import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// Mount <App/> into <div id="root"> from index.html. StrictMode runs effects twice
// in development to surface missing cleanups (our useApi abort handles that).
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

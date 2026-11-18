import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AccountProvider } from "./account";
import { PolicyPage, isPolicyPath } from "./components/Policies";
import "./styles.css";

// Mount <App/> into <div id="root"> from index.html. StrictMode runs effects twice
// in development to surface missing cleanups (our useApi abort handles that).
// /pricing, /terms and the other policy pages are plain views (any path serves index.html).
const path = window.location.pathname.replace(/\/+$/, "");
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AccountProvider>
      {isPolicyPath(path) ? <PolicyPage path={path} /> : <App />}
    </AccountProvider>
  </StrictMode>,
);

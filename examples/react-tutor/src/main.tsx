import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/archivo/standard.css";
import "@fontsource-variable/inter";
import "./brand/tokens.css";
import "./styles.css";
import { DemoIdentity } from "./DemoIdentity";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DemoIdentity />
  </React.StrictMode>,
);

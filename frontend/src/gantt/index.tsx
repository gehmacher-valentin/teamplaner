import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./gantt.css";
import { Gantt } from "./Gantt";

const wurzel = document.getElementById("gantt");
if (wurzel) {
  createRoot(wurzel).render(
    <StrictMode>
      <Gantt />
    </StrictMode>,
  );
}

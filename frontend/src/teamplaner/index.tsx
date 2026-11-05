import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./teamplaner.css";
import { Teamplaner } from "./Teamplaner";

const wurzel = document.getElementById("teamplaner");
if (wurzel) {
  createRoot(wurzel).render(
    <StrictMode>
      <Teamplaner planen={wurzel.dataset.planen === "1"} />
    </StrictMode>,
  );
}

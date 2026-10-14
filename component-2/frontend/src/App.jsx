import { useState } from "react";
import { FiFileText, FiCheckSquare, FiClock, FiLayout } from "react-icons/fi";
import GenerateUml from "./pages/GenerateUml.jsx";
import ValidateUml from "./pages/ValidateUml.jsx";
import History from "./pages/History.jsx";
import Wireframes from "./pages/Wireframes.jsx";

// Every page of the app. To add a page: make a file in pages/ and add one line here.
const PAGES = [
  { id: "generate", label: "Generate UML", icon: <FiFileText />, page: <GenerateUml /> },
  { id: "validate", label: "Validate diagram", icon: <FiCheckSquare />, page: <ValidateUml /> },
  { id: "history", label: "History", icon: <FiClock />, page: <History /> },
  { id: "wireframes", label: "Wireframes", icon: <FiLayout />, page: <Wireframes />, soon: true },
];

export default function App() {
  const [current, setCurrent] = useState("generate");

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="brand">
          InteliSE
          <span>UML generation and validation</span>
        </div>
        {PAGES.map((p) => (
          <button key={p.id} className={p.id === current ? "nav active" : "nav"} onClick={() => setCurrent(p.id)}>
            {p.icon} {p.label}
            {p.soon && <em>soon</em>}
          </button>
        ))}
      </nav>
      <main className="content">{PAGES.find((p) => p.id === current).page}</main>
    </div>
  );
}
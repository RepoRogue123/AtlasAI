import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import MissionControl from "./pages/MissionControl";
import RunView from "./pages/RunView";
import Runs from "./pages/Runs";
import Skills from "./pages/Skills";
import Sandbox from "./pages/Sandbox";

const Evals = lazy(() => import("./pages/Evals"));   // recharts is only needed here

export default function App() {
  return (
    <Shell>
      <Suspense fallback={null}>
      <Routes>
        <Route path="/" element={<MissionControl />} />
        <Route path="/runs/:runId" element={<RunView />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/skills" element={<Skills />} />
        <Route path="/evals" element={<Evals />} />
        <Route path="/sandbox" element={<Sandbox />} />
      </Routes>
      </Suspense>
    </Shell>
  );
}

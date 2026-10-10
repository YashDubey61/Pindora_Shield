import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/home";
import MoleculeViewer from "./pages/MoleculeViewer";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/viewer" element={<MoleculeViewer />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

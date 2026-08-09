import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Home from "./components/Home.jsx";
import AddPage from "./components/AddPage.jsx";
import ListingsPage from "./components/ListingsPage.jsx";
import ListingDetail from "./components/ListingDetail.jsx";
import AdminPage from "./components/AdminPage.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <Link to="/">
            <h1>🏠 Roost</h1>
          </Link>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/add" element={<AddPage />} />
            <Route path="/triage" element={<ListingsPage status="triage" />} />
            <Route path="/approved" element={<ListingsPage status="approved" />} />
            <Route path="/rejected" element={<ListingsPage status="rejected" />} />
            <Route path="/listings/:id" element={<ListingDetail />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

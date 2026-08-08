import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Home from "./components/Home.jsx";
import AddPage from "./components/AddPage.jsx";
import ListingsPage from "./components/ListingsPage.jsx";
import ListingDetail from "./components/ListingDetail.jsx";

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
            <Route path="/active" element={<ListingsPage status="active" />} />
            <Route path="/in-review" element={<ListingsPage status="in_review" />} />
            <Route path="/listings/:id" element={<ListingDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

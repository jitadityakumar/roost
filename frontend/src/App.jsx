import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Home from "./components/Home.jsx";
import AddPage from "./components/AddPage.jsx";
import ListingsPage from "./components/ListingsPage.jsx";
import ListingDetail from "./components/ListingDetail.jsx";
import AdminPage from "./components/AdminPage.jsx";
import JourneyDetailsPage from "./components/JourneyDetailsPage.jsx";
import MapPage from "./components/MapPage.jsx";
import FloorplanTracePage from "./components/FloorplanTracePage.jsx";
import FloorplanBaselineTracePage from "./components/FloorplanBaselineTracePage.jsx";
import { USER_STATUSES } from "./userStatus.js";

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
            {USER_STATUSES.map((status) => (
              <Route key={status} path={`/${status}`} element={<ListingsPage status={status} />} />
            ))}
            <Route path="/listings/:id" element={<ListingDetail />} />
            <Route path="/listings/:id/trace" element={<FloorplanTracePage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/admin/floorplan-baseline/trace" element={<FloorplanBaselineTracePage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/journey-details/:poolId" element={<JourneyDetailsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

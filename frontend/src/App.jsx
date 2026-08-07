import { useState } from "react";
import Dashboard from "./components/Dashboard.jsx";
import ListingDetail from "./components/ListingDetail.jsx";

export default function App() {
  const [selectedId, setSelectedId] = useState(null);

  return (
    <div className="app">
      <header className="app-header">
        <h1 onClick={() => setSelectedId(null)}>🏠 Roost</h1>
      </header>
      <main>
        {selectedId ? (
          <ListingDetail id={selectedId} onBack={() => setSelectedId(null)} />
        ) : (
          <Dashboard onSelect={setSelectedId} />
        )}
      </main>
    </div>
  );
}

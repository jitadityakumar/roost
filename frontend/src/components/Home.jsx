import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div className="home-menu">
      <Link className="home-option" to="/add">
        Add property
      </Link>
      <Link className="home-option" to="/triage">
        View triage
      </Link>
      <Link className="home-option" to="/approved">
        View approved
      </Link>
      <Link className="home-option" to="/rejected">
        View rejected
      </Link>
    </div>
  );
}

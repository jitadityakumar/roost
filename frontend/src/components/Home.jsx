import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div className="home-menu">
      <Link className="home-option" to="/add">
        Add property
      </Link>
      <Link className="home-option" to="/active">
        View active
      </Link>
      <Link className="home-option" to="/in-review">
        View in-review
      </Link>
    </div>
  );
}

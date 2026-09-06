import { Link } from "react-router-dom";
import { USER_STATUSES, USER_STATUS_LABEL } from "../userStatus.js";

export default function Home() {
  return (
    <div className="home-menu">
      <Link className="home-option" to="/add">
        Add property
      </Link>
      {USER_STATUSES.map((status) => (
        <Link key={status} className="home-option" to={`/${status}`}>
          View {USER_STATUS_LABEL[status].toLowerCase()}
        </Link>
      ))}
      <Link className="home-option" to="/admin">
        Admin
      </Link>
    </div>
  );
}

import { Link } from "react-router-dom";
import { HOME_MENU_ORDER, USER_STATUS_LABEL } from "../userStatus.js";

export default function Home() {
  return (
    <div className="home-menu">
      <Link className="home-option" to="/add">
        Add property
      </Link>
      {HOME_MENU_ORDER.map((status) => (
        <Link key={status} className={`home-option status-${status}`} to={`/${status}`}>
          {USER_STATUS_LABEL[status]}
        </Link>
      ))}
      <Link className="home-option" to="/map">
        Map view
      </Link>
      <Link className="home-option" to="/admin">
        Admin
      </Link>
    </div>
  );
}

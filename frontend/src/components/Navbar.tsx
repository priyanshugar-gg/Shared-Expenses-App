import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { logout } = useAuth();
  return (
    <nav className="bg-slate-800 text-white px-6 py-3 flex justify-between items-center">
      <Link to="/" className="font-bold text-lg">Shared Expenses</Link>
      <button onClick={logout} className="text-sm bg-slate-700 px-3 py-1 rounded hover:bg-slate-600">
        Log out
      </button>
    </nav>
  );
}
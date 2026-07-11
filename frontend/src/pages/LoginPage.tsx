import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await login(username, password);
      navigate("/");
    } catch (err: any) {
      setError("Login failed. Check your credentials.");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form onSubmit={handleSubmit} className="bg-white p-8 rounded shadow w-80">
        <h1 className="text-xl font-bold mb-4">Log in</h1>
        {error && <p className="text-red-600 text-sm mb-2">{error}</p>}
        <input className="w-full border p-2 mb-3 rounded" placeholder="Username"
          value={username} onChange={(e) => setUsername(e.target.value)} />
        <input className="w-full border p-2 mb-3 rounded" placeholder="Password" type="password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <button className="w-full bg-slate-800 text-white py-2 rounded hover:bg-slate-700">Log in</button>
        <p className="text-sm mt-3 text-center">
          No account? <Link to="/register" className="text-blue-600">Register</Link>
        </p>
      </form>
    </div>
  );
}
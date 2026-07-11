import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";

export default function RegisterPage() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.register(username, email, password);
      navigate("/login");
    } catch (err: any) {
      setError("Registration failed: " + err.message);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form onSubmit={handleSubmit} className="bg-white p-8 rounded shadow w-80">
        <h1 className="text-xl font-bold mb-4">Register</h1>
        {error && <p className="text-red-600 text-xs mb-2 break-words">{error}</p>}
        <input className="w-full border p-2 mb-3 rounded" placeholder="Username"
          value={username} onChange={(e) => setUsername(e.target.value)} />
        <input className="w-full border p-2 mb-3 rounded" placeholder="Email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className="w-full border p-2 mb-3 rounded" placeholder="Password" type="password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <button className="w-full bg-slate-800 text-white py-2 rounded hover:bg-slate-700">Register</button>
        <p className="text-sm mt-3 text-center">
          Have an account? <Link to="/login" className="text-blue-600">Log in</Link>
        </p>
      </form>
    </div>
  );
}
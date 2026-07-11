import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Group } from "../types";
import Navbar from "../components/Navbar";

export default function GroupsPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [newName, setNewName] = useState("");

  function load() { api.getGroups().then(setGroups); }
  useEffect(load, []);

  async function createGroup(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    await api.createGroup(newName);
    setNewName("");
    load();
  }

  return (
    <div>
      <Navbar />
      <div className="max-w-2xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-4">Your Groups</h1>
        <form onSubmit={createGroup} className="flex gap-2 mb-6">
          <input className="border p-2 rounded flex-1" placeholder="New group name"
            value={newName} onChange={(e) => setNewName(e.target.value)} />
          <button className="bg-slate-800 text-white px-4 rounded">Create</button>
        </form>
        <ul className="space-y-2">
          {groups.map((g) => (
            <li key={g.id}>
              <Link to={`/groups/${g.id}`} className="block bg-white p-4 rounded shadow hover:bg-slate-50">
                <span className="font-semibold">{g.name}</span>
                <span className="text-sm text-slate-500 ml-2">{g.memberships.length} members</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
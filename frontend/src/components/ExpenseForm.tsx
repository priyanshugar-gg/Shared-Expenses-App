import { useState } from "react";
import { api } from "../api/client";
import type { Group } from "../types";

export default function ExpenseForm({ group, onClose, onCreated }: { group: Group; onClose: () => void; onCreated: () => void }) {
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [paidBy, setPaidBy] = useState(group.memberships[0]?.id ?? 0);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [splitType, setSplitType] = useState<"equal" | "unequal" | "percentage" | "share">("equal");
  const [selected, setSelected] = useState<number[]>(group.memberships.map((m) => m.id));
  const [values, setValues] = useState<Record<number, string>>({});
  const [error, setError] = useState("");

  function toggle(id: number) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    let participants: any[] = [];
    if (splitType === "equal") {
      participants = selected.map((id) => ({ member_id: id }));
    } else if (splitType === "unequal") {
      participants = selected.map((id) => ({ member_id: id, amount: values[id] || "0" }));
    } else if (splitType === "percentage") {
      participants = selected.map((id) => ({ member_id: id, percentage: values[id] || "0" }));
    } else {
      participants = selected.map((id) => ({ member_id: id, units: values[id] || "1" }));
    }

    try {
      await api.createExpense({
        group: group.id, description, paid_by: paidBy, date, currency, amount,
        split_type: splitType, participants,
      });
      onCreated();
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white p-4 rounded shadow mb-4 space-y-3">
      {error && <p className="text-red-600 text-xs break-words">{error}</p>}
      <input className="w-full border p-2 rounded" placeholder="Description" value={description}
        onChange={(e) => setDescription(e.target.value)} required />
      <div className="flex gap-2">
        <input className="border p-2 rounded flex-1" placeholder="Amount" value={amount}
          onChange={(e) => setAmount(e.target.value)} required />
        <select className="border p-2 rounded" value={currency} onChange={(e) => setCurrency(e.target.value)}>
          <option value="INR">INR</option>
          <option value="USD">USD</option>
        </select>
      </div>
      <div className="flex gap-2">
        <select className="border p-2 rounded flex-1" value={paidBy} onChange={(e) => setPaidBy(Number(e.target.value))}>
          {group.memberships.map((m) => <option key={m.id} value={m.id}>{m.user.username}</option>)}
        </select>
        <input className="border p-2 rounded" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <select className="border p-2 rounded w-full" value={splitType} onChange={(e) => setSplitType(e.target.value as any)}>
        <option value="equal">Equal</option>
        <option value="unequal">Unequal</option>
        <option value="percentage">Percentage</option>
        <option value="share">Share</option>
      </select>
      <div>
        <p className="text-sm font-medium mb-1">Participants:</p>
        {group.memberships.map((m) => (
          <div key={m.id} className="flex items-center gap-2 mb-1">
            <input type="checkbox" checked={selected.includes(m.id)} onChange={() => toggle(m.id)} />
            <span className="w-24">{m.user.username}</span>
            {selected.includes(m.id) && splitType !== "equal" && (
              <input className="border p-1 rounded w-24 text-sm"
                placeholder={splitType === "unequal" ? "amount" : splitType === "percentage" ? "%" : "units"}
                value={values[m.id] || ""}
                onChange={(e) => setValues({ ...values, [m.id]: e.target.value })} />
            )}
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <button className="bg-slate-800 text-white px-4 py-2 rounded">Create</button>
        <button type="button" onClick={onClose} className="px-4 py-2 rounded border">Cancel</button>
      </div>
    </form>
  );
}
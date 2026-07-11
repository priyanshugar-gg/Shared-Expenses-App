import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Group, Expense, BalancesResponse, BalanceTrace } from "../types";
import Navbar from "../components/Navbar";
import ExpenseForm from "../components/ExpenseForm";
import ImportPanel from "../components/ImportPanel";

type Tab = "expenses" | "balances" | "members" | "import";

export default function GroupDetailPage() {
  const { id } = useParams();
  const groupId = Number(id);
  const [group, setGroup] = useState<Group | null>(null);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [balances, setBalances] = useState<BalancesResponse | null>(null);
  const [tab, setTab] = useState<Tab>("expenses");
  const [showExpenseForm, setShowExpenseForm] = useState(false);
  const [trace, setTrace] = useState<{ username: string; data: BalanceTrace } | null>(null);
  const [newMemberUserId, setNewMemberUserId] = useState("");
  const [newMemberJoined, setNewMemberJoined] = useState("");

  function loadAll() {
    api.getGroup(groupId).then(setGroup);
    api.getExpenses(groupId).then(setExpenses);
    api.getBalances(groupId).then(setBalances);
  }
  useEffect(loadAll, [groupId]);

  async function viewTrace(membershipId: number, username: string) {
    const data = await api.getBalanceTrace(groupId, membershipId);
    setTrace({ username, data });
  }

  async function recordSettlement(fromUsername: string, toUsername: string, amount: string) {
    if (!group) return;
    const fromM = group.memberships.find((m) => m.user.username === fromUsername);
    const toM = group.memberships.find((m) => m.user.username === toUsername);
    if (!fromM || !toM) return;
    await api.createSettlement({
      group: groupId, paid_by: fromM.id, paid_to: toM.id,
      amount, currency: "INR", date: new Date().toISOString().slice(0, 10),
    });
    loadAll();
  }

  async function addMember(e: React.FormEvent) {
    e.preventDefault();
    if (!newMemberUserId || !newMemberJoined) return;
    await api.addMember(groupId, Number(newMemberUserId), newMemberJoined);
    setNewMemberUserId(""); setNewMemberJoined("");
    loadAll();
  }

  async function markLeft(membershipId: number) {
    const date = prompt("Left date (YYYY-MM-DD):");
    if (!date) return;
    await api.updateMember(groupId, membershipId, date);
    loadAll();
  }

  if (!group) return <div className="p-6">Loading...</div>;

  return (
    <div>
      <Navbar />
      <div className="max-w-4xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-2">{group.name}</h1>
        <div className="flex gap-4 border-b mb-4">
          {(["expenses", "balances", "members", "import"] as Tab[]).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`pb-2 capitalize ${tab === t ? "border-b-2 border-slate-800 font-semibold" : "text-slate-500"}`}>
              {t}
            </button>
          ))}
        </div>

        {tab === "expenses" && (
          <div>
            <button onClick={() => setShowExpenseForm(true)} className="bg-slate-800 text-white px-4 py-2 rounded mb-4">
              + Add Expense
            </button>
            {showExpenseForm && (
              <ExpenseForm group={group} onClose={() => setShowExpenseForm(false)}
                onCreated={() => { setShowExpenseForm(false); loadAll(); }} />
            )}
            <ul className="space-y-2">
              {expenses.map((e) => (
                <li key={e.id} className="bg-white p-3 rounded shadow">
                  <div className="flex justify-between">
                    <span className="font-medium">{e.description}</span>
                    <span>{e.currency} {e.amount}</span>
                  </div>
                  <div className="text-xs text-slate-500">{e.date} · {e.split_type} · {e.source}</div>
                  <div className="text-xs mt-1">
                    {e.splits.map((s) => (
                      <span key={s.id} className="mr-3">{s.member_username}: ₹{s.share_amount}</span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {tab === "balances" && balances && (
          <div>
            <h2 className="font-semibold mb-2">Net Balances</h2>
            <ul className="space-y-1 mb-6">
              {balances.balances.map((b) => (
                <li key={b.membership_id} className="flex justify-between bg-white p-2 rounded shadow">
                  <button className="text-blue-600 underline" onClick={() => viewTrace(b.membership_id, b.username)}>
                    {b.username}
                  </button>
                  <span className={Number(b.net_balance) < 0 ? "text-red-600" : "text-green-600"}>
                    ₹{b.net_balance}
                  </span>
                </li>
              ))}
            </ul>
            <h2 className="font-semibold mb-2">Suggested Settlements</h2>
            <ul className="space-y-1">
              {balances.settle_up.map((s, i) => (
                <li key={i} className="flex justify-between items-center bg-white p-2 rounded shadow">
                  <span>{s.from_username} → {s.to_username}: ₹{s.amount}</span>
                  <button className="text-xs bg-green-600 text-white px-2 py-1 rounded"
                    onClick={() => recordSettlement(s.from_username, s.to_username, s.amount)}>
                    Mark Settled
                  </button>
                </li>
              ))}
              {balances.settle_up.length === 0 && <li className="text-slate-500 text-sm">All settled up.</li>}
            </ul>

            {trace && (
              <div className="mt-6 bg-white p-4 rounded shadow">
                <h3 className="font-semibold mb-2">{trace.username}'s balance trace (₹{trace.data.net_balance})</h3>
                <p className="text-sm font-medium mt-2">Expenses paid:</p>
                <ul className="text-sm">
                  {trace.data.expenses_paid.map((e) => (
                    <li key={e.id}>{e.date} — {e.description}: +₹{e.amount_base_currency}</li>
                  ))}
                </ul>
                <p className="text-sm font-medium mt-2">Shares owed:</p>
                <ul className="text-sm">
                  {trace.data.expense_shares_owed.map((s, i) => (
                    <li key={i}>{s.expense__date} — {s.expense__description}: -₹{s.share_amount}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {tab === "members" && (
          <div>
            <ul className="space-y-1 mb-4">
              {group.memberships.map((m) => (
                <li key={m.id} className="flex justify-between bg-white p-2 rounded shadow">
                  <span>{m.user.username} (joined {m.joined_at}{m.left_at ? `, left ${m.left_at}` : ""})</span>
                  {!m.left_at && <button className="text-xs text-red-600" onClick={() => markLeft(m.id)}>Mark left</button>}
                </li>
              ))}
            </ul>
            <form onSubmit={addMember} className="flex gap-2">
              <input className="border p-2 rounded" placeholder="User ID" value={newMemberUserId}
                onChange={(e) => setNewMemberUserId(e.target.value)} />
              <input className="border p-2 rounded" type="date" value={newMemberJoined}
                onChange={(e) => setNewMemberJoined(e.target.value)} />
              <button className="bg-slate-800 text-white px-4 rounded">Add Member</button>
            </form>
          </div>
        )}

        {tab === "import" && <ImportPanel groupId={groupId} onCommitted={loadAll} />}
      </div>
    </div>
  );
}
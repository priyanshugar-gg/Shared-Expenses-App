import { useState } from "react";
import { api } from "../api/client";
import type { ImportBatch, ImportReport } from "../types";

export default function ImportPanel({ groupId, onCommitted }: { groupId: number; onCommitted: () => void }) {
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");

  async function upload() {
    if (!file) return;
    setError("");
    try {
      const b = await api.uploadImport(groupId, file);
      setBatch(b);
      setReport(null);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function resolveRow(rowId: number, resolution: "approved" | "rejected") {
    if (!batch) return;
    await api.updateImportRow(batch.id, rowId, { resolution });
    const refreshed = await api.getImportBatch(batch.id);
    setBatch(refreshed);
  }

  async function commit() {
    if (!batch) return;
    const committed = await api.commitImport(batch.id);
    setBatch(committed);
    const r = await api.getImportReport(batch.id);
    setReport(r);
    onCommitted();
  }

  const needsReview = batch?.rows.filter((r) => r.resolution === null && r.proposed_action !== "skip") ?? [];

  return (
    <div>
      <div className="flex gap-2 mb-4">
        <input type="file" accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button onClick={upload} className="bg-slate-800 text-white px-4 py-2 rounded">Upload & Scan</button>
      </div>
      {error && <p className="text-red-600 text-sm mb-2 break-words">{error}</p>}

      {batch && (
        <div className="bg-white p-4 rounded shadow mb-4">
          <p className="font-semibold">Batch #{batch.id} — {batch.status} — {batch.total_rows} rows</p>
          <p className="text-sm text-slate-500">
            {batch.rows.filter((r) => r.resolution === "approved").length} auto/approved,{" "}
            {needsReview.length} need review,{" "}
            {batch.rows.filter((r) => r.proposed_action === "skip").length} skipped (duplicates)
          </p>
        </div>
      )}

      {needsReview.length > 0 && (
        <div className="space-y-2 mb-4">
          <h3 className="font-semibold">Rows needing review</h3>
          {needsReview.map((row) => (
            <div key={row.id} className="bg-white p-3 rounded shadow">
              <p className="text-sm font-medium">Row {row.row_number}: {row.raw_data.description}</p>
              <ul className="text-xs text-slate-600 mb-2">
                {row.anomalies.map((a, i) => (
                  <li key={i} className={a.severity === "high" ? "text-red-600" : a.severity === "medium" ? "text-orange-600" : ""}>
                    [{a.severity}] {a.message}
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <button onClick={() => resolveRow(row.id, "approved")}
                  className="text-xs bg-green-600 text-white px-2 py-1 rounded">Approve</button>
                <button onClick={() => resolveRow(row.id, "rejected")}
                  className="text-xs bg-red-600 text-white px-2 py-1 rounded">Reject</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {batch && batch.status === "pending_review" && (
        <button onClick={commit} className="bg-blue-700 text-white px-4 py-2 rounded">
          Commit Import
        </button>
      )}

      {report && (
        <div className="bg-white p-4 rounded shadow mt-4">
          <h3 className="font-semibold mb-2">Import Report</h3>
          <p className="text-sm">Created: {report.created_expenses} expenses, {report.created_settlements} settlements</p>
          <p className="text-sm">Skipped duplicates: {report.skipped_as_duplicate}</p>
          <p className="text-sm">Still pending review: {report.still_pending_review}</p>
          <p className="text-sm font-medium mt-2">Anomaly counts:</p>
          <ul className="text-xs">
            {Object.entries(report.anomaly_counts_by_type).map(([type, count]) => (
              <li key={type}>{type}: {count}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
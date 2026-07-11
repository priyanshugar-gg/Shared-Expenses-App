export interface User { id: number; username: string; }

export interface GroupMembership {
  id: number;
  group: number;
  user: User;
  joined_at: string;
  left_at: string | null;
}

export interface Group {
  id: number;
  name: string;
  created_by: User;
  created_at: string;
  memberships: GroupMembership[];
}

export interface ExpenseSplit {
  id: number;
  member: number;
  member_username: string;
  share_amount: string;
}

export interface Expense {
  id: number;
  group: number;
  description: string;
  paid_by: number;
  date: string;
  currency: string;
  amount: string;
  amount_base_currency: string;
  split_type: "equal" | "unequal" | "percentage" | "share";
  notes: string;
  source: string;
  splits: ExpenseSplit[];
}

export interface Settlement {
  id: number;
  group: number;
  paid_by: number;
  paid_by_username: string;
  paid_to: number;
  paid_to_username: string;
  amount: string;
  currency: string;
  date: string;
  notes: string;
}

export interface BalanceEntry { membership_id: number; username: string; net_balance: string; }
export interface SettleUpEntry { from_username: string; to_username: string; amount: string; }
export interface BalancesResponse { balances: BalanceEntry[]; settle_up: SettleUpEntry[]; }

export interface BalanceTrace {
  expenses_paid: { id: number; description: string; date: string; amount_base_currency: string }[];
  expense_shares_owed: { expense_id: number; expense__description: string; expense__date: string; share_amount: string }[];
  settlements_paid: { id: number; paid_to__user__username: string; amount: string; date: string }[];
  settlements_received: { id: number; paid_by__user__username: string; amount: string; date: string }[];
  net_balance: string;
}

export interface Anomaly { type: string; message: string; severity: "low" | "medium" | "high"; }

export interface ImportRow {
  id: number;
  row_number: number;
  raw_data: Record<string, any>;
  resolved_data: Record<string, any> | null;
  anomalies: Anomaly[];
  proposed_action: string;
  resolution: "approved" | "rejected" | "edited" | null;
  resolution_notes: string;
  resulting_expense: number | null;
  resulting_settlement: number | null;
}

export interface ImportBatch {
  id: number;
  group: number;
  file_name: string;
  uploaded_by_username: string;
  uploaded_at: string;
  status: "scanning" | "pending_review" | "committed" | "cancelled";
  total_rows: number;
  rows: ImportRow[];
}

export interface ImportReport {
  batch_id: number;
  file_name: string;
  status: string;
  total_rows: number;
  created_expenses: number;
  created_settlements: number;
  skipped_as_duplicate: number;
  still_pending_review: number;
  rejected_by_user: number;
  anomaly_counts_by_type: Record<string, number>;
  rows_with_anomalies: { row_number: number; anomalies: Anomaly[]; proposed_action: string; resolution: string | null }[];
}
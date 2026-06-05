CREATE TABLE vendors (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL
);

CREATE TABLE invoices (
  id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(id),
  invoice_number TEXT NOT NULL,
  amount REAL NOT NULL,
  invoice_date TEXT NOT NULL,
  due_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'paid', 'void')),
  UNIQUE(vendor_id, invoice_number)
);

CREATE TABLE payments (
  id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(id),
  invoice_id TEXT REFERENCES invoices(id),
  amount REAL NOT NULL,
  payment_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('unmatched', 'matched', 'duplicate', 'void')),
  duplicate_of_payment_id TEXT REFERENCES payments(id)
);

CREATE TABLE bank_transactions (
  id TEXT PRIMARY KEY,
  payment_id TEXT REFERENCES payments(id),
  transaction_date TEXT NOT NULL,
  description TEXT NOT NULL,
  amount REAL NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE journal_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_date TEXT NOT NULL,
  account TEXT NOT NULL,
  debit REAL NOT NULL DEFAULT 0,
  credit REAL NOT NULL DEFAULT 0,
  memo TEXT NOT NULL
);

CREATE TABLE reconciliation_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bank_transaction_id TEXT REFERENCES bank_transactions(id),
  description TEXT NOT NULL,
  amount REAL NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'resolved'))
);

CREATE TABLE close_tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'complete')),
  completed_at TEXT
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT,
  action TEXT NOT NULL,
  record_id TEXT,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

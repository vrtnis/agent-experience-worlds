CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  version TEXT NOT NULL,
  path TEXT NOT NULL,
  body TEXT NOT NULL
);

CREATE TABLE contracts (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  document_id TEXT NOT NULL REFERENCES documents(id),
  effective_date TEXT NOT NULL
);

CREATE TABLE clauses (
  id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL REFERENCES contracts(id),
  document_id TEXT NOT NULL REFERENCES documents(id),
  clause_type TEXT NOT NULL,
  text TEXT NOT NULL,
  start_char INTEGER NOT NULL,
  end_char INTEGER NOT NULL
);

CREATE TABLE parties (
  id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL REFERENCES contracts(id),
  name TEXT NOT NULL,
  role TEXT NOT NULL
);

CREATE TABLE obligations (
  id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL REFERENCES contracts(id),
  obligation_type TEXT NOT NULL,
  description TEXT NOT NULL,
  source_clause_id TEXT REFERENCES clauses(id)
);

CREATE TABLE deadlines (
  id TEXT PRIMARY KEY,
  obligation_id TEXT NOT NULL REFERENCES obligations(id),
  due_date TEXT NOT NULL,
  description TEXT NOT NULL
);

CREATE TABLE risks (
  id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL REFERENCES contracts(id),
  risk_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE citations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_table TEXT NOT NULL,
  source_id TEXT NOT NULL,
  document_id TEXT NOT NULL REFERENCES documents(id),
  start_char INTEGER NOT NULL,
  end_char INTEGER NOT NULL,
  quote TEXT NOT NULL
);

CREATE TABLE matter_status (
  id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL REFERENCES contracts(id),
  status TEXT NOT NULL,
  updated_at TEXT
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT,
  action TEXT NOT NULL,
  record_id TEXT,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

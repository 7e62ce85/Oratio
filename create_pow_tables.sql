CREATE TABLE IF NOT EXISTS pow_verifications (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    hash TEXT NOT NULL,
    verified_at INTEGER NOT NULL,
    user_token TEXT NOT NULL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS pow_credits (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    invoice_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    amount REAL NOT NULL,
    created_at INTEGER NOT NULL,
    confirmed BOOLEAN DEFAULT FALSE,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id)
);

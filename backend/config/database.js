// Database connection - SQLite for simplicity, one file per company deployment.
// Swap to Postgres later by replacing this file only; nothing else touches SQL directly
// except through the model files, so the migration path stays clean.

const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');
require('dotenv').config();

const dbPath = process.env.DATABASE_PATH || './database/company_001.db';
const dbDir = path.dirname(dbPath);

if (!fs.existsSync(dbDir)) {
    fs.mkdirSync(dbDir, { recursive: true });
}

const db = new Database(dbPath);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

function initSchema() {
    const schemaPath = path.join(__dirname, '../../database/schema.sql');
    const schema = fs.readFileSync(schemaPath, 'utf8');
    db.exec(schema);
    console.log(`✓ Database initialized at ${dbPath}`);
}

module.exports = { db, initSchema };

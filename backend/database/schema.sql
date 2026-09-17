-- SocialFlow SaaS Database Schema

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    telegram_chat_id TEXT UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    telegram_bot_token TEXT,
    telegram_bot_username TEXT,
    timezone TEXT DEFAULT 'Africa/Mogadishu',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS workspace_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('owner', 'manager', 'editor', 'viewer')),
    invited_by INTEGER,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS social_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    platform TEXT NOT NULL CHECK(platform IN ('facebook', 'instagram', 'tiktok', 'twitter')),
    username TEXT NOT NULL,
    account_id TEXT,
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at DATETIME,
    connected_by INTEGER,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY (connected_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    file_url TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK(file_type IN ('image', 'video')),
    file_size INTEGER,
    telegram_file_id TEXT,
    uploaded_by INTEGER,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY (uploaded_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS scheduled_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    caption TEXT,
    platforms TEXT NOT NULL,  -- JSON array e.g. ["instagram","tiktok"]
    scheduled_time DATETIME NOT NULL,
    status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled', 'posting', 'posted', 'failed', 'cancelled')),
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS post_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_post_id INTEGER NOT NULL,
    media_file_id INTEGER NOT NULL,
    FOREIGN KEY (scheduled_post_id) REFERENCES scheduled_posts(id),
    FOREIGN KEY (media_file_id) REFERENCES media_files(id)
);

CREATE TABLE IF NOT EXISTS post_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_post_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    platform_post_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed')),
    error_message TEXT,
    posted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scheduled_post_id) REFERENCES scheduled_posts(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_scheduled_posts_time ON scheduled_posts(scheduled_time, status);
CREATE INDEX IF NOT EXISTS idx_social_accounts_workspace ON social_accounts(workspace_id);
CREATE INDEX IF NOT EXISTS idx_media_workspace ON media_files(workspace_id);


const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { db } = require('../config/database');

// POST /api/auth/signup
// Creates the user AND their first workspace (they become 'owner')
function signup(req, res) {
    const { email, password, fullName, workspaceName } = req.body;

    if (!email || !password || !workspaceName) {
        return res.status(400).json({ error: 'email, password, and workspaceName are required' });
    }

    const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(email);
    if (existing) {
        return res.status(409).json({ error: 'Email already registered' });
    }

    const passwordHash = bcrypt.hashSync(password, 10);

    const insertUser = db.prepare(
        'INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)'
    );
    const userResult = insertUser.run(email, passwordHash, fullName || null);
    const userId = userResult.lastInsertRowid;

    const insertWorkspace = db.prepare(
        'INSERT INTO workspaces (name, owner_id) VALUES (?, ?)'
    );
    const wsResult = insertWorkspace.run(workspaceName, userId);
    const workspaceId = wsResult.lastInsertRowid;

    db.prepare(
        'INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (?, ?, ?)'
    ).run(workspaceId, userId, 'owner');

    // Every new workspace starts with a subscription row. TRIAL_DAYS=0 (the
    // default) skips the trial and goes straight to pending_payment; set
    // TRIAL_DAYS to a positive number to give new signups free time first.
    const trialDays = parseInt(process.env.TRIAL_DAYS || '0', 10);
    const subStatus = trialDays > 0 ? 'trial' : 'pending_payment';
    const trialEndsAt = trialDays > 0
        ? new Date(Date.now() + trialDays * 24 * 60 * 60 * 1000).toISOString()
        : null;

    db.prepare(
        'INSERT INTO subscriptions (workspace_id, status, trial_ends_at) VALUES (?, ?, ?)'
    ).run(workspaceId, subStatus, trialEndsAt);

    const token = jwt.sign(
        { id: userId, email, workspaceId, role: 'owner' },
        process.env.JWT_SECRET,
        { expiresIn: process.env.JWT_EXPIRY || '7d' }
    );

    res.status(201).json({
        token,
        user: { id: userId, email, fullName },
        workspace: { id: workspaceId, name: workspaceName, role: 'owner' },
        subscription: { status: subStatus, trialEndsAt }
    });
}

// POST /api/auth/login
function login(req, res) {
    const { email, password, workspaceId } = req.body;

    const user = db.prepare('SELECT * FROM users WHERE email = ?').get(email);
    if (!user || !bcrypt.compareSync(password, user.password_hash)) {
        return res.status(401).json({ error: 'Invalid email or password' });
    }

    // Find their workspace membership (use provided workspaceId, or default to first one)
    let membership;
    if (workspaceId) {
        membership = db.prepare(
            'SELECT * FROM workspace_members WHERE user_id = ? AND workspace_id = ?'
        ).get(user.id, workspaceId);
    } else {
        membership = db.prepare(
            'SELECT * FROM workspace_members WHERE user_id = ? LIMIT 1'
        ).get(user.id);
    }

    if (!membership) {
        return res.status(403).json({ error: 'No workspace access found for this user' });
    }

    const token = jwt.sign(
        { id: user.id, email: user.email, workspaceId: membership.workspace_id, role: membership.role },
        process.env.JWT_SECRET,
        { expiresIn: process.env.JWT_EXPIRY || '7d' }
    );

    res.json({
        token,
        user: { id: user.id, email: user.email, fullName: user.full_name },
        workspace: { id: membership.workspace_id, role: membership.role }
    });
}

// GET /api/auth/me
function me(req, res) {
    const user = db.prepare('SELECT id, email, full_name, telegram_chat_id FROM users WHERE id = ?').get(req.user.id);
    res.json({ user, workspaceId: req.user.workspaceId, role: req.user.role });
}

module.exports = { signup, login, me };

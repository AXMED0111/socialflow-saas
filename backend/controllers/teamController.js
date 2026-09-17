const bcrypt = require('bcryptjs');
const { db } = require('../config/database');

// GET /api/team - list all members of the workspace
function listMembers(req, res) {
    const members = db.prepare(`
        SELECT u.id, u.email, u.full_name, wm.role, wm.joined_at
        FROM workspace_members wm
        JOIN users u ON u.id = wm.user_id
        WHERE wm.workspace_id = ?
        ORDER BY wm.joined_at ASC
    `).all(req.user.workspaceId);

    res.json({ members });
}

// POST /api/team/invite - Manager+ invites a new member by email
// If the user doesn't exist yet, creates them with a temp password they must reset.
function inviteMember(req, res) {
    const { email, role } = req.body;
    const validRoles = ['manager', 'editor', 'viewer'];

    if (!email || !validRoles.includes(role)) {
        return res.status(400).json({ error: `role must be one of: ${validRoles.join(', ')}` });
    }

    // Only owner can invite managers; managers can invite editor/viewer
    if (role === 'manager' && req.user.role !== 'owner') {
        return res.status(403).json({ error: 'Only the owner can invite managers' });
    }

    let user = db.prepare('SELECT id FROM users WHERE email = ?').get(email);

    if (!user) {
        const tempPassword = bcrypt.hashSync(Math.random().toString(36).slice(-10), 10);
        const result = db.prepare(
            'INSERT INTO users (email, password_hash) VALUES (?, ?)'
        ).run(email, tempPassword);
        user = { id: result.lastInsertRowid };
    }

    const existingMembership = db.prepare(
        'SELECT id FROM workspace_members WHERE workspace_id = ? AND user_id = ?'
    ).get(req.user.workspaceId, user.id);

    if (existingMembership) {
        return res.status(409).json({ error: 'User is already a member of this workspace' });
    }

    db.prepare(
        'INSERT INTO workspace_members (workspace_id, user_id, role, invited_by) VALUES (?, ?, ?, ?)'
    ).run(req.user.workspaceId, user.id, role, req.user.id);

    logAudit(req.user.workspaceId, req.user.id, 'invite_member', `Invited ${email} as ${role}`);

    res.status(201).json({ message: `${email} invited as ${role}` });
}

// PATCH /api/team/:userId/role - change a member's role (owner only)
function changeRole(req, res) {
    const { userId } = req.params;
    const { role } = req.body;

    if (req.user.role !== 'owner') {
        return res.status(403).json({ error: 'Only the owner can change roles' });
    }

    db.prepare(
        'UPDATE workspace_members SET role = ? WHERE workspace_id = ? AND user_id = ?'
    ).run(role, req.user.workspaceId, userId);

    logAudit(req.user.workspaceId, req.user.id, 'change_role', `Changed user ${userId} to ${role}`);
    res.json({ message: 'Role updated' });
}

// DELETE /api/team/:userId - remove a member
function removeMember(req, res) {
    const { userId } = req.params;

    if (req.user.role !== 'owner' && req.user.role !== 'manager') {
        return res.status(403).json({ error: 'Insufficient permissions' });
    }

    db.prepare(
        'DELETE FROM workspace_members WHERE workspace_id = ? AND user_id = ?'
    ).run(req.user.workspaceId, userId);

    logAudit(req.user.workspaceId, req.user.id, 'remove_member', `Removed user ${userId}`);
    res.json({ message: 'Member removed' });
}

// GET /api/team/bot-link - the shareable Telegram bot link for this workspace
// This is the "manager shares bot with media person" flow.
function getBotShareLink(req, res) {
    const workspace = db.prepare('SELECT telegram_bot_username FROM workspaces WHERE id = ?').get(req.user.workspaceId);

    if (!workspace?.telegram_bot_username) {
        return res.status(404).json({ error: 'No Telegram bot configured for this workspace yet' });
    }

    res.json({
        botLink: `https://t.me/${workspace.telegram_bot_username}`,
        note: 'Share this link with anyone you want to allow uploading media. They will need to link their Telegram account via /start.'
    });
}

function logAudit(workspaceId, userId, action, details) {
    db.prepare(
        'INSERT INTO audit_log (workspace_id, user_id, action, details) VALUES (?, ?, ?, ?)'
    ).run(workspaceId, userId, action, details);
}

module.exports = { listMembers, inviteMember, changeRole, removeMember, getBotShareLink };

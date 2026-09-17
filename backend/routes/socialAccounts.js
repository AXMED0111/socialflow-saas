const express = require('express');
const router = express.Router();
const { requireAuth, requireRole } = require('../middleware/auth');
const { db } = require('../config/database');

router.use(requireAuth);

// GET /api/accounts - list connected social accounts for the workspace
router.get('/', (req, res) => {
    const accounts = db.prepare(`
        SELECT id, platform, username, is_active, created_at
        FROM social_accounts WHERE workspace_id = ?
    `).all(req.user.workspaceId);
    res.json({ accounts });
});

// POST /api/accounts - connect a new social account
// NOTE: In production this is replaced by an OAuth redirect flow per platform.
// For now it accepts a manually-entered token (useful for TikTok/dev testing).
router.post('/', requireRole('manager'), (req, res) => {
    const { platform, username, accessToken } = req.body;
    const validPlatforms = ['facebook', 'instagram', 'tiktok', 'twitter'];

    if (!validPlatforms.includes(platform)) {
        return res.status(400).json({ error: `platform must be one of: ${validPlatforms.join(', ')}` });
    }

    const result = db.prepare(`
        INSERT INTO social_accounts (workspace_id, platform, username, access_token, connected_by)
        VALUES (?, ?, ?, ?, ?)
    `).run(req.user.workspaceId, platform, username, accessToken || null, req.user.id);

    res.status(201).json({ id: result.lastInsertRowid, platform, username });
});

// DELETE /api/accounts/:id - disconnect
router.delete('/:id', requireRole('manager'), (req, res) => {
    db.prepare(
        'UPDATE social_accounts SET is_active = 0 WHERE id = ? AND workspace_id = ?'
    ).run(req.params.id, req.user.workspaceId);
    res.json({ message: 'Account disconnected' });
});

module.exports = router;

const { db } = require('../config/database');
const path = require('path');
const fs = require('fs');

const UPLOAD_DIR = process.env.UPLOAD_DIR || './uploads';
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

// GET /api/media - list media library for the workspace
function listMedia(req, res) {
    const media = db.prepare(`
        SELECT id, file_url, file_type, file_size, uploaded_at
        FROM media_files WHERE workspace_id = ?
        ORDER BY uploaded_at DESC LIMIT 100
    `).all(req.user.workspaceId);

    res.json({ media });
}

// POST /api/media/upload - dashboard file upload (multer puts file on req.file)
function uploadMedia(req, res) {
    if (!req.file) return res.status(400).json({ error: 'No file provided' });

    const fileType = req.file.mimetype.startsWith('video') ? 'video' : 'image';
    const fileUrl = `/uploads/${req.file.filename}`;

    const result = db.prepare(`
        INSERT INTO media_files (workspace_id, file_url, file_type, file_size, uploaded_by)
        VALUES (?, ?, ?, ?, ?)
    `).run(req.user.workspaceId, fileUrl, fileType, req.file.size, req.user.id);

    res.status(201).json({ id: result.lastInsertRowid, fileUrl, fileType });
}

// Internal function used by the Telegram bot webhook (not a route directly)
// Bot downloads the file from Telegram's servers, then calls this to register it.
function registerTelegramMedia({ workspaceId, fileUrl, fileType, fileSize, telegramFileId, uploadedByUserId }) {
    const result = db.prepare(`
        INSERT INTO media_files (workspace_id, file_url, file_type, file_size, telegram_file_id, uploaded_by)
        VALUES (?, ?, ?, ?, ?, ?)
    `).run(workspaceId, fileUrl, fileType, fileSize, telegramFileId, uploadedByUserId);

    return result.lastInsertRowid;
}

module.exports = { listMedia, uploadMedia, registerTelegramMedia, UPLOAD_DIR };

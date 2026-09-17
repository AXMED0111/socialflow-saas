const { db } = require('../config/database');

// GET /api/posts - list posts (optionally filter by status)
function listPosts(req, res) {
    const { status } = req.query;
    let query = `SELECT * FROM scheduled_posts WHERE workspace_id = ?`;
    const params = [req.user.workspaceId];

    if (status) {
        query += ` AND status = ?`;
        params.push(status);
    }
    query += ` ORDER BY scheduled_time DESC LIMIT 200`;

    const posts = db.prepare(query).all(...params);

    // attach media + results for each post
    const withDetails = posts.map(p => ({
        ...p,
        platforms: JSON.parse(p.platforms),
        media: db.prepare(`
            SELECT mf.id, mf.file_url, mf.file_type FROM post_media pm
            JOIN media_files mf ON mf.id = pm.media_file_id
            WHERE pm.scheduled_post_id = ?
        `).all(p.id),
        results: db.prepare(`SELECT * FROM post_results WHERE scheduled_post_id = ?`).all(p.id)
    }));

    res.json({ posts: withDetails });
}

// POST /api/posts - create a scheduled (or immediate) post
// body: { caption, platforms: ["instagram","tiktok"], mediaIds: [1,2], scheduledTime }
function createPost(req, res) {
    const { caption, platforms, mediaIds, scheduledTime } = req.body;

    if (!platforms?.length) return res.status(400).json({ error: 'At least one platform is required' });
    if (!mediaIds?.length) return res.status(400).json({ error: 'At least one media file is required' });

    const postTime = scheduledTime || new Date().toISOString(); // "now" if not provided

    const result = db.prepare(`
        INSERT INTO scheduled_posts (workspace_id, caption, platforms, scheduled_time, status, created_by)
        VALUES (?, ?, ?, ?, 'scheduled', ?)
    `).run(req.user.workspaceId, caption || '', JSON.stringify(platforms), postTime, req.user.id);

    const postId = result.lastInsertRowid;

    const linkMedia = db.prepare('INSERT INTO post_media (scheduled_post_id, media_file_id) VALUES (?, ?)');
    for (const mediaId of mediaIds) linkMedia.run(postId, mediaId);

    db.prepare(
        'INSERT INTO audit_log (workspace_id, user_id, action, details) VALUES (?, ?, ?, ?)'
    ).run(req.user.workspaceId, req.user.id, 'create_post', `Post #${postId} scheduled for ${postTime} on ${platforms.join(', ')}`);

    res.status(201).json({ id: postId, status: 'scheduled', scheduledTime: postTime });
}

// DELETE /api/posts/:id - cancel a scheduled post (only if not yet posted)
function cancelPost(req, res) {
    const { id } = req.params;
    const post = db.prepare('SELECT * FROM scheduled_posts WHERE id = ? AND workspace_id = ?').get(id, req.user.workspaceId);

    if (!post) return res.status(404).json({ error: 'Post not found' });
    if (post.status === 'posted') return res.status(400).json({ error: 'Cannot cancel a post that already went out' });

    db.prepare('UPDATE scheduled_posts SET status = ? WHERE id = ?').run('cancelled', id);
    res.json({ message: 'Post cancelled' });
}

module.exports = { listPosts, createPost, cancelPost };

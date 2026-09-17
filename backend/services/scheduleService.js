const cron = require('node-cron');
const { db } = require('../config/database');
const { PLATFORM_HANDLERS } = require('./socialPlatforms');

async function processDuePosts() {
    const now = new Date().toISOString();

    const duePosts = db.prepare(`
        SELECT * FROM scheduled_posts
        WHERE status = 'scheduled' AND scheduled_time <= ?
    `).all(now);

    for (const post of duePosts) {
        db.prepare('UPDATE scheduled_posts SET status = ? WHERE id = ?').run('posting', post.id);

        const platforms = JSON.parse(post.platforms);
        const mediaFiles = db.prepare(`
            SELECT mf.* FROM post_media pm
            JOIN media_files mf ON mf.id = pm.media_file_id
            WHERE pm.scheduled_post_id = ?
        `).all(post.id);

        let allSucceeded = true;

        for (const platform of platforms) {
            const account = db.prepare(`
                SELECT * FROM social_accounts
                WHERE workspace_id = ? AND platform = ? AND is_active = 1
                LIMIT 1
            `).get(post.workspace_id, platform);

            if (!account) {
                db.prepare(`
                    INSERT INTO post_results (scheduled_post_id, platform, status, error_message)
                    VALUES (?, ?, 'failed', ?)
                `).run(post.id, platform, 'No connected account for this platform');
                allSucceeded = false;
                continue;
            }

            const handler = PLATFORM_HANDLERS[platform];
            const result = await handler({ account, caption: post.caption, mediaFiles });

            db.prepare(`
                INSERT INTO post_results (scheduled_post_id, platform, platform_post_id, status, error_message)
                VALUES (?, ?, ?, ?, ?)
            `).run(
                post.id, platform,
                result.platformPostId || null,
                result.success ? 'success' : 'failed',
                result.error || null
            );

            if (!result.success) allSucceeded = false;
        }

        db.prepare('UPDATE scheduled_posts SET status = ? WHERE id = ?')
            .run(allSucceeded ? 'posted' : 'failed', post.id);

        console.log(`Post #${post.id} processed → ${allSucceeded ? 'posted' : 'had failures'}`);
    }
}

function startScheduler() {
    // Runs every minute - checks for posts due to go out
    cron.schedule('* * * * *', () => {
        processDuePosts().catch(err => console.error('Scheduler error:', err));
    });
    console.log('✓ Post scheduler running (checks every minute)');
}

module.exports = { startScheduler, processDuePosts };

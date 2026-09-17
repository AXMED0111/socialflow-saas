const { db } = require('../config/database');

// Protects the paid action (creating/scheduling posts). Everything else
// (login, signup, browsing, linking accounts, uploading media) stays open
// so a new signup can look around and get set up before paying.
//
// A subscription counts as active access when status is 'active', or
// status is 'trial' and trial_ends_at hasn't passed yet.
function requireActiveSubscription(req, res, next) {
    const sub = db.prepare(
        'SELECT * FROM subscriptions WHERE workspace_id = ?'
    ).get(req.user.workspaceId);

    if (!sub) {
        return res.status(403).json({ error: 'No subscription found for this workspace' });
    }

    const now = new Date();
    const trialActive = sub.status === 'trial' && sub.trial_ends_at && new Date(sub.trial_ends_at) > now;
    const paidActive = sub.status === 'active' && (!sub.current_period_end || new Date(sub.current_period_end) > now);

    if (trialActive || paidActive) {
        return next();
    }

    return res.status(402).json({
        error: 'Payment required',
        subscriptionStatus: sub.status,
        message: 'Your subscription is not active. Submit a payment claim via /api/billing/claim (or in the Telegram bot) and wait for approval.'
    });
}

// Simple shared-secret admin check for the billing review endpoints.
// Not tied to a user account on purpose: the Telegram bot's admin commands
// call these with the same key, set once in the bot's env.
function requireAdmin(req, res, next) {
    const key = req.headers['x-admin-key'];
    if (!key || !process.env.ADMIN_API_KEY || key !== process.env.ADMIN_API_KEY) {
        return res.status(403).json({ error: 'Admin key missing or invalid' });
    }
    next();
}

module.exports = { requireActiveSubscription, requireAdmin };

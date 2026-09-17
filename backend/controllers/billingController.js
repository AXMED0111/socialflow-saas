const { db } = require('../config/database');
const pricing = require('../services/pricingService');

const VALID_METHODS = ['local_manual', 'crypto', 'international'];

// GET /api/billing/status
function getStatus(req, res) {
    const sub = db.prepare(
        'SELECT * FROM subscriptions WHERE workspace_id = ?'
    ).get(req.user.workspaceId);

    if (!sub) {
        return res.status(404).json({ error: 'No subscription found' });
    }

    const pendingClaim = db.prepare(
        `SELECT id, method, billing_cycle, status, created_at FROM payment_claims
         WHERE workspace_id = ? AND status = 'pending'
         ORDER BY created_at DESC LIMIT 1`
    ).get(req.user.workspaceId);

    res.json({
        status: sub.status,
        plan: sub.plan,
        billingCycle: sub.billing_cycle,
        trialEndsAt: sub.trial_ends_at,
        currentPeriodEnd: sub.current_period_end,
        pendingClaim: pendingClaim || null
    });
}

// GET /api/billing/pricing  (optionally ?cycle=monthly|yearly)
// Shows customers what they'd pay right now, including any live seasonal
// discount, before they commit to a payment method.
function getPricing(req, res) {
    const { cycle } = req.query;

    if (cycle) {
        if (!pricing.isValidCycle(cycle)) {
            return res.status(400).json({ error: 'cycle must be monthly or yearly' });
        }
        return res.json(pricing.getPricing(cycle));
    }

    res.json(pricing.getAllPricing());
}

// POST /api/billing/claim
// Body: { method, billingCycle: 'monthly'|'yearly', reference, telegramChatId }
// The final price is computed server-side from the live pricing/promo at the
// moment of the claim (never trust a client-supplied amount).
function submitClaim(req, res) {
    const { method, billingCycle, reference, telegramChatId } = req.body;

    if (!method || !VALID_METHODS.includes(method)) {
        return res.status(400).json({ error: `method must be one of: ${VALID_METHODS.join(', ')}` });
    }
    const cycle = billingCycle || 'monthly';
    if (!pricing.isValidCycle(cycle)) {
        return res.status(400).json({ error: 'billingCycle must be monthly or yearly' });
    }

    const quote = pricing.getPricing(cycle);
    const amountLabel = `${quote.finalPrice} ${quote.currency}`;

    const result = db.prepare(
        `INSERT INTO payment_claims
            (workspace_id, method, billing_cycle, reference, amount, discount_percent, promo_name, telegram_chat_id, submitted_by)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).run(
        req.user.workspaceId, method, cycle, reference || null, amountLabel,
        quote.discountPercent, quote.promoName, telegramChatId || null, req.user.id
    );

    res.status(201).json({
        claim: {
            id: result.lastInsertRowid,
            method,
            billingCycle: cycle,
            amount: amountLabel,
            discountPercent: quote.discountPercent,
            promoName: quote.promoName,
            status: 'pending'
        },
        message: 'Payment claim submitted. An admin will review it shortly.'
    });
}

// GET /api/billing/claims?status=pending
function listClaims(req, res) {
    const status = req.query.status || 'pending';
    const claims = db.prepare(
        `SELECT pc.*, w.name AS workspace_name, u.email AS submitted_by_email
         FROM payment_claims pc
         JOIN workspaces w ON w.id = pc.workspace_id
         LEFT JOIN users u ON u.id = pc.submitted_by
         WHERE pc.status = ?
         ORDER BY pc.created_at ASC`
    ).all(status);

    res.json({ claims });
}

// POST /api/billing/claims/:id/approve
function approveClaim(req, res) {
    const claim = db.prepare('SELECT * FROM payment_claims WHERE id = ?').get(req.params.id);
    if (!claim) return res.status(404).json({ error: 'Claim not found' });
    if (claim.status !== 'pending') return res.status(409).json({ error: `Claim already ${claim.status}` });

    const cycle = claim.billing_cycle || 'monthly';
    const periodDays = pricing.PERIOD_DAYS[cycle] || pricing.PERIOD_DAYS.monthly;
    const periodEnd = new Date(Date.now() + periodDays * 24 * 60 * 60 * 1000).toISOString();

    const tx = db.transaction(() => {
        db.prepare(
            `UPDATE payment_claims SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?`
        ).run(claim.id);

        db.prepare(
            `UPDATE subscriptions SET status = 'active', billing_cycle = ?, current_period_end = ?, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = ?`
        ).run(cycle, periodEnd, claim.workspace_id);
    });
    tx();

    res.json({
        claim: { id: claim.id, status: 'approved' },
        subscription: { status: 'active', billingCycle: cycle, currentPeriodEnd: periodEnd },
        telegramChatId: claim.telegram_chat_id
    });
}

// POST /api/billing/claims/:id/reject
function rejectClaim(req, res) {
    const claim = db.prepare('SELECT * FROM payment_claims WHERE id = ?').get(req.params.id);
    if (!claim) return res.status(404).json({ error: 'Claim not found' });
    if (claim.status !== 'pending') return res.status(409).json({ error: `Claim already ${claim.status}` });

    db.prepare(
        `UPDATE payment_claims SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?`
    ).run(claim.id);

    res.json({
        claim: { id: claim.id, status: 'rejected' },
        telegramChatId: claim.telegram_chat_id
    });
}

// ---------- Promotions (seasonal/marketing discounts) ----------

// GET /api/billing/promotions/active — what a customer would currently see.
// Not admin-gated: this is exactly the discount info shown at checkout.
function getActivePromotion(req, res) {
    const monthly = pricing.getActivePromo('monthly');
    const yearly = pricing.getActivePromo('yearly');
    res.json({
        monthly: monthly ? { name: monthly.name, discountPercent: monthly.discount_percent, endsAt: monthly.ends_at } : null,
        yearly: yearly ? { name: yearly.name, discountPercent: yearly.discount_percent, endsAt: yearly.ends_at } : null
    });
}

// GET /api/billing/promotions — admin: full history
function listPromotions(req, res) {
    const promotions = db.prepare('SELECT * FROM promotions ORDER BY created_at DESC').all();
    res.json({ promotions });
}

// POST /api/billing/promotions — admin: create + activate a promo.
// Body: { name, discountPercent, billingCycle: 'monthly'|'yearly'|'both', days? }
// Deactivates any currently-active promo first, so there's only ever one live
// discount at a time (keeps pricing unambiguous).
function setPromotion(req, res) {
    const { name, discountPercent, billingCycle, days } = req.body;

    if (!name || !discountPercent) {
        return res.status(400).json({ error: 'name and discountPercent are required' });
    }
    const pct = parseInt(discountPercent, 10);
    if (!Number.isFinite(pct) || pct <= 0 || pct > 100) {
        return res.status(400).json({ error: 'discountPercent must be a number between 1 and 100' });
    }
    const cycle = billingCycle || 'both';
    if (!['monthly', 'yearly', 'both'].includes(cycle)) {
        return res.status(400).json({ error: "billingCycle must be 'monthly', 'yearly', or 'both'" });
    }

    const now = new Date();
    const endsAt = days ? new Date(now.getTime() + parseInt(days, 10) * 24 * 60 * 60 * 1000).toISOString() : null;

    const tx = db.transaction(() => {
        db.prepare('UPDATE promotions SET active = 0 WHERE active = 1').run();
        return db.prepare(
            `INSERT INTO promotions (name, discount_percent, billing_cycle, active, starts_at, ends_at)
             VALUES (?, ?, ?, 1, ?, ?)`
        ).run(name, pct, cycle, now.toISOString(), endsAt);
    });
    const result = tx();

    res.status(201).json({
        promotion: { id: result.lastInsertRowid, name, discountPercent: pct, billingCycle: cycle, endsAt }
    });
}

// POST /api/billing/promotions/clear — admin: turn off any live promo.
function clearPromotion(req, res) {
    db.prepare('UPDATE promotions SET active = 0 WHERE active = 1').run();
    res.json({ message: 'Promotion cleared. Customers will see standard pricing.' });
}

module.exports = {
    getStatus,
    getPricing,
    submitClaim,
    listClaims,
    approveClaim,
    rejectClaim,
    getActivePromotion,
    listPromotions,
    setPromotion,
    clearPromotion
};

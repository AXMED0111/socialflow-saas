const { db } = require('../config/database');

// Base prices per cycle. Change these via env vars per deployment/currency —
// no code change needed to reprice.
const BASE_PRICES = {
    monthly: parseFloat(process.env.PRICE_MONTHLY || '10'),
    yearly: parseFloat(process.env.PRICE_YEARLY || '100')
};

const PERIOD_DAYS = {
    monthly: parseInt(process.env.MONTHLY_PERIOD_DAYS || '30', 10),
    yearly: parseInt(process.env.YEARLY_PERIOD_DAYS || '365', 10)
};

const CURRENCY = process.env.CURRENCY || 'USD';

function isValidCycle(cycle) {
    return cycle === 'monthly' || cycle === 'yearly';
}

// Only one promotion is meant to be "live" at a time (see schema.sql), but
// this also respects starts_at/ends_at so an old promo that was never
// explicitly cleared doesn't linger past its own end date.
function getActivePromo(cycle) {
    const now = new Date().toISOString();
    return db.prepare(`
        SELECT * FROM promotions
        WHERE active = 1
          AND (billing_cycle = ? OR billing_cycle = 'both')
          AND (starts_at IS NULL OR starts_at <= ?)
          AND (ends_at IS NULL OR ends_at >= ?)
        ORDER BY created_at DESC LIMIT 1
    `).get(cycle, now, now) || null;
}

function getPricing(cycle) {
    if (!isValidCycle(cycle)) {
        throw new Error(`Unknown billing cycle: ${cycle}`);
    }
    const basePrice = BASE_PRICES[cycle];
    const promo = getActivePromo(cycle);
    const discountPercent = promo ? promo.discount_percent : 0;
    const finalPrice = Math.round(basePrice * (1 - discountPercent / 100) * 100) / 100;

    return {
        cycle,
        currency: CURRENCY,
        basePrice,
        discountPercent,
        finalPrice,
        promoName: promo ? promo.name : null,
        periodDays: PERIOD_DAYS[cycle]
    };
}

function getAllPricing() {
    return { monthly: getPricing('monthly'), yearly: getPricing('yearly') };
}

module.exports = { getPricing, getAllPricing, getActivePromo, isValidCycle, PERIOD_DAYS, BASE_PRICES, CURRENCY };

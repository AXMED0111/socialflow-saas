const express = require('express');
const router = express.Router();
const { requireAuth } = require('../middleware/auth');
const { requireAdmin } = require('../middleware/billing');
const {
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
} = require('../controllers/billingController');

// Customer-facing (needs a logged-in user, any role)
router.get('/status', requireAuth, getStatus);
router.get('/pricing', requireAuth, getPricing);
router.get('/promotions/active', requireAuth, getActivePromotion);
router.post('/claim', requireAuth, submitClaim);

// Admin-facing (shared-secret key, used by the Telegram bot's admin commands)
router.get('/claims', requireAdmin, listClaims);
router.post('/claims/:id/approve', requireAdmin, approveClaim);
router.post('/claims/:id/reject', requireAdmin, rejectClaim);
router.get('/promotions', requireAdmin, listPromotions);
router.post('/promotions', requireAdmin, setPromotion);
router.post('/promotions/clear', requireAdmin, clearPromotion);

module.exports = router;

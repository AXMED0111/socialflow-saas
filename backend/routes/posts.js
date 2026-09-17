const express = require('express');
const router = express.Router();
const { requireAuth, requireRole } = require('../middleware/auth');
const { requireActiveSubscription } = require('../middleware/billing');
const { listPosts, createPost, cancelPost } = require('../controllers/postController');

router.use(requireAuth);
router.get('/', listPosts);
// Scheduling a post is the paid action: browsing/listing stays open, but
// actually creating one requires an active subscription (trial or paid).
router.post('/', requireRole('editor'), requireActiveSubscription, createPost);
router.delete('/:id', requireRole('editor'), cancelPost);

module.exports = router;

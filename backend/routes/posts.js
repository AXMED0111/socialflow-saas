const express = require('express');
const router = express.Router();
const { requireAuth, requireRole } = require('../middleware/auth');
const { listPosts, createPost, cancelPost } = require('../controllers/postController');

router.use(requireAuth);
router.get('/', listPosts);
router.post('/', requireRole('editor'), createPost);
router.delete('/:id', requireRole('editor'), cancelPost);

module.exports = router;

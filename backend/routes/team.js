const express = require('express');
const router = express.Router();
const { requireAuth, requireRole } = require('../middleware/auth');
const {
    listMembers, inviteMember, changeRole, removeMember, getBotShareLink
} = require('../controllers/teamController');

router.use(requireAuth);

router.get('/', listMembers);
router.get('/bot-link', getBotShareLink);
router.post('/invite', requireRole('editor'), inviteMember); // editor+ can invite (role check refined inside)
router.patch('/:userId/role', requireRole('owner'), changeRole);
router.delete('/:userId', requireRole('manager'), removeMember);

module.exports = router;

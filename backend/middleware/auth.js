const jwt = require('jsonwebtoken');

function requireAuth(req, res, next) {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'No token provided' });
    }

    const token = authHeader.split(' ')[1];
    try {
        const decoded = jwt.verify(token, process.env.JWT_SECRET);
        req.user = decoded; // { id, email, workspaceId, role }
        next();
    } catch (err) {
        return res.status(401).json({ error: 'Invalid or expired token' });
    }
}

// Role hierarchy: owner > manager > editor > viewer
const ROLE_LEVELS = { owner: 4, manager: 3, editor: 2, viewer: 1 };

function requireRole(minRole) {
    return (req, res, next) => {
        const userLevel = ROLE_LEVELS[req.user?.role] || 0;
        const requiredLevel = ROLE_LEVELS[minRole] || 999;
        if (userLevel < requiredLevel) {
            return res.status(403).json({ error: `Requires ${minRole} role or higher` });
        }
        next();
    };
}

module.exports = { requireAuth, requireRole };

const express = require('express');
const multer = require('multer');
const path = require('path');
const router = express.Router();
const { requireAuth } = require('../middleware/auth');
const { listMedia, uploadMedia, UPLOAD_DIR } = require('../controllers/mediaController');

const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, UPLOAD_DIR),
    filename: (req, file, cb) => {
        const unique = `${Date.now()}-${Math.round(Math.random() * 1e9)}`;
        cb(null, `${unique}${path.extname(file.originalname)}`);
    }
});

const upload = multer({
    storage,
    limits: { fileSize: 500 * 1024 * 1024 } // 500MB cap
});

router.use(requireAuth);
router.get('/', listMedia);
router.post('/upload', upload.single('file'), uploadMedia);

module.exports = router;

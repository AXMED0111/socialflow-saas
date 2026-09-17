require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');

const { initSchema } = require('./config/database');
const { startScheduler } = require('./services/scheduleService');

const authRoutes = require('./routes/auth');
const teamRoutes = require('./routes/team');
const mediaRoutes = require('./routes/media');
const postsRoutes = require('./routes/posts');
const socialAccountsRoutes = require('./routes/socialAccounts');

initSchema();

const app = express();
app.use(cors());
app.use(express.json());
app.use('/uploads', express.static(path.resolve(process.env.UPLOAD_DIR || './uploads')));

app.use('/api/auth', authRoutes);
app.use('/api/team', teamRoutes);
app.use('/api/media', mediaRoutes);
app.use('/api/posts', postsRoutes);
app.use('/api/accounts', socialAccountsRoutes);

app.get('/health', (req, res) => res.json({ status: 'ok', company: process.env.COMPANY_NAME }));

app.use((err, req, res, next) => {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`✓ SocialFlow backend running on port ${PORT} for ${process.env.COMPANY_NAME || 'default'}`);
    startScheduler();
});

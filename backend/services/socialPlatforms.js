// Each platform function has the SAME signature so the scheduler can call them generically:
//   async function postToX({ account, caption, mediaFiles }) -> { success, platformPostId, error }
//
// Right now these are STUBBED - they log what WOULD be sent and return success.
// To go live: replace the axios call inside each function with the real Graph/API call,
// using account.access_token (already stored per workspace in social_accounts table).

// const axios = require('axios'); // uncomment when wiring real platform API calls

async function postToFacebook({ account, caption, mediaFiles }) {
    try {
        // Real call would be:
        // POST https://graph.facebook.com/{page-id}/photos or /feed
        // with access_token = account.access_token
        console.log(`[STUB] Posting to Facebook page "${account.username}": "${caption}" (${mediaFiles.length} files)`);
        return { success: true, platformPostId: `fb_stub_${Date.now()}` };
    } catch (err) {
        return { success: false, error: err.message };
    }
}

async function postToInstagram({ account, caption, mediaFiles }) {
    try {
        // Real call: Instagram Graph API - 2 step process
        // 1. POST /{ig-user-id}/media (create container)
        // 2. POST /{ig-user-id}/media_publish (publish container)
        console.log(`[STUB] Posting to Instagram "${account.username}": "${caption}" (${mediaFiles.length} files)`);
        return { success: true, platformPostId: `ig_stub_${Date.now()}` };
    } catch (err) {
        return { success: false, error: err.message };
    }
}

async function postToTikTok({ account, caption, mediaFiles }) {
    try {
        // Real call: TikTok Content Posting API - /v2/post/publish/video/init/
        console.log(`[STUB] Posting to TikTok "${account.username}": "${caption}" (${mediaFiles.length} files)`);
        return { success: true, platformPostId: `tt_stub_${Date.now()}` };
    } catch (err) {
        return { success: false, error: err.message };
    }
}

async function postToTwitter({ account, caption, mediaFiles }) {
    try {
        // Real call: POST https://api.twitter.com/2/tweets (with media_ids from upload endpoint)
        console.log(`[STUB] Posting to Twitter "${account.username}": "${caption}" (${mediaFiles.length} files)`);
        return { success: true, platformPostId: `tw_stub_${Date.now()}` };
    } catch (err) {
        return { success: false, error: err.message };
    }
}

const PLATFORM_HANDLERS = {
    facebook: postToFacebook,
    instagram: postToInstagram,
    tiktok: postToTikTok,
    twitter: postToTwitter
};

module.exports = { PLATFORM_HANDLERS };

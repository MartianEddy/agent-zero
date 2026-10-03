import assert from 'node:assert/strict';
import { once } from 'node:events';
import test from 'node:test';
import { createApp } from './server.js';
import { assessLinks, extractUrls } from './link-check.js';
import { downloadTwilioMedia, supportedMediaType } from './media.js';
import { reviewWithGemini } from './gemini-review.js';

const TEST_ACCOUNT_SID = `AC${'1234567890abcdef'.repeat(2)}`;
const TEST_MESSAGE_SID = `MM${'1234567890abcdef'.repeat(2)}`;
const TEST_MEDIA_SID = `ME${'1234567890abcdef'.repeat(2)}`;

async function withServer(app, run) {
  const server = app.listen(0);
  await once(server, 'listening');
  try {
    const { port } = server.address();
    await run(`http://127.0.0.1:${port}`);
  } finally {
    server.close();
    await once(server, 'close');
  }
}

test('extracts URLs and flags common link-format risks without fetching them', () => {
  const urls = extractUrls('Check this: http://bit.ly/news?ref=chat).');
  assert.deepEqual(urls, ['http://bit.ly/news?ref=chat']);
  assert.deepEqual(assessLinks(urls), [{
    host: 'bit.ly',
    flags: ['not using HTTPS', 'uses a URL shortener, so the destination is obscured']
  }]);
});

test('accepts only supported image, video, and audio attachment types', () => {
  assert.equal(supportedMediaType('image/jpeg'), true);
  assert.equal(supportedMediaType('video/mp4'), true);
  assert.equal(supportedMediaType('audio/ogg'), true);
  assert.equal(supportedMediaType('application/pdf'), false);
});

test('media downloader rejects untrusted hosts before making a request', async () => {
  let requested = false;
  await assert.rejects(
    downloadTwilioMedia({
      url: 'https://example.com/media',
      contentType: 'image/jpeg',
      env: { TWILIO_ACCOUNT_SID: TEST_ACCOUNT_SID, TWILIO_AUTH_TOKEN: 'token' },
      fetchImpl: async () => {
        requested = true;
        throw new Error('must not fetch');
      }
    }),
    /not an approved Twilio media resource/
  );
  assert.equal(requested, false);
});

test('media downloader follows approved redirects without forwarding Twilio credentials', async () => {
  const requests = [];
  const result = await downloadTwilioMedia({
    url: `https://api.twilio.com/2010-04-01/Accounts/${TEST_ACCOUNT_SID}/Messages/${TEST_MESSAGE_SID}/Media/${TEST_MEDIA_SID}.json`,
    contentType: 'image/jpeg',
    env: { TWILIO_ACCOUNT_SID: TEST_ACCOUNT_SID, TWILIO_AUTH_TOKEN: 'test-token' },
    fetchImpl: async (url, options) => {
      requests.push({ url: String(url), options });
      if (requests.length === 1) {
        return new Response(null, {
          status: 302,
          headers: { Location: 'https://media.twiliocdn.com/signed-media' }
        });
      }
      return new Response(Buffer.from('jpeg'), {
        status: 200,
        headers: { 'Content-Type': 'image/jpeg' }
      });
    }
  });

  assert.equal(requests.length, 2);
  assert.match(requests[0].options.headers.Authorization, /^Basic /);
  assert.equal(requests[1].options.headers.Authorization, undefined);
  assert.deepEqual(result, {
    mimeType: 'image/jpeg',
    data: Buffer.from('jpeg').toString('base64'),
    sizeBytes: 4
  });
});

test('media downloader enforces the caller-provided byte limit', async () => {
  await assert.rejects(
    downloadTwilioMedia({
      url: `https://api.twilio.com/2010-04-01/Accounts/${TEST_ACCOUNT_SID}/Messages/${TEST_MESSAGE_SID}/Media/${TEST_MEDIA_SID}`,
      contentType: 'image/jpeg',
      env: { TWILIO_ACCOUNT_SID: TEST_ACCOUNT_SID, TWILIO_AUTH_TOKEN: 'test-token' },
      maxBytes: 2,
      fetchImpl: async () => new Response(Buffer.from('jpeg'), {
        status: 200,
        headers: { 'Content-Type': 'image/jpeg', 'Content-Length': '4' }
      })
    }),
    /media processing limit/
  );
});

test('Gemini reviewer sends multimodal content and extracts grounded sources', async () => {
  let requestBody;
  const result = await reviewWithGemini({
    text: 'Is this real?',
    attachments: [{ mimeType: 'image/jpeg', data: 'dGVzdA==' }],
    apiKey: 'test-key',
    fetchImpl: async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return new Response(JSON.stringify({
        candidates: [{
          content: { parts: [{ text: 'Assessment: Unverified.' }] },
          groundingMetadata: {
            groundingChunks: [{ web: { uri: 'https://example.org/source', title: 'Example source' } }]
          }
        }]
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
  });

  assert.equal(requestBody.tools[0].google_search !== undefined, true);
  assert.deepEqual(requestBody.contents[0].parts[1].inlineData, {
    mimeType: 'image/jpeg',
    data: 'dGVzdA=='
  });
  assert.deepEqual(result.sources, [{ uri: 'https://example.org/source', title: 'Example source' }]);
});

test('webhook returns a grounded-review report and sends supported attachments to the reviewer', async () => {
  let receivedReview;
  const app = createApp({
    env: { GEMINI_API_KEY: 'test-key' },
    matchClaim: async () => null,
    downloadMedia: async ({ url, contentType }) => ({
      mimeType: contentType,
      data: url.endsWith('/media') ? 'dGVzdA==' : ''
    }),
    reviewContent: async (input) => {
      receivedReview = input;
      return {
        summary: 'Assessment: Unverified. More evidence is needed.',
        sources: [{ title: 'Example source', uri: 'https://example.org/report' }]
      };
    }
  });

  await withServer(app, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/webhook/whatsapp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        Body: 'Is this genuine? https://example.org/news',
        NumMedia: '1',
        MediaUrl0: 'https://api.twilio.com/media',
        MediaContentType0: 'image/jpeg'
      })
    });

    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /text\/xml/);
    const xml = await response.text();
    assert.match(xml, /Assessment: Unverified/);
    assert.match(xml, /example\.org\/report/);
    assert.match(xml, /included in the AI-assisted review/);
    assert.equal(receivedReview.attachments.length, 1);
    assert.equal(receivedReview.attachments[0].mimeType, 'image/jpeg');
    assert.equal(receivedReview.text, 'Is this genuine? https://example.org/news');
  });
});

test('webhook accurately reports unavailable AI and Supabase services', async () => {
  const app = createApp({
    env: {},
    matchClaim: async () => {
      throw new Error('test database error');
    }
  });

  await withServer(app, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/webhook/whatsapp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ Body: 'Please verify this claim.' })
    });

    assert.equal(response.status, 200);
    const xml = await response.text();
    assert.match(xml, /GEMINI_API_KEY/);
    assert.match(xml, /Known-claim check:.*Unavailable/);
    assert.match(xml, /AI\/media indicators are not forensic proof/);
  });
});

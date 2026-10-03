const MAX_MEDIA_BYTES = 8 * 1024 * 1024;
export const DEFAULT_MAX_MEDIA_BYTES = MAX_MEDIA_BYTES;
const MEDIA_HOSTS = new Set(['api.twilio.com', 'media.twiliocdn.com']);
const SUPPORTED_MEDIA_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
  'video/mp4',
  'video/webm',
  'video/quicktime',
  'audio/mpeg',
  'audio/mp4',
  'audio/wav',
  'audio/x-wav',
  'audio/ogg',
  'audio/webm',
  'audio/aac',
  'audio/flac'
]);

function isApprovedMediaUrl(url, accountSid) {
  if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443') || url.hash) return false;
  if (url.hostname === 'media.twiliocdn.com') return true;
  if (url.hostname !== 'api.twilio.com') return false;

  const escapedAccountSid = accountSid.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const mediaPath = new RegExp(
    `^/2010-04-01/Accounts/${escapedAccountSid}/Messages/(?:SM|MM)[0-9a-f]{32}/Media/ME[0-9a-f]{32}(?:\\.json)?$`,
    'i'
  );
  return mediaPath.test(url.pathname);
}

export function supportedMediaType(contentType) {
  return typeof contentType === 'string' && SUPPORTED_MEDIA_TYPES.has(contentType.split(';', 1)[0].trim().toLowerCase());
}

export async function downloadTwilioMedia({ url, contentType, env = process.env, fetchImpl = fetch, maxBytes = MAX_MEDIA_BYTES }) {
  const parsedUrl = new URL(url);
  const accountSid = env.TWILIO_ACCOUNT_SID;
  const authToken = env.TWILIO_AUTH_TOKEN;
  if (!accountSid || !authToken) {
    throw new Error('configure TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to retrieve attachments');
  }
  if (!/^AC[0-9a-f]{32}$/i.test(accountSid)) {
    throw new Error('TWILIO_ACCOUNT_SID is not a valid Twilio account SID');
  }
  if (!isApprovedMediaUrl(parsedUrl, accountSid)) {
    throw new Error('media URL is not an approved Twilio media resource');
  }

  const normalizedType = contentType.split(';', 1)[0].trim().toLowerCase();
  if (!supportedMediaType(normalizedType)) {
    throw new Error('unsupported media type');
  }

  let mediaUrl = parsedUrl;
  let response;
  for (let redirects = 0; redirects <= 3; redirects += 1) {
    if (!isApprovedMediaUrl(mediaUrl, accountSid) || !MEDIA_HOSTS.has(mediaUrl.hostname)) {
      throw new Error('Twilio media redirected to an unapproved host or resource');
    }

    const headers = mediaUrl.hostname === 'api.twilio.com'
      ? { Authorization: `Basic ${Buffer.from(`${accountSid}:${authToken}`).toString('base64')}` }
      : {};
    response = await fetchImpl(mediaUrl, {
      headers,
      redirect: 'manual',
      signal: AbortSignal.timeout(20_000)
    });
    if (![301, 302, 303, 307, 308].includes(response.status)) break;
    if (redirects === 3) {
      throw new Error('Twilio media redirect limit exceeded');
    }
    const location = response.headers.get('location');
    if (!location) {
      throw new Error('Twilio media redirect did not include a destination');
    }
    await response.body?.cancel();
    mediaUrl = new URL(location, mediaUrl);
  }

  if (!response.ok) {
    throw new Error(`Twilio media request failed (HTTP ${response.status})`);
  }

  const responseType = response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase();
  if (responseType && responseType !== 'application/octet-stream' && responseType !== normalizedType) {
    throw new Error('downloaded media type does not match the Twilio attachment type');
  }

  const declaredLength = Number(response.headers.get('content-length'));
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
    throw new Error('attachment exceeds the media processing limit');
  }
  if (!response.body) {
    throw new Error('Twilio returned an empty media response');
  }

  const chunks = [];
  let totalBytes = 0;
  for await (const chunk of response.body) {
    totalBytes += chunk.length;
    if (totalBytes > maxBytes) {
      throw new Error('attachment exceeds the media processing limit');
    }
    chunks.push(Buffer.from(chunk));
  }
  if (totalBytes === 0) {
    throw new Error('Twilio returned an empty media response');
  }

  return {
    mimeType: normalizedType,
    data: Buffer.concat(chunks).toString('base64'),
    sizeBytes: totalBytes
  };
}

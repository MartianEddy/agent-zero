import express from 'express';
import twilio from 'twilio';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { matchIncomingClaim } from './agent0-engine.js';
import { DEFAULT_MAX_MEDIA_BYTES, downloadTwilioMedia, supportedMediaType } from './media.js';
import { reviewWithGemini } from './gemini-review.js';
import { assessLinks, extractUrls } from './link-check.js';
import 'dotenv/config';

const { MessagingResponse } = twilio.twiml;
const MAX_MEDIA_COUNT = 3;
const MAX_MESSAGE_LENGTH = 6000;
const MAX_TOTAL_MEDIA_BYTES = 12 * 1024 * 1024;

function buildReport({ env, text, textTruncated, mediaCount, reviewedMediaCount, skippedMediaCount, review, reviewError, match, matchError, links, mediaErrors }) {
  const sections = ['*Agent Zero | Verification*'];

  if (review?.summary) {
    sections.push(`*AI-assisted review:*\n${review.summary}`);
  } else if (reviewError) {
    sections.push(`*AI-assisted review:* Unavailable (${reviewError})`);
  } else if (text) {
    sections.push('*AI-assisted review:* Not configured. Add GEMINI_API_KEY to enable conversational and multimodal review.');
  }

  if (match) {
    const similarity = Number(match.similarity);
    const confidence = Number.isFinite(similarity) ? ` (${Math.round(similarity * 100)}% semantic similarity)` : '';
    sections.push(`*Known-claim match:* ${match.verdict}${confidence}\n“${match.claim}”\nReference: ${match.source_url}`);
  } else if (text) {
    sections.push(matchError
      ? `*Known-claim check:* Unavailable (${matchError})`
      : '*Known-claim check:* No matching record found. This does not establish that the claim is false.');
  }

  if (links.length > 0) {
    const linkLines = links.map(({ host, flags }) => flags.length
      ? `• ${host}: caution — ${flags.join('; ')}`
      : `• ${host}: no obvious URL-format warning`);
    sections.push(`*Link checks (not a reputation verdict):*\n${linkLines.join('\n')}`);
  }

  if (mediaCount > 0) {
    const mediaStatus = [];
    if (review?.summary && reviewedMediaCount > 0) {
      mediaStatus.push(`${reviewedMediaCount} attachment(s) included in the AI-assisted review.`);
    }
    if (mediaErrors.length > 0) {
      mediaStatus.push(...mediaErrors);
    }
    if (reviewError) {
      mediaStatus.push('AI review failed; media authenticity was not assessed.');
    }
    if (mediaStatus.length === 0) {
      mediaStatus.push(env.GEMINI_API_KEY
        ? 'No attachment was available for AI review.'
        : 'Not analyzed. Configure GEMINI_API_KEY to enable image, video, and audio review.');
    }
    sections.push(`*Media review:* ${mediaStatus.join(' | ')}`);
  }

  if (skippedMediaCount > 0) {
    sections.push(`*Attachments:* ${skippedMediaCount} additional item(s) were not processed (limit: ${MAX_MEDIA_COUNT}).`);
  }
  if (textTruncated) {
    sections.push(`*Message:* Only the first ${MAX_MESSAGE_LENGTH} characters were analyzed.`);
  }

  if (review?.sources?.length) {
    sections.push(`*Web sources:*\n${review.sources.slice(0, 3).map(({ title, uri }) => `• ${title}: ${uri}`).join('\n')}`);
  }
  if (match?.source_url && !review?.sources?.some(({ uri }) => uri === match.source_url)) {
    sections.push(`*Fact-check reference:* ${match.source_url}`);
  }

  if (text || mediaCount > 0) {
    sections.push('_Automated analysis can be wrong. AI/media indicators are not forensic proof; verify important claims with reliable sources._');
  }

  return sections.join('\n\n').slice(0, 1500);
}

export function createApp({
  env = process.env,
  matchClaim = matchIncomingClaim,
  reviewContent = reviewWithGemini,
  downloadMedia = downloadTwilioMedia
} = {}) {
  const app = express();
  app.use(express.urlencoded({ extended: false, limit: '64kb' }));
  app.use(express.json({ limit: '64kb' }));

  app.get('/health', (_req, res) => {
    res.json({
      status: 'ok',
      capabilities: {
        claimMatching: Boolean(
          (env.SUPABASE_URL || env.NEXT_PUBLIC_SUPABASE_URL) &&
          (env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_SECRET_KEY || env.SUPABASE_ANON_KEY || env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY)
        ),
        aiReview: Boolean(env.GEMINI_API_KEY)
      }
    });
  });

  app.post('/webhook/whatsapp', async (req, res) => {
    if (env.TWILIO_AUTH_TOKEN) {
      const signature = req.get('X-Twilio-Signature') || '';
      const webhookUrl = env.PUBLIC_WEBHOOK_URL || `${req.protocol}://${req.get('host')}${req.originalUrl}`;
      if (!twilio.validateRequest(env.TWILIO_AUTH_TOKEN, signature, webhookUrl, req.body)) {
        return res.status(403).send('Invalid Twilio signature');
      }
    }

    const body = typeof req.body.Body === 'string' ? req.body.Body.trim() : '';
    const text = body.slice(0, MAX_MESSAGE_LENGTH);
    const textTruncated = body.length > MAX_MESSAGE_LENGTH;
    const urls = extractUrls(text);
    const links = assessLinks(urls);
    const parsedMediaCount = Number.parseInt(req.body.NumMedia, 10);
    const mediaCount = Number.isInteger(parsedMediaCount) && parsedMediaCount > 0
      ? parsedMediaCount
      : (req.body.MediaUrl0 ? 1 : 0);
    const attachments = [];
    const mediaErrors = [];
    let totalMediaBytes = 0;
    const skippedMediaCount = Math.max(0, mediaCount - MAX_MEDIA_COUNT);

    if (!text && mediaCount === 0) {
      const greeting = new MessagingResponse();
      greeting.message('👋 Hello! Send me a claim, link, image, video, or audio clip. I’ll check available sources and explain what I can—and cannot—verify.');
      return res.type('text/xml').send(greeting.toString());
    }

    if (mediaCount > 0 && env.GEMINI_API_KEY) {
      for (let index = 0; index < Math.min(mediaCount, MAX_MEDIA_COUNT); index += 1) {
        const mediaUrl = req.body[`MediaUrl${index}`];
        const contentType = req.body[`MediaContentType${index}`] || req.body[`ContentType${index}`] || req.body.ContentType0;

        if (!mediaUrl) {
          mediaErrors.push(`Attachment ${index + 1} has no media URL.`);
          continue;
        }
        if (!supportedMediaType(contentType)) {
          mediaErrors.push(`Attachment ${index + 1} has unsupported media type (${contentType || 'unknown'}).`);
          continue;
        }
        const remainingBytes = MAX_TOTAL_MEDIA_BYTES - totalMediaBytes;
        if (remainingBytes <= 0) {
          mediaErrors.push(`Attachment ${index + 1} exceeds the 12 MB combined media limit.`);
          continue;
        }

        try {
          const attachment = await downloadMedia({
            url: mediaUrl,
            contentType,
            env,
            maxBytes: Math.min(DEFAULT_MAX_MEDIA_BYTES, remainingBytes)
          });
          const sizeBytes = attachment.sizeBytes ?? Buffer.from(attachment.data, 'base64').length;
          if (sizeBytes > remainingBytes) {
            mediaErrors.push(`Attachment ${index + 1} exceeds the 12 MB combined media limit.`);
            continue;
          }
          totalMediaBytes += sizeBytes;
          attachments.push(attachment);
        } catch (error) {
          console.error(`Media download failed for attachment ${index + 1}:`, error.message);
          mediaErrors.push(`Attachment ${index + 1} could not be downloaded (${error.message}).`);
        }
      }
    }

    const claimText = text.replace(/https?:\/\/[^\s<>"']+/gi, '').trim();
    const [reviewResult, matchResult] = await Promise.allSettled([
      env.GEMINI_API_KEY && (text || attachments.length > 0)
        ? reviewContent({ text, attachments, apiKey: env.GEMINI_API_KEY, model: env.GEMINI_MODEL })
        : Promise.resolve(null),
      claimText ? matchClaim(claimText) : Promise.resolve(null)
    ]);

    let review = null;
    let reviewError = null;
    if (reviewResult.status === 'fulfilled') {
      review = reviewResult.value;
    } else {
      reviewError = 'the review service returned an error';
      console.error('AI review failed:', reviewResult.reason?.message || reviewResult.reason);
    }

    let match = null;
    let matchError = null;
    if (matchResult.status === 'fulfilled') {
      match = matchResult.value;
    } else {
      matchError = 'the fact-check database is not configured or could not be reached';
      console.error('Claim matching failed:', matchResult.reason?.message || matchResult.reason);
    }

    const report = buildReport({
      env,
      text,
      textTruncated,
      mediaCount,
      reviewedMediaCount: attachments.length,
      skippedMediaCount,
      review,
      reviewError,
      match,
      matchError,
      links,
      mediaErrors
    });
    const response = new MessagingResponse();
    response.message(report);
    return res.type('text/xml').send(response.toString());
  });

  return app;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT) || 3000;
  createApp().listen(port, () => {
    console.log(`Agent Zero listening on port ${port}`);
    console.log(`WhatsApp webhook: http://localhost:${port}/webhook/whatsapp`);
  });
}

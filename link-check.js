import { isIP } from 'node:net';

const URL_PATTERN = /https?:\/\/[^\s<>"']+/gi;
const TRAILING_PUNCTUATION = /[),.!?;:]+$/;
const SHORTENER_HOSTS = new Set([
  'bit.ly',
  'buff.ly',
  'goo.gl',
  'is.gd',
  'ow.ly',
  't.co',
  'tiny.cc',
  'tinyurl.com'
]);

export function extractUrls(text) {
  return [...text.matchAll(URL_PATTERN)]
    .map(([url]) => url.replace(TRAILING_PUNCTUATION, ''))
    .filter(Boolean)
    .slice(0, 5);
}

export function assessLinks(urls) {
  return urls.map((value) => {
    const flags = [];
    let host = 'invalid URL';

    try {
      const url = new URL(value);
      host = url.hostname.toLowerCase();
      if (url.protocol !== 'https:') flags.push('not using HTTPS');
      if (url.username || url.password) flags.push('contains embedded credentials');
      if (isIP(host.replace(/^\[|\]$/g, ''))) flags.push('uses a direct IP address');
      if (host.split('.').some((label) => label.startsWith('xn--'))) flags.push('contains an internationalized domain label');
      if (SHORTENER_HOSTS.has(host)) flags.push('uses a URL shortener, so the destination is obscured');
      if (url.port && !['80', '443'].includes(url.port)) flags.push('uses a non-standard port');
      if (host.split('.').length > 5) flags.push('uses an unusually deep subdomain');
    } catch {
      flags.push('could not be parsed');
    }

    return { host, flags };
  });
}

/**
 * Extract embeddable video iframe URL from known video platforms.
 *
 * Supports: YouTube, MGTOW.tv, Bitchute, Odysee
 * Returns null if the URL is not a recognized video platform.
 *
 * NOTE: Rumble uses internal embed IDs that differ from the view URL slug,
 *       and their pages are behind Cloudflare challenge — embed not feasible.
 *
 * This runs client-side only — zero server load.
 * The browser loads the iframe directly from the platform CDN.
 */
export default function getVideoEmbedUrl(
  url: string | undefined,
): string | null {
  if (!url) return null;

  // YouTube: youtube.com/watch?v=ID, youtu.be/ID, youtube.com/shorts/ID
  const ytMatch = url.match(
    /(?:youtube\.com\/(?:watch\?.*v=|shorts\/)|youtu\.be\/)([\w-]{11})/,
  );
  if (ytMatch) {
    return `https://www.youtube-nocookie.com/embed/${ytMatch[1]}?autoplay=0&rel=0`;
  }

  // MGTOW.tv: mgtow.tv/watch/slug_ID.html → embed uses same path
  const mgtowtMatch = url.match(
    /mgtow\.tv\/watch\/([\w-]+_[\w]+)\.html/,
  );
  if (mgtowtMatch) {
    return `https://www.mgtow.tv/embed/${mgtowtMatch[1]}`;
  }

  // Bitchute: bitchute.com/video/ID/
  const bitchuteMatch = url.match(/bitchute\.com\/video\/([\w]+)/);
  if (bitchuteMatch) {
    return `https://www.bitchute.com/embed/${bitchuteMatch[1]}/`;
  }

  // Odysee: odysee.com/@channel/video
  const odyseeMatch = url.match(/odysee\.com\/(@[^/]+\/[^/?]+)/);
  if (odyseeMatch) {
    return `https://odysee.com/$/embed/${odyseeMatch[1]}`;
  }

  // 9GAG animated/video: direct mp4/webm URLs from 9cache CDN
  if (/9cache\.com\/.*\.(mp4|webm)/i.test(url)) {
    return url; // direct video — handled by <video> tag, not iframe
  }

  return null;
}

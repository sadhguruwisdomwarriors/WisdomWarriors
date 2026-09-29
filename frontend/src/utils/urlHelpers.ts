/**
 * Helper utilities for formatting and resolving social media channel URLs
 */

export function getInstagramUrl(username: string): string {
  if (!username) return "https://www.instagram.com/";
  const clean = username.trim().replace(/^@/, "");
  return `https://www.instagram.com/${clean}/`;
}

export function getYoutubeUrl(channelIdOrHandle: string, customUrl?: string): string {
  if (customUrl && customUrl.trim()) {
    const cleanCustom = customUrl.trim();
    if (cleanCustom.startsWith("http://") || cleanCustom.startsWith("https://")) {
      return cleanCustom;
    }
    const handle = cleanCustom.startsWith("@") ? cleanCustom : `@${cleanCustom}`;
    return `https://www.youtube.com/${handle}`;
  }

  if (!channelIdOrHandle) return "https://www.youtube.com/";
  const clean = channelIdOrHandle.trim();

  if (clean.startsWith("http://") || clean.startsWith("https://")) {
    return clean;
  }
  if (clean.startsWith("UC")) {
    return `https://www.youtube.com/channel/${clean}`;
  }
  const handle = clean.startsWith("@") ? clean : `@${clean}`;
  return `https://www.youtube.com/${handle}`;
}

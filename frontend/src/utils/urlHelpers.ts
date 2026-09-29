export const getInstagramUrl = (username?: string | null): string => {
  if (!username) return "https://www.instagram.com";
  const clean = username.replace(/^@/, "").trim();
  return `https://www.instagram.com/${clean}/`;
};

export const getYoutubeUrl = (channelIdOrHandle?: string | null, customUrl?: string | null): string => {
  if (customUrl && customUrl.trim()) {
    const clean = customUrl.trim().replace(/^@/, "");
    return `https://www.youtube.com/@${clean}`;
  }
  if (!channelIdOrHandle) return "https://www.youtube.com";
  const clean = channelIdOrHandle.trim();
  if (clean.startsWith("http://") || clean.startsWith("https://")) return clean;
  if (clean.startsWith("@")) return `https://www.youtube.com/${clean}`;
  if (clean.startsWith("UC")) return `https://www.youtube.com/channel/${clean}`;
  return `https://www.youtube.com/@${clean}`;
};

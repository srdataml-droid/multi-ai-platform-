// The widget allowlist stores exact origins, not complete page addresses.
export function websiteOrigins(input: string): string[] {
  const origins: string[] = [];
  for (const entry of input.split(/[,\n]/).map((item) => item.trim()).filter(Boolean)) {
    let url: URL;
    try { url = new URL(entry.includes("://") ? entry : `https://${entry}`); }
    catch { throw new Error("Enter a valid website address, such as https://example.com."); }
    if (!/^https?:$/.test(url.protocol) || url.username || url.password ||
        !/^https?:\/\/[a-z0-9.-]+(:\d{1,5})?$/.test(url.origin)) {
      throw new Error("Use an http or https website address without a username or password.");
    }
    if (!origins.includes(url.origin)) origins.push(url.origin);
  }
  return origins;
}

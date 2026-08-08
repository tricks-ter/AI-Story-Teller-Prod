// Rich client telemetry collector. Silent on failure — never blocks the user.
let cachedTelemetry = null;

function parseBrowser(ua) {
  const m = ua.match(/(Chrome|Safari|Firefox|Edge|Brave|Opera|SamsungBrowser|UCBrowser)\/([\d.]+)/);
  if (m) return { browser: m[1], browser_version: m[2] };
  if (/Brave/i.test(ua)) return { browser: "Brave", browser_version: "unknown" };
  return { browser: "Unknown", browser_version: "0" };
}

function parseOS(ua) {
  const m = ua.match(/(Android|iOS|iPhone|iPad|Windows|Mac OS X|Linux|CrOS) ?([\d._]*)/);
  if (m) return { os: m[1], os_version: (m[2] || "unknown").replace(/_/g, ".") };
  return { os: "Unknown", os_version: "unknown" };
}

async function fetchGeo() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    const res = await fetch("https://ipwho.is/?lang=en", { signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) return null;
    const d = await res.json();
    if (!d.success) return null;
    return {
      ip: d.ip || null,
      location: {
        isp: d.connection?.isp || null,
        city: d.city || null,
        region: d.region || null,
        country: d.country_code || null,
        latitude: d.latitude != null ? String(d.latitude) : null,
        longitude: d.longitude != null ? String(d.longitude) : null,
      },
    };
  } catch { return null; }
}

export async function getTelemetry(forceRefresh = false) {
  if (cachedTelemetry && !forceRefresh) return cachedTelemetry;
  try {
    const ua = navigator.userAgent || "";
    const uaData = navigator.userAgentData;
    const browser = parseBrowser(ua);
    const os = parseOS(ua);
    const isMobile = /Mobile|Android|iPhone|iPad/i.test(ua) || uaData?.mobile === true;

    let uaBrands = "", uaPlatform = "", uaPlatformVersion = "", uaModel = "";
    try {
      if (uaData) {
        uaBrands = (uaData.brands || []).map(b => `${b.brand} ${b.version}`).join(", ");
        uaPlatform = uaData.platform || "";
        const hi = await uaData.getHighEntropyValues(["platformVersion", "model", "architecture"]);
        uaPlatformVersion = hi.platformVersion || "";
        uaModel = hi.model || "";
      }
    } catch {}

    const geo = (await fetchGeo()) || { ip: null, location: null };

    cachedTelemetry = {
      ip: geo.ip,
      client: {
        cores: navigator.hardwareConcurrency || null,
        mobile: !!isMobile,
        screen: `${screen.width}x${screen.height}`,
        language: navigator.language || null,
        platform: navigator.platform || null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
        ua_model: uaModel,
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        memory_gb: navigator.deviceMemory || null,
        ua_brands: uaBrands,
        ua_platform: uaPlatform,
        touch_points: navigator.maxTouchPoints || 0,
        ua_platform_version: uaPlatformVersion,
      },
      device: {
        os: os.os,
        type: isMobile ? "mobile" : "desktop",
        device: os.os === "Android" ? "Android device" : (os.os === "iOS" || os.os === "iPhone" ? "iOS device" : "Unknown"),
        browser: browser.browser,
        os_version: os.os_version,
        browser_version: browser.browser_version,
      },
      location: geo.location || { isp: null, city: null, region: null, country: null, latitude: null, longitude: null },
      user_agent: ua,
    };
    return cachedTelemetry;
  } catch (err) {
    console.warn("[telemetry] collection failed, using empty:", err);
    cachedTelemetry = { ip: null, client: null, device: null, location: null, user_agent: null };
    return cachedTelemetry;
  }
}

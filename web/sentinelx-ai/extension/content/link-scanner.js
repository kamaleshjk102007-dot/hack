// sentinelx-ai/extension/content/link-scanner.js
/**
 * SYNTRAX AI — In-Page Link, Button & Form Destination Scanner
 * Manifest V3 Content Script
 *
 * Responsibilities:
 * 1. Hyperlink discovery across visible and hidden elements (menus, dropdowns, details).
 * 2. Form submission destination inspection (form action URLs and HTTP methods).
 * 3. Actionable button navigation inspection (data-href, data-url, explicit location attributes).
 * 4. Subframe / iframe destination inspection and cross-origin SOP boundary logging.
 * 5. Scheme isolation: javascript:, mailto:, tel:, file downloads, and unsupported protocols.
 * 6. High-efficiency deduplication and relative URL normalization against document.baseURI.
 * 7. Debounced MutationObserver for real-time dynamic DOM link additions.
 * 8. Pure-local privacy: zero form input scraping, zero credential reading.
 */

// Known binary/executable download file extensions
const DOWNLOAD_EXTENSIONS = new Set([
  'exe', 'scr', 'msi', 'bat', 'cmd', 'vbs', 'ps1', 'jar', 'apk',
  'iso', 'img', 'dmg', 'pkg', 'zip', 'rar', '7z', 'tar', 'gz'
]);

/**
 * Resolve and normalize raw link destination against base URI.
 *
 * @param {string} rawHref
 * @param {string} [baseUri]
 * @returns {Object} { normalizedUrl, protocol, hostname, isValid, isRelative }
 */
function resolveDestinationUrl(rawHref, baseUri) {
  if (typeof rawHref !== 'string') {
    return { raw: '', normalizedUrl: '', protocol: 'unknown:', hostname: '', isValid: false, isRelative: false };
  }

  const trimmed = rawHref.trim();
  if (!trimmed) {
    return { raw: '', normalizedUrl: '', protocol: 'empty:', hostname: '', isValid: false, isRelative: false };
  }

  // Handle JavaScript pseudo-protocol
  if (/^javascript:/i.test(trimmed)) {
    return {
      raw: trimmed,
      normalizedUrl: trimmed,
      protocol: 'javascript:',
      hostname: '',
      isValid: true,
      isRelative: false,
      isPseudoProtocol: true
    };
  }

  // Handle mailto: and tel:
  if (/^mailto:/i.test(trimmed)) {
    return {
      raw: trimmed,
      normalizedUrl: trimmed,
      protocol: 'mailto:',
      hostname: '',
      isValid: true,
      isRelative: false,
      isCommunicationProtocol: true
    };
  }

  if (/^tel:/i.test(trimmed)) {
    return {
      raw: trimmed,
      normalizedUrl: trimmed,
      protocol: 'tel:',
      hostname: '',
      isValid: true,
      isRelative: false,
      isCommunicationProtocol: true
    };
  }

  // Resolve standard or relative URL
  try {
    const base = baseUri || (typeof document !== 'undefined' ? (document.baseURI || window.location.href) : 'https://example.local');
    const parsed = new URL(trimmed, base);
    const isRelative = !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(trimmed);

    return {
      raw: trimmed,
      normalizedUrl: parsed.href,
      protocol: parsed.protocol.toLowerCase(),
      hostname: parsed.hostname.toLowerCase(),
      pathname: parsed.pathname,
      search: parsed.search,
      isValid: true,
      isRelative
    };
  } catch (_) {
    return {
      raw: trimmed,
      normalizedUrl: trimmed,
      protocol: 'malformed:',
      hostname: '',
      isValid: false,
      isRelative: false
    };
  }
}

/**
 * Categorize destination into security and protocol categories.
 *
 * @param {Object} resolved
 * @param {Object} [meta]
 * @returns {Object} { category, isInspectableWebUrl, skipReason }
 */
function categorizeDestination(resolved, meta = {}) {
  const protocol = resolved.protocol || '';

  if (protocol === 'javascript:') {
    return {
      category: 'SCHEME_JAVASCRIPT',
      isInspectableWebUrl: false,
      skipReason: 'Embedded JavaScript pseudo-protocol execution.'
    };
  }

  if (protocol === 'mailto:') {
    return {
      category: 'SCHEME_MAILTO',
      isInspectableWebUrl: false,
      skipReason: 'External email composition handler.'
    };
  }

  if (protocol === 'tel:') {
    return {
      category: 'SCHEME_TEL',
      isInspectableWebUrl: false,
      skipReason: 'Telephony dialer protocol handler.'
    };
  }

  if (protocol === 'chrome:' || protocol === 'chrome-extension:' || protocol === 'about:') {
    return {
      category: 'BROWSER_INTERNAL',
      isInspectableWebUrl: false,
      skipReason: 'Protected browser internal system interface.'
    };
  }

  if (protocol !== 'http:' && protocol !== 'https:') {
    return {
      category: 'UNSUPPORTED_SCHEME',
      isInspectableWebUrl: false,
      skipReason: `Non-web protocol (${protocol}) not eligible for HTTP threat inspection.`
    };
  }

  // Check for download file extensions or explicit download attribute
  if (meta.isDownload || meta.hasDownloadAttr) {
    return {
      category: 'DOWNLOAD_DESTINATION',
      isInspectableWebUrl: true,
      skipReason: null
    };
  }

  if (resolved.pathname) {
    const segments = resolved.pathname.split('/');
    const lastSeg = segments[segments.length - 1] || '';
    const dotIdx = lastSeg.lastIndexOf('.');
    if (dotIdx > 0) {
      const ext = lastSeg.slice(dotIdx + 1).toLowerCase();
      if (DOWNLOAD_EXTENSIONS.has(ext)) {
        return {
          category: 'DOWNLOAD_DESTINATION',
          isInspectableWebUrl: true,
          skipReason: null,
          downloadExtension: ext
        };
      }
    }
  }

  if (meta.isFormAction) {
    return {
      category: 'FORM_ACTION',
      isInspectableWebUrl: true,
      skipReason: null
    };
  }

  if (meta.isButtonAction) {
    return {
      category: 'BUTTON_ACTION',
      isInspectableWebUrl: true,
      skipReason: null
    };
  }

  if (meta.isIframeSrc) {
    return {
      category: 'IFRAME_EMBED',
      isInspectableWebUrl: true,
      skipReason: null
    };
  }

  return {
    category: 'HYPERLINK_DESTINATION',
    isInspectableWebUrl: true,
    skipReason: null
  };
}

/**
 * Check if a DOM node is located inside a hidden section (menu, dropdown, hidden container)
 *
 * @param {Element} element
 * @returns {boolean}
 */
function isElementInHiddenSection(element) {
  if (!element || typeof element.closest !== 'function') return false;

  // Check HTML5 hidden attribute or aria-hidden
  if (element.closest('[hidden]') || element.closest('[aria-hidden="true"]')) {
    return true;
  }

  // Check closed details element
  const details = element.closest('details');
  if (details && !details.open) {
    return true;
  }

  // Check inline styles or common dropdown/menu classes
  const hiddenAncestor = element.closest(
    '[style*="display: none"], [style*="display:none"], [style*="visibility: hidden"], [style*="visibility:hidden"], .hidden, .dropdown-menu:not(.show), .menu-closed, .collapse:not(.show)'
  );
  if (hiddenAncestor) {
    return true;
  }

  // Check computed visibility if element has offsetParent === null and is not fixed/body
  if (typeof window !== 'undefined' && element.offsetParent === null && element.tagName !== 'BODY') {
    return true;
  }

  return false;
}

// Maximum unique destinations scanned per page to prevent memory exhaustion on giant DOMs
const MAX_DISCOVERED_DESTINATIONS = 500;

/**
 * Scan DOM document for all actionable hyperlinks, form actions, buttons, and frames.
 *
 * @param {Document|Element} rootNode
 * @param {string} [baseUri]
 * @returns {Object} Structured destination collection & telemetry
 */
function extractPageDestinations(rootNode, baseUri) {
  const root = rootNode || (typeof document !== 'undefined' ? document : null);
  if (!root || typeof root.querySelectorAll !== 'function') {
    return {
      totalDiscovered: 0,
      uniqueDestinations: [],
      skippedSummary: {},
      boundedCapReached: false,
      scannedAt: new Date().toISOString()
    };
  }

  const effectiveBaseUri = baseUri || (root && root.baseURI ? root.baseURI : (typeof document !== 'undefined' ? (document.baseURI || window.location.href) : 'https://example.local'));
  const currentOrigin = (() => {
    try { return new URL(effectiveBaseUri).origin; } catch (_) { return ''; }
  })();

  const destinationMap = new Map();
  const skippedCategories = {};
  let boundedCapReached = false;

  function registerDestination(rawHref, type, meta = {}) {
    if (!rawHref) return;

    const resolved = resolveDestinationUrl(rawHref, effectiveBaseUri);
    const categorization = categorizeDestination(resolved, meta);

    if (!categorization.isInspectableWebUrl) {
      const cat = categorization.category;
      skippedCategories[cat] = (skippedCategories[cat] || 0) + 1;
    }

    const key = resolved.normalizedUrl || rawHref;
    if (destinationMap.has(key)) {
      const existing = destinationMap.get(key);
      existing.occurrences += 1;
      if (meta.sourceTag && !existing.sourceTags.includes(meta.sourceTag)) {
        existing.sourceTags.push(meta.sourceTag);
      }
      if (meta.isHidden && !existing.isHidden) {
        existing.isHidden = true;
      }
      return;
    }

    // Enforce bounded queue limit to protect browser performance
    if (destinationMap.size >= MAX_DISCOVERED_DESTINATIONS) {
      boundedCapReached = true;
      return;
    }

    const isCrossSite = Boolean(resolved.hostname && currentOrigin && !currentOrigin.includes(resolved.hostname));
    const isCrossOriginFrame = (type === 'iframe' || type === 'iframe_embed') && (isCrossSite || meta.frameAccessible === false);
    const effectiveSkipReason = isCrossOriginFrame
      ? 'Cross-origin subframe boundary protected by browser Same-Origin Policy (SOP).'
      : (categorization.skipReason || meta.skipReason || null);

    destinationMap.set(key, {
      url: resolved.normalizedUrl,
      normalizedUrl: resolved.normalizedUrl,
      destination: resolved.normalizedUrl,
      raw: rawHref,
      protocol: resolved.protocol,
      hostname: resolved.hostname,
      isRelative: resolved.isRelative,
      isCrossSite,
      isCrossOriginFrame,
      type,
      category: categorization.category,
      isInspectableWebUrl: categorization.isInspectableWebUrl,
      skipReason: effectiveSkipReason,
      sourceTags: meta.sourceTag ? [meta.sourceTag] : [type],
      label: meta.label || '',
      isHidden: Boolean(meta.isHidden),
      formMethod: meta.formMethod || null,
      occurrences: 1,
      frameAccessible: meta.frameAccessible !== undefined ? meta.frameAccessible : !isCrossOriginFrame,
      meta
    });
  }

  // 1. Scan Hyperlinks (<a href>, <area href>)
  const linkNodes = root.querySelectorAll('a[href], area[href]');
  linkNodes.forEach(link => {
    const rawHref = link.getAttribute('href');
    const label = (link.textContent || link.getAttribute('title') || link.getAttribute('aria-label') || '').trim().slice(0, 60);
    const isHidden = isElementInHiddenSection(link);
    const hasDownloadAttr = typeof link.hasAttribute === 'function'
      ? link.hasAttribute('download')
      : Boolean(link.getAttribute && link.getAttribute('download'));

    registerDestination(rawHref, 'hyperlink', {
      sourceTag: 'a',
      label,
      isHidden,
      hasDownloadAttr
    });
  });

  // 2. Scan Form Actions (<form action="..."> or <form>)
  const formNodes = root.querySelectorAll('form[action], form');
  formNodes.forEach(form => {
    const rawAction = form.getAttribute('action') || '';
    const method = (form.getAttribute('method') || 'GET').toUpperCase();
    const isHidden = isElementInHiddenSection(form);
    const name = form.getAttribute('name') || form.getAttribute('id') || 'form';

    // Form action can be empty or relative, default to current page if empty
    const targetUrl = rawAction || effectiveBaseUri;

    registerDestination(targetUrl, 'form_action', {
      sourceTag: 'form',
      label: `Form (${method}): ${name}`,
      isHidden,
      isFormAction: true,
      formMethod: method
    });
  });

  // 3. Scan Explicit Button Destinations
  const buttonNodes = root.querySelectorAll('button[data-href], button[data-url], [role="button"][data-href], [role="button"][data-url], button[onclick*="location"]');
  buttonNodes.forEach(btn => {
    const rawUrl = btn.getAttribute('data-href') || btn.getAttribute('data-url');
    let target = rawUrl;

    if (!target) {
      const onclickAttr = btn.getAttribute('onclick') || '';
      const match = onclickAttr.match(/location(?:\.href)?\s*=\s*['"]([^'"]+)['"]/);
      if (match && match[1]) {
        target = match[1];
      }
    }

    if (target) {
      const label = (btn.textContent || btn.getAttribute('aria-label') || 'Button').trim().slice(0, 60);
      const isHidden = isElementInHiddenSection(btn);
      registerDestination(target, 'button_action', {
        sourceTag: 'button',
        label,
        isHidden,
        isButtonAction: true
      });
    }
  });

  // 4. Scan Subframes (<iframe src="...">)
  const frameNodes = root.querySelectorAll('iframe[src]');
  frameNodes.forEach(frame => {
    const rawSrc = frame.getAttribute('src');
    if (!rawSrc) return;

    let isCrossDomain = false;
    let frameAccessible = true;
    try {
      if (frame.contentWindow && frame.contentWindow.location) {
        const frameOrigin = frame.contentWindow.location.origin;
        isCrossDomain = Boolean(currentOrigin && frameOrigin && frameOrigin !== currentOrigin);
      }
    } catch (_) {
      isCrossDomain = true;
      frameAccessible = false;
    }

    registerDestination(rawSrc, 'iframe_embed', {
      sourceTag: 'iframe',
      label: frame.getAttribute('title') || 'Subframe',
      isHidden: isElementInHiddenSection(frame),
      isIframeSrc: true,
      frameAccessible,
      skipReason: !frameAccessible ? 'Cross-origin subframe boundary protected by browser Same-Origin Policy (SOP).' : null
    });
  });

  const uniqueDestinations = Array.from(destinationMap.values());
  const inspectableCount = uniqueDestinations.filter(d => d.isInspectableWebUrl).length;
  const totalElementsScanned = linkNodes.length + formNodes.length + buttonNodes.length + frameNodes.length;

  return {
    pageOrigin: currentOrigin,
    totalDiscovered: uniqueDestinations.length,
    totalElementsScanned,
    inspectableCount,
    uniqueDestinations,
    skippedSummary: skippedCategories,
    boundedCapReached,
    scannedAt: new Date().toISOString()
  };
}

// ============================================================================
// CONTENT SCRIPT RUNTIME OBSERVER & MESSAGING
// ============================================================================

let cachedScanResult = null;
let mutationDebounceTimer = null;

function executePageScanAndBroadcast() {
  if (typeof document === 'undefined') return;

  const result = extractPageDestinations(document, document.baseURI || window.location.href);
  cachedScanResult = result;

  // Notify background service worker of updated page destinations
  if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
    chrome.runtime.sendMessage({
      type: 'PAGE_LINKS_DISCOVERED',
      pageUrl: window.location.href,
      summary: {
        totalDiscovered: result.totalDiscovered,
        inspectableCount: result.inspectableCount,
        skippedSummary: result.skippedSummary,
        scannedAt: result.scannedAt
      },
      destinations: result.uniqueDestinations
    }, () => {
      // Ignore background receipt errors if popup is closed
      if (chrome.runtime.lastError) {}
    });
  }
}

/**
 * Setup debounced MutationObserver for dynamic links
 */
function setupDynamicMutationObserver() {
  if (typeof MutationObserver === 'undefined' || typeof document === 'undefined') return;

  const observer = new MutationObserver((mutations) => {
    let hasRelevantChanges = false;
    for (const m of mutations) {
      if (m.type === 'childList' && (m.addedNodes.length > 0 || m.removedNodes.length > 0)) {
        hasRelevantChanges = true;
        break;
      } else if (m.type === 'attributes') {
        const attr = m.attributeName;
        if (attr === 'href' || attr === 'action' || attr === 'data-href' || attr === 'src') {
          hasRelevantChanges = true;
          break;
        }
      }
    }

    if (hasRelevantChanges) {
      if (mutationDebounceTimer) clearTimeout(mutationDebounceTimer);
      mutationDebounceTimer = setTimeout(() => {
        executePageScanAndBroadcast();
      }, 450);
    }
  });

  observer.observe(document.documentElement || document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['href', 'action', 'data-href', 'data-url', 'src']
  });
}

// Listen for messages from popup or background coordinator
if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !message.type) return false;

    if (message.type === 'SCAN_PAGE_LINKS') {
      const freshResult = extractPageDestinations(document, document.baseURI || window.location.href);
      cachedScanResult = freshResult;
      sendResponse({
        success: true,
        pageUrl: window.location.href,
        ...freshResult
      });
      return true;
    }

    if (message.type === 'GET_PAGE_SCAN_STATUS') {
      if (!cachedScanResult) {
        cachedScanResult = extractPageDestinations(document, document.baseURI || window.location.href);
      }
      sendResponse({
        success: true,
        pageUrl: window.location.href,
        ...cachedScanResult
      });
      return true;
    }

    return false;
  });
}

// Initial scan execution when document is ready
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      executePageScanAndBroadcast();
      setupDynamicMutationObserver();
    });
  } else {
    executePageScanAndBroadcast();
    setupDynamicMutationObserver();
  }
}

// Export for Node.js automated test suites
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    resolveDestinationUrl,
    categorizeDestination,
    isElementInHiddenSection,
    extractPageDestinations,
    DOWNLOAD_EXTENSIONS,
    MAX_DISCOVERED_DESTINATIONS
  };
}

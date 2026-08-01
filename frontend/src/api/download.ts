/**
 * download.ts — one place that turns a PDF Blob into a saved file.
 *
 * Every report screen used to carry its own copy of the anchor dance, and all seven
 * copies shared two real defects:
 *
 *   1. `URL.revokeObjectURL(url)` fired 150 ms after `a.click()`. The combined report is
 *      ~13 MB; revoking a blob URL while the browser is still reading it ABORTS the
 *      download — with no exception, so the spinner just stops and no file appears.
 *   2. `document.body.removeChild(a)` ran synchronously right after `click()`. Firefox
 *      requires the anchor to stay in the document until the download has started.
 *
 * Both fail silently, which is why "it generated but nothing downloaded" produced no
 * error banner. This helper keeps the URL and the anchor alive well past the click, and
 * returns the object URL so the caller can offer a manual fallback link — so a failed
 * programmatic click can never leave the designer with nothing to click.
 */

/** How long the blob URL stays valid after the click. Generous on purpose: the cost of
 *  holding it is a few MB of memory until navigation; the cost of revoking early is a
 *  silently lost report. */
const REVOKE_AFTER_MS = 10 * 60 * 1000

export interface DownloadHandle {
  /** Object URL for the blob — still valid, for a manual fallback <a href>. */
  url: string
  /** Filename offered to the browser. */
  filename: string
}

/**
 * Save `blob` as `filename`. Returns the still-valid object URL so callers can render a
 * manual "download didn't start? click here" link.
 *
 * Throws only if the browser refuses to create an object URL at all.
 */
export function downloadBlob(blob: Blob, filename: string): DownloadHandle {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  // Keep BOTH the anchor and the URL alive: removing or revoking too early is exactly
  // what silently killed these downloads.
  window.setTimeout(() => {
    try { a.remove() } catch { /* already detached */ }
    URL.revokeObjectURL(url)
  }, REVOKE_AFTER_MS)
  return { url, filename }
}

/**
 * Build the standard report filename. Centralised because the per-screen copies drifted:
 * some read `confirmedState.project_id` without optional chaining, which throws a
 * TypeError AFTER the PDF has already been fetched — losing a report that had been
 * successfully generated, and (on the control screen) skipping the approve-gate flag.
 */
export function reportFilename(state: unknown, suffix: string): string {
  const pid = (state as { project_id?: unknown } | null | undefined)?.project_id
  const safe = typeof pid === 'string' || typeof pid === 'number' ? String(pid) : 'design'
  return `PFC_Report_${safe}_${suffix}.pdf`
}

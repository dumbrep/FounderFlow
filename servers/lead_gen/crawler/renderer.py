"""
Playwright-based page renderer.
Renders JS-heavy pages and extracts clean text content.
"""
import asyncio
from servers.lead_gen.models import PageContent
from servers.lead_gen.config import PAGE_TIMEOUT_MS

# Lazy-import playwright to avoid import errors if not installed yet
_browser = None
_playwright = None


async def _get_browser():
    """Lazy-initialize a shared Playwright browser instance."""
    global _browser, _playwright
    if _browser is None:
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
    return _browser


async def render_page(url: str) -> PageContent:
    """
    Render a web page using Playwright and extract clean text.
    Falls back to raw HTTP fetch if Playwright is unavailable.
    """
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        await page.goto(url, wait_until="domcontentloaded")
        # Wait a bit for dynamic content to load
        await asyncio.sleep(1)

        title = await page.title()

        # Extract meta description
        meta_desc = ""
        try:
            meta_desc = await page.get_attribute('meta[name="description"]', "content") or ""
        except Exception:
            pass

        # Extract main text content — strip nav, header, footer, ads
        text = await page.evaluate("""
            () => {
                // Remove noise elements
                const selectors = ['nav', 'header', 'footer', '.sidebar', '.ad', 
                                   '.cookie-banner', '.popup', 'script', 'style',
                                   'noscript', 'iframe'];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
                return document.body ? document.body.innerText : '';
            }
        """)

        # Extract outgoing links for the crawler
        links = await page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a[href]');
                const urls = [];
                anchors.forEach(a => {
                    const href = a.href;
                    if (href && href.startsWith('http') && !href.includes('#')) {
                        urls.push(href);
                    }
                });
                return [...new Set(urls)].slice(0, 50);
            }
        """)

        await page.close()

        # Truncate very long pages to avoid LLM token limits
        if len(text) > 15000:
            text = text[:15000] + "\n\n[... truncated ...]"

        return PageContent(
            url=url,
            title=title,
            text=text.strip(),
            meta_description=meta_desc,
            links=links,
        )

    except Exception as e:
        print(f"[Renderer] Playwright failed for {url}: {e}, falling back to HTTP")
        return await _fallback_fetch(url)


async def _fallback_fetch(url: str) -> PageContent:
    """Fallback: fetch raw HTML and extract text with BeautifulSoup."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0 (compatible; LeadGenBot/1.0)"},
            ) as resp:
                if resp.status != 200:
                    return PageContent(url=url)
                html = await resp.text()

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
                tag.decompose()

            title = soup.title.string if soup.title else ""
            text = soup.get_text(separator="\n", strip=True)

            # Extract links
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http"):
                    links.append(href)

            if len(text) > 15000:
                text = text[:15000] + "\n\n[... truncated ...]"

            return PageContent(
                url=url,
                title=title or "",
                text=text,
                links=links[:50],
            )
        except ImportError:
            # No BeautifulSoup — return raw truncated HTML
            return PageContent(url=url, text=html[:10000])

    except Exception as e:
        print(f"[Renderer] Fallback fetch failed for {url}: {e}")
        return PageContent(url=url)


async def cleanup():
    """Close the browser when shutting down."""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None

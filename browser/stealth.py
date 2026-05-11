from playwright.async_api import Page, BrowserContext


async def apply_stealth(context: BrowserContext) -> None:
    """Apply stealth patches to avoid bot detection."""
    await context.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });

        // Spoof plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Spoof languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Override permissions query
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );

        // Override chrome runtime
        window.chrome = {
            runtime: {},
        };

        // Correct iframe contentWindow
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function () {
                return window;
            },
        });
    """)


async def set_human_like_viewport(page: Page) -> None:
    """Set a realistic viewport and user agent."""
    await page.set_viewport_size({"width": 1366, "height": 768})


async def human_delay(page: Page, min_ms: int = 500, max_ms: int = 1500) -> None:
    """Add human-like random delay."""
    import random
    delay = random.randint(min_ms, max_ms)
    await page.wait_for_timeout(delay)


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text with human-like delays between keystrokes."""
    import random
    element = await page.wait_for_selector(selector, timeout=10000)
    await element.click()
    await page.wait_for_timeout(random.randint(100, 300))
    for char in text:
        await page.keyboard.type(char)
        await page.wait_for_timeout(random.randint(50, 150))

import re
from collections.abc import Callable, Generator
from typing import override


class CSS:
    """
    A simple CSS parser to extract and replace URLs in CSS content.
    """

    url_pattern: re.Pattern[str] = re.compile(
        r'url\(\s*["\']?(.*?)["\']?\s*\)',
        re.IGNORECASE,
    )

    def __init__(self, content: str):
        self.content: str = content

    def get_urls(self) -> Generator[str]:
        """
        Extract all URLs from the CSS content.

        Yields:
            The extracted URLs.
        """
        for match in self.url_pattern.finditer(self.content):
            yield match.group(1)

    def replace_urls(self, replacer: Callable[[str], str | None]) -> None:
        """
        Replace all URLs in the CSS content using the provided replacer
        function.

        Args:
            replacer: A function that takes the original URL and returns the
                new URL.
        """

        def replacement(match: re.Match[str]) -> str:
            original_url = match.group(1)
            new_url = replacer(original_url)
            if new_url is None:
                return match.group(0)
            return f'url("{new_url}")'

        self.content = self.url_pattern.sub(replacement, self.content)

    def replace_url(self, old: str, repl: str) -> None:
        """
        Replace given URL in the CSS with the replacement.

        Args:
            old: The URL to be replaced.
            repl: The replacement URL.
        """

        def replacement(match: re.Match[str]) -> str:
            original_url = match.group(1)
            if original_url == old:
                return f'url("{repl}")'
            return match.group(0)

        self.content = self.url_pattern.sub(replacement, self.content)

    @override
    def __str__(self) -> str:
        return self.content

    def encode(self) -> bytes:
        return self.content.encode()

    @override
    def __repr__(self) -> str:
        return f'CSS(content="{self.content[:30]}...")'

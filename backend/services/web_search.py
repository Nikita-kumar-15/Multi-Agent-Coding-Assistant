# backend/services/web_search.py
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from backend.terminal.logger import tlog

def web_search(query: str, max_results: int = 3) -> list:
    """Performs a web search using DuckDuckGo."""
    tlog.info("WebSearch", f"Searching for: '{query}'")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return results
    except Exception as e:
        tlog.error("WebSearch", f"Search failed: {e}")
        return []

def fetch_page_content(url: str, timeout: int = 10) -> str:
    """Fetches and extracts text content from a URL."""
    tlog.info("WebSearch", f"Fetching content from: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
            
        text = soup.get_text(separator=' ', strip=True)
        return text
    except Exception as e:
        tlog.error("WebSearch", f"Failed to fetch page: {e}")
        return ""

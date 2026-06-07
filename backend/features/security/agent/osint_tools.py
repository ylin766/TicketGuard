import os
import requests

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "f99d20a7ebb230a9eaf4126d74a06e102ba0e1df")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "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")

def _run_serper_search(query: str, num: int = 4) -> str:
    """Internal generic Serper request function"""
    url = "https://google.serper.dev/search"
    payload = {"q": query, "num": num}
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        results = response.json().get('organic', [])
        if not results:
            return f"No records found for query: {query}"
        
        output = []
        for i, res in enumerate(results):
            output.append(f"Record {i+1}: {res.get('title')}\nSnippet: {res.get('snippet')}\nLink: {res.get('link')}\n")
        return "\n".join(output)
    except Exception as e:
        return f"Serper search exception: {str(e)}"

def search_consumer_reviews(brand_or_url: str, extra_keywords: str = "") -> str:
    """
    Broadly search for real user reviews of the ticketing website on consumer review platforms.
    Args:
        brand_or_url: Target brand or URL.
        extra_keywords: (Optional) Additional search terms. For example, pass "scam" or "fake tickets" for precise targeting.
    """
    query = f"(site:trustpilot.com OR site:sitejabber.com) \"{brand_or_url}\" {extra_keywords}".strip()
    return _run_serper_search(query, num=8)

def search_reddit_discussions(brand_or_url: str, specific_subreddit: str = "", extra_keywords: str = "") -> str:
    """
    Search for discussions about the website across all of Reddit or in a specific subreddit.
    Args:
        brand_or_url: Target brand or URL.
        specific_subreddit: (Optional) Specify a subreddit. e.g., "r/Scams" for fraud-related info. Leave empty for site-wide.
        extra_keywords: (Optional) Additional search terms like "scam", "legit", "not working".
    """
    site_modifier = f"site:reddit.com/{specific_subreddit}" if specific_subreddit else "site:reddit.com"
    query = f"{site_modifier} \"{brand_or_url}\" {extra_keywords}".strip()
    return _run_serper_search(query, num=8)

def search_twitter_mentions(brand_or_url: str, extra_keywords: str = "") -> str:
    """
    Search Twitter (X) for mentions of the brand, suitable for finding real-time scam alerts.
    Args:
        brand_or_url: Target brand or URL.
        extra_keywords: (Optional) Additional search terms like "scam", "fake".
    """
    query = f"(site:twitter.com OR site:x.com) \"{brand_or_url}\" {extra_keywords}".strip()
    return _run_serper_search(query, num=8)

def search_general_opinions(brand_or_url: str, investigation_focus: str = "safe or reliable? User experiences and reviews.") -> str:
    """
    Use Tavily's advanced deep search to extract the most detailed discussions across the web as a fallback.
    Args:
        brand_or_url: Target brand or URL.
        investigation_focus: Agent can customize the focus of the investigation.
    """
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": f"Regarding {brand_or_url}: {investigation_focus}",
        "search_depth": "advanced",
        "max_results": 6,
        "include_raw_content": False
    }
    try:
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
        results = response.json().get('results', [])
        if not results:
            return f"Tavily found no discussions about {brand_or_url}."
            
        output = []
        for i, res in enumerate(results):
            output.append(f"Record {i+1}: {res.get('title')}\nContent Snippet: {res.get('content')}\nLink: {res.get('url')}\n")
        return "\n".join(output)
    except Exception as e:
        return f"Tavily search exception: {str(e)}"

def read_specific_url(url: str) -> str:
    """
    When a highly valuable clue is found in a search snippet, use this tool to directly read the full webpage content.
    Args:
        url: The full link of the webpage to be read deeply.
    """
    try:
        reader_url = f"https://r.jina.ai/{url}"
        response = requests.get(reader_url, timeout=15)
        response.raise_for_status()
        content = response.text
        if len(content) > 10000:
            content = content[:10000] + "\n...[Content too long, truncated]..."
        return content
    except Exception as e:
        return f"Failed to read webpage content: {str(e)}"

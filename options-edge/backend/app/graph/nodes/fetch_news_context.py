"""Fetch news context using Benzinga API and Claude web search synthesis."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.data.benzinga_client import BenzingaClient
from app.models.state import AnalysisState, NewsContext

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

NEWS_SYNTHESIS_PROMPT = """\
You are a financial news analyst specializing in options-relevant catalysts. Analyze the
following news headlines and summaries for the ticker {ticker}.

Your task:
1. Identify material catalysts (earnings, FDA decisions, M&A, guidance changes, analyst actions)
2. Assess overall sentiment (bullish, bearish, neutral, mixed)
3. Flag any upcoming scheduled events that could drive implied volatility
4. Note analyst upgrades/downgrades and price target changes

Return your analysis as JSON with this exact structure:
{{
    "headlines": ["headline 1", "headline 2", ...],
    "summaries": ["1-2 sentence summary of each material news item"],
    "sentiment": "bullish" | "bearish" | "neutral" | "mixed",
    "analyst_actions": [
        {{
            "firm": "analyst firm name",
            "action": "upgrade/downgrade/initiate/reiterate",
            "rating": "buy/hold/sell",
            "price_target": 123.00,
            "date": "YYYY-MM-DD"
        }}
    ],
    "upcoming_catalysts": ["description of upcoming events"],
    "iv_impact_assessment": "description of expected IV impact from news"
}}

Raw news data:
{news_data}
"""


async def fetch_news_context(state: AnalysisState) -> dict:
    """Fetch and synthesize news context for the ticker.

    Steps:
    1. Pull recent ticker-tagged news headlines from Benzinga free tier.
    2. Use Claude with web search tool for broader context (analyst upgrades,
       social sentiment, macro factors).
    3. Synthesize everything into a structured news summary.

    Returns a dict keyed by ``news_context`` for state merging.
    """
    settings = get_settings()
    ticker = state.ticker.upper()

    logger.info("Fetching news context for %s", ticker)

    # -- Fetch structured headlines from Benzinga free tier --------------------
    formatted_articles: list[dict] = []
    try:
        async with BenzingaClient(api_key=settings.BENZINGA_API_KEY) as bz_client:
            articles = await bz_client.get_news(ticker=ticker, limit=20)
            for article in articles:
                formatted_articles.append({
                    "title": article.get("title", ""),
                    "teaser": article.get("teaser", ""),
                    "published": article.get("published", ""),
                    "source": article.get("source", ""),
                    "url": article.get("url", ""),
                    "tickers": article.get("tickers", []),
                })
    except Exception:
        logger.warning(
            "Benzinga API unavailable for %s, proceeding with web search only",
            ticker,
            exc_info=True,
        )

    if not formatted_articles:
        logger.info("No Benzinga headlines found for %s, relying on web search", ticker)

    # -- Claude synthesis with web search for broader context ------------------
    anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    news_payload = (
        json.dumps(formatted_articles, indent=2, default=str)
        if formatted_articles
        else "(no structured headlines available — rely on web search)"
    )

    prompt = NEWS_SYNTHESIS_PROMPT.format(
        ticker=ticker,
        news_data=news_payload,
    )

    response = await anthropic_client.messages.create(
        model=MODEL,
        max_tokens=2000,
        tools=[{"type": "web_search_20250305"}],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Research the latest news, analyst actions, and sentiment for "
                    f"{ticker} using web search for broader context (analyst upgrades, "
                    f"social sentiment, macro factors). Then synthesize everything — "
                    f"including the Benzinga headlines below — into the required JSON "
                    f"format.\n\n{prompt}"
                ),
            }
        ],
    )

    # Extract text content from response
    synthesis_text = ""
    for block in response.content:
        if block.type == "text":
            synthesis_text += block.text

    # Parse JSON from Claude response
    try:
        # Handle potential markdown code fences
        json_str = synthesis_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        synthesis = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse Claude news synthesis as JSON, using fallback")
        synthesis = {
            "headlines": [a.get("title", "") for a in formatted_articles[:10]],
            "summaries": [a.get("teaser", "") for a in formatted_articles[:5]],
            "sentiment": "neutral",
            "analyst_actions": [],
        }

    news_context = NewsContext(
        headlines=synthesis.get("headlines", []),
        summaries=synthesis.get("summaries", []),
        sentiment=synthesis.get("sentiment", "neutral"),
        analyst_actions=synthesis.get("analyst_actions", []),
    )

    logger.info(
        "News context fetched: %d headlines, sentiment=%s",
        len(news_context.headlines),
        news_context.sentiment,
    )

    return {"news_context": news_context}

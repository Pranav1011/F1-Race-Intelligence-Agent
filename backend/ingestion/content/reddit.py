"""
Reddit Content Scraper for r/f1technical

Uses Reddit's public JSON API (no authentication required).
Rate limited to 1 request per 2 seconds to be respectful.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Reddit public JSON API - no auth needed
REDDIT_BASE_URL = "https://www.reddit.com"
USER_AGENT = "F1-RIA-Bot/1.0 (Educational F1 Analysis Project)"

# Rate limiting: Reddit allows ~60 requests/min for unauthenticated
# Using 3s delay to be safe and avoid 429 errors
RATE_LIMIT_DELAY = 3.0  # seconds between requests


@dataclass
class RedditPost:
    """Represents a Reddit post with comments."""

    id: str
    title: str
    selftext: str
    author: str
    score: int
    upvote_ratio: float
    num_comments: int
    created_utc: float
    url: str
    permalink: str
    flair: Optional[str]
    top_comments: list[dict]

    @property
    def created_date(self) -> datetime:
        return datetime.fromtimestamp(self.created_utc)

    @property
    def full_text(self) -> str:
        """Combine title, body, and top comments for embedding."""
        parts = [f"Title: {self.title}"]

        if self.selftext:
            parts.append(f"\nPost: {self.selftext}")

        if self.top_comments:
            parts.append("\nTop Comments:")
            for i, comment in enumerate(self.top_comments[:5], 1):
                parts.append(f"{i}. {comment['body'][:500]}")

        return "\n".join(parts)


class RedditScraper:
    """Scrape r/f1technical using public JSON API."""

    def __init__(
        self,
        subreddit: str = "f1technical",
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
    ):
        self.subreddit = subreddit
        self.base_url = f"{REDDIT_BASE_URL}/r/{subreddit}"
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.encoder: Optional[SentenceTransformer] = None
        self.collection_name = "reddit_discussions"

        # HTTP client with proper headers
        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        )

    def _init_encoder(self):
        """Lazy load the encoder."""
        if self.encoder is None:
            logger.info("Loading sentence transformer model...")
            self.encoder = SentenceTransformer("BAAI/bge-base-en-v1.5")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def _fetch_json(self, url: str, retry_count: int = 0) -> Optional[dict]:
        """Fetch JSON from Reddit with rate limiting."""
        await asyncio.sleep(RATE_LIMIT_DELAY)

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                if retry_count >= 2:
                    logger.warning(f"Rate limited 3 times, skipping: {url}")
                    return None
                logger.warning(f"Rate limited, waiting 60s... (retry {retry_count + 1}/3)")
                await asyncio.sleep(60)
                return await self._fetch_json(url, retry_count + 1)
            logger.error(f"HTTP error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    async def get_top_posts(
        self,
        time_filter: str = "all",
        limit: int = 100,
    ) -> list[RedditPost]:
        """
        Get top posts from the subreddit.

        Args:
            time_filter: "hour", "day", "week", "month", "year", "all"
            limit: Maximum posts to fetch (max 100 per request)
        """
        posts = []
        after = None
        fetched = 0

        while fetched < limit:
            url = f"{self.base_url}/top.json?t={time_filter}&limit=100"
            if after:
                url += f"&after={after}"

            data = await self._fetch_json(url)
            if not data or "data" not in data:
                break

            children = data["data"].get("children", [])
            if not children:
                break

            for child in children:
                if fetched >= limit:
                    break

                post_data = child["data"]

                # Skip non-text posts
                if post_data.get("is_video") or post_data.get("is_gallery"):
                    continue

                # Fetch comments for this post
                comments = await self._get_post_comments(post_data["id"])

                post = RedditPost(
                    id=post_data["id"],
                    title=post_data["title"],
                    selftext=post_data.get("selftext", ""),
                    author=post_data.get("author", "[deleted]"),
                    score=post_data.get("score", 0),
                    upvote_ratio=post_data.get("upvote_ratio", 0),
                    num_comments=post_data.get("num_comments", 0),
                    created_utc=post_data.get("created_utc", 0),
                    url=post_data.get("url", ""),
                    permalink=post_data.get("permalink", ""),
                    flair=post_data.get("link_flair_text"),
                    top_comments=comments,
                )
                posts.append(post)
                fetched += 1

                logger.info(f"Fetched post {fetched}/{limit}: {post.title[:50]}...")

            after = data["data"].get("after")
            if not after:
                break

        return posts

    async def get_hot_posts(self, limit: int = 50) -> list[RedditPost]:
        """Get hot/trending posts."""
        posts = []

        url = f"{self.base_url}/hot.json?limit={min(limit, 100)}"
        data = await self._fetch_json(url)

        if not data or "data" not in data:
            return posts

        for child in data["data"].get("children", [])[:limit]:
            post_data = child["data"]

            if post_data.get("is_video") or post_data.get("is_gallery"):
                continue

            comments = await self._get_post_comments(post_data["id"])

            post = RedditPost(
                id=post_data["id"],
                title=post_data["title"],
                selftext=post_data.get("selftext", ""),
                author=post_data.get("author", "[deleted]"),
                score=post_data.get("score", 0),
                upvote_ratio=post_data.get("upvote_ratio", 0),
                num_comments=post_data.get("num_comments", 0),
                created_utc=post_data.get("created_utc", 0),
                url=post_data.get("url", ""),
                permalink=post_data.get("permalink", ""),
                flair=post_data.get("link_flair_text"),
                top_comments=comments,
            )
            posts.append(post)

        return posts

    async def search_posts(
        self,
        query: str,
        time_filter: str = "all",
        limit: int = 50,
    ) -> list[RedditPost]:
        """Search for posts matching a query."""
        posts = []

        url = f"{self.base_url}/search.json?q={query}&restrict_sr=1&t={time_filter}&limit={min(limit, 100)}"
        data = await self._fetch_json(url)

        if not data or "data" not in data:
            return posts

        for child in data["data"].get("children", [])[:limit]:
            post_data = child["data"]

            if post_data.get("is_video") or post_data.get("is_gallery"):
                continue

            comments = await self._get_post_comments(post_data["id"])

            post = RedditPost(
                id=post_data["id"],
                title=post_data["title"],
                selftext=post_data.get("selftext", ""),
                author=post_data.get("author", "[deleted]"),
                score=post_data.get("score", 0),
                upvote_ratio=post_data.get("upvote_ratio", 0),
                num_comments=post_data.get("num_comments", 0),
                created_utc=post_data.get("created_utc", 0),
                url=post_data.get("url", ""),
                permalink=post_data.get("permalink", ""),
                flair=post_data.get("link_flair_text"),
                top_comments=comments,
            )
            posts.append(post)

        return posts

    async def _get_post_comments(
        self,
        post_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get top comments for a post."""
        url = f"{REDDIT_BASE_URL}/comments/{post_id}.json?limit={limit}&sort=top"
        data = await self._fetch_json(url)

        if not data or len(data) < 2:
            return []

        comments = []
        comment_data = data[1].get("data", {}).get("children", [])

        for child in comment_data:
            if child.get("kind") != "t1":
                continue

            comment = child.get("data", {})
            body = comment.get("body", "")

            # Skip deleted/removed comments
            if body in ["[deleted]", "[removed]", ""]:
                continue

            comments.append({
                "id": comment.get("id"),
                "author": comment.get("author", "[deleted]"),
                "body": body,
                "score": comment.get("score", 0),
            })

            if len(comments) >= limit:
                break

        return comments

    def _clean_text(self, text: str) -> str:
        """Clean Reddit markdown and formatting."""
        # Remove Reddit markdown links
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove URLs
        text = re.sub(r'https?://\S+', '', text)
        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    async def ingest_to_qdrant(
        self,
        posts: list[RedditPost],
        batch_size: int = 10,
    ) -> int:
        """
        Embed and store posts in Qdrant.

        Returns:
            Number of posts ingested
        """
        self._init_encoder()

        points = []
        for post in posts:
            # Clean and prepare text
            full_text = self._clean_text(post.full_text)

            # Skip posts with too little content
            if len(full_text) < 100:
                continue

            # Generate embedding
            embedding = self.encoder.encode(full_text).tolist()

            # Create point
            point = PointStruct(
                id=hash(post.id) % (2**63),  # Convert string ID to int
                vector=embedding,
                payload={
                    "reddit_id": post.id,
                    "title": post.title,
                    "content": full_text[:2000],  # Limit stored content
                    "author": post.author,
                    "score": post.score,
                    "upvote_ratio": post.upvote_ratio,
                    "num_comments": post.num_comments,
                    "created_date": post.created_date.isoformat(),
                    "url": f"https://reddit.com{post.permalink}",
                    "flair": post.flair,
                    "source": f"r/{self.subreddit}",
                    "type": "reddit_discussion",
                },
            )
            points.append(point)

        # Upsert in batches
        ingested = 0
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=batch,
            )
            ingested += len(batch)
            logger.info(f"Ingested {ingested}/{len(points)} posts")

        return ingested


async def run_reddit_ingestion(
    subreddit: str = "f1technical",
    qdrant_host: str = "qdrant",
    qdrant_port: int = 6333,
    top_limit: int = 200,
    hot_limit: int = 50,
    search_queries: Optional[list[str]] = None,
):
    """
    Run full Reddit ingestion job.

    Args:
        subreddit: Subreddit to scrape
        qdrant_host: Qdrant host
        qdrant_port: Qdrant port
        top_limit: Number of top posts to fetch
        hot_limit: Number of hot posts to fetch
        search_queries: Additional search queries to run
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Default F1 technical search queries
    if search_queries is None:
        search_queries = [
            "aerodynamics",
            "suspension setup",
            "tire strategy",
            "DRS",
            "ground effect",
            "power unit",
            "regulations",
            "undercut overcut",
        ]

    scraper = RedditScraper(
        subreddit=subreddit,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
    )

    try:
        all_posts = []

        # Fetch top posts of all time
        logger.info(f"Fetching top {top_limit} posts from r/{subreddit}...")
        top_posts = await scraper.get_top_posts(time_filter="all", limit=top_limit)
        all_posts.extend(top_posts)
        logger.info(f"Fetched {len(top_posts)} top posts")

        # Fetch hot/trending posts
        logger.info(f"Fetching hot posts...")
        hot_posts = await scraper.get_hot_posts(limit=hot_limit)
        all_posts.extend(hot_posts)
        logger.info(f"Fetched {len(hot_posts)} hot posts")

        # Search for specific technical topics
        for query in search_queries:
            logger.info(f"Searching for '{query}'...")
            search_results = await scraper.search_posts(query, limit=30)
            all_posts.extend(search_results)
            logger.info(f"Found {len(search_results)} posts for '{query}'")

        # Deduplicate by post ID
        seen_ids = set()
        unique_posts = []
        for post in all_posts:
            if post.id not in seen_ids:
                seen_ids.add(post.id)
                unique_posts.append(post)

        logger.info(f"Total unique posts: {len(unique_posts)}")

        # Ingest to Qdrant
        ingested = await scraper.ingest_to_qdrant(unique_posts)
        logger.info(f"Successfully ingested {ingested} posts to Qdrant")

        return ingested

    finally:
        await scraper.close()


# CLI entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Reddit Content Ingestion")
    parser.add_argument(
        "--subreddit",
        type=str,
        default="f1technical",
        help="Subreddit to scrape",
    )
    parser.add_argument(
        "--top-limit",
        type=int,
        default=200,
        help="Number of top posts to fetch",
    )
    parser.add_argument(
        "--hot-limit",
        type=int,
        default=50,
        help="Number of hot posts to fetch",
    )
    parser.add_argument(
        "--qdrant-host",
        type=str,
        default="qdrant",
        help="Qdrant host",
    )

    args = parser.parse_args()

    asyncio.run(
        run_reddit_ingestion(
            subreddit=args.subreddit,
            qdrant_host=args.qdrant_host,
            top_limit=args.top_limit,
            hot_limit=args.hot_limit,
        )
    )

import asyncio
import io
import re
from datetime import datetime, timedelta
from random import shuffle

import aiohttp
import requests
from bs4 import BeautifulSoup, PageElement

import memes

# from fake_useragent import UserAgent


_MOVIE_OR_LOG = re.compile(r"(https\:\/\/letterboxd\.com\/).*(film\/.+\/?)")


class MovieLog:
    """
    Attributes
    ----------
    link : str
    title : str
    is_liked : bool
    is_rewatch : bool
    year: str | None
    rating : str | None
    review : str | None
    poster_url: str | None
    """

    _RATING_TO_STARS = {
        "0.5": "½★",
        "1.0": "★",
        "1.5": "★½",
        "2.0": "★★",
        "2.5": "★★½",
        "3.0": "★★★",
        "3.5": "★★★½",
        "4.0": "★★★★",
        "4.5": "★★★★½",
        "5.0": "★★★★★",
    }

    _RATING_TO_TELEMOJI = {
        None: (5433986691549387917, "😋"),
        "0.5": (5436167151956284338, "🖕"),
        "1.0": (5434146580296913175, "🤓"),
        "1.5": (5433905855969906170, "😁"),
        "2.0": (5435946807249099970, "🚬"),
        "2.5": (5434010992474349724, "😐"),
        "3.0": (5435893352086136461, "🐱"),
        "3.5": (5435908904162713385, "🎧"),
        "4.0": (5435881665480119374, "😳"),
        "4.5": (5436196100035862776, "😭"),
        "5.0": (5435974213435415251, "🤯"),
    }

    _REWATCHED = re.compile(r"\/\d+\/$")

    def __init__(self, entry: PageElement) -> None:
        self._entry = entry
        self._parse_metadata()
        self._parse_review()

    async def get_advanced_metadata(self, session: aiohttp.ClientSession) -> None:
        if response := await _make_request(session, self.link):
            log = BeautifulSoup(response, features="html.parser")
            self.is_liked = bool(log.find("span", {"class": "icon-liked"}))
        else:
            self.is_liked = False
        # end = datetime.now()
        # print(end - start)

    def format(self) -> str:
        year = f" ({self.year})" if self.year else ""
        rewatch = "🔄" if self.is_rewatch else ""
        heart = "❤️" if self.is_liked else ""
        stars = self._RATING_TO_STARS[self.rating] if self.rating else ""
        emoji = '<tg-emoji emoji-id="{}">{}</tg-emoji>'.format(
            *self._RATING_TO_TELEMOJI[self.rating]
        )

        prefix_components = (
            [rewatch, heart, emoji, stars] if stars else [rewatch, heart, emoji]
        )
        prefix = " ".join(filter(bool, prefix_components))

        review = self._format_review(self._unformatted_review, self.has_spoilers)
        if review:
            review = f"\n<blockquote expandable>{review}<blockquote expandable/>"
        else:
            review = ""

        # tmdb_id = entry.find("tmdb:movieId") or entry.find("tmdb:tvId")
        # self.link = f"https://letterboxd.com/tmdb/{tmdb_id.text}"

        return f'{prefix} <a href="{self.link}"><i>{self.title}{year}</i></a>{review}'

    def _parse_metadata(self) -> None:
        self.link = self._entry.find("link").text  # type: ignore

        self.title = self._entry.find("letterboxd:filmTitle").text  # type: ignore
        self.year = (
            year.text if (year := self._entry.find("letterboxd:filmYear")) else None  # type: ignore
        )
        self.rating = (
            rating.text
            if (rating := self._entry.find("letterboxd:memberRating"))  # type: ignore
            else None
        )
        self.is_rewatch = (
            rewatch.text == "Yes"
            if (rewatch := self._entry.find("letterboxd:rewatch"))  # type: ignore
            else None
        )

    def _parse_review(self) -> None:
        review = BeautifulSoup(
            self._entry.find("description").text,  # type: ignore
            features="html.parser",
        )
        self.poster_url = None
        self.has_spoilers = False

        first_p = review.find("p")
        if first_p:
            img = first_p.find("img")
            if img:
                self.poster_url = img["src"]  # type: ignore
                first_p.decompose()  # type: ignore

        first_p = review.find("p")
        if (
            first_p
            and first_p.find("em")
            and first_p.text.startswith("This review may contain spoilers.")
        ):
            self.has_spoilers = True
            first_p.decompose()  # type: ignore

        last_p = review.find_all("p")[-1]
        if last_p and last_p.text.startswith("Watched on"):
            last_p.decompose()

        self._unformatted_review = BeautifulSoup(
            str(review).strip(), features="html.parser"
        )

    @staticmethod
    def _format_review(review: BeautifulSoup, has_spoilers: bool) -> str | None:
        for blockquote in review.find_all("blockquote"):
            for p in blockquote.find_all("p"):
                p.insert_before("\u00a0" * 8)

            for br in blockquote.find_all("br"):
                br.insert_before("\n" + "\u00a0" * 8)
                br.unwrap()
            blockquote.unwrap()

        for br in review.find_all("br"):
            br.replace_with("\n")

        for p in review.find_all("p")[:-1]:
            p.append("\n\n")
            p.unwrap()

        if has_spoilers:
            return f"<b><i>\u00a0\nЦе ревʼю містить спойлери.\n</i></b>\n{review}"

        return formatted_review if (formatted_review := str(review)) else None


class ListLog:
    """
    Attributes
    ----------
    link : str
    title: str
    size: int | None
    """

    _LIST_SIZE = re.compile(r"^A list of (\d+)")

    def __init__(self, entry: PageElement) -> None:
        self._entry = entry
        self._parse_metadata()

    async def get_advanced_metadata(self, session: aiohttp.ClientSession) -> None:
        if response := await _make_request(session, self.link):
            log = BeautifulSoup(response, features="html.parser")
            desc = log.find("meta", {"name": "description"})["content"]  # type: ignore
            if desc and (match := re.match(self._LIST_SIZE, desc)):  # type: ignore
                self.size = int(match[1])
        else:
            self.size = None

    def format(self) -> str:
        size = f" ({self._decline_size(self.size)})" if self.size else ""
        return f'🆕 🎬 <a href="{self.link}"><i>{self.title}</i>{size}</a>'

    def _parse_metadata(self) -> None:
        self.link = self._entry.find("link").text  # type: ignore
        self.title = self._entry.find("title").text  # type: ignore

    @staticmethod
    def _decline_size(size: int) -> str:
        last_digit = size % 10
        last_two_digits = size % 100

        if last_digit == 1 and last_two_digits != 11:
            return f"{size} фільм"
        elif 2 <= last_digit <= 4 and not (11 <= last_two_digits <= 14):
            return f"{size} фільми"
        else:
            return f"{size} фільмів"


class UserFeed(list[MovieLog | ListLog]):
    """
    Attributes
    ----------
    user_link : str
    name : str
    cutoff_time : datetime | None
    """

    _USER_LINK = re.compile(r"(https:\/\/letterboxd\.com\/[^\/]+\/)")

    def __init__(
        self,
        entries: list[MovieLog | ListLog],
        user_link: str,
        name: str,
    ) -> None:
        super().__init__(entries)
        self.name = name
        self.user_link = user_link

    def format(self) -> str:
        prefix = f'<b>Оновлення від <a href="{self.user_link}">{self.name}</a>:</b>'
        return "\n".join([prefix, *[entry.format() for entry in self]])


class RssUpdatesManager:
    """
    Attributes
    ----------
    cutoff_time : datetime
    """

    def __init__(self, max_age_minutes: int):
        self.age = max_age_minutes

    async def fetch_updates_from_users(self, usernames: list[str]) -> list[UserFeed]:
        shuffle(usernames)
        urls = [f"https://letterboxd.com/{username}/rss" for username in usernames]
        responses: list = await _fetch_all(urls)

        return await self._create_user_feeds(list(filter(bool, responses)))

    @staticmethod
    def format_feeds(user_feeds: list[UserFeed]) -> list[str]:
        return [user_feed.format() for user_feed in user_feeds if user_feed]

    @staticmethod
    def chunk_feeds(user_feeds: list[str], chunk_len=0) -> list[str]:
        messages = []
        curr_message_parts = []
        curr_message_len = 0

        for user_feed in user_feeds:
            text_len = len(user_feed)

            if text_len > chunk_len:
                continue

            if curr_message_len + text_len <= chunk_len - 2:
                curr_message_parts.append(user_feed)
                curr_message_len += text_len
            else:
                messages.append("\n\n".join(curr_message_parts))
                curr_message_parts = [user_feed]
                curr_message_len = text_len

        if curr_message_parts:
            messages.append("\n\n".join(curr_message_parts))

        return messages

    async def _create_user_feeds(self, responses: list):
        user_feeds = []
        cutoff_time = datetime.now().astimezone() - timedelta(minutes=self.age)

        for rss in responses:
            xml = BeautifulSoup(rss, features="xml")

            user_link = xml.find("link").text  # type: ignore
            name = xml.find("title").text.removeprefix("Letterboxd - ")  # type: ignore

            all_entries = xml.find_all("item")
            new_entries = list(
                filter(
                    lambda entry: self._is_entry_new(entry, cutoff_time),
                    all_entries,
                )
            )

            if new_entries:
                user_feed = UserFeed([], user_link, name)

                for entry in new_entries:
                    user_feed.append(
                        MovieLog(entry) if "w" in entry.guid.text else ListLog(entry)
                    )

                async with aiohttp.ClientSession() as session:
                    tasks = [log.get_advanced_metadata(session) for log in user_feed]
                    await asyncio.gather(*tasks)

                user_feeds.append(user_feed)

        return user_feeds

    @staticmethod
    def _is_entry_new(entry: PageElement, cutoff_time: datetime) -> bool:
        # Example timestamp: "Thu, 19 Sep 2024 10:32:31 +1200"
        entry_timestamp = entry.find("pubDate").text  # type: ignore
        timestamp = datetime.strptime(entry_timestamp, "%a, %d %b %Y %H:%M:%S %z")
        return timestamp > cutoff_time


async def create_memes(feeds: list[UserFeed]):
    originating_feeds = []
    creators = []
    poster_urls = []

    if feeds:
        for feed in feeds:
            for entry in feed:
                if isinstance(entry, MovieLog) and entry.rating and entry.poster_url:
                    match entry.rating:
                        case "5.0":
                            creators.append(memes.create_high_rating_meme)
                        case "0.5" | "1.0":
                            creators.append(memes.create_low_rating_meme)
                        case _:
                            continue
                    originating_feeds.append(feed)
                    poster_urls.append(entry.poster_url)
        posters = await _fetch_all(poster_urls)

    pictures = []
    for feed, creator, poster in zip(originating_feeds, creators, posters):
        pictures.append(creator(feed.name, io.BytesIO(poster)))

    return pictures


def letterboxd_to_link(url: str) -> str | None:
    letterboxd_or_boxd = requests.get(url)
    if letterboxd_or_boxd.status_code == 200:
        url = BeautifulSoup(
            letterboxd_or_boxd.text,
            features="html.parser",
        ).find("meta", property="og:url")["content"]  # type: ignore

        if match := re.search(_MOVIE_OR_LOG, url):  # type: ignore
            movie_response = requests.get(f"{match[1]}{match[2]}")
            return (
                r"https://vidsrc.cc/v2/embed/movie/"
                + (
                    BeautifulSoup(movie_response.text, features="html.parser")
                    .find("p", {"class": "text-link text-footer"})
                    .find_all("a")[1]["href"]  # type: ignore
                    .split("/")[-2]
                )
            )


async def _make_request(session: aiohttp.ClientSession, url):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.read()
            else:
                print(response.status, url)
    except Exception as e:
        print(e)


async def _fetch_all(urls: list[str]) -> list:
    responses = []

    async with aiohttp.ClientSession() as session:
        tasks = [_make_request(session, url) for url in urls]
        responses = await asyncio.gather(*tasks)

    return responses

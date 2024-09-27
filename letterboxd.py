import asyncio
from datetime import datetime
from random import shuffle

import aiohttp
import requests
from bs4 import BeautifulSoup

RATING_TO_STARS = {
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

RATING_TO_EMOJI = {
    "": (5433986691549387917, "😋"),
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


async def _make_request(session, url):
    try:
        async with session.get(url) as response:
            return await response.read()
    except Exception as e:
        return str(e)


async def _fetch_all(users):
    urls = [f"https://letterboxd.com/{username}/rss" for username in users]
    connector = aiohttp.TCPConnector(limit=25)
    responses = []

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_make_request(session, url) for url in urls]
        responses = await asyncio.gather(*tasks)

    return responses


def letterboxd_to_link(url):
    video_source = r"https://vidsrc.cc/v2/embed/movie/"

    response = requests.get(url)

    if response.status_code == 200:
        link = (
            video_source
            + (
                BeautifulSoup(response.text, features="html.parser")
                .find("p", {"class": "text-link text-footer"})
                .find_all("a")[1]["href"]
                .split("/")[-2]
            )
        )
        response = requests.get(
            link,
            headers={"User-Agent": ""},
        )

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, features="html.parser")
            if soup.find("div", {"class": "not-found"}):
                raise ValueError

            return link

    return None


def _get_review_and_metadata(entry):
    review = BeautifulSoup(entry.find("description").text, features="html.parser")
    img = None
    has_spoilers = False

    first_p = review.find("p")
    if first_p:
        img = first_p.find("img")
        if img:
            img = img["src"]
            first_p.decompose()

    first_p = review.find("p")
    if (
        first_p
        and first_p.find("em")
        and first_p.text.startswith("This review may contain spoilers.")
    ):
        first_p.decompose()
        has_spoilers = True

    last_p = review.find_all("p")[-1]
    if last_p and last_p.text.startswith("Watched on"):
        last_p.decompose()

    return BeautifulSoup(str(review).strip(), features="html.parser"), img, has_spoilers


def _format_review(entry):
    review, img, has_spoilers = _get_review_and_metadata(entry)

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
    return review if str(review) else ""


def _format_movie(entry):
    movie = entry.find("letterboxd:filmTitle").text.rstrip()

    year = entry.find("letterboxd:filmYear")
    year = f" ({year.text})" if year else ""

    rating = entry.find("letterboxd:memberRating")
    stars = RATING_TO_STARS[rating.text] if rating else ""

    emoji = '<tg-emoji emoji-id="{}">{}</tg-emoji>'.format(
        *RATING_TO_EMOJI[rating.text if rating else ""]
    )

    if stars:
        prefix = " ".join([emoji, stars])
    else:
        prefix = emoji

    review = _format_review(entry)
    if review:
        review = f"\n<blockquote expandable>{review}<blockquote expandable/>"
        link = entry.find("link").text
    else:
        tmdb_id = entry.find("tmdb:movieId") or entry.find("tmdb:tvId")
        link = f"https://letterboxd.com/tmdb/{tmdb_id.text}"

    return f'{prefix} <a href="{link}"><i>{movie}{year}</i></a>{review}'


def _format_user(entries):
    link = entries[0].find("link").text.split("/film/")[0]
    name = entries[0].find("dc:creator").text

    text = [f'<b>Оновлення від <a href="{link}">{name}</a>:</b>']

    for entry in entries:
        text.append(_format_movie(entry))

    return "\n".join(text)


def _is_entry_new(entry_time_str, cutoff_time):
    # Example timestamp: "Thu, 19 Sep 2024 10:32:31 +1200"
    timestamp = datetime.strptime(entry_time_str, "%a, %d %b %Y %H:%M:%S %z")
    return timestamp > cutoff_time


def _filter_new_movies(rss, cutoff_time):
    movies = []

    soup = BeautifulSoup(rss, features="xml")
    entries = soup.find_all("item")
    if len(entries) > 0:
        # w is movie, l is list
        movies = [e for e in entries if "w" in e.guid.text]

    return [
        movie
        for movie in movies
        if _is_entry_new(movie.find("pubDate").text, cutoff_time)
    ]


async def fetch_movie_updates(users, cutoff_time):
    shuffle(users)
    responses = await _fetch_all(users)
    message = []

    for user in responses:
        if updates := _filter_new_movies(user, cutoff_time):
            message.append(_format_user(updates))

    return "\n\n".join(message)

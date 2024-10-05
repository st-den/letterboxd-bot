import asyncio
import re
from argparse import ArgumentParser
from datetime import datetime

from telethon import TelegramClient, events

# from telethon.tl.functions.messages import SendReactionRequest
# from telethon.tl.types import ReactionEmoji
from telethon.types import MessageEntityUrl, PeerChannel

import letterboxd
import settings
from custom_html_parser import CustomHtmlParser

LETTERBOXD_OR_BOXD = re.compile(
    r"^(?:https?:\/\/)?(?:www\.)?(boxd\.it.*|letterboxd\.com.*)"
)

current_task = None

client = TelegramClient(
    settings.session,  # type: ignore
    settings.api_id,
    settings.api_hash,  # type: ignore
)
client.start(phone=settings.phone_number)  # type: ignore
client.parse_mode = CustomHtmlParser()  # type: ignore

parser = ArgumentParser()
parser.add_argument(
    "--age",
    default=60,
    type=int,
    help="The maximum age of new entries in minutes.",
)
parser.add_argument(
    "--debug",
    default=False,
    type=bool,
    help="Debug mode sends updates to Saved Messages once.",
)
args = parser.parse_args()

# @client.on(events.NewMessage(from_users=258692322))
# async def like_user_messages(event):
#     await event.client(
#         SendReactionRequest(
#             peer=event.chat_id,
#             msg_id=event.id,
#             reaction=[ReactionEmoji(emoticon="👍")],
#         )
#     )


@client.on(events.NewMessage())
async def letterboxd_link_handler(event):  # sourcery skip: last-if-guard
    if event.message.entities and (
        event.is_group and event.mentioned or event.message.is_private
    ):
        for entity in event.message.entities:
            if isinstance(entity, MessageEntityUrl):
                url = event.raw_text[entity.offset : entity.offset + entity.length]
                if match := re.search(LETTERBOXD_OR_BOXD, url):
                    url = f"https://{match[1]}"
                    try:
                        if link := letterboxd.letterboxd_to_link(url):
                            await event.reply(link)
                    except AttributeError:
                        print("Неправильне посилання.")


@client.on(events.NewMessage(pattern=r"^>add (\w+)"))
async def add_user_handler(event):
    settings.add_user(event.pattern_match.group(1))


@client.on(events.NewMessage(pattern=r"^>remove (\w+)"))
async def remove_user_handler(event):
    settings.remove_user(event.pattern_match.group(1))


@client.on(events.NewMessage(pattern=r"^>age (\d+)"))
async def age_handler(event):
    global current_task
    new_age = int(event.pattern_match.group(1))

    if current_task:
        current_task.cancel()
        try:
            await current_task
        except asyncio.CancelledError:
            print(f"Restarting main() with age_minutes={new_age}")

    current_task = client.loop.create_task(main(age_minutes=new_age))


@client.on(events.NewMessage(pattern=r"^ping$"))
async def ping_handler(event):
    event.reply("pong")


async def main(
    users: list[str] = settings.users,
    age_minutes: int = args.age,
    debug: bool = args.debug,
):
    chat = PeerChannel(settings.chat_id)
    bot = await client.get_me()

    while True:
        start_time = datetime.now()

        manager = letterboxd.RssUpdatesManager(age_minutes)
        updates = await manager.fetch_updates_from_users(users)

        if updates:
            uploads = [
                client.upload_file(picture)
                for picture in await letterboxd.create_memes(updates)
            ]
            if uploads:
                await client.send_message(
                    bot if debug else chat,
                    await manager.format_updates(updates),
                    file=await asyncio.gather(*uploads),
                    link_preview=False,
                )
            else:
                await client.send_message(
                    bot if debug else chat,
                    await manager.format_updates(updates),
                    link_preview=False,
                )

        end_time = datetime.now()
        print(f"{end_time.strftime('%H:%M:%S')} — {(end_time - start_time).seconds}s")

        await asyncio.sleep(age_minutes * 60)


with client:
    current_task = client.loop.create_task(main())
    client.run_until_disconnected()

# Taken from https://gist.github.com/YouKnow-sys/3d571bdd4857f175d91db8146ec065bf

"""
Simple HTML -> Telegram entity parser.
"""

from collections import deque
from html import escape
from html.parser import HTMLParser
from typing import Iterable, List, Tuple

from telethon.helpers import add_surrogate, del_surrogate, strip_text, within_surrogate
from telethon.tl import TLObject
from telethon.types import (
    MessageEntityBlockquote,
    MessageEntityBold,
    MessageEntityCode,
    MessageEntityCustomEmoji,
    MessageEntityEmail,
    MessageEntityItalic,
    MessageEntityMentionName,
    MessageEntityPre,
    MessageEntitySpoiler,
    MessageEntityStrike,
    MessageEntityTextUrl,
    MessageEntityUnderline,
    MessageEntityUrl,
    TypeMessageEntity,
)


class HTMLToTelegramParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.entities = []
        self._building_entities = {}
        self._open_tags = deque()
        self._open_tags_meta = deque()

    def handle_starttag(self, tag, attrs):
        self._open_tags.appendleft(tag)
        self._open_tags_meta.appendleft(None)

        attrs = dict(attrs)
        EntityType = None
        args = {}
        match tag:
            case "strong" | "b":
                EntityType = MessageEntityBold
            case "em" | "i":
                EntityType = MessageEntityItalic
            case "u":
                EntityType = MessageEntityUnderline
            case "del" | "s":
                EntityType = MessageEntityStrike
            case "blockquote":
                EntityType = MessageEntityBlockquote
                args["collapsed"] = "True"
            case "tg-spoiler":
                EntityType = MessageEntitySpoiler
            case "code":
                try:
                    # If we're in the middle of a <pre> tag, this <code> tag is
                    # probably intended for syntax highlighting.
                    #
                    # Syntax highlighting is set with
                    #     <code class='language-...'>codeblock</code>
                    # inside <pre> tags
                    pre = self._building_entities["pre"]
                    try:
                        pre.language = attrs["class"][len("language-") :]  # type: ignore
                    except KeyError:
                        pass
                except KeyError:
                    EntityType = MessageEntityCode
            case "pre":
                EntityType = MessageEntityPre
                args["language"] = ""
            case "a":
                try:
                    url = attrs["href"]
                    if not url:
                        raise KeyError
                except KeyError:
                    return
                if url.startswith("mailto:"):
                    url = url[len("mailto:") :]
                    EntityType = MessageEntityEmail
                else:
                    if self.get_starttag_text() == url:
                        EntityType = MessageEntityUrl
                    else:
                        EntityType = MessageEntityTextUrl
                        args["url"] = del_surrogate(url)
                        url = None
                self._open_tags_meta.popleft()
                self._open_tags_meta.appendleft(url)
            case "tg-emoji":
                try:
                    emoji_id = attrs["emoji-id"]
                    if not emoji_id:
                        raise ValueError
                    emoji_id = int(emoji_id)
                except (KeyError, ValueError):
                    return
                EntityType = MessageEntityCustomEmoji
                args["document_id"] = emoji_id

        if EntityType and tag not in self._building_entities:
            self._building_entities[tag] = EntityType(
                offset=len(self.text),
                # The length will be determined when closing the tag.
                length=0,
                **args,
            )

    def handle_data(self, data):
        previous_tag = self._open_tags[0] if len(self._open_tags) > 0 else ""
        if previous_tag == "a":
            url = self._open_tags_meta[0]
            if url:
                data = url

        for tag, entity in self._building_entities.items():
            entity.length += len(data)

        self.text += data

    def handle_endtag(self, tag):
        try:
            self._open_tags.popleft()
            self._open_tags_meta.popleft()
        except IndexError:
            pass
        entity = self._building_entities.pop(tag, None)
        if entity:
            self.entities.append(entity)


ENTITY_TO_FORMATTER = {
    MessageEntityBold: ("<strong>", "</strong>"),
    MessageEntityItalic: ("<em>", "</em>"),
    MessageEntityCode: ("<code>", "</code>"),
    MessageEntityUnderline: ("<u>", "</u>"),
    MessageEntityStrike: ("<del>", "</del>"),
    MessageEntityBlockquote: ("<blockquote>", "</blockquote>"),
    MessageEntitySpoiler: ("<tg-spoiler>", "</tg-spoiler>"),
    MessageEntityPre: lambda e, _: (
        "<pre>\n" "    <code class='language-{}'>\n" "        ".format(e.language),
        "{}\n" "    </code>\n" "</pre>",
    ),
    MessageEntityEmail: lambda _, t: ('<a href="mailto:{}">'.format(t), "</a>"),
    MessageEntityUrl: lambda _, t: ('<a href="{}">'.format(t), "</a>"),
    MessageEntityTextUrl: lambda e, _: ('<a href="{}">'.format(escape(e.url)), "</a>"),
    MessageEntityMentionName: lambda e, _: (
        '<a href="tg://user?id={}">'.format(e.user_id),
        "</a>",
    ),
    MessageEntityCustomEmoji: lambda e, _: (
        '<tg-emoji emoji-id="{}">'.format(e.document_id),
        "</tg-emoji>",
    ),
}


class CustomHtmlParser:
    @staticmethod
    def parse(html: str) -> Tuple[str, List[TypeMessageEntity]]:
        """
        Parses the given HTML message and returns its stripped representation
        plus a list of the MessageEntity's that were found.

        :param html: the message with HTML to be parsed.
        :return: a tuple consisting of (clean message, [message entities]).
        """
        if not html:
            return html, []

        parser = HTMLToTelegramParser()
        parser.feed(add_surrogate(html))
        text = strip_text(parser.text, parser.entities)
        parser.entities.reverse()
        parser.entities.sort(key=lambda entity: entity.offset)
        return del_surrogate(text), parser.entities

    @staticmethod
    def unparse(text: str, entities: Iterable[TypeMessageEntity]) -> str:
        """
        Performs the reverse operation to .parse(), effectively returning HTML
        given a normal text and its MessageEntity's.

        :param text: the text to be reconverted into HTML.
        :param entities: the MessageEntity's applied to the text.
        :return: a HTML representation of the combination of both inputs.
        """
        if not text:
            return text
        elif not entities:
            return escape(text)

        if isinstance(entities, TLObject):
            entities = (entities,)  # type: ignore

        text = add_surrogate(text)
        insert_at = []
        for i, entity in enumerate(entities):
            s = entity.offset
            e = entity.offset + entity.length
            delimiter = ENTITY_TO_FORMATTER.get(type(entity), None)  # type: ignore
            if delimiter:
                if callable(delimiter):
                    delimiter = delimiter(entity, text[s:e])
                insert_at.append((s, i, delimiter[0]))
                insert_at.append((e, -i, delimiter[1]))

        insert_at.sort(key=lambda t: (t[0], t[1]))
        next_escape_bound = len(text)
        while insert_at:
            # Same logic as markdown.py
            at, _, what = insert_at.pop()
            while within_surrogate(text, at):
                at += 1

            text = (
                text[:at]
                + what
                + escape(text[at:next_escape_bound])
                + text[next_escape_bound:]
            )
            next_escape_bound = at

        text = escape(text[:next_escape_bound]) + text[next_escape_bound:]

        return del_surrogate(text)

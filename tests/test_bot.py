"""Drives the real aiogram dispatcher with fake Telegram updates; Telegram, DB and Gemini are stubbed."""
import asyncio
import datetime as dt
import io
from types import SimpleNamespace

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User, Voice

from app import bot as botmod
from app import config, rag

DP = Dispatcher()  # a router can be attached only once
DP.include_router(botmod.router)
USER = User(id=111, is_bot=False, first_name="Ali")
CHAT = Chat(id=111, type="private")


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent: list = []

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        if isinstance(method, SendMessage) or type(method).__name__.startswith("Send"):
            return Message(message_id=len(self.sent), date=dt.datetime.now(), chat=CHAT, text=getattr(method, "text", None))
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def close(self):
        pass

    def texts(self) -> list[str]:
        return [m.text for m in self.sent if isinstance(m, SendMessage)]


class FakeDB:
    def __init__(self):
        self.credits, self.pending, self.quota, self.messages, self.feedback = 0, None, 0, [], []

    async def ensure_user(self, uid):
        return {"id": uid, "credits": self.credits, "pending_doc": self.pending}

    async def take_daily_quota(self, uid, limit):
        self.quota += 1
        return self.quota <= limit

    async def add_message(self, uid, role, content):
        self.messages.append((role, content))

    async def clear_history(self, uid):
        self.messages.clear()

    async def set_pending_doc(self, uid, d):
        self.pending = d

    async def save_feedback(self, uid, good):
        self.feedback.append(good)

    async def spend_credit(self, uid):
        if self.credits > 0:
            self.credits -= 1
            return True
        return False


@pytest.fixture
def env(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(botmod, "db", fake)
    DP.fsm.storage = MemoryStorage()  # FSM state (e.g. "waiting for receipt") must not leak between tests
    monkeypatch.setattr(config, "CARD_NUMBER", "9860 0000 0000 1234")
    monkeypatch.setattr(config, "FREE_DAILY_LIMIT", 3)

    async def answer(uid, text):
        return rag.Reply(f"JAVOB: {text} [1]", offer="ish beruvchiga talabnoma")

    async def transcribe(data, mime):
        return "ish haqi berilmayapti"

    monkeypatch.setattr(rag, "answer", answer)
    monkeypatch.setattr(rag, "transcribe", transcribe)
    analyzed = []

    async def analyze_file(uid, parts, caption):
        analyzed.append((len(parts), caption))
        return rag.Reply("TAHLIL")

    monkeypatch.setattr(rag, "analyze_file", analyze_file)
    monkeypatch.setattr(botmod.asyncio, "sleep", _no_sleep)
    session = FakeSession()
    bot = Bot("42:TEST", session=session)

    async def download(file, destination=None):
        return io.BytesIO(b"OggS-fake")
    monkeypatch.setattr(bot, "download", download)

    return SimpleNamespace(bot=bot, dp=DP, session=session, db=fake, analyzed=analyzed)


_ids = iter(range(1, 10_000))
_real_sleep = asyncio.sleep


async def _no_sleep(_):
    await _real_sleep(0.05)


async def send(env, text=None, **extra):
    msg = Message(message_id=next(_ids), date=dt.datetime.now(), chat=CHAT, from_user=USER, text=text, **extra)
    await env.dp.feed_update(env.bot, Update(update_id=next(_ids), message=msg))


async def click(env, data):
    msg = Message(message_id=next(_ids), date=dt.datetime.now(), chat=CHAT, from_user=USER, text="x")
    cb = CallbackQuery(id=str(next(_ids)), from_user=USER, chat_instance="c", message=msg, data=data)
    await env.dp.feed_update(env.bot, Update(update_id=next(_ids), callback_query=cb))


async def test_start_and_menu_buttons(env):
    await send(env, "/start")
    assert "Assalomu alaykum" in env.session.texts()[-1]
    await send(env, "👷 Mehnat")
    assert "Mehnat munosabatlari" in env.session.texts()[-1]
    assert env.db.messages[-1][0] == "model"  # topic remembered for the next answer


async def test_question_gets_answer_and_paid_offer(env):
    await send(env, "oylik bermayapti")
    texts = env.session.texts()
    assert texts[0].startswith("⏳") and "JAVOB: oylik bermayapti" in texts[-1]
    last = [m for m in env.session.sent if isinstance(m, SendMessage)][-1]
    assert last.reply_markup.inline_keyboard[0][0].callback_data == "draft"
    assert env.db.pending == "ish beruvchiga talabnoma"


async def test_voice_message_is_transcribed_and_answered(env):
    await send(env, voice=Voice(file_id="v", file_unique_id="u", duration=12, mime_type="audio/ogg"))
    texts = env.session.texts()
    assert any("Siz dedingiz" in t and "ish haqi berilmayapti" in t for t in texts)
    assert "JAVOB: ish haqi berilmayapti" in texts[-1]


async def test_too_long_voice_rejected(env):
    await send(env, voice=Voice(file_id="v", file_unique_id="u", duration=3600))
    assert "10 daqiqadan" in env.session.texts()[-1]


async def test_draft_without_credits_shows_payment(env):
    env.db.pending = "talabnoma"
    await click(env, "draft")
    assert "9860 0000 0000 1234" in env.session.texts()[-1]


async def test_daily_limit(env):
    for _ in range(4):
        await send(env, "savol")
    assert "limit" in env.session.texts()[-1]


async def test_admin_commands_hidden_from_users(env):
    await send(env, "/stats")
    assert "Noma'lum buyruq" in env.session.texts()[-1]


def _photo(n):
    return [PhotoSize(file_id=f"p{n}", file_unique_id=f"u{n}", width=800, height=1200, file_size=1000)]


async def test_album_pages_analyzed_together(env):
    await asyncio.gather(
        send(env, photo=_photo(1), media_group_id="album1", caption="imzolasam bo'ladimi?"),
        send(env, photo=_photo(2), media_group_id="album1"),
        send(env, photo=_photo(3), media_group_id="album1"),
    )
    assert env.analyzed == [(3, "imzolasam bo'ladimi?")]
    assert any("3 sahifa" in t for t in env.session.texts())


async def test_feedback_saved_and_buttons_removed(env):
    msg = Message(message_id=next(_ids), date=dt.datetime.now(), chat=CHAT, from_user=USER, text="javob",
                  reply_markup=botmod.InlineKeyboardMarkup(inline_keyboard=[botmod.FEEDBACK_ROW]))
    cb = CallbackQuery(id="9", from_user=USER, chat_instance="c", message=msg, data="fb:1")
    await env.dp.feed_update(env.bot, Update(update_id=next(_ids), callback_query=cb))
    assert env.db.feedback == [True]
    edits = [m for m in env.session.sent if type(m).__name__ == "EditMessageReplyMarkup"]
    assert edits and edits[-1].reply_markup is None


async def test_users_command_is_admin_only(env):
    await send(env, "/users")
    assert "Noma'lum buyruq" in env.session.texts()[-1]

import os
import re
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

MASTER_ID = os.environ.get("ASTRBOT_MASTER_ID", "")

# 命中唤醒词后，群聊接话窗口 120 秒
WAKE_WINDOW = 120

# 会话 -> 上次被主人唤醒的时间戳
_wake_window: dict[str, float] = {}

# 窗口过期后的清理阈值：超过此数量时清掉已过期的会话键，防止长期运行无限增长
_WINDOW_GC_THRESHOLD = 256


def _gc_wake_window(now: float) -> None:
    """清理已过唤醒窗口的会话键。仅在键数超过阈值时执行，开销可忽略。"""
    if len(_wake_window) <= _WINDOW_GC_THRESHOLD:
        return
    expired = [k for k, t in _wake_window.items() if now - t > WAKE_WINDOW]
    for k in expired:
        _wake_window.pop(k, None)


class MasterWakeFilter(filter.CustomFilter):
    """只认主人的唤醒闸门：群里只要主人发出的消息包含「静」，或者在连续对话窗口内，一律放行。

    - 非主人：一律不放行（别人喊「静」静不理会）
    - 主人：只要提到「静」，或者在唤醒窗口内，静必须立刻回应！
    """

    def filter(self, event: AstrMessageEvent, cfg) -> bool:
        if event.get_sender_id() != MASTER_ID:
            return False

        text = (event.message_str or "").strip()
        session = event.unified_msg_origin
        now = time.time()
        _gc_wake_window(now)

        # 只要主人提到了“静”，无论在句首、句中还是句尾，无论怎么说，静都立刻应答！
        if "静" in text:
            _wake_window[session] = now
            event.is_at_or_wake_command = True
            event.is_wake = True
            return True

        last = _wake_window.get(session, 0)
        if now - last <= WAKE_WINDOW:
            _wake_window[session] = now
            event.is_at_or_wake_command = True
            event.is_wake = True
            return True

        return False


@register(
    "astrbot_plugin_wake_static",
    "静",
    "免 @ 唤醒（仅认主人）：主人呼唤静，静必定应答",
    "2.2.0",
)
class WakeStatic(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.event_message_type(filter.EventMessageType.ALL)
    @filter.custom_filter(MasterWakeFilter)
    async def on_master_wake(self, event: AstrMessageEvent):
        logger.debug(
            f"[wake_static] 主人唤醒命中：{event.get_message_str()!r} "
            f"@ {event.unified_msg_origin}"
        )
        return

    async def terminate(self):
        _wake_window.clear()

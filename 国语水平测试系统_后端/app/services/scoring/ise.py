"""讯飞语音评测（ISE）实现 —— SCORING_MODE=ise 时启用。

协议要点（2026-09 按官方文档实测，文档：https://www.xfyun.cn/doc/Ise/IseAPI.html）：
  1. business 是**扁平**结构：没有 data_type 字段、也不要再套一层 business
     （套了会被服务端判为 10163 未知字段）；
  2. 参数帧：cmd="ssb"、data={"status": 0}，**这一帧不带音频**；
  3. 音频帧：business.cmd="auw" + aus（首帧 1 / 中间 2 / 末帧 4），
     data.status 同步为 1 / 1 / 2（末帧代表音频结束）；
  4. 音频规格 16k / 16bit / 单声道裸 PCM，每帧 1280 字节（40ms），
     整个会话不超过 5 分钟（超了报 10114 / 60114）；
  5. 返回 XML 里的 total_score 已经是百分制（0~100），不需要再 ×20 换算；
  6. 中文题型只有 read_syllable / read_word / read_sentence / read_chapter 四种；
     "命题说话"属于自由说，需要额外购买讯飞试卷定制服务，见 free_speak.py。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import select
import ssl
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Optional
from urllib.parse import quote
from xml.etree import ElementTree

from app.core.config import settings
from app.core.constants import TYPE_TOTALS
from app.core.errors import BizException
from app.services.scoring.audio import read_pcm
from app.services.scoring.base import ScoreRequest, ScoreResult

logger = logging.getLogger(__name__)

ISE_PATH = "/v2/open-ise"
AUDIO_FRAME_SIZE = 1280          # 40ms @ 16k / 16bit / 单声道
POLL_EVERY = 25                  # 每发 25 帧（约 1 秒）顺手读一次，尽早发现服务端判错

#: 题型 -> 讯飞评测类别（第四题命题说话不走这里）
ISE_CATEGORY = {1: "read_syllable", 2: "read_word", 3: "read_chapter"}

#: 结果 XML 里可能出现的题型根节点
RESULT_TAGS = ("read_syllable", "read_word", "read_sentence", "read_chapter")

#: 常见错误码 -> 给用户看的中文提示
FRIENDLY_ERRORS = {
    10114: "录音太长（评测会话超过 5 分钟），请缩短后重试",
    60114: "录音太长，建议单次评测控制在 3 分钟以内",
    10200: "上传中断（讯飞等待音频超时）",
    11200: "讯飞账号未开通该能力或授权已用尽",
    11201: "讯飞接口调用量已超出套餐限制",
    48195: "讯飞评测参数与文本不匹配（请检查题型与参考文本）",
    68676: "疑似乱读，未能正常评测",
}


class IseScoringService:
    """讯飞语音评测实现（单字 / 词语 / 短文）。"""

    def score(self, request: ScoreRequest) -> ScoreResult:
        category = ISE_CATEGORY.get(request.type)
        if category is None:
            raise BizException(f"讯飞评测不支持第 {request.type} 题", 400)

        if not (settings.ise_app_id and settings.ise_api_key and settings.ise_api_secret):
            raise BizException(
                "讯飞评测参数未配置，请在 .env 中填写 ISE_APP_ID / ISE_API_KEY / ISE_API_SECRET", 500
            )

        try:
            audio = read_pcm(request.audio_path)
        except ValueError as exc:
            raise BizException(str(exc), 400) from exc
        if len(audio) < 16000:                      # 不足 0.5 秒
            raise BizException("没有采集到有效录音（时间太短），请重新录制本题", 400)

        text = self._normalize_text(request.text)
        if not text.strip():
            raise BizException("本题缺少参考文本，无法评测", 500)

        total = TYPE_TOTALS.get(request.type, 100.0)
        xml_text = self._request_ise(category, text, audio)
        return self._parse(xml_text, request.type, total)

    # ---------- 网络交互 ----------
    def _request_ise(self, category: str, text: str, audio: bytes) -> str:
        """调用讯飞；网络抖动重试若干次，服务端业务错误直接抛出。"""
        last_error: Optional[Exception] = None
        for attempt in range(settings.ise_max_retry + 1):
            try:
                return self._talk(category, text, audio)
            except BizException:
                raise
            except Exception as exc:  # noqa: BLE001 - 连接/SSL/超时都归到这里
                last_error = exc
                logger.warning("讯飞评测第 %s 次调用失败：%r", attempt + 1, exc)
                time.sleep(0.5 * (attempt + 1))
        raise BizException(f"讯飞评测连接失败：{last_error}", 500)

    def _talk(self, category: str, text: str, audio: bytes) -> str:
        try:
            import websocket  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise BizException("缺少依赖 websocket-client，请执行 pip install websocket-client", 500) from exc

        ws = websocket.create_connection(
            _sign_url(), timeout=10, sslopt={"cert_reqs": ssl.CERT_NONE}
        )
        parts: list[str] = []
        try:
            ws.settimeout(settings.ise_timeout)
            ws.send(json.dumps(_ssb_frame(category, text)))

            chunks = [audio[i:i + AUDIO_FRAME_SIZE] for i in range(0, len(audio), AUDIO_FRAME_SIZE)]
            ended = False
            if len(chunks) == 1:                     # 极短录音：首帧之后补一个空的结束帧
                ws.send(json.dumps(_auw_frame(chunks[0], 1, 1)))
                ws.send(json.dumps(_auw_frame(b"", 4, 2)))
            else:
                for index, chunk in enumerate(chunks):
                    # 边发边读：讯飞判参数/音频不合格时会立刻回错误码并断开，
                    # 只发不收的话只能看到 WinError 10053，看不到真正的报错。
                    if index % POLL_EVERY == 0 and _poll(ws, parts):
                        ended = True
                        break
                    last = index == len(chunks) - 1
                    aus = 4 if last else (1 if index == 0 else 2)
                    try:
                        ws.send(json.dumps(_auw_frame(chunk, aus, 2 if last else 1)))
                    except Exception as exc:  # noqa: BLE001
                        _poll(ws, parts, force=True)   # 先把服务端回的错误读出来再抛
                        raise BizException(f"上传音频时连接被断开：{exc}", 500) from exc
                    if not last:
                        time.sleep(settings.ise_send_interval)

            while not ended:
                ended = _poll(ws, parts, force=True)
        finally:
            try:
                ws.close()
            except Exception:  # noqa: BLE001 - 关闭失败不影响结果
                pass

        xml_text = "".join(parts)
        if not xml_text:
            raise BizException("讯飞评测没有返回结果", 500)
        return xml_text

    # ---------- 结果解析 ----------
    @staticmethod
    def _normalize_text(text: str) -> str:
        """讯飞要求文本带 UTF-8 BOM 前缀 \\uFEFF。"""
        cleaned = (text or "").strip()
        return "\ufeff" + cleaned if cleaned else ""

    @staticmethod
    def _parse(xml_text: str, type_no: int, total: float) -> ScoreResult:
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            raise BizException("讯飞评测结果解析失败", 500) from exc

        node = _result_node(root)
        if node.get("is_rejected") == "true":
            raise BizException("没有识别到有效朗读（疑似乱读或环境噪声），请重新录制本题", 400)
        except_info = (node.get("except_info") or "0").strip()
        if except_info not in ("0", ""):
            raise BizException(
                f"没有检测到有效朗读语音（讯飞 except_info={except_info}）："
                "请确认麦克风正常、环境安静，再重新录制本题",
                400,
            )

        percent = _float_of(node, "total_score")
        if percent is None:
            raise BizException("讯飞评测结果中缺少总分", 500)
        percent = max(0.0, min(100.0, percent))
        score = round(total * percent / 100.0, 1)

        phone_score = _float_of(node, "phone_score")
        tone_score = _float_of(node, "tone_score")
        detail = _detail_from_phones(root, phone_score or percent, tone_score or percent)
        detail["engine"] = "xfyun_ise"
        if phone_score is not None:
            detail["phone_score"] = round(phone_score, 1)
        if tone_score is not None:
            detail["tone_score"] = round(tone_score, 1)
        for key in ("fluency_score", "integrity_score", "accuracy_score", "emotion_score"):
            value = _float_of(node, key)
            if value:
                detail[key] = round(value, 1)

        logger.info("【讯飞评测】题%s 百分制 %.1f -> %.1f/%s", type_no, percent, score, total)
        return ScoreResult(type=type_no, score=score, total=total, detail=detail)


# ---------- 报文构造 ----------
def _sign_url() -> str:
    """按讯飞要求生成带鉴权参数的 WebSocket URL（HMAC-SHA256）。"""
    host = (settings.ise_host or "ise-api.xfyun.cn").strip()
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    origin = f"host: {host}\ndate: {date}\nGET {ISE_PATH} HTTP/1.1"
    signature = hmac.new(
        settings.ise_api_secret.encode("utf-8"), origin.encode("utf-8"), hashlib.sha256
    ).digest()
    authorization_origin = (
        f'api_key="{settings.ise_api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{base64.b64encode(signature).decode()}"'
    )
    params = {
        "authorization": base64.b64encode(authorization_origin.encode("utf-8")).decode(),
        "date": date,
        "host": host,
    }
    query = "&".join(f"{key}={quote(str(value), safe='')}" for key, value in params.items())
    return f"wss://{host}{ISE_PATH}?{query}"


def _ssb_frame(category: str, text: str) -> dict:
    """参数帧（不带音频）。"""
    return {
        "common": {"app_id": settings.ise_app_id},
        "business": {
            "sub": "ise",
            "ent": "cn_vip",
            "category": category,
            "cmd": "ssb",
            "text": text,
            "tte": "utf-8",
            "ttp_skip": True,
            "auf": "audio/L16;rate=16000",
            "aue": "raw",
            "rstcd": "utf8",
            "rst": "entirety",              # entirety + ise_unite=1 = 百分制推荐参数
            "ise_unite": "1",
            "extra_ability": "multi_dimension;syll_phone_err_msg",
            "group": "adult",
            "check_type": "common",
        },
        "data": {"status": 0},
    }


def _auw_frame(chunk: bytes, aus: int, status: int) -> dict:
    """音频帧：aus 区分首/中/末帧，status 区分数据状态。"""
    return {
        "business": {"cmd": "auw", "aus": aus},
        "data": {"status": status, "data": base64.b64encode(chunk).decode()},
    }


def _poll(ws, parts: list, force: bool = False) -> bool:
    """读一条服务端消息；返回 True 表示评测已结束（status=2）。"""
    if not force:
        try:
            if not (select.select([ws.sock], [], [], 0)[0] or ws.sock.pending()):
                return False
        except Exception:  # noqa: BLE001 - 拿不到 socket 状态就直接尝试读
            pass
    message = json.loads(ws.recv())
    if message.get("code") != 0:
        raise BizException(_error_text(message.get("code"), message.get("message")), 500)
    payload = message.get("data") or {}
    if payload.get("data"):
        parts.append(base64.b64decode(payload["data"]).decode("utf-8"))
    return payload.get("status") == 2

def _error_text(code, message) -> str:
    friendly = FRIENDLY_ERRORS.get(code)
    detail = f"（讯飞返回 {code}：{message}）"
    return (friendly + detail) if friendly else f"讯飞评测失败{detail}"


# ---------- XML 解析工具 ----------
def _result_node(root) -> ElementTree.Element:
    """取最外层带 total_score 的题型节点（文档顺序即由外到内）。"""
    for node in root.iter():
        if node.tag in RESULT_TAGS and node.get("total_score") is not None:
            return node
    raise BizException("讯飞评测结果结构异常（未找到总分节点）", 500)


def _float_of(node, attr: str) -> Optional[float]:
    raw = node.get(attr)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _detail_from_phones(root, phone_score: float, tone_score: float) -> dict:
    """按官方字段语义拆出声母 / 韵母 / 声调三个正确率。

    is_yun=0（声母）：perr_msg 0=正确 / 1=错误
    is_yun=1（韵母）：perr_msg 0=韵母和声调都对 / 1=韵母错 / 2=声调错 / 3=都错
    没有 is_yun 属性的节点是 sil / silv / fil（静音、噪声），直接跳过。
    """
    initials: list[bool] = []
    finals: list[bool] = []
    tones: list[bool] = []
    for node in root.iter("phone"):
        is_yun = node.get("is_yun")
        if is_yun is None:
            continue
        try:
            code = int(node.get("perr_msg", "-1"))
        except (TypeError, ValueError):
            code = -1
        if is_yun == "0":
            initials.append(code == 0)
        else:
            finals.append(code in (0, 2))
            tones.append(code in (0, 1))
    return {
        "shengmu": _percent(initials, phone_score),
        "yunmu": _percent(finals, phone_score),
        "shengdiao": _percent(tones, tone_score),
    }


def _percent(flags: list[bool], fallback: float) -> int:
    """没有音素样本时退回讯飞给的整句分，避免出现 0%。"""
    if not flags:
        return int(round(max(0.0, min(100.0, fallback))))
    return int(round(sum(1 for ok in flags if ok) * 100.0 / len(flags)))
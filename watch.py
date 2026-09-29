#!/usr/bin/env python3
"""Внешний сторож для бота. Запускается GitHub Actions каждые 10 минут.

Стучится на сервер (/api/health/watch через публичный адрес). Если сервер не
отвечает или что-то красное — пишет владельцу в Telegram и VK НАПРЯМУЮ через
их API (серверы GitHub за границей, Telegram доступен). Поэтому тревога дойдёт,
даже если сам сервер мёртв.

Без спама: тревога только при смене состояния (или напоминание раз в 6 ч, пока
не починено), и только если плохо 2 проверки подряд — разовые сбои сети не будят.
Все адреса и токены — в Secrets репозитория, в код и логи не попадают.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

E = os.environ.get
WATCH_URL = E("WATCH_URL", "")
TG_TOKEN, TG_CHAT = E("TG_TOKEN", ""), E("TG_CHAT", "")
VK_TOKEN, VK_PEER = E("VK_TOKEN", ""), E("VK_PEER", "")
STATE = E("STATE_FILE", "state/state.json")
TG_API = E("TG_API", "https://api.telegram.org")
VK_API = E("VK_API", "https://api.vk.com/method")
REMIND_EVERY = int(E("REMIND_EVERY", str(6 * 3600)))
CONFIRM_RUNS = int(E("CONFIRM_RUNS", "2"))
RETRY_GAP = float(E("RETRY_GAP", "20"))


def http(url, data=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "bot-watchdog/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def notify(text):
    sent = []
    if TG_TOKEN and TG_CHAT:
        try:
            http(f"{TG_API}/bot{TG_TOKEN}/sendMessage", urllib.parse.urlencode(
                {"chat_id": TG_CHAT, "text": text, "disable_web_page_preview": "true"}).encode())
            sent.append("TG")
        except Exception as e:
            print("TG: не отправлено:", type(e).__name__)
    if VK_TOKEN and VK_PEER:
        try:
            _, b = http(f"{VK_API}/messages.send", urllib.parse.urlencode(
                {"peer_id": VK_PEER, "message": text, "random_id": random.randint(1, 2**31 - 1),
                 "access_token": VK_TOKEN, "v": "5.199"}).encode())
            if b"error" in b[:20]:
                print("VK: ошибка API:", json.loads(b).get("error", {}).get("error_msg", "?"))
            else:
                sent.append("VK")
        except Exception as e:
            print("VK: не отправлено:", type(e).__name__)
    print("уведомление ->", ", ".join(sent) or "НИКУДА (проверь секреты)")
    return sent


def probe():
    """(status, reasons): ok | fail | down. Две попытки — Funnel иногда моргает."""
    last = ""
    for attempt in range(2):
        try:
            st, body = http(WATCH_URL, timeout=30)
            d = json.loads(body)
            if d.get("ok"):
                return "ok", []
            return "fail", [str(x) for x in d.get("fails", [])] or ["сервер сообщил о проблеме"]
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}" + (" — неверный ключ или dashboard без эндпоинта" if e.code == 404 else "")
        except Exception as e:
            last = type(e).__name__ + (f": {e.reason}" if hasattr(e, "reason") else "")
        if attempt == 0:
            time.sleep(RETRY_GAP)
    return "down", [f"сервер не отвечает ({last})"]


def main():
    if not WATCH_URL:
        print("нет секрета WATCH_URL")
        return 1
    try:
        st = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        st = {}
    now = int(time.time())

    if E("TEST_ALERT") == "1":
        notify("🧪 Тест внешнего сторожа: если ты это читаешь — тревоги дойдут, даже если сервер умрёт.")

    status, reasons = probe()
    key = status if status != "fail" else "fail:" + "|".join(sorted(reasons))
    st["bad_runs"] = 0 if status == "ok" else st.get("bad_runs", 0) + 1
    print(f"статус: {status}, подряд плохих: {st['bad_runs']}")  # без деталей: логи публичные

    if status == "ok":
        if st.get("alerted"):
            down_min = (now - st.get("since", now)) // 60
            notify(f"✅ Бот восстановился (проблема длилась ~{down_min} мин).")
        st.update(alerted=False, last_key="ok", since=None)
    elif st["bad_runs"] >= CONFIRM_RUNS:
        changed = key != st.get("last_key")
        stale = now - st.get("last_alert", 0) >= REMIND_EVERY
        if not st.get("alerted") or changed or stale:
            head = "🚨 Сервер бота недоступен" if status == "down" else "🚨 Проблема с ботом"
            if st.get("alerted") and not changed:
                head += " — всё ещё не починено"
            notify(head + ":\n• " + "\n• ".join(reasons[:8]) +
                   "\n\n(внешний сторож GitHub, проверка раз в ~10 мин)")
            st.update(alerted=True, last_alert=now, last_key=key)
        if not st.get("since"):
            st["since"] = now - 600 * (st["bad_runs"] - 1)
    os.makedirs(os.path.dirname(STATE) or ".", exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

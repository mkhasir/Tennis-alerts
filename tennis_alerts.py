"""
Уведомления в Telegram, когда выбранный теннисист выигрывает или проигрывает сет.
Данные: api-tennis.com (метод get_livescore). Запускается один раз за вызов;
состояние (какие сеты уже отправлены) хранится в state.json.
"""
import json
import os
import urllib.parse
import urllib.request

# Фамилия латиницей (как в API) -> как показывать в сообщении
PLAYERS = {
    "medvedev": "Медведев",
    "khachanov": "Хачанов",
    "rublev": "Рублёв",
    "safiullin": "Сафиуллин",
    "sharipov": "Шарипов",
    "simakin": "Симакин",
    "kachmazov": "Качмазов",
    "lagutin": "Лагутин",
    "belozertsev": "Белозерцев",
}

API_KEY = os.environ["TENNIS_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = "state.json"


def http_get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def send_telegram(text):
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text}).encode()
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    urllib.request.urlopen(url, data=data, timeout=30)


def find_player(name):
    """Возвращает русское имя, если в строке игрока есть фамилия из списка."""
    low = (name or "").lower()
    for key, ru in PLAYERS.items():
        if key in low:
            return ru
    return None


def games(value):
    """'7' или '7.5' (с тай-брейком) -> 7"""
    try:
        return int(str(value).split(".")[0])
    except ValueError:
        return None


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    # храним только последние 300 матчей, чтобы файл не рос бесконечно
    items = list(state.items())[-300:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(items), f, ensure_ascii=False, indent=1)


def main():
    url = ("https://api.api-tennis.com/tennis/?method=get_livescore"
           f"&APIkey={urllib.parse.quote(API_KEY)}&timezone=Australia/Sydney")
    data = http_get_json(url)
    matches = data.get("result") or []

    state = load_state()
    changed = False

    for m in matches:
        if "doubles" in (m.get("event_type_type") or "").lower():
            continue  # только одиночки

        p1, p2 = m.get("event_first_player"), m.get("event_second_player")
        ru1, ru2 = find_player(p1), find_player(p2)
        if not ru1 and not ru2:
            continue

        scores = sorted(m.get("scores") or [], key=lambda s: int(s.get("score_set") or 0))
        finished = (m.get("event_status") or "").lower() == "finished"
        # Сет завершён, если после него начался следующий или матч окончен
        done_sets = scores if finished else scores[:-1]

        key = str(m.get("event_key"))
        already = state.get(key, 0)

        for i in range(already, len(done_sets)):
            s = done_sets[i]
            g1, g2 = games(s.get("score_first")), games(s.get("score_second"))
            if g1 is None or g2 is None or g1 == g2:
                continue
            # счёт по сетам после этого сета
            w1 = sum(1 for x in done_sets[: i + 1] if (games(x["score_first"]) or 0) > (games(x["score_second"]) or 0))
            w2 = (i + 1) - w1
            tour = m.get("tournament_name") or ""
            match_over = finished and i == len(done_sets) - 1

            # отправляем от лица каждого «нашего» игрока в матче
            for ru, mine, opp, my_g, opp_g, my_sets, opp_sets in (
                (ru1, p1, p2, g1, g2, w1, w2),
                (ru2, p2, p1, g2, g1, w2, w1),
            ):
                if not ru:
                    continue
                won = my_g > opp_g
                icon = "✅" if won else "❌"
                verb = "выиграл" if won else "проиграл"
                text = (f"{icon} {ru} {verb} {i + 1}-й сет {my_g}:{opp_g}\n"
                        f"Соперник: {opp}\n"
                        f"Счёт по сетам: {my_sets}:{opp_sets}\n"
                        f"{tour}")
                if match_over:
                    text += "\n🏁 Матч окончен: " + ("победа" if my_sets > opp_sets else "поражение")
                send_telegram(text)

        if len(done_sets) != already:
            state[key] = len(done_sets)
            changed = True

    if changed:
        save_state(state)
    print(f"Проверено матчей: {len(matches)}, изменения: {changed}")


if __name__ == "__main__":
    main()

"""
比赛日 Push 生成器。

输入来自两路信源：
- 聚合数据 API 的官方赛程/球队信息
- X Sports Trending 过滤后的社媒热点
"""
from __future__ import annotations

import json
from typing import Any

from processors.content_generator import ContentGenerator


LANGUAGE_CODES = ["EN", "ZH", "ES", "MS", "FIL", "PT-PT", "PT-BR"]


class MatchdayPushGenerator:
    """一次 LLM 调用生成 7 种语言的比赛日推送内容。"""

    def __init__(self, mock: bool = False):
        self.mock = mock
        self.generator = ContentGenerator()

    def generate(self, match: dict, trending_data: dict | None, opportunity: dict | None = None) -> dict:
        if self.mock:
            return self._mock_content(match, trending_data, opportunity or {})

        prompt = self._build_prompt(match, trending_data or {}, opportunity or {})
        response = self.generator._call_llm(prompt, system_role="matchday_push_generator")
        payload = self._parse_json(response)
        return self._normalize_payload(payload, match, opportunity or {})

    def _build_prompt(self, match: dict, trending_data: dict, opportunity: dict) -> str:
        home = match.get("team_home", {})
        away = match.get("team_away", {})
        compact_match = {
            "fixture_id": match.get("fixture_id"),
            "date": match.get("date"),
            "stage": match.get("stage"),
            "group": match.get("group"),
            "status": match.get("status"),
            "match_des": match.get("match_des"),
            "home": {
                "name": home.get("name"),
                "code": home.get("code"),
                "score": home.get("score"),
            },
            "away": {
                "name": away.get("name"),
                "code": away.get("code"),
                "score": away.get("score"),
            },
        }
        compact_trending = {
            "topics": trending_data.get("topics", [])[:8],
            "hashtags": trending_data.get("hashtags", [])[:12],
            "raw_items": [
                {
                    "author": item.get("author", ""),
                    "content": item.get("content", "")[:260],
                    "likes": item.get("likes", 0),
                    "retweets": item.get("retweets", 0),
                    "views": item.get("views", 0),
                }
                for item in trending_data.get("raw_items", [])[:12]
            ],
        }
        compact_opportunity = {
            "type": opportunity.get("type", "matchday"),
            "title": opportunity.get("title", ""),
            "description": opportunity.get("description", ""),
            "scenario_hint": opportunity.get("scenario_hint", ""),
            "emotion_hint": opportunity.get("emotion_hint", []),
            "source": opportunity.get("source", ""),
            "related_topic": opportunity.get("related_topic", ""),
            "priority": opportunity.get("priority", "normal"),
        }

        return f"""You are Vanso's World Cup matchday push editor.
Use the official match data and X Sports trending signals to create one push notification for an AI music generation app.

## Official Match Data
```json
{json.dumps(compact_match, ensure_ascii=False, indent=2)}
```

## X Sports Trending Signals
```json
{json.dumps(compact_trending, ensure_ascii=False, indent=2)}
```

## Push Trigger / Opportunity
```json
{json.dumps(compact_opportunity, ensure_ascii=False, indent=2)}
```

## Task
Generate exactly one push content package for this trigger in 7 languages:
EN, ZH, ES, MS, FIL, PT-PT, PT-BR.

Each language item must include:
- title: short push title, energetic, fan-native, and written like a real fan would tap it out
- body: push body with a clear call to generate a song in Vanso, but never stiff or corporate
- tags: 5-8 hashtags, including #VansoWorldCup26 and #MyAnthem2026 where natural
- emotion_tags: 2-4 emotion labels in that language or simple English if better

## Voice Rules
- Make title/body feel social-native: group-chat energy, meme-aware, a little punchy.
- Avoid stiff phrases like "Turn this football moment into..." unless the wording is unusually fresh.
- Do not sound like a press release, system notification, campaign slogan, or translated template.
- Use simple, alive wording: surprise, teasing, fan tension, "we are so back" energy when appropriate.
- Keep it safe and non-toxic: no insults, slurs, harassment, or unsupported claims.
- Localize the vibe per language; do not mechanically translate the English line.

Use the push trigger as the main angle. Use X signals only as cultural/emotional calibration. Do not copy full tweets.
Avoid profanity, slurs, harassment, or claims that are not supported by the official match data.

Return ONLY valid JSON in this exact shape:
```json
{{
  "scenario": "社交派对|主场狂热|情怀致敬|短视频二创|玩梗群嘲|遗憾怀念",
  "scenario_reason": "short reason",
  "confidence": 0.0,
  "applicable_object": "team/player/topic this targets",
  "languages": {{
    "EN": {{"title": "", "body": "", "tags": "", "emotion_tags": []}},
    "ZH": {{"title": "", "body": "", "tags": "", "emotion_tags": []}},
    "ES": {{"title": "", "body": "", "tags": "", "emotion_tags": []}},
    "MS": {{"title": "", "body": "", "tags": "", "emotion_tags": []}},
    "FIL": {{"title": "", "body": "", "tags": "", "emotion_tags": []}},
    "PT-PT": {{"title": "", "body": "", "tags": "", "emotion_tags": []}},
    "PT-BR": {{"title": "", "body": "", "tags": "", "emotion_tags": []}}
  }}
}}
```"""

    def _parse_json(self, response: str) -> dict:
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            if "```json" in response:
                return json.loads(response.split("```json", 1)[1].split("```", 1)[0].strip())
            if "```" in response:
                return json.loads(response.split("```", 1)[1].split("```", 1)[0].strip())
            raise

    def _normalize_payload(self, payload: dict, match: dict, opportunity: dict) -> dict:
        languages = payload.get("languages", {})
        en = self._normalize_language(languages.get("EN", {}), "EN", match)
        translations = {
            code: self._normalize_language(languages.get(code, {}), code, match)
            for code in LANGUAGE_CODES
            if code != "EN"
        }
        emotion_tags = en.get("emotion_tags", [])
        return {
            "scenario": payload.get("scenario") or "社交派对",
            "scenario_reason": payload.get("scenario_reason") or opportunity.get("description") or "比赛日官方赛程 + X Sports 热点",
            "confidence": float(payload.get("confidence") or 0.75),
            "trigger": opportunity,
            "en": {
                "push_title": en["push_title"],
                "push_description": en["push_description"],
                "hashtags": en["hashtags"],
                "emotion_tags": emotion_tags,
                "applicable_object": payload.get("applicable_object", ""),
                "aigc_prompt": {},
            },
            "translations": translations,
        }

    def _normalize_language(self, item: dict, code: str, match: dict) -> dict:
        fallback = self._fallback_text(match, code)
        title = item.get("title") or item.get("push_title") or fallback["title"]
        body = item.get("body") or item.get("push_description") or fallback["body"]
        tags = item.get("tags") or item.get("hashtags") or fallback["tags"]
        emotions = item.get("emotion_tags") or fallback["emotion_tags"]
        if isinstance(emotions, str):
            emotions = [part.strip() for part in emotions.split(",") if part.strip()]
        return {
            "push_title": title,
            "push_description": body,
            "hashtags": tags,
            "emotion_tags": emotions,
            "aigc_prompt": item.get("aigc_prompt", {}),
        }

    def _mock_content(self, match: dict, trending_data: dict | None, opportunity: dict) -> dict:
        payload = {
            "scenario": opportunity.get("scenario_hint") or "社交派对",
            "scenario_reason": opportunity.get("description") or "mock: 官方赛程 + X Sports 热点合并",
            "confidence": 0.88,
            "applicable_object": opportunity.get("title") or self._match_display(match),
            "languages": {
                code: self._fallback_text(match, code, opportunity)
                for code in LANGUAGE_CODES
            },
        }
        return self._normalize_payload(payload, match, opportunity)

    def _fallback_text(self, match: dict, code: str, opportunity: dict | None = None) -> dict[str, Any]:
        display = self._match_display(match)
        opportunity = opportunity or {}
        angle = opportunity.get("title") or "matchday"
        localized_angle = self._localized_angle(angle, code)
        templates = {
            "EN": {
                "title": f"{display}: {localized_angle}",
                "body": "The timeline is already biting. Make the Vanso anthem before it moves on.",
                "emotion_tags": opportunity.get("emotion_hint") or ["hype", "matchday", "party"],
            },
            "ZH": {
                "title": f"{display} {localized_angle}",
                "body": f"{localized_angle}，这波已经有点上头了，趁热做首 Vanso 战歌。",
                "emotion_tags": opportunity.get("emotion_hint") or ["热血", "赛前", "派对"],
            },
            "ES": {
                "title": f"{display}: {localized_angle}",
                "body": f"{localized_angle} ya está sonando fuerte. Hazlo himno en Vanso antes de que cambie el timeline.",
                "emotion_tags": opportunity.get("emotion_hint") or ["pasión", "previa", "fiesta"],
            },
            "MS": {
                "title": f"{display}: {localized_angle}",
                "body": f"{localized_angle} tengah naik. Buat anthem Vanso sebelum timeline move on.",
                "emotion_tags": opportunity.get("emotion_hint") or ["hype", "matchday", "lepak"],
            },
            "FIL": {
                "title": f"{display}: {localized_angle}",
                "body": f"{localized_angle} is already popping. Gawin nang Vanso anthem habang mainit pa.",
                "emotion_tags": opportunity.get("emotion_hint") or ["hype", "matchday", "solid"],
            },
            "PT-PT": {
                "title": f"{display}: {localized_angle}",
                "body": f"{localized_angle} já está a puxar pela bancada. Faz disso um hino no Vanso.",
                "emotion_tags": opportunity.get("emotion_hint") or ["emoção", "jogo", "festa"],
            },
            "PT-BR": {
                "title": f"{display}: {localized_angle}",
                "body": f"{localized_angle} já pegou fogo. Faz virar hino no Vanso antes que o feed passe.",
                "emotion_tags": opportunity.get("emotion_hint") or ["vibração", "copa", "festa"],
            },
        }
        item = templates.get(code, templates["EN"])
        item["tags"] = "#VansoWorldCup26 #MyAnthem2026 #WorldCup2026 #Matchday #AIMusic"
        return item

    def _localized_angle(self, angle: str, code: str) -> str:
        labels = {
            "matchday warmup": {
                "EN": "warmup getting loud",
                "ZH": "赛前味儿来了",
                "ES": "la previa ya pica",
                "MS": "pre-match makin panas",
                "FIL": "pre-game ang ingay na",
                "PT-PT": "a antevisão já ferve",
                "PT-BR": "pré-jogo já pegou",
            },
            "fan heat check": {
                "EN": "timeline heating up",
                "ZH": "球迷已经聊炸了",
                "ES": "el timeline está ardiendo",
                "MS": "timeline tengah panas",
                "FIL": "timeline umiingay na",
                "PT-PT": "o feed está a ferver",
                "PT-BR": "a timeline ferveu",
            },
            "fan banter": {
                "EN": "banter flying already",
                "ZH": "开麦互呛开始了",
                "ES": "ya vuelan las bromas",
                "MS": "banter dah mula",
                "FIL": "asaran mode on",
                "PT-PT": "a picardia já começou",
                "PT-BR": "a resenha começou",
            },
            "short-video bait": {
                "EN": "edit bait alert",
                "ZH": "二创素材来了",
                "ES": "material de edit servido",
                "MS": "bahan edit dah sampai",
                "FIL": "edit material na ito",
                "PT-PT": "material para edits",
                "PT-BR": "material de edit na mão",
            },
            "VAR outrage": {
                "EN": "VAR takes incoming",
                "ZH": "VAR 话题要炸",
                "ES": "se viene debate VAR",
                "MS": "VAR takes incoming",
                "FIL": "VAR takes incoming",
                "PT-PT": "vem debate do VAR",
                "PT-BR": "vem treta de VAR",
            },
            "legacy feels": {
                "EN": "legacy talk is back",
                "ZH": "传奇滤镜又开了",
                "ES": "vuelve el modo leyenda",
                "MS": "cerita legend kembali",
                "FIL": "legacy talk is back",
                "PT-PT": "modo legado voltou",
                "PT-BR": "papo de legado voltou",
            },
        }
        return labels.get(angle, {}).get(code, angle)

    def _match_display(self, match: dict) -> str:
        home = match.get("team_home", {})
        away = match.get("team_away", {})
        left = home.get("code") or home.get("name") or "TBD"
        right = away.get("code") or away.get("name") or "TBD"
        return f"{left} vs {right}"

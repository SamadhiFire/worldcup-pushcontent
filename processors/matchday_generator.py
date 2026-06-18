"""
比赛日 Push 生成器。

输入来自两路信源：
- 聚合数据 API 的官方赛程/球队信息
- X Sports Trending 过滤后的社媒热点
"""
from __future__ import annotations

import json
from typing import Any

from processors.content_generator import ContentGenerator, SCENARIO_STYLE_MAP


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
            "hook": opportunity.get("hook", ""),
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
- Use the hook in the trigger as the center of gravity. Write from the actual fan angle, not from a generic category label.
- Avoid stiff phrases like "Turn this football moment into..." unless the wording is unusually fresh.
- Do not sound like a press release, system notification, campaign slogan, or translated template.
- Use simple, alive wording: surprise, teasing, fan tension, "we are so back" energy when appropriate.
- Keep it safe and non-toxic: no insults, slurs, harassment, or unsupported claims.
- Localize the vibe per language; do not mechanically translate the English line.

## Style Anchors
Good:
- "Brazil dance edits are taking over. Make yours louder."
- "This is already a group chat war. Drop the anthem now."
- "The watch-party side picking has started. Score your version first."

Avoid:
- "Generate a song for this exciting football moment now."
- "This match is trending on social media. Create content with Vanso."
- "Stay tuned and make an anthem before the trend ends."

Use the push trigger as the main angle. Use X signals only as cultural/emotional calibration. Do not copy full tweets.
Avoid profanity, slurs, harassment, or claims that are not supported by the official match data.

Use this JSON schema and return JSON only:
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
        en_aigc_prompt = en.get("aigc_prompt") or self._build_en_aigc_prompt(
            match=match,
            opportunity=opportunity,
            scenario=payload.get("scenario") or opportunity.get("scenario_hint") or "社交派对",
            en_title=en["push_title"],
            en_body=en["push_description"],
            en_hashtags=en["hashtags"],
        )
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
                "aigc_prompt": en_aigc_prompt,
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
        angle = opportunity.get("hook") or opportunity.get("title") or "matchday"
        localized_angle = self._localized_angle(angle, code)
        variant = self._pick_variant(f"{display}|{angle}|{code}", 3)
        title_variants = {
            "EN": [
                f"{display}: {localized_angle}",
                f"{localized_angle.capitalize()} for {display}",
                f"{display} and the feed is moving",
            ],
            "ZH": [
                f"{display} {localized_angle}",
                f"{localized_angle}，{display} 先热起来了",
                f"{display} 这场已经开始有话题了",
            ],
            "ES": [
                f"{display}: {localized_angle}",
                f"{localized_angle.capitalize()} con {display}",
                f"{display} ya mueve el timeline",
            ],
            "MS": [
                f"{display}: {localized_angle}",
                f"{localized_angle.capitalize()} untuk {display}",
                f"{display} dah mula panas",
            ],
            "FIL": [
                f"{display}: {localized_angle}",
                f"{localized_angle.capitalize()} sa {display}",
                f"{display} umiingay na agad",
            ],
            "PT-PT": [
                f"{display}: {localized_angle}",
                f"{localized_angle.capitalize()} em {display}",
                f"{display} já mexe com o feed",
            ],
            "PT-BR": [
                f"{display}: {localized_angle}",
                f"{localized_angle.capitalize()} em {display}",
                f"{display} já virou assunto cedo",
            ],
        }
        body_variants = {
            "EN": [
                "The group chat is already moving. Make the Vanso anthem before someone else claims the moment.",
                "This one already has feed energy. Turn it into a Vanso anthem while it is still hot.",
                "People are already picking sides. Drop the Vanso anthem before the timeline flips again.",
            ],
            "ZH": [
                f"{localized_angle}，群聊已经开始刷屏了，趁热做首 Vanso 战歌。",
                f"{localized_angle}，这波话题感已经起来了，先把 Vanso 战歌做出来。",
                f"{localized_angle}，大家已经开始站队了，快把这口气写成 Vanso 战歌。",
            ],
            "ES": [
                f"{localized_angle}, el grupo ya está encendido. Haz tu himno en Vanso antes de que cambie el mood.",
                f"{localized_angle}, esto ya tiene energía de feed. Vuélvelo himno en Vanso mientras sigue caliente.",
                f"{localized_angle}, la gente ya está tomando partido. Saca el himno en Vanso ya.",
            ],
            "MS": [
                f"{localized_angle}, group chat dah bising. Buat anthem Vanso sebelum mood bertukar.",
                f"{localized_angle}, feed memang tengah hidup. Tukar jadi anthem Vanso masa masih panas.",
                f"{localized_angle}, orang dah mula pilih side. Lepaskan anthem Vanso sekarang.",
            ],
            "FIL": [
                f"{localized_angle}, maingay na ang group chat. Gawin na itong Vanso anthem habang mainit pa.",
                f"{localized_angle}, may laman na agad ang feed. I-Vanso anthem mo na bago humupa.",
                f"{localized_angle}, may kampihan na agad. Ilabas mo na ang Vanso anthem ngayon.",
            ],
            "PT-PT": [
                f"{localized_angle}, o grupo já está aceso. Faz disto um hino no Vanso antes de mudar o tom.",
                f"{localized_angle}, isto já tem energia de feed. Puxa por um hino no Vanso enquanto ferve.",
                f"{localized_angle}, já há gente a escolher lado. Lança o hino no Vanso agora.",
            ],
            "PT-BR": [
                f"{localized_angle}, o grupo já tá daquele jeito. Faz virar hino no Vanso antes da conversa mudar.",
                f"{localized_angle}, isso já tem cara de feed ligado. Puxa o hino no Vanso enquanto tá quente.",
                f"{localized_angle}, a galera já começou a escolher lado. Solta o hino no Vanso agora.",
            ],
        }
        templates = {
            "EN": {
                "title": title_variants["EN"][variant],
                "body": body_variants["EN"][variant],
                "emotion_tags": opportunity.get("emotion_hint") or ["hype", "matchday", "party"],
            },
            "ZH": {
                "title": title_variants["ZH"][variant],
                "body": body_variants["ZH"][variant],
                "emotion_tags": opportunity.get("emotion_hint") or ["热血", "赛前", "派对"],
            },
            "ES": {
                "title": title_variants["ES"][variant],
                "body": body_variants["ES"][variant],
                "emotion_tags": opportunity.get("emotion_hint") or ["pasión", "previa", "fiesta"],
            },
            "MS": {
                "title": title_variants["MS"][variant],
                "body": body_variants["MS"][variant],
                "emotion_tags": opportunity.get("emotion_hint") or ["hype", "matchday", "lepak"],
            },
            "FIL": {
                "title": title_variants["FIL"][variant],
                "body": body_variants["FIL"][variant],
                "emotion_tags": opportunity.get("emotion_hint") or ["hype", "matchday", "solid"],
            },
            "PT-PT": {
                "title": title_variants["PT-PT"][variant],
                "body": body_variants["PT-PT"][variant],
                "emotion_tags": opportunity.get("emotion_hint") or ["emoção", "jogo", "festa"],
            },
            "PT-BR": {
                "title": title_variants["PT-BR"][variant],
                "body": body_variants["PT-BR"][variant],
                "emotion_tags": opportunity.get("emotion_hint") or ["vibração", "copa", "festa"],
            },
        }
        item = templates.get(code, templates["EN"])
        item["tags"] = "#VansoWorldCup26 #MyAnthem2026 #WorldCup2026 #Matchday #AIMusic"
        return item

    def _build_en_aigc_prompt(
        self,
        match: dict,
        opportunity: dict,
        scenario: str,
        en_title: str,
        en_body: str,
        en_hashtags: str,
    ) -> dict[str, Any]:
        style = SCENARIO_STYLE_MAP.get(scenario, SCENARIO_STYLE_MAP["社交派对"])
        hook = opportunity.get("hook") or opportunity.get("title") or self._match_display(match)
        display = self._match_display(match)
        event_type = opportunity.get("type", "matchday")
        score = self._score_display(match)
        title_hint = en_title.replace(":", " -").strip()[:60]
        hashtags = [tag for tag in en_hashtags.split() if tag.startswith("#")][:6]

        return {
            "title_hint": title_hint or f"{display} Anthem",
            "genre": {
                "primary": style["genre_primary"],
                "secondary": style["genre_options"][0],
                "fusion": style["genre_options"][1] if len(style["genre_options"]) > 1 else None,
            },
            "mood": {
                "primary": style["mood"].split(",")[0].strip(),
                "secondary": style["mood"].split(",")[1].strip() if "," in style["mood"] else style["mood"],
                "intensity": "high" if opportunity.get("priority") == "high" else "medium",
            },
            "tempo": {
                "bpm_range": style["bpm_range"],
                "feel": f"{hook} with {style['social_focus'].lower()}",
                "rhythm_pattern": "chant-ready pulse with a fast, repeatable hook",
            },
            "instrumentation": {
                "core": [style["genre_options"][0], "stadium drums"],
                "accent": ["crowd chants", "riser synths"],
                "exclude": ["soft ambient pads", "slow cinematic intro"],
            },
            "vocal": {
                "style": "anthemic lead with crowd response",
                "gender": "any",
                "language": "en",
                "tone": style["vocal_tone"],
                "reference": "festival football anthem energy",
            },
            "lyrics": {
                "theme": f"Turn {hook} in {display} into a fan anthem that matches the push copy.",
                "key_imagery": [
                    hook,
                    f"scoreline pressure {score or 'before kickoff tension'}",
                    "group chat, feed, and crowd noise colliding",
                ],
                "tone": en_body,
                "structure": "cold open hook, chant-heavy chorus, one sharp verse, repeatable outro",
                "must_include": [
                    display,
                    "a line that sounds native to football fans",
                    "a chantable phrase built from the trigger angle",
                ],
                "must_avoid": ["profanity", "slurs", "direct harassment", "unsupported factual claims"],
            },
            "production": {
                "length_seconds": [60, 90],
                "energy_curve": "start hot, lift at the chorus by 15 seconds, finish with one replayable chant",
                "mix_style": "clean, loud, mobile-first, punchy low end",
                "hook_strength": "high",
            },
            "social_optimization": {
                "tiktok_friendly": True,
                "meme_potential": "high",
                "duet_friendly": True,
                "trending_audio_style": event_type in {"x_trending", "matchday_live"},
                "reference_hashtags": hashtags,
            },
        }

    def _pick_variant(self, seed: str, size: int) -> int:
        return sum(ord(ch) for ch in seed) % size

    def _localized_angle(self, angle: str, code: str) -> str:
        labels = {
        }
        keyword_rules = [
            (["pre-kickoff"], {
                "EN": "pre-kickoff noise is building",
                "ZH": "赛前气氛已经拱起来了",
                "ES": "el ruido previo ya va subiendo",
                "MS": "suasana pra-sepak mula naik",
                "FIL": "umiinit na ang pre-kickoff vibe",
                "PT-PT": "o barulho antes do jogo já sobe",
                "PT-BR": "o pré-jogo já tá ganhando barulho",
            }),
            (["live momentum"], {
                "EN": "live momentum keeps swinging",
                "ZH": "现场节奏已经开始摇摆了",
                "ES": "la inercia en vivo no para de cambiar",
                "MS": "momentum live asyik berubah",
                "FIL": "palit nang palit ang live momentum",
                "PT-PT": "o embalo ao vivo não pára de mexer",
                "PT-BR": "o momentum ao vivo tá virando toda hora",
            }),
            (["final-whistle"], {
                "EN": "final-whistle reactions are landing",
                "ZH": "终场情绪已经落下来了",
                "ES": "ya caen las reacciones del pitido final",
                "MS": "reaksi wisel penamat dah turun",
                "FIL": "bumubuhos na ang final-whistle reactions",
                "PT-PT": "já caem as reacções do apito final",
                "PT-BR": "já tão vindo as reações do apito final",
            }),
            (["watch-party", "watch party"], {
                "EN": "watch-party plans are getting loud",
                "ZH": "观赛局已经热起来了",
                "ES": "los planes para ver el partido ya se calentaron",
                "MS": "plan tengok ramai-ramai dah panas",
                "FIL": "umiinit na ang watch-party plans",
                "PT-PT": "os planos de watch party já aqueceram",
                "PT-BR": "o esquenta da watch party já começou",
            }),
            (["dance edits", "edit culture", "edit"], {
                "EN": "edit culture found its next clip",
                "ZH": "二创素材已经到位了",
                "ES": "los edits ya encontraron su próximo clip",
                "MS": "bahan edit dah jumpa klip baru",
                "FIL": "may bago nang clip ang edit crowd",
                "PT-PT": "os edits já encontraram o próximo clip",
                "PT-BR": "os edits já acharam o próximo corte",
            }),
            (["mbappe", "vini"], {
                "EN": "Mbappe vs Vini debates are heating up",
                "ZH": "姆总和维尼这波开始对喷了",
                "ES": "el debate Mbappe vs Vini ya sube",
                "MS": "debat Mbappe lawan Vini dah naik",
                "FIL": "umiinit na ang Mbappe vs Vini debate",
                "PT-PT": "o debate Mbappe vs Vini já aquece",
                "PT-BR": "o debate Mbappe vs Vini já esquentou",
            }),
            (["var"], {
                "EN": "VAR takes are already flying",
                "ZH": "VAR 话题已经飞起来了",
                "ES": "ya vuelan las takes del VAR",
                "MS": "cerita VAR dah terbang",
                "FIL": "lumilipad na ang VAR takes",
                "PT-PT": "as takes sobre o VAR já voam",
                "PT-BR": "as takes de VAR já tão voando",
            }),
            (["banter"], {
                "EN": "banter is already getting messy",
                "ZH": "玩梗互呛已经开始乱了",
                "ES": "las bromas ya se están poniendo picantes",
                "MS": "banter dah mula jadi pedas",
                "FIL": "umiinit na ang asaran",
                "PT-PT": "a picardia já ficou mais acesa",
                "PT-BR": "a resenha já ficou mais ácida",
            }),
            (["group chat"], {
                "EN": "group chat is already losing it",
                "ZH": "群聊已经先炸了",
                "ES": "el grupo ya está perdiendo la cabeza",
                "MS": "group chat dah meletup dulu",
                "FIL": "nabaliw na agad ang group chat",
                "PT-PT": "o grupo já está a perder a cabeça",
                "PT-BR": "o grupo já enlouqueceu",
            }),
            (["fans are already picking"], {
                "EN": "fans are already picking their angle",
                "ZH": "球迷已经开始选边站了",
                "ES": "la afición ya está escogiendo bando",
                "MS": "fans dah mula pilih side",
                "FIL": "pumipili na agad ng side ang fans",
                "PT-PT": "os adeptos já estão a escolher lado",
                "PT-BR": "a torcida já começou a escolher lado",
            }),
            (["fan chants"], {
                "EN": "fan chants are writing themselves",
                "ZH": "助威词已经自己冒出来了",
                "ES": "los cánticos ya se escriben solos",
                "MS": "chant fan macam tulis sendiri",
                "FIL": "parang kusang sumusulat ang chants",
                "PT-PT": "os cânticos já se escrevem sozinhos",
                "PT-BR": "os cantos já tão vindo sozinhos",
            }),
        ]
        lowered = angle.lower()
        for keywords, mapping in keyword_rules:
            if any(keyword in lowered for keyword in keywords):
                return mapping.get(code, mapping["EN"])
        if code == "ZH":
            return angle
        return angle.rstrip(".")

    def _match_display(self, match: dict) -> str:
        home = match.get("team_home", {})
        away = match.get("team_away", {})
        left = home.get("code") or home.get("name") or "TBD"
        right = away.get("code") or away.get("name") or "TBD"
        return f"{left} vs {right}"

    def _score_display(self, match: dict) -> str:
        home = match.get("team_home", {})
        away = match.get("team_away", {})
        if home.get("score") is None or away.get("score") is None:
            return ""
        return f"{home.get('score')}-{away.get('score')}"

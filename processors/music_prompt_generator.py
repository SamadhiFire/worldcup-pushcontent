"""
LLM-generated AI music prompt director.

The table stores only the final plain English music prompt, but this generator
asks the LLM for both a positive prompt and a negative prompt so downstream
music generation can use both when needed.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from data_sources.api_football import TEAM_CN_TO_CODE
from processors.content_generator import ContentGenerator


TEAM_CODE_TO_EN = {
    "ARG": "Argentina",
    "AUS": "Australia",
    "AUT": "Austria",
    "BEL": "Belgium",
    "BOL": "Bolivia",
    "BRA": "Brazil",
    "CAN": "Canada",
    "CHI": "Chile",
    "CIV": "Ivory Coast",
    "CMR": "Cameroon",
    "COL": "Colombia",
    "CRC": "Costa Rica",
    "CRO": "Croatia",
    "CPV": "Cape Verde",
    "CZE": "Czech Republic",
    "DEN": "Denmark",
    "ECU": "Ecuador",
    "EGY": "Egypt",
    "ENG": "England",
    "ESP": "Spain",
    "FRA": "France",
    "GER": "Germany",
    "GHA": "Ghana",
    "HAI": "Haiti",
    "HON": "Honduras",
    "IRN": "Iran",
    "IRQ": "Iraq",
    "ITA": "Italy",
    "JPN": "Japan",
    "KOR": "South Korea",
    "KSA": "Saudi Arabia",
    "MAR": "Morocco",
    "MEX": "Mexico",
    "NED": "Netherlands",
    "NGA": "Nigeria",
    "NOR": "Norway",
    "NZL": "New Zealand",
    "PAR": "Paraguay",
    "PER": "Peru",
    "POL": "Poland",
    "POR": "Portugal",
    "QAT": "Qatar",
    "RSA": "South Africa",
    "SCO": "Scotland",
    "SEN": "Senegal",
    "SRB": "Serbia",
    "SUI": "Switzerland",
    "SWE": "Sweden",
    "TUN": "Tunisia",
    "TUR": "Turkey",
    "UKR": "Ukraine",
    "URU": "Uruguay",
    "USA": "United States",
    "UZB": "Uzbekistan",
    "WAL": "Wales",
}

TEAM_CN_TO_EN = {
    "佛得角": "Cape Verde",
    "新西兰": "New Zealand",
    "埃及": "Egypt",
    **{cn: TEAM_CODE_TO_EN[code] for cn, code in TEAM_CN_TO_CODE.items() if code in TEAM_CODE_TO_EN},
}

TEAM_EN_ALIASES = {
    "cote d ivoire": "Ivory Coast",
    "cote divoire": "Ivory Coast",
    "ivory coast": "Ivory Coast",
    "korea republic": "South Korea",
    "south korea": "South Korea",
    "south africa": "South Africa",
    "saudi": "Saudi Arabia",
    "saudi arabia": "Saudi Arabia",
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "czechia": "Czech Republic",
    "czech republic": "Czech Republic",
    "turkiye": "Turkey",
    "turkey": "Turkey",
    "cape verde": "Cape Verde",
    "new zealand": "New Zealand",
    "egypt": "Egypt",
}

TEAM_CODE_PATTERN = re.compile(r"\b(" + "|".join(sorted(TEAM_CODE_TO_EN.keys(), key=len, reverse=True)) + r")\b")
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
JSON_SYMBOL_PATTERN = re.compile(r"[{}\[\]\"]+")


class MusicPromptGenerator:
    """Generate final plain-English AI music prompts."""

    def __init__(self, mock: bool = False):
        self.mock = mock
        self.generator = ContentGenerator()

    def generate(self, event_ctx: dict, content: dict) -> dict[str, str]:
        """Return {"music_prompt": str, "negative_prompt": str}."""
        match_display = self._match_display_en(event_ctx)
        if self.mock:
            return self._fallback_prompt(event_ctx, content, match_display)

        base_prompt = self._build_prompt(event_ctx, content, match_display)
        retry_note = ""
        last_payload: dict[str, str] = {}

        for _ in range(2):
            response = self.generator._call_llm(
                base_prompt + retry_note,
                system_role="music_prompt_director",
            )
            payload = self._parse_json(response)
            normalized = {
                "music_prompt": self._normalize_output(payload.get("music_prompt", "")),
                "negative_prompt": self._normalize_output(payload.get("negative_prompt", "")),
            }
            last_payload = normalized
            issues = self._validate(normalized)
            if not issues:
                return normalized

            retry_note = (
                "\n\nPrevious output was rejected for: "
                + "; ".join(issues)
                + ". Regenerate both fields and obey every rule exactly."
            )

        fallback = self._fallback_prompt(event_ctx, content, match_display)
        if last_payload.get("music_prompt") and not CJK_PATTERN.search(last_payload["music_prompt"]):
            fallback["music_prompt"] = self._truncate_words(last_payload["music_prompt"], 90)
        if last_payload.get("negative_prompt") and not CJK_PATTERN.search(last_payload["negative_prompt"]):
            fallback["negative_prompt"] = self._truncate_words(last_payload["negative_prompt"], 45)
        return fallback

    def _build_prompt(self, event_ctx: dict, content: dict, match_display: str) -> str:
        match = event_ctx.get("match", {})
        event = event_ctx.get("event", {})
        en = content.get("en", {})
        x_trending = event_ctx.get("x_trending", {})
        style_reference = self._style_reference(en.get("aigc_prompt", {}))
        trigger = content.get("trigger", {}) or event_ctx.get("trigger", {})

        return f"""Generate one AI music-generation prompt for this World Cup push.

The final music prompt will be stored in a Feishu/Bitable text column. It must be a natural English paragraph, not JSON.

## Match
- Match: {match_display}
- Stage: {match.get('stage', '')}
- Venue: {match.get('venue', '')}
- Score: {match.get('score', '') or 'not provided'}

## Trigger
- Event type: {event.get('type', '')}
- Event description: {event.get('description', '')}
- Player: {event.get('player', '')}
- Minute: {event.get('minute', '')}
- Opportunity hook: {trigger.get('hook', '')}
- Related topic: {trigger.get('related_topic', '')}
- Priority: {trigger.get('priority', '')}

## Push Copy
- Scenario: {content.get('scenario', '')}
- Push title: {en.get('push_title', '')}
- Push description: {en.get('push_description', '')}
- Applicable object: {en.get('applicable_object', '')}
- Hashtags: {en.get('hashtags', '')}

## Social Context
- Topics: {self._compact_list(x_trending.get('topics', []), 5)}
- Hashtags: {self._compact_list(x_trending.get('hashtags', []), 8)}

## Music Style Reference
{style_reference}

## Requirements
- Output JSON only with keys: music_prompt, negative_prompt.
- music_prompt: English only, under 90 words, one natural paragraph.
- negative_prompt: English only, under 45 words, one natural paragraph.
- Use full English team names like "Spain vs Saudi Arabia"; never use team codes like ESP or KSA.
- Do not use Chinese or any non-English text.
- Do not mention "push copy", "mobile-first", "social-native", JSON, Feishu, Bitable, or internal workflow terms.
- Make the prompt specific to the match, trigger, fan emotion, scenario, and social context.
- Guide genre, mood, instrumentation, vocal style, lyrical angle, and energy curve.
- Do not invent facts, scores, injuries, scandals, winners, or player actions that are not provided.
- Keep it safe: no profanity, slurs, hate, harassment, national stereotypes, political chants, copyrighted lyrics, or exact artist imitation.

Return exactly:
{{
  "music_prompt": "English prompt under 90 words",
  "negative_prompt": "English negative prompt under 45 words"
}}"""

    def _style_reference(self, prompt: Any) -> str:
        if not isinstance(prompt, dict):
            return "No structured music reference provided."

        pieces = []
        for label, value in (
            ("Genre", prompt.get("genre")),
            ("Mood", prompt.get("mood")),
            ("Tempo", prompt.get("tempo")),
            ("Instrumentation", prompt.get("instrumentation")),
            ("Vocal", prompt.get("vocal")),
            ("Lyrics", prompt.get("lyrics")),
            ("Production", prompt.get("production")),
        ):
            compact = self._compact_value(value)
            if compact:
                pieces.append(f"- {label}: {compact}")
        return "\n".join(pieces[:7]) or "No structured music reference provided."

    def _compact_value(self, value: Any) -> str:
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                compact = self._compact_value(item)
                if compact:
                    parts.append(f"{key}: {compact}")
            return "; ".join(parts[:6])
        if isinstance(value, list):
            parts = []
            for item in value[:6]:
                compact = self._compact_value(item)
                if compact:
                    parts.append(compact)
            return ", ".join(parts)
        return str(value or "").strip()

    def _compact_list(self, values: list, limit: int) -> str:
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        return "; ".join(cleaned[:limit])

    def _parse_json(self, response: str) -> dict:
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            if "```json" in response:
                return json.loads(response.split("```json", 1)[1].split("```", 1)[0].strip())
            if "```" in response:
                return json.loads(response.split("```", 1)[1].split("```", 1)[0].strip())
            raise

    def _normalize_output(self, text: str) -> str:
        text = str(text or "").strip()
        text = JSON_SYMBOL_PATTERN.sub("", text)
        text = self._replace_team_codes(text)
        text = self._replace_chinese_team_names(text)
        text = re.sub(r"\bmatches the push copy\b", "fits the fan moment", text, flags=re.I)
        text = re.sub(r"\bmobile-first\b", "clear", text, flags=re.I)
        text = re.sub(r"\bsocial-native\b", "fan-ready", text, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _replace_team_codes(self, text: str) -> str:
        return TEAM_CODE_PATTERN.sub(lambda match: TEAM_CODE_TO_EN.get(match.group(1), match.group(1)), text)

    def _replace_chinese_team_names(self, text: str) -> str:
        for cn_name, en_name in sorted(TEAM_CN_TO_EN.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(cn_name, en_name)
        return text

    def _validate(self, payload: dict[str, str]) -> list[str]:
        issues = []
        music = payload.get("music_prompt", "")
        negative = payload.get("negative_prompt", "")

        if not music:
            issues.append("music_prompt is empty")
        if not negative:
            issues.append("negative_prompt is empty")
        if len(music.split()) > 90:
            issues.append("music_prompt is over 90 words")
        if len(negative.split()) > 45:
            issues.append("negative_prompt is over 45 words")
        if CJK_PATTERN.search(music) or CJK_PATTERN.search(negative):
            issues.append("output contains non-English CJK characters")
        if any(symbol in music + negative for symbol in "{}[]"):
            issues.append("output contains JSON-like symbols")
        if TEAM_CODE_PATTERN.search(music) or TEAM_CODE_PATTERN.search(negative):
            issues.append("output contains team codes")
        banned_phrases = ("push copy", "mobile-first", "social-native", "feishu", "bitable")
        lowered = (music + " " + negative).lower()
        for phrase in banned_phrases:
            if phrase in lowered:
                issues.append(f"output contains internal phrase: {phrase}")
        return issues

    def _match_display_en(self, event_ctx: dict) -> str:
        match = event_ctx.get("match", {})
        api_data = event_ctx.get("api_data", {})
        home = api_data.get("team_home", {})
        away = api_data.get("team_away", {})
        if home or away:
            return f"{self._team_to_en(home)} vs {self._team_to_en(away)}"

        teams = match.get("teams", [])
        if isinstance(teams, list) and len(teams) >= 2:
            return f"{self._team_to_en(teams[0])} vs {self._team_to_en(teams[1])}"

        display = str(match.get("match_display", "") or "").strip()
        parts = [part.strip() for part in re.split(r"\bvs\b", display, maxsplit=1, flags=re.I)]
        if len(parts) == 2 and all(parts):
            return f"{self._team_to_en(parts[0])} vs {self._team_to_en(parts[1])}"
        return self._team_to_en(display) or display

    def _team_to_en(self, team: dict | str) -> str:
        if isinstance(team, dict):
            for key in ("code", "name_en", "name", "name_zh", "name_cn"):
                value = team.get(key)
                display = self._team_value_to_en(value)
                if display:
                    return display
            return "TBD"
        return self._team_value_to_en(team) or "TBD"

    def _team_value_to_en(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        upper = text.upper()
        if upper in TEAM_CODE_TO_EN:
            return TEAM_CODE_TO_EN[upper]
        if text in TEAM_CN_TO_EN:
            return TEAM_CN_TO_EN[text]

        normalized = self._normalize_key(text)
        if normalized in TEAM_EN_ALIASES:
            return TEAM_EN_ALIASES[normalized]
        for standard in TEAM_CODE_TO_EN.values():
            if normalized == self._normalize_key(standard):
                return standard
        return text

    def _normalize_key(self, value: str) -> str:
        ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()

    def _fallback_prompt(self, event_ctx: dict, content: dict, match_display: str) -> dict[str, str]:
        event = event_ctx.get("event", {})
        trigger = content.get("trigger", {}) or event_ctx.get("trigger", {})
        event_type = event.get("type", "")
        scenario = content.get("scenario", "")
        style = self._fallback_style(event_type, scenario)
        fan_angle = self._fallback_fan_angle(event, trigger)
        music_prompt = (
            f"Create {self._article_for(style)} {style} anthem for {match_display}. Capture {fan_angle} with clear fan emotion, "
            "stadium drums, crowd chants, a strong vocal lead, and a chorus supporters can repeat. "
            "Keep the lyrics clean, specific, dramatic, and built around the match atmosphere."
        )
        negative_prompt = (
            "Avoid profanity, slurs, national stereotypes, political chants, fake match claims, exact artist "
            "imitation, copyrighted lyrics, team codes, non-English lyrics, and generic ad copy."
        )
        return {
            "music_prompt": self._truncate_words(self._normalize_output(music_prompt), 90),
            "negative_prompt": self._truncate_words(self._normalize_output(negative_prompt), 45),
        }

    def _fallback_style(self, event_type: str, scenario: str) -> str:
        if event_type == "matchday_ft" or scenario in {"情怀致敬", "遗憾怀念"}:
            return "cinematic orchestral pop and R&B ballad"
        if event_type == "matchday_live" or scenario == "主场狂热":
            return "high-energy stadium pop and hip-hop"
        if event_type == "x_trending" or scenario == "短视频二创":
            return "tense edit-friendly stadium pop"
        return "upbeat stadium pop"

    def _fallback_fan_angle(self, event: dict, trigger: dict) -> str:
        event_type = event.get("type", "")
        if event_type == "matchday_ft":
            return "final-whistle pride, relief, heartbreak, and fans replaying the biggest moments"
        if event_type == "matchday_live":
            return "a live momentum swing, rising pressure, and fans choosing sides in real time"
        if event_type == "x_trending":
            return trigger.get("hook") or trigger.get("related_topic") or "a heated fan debate around the match"
        if event_type == "matchday_ns":
            return "pre-kickoff anticipation, watch-party energy, and supporters warming up their chants"
        return event.get("description") or trigger.get("hook") or "the fan reaction around this match"

    def _article_for(self, text: str) -> str:
        return "an" if text[:1].lower() in {"a", "e", "i", "o", "u"} else "a"

    def _truncate_words(self, text: str, max_words: int) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words]).rstrip(" ,.;:") + "."

"""
X (Twitter) Trending 数据抓取器
复用 x-trending 项目的 Playwright 爬虫逻辑，专注 Sports 分类
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from config import settings


# X Trending 项目的路径 (作为备份数据源)
X_TRENDING_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / \
                     "飞书抓ai音乐机器人" / "x-trending"


class XTrendingScraper:
    """X Trending Sports 分类数据抓取器"""

    def __init__(self):
        self.project_path = X_TRENDING_PROJECT
        self.has_project = self.project_path.exists()

    def get_sports_trending(self, query: str = "", limit: int = 20) -> Optional[dict]:
        """
        获取 X 上 Sports 分类的热门话题
        query: 可选的搜索关键词（如球员名、球队名）

        策略:
        1. 优先尝试调用 x-trending 项目的 JSON 输出
        2. 回退到直接调用 Playwright 爬取
        """
        # 优先使用最近的 JSON 输出文件
        cached = self._load_latest_cache()
        if cached and self._is_fresh(cached, max_age_minutes=30):
            sports_data = self._filter_sports(cached, query)
            if sports_data:
                return sports_data

        # 尝试直接爬取 (如果 x-trending 项目可用)
        if self.has_project:
            try:
                return self._scrape_via_project(query)
            except Exception as e:
                print(f"  ⚠ X Trending 爬取失败: {e}")

        return None

    def summarize_sentiment(self, trending_data: dict) -> str:
        """将 trending 数据总结为情绪摘要文本"""
        topics = trending_data.get("topics", [])
        hashtags = trending_data.get("hashtags", [])
        sentiments = trending_data.get("sentiments", [])

        parts = []
        if topics:
            parts.append(f"热门话题: {', '.join(topics[:5])}")
        if hashtags:
            parts.append(f"热门标签: {', '.join(hashtags[:5])}")
        if sentiments:
            parts.append(f"情绪风向: {', '.join(sentiments[:3])}")

        return " | ".join(parts) if parts else "无 X Trending 数据"

    def _load_latest_cache(self) -> Optional[dict]:
        """加载最近的 X Trending JSON 输出"""
        if not self.has_project:
            return None

        outputs_dir = self.project_path / "outputs"
        if not outputs_dir.exists():
            return None

        json_files = sorted(outputs_dir.glob("x_trending_*.json"), reverse=True)
        if not json_files:
            return None

        try:
            with open(json_files[0], "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _is_fresh(self, data: dict, max_age_minutes: int = 30) -> bool:
        """检查缓存数据是否足够新鲜"""
        timestamp = data.get("scraped_at", "")
        if not timestamp:
            return True  # 没有时间戳就假设可用
        try:
            from datetime import datetime
            scraped_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            age_minutes = (datetime.now(scraped_time.tzinfo) - scraped_time).total_seconds() / 60
            return age_minutes <= max_age_minutes
        except Exception:
            return True

    # 世界杯相关关键词（用于过滤无关内容）
    WORLDCUP_KEYWORDS = [
        "world cup", "worldcup", "fifa", "世界杯",
        "copa mundial", "copa do mundo", "piala dunia",
        "uefa", "champions",  # 足球相关也保留
        # 参赛队名
        "france", "brazil", "argentina", "germany", "england", "spain",
        "portugal", "netherlands", "belgium", "croatia", "italy", "japan",
        "korea", "mexico", "usa", "canada", "colombia", "uruguay",
        "senegal", "morocco", "nigeria", "serbia", "switzerland",
        # 球星名
        "mbappe", "vinicius", "haaland", "messi", "ronaldo", "neymar",
        "bellingham", "kane", "salah", "de bruyne", "modric",
    ]

    def _filter_sports(self, data: dict, query: str = "") -> Optional[dict]:
        """从数据中过滤 Sports + 世界杯相关内容"""
        groups = data.get("groups", [])
        all_items = []

        for group in groups:
            items = group.get("items", [])
            all_items.extend(items)

        if not all_items:
            # 如果没有 groups 结构，尝试直接从 raw 数据取
            all_items = data.get("items", []) or data.get("raw_items", [])

        # 过滤：必须包含世界杯相关关键词 或 匹配查询词
        def is_worldcup_related(item: dict) -> bool:
            text = json.dumps(item, ensure_ascii=False).lower()
            # 如果指定了 query（球员/球队名），优先匹配
            if query and query.lower() in text:
                return True
            # 检查世界杯关键词
            return any(kw in text for kw in self.WORLDCUP_KEYWORDS)

        filtered = [item for item in all_items if is_worldcup_related(item)]

        if not filtered:
            return None

        return {
            "topics": [item.get("summary", "") for item in filtered[:10]],
            "hashtags": self._extract_hashtags(filtered),
            "sentiments": [item.get("sentiment", "") for item in filtered if item.get("sentiment")],
            "raw_items": filtered[:20],
        }

    def _extract_hashtags(self, items: list) -> list:
        """从推文内容中提取 hashtag"""
        import re
        hashtags = set()
        for item in items:
            content = item.get("content", "") or item.get("summary", "")
            found = re.findall(r"#(\w+)", content)
            hashtags.update(found)
        return sorted(hashtags)[:10]

    def _scrape_via_project(self, query: str = "") -> Optional[dict]:
        """通过 x-trending 项目的 Playwright 爬虫获取数据"""
        main_script = self.project_path / "main.py"
        if not main_script.exists():
            return None

        try:
            # 使用 x-trending 项目的 venv
            venv_python = self.project_path / ".venv" / \
                ("Scripts" if sys.platform == "win32" else "bin") / \
                ("python.exe" if sys.platform == "win32" else "python")

            if not venv_python.exists():
                venv_python = sys.executable

            result = subprocess.run(
                [str(venv_python), str(main_script),
                 "--dry-run", "--output-format", "json",
                 "--categories", "Sports"],
                capture_output=True, text=True, timeout=120,
                cwd=str(self.project_path),
            )

            if result.returncode == 0:
                return self._load_latest_cache()
        except subprocess.TimeoutExpired:
            print("  ⚠ X Trending 爬取超时")
        except Exception as e:
            print(f"  ⚠ X Trending 子进程失败: {e}")

        return None

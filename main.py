#!/usr/bin/env python3
"""
Vanso 2026 世界杯 Push 内容生成器 - CLI 入口

用法:
    python main.py generate --match "FRA vs BRA" --event "goal" --player "Vinícius Júnior" --minute 78 --score "1-2"
    python main.py generate --match "ENG vs GER" --event "red_card" --player "Harry Maguire" --minute 34 --score "0-0"
    python main.py generate --match "MEX vs CAN" --event "var_controversy" --minute 89 --score "1-1"
    python main.py test  # 用模拟数据测试全流程
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from config import settings
from data_sources.api_football import APIFootballClient
from scrapers.x_trending_scraper import XTrendingScraper
from processors.scenario_classifier import ScenarioClassifier
from processors.content_generator import ContentGenerator
from processors.translator import MultiLanguageTranslator
from exporters.bitable_exporter import BitableExporter


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Vanso 世界杯 Push 内容生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # ── generate 命令 ──
    gen = sub.add_parser("generate", help="根据比赛事件生成 Push 内容")
    gen.add_argument("--match", required=True, help="对阵信息，如 'FRA vs BRA'")
    gen.add_argument("--event", required=True,
                      choices=["goal", "red_card", "penalty", "var_controversy",
                               "upset", "injury", "hat_trick", "own_goal",
                               "last_minute_goal", "penalty_save", "milestone"],
                      help="事件类型")
    gen.add_argument("--player", default="", help="关联球员姓名")
    gen.add_argument("--minute", type=int, default=0, help="事件发生分钟数")
    gen.add_argument("--score", default="", help="当前比分，如 '1-2'")
    gen.add_argument("--stage", default="小组赛",
                      choices=["小组赛", "16强", "8强", "4强", "半决赛", "决赛"],
                      help="赛事阶段")
    gen.add_argument("--venue", default="", help="比赛场馆")
    gen.add_argument("--scenario", default="",
                      help="强制指定场景 (可选): 玩梗群嘲/情怀致敬/社交派对/短视频二创/主场狂热/遗憾怀念")
    gen.add_argument("--x-trending", action="store_true", help="启用 X Trending 数据作为情绪校准")
    gen.add_argument("--dry-run", action="store_true", help="仅生成内容，不写入 Bitable")
    gen.add_argument("--output", default="", help="额外输出 JSON 到指定路径")

    # ── test 命令 ──
    sub.add_parser("test", help="用模拟数据测试全流程")

    return parser


def run_generate(args):
    """主生成流程"""
    print(f"\n{'='*60}")
    print(f"  Vanso World Cup Push Generator")
    print(f"  Match: {args.match} | Event: {args.event} | Minute: {args.minute}'")
    print(f"{'='*60}\n")

    start_time = time.time()

    # ── Step 1: 构建事件上下文 ──
    print("[1/5] 构建事件上下文...")
    teams = [t.strip() for t in args.match.upper().replace("VS", "vs").split(" vs ")]
    event_context = {
        "match": {
            "teams": teams,
            "match_display": args.match,
            "stage": args.stage,
            "venue": args.venue,
            "score": args.score,
        },
        "event": {
            "type": args.event,
            "minute": args.minute,
            "player": args.player,
            "description": f"{args.minute}' {args.player or 'Unknown'} - {args.event.replace('_', ' ')}",
        },
        "triggered_at": datetime.now().isoformat(),
    }

    # ── Step 1.5: 尝试从聚合数据补充赛程 ──
    if settings.JUHE_API_KEY:
        try:
            print("  ↳ 查询聚合数据补充赛程信息...")
            api = APIFootballClient()
            match_data = api.search_match(teams[0], teams[1])
            if match_data:
                event_context["api_data"] = match_data
                print(f"  ✓ 赛程数据已获取")
            else:
                print(f"  ⚠ 未找到匹配赛程，使用手动输入数据")
        except Exception as e:
            print(f"  ⚠ 聚合数据查询失败: {e}，使用手动输入数据")

    # ── Step 2: X Trending 情绪校准（可选）──
    x_sentiment = ""
    if args.x_trending:
        print("[2/5] 抓取 X Trending 情绪数据...")
        try:
            scraper = XTrendingScraper()
            trending_data = scraper.get_sports_trending(query=args.player or teams[0])
            if trending_data:
                x_sentiment = scraper.summarize_sentiment(trending_data)
                event_context["x_trending"] = {
                    "sentiment": x_sentiment,
                    "top_hashtags": trending_data.get("hashtags", []),
                    "trending_topics": trending_data.get("topics", []),
                }
                print(f"  ✓ X 情绪: {x_sentiment[:80]}...")
            else:
                print(f"  ⚠ 未获取到 X Trending 数据")
        except Exception as e:
            print(f"  ⚠ X Trending 抓取失败: {e}")
    else:
        print("[2/5] 跳过 X Trending (未启用 --x-trending)")

    # ── Step 3: 场景分类 ──
    print("[3/5] 场景分类...")
    classifier = ScenarioClassifier()
    if args.scenario:
        scenarios = [{"scenario": args.scenario, "confidence": 1.0, "reason": "手动指定"}]
    else:
        scenarios = classifier.classify(event_context)

    for s in scenarios:
        print(f"  → {s['scenario']} (置信度: {s['confidence']:.0%}) - {s['reason']}")

    # ── Step 4: 内容生成 (EN 基准) ──
    print("[4/5] 生成 Push 内容 (EN 基准)...")
    generator = ContentGenerator()
    all_content = []

    for scenario_info in scenarios:
        scenario = scenario_info["scenario"]
        print(f"  ↳ 生成场景: {scenario}")

        # 生成英文基准内容
        en_content = generator.generate(
            event_context=event_context,
            scenario=scenario,
            x_sentiment=x_sentiment,
        )

        # 多语言适配
        print(f"  ↳ 翻译为 7 语言...")
        translator = MultiLanguageTranslator()
        multilang_content = translator.translate_all(en_content, scenario, event_context)

        content_entry = {
            "scenario": scenario,
            "scenario_reason": scenario_info["reason"],
            "confidence": scenario_info["confidence"],
            "en": en_content,
            "translations": multilang_content,
        }
        all_content.append(content_entry)

        print(f"  ✓ 完成: Push Title (EN) = {en_content.get('push_title', '')[:50]}")

    # ── Step 5: 输出 ──
    print("[5/5] 输出结果...")

    result = {
        "event_context": event_context,
        "content": all_content,
        "generated_at": datetime.now().isoformat(),
        "x_sentiment": x_sentiment,
    }

    # 保存 JSON
    output_path = args.output or str(
        settings.OUTPUT_DIR / f"push_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  ✓ JSON 已保存: {output_path}")

    # 写入 Bitable
    if not args.dry_run and not settings.DRY_RUN:
        print("  ↳ 写入飞书多维表格...")
        try:
            exporter = BitableExporter()
            record_ids = exporter.export(result)
            print(f"  ✓ 已写入 {len(record_ids)} 条记录到 Bitable")
        except Exception as e:
            print(f"  ✗ Bitable 写入失败: {e}")
            print(f"    JSON 文件已保存，可稍后手动导入")
    else:
        print("  ⚠ DRY RUN 模式，跳过 Bitable 写入")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  完成! 生成 {len(all_content)} 个场景 × 7 语言 = {len(all_content)*7} 条内容")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"{'='*60}\n")

    return result


def run_test():
    """用模拟数据测试全流程"""
    print("\n🧪 测试模式：使用模拟事件数据\n")

    test_args = argparse.Namespace(
        match="FRA vs BRA",
        event="goal",
        player="Vinícius Júnior",
        minute=78,
        score="1-2",
        stage="小组赛",
        venue="MetLife Stadium, New Jersey",
        scenario="玩梗群嘲",
        x_trending=False,
        dry_run=True,
        output="",
    )
    return run_generate(test_args)


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "generate":
        run_generate(args)
    elif args.command == "test":
        run_test()


if __name__ == "__main__":
    main()

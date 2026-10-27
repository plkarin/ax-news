"""The checks on what Argos writes, and the requeue of stories translated
before them (backend/translation.py)."""
from conftest import add_story, with_db

from translation import _bad_title, requeue_bad

# (Argos's output, the original title): real cases from the shared feeds.
BAD = [
    ("Copyright (c) 2015 SHINSEGAE. All Rights Reserved.", "프랑스, 태양광 계약 조기 종료·매입가격 인하 제동"),
    ("COPYRIGHT(C) 2015 BY PSEEN. ALL RIGHTS RESERVED.", "경북, 퓨리오사AI와 지역 AI 반도체 산업 생태계 조성 나서"),
    ("Adress: No. 5 Yard, 7th Guanggu Street, Badaling", "某某科技发布新品"),
    ("I'm sorry.", "【IT之家开箱】雷神水冷迷你 AI 工作站图赏：你的桌面 Agent“小黑匣”"),
    ("继 展 展", "继科隆游戏展后 IFA 柏林 2026 也闹贼：极摩客多款设备被盗"),
    ("2800mm", "奇瑞捷途旅行者 7 官图发布：方盒子造型，轴距 2800mm"),
    ("tο tο tο tο tο", "κάτι άλλο"),
    ("", "무엇"),
]
GOOD = [
    ("France, early termination of solar contracts", "프랑스, 태양광 계약 조기 종료·매입가격 인하 제동"),
    ("비아임, a AI productivity ecosystem with all the tools", "비아임, 모든 도구를 갖춘 AI 생산성 생태계"),
    ("[부음] YU Sangmo (Korea Del Technology Company) father-in-law", "[부음] 유상모(코리아델테크놀로지) 장인상"),
    ("Huawei HarmonyOS 7.0.0.111 hides a new feature", "华为 HarmonyOS 7.0.0.111 版本暗藏新特性"),
    ("Copyright does more harm than good and should be abolished", "Le droit d'auteur fait plus de mal que de bien"),
]


def test_bad_translations_are_refused():
    for new, original in BAD:
        assert _bad_title(new, original), new


def test_good_translations_pass():
    for new, original in GOOD:
        assert not _bad_title(new, original), new


def test_requeue_bad():
    async def t(pool):
        await pool.execute("""INSERT INTO feed_catalog (url, title, category, domain, lang, provider)
                              VALUES ('https://www.ithome.com/rss/', 'IT Home', 'Hardware', 'technology', 'zh', 'freshrss')""")
        footer = await add_story(pool, "Copyright (c) 2015 SHINSEGAE. All Rights Reserved.", lang="ko",
                                 original_title="프랑스, 태양광 계약 조기 종료", source="AI Times (Korea)")
        wrong_model = await add_story(pool, "继 展 展", lang="ko", original_title="继科隆游戏展后 IFA 柏林 2026 也闹贼",
                                      source="IT Home")
        never_translated = await add_story(pool, "Home Assistant 将新增 Live USB 安装选项", lang="en", source="IT Home")
        english_in_cjk_feed = await add_story(pool, "Apple ships iOS 27.1", lang="en", source="IT Home")
        name_kept = await add_story(pool, "비아임, a AI productivity ecosystem with all the tools", lang="ko",
                                    original_title="비아임, 모든 도구를 갖춘 AI 생산성 생태계", source="AI Times (Korea)")
        about_copyright = await add_story(pool, "Copyright does more harm than good", source="Hacker News")

        assert await requeue_bad(pool) == 3
        rows = {r["id"]: r for r in await pool.fetch("SELECT id, title, original_lang, translation_status FROM articles")}
        assert rows[footer]["translation_status"] == "pending"
        assert rows[footer]["title"] == "프랑스, 태양광 계약 조기 종료"      # the original title is back
        assert (rows[wrong_model]["translation_status"], rows[wrong_model]["original_lang"]) == ("pending", "zh")
        assert rows[wrong_model]["title"].startswith("继科隆")
        assert (rows[never_translated]["translation_status"], rows[never_translated]["original_lang"]) == ("pending", "zh")
        for kept in (english_in_cjk_feed, name_kept, about_copyright):
            assert rows[kept]["translation_status"] == "done", rows[kept]["title"]
        assert await requeue_bad(pool) == 0                                   # nothing twice
    with_db(t)

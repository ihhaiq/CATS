"""
An executable spec for the game.

Each scenario drives a throwaway in-memory world through a sequence of actions
and asserts the outcome. The same suite backs two entry points:

  * `python -m tests.test_rules` — run it in CI or before a deploy.
  * `/dev_scenarios` in Telegram — run it against the live process, which also
    proves the deployed build behaves the way the spec says.

Scenarios never touch the real repository or send messages, so running them in
production is safe.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from bot.config import Settings, settings as live_settings
from bot.core.clock import Clock
from bot.core.enums import AlertState, Breed, CareAction, Emotion
from bot.domain import rules
from bot.domain.entities import CatData
from bot.services.cat_service import CatService
from bot.storage.memory import MemoryRepository


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""

    @property
    def icon(self) -> str:
        return "✅" if self.ok else "❌"


class _Recorder:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def expect(self, name: str, condition: bool, detail: str = "") -> None:
        self.checks.append(Check(name, bool(condition), detail))

    def equal(self, name: str, got, want) -> None:
        self.expect(name, got == want, f"got={got!r} want={want!r}")

    def approx(self, name: str, got: float, want: float, tol: float = 2.0) -> None:
        self.expect(name, abs(got - want) <= tol, f"got={got} want≈{want}")


def _settings() -> Settings:
    return live_settings


def _fresh_cat(**over) -> CatData:
    base = dict(
        cat_id=1, owner_id=1, name="اختبار", breed=Breed.BLACK, id_number="000001"
    )
    base.update(over)
    return CatData(**base)


# --- pure rule checks (no IO) ----------------------------------------------
def check_rules(rec: _Recorder) -> None:
    clock = Clock()
    t0 = clock.now()

    # decay is anchored, not cumulative: two 1h windows == one 2h window
    once = rules.compute_decay(
        hunger=0, happiness=100, love_bar=100, since=t0, now=t0 + timedelta(hours=2)
    )
    step1 = rules.compute_decay(
        hunger=0, happiness=100, love_bar=100, since=t0, now=t0 + timedelta(hours=1)
    )
    step2 = rules.compute_decay(
        hunger=step1.hunger,
        happiness=step1.happiness,
        love_bar=step1.love_bar,
        since=t0 + timedelta(hours=1),
        now=t0 + timedelta(hours=2),
    )
    rec.equal("الاضمحلال تراكمي بشكل صحيح (ساعتين = ساعة+ساعة)", step2.hunger, once.hunger)

    # no time passed -> no change
    none = rules.compute_decay(hunger=50, happiness=50, love_bar=50, since=t0, now=t0)
    rec.expect("بدون وقت ما يصير اضمحلال", not none.changed and none.hunger == 50)

    # love only drains while neglected
    healthy = rules.compute_decay(
        hunger=0, happiness=100, love_bar=100, since=t0, now=t0 + timedelta(hours=3)
    )
    rec.equal("الحب ما ينزل والقطة بخير", healthy.love_bar, 100)

    neglected = rules.compute_decay(
        hunger=95, happiness=10, love_bar=100, since=t0, now=t0 + timedelta(hours=10)
    )
    rec.expect("الحب ينزل بالإهمال", neglected.love_bar < 90, f"love={neglected.love_bar}")

    # clamping
    extreme = rules.compute_decay(
        hunger=99, happiness=1, love_bar=1, since=t0, now=t0 + timedelta(days=30)
    )
    rec.expect(
        "القيم محصورة بين ٠ و١٠٠",
        0 <= extreme.hunger <= 100 and 0 <= extreme.happiness <= 100 and extreme.love_bar == 0,
    )

    # emotions
    rec.equal(
        "قطة جوعانة = حزينة",
        rules.emotion_of(hunger=90, happiness=90),
        Emotion.SAD,
    )
    rec.equal(
        "قطة شبعانة ومبسوطة = سعيدة",
        rules.emotion_of(hunger=20, happiness=90),
        Emotion.HAPPY,
    )
    rec.equal(
        "الهاربة لها حالة خاصة",
        rules.emotion_of(hunger=10, happiness=99, is_fled=True),
        Emotion.FLED,
    )

    # alert priority: love beats hunger
    rec.equal(
        "أولوية التنبيه للحب المنخفض",
        rules.alert_state(hunger=99, happiness=0, love_bar=5, is_fled=False),
        AlertState.LOVE_LOW,
    )
    rec.equal(
        "قطة بخير ما تعطي تنبيه",
        rules.alert_state(hunger=10, happiness=90, love_bar=90, is_fled=False),
        None,
    )

    # anti-spam
    rec.expect(
        "أول تنبيه ينرسل",
        rules.should_notify(
            state=AlertState.HUNGRY, last_state=None, last_at=None, now=t0, min_gap_seconds=3600
        ),
    )
    rec.expect(
        "ما يتكرر نفس التنبيه بسرعة",
        not rules.should_notify(
            state=AlertState.HUNGRY,
            last_state="hungry",
            last_at=t0,
            now=t0 + timedelta(minutes=30),
            min_gap_seconds=3600,
        ),
    )
    rec.expect(
        "يتكرر بعد انتهاء المهلة",
        rules.should_notify(
            state=AlertState.HUNGRY,
            last_state="hungry",
            last_at=t0,
            now=t0 + timedelta(hours=2),
            min_gap_seconds=3600,
        ),
    )
    rec.expect(
        "حالة جديدة تنرسل فوراً",
        rules.should_notify(
            state=AlertState.SAD,
            last_state="hungry",
            last_at=t0,
            now=t0 + timedelta(minutes=1),
            min_gap_seconds=3600,
        ),
    )

    # flee
    rec.expect("الهروب عند حب صفر", rules.should_flee(love_bar=0, is_fled=False))
    rec.expect("ما تهرب مرتين", not rules.should_flee(love_bar=0, is_fled=True))

    # cooldown
    ready, left = rules.check_cooldown(t0, 900, t0 + timedelta(minutes=5))
    rec.expect("التبريد يمنع التكرار", not ready and 550 < left < 650, f"left={left}")
    ready2, _ = rules.check_cooldown(t0, 900, t0 + timedelta(minutes=20))
    rec.expect("التبريد ينتهي بوقته", ready2)

    # names
    for bad in ("", "x", "a" * 40, "اسم<script>"):
        try:
            rules.validate_cat_name(bad)
            rec.expect(f"رفض الاسم غير الصالح: {bad[:12]!r}", False)
        except ValueError:
            rec.expect(f"رفض الاسم غير الصالح: {bad[:12]!r}", True)
    rec.equal("تنظيف المسافات بالاسم", rules.validate_cat_name("  مشمش   حلو "), "مشمش حلو")

    # id numbers
    ids = {rules.generate_id_number() for _ in range(500)}
    rec.expect("أرقام الهوية ٦ خانات", all(len(i) == 6 and i.isdigit() for i in ids))


# --- service-level checks (in-memory world) --------------------------------
async def check_service(rec: _Recorder) -> None:
    from bot.core import clock as clock_module

    repo = MemoryRepository()
    await repo.setup()
    service = CatService(repo, _settings())
    saved_offset = clock_module.clock.offset
    clock_module.clock.reset()

    try:
        user = await repo.get_or_create_user(1001, is_guest=True)
        cat = await service.adopt(1001, name="مشمش", is_guest=True)
        rec.expect("التبني ينشئ قطة", cat.cat_id > 0)

        user = await repo.get_or_create_user(1001)
        rec.expect("مكافأة التبني تنضاف", user.points > 100, f"points={user.points}")

        # no second cat
        try:
            await service.adopt(1001, name="ثانية")
            rec.expect("منع تبني قطة ثانية", False)
        except ValueError:
            rec.expect("منع تبني قطة ثانية", True)

        # cooldown blocks the immediate repeat
        r1 = await service.do_care(user, cat, CareAction.FEED)
        rec.expect("الإطعام الأول ينجح", r1.ok)
        r2 = await service.do_care(user, cat, CareAction.FEED)
        rec.expect("الإطعام الثاني مرفوض بالتبريد", not r2.ok and r2.reason == "cooldown")

        before = (await repo.get_or_create_user(1001)).points
        await service.do_care(user, cat, CareAction.FEED)
        after = (await repo.get_or_create_user(1001)).points
        rec.equal("ما تنطي نقاط أثناء التبريد", after, before)

        # fast-forward: the cat gets hungry and alerts
        clock_module.clock.advance(hours=30)
        result = await service.refresh(cat)
        rec.expect(
            "بعد ٣٠ ساعة القطة تحتاج اهتمام",
            result.state is not None,
            f"state={result.state}",
        )

        # refresh is idempotent
        h1 = result.cat.hunger
        again = await service.refresh(result.cat)
        rec.equal("تكرار الفحص ما يغير الحالة", again.cat.hunger, h1)

        # neglect it into fleeing
        clock_module.clock.advance(days=20)
        fled = await service.refresh(cat)
        rec.expect("الإهمال الطويل يخلي القطة تهرب", fled.cat.is_fled, f"love={fled.cat.love_bar}")
        rec.expect("وقت الهروب مسجّل", fled.cat.fled_at is not None)

        # shelter
        shelter = await repo.list_fled_cats()
        rec.expect("القطة الهاربة تظهر بالملجأ", any(c.cat_id == cat.cat_id for c in shelter))

        rescued = await service.readopt(2002, cat.cat_id)
        rec.equal("الاسترجاع يبدي بحب ٤٠", rescued.love_bar, rules.SHELTER_READOPT_LOVE)
        rec.equal("الاسترجاع ينقل الملكية", rescued.owner_id, 2002)
        rec.equal("الاسم والسلالة تبقى", rescued.name, "مشمش")

        # economy
        buyer = await repo.get_or_create_user(3003)
        item = (await repo.list_items())[0]
        await repo.add_points(3003, 500, "test")
        buyer = await repo.get_or_create_user(3003)
        ok, balance = await service.buy(buyer, item)
        rec.expect("الشراء ينجح مع رصيد كافي", ok)
        rec.equal("النقاط تنخصم", balance, 600 - item.price)
        bag = await repo.inventory(3003)
        rec.expect("الغرض ينضاف للحقيبة", any(i.item_id == item.item_id for i, _ in bag))

        poor = await repo.get_or_create_user(4004)
        expensive = max(await repo.list_items(), key=lambda i: i.price)
        ok2, _ = await service.buy(poor, expensive)
        rec.expect("الشراء يفشل بدون رصيد", not ok2)

        # partner
        owner_cat = await service.adopt(5005, name="لولو")
        ok3, reason = await service.attach_partner(owner_cat, 5005)
        rec.expect("ما يصير شريك نفسه", not ok3 and reason == "self")
        ok4, reason4 = await service.attach_partner(owner_cat, 6006)
        rec.expect("انضمام الشريك ينجح", ok4 and reason4 == "joined")
        partner_view = await repo.get_active_cat_for(6006)
        rec.expect("الشريك يشوف نفس القطة", partner_view is not None
                   and partner_view.cat_id == owner_cat.cat_id)

        partner_user = await repo.get_or_create_user(6006)
        care = await service.do_care(partner_user, owner_cat, CareAction.PLAY)
        rec.expect("عناية الشريك ترفع الانسجام", care.ok and care.cat.partner_affinity > 0)

        # reset wipes everything for that user
        await repo.reset_user(5005)
        rec.expect("التصفير يمسح بيانات المستخدم",
                   await repo.get_active_cat_for(5005) is None)
    finally:
        clock_module.clock.reset()
        if saved_offset:
            clock_module.clock.advance(hours=saved_offset.total_seconds() / 3600)
        await repo.close()


async def run_all() -> list[Check]:
    rec = _Recorder()
    check_rules(rec)
    await check_service(rec)
    return rec.checks


def summarize(checks: list[Check], *, verbose: bool = False) -> str:
    passed = sum(1 for c in checks if c.ok)
    failed = [c for c in checks if not c.ok]
    head = f"🧪 <b>نتيجة السيناريوهات: {passed}/{len(checks)}</b>"
    if not failed and not verbose:
        return head + "\n\n✅ كل الحالات اشتغلت صح."
    lines = [head, ""]
    shown = checks if verbose else failed
    for check in shown[:40]:
        lines.append(f"{check.icon} {check.name}")
        if not check.ok and check.detail:
            lines.append(f"   <code>{check.detail}</code>")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    results = asyncio.run(run_all())
    for c in results:
        print(f"{'PASS' if c.ok else 'FAIL'}  {c.name}  {c.detail if not c.ok else ''}")
    bad = [c for c in results if not c.ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} passed")
    raise SystemExit(1 if bad else 0)

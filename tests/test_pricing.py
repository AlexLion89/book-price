import unittest

from bookprice.model import Offer
from bookprice.pricing import drop_outliers, percentile, round_price, suggest


def shops(*prices, in_stock=True):
    return [Offer("shop", p, in_stock=in_stock) for p in prices]


def avito(*prices):
    return [Offer("avito", p) for p in prices]


class HelpersTest(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(percentile([100, 200, 300, 400, 500], 0.25), 200)
        self.assertEqual(percentile([400], 0.25), 400)

    def test_outliers(self):
        self.assertEqual(drop_outliers([400, 450, 500, 50, 5000]), [400, 450, 500])

    def test_round(self):
        self.assertEqual(round_price(377), 380)
        self.assertEqual(round_price(1234), 1250)
        self.assertEqual(round_price(3456), 3500)
        self.assertEqual(round_price(3), 10)


class SuggestTest(unittest.TestCase):
    def test_new_in_shops_caps_at_sixty_percent(self):
        v = suggest(shops(500, 650), avito(400, 420, 450, 500), [])
        self.assertEqual(v.scenario, "new_in_shops")
        self.assertEqual(v.start, 300)
        self.assertEqual(v.floor, 240)

    def test_cheap_avito_beats_cap(self):
        v = suggest(shops(1000), avito(300, 350, 400, 450), [])
        self.assertEqual(v.start, 320)

    def test_new_in_shops_without_avito(self):
        v = suggest(shops(800), [], [])
        self.assertEqual(v.start, 480)

    def test_only_used(self):
        v = suggest(shops(900, in_stock=False), avito(1800, 2000, 2200, 2500), [])
        self.assertEqual(v.scenario, "only_used")
        self.assertEqual(v.start, 1800)

    def test_few_listings_warns(self):
        v = suggest([], avito(2000), [])
        self.assertTrue(any("мало" in r for r in v.reasons))

    def test_history_only(self):
        v = suggest([], [], [800])
        self.assertEqual(v.scenario, "history_only")
        self.assertEqual(v.start, 1500)
        self.assertEqual(v.floor, 800)
        self.assertEqual(v.schedule(), [1500, 1350, 1200, 1100, 1000, 900, 800])

    def test_out_of_stock_shop_price_counts_as_history(self):
        v = suggest(shops(700, in_stock=False), [], [])
        self.assertEqual(v.scenario, "history_only")
        self.assertEqual(v.floor, 700)

    def test_unknown(self):
        v = suggest([], [], [])
        self.assertIsNone(v.start)
        self.assertEqual(v.schedule(), [])

    def test_condition(self):
        v = suggest(shops(1000), [], [], condition="marked")
        self.assertEqual(v.start, 330)

    def test_cheap_goes_to_lot(self):
        v = suggest(shops(300), [], [])
        self.assertTrue(v.as_lot)

    def test_schedule_reaches_floor(self):
        v = suggest(shops(1000), [], [])
        plan = v.schedule()
        self.assertEqual(plan[0], v.start)
        self.assertEqual(plan[-1], v.floor)
        self.assertTrue(all(a > b for a, b in zip(plan, plan[1:])))


if __name__ == "__main__":
    unittest.main()

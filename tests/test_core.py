import unittest
from datetime import datetime, timedelta, timezone

from market_help.checker import evaluate_product, is_fresh
from market_help.matcher import matches, parse_watch_text
from market_help.models import Deal, Product, Watch
from market_help.sources.pelando import parse_page as parse_pelando
from market_help.textutil import brl, parse_price


def deal(title, price=None, store=None, **kw):
    return Deal(source="Teste", key=title, title=title, url="https://x", price=price, store=store, **kw)


class TestPrice(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_price("R$ 1.178,90"), 1178.90)
        self.assertEqual(parse_price("R$584,10"), 584.10)
        self.assertEqual(parse_price("1800"), 1800)
        self.assertEqual(parse_price("1.800"), 1800)
        self.assertEqual(parse_price("99.90"), 99.90)
        self.assertIsNone(parse_price("grátis"))

    def test_brl(self):
        self.assertEqual(brl(1329), "R$ 1.329,00")


class TestParseWatch(unittest.TestCase):
    def test_full(self):
        q, p, ex, st = parse_watch_text("Air Fryer até R$ 300 exceto usado, recondicionado loja amazon, mercado livre")
        self.assertEqual(q, "air fryer")
        self.assertEqual(p, 300)
        self.assertEqual(ex, ["usado", "recondicionado"])
        self.assertEqual(st, ["amazon", "mercado livre"])

    def test_sem_is_part_of_query(self):
        self.assertEqual(parse_watch_text("fone sem fio até 150"), ("fone sem fio", 150, [], []))

    def test_only_query(self):
        self.assertEqual(parse_watch_text("rtx 4060"), ("rtx 4060", None, [], []))

    def test_price_with_thousands(self):
        self.assertEqual(parse_watch_text("rtx 4060 ate 1.800,50")[1], 1800.50)


class TestMatch(unittest.TestCase):
    def test_words_any_order_and_accents(self):
        w = Watch(1, "fritadeira eletrica")
        self.assertTrue(matches(w, deal("Fritadeira Elétrica Air Fryer Mondial")))

    def test_word_prefix_only(self):
        w = Watch(1, "tv")
        self.assertTrue(matches(w, deal("Smart TV 50\" Samsung")))
        self.assertFalse(matches(w, deal("Fone Estvalo")))

    def test_max_price(self):
        w = Watch(1, "air fryer", max_price=300)
        self.assertTrue(matches(w, deal("Air Fryer Elgin", 151.9)))
        self.assertFalse(matches(w, deal("Air Fryer Philco", 386)))
        self.assertFalse(matches(w, deal("Air Fryer sem preço")))

    def test_exclude_and_store(self):
        w = Watch(1, "iphone", exclude=["usado", "capa"], stores=["amazon"])
        self.assertTrue(matches(w, deal("iPhone 15 128GB", 4000, "Amazon")))
        self.assertFalse(matches(w, deal("iPhone 15 usado", 2000, "Amazon")))
        self.assertFalse(matches(w, deal("Capa para iPhone 15", 20, "Amazon")))
        self.assertFalse(matches(w, deal("iPhone 15 128GB", 4000, "Magalu")))


class TestFresh(unittest.TestCase):
    def test_age(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(is_fresh(deal("a", published=now - timedelta(hours=1)), 48))
        self.assertFalse(is_fresh(deal("a", published=now - timedelta(hours=72)), 48))
        self.assertFalse(is_fresh(deal("a", active=False), 48))


class TestProduct(unittest.TestCase):
    def test_target_notifies_once_then_again_after_rise(self):
        p = Product(1, "u", "Echo", target_price=500, last_price=None, notified_price=None)
        self.assertIsNone(evaluate_product(p, "Echo", 584))
        self.assertIn("alvo", evaluate_product(p, "Echo", 499))
        self.assertIsNone(evaluate_product(p, "Echo", 499))  # não repete
        self.assertIn("alvo", evaluate_product(p, "Echo", 480))  # caiu mais: avisa
        self.assertIsNone(evaluate_product(p, "Echo", 520))
        self.assertIn("alvo", evaluate_product(p, "Echo", 490))  # subiu e voltou: avisa

    def test_drop_without_target(self):
        p = Product(1, "u", "Echo", None, last_price=600, notified_price=None)
        self.assertIn("caiu", evaluate_product(p, "Echo", 540))
        self.assertIsNone(evaluate_product(p, "Echo", 560))


class TestPelandoParser(unittest.TestCase):
    def test_astro_props(self):
        page = (
            '<astro-island props="{&quot;initialData&quot;:[0,{&quot;deals&quot;:[0,{&quot;deals&quot;:[1,[[0,'
            '{&quot;id&quot;:[0,&quot;abc&quot;],&quot;slug&quot;:[0,&quot;air-fryer-x&quot;],'
            '&quot;title&quot;:[0,&quot;Air Fryer X&quot;],&quot;price&quot;:[0,199.9],'
            '&quot;status&quot;:[0,&quot;active&quot;],&quot;kind&quot;:[0,&quot;promotion&quot;],'
            '&quot;createdAt&quot;:[0,&quot;2026-11-12T23:41:22.027Z&quot;],'
            '&quot;store&quot;:[0,{&quot;name&quot;:[0,&quot;Amazon&quot;]}]}]]]}]}]}"></astro-island>'
        )
        [d] = parse_pelando(page)
        self.assertEqual((d.title, d.price, d.store, d.url), ("Air Fryer X", 199.9, "Amazon", "https://www.pelando.com.br/d/air-fryer-x"))


if __name__ == "__main__":
    unittest.main()

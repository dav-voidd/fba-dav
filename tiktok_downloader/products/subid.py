"""Affiliate sub ID generator.

    NOV11 + IC + spicesstorage + 1  ->  NOV11ICspicesstorage1
    date    code   product (≤2 words)  #

The number is added only when the same product appears more than once in a batch,
counting in queue order. The code ("IC") is a user setting.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from ..models import QueueItem


def date_prefix(when: date | None = None) -> str:
    when = when or date.today()
    return f"{when.strftime('%b').upper()}{when.day}"


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"                      # batteries -> battery
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "oes")):
        return word[:-2]                            # brushes -> brush, mangoes -> mango
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]                            # ties -> tie, mangos -> mango
    return word


def _words(text: str) -> list[str]:
    return [_singular(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower())]


def product_slug(short_name: str) -> str:
    """The product part of the sub ID, as written (e.g. "zipties", "spicesstorage")."""
    return "".join(re.findall(r"[a-z0-9]+", (short_name or "").lower())[:2])


def _match_key(short_name: str) -> str:
    """Spelling-insensitive key used only to spot the same product (dried mangoes = dried mango)."""
    return "".join(_words(short_name)[:2])


_FILLER = {"for", "with", "and", "the", "a", "of", "in", "set", "pcs", "pc", "piece", "pieces",
           "new", "best", "original", "premium", "high", "quality", "portable", "mini"}


def _same_product(a, b) -> bool:
    """Two Gemini answers describing the same product, worded a bit differently."""
    if _match_key(a.short_name) == _match_key(b.short_name):
        return True
    short_a, short_b = set(_words(a.short_name)), set(_words(b.short_name))
    name_a = set(_words(a.name)) - _FILLER
    name_b = set(_words(b.name)) - _FILLER
    if not (short_a & short_b) or not name_a or not name_b:
        return False  # must at least share a core word, e.g. "mango"
    return len(name_a & name_b) / len(name_a | name_b) >= 0.6


def clean_code(text: str) -> str:
    return "".join(re.findall(r"[A-Za-z0-9]+", text or ""))


def make_subid(short_name: str, when: date | None = None, code: str = "IC",
               number: int | None = None, prefix: str | None = None) -> str:
    """``prefix`` overrides the date part, e.g. "NOV13" to prepare tomorrow's videos."""
    start = clean_code(prefix).upper() if prefix and clean_code(prefix) else date_prefix(when)
    return start + clean_code(code) + product_slug(short_name) + (str(number) if number else "")


def assign_subids(items: Iterable[QueueItem], code: str = "IC", when: date | None = None,
                  prefix: str | None = None) -> None:
    """Give every recognised item its sub ID. Videos of the same product share one name
    (taken from the first of them) and are numbered 1, 2, 3… in queue order."""
    scanned = [item for item in items if item.product]
    groups: list[list] = []  # each: [representative product, items...]
    for item in scanned:
        for group in groups:
            if _same_product(group[0], item.product):
                group.append(item)
                break
        else:
            groups.append([item.product, item])
    for representative, *members in groups:
        for number, item in enumerate(members, 1):
            item.product.sub_id = make_subid(representative.short_name, when, code,
                                             number if len(members) > 1 else None, prefix)


_SUBID = re.compile(r"^[A-Z]{3}\d{1,2}[A-Z]*([a-z][a-z0-9]*?)(\d*)([A-Z][A-Z0-9]*)?$")


def number_from_subid(sub_id: str) -> str:
    """NOV11ICspicesstorage1BEFINE -> "1" (the repeat number), "" when there is none."""
    match = _SUBID.match((sub_id or "").strip())
    return match.group(2) if match else ""


def caption_name(sub_id: str, name: str) -> str:
    """"Spices Storage" + NOV11ICspicesstorage1BEFINE -> "Spices Storage 1" (shop name never included)."""
    number = number_from_subid(sub_id)
    return f"{name} {number}" if name and number else name


def slug_from_subid(sub_id: str) -> str:
    """NOV11ICspicesstorage1BEFINE -> "spicesstorage" (date, code, number and shop removed)."""
    match = _SUBID.match((sub_id or "").strip())
    return match.group(1) if match else ""


# Common Shopee product words, for splitting names offline ("spicesstorage" -> "Spices Storage").
_VOCAB = set("""
a air anti antifog bag bags baby bamboo band bar basket bath battery beauty bed belt bike bin black blade blender
blanket board body bottle bottles bowl box boxes brush bucket button buttons cabinet cable cake camera can candle
cap car card care carpet case cat ceramic chair charger cleaner cleaning clip clips cloth clothes clothing coat
coating collar comb container cooker cooking cotton cover cream cup curtain curtains cushion cutter cutting
dish dispenser dog door drawer dress drill dried dryer duster dust ear egg electric eye face fan film filter
fish flash flashlight floor flower foam foldable food fork frame fridge fruit garden gel glass glasses glue grill
hair hand hanger hangers hat head heater holder home hook hooks hose ice iron jar jeans juice kettle key keyboard
kids killer kit kitchen knife lamp laptop led leak light lights lint lip lock long magnetic mango mask mat
meat mint mirror mop mouse mug nail nano neck net oil organizer oven pad pan pants paper pen pet phone pillow
plate plant plastic pocket pot powder pressure probiotic pump rack remover repair ring roach roof rope rubber
rug sanitizer scale scissors screen seal sealant seat set shampoo shelf shirt shoe shoes short shower silicone
sink skin slipper slippers soap socks sofa spatula spice spices sponge spoon spray stand steel sticker stickers
storage stove strap straw sun table tape tie ties tire tissue toilet tool tools toothbrush toothpaste towel toy
toys tray tube tumbler umbrella vacuum wall wallet wash washer watch water waterproof whitening window wipes
wire wireless wood wooden chopper slicer peeler grater sharpener opener lunch sealer gadget
machine vegetable massager adapter agent aircon airfryer airtight anklet aquarium automatic backpack bag baking ball bank basket bathrobe beanie bedsheet bedside bike bin blanket bleach blender blocks blouse blush bowl boxer bra bracelet brief broom brush bulb burner butter cable cage camping candle candy canister cap car cardigan case cat chair charger chips chocolate cleaner cleanser clip clipper cloth coating coffee colander collagen collar cologne commode concealer container cooker cookies cooler cooling cover crossbody curtain cuttingboard dashboard dehumidifier dent deodorant desk detergent diffuser dispenser divider dog doll drawer dress drill drone dustpan earbuds earrings eraser extension eyeliner facewash facial fan feeder fence fertilizer film fishing flashlight flask foundation freshener fryer gas gloves glue grater grinder hairclip hammer hammock hamper hanger hanging harness headband headlamp headset heater heating helmet holder honey hoodie hose humidifier ink insect iron jacket jam jar jeans jug juicer kettle keyboard keychain knife label ladder ladle lamp lantern lanyard laptop lashes launcher laundry leash lego lid lighter lipgloss lipstick litter lotion lunchbox manicure marker massager mat matches measuring microfiber microphone milk mixer moisturizer mold monitor mop mosquito mount mouse nailcutter nailpolish nebulizer necklace needle night noodles notebook oil organizer oximeter pad pajama pan panty peanut pedicure peeler pegboard pencil perfume pesticide pet phone pitcher planner planter pliers plug polish polo pot pouch powder power primer printer protector protein puller pump purifier purse puzzle rack rat razor repellent rice ring rings roach rocket roller rope salt sandals sauce saw scarf scissors scooter screwdriver scrubber scrunchie sealer seasoning seat seeds selfie serum sewing shampoo shaver shoe shorts skateboard skirt slicer sling slippers smartwatch snacks sneakers soap socket socks softener soil solar speaker sponge sprinkler squeegee stand stapler steamer stick sticker stove strainer stylus sugar sunglasses sunscreen supplement sweater tablet tape tea tempered tent thermometer thermos thread tire toaster toiletry toner tongs tote towel toy tracker trap travel tray trimmer tripod tumbler tupperware tweezer underwear usb vacuum vinegar visor vitamins wax webcam whisk wig wiper wok wrench zip headphones earphones speaker phonecase stainless glow cutlery pack portable mini
""".split())


def split_words(slug: str) -> str:
    """Best-effort offline split: "spicesstorage" -> "Spices Storage". Falls back to "Spicesstorage"."""
    return split_known(slug) or re.sub(r"[^a-z0-9]", "", (slug or "").lower()).capitalize()


def split_known(slug: str) -> str:
    """Offline split only when every piece is a known word; "" when unsure."""
    slug = re.sub(r"[^a-z0-9]", "", (slug or "").lower())
    if not slug:
        return ""
    n = len(slug)
    best: list[tuple[int, list[str]] | None] = [None] * (n + 1)
    best[0] = (0, [])
    for end in range(1, n + 1):
        for start in range(max(0, end - 14), end):
            if best[start] is None:
                continue
            piece = slug[start:end]
            known = (piece in _VOCAB or piece.isdigit() or (piece.endswith("s") and piece[:-1] in _VOCAB)
                     or (piece.endswith("es") and piece[:-2] in _VOCAB))      # mangoes, ties, boxes
            cost = 1 if known else 10 * len(piece)   # unknown letters cost a lot
            total = best[start][0] + cost
            if best[end] is None or total < best[end][0]:
                best[end] = (total, best[start][1] + [piece])
    cost, words = best[n]
    if cost >= 10:                       # something unknown in there: don't guess the split
        return ""
    return " ".join(w.capitalize() for w in words)


def shop_from_subid(sub_id: str) -> str:
    """NOV14ICtumbler1DAILYMART -> "DAILYMART" ("" when the sub ID has no shop name)."""
    match = _SUBID.match((sub_id or "").strip())
    return (match.group(3) or "") if match else ""

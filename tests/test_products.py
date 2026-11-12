from datetime import date

from tiktok_downloader.models import Product, QueueItem, Status
from tiktok_downloader.products.subid import assign_subids, make_subid

NOV11 = date(2026, 11, 11)


def test_subid_format():
    assert make_subid("led flashlight", NOV11) == "NOV11ICledflashlight"
    assert make_subid("Spices Storage Rack", NOV11, number=2) == "NOV11ICspicesstorage2"
    assert make_subid("hair tie", date(2026, 1, 5), code="XY") == "JAN5XYhairtie"


def _item(index, short):
    return QueueItem(index, f"u{index}", Status.DONE, product=Product(short.title(), short))


def test_repeats_are_numbered_in_queue_order():
    items = [_item(1, "spices storage"), _item(2, "zip ties"), _item(3, "spices storage"),
             QueueItem(4, "u4", Status.DONE), _item(5, "travel bag"), _item(6, "travel bag")]
    assign_subids(items, "IC", NOV11)
    assert [i.product.sub_id for i in items if i.product] == [
        "NOV11ICspicesstorage1", "NOV11ICzipties", "NOV11ICspicesstorage2",
        "NOV11ICtravelbag1", "NOV11ICtravelbag2"]


def test_custom_edit_wins():
    item = _item(1, "hair tie")
    assign_subids([item], "IC", NOV11)
    item.product.custom_sub_id = "NOV11IChairtieSUNSHINE2PH"
    assert item.product.display_sub_id == "NOV11IChairtieSUNSHINE2PH"


def test_gemini_batch_parse():
    import json
    from tiktok_downloader.products import gemini
    text = json.dumps([
        {"video": 1, "product_name": " Tissue Box  Holder ", "short_name": "Tissue Holder", "confidence": 0.9},
        {"video": 3, "product_name": "LED Flashlight", "short_name": "led flashlight", "confidence": "0.7"},
        {"video": 4, "product_name": "", "short_name": "", "confidence": 0},
    ])
    results = gemini.parse_batch({"candidates": [{"content": {"parts": [{"text": text}]}}]})
    assert set(results) == {1, 3}
    assert results[1]["product_name"] == "Tissue Box Holder" and results[1]["short_name"] == "tissue holder"
    assert gemini.find_key("x AIzaSyA1b2C3d4E5f6G7h8I9j0K_lMnOpQrStUv y") == "AIzaSyA1b2C3d4E5f6G7h8I9j0K_lMnOpQrStUv"
    assert gemini.rank_models(["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite"])[:2] == ["gemini-3.5-flash", "gemini-3.5-flash-lite"]


def test_prompt_uses_visuals_and_audio():
    from tiktok_downloader.products import gemini
    assert "visuals AND the audio" in gemini.PROMPT and "Ignore everything else" in gemini.PROMPT


def test_shopee_search_sorted_by_sales():
    from tiktok_downloader.products.shopee import search_url
    url = search_url("tissue box holder")
    assert url == "https://shopee.ph/search?keyword=tissue+box+holder&sortBy=sales"

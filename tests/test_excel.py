from openpyxl import load_workbook

from tiktok_downloader.products import excel


def test_same_layout_as_sample(tmp_path):
    links = ["https://s.shopee.ph/5VWoYfiBZ2", "https://s.shopee.ph/5LDOMMiou1", "https://s.shopee.ph/5q9exHgut8"]
    subs = ["NOV11IChairtieSUNSHINE2PH", "NOV11ICroachkillerCFLOWPH", "NOV11ICspicesstorage1BEFINE"]
    path = tmp_path / excel.safe_filename("NOV11IC")
    assert excel.build(links, subs, path) == 3
    ws = load_workbook(path).active
    assert [c.value for c in ws[1]] == excel.HEADERS
    assert [ws[f"A{r}"].value for r in (3, 6, 9)] == links
    assert [ws[f"B{r}"].value for r in (3, 6, 9)] == subs
    assert ws["A4"].value is None and ws["A5"].value is None          # 2 blank rows between
    assert ws["A3"].font.name == "Arial" and ws["A3"].font.sz == 11 and ws["B3"].font.sz == 10
    assert round(ws.column_dimensions["A"].width, 1) == 35.7
    assert ws["A3"].hyperlink.target == links[0] and ws["A3"].font.u == "single"


def test_lines_and_filename():
    assert excel.lines(" a \n\n b\r\n") == ["a", "b"]
    assert excel.safe_filename('NOV13:IC') == "NOV13IC.xlsx"

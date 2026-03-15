"""JLCPCB/EasyEDA component search GUI.

Can be used standalone:  python plugins/component_search.py
Or embedded via SearchDialog / SearchPanel in the main plugin.
"""

from __future__ import annotations

import io
import logging
import sys
import threading
import urllib.request
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import wx
import wx.adv

# --- make the easyeda2kicad submodule importable ---
current_dir = Path(__file__).resolve().parent
easyeda_submodule = current_dir / "easyeda2kicad"
if easyeda_submodule.exists():
    easyeda_str = str(easyeda_submodule)
    if easyeda_str not in sys.path:
        sys.path.insert(0, easyeda_str)

from easyeda2kicad.easyeda.easyeda_api import EasyedaApi  # noqa: E402

Row = dict[str, Any]

_SEARCH_PAGE_SIZE = 25  # API page size; results are capped at this value
_IMAGE_CACHE_MAX = 50  # max cached product images per session

# (label, field_keys, min_width)  - first matching key wins
COLUMNS: list[tuple[str, list[str], int]] = [
    ("LCSC#", ["lcsc", "componentCode"], 80),
    ("Name", ["name", "componentModelEn"], 200),
    ("Brand", ["brand", "brandNameEn"], 100),
    ("Package", ["package", "packageEnglish"], 110),
    ("Stock", ["stock", "stockCount"], 70),
    ("Type", ["type", "componentLibraryType"], 70),
    ("Price", ["price"], 60),
    ("Description", ["description", "componentDescription"], 260),
]

# fields shown in the detail panel (label, keys, is_url)
DETAIL_FIELDS: list[tuple[str, list[str], bool]] = [
    ("LCSC", ["lcsc", "componentCode"], False),
    ("Name", ["name", "componentModelEn"], False),
    ("Model", ["model"], False),
    ("Brand", ["brand", "brandNameEn"], False),
    ("Package", ["package", "packageEnglish"], False),
    ("Category", ["category"], False),
    ("Stock", ["stock", "stockCount"], False),
    ("Min. Qty", ["min_qty"], False),
    ("Reel Qty", ["reel_qty"], False),
    ("Type", ["type", "componentLibraryType"], False),
    ("Description", ["description", "componentDescription"], False),
    ("Datasheet", ["datasheet"], True),
    ("URL", ["url"], True),
]


def _pick(row: Row, keys: list[str]) -> str:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return ""


@dataclass
class FilterState:
    excluded_brands: set[str] = field(default_factory=set)
    excluded_packages: set[str] = field(default_factory=set)
    excluded_types: set[str] = field(default_factory=set)
    min_stock: int = 0
    min_price: str = ""
    max_price: str = ""

    @property
    def is_active(self) -> bool:
        return bool(
            self.excluded_brands
            or self.excluded_packages
            or self.excluded_types
            or self.min_stock
            or self.min_price
            or self.max_price
        )

    def matches(self, row: Row) -> bool:
        if self.excluded_brands and _pick(row, ["brand", "brandNameEn"]) in self.excluded_brands:
            return False
        if (
            self.excluded_packages
            and _pick(row, ["package", "packageEnglish"]) in self.excluded_packages
        ):
            return False
        if (
            self.excluded_types
            and _pick(row, ["type", "componentLibraryType"]) in self.excluded_types
        ):
            return False
        if self.min_stock:
            try:
                if int(row.get("stock") or 0) < self.min_stock:
                    return False
            except (ValueError, TypeError):
                pass
        price = row.get("price")
        if price is not None:
            try:
                p = float(price)
                if self.min_price and p < float(self.min_price):
                    return False
                if self.max_price and p > float(self.max_price):
                    return False
            except (ValueError, TypeError):
                pass
        return True


class FilterDialog(wx.Dialog):  # type: ignore[misc]
    """Dialog for filtering search results by brand, package, type, stock and price."""

    def __init__(self, parent: wx.Window, results: list[Row], state: FilterState) -> None:
        super().__init__(
            parent, title="Filter Results", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        brands = sorted({v for r in results if (v := _pick(r, ["brand", "brandNameEn"]))})
        packages = sorted({v for r in results if (v := _pick(r, ["package", "packageEnglish"]))})
        types = sorted({v for r in results if (v := _pick(r, ["type", "componentLibraryType"]))})

        main = wx.BoxSizer(wx.VERTICAL)
        lists_row = wx.BoxSizer(wx.HORIZONTAL)

        self._brand_clb = self._clb_group("Brand", brands, state.excluded_brands, lists_row)
        self._package_clb = self._clb_group("Package", packages, state.excluded_packages, lists_row)
        self._type_clb = self._clb_group("Type", types, state.excluded_types, lists_row)

        # Numeric filters
        num_box = wx.StaticBox(self, label="Numeric")
        num_sizer = wx.StaticBoxSizer(num_box, wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, vgap=4, hgap=6)
        grid.AddGrowableCol(1)
        self._min_stock = wx.TextCtrl(
            num_box, value=str(state.min_stock) if state.min_stock else "", size=wx.Size(80, -1)
        )
        self._min_price = wx.TextCtrl(num_box, value=state.min_price, size=wx.Size(80, -1))
        self._max_price = wx.TextCtrl(num_box, value=state.max_price, size=wx.Size(80, -1))
        for lbl, ctrl in [
            ("Min Stock:", self._min_stock),
            ("Min Price $:", self._min_price),
            ("Max Price $:", self._max_price),
        ]:
            grid.Add(wx.StaticText(num_box, label=lbl), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
        num_sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 4)
        lists_row.Add(num_sizer, 0, wx.EXPAND)

        main.Add(lists_row, 1, wx.EXPAND | wx.ALL, 6)

        reset_btn = wx.Button(self, label="Reset")
        reset_btn.Bind(wx.EVT_BUTTON, self._on_reset)
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_row.Add(reset_btn, 0)
        btn_row.AddStretchSpacer()
        btn_row.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0)
        main.Add(btn_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.SetSizer(main)
        parent_w = parent.GetTopLevelParent().GetSize().width
        self.SetSize(wx.Size(parent_w, 320))

    def _clb_group(
        self, label: str, items: list[str], excluded: set[str], parent_sizer: wx.BoxSizer
    ) -> wx.CheckListBox:
        box = wx.StaticBox(self, label=label)
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        clb = wx.CheckListBox(box, choices=items)
        for i, item in enumerate(items):
            clb.Check(i, item not in excluded)
        # Width: fit longest item (char estimate) up to 200 px, at least 80 px.
        char_w = self.GetCharWidth()
        max_chars = max((len(s) for s in items), default=8)
        w = min(max(max_chars * char_w + 30, 80), 200)
        clb.SetMinSize(wx.Size(w, -1))
        sizer.Add(clb, 1, wx.EXPAND | wx.ALL, 2)
        parent_sizer.Add(sizer, 0, wx.EXPAND | wx.RIGHT, 4)
        return clb

    def _on_reset(self, _: wx.CommandEvent) -> None:
        for clb in (self._brand_clb, self._package_clb, self._type_clb):
            for i in range(clb.GetCount()):
                clb.Check(i, True)
        self._min_stock.SetValue("")
        self._min_price.SetValue("")
        self._max_price.SetValue("")

    def get_state(self) -> FilterState:
        def excluded(clb: wx.CheckListBox) -> set[str]:
            return {clb.GetString(i) for i in range(clb.GetCount()) if not clb.IsChecked(i)}

        def safe_int(ctrl: wx.TextCtrl) -> int:
            # Remove thousands separators (. or ,) then parse as int.
            s = ctrl.GetValue().strip().replace(".", "").replace(",", "")
            try:
                return max(0, int(s))
            except ValueError:
                return 0

        def safe_price(ctrl: wx.TextCtrl) -> str:
            # Normalize German decimal comma to dot.
            return str(ctrl.GetValue().strip().replace(",", "."))

        return FilterState(
            excluded_brands=excluded(self._brand_clb),
            excluded_packages=excluded(self._package_clb),
            excluded_types=excluded(self._type_clb),
            min_stock=safe_int(self._min_stock),
            min_price=safe_price(self._min_price),
            max_price=safe_price(self._max_price),
        )


class DetailPanel(wx.ScrolledWindow):  # type: ignore[misc]
    """Grid of label/value rows; URL values become clickable hyperlinks."""

    _IMG_MAX = 160  # max image dimension in pixels

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.VSCROLL)
        self.SetScrollRate(0, 12)

        self._img_bmp = wx.StaticBitmap(self)
        self._img_bmp.Hide()

        self._sizer = wx.FlexGridSizer(cols=2, vgap=4, hgap=8)
        self._sizer.AddGrowableCol(1, 1)

        outer = wx.BoxSizer(wx.HORIZONTAL)
        outer.Add(self._sizer, 1, wx.EXPAND | wx.ALL, 4)
        outer.Add(self._img_bmp, 0, wx.ALIGN_TOP | wx.ALL, 4)
        self.SetSizer(outer)
        self._widgets: list[wx.Window] = []

    def set_image(self, data: bytes | None) -> None:
        if data:
            try:
                img = wx.Image(io.BytesIO(data))
                if img.IsOk():
                    w, h = img.GetWidth(), img.GetHeight()
                    if w > self._IMG_MAX or h > self._IMG_MAX:
                        scale = self._IMG_MAX / max(w, h)
                        img = img.Scale(int(w * scale), int(h * scale), wx.IMAGE_QUALITY_HIGH)
                    self._img_bmp.SetBitmap(wx.Bitmap(img))
                    self._img_bmp.Show()
                    self.FitInside()
                    self.Layout()
                    return
            except Exception:
                pass
        self._img_bmp.Hide()
        self.FitInside()
        self.Layout()

    def _add_row(self, label: str, widget: wx.Window) -> None:
        lbl = wx.StaticText(self, label=f"{label}:")
        font = lbl.GetFont()
        font.MakeBold()
        lbl.SetFont(font)
        self._sizer.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        self._sizer.Add(widget, 1, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self._widgets += [lbl, widget]

    def show_component(self, row: Row) -> None:
        self._img_bmp.Hide()
        for w in self._widgets:
            w.Destroy()
        self._widgets.clear()
        self._sizer.Clear()
        # Reserve space for image column + padding; fall back to 300 if panel not yet sized.
        wrap_w = max(200, self.GetClientSize().width - self._IMG_MAX - 30)

        for label, keys, is_url in DETAIL_FIELDS:
            val = _pick(row, keys)
            if not val:
                continue
            if is_url:
                if len(val) <= 60:
                    short = val
                else:
                    parsed = urlparse(val)
                    filename = Path(parsed.path).name
                    candidate = f"{parsed.netloc}/…{filename}" if filename else val
                    short = candidate if len(candidate) <= 60 else candidate[:59] + "…"
                widget: wx.Window = wx.adv.HyperlinkCtrl(self, label=short, url=val)
            else:
                widget = wx.StaticText(self, label=val)
                widget.Wrap(wrap_w)
            self._add_row(label, widget)

        # Price breaks: "1+: $0.20  |  50+: $0.16  |  ..."
        price_breaks: list[dict[str, Any]] = row.get("price_breaks") or []
        if price_breaks:
            parts = [
                f"{p['qty']}+: ${p['price']:.4f}".rstrip("0").rstrip(".") for p in price_breaks
            ]
            txt = wx.StaticText(self, label="  |  ".join(parts))
            txt.Wrap(wrap_w)
            self._add_row("Prices", txt)

        # Technical attributes: one row per spec
        attributes: list[dict[str, Any]] = row.get("attributes") or []
        if attributes:
            specs = "\n".join(f"{a['name']}: {a['value']}" for a in attributes)
            txt = wx.StaticText(self, label=specs)
            self._add_row("Specs", txt)

        self._sizer.Layout()
        self.FitInside()
        self.Layout()

    def clear(self) -> None:
        self._img_bmp.Hide()
        for w in self._widgets:
            w.Destroy()
        self._widgets.clear()
        self._sizer.Clear()
        self.FitInside()
        self.Layout()


class SearchPanel(wx.Panel):  # type: ignore[misc]
    """Self-contained component-search panel - can later be embedded anywhere."""

    def __init__(
        self,
        parent: wx.Window,
        on_select: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = EasyedaApi()
        self._on_select_cb = on_select
        self._all_results: list[Row] = []
        self._results: list[Row] = []
        self._filter_state = FilterState()
        self._sort_col: int = -1
        self._sort_asc: bool = True
        self._search_request_id: int = 0
        self._image_request_id: int = 0
        self._image_cache: OrderedDict[str, bytes] = OrderedDict()
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = wx.BoxSizer(wx.VERTICAL)

        # ---- search row ----
        search_row = wx.BoxSizer(wx.HORIZONTAL)
        self.search_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.SetHint("Search JLCPCB / EasyEDA …")
        self.btn_search = wx.Button(self, label="Search")
        self.btn_filter = wx.Button(self, label="Filter")
        search_row.Add(self.search_ctrl, 1, wx.EXPAND | wx.RIGHT, 4)
        search_row.Add(self.btn_search, 0, wx.RIGHT, 4)
        search_row.Add(self.btn_filter, 0)
        root.Add(search_row, 0, wx.EXPAND | wx.ALL, 6)

        # ---- splitter: result list (top) / detail panel (bottom) ----
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)
        splitter.SetMinimumPaneSize(80)

        self.list_ctrl = wx.ListCtrl(
            splitter,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
        )
        for i, (label, _, width) in enumerate(COLUMNS):
            self.list_ctrl.InsertColumn(i, label, width=width)

        self.detail_panel = DetailPanel(splitter)
        splitter.SplitHorizontally(self.list_ctrl, self.detail_panel, sashPosition=-220)

        root.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.list_ctrl.Bind(wx.EVT_SIZE, self._on_list_resize)

        # ---- status line ----
        self.status = wx.StaticText(self, label="")
        root.Add(self.status, 0, wx.LEFT | wx.BOTTOM, 6)

        self.SetSizer(root)

        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.btn_filter.Bind(wx.EVT_BUTTON, self._on_filter)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_COL_CLICK, self._on_col_click)

    # ------------------------------------------------------------------
    # Search logic
    # ------------------------------------------------------------------

    def _on_search(self, _: wx.CommandEvent) -> None:
        keyword = self.search_ctrl.GetValue().strip()
        if not keyword:
            return
        self._set_status(f"Searching for '{keyword}' …")
        self.btn_search.Disable()
        self.btn_filter.Disable()
        self.list_ctrl.DeleteAllItems()
        self.detail_panel.clear()
        self._results = []
        self._search_request_id += 1
        req_id = self._search_request_id
        threading.Thread(target=self._do_search, args=(keyword, req_id), daemon=True).start()

    def _do_search(self, keyword: str, req_id: int) -> None:
        try:
            data: dict[str, Any] = self.api.search_jlcpcb_components(
                keyword, page=1, page_size=_SEARCH_PAGE_SIZE
            )
            raw = data.get("result", data.get("results", []))
            results: list[Row] = raw.get("componentList", []) if isinstance(raw, dict) else raw
        except Exception as exc:
            msg = f"Error: {exc}"
            wx.CallAfter(lambda: self._search_done(req_id, [], msg))
            return
        wx.CallAfter(lambda: self._search_done(req_id, results, None))

    def _search_done(self, req_id: int, results: list[Row], error: str | None) -> None:
        if req_id != self._search_request_id:
            return  # superseded by a newer search
        self.btn_search.Enable()
        self.btn_filter.Enable()
        if error:
            self._set_status(error)
            return

        self._all_results = results
        self._filter_state = FilterState()
        self._sort_col = -1
        self._apply_filters()

    def _populate_list(self) -> None:
        self.list_ctrl.DeleteAllItems()
        for row in self._results:
            values = [_pick(row, keys) for (_, keys, _) in COLUMNS]
            idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), values[0])
            for col, val in enumerate(values[1:], start=1):
                self.list_ctrl.SetItem(idx, col, val)

    def _on_filter(self, _: wx.CommandEvent) -> None:
        if not self._all_results:
            return
        dlg = FilterDialog(self, self._all_results, self._filter_state)
        if dlg.ShowModal() == wx.ID_OK:
            self._filter_state = dlg.get_state()
            self._apply_filters()
        dlg.Destroy()

    def _apply_filters(self) -> None:
        self._results = [r for r in self._all_results if self._filter_state.matches(r)]
        self._sort_results()
        self._populate_list()
        label = "Filter ●" if self._filter_state.is_active else "Filter"
        self.btn_filter.SetLabel(label)
        total = len(self._all_results)
        shown = len(self._results)
        limit_hint = " (try a more specific search)" if total >= _SEARCH_PAGE_SIZE else ""
        if self._filter_state.is_active:
            self._set_status(
                f"{shown} of {total} result{'s' if total != 1 else ''} shown{limit_hint}."
            )
        else:
            self._set_status(f"{total} result{'s' if total != 1 else ''} found{limit_hint}.")

    def _sort_results(self) -> None:
        if self._sort_col < 0:
            return
        keys = COLUMNS[self._sort_col][1]

        def sort_key(row: Row) -> tuple[int, float | str]:
            val = _pick(row, keys)
            try:
                return (0, float(val))
            except (ValueError, TypeError):
                return (1, val.lower())

        self._results.sort(key=sort_key, reverse=not self._sort_asc)

    def _on_col_click(self, event: wx.ListEvent) -> None:
        col = event.GetColumn()
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._sort_results()
        self._populate_list()

    # ------------------------------------------------------------------
    # Detail view
    # ------------------------------------------------------------------

    def _on_item_selected(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        if 0 <= idx < len(self._results):
            row = self._results[idx]
            self.detail_panel.show_component(row)
            self._image_request_id += 1
            req_id = self._image_request_id
            lcsc_url = row.get("url", "")
            threading.Thread(
                target=self._fetch_image, args=(str(lcsc_url), req_id), daemon=True
            ).start()
            if self._on_select_cb is not None:
                lcsc = self.get_selected_lcsc()
                if lcsc:
                    self._on_select_cb(lcsc)

    def _fetch_image(self, lcsc_url: str, req_id: int) -> None:
        if lcsc_url in self._image_cache:
            wx.CallAfter(lambda: self._on_image_ready(req_id, self._image_cache[lcsc_url]))
            return

        data: bytes | None = None
        if lcsc_url:
            try:
                img_url = self.api.get_product_image_url(lcsc_url)
                if img_url:
                    req = urllib.request.Request(img_url, headers=self.api.headers)  # noqa: S310
                    with urllib.request.urlopen(  # noqa: S310
                        req, timeout=10, context=self.api.ssl_context
                    ) as r:
                        data = r.read()
                if data:
                    self._image_cache[lcsc_url] = data
                    if len(self._image_cache) > _IMAGE_CACHE_MAX:
                        self._image_cache.popitem(last=False)  # evict oldest
            except Exception as e:
                logging.debug(f"Image fetch failed for {lcsc_url}: {e}")
        wx.CallAfter(lambda: self._on_image_ready(req_id, data))

    def _on_image_ready(self, req_id: int, data: bytes | None) -> None:
        # Discard result if user has already selected a different component.
        if req_id == self._image_request_id:
            self.detail_panel.set_image(data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _on_list_resize(self, event: wx.SizeEvent) -> None:
        event.Skip()
        # Stretch the last column to fill any remaining horizontal space.
        total = self.list_ctrl.GetClientSize().width
        used = sum(
            self.list_ctrl.GetColumnWidth(i) for i in range(self.list_ctrl.GetColumnCount() - 1)
        )
        last = self.list_ctrl.GetColumnCount() - 1
        remaining = total - used
        if last >= 0 and remaining > COLUMNS[last][2]:
            self.list_ctrl.SetColumnWidth(last, remaining)

    def _set_status(self, msg: str) -> None:
        self.status.SetLabel(msg)
        self.Layout()

    def get_selected_lcsc(self) -> str | None:
        """Return the LCSC# of the currently selected item, or None."""
        idx = self.list_ctrl.GetFirstSelected()
        if idx == wx.NOT_FOUND:
            return None
        return self.list_ctrl.GetItemText(idx, 0) or None


# ---------------------------------------------------------------------------
# Dialog wrapper – used when embedded in the main plugin GUI
# ---------------------------------------------------------------------------


class SearchDialog(wx.Dialog):  # type: ignore[misc]
    """Wraps SearchPanel in a dialog.

    Parameters
    ----------
    on_select:
        Optional callback called immediately whenever the user clicks a row in
        the result list.  Receives the LCSC# string of the selected component.
    """

    def __init__(
        self,
        parent: wx.Window,
        on_select: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(
            parent,
            title="Component Search",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.panel = SearchPanel(self, on_select=on_select)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self.panel, 1, wx.EXPAND)
        self.SetSizer(root)

        w = parent.GetTopLevelParent().GetSize().width
        self.SetSize(wx.Size(max(w, 800), 600))
        self.Centre()

    def get_lcsc(self) -> str | None:
        return self.panel.get_selected_lcsc()


# ---------------------------------------------------------------------------
# Standalone window (for testing)
# ---------------------------------------------------------------------------


class SearchFrame(wx.Frame):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__(
            None,
            title="Component Search (test)",
            size=wx.Size(800, 600),
            style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER,
        )
        self.search_panel = SearchPanel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.search_panel, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.Centre()


if __name__ == "__main__":
    app = wx.App(False)
    frame = SearchFrame()
    frame.Show()
    app.MainLoop()

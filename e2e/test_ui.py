"""Browser round trips: create, read, edit, persist, delete — plus an XSS probe."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

CONCEPT = "Wandering tea merchant of the salt roads"
XSS_CONCEPT = "<script>alert(1)</script> probe"
EDITED = "Rewritten by hand: the merchant never left the coast."
SECTIONS = ("profile", "background", "voice", "lines", "palette", "world", "prompt")


# The app ships CSP `default-src 'self'`, which forbids eval in the page. That
# rules out page.wait_for_function / page.evaluate with a JS string, so every
# wait and assertion below goes through locators.
def home(page: Page, server: str) -> None:
    page.goto(server + "/#/")
    expect(page.locator("#view-home")).to_be_visible()


def create_book(page: Page, server: str, concept: str) -> None:
    home(page, server)
    page.fill("#f-concept", concept)
    page.click("#f-submit")
    expect(page.locator("#view-detail")).to_be_visible()
    expect(page.locator("#detail-status")).to_have_text("draft")


def field_value(page: Page, field: str):
    return page.locator(f'[data-field="{field}"] .field-value')


def edit_field(page: Page, field: str, text: str) -> None:
    row = page.locator(f'[data-field="{field}"]')
    row.get_by_role("button", name="Edit").click()
    row.locator("textarea").fill(text)
    row.get_by_role("button", name="Save").click()


def delete_first_card(page: Page) -> None:
    page.locator(".card-actions").first.get_by_role("button", name="Delete").click()
    page.locator(".confirm-bar").first.get_by_role("button", name="Delete").click()


def test_full_book_round_trip(page: Page, server: str) -> None:
    home(page, server)
    expect(page.locator("#book-empty")).to_be_visible()
    expect(page.locator("#book-count")).to_have_text("0")

    create_book(page, server, CONCEPT)
    expect(page.locator("#detail-title")).to_have_text(CONCEPT)
    for name in SECTIONS:
        expect(page.locator(f"#section-{name}")).to_be_visible()
    expect(page.locator("#section-palette .swatch")).to_have_count(4)
    expect(page.locator("#section-lines .line-item")).to_have_count(5)
    expect(page.locator("#master-prompt")).to_contain_text(CONCEPT)
    expect(page.locator("#copy-prompt")).to_be_visible()
    expect(page.locator("#detail-render")).to_be_disabled()
    expect(page.locator("#detail-export")).to_be_disabled()

    edit_field(page, "background", EDITED)
    expect(field_value(page, "background")).to_have_text(EDITED)

    page.reload()
    expect(field_value(page, "background")).to_have_text(EDITED)

    page.click("#detail-back-link")
    expect(page.locator(".card")).to_have_count(1)
    expect(page.locator(".card .swatch")).to_have_count(4)
    delete_first_card(page)
    expect(page.locator(".card")).to_have_count(0)
    expect(page.locator("#book-empty")).to_be_visible()
    expect(page.locator("#book-count")).to_have_text("0")


def test_hostile_text_stays_literal(page: Page, server: str) -> None:
    dialogs: list = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))

    create_book(page, server, XSS_CONCEPT)
    expect(page.locator("#detail-title")).to_have_text(XSS_CONCEPT)
    expect(field_value(page, "background")).to_contain_text("<script>alert(1)</script>")

    scripts = page.locator("script")
    bodies = [scripts.nth(index).text_content() or "" for index in range(scripts.count())]
    assert not any("alert(1)" in body for body in bodies)
    assert dialogs == []

    home(page, server)
    expect(page.locator(".card-title")).to_have_text(XSS_CONCEPT)
    delete_first_card(page)
    expect(page.locator(".card")).to_have_count(0)


def test_lines_bounds_and_palette_validation(page: Page, server: str) -> None:
    create_book(page, server, CONCEPT)

    # the fake bible has the minimum 5 lines, so Remove is off and Add is on
    lines = page.locator("#section-lines")
    expect(lines.get_by_role("button", name="Remove").first).to_be_disabled()
    lines.get_by_role("button", name="Add line").click()
    expect(page.locator("#section-lines .line-item")).to_have_count(6)
    lines.get_by_role("button", name="Remove").first.click()
    expect(page.locator("#section-lines .line-item")).to_have_count(5)

    row = page.locator('[data-field="palette.0.hex"]')
    row.get_by_role("button", name="Edit").click()
    row.locator("input").fill("not-a-hex")
    row.get_by_role("button", name="Save").click()
    expect(page.locator("#notice")).to_contain_text("#RRGGBB")
    expect(page.locator('[data-field="palette.0.hex"] .field-value')).to_have_text("#2f3a4f")

    home(page, server)
    delete_first_card(page)
    expect(page.locator(".card")).to_have_count(0)

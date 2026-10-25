"""The interface languages (spec 09 §14): German, French and Italian next to English, tag names in a language of their
own, and catalogues that are complete and built."""

import json

import pytest

from spaced_positions.core import i18n_catalog
from spaced_positions.core.models import Preferences
from spaced_positions.library.models import Tag

pytestmark = pytest.mark.django_db


def set_settings(**values):
    Preferences.objects.update_or_create(pk=Preferences.current().pk, defaults={"settings": values})


def test_the_language_setting_switches_pages_messages_and_the_js_catalogue(client):
    html = client.get("/m/home/").content.decode()
    assert "Due now" in html
    set_settings(**{"ui.language": "de"})
    page = client.get("/home/").content.decode()
    assert '<html lang="de"' in page and 'id="i18n"' in page and "Bibliothek" in page
    assert "Jetzt fällig" in client.get("/m/home/").content.decode()
    catalogue = json.loads(page.split('id="i18n" type="application/json">')[1].split("</script>")[0])
    assert catalogue["Engine off"] == "Engine aus"
    reply = client.post("/cmd/pref.set/", json.dumps({"args": ["nonsense=1"], "context": {}}), content_type="application/json").json()
    assert reply["message"] == "unbekannte Einstellung «nonsense»"
    set_settings(**{"ui.language": "it"})
    assert "Da ripassare ora" in client.get("/m/home/").content.decode()


def test_automatic_follows_the_browser(client):
    assert '<html lang="fr"' in client.get("/home/", HTTP_ACCEPT_LANGUAGE="fr-CH,fr;q=0.9").content.decode()
    assert '<html lang="en"' in client.get("/home/", HTTP_ACCEPT_LANGUAGE="ja").content.decode()


def test_tag_names_follow_the_app_or_their_own_language(client):
    fork = Tag.objects.get(key="fork")
    assert (fork.name, fork.name_en, fork.name_fr, fork.name_it) == ("Gabel", "Fork", "Fourchette", "Forchetta")
    set_settings(**{"ui.language": "fr"})
    assert "Fourchette" in client.get("/lib/results/", {"c": "tags", "q": "fork"}).content.decode()
    set_settings(**{"ui.language": "en", "tags.language": "de"})
    html = client.get("/lib/results/", {"c": "tags", "q": "fork"}).content.decode()
    assert ">Gabel" in html and "Fork" in html  # the other names show muted


def test_swiss_german_spelling():
    assert Tag.objects.get(key="skewer").name == "Spiess" and "Spieß" in Tag.objects.get(key="skewer").aliases


def test_catalogues_are_complete_and_built():
    assert i18n_catalog.check() == []

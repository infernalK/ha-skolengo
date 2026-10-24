import requests

from custom_components.skolengo.api import SkolengoBirthdateRequired, SkolengoClient

# Shape of ÉduConnect's "Confirmation de l'identité" page (parent account):
# its script copies the date into the hidden `j_password` as YYYY-MM-DD.
PAGE = """<html><title>Confirmation de l'identité - ÉduConnect</title><body>
<form action="/idp/profile/SAML2/POST/SSO?execution=e1s3" method="post">
<input type="hidden" name="csrf_token" value="tok">
<input type="hidden" name="j_username" value="parent">
<input type="hidden" name="j_password" value="">
<fieldset><legend><p id="nomEleve">Jean DUPONT</p></legend>
<input name="jour" type="number"><input name="mois" type="number"><input name="annee" type="number">
</fieldset>
<button type="submit" name="_eventId_proceed">Confirmer</button>
<button type="submit" name="_eventId_RestartAuthentication">Précédent</button>
</form></body></html>"""


class _Response:
    url = "https://educonnect.education.gouv.fr/idp/profile/SAML2/POST/SSO?execution=e1s3"
    status_code = 200
    text = PAGE


def _submit(monkeypatch, birthdates):
    sent = {}

    def fake_submit(session, url, method, form_data):
        sent.update(form_data)
        return "response"

    monkeypatch.setattr(SkolengoClient, "_submit_form", staticmethod(fake_submit))
    SkolengoClient._fill_and_submit_form(
        requests.Session(), _Response(), "u", "p", True, "", birthdates
    )
    return sent


def test_birthdate_is_copied_into_hidden_j_password(monkeypatch):
    sent = _submit(monkeypatch, {"jean dupont": (5, 3, 2012)})
    assert sent["j_password"] == "2012-03-05"
    assert (sent["jour"], sent["mois"], sent["annee"]) == ("05", "03", "2012")
    assert sent["j_username"] == "parent"
    assert sent["csrf_token"] == "tok"
    assert "_eventId_proceed" in sent
    assert "_eventId_RestartAuthentication" not in sent


def test_unknown_pupil_asks_for_the_date(monkeypatch):
    try:
        _submit(monkeypatch, {})
    except SkolengoBirthdateRequired as err:
        assert err.student_name == "Jean DUPONT"
    else:
        raise AssertionError("expected SkolengoBirthdateRequired")

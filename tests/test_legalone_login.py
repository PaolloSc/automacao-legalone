from legalone_cadastro import LOGIN_URL, LegalOneCadastro


class FakeElement:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def click(self):
        self.events.append((self.name, "click"))

    def fill(self, value):
        self.events.append((self.name, "fill", value))


class FakePage:
    def __init__(self):
        self.events = []

    def wait_for_selector(self, selector, timeout=0):
        self.events.append(("wait", selector, timeout))
        if selector == 'input#username, input[name="username"], input[type="email"]':
            return FakeElement("username", self.events)
        if selector == 'button._button-login-id, button[name="action"][type="submit"]':
            return FakeElement("email_submit", self.events)
        if selector == 'input#password, input[name="password"], input[type="password"]':
            return FakeElement("password", self.events)
        if selector == 'button._button-login-password, button[name="action"][type="submit"]':
            return FakeElement("password_submit", self.events)
        raise AssertionError(f"unexpected selector: {selector}")

    def wait_for_load_state(self, state, timeout=0):
        self.events.append(("load_state", state, timeout))


class FakeOldSignonPage:
    def __init__(self):
        self.events = []

    def wait_for_selector(self, selector, timeout=0):
        self.events.append(("wait", selector, timeout))
        if selector == 'input#username, input[name="username"], input[type="email"]':
            raise TimeoutError("new auth field absent")
        if selector == 'input:visible':
            return FakeElement("old_username", self.events)
        if selector == 'input#password, input[name="password"], input[type="password"]':
            return FakeElement("new_password_after_old_username", self.events)
        if selector == 'input[type="password"]':
            return FakeElement("old_password", self.events)
        if selector == 'button._button-login-password, button[name="action"][type="submit"]':
            return FakeElement("new_password_submit", self.events)
        if selector == 'button[type="submit"], input[type="submit"]':
            return FakeElement("old_submit", self.events)
        raise AssertionError(f"unexpected selector: {selector}")

    def wait_for_load_state(self, state, timeout=0):
        self.events.append(("load_state", state, timeout))


def test_login_url_usa_entrada_estavel_do_tenant_sem_state_fixo():
    assert LOGIN_URL == "https://carvalhofurtadoadv.novajus.com.br/"
    assert "state=" not in LOGIN_URL
    assert "signon.thomsonreuters.com" not in LOGIN_URL


def test_fazer_login_fluxo_auth0_email_depois_senha(monkeypatch):
    monkeypatch.setattr("legalone_cadastro.time.sleep", lambda *_args, **_kwargs: None)
    cad = LegalOneCadastro(username="seu_email@exemplo.com", password="senha")
    page = FakePage()
    cad.page = page

    assert cad.fazer_login() is True

    assert ("username", "fill", "seu_email@exemplo.com") in page.events
    assert ("email_submit", "click") in page.events
    assert ("password", "fill", "senha") in page.events
    assert ("password_submit", "click") in page.events
    assert page.events.index(("email_submit", "click")) < page.events.index(("password", "fill", "senha"))


def test_fazer_login_fallback_tela_legal_one_firm_antiga(monkeypatch):
    monkeypatch.setattr("legalone_cadastro.time.sleep", lambda *_args, **_kwargs: None)
    cad = LegalOneCadastro(username="seu_email@exemplo.com", password="senha")
    page = FakeOldSignonPage()
    cad.page = page

    assert cad.fazer_login() is True

    assert ("old_username", "fill", "seu_email@exemplo.com") in page.events
    assert ("new_password_after_old_username", "fill", "senha") in page.events
    assert ("new_password_submit", "click") in page.events

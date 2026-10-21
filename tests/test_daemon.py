import stat

from tabsidebar.daemon import load_or_create_token


def test_token_is_created_private_to_the_user_and_reused_across_restarts(tmp_path):
    path = tmp_path / "token"

    first = load_or_create_token(path)
    second = load_or_create_token(path)

    assert first and first == second
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_an_empty_token_file_gets_a_fresh_private_token(tmp_path):
    path = tmp_path / "token"
    path.write_text("")
    path.chmod(0o644)

    token = load_or_create_token(path)

    assert token and path.read_text() == token
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

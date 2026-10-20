"""Password hashing uses only the standard library but reads Werkzeug-style hashes,
so data files from the earlier Flask version still sign in."""

import pytest

from foodshare.passwords import check_password, hash_password


def test_hash_and_check():
    stored = hash_password("password123")
    assert stored.startswith("scrypt:") and "password123" not in stored
    assert check_password(stored, "password123")
    assert not check_password(stored, "password124")


def test_two_hashes_of_one_password_differ():
    assert hash_password("same") != hash_password("same")


@pytest.mark.parametrize("stored", ["", "nonsense", "md5$x$y", "scrypt:abc$s$h", None])
def test_broken_hashes_never_match(stored):
    assert not check_password(stored, "anything")


# Made by Werkzeug's generate_password_hash("password123"), as the Flask version did.
WERKZEUG_HASHES = [
    "scrypt:32768:8:1$MoxZsw2GYW9Os5EQ$ce00659c1b0f814aedcd9c1b866c24a61ab1d63cf4c666c04a5d3b5f5c6ae1b81eada8a47811edddb89734231f9b21ef433318e963eaefd9e5dc254905ca8b65",
    "pbkdf2:sha256:1000000$wGl7cLDIlsxW07pB$16a989785d1116e73f36e424064cdfa468c2f0a363f62adb2c04ce86530d2ac8",
]


@pytest.mark.parametrize("stored", WERKZEUG_HASHES)
def test_reads_hashes_from_the_flask_version(stored):
    assert check_password(stored, "password123")
    assert not check_password(stored, "password124")

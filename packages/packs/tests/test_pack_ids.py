from novaxis_packs import PACK_IDS


def test_three_packs_are_planned() -> None:
    assert PACK_IDS == ("hvac", "dental", "restoration")

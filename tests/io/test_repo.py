from datetime import date

from engine.io.repo import SupabaseRepo
from tests.io.fake_supabase import FakeClient


def test_lecture_paginee_recupere_toutes_les_lignes():
    players = [{"id": i} for i in range(2500)]
    repo = SupabaseRepo(FakeClient({"players": players}))
    assert len(repo.load_players()) == 2500


def test_upsert_par_lots_de_500():
    client = FakeClient()
    SupabaseRepo(client).upsert_game_logs([{"player_id": i, "game_id": "g"} for i in range(1200)])
    assert client.ops == [
        ("upsert", "game_logs", 500, "player_id,game_id"),
        ("upsert", "game_logs", 500, "player_id,game_id"),
        ("upsert", "game_logs", 200, "player_id,game_id"),
    ]


def test_replace_nights_upsert_puis_supprime_les_obsoletes():
    # M2 (final review) : upsert des nouvelles lignes d'abord, purge des
    # soirées obsolètes ensuite — un échec de l'insert ne doit jamais laisser
    # la soirée du jour sans ligne `nights`.
    client = FakeClient()
    SupabaseRepo(client).replace_nights(date(2026, 11, 10), [{"date": "2026-11-10"}])
    assert [op[0] for op in client.ops] == ["upsert", "delete"]
    assert client.ops[0] == ("upsert", "nights", 1, "date")


def test_replace_nights_vide_supprime_seulement():
    client = FakeClient()
    SupabaseRepo(client).replace_nights(date(2026, 11, 10), [])
    assert [op[0] for op in client.ops] == ["delete"]


def test_replace_recommendations_supprime_puis_insere():
    client = FakeClient()
    SupabaseRepo(client).replace_recommendations(date(2026, 11, 10), [{"player_id": 1}])
    assert [op[0] for op in client.ops] == ["delete", "insert"]


def test_replace_recommendations_vide_supprime_seulement():
    client = FakeClient()
    SupabaseRepo(client).replace_recommendations(date(2026, 11, 10), [])
    assert [op[0] for op in client.ops] == ["delete"]


def test_game_ids_with_logs_sans_ids_ne_requete_pas():
    client = FakeClient()
    assert SupabaseRepo(client).game_ids_with_logs(set()) == set()


def test_start_log_renvoie_l_id():
    assert SupabaseRepo(FakeClient()).start_log("daily_sync") == 42


def test_game_ids_with_logs_retourne_les_ids_presents():
    game_logs = [
        {"id": 1, "game_id": "g1"},
        {"id": 2, "game_id": "g1"},
        {"id": 3, "game_id": "g2"},
    ]
    repo = SupabaseRepo(FakeClient({"game_logs": game_logs}))
    assert repo.game_ids_with_logs({"g1", "g2", "g3"}) == {"g1", "g2"}

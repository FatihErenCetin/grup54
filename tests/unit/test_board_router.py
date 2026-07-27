from fastapi.testclient import TestClient

from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.store.models import Base, TaskProjectionRow


def test_get_board_returns_cards_successfully(tmp_path):
    db_path = tmp_path / "test_board.db"
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    app = create_app(settings)

    with TestClient(app) as client:
        engine = app.state.session_factory.kw["bind"]
        Base.metadata.create_all(engine)

        with app.state.session_factory() as session:
            session.add(TaskProjectionRow(task_id="T-51", title="Board API", status="in_progress"))
            session.commit()

        response = client.get("/board")

        assert response.status_code == 200
        data = response.json()
        assert "cards" in data
        assert len(data["cards"]) == 1
        assert data["cards"][0]["task_id"] == "T-51"
        assert data["cards"][0]["title"] == "Board API"

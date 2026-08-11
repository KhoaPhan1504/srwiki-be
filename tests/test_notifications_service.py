from app.notifications import create_notification


def test_create_notification_inserts_row(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.notifications.admin_client", return_value=fake_admin)

    create_notification(
        "user-1",
        "phone_verified",
        "Title",
        "Message",
        metadata={"phone": "+84912345678"},
    )

    fake_admin.table.assert_called_once_with("notifications")
    insert_call = fake_admin.table.return_value.insert.call_args[0][0]
    assert insert_call["user_id"] == "user-1"
    assert insert_call["type"] == "phone_verified"
    assert insert_call["title"] == "Title"
    assert insert_call["message"] == "Message"
    assert insert_call["metadata"] == {"phone": "+84912345678"}
    fake_admin.table.return_value.insert.return_value.execute.assert_called_once()


def test_create_notification_defaults_metadata_to_empty_dict(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.notifications.admin_client", return_value=fake_admin)

    create_notification("user-1", "avatar_updated", "Title", "Message")

    insert_call = fake_admin.table.return_value.insert.call_args[0][0]
    assert insert_call["metadata"] == {}

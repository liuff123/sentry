import datetime
import uuid

import pytest
from django.urls import reverse

from sentry.replays.testutils import mock_replay
from sentry.testutils import APITestCase, SnubaTestCase
from sentry.testutils.cases import ReplaysSnubaTestCase
from sentry.testutils.helpers.datetime import before_now, iso_format
from sentry.testutils.silo import region_silo_test

pytestmark = pytest.mark.sentry_metrics


@region_silo_test
class OrganizationIssueReplayCountEndpoint(APITestCase, SnubaTestCase, ReplaysSnubaTestCase):
    def setUp(self):
        super().setUp()
        self.min_ago = before_now(minutes=1)
        self.login_as(user=self.user)
        self.url = reverse(
            "sentry-api-0-organization-issue-replay-count",
            kwargs={"organization_slug": self.project.organization.slug},
        )
        self.features = {"organizations:session-replay": True}

    def test_simple(self):
        event_id_a = "a" * 32
        event_id_b = "b" * 32
        replay1_id = uuid.uuid4().hex
        replay2_id = uuid.uuid4().hex
        replay3_id = uuid.uuid4().hex

        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                replay1_id,
            )
        )
        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                replay2_id,
            )
        )
        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                replay3_id,
            )
        )
        event_a = self.store_event(
            data={
                "event_id": event_id_a,
                "timestamp": iso_format(self.min_ago),
                "tags": {"replayId": replay1_id},
                "fingerprint": ["group-1"],
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid.uuid4().hex,
                "timestamp": iso_format(self.min_ago),
                "tags": {"replayId": replay2_id},
                "fingerprint": ["group-1"],
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": event_id_b,
                "timestamp": iso_format(self.min_ago),
                "tags": {"replayId": "z" * 32},  # a replay id that doesn't exist
                "fingerprint": ["group-1"],
            },
            project_id=self.project.id,
        )
        event_c = self.store_event(
            data={
                "event_id": event_id_b,
                "timestamp": iso_format(self.min_ago),
                "tags": {"replayId": replay3_id},
                "fingerprint": ["group-2"],
            },
            project_id=self.project.id,
        )

        query = {"query": f"issue.id:[{event_a.group.id}, {event_c.group.id}]"}
        with self.feature(self.features):
            response = self.client.get(self.url, query, format="json")

        expected = {
            event_a.group.id: 2,
            event_c.group.id: 1,
        }
        assert response.status_code == 200, response.content
        assert response.data == expected

    def test_one_replay_multiple_issues(self):
        event_id_a = "a" * 32
        event_id_b = "b" * 32
        replay1_id = uuid.uuid4().hex

        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                replay1_id,
            )
        )
        event_a = self.store_event(
            data={
                "event_id": event_id_a,
                "timestamp": iso_format(self.min_ago),
                "tags": {"replayId": replay1_id},
                "fingerprint": ["group-1"],
            },
            project_id=self.project.id,
        )
        event_b = self.store_event(
            data={
                "event_id": event_id_b,
                "timestamp": iso_format(self.min_ago),
                "tags": {"replayId": replay1_id},
                "fingerprint": ["group-2"],
            },
            project_id=self.project.id,
        )

        query = {"query": f"issue.id:[{event_a.group.id}, {event_b.group.id}]"}
        with self.feature(self.features):
            response = self.client.get(self.url, query, format="json")

        expected = {
            event_a.group.id: 1,
            event_b.group.id: 1,
        }
        assert response.status_code == 200, response.content
        assert response.data == expected

    def test_one_replay_same_issue_twice(self):
        event_id_a = "a" * 32
        event_id_b = "b" * 32
        replay1_id = uuid.uuid4().hex

        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                replay1_id,
            )
        )
        event_a = self.store_event(
            data={
                "event_id": event_id_a,
                "timestamp": iso_format(self.min_ago),
                "tags": {"replayId": replay1_id},
                "fingerprint": ["group-1"],
            },
            project_id=self.project.id,
        )
        event_b = self.store_event(
            data={
                "event_id": event_id_b,
                "timestamp": iso_format(self.min_ago),
                "tags": {"replayId": replay1_id},
                "fingerprint": ["group-1"],
            },
            project_id=self.project.id,
        )

        query = {"query": f"issue.id:[{event_a.group.id}, {event_b.group.id}]"}
        with self.feature(self.features):
            response = self.client.get(self.url, query, format="json")

        expected = {
            event_a.group.id: 1,
        }
        assert response.status_code == 200, response.content
        assert response.data == expected

    def test_max_51(self):
        replay_ids = [uuid.uuid4().hex for _ in range(100)]
        for replay_id in replay_ids:
            self.store_replays(
                mock_replay(
                    datetime.datetime.now() - datetime.timedelta(seconds=22),
                    self.project.id,
                    replay_id,
                )
            )
            event_a = self.store_event(
                data={
                    "event_id": uuid.uuid4().hex,
                    "timestamp": iso_format(self.min_ago),
                    "tags": {"replayId": replay_id},
                    "fingerprint": ["group-1"],
                },
                project_id=self.project.id,
            )

        query = {"query": f"issue.id:[{event_a.group.id}]"}
        with self.feature(self.features):
            response = self.client.get(self.url, query, format="json")

        expected = {
            event_a.group.id: 51,
        }
        assert response.status_code == 200, response.content
        assert response.data == expected

    def test_invalid_params_need_one_issue_id(self):
        query = {"query": ""}
        with self.feature(self.features):
            response = self.client.get(self.url, query, format="json")
            assert response.status_code == 400
            assert response.data["detail"] == "Must provide at least one issue id"

    def test_invalid_params_max_issue_id(self):
        issue_ids = ",".join(str(i) for i in range(26))

        query = {"query": f"issue.id:[{issue_ids}]"}

        with self.feature(self.features):
            response = self.client.get(self.url, query, format="json")
            assert response.status_code == 400
            assert response.data["detail"] == "Too many issues ids provided"

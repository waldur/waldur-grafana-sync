import logging
import os
import sys
from functools import lru_cache, cached_property

from waldur_client import WaldurClient
from backend import Backend, User


handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger(__name__)
formatter = logging.Formatter("[%(levelname)s] [%(asctime)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

WALDUR_API_URL = os.environ["WALDUR_API_URL"]
WALDUR_API_TOKEN = os.environ["WALDUR_API_TOKEN"]

REGISTRATION_METHOD = os.environ["REGISTRATION_METHOD"]
STAFF_TEAM_NAME = os.environ.get("STAFF_TEAM_NAME", 'staff')
SUPPORT_TEAM_NAME = os.environ.get("SUPPORT_TEAM_NAME", 'support')
ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", 'admin')
# ISSUE_TYPE = os.environ.get("ISSUE_TYPE", "Incident")
# ISSUE_ID_PREFIX = os.environ.get("ISSUE_ID_PREFIX", "RT_ID")
# WALDUR_COMMENT_UUID_PREFIX = os.environ.get("WALDUR_COMMENT_UUID_PREFIX", "WALDUR_COMMENT_UUID")
# WALDUR_COMMENT_MARKER = os.environ.get("WALDUR_COMMENT_MARKER", "THIS IS WALDUR COMMENT.")


class Sync:
    @cached_property
    def backend_client(self):
        return Backend()

    @cached_property
    def waldur_client(self):
        return WaldurClient(WALDUR_API_URL, WALDUR_API_TOKEN)

    @cached_property
    def waldur_staff_users(self):
        return self.waldur_client.list_users(
                    {
                        'is_active': True,
                        'is_staff': True,
                        'registration_method': REGISTRATION_METHOD,
                        'page_size': 10000,
                    }
                )

    @cached_property
    def waldur_support_users(self):
        return self.waldur_client.list_users(
                    {
                        'is_active': True,
                        'is_support': True,
                        'registration_method': REGISTRATION_METHOD,
                        'page_size': 10000,
                    }
                )

    @cached_property
    def waldur_users(self):
        return self.waldur_staff_users + self.waldur_support_users

    def run(self):
        self.sync_users()
        self.sync_staff_team()
        self.sync_support_team()

    def sync_users(self):
        backend_users = self.backend_client.list_users()
        for backend_user in backend_users:
            if backend_user['email'] not in [waldur_user['email'] for waldur_user in self.waldur_users] and \
                    backend_user['login'] != ADMIN_LOGIN:
                self.backend_client.delete_user(backend_user['id'])

        for waldur_user in self.waldur_users:
            if waldur_user['email'] not in [backend_user['email'] for backend_user in backend_users]:
                self.backend_client.create_user(
                    email=waldur_user['email'],
                    name=waldur_user['full_name'],
                    login=waldur_user['username']
                )

    def _sync_teams(self, team_name, waldur_users):
        if not self.backend_client.list_teams(team_name):
            staff_team_id = self.backend_client.create_team(team_name)['teamId']
        else:
            staff_team_id = self.backend_client.list_teams(team_name)[0]['id']

        members = self.backend_client.get_team_members(staff_team_id)

        for member in members:
            if member['email'] not in [s['email'] for s in waldur_users]:
                self.backend_client.remove_team_member(staff_team_id, member['userId'])

        for s in waldur_users:
            if s['email'] not in [member['email'] for member in members]:
                self.backend_client.create_team_member(staff_team_id, s['full_name'], s['username'], s['email'])

    def sync_staff_team(self):
        self._sync_teams(
            team_name=STAFF_TEAM_NAME,
            waldur_users=self.waldur_staff_users,

        )

    def sync_support_team(self):
        self._sync_teams(
            team_name=SUPPORT_TEAM_NAME,
            waldur_users=self.waldur_support_users,

        )

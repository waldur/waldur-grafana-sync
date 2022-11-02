import os
import secrets
import string
from dataclasses import dataclass
from urllib.parse import urlparse

from grafana_api.grafana_face import GrafanaFace
from grafana_api.grafana_api import GrafanaClientError

BACKEND_API_URL = os.environ['BACKEND_API_URL']
BACKEND_API_USER = os.environ['BACKEND_API_USER']
BACKEND_API_PASSWORD = os.environ['BACKEND_API_PASSWORD']


@dataclass
class User:
    id: str
    login: str
    email: str
    name: str = ''
    is_admin: bool = False
    is_support: bool = False
    is_disabled: bool = True


class Backend:
    def __init__(self):
        url = urlparse(BACKEND_API_URL)
        self.manager = GrafanaFace(
            auth=(BACKEND_API_USER, BACKEND_API_PASSWORD),
            host=url.hostname,
            port=url.port,
            protocol=url.scheme,
        )

    def create_team(self, name):
        return self.manager.teams.add_team({'name': name})

    def list_teams(self, name=None):
        return self.manager.teams.search_teams(name)

    def get_team_members(self, team_id):
        return self.manager.teams.get_team_members(team_id)

    def remove_team_member(self, team_id, user_id):
        return self.manager.teams.remove_team_member(team_id, user_id)

    def add_team_member(self, team_id, user_id_or_email):
        try:
            user_id = int(user_id_or_email)
        except ValueError:
            user = self.manager.users.find_user(user_id_or_email)
            user_id = user['id']

        return self.manager.teams.add_team_member(team_id, user_id)

    def create_team_member(self, team_id, name, login, email):
        try:
            user = self.manager.users.find_user(email)
            user_id = user['id']
        except GrafanaClientError:
            response = self.create_user(name, login, email)
            user_id = response['id']

        return self.manager.teams.add_team_member(team_id, user_id)

    def list_users(self):
        return self.manager.users.search_users()

    def delete_user(self, user_id):
        return self.manager.admin.delete_user(user_id)

    def create_user(self, name, login, email):
        payload = {
            "name": name,
            "email": email,
            "login": login,
            "password": self._generate_password(),
        }
        return self.manager.admin.create_user(payload)

    def _generate_password(self):
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for i in range(20))

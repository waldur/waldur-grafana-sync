import os
import secrets
import string
from urllib.parse import urlparse

from grafana_api.grafana_api import GrafanaClientError
from grafana_api.grafana_face import GrafanaFace

BACKEND_API_URL = os.environ['BACKEND_API_URL']
BACKEND_API_USER = os.environ['BACKEND_API_USER']
BACKEND_API_PASSWORD = os.environ['BACKEND_API_PASSWORD']


class Backend:
    def __init__(self):
        url = urlparse(BACKEND_API_URL)
        self.manager = GrafanaFace(
            auth=(BACKEND_API_USER, BACKEND_API_PASSWORD),
            host=url.hostname,
            port=url.port,
            protocol=url.scheme,
        )

    def list_folders(self):
        return self.manager.folder.get_all_folders()

    def create_folder(self, title, uid=None):
        return self.manager.folder.create_folder(title, uid)

    def delete_folder(self, uid):
        return self.manager.folder.delete_folder(uid)

    def update_folder(self, uid, title):
        return self.manager.folder.update_folder(uid, title, overwrite=True)

    def add_folder_team_permission(self, uid, team_name):
        existing_permissions = self.manager.folder.get_folder_permissions(uid)
        team = self.list_teams(team_name)
        new_permissions = [{'teamId': team[0]['id'], 'permission': 1}]
        for p in existing_permissions:
            if 'role' in p:
                new_permissions.append(
                    {'role': p['role'], 'permission': p['permission']}
                )
            elif p['userId']:
                new_permissions.append(
                    {'userId': p['userId'], 'permission': p['permission']},
                )
            elif p['teamId']:
                new_permissions.append(
                    {'teamId': p['teamId'], 'permission': p['permission']},
                )
            else:
                print('Failed to detect permission', p)
        self.manager.folder.update_folder_permissions(uid, {'items': new_permissions})

    def create_team(self, name):
        return self.manager.teams.add_team({'name': name})

    def list_teams(self, name=None):
        return self.manager.teams.search_teams(name)

    def delete_teams(self, id_or_name):
        try:
            team_id = int(id_or_name)
        except ValueError:
            team = self.manager.teams.get_team_by_name(id_or_name)

            if not team or len(team) > 1:
                return

            team_id = team[0]['id']
        return self.manager.teams.delete_team(team_id)

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

    def list_user_teams(self, user_id):
        # XXX: Dirty hack, but SDK doesn't have a method for user teams
        return self.manager.users.get_user(f'{user_id}/teams')

    def delete_user(self, user_id):
        return self.manager.admin.delete_user(user_id)

    def create_user(self, name, login, email):
        payload = {
            'name': name,
            'email': email,
            'login': login,
            'password': self._generate_password(),
        }
        return self.manager.admin.create_user(payload)

    def _generate_password(self):
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for i in range(20))

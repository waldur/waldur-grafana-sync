import logging
import os
import sys
from dataclasses import dataclass, field
from functools import cached_property

from waldur_client import WaldurClient

from backend import Backend, BACKEND_API_USER

handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger(__name__)
formatter = logging.Formatter("[%(levelname)s] [%(asctime)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

WALDUR_API_URL = os.environ['WALDUR_API_URL']
WALDUR_API_TOKEN = os.environ['WALDUR_API_TOKEN']

REGISTRATION_METHOD = os.environ.get('REGISTRATION_METHOD', 'eduteams')
STAFF_TEAM_NAME = os.environ.get('STAFF_TEAM_NAME', 'staff')
SUPPORT_TEAM_NAME = os.environ.get('SUPPORT_TEAM_NAME', 'support')

PROTECTED_USERNAMES = os.environ.get('PROTECTED_USERNAMES', 'admin,' + BACKEND_API_USER).split(',')
PROTECTED_TEAMS = os.environ.get('PROTECTED_TEAMS', 'Development,Management').split(',')

DRY_RUN = False


@dataclass
class Organisation:
    uuid: str
    name: str
    division: str = ''


@dataclass
class User:
    uuid: str
    username: str
    email: str
    name: str
    is_staff: bool
    is_support: bool
    organizations: list[Organisation] = field(default_factory=list)


class Sync:
    @cached_property
    def grafana_client(self):
        return Backend()

    @cached_property
    def waldur_client(self):
        return WaldurClient(WALDUR_API_URL, WALDUR_API_TOKEN)

    def run(self):
        self.sync_users()
        self.sync_staff_team()
        self.sync_support_team()
        self.sync_organization_teams()

    @property
    def waldur_staff_users(self):
        return [user for user in self.waldur_users if user.is_staff]

    @property
    def waldur_support_users(self):
        return [user for user in self.waldur_users if user.is_support]

    @cached_property
    def waldur_users(self):
        result = []
        query = {
            'registration_method': REGISTRATION_METHOD,
            'is_active': True,
            'field': ['customer_permissions', 'is_staff', 'is_support', 'username', 'uuid', 'full_name', 'email'],
        }

        for item in self.waldur_client.list_users(query):
            organizations = [
                Organisation(p['customer_uuid'], p['customer_name'], p.get('customer_division_name', ''))
                for p in item['customer_permissions'] if p['role'] == 'owner'
            ]
            # temporary workaround till waldur API is updated
            for o in organizations:
                if o.division == '':
                    o.division = self.waldur_client.get_customer(o.uuid).get('division_name', '')

            if not item['is_staff'] and not item['is_support'] and not organizations:
                continue

            result.append(
                User(
                    uuid=item['uuid'],
                    username=item['username'],
                    email=item['email'],
                    name=item['full_name'],
                    is_staff=item['is_staff'],
                    is_support=item['is_support'],
                    organizations=organizations,
                )
            )
        return result

    def sync_users(self):
        grafana_users = self.grafana_client.list_users()
        waldur_usernames = [waldur_user.username for waldur_user in self.waldur_users]
        for grafana_user in grafana_users:
            if grafana_user['login'] not in waldur_usernames and grafana_user['login'] not in PROTECTED_USERNAMES:
                if not DRY_RUN:
                    self.grafana_client.delete_user(grafana_user['id'])
                logger.info(f'User {grafana_user["login"]} / {grafana_user["email"]} has been deleted.')

        for waldur_user in self.waldur_users:
            if waldur_user.username not in [grafana_user['login'] for grafana_user in grafana_users]:
                if not DRY_RUN:
                    self.grafana_client.create_user(
                        email=waldur_user.email,
                        name=waldur_user.name,
                        login=waldur_user.username
                    )
                logger.info(f'User {waldur_user.username} / {waldur_user.email} has been created.')

    def _sync_teams(self, team_name, waldur_users):
        if not self.grafana_client.list_teams(team_name):
            if not DRY_RUN:
                team_id = self.grafana_client.create_team(team_name)['teamId']
            logger.info(f'Team {team_name} has been created.')
        else:
            team_id = self.grafana_client.list_teams(team_name)[0]['id']

        members = self.grafana_client.get_team_members(team_id)

        for member in members:
            if member['login'] not in [s.username for s in waldur_users]:
                if not DRY_RUN:
                    self.grafana_client.remove_team_member(team_id, member['userId'])
                logger.info(f'User {member["login"]} / {member["email"]} has been deleted from members of {team_name} / {team_id}.')

        for s in waldur_users:
            if s.username not in [member['login'] for member in members]:
                if not DRY_RUN:
                    self.grafana_client.create_team_member(team_id, s.name, s.username, s.email)
                logger.info(f'User {s.username} / {s.email} has been added to members of {team_name} / {team_id}.')

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

    def sync_organization_teams(self):
        teams = {}

        for user in self.waldur_users:
            for o in user.organizations:

                if [u for u in teams.get(o.division, []) if u.username == user.username]:
                    continue
                if o.division == '':
                    continue

                teams[o.division] = teams.get(o.division, []) + [user]

        for team_name in teams.keys():
            self._sync_teams(
                team_name=team_name,
                waldur_users=teams[team_name],
            )

        for grafana_team in self.grafana_client.list_teams():
            if grafana_team['name'] not in teams.keys() \
                    and grafana_team['name'] not in [STAFF_TEAM_NAME, SUPPORT_TEAM_NAME] + PROTECTED_TEAMS:
                if not DRY_RUN:
                    self.grafana_client.delete_teams(grafana_team['name'])
                logger.info(f'Team {grafana_team["name"]} has been deleted.')
